# T01 — Project foundation: settings, database, app bootstrap

| Mode | Effort | Priority | Depends on | Unblocks | Learning value |
| --- | --- | --- | --- | --- | --- |
| Write | 1 day | P1 | — | everything | Medium |

## Learning value

New ground once: pydantic-settings, async SQLAlchemy, FastAPI lifespan and exception handlers. After that it is configuration.

## Why

Today `src/app/main.py` builds a FastAPI app from router stubs, `db/postgresql.py` reads only
`DATABASE_URL` (with `echo=True`, which floods the log), there is no place for the other
environment variables, and `main.py` at the root is a hello-world. Nothing can be run end to end
until the process can start against the existing database and serve errors in the contract's shape.

The Python backend runs **no database migrations**. The Node backend owns the schema: it applies
the `.sql` files of `NOTEBOOKS/apps/backend/src/db/migrations/` on its own startup (or with
`pnpm backend:migrate`). copycat-backend connects to that database and uses the tables as they are.

## Current state

- `src/db/postgresql.py`: `DbSettings` with `DATABASE_URL` only; `engine` with `echo=True`.
- `src/app/main.py`: includes the five routers; no lifespan, no CORS, no error handlers.
- `main.py` (root): hello world. `src/main.py`: a throwaway query script, delete it.
- No `settings.py`, no logging setup. No migrations folder, and none is wanted.

## What you need to know

### 1. pydantic-settings: one class for every environment variable

A `BaseSettings` subclass reads each field from the environment (or a `.env` file), converts
it to the annotated type and falls back to the default. Properties derive values the code needs
in another shape.

```python
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")
    PORT: int = 3000
    DATABASE_URL: str = (
        "postgresql+asyncpg://rag_notebook:rag_notebook@localhost:5432/rag_notebook"
    )
    ADMIN_EMAILS: str = ""

    @property
    def postgres_dsn(
        self,
    ) -> str:  # drivers other than SQLAlchemy want the plain scheme
        return self.DATABASE_URL.replace("postgresql+asyncpg://", "postgresql://")

    @property
    def administrators(self) -> set[str]:
        return {e.strip().lower() for e in self.ADMIN_EMAILS.split(",") if e.strip()}


settings = Settings()  # one module-level instance, imported everywhere
```

Try it: `PORT=3100 ADMIN_EMAILS="Ada@x.io, bob@x.io" uv run python -c "from settings import settings; print(settings.PORT, settings.administrators)"` from `src/` prints `3100 {'ada@x.io', 'bob@x.io'}`.

### 2. Async SQLAlchemy: engine, session factory, one session per request

The engine owns the connection pool. A `async_sessionmaker` makes sessions; `get_db` is a
generator dependency that yields one session per request and closes it after. Raw SQL goes
through `text()` with named `:parameters`, never f-strings with user data.

```python
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

engine = create_async_engine(settings.DATABASE_URL)
AsyncSessionLocal = async_sessionmaker(
    bind=engine, class_=AsyncSession, expire_on_commit=False
)


async def get_db():
    async with AsyncSessionLocal() as session:
        yield session


# usage
async with AsyncSessionLocal() as db:
    value = (await db.execute(text("SELECT :n + 1"), {"n": 1})).scalar_one()  # 2
```

### 3. The database is not this project's concern

