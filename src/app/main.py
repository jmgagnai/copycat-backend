import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy.orm import configure_mappers
from starlette.exceptions import HTTPException

from auth import auth_router
from chat import chat_router
from document import document_router
from event import events_router
from event.events_bus import AppEventSubscriber
from ingestion.docling import DoclingConverter
from jobs.tasks import JobQueue, WorkerDeps
from llm.embeddings import OpenRouterEmbedder
from llm.models import resolve_embedding_model, resolve_task_models
from llm.openrouter import OpenRouterClient
from notebook import notebook_router
from search import search_router
from settings import settings
from storage import S3Storage

log = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logging.basicConfig(level=settings.LOG_LEVEL.upper())
    configure_mappers()  # fail at boot, not on the first query, if a relationship target is missing
    # Placeholder. T16 replaces it with the chat dependencies.
    app.state.chat = None

    # T07: raw Document bytes live in MinIO; the bucket is created at boot if missing.
    storage = S3Storage(
        settings.MINIO_ENDPOINT,
        settings.MINIO_ACCESS_KEY,
        settings.MINIO_SECRET_KEY,
        settings.DOCUMENTS_BUCKET,
    )
    await storage.ensure_bucket()
    app.state.storage = storage
    log.info(
        "Bucket %s ready at %s", settings.DOCUMENTS_BUCKET, settings.MINIO_ENDPOINT
    )

    # T09: the job worker runs inside this process. Without an OpenRouter key only Stage 1 runs.
    if not settings.OPENROUTER_API_KEY:
        log.warning(
            "OPENROUTER_API_KEY is not set: ingestion stages 2 and 3 will not run and Documents will stop at"
            ' the "converted" status.'
        )
    # T11: one client and one embedder for the whole process, only when a key is set. Stage 3
    # and chat must embed with the same model, and this is where that is guaranteed.
    api_key = settings.OPENROUTER_API_KEY
    client = OpenRouterClient(api_key) if api_key else None
    embed = OpenRouterEmbedder(api_key, resolve_embedding_model()) if api_key else None
    jobs = JobQueue(
        WorkerDeps(
            storage=storage,
            convert_to_markdown=DoclingConverter(),
            complete=client.complete if client else None,
            models=resolve_task_models(),
            embed=embed,
        )
    )
    await jobs.start()
    app.state.jobs = jobs

    # T06: one LISTEN connection feeding every /events stream.
    app_events = AppEventSubscriber(settings.postgres_dsn)
    await app_events.start()
    app.state.app_events = app_events

    try:
        yield
    finally:
        # shutdown, in reverse order of startup
        await app_events.close()
        await jobs.stop()


app = FastAPI(
    title="RAG Notebook API",
    description="A cleanly structured FastAPI application.",
    version="1.0.0",
    lifespan=lifespan,
    docs_url="/swagger",
    openapi_url="/swagger/json",
)

app.add_middleware(
    CORSMiddleware,
    allow_origin_regex=".*",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router, tags=["Users Operations"])

app.include_router(notebook_router, tags=["Notebook Operations"])

app.include_router(chat_router, tags=["Chat Operations"])

app.include_router(search_router, tags=["Search Operations"])

app.include_router(document_router, tags=["Document Operations"])

app.include_router(events_router, tags=["Event Operations"])


@app.exception_handler(HTTPException)
async def http_exception_handler(_: Request, exc: HTTPException) -> JSONResponse:
    """Errors are `{"message": "..."}`, as the Node backend's contract has them."""
    return JSONResponse(
        status_code=exc.status_code,
        content={"message": str(exc.detail)},
        headers=exc.headers,
    )


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(
    _: Request, __: RequestValidationError
) -> JSONResponse:
    return JSONResponse(status_code=400, content={"message": "Invalid request."})
