import re
from dataclasses import dataclass

_ATX_HEADING = re.compile(r"^(#{1,6})\s+(.*?)\s*#*\s*$")
_FENCE = re.compile(r"^\s*(```|~~~)")


@dataclass
class MarkdownSection:
    heading_path: list[str]
    heading: str | None
    level: int
    content: str


def split_markdown_sections(markdown: str) -> list[MarkdownSection]:
    sections: list[MarkdownSection] = []
    open_headings: list[str] = []
    current = MarkdownSection([], None, 0, "")
    body: list[str] = []
    open_fence: str | None = None

    def flush() -> None:
        nonlocal body
        current.content = "\n".join(body).strip()
        if current.level > 0 or current.content:
            sections.append(current)
        body = []

    for line in re.split(r"\r?\n", markdown):
        fence = _FENCE.match(line)
        if fence:
            if open_fence is None:
                open_fence = fence.group(1)
            elif open_fence == fence.group(1):
                open_fence = None
            body.append(line)
            continue
        if open_fence is not None:
            body.append(line)
            continue

        heading = _ATX_HEADING.match(line)
        if not heading:
            body.append(line)
            continue

        flush()
        level = len(heading.group(1))
        text = heading.group(2).strip()
        del open_headings[level - 1 :]
        open_headings.append(text)
        current = MarkdownSection(
            heading_path=list(open_headings), heading=text, level=level, content=""
        )
    flush()
    return sections
