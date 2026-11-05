# T05 — Test harness

| Mode | Effort | Priority | Depends on | Unblocks | Learning value |
| --- | --- | --- | --- | --- | --- |
| Write | 0.5 day | P1 | T01 | tests of every later task | Medium |

## Learning value

Async fixtures on a session-scoped loop, dependency overrides and a throwaway database: worth learning once, reused by every later task.

## Why

`test/` holds only an `__init__.py`.\
Without a harness every task's acceptance check is manual.\
The Node suite runs on Testcontainers.\
Here the tests run against the dev `rag_notebook` database itself: each test is wrapped in one transaction that is rolled back at the end, so no second database is needed and the dev data is never modified.

## What you need to know

The harness is one file, `test/conftest.py`.\
pytest loads it automatically before any test in `test/`.\
Everything below ends up in that file; the numbered parts explain the ideas in the order the file needs them.\
Three words first, because the rest leans on them:

- **A fixture** is a function pytest runs for you to prepare something a test needs.\
  A test asks for it by naming it as a parameter: `async def test_x(client)` receives whatever the fixture called `client` produced.\
  Fixtures can ask for other fixtures the same way, so `client` can be built on top of `db`, which is built on top of `engine`.
- **Teardown** is the clean-up that runs after the test.\
  In a fixture it is simply the code after `yield`: everything before `yield` is setup, the value yielded is what the test receives, and everything after `yield` runs once the test is over.
- **Scope** is how often a fixture runs.\
  The default, *function* scope, runs it before every test.\
  *Session* scope runs it once for the whole `pytest` command and shares the result.

### 1. Running `async def` tests: pytest-asyncio and the event loop

The application is asynchronous, so the tests are `async def` functions too.\
Plain pytest does not know how to run those; the `pytest-asyncio` plugin does.\
Two settings in `pyproject.toml` configure it, and two more decide which event loop is used.

```toml
[tool.pytest.ini_options]
pythonpath = ["src"]                              # so tests can `import app.main`, `import db`
testpaths = ["test"]                              # `uv run pytest` looks here
asyncio_mode = "auto"                             # every `async def test_*` is a test, no marker needed
asyncio_default_fixture_loop_scope = "session"    # one event loop for all fixtures...
asyncio_default_test_loop_scope = "session"       # ...and all tests
```

An *event loop* is the scheduler that runs `async` code.\
By default pytest-asyncio would create a fresh loop for every test.\
That breaks here, because an asyncpg connection is tied to the loop it was opened on and cannot be used from another one.\
The SQLAlchemy engine keeps a pool of such connections for the whole run, so every fixture and every test must run on the same loop.\
The two `loop_scope = "session"` lines do exactly that.\
If you ever see `RuntimeError: ... attached to a different loop`, one of them is missing.

### 2. The database fixtures: a connection shared by the whole run, a transaction per test

Two fixtures, two scopes.

**`engine`, session scope.** Runs once.\
It first opens a bare asyncpg connection with a 3 second timeout, purely to find out whether Postgres is reachable.\
If that fails, `pytest.skip(...)` inside the fixture marks every test that depends on it as *skipped* (shown as `s`, not `F`), so running the suite with Postgres down is a clean "nothing to see" rather than a wall of errors.\
Then it builds the SQLAlchemy engine, hands it to the tests, and after the last test disposes it, which closes the pooled connections.

```python
@pytest_asyncio.fixture(
    scope="session"
)  # pytest_asyncio.fixture, because the function is async
async def engine() -> AsyncIterator[AsyncEngine]:
    try:
        conn = await asyncpg.connect(TEST_DSN, timeout=3)
        await conn.close()
    except Exception as err:
        pytest.skip(f"No database at {TEST_DSN}: {err}")
    engine = create_async_engine(TEST_DATABASE_URL)
    yield engine  # <- tests run here
    await engine.dispose()  # teardown, after the whole run
```

**`db`, function scope.** Runs before every test.\
This is where the "tests never change the dev database" guarantee lives, so it is worth reading slowly.

```python
@pytest_asyncio.fixture
async def db(engine: AsyncEngine) -> AsyncIterator[AsyncSession]:
    async with engine.connect() as conn:  # one connection for this test
        await conn.begin()  # BEGIN: open a transaction on it
        session = AsyncSession(
            bind=conn, join_transaction_mode="create_savepoint", expire_on_commit=False
        )
        try:
            yield session  # <- the test runs here
        finally:
            await session.close()
            await conn.rollback()  # ROLLBACK: everything the test did disappears
```

A *transaction* is a group of SQL statements that Postgres applies all together with `COMMIT`, or throws away all together with `ROLLBACK`.\
The fixture opens one before the test and always rolls it back after, so every INSERT and UPDATE the test caused is undone, and nothing is ever written to the dev data.\
Two tests can both register `ada@example.com`; neither sees the other's row.

