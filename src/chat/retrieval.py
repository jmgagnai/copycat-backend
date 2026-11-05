import uuid
from dataclasses import dataclass

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from document.searchable_versions import SEARCHABLE_VERSIONS_CTE
from ingestion.embed_chunks import to_vector_literal


@dataclass(frozen=True)
class RetrievedChunk:
    chunk_id: uuid.UUID
    document_id: uuid.UUID
    document_version_id: uuid.UUID
    filename: str
    heading_path: list[str]
    text: str
    chat_snippet: str | None
    similarity: float


DEFAULT_RETRIEVAL_LIMIT = 12


async def retrieve_chunks(
    db: AsyncSession,
    notebook_id: uuid.UUID,
    query_embedding: list[float],
    limit: int = DEFAULT_RETRIEVAL_LIMIT,
) -> list[RetrievedChunk]:
    rows = await db.execute(
        text(
            f"WITH {SEARCHABLE_VERSIONS_CTE}"
            " SELECT c.id AS chunk_id, l.document_id, l.version_id AS document_version_id, l.filename,"
            " c.heading_path, c.text, l.chat_snippet, 1 - (c.embedding <=> CAST(:q AS vector)) AS similarity"
            " FROM chunks c JOIN searchable_versions l ON l.version_id = c.document_version_id"
            " ORDER BY c.embedding <=> CAST(:q AS vector), c.id LIMIT :limit"
        ),
        {
            "notebook_id": notebook_id,
            "q": to_vector_literal(query_embedding),
            "limit": limit,
        },
    )
    return [
        RetrievedChunk(
            r.chunk_id,
            r.document_id,
            r.document_version_id,
            r.filename,
            list(r.heading_path),
            r.text,
            r.chat_snippet,
            float(r.similarity),
        )
        for r in rows
    ]
