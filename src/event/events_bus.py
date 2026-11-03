import json
import logging
import uuid
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

import asyncpg
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from event.events_dto import AppEvent, AppEventDraft

APP_EVENT_CHANNEL = "app_events"
AppEventListener = Callable[[AppEvent], None]


log = logging.getLogger(
    __name__
)  # records show as `event.events_bus`, filterable per module


async def publish_app_event(db: AsyncSession, draft: AppEventDraft) -> AppEvent:
    """Stamp the draft with an id and a timestamp and send it with pg_notify on the caller's
    session. No commit here: pg_notify is transactional, so the event leaves Postgres only when
    the caller commits, together with whatever change it announces."""
    event = AppEvent.model_validate(
        {"id": uuid.uuid4(), "occurredAt": datetime.now(UTC), **draft.model_dump()}
    )
    await db.execute(
        text("SELECT pg_notify(:channel, :payload)"),
        {"channel": APP_EVENT_CHANNEL, "payload": event.model_dump_json(by_alias=True)},
    )
    return event


class AppEventSubscriber:
    def __init__(self, dsn: str) -> None:
        self._dsn = dsn
        self._listeners: set[AppEventListener] = set()
        self._conn: asyncpg.Connection[Any] | None = None

    async def start(self) -> None:
        """Open the dedicated connection and ask Postgres to deliver `app_events` to it."""
        conn = await asyncpg.connect(self._dsn)
        await conn.add_listener(APP_EVENT_CHANNEL, self._on_notification)
        self._conn = conn
        log.info("Listening on %s", APP_EVENT_CHANNEL)

    def _on_notification(
        self, _conn: object, _pid: int, _channel: str, payload: object
    ) -> None:
        """Called by asyncpg on the event loop for every NOTIFY. Parse, then fan out."""
        event = AppEvent.model_validate(json.loads(str(payload)))
        for listener in list(
            self._listeners
        ):  # copy: a listener may unsubscribe during the loop
            listener(event)

    def subscribe(self, listener: AppEventListener) -> Callable[[], None]:
        """Register a plain function to be called with each event; returns the undo."""
        self._listeners.add(listener)
        return lambda: self._listeners.discard(listener)

    async def close(self) -> None:
        if self._conn is not None:
            await self._conn.close()
            log.info("Stopped listening on %s", APP_EVENT_CHANNEL)
