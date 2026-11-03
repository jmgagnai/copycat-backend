import uuid
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from event.events_bus import publish_app_event
from event.events_dto import AppEventDraft, notebook_topic

from .chat_dto import CitationResponse

# The three app-event types a streamed answer travels as (NBK-11), on the Notebook's topic
# because a Chat Thread is shared: everyone with the Notebook open watches the answer arrive.
CHAT_ANSWER_CHUNK = "chat-answer-chunk"
CHAT_ANSWER_COMPLETED = "chat-answer-completed"
CHAT_ANSWER_FAILED = "chat-answer-failed"


class AnswerChunker:
    """Turns a model's token stream into the pieces a reader is shown: one per paragraph, released
    when the blank line after it arrives. Nothing is released early, so a chunk is never revised."""

    def __init__(self) -> None:
        self.buffer = ""

    def push(self, delta: str) -> list[str]:
        self.buffer += delta.replace("\r\n", "\n")
        *done, self.buffer = self.buffer.split("\n\n")
        return [piece.strip() for piece in done if piece.strip()]

    def flush(self) -> list[str]:
        last, self.buffer = self.buffer.strip(), ""
        return [last] if last else []


class AnswerStream:
    """Publishes one answer's progress onto the app-event channel. `stream_id` is minted before
    the answer exists; clients learn the row's id from the completion event."""

    def __init__(self, db: AsyncSession, notebook_id: uuid.UUID, thread_id: uuid.UUID):
        self.db = db
        self.index = 0
        self.identity = {
            "notebookId": str(notebook_id),
            "threadId": str(thread_id),
            "streamId": str(uuid.uuid4()),
        }
        self.topic = notebook_topic(notebook_id)

    async def _publish(self, type: str, data: dict[str, Any]) -> None:
        await publish_app_event(
            self.db,
            AppEventDraft(type=type, topic=self.topic, data={**self.identity, **data}),
        )
        await self.db.commit()

    async def chunk(self, text: str) -> None:
        # `index` lets a client notice it joined mid-answer and re-read the Thread instead.
        await self._publish(CHAT_ANSWER_CHUNK, {"index": self.index, "text": text})
        self.index += 1

    async def completed(
        self,
        message_id: uuid.UUID,
        question_id: uuid.UUID,
        citations: list[CitationResponse],
    ) -> None:
        # Citations ride the completion event: they can only be resolved from the complete text.
        data = {"messageId": str(message_id), "questionId": str(question_id)}
        await self._publish(
            CHAT_ANSWER_COMPLETED,
            {
                **data,
                "citations": [
                    c.model_dump(by_alias=True, mode="json") for c in citations
                ],
            },
        )

    async def failed(self, reason: str) -> None:
        await self._publish(CHAT_ANSWER_FAILED, {"reason": reason})
