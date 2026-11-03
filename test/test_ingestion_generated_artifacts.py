"""T12 step 3. No database, no network: the scripted completer of the tutorial answers by model
name."""

import pytest

from ingestion.generated_artifacts import (
    ARTIFACT_CHAR_BUDGET,
    GenerationDeps,
    generate_artifacts,
    parse_json_object,
    truncate,
)
from llm.models import TaskModels
from llm.openrouter import ChatCompletionRequest

MARKDOWN = (
    "# Report\n\n" + "Revenue grew 12% in 2024. " * 40 + "\n\n## Risks\n\nSome risks."
)

MODELS = TaskModels(
    metadata="meta",
    chat_snippet="snippet",
    executive_summary="exec",
    abstract="abstract",
)


def scripted() -> tuple[GenerationDeps, list[ChatCompletionRequest]]:
    calls: list[ChatCompletionRequest] = []

    async def complete(request: ChatCompletionRequest) -> str:
        calls.append(request)
        if request.model == "meta":
            return (
                'Sure:\n```json\n{"title": "Annual report", "authors": ["Ada"],'
                ' "documentType": "report", "keywords": ["a"]}\n```'
            )
        words = {"snippet": 150, "exec": 500, "abstract": 50}[request.model]
        return " ".join(["word"] * words) + "\n"

    return GenerationDeps(complete=complete, models=MODELS), calls


def test_truncate_marks_the_cut() -> None:
    assert truncate("abcdef", 6) == "abcdef"
    assert truncate("abcdef", 3) == "abc\n\n[truncated]"


def test_parse_json_object_unwraps_fences_and_rejects_prose() -> None:
    assert parse_json_object('Sure:\n```json\n{"title": "T", "authors": []}\n```') == {
        "title": "T",
        "authors": [],
    }
    with pytest.raises(ValueError):
        parse_json_object("no json here")
    with pytest.raises(ValueError):
        parse_json_object("[1, 2]")


async def test_generate_artifacts_makes_four_calls_in_order() -> None:
    deps, calls = scripted()
    result = await generate_artifacts(deps, filename="r.md", markdown=MARKDOWN)

    assert result.metadata["title"] == "Annual report"
    assert len(result.abstract.split()) == 50
    assert len(result.chat_snippet.split()) == 150
    assert len(result.executive_summary.split()) == 500
    assert not result.abstract.endswith("\n")
    assert [c.model for c in calls] == ["meta", "snippet", "exec", "abstract"]

    meta = calls[0]
    assert "Filename: r.md" in meta.user
    assert "Report\n  Risks" in meta.user
    assert '"keywords": string[]' in meta.system

    snippet = calls[1]
    assert snippet.system.startswith("You write a Chat Snippet")
    assert "Copy every number, unit and currency exactly as given." in snippet.system
    assert (
        "Length: between 150 and 300 words. Answer with the text only."
        in snippet.system
    )
    assert snippet.user.startswith(
        "Document: Annual report\nType: report\nAuthors: Ada\n\n"
    )
    assert snippet.max_output_tokens == 300 * 2 + 200


async def test_artifact_prompts_are_cut_at_the_budget() -> None:
    deps, calls = scripted()
    await generate_artifacts(deps, filename="r.md", markdown="x" * 200_000)
    assert all(
        c.user.endswith("[truncated]") and len(c.user) < 121_000 for c in calls[-3:]
    )
    assert all(len(c.user) > ARTIFACT_CHAR_BUDGET for c in calls[-3:])
    assert calls[0].user.endswith("[truncated]") and len(calls[0].user) < 13_000
