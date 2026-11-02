import uuid
from typing import Annotated

from fastapi import Depends

from notebook.notebook_entity import NotebookEntity
from notebook.notebook_repository import NotebookRepository


class NotebookService:
    """Per ADR-0001 there is no ownership check: any authenticated user sees every Notebook."""

    def __init__(self, repo: Annotated[NotebookRepository, Depends()]):
        self.repo = repo

    async def list_notebooks(self) -> list[NotebookEntity]:
        return await self.repo.list_notebooks()

    async def create_notebook(self, title: str) -> NotebookEntity:
        return await self.repo.create_notebook(title)

    async def rename_notebook(
        self, notebook_id: uuid.UUID, title: str
    ) -> NotebookEntity | None:
        return await self.repo.rename_notebook(notebook_id, title)

    async def delete_notebook(self, notebook_id: uuid.UUID) -> NotebookEntity | None:
        return await self.repo.soft_delete_notebook(notebook_id)

    async def restore_notebook(self, notebook_id: uuid.UUID) -> NotebookEntity | None:
        return await self.repo.restore_notebook(notebook_id)
