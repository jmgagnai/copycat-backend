# T09 — Background job queue (procrastinate)

| Mode | Effort | Priority | Depends on | Unblocks | Learning value |
| --- | --- | --- | --- | --- | --- |
| Write | 1 day | P1 | T01, T08 | T10, T12, T13 | High |

## Learning value

A real job queue on Postgres: procrastinate's app, per-queue retry strategies, running a worker as an asyncio task inside the web process, injecting dependencies into tasks. Reusable far beyond this project.

## Why

Ingestion runs in the background, one queue per Stage, each Stage enqueueing the next on success
(ADR-0004). `procrastinate` and `psycopg` are already in `pyproject.toml` for this; nothing uses them.

## What you need to know

### 1. Why a job table in Postgres

An HTTP request must answer in milliseconds; converting a PDF takes seconds to minutes.\
So the upload route only writes a Version row with status `queued` and hands the work to a queue.\
The queue lives in Postgres, in a table called `procrastinate_jobs`.\
That means no extra broker, and a job and the row it works on can be committed together.\
A *worker* polls the table, locks a job, runs it, and marks it `succeeded` or `failed`.

### 2. procrastinate's four ideas

- **The app.** `procrastinate.App(connector=...)` is the object everything hangs off: it knows the database and the tasks.
- **A task.** A coroutine decorated with `@job_app.task(queue="...")`.
  Its parameters are the job's arguments. They must be JSON serializable, so ids travel as `str`.
- **Deferring.** `await task.defer_async(**kwargs)` inserts one row in `procrastinate_jobs` with status `todo`.
  Nothing runs yet.
- **The worker.** `await job_app.run_worker_async(queues=[...])` polls the table and runs the tasks.
  It is a coroutine that never returns, unless started with `wait=False`, which makes it stop when the queue is empty.

```python
import asyncio, procrastinate
from procrastinate import PsycopgConnector, RetryStrategy

job_app = procrastinate.App(
    connector=PsycopgConnector(conninfo="postgresql://user:pass@localhost:5432/db")
)
done = []


@job_app.task(
    queue="convert", retry=RetryStrategy(max_attempts=4, wait=10, exponential_wait=2)
)
async def convert(document_id: str, version_id: str) -> None:
    done.append((document_id, version_id))


async def main():
    await job_app.open_async()  # connect; the tables must already exist (section 3)
    await convert.defer_async(document_id="d1", version_id="v1")
    await job_app.run_worker_async(
        queues=["convert"], concurrency=1, install_signal_handlers=False, wait=False
    )
    print(done)  # [('d1', 'v1')]
    await job_app.close_async()


asyncio.run(main())
```

`install_signal_handlers=False` leaves Ctrl-C to whoever owns the process (uvicorn, later).\
`concurrency=1` runs one job at a time, which is right for a converter that already uses every core.

### 3. procrastinate's own tables, applied once by hand

procrastinate keeps its jobs in four tables of its own: `procrastinate_jobs`, `procrastinate_events`, `procrastinate_periodic_defers`, `procrastinate_workers`.\
The Node migrations do not create them, and this backend never applies a schema from Python.\
Apply them once per database with procrastinate's CLI:

```sh
cd src && PYTHONPATH=. uv run procrastinate --app jobs.app.job_app schema --apply
```

- `--app jobs.app.job_app` is a dotted path, which is why `src` must be on `PYTHONPATH` and why the app lives in a module that imports nothing heavy (step 1).
- The DSN comes from `settings`, so the command targets whatever `DATABASE_URL` says: the dev `rag_notebook` database by default.
- Running it a second time on the same database prints `Database error.` and changes nothing. That is the expected refusal.
- `schema --read` prints the SQL instead of applying it.
- The reference backend applies this schema at startup (`schema_manager.apply_schema_async()`). Do not copy that part.

### 4. Retries

`RetryStrategy(max_attempts=4, wait=10, exponential_wait=2)` means one attempt plus three retries, 10 s, then 20 s, then 40 s apart.\
A task that raises is rescheduled; after the last attempt the job is marked `failed` in the jobs table.\
The Stage code (T10) also records the failure on the Version row on every attempt, so the user sees `failed` at once and a later success overwrites it.

### 5. The worker as a background task of the web process

One process both serves HTTP and works jobs.\
`run_worker_async` never returns, so the lifespan wraps it in `asyncio.create_task` and cancels it at shutdown.

```python
worker = asyncio.create_task(
    job_app.run_worker_async(
        queues=["convert"], concurrency=1, install_signal_handlers=False
    )
)
...
worker.cancel()
try:
    await worker
except asyncio.CancelledError:
    pass
await job_app.close_async()
```

### 6. Giving tasks their dependencies

