import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from document.chunk_ranges import locate_in_markdown
from llm.embeddings import Embedder

from .chunking import CHUNK_OVERLAP, CHUNK_SIZE, DocumentChunk, chunk_markdown
from .stage import (
    EMBED_CHUNKS_QUEUE,
    DocumentVersionRef,
    IngestionVersion,
    load_version,
    set_version_status,
)

__all__ = ["EMBED_CHUNKS_QUEUE", "EmbedChunksDeps", "run_embed_chunks_job"]


@dataclass
class EmbedChunksDeps:
    db: AsyncSession
    embed: Embedder
    chunk_size: int = CHUNK_SIZE
    chunk_overlap: int = CHUNK_OVERLAP


def to_vector_literal(vector: list[float]) -> str:
    return "[" + ",".join(repr(x) for x in vector) + "]"


_INSERT_CHUNK = text(
    "INSERT INTO chunks (document_version_id, chunk_index, heading_path, text, embedding)"
    " VALUES (:v, :i, CAST(:hp AS text[]), :t, CAST(:e AS vector)) RETURNING id"
)
_INSERT_RANGE = text(
    "INSERT INTO chunk_ranges (chunk_id, char_start, char_end)"
    " VALUES (:chunk_id, :char_start, :char_end)"
)


async def replace_chunks(
    db: AsyncSession,
    version_id: uuid.UUID,
    markdown: str,
    chunks: list[DocumentChunk],
    vectors: list[list[float]],
) -> None:
    await db.execute(
        text("DELETE FROM chunks WHERE document_version_id = :id"), {"id": version_id}
    )
    ranges = locate_in_markdown(markdown, [c.text for c in chunks])
    for chunk, vector, located in zip(chunks, vectors, ranges, strict=True):
        chunk_id: uuid.UUID = (
            await db.execute(
                _INSERT_CHUNK,
                {
                    "v": version_id,
                    "i": chunk.index,
                    "hp": chunk.heading_path,
                    "t": chunk.text,
                    "e": to_vector_literal(vector),
                },
            )
        ).scalar_one()
        if located is not None:
            await db.execute(
                _INSERT_RANGE,
                {
                    "chunk_id": chunk_id,
                    "char_start": located.char_start,
                    "char_end": located.char_end,
                },
            )


async def run_embed_chunks_job(deps: EmbedChunksDeps, ref: DocumentVersionRef) -> None:
    row = await load_version(deps.db, ref, "markdown")
    if row is None:
        return
    version = IngestionVersion(
        row.notebook_id, ref.document_id, ref.version_id, row.filename
    )
    await set_version_status(deps.db, version, "indexing")

    try:
        if not row.markdown:
            raise RuntimeError("Version has no Converted Markdown to index")
        chunks = chunk_markdown(row.markdown, deps.chunk_size, deps.chunk_overlap)
        vectors = await deps.embed([c.text for c in chunks])
        await replace_chunks(deps.db, ref.version_id, row.markdown, chunks, vectors)
        now = datetime.now(UTC)
        await set_version_status(
            deps.db,
            version,
            "ready",
            embedded_at=now,
            chunk_ranges_located_at=now,
        )
    except Exception as err:
        await deps.db.rollback()
        await set_version_status(
            deps.db, version, "failed", error=err, failed_at="indexing"
        )
        raise
