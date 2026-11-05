import re

EMBEDDED_PICTURE = re.compile(r"!\[[^\]\n]*\]\(data:[^)\s]*\)")


def without_embedded_pictures(markdown: str) -> str:
    return EMBEDDED_PICTURE.sub("", markdown)
