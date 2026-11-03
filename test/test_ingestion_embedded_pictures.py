"""T12 step 2. No database."""

from ingestion.embedded_pictures import EMBEDDED_PICTURE, without_embedded_pictures


def test_removes_the_embedded_picture_only() -> None:
    assert (
        without_embedded_pictures("a ![Image](data:image/png;base64,AAAA) b") == "a  b"
    )


def test_keeps_linked_pictures_and_spans_no_lines() -> None:
    markdown = "![alt](https://x/y.png)\n![Image](data:image/png;base64,QUJD)\ntext"
    assert without_embedded_pictures(markdown) == "![alt](https://x/y.png)\n\ntext"
    assert EMBEDDED_PICTURE.search("![a\nb](data:image/png;base64,QUJD)") is None
