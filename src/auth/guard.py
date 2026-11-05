import uuid
from typing import Annotated

from fastapi import Depends, HTTPException
from fastapi.security import APIKeyCookie

from . import AuthEntity, AuthRepository
from .auth_jwt import verify_session_token
from .cookie import SESSION_COOKIE_NAME

session_cookie = APIKeyCookie(
    name=SESSION_COOKIE_NAME,
    scheme_name="sessionCookie",
    description="The session cookie issued by `POST /auth/login`.",
    auto_error=False,
)


async def get_current_user(
    repo: Annotated[AuthRepository, Depends()],
    session: Annotated[str | None, Depends(session_cookie)],
) -> AuthEntity:
    user_id = verify_session_token(session) if session else None
    if not user_id:
        raise HTTPException(status_code=401, detail="Authentication required.")
    try:
        user = await repo.get_user_by_id(uuid.UUID(user_id))
    except ValueError:
        user = None
    if user is None:
        raise HTTPException(status_code=401, detail="Authentication required.")
    return user


CurrentUser = Annotated[AuthEntity, Depends(get_current_user)]
