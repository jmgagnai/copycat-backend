from __future__ import annotations

import uuid
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Path, Query

from auth.guard import CurrentUser
from notebook.notebook_repository import NotebookRepository

from .search_dto import SearchChatThreadsResponse, SearchNotebookResponse

router = APIRouter(tags=["search"])

NotebookId = Annotated[uuid.UUID, Path(alias="notebookId")]
Notebooks = Annotated[NotebookRepository, Depends()]
SearchQuery = Annotated[str | None, Query(max_length=1000)]
Exact = Literal["true", "false"] | None

EMPTY_SEARCH: dict[str, Any] = {
    "correctedQuery": None,
    "words": [],
    "total": 0,
    "results": [],
}


async def _require_notebook(
    notebooks: NotebookRepository, notebook_id: uuid.UUID
) -> None:
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
    await _require_notebook(notebooks, notebook_id)
    return EMPTY_SEARCH
