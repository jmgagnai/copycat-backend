# T06 — App events: NOTIFY bus and the SSE endpoint

| Mode | Effort | Priority | Depends on | Unblocks | Learning value |
| --- | --- | --- | --- | --- | --- |
| Write | 1 day | P1 | T01, T03 | T10 (status events), T16 (streamed answers) | High |

## Learning value

Postgres LISTEN/NOTIFY as a message bus, transactional `pg_notify`, server-sent events over a `StreamingResponse`, keepalives and client cleanup. The most transferable piece of the backend.

## Why

Ingestion progress and streamed chat answers reach the browser through one generic
`GET /events` stream fed by Postgres `LISTEN/NOTIFY` (ADR-0004). `event/events_router.py` is a
stub and `events_dto.py` is empty.

## What you need to know

### 1. Postgres LISTEN/NOTIFY

Postgres can push a short text message to every connection that is listening on a channel.
`pg_notify(channel, payload)` sends it, and it is transactional: a NOTIFY issued inside a
transaction is delivered only when that transaction commits. That is why a status change and its
event can be written in the same transaction and never disagree. Payloads are capped at 8000 bytes,
so events say what changed and never carry bulk data.

```sql
-- session A
LISTEN app_events;
-- session B
SELECT pg_notify('app_events', '{"type": "hello"}');
-- session A sees: Asynchronous notification "app_events" with payload "{"type": "hello"}"
```

Try it: open two `psql` sessions on the dev database and run the lines above.

### 2. Listening from Python with asyncpg

A pooled SQLAlchemy connection cannot be used for LISTEN, because LISTEN is tied to one
connection for as long as you want notifications. Open one dedicated `asyncpg` connection and
register a callback. The callback is a plain function, called on the event loop, and must not block.

```python
import asyncio, asyncpg, json


async def main():
    got: asyncio.Queue[str] = asyncio.Queue()
    listener = await asyncpg.connect(
        DSN
    )  # DSN = "postgresql://user:pass@localhost:5432/db"
    await listener.add_listener(
        "app_events", lambda conn, pid, channel, payload: got.put_nowait(payload)
    )
    publisher = await asyncpg.connect(DSN)
    async with publisher.transaction():
        await publisher.execute(
            "SELECT pg_notify('app_events', $1)", json.dumps({"type": "hello"})
        )
    print(await asyncio.wait_for(got.get(), 2))  # {"type": "hello"}
    await listener.close()
    await publisher.close()


asyncio.run(main())
```

Try it: `uv run python listen.py` against the test database prints the payload.

### 3. Publishing through the caller's SQLAlchemy session

From a repository or a job, publish on the session that is doing the work, so the event is part of
the same transaction. Bound parameters go through `text()`, never through f-strings.

```python
from sqlalchemy import text

await db.execute(
    text("SELECT pg_notify(:channel, :payload)"),
    {"channel": "app_events", "payload": event.model_dump_json(by_alias=True)},
)
await db.commit()  # the notification leaves Postgres here, not before
```

### 4. Fan-out with asyncio.Queue

One LISTEN connection serves every open SSE request in the process. Keep a set of listener
callables; each SSE request creates its own `asyncio.Queue` and subscribes `queue.put_nowait`.
Subscribing returns an unsubscribe function, which the request calls in a `finally`.

```python
class Subscriber:
    def __init__(self) -> None:
        self._listeners: set[Callable[[AppEvent], None]] = set()

    def subscribe(self, listener):
        self._listeners.add(listener)
        return lambda: self._listeners.discard(listener)

    def _on_notification(self, _conn, _pid, _channel, payload: str) -> None:
        event = AppEvent.model_validate(json.loads(payload))
        for listener in list(
            self._listeners
        ):  # copy: a listener may unsubscribe while iterating
            listener(event)
```

### 5. Server-sent events over a StreamingResponse

SSE is plain text over a long-lived HTTP response with `Content-Type: text/event-stream`. Each
frame is lines of `field: value` ended by a blank line. A line starting with `:` is a comment,
useful to flush headers on connect and as a keepalive. FastAPI streams an async generator with
`StreamingResponse`; `asyncio.wait_for` with a timeout turns "nothing happened for 25 s" into a
keepalive frame.

