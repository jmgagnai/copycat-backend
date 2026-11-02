import uuid
from typing import Annotated, Any

from fastapi import Depends
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from db import get_db
from notebook.notebook_entity import NotebookEntity

# Deleted Notebooks are kept in the database (soft delete): every read filters on deleted_at IS NULL.


def _to_entity(row: Any) -> NotebookEntity:
    """A `RETURNING id, title, created_at, deleted_at` row as an entity, column by column."""
    return NotebookEntity(
        id=row.id, title=row.title, created_at=row.created_at, deleted_at=row.deleted_at
    )


class NotebookRepository:
    def __init__(self, db: Annotated[AsyncSession, Depends(get_db)]):
        self.db = db

    async def notebook_exists(self, notebook_id: uuid.UUID) -> bool:
        stmt = select(NotebookEntity.id).where(
            NotebookEntity.id == notebook_id, NotebookEntity.deleted_at.is_(None)
        )
        return (await self.db.execute(stmt)).first() is not None

    async def list_notebooks(self) -> list[NotebookEntity]:
        stmt = (
            select(NotebookEntity)
            .where(NotebookEntity.deleted_at.is_(None))
            .order_by(NotebookEntity.created_at)
        )
        return list((await self.db.execute(stmt)).scalars())

    async def create_notebook(self, title: str) -> NotebookEntity:
        notebook = NotebookEntity(title=title)
        self.db.add(notebook)
        await self.db.commit()
        await self.db.refresh(notebook)
        return notebook

    async def rename_notebook(
        self, notebook_id: uuid.UUID, title: str
    ) -> NotebookEntity | None:
        stmt = text(
            "UPDATE notebooks SET title=:notebook_title "
            "WHERE id=:notebook_id AND deleted_at IS NULL "
            "RETURNING id, title, created_at, deleted_at"
        )
        result = await self.db.execute(
            stmt, {"notebook_id": notebook_id, "notebook_title": title}
        )
        row = result.first()
        await self.db.commit()
        return _to_entity(row) if row else None

    async def soft_delete_notebook(
        self, notebook_id: uuid.UUID
    ) -> NotebookEntity | None:
        stmt = text(
            "UPDATE notebooks SET deleted_at = now() "
            "WHERE id=:notebook_id AND deleted_at IS NULL "
            "RETURNING id, title, created_at, deleted_at"
        )
        result = await self.db.execute(stmt, {"notebook_id": notebook_id})
        row = result.first()
        await self.db.commit()
        return _to_entity(row) if row else None

    async def restore_notebook(self, notebook_id: uuid.UUID) -> NotebookEntity | None:
        stmt = text(
            "UPDATE notebooks SET deleted_at=NULL "
            "WHERE id=:notebook_id AND deleted_at IS NOT NULL "
            "RETURNING id, title, created_at, deleted_at"
        )
        result = await self.db.execute(stmt, {"notebook_id": notebook_id})
        row = result.first()
        await self.db.commit()
        return _to_entity(row) if row else None
