from __future__ import annotations

import logging
import uuid
from typing import Annotated, Protocol
from urllib.parse import quote

from fastapi import APIRouter, Depends, File, HTTPException, Path, Request, UploadFile
from fastapi.responses import Response

from auth.guard import CurrentUser
from notebook.notebook_repository import NotebookRepository
from storage import S3Storage

from .document_dto import (
    DocumentDetailResponse,
    DocumentResponse,
    DocumentVersionContentResponse,
    DocumentVersionDetailResponse,
)
from .document_repository import DocumentRepository
from .file_types import (
    MAX_UPLOAD_FILE_BYTES,
    MAX_UPLOAD_FILE_DESCRIPTION,
    describe_rejected_file_type,
    resolve_accepted_mime_type,
)

# Full paths rather than a prefix: the contract is `/notebooks/{notebookId}/documents`, and a
# prefix with "/" would register a trailing slash and answer the bare path with a 307.
router = APIRouter(tags=["documents"])
log = logging.getLogger(__name__)

NotebookId = Annotated[uuid.UUID, Path(alias="notebookId")]
DocumentId = Annotated[uuid.UUID, Path(alias="documentId")]
VersionId = Annotated[uuid.UUID, Path(alias="versionId")]


def get_storage(request: Request) -> S3Storage:
    """The S3Storage the lifespan put on app.state (a FakeStorage in tests)."""
    return request.app.state.storage


class ConversionJobs(Protocol):
    """What the upload route needs from the job queue. jobs.tasks.JobQueue satisfies it. A
    protocol rather than the class itself: importing jobs.tasks here would close an import cycle
    (document -> jobs.tasks -> ingestion.stage -> document)."""

    async def enqueue_convert_to_markdown(
        self, document_id: uuid.UUID, version_id: uuid.UUID
    ) -> None: ...


def get_jobs(request: Request) -> ConversionJobs | None:
    """The JobQueue the lifespan put on app.state (a FakeJobs in tests, None when absent)."""
    return getattr(request.app.state, "jobs", None)


async def enqueue_conversion(
    jobs: ConversionJobs | None, document_id: uuid.UUID, version_id: uuid.UUID
) -> None:
    """Enqueued after the row is committed, never before; a failure to enqueue must not fail a
    request whose row already records the work owed."""
    if jobs is None:
        return
    try:
        await jobs.enqueue_convert_to_markdown(document_id, version_id)
    except Exception:
        log.exception(
            "Could not enqueue the conversion of Document Version %s.", version_id
        )


@router.get(
    "/notebooks/{notebookId}/documents",
    response_model=list[DocumentResponse],
    summary="List all Documents in a Notebook",
)
async def list_documents(
    *,
    notebook_id: NotebookId,
    _: CurrentUser,
    repo: Annotated[DocumentRepository, Depends()],
    notebooks: Annotated[NotebookRepository, Depends()],
) -> list[DocumentResponse]:
    if not await notebooks.notebook_exists(notebook_id):
        raise HTTPException(404, "Notebook not found.")
    return await repo.list_documents(notebook_id)


@router.post(
    "/notebooks/{notebookId}/documents",
    response_model=DocumentResponse,
    status_code=201,
    summary="Upload a Document. Re-uploading an existing, undeleted filename within the same Notebook adds a new Version to that Document instead of creating a new one.",
)
async def upload_document(
    *,
    notebook_id: NotebookId,
    file: Annotated[UploadFile, File()],
    _: CurrentUser,
    repo: Annotated[DocumentRepository, Depends()],
    notebooks: Annotated[NotebookRepository, Depends()],
    storage: Annotated[S3Storage, Depends(get_storage)],
    jobs: Annotated[ConversionJobs | None, Depends(get_jobs)],
) -> DocumentResponse:
    if not await notebooks.notebook_exists(notebook_id):
        raise HTTPException(404, "Notebook not found.")
    filename = file.filename or ""
    mime_type = resolve_accepted_mime_type(filename)
    if mime_type is None:
        raise HTTPException(400, describe_rejected_file_type(filename))
    body = await file.read(MAX_UPLOAD_FILE_BYTES + 1)
    if len(body) > MAX_UPLOAD_FILE_BYTES:
        raise HTTPException(
            413,
            f"The file is larger than the {MAX_UPLOAD_FILE_DESCRIPTION} limit for a single upload.",
        )
    storage_key = f"notebooks/{notebook_id}/{uuid.uuid4()}-{filename}"
    await storage.put_object(storage_key, body, mime_type)
    document = await repo.create_document_version(
        notebook_id, filename, mime_type, len(body), storage_key
    )
    await enqueue_conversion(jobs, document.id, document.latest_version.id)
    return document