copycat-backend neither creates, migrates nor checks the schema. It connects to the database named
by `DATABASE_URL`, which the Node backend has already migrated, and runs queries against the tables
as they are. If a table is missing, the first query raises a `ProgrammingError` ("relation ... does
not exist"), and that is enough of a signal: the fix is on the Node side (`pnpm backend:migrate`),
not here. There is no `migrations/` folder, no runner and no startup check to write.

The only place a second database appears is the test suite (T05). It is prepared once, by hand,
with the Node tooling; the Python code only reads it.

### 4. FastAPI lifespan and `app.state`

`lifespan` is an async context manager: the code before `yield` runs at startup, the code after
at shutdown. Objects built at startup (storage, queue, subscriber) are hung on `app.state` so
routes can reach them through `request.app.state` and tests can replace them.

```python
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request


@asynccontextmanager
async def lifespan(app: FastAPI):
    logging.basicConfig(level=settings.LOG_LEVEL.upper())
    app.state.storage = None  # T07 puts the real object here
    yield
    # shutdown: close what you opened


app = FastAPI(
    lifespan=lifespan, docs_url="/documentation", openapi_url="/documentation/json"
)


@app.get("/health")
async def health(request: Request):
    return {"storage": request.app.state.storage is not None}
```

### 5. Exception handlers shape every error body

FastAPI answers `{"detail": ...}` by default. The frontend reads `{"message": ...}`. Two handlers
fix every route at once: one for `HTTPException` (your 401/404/409), one for
`RequestValidationError` (bad body or query, FastAPI's default is 422).

```python
from fastapi import HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse


@app.exception_handler(HTTPException)
async def http_exception_handler(_: Request, exc: HTTPException) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code,
        content={"message": str(exc.detail)},
        headers=exc.headers,
    )


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(
    _: Request, __: RequestValidationError
) -> JSONResponse:
    return JSONResponse(status_code=400, content={"message": "Invalid request."})
```

From now on a route raises `HTTPException(404, "Notebook not found.")` with a plain string, never
a dict.

### 6. CORS for the Angular dev server

The frontend runs on another port and sends the session cookie, so CORS must allow credentials.
With credentials, `allow_origins=["*"]` is refused by browsers; use `allow_origin_regex=".*"`.

```python
from fastapi.middleware.cors import CORSMiddleware

app.add_middleware(
    CORSMiddleware,
    allow_origin_regex=".*",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
```

### 7. `src` as the import root

Every module imports as `from settings import settings`, `from db import get_db`. That works
because `uvicorn.run(..., app_dir="src")` and pytest's `pythonpath = ["src"]` put `src` on
`sys.path`. The root `main.py` must do the same before importing anything from `src`.

## What to build

1. **`src/settings.py`.** One `Settings(BaseSettings)` with every variable the Node backend reads
   (`apps/backend/src/env.ts`): `PORT`, `APP_ENV`, `LOG_LEVEL`, `DATABASE_URL`, `JWT_SECRET`,
   `MINIO_ENDPOINT`, `MINIO_ACCESS_KEY`, `MINIO_SECRET_KEY`, `DOCUMENTS_BUCKET`,
   `OPENROUTER_API_KEY: str | None`, the seven `OPENROUTER_MODEL_*: str | None` overrides,
   `ADMIN_EMAILS`, `DOCLING_IMAGE`, `DOCLING_TIMEOUT_MS`, `DOCLING_TABLE_MODE: Literal["fast", "accurate"]`,
   `DOCKER_BIN`. Copy each default from `env.ts`. Add the `postgres_dsn` and `administrators`
   properties of the tutorial. Use `str`, not `PostgresDsn`, for the URL: the drivers want a string.

   **DONE WHEN:** the command prints a `postgresql://` URL, and prefixing it with `PORT=1` changes `settings.PORT`:

   ```sh
   cd src && uv run python -c "from settings import settings; print(settings.postgres_dsn)"
   ```
![img.png](screenshots/img.png)

2. **`src/db/postgresql.py`.** Delete `DbSettings`; build the engine from `settings.DATABASE_URL`
   without `echo=True`; keep `AsyncSessionLocal` and `get_db`. Add the small helper the UPDATE
   routes need later:

   ```python
   from typing import cast
   from sqlalchemy import CursorResult, Result


   def rowcount(result: Result) -> int:
       return cast(CursorResult, result).rowcount
   ```

   Re-export `AsyncSessionLocal`, `get_db` and `rowcount` from `src/db/__init__.py` (the check
   below and T05 import them from the package `db`, not from `db.postgresql`).

   **DONE WHEN:** the command prints `1` with no SQL echoed:

   ```sh
   cd src && uv run python -c "import asyncio; from sqlalchemy import text; from db import AsyncSessionLocal
   async def m():
       async with AsyncSessionLocal() as db: print((await db.execute(text('SELECT 1'))).scalar_one())
   asyncio.run(m())"
   ```
![img_1.png](screenshots/img_1.png)

3. **No database setup.** Nothing to write: do not copy the `.sql` files, do not write a
   migration runner, do not add a schema check (topic 3). The database is the one the Node backend
   migrated, reached through `DATABASE_URL`.

   **DONE WHEN:** `src/db/` holds only `__init__.py`, `base.py` and `postgresql.py`, and the
   session check of step 2 passes against the dev database.

![img_2.png](screenshots/img_2.png)

4. **`src/app/main.py`.** Rebuild the module in this order: the `lifespan` (logging,
   placeholders `app.state.storage = app.state.jobs = app.state.app_events = app.state.chat = None`
   that T06, T07 and T09 fill), `app = FastAPI(title="RAG Notebook API", docs_url="/documentation",
   openapi_url="/documentation/json", lifespan=lifespan)`, the CORS middleware, one loop including
   the routers, then the two exception handlers of the tutorial. Delete `src/main.py`.

   **DONE WHEN:** with the server running, the three commands show that both handlers are in
   place. An unknown path answers 404 with `{"message":"Not Found"}` (the `HTTPException` handler,
   instead of FastAPI's `{"detail":"Not Found"}`); a bad register body answers 400 with
   `{"message":"Invalid request."}` (the validation handler); and a stub route answers 500, which
   is expected until T03 and T04 replace the `NotImplementedError` stubs:

   ```sh
   curl -s -i localhost:3000/nope | sed -n '1p;$p'                                                  # HTTP/1.1 404 ... {"message":"Not Found"}
   curl -s -X POST localhost:3000/auth/register -H 'content-type: application/json' -d '{}'        # {"message":"Invalid request."}
   curl -s -o /dev/null -w '%{http_code}\n' localhost:3000/notebooks                               # 500 for now
   ```
   If the last command answers 307, a router declares its collection route as `"/"` under a
   `prefix`; declare full paths (`@router.get("/notebooks")`) as the contract does.

![img_3.png](screenshots/img_3.png)

5. **Root `main.py`.** Replace the hello world:

   ```python
   import sys
   from pathlib import Path
   import uvicorn

   sys.path.insert(0, str(Path(__file__).parent / "src"))
   from settings import settings  # noqa: E402

   if __name__ == "__main__":
       uvicorn.run("app.main:app", host="0.0.0.0", port=settings.PORT, app_dir="src")
   ```

   **DONE WHEN:** the server starts and `http://localhost:3000/swagger` opens Swagger with
   the five routers:

   ```sh
   uv run python main.py
   ```
![img_4.png](screenshots/img_4.png)

![img_5.png](screenshots/img_5.png)

6. **`.env.example`.** One line per variable of step 1 with its default, the secrets left blank.
   Keep `.env` in `.gitignore`. Add `[tool.pytest.ini_options]` with `pythonpath = ["src"]` to
   `pyproject.toml` now so T05 only adds the asyncio keys, and lower pyright to
   `typeCheckingMode = "basic"` with `pythonVersion = "3.12"` (the current `3.15` and strict mode
   will stop you on every library without stubs).

   **DONE WHEN:** a fresh clone starts with step 5's command after:

   ```sh
   cp .env.example .env
   ```
![img_6.png](screenshots/img_6.png)

## Acceptance

✅ `uv run python main.py` starts against the compose Postgres that the Node backend migrated and
  `/swagger` opens.

✅ A request with a bad body answers `400 {"message": "..."}`; a 404 from a router answers
  `{"message": "..."}` (not FastAPI's `{"detail": ...}`).