```python
import asyncio
from fastapi import FastAPI
from fastapi.responses import StreamingResponse

app = FastAPI()
queue: asyncio.Queue[str] = asyncio.Queue()


@app.get("/events")
async def events():
    async def frames():
        yield ": connected\n\n"
        while True:
            try:
                data = await asyncio.wait_for(queue.get(), timeout=25)
            except TimeoutError:
                yield ": keepalive\n\n"
                continue
            yield f"id: 1\ndata: {data}\n\n"

    return StreamingResponse(frames(), media_type="text/event-stream")
```

Try it: run it with uvicorn, then `curl -N http://localhost:8000/events` prints `: connected` and a
keepalive every 25 s. Note that `httpx`'s `ASGITransport` buffers the whole response, so an SSE
route cannot be tested end to end with the T05 client; test the frame function instead.

### 6. Cleanup when the client goes away

When the browser closes the EventSource, the generator is cancelled at its next `await` with
`asyncio.CancelledError`. Anything in a `finally` still runs, which is where the unsubscribe goes.
No polling of `request.is_disconnected()` is needed.

### 7. The frontend's expectations

The Angular client opens one `EventSource('/events?topic=notebook:<id>')` with cookies and listens
on the default `message` event. So frames carry no `event:` line, and the JSON `data` has `type`,
`topic`, `occurredAt`, `data`. Every JSON key is camelCase.

## What to build

1. **`event/events_dto.py`: the shape of one event.** Before any code that sends or receives
   events, decide what an event *is*. Everything in this task passes the same small JSON object
   around: a repository or a job publishes it through `pg_notify`, the subscriber parses it back
   from the NOTIFY payload, and the `/events` route writes it into an SSE frame for the browser.
   One pydantic model describes that object, so every stage agrees on its fields.

   An event answers three questions. `type` says *what happened*, for example
   `"document.ingestion.progress"`. `topic` says *who cares*: a browser page watching one Notebook
   subscribes to `"notebook:<uuid>"` and ignores everything else. `data` carries the
   type-specific details, such as a document id and a stage name. Two bookkeeping fields complete
   it: `id`, so the browser can tell frames apart, and `occurred_at`, when it happened.

   ```python
   class AppEvent(BaseModel):
       model_config = ConfigDict(extra="ignore", frozen=False, populate_by_name=True)
       id: uuid.UUID
       type: str = Field(min_length=1)
       topic: str = Field(min_length=1)
       occurred_at: datetime.datetime = Field(alias="occurredAt")
       data: dict[str, Any]
   ```

   The code that *raises* an event should not have to invent an id or read the clock; it only
   knows the three meaningful fields. A second, smaller model carries exactly those, and step 2's
   `publish_app_event` turns a draft into a full `AppEvent` by stamping `id` and `occurred_at`:

   ```python
   class AppEventDraft(BaseModel):
       type: str
       topic: str
       data: dict[str, Any]
   ```

   Finally, since every Notebook-scoped publisher and the frontend must spell the topic the same
   way, a one-line helper is the only place that format lives:

   ```python
   def notebook_topic(notebook_id: uuid.UUID | str) -> str:
       return f"notebook:{notebook_id}"
   ```

   **Why `alias` and not `serialization_alias` this time.** The JSON field is `occurredAt`, the
   Python attribute is `occurred_at`. In T04's `NotebookResponse` the model only ever went *out*
   (entity in, JSON out), so `serialization_alias` renamed the field on output only. `AppEvent`
   goes both ways: it is parsed *from* JSON when the subscriber receives a NOTIFY payload, and
   dumped *to* JSON when the route writes the SSE frame. A plain `alias` applies to both
   directions. `populate_by_name=True` additionally lets Python code construct it with
   `occurred_at=...`, so both spellings are accepted on input.

   `extra="ignore"` means a payload with an unknown key is accepted rather than rejected; a newer
   publisher can add a field without breaking an older subscriber.

   **DONE WHEN:** a camelCase JSON object parses into the model and dumps back out with
   `occurredAt`, which is what "round-trips" means. Run from `src/`:

   ```sh
   cd src && uv run python -c "
   import uuid
   from event.events_dto import AppEvent
   print(AppEvent.model_validate({'id': str(uuid.uuid4()), 'type': 'x', 'topic': 't', 'occurredAt': '2026-11-02T10:00:00Z', 'data': {}}).model_dump_json(by_alias=True))
   "
   ```

   The output must contain `"occurredAt":"2026-11-02T10:00:00Z"` and no `occurred_at`.

