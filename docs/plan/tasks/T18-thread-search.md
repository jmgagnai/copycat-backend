# T18 — Keyword search over Chat Threads (dropped)

| Mode | Effort | Priority | Depends on | Unblocks | Learning value |
| --- | --- | --- | --- | --- | --- |
| Drop | 0 | — | — | — | — |

## Why it is dropped

A second search over a different table, reusing every helper of T17, which is itself dropped.
The route is stubbed in T17 so the frontend gets an empty result instead of a 404.

## If you pick it up later

`GET /notebooks/{nb}/search/threads` returns matching Exchanges (a question and the answer it
produced) with their matches marked. Only the SQL is new: hits on `chat_messages.search_vector`
in live Threads of a live Notebook, each paired with the question before it or the answer after it
by `seq`, grouped, the question headlined whole and the answer as up to two fragments.

### What you would need to know

- Everything T17 needs (full-text search, `ts_headline`, typo correction), plus:
- Window functions: `LAG(id) OVER (PARTITION BY chat_thread_id ORDER BY seq)` and `LEAD(...)` give
  the message before and after a hit in one query.
- Grouping rows in Python so a question and its answer form one result even when both matched.
- A shared `search()` helper that takes the finder as a callable, so one route body serves both kinds.

Reference: `BACKEND/reference-backend/src/search/exchanges.py` and the second route of
`search_router.py`; Node `apps/backend/src/search/exchanges.ts`.
