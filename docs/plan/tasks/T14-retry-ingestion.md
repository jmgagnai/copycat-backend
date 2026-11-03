# T14 — Retry a failed ingestion (dropped)

| Mode | Effort | Priority | Depends on | Unblocks | Learning value |
| --- | --- | --- | --- | --- | --- |
| Drop | 0 | — | — | — | — |

## Why it is dropped

One more UPDATE and one more route in a shape T08 already taught. A failed Version stays failed;
uploading the file again creates a new Version and runs ingestion from the start, which is what
the retry did anyway in the simplified design.

## What the frontend sees

`POST .../versions/{versionId}/retry` does not exist, so the Retry button on a failed Document
gets a 404 `{"message": "Not Found"}` and shows an error. Accepted.

## If you pick it up later

Three pieces: a repository method, a route, and a test. The contract already defines the route:

| Answer | When |
| --- | --- |
| 202 `{"status": "queued"}` | the Version was `failed` for a reason worth retrying, and is queued again |
| 404 | the Notebook, Document or Version does not exist |
| 409 | the Version is not `failed`, or failed for a reason the same file would repeat |

### 1. The repository method

```python
RETRYABLE_REASONS = ["unexpected", "service-unavailable", "timed-out"]

RetryOutcome = Literal["retried", "not-found", "not-retryable"]


async def retry_ingestion(
    self, notebook_id: uuid.UUID, document_id: uuid.UUID, version_id: uuid.UUID
) -> RetryOutcome: ...
```

1. Load the Version with the shared `_version_row()`; `not-found` when it is missing.
2. Reset it in one conditional UPDATE. The WHERE clause is the whole decision:

   ```sql
   UPDATE document_versions
   SET ingestion_status = 'queued',
       failure_reason = NULL,
       failed_at = NULL,
       ingestion_error = NULL
   WHERE id = :id
     AND ingestion_status = 'failed'
     AND failure_reason = ANY(:retryable)
   ```

   with `{"id": version_id, "retryable": RETRYABLE_REASONS}`.
3. Read the row count with T08's `rowcount()` helper. Zero rows updated means the Version was
   not `failed`, or failed for a non-retryable reason: return `not-retryable`.
4. Otherwise publish the `queued` status event through `set_version_status` (T10) and return
   `retried`.

### 2. The route

`POST /notebooks/{nb}/documents/{id}/versions/{versionId}/retry`:

- map the outcome to the three answers above;
- enqueue stage 1 only after the commit, so the worker never sees a row that was rolled back.

### 3. The test

- A `queued` Version answers 409.
- After setting it `failed` with reason `timed-out` by SQL, it answers 202 and the stub queue saw
  one `convert_to_markdown` enqueue.

### What you would need to know

- **A conditional UPDATE as the decision.** `WHERE ... AND ingestion_status = 'failed' AND
  failure_reason = ANY(:retryable)`, then `result.rowcount`: 0 rows updated means
  "not retryable". No separate SELECT, no race between the check and the write.
- **A Python list as a Postgres array parameter.** Pass the list as-is, asyncpg binds it:
  `{"retryable": ["unexpected", "service-unavailable", "timed-out"]}`.
- **A three-valued outcome.** The repository returns `retried`, `not-found` or `not-retryable`;
  the route maps them to 202, 404 and 409.
- **Event, then commit, then enqueue.** The `queued` status event goes through
  `set_version_status` (T10), which commits; stage 1 is enqueued after that `commit()`.

### References

- Python: `retry_ingestion` in `BACKEND/reference-backend/src/document/document_repository.py`
  and the route in `document_router.py`.
- Node: `retryIngestion` in `apps/backend/src/documents/`.
