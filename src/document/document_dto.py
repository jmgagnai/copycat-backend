from __future__ import annotations

import datetime
import uuid
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

# Where a Document Version is in the ingestion pipeline: stage 1 converts (queued ->
# converting -> converted), stage 2 summarizes (summarizing -> summarized), stage 3 indexes
# (indexing -> ready). `failed` is terminal for whichever stage exhausted its retries.
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
# Why a `failed` Version failed, in terms a user can act on (NBK-63); mirrored by migration 0012.
FailureReason = Literal[
    "no-text-layer", "unreadable", "timed-out", "service-unavailable", "unexpected"
]
# The failure reasons a Retry is offered for (NBK-110): those a second attempt could change.
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
    """A Document with its latest Version only: per GLOSSARY.md only the latest Version is
    searched in chat. `abstract` is on the list payload because that is where cards render;
    the Executive Summary and the Converted Markdown deliberately are not."""

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
    """One named Version, as it was: what following a Citation reads. Every artifact describes
    that Version, not the Document's latest; `isLatestVersion` and `latestVersionNumber` are the
    only facts about any other Version."""

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
