from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Body, Depends, HTTPException

from auth.guard import CurrentUser

from .notebook_dto import CreateNotebookBody, NotebookResponse, RenameNotebookBody
from .notebook_service import NotebookService

# Full paths rather than a prefix: the contract is `/notebooks`, and a prefix with "/" would
# register `/notebooks/` and answer the bare path with a 307 redirect.
router = APIRouter(tags=["notebooks"])


@router.get(
    "/notebooks", response_model=list[NotebookResponse], summary="List all Notebooks"
)
async def list_notebooks(
    _: CurrentUser,
    notebook_service: Annotated[NotebookService, Depends()],
) -> list[NotebookResponse]:
    return [
        NotebookResponse.model_validate(n)
        for n in await notebook_service.list_notebooks()
    ]


@router.post(
    "/notebooks",
    response_model=NotebookResponse,
    status_code=201,
    summary="Create a Notebook",
)
async def create_notebook(
    *,
    notebook_service: Annotated[NotebookService, Depends()],
    body: Annotated[CreateNotebookBody, Body()],
    _: CurrentUser,
) -> NotebookResponse:
    notebook = await notebook_service.create_notebook(body.title)
    return NotebookResponse.model_validate(notebook)


@router.patch(
    "/notebooks/{id}", response_model=NotebookResponse, summary="Rename a Notebook"
)
async def rename_notebook(
    *,
    id: uuid.UUID,
    body: Annotated[RenameNotebookBody, Body()],
    notebook_service: Annotated[NotebookService, Depends()],
    _: CurrentUser,
) -> NotebookResponse:
    notebook = await notebook_service.rename_notebook(id, body.title)
    if notebook is None:
        raise HTTPException(404, "Notebook not found.")
    return NotebookResponse.model_validate(notebook)


@router.delete("/notebooks/{id}", status_code=204, summary="Soft-delete a Notebook")
async def delete_notebook(
    *,
    id: uuid.UUID,
    notebook_service: Annotated[NotebookService, Depends()],
    _: CurrentUser,
) -> None:
    if await notebook_service.delete_notebook(id) is None:
        raise HTTPException(404, "Notebook not found.")


@router.post(
    "/notebooks/{id}/restore",
    response_model=NotebookResponse,
    summary="Restore a soft-deleted Notebook",
)
async def restore_notebook(
    *,
    id: uuid.UUID,
    notebook_service: Annotated[NotebookService, Depends()],
    _: CurrentUser,
) -> NotebookResponse:
    notebook = await notebook_service.restore_notebook(id)
    if notebook is None:
        raise HTTPException(404, "Notebook not found.")
    return NotebookResponse.model_validate(notebook)
