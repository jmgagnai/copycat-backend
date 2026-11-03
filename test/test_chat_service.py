"""T16 step 4: `stream_answer` end to end with a fake streamer and embedder, on the T05 `db`
fixture. No network."""

from collections.abc import AsyncIterator

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from chat.chat_dto import ChatMessageResponse
from chat.chat_service import (
    CHAT_SYSTEM_PROMPT,
    NO_SOURCES_ANSWER,
    ChatDeps,
    build_user_turn,
    format_history,
    format_sources,
    stream_answer,
)
from chat.retrieval import retrieve_chunks
from llm.openrouter import ChatCompletionRequest
from test.test_chat_pure import chunk
from test.test_chat_retrieval import seed_notebook, seed_version, unit_vector


async def fake_embed(texts: list[str]) -> list[list[float]]:
    return [unit_vector(0) for _ in texts]


def streamer(text: str) -> tuple[ChatDeps, list[ChatCompletionRequest]]:
    requests: list[ChatCompletionRequest] = []

    async def fake_stream(request: ChatCompletionRequest) -> AsyncIterator[str]:
        requests.append(request)
        for piece in [text[:5], text[5:]]:
            yield piece

    return ChatDeps(stream=fake_stream, embed=fake_embed, model="m"), requests


async def test_stream_answer_streams_paragraphs_and_resolves_markers(
    db: AsyncSession,
) -> None:
    notebook_id = await seed_notebook(db)
    await seed_version(db, notebook_id)
    deps, requests = streamer("Para one [1].\n\nPara two.")
    pieces: list[str] = []

    async def on_chunk(piece: str) -> None:
        pieces.append(piece)

    answer = await stream_answer(db, deps, notebook_id, "What grew?", [], on_chunk)

    assert pieces == ["Para one [1].", "Para two."]
    assert answer.text == "Para one [1].\n\nPara two."
    assert [c.marker for c in answer.citations] == [1]
    assert answer.citations[0].chunk.text == "Revenue grew 12%."
    (request,) = requests
    assert request.model == "m" and request.system == CHAT_SYSTEM_PROMPT
    assert request.user.startswith("## Sources\n\n### Source: report.md")
    assert "Chunk [1] (under Report):\nRevenue grew 12%." in request.user
    assert "## The Chat Thread so far" not in request.user
    assert request.user.endswith("## The question to answer now\n\nWhat grew?")


async def test_stream_answer_says_so_without_sources(db: AsyncSession) -> None:
    notebook_id = await seed_notebook(db)

    async def never_stream(request: ChatCompletionRequest) -> AsyncIterator[str]:
        raise AssertionError("the model must not be called without sources")
        yield ""  # makes this an async generator

    pieces: list[str] = []

    async def on_chunk(piece: str) -> None:
        pieces.append(piece)

    deps = ChatDeps(stream=never_stream, embed=fake_embed, model="m")
    answer = await stream_answer(db, deps, notebook_id, "What?", [], on_chunk)
    assert answer.text == NO_SOURCES_ANSWER and answer.citations == []
    assert pieces == [NO_SOURCES_ANSWER]


async def test_stream_answer_raises_on_an_empty_answer(db: AsyncSession) -> None:
    notebook_id = await seed_notebook(db)
    await seed_version(db, notebook_id)
    deps, _ = streamer("   \n\n ")

    async def on_chunk(piece: str) -> None:
        raise AssertionError("nothing to show")

    with pytest.raises(RuntimeError):
        await stream_answer(db, deps, notebook_id, "What?", [], on_chunk)


async def test_prompt_formatting(db: AsyncSession) -> None:
    notebook_id = await seed_notebook(db)
    await seed_version(db, notebook_id)
    chunks = await retrieve_chunks(db, notebook_id, unit_vector(0))
    sources = format_sources(chunks)
    assert sources.startswith(
        "### Source: report.md\n\nAbout this source: A report about"
    )
    assert sources.endswith("Chunk [1] (under Report):\nRevenue grew 12%.")

    message = ChatMessageResponse.model_validate(
        {
            "id": chunks[0].chunk_id,
            "thread_id": chunks[0].document_id,
            "role": "user",
            "content": "Earlier?",
            "asked_by": {"id": chunks[0].chunk_id, "email": "a@example.com"},
            "citations": [],
            "created_at": "2026-01-01T00:00:00Z",
        }
    )
    assert format_history([message]) == "Question: Earlier?"
    assert format_history([]) == ""
    turn = build_user_turn(chunks, [message], "Now?")
    assert "## The Chat Thread so far\n\nQuestion: Earlier?" in turn
    # Two chunks of one source are introduced by that source once.
    two = format_sources([chunk("a"), chunk("b")])
    assert two.count("### Source:") == 2  # distinct Versions: two sources
