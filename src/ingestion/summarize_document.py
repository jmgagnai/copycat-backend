"""Ingestion Stage 2: metadata and the three summaries from the Converted Markdown, stored on the
Version, then hand over to Stage 3. Same shape as Stage 1: raises on failure (after recording it)
so the queue applies its retry policy."""

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
    models: TaskModels | None = (
        None  # tests pass fake names; the worker the resolved ones
    )
    # Hands the Version to Stage 3; a plain callback, so tests pass a list-appending fake.
    enqueue_embed_chunks: Callable[[DocumentVersionRef], Awaitable[None]] | None = None


async def run_summarize_document_job(
    deps: SummarizeDocumentDeps, ref: DocumentVersionRef
) -> None:
    row = await load_version(deps.db, ref, "markdown")
    if row is None:
        return  # gone meanwhile: nothing to summarize, nothing to retry
    version = IngestionVersion(
        row.notebook_id, ref.document_id, ref.version_id, row.filename
    )
    await set_version_status(deps.db, version, "summarizing")

    try:
        if not row.markdown:
            # Stage 1 stores the Markdown before enqueuing this job: an empty one is a bug,
            # not a user-facing reason, so it is recorded as `unexpected`.
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
            # JSONB: asyncpg hands the string to Postgres, which parses it.
            metadata=json.dumps(result.metadata),
            chat_snippet=result.chat_snippet,
            executive_summary=result.executive_summary,
            abstract=result.abstract,
            summarized_at=datetime.now(UTC),
        )
        # After the commit, and raised rather than logged if it fails: this caller is itself a
        # retryable job, and a swallowed failure would stall the pipeline silently.
        if deps.enqueue_embed_chunks:
            await deps.enqueue_embed_chunks(ref)
    except Exception as err:
        await (
            deps.db.rollback()
        )  # a failed statement leaves the session unusable until this
        await set_version_status(
            deps.db, version, "failed", error=err, failed_at="summarizing"
        )
        raise
