import uuid
from typing import Annotated, Any

from fastapi import Depends
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from db import get_db, rowcount

from .chat_dto import (
    ChatMessageResponse,
    ChatParticipant,
    ChatThreadResponse,
    CitationResponse,
)
from .citations import ResolvedCitation

SELECT_THREAD = """
  SELECT t.id, t.notebook_id, t.title, t.created_at, u.id AS author_id, u.email AS author_email
  FROM chat_threads t JOIN users u ON u.id = t.created_by
"""
LIVE_NOTEBOOK_JOIN = "JOIN notebooks n ON n.id = t.notebook_id AND n.deleted_at IS NULL"
SELECT_MESSAGE = """
  SELECT m.id, m.chat_thread_id, m.role, m.content, m.created_at, u.id AS asked_by_id, u.email AS asked_by_email
  FROM chat_messages m JOIN users u ON u.id = m.asked_by
"""
SELECT_CITATIONS = """
  SELECT ci.id, ci.chat_message_id, ci.marker, v.document_id, ci.document_version_id, v.version_number,
         ci.chunk_id, d.filename, c.heading_path, ci.char_start, ci.char_end
  FROM citations ci
  JOIN chunks c ON c.id = ci.chunk_id
  JOIN document_versions v ON v.id = ci.document_version_id
  JOIN documents d ON d.id = v.document_id
  WHERE ci.chat_message_id = ANY(CAST(:ids AS uuid[]))
  ORDER BY ci.chat_message_id, ci.marker
"""
INSERT_MESSAGE = """
  WITH inserted AS (
    INSERT INTO chat_messages (chat_thread_id, asked_by, role, content)
    VALUES (:thread_id, :asked_by, :role, :content)
    RETURNING id, chat_thread_id, role, content, created_at, asked_by
  )
  SELECT i.id, i.chat_thread_id, i.role, i.content, i.created_at, u.id AS asked_by_id, u.email AS asked_by_email
  FROM inserted i JOIN users u ON u.id = i.asked_by
"""


def to_chat_thread(row: Any) -> ChatThreadResponse:
    return ChatThreadResponse(
        id=row.id,
        notebook_id=row.notebook_id,
        title=row.title,
        author=ChatParticipant(id=row.author_id, email=row.author_email),
        created_at=row.created_at,
    )


def to_citation(row: Any) -> CitationResponse:
    return CitationResponse(
        id=row.id,
        marker=row.marker,
        document_id=row.document_id,
        document_version_id=row.document_version_id,
        version_number=row.version_number,
        chunk_id=row.chunk_id,
        filename=row.filename,
        heading_path=list(row.heading_path),
        char_start=row.char_start,
        char_end=row.char_end,
    )


def to_chat_message(
    row: Any, citations: list[CitationResponse] | None = None
) -> ChatMessageResponse:
    return ChatMessageResponse(
        id=row.id,
        thread_id=row.chat_thread_id,
        role=row.role,
        content=row.content,
        asked_by=ChatParticipant(id=row.asked_by_id, email=row.asked_by_email),
        citations=citations or [],
        created_at=row.created_at,
    )


