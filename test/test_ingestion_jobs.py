import uuid
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any, cast

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from ingestion.convert_to_markdown import (
    ConvertToMarkdownDeps,
    run_convert_to_markdown_job,
)
from ingestion.stage import (
    DocumentVersionRef,
    IngestionFailure,
    IngestionVersion,
    load_version,
    set_version_status,
)
from ingestion.summarize_document import (
    SummarizeDocumentDeps,
    run_summarize_document_job,
)
from llm.models import TaskModels
from llm.openrouter import ChatCompletionRequest
from test.conftest import FakeStorage


async def seed(db: AsyncSession, status: str = "queued") -> DocumentVersionRef:
    notebook_id: uuid.UUID = (
        await db.execute(
            text("INSERT INTO notebooks (title) VALUES ('N') RETURNING id")
        )
    ).scalar_one()
    document_id: uuid.UUID = (
        await db.execute(
            text(
                "INSERT INTO documents (notebook_id, filename) VALUES (:n, 'report.md') RETURNING id"
            ),
            {"n": notebook_id},
        )
    ).scalar_one()
    version_id: uuid.UUID = (
        await db.execute(
            text(
                "INSERT INTO document_versions (document_id, version_number, mime_type, size_bytes, storage_key, ingestion_status)"
                " VALUES (:d, 1, 'text/markdown', 1, 'key', :s) RETURNING id"
            ),
            {"d": document_id, "s": status},
        )
    ).scalar_one()
    await db.commit()
    return DocumentVersionRef(document_id=document_id, version_id=version_id)


async def version_row(db: AsyncSession, version_id: uuid.UUID) -> tuple:
    sql = text(
        "SELECT ingestion_status, ingestion_error, failure_reason, failed_at, markdown"
        " FROM document_versions WHERE id = :id"
    )
    return tuple((await db.execute(sql, {"id": version_id})).one())


async def test_set_version_status_writes_all_four_columns(db: AsyncSession) -> None:
    ref = await seed(db)
    row = await load_version(db, ref, "storage_key")
    assert row is not None and row.storage_key == "key" and row.filename == "report.md"
    version = IngestionVersion(
        row.notebook_id, ref.document_id, ref.version_id, row.filename
    )

    await set_version_status(db, version, "converting")
    assert await version_row(db, ref.version_id) == (
        "converting",
        None,
        None,
        None,
        None,
    )

    await set_version_status(
        db, version, "failed", error=RuntimeError("x"), failed_at="converting"
    )
    assert await version_row(db, ref.version_id) == (
        "failed",
        "x",
        "unexpected",
        "converting",
        None,
    )

    await set_version_status(db, version, "converted", markdown="# A")
    assert await version_row(db, ref.version_id) == (
        "converted",
        None,
        None,
        None,
        "# A",
    )


async def test_load_version_returns_none_for_a_deleted_or_unknown_version(
    db: AsyncSession,
) -> None:
    ref = await seed(db)
    await db.execute(
        text("UPDATE document_versions SET deleted_at = now() WHERE id = :id"),
        {"id": ref.version_id},
    )
    assert await load_version(db, ref, "storage_key") is None
    assert (
        await load_version(
            db, DocumentVersionRef(ref.document_id, uuid.uuid4()), "storage_key"
        )
        is None
    )


async def test_stage_1_stores_the_markdown_and_hands_over(
    db: AsyncSession, tmp_path: Path
) -> None:
    ref = await seed(db)
    storage = FakeStorage()
    storage.objects["key"] = b"# Report"
    handed_over: list[DocumentVersionRef] = []

    async def convert(input_path: Path, output_path: Path) -> None:
        assert input_path.name == "report.md"
        output_path.write_text(input_path.read_bytes().decode() + "\n\nconverted")

    async def enqueue(payload: DocumentVersionRef) -> None:
        handed_over.append(payload)

    deps = ConvertToMarkdownDeps(
        db, storage, convert, enqueue_summarize_document=enqueue, temp_dir=tmp_path
    )
    await run_convert_to_markdown_job(deps, ref)

    assert await version_row(db, ref.version_id) == (
        "converted",
        None,
        None,
        None,
        "# Report\n\nconverted",
    )
    assert handed_over == [ref]
    assert list(tmp_path.iterdir()) == []


