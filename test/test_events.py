import uuid
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from event.events_bus import publish_app_event
from event.events_dto import AppEvent, AppEventDraft, notebook_topic
from event.events_router import to_sse_frame


def test_sse_frame_has_an_id_and_unnamed_data() -> None:
    event = AppEvent(
        id=uuid.uuid4(), type="x", topic="t", occurredAt=datetime.now(UTC), data={}
    )
    frame = to_sse_frame(event)
    assert frame.startswith("id: ") and "event:" not in frame and frame.endswith("\n\n")
    assert '"occurredAt"' in frame and "occurred_at" not in frame


async def test_publish_stamps_the_event(db: AsyncSession) -> None:
    notebook_id = uuid.uuid4()
    draft = AppEventDraft(
        type="document.ingestion.progress",
        topic=notebook_topic(notebook_id),
        data={"stage": "metadata"},
    )

    event = await publish_app_event(db, draft)

    assert isinstance(event, AppEvent)
    assert isinstance(event.id, uuid.UUID)
    offset = event.occurred_at.utcoffset()
    assert offset is not None and offset.total_seconds() == 0
    assert event.type == draft.type
    assert event.topic == f"notebook:{notebook_id}"
    assert event.data == {"stage": "metadata"}
    assert (await publish_app_event(db, draft)).id != event.id