class ChatRepository:
    def __init__(self, db: Annotated[AsyncSession, Depends(get_db)]):
        self.db = db

    async def list_chat_threads(
        self, notebook_id: uuid.UUID
    ) -> list[ChatThreadResponse]:
        rows = await self.db.execute(
            text(
                f"{SELECT_THREAD} WHERE t.notebook_id = :id AND t.deleted_at IS NULL ORDER BY t.created_at DESC, t.id DESC"
            ),
            {"id": notebook_id},
        )
        return [to_chat_thread(r) for r in rows]

    async def find_chat_thread(
        self, notebook_id: uuid.UUID, thread_id: uuid.UUID
    ) -> ChatThreadResponse | None:
        row = (
            await self.db.execute(
                text(
                    f"{SELECT_THREAD} {LIVE_NOTEBOOK_JOIN}"
                    " WHERE t.id = :id AND t.notebook_id = :notebook_id AND t.deleted_at IS NULL"
                ),
                {"id": thread_id, "notebook_id": notebook_id},
            )
        ).first()
        return to_chat_thread(row) if row else None

    async def create_chat_thread(
        self, notebook_id: uuid.UUID, title: str, author_id: uuid.UUID
    ) -> ChatThreadResponse:
        thread_id: uuid.UUID = (
            await self.db.execute(
                text(
                    "INSERT INTO chat_threads (notebook_id, title, created_by) VALUES (:notebook_id, :title, :author) RETURNING id"
                ),
                {"notebook_id": notebook_id, "title": title, "author": author_id},
            )
        ).scalar_one()
        await self.db.commit()
        thread = await self.find_chat_thread(notebook_id, thread_id)
        if thread is None:
            raise RuntimeError("Chat Thread vanished immediately after it was created.")
        return thread

    async def _update_thread(
        self, set_clause: str, where: str, params: dict[str, Any]
    ) -> bool:
        result = await self.db.execute(
            text(
                f"UPDATE chat_threads t SET {set_clause} FROM notebooks n"
                f" WHERE t.id = :id AND t.notebook_id = :notebook_id AND {where}"
                " AND n.id = t.notebook_id AND n.deleted_at IS NULL"
            ),
            params,
        )
        await self.db.commit()
        return rowcount(result) == 1

    async def delete_chat_thread(
        self, notebook_id: uuid.UUID, thread_id: uuid.UUID
    ) -> bool:
        return await self._update_thread(
            "deleted_at = now()",
            "t.deleted_at IS NULL",
            {"id": thread_id, "notebook_id": notebook_id},
        )

    async def restore_chat_thread(
        self, notebook_id: uuid.UUID, thread_id: uuid.UUID
    ) -> ChatThreadResponse | None:
        if not await self._update_thread(
            "deleted_at = NULL",
            "t.deleted_at IS NOT NULL",
            {"id": thread_id, "notebook_id": notebook_id},
        ):
            return None
        return await self.find_chat_thread(notebook_id, thread_id)

    async def rename_chat_thread(
        self, notebook_id: uuid.UUID, thread_id: uuid.UUID, title: str
    ) -> ChatThreadResponse | None:
        if not await self._update_thread(
            "title = :title",
            "t.deleted_at IS NULL",
            {"id": thread_id, "notebook_id": notebook_id, "title": title},
        ):
            return None
        return await self.find_chat_thread(notebook_id, thread_id)

    async def _citations_by_message(
        self, message_ids: list[uuid.UUID]
    ) -> dict[uuid.UUID, list[CitationResponse]]:
        grouped: dict[uuid.UUID, list[CitationResponse]] = {}
        if message_ids:
            for row in await self.db.execute(
                text(SELECT_CITATIONS), {"ids": message_ids}
            ):
                grouped.setdefault(row.chat_message_id, []).append(to_citation(row))
        return grouped

    async def list_chat_messages(
        self, thread_id: uuid.UUID
    ) -> list[ChatMessageResponse]:
        rows = list(
            await self.db.execute(
                text(f"{SELECT_MESSAGE} WHERE m.chat_thread_id = :id ORDER BY m.seq"),
                {"id": thread_id},
            )
        )
        citations = await self._citations_by_message([r.id for r in rows])
        return [to_chat_message(r, citations.get(r.id)) for r in rows]

    async def append_question_and_answer(
        self,
        thread_id: uuid.UUID,
        asker_id: uuid.UUID,
        question: str,
        answer: str,
        citations: list[ResolvedCitation],
    ) -> tuple[ChatMessageResponse, ChatMessageResponse]:
        base = {"thread_id": thread_id, "asked_by": asker_id}
        question_row = (
            await self.db.execute(
                text(INSERT_MESSAGE), {**base, "role": "user", "content": question}
            )
        ).one()
        answer_row = (
            await self.db.execute(
                text(INSERT_MESSAGE), {**base, "role": "assistant", "content": answer}
            )
        ).one()
        for citation in citations:
            await self.db.execute(
                text(
                    "INSERT INTO citations (chat_message_id, document_version_id, chunk_id, marker, char_start, char_end)"
                    " VALUES (:message_id, :version_id, :chunk_id, :marker, :char_start, :char_end)"
                ),
                {
                    "message_id": answer_row.id,
                    "version_id": citation.chunk.document_version_id,
                    "chunk_id": citation.chunk.chunk_id,
                    "marker": citation.marker,
                    "char_start": citation.char_start,
                    "char_end": citation.char_end,
                },
            )
        written = await self._citations_by_message([answer_row.id])
        await self.db.commit()
        return to_chat_message(question_row), to_chat_message(
            answer_row, written.get(answer_row.id)
        )
