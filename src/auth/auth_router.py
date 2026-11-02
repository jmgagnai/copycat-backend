from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Body, Depends, HTTPException, Response, status
from sqlalchemy.exc import IntegrityError

from .auth_dto import (
    GetCurrentUserResponse,
    LoginBody,
    LoginResponse,
    RegisterBody,
    RegisterResponse,
)
from .auth_jwt import sign_session_token
from .auth_service import AuthService
from .cookie import SESSION_COOKIE_NAME, session_cookie_options
from .guard import CurrentUser

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post(
    "/login",
    response_model=LoginResponse,
    summary="Log in and receive a session cookie",
)
async def login(
    *,
    body: Annotated[LoginBody, Body()],
    response: Response,
    auth_service: Annotated[AuthService, Depends()],
) -> LoginResponse:
    email = body.email
    password = body.password
    auth_entity = await auth_service.authenticate(email, password)
    if not auth_entity:
        raise HTTPException(status_code=401, detail="Incorrect email or password")
    response.set_cookie(
        SESSION_COOKIE_NAME,
        sign_session_token(f"{auth_entity.id}"),
        **session_cookie_options(),
    )
    return LoginResponse.model_validate(auth_entity)


@router.post("/logout", status_code=204, summary="Log out and clear the session cookie")
async def logout() -> Response:
    response = Response(status_code=status.HTTP_204_NO_CONTENT)
    response.delete_cookie(SESSION_COOKIE_NAME, path="/")
    return response


@router.get(
    "/me",
    response_model=GetCurrentUserResponse,
    summary="Get the current authenticated user",
)
async def get_current_user(user: CurrentUser) -> GetCurrentUserResponse:
    return GetCurrentUserResponse.model_validate(user)


@router.post(
    "/register",
    response_model=RegisterResponse,
    status_code=201,
    summary="Register a new user account",
)
async def register(
    *,
    body: Annotated[RegisterBody, Body()],
    auth_service: Annotated[AuthService, Depends()],
) -> RegisterResponse:
    email = body.email
    password = body.password
    try:
        user = await auth_service.register_new_user(email, password)
    except IntegrityError:
        raise HTTPException(409, "An account with this email already exists.") from None
    return RegisterResponse.model_validate(user)
