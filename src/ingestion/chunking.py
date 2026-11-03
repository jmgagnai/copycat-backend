"""Splits Converted Markdown into embeddable chunks: ingestion Stage 3's chunking half (T13
step 1). Two passes: T12's heading split, then a recursive character split within each section,
so no chunk straddles two headings and every chunk has one true heading path.

Chunk text is a verbatim, contiguous slice of the Markdown. The splitter never normalises
whitespace, and every separator stays attached to the piece before it, so joining the pieces
gives the input back. A Citation points at a chunk and must find that text in the document the
reader is shown; `chunk_ranges` (step 2) relies on it too.
"""

import re
from dataclasses import dataclass

from .embedded_pictures import EMBEDDED_PICTURE
from .markdown_sections import split_markdown_sections

CHUNK_SIZE = 1000  # target chunk size in characters
CHUNK_OVERLAP = (
    150  # characters of the previous chunk repeated at the start of the next
)

# Where to prefer a cut, strongest first: between paragraphs, lines, sentences, words, and only
# then mid-word. The empty string is the floor for a run with no separator at all.
SEPARATORS = ["\n\n", "\n", ". ", " ", ""]

_WORD_CHARACTER = re.compile(r"[^\W_]")


@dataclass(frozen=True)
class DocumentChunk:
    index: int  # position in the document, 0-based and contiguous
    heading_path: list[str]  # the enclosing headings, outermost first
    text: str  # a verbatim slice of the Markdown


def split_keeping_separator(text: str, separator: str) -> list[str]:
    """Splits on `separator`, leaving it attached to the end of the part it followed."""
    if separator == "":
        return [text]
    parts: list[str] = []
    start = 0
    while (at := text.find(separator, start)) != -1:
        parts.append(text[start : at + len(separator)])
        start = at + len(separator)
    if start < len(text):
        parts.append(text[start:])
    return parts


def split_into_pieces(text: str, chunk_size: int, separators: list[str]) -> list[str]:
    """Breaks `text` down until every piece fits `chunk_size`, trying each separator in turn and
    recursing only into the parts still too long. Concatenating the result reproduces `text`."""
    if not separators or separators[0] == "":
        return [text[i : i + chunk_size] for i in range(0, len(text), chunk_size)]
    separator, rest = separators[0], separators[1:]
    pieces: list[str] = []
    for part in split_keeping_separator(text, separator):
        if part == "":
            continue
        if len(part) <= chunk_size:
            pieces.append(part)
        else:
            pieces.extend(split_into_pieces(part, chunk_size, rest))
    return pieces


def merge_pieces(pieces: list[str], chunk_size: int, chunk_overlap: int) -> list[str]:
    """Reassembles pieces into chunks of at most `chunk_size` characters, each starting with the
    last `chunk_overlap` characters of the one before it. The overlap is taken back by whole
    pieces where it can be, and by raw characters only when one piece is longer than it."""
    chunks: list[str] = []
    buffer: list[str] = []
    length = 0

    def flush() -> None:
        nonlocal buffer, length
        chunks.append("".join(buffer))
        if chunk_overlap <= 0:
            buffer, length = [], 0
            return
        # Walk back from the end taking whole pieces while they fit the overlap.
        kept: list[str] = []
        kept_length = 0
        for piece in reversed(buffer):
            if kept_length + len(piece) > chunk_overlap:
                break
            kept.insert(0, piece)
            kept_length += len(piece)
        if not kept:
            # (1) One piece longer than the whole overlap: take its tail, so the chunks still
            # overlap at all rather than starting mid-sentence with no overlap.
            tail = buffer[-1][-chunk_overlap:]
            kept, kept_length = [tail], len(tail)
        buffer, length = kept, kept_length

    for piece in pieces:
        if length and length + len(piece) > chunk_size:
            flush()
        # (2) The carried overlap plus this piece can itself exceed the chunk size. Overlap is
        # given up rather than the size: drop pieces from the front, then cut the last one.
        while len(buffer) > 1 and length + len(piece) > chunk_size:
            length -= len(buffer[0])
            del buffer[0]
        if len(buffer) == 1 and length + len(piece) > chunk_size:
            room = chunk_size - len(piece)
            kept = buffer[0][-room:] if room > 0 else ""
            buffer = [kept] if kept else []
            length = len(kept)
        buffer.append(piece)
        length += len(piece)
    if length:
        chunks.append("".join(buffer))
    return chunks


def chunk_markdown(
    markdown: str, chunk_size: int = CHUNK_SIZE, chunk_overlap: int = CHUNK_OVERLAP
) -> list[DocumentChunk]:
    """A heading with no body contributes no chunk but still appears in its children's paths.
    An embedded picture cuts its section in two, and no chunk holds any part of it."""
    chunk_size = max(1, chunk_size)
    # An overlap at or above the chunk size could never advance.
    chunk_overlap = min(max(0, chunk_overlap), chunk_size - 1)

    chunks: list[DocumentChunk] = []
    for section in split_markdown_sections(markdown):
        stretches = EMBEDDED_PICTURE.split(section.content)
        for stretch in stretches:
            content = stretch.strip()
            if not content:
                continue
            # A picture in a list item or a table cell leaves its bullet or pipes behind:
            # Markdown around a picture, not text to embed.
            if len(stretches) > 1 and not _WORD_CHARACTER.search(content):
                continue
            pieces = split_into_pieces(content, chunk_size, SEPARATORS)
            for text in merge_pieces(pieces, chunk_size, chunk_overlap):
                if trimmed := text.strip():
                    chunks.append(
                        DocumentChunk(len(chunks), section.heading_path, trimmed)
                    )
    return chunks
