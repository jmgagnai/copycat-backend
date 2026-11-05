from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import APIRouter, Query, Request
from fastapi.responses import StreamingResponse

from auth.guard import CurrentUser

from .events_bus import AppEventSubscriber
from .events_dto import AppEvent

router = APIRouter(tags=["events"])

KEEPALIVE_INTERVAL_S = 25


def to_sse_frame(event: AppEvent) -> str:
    return f"id: {event.id}\ndata: {event.model_dump_json(by_alias=True)}\n\n"


def get_app_events(request: Request) -> AppEventSubscriber | None:
    return getattr(request.app.state, "app_events", None)


@router.get(
    "/events",
    summary="Subscribe to live app events over server-sent events. Generic: every event type "
    "(ingestion progress, and later chat streaming) arrives on this one stream.",
    response_class=StreamingResponse,
    responses={
        200: {
            "description": "An endless stream of App Events, one `id:`/`data:` block each, deliberately "
            "with no `event:` name: `data` is the JSON envelope and its `type` field says what "
            "happened, so an EventSource reads every event on its default `message` listener.",
            "content": {"text/event-stream": {"schema": {"type": "string"}}},
        }
    },
)
async def stream_events(
    *,
    request: Request,
    _: CurrentUser,
    topic: Annotated[list[str] | None, Query()] = None,
) -> StreamingResponse:
    app_events = get_app_events(request)
    topics = set(topic) if topic else None
    queue: asyncio.Queue[AppEvent] = asyncio.Queue()

    async def frames() -> AsyncIterator[str]:
        yield ": connected\n\n"
        unsubscribe = (
            app_events.subscribe(queue.put_nowait) if app_events else (lambda: None)
        )
        try:
            while True:
                try:
                    event = await asyncio.wait_for(
                        queue.get(), timeout=KEEPALIVE_INTERVAL_S
                    )
                except TimeoutError:
                    yield ": keepalive\n\n"
                    continue
                if topics is None or event.topic in topics:
                    yield to_sse_frame(event)
        finally:
            unsubscribe()

    return StreamingResponse(
        frames(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache, no-transform", "X-Accel-Buffering": "no"},
    )
