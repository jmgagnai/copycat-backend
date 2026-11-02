import uuid
from typing import Annotated

from fastapi import Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from db import get_db

from .auth_entity import AuthEntity


class AuthRepository:
    def __init__(self, db: Annotated[AsyncSession, Depends(get_db)]):
        self.db = db

    async def create_user(self, email: str, hashed_password: str) -> AuthEntity:
        new_user = AuthEntity(email=email, password_hash=hashed_password)
        self.db.add(new_user)
        await self.db.commit()
        await self.db.refresh(new_user)
        return new_user

    async def get_user(self, email: str) -> AuthEntity | None:
        statement = select(AuthEntity).where(AuthEntity.email == email)
        result = await self.db.execute(statement)
        return result.scalar_one_or_none()

    async def get_user_by_id(self, id: uuid.UUID) -> AuthEntity | None:
        statement = select(AuthEntity).where(AuthEntity.id == id)
        result = await self.db.execute(statement)
        return result.scalar_one_or_none()
