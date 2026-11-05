import json
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from llm.models import TaskModels, resolve_task_models
from llm.openrouter import ChatCompleter

from .embedded_pictures import without_embedded_pictures
from .generated_artifacts import GenerationDeps, generate_artifacts
from .stage import (
    SUMMARIZE_DOCUMENT_QUEUE,
    DocumentVersionRef,
    IngestionVersion,
    load_version,
    set_version_status,
)

__all__ = [
    "SUMMARIZE_DOCUMENT_QUEUE",
    "SummarizeDocumentDeps",
    "run_summarize_document_job",
]


@dataclass
class SummarizeDocumentDeps:
    db: AsyncSession
    complete: ChatCompleter
    models: TaskModels | None = None
    enqueue_embed_chunks: Callable[[DocumentVersionRef], Awaitable[None]] | None = None


async def run_summarize_document_job(
    deps: SummarizeDocumentDeps, ref: DocumentVersionRef
) -> None:
    row = await load_version(deps.db, ref, "markdown")
    if row is None:
        return
    version = IngestionVersion(
        row.notebook_id, ref.document_id, ref.version_id, row.filename
    )
    await set_version_status(deps.db, version, "summarizing")

    try:
        if not row.markdown:
            raise RuntimeError("Version has no Converted Markdown to summarize")
        result = await generate_artifacts(
            GenerationDeps(deps.complete, deps.models or resolve_task_models()),
            filename=version.filename,
            markdown=without_embedded_pictures(row.markdown),
        )
        await set_version_status(
            deps.db,
            version,
            "summarized",
            metadata=json.dumps(result.metadata),
            chat_snippet=result.chat_snippet,
            executive_summary=result.executive_summary,
            abstract=result.abstract,
            summarized_at=datetime.now(UTC),
        )
        if deps.enqueue_embed_chunks:
            await deps.enqueue_embed_chunks(ref)
    except Exception as err:
        await deps.db.rollback()
        await set_version_status(
            deps.db, version, "failed", error=err, failed_at="summarizing"
        )
        raise
