from __future__ import annotations

import datetime
import uuid
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field


class CreateNotebookBody(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=False, populate_by_name=True)
    title: Annotated[str, Field(min_length=1, default=...)]


class RenameNotebookBody(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=False, populate_by_name=True)
    title: Annotated[str, Field(min_length=1, default=...)]


class NotebookResponse(BaseModel):
    """One shape for create, rename, restore and list answers; built from the entity."""

    model_config = ConfigDict(
        extra="ignore", frozen=False, populate_by_name=True, from_attributes=True
    )
    id: uuid.UUID = Field(default=...)
    title: str = Field(default=...)
    created_at: datetime.datetime = Field(default=..., serialization_alias="createdAt")