procrastinate calls a task with its job arguments and nothing else.\
Everything else a task needs (storage, the converter, the LLM client) is set once at startup in a module-level `WorkerDeps` dataclass.\
Each task opens its own database session: the request that enqueued the job is long gone.

```python
@dataclass
class WorkerDeps:
    storage: S3Storage
    convert_to_markdown: MarkdownConverter
    complete: ChatCompleter | None = None  # None without an OpenRouter key (T12)
    embed: Embedder | None = None  # same (T13)


_deps: WorkerDeps | None = None  # set by JobQueue.__init__


@job_app.task(queue=CONVERT_TO_MARKDOWN_QUEUE, retry=RETRY)
async def convert_to_markdown(document_id: str, version_id: str) -> None:
    assert _deps is not None
    async with AsyncSessionLocal() as db:
        await run_convert_to_markdown_job(
            ConvertToMarkdownDeps(db, _deps.storage, _deps.convert_to_markdown, ...),
            ref,
        )
```

### 7. Enqueue after the commit; fakes in tests

- Defer only after the Version row is committed. Otherwise the worker may pick the job up before the row exists.
- A failed defer is logged, not raised: the row already records that work is owed. T08's `enqueue_conversion` does this.
- In tests nothing touches `procrastinate_jobs`. The routes read the queue from `app.state.jobs`, and the T05 `client` fixture puts a `FakeJobs` there that only records calls:

```python
@dataclass
class FakeJobs:
    enqueued: list[tuple[uuid.UUID, uuid.UUID]] = field(default_factory=list)

    async def enqueue_convert_to_markdown(
        self, document_id: uuid.UUID, version_id: uuid.UUID
    ) -> None:
        self.enqueued.append((document_id, version_id))
```

## What to build

**Files.** A new package `src/jobs/` with two modules, `app.py` and `tasks.py`, and a new module `src/ingestion/stage.py` holding what the tasks and the Stages share.\
`JobQueue` goes in `tasks.py` as well.\
Every step is checked against the dev `rag_notebook` database; the suite never touches the queue.

---

### Step 0. Apply the schema to the dev database, once

Run the command of section 3 after step 1 exists (it needs `jobs.app`):

```sh
cd src && PYTHONPATH=. uv run procrastinate --app jobs.app.job_app schema --apply
```

**DONE WHEN**

```sql
-- psql, dev database
\dt procrastinate*
```

lists the four tables, and running the command again prints `Database error.`


![img_58.png](screenshots/img_58.png)

---

### Step 1. The app in one module, the tasks in another

**Why two modules.** The CLI of section 3 imports the app by dotted path.\
If the app module imported the Stages, the CLI would pull in Docling and the LLM clients just to print SQL.\
So `app.py` stays tiny, and procrastinate loads `tasks.py` itself through `import_paths` when the worker starts.

**`src/jobs/app.py`**, the whole file:

```python
import procrastinate
from procrastinate import PsycopgConnector

from settings import settings

# The plain postgresql:// DSN: procrastinate speaks psycopg, not asyncpg.
job_app = procrastinate.App(
    connector=PsycopgConnector(conninfo=settings.postgres_dsn),
    import_paths=["jobs.tasks"],
)
```

**`src/ingestion/stage.py`**, created now with only what T09 needs; T10 adds to it:

```python
import uuid
from dataclasses import dataclass

CONVERT_TO_MARKDOWN_QUEUE = "convert_to_markdown"
SUMMARIZE_DOCUMENT_QUEUE = "summarize_document"
EMBED_CHUNKS_QUEUE = "embed_chunks"


@dataclass(frozen=True)
class DocumentVersionRef:
    """Which Version a job works on: the only thing a job argument carries."""

    document_id: uuid.UUID
    version_id: uuid.UUID
```

Add an empty `src/ingestion/__init__.py` next to it.

**`src/jobs/tasks.py`**, first part: the retry policy and three tasks, one queue each.

```python
RETRY = RetryStrategy(max_attempts=4, wait=10, exponential_wait=2)


def _ref(document_id: str, version_id: str) -> DocumentVersionRef:
    return DocumentVersionRef(
        document_id=uuid.UUID(document_id), version_id=uuid.UUID(version_id)
    )


@job_app.task(queue=CONVERT_TO_MARKDOWN_QUEUE, retry=RETRY)
async def convert_to_markdown(document_id: str, version_id: str) -> None:
    # T10 replaces the body with: open AsyncSessionLocal(), build ConvertToMarkdownDeps, run the Stage.
    log.info("convert_to_markdown: %s", _ref(document_id, version_id))


@job_app.task(queue=SUMMARIZE_DOCUMENT_QUEUE, retry=RETRY)
async def summarize_document(document_id: str, version_id: str) -> None:
    log.info("summarize_document: %s", _ref(document_id, version_id))  # T12


@job_app.task(queue=EMBED_CHUNKS_QUEUE, retry=RETRY)
async def embed_chunks(document_id: str, version_id: str) -> None:
    log.info("embed_chunks: %s", _ref(document_id, version_id))  # T13
```

