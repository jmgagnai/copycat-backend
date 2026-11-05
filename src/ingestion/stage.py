import uuid
from dataclasses import dataclass
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from document.document_dto import DocumentStatus, FailedAt, FailureReason
from event.events_bus import publish_app_event
from event.events_dto import AppEventDraft, notebook_topic

CONVERT_TO_MARKDOWN_QUEUE = "convert_to_markdown"
SUMMARIZE_DOCUMENT_QUEUE = "summarize_document"
EMBED_CHUNKS_QUEUE = "embed_chunks"

DOCUMENT_VERSION_STATUS_CHANGED = "document-version-status-changed"


@dataclass(frozen=True)
class DocumentVersionRef:
    document_id: uuid.UUID
    version_id: uuid.UUID


@dataclass(frozen=True)
class IngestionVersion:
    notebook_id: uuid.UUID
    document_id: uuid.UUID
    version_id: uuid.UUID
    filename: str


class IngestionFailure(Exception):
    def __init__(self, reason: FailureReason, message: str):
        super().__init__(message)
        self.reason: FailureReason = reason


async def load_version(db: AsyncSession, ref: DocumentVersionRef, *columns: str) -> Any:
    selected = ", ".join(f"v.{c}" for c in columns)
    sql = text(
        f"SELECT d.notebook_id, d.filename, {selected} FROM document_versions v"
        " JOIN documents d ON d.id = v.document_id"
        " WHERE v.id = :version_id AND v.document_id = :document_id AND v.deleted_at IS NULL"
    )
    return (
        await db.execute(
            sql, {"version_id": ref.version_id, "document_id": ref.document_id}
        )
    ).first()


async def set_version_status(
    db: AsyncSession,
    version: IngestionVersion,
    status: DocumentStatus,
    *,
    error: BaseException | None = None,
    failed_at: FailedAt | None = None,
    **columns: Any,
) -> None:
    reason: FailureReason | None = None
    if status == "failed":
        reason = error.reason if isinstance(error, IngestionFailure) else "unexpected"
    assignments = ", ".join(f"{name} = :{name}" for name in columns)
    await db.execute(
        text(
            "UPDATE document_versions SET ingestion_status = :status, ingestion_error = :error,"
            f" failure_reason = :reason, failed_at = :failed_at{', ' + assignments if assignments else ''}"
            " WHERE id = :id"
        ),
        {
            "id": version.version_id,
            "status": status,
            "error": str(error) if error else None,
            "reason": reason,
            "failed_at": failed_at if status == "failed" else None,
            **columns,
        },
    )
    data: dict[str, Any] = {
        "notebookId": str(version.notebook_id),
        "documentId": str(version.document_id),
        "versionId": str(version.version_id),
        "filename": version.filename,
        "status": status,
    }
    if reason:
        data["failure"] = {"reason": reason, "failedAt": failed_at}
    await publish_app_event(
        db,
        AppEventDraft(
            type=DOCUMENT_VERSION_STATUS_CHANGED,
            topic=notebook_topic(version.notebook_id),
            data=data,
        ),
    )
    await db.commit()
