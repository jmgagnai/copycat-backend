from __future__ import annotations

import datetime
import uuid
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field


class CreateNotebookBody(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        frozen=False,
        populate_by_name=True,
    )
    title: Annotated[str, Field(min_length=1, default=...)]


class CreateNotebookResponse(BaseModel):
    model_config = ConfigDict(
        extra="ignore",
        frozen=False,
        populate_by_name=True,
    )
    id: uuid.UUID = Field(default=...)
    title: str = Field(default=...)
    created_at: datetime.datetime = Field(default=..., alias="createdAt")


class RenameNotebookBody(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        frozen=False,
        populate_by_name=True,
    )
    title: Annotated[str, Field(min_length=1, default=...)]


class RenameNotebookResponse(BaseModel):
    model_config = ConfigDict(
        extra="ignore",
        frozen=False,
        populate_by_name=True,
    )
    id: uuid.UUID = Field(default=...)
    title: str = Field(default=...)
    created_at: datetime.datetime = Field(default=..., alias="createdAt")


class RestoreNotebookResponse(BaseModel):
    model_config = ConfigDict(
        extra="ignore",
        frozen=False,
        populate_by_name=True,
    )
    id: uuid.UUID = Field(default=...)
    title: str = Field(default=...)
    created_at: datetime.datetime = Field(default=..., alias="createdAt")
