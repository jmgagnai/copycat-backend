"""The seven chat routes: six CRUD routes over Chat Threads and their messages (T15), and asking
a question (T16). Per ADR-0001 anyone may read, rename and continue a Thread; its amendment adds
the author rule on delete and the Administrator rule on restore, both enforced here."""

from __future__ import annotations

import logging
import uuid
from typing import Annotated

from fastapi import APIRouter, Body, Depends, HTTPException, Path, Request
from sqlalchemy.ext.asyncio import AsyncSession

from auth.guard import CurrentUser
from db import get_db
from notebook.notebook_repository import NotebookRepository
from settings import settings

from .chat_dto import (
    ChatMessageResponse,
    ChatThreadResponse,
    CreateChatThreadBody,
    RenameChatThreadBody,
    SendChatMessageBody,
    SendChatMessageResponse,
)
from .chat_repository import ChatRepository
from .chat_service import ChatDeps, stream_answer
from .streaming import AnswerStream

router = APIRouter(tags=["chat"])
log = logging.getLogger("chat")

NotebookId = Annotated[uuid.UUID, Path(alias="notebookId")]
ThreadId = Annotated[uuid.UUID, Path(alias="threadId")]
Threads = Annotated[ChatRepository, Depends()]
Notebooks = Annotated[NotebookRepository, Depends()]


def get_chat_deps(request: Request) -> ChatDeps | None:
    """The OpenRouter-backed answer path, built once in the lifespan; absent (no
    OPENROUTER_API_KEY), asking reports 503."""
    return getattr(request.app.state, "chat", None)


@router.get(
    "/notebooks/{notebookId}/threads",
    response_model=list[ChatThreadResponse],
    summary="List every Chat Thread in a Notebook",
)
async def list_chat_threads(
    *, notebook_id: NotebookId, _: CurrentUser, repo: Threads, notebooks: Notebooks
) -> list[ChatThreadResponse]:
    if not await notebooks.notebook_exists(notebook_id):
        raise HTTPException(404, "Notebook not found.")
    return await repo.list_chat_threads(notebook_id)


@router.post(
    "/notebooks/{notebookId}/threads",
    response_model=ChatThreadResponse,
    status_code=201,
    summary="Start a Chat Thread in a Notebook",
)
async def create_chat_thread(
    *,
    notebook_id: NotebookId,
    body: Annotated[CreateChatThreadBody, Body()],
    user: CurrentUser,
    repo: Threads,
    notebooks: Notebooks,
) -> ChatThreadResponse:
    if not await notebooks.notebook_exists(notebook_id):
        raise HTTPException(404, "Notebook not found.")
    return await repo.create_chat_thread(notebook_id, body.title, user.id)


@router.patch(
    "/notebooks/{notebookId}/threads/{threadId}",
    response_model=ChatThreadResponse,
    summary="Rename a Chat Thread",
)
async def rename_chat_thread(
    *,
    notebook_id: NotebookId,
    thread_id: ThreadId,
    body: Annotated[RenameChatThreadBody, Body()],
    _: CurrentUser,
    repo: Threads,
) -> ChatThreadResponse:
    thread = await repo.rename_chat_thread(notebook_id, thread_id, body.title)
    if thread is None:
        raise HTTPException(404, "Chat Thread not found.")
    return thread


@router.delete(
    "/notebooks/{notebookId}/threads/{threadId}",
    status_code=204,
    summary="Delete a Chat Thread (its author only)",
)
async def delete_chat_thread(
    *, notebook_id: NotebookId, thread_id: ThreadId, user: CurrentUser, repo: Threads
) -> None:
    """Soft-deletes the Chat Thread: its messages and Citations are kept and an Administrator can
    restore it. Only the user who started the Thread may delete it (ADR-0001 amendment)."""
    thread = await repo.find_chat_thread(notebook_id, thread_id)
    if thread is None:
        raise HTTPException(404, "Chat Thread not found.")
    if thread.author.id != user.id:
        raise HTTPException(
            403, "Only the user who started a Chat Thread may delete it."
        )
    await repo.delete_chat_thread(notebook_id, thread_id)
    # There is no list of deleted Threads: this line is how an Administrator finds one to restore.
    log.info(
        'Chat Thread deleted: id=%s title="%s" notebook=%s author=%s',
        thread_id,
        thread.title,
        notebook_id,
        thread.author.email,
    )


