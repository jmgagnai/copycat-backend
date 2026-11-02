"""Docling inlines pictures as base64 data URIs in its Markdown; they are not text. T12 reuses this."""

import re

_EMBEDDED_PICTURE = re.compile(r"!\[[^\]]*\]\(data:image/[^)]*\)")


def without_embedded_pictures(markdown: str) -> str:
    return _EMBEDDED_PICTURE.sub("", markdown)
