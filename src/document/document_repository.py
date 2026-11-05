import uuid
from dataclasses import dataclass
from typing import Annotated, Any, Literal

from fastapi import Depends
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from db import get_db, rowcount

from .document_dto import (
    DocumentDetailResponse,
    DocumentFailure,
    DocumentResponse,
    DocumentVersion,
    DocumentVersionContentResponse,
    DocumentVersionDetailResponse,
)

SELECT_DOCUMENTS_WITH_LATEST_VERSION = """
  SELECT d.id, d.notebook_id, d.filename, d.created_at,
         v.id AS version_id, v.version_number, v.mime_type, v.size_bytes, v.created_at AS version_created_at,
         v.ingestion_status, v.failure_reason, v.failed_at,
         v.abstract, v.chat_snippet, v.executive_summary, v.metadata
  FROM documents d
  JOIN notebooks n ON n.id = d.notebook_id AND n.deleted_at IS NULL
  JOIN LATERAL (
    SELECT id, version_number, mime_type, size_bytes, created_at, ingestion_status,
           failure_reason, failed_at, abstract, chat_snippet, executive_summary, metadata
    FROM document_versions
    WHERE document_id = d.id AND deleted_at IS NULL
    ORDER BY version_number DESC
    LIMIT 1
  ) v ON true
"""


SELECT_VERSION = """
  SELECT d.id AS document_id, d.notebook_id, d.filename, d.created_at AS document_created_at,
         v.id AS version_id, v.version_number, v.mime_type, v.size_bytes, v.created_at AS version_created_at,
         v.ingestion_status, v.abstract, v.chat_snippet, v.executive_summary, v.metadata,
         v.markdown, v.storage_key,
         (SELECT MAX(l.version_number) FROM document_versions l
          WHERE l.document_id = d.id AND l.deleted_at IS NULL) AS latest_version_number
  FROM document_versions v
  JOIN documents d ON d.id = v.document_id
  JOIN notebooks n ON n.id = d.notebook_id AND n.deleted_at IS NULL
  WHERE v.id = :version_id AND v.document_id = :document_id AND d.notebook_id = :notebook_id
    AND v.deleted_at IS NULL
"""


def to_version(row: Any) -> DocumentVersion:
    return DocumentVersion(
        id=row.version_id,
        version_number=row.version_number,
        mime_type=row.mime_type,
        size_bytes=int(row.size_bytes),
        created_at=row.version_created_at,
    )


def to_document(row: Any) -> DocumentResponse:
    failure = None
    if row.ingestion_status == "failed":
        failure = DocumentFailure(
            reason=row.failure_reason or "unexpected", failed_at=row.failed_at
        )
    return DocumentResponse(
        id=row.id,
        notebook_id=row.notebook_id,
        filename=row.filename,
        status=row.ingestion_status,
        failure=failure,
        abstract=row.abstract,
        created_at=row.created_at,
        latest_version=to_version(row),
    )


@dataclass(frozen=True)
class DownloadableVersion:
    storage_key: str
    mime_type: str
    filename: str


@dataclass(frozen=True)
class RestoreResult:
    outcome: Literal["restored", "not-found", "filename-taken"]
    document: DocumentResponse | None = None
    filename: str | None = None