@router.post(
    "/notebooks/{notebookId}/threads/{threadId}/restore",
    response_model=ChatThreadResponse,
    summary="Restore a deleted Chat Thread (Administrator only)",
)
async def restore_chat_thread(
    *, notebook_id: NotebookId, thread_id: ThreadId, user: CurrentUser, repo: Threads
) -> ChatThreadResponse:
    """Only an Administrator (a user whose email is in `ADMIN_EMAILS`) may call it."""
    if user.email.lower() not in settings.administrators:
        raise HTTPException(403, "Only an Administrator may restore a Chat Thread.")
    thread = await repo.restore_chat_thread(notebook_id, thread_id)
    if thread is None:
        raise HTTPException(404, "No deleted Chat Thread by that id.")
    return thread


@router.get(
    "/notebooks/{notebookId}/threads/{threadId}/messages",
    response_model=list[ChatMessageResponse],
    summary="Read every message in a Chat Thread, in the order they were asked",
)
async def list_chat_messages(
    *, notebook_id: NotebookId, thread_id: ThreadId, _: CurrentUser, repo: Threads
) -> list[ChatMessageResponse]:
    thread = await repo.find_chat_thread(notebook_id, thread_id)
    if thread is None:
        raise HTTPException(404, "Chat Thread not found.")
    return await repo.list_chat_messages(thread.id)


@router.post(
    "/notebooks/{notebookId}/threads/{threadId}/messages",
    response_model=SendChatMessageResponse,
    status_code=201,
    summary="Ask a question in a Chat Thread and get one grounded answer",
)
async def send_chat_message(
    *,
    notebook_id: NotebookId,
    thread_id: ThreadId,
    body: Annotated[SendChatMessageBody, Body()],
    user: CurrentUser,
    repo: Threads,
    # The same session serves the repository, the stream and retrieval.
    db: Annotated[AsyncSession, Depends(get_db)],
    chat: Annotated[ChatDeps | None, Depends(get_chat_deps)],
) -> SendChatMessageResponse:
    """Retrieves the closest Chunks from the Notebook's latest-version `ready` Documents and
    returns the complete recorded exchange. While the answer is generated it is also published
    to `GET /events` as `chat-answer-chunk` events, then one `chat-answer-completed` naming the
    persisted message and carrying its Citations; this response is the authoritative result."""
    thread = await repo.find_chat_thread(notebook_id, thread_id)
    if thread is None:
        raise HTTPException(404, "Chat Thread not found.")
    if chat is None:
        raise HTTPException(
            503,
            "Chat is not configured on this server: OPENROUTER_API_KEY is not set.",
        )

    # Read before writing: the question being asked must not appear in its own history.
    history = await repo.list_chat_messages(thread.id)
    stream = AnswerStream(db, thread.notebook_id, thread.id)
    try:
        answer = await stream_answer(
            db, chat, thread.notebook_id, body.content, history, stream.chunk
        )
    except Exception as err:
        # Nothing is recorded: asking again is the retry, and the preview others saw is dropped.
        log.exception("A chat answer could not be generated.")
        await stream.failed(str(err))
        raise HTTPException(
            502,
            "The answer could not be generated. Nothing was recorded; please ask again.",
        ) from None

    question, recorded = await repo.append_question_and_answer(
        thread.id, user.id, body.content, answer.text, answer.citations
    )
    await stream.completed(recorded.id, question.id, recorded.citations)
    return SendChatMessageResponse(question=question, answer=recorded)