- The parameters are `str` because job arguments are stored as JSON; `_ref` turns them back into UUIDs.
- The bodies only log for now, so the wiring can be tested end to end before any Stage exists.
- `log = logging.getLogger(__name__)`, as everywhere else.

**DONE WHEN**

```sh
cd src && PYTHONPATH=. uv run procrastinate --app jobs.app.job_app schema --read | grep -c "CREATE TABLE"
cd src && uv run python -c "from jobs.app import job_app; job_app.perform_import_paths(); print(list(job_app.tasks))"
```

The first prints `4`.\
The second prints procrastinate's built-in `remove_old_jobs` (listed twice, under `builtin:` and its module path) followed by `jobs.tasks.convert_to_markdown`, `jobs.tasks.summarize_document` and `jobs.tasks.embed_chunks`.

![img_59.png](screenshots/img_59.png)

---

### Step 2. The enqueue functions

**Add to `tasks.py`.** One async function per task, taking a `DocumentVersionRef` and deferring with string ids:

```python
async def enqueue_convert_to_markdown(ref: DocumentVersionRef) -> None:
    await convert_to_markdown.defer_async(
        document_id=str(ref.document_id), version_id=str(ref.version_id)
    )


async def enqueue_summarize_document(ref: DocumentVersionRef) -> None:
    await summarize_document.defer_async(
        document_id=str(ref.document_id), version_id=str(ref.version_id)
    )


async def enqueue_embed_chunks(ref: DocumentVersionRef) -> None:
    await embed_chunks.defer_async(
        document_id=str(ref.document_id), version_id=str(ref.version_id)
    )
```

**Who calls them.**

- The upload route, through `JobQueue` (step 3), calls the first.
- Stage 1 (T10) calls the second when a conversion succeeds; Stage 2 (T12) calls the third.
- The Stages receive them as dependencies instead of importing them.
  That is what lets a Stage test pass a list-appending fake and never touch the queue.

**DONE WHEN:** from `src/`, this leaves one `todo` row in `procrastinate_jobs` on the dev database.\
Nothing works it, because no worker runs:

```sh
cd src && uv run python -c "
import asyncio, uuid
from jobs.app import job_app
from jobs.tasks import enqueue_convert_to_markdown
from ingestion.stage import DocumentVersionRef
async def main():
    await job_app.open_async()
    await enqueue_convert_to_markdown(DocumentVersionRef(uuid.uuid4(), uuid.uuid4()))
    await job_app.close_async()
asyncio.run(main())
"
```

_I ran this command two times_


```sql
SELECT id, status, queue_name, args FROM procrastinate_jobs ORDER BY id DESC LIMIT 1;
-- status todo, queue_name convert_to_markdown, args {"document_id": "...", "version_id": "..."}
```

![img_60.png](screenshots/img_60.png)

---

### Step 3. `JobQueue`: the worker's lifecycle and the producer side

**Add to `tasks.py`.** The `WorkerDeps` dataclass, the module global `_deps = None`, and the class.\
`WorkerDeps` has four fields; the last two stay `None` until T12 and T13 and decide which queues the worker takes:

```python
@dataclass
class WorkerDeps:
    storage: S3Storage
    convert_to_markdown: object  # T10 gives this the MarkdownConverter type
    complete: object | None = (
        None  # T12: the chat-completion client, needs an OpenRouter key
    )
    embed: object | None = None  # T13: the embedder, needs an OpenRouter key
```

Then the class:

```python
class JobQueue:
    """The producer side the routes see, plus the worker's lifecycle."""

    def __init__(self, worker: WorkerDeps | None = None) -> None:
        global _deps
        _deps = worker
        self._worker: asyncio.Task[None] | None = None
        self._queues = [CONVERT_TO_MARKDOWN_QUEUE]
        if worker and worker.complete:
            self._queues.append(SUMMARIZE_DOCUMENT_QUEUE)
        if worker and worker.embed:
            self._queues.append(EMBED_CHUNKS_QUEUE)

    async def start(self, work: bool = True) -> None:
        await job_app.open_async()
        if work and _deps is not None:
            self._worker = asyncio.create_task(
                job_app.run_worker_async(
                    queues=self._queues, concurrency=1, install_signal_handlers=False
                )
            )
        log.info("Job worker started on queues %s", self._queues)

    async def stop(self) -> None:
        if self._worker:
            self._worker.cancel()
            try:
                await self._worker
            except asyncio.CancelledError:
                pass
        await job_app.close_async()

    async def enqueue_convert_to_markdown(
        self, document_id: uuid.UUID, version_id: uuid.UUID
    ) -> None:
        await enqueue_convert_to_markdown(
            DocumentVersionRef(document_id=document_id, version_id=version_id)
        )
```

