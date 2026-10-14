from __future__ import annotations

import datetime
import uuid
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field


class RegisterBody(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        frozen=False,
        populate_by_name=True,
    )
    email: str = Field(default=...)
    password: Annotated[str, Field(min_length=8, default=...)]


class RegisterResponse(BaseModel):
    model_config = ConfigDict(
        extra="ignore",
        frozen=False,
        populate_by_name=True,
    )
    id: uuid.UUID = Field(default=...)
    email: str = Field(default=...)
    created_at: datetime.datetime = Field(default=..., alias="createdAt")


class LoginBody(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        frozen=False,
        populate_by_name=True,
    )
    email: str = Field(default=...)
    password: Annotated[str, Field(min_length=1, default=...)]


class LoginResponse(BaseModel):
    model_config = ConfigDict(
        extra="ignore",
        frozen=False,
        populate_by_name=True,
    )
    id: uuid.UUID = Field(default=...)
    email: str = Field(default=...)
    created_at: datetime.datetime = Field(default=..., alias="createdAt")


class GetCurrentUserResponse(BaseModel):
    model_config = ConfigDict(
        extra="ignore",
        frozen=False,
        populate_by_name=True,
    )
    id: uuid.UUID = Field(default=...)
    email: str = Field(default=...)
    created_at: datetime.datetime = Field(default=..., alias="createdAt")
