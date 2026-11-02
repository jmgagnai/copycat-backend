"""The OpenRouter chat client: one completion, or the same request streamed as text deltas.
OpenRouter speaks the OpenAI format."""

import asyncio
import json
from collections.abc import AsyncIterator, Awaitable, Callable
from dataclasses import dataclass
from typing import Any

import httpx

OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"


@dataclass(frozen=True)
class ChatCompletionRequest:
    """One generation request: a system instruction and a single user turn is everything the
    pipeline needs. `model` comes from `TaskModels`, never from a user."""

    model: str
    system: str
    user: str
    max_output_tokens: int | None = None
    temperature: float = 0.2


# The seams everything downstream depends on (T12 takes a completer, T16 a streamer); tests
# pass an `async def`.
ChatCompleter = Callable[[ChatCompletionRequest], Awaitable[str]]
ChatStreamer = Callable[[ChatCompletionRequest], AsyncIterator[str]]


async def with_retries[T](
    attempt: Callable[[], Awaitable[T]], *, retries: int, retry_delay_s: float
) -> T:
    """Runs `attempt` again after any failure, with a doubling delay, and re-raises the last
    error. `attempt` must build a fresh coroutine each time (a lambda or a partial)."""
    for i in range(retries + 1):
        try:
            return await attempt()
        except Exception:
            if i == retries:
                raise
            await asyncio.sleep(retry_delay_s * 2**i)
    raise AssertionError("unreachable")


def headers(api_key: str) -> dict[str, str]:
    return {
        "authorization": f"Bearer {api_key}",
        "content-type": "application/json",
        # OpenRouter attributes traffic by these two; they make this app's spend identifiable.
        "http-referer": "https://github.com/rag-notebook",
        "x-title": "RAG Notebook",
    }


class OpenRouterClient:
    def __init__(
        self,
        api_key: str,
        *,
        base_url: str = OPENROUTER_BASE_URL,
        http: httpx.AsyncClient
        | None = None,  # (1) injectable, for httpx.MockTransport in tests
        retries: int = 2,
        retry_delay_s: float = 0.5,
        timeout_s: float = 120,  # model calls take tens of seconds
    ):
        self._url = f"{base_url.rstrip('/')}/chat/completions"
        self._headers = headers(api_key)
        self._http = http or httpx.AsyncClient(timeout=timeout_s)
        self._retries = retries
        self._retry_delay_s = retry_delay_s

    def _body(self, request: ChatCompletionRequest, stream: bool) -> dict[str, Any]:
        body: dict[str, Any] = {
            "model": request.model,
            "temperature": request.temperature,
            "messages": [
                {"role": "system", "content": request.system},
                {"role": "user", "content": request.user},
            ],
        }
        if request.max_output_tokens is not None:
            body["max_tokens"] = request.max_output_tokens
        if stream:
            body["stream"] = True
        return body

    async def _complete(self, request: ChatCompletionRequest) -> str:
        response = await self._http.post(
            self._url, headers=self._headers, json=self._body(request, stream=False)
        )
        response.raise_for_status()
        payload = response.json()
        if "error" in payload:  # (2) a 200 can still carry an error...
            raise RuntimeError(
                f"OpenRouter error for model {request.model}: {payload['error']}"
            )
        text = payload["choices"][0]["message"]["content"]
        if not text or not text.strip():  # (2) ...or an empty answer
            raise RuntimeError(
                f"OpenRouter returned no content for model {request.model}."
            )
        return text

    async def complete(self, request: ChatCompletionRequest) -> str:
        # (3) retried: nothing has been consumed yet; the lambda builds a fresh coroutine per attempt
        return await with_retries(
            lambda: self._complete(request),
            retries=self._retries,
            retry_delay_s=self._retry_delay_s,
        )

    async def stream(self, request: ChatCompletionRequest) -> AsyncIterator[str]:
        """The same request with `stream: true`, yielding the provider's text deltas."""
        # (4) not retried: once a delta has been yielded there is no clean way to start over
        async with self._http.stream(
            "POST",
            self._url,
            headers={**self._headers, "accept": "text/event-stream"},
            json=self._body(request, stream=True),
        ) as response:
            response.raise_for_status()
            async for delta in decode_deltas(response.aiter_lines()):
                yield delta


STREAM_DONE = "[DONE]"


async def decode_deltas(lines: AsyncIterator[str]) -> AsyncIterator[str]:
    """Pulls the assistant's text deltas out of an OpenAI-compatible `text/event-stream`: only
    `data:` lines are read (`: OPENROUTER PROCESSING` comments fall away), unparseable frames
    are skipped, and `[DONE]` ends the stream."""
    async for line in lines:
        if not line.startswith("data:"):
            continue
        payload = line[len("data:") :].strip()
        if payload == STREAM_DONE:
            return
        try:
            content = json.loads(payload)["choices"][0]["delta"].get("content")
        except (ValueError, KeyError, IndexError, TypeError):
            continue
        if content:
            yield content
