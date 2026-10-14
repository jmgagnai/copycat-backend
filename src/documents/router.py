from __future__ import annotations

import uuid
from typing import Annotated, Any

from fastapi import APIRouter, File, Path, Response, UploadFile

from .models import (
    GetDocumentResponse,
    GetDocumentVersionContentResponse,
    GetDocumentVersionResponse,
    RestoreDocumentResponse,
    RetryIngestionResponse,
    UploadDocumentResponse,
)

router = APIRouter(tags=["documents"])


@router.get(
    "/notebooks/{notebookId}/documents",
    response_model=list[dict[str, Any]],
    summary="List all Documents in a Notebook",
)
async def list_documents(
    *,
    notebook_id: Annotated[uuid.UUID, Path(alias="notebookId")],
    # TODO: add authentication dependency, e.g.: current_user = Depends(get_auth_context)
) -> list[dict[str, Any]]:
    raise NotImplementedError


@router.post(
    "/notebooks/{notebookId}/documents",
    response_model=UploadDocumentResponse,
    status_code=201,
    summary="Upload a Document. Re-uploading an existing, undeleted filename within the same Notebook adds a new Version to that Document instead of creating a new one.",
)
async def upload_document(
    *,
    notebook_id: Annotated[uuid.UUID, Path(alias="notebookId")],
    file: Annotated[UploadFile, File()],
    # TODO: add authentication dependency, e.g.: current_user = Depends(get_auth_context)
) -> UploadDocumentResponse:
    raise NotImplementedError


@router.get(
    "/notebooks/{notebookId}/documents/{documentId}",
    response_model=GetDocumentResponse,
    summary="Get one Document with its latest Version's extracted metadata and generated summaries (Abstract, Executive Summary, Chat Snippet)",
)
async def get_document(
    *,
    notebook_id: Annotated[uuid.UUID, Path(alias="notebookId")],
    document_id: Annotated[uuid.UUID, Path(alias="documentId")],
    # TODO: add authentication dependency, e.g.: current_user = Depends(get_auth_context)
) -> GetDocumentResponse:
    raise NotImplementedError


@router.delete(
    "/notebooks/{notebookId}/documents/{documentId}",
    status_code=204,
    summary="Soft-delete a Document",
)
async def delete_document(
    *,
    notebook_id: Annotated[uuid.UUID, Path(alias="notebookId")],
    document_id: Annotated[uuid.UUID, Path(alias="documentId")],
    # TODO: add authentication dependency, e.g.: current_user = Depends(get_auth_context)
) -> None:
    raise NotImplementedError


@router.post(
    "/notebooks/{notebookId}/documents/{documentId}/restore",
    response_model=RestoreDocumentResponse,
    summary="Restore a soft-deleted Document",
)
async def restore_document(
    *,
    notebook_id: Annotated[uuid.UUID, Path(alias="notebookId")],
    document_id: Annotated[uuid.UUID, Path(alias="documentId")],
    # TODO: add authentication dependency, e.g.: current_user = Depends(get_auth_context)
) -> RestoreDocumentResponse:
    """Reports 409 if the Notebook has since acquired another Document under the same filename — a re-upload after the delete created one, and only one non-deleted Document per filename can exist in a Notebook."""
    raise NotImplementedError


@router.get(
    "/notebooks/{notebookId}/documents/{documentId}/versions/{versionId}",
    response_model=GetDocumentVersionResponse,
    summary="Get one Document Version with its own extracted metadata and generated summaries (Abstract, Executive Summary, Chat Snippet)",
)
async def get_document_version(
    *,
    notebook_id: Annotated[uuid.UUID, Path(alias="notebookId")],
    document_id: Annotated[uuid.UUID, Path(alias="documentId")],
    version_id: Annotated[uuid.UUID, Path(alias="versionId")],
    # TODO: add authentication dependency, e.g.: current_user = Depends(get_auth_context)
) -> GetDocumentVersionResponse:
    """Every field describes the Version named in the path, not the Document's latest Version — this is what following a Citation reads, so an answer recorded against a superseded Version stays checkable against what that Version actually said. `isLatestVersion` and `latestVersionNumber` say where that Version stands. Succeeds for a Version whose Document has since been soft-deleted, and 404s once its Notebook is."""
    raise NotImplementedError


@router.get(
    "/notebooks/{notebookId}/documents/{documentId}/versions/{versionId}/content",
    response_model=GetDocumentVersionContentResponse,
    summary="Get the Converted Markdown of a Document Version",
)
async def get_document_version_content(
    *,
    notebook_id: Annotated[uuid.UUID, Path(alias="notebookId")],
    document_id: Annotated[uuid.UUID, Path(alias="documentId")],
    version_id: Annotated[uuid.UUID, Path(alias="versionId")],
    # TODO: add authentication dependency, e.g.: current_user = Depends(get_auth_context)
) -> GetDocumentVersionContentResponse:
    raise NotImplementedError


@router.get(
    "/notebooks/{notebookId}/documents/{documentId}/versions/{versionId}/download",
    summary="Download the exact original bytes uploaded for a Document Version",
)
async def download_document_version(
    *,
    notebook_id: Annotated[uuid.UUID, Path(alias="notebookId")],
    document_id: Annotated[uuid.UUID, Path(alias="documentId")],
    version_id: Annotated[uuid.UUID, Path(alias="versionId")],
    # TODO: add authentication dependency, e.g.: current_user = Depends(get_auth_context)
) -> Response:
    raise NotImplementedError


@router.post(
    "/notebooks/{notebookId}/documents/{documentId}/versions/{versionId}/retry",
    response_model=RetryIngestionResponse,
    status_code=202,
    summary="Retry the Ingestion of a failed Document Version",
)
async def retry_ingestion(
    *,
    notebook_id: Annotated[uuid.UUID, Path(alias="notebookId")],
    document_id: Annotated[uuid.UUID, Path(alias="documentId")],
    version_id: Annotated[uuid.UUID, Path(alias="versionId")],
    # TODO: add authentication dependency, e.g.: current_user = Depends(get_auth_context)
) -> RetryIngestionResponse:
    """Runs Ingestion again on the same file, from the Stage that failed (NBK-110): only for a Version that is failed for a reason a second attempt could change (unexpected, service-unavailable, timed-out). Reports 409 otherwise, including while a Retry is already under way. Answers with the status the Version went back to; the rest arrives as status App Events. Per ADR-0001 there is no ownership check."""
    raise NotImplementedError
