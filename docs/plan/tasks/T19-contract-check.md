# T19 — Frontend round trip

| Mode | Effort | Priority | Depends on | Unblocks | Learning value |
| --- | --- | --- | --- | --- | --- |
| Write (a checklist) | 0.25 day | P2 | T16, T17 | — | Low |

## What was cut

The contract comparison script (`openapi.json` against `/documentation/json`) and
`docs/contract-check.md`. The frontend run finds the same mismatches faster.

## Why

The frontend's API client is generated from `NOTEBOOKS/apps/backend/openapi.json`. The Python
backend must answer the same paths, status codes and camelCase JSON keys or the UI breaks silently.

## What you need to know

### 1. Running both sides

The Angular dev server calls `http://localhost:3000` directly (`apps/frontend/src/environments/environment.ts`),
so the Python backend must listen on 3000 and allow the browser origin with credentials. Stop the
Node backend first or the port is taken.

```sh
# terminal 1, in NOTEBOOKS: Postgres, MinIO, Docling
docker compose up -d
# terminal 2, in BACKEND/copycat-backend
uv run python main.py            # must say it listens on :3000
# terminal 3, in NOTEBOOKS
pnpm frontend:dev                 # opens http://localhost:4200
```

CORS is set up in T01. Without `allow_credentials` the auth cookie is never sent and every call
after login is 401:

```python
CORSMiddleware(
    allow_origin_regex=".*",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
```

### 2. Reading the browser

Open DevTools (F12). The **Console** tab shows uncaught errors; a red line naming an Angular
component after you clicked something usually means a response had the wrong shape. The
**Network** tab shows each request: click one, then **Response** to see the JSON the backend sent
and **Headers** for the status code. Filter by `Fetch/XHR` to hide assets, and tick "Preserve log"
so a page reload does not clear it.

### 3. What a mismatch looks like

| Symptom | Cause | Fix |
| --- | --- | --- |
| A field shows as empty or `undefined` | snake_case key, e.g. `created_at` | add `serialization_alias="createdAt"` on the DTO field |
| Error toast says `[object Object]` or nothing | body is `{"detail": "..."}` | raise `HTTPException(code, "text")` and let T01's handler produce `{"message"}` |
| 422 in the Network tab | FastAPI validation error not mapped | T01's handler must turn it into 400 `{"message": "Invalid request."}` |
| Every request 401 after login | cookie not set or not sent | check `Set-Cookie` on the login response and the CORS credentials flag |
| Status badge never moves | `/events` not streaming | `curl -N -b cookies.txt localhost:3000/events` must print `: connected` immediately |

Try it. This must print `401` and a body of exactly `{"message":"..."}`:

```sh
curl -i -c cookies.txt -X POST localhost:3000/auth/login \
  -H 'content-type: application/json' -d '{"email":"a@b.c","password":"wrong"}'
```

## What to do

Run the frontend against this backend and walk the eight steps below with DevTools open, the
Network tab filtered on `Fetch/XHR`. Each step says what to do in the UI, then what you must see
for it to count as done. Fix every mismatch before moving on; most are a missing alias or a
`detail` body, both found with the table above.

### Step 1. Register, log out, log in

**DONE WHEN** the Network tab shows, in this order:

| Request | Status | Also check |
| --- | --- | --- |
| `POST /auth/register` | 201 | |
| `POST /auth/logout` | 204 | |
| `POST /auth/login` | 200 | a `Set-Cookie` header on the response |
| `GET /auth/me` | 200 | |

### Step 2. Create a Notebook, rename it, see it in the list

**DONE WHEN:**

- the list shows the new title after a page reload;
- `GET /notebooks` returns `createdAt` in camelCase.

### Step 3. Upload a PDF and watch the badge

**DONE WHEN:**

- the status moves through every stage without a reload (T06):
  `queued`, `converting`, `converted`, `summarizing`, `summarized`, `indexing`, `ready`;
- `/events` in the Network tab stays pending with a growing size.

### Step 4. Open the Document

**DONE WHEN:**

- the Abstract and the Executive Summary are shown and non-empty;
- the download button gives a file of the same size as the one uploaded (`ls -l` both).

### Step 5. Upload the same file again, delete, restore

**DONE WHEN:**

- the Document shows version 2;
- after delete it leaves the list;
- after restore it is back, with version 2 still current.

### Step 6. Create a Thread and ask a question

**DONE WHEN:**

- paragraphs appear one by one before the full answer;
- `[n]` markers render as links, and clicking one opens the right Document at the cited passage;
- `POST .../messages` answers 201 with `question` and `answer`.

### Step 7. Search

**DONE WHEN:** the search box answers "no results" and the Console shows no error (T17 stub).

### Step 8. Retry on a failed Document

Stop the Docling container, upload a file, start the container again.

**DONE WHEN:** the Retry button shows an error toast and nothing else breaks (T14 dropped).

## Acceptance

- The eight steps above work without an uncaught console error.

## References

- NOTEBOOKS `README.md` (Generated code), `apps/frontend/src/app/api/`,
  `apps/frontend/src/environments/environment.ts`.
