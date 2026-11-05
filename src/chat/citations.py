import re
from dataclasses import dataclass, replace

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from .retrieval import RetrievedChunk


@dataclass(frozen=True)
class ResolvedCitation:
    marker: int
    chunk: RetrievedChunk
    char_start: int | None = None
    char_end: int | None = None


CITATION_INSTRUCTIONS = (
    "- Cite your sources. Every Chunk you were given is labelled with a number, like [2].\n"
    "  End each sentence that makes a factual claim with the marker(s) of the Chunk(s) it came\n"
    '  from, e.g. "Revenue was 12.4M [2]." Use several markers when a claim draws on several\n'
    '  Chunks, each in its own brackets: "[1][3]".\n'
    "- Only ever use a marker that appears in the Chunks above. Never invent one, never cite a\n"
    "  source you were not given, and never cite a marker for a claim it does not support."
)

MARKER_GROUP = re.compile(r"\[\s*(\d{1,3}(?:\s*,\s*\d{1,3})*)\s*\]")


def resolve_citation_markers(
    answer: str, chunks: list[RetrievedChunk]
) -> list[ResolvedCitation]:
    by_marker: dict[int, ResolvedCitation] = {}
    for match in MARKER_GROUP.finditer(answer):
        for part in match.group(1).split(","):
            marker = int(part.strip())
            if 1 <= marker <= len(chunks) and marker not in by_marker:
                by_marker[marker] = ResolvedCitation(marker, chunks[marker - 1])
    return [by_marker[m] for m in sorted(by_marker)]


async def locate_citations(
    db: AsyncSession, citations: list[ResolvedCitation]
) -> list[ResolvedCitation]:

    rows = await db.execute(
        text(
            "SELECT chunk_id, char_start, char_end FROM chunk_ranges WHERE chunk_id = ANY(CAST(:ids AS uuid[]))"
        ),
        {"ids": [c.chunk.chunk_id for c in citations]},
    )
    ranges = {row.chunk_id: (row.char_start, row.char_end) for row in rows}
    return [
        replace(
            c,
            char_start=ranges[c.chunk.chunk_id][0],
            char_end=ranges[c.chunk.chunk_id][1],
        )
        if c.chunk.chunk_id in ranges
        else c
        for c in citations
    ]
