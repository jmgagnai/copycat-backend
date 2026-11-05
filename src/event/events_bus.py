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


logger = logging.getLogger(__name__)


async def publish_app_event(db: AsyncSession, draft: AppEventDraft) -> AppEvent:
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
        conn = await asyncpg.connect(self._dsn)
        await conn.add_listener(APP_EVENT_CHANNEL, self._on_notification)
        self._conn = conn
        logger.info("Listening on %s", APP_EVENT_CHANNEL)

    def _on_notification(
        self, _conn: object, _pid: int, _channel: str, payload: object
    ) -> None:
        event = AppEvent.model_validate(json.loads(str(payload)))
        for listener in list(self._listeners):
            listener(event)

    def subscribe(self, listener: AppEventListener) -> Callable[[], None]:
        self._listeners.add(listener)
        return lambda: self._listeners.discard(listener)

    async def close(self) -> None:
        if self._conn is not None:
            await self._conn.close()
            logger.info("Stopped listening on %s", APP_EVENT_CHANNEL)
