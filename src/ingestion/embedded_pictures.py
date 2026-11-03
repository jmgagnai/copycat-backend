"""Docling embeds pictures on one line as `![Image](data:image/png;base64,...)`. They are not
text: the model reads words, and a base64 picture is thousands of useless characters of budget.
T10's scanned-document check and T12's summaries both strip them (T12 step 2).
"""

import re

# One embedded picture: a Markdown image whose target is a `data:` URI, on a single line.
EMBEDDED_PICTURE = re.compile(r"!\[[^\]\n]*\]\(data:[^)\s]*\)")


def without_embedded_pictures(markdown: str) -> str:
    return EMBEDDED_PICTURE.sub("", markdown)
