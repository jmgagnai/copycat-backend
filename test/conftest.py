import os
import uuid
from collections.abc import AsyncIterator
from typing import Any

import asyncpg
import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, create_async_engine

from app.main import app
from db import get_db
from settings import settings
from storage import StoredObject

TEST_DATABASE_URL = os.environ.get("TEST_DATABASE_URL") or settings.DATABASE_URL
TEST_DSN = TEST_DATABASE_URL.replace("postgresql+asyncpg://", "postgresql://")


@pytest_asyncio.fixture(scope="session")
async def engine() -> AsyncIterator[AsyncEngine]:
    try:
        conn = await asyncpg.connect(TEST_DSN, timeout=3)
        await conn.close()
    except Exception as err:  # noqa: BLE001
        pytest.skip(f"No database at {TEST_DSN}: {err}")
    engine = create_async_engine(TEST_DATABASE_URL)
    yield engine
    await engine.dispose()


@pytest_asyncio.fixture
async def db(engine: AsyncEngine) -> AsyncIterator[AsyncSession]:
    async with engine.connect() as conn:
        await conn.begin()
        session = AsyncSession(
            bind=conn, join_transaction_mode="create_savepoint", expire_on_commit=False
        )
        try:
            yield session
        finally:
            await session.close()
            await conn.rollback()


class FakeStorage:
    def __init__(self) -> None:
        self.objects: dict[str, bytes] = {}

    async def put_object(self, key: str, body: bytes, content_type: str) -> None:
        self.objects[key] = body

    async def get_object(self, key: str) -> StoredObject:
        return StoredObject(
            body=self.objects[key], content_length=len(self.objects[key])
        )


class FakeJobs:
    def __init__(self) -> None:
        self.enqueued: list[tuple[uuid.UUID, uuid.UUID]] = []

    async def enqueue_convert_to_markdown(
        self, document_id: uuid.UUID, version_id: uuid.UUID
    ) -> None:
        self.enqueued.append((document_id, version_id))


@pytest_asyncio.fixture
async def client(db: AsyncSession) -> AsyncIterator[AsyncClient]:

    async def override_get_db() -> AsyncIterator[AsyncSession]:
        yield db

    app.dependency_overrides[get_db] = override_get_db
    app.state.storage = FakeStorage()
    app.state.jobs = FakeJobs()
    app.state.app_events = None
    app.state.chat = None
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as http:
        yield http
    app.dependency_overrides.clear()


async def sign_in(
    client: AsyncClient, email: str = "ada@example.com", password: str = "correct horse"
) -> dict[str, Any]:
    user = (
        await client.post("/auth/register", json={"email": email, "password": password})
    ).json()
    assert (
        await client.post("/auth/login", json={"email": email, "password": password})
    ).status_code == 200
    return user


async def create_notebook(
    client: AsyncClient, title: str = "Research"
) -> dict[str, Any]:
    response = await client.post("/notebooks", json={"title": title})
    assert response.status_code == 201
    return response.json()
