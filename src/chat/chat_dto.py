from __future__ import annotations

import datetime
import uuid
from typing import Annotated, Any

from pydantic import BaseModel, ConfigDict, Field


class CreateChatThreadBody(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        frozen=False,
        populate_by_name=True,
    )
    title: Annotated[str, Field(min_length=1, default=...)]


class CreateChatThreadResponse(BaseModel):
    model_config = ConfigDict(
        extra="ignore",
        frozen=False,
        populate_by_name=True,
    )
    id: uuid.UUID = Field(default=...)
    notebook_id: uuid.UUID = Field(default=..., alias="notebookId")
    title: str = Field(default=...)
    author: dict[str, Any] = Field(default=...)
    created_at: datetime.datetime = Field(default=..., alias="createdAt")


class RenameChatThreadBody(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        frozen=False,
        populate_by_name=True,
    )

    title: Annotated[str, Field(min_length=1, default=...)]


class RenameChatThreadResponse(BaseModel):
    model_config = ConfigDict(
        extra="ignore",
        frozen=False,
        populate_by_name=True,
    )
    id: uuid.UUID = Field(default=...)
    notebook_id: uuid.UUID = Field(default=..., alias="notebookId")
    title: str = Field(default=...)
    author: dict[str, Any] = Field(default=...)
    created_at: datetime.datetime = Field(default=..., alias="createdAt")


class RestoreChatThreadResponse(BaseModel):
    model_config = ConfigDict(
        extra="ignore",
        frozen=False,
        populate_by_name=True,
    )
    id: uuid.UUID = Field(default=...)
    notebook_id: uuid.UUID = Field(default=..., alias="notebookId")
    title: str = Field(default=...)
    author: dict[str, Any] = Field(default=...)
    created_at: datetime.datetime = Field(default=..., alias="createdAt")


class SendChatMessageBody(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        frozen=False,
        populate_by_name=True,
    )
    content: Annotated[str, Field(min_length=1, default=...)]


class SendChatMessageResponse(BaseModel):
    model_config = ConfigDict(
        extra="ignore",
        frozen=False,
        populate_by_name=True,
    )
    question: dict[str, Any] = Field(default=...)
    answer: dict[str, Any] = Field(default=...)
