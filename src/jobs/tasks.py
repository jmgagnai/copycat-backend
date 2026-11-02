"""The three ingestion tasks, one queue each (ADR-0004), with their enqueue functions and the
JobQueue the lifespan and the routes use. Loaded by procrastinate through jobs.app's import_paths."""

import asyncio
import logging
import uuid
from dataclasses import dataclass

from procrastinate import RetryStrategy

from db import AsyncSessionLocal
from ingestion.convert_to_markdown import (
    ConvertToMarkdownDeps,
    run_convert_to_markdown_job,
)
from ingestion.docling import MarkdownConverter
from ingestion.stage import (
    CONVERT_TO_MARKDOWN_QUEUE,
    EMBED_CHUNKS_QUEUE,
    SUMMARIZE_DOCUMENT_QUEUE,
    DocumentVersionRef,
)
from jobs.app import job_app
from llm.embeddings import Embedder
from llm.models import TaskModels
from llm.openrouter import ChatCompleter
from storage import S3Storage

log = logging.getLogger(__name__)

# One attempt plus three retries, 10 s, 20 s, 40 s apart.
RETRY = RetryStrategy(max_attempts=4, wait=10, exponential_wait=2)


@dataclass
class WorkerDeps:
    """What a worker needs for the whole pipeline, set once at startup. Stage 2's and 3's are
    optional: a backend with no OpenRouter key converts Documents and stops at `converted`."""

    storage: S3Storage
    convert_to_markdown: MarkdownConverter
    complete: ChatCompleter | None = (
        None  # Stage 2 (T12); None without an OpenRouter key
    )
    models: TaskModels | None = None  # which model per task, resolved once at boot
    embed: Embedder | None = None  # Stage 3 (T13); None without an OpenRouter key


# A task is called with its job arguments only; everything else comes from here (set by JobQueue).
_deps: WorkerDeps | None = None


def _ref(document_id: str, version_id: str) -> DocumentVersionRef:
    # Job arguments are stored as JSON, so the ids travel as strings.
    return DocumentVersionRef(
        document_id=uuid.UUID(document_id), version_id=uuid.UUID(version_id)
    )


@job_app.task(queue=CONVERT_TO_MARKDOWN_QUEUE, retry=RETRY)
async def convert_to_markdown(document_id: str, version_id: str) -> None:
    assert _deps is not None
    async with AsyncSessionLocal() as db:
        deps = ConvertToMarkdownDeps(
            db,
            _deps.storage,
            _deps.convert_to_markdown,
            enqueue_summarize_document=enqueue_summarize_document,
        )
        await run_convert_to_markdown_job(deps, _ref(document_id, version_id))


@job_app.task(queue=SUMMARIZE_DOCUMENT_QUEUE, retry=RETRY)
async def summarize_document(document_id: str, version_id: str) -> None:
    log.info("summarize_document: %s", _ref(document_id, version_id))  # T12


@job_app.task(queue=EMBED_CHUNKS_QUEUE, retry=RETRY)
async def embed_chunks(document_id: str, version_id: str) -> None:
    log.info("embed_chunks: %s", _ref(document_id, version_id))  # T13


# Enqueue functions. The upload route calls the first through JobQueue (step 3); Stage 1 calls the
# second on success and Stage 2 the third. The Stages receive them as dependencies rather than
# importing them, so a Stage test can pass a list-appending fake and never touch the queue.
async def enqueue_convert_to_markdown(ref: DocumentVersionRef) -> None:
    await convert_to_markdown.defer_async(
        document_id=str(ref.document_id), version_id=str(ref.version_id)
    )


async def enqueue_summarize_document(ref: DocumentVersionRef) -> None:
    await summarize_document.defer_async(
        document_id=str(ref.document_id), version_id=str(ref.version_id)
    )


async def enqueue_embed_chunks(ref: DocumentVersionRef) -> None:
    await embed_chunks.defer_async(
        document_id=str(ref.document_id), version_id=str(ref.version_id)
    )


class JobQueue:
    """The producer side the routes see, plus the worker's lifecycle (one asyncio task in the web
    process). It never applies or checks procrastinate's schema: that is done once by hand with
    `procrastinate --app jobs.app.job_app schema --apply` (T09 step 0)."""

    def __init__(self, worker: WorkerDeps | None = None) -> None:
        global _deps
        _deps = worker
        self._worker: asyncio.Task[None] | None = None
        # Without an OpenRouter key, Stages 2 and 3 cannot run: their jobs stay `todo` rather
        # than failing four times each.
        self._queues = [CONVERT_TO_MARKDOWN_QUEUE]
        if worker and worker.complete:
            self._queues.append(SUMMARIZE_DOCUMENT_QUEUE)
        if worker and worker.embed:
            self._queues.append(EMBED_CHUNKS_QUEUE)

    async def start(self, work: bool = True) -> None:
        """Connect, and unless `work=False` (scripts that only defer) run the worker in the background."""
        await job_app.open_async()
        if work and _deps is not None:
            self._worker = asyncio.create_task(
                job_app.run_worker_async(
                    queues=self._queues, concurrency=1, install_signal_handlers=False
                )
            )
            log.info("Job worker started on queues %s", self._queues)

    async def stop(self) -> None:
        if self._worker:
            self._worker.cancel()
            try:
                await self._worker
            except asyncio.CancelledError:
                pass
        await job_app.close_async()
        log.info("Job worker stopped")

    async def enqueue_convert_to_markdown(
        self, document_id: uuid.UUID, version_id: uuid.UUID
    ) -> None:
        await enqueue_convert_to_markdown(
            DocumentVersionRef(document_id=document_id, version_id=version_id)
        )