![img_28.png](screenshots/img_28.png)


2. **`event/events_bus.py`, the publisher.** `publish_app_event(db, draft) -> AppEvent` stamps
   `id=uuid.uuid4()` and `occurred_at=datetime.now(UTC)`, runs `SELECT pg_notify(:channel, :payload)`
   on the caller's session (section 3) and returns the stamped event. It does not commit; the
   caller does, so the event rides on the caller's transaction.

   **DONE WHEN:** a test calls it on the `db` fixture and asserts the returned event has a
   timezone-aware `occurred_at` and the draft's `type`. Then, with `psql` listening on the test
   database, a second call followed by a commit shows the payload in `psql`:

   ```sql
   -- in psql, on the test database
   LISTEN app_events;
   ```

   ```python
   # in the script, after the second publish
   await db.commit()
   ```

![img_29.png](screenshots/img_29.png)

![img_30.png](screenshots/img_30.png)

3. **`event/events_bus.py`, the subscriber: one LISTEN connection for the whole process.** Step 2
   sends events into Postgres. This step receives them back. The server process needs one place
   that holds a `LISTEN app_events` connection open for its whole life, turns each NOTIFY payload
   back into an `AppEvent`, and hands it to whoever asked: later, every open `/events` request.
   That place is a class, `AppEventSubscriber`, created once at startup (step 5) and shared by all
   requests through `app.state`.

   It cannot reuse the SQLAlchemy engine. `LISTEN` works per connection and the engine hands out
   pooled connections that change from one query to the next, so the subscriber opens its own
   `asyncpg` connection with the plain `postgresql://` DSN from `settings.postgres_dsn`
   (`DATABASE_URL` without the `+asyncpg` driver suffix, which only SQLAlchemy understands).

   The class has four members, in the order they are used:

   ```python
   APP_EVENT_CHANNEL = "app_events"
   AppEventListener = Callable[[AppEvent], None]


   class AppEventSubscriber:
       def __init__(self, dsn: str) -> None:
           self._dsn = dsn
           self._listeners: set[AppEventListener] = set()
           self._conn: asyncpg.Connection | None = None

       async def start(self) -> None:
           """Open the dedicated connection and ask Postgres to deliver `app_events` to it."""
           self._conn = await asyncpg.connect(self._dsn)
           await self._conn.add_listener(APP_EVENT_CHANNEL, self._on_notification)

       def _on_notification(
           self, _conn: object, _pid: int, _channel: str, payload: str
       ) -> None:
           """Called by asyncpg on the event loop for every NOTIFY. Parse, then fan out."""
           event = AppEvent.model_validate(json.loads(payload))
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
   ```

   - `start()` is `async` and separate from `__init__` because connecting needs `await`, and
     constructors cannot await. The lifespan calls it once.
   - `_on_notification` has the four-argument signature asyncpg requires for a listener callback.
     It runs on the event loop, so it must return quickly and never block; it only parses the JSON
     into an `AppEvent` (step 1) and calls each subscriber.
   - `subscribe()` is how a consumer registers interest. The "listener" is any function taking one
     `AppEvent`; the `/events` route (step 4) will pass `queue.put_nowait` so events land in a
     per-request queue. It returns a function that removes the listener again, which the route
     calls in a `finally` when the browser disconnects. Iterating over a *copy* of the set matters
     because that unsubscribe can happen while `_on_notification` is still looping.
   - `close()` is for shutdown, so Ctrl-C does not end with an asyncpg traceback.

   There is deliberately no reconnect loop: if the connection drops, the process restarts and the
   lifespan reconnects. Resilience here would be code nobody reads until it fails.

   **DONE WHEN:** a throwaway script starts the subscriber, subscribes `print`, and waits; an
   event published from `psql` is printed by the script as an `AppEvent`. Script, run from `src/`:

   ```sh
   cd src && uv run python -c "
   import asyncio
   from event.events_bus import AppEventSubscriber
   from settings import settings
   async def main():
       sub = AppEventSubscriber(settings.postgres_dsn)
       await sub.start()
       unsubscribe = sub.subscribe(print)
       print('listening; publish from psql now, Ctrl-C to stop')
       try:
           await asyncio.sleep(60)
       finally:
           unsubscribe(); await sub.close()
   asyncio.run(main())
   "
   ```

   Then, in `psql` on the dev database (any `<uuid>` will do, for example `uuidgen | tr A-F a-f`):

   ```sql
   SELECT pg_notify('app_events', '{"id": "<uuid>", "type": "x", "topic": "t", "occurredAt": "2026-11-02T10:00:00Z", "data": {}}');
   ```

   The script prints `id=UUID('...') type='x' topic='t' occurred_at=datetime.datetime(2026, 11, 2, 10, 0, tzinfo=TzInfo(0)) data={}`.