async def test_stage_1_records_the_failure_reason(
    db: AsyncSession, tmp_path: Path
) -> None:
    ref = await seed(db)
    storage = FakeStorage()
    storage.objects["key"] = b"scan"

    async def refuse(input_path: Path, output_path: Path) -> None:
        raise IngestionFailure("no-text-layer", "a scan")

    deps = ConvertToMarkdownDeps(db, storage, refuse, temp_dir=tmp_path)
    with pytest.raises(IngestionFailure):
        await run_convert_to_markdown_job(deps, ref)

    assert await version_row(db, ref.version_id) == (
        "failed",
        "a scan",
        "no-text-layer",
        "converting",
        None,
    )
    assert list(tmp_path.iterdir()) == []


async def test_stage_1_skips_a_deleted_version(
    db: AsyncSession, tmp_path: Path
) -> None:
    ref = await seed(db)
    await db.execute(
        text("UPDATE document_versions SET deleted_at = now() WHERE id = :id"),
        {"id": ref.version_id},
    )
    called = False

    async def convert(input_path: Path, output_path: Path) -> None:
        nonlocal called
        called = True

    await run_convert_to_markdown_job(
        ConvertToMarkdownDeps(db, FakeStorage(), convert, temp_dir=tmp_path), ref
    )
    assert not called
    assert (await version_row(db, ref.version_id))[0] == "queued"


SUMMARY_MARKDOWN = (
    "# Report\n\n" + "Revenue grew 12% in 2024. " * 40 + "\n\n## Risks\n\nSome risks."
)

FAKE_MODELS = TaskModels(
    metadata="meta",
    chat_snippet="snippet",
    executive_summary="exec",
    abstract="abstract",
)


def scripted_completer() -> tuple[
    Callable[[ChatCompletionRequest], Awaitable[str]], list[ChatCompletionRequest]
]:
    calls: list[ChatCompletionRequest] = []

    async def complete(request: ChatCompletionRequest) -> str:
        calls.append(request)
        if request.model == "meta":
            return '{"title": "Annual report", "authors": ["Ada"], "keywords": ["a"]}'
        words = {"snippet": 150, "exec": 500, "abstract": 50}[request.model]
        return " ".join(["word"] * words)

    return complete, calls


async def test_stage_2_stores_the_metadata_and_summaries_and_hands_over(
    db: AsyncSession,
) -> None:
    ref = await seed(db, "converted")
    await db.execute(
        text("UPDATE document_versions SET markdown = :markdown WHERE id = :id"),
        {"markdown": SUMMARY_MARKDOWN, "id": ref.version_id},
    )
    await db.commit()
    complete, calls = scripted_completer()
    enqueued: list[DocumentVersionRef] = []

    async def enqueue_embed_chunks(ref: DocumentVersionRef) -> None:
        enqueued.append(ref)

    await run_summarize_document_job(
        SummarizeDocumentDeps(
            db, complete, FAKE_MODELS, enqueue_embed_chunks=enqueue_embed_chunks
        ),
        ref,
    )

    row = (
        await db.execute(
            text(
                "SELECT ingestion_status, metadata, chat_snippet, executive_summary, abstract,"
                " summarized_at FROM document_versions WHERE id = :id"
            ),
            {"id": ref.version_id},
        )
    ).one()
    assert row.ingestion_status == "summarized"
    metadata = cast(dict[str, Any], row.metadata)
    assert isinstance(metadata, dict)
    assert metadata["title"] == "Annual report"
    assert len(row.abstract.split()) == 50
    assert len(row.chat_snippet.split()) == 150
    assert len(row.executive_summary.split()) == 500
    assert row.summarized_at is not None
    assert [c.model for c in calls] == ["meta", "snippet", "exec", "abstract"]
    assert enqueued == [ref]


async def test_stage_2_records_an_empty_markdown_as_unexpected(
    db: AsyncSession,
) -> None:
    ref = await seed(db, "converted")
    complete, calls = scripted_completer()

    with pytest.raises(RuntimeError):
        await run_summarize_document_job(
            SummarizeDocumentDeps(db, complete, FAKE_MODELS), ref
        )
    assert calls == []
    assert (await version_row(db, ref.version_id))[:4] == (
        "failed",
        "Version has no Converted Markdown to summarize",
        "unexpected",
        "summarizing",
    )
