from __future__ import annotations

import datetime
import uuid
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class DocumentFailure(BaseModel):
    model_config = ConfigDict(
        extra="ignore",
        frozen=False,
        populate_by_name=True,
    )
    reason: Literal[
        "no-text-layer", "unreadable", "timed-out", "service-unavailable", "unexpected"
    ] = Field(default=...)
    failed_at: Literal["converting", "summarizing", "indexing"] | None = Field(
        default=..., alias="failedAt"
    )


class UploadDocumentResponse(BaseModel):
    model_config = ConfigDict(
        extra="ignore",
        frozen=False,
        populate_by_name=True,
    )

    id: uuid.UUID = Field(default=...)
    notebook_id: uuid.UUID = Field(default=..., alias="notebookId")
    filename: str = Field(default=...)
    status: Literal[
        "queued",
        "converting",
        "converted",
        "summarizing",
        "summarized",
        "indexing",
        "ready",
        "failed",
    ] = Field(default=...)
    failure: DocumentFailure | None = Field(default=...)
    abstract: str | None = Field(default=...)
    created_at: datetime.datetime = Field(default=..., alias="createdAt")
    latest_version: dict[str, Any] = Field(default=..., alias="latestVersion")


class GetDocumentResponse(BaseModel):
    model_config = ConfigDict(
        extra="ignore",
        frozen=False,
        populate_by_name=True,
    )
    id: uuid.UUID = Field(default=...)
    notebook_id: uuid.UUID = Field(default=..., alias="notebookId")
    filename: str = Field(default=...)
    status: Literal[
        "queued",
        "converting",
        "converted",
        "summarizing",
        "summarized",
        "indexing",
        "ready",
        "failed",
    ] = Field(default=...)
    failure: DocumentFailure | None = Field(default=...)
    abstract: str | None = Field(default=...)
    created_at: datetime.datetime = Field(default=..., alias="createdAt")
    latest_version: dict[str, Any] = Field(default=..., alias="latestVersion")
    metadata: dict[str, Any] | None = Field(default=...)
    chat_snippet: str | None = Field(default=..., alias="chatSnippet")
    executive_summary: str | None = Field(default=..., alias="executiveSummary")


class GetDocumentVersionResponse(BaseModel):
    model_config = ConfigDict(
        extra="ignore",
        frozen=False,
        populate_by_name=True,
    )
    document_id: uuid.UUID = Field(default=..., alias="documentId")
    notebook_id: uuid.UUID = Field(default=..., alias="notebookId")
    filename: str = Field(default=...)
    document_created_at: datetime.datetime = Field(
        default=..., alias="documentCreatedAt"
    )
    version: dict[str, Any] = Field(default=...)
    status: Literal[
        "queued",
        "converting",
        "converted",
        "summarizing",
        "summarized",
        "indexing",
        "ready",
        "failed",
    ] = Field(default=...)
    abstract: str | None = Field(default=...)
    chat_snippet: str | None = Field(default=..., alias="chatSnippet")
    executive_summary: str | None = Field(default=..., alias="executiveSummary")
    metadata: dict[str, Any] | None = Field(default=...)
    is_latest_version: bool = Field(default=..., alias="isLatestVersion")
    latest_version_number: Annotated[
        int, Field(ge=0, gt=0, default=..., alias="latestVersionNumber")
    ]


class GetDocumentVersionContentResponse(BaseModel):
    model_config = ConfigDict(
        extra="ignore",
        frozen=False,
        populate_by_name=True,
    )
    version_id: uuid.UUID = Field(default=..., alias="versionId")
    markdown: str | None = Field(default=...)


class RestoreDocumentResponse(BaseModel):
    model_config = ConfigDict(
        extra="ignore",
        frozen=False,
        populate_by_name=True,
    )
    id: uuid.UUID = Field(default=...)
    notebook_id: uuid.UUID = Field(default=..., alias="notebookId")
    filename: str = Field(default=...)
    status: Literal[
        "queued",
        "converting",
        "converted",
        "summarizing",
        "summarized",
        "indexing",
        "ready",
        "failed",
    ] = Field(default=...)
    failure: DocumentFailure | None = Field(default=...)
    abstract: str | None = Field(default=...)
    created_at: datetime.datetime = Field(default=..., alias="createdAt")
    latest_version: dict[str, Any] = Field(default=..., alias="latestVersion")


class RetryIngestionResponse(BaseModel):
    model_config = ConfigDict(
        extra="ignore",
        frozen=False,
        populate_by_name=True,
    )
    status: Literal[
        "queued",
        "converting",
        "converted",
        "summarizing",
        "summarized",
        "indexing",
        "ready",
        "failed",
    ] = Field(default=...)
