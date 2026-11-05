import logging
from collections.abc import Awaitable, Callable
from functools import partial

import httpx

from .openrouter import OPENROUTER_BASE_URL, headers, with_retries

log = logging.getLogger(__name__)

Embedder = Callable[[list[str]], Awaitable[list[list[float]]]]

DEFAULT_BATCH_SIZE = 32


class OpenRouterEmbedder:
    def __init__(
        self,
        api_key: str,
        model: str,
        *,
        base_url: str = OPENROUTER_BASE_URL,
        http: httpx.AsyncClient | None = None,
        retries: int = 2,
        retry_delay_s: float = 0.5,
        timeout_s: float = 120,
        batch_size: int = DEFAULT_BATCH_SIZE,
    ):
        self._url = f"{base_url.rstrip('/')}/embeddings"
        self._headers = headers(api_key)
        self._model = model
        self._http = http or httpx.AsyncClient(timeout=timeout_s)
        self._retries = retries
        self._retry_delay_s = retry_delay_s
        self._batch_size = max(1, batch_size)

    async def _embed_batch(self, batch: list[str]) -> list[list[float]]:
        log.debug("Embedding %d texts with %s", len(batch), self._model)
        response = await self._http.post(
            self._url,
            headers=self._headers,
            json={"model": self._model, "input": batch},
        )
        response.raise_for_status()
        payload = response.json()
        if "error" in payload:
            raise RuntimeError(
                f"OpenRouter error for embedding model {self._model}: {payload['error']}"
            )
        return [entry["embedding"] for entry in payload["data"]]

    async def __call__(self, texts: list[str]) -> list[list[float]]:
        vectors: list[list[float]] = []
        for start in range(0, len(texts), self._batch_size):
            batch = texts[start : start + self._batch_size]
            vectors.extend(
                await with_retries(
                    partial(self._embed_batch, batch),
                    retries=self._retries,
                    retry_delay_s=self._retry_delay_s,
                )
            )
        return vectors
