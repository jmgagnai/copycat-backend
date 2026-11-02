"""Ingestion Stage 1: download the raw bytes to a temp file, hand the converter the path, store
the Markdown on the Version, hand over to Stage 2. Raises on failure (after recording it) so the
queue applies its retry policy."""

import shutil
import tempfile
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy.ext.asyncio import AsyncSession

from storage import S3Storage

from .docling import MarkdownConverter, markdown_output_path
from .stage import (
    DocumentVersionRef,
    IngestionVersion,
    load_version,
    set_version_status,
)


@dataclass
class ConvertToMarkdownDeps:
    db: AsyncSession
    storage: S3Storage
    convert_to_markdown: MarkdownConverter
    # Hands the Version to Stage 2; a plain callback, so tests pass a list-appending fake.
    enqueue_summarize_document: (
        Callable[[DocumentVersionRef], Awaitable[None]] | None
    ) = None
    temp_dir: Path | None = None  # tests pass tmp_path


async def run_convert_to_markdown_job(
    deps: ConvertToMarkdownDeps, ref: DocumentVersionRef
) -> None:
    row = await load_version(deps.db, ref, "storage_key")
    if row is None:
        return  # (1) gone meanwhile: nothing to convert, nothing to retry
    version = IngestionVersion(
        row.notebook_id, ref.document_id, ref.version_id, row.filename
    )
    await set_version_status(
        deps.db, version, "converting"
    )  # the browser sees the spinner start

    work_dir = Path(tempfile.mkdtemp(prefix="nbk-convert-", dir=deps.temp_dir))
    try:
        input_path = (
            work_dir / Path(version.filename).name
        )  # (2) keep the extension: Docling picks its parser from it
        output_path = markdown_output_path(work_dir)
        input_path.write_bytes((await deps.storage.get_object(row.storage_key)).body)
        await deps.convert_to_markdown(input_path, output_path)
        await set_version_status(
            deps.db,
            version,
            "converted",
            markdown=output_path.read_text(),
            converted_at=datetime.now(UTC),
        )
        # (3) After the commit, and raised rather than logged if it fails: this caller is itself a
        # retryable job, and a swallowed failure would stall the pipeline silently.
        if deps.enqueue_summarize_document:
            await deps.enqueue_summarize_document(ref)
    except Exception as err:
        await (
            deps.db.rollback()
        )  # (4) a failed statement leaves the session unusable until this
        await set_version_status(
            deps.db, version, "failed", error=err, failed_at="converting"
        )
        raise
    finally:
        shutil.rmtree(work_dir, ignore_errors=True)
