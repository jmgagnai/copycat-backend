from __future__ import annotations

import datetime
import uuid
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

DocumentStatus = Literal[
    "queued",
    "converting",
    "converted",
    "summarizing",
    "summarized",
    "indexing",
    "ready",
    "failed",
]
FailureReason = Literal[
    "no-text-layer", "unreadable", "timed-out", "service-unavailable", "unexpected"
]
RETRYABLE_FAILURE_REASONS: list[str] = [
    "unexpected",
    "service-unavailable",
    "timed-out",
]
FailedAt = Literal["converting", "summarizing", "indexing"]

_response = ConfigDict(extra="ignore", frozen=False, populate_by_name=True)


class DocumentFailure(BaseModel):
    model_config = _response
    reason: FailureReason = Field(default=...)
    failed_at: FailedAt | None = Field(default=..., serialization_alias="failedAt")


class DocumentVersion(BaseModel):
    model_config = _response
    id: uuid.UUID = Field(default=...)
    version_number: int = Field(default=..., serialization_alias="versionNumber", gt=0)
    mime_type: str = Field(default=..., serialization_alias="mimeType")
    size_bytes: int = Field(default=..., serialization_alias="sizeBytes", ge=0)
    created_at: datetime.datetime = Field(default=..., serialization_alias="createdAt")


class DocumentResponse(BaseModel):
    model_config = _response
    id: uuid.UUID = Field(default=...)
    notebook_id: uuid.UUID = Field(default=..., serialization_alias="notebookId")
    filename: str = Field(default=...)
    status: DocumentStatus = Field(default=...)
    failure: DocumentFailure | None = Field(default=...)
    abstract: str | None = Field(default=...)
    created_at: datetime.datetime = Field(default=..., serialization_alias="createdAt")
    latest_version: DocumentVersion = Field(
        default=..., serialization_alias="latestVersion"
    )


class DocumentDetailResponse(DocumentResponse):
    metadata: dict[str, Any] | None = Field(default=...)
    chat_snippet: str | None = Field(default=..., serialization_alias="chatSnippet")
    executive_summary: str | None = Field(
        default=..., serialization_alias="executiveSummary"
    )


class DocumentVersionDetailResponse(BaseModel):
    model_config = _response
    document_id: uuid.UUID = Field(default=..., serialization_alias="documentId")
    notebook_id: uuid.UUID = Field(default=..., serialization_alias="notebookId")
    filename: str = Field(default=...)
    document_created_at: datetime.datetime = Field(
        default=..., serialization_alias="documentCreatedAt"
    )
    version: DocumentVersion = Field(default=...)
    status: DocumentStatus = Field(default=...)
    abstract: str | None = Field(default=...)
    chat_snippet: str | None = Field(default=..., serialization_alias="chatSnippet")
    executive_summary: str | None = Field(
        default=..., serialization_alias="executiveSummary"
    )
    metadata: dict[str, Any] | None = Field(default=...)
    is_latest_version: bool = Field(default=..., serialization_alias="isLatestVersion")
    latest_version_number: int = Field(
        default=..., serialization_alias="latestVersionNumber", gt=0
    )


class DocumentVersionContentResponse(BaseModel):
    model_config = _response
    version_id: uuid.UUID = Field(default=..., serialization_alias="versionId")
    markdown: str | None = Field(default=...)


class RetryIngestionResponse(BaseModel):
    model_config = _response
    status: DocumentStatus = Field(default=...)
