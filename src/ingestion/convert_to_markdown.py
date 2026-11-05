import shutil
import tempfile
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Protocol

from sqlalchemy.ext.asyncio import AsyncSession

from storage import StoredObject

from .docling import MarkdownConverter, markdown_output_path
from .stage import (
    DocumentVersionRef,
    IngestionVersion,
    load_version,
    set_version_status,
)


class ObjectStore(Protocol):
    async def get_object(self, key: str) -> StoredObject: ...


@dataclass
class ConvertToMarkdownDeps:
    db: AsyncSession
    storage: ObjectStore
    convert_to_markdown: MarkdownConverter
    enqueue_summarize_document: (
        Callable[[DocumentVersionRef], Awaitable[None]] | None
    ) = None
    temp_dir: Path | None = None


async def run_convert_to_markdown_job(
    deps: ConvertToMarkdownDeps, ref: DocumentVersionRef
) -> None:
    row = await load_version(deps.db, ref, "storage_key")
    if row is None:
        return
    version = IngestionVersion(
        row.notebook_id, ref.document_id, ref.version_id, row.filename
    )
    await set_version_status(deps.db, version, "converting")

    work_dir = Path(tempfile.mkdtemp(prefix="nbk-convert-", dir=deps.temp_dir))
    try:
        input_path = work_dir / Path(version.filename).name
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
        if deps.enqueue_summarize_document:
            await deps.enqueue_summarize_document(ref)
    except Exception as err:
        await deps.db.rollback()
        await set_version_status(
            deps.db, version, "failed", error=err, failed_at="converting"
        )
        raise
    finally:
        shutil.rmtree(work_dir, ignore_errors=True)
