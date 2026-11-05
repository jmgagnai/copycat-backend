import asyncio
import json
from collections.abc import AsyncIterator, Awaitable, Callable
from dataclasses import dataclass
from typing import Any

import httpx

OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"


@dataclass(frozen=True)
class ChatCompletionRequest:
    model: str
    system: str
    user: str
    max_output_tokens: int | None = None
    temperature: float = 0.2


ChatCompleter = Callable[[ChatCompletionRequest], Awaitable[str]]
ChatStreamer = Callable[[ChatCompletionRequest], AsyncIterator[str]]


async def with_retries[T](
    attempt: Callable[[], Awaitable[T]], *, retries: int, retry_delay_s: float
) -> T:
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
        "http-referer": "https://github.com/rag-notebook",
        "x-title": "RAG Notebook",
    }


class OpenRouterClient:
    def __init__(
        self,
        api_key: str,
        *,
        base_url: str = OPENROUTER_BASE_URL,
        http: httpx.AsyncClient | None = None,
        retries: int = 2,
        retry_delay_s: float = 0.5,
        timeout_s: float = 120,
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
        if "error" in payload:
            raise RuntimeError(
                f"OpenRouter error for model {request.model}: {payload['error']}"
            )
        text = payload["choices"][0]["message"]["content"]
        if not text or not text.strip():
            raise RuntimeError(
                f"OpenRouter returned no content for model {request.model}."
            )
        return text

    async def complete(self, request: ChatCompletionRequest) -> str:
        return await with_retries(
            lambda: self._complete(request),
            retries=self._retries,
            retry_delay_s=self._retry_delay_s,
        )

    async def stream(self, request: ChatCompletionRequest) -> AsyncIterator[str]:
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
