from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Body

from .models import (
    GetCurrentUserResponse,
    LoginBody,
    LoginResponse,
    RegisterBody,
    RegisterResponse,
)

router = APIRouter(tags=["auth"])


@router.post(
    "/auth/login",
    response_model=LoginResponse,
    summary="Log in and receive a session cookie",
)
async def login(
    *,
    body: Annotated[LoginBody, Body()],
) -> LoginResponse:
    raise NotImplementedError


@router.post(
    "/auth/logout", status_code=204, summary="Log out and clear the session cookie"
)
async def logout(
    # TODO: add authentication dependency, e.g.: current_user = Depends(get_auth_context)
) -> None:
    raise NotImplementedError


@router.get(
    "/auth/me",
    response_model=GetCurrentUserResponse,
    summary="Get the current authenticated user",
)
async def get_current_user(
    # TODO: add authentication dependency, e.g.: current_user = Depends(get_auth_context)
) -> GetCurrentUserResponse:
    raise NotImplementedError


@router.post(
    "/auth/register",
    response_model=RegisterResponse,
    status_code=201,
    summary="Register a new user account",
)
async def register(
    *,
    body: Annotated[RegisterBody, Body()],
) -> RegisterResponse:
    raise NotImplementedError
