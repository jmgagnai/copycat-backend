"""Splits Converted Markdown on its ATX heading structure (T12 step 1). Stage 2 only needs the
heading outline from this; T13's chunking is the real user.

Only ATX headings (`# Heading`) are recognised, because that is what Docling emits; Setext
underlining never appears in its output. Headings inside fenced code blocks are ignored: a shell
comment in a code sample is not a document section.
"""

import re
from dataclasses import dataclass

_ATX_HEADING = re.compile(r"^(#{1,6})\s+(.*?)\s*#*\s*$")
_FENCE = re.compile(r"^\s*(```|~~~)")


@dataclass
class MarkdownSection:
    """One heading-delimited slice of a document. `heading_path` is the chain of enclosing
    headings, outermost first, including this section's own heading, so a section under
    `## Risks` inside `# Report` carries `["Report", "Risks"]`. The text before the first
    heading has an empty path, no heading and level 0."""

    heading_path: list[str]
    heading: str | None
    level: int
    content: str


def split_markdown_sections(markdown: str) -> list[MarkdownSection]:
    """The preamble (text before the first heading) is a section only if it has content; a heading
    with no body still yields a section, because it carries the path of everything beneath it."""
    sections: list[MarkdownSection] = []
    # Index i holds the heading text currently open at level i + 1.
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
            # A fence of the same marker closes the block; a different one inside it is content.
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
        # A level-2 heading cuts the open list at index 1 and appends; a document that skips a
        # level (`###` right under `#`) simply gets a shorter path.
        del open_headings[level - 1 :]
        open_headings.append(text)
        current = MarkdownSection(
            heading_path=list(open_headings), heading=text, level=level, content=""
        )
    flush()
    return sections
