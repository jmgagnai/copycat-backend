"""Stage 1's converter: one `docker run --rm` of the pinned Docling image per conversion, with
the input file and the output directory bind-mounted in (see NOTEBOOKS docs/ingestion-docling.md)."""

import asyncio
import re
from collections.abc import Awaitable, Callable
from pathlib import Path

from settings import settings

from .embedded_pictures import without_embedded_pictures
from .stage import IngestionFailure

# The seam between the job and Docling: two paths in, the Markdown written to the second.
# Tests stub exactly this boundary with an `async def`.
MarkdownConverter = Callable[[Path, Path], Awaitable[None]]

# Where the pinned image keeps its models; without this flag every PDF fails after ten seconds
# trying to download them (the container runs with --network none).
DOCLING_ARTIFACTS_PATH = "/opt/app-root/src/.cache/docling/models"
CONTAINER_INPUT_DIR = "/work/in"
CONTAINER_OUTPUT_DIR = "/work/out"
MIN_TEXT_CHARS_FOR_TEXT_PDF = 20
_NON_TEXT = re.compile(r"[\W_]", re.UNICODE)


def looks_scanned(markdown: str) -> bool:
    """Whether Docling's Markdown looks like it came from a scanned PDF: once the embedded
    pictures, `<!-- image -->` placeholders and punctuation are gone, essentially no letters remain."""
    textual = re.sub(r"<!--[\s\S]*?-->", "", without_embedded_pictures(markdown))
    return len(_NON_TEXT.sub("", textual)) < MIN_TEXT_CHARS_FOR_TEXT_PDF


def markdown_output_path(directory: Path) -> Path:
    return directory / "converted.md"


class DoclingConverter:
    """An instance is a MarkdownConverter. Tables run in `fast` mode by default; the timeout is a
    hard cap."""

    def __init__(
        self,
        image: str | None = None,
        timeout_ms: int | None = None,
        table_mode: str | None = None,
    ):
        self.image = image or settings.DOCLING_IMAGE
        self.timeout_ms = timeout_ms or settings.DOCLING_TIMEOUT_MS
        self.table_mode = table_mode or settings.DOCLING_TABLE_MODE

    async def __call__(self, input_path: Path, output_path: Path) -> None:
        input_name = input_path.name
        output_dir = output_path.parent
        # (1) The CLI names its output after the input stem; it is renamed to what the caller asked.
        produced = output_dir / f"{input_path.stem}.md"
        args = [
            "run", "--rm", "--init", "--network", "none",
            "--volume", f"{input_path}:{CONTAINER_INPUT_DIR}/{input_name}:ro",
            "--volume", f"{output_dir}:{CONTAINER_OUTPUT_DIR}",
            "--entrypoint", "docling", self.image,
            "--artifacts-path", DOCLING_ARTIFACTS_PATH,
            "--table-mode", self.table_mode, "--to", "md", "--output", CONTAINER_OUTPUT_DIR,
            f"{CONTAINER_INPUT_DIR}/{input_name}",
        ]  # fmt: skip
        proc = await asyncio.create_subprocess_exec(
            settings.DOCKER_BIN,
            *args,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
        )
        try:
            out, _ = await asyncio.wait_for(
                proc.communicate(), timeout=self.timeout_ms / 1000
            )
        except TimeoutError:
            proc.kill()  # (2) a timeout is a failure with a reason
            raise IngestionFailure(
                "timed-out", f"Docling timed out converting {input_name}."
            ) from None
        diagnostics = out.decode(errors="replace")[:8000].strip()
        # (3) A zero exit code is not proof of success: the CLI logs "failed to convert", writes
        # no file, and still exits 0.
        if proc.returncode != 0 or not produced.exists():
            raise IngestionFailure(
                "unreadable",
                f"Docling exited with code {proc.returncode}: {diagnostics}",
            )
        # (4) OCR is disabled: a scanned PDF converts to pictures and placeholders only.
        if input_path.suffix.lower() == ".pdf" and looks_scanned(produced.read_text()):
            raise IngestionFailure(
                "no-text-layer",
                f"{input_name} has no text layer (a scanned PDF), and OCR is disabled.",
            )
        if produced != output_path:
            produced.rename(output_path)
