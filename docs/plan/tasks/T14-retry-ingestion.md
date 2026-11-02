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

The contract answers 202 `{"status": ...}`, 404, or 409 when the Version is not failed or failed
for a reason the same file would repeat.

1. `DocumentRepository.retry_ingestion(notebook_id, document_id, version_id)`: load the Version
   with the shared `_version_row()` (404 when missing); `UPDATE document_versions SET
   ingestion_status = 'queued', failure_reason = NULL, failed_at = NULL, ingestion_error = NULL WHERE
   id = :id AND ingestion_status = 'failed' AND failure_reason = ANY(:retryable)` with
   `retryable = ['unexpected', 'service-unavailable', 'timed-out']`; rowcount 0 → `not-retryable`;
   otherwise publish the `queued` status event through `set_version_status` and return `retried`.
2. Route: map the outcome to 202 `{"status": "queued"}`, 404, 409; enqueue stage 1 after the commit.
3. Test: a queued Version answers 409; after setting it `failed`/`timed-out` by SQL it answers 202
   and the stub queue saw the enqueue.

### What you would need to know

- `UPDATE ... WHERE id = :id AND ingestion_status = 'failed' AND failure_reason = ANY(:retryable)`
  and reading `result.rowcount` (T08's `rowcount()` helper): 0 rows updated means "not retryable".
- Passing a Python list as a Postgres array parameter: `{"retryable": ["unexpected", "timed-out"]}`.
- Mapping a three-valued outcome (`retried`, `not-found`, `not-retryable`) to 202, 404, 409 in the route.
- Publishing the `queued` status event through `set_version_status` (T10) and enqueueing stage 1
  only after `commit()`, so the worker never sees a row that was rolled back.

Reference: `retry_ingestion` in `BACKEND/reference-backend/src/document/document_repository.py`
and the route in `document_router.py`; Node `retryIngestion` in `apps/backend/src/documents/`.