- **Queues to work.** Always `convert_to_markdown`. `summarize_document` only when `deps.complete` is set, `embed_chunks` only when `deps.embed` is set: without an OpenRouter key those Stages cannot run, so their jobs stay `todo` instead of failing four times.
- **`start()` never applies or checks the schema.** That was step 0. If the tables are missing, `open_async` succeeds but the first defer fails with `relation "procrastinate_jobs" does not exist`, which is the hint to run step 0.
- **`work=False`** opens the app for deferring without running a worker; useful in scripts.
- **`stop()`** is section 5. Cancelling the worker task is the normal way to end it.

**DONE WHEN:** from `src/`, this script logs the two worker lines and exits without a traceback:

```sh
cd src && uv run python -c "
import asyncio, logging, uuid
logging.basicConfig(level='INFO', format='%(levelname)s %(name)s: %(message)s')
from jobs.tasks import JobQueue, WorkerDeps
async def main():
    q = JobQueue(WorkerDeps(storage=None, convert_to_markdown=None))
    await q.start()
    await q.enqueue_convert_to_markdown(uuid.uuid4(), uuid.uuid4())
    await asyncio.sleep(2)
    await q.stop()
asyncio.run(main())
"
```

Expected in the output:

```
INFO procrastinate.worker.worker: Starting job jobs.tasks.convert_to_markdown[3](version_id='...', document_id='...')
INFO jobs.tasks: convert_to_markdown: DocumentVersionRef(document_id=UUID('...'), version_id=UUID('...'))
INFO procrastinate.worker: Job jobs.tasks.convert_to_markdown[3](...) ended with status: Success, lasted 0.000 s
```

The worker also picks up the `todo` row left by step 2, so expect those three lines twice.

![img_61.png](screenshots/img_61.png)

---

### Step 4. The route side: already wired by T08

T08's `document_router.py` has `get_jobs(request)` returning `app.state.jobs`, an `enqueue_conversion` helper that skips when it is `None` and logs a failed defer, and a `ConversionJobs` protocol describing the one method it calls.\
`JobQueue` satisfies that protocol.\
Nothing to write. Keep the protocol: importing `jobs.tasks` from the router would close an import cycle
(`document` -> `jobs.tasks` -> `ingestion.stage` -> `document.document_dto` -> `document/__init__` -> the router) once T10 lands.

**DONE WHEN:** the T08 upload test still holds this assertion, with the `FakeJobs` of section 7 installed by the `client` fixture:

```python
assert app.state.jobs.enqueued == [
    (uuid.UUID(document["id"]), uuid.UUID(document["latestVersion"]["id"]))
]
```
![img_62.png](screenshots/img_62.png)

---

### Step 5. Lifespan

In `app/main.py`, after the storage is built and before the LISTEN subscriber:

```python
jobs = JobQueue(
    WorkerDeps(storage=storage, convert_to_markdown=None)
)  # T10 passes DoclingConverter()
await jobs.start()
app.state.jobs = jobs
```

and `await jobs.stop()` first thing in the `finally`, before `app_events.close()`.\
Also log one warning at boot when `OPENROUTER_API_KEY` is empty: Documents will stop at `converted` (Stages 2 and 3 need the key).

**DONE WHEN**

- `uv run main.py` logs `Job worker started on queues ['convert_to_markdown']`.
- Uploading a Document in Swagger logs `Starting job jobs.tasks.convert_to_markdown[...]` and `ended with status: Success`.
- Ctrl-C stops the server with no traceback.
- If the boot fails with `relation "procrastinate_jobs" does not exist`, step 0 was skipped.

![img_63.png](screenshots/img_63.png)

---

### Step 6. Tests

None for procrastinate itself.\
The `FakeJobs` assertion in T08's test and the manual check of step 5 are the coverage.\
The Stage tests of T10 to T13 call the job functions directly with fakes and never touch the queue.

**DONE WHEN:** the suite passes and adds no rows to `procrastinate_jobs`:

```sh
psql "$DATABASE_URL" -tAc "select count(*) from procrastinate_jobs"   # note the number
uv run pytest -q
psql "$DATABASE_URL" -tAc "select count(*) from procrastinate_jobs"   # unchanged
```

(`psql` wants the plain `postgresql://` form of the URL, without `+asyncpg`.)


![img_64.png](screenshots/img_64.png)

## Acceptance

- Uploading a Document while the server runs logs `Starting job jobs.tasks.convert_to_markdown[...]`
  and the row leaves `queued` (with T10).

## References

- Node: `apps/backend/src/jobs/queue.ts`; procrastinate docs: "Quickstart", `App`, `RetryStrategy`,
  `run_worker_async`, "Top-level app" discussion (why the app lives in its own module).
- Reference: `FakeJobs` in `test/conftest.py`.
