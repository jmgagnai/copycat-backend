"""Keyword search, stubbed (T17): both routes check the Notebook and answer the empty result.
The full-text search itself was dropped; "If you pick it up later" in the task doc says how."""

from __future__ import annotations

import uuid
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Path, Query

from auth.guard import CurrentUser
from notebook.notebook_repository import NotebookRepository

from .search_dto import SearchChatThreadsResponse, SearchNotebookResponse

# Full paths, no prefix: a prefix plus "/" would make the route "/search/" and redirect "/search".
router = APIRouter(tags=["search"])

NotebookId = Annotated[uuid.UUID, Path(alias="notebookId")]
Notebooks = Annotated[NotebookRepository, Depends()]
SearchQuery = Annotated[str | None, Query(max_length=1000)]
Exact = Literal["true", "false"] | None

# The empty shape of both responses is the same four keys.
EMPTY_SEARCH: dict[str, Any] = {
    "correctedQuery": None,
    "words": [],
    "total": 0,
    "results": [],
}


async def _require_notebook(
    notebooks: NotebookRepository, notebook_id: uuid.UUID
) -> None:
    """An unknown or deleted Notebook answers 404, not an empty result."""
    if not await notebooks.notebook_exists(notebook_id):
        raise HTTPException(404, "Notebook not found.")


@router.get(
    "/notebooks/{notebookId}/search",
    response_model=SearchNotebookResponse,
    summary="Search a Notebook's Documents by keyword. Returns each matching Chunk as an Excerpt with its matches marked; up to 20, best first.",
)
async def search_notebook(
    *,
    notebook_id: NotebookId,
    q: SearchQuery = "",
    exact: Exact = "false",
    _: CurrentUser,
    notebooks: Notebooks,
) -> dict[str, Any]:
    """Full-text search over the Chunks of each Document's latest ready Version, accents and case ignored (no embedding, so it needs no OpenRouter key). A Document appears once per matching Chunk. A misspelt word is corrected to the closest word the Notebook holds unless exact=true; correctedQuery says what was searched. Per ADR-0001 there is no ownership check."""
    await _require_notebook(notebooks, notebook_id)
    return EMPTY_SEARCH


@router.get(
    "/notebooks/{notebookId}/search/threads",
    response_model=SearchChatThreadsResponse,
    summary="Search a Notebook's Chat Threads by keyword. Returns each matching Exchange — a question and the answer it produced — with its matches marked; up to 20, best first.",
)
async def search_chat_threads(
    *,
    notebook_id: NotebookId,
    q: SearchQuery = "",
    exact: Exact = "false",
    _: CurrentUser,
    notebooks: Notebooks,
) -> dict[str, Any]:
    """Full-text search over questions and answers, accents and case ignored (no embedding, so it needs no OpenRouter key). A misspelt word is corrected as for Documents. Deleted Chat Threads are left out. Per ADR-0001 there is no ownership check."""
    await _require_notebook(notebooks, notebook_id)
    return EMPTY_SEARCH