@router.get(
    "/notebooks/{notebookId}/documents/{documentId}",
    response_model=DocumentDetailResponse,
    summary="Get one Document with its latest Version's extracted metadata and generated summaries (Abstract, Executive Summary, Chat Snippet)",
)
async def get_document(
    *,
    notebook_id: NotebookId,
    document_id: DocumentId,
    _: CurrentUser,
    repo: Annotated[DocumentRepository, Depends()],
) -> DocumentDetailResponse:
    document = await repo.find_document_detail(notebook_id, document_id)
    if document is None:
        raise HTTPException(404, "Document not found.")
    return document


@router.delete(
    "/notebooks/{notebookId}/documents/{documentId}",
    status_code=204,
    summary="Soft-delete a Document",
)
async def delete_document(
    *,
    notebook_id: NotebookId,
    document_id: DocumentId,
    _: CurrentUser,
    repo: Annotated[DocumentRepository, Depends()],
) -> None:
    if not await repo.soft_delete_document(notebook_id, document_id):
        raise HTTPException(404, "Document not found.")


@router.post(
    "/notebooks/{notebookId}/documents/{documentId}/restore",
    response_model=DocumentResponse,
    summary="Restore a soft-deleted Document",
)
async def restore_document(
    *,
    notebook_id: NotebookId,
    document_id: DocumentId,
    _: CurrentUser,
    repo: Annotated[DocumentRepository, Depends()],
) -> DocumentResponse:
    """Reports 409 if the Notebook has since acquired another Document under the same filename."""
    result = await repo.restore_document(notebook_id, document_id)
    if result.outcome == "filename-taken":
        raise HTTPException(
            409,
            f'A Document named "{result.filename}" already exists in this Notebook.',
        )
    if result.outcome == "not-found" or result.document is None:
        raise HTTPException(404, "Document not found.")
    return result.document


@router.get(
    "/notebooks/{notebookId}/documents/{documentId}/versions/{versionId}",
    response_model=DocumentVersionDetailResponse,
    summary="Get one Document Version with its own extracted metadata and generated summaries (Abstract, Executive Summary, Chat Snippet)",
)
async def get_document_version(
    *,
    notebook_id: NotebookId,
    document_id: DocumentId,
    version_id: VersionId,
    _: CurrentUser,
    repo: Annotated[DocumentRepository, Depends()],
) -> DocumentVersionDetailResponse:
    """Every field describes the Version named in the path, not the Document's latest Version:
    this is what following a Citation reads."""
    version = await repo.find_document_version_detail(
        notebook_id, document_id, version_id
    )
    if version is None:
        raise HTTPException(404, "Document Version not found.")
    return version


@router.get(
    "/notebooks/{notebookId}/documents/{documentId}/versions/{versionId}/content",
    response_model=DocumentVersionContentResponse,
    summary="Get the Converted Markdown of a Document Version",
)
async def get_document_version_content(
    *,
    notebook_id: NotebookId,
    document_id: DocumentId,
    version_id: VersionId,
    _: CurrentUser,
    repo: Annotated[DocumentRepository, Depends()],
) -> DocumentVersionContentResponse:
    content = await repo.find_document_content(notebook_id, document_id, version_id)
    if content is None:
        raise HTTPException(404, "Document Version not found.")
    return content


@router.get(
    "/notebooks/{notebookId}/documents/{documentId}/versions/{versionId}/download",
    summary="Download the exact original bytes uploaded for a Document Version",
    response_class=Response,
)
async def download_document_version(
    *,
    notebook_id: NotebookId,
    document_id: DocumentId,
    version_id: VersionId,
    _: CurrentUser,
    repo: Annotated[DocumentRepository, Depends()],
    storage: Annotated[S3Storage, Depends(get_storage)],
) -> Response:
    version = await repo.find_downloadable_version(notebook_id, document_id, version_id)
    if version is None:
        raise HTTPException(404, "Document Version not found.")
    stored = await storage.get_object(version.storage_key)
    return Response(
        content=stored.body,
        media_type=version.mime_type,
        headers={
            "Content-Disposition": f'attachment; filename="{quote(version.filename)}"'
        },
    )
