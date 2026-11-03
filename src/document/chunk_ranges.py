"""Where each Chunk sits in its Version's Converted Markdown (T13 step 2). Lives in `document/`
rather than `ingestion/` because T16's Citations read the same ranges that Stage 3 writes."""

from dataclasses import dataclass


@dataclass(frozen=True)
class ChunkRange:
    char_start: int
    char_end: int  # exclusive, as in `markdown[char_start:char_end]`


def locate_in_markdown(markdown: str, texts: list[str]) -> list[ChunkRange | None]:
    """One range per text, in chunk order, or None when a text is not found. Chunks are verbatim
    slices in document order, so a forward-moving `str.find` is enough. The cursor advances by
    one character, not to the end of the match, because consecutive chunks overlap."""
    cursor = 0
    ranges: list[ChunkRange | None] = []
    for text in texts:
        at = markdown.find(text, cursor)
        if at == -1:
            ranges.append(None)
            continue
        cursor = at + 1
        ranges.append(ChunkRange(at, at + len(text)))
    return ranges