![img_31.png](screenshots/img_31.png)
![img_32.png](screenshots/img_32.png)

   A payload that is not valid JSON, or lacks a field, raises inside `_on_notification`; asyncpg
   logs it and keeps listening. Leave it that way for now.

4. **`event/events_router.py`: the `/events` stream.** This is where a browser connects, once,
   and then receives every event it cares about for as long as the tab stays open. The contract
   describes it as an endless `text/event-stream` of `id:`/`data:` blocks with no `event:` name.
   Step 3's subscriber already receives every event in the process; this route's only job is to
   take the events one browser wants and write them, in SSE format, into a response that never
   ends. Six small pieces do that.

   **a. The frame format, as a pure function.** One SSE frame is a few `field: value` lines and a
   blank line. Keep its construction in a function with no I/O, so the unit test can check the
   bytes without a server:

   ```python
   def to_sse_frame(event: AppEvent) -> str:
       # No `event:` line on purpose: an EventSource delivers unnamed frames to its single
       # `message` listener, and the Angular client dispatches on the `type` inside the JSON.
       return f"id: {event.id}\ndata: {event.model_dump_json(by_alias=True)}\n\n"
   ```

   `id:` lets the browser remember the last event it saw (it sends it back as
   `Last-Event-ID` on reconnect; nothing uses that yet). `data:` is the event JSON, camelCase
   through `by_alias=True`. The two `\n` at the end are the frame terminator; a frame without them
   is never delivered.

   **b. The query parameter.** `GET /events?topic=notebook:<id>` follows one Notebook;
   `?topic=a&topic=b` several; no `topic` at all follows everything (ADR-0001: any authenticated
   user may see every Notebook). FastAPI collects a repeated query parameter into a list when the
   parameter is declared as one:

   ```python
   topic: Annotated[list[str] | None, Query()] = None
   topics = set(topic) if topic else None  # None means "no filter"
   ```

   **c. Reaching the subscriber from a route.** The subscriber is created by the lifespan (step 5)
   and stored on `app.state.app_events`; a route reads it through `request.app.state`. Go through a
   tiny function rather than the attribute directly, so that in tests, where the T05 `client`
   fixture sets `app.state.app_events = None`, the route still answers instead of failing on a
   missing attribute:

   ```python
   def get_app_events(request: Request) -> AppEventSubscriber | None:
       return getattr(request.app.state, "app_events", None)
   ```

   **d. One queue per request, fed by the subscriber.** The subscriber calls listeners
   synchronously, from inside asyncpg's callback. A route cannot write to its response from
   there; it needs to `await` for the next event in its own generator. An `asyncio.Queue` bridges
   the two: `queue.put_nowait` is a plain function, so it can be the listener, and the generator
   `await`s `queue.get()`. Every request owns its own queue, which is how one LISTEN connection
   serves many browsers.

   ```python
   queue: asyncio.Queue[AppEvent] = asyncio.Queue()
   unsubscribe = app_events.subscribe(queue.put_nowait) if app_events else (lambda: None)
   ```

   **e. The generator.** The body of the response is an `async` generator that `yield`s strings.
   FastAPI's `StreamingResponse` sends each one as soon as it is produced. Three kinds of string:

   ```python
   KEEPALIVE_INTERVAL_S = 25


   async def frames() -> AsyncIterator[str]:
       yield ": connected\n\n"  # 1. a comment: flushes the headers at once
       try:
           while True:
               try:
                   event = await asyncio.wait_for(
                       queue.get(), timeout=KEEPALIVE_INTERVAL_S
                   )
               except TimeoutError:
                   yield ": keepalive\n\n"  # 2. a comment: nothing happened for 25 s
                   continue
               if topics is None or event.topic in topics:
                   yield to_sse_frame(event)  # 3. a real frame
       finally:
           unsubscribe()  # the browser went away (see section 6)
   ```

   A line starting with `:` is an SSE comment: the browser ignores it, but it is bytes on the
   wire. The first one makes the response headers leave the server immediately, so the
   `EventSource` fires `open` instead of waiting for the first real event. The periodic one keeps
   proxies and load balancers from closing an idle connection; `asyncio.wait_for` turns "no event
   for 25 s" into that comment, then the loop goes back to waiting. The filter is applied here, in
   the route, because the subscriber does not know what each request asked for.

   When the browser closes the `EventSource`, the server cancels this generator at its current
   `await`. The `finally` still runs, and `unsubscribe()` removes the queue from the subscriber,
   otherwise every closed tab would leave a queue filling up forever.

   **f. The response and its headers.** `media_type="text/event-stream"` is what makes the
   browser treat the body as SSE. The two extra headers tell caches and nginx-style proxies not to
   buffer the body, which would otherwise hold frames back until some size is reached:

   ```python
   return StreamingResponse(
       frames(),
       media_type="text/event-stream",
       headers={"Cache-Control": "no-cache, no-transform", "X-Accel-Buffering": "no"},
   )
   ```

   The route itself is `@router.get("/events", response_class=StreamingResponse)` behind
   `_: CurrentUser`, with `request: Request` as a parameter so step c can read `app.state`.
   Replace the stub's `topic: str | list[str] | None` with the `Annotated[...]` form of step b.

   **DONE WHEN:** two checks. First, a unit test on the pure function:

   ```python
   def test_sse_frame_has_an_id_and_unnamed_data() -> None:
       event = AppEvent(
           id=uuid.uuid4(), type="x", topic="t", occurred_at=datetime.now(UTC), data={}
       )
       frame = to_sse_frame(event)
       assert frame.startswith("id: ") and "event:" not in frame and frame.endswith("\n\n")
       assert '"occurredAt"' in frame and "occurred_at" not in frame
   ```
