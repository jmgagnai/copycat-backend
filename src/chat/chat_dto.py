from __future__ import annotations

import datetime
import uuid
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

_response = ConfigDict(extra="ignore", frozen=False, populate_by_name=True)


class ChatParticipant(BaseModel):
    model_config = _response
    id: uuid.UUID = Field(default=...)
    email: str = Field(default=...)


class ChatThreadResponse(BaseModel):
    model_config = _response
    id: uuid.UUID = Field(default=...)
    notebook_id: uuid.UUID = Field(default=..., serialization_alias="notebookId")
    title: str = Field(default=...)
    author: ChatParticipant = Field(default=...)
    created_at: datetime.datetime = Field(default=..., serialization_alias="createdAt")


class CreateChatThreadBody(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=False, populate_by_name=True)
    title: Annotated[str, Field(min_length=1, default=...)]


class RenameChatThreadBody(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=False, populate_by_name=True)
    title: Annotated[str, Field(min_length=1, default=...)]


class CitationResponse(BaseModel):
    model_config = _response
    id: uuid.UUID = Field(default=...)
    marker: int = Field(default=..., gt=0)
    document_id: uuid.UUID = Field(default=..., serialization_alias="documentId")
    document_version_id: uuid.UUID = Field(
        default=..., serialization_alias="documentVersionId"
    )
    version_number: int = Field(default=..., serialization_alias="versionNumber", gt=0)
    chunk_id: uuid.UUID = Field(default=..., serialization_alias="chunkId")
    filename: str = Field(default=...)
    heading_path: list[str] = Field(default=..., serialization_alias="headingPath")
    char_start: int | None = Field(default=..., serialization_alias="charStart")
    char_end: int | None = Field(default=..., serialization_alias="charEnd")


class ChatMessageResponse(BaseModel):
    model_config = _response
    id: uuid.UUID = Field(default=...)
    thread_id: uuid.UUID = Field(default=..., serialization_alias="threadId")
    role: Literal["user", "assistant"] = Field(default=...)
    content: str = Field(default=...)
    asked_by: ChatParticipant = Field(default=..., serialization_alias="askedBy")
    citations: list[CitationResponse] = Field(default=...)
    created_at: datetime.datetime = Field(default=..., serialization_alias="createdAt")


class SendChatMessageBody(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=False, populate_by_name=True)
    content: Annotated[str, Field(min_length=1, default=...)]


class SendChatMessageResponse(BaseModel):
    model_config = _response
    question: ChatMessageResponse = Field(default=...)
    answer: ChatMessageResponse = Field(default=...)
