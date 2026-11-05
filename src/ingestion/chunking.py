import re
from dataclasses import dataclass

from .embedded_pictures import EMBEDDED_PICTURE
from .markdown_sections import split_markdown_sections

CHUNK_SIZE = 1000
CHUNK_OVERLAP = 150

SEPARATORS = ["\n\n", "\n", ". ", " ", ""]

_WORD_CHARACTER = re.compile(r"[^\W_]")


@dataclass(frozen=True)
class DocumentChunk:
    index: int
    heading_path: list[str]
    text: str


def split_keeping_separator(text: str, separator: str) -> list[str]:
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
    chunks: list[str] = []
    buffer: list[str] = []
    length = 0

    def flush() -> None:
        nonlocal buffer, length
        chunks.append("".join(buffer))
        if chunk_overlap <= 0:
            buffer, length = [], 0
            return
        kept: list[str] = []
        kept_length = 0
        for piece in reversed(buffer):
            if kept_length + len(piece) > chunk_overlap:
                break
            kept.insert(0, piece)
            kept_length += len(piece)
        if not kept:
            tail = buffer[-1][-chunk_overlap:]
            kept, kept_length = [tail], len(tail)
        buffer, length = kept, kept_length

    for piece in pieces:
        if length and length + len(piece) > chunk_size:
            flush()
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
    chunk_size = max(1, chunk_size)
    chunk_overlap = min(max(0, chunk_overlap), chunk_size - 1)

    chunks: list[DocumentChunk] = []
    for section in split_markdown_sections(markdown):
        stretches = EMBEDDED_PICTURE.split(section.content)
        for stretch in stretches:
            content = stretch.strip()
            if not content:
                continue
            if len(stretches) > 1 and not _WORD_CHARACTER.search(content):
                continue
            pieces = split_into_pieces(content, chunk_size, SEPARATORS)
            for text in merge_pieces(pieces, chunk_size, chunk_overlap):
                if trimmed := text.strip():
                    chunks.append(
                        DocumentChunk(len(chunks), section.heading_path, trimmed)
                    )
    return chunks
