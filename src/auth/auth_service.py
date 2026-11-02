from typing import Annotated

from fastapi import Depends

from .auth_entity import AuthEntity
from .auth_repository import AuthRepository
from .password import hash_password, verify_password


class AuthService:
    def __init__(self, repo: Annotated[AuthRepository, Depends()]):
        self.repo = repo

    async def register_new_user(self, email: str, raw_password: str) -> AuthEntity:
        hashed = await hash_password(raw_password)
        user = await self.repo.create_user(email=email, hashed_password=hashed)
        return user

    async def get_user(self, email: str) -> AuthEntity | None:
        return await self.repo.get_user(email=email)

    async def authenticate(self, email: str, raw_password: str) -> AuthEntity | None:
        user = await self.repo.get_user(email=email)
        if user is None:
            return user
        ok = await verify_password(raw_password, user.password_hash)
        if ok:
            return user
        return None