There is a catch: the application code calls `session.commit()` itself, for example in `create_notebook`.\
A real `COMMIT` would end our transaction and make the rows permanent.\
The option `join_transaction_mode="create_savepoint"` prevents that.\
A *savepoint* is a bookmark inside a transaction (`SAVEPOINT` / `RELEASE SAVEPOINT` in SQL).\
With this mode, the session runs its work inside savepoints, and each `commit()` from the application only releases the current savepoint.\
The outer transaction opened by the fixture stays open until the fixture's `rollback()`, which discards the lot.

`expire_on_commit=False` is a smaller point: by default SQLAlchemy forgets the attribute values of every loaded object at each commit and reloads them on next access.\
In async code that reload is an `await` you did not write, which raises an error.\
Turning it off keeps `notebook.title` readable after the commit.\
The application's own session factory in `db/postgresql.py` uses the same flag for the same reason.

Because the fixture rolls back, nothing in the harness may `TRUNCATE` or `DELETE` for clean-up.\
There is no clean-up to do, and the tables are the real ones.

### 3. Calling the app without starting a server

The routes are tested by sending HTTP requests to them.\
Starting uvicorn in a test would be slow and fragile, so the requests are sent to the FastAPI application object directly, in the same process.\
`httpx` can do that: `ASGITransport(app=app)` tells the client to hand each request to the app object instead of opening a network socket.\
`base_url="http://test"` is a placeholder hostname the client needs; nothing listens there.

```python
from httpx import ASGITransport, AsyncClient

async with AsyncClient(
    transport=ASGITransport(app=app), base_url="http://test"
) as http:
    response = await http.post(
        "/auth/register", json={"email": "ada@example.com", "password": "correct horse"}
    )
    assert response.status_code == 201
```

The client keeps a cookie jar, like a browser.\
The `Set-Cookie` from `/auth/login` is stored and sent with the next requests, so `GET /auth/me` after a login works without any extra code.

One consequence to know: this transport does not run the app's *lifespan*, the startup code in `app/main.py` that will later build the MinIO client and the job queue.\
In tests those objects are simply never created, which is why part 4 puts fakes in their place by hand.

### 4. Replacing the real database session and the real services

Two mechanisms swap production objects for test ones.

**`app.dependency_overrides`.** Routes get their database session through FastAPI's dependency injection: `Depends(get_db)` means "call `get_db` and pass me what it yields".\
FastAPI keeps a dictionary, `app.dependency_overrides`, where a test can say "whenever `get_db` would be called, call this instead".\
The override must have the same shape as the original, here an async generator that yields a session.\
Ours yields the test's own `db` session, so every request of a test runs inside that test's transaction and is rolled back with it.

```python
@pytest_asyncio.fixture
async def client(db: AsyncSession) -> AsyncIterator[AsyncClient]:
    async def override_get_db() -> AsyncIterator[AsyncSession]:
        yield db  # the same rolled-back session for every request

    app.dependency_overrides[get_db] = override_get_db
    app.state.storage = FakeStorage()  # see below
    app.state.jobs = FakeJobs()
    app.state.app_events = None
    app.state.chat = None
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as http:
        yield http  # <- the test runs here
    app.dependency_overrides.clear()  # teardown: back to the real get_db
```

**`app.state` fakes.** Some things are not dependencies but attributes the lifespan sets on `app.state`, which routes read as `request.app.state.storage`.\
Since the lifespan does not run (part 3), the fixture assigns them directly.\
A *fake* is a small ordinary class with the two or three methods a route calls, keeping its data in a dict or a list so a test can inspect it:

```python
class FakeStorage:  # stands in for MinIO
    def __init__(self) -> None:
        self.objects: dict[str, bytes] = {}

    async def put_object(self, key: str, body: bytes, content_type: str) -> None:
        self.objects[key] = body

    async def get_object(self, key: str) -> bytes:
        return self.objects[key]


@dataclass
class FakeJobs:  # stands in for the Procrastinate queue
    enqueued: list[tuple[uuid.UUID, uuid.UUID]] = field(default_factory=list)

    async def enqueue_convert_to_markdown(
        self, document_id: uuid.UUID, version_id: uuid.UUID
    ) -> None:
        self.enqueued.append((document_id, version_id))
```

A test for the upload route can then assert `app.state.jobs.enqueued == [(doc_id, version_id)]` instead of waiting for a real conversion.\
No mocking library is needed for this.

### 5. Helpers for data, not more fixtures

Data setup that a test wants to control, like "register and log in as this user", is clearer as a plain `async` function than as a fixture: a test can call it twice with two emails, and the steps are visible in the test itself.\
`conftest.py` ends with two such helpers, imported by tests with `from test.conftest import sign_in, create_notebook`.

```python
async def sign_in(
    client: AsyncClient, email: str = "ada@example.com", password: str = "correct horse"
) -> dict:
    user = (
        await client.post("/auth/register", json={"email": email, "password": password})
    ).json()
    assert (
        await client.post("/auth/login", json={"email": email, "password": password})
    ).status_code == 200
    return user  # the cookie now lives in `client`
```

### How a request travels through all of this

For `await client.post("/notebooks", json={"title": "Research"})` in a test:

