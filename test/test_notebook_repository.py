import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from notebook.notebook_entity import NotebookEntity
from notebook.notebook_repository import NotebookRepository


async def test_notebook_round_trip(db: AsyncSession) -> None:
    repo = NotebookRepository(db)

    notebook = await repo.create_notebook("Research")
    assert isinstance(notebook, NotebookEntity)
    assert isinstance(notebook.id, uuid.UUID) and notebook.created_at.tzinfo is not None
    assert notebook.deleted_at is None
    assert await repo.notebook_exists(notebook.id) is True

    renamed = await repo.rename_notebook(notebook.id, "Renamed")
    assert (
        renamed is not None and renamed.id == notebook.id and renamed.title == "Renamed"
    )

    deleted = await repo.soft_delete_notebook(notebook.id)
    assert (
        deleted is not None
        and deleted.id == notebook.id
        and deleted.deleted_at is not None
    )
    assert await repo.notebook_exists(notebook.id) is False
    assert await repo.soft_delete_notebook(notebook.id) is None
    assert await repo.rename_notebook(notebook.id, "x") is None

    restored = await repo.restore_notebook(notebook.id)
    assert isinstance(restored, NotebookEntity)
    assert (
        restored.id == notebook.id
        and restored.title == "Renamed"
        and restored.deleted_at is None
    )
    assert await repo.notebook_exists(notebook.id) is True
    assert await repo.restore_notebook(notebook.id) is None


async def test_unknown_notebook(db: AsyncSession) -> None:
    repo = NotebookRepository(db)
    missing = uuid.uuid4()
    assert await repo.notebook_exists(missing) is False
    assert await repo.rename_notebook(missing, "x") is None
    assert await repo.soft_delete_notebook(missing) is None
    assert await repo.restore_notebook(missing) is None


async def test_list_notebooks_is_live_only_and_oldest_first(db: AsyncSession) -> None:
    repo = NotebookRepository(db)
    first = await repo.create_notebook("First")
    second = await repo.create_notebook("Second")
    gone = await repo.create_notebook("Gone")
    await repo.soft_delete_notebook(gone.id)

    listed = await repo.list_notebooks()
    ids = [n.id for n in listed]
    assert gone.id not in ids
    assert ids.index(first.id) < ids.index(second.id)
    assert all(n.deleted_at is None for n in listed)
