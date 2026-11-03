"""Stage 2's generation code (T12 step 3): the metadata and the three summaries, each one model
call over the Converted Markdown cut at a character budget. Pure: it takes a completer and the
model names, and returns text. No database, no queue, no module-level client.

Anything past a budget is simply not seen by the model; that is accepted by decision. The Node
extras (section summaries, corrective rewrite, trimming, warnings, resumable cache) are skipped on
purpose.
"""

import json
import re
from dataclasses import dataclass
from typing import Any, cast

from llm.models import TaskModels
from llm.openrouter import ChatCompleter, ChatCompletionRequest

from .markdown_sections import MarkdownSection, split_markdown_sections

# name -> (min words, max words, brief). Briefs and word ranges from the Node
# `generated-artifacts.ts`; the name is also the `TaskModels` attribute that runs it.
ARTIFACT_BRIEFS: dict[str, tuple[int, int, str]] = {
    # "Optimized for a model to read, not a human" (GLOSSARY.md).
    "chat_snippet": (
        150,
        300,
        (
            "a Chat Snippet: a dense, factual description of this document that will be injected into"
            " another language model's context as grounding about this source. Write it for a model"
            " to read, not a human: no preamble, no hedging, no marketing tone. State what the"
            " document is, what it covers, the entities, dates and figures that identify it, and what"
            " kinds of question it can answer."
        ),
    ),
    # "Shown first when a user opens a document" (GLOSSARY.md).
    "executive_summary": (
        500,
        1000,
        (
            "an Executive Summary: a one-to-two-page summary of this document's key points for a human"
            " reader who will decide from it whether to read the full document. Use short Markdown"
            " sections with headings and bullet points where they help. Cover the document's purpose,"
            " its main findings or provisions, and any conclusions, obligations or figures a reader"
            ' must not miss. Do not begin with a title or an "Executive Summary" heading - the page'
            " already shows one - but open with your first section."
        ),
    ),
    "abstract": (
        50,
        100,
        (
            "an Abstract: a single short paragraph describing what this document is, to be skimmed in"
            " a list of search results and on a document card. Plain prose, no headings, no bullet"
            " points, no Markdown. It must help a reader judge relevance at a glance - it does not"
            " stand in for the document."
        ),
    ),
}

# A rough rule: four characters per token. 120,000 characters is about 30k tokens, within the
# default models' windows with room for the answer. Lower it if a model rejects the prompt.
METADATA_CHAR_BUDGET = 12_000
ARTIFACT_CHAR_BUDGET = 120_000

METADATA_OUTLINE_MAX_HEADINGS = 80

METADATA_SYSTEM = (
    "You extract bibliographic metadata from a document. Answer with a single JSON object and"
    " nothing else, with exactly this shape:\n"
    '{"title": string|null, "authors": string[], "documentType": string|null,'
    ' "language": string|null, "publishedOn": string|null, "subject": string|null,'
    ' "keywords": string[]}\n'
    "Rules: at most 10 keywords. Use null when the document does not state a value. Never infer"
    " an author from the filename. Copy names, dates and titles exactly as written."
)


def truncate(text: str, limit: int) -> str:
    """Cuts at the budget and says so, so the model does not treat the cut as the end."""
    return text if len(text) <= limit else f"{text[:limit]}\n\n[truncated]"


def parse_json_object(text: str) -> dict[str, Any]:
    """Models wrap JSON in a code fence or add a sentence: pull the outermost braces out first.
    No object at all is a `ValueError`, which the job records as an `unexpected` failure."""
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if not match:
        raise ValueError(f"Expected a JSON object, got: {text[:200]}")
    parsed: Any = json.loads(match.group(0))
    if isinstance(parsed, dict):
        return cast(dict[str, Any], parsed)
    raise ValueError(f"Expected a JSON object, got: {text[:200]}")


@dataclass
class GenerationDeps:
    """What the generation code needs: the job builds it from the real client, tests from a
    fake. No patching."""

    complete: ChatCompleter
    models: TaskModels


@dataclass
class GenerationResult:
    metadata: dict[str, Any]
    chat_snippet: str
    executive_summary: str
    abstract: str


def heading_outline(sections: list[MarkdownSection]) -> str:
    """One line per heading, indented by level, first 80 only: the document's shape in a few
    hundred characters, for the metadata call."""
    lines = [
        f"{'  ' * (s.level - 1)}{s.heading}" for s in sections if s.heading is not None
    ]
    return "\n".join(lines[:METADATA_OUTLINE_MAX_HEADINGS])


async def extract_metadata(
    deps: GenerationDeps,
    *,
    filename: str,
    markdown: str,
    sections: list[MarkdownSection],
) -> dict[str, Any]:
    outline = heading_outline(sections)
    user = (
        f"Filename: {filename}\n\n"
        f"Heading outline:\n{outline or '(no headings)'}\n\n"
        f"Document:\n{truncate(markdown, METADATA_CHAR_BUDGET)}"
    )
    answer = await deps.complete(
        ChatCompletionRequest(
            model=deps.models.metadata,
            system=METADATA_SYSTEM,
            user=user,
            max_output_tokens=600,
        )
    )
    return parse_json_object(answer)


def _artifact_header(filename: str, metadata: dict[str, Any]) -> str:
    """`Document:` always; `Type:` and `Authors:` only when the metadata states them."""
    lines = [f"Document: {metadata.get('title') or filename}"]
    if document_type := metadata.get("documentType"):
        lines.append(f"Type: {document_type}")
    authors = metadata.get("authors")
    if isinstance(authors, list) and authors:
        names = [str(a) for a in cast(list[object], authors)]
        lines.append(f"Authors: {', '.join(names)}")
    return "\n".join(lines)


async def generate_artifact(
    deps: GenerationDeps,
    name: str,
    *,
    filename: str,
    metadata: dict[str, Any],
    markdown: str,
) -> str:
    min_words, max_words, brief = ARTIFACT_BRIEFS[name]
    system = (
        f"You write {brief}\n\n"
        "Use only what the text below states. Do not add facts. Copy every number, unit and"
        " currency exactly as given.\n\n"
        f"Length: between {min_words} and {max_words} words. Answer with the text only."
    )
    user = (
        f"{_artifact_header(filename, metadata)}\n\n"
        f"{truncate(markdown, ARTIFACT_CHAR_BUDGET)}"
    )
    answer = await deps.complete(
        ChatCompletionRequest(
            model=getattr(deps.models, name),
            system=system,
            user=user,
            max_output_tokens=max_words * 2 + 200,
        )
    )
    return answer.strip()


async def generate_artifacts(
    deps: GenerationDeps, *, filename: str, markdown: str
) -> GenerationResult:
    """Four calls in total: metadata, then chat snippet, executive summary and abstract."""
    sections = split_markdown_sections(markdown)
    metadata = await extract_metadata(
        deps, filename=filename, markdown=markdown, sections=sections
    )
    texts = {
        name: await generate_artifact(
            deps, name, filename=filename, metadata=metadata, markdown=markdown
        )
        for name in ARTIFACT_BRIEFS
    }
    return GenerationResult(metadata, **texts)
