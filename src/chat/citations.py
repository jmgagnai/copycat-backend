import re
from dataclasses import dataclass, replace

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from .retrieval import RetrievedChunk


@dataclass(frozen=True)
class ResolvedCitation:
    """One Citation an answer earned: the Chunk a claim came from, the marker the model used,
    and where that Chunk's text sits in its Version's Converted Markdown."""

    marker: int
    chunk: RetrievedChunk
    char_start: int | None = None
    char_end: int | None = None


# Kept next to the parser that reads the markers back: the two are one contract. It calls the
# evidence "Chunks", GLOSSARY.md's word, because the model echoes its prompt's vocabulary.
CITATION_INSTRUCTIONS = (
    "- Cite your sources. Every Chunk you were given is labelled with a number, like [2].\n"
    "  End each sentence that makes a factual claim with the marker(s) of the Chunk(s) it came\n"
    '  from, e.g. "Revenue was 12.4M [2]." Use several markers when a claim draws on several\n'
    '  Chunks, each in its own brackets: "[1][3]".\n'
    "- Only ever use a marker that appears in the Chunks above. Never invent one, never cite a\n"
    "  source you were not given, and never cite a marker for a claim it does not support."
)

# One or more integers inside one pair of brackets; "[1, 3]" is accepted as well as "[1][3]".
MARKER_GROUP = re.compile(r"\[\s*(\d{1,3}(?:\s*,\s*\d{1,3})*)\s*\]")


def resolve_citation_markers(
    answer: str, chunks: list[RetrievedChunk]
) -> list[ResolvedCitation]:
    """Turns the markers in an answer into Citations against the Chunks actually retrieved for
    it: a marker is only ever resolved by indexing into that list, so a Citation cannot point at
    a Chunk the answer was not grounded in. A marker outside the list is ignored; the prose is
    recorded exactly as written."""
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
    """Fills in each Citation's character range from `chunk_ranges`; a Chunk with no row keeps a null range."""
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