1. `client` asked for `db`, which asked for `engine`: Postgres was reachable, a connection was taken from the pool and a transaction opened on it.\
2.\
   httpx hands the request to the FastAPI app in-process.\
   The session cookie from `sign_in` is on it.
3. The route asks for `NotebookService`, which asks for `NotebookRepository`, which asks for `get_db`.\
   The override answers with the test's session.
4. The repository runs `INSERT ...\
   RETURNING` and calls `commit()`, which releases a savepoint.
5. The route answers 201; the test reads the JSON.
6. The test ends.\
   `client` clears the overrides, `db` closes the session and rolls back the transaction.\
   The Notebook never existed as far as the dev database is concerned.

## What to build

1. **`pyproject.toml`.** Add the `[tool.pytest.ini_options]` block of the tutorial.\
   Move `pytest`, `pyright`, `ruff`, `pre-commit` out of `dependencies` into a dev group and add `pytest-asyncio` and `httpx` there:

   ```toml
   [dependency-groups]
   dev = ["pytest==9.2.0", "pytest-asyncio>=1.0.0", "httpx>=0.28.0", "ruff==0.17.3", "pyright>=1.1.414", "pre-commit>=4.7.0"]
   ```

   then `uv sync`.

   **DONE WHEN:** the first command runs (0 tests collected, no error) and the second succeeds:

   ```sh
   uv run pytest -q
   uv run python -c "import pytest_asyncio, httpx"
   ```
![img_22.png](screenshots/img_22.png)

2. **Database access.** No separate database.\
   In `test/conftest.py`:

   ```python
   TEST_DATABASE_URL = os.environ.get("TEST_DATABASE_URL") or settings.DATABASE_URL
   TEST_DSN = TEST_DATABASE_URL.replace("postgresql+asyncpg://", "postgresql://")
   ```

   and the session-scoped `engine` fixture of the tutorial: try `asyncpg.connect(TEST_DSN, timeout=3)`, `pytest.skip` on failure, then `create_async_engine(TEST_DATABASE_URL)`, yield it, `await engine.dispose()` after.\
   `TEST_DATABASE_URL` stays as an escape hatch for CI or anyone who does want a throwaway database.

   **DONE WHEN:** a throwaway test passes, and with an unreachable URL it is reported as skipped, not failed:

   ```python
   async def test_engine(engine):
       assert engine is not None
   ```

   ```sh
   TEST_DATABASE_URL=postgresql+asyncpg://rag_notebook:rag_notebook@localhost:1/x uv run pytest -q -rs   # skipped
   ```
![img_23.png](screenshots/img_23.png)

3. **The `db` fixture.** Function-scoped as in the tutorial: one connection, `begin()`, an `AsyncSession` bound to it with `join_transaction_mode="create_savepoint"`, yield, then `close()` the session and `rollback()` the connection.

   **DONE WHEN:** two tests that each register `ada@example.com` both pass, and `select count(*) from users where email = 'ada@example.com'` on the dev database stays 0.

![img_24.png](screenshots/img_24.png)

4. **Fakes and the `client` fixture.** In `conftest.py`:

   ```python
   class FakeStorage:
       def __init__(self):
           self.objects: dict[str, bytes] = {}

       async def put_object(self, key, body, content_type):
           self.objects[key] = body

       async def get_object(self, key):
           return self.objects[key]


   @dataclass
   class FakeJobs:
       enqueued: list[tuple[uuid.UUID, uuid.UUID]] = field(default_factory=list)

       async def enqueue_convert_to_markdown(self, document_id, version_id):
           self.enqueued.append((document_id, version_id))
   ```

   (adjust `get_object`'s return shape to what T07's real class returns.) Then the `client` fixture of the tutorial: depends on `db`, overrides `get_db` with a generator that yields that same `db` session, sets `app.state.storage/jobs/app_events/chat`, yields the `AsyncClient`, clears the overrides.

   **DONE WHEN:** this test passes:

   ```python
   async def test_health(client):
       assert (await client.get("/swagger/json")).status_code == 200
   ```

![img_25.png](screenshots/img_25.png)

5. **Helpers.** `sign_in(client, email="ada@example.com", password="correct horse") -> dict` (register, then login asserting 200, return the user JSON) and `create_notebook(client, title="Research") -> dict` (POST, assert 201).\
   Tests import them with `from test.conftest import sign_in`.

   **DONE WHEN:** T03's five auth tests pass:

   ```sh
   uv run pytest test/test_auth_route.py -q
   ```
![img_26.png](screenshots/img_26.png)

6. **README.** Three lines: tests run against the dev database and roll back, `uv run pytest -q`, tests skip without Postgres.\
   The rule for the rest of the plan: one test per pattern (a router test, a repository test, a job test with fakes); no coverage target.

   **DONE WHEN:** a colleague can run the suite from the README alone.

![img_27.png](screenshots/img_27.png)

## Acceptance

- `uv run pytest` runs the auth tests of T03 green against the dev database, leaves no rows behind, and skips cleanly when Postgres is down.

## References

- Reference: `pyproject.toml`.
