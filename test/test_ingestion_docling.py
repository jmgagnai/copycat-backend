"""T10 step 2. No database. The timeout test starts Docker for a millisecond."""

import shutil
from pathlib import Path

import pytest

from ingestion.docling import DoclingConverter, looks_scanned
from ingestion.embedded_pictures import without_embedded_pictures
from ingestion.stage import IngestionFailure


def test_looks_scanned() -> None:
    assert looks_scanned("![Image](data:image/png;base64,QUJD)\n<!-- image -->")
    assert looks_scanned("")
    assert not looks_scanned("A real sentence with words in it.")


def test_without_embedded_pictures_keeps_the_text() -> None:
    markdown = "Before ![Figure 1](data:image/png;base64,QUJDREVG) after ![alt](https://x/y.png)"
    assert (
        without_embedded_pictures(markdown) == "Before  after ![alt](https://x/y.png)"
    )


@pytest.mark.skipif(shutil.which("docker") is None, reason="no docker")
async def test_docling_timeout_is_a_failure_reason(tmp_path: Path) -> None:
    (tmp_path / "x.pdf").write_bytes(b"%PDF-1.4 not really")
    with pytest.raises(IngestionFailure) as err:
        await DoclingConverter(timeout_ms=1)(tmp_path / "x.pdf", tmp_path / "out.md")
    assert err.value.reason == "timed-out"
