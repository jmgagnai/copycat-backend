"""T05 steps 2 and 3: the harness itself."""

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from auth.auth_repository import AuthRepository


async def test_engine(engine: AsyncEngine) -> None:
    assert engine is not None


async def _count_ada(db: AsyncSession) -> int:
    sql = text("SELECT count(*) FROM users WHERE email = 'ada@example.com'")
    return (await db.execute(sql)).scalar_one()


async def test_register_ada_once(db: AsyncSession) -> None:
    assert await _count_ada(db) == 0
    user = await AuthRepository(db).create_user(
        "ada@example.com", "x"
    )  # commits: a savepoint release
    assert user.email == "ada@example.com"
    assert await _count_ada(db) == 1  # visible inside this transaction


async def test_register_ada_again(db: AsyncSession) -> None:
    assert await _count_ada(db) == 0  # the previous test left nothing
    await AuthRepository(db).create_user("ada@example.com", "x")
    assert await _count_ada(db) == 1
