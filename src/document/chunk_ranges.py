from dataclasses import dataclass


@dataclass(frozen=True)
class ChunkRange:
    char_start: int
    char_end: int


def locate_in_markdown(markdown: str, texts: list[str]) -> list[ChunkRange | None]:
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
