from __future__ import annotations

import uuid
from typing import Annotated, Any

from fastapi import APIRouter, Body

from .models import (
    CreateNotebookBody,
    CreateNotebookResponse,
    RenameNotebookBody,
    RenameNotebookResponse,
    RestoreNotebookResponse,
)

router = APIRouter(tags=["notebooks"])


@router.get(
    "/notebooks", response_model=list[dict[str, Any]], summary="List all Notebooks"
)
async def list_notebooks(
    # TODO: add authentication dependency, e.g.: current_user = Depends(get_auth_context)
) -> list[dict[str, Any]]:
    raise NotImplementedError


@router.post(
    "/notebooks",
    response_model=CreateNotebookResponse,
    status_code=201,
    summary="Create a Notebook",
)
async def create_notebook(
    *,
    body: Annotated[CreateNotebookBody, Body()],
    # TODO: add authentication dependency, e.g.: current_user = Depends(get_auth_context)
) -> CreateNotebookResponse:
    raise NotImplementedError


@router.patch(
    "/notebooks/{id}",
    response_model=RenameNotebookResponse,
    summary="Rename a Notebook",
)
async def rename_notebook(
    *,
    id: uuid.UUID,
    body: Annotated[RenameNotebookBody, Body()],
    # TODO: add authentication dependency, e.g.: current_user = Depends(get_auth_context)
) -> RenameNotebookResponse:
    raise NotImplementedError


@router.delete("/notebooks/{id}", status_code=204, summary="Soft-delete a Notebook")
async def delete_notebook(
    *,
    id: uuid.UUID,
    # TODO: add authentication dependency, e.g.: current_user = Depends(get_auth_context)
) -> None:
    raise NotImplementedError


@router.post(
    "/notebooks/{id}/restore",
    response_model=RestoreNotebookResponse,
    summary="Restore a soft-deleted Notebook",
)
async def restore_notebook(
    *,
    id: uuid.UUID,
    # TODO: add authentication dependency, e.g.: current_user = Depends(get_auth_context)
) -> RestoreNotebookResponse:
    raise NotImplementedError
