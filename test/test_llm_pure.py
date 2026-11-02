"""T11 step 5: no database, no network."""

from collections.abc import AsyncIterator

import httpx
import pytest

from llm.openrouter import (
    ChatCompletionRequest,
    OpenRouterClient,
    decode_deltas,
    with_retries,
)

REQUEST = ChatCompletionRequest(
    "m", "Answer in one word.", "Capital of France?", max_output_tokens=5
)


async def _lines(*lines: str) -> AsyncIterator[str]:
    for line in lines:
        yield line


async def test_decode_deltas_reads_data_lines_only() -> None:
    lines = _lines(
        ": OPENROUTER PROCESSING",
        'data: {"choices":[{"delta":{"content":"Pa"}}]}',
        'data: {"choices":[{"delta":{"content":"ris"}}]}',
        "data: [DONE]",
    )
    assert [d async for d in decode_deltas(lines)] == ["Pa", "ris"]


async def test_decode_deltas_skips_malformed_frames_and_stops_at_done() -> None:
    lines = _lines(
        "data: {",
        'data: {"choices":[]}',
        'data: {"choices":[{"delta":{"role":"assistant"}}]}',
        'data: {"choices":[{"delta":{"content":"ok"}}]}',
        "data: [DONE]",
        'data: {"choices":[{"delta":{"content":"NOT READ"}}]}',
    )
    assert [d async for d in decode_deltas(lines)] == ["ok"]


async def test_with_retries_recovers_then_gives_up() -> None:
    calls = 0

    async def flaky() -> str:
        nonlocal calls
        calls += 1
        if calls < 3:
            raise ConnectionError("blip")
        return "ok"

    assert await with_retries(flaky, retries=2, retry_delay_s=0) == "ok" and calls == 3

    calls = 0
    with pytest.raises(ConnectionError):
        await with_retries(flaky, retries=1, retry_delay_s=0)
    assert calls == 2


def _client(handler) -> OpenRouterClient:
    return OpenRouterClient(
        "k",
        http=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
        retry_delay_s=0,
    )


async def test_complete_parses_the_answer() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(
            200, json={"choices": [{"message": {"content": "Paris"}}]}
        )

    assert await _client(handler).complete(REQUEST) == "Paris"
    sent = seen[0]
    assert (
        sent.url.path == "/api/v1/chat/completions"
        and sent.headers["authorization"] == "Bearer k"
    )
    body = sent.read().decode()
    assert '"max_tokens":5' in body.replace(" ", "") and '"stream"' not in body


async def test_complete_rejects_an_error_body_after_retrying() -> None:
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(200, json={"error": {"message": "model is down"}})

    with pytest.raises(RuntimeError, match="model is down"):
        await _client(handler).complete(REQUEST)
    assert calls == 3  # one attempt plus the two default retries


async def test_stream_yields_the_deltas() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert (
            request.headers["accept"] == "text/event-stream"
            and b'"stream":true' in request.read()
        )
        body = 'data: {"choices":[{"delta":{"content":"Par"}}]}\n\ndata: {"choices":[{"delta":{"content":"is"}}]}\n\ndata: [DONE]\n\n'
        return httpx.Response(
            200, content=body.encode(), headers={"content-type": "text/event-stream"}
        )

    assert [d async for d in _client(handler).stream(REQUEST)] == ["Par", "is"]


async def test_embedder_batches_and_keeps_order() -> None:
    from llm.embeddings import OpenRouterEmbedder

    batches: list[list[str]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        import json

        body = json.loads(request.read())
        assert request.url.path == "/api/v1/embeddings" and body["model"] == "emb"
        batches.append(body["input"])
        # one tiny vector per text, encoding the text's index so order can be checked
        return httpx.Response(
            200,
            json={
                "data": [{"embedding": [float(t.split()[1])]} for t in body["input"]]
            },
        )

    embed = OpenRouterEmbedder(
        "k",
        "emb",
        http=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
        batch_size=32,
    )
    vectors = await embed([f"text {i}" for i in range(70)])
    assert [len(b) for b in batches] == [32, 32, 6]
    assert vectors == [[float(i)] for i in range(70)]
    assert await embed([]) == [] and len(batches) == 3  # nothing sent for no texts
