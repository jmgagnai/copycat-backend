from __future__ import annotations

import uuid
from typing import Annotated, Any

from fastapi import APIRouter, Body, Path

from .models import (
    CreateChatThreadBody,
    CreateChatThreadResponse,
    RenameChatThreadBody,
    RenameChatThreadResponse,
    RestoreChatThreadResponse,
    SendChatMessageBody,
    SendChatMessageResponse,
)

router = APIRouter(tags=["chat"])


@router.get(
    "/notebooks/{notebookId}/threads",
    response_model=list[dict[str, Any]],
    summary="List every Chat Thread in a Notebook",
)
async def list_chat_threads(
    *,
    notebook_id: Annotated[uuid.UUID, Path(alias="notebookId")],
    # TODO: add authentication dependency, e.g.: current_user = Depends(get_auth_context)
) -> list[dict[str, Any]]:
    raise NotImplementedError


@router.post(
    "/notebooks/{notebookId}/threads",
    response_model=CreateChatThreadResponse,
    status_code=201,
    summary="Start a Chat Thread in a Notebook",
)
async def create_chat_thread(
    *,
    notebook_id: Annotated[uuid.UUID, Path(alias="notebookId")],
    body: Annotated[CreateChatThreadBody, Body()],
    # TODO: add authentication dependency, e.g.: current_user = Depends(get_auth_context)
) -> CreateChatThreadResponse:
    raise NotImplementedError


@router.patch(
    "/notebooks/{notebookId}/threads/{threadId}",
    response_model=RenameChatThreadResponse,
    summary="Rename a Chat Thread",
)
async def rename_chat_thread(
    *,
    notebook_id: Annotated[uuid.UUID, Path(alias="notebookId")],
    thread_id: Annotated[uuid.UUID, Path(alias="threadId")],
    body: Annotated[RenameChatThreadBody, Body()],
    # TODO: add authentication dependency, e.g.: current_user = Depends(get_auth_context)
) -> RenameChatThreadResponse:
    raise NotImplementedError


@router.delete(
    "/notebooks/{notebookId}/threads/{threadId}",
    status_code=204,
    summary="Delete a Chat Thread (its author only)",
)
async def delete_chat_thread(
    *,
    notebook_id: Annotated[uuid.UUID, Path(alias="notebookId")],
    thread_id: Annotated[uuid.UUID, Path(alias="threadId")],
    # TODO: add authentication dependency, e.g.: current_user = Depends(get_auth_context)
) -> None:
    """Soft-deletes the Chat Thread: it leaves the list and every route answers 404 for it, but its messages and their Citations are kept, and an Administrator can restore it. Only the user who started the Thread may delete it (ADR-0001 amendment)."""
    raise NotImplementedError


@router.get(
    "/notebooks/{notebookId}/threads/{threadId}/messages",
    response_model=list[dict[str, Any]],
    summary="Read every message in a Chat Thread, in the order they were asked",
)
async def list_chat_messages(
    *,
    notebook_id: Annotated[uuid.UUID, Path(alias="notebookId")],
    thread_id: Annotated[uuid.UUID, Path(alias="threadId")],
    # TODO: add authentication dependency, e.g.: current_user = Depends(get_auth_context)
) -> list[dict[str, Any]]:
    raise NotImplementedError


@router.post(
    "/notebooks/{notebookId}/threads/{threadId}/messages",
    response_model=SendChatMessageResponse,
    status_code=201,
    summary="Ask a question in a Chat Thread and get one grounded answer",
)
async def send_chat_message(
    *,
    notebook_id: Annotated[uuid.UUID, Path(alias="notebookId")],
    thread_id: Annotated[uuid.UUID, Path(alias="threadId")],
    body: Annotated[SendChatMessageBody, Body()],
    # TODO: add authentication dependency, e.g.: current_user = Depends(get_auth_context)
) -> SendChatMessageResponse:
    """Retrieves the closest Chunks from the Notebook's latest-version, `ready` Documents and returns the complete recorded exchange. While the answer is being generated it is also published to the live `GET /events` stream as `chat-answer-chunk` events in paragraph/heading-sized pieces, followed by one `chat-answer-completed` event naming the persisted message and carrying its Citations — so a client can render the answer progressively and this response is the authoritative result. The answer message carries a Citation per source marker in its text, each pinned to the exact Document Version and chunk it was grounded in and persisted with the message."""
    raise NotImplementedError


@router.post(
    "/notebooks/{notebookId}/threads/{threadId}/restore",
    response_model=RestoreChatThreadResponse,
    summary="Restore a deleted Chat Thread (Administrator only)",
)
async def restore_chat_thread(
    *,
    notebook_id: Annotated[uuid.UUID, Path(alias="notebookId")],
    thread_id: Annotated[uuid.UUID, Path(alias="threadId")],
    # TODO: add authentication dependency, e.g.: current_user = Depends(get_auth_context)
) -> RestoreChatThreadResponse:
    """Brings a deleted Chat Thread back with its messages. Only an Administrator — a user whose email is in the backend's `ADMIN_EMAILS` — may call it; the app's UI never does. See docs/administration.md."""
    raise NotImplementedError
