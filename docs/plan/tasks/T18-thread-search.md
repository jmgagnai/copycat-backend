# T18 — Keyword search over Chat Threads (dropped)

| Mode | Effort | Priority | Depends on | Unblocks | Learning value |
| --- | --- | --- | --- | --- | --- |
| Drop | 0 | — | — | — | — |

## Why it is dropped

A second search over a different table, reusing every helper of T17, which is itself dropped.
The route is stubbed in T17 so the frontend gets an empty result instead of a 404.

## If you pick it up later

`GET /notebooks/{nb}/search/threads?q=&exact=` returns matching Exchanges, a question and the
answer it produced, with their matches marked. T17 already stubs the route with the empty result
and provides every helper: full-text search, `ts_headline`, typo correction. Only the SQL and
the grouping are new.

### What the query does

1. **Find the hits** on `chat_messages.search_vector`, restricted to live Threads
   (`deleted_at IS NULL`) of a live Notebook.
2. **Pair each hit with its other half.** A matching question is paired with the answer after it,
   a matching answer with the question before it, by `seq`:

   ```sql
   LAG(id)  OVER (PARTITION BY chat_thread_id ORDER BY seq) AS previous_id,
   LEAD(id) OVER (PARTITION BY chat_thread_id ORDER BY seq) AS next_id
   ```

3. **Group into Exchanges** in Python, so a question and its answer form one result even when
   both matched.
4. **Headline** the question whole and the answer as up to two fragments.

### What you would need to know

- **Window functions.** `LAG` and `LEAD` give the message before and after a hit in the same
  query, with no self-join.
- **Grouping rows in Python.** One dict keyed by the question's id, filled from hits on either
  side of the pair.
- **One route body for both searches.** A shared `search()` helper takes the finder as a
  callable, so the Documents route and the Threads route differ only in the finder they pass.

### References

- Node: `apps/backend/src/search/exchanges.ts`.
