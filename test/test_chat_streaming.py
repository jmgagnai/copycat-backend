"""T16 step 3's `AnswerStream`, on the T05 `db` fixture: the events go through `pg_notify` on
the test's session, so publishing must leave the session usable."""

import uuid

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from chat.chat_dto import CitationResponse
from chat.streaming import AnswerStream


async def test_stream_publishes_and_keeps_the_session_usable(
    db: AsyncSession,
) -> None:
    notebook_id, thread_id = uuid.uuid4(), uuid.uuid4()
    stream = AnswerStream(db, notebook_id, thread_id)
    assert stream.identity["notebookId"] == str(notebook_id)
    assert stream.identity["threadId"] == str(thread_id)
    assert stream.topic == f"notebook:{notebook_id}"

    await stream.chunk("hi")
    await db.execute(text("SELECT 1"))
    await stream.chunk("second paragraph")
    assert stream.index == 2

    citation = CitationResponse(
        id=uuid.uuid4(),
        marker=1,
        document_id=uuid.uuid4(),
        document_version_id=uuid.uuid4(),
        version_number=1,
        chunk_id=uuid.uuid4(),
        filename="report.md",
        heading_path=["Report"],
        char_start=0,
        char_end=10,
    )
    await stream.completed(uuid.uuid4(), uuid.uuid4(), [citation])
    await stream.failed("boom")
    assert (await db.execute(text("SELECT 1"))).scalar_one() == 1


async def test_two_streams_have_distinct_ids(db: AsyncSession) -> None:
    notebook_id, thread_id = uuid.uuid4(), uuid.uuid4()
    first, second = (AnswerStream(db, notebook_id, thread_id) for _ in range(2))
    assert first.identity["streamId"] != second.identity["streamId"]
