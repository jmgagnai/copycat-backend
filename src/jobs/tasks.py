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
from ingestion.embed_chunks import EmbedChunksDeps, run_embed_chunks_job
from ingestion.stage import (
    CONVERT_TO_MARKDOWN_QUEUE,
    EMBED_CHUNKS_QUEUE,
    SUMMARIZE_DOCUMENT_QUEUE,
    DocumentVersionRef,
)
from ingestion.summarize_document import (
    SummarizeDocumentDeps,
    run_summarize_document_job,
)
from jobs.app import job_app
from llm.embeddings import Embedder
from llm.models import TaskModels
from llm.openrouter import ChatCompleter
from storage import S3Storage

log = logging.getLogger(__name__)

RETRY = RetryStrategy(max_attempts=4, wait=10, exponential_wait=2)


@dataclass
class WorkerDeps:
    storage: S3Storage
    convert_to_markdown: MarkdownConverter
    complete: ChatCompleter | None = None
    models: TaskModels | None = None
    embed: Embedder | None = None


_deps: WorkerDeps | None = None


def _ref(document_id: str, version_id: str) -> DocumentVersionRef:
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
    assert _deps is not None and _deps.complete is not None
    async with AsyncSessionLocal() as db:
        deps = SummarizeDocumentDeps(
            db, _deps.complete, _deps.models, enqueue_embed_chunks=enqueue_embed_chunks
        )
        await run_summarize_document_job(deps, _ref(document_id, version_id))


@job_app.task(queue=EMBED_CHUNKS_QUEUE, retry=RETRY)
async def embed_chunks(document_id: str, version_id: str) -> None:
    assert _deps is not None and _deps.embed is not None
    async with AsyncSessionLocal() as db:
        await run_embed_chunks_job(
            EmbedChunksDeps(db, _deps.embed), _ref(document_id, version_id)
        )


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
    def __init__(self, worker: WorkerDeps | None = None) -> None:
        global _deps
        _deps = worker
        self._worker: asyncio.Task[None] | None = None
        self._queues = [CONVERT_TO_MARKDOWN_QUEUE]
        if worker and worker.complete:
            self._queues.append(SUMMARIZE_DOCUMENT_QUEUE)
        if worker and worker.embed:
            self._queues.append(EMBED_CHUNKS_QUEUE)

    async def start(self, work: bool = True) -> None:
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
