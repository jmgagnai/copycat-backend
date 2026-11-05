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
    user = await AuthRepository(db).create_user("ada@example.com", "x")
    assert user.email == "ada@example.com"
    assert await _count_ada(db) == 1


async def test_register_ada_again(db: AsyncSession) -> None:
    assert await _count_ada(db) == 0
    await AuthRepository(db).create_user("ada@example.com", "x")
    assert await _count_ada(db) == 1
