"""T16 step 1. Runs on the T05 `db` fixture: everything is rolled back, no LLM involved."""

import uuid

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from chat.citations import locate_citations, resolve_citation_markers
from chat.retrieval import RetrievedChunk, retrieve_chunks
from ingestion.embed_chunks import to_vector_literal
from llm.models import EMBEDDING_DIMENSIONS


def unit_vector(axis: int) -> list[float]:
    vector = [0.0] * EMBEDDING_DIMENSIONS
    vector[axis] = 1.0
    return vector


async def seed_version(
    db: AsyncSession,
    notebook_id: uuid.UUID,
    status: str = "ready",
    document_id: uuid.UUID | None = None,
    version_number: int = 1,
) -> tuple[uuid.UUID, uuid.UUID]:
    """A Document (or a new Version of one) in the given status, with one chunk on axis 0."""
    if document_id is None:
        inserted: uuid.UUID = (
            await db.execute(
                text(
                    "INSERT INTO documents (notebook_id, filename) VALUES (:n, 'report.md') RETURNING id"
                ),
                {"n": notebook_id},
            )
        ).scalar_one()
        document_id = inserted
    version_id: uuid.UUID = (
        await db.execute(
            text(
                "INSERT INTO document_versions (document_id, version_number, mime_type, size_bytes,"
                " storage_key, ingestion_status, chat_snippet)"
                " VALUES (:d, :n, 'text/markdown', 1, 'key', :s, 'A report about revenue.')"
                " RETURNING id"
            ),
            {"d": document_id, "n": version_number, "s": status},
        )
    ).scalar_one()
    await db.execute(
        text(
            "INSERT INTO chunks (document_version_id, chunk_index, heading_path, text, embedding)"
            " VALUES (:v, 0, CAST(:hp AS text[]), 'Revenue grew 12%.', CAST(:e AS vector))"
        ),
        {"v": version_id, "hp": ["Report"], "e": to_vector_literal(unit_vector(0))},
    )
    await db.commit()
    return document_id, version_id


async def seed_notebook(db: AsyncSession) -> uuid.UUID:
    notebook_id: uuid.UUID = (
        await db.execute(
            text("INSERT INTO notebooks (title) VALUES ('N') RETURNING id")
        )
    ).scalar_one()
    await db.commit()
    return notebook_id


async def test_retrieval_returns_the_ready_chunk_with_its_similarity(
    db: AsyncSession,
) -> None:
    notebook_id = await seed_notebook(db)
    document_id, version_id = await seed_version(db, notebook_id)

    # Orthogonal to the chunk: similarity 0 (the spec's "close to 0").
    chunks = await retrieve_chunks(db, notebook_id, unit_vector(1))
    assert len(chunks) == 1 and abs(chunks[0].similarity) < 1e-6
    chunk = chunks[0]
    assert isinstance(chunk, RetrievedChunk)
    assert chunk.document_id == document_id
    assert chunk.document_version_id == version_id
    assert chunk.filename == "report.md"
    assert chunk.heading_path == ["Report"] and isinstance(chunk.heading_path, list)
    assert chunk.text == "Revenue grew 12%."
    assert chunk.chat_snippet == "A report about revenue."

    # The same direction: similarity 1.
    same = await retrieve_chunks(db, notebook_id, unit_vector(0))
    assert len(same) == 1 and abs(same[0].similarity - 1.0) < 1e-6

    # Another Notebook sees nothing.
    assert await retrieve_chunks(db, await seed_notebook(db), unit_vector(0)) == []


async def test_retrieval_skips_versions_that_are_not_ready(db: AsyncSession) -> None:
    notebook_id = await seed_notebook(db)
    await seed_version(db, notebook_id, status="indexing")
    assert await retrieve_chunks(db, notebook_id, unit_vector(0)) == []


async def test_retrieval_reads_only_the_latest_version(db: AsyncSession) -> None:
    """A re-upload still ingesting hides the superseded Version's chunks (docs/versioning.md)."""
    notebook_id = await seed_notebook(db)
    document_id, _ = await seed_version(db, notebook_id)
    assert len(await retrieve_chunks(db, notebook_id, unit_vector(0))) == 1

    await seed_version(
        db, notebook_id, status="converting", document_id=document_id, version_number=2
    )
    assert await retrieve_chunks(db, notebook_id, unit_vector(0)) == []


async def test_retrieval_honours_the_limit_and_orders_closest_first(
    db: AsyncSession,
) -> None:
    notebook_id = await seed_notebook(db)
    _, version_id = await seed_version(db, notebook_id)
    await db.execute(
        text(
            "INSERT INTO chunks (document_version_id, chunk_index, heading_path, text, embedding)"
            " VALUES (:v, 1, CAST(:hp AS text[]), 'Costs fell.', CAST(:e AS vector))"
        ),
        {"v": version_id, "hp": [], "e": to_vector_literal(unit_vector(1))},
    )
    await db.commit()

    chunks = await retrieve_chunks(db, notebook_id, unit_vector(1))
    assert [c.text for c in chunks] == ["Costs fell.", "Revenue grew 12%."]
    assert len(await retrieve_chunks(db, notebook_id, unit_vector(1), limit=1)) == 1


# T16 step 2: locating Citations needs `chunk_ranges`, so it lives with the database tests.
async def test_locate_citations_fills_ranges_where_a_row_exists(
    db: AsyncSession,
) -> None:
    notebook_id = await seed_notebook(db)
    _, version_id = await seed_version(db, notebook_id)
    await db.execute(
        text(
            "INSERT INTO chunks (document_version_id, chunk_index, heading_path, text, embedding)"
            " VALUES (:v, 1, CAST(:hp AS text[]), 'Costs fell.', CAST(:e AS vector))"
        ),
        {"v": version_id, "hp": [], "e": to_vector_literal(unit_vector(1))},
    )
    await db.execute(
        text(
            "INSERT INTO chunk_ranges (chunk_id, char_start, char_end)"
            " SELECT id, 10, 27 FROM chunks WHERE document_version_id = :v AND chunk_index = 0"
        ),
        {"v": version_id},
    )
    await db.commit()
    chunks = await retrieve_chunks(db, notebook_id, unit_vector(0))
    assert [c.text for c in chunks] == ["Revenue grew 12%.", "Costs fell."]

    located = await locate_citations(
        db, resolve_citation_markers("A [1]. B [2].", chunks)
    )
    assert [(c.marker, c.char_start, c.char_end) for c in located] == [
        (1, 10, 27),
        (2, None, None),
    ]
    assert located[0].chunk is chunks[0]
    assert await locate_citations(db, []) == []