class DocumentRepository:
    def __init__(self, db: Annotated[AsyncSession, Depends(get_db)]):
        self.db = db

    async def list_documents(self, notebook_id: uuid.UUID) -> list[DocumentResponse]:
        rows = await self.db.execute(
            text(
                f"{SELECT_DOCUMENTS_WITH_LATEST_VERSION}"
                " WHERE d.notebook_id = :notebook_id AND d.deleted_at IS NULL ORDER BY d.created_at"
            ),
            {"notebook_id": notebook_id},
        )
        return [to_document(row) for row in rows]

    async def _find_document(
        self, notebook_id: uuid.UUID, document_id: uuid.UUID
    ) -> DocumentResponse | None:
        row = (
            await self.db.execute(
                text(
                    f"{SELECT_DOCUMENTS_WITH_LATEST_VERSION} WHERE d.id = :id AND d.notebook_id = :notebook_id"
                ),
                {"id": document_id, "notebook_id": notebook_id},
            )
        ).first()
        return to_document(row) if row else None

    async def create_document_version(
        self,
        notebook_id: uuid.UUID,
        filename: str,
        mime_type: str,
        size_bytes: int,
        storage_key: str,
    ) -> DocumentResponse:
        document_id: uuid.UUID = (
            await self.db.execute(
                text(
                    "INSERT INTO documents (notebook_id, filename) VALUES (:notebook_id, :filename)"
                    " ON CONFLICT (notebook_id, filename) WHERE deleted_at IS NULL"
                    " DO UPDATE SET filename = EXCLUDED.filename"
                    " RETURNING id"
                ),
                {"notebook_id": notebook_id, "filename": filename},
            )
        ).scalar_one()
        await self.db.execute(
            text(
                "INSERT INTO document_versions (document_id, version_number, mime_type, size_bytes, storage_key)"
                " VALUES (:document_id,"
                "         (SELECT COALESCE(MAX(version_number), 0) + 1 FROM document_versions WHERE document_id = :document_id),"
                "         :mime_type, :size_bytes, :storage_key)"
            ),
            {
                "document_id": document_id,
                "mime_type": mime_type,
                "size_bytes": size_bytes,
                "storage_key": storage_key,
            },
        )
        await self.db.commit()
        document = await self._find_document(notebook_id, document_id)
        assert document is not None
        return document

    async def find_document_detail(
        self, notebook_id: uuid.UUID, document_id: uuid.UUID
    ) -> DocumentDetailResponse | None:
        row = (
            await self.db.execute(
                text(
                    f"{SELECT_DOCUMENTS_WITH_LATEST_VERSION}"
                    " WHERE d.id = :id AND d.notebook_id = :notebook_id AND d.deleted_at IS NULL"
                ),
                {"id": document_id, "notebook_id": notebook_id},
            )
        ).first()
        if row is None:
            return None
        document = to_document(row)
        return DocumentDetailResponse(
            **document.model_dump(),
            metadata=row.metadata,
            chat_snippet=row.chat_snippet,
            executive_summary=row.executive_summary,
        )

    async def _version_row(
        self, notebook_id: uuid.UUID, document_id: uuid.UUID, version_id: uuid.UUID
    ) -> Any:
        params = {
            "version_id": version_id,
            "document_id": document_id,
            "notebook_id": notebook_id,
        }
        return (await self.db.execute(text(SELECT_VERSION), params)).first()

    async def find_document_version_detail(
        self, notebook_id: uuid.UUID, document_id: uuid.UUID, version_id: uuid.UUID
    ) -> DocumentVersionDetailResponse | None:
        row = await self._version_row(notebook_id, document_id, version_id)
        if row is None:
            return None
        version_number: int = row.version_number
        latest_version_number: int = row.latest_version_number
        return DocumentVersionDetailResponse(
            document_id=row.document_id,
            notebook_id=row.notebook_id,
            filename=row.filename,
            document_created_at=row.document_created_at,
            version=to_version(row),
            status=row.ingestion_status,
            abstract=row.abstract,
            chat_snippet=row.chat_snippet,
            executive_summary=row.executive_summary,
            metadata=row.metadata,
            is_latest_version=version_number == latest_version_number,
            latest_version_number=latest_version_number,
        )

    async def find_document_content(
        self, notebook_id: uuid.UUID, document_id: uuid.UUID, version_id: uuid.UUID
    ) -> DocumentVersionContentResponse | None:
        row = await self._version_row(notebook_id, document_id, version_id)
        return (
            DocumentVersionContentResponse(
                version_id=row.version_id, markdown=row.markdown
            )
            if row
            else None
        )

    async def find_downloadable_version(
        self, notebook_id: uuid.UUID, document_id: uuid.UUID, version_id: uuid.UUID
    ) -> DownloadableVersion | None:
        row = await self._version_row(notebook_id, document_id, version_id)
        return (
            DownloadableVersion(row.storage_key, row.mime_type, row.filename)
            if row
            else None
        )

    async def soft_delete_document(
        self, notebook_id: uuid.UUID, document_id: uuid.UUID
    ) -> bool:
        result = await self.db.execute(
            text(
                "UPDATE documents SET deleted_at = now()"
                " WHERE id = :id AND notebook_id = :notebook_id AND deleted_at IS NULL"
            ),
            {"id": document_id, "notebook_id": notebook_id},
        )
        await self.db.commit()
        return rowcount(result) == 1

    async def restore_document(
        self, notebook_id: uuid.UUID, document_id: uuid.UUID
    ) -> RestoreResult:
        try:
            result = await self.db.execute(
                text(
                    "UPDATE documents SET deleted_at = NULL"
                    " WHERE id = :id AND notebook_id = :notebook_id AND deleted_at IS NOT NULL"
                ),
                {"id": document_id, "notebook_id": notebook_id},
            )
            await self.db.commit()
        except IntegrityError:
            await self.db.rollback()
            filename: str = (
                await self.db.execute(
                    text("SELECT filename FROM documents WHERE id = :id"),
                    {"id": document_id},
                )
            ).scalar_one()
            return RestoreResult("filename-taken", filename=filename)
        if rowcount(result) != 1:
            return RestoreResult("not-found")
        document = await self._find_document(notebook_id, document_id)
        return (
            RestoreResult("restored", document)
            if document
            else RestoreResult("not-found")
        )