![img_33.png](screenshots/img_33.png)

   Second, against the running server (after step 5 wires the subscriber in), log in once to get a
   cookie file, then open the stream with `-N` so curl does not buffer:

   ```sh
   curl -c cookies.txt -X POST localhost:3000/auth/login -H 'content-type: application/json' -d '{"email":"ada@example.com","password":"correct horse"}'
   curl -N -b cookies.txt http://localhost:3000/events
   ```

   It prints `: connected` at once and `: keepalive` every 25 s. Without `-b cookies.txt` it
   answers 401. `httpx`'s `ASGITransport` buffers whole responses, so there is no automated test
   of the stream itself; the frame function and the curl above are the coverage.

![img_34.png](screenshots/img_34.png)

5. **Lifespan.** In `app/main.py`, in the lifespan: `app_events = AppEventSubscriber(settings.postgres_dsn)`,
   `await app_events.start()`, `app.state.app_events = app_events`; in the `finally` of the
   lifespan, `await app_events.close()`.

   Log one line in `start()` (`log.info("Listening on app_events")`) so the boot sequence is visible.

   **DONE WHEN:** the server log shows that line at boot, and the `curl -N` of step 4 prints a
   frame when you run this in `psql` on the dev database. Stopping the server with Ctrl-C closes
   the connection without a traceback:

   ```sql
   SELECT pg_notify('app_events', '{"id": "<uuid>", "type": "x", "topic": "t", "occurredAt": "2026-11-02T10:00:00Z", "data": {}}');
   ```
![img_35.png](screenshots/img_35.png)
![img_37.png](screenshots/img_37.png)
![img_38.png](screenshots/img_38.png)

6. **Tests.** Two, no more: `test_sse_frame_has_an_id_and_unnamed_data` (pure) and
   `test_publish_stamps_the_event` (uses the `db` fixture). The listener and the route are checked
   by hand with `curl` and `psql` as in the Acceptance section.

   **DONE WHEN:** the events tests pass in under a second:

   ```sh
   uv run pytest test/test_events.py -q
   ```
![img_39.png](screenshots/img_39.png)


## Acceptance

- With the server running, `curl -N -b cookies 'http://localhost:3000/events'` prints
  `: connected` and then a frame when `SELECT pg_notify('app_events', '{...}')` is run in psql.

## References

- Node: `apps/backend/src/events/{bus,routes,schema}.ts`; NOTEBOOKS `docs/adr/0004-*.md`.
- Postgres docs: `NOTIFY`, `pg_notify`. asyncpg docs: `Connection.add_listener`.
- MDN: "Using server-sent events" for the frame format.
