from __future__ import annotations

import uuid
from typing import Annotated, Literal

from fastapi import APIRouter, Path, Query

from .search_dto import SearchChatThreadsResponse, SearchNotebookResponse

router = APIRouter(prefix="/notebooks/{notebookId}/search", tags=["search"])


@router.get(
    "/",
    response_model=SearchNotebookResponse,
    summary="Search a Notebook's Documents by keyword. Returns each matching Chunk as an Excerpt with its matches marked; up to 20, best first.",
)
async def search_notebook(
    *,
    notebook_id: Annotated[uuid.UUID, Path(alias="notebookId")],
    q: Annotated[str | None, Query(max_length=1000)] = "",
    exact: Literal["true", "false"] | None = "false",
    # TODO: add authentication dependency, e.g.: current_user = Depends(get_auth_context)
) -> SearchNotebookResponse:
    """Full-text search over the Chunks of each Document's latest ready Version, accents and case ignored (no embedding, so it needs no OpenRouter key). A Document appears once per matching Chunk. A misspelt word is corrected to the closest word the Notebook holds unless exact=true; correctedQuery says what was searched. Per ADR-0001 there is no ownership check."""
    raise NotImplementedError


@router.get(
    "/threads",
    response_model=SearchChatThreadsResponse,
    summary="Search a Notebook's Chat Threads by keyword. Returns each matching Exchange — a question and the answer it produced — with its matches marked; up to 20, best first.",
)
async def search_chat_threads(
    *,
    notebook_id: Annotated[uuid.UUID, Path(alias="notebookId")],
    q: Annotated[str | None, Query(max_length=1000)] = "",
    exact: Literal["true", "false"] | None = "false",
    # TODO: add authentication dependency, e.g.: current_user = Depends(get_auth_context)
) -> SearchChatThreadsResponse:
    """Full-text search over questions and answers, accents and case ignored (no embedding, so it needs no OpenRouter key). A misspelt word is corrected as for Documents. Deleted Chat Threads are left out. Per ADR-0001 there is no ownership check."""
    raise NotImplementedError
