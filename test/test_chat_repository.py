"""T15 step 2's DONE WHEN, at the repository level. Runs on the T05 `db` fixture: everything is
rolled back, and no route or LLM is involved."""

import uuid

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from chat.chat_dto import ChatThreadResponse
from chat.chat_repository import ChatRepository


async def seed_user_and_notebook(db: AsyncSession) -> tuple[uuid.UUID, str, uuid.UUID]:
    """A user and a Notebook by SQL: a repository test must not depend on the routes."""
    user_email = f"{uuid.uuid4().hex[:8]}@example.com"
    user_id: uuid.UUID = (
        await db.execute(
            text(
                "INSERT INTO users (email, password_hash) VALUES (:email, 'x') RETURNING id"
            ),
            {"email": user_email},
        )
    ).scalar_one()
    nb_id: uuid.UUID = (
        await db.execute(
            text("INSERT INTO notebooks (title) VALUES ('N') RETURNING id")
        )
    ).scalar_one()
    await db.commit()
    return user_id, user_email, nb_id


async def test_create_chat_thread_returns_its_author(db: AsyncSession) -> None:
    user_id, user_email, nb_id = await seed_user_and_notebook(db)

    thread = await ChatRepository(db).create_chat_thread(nb_id, "Hello", user_id)

    assert isinstance(thread, ChatThreadResponse)
    assert thread.author.email == user_email
    assert thread.author.id == user_id
    assert thread.notebook_id == nb_id and thread.title == "Hello"


async def test_chat_thread_round_trip(db: AsyncSession) -> None:
    user_id, _, nb_id = await seed_user_and_notebook(db)
    repo = ChatRepository(db)
    thread = await repo.create_chat_thread(nb_id, "Hello", user_id)

    assert [t.id for t in await repo.list_chat_threads(nb_id)] == [thread.id]
    renamed = await repo.rename_chat_thread(nb_id, thread.id, "Renamed")
    assert renamed is not None and renamed.title == "Renamed"
    assert await repo.list_chat_messages(thread.id) == []

    assert await repo.delete_chat_thread(nb_id, thread.id) is True
    assert await repo.find_chat_thread(nb_id, thread.id) is None
    assert await repo.list_chat_threads(nb_id) == []
    assert await repo.delete_chat_thread(nb_id, thread.id) is False  # already gone

    restored = await repo.restore_chat_thread(nb_id, thread.id)
    assert restored is not None and restored.id == thread.id
    assert await repo.restore_chat_thread(nb_id, thread.id) is None  # not deleted


async def test_a_deleted_notebook_hides_and_freezes_its_threads(
    db: AsyncSession,
) -> None:
    user_id, _, nb_id = await seed_user_and_notebook(db)
    repo = ChatRepository(db)
    thread = await repo.create_chat_thread(nb_id, "Hello", user_id)

    await db.execute(
        text("UPDATE notebooks SET deleted_at = now() WHERE id = :id"), {"id": nb_id}
    )
    await db.commit()

    assert await repo.find_chat_thread(nb_id, thread.id) is None
    assert await repo.rename_chat_thread(nb_id, thread.id, "Nope") is None
    assert await repo.delete_chat_thread(nb_id, thread.id) is False
