# T16 — Grounded chat answers, streamed with Citations

| Mode | Effort | Priority | Depends on | Unblocks | Learning value |
| --- | --- | --- | --- | --- | --- |
| Write | 1.5 days | P2 | T06, T11, T13, T15 | — | High |

## Learning value

Retrieval with pgvector cosine distance, building a grounded prompt, resolving `[n]` markers into pinned Citations, streaming an answer paragraph by paragraph over the event bus, and recording the exchange atomically. The heart of the product.

## Why

`POST /notebooks/{nb}/threads/{t}/messages` is the product: retrieve the closest Chunks from the
Notebook's `ready` Documents, stream the answer as `chat-answer-chunk` events, then record the
exchange with one Citation per source marker, pinned to the exact Document Version and chunk.

## What you need to know

### 1. Cosine distance in pgvector

`chunks.embedding` is a `vector(2560)` column. The `<=>` operator is cosine distance: 0 for the
same direction, 1 for orthogonal, 2 for opposite. Similarity is `1 - distance`. Sort by distance
ascending and `LIMIT` to get the closest Chunks. There is no index on 2560 dimensions, so this is
an exact scan over the Notebook's Chunks, which is fine at this size.

```sql
SELECT c.id, c.text, 1 - (c.embedding <=> CAST(:q AS vector)) AS similarity
FROM chunks c
ORDER BY c.embedding <=> CAST(:q AS vector), c.id
LIMIT 12;
```

`:q` is pgvector's text form, `[0.1,0.2,...]`, not a Postgres array. T13 already has the helper:

```python
def to_vector_literal(vector: list[float]) -> str:
    return "[" + ",".join(repr(x) for x in vector) + "]"
```

Try it: `psql postgresql://rag_notebook:rag_notebook@localhost:5432/reference_backend_test -c "SELECT 1 - (CAST('[1,0]' AS vector) <=> CAST('[0,1]' AS vector))"` prints `0`.

### 2. Only search the right Versions

Retrieval joins `chunks` to the `searchable_versions` CTE from T08: per Document the latest
non-deleted Version, kept only when `ready`. Prefix the query with the CTE and pass `:notebook_id`
alongside `:q`:

```python
rows = await db.execute(
    text(
        f"WITH {SEARCHABLE_VERSIONS_CTE} SELECT c.id AS chunk_id, l.document_id, l.version_id, "
        "l.filename, c.heading_path, c.text, l.chat_snippet, "
        "1 - (c.embedding <=> CAST(:q AS vector)) AS similarity "
        "FROM chunks c JOIN searchable_versions l ON l.version_id = c.document_version_id "
        "ORDER BY c.embedding <=> CAST(:q AS vector), c.id LIMIT :limit"
    ),
    {"notebook_id": notebook_id, "q": to_vector_literal(query_embedding), "limit": 12},
)
```

Carry `version_id` out of retrieval: a Citation pins the Version retrieval chose, not whatever
Version is latest when someone reads the answer later.

### 3. A prompt that numbers its sources

The model can only cite what it is shown, so each Chunk gets a 1-based label in retrieval order,
and the same list is used to read the markers back. Group Chunks by source and introduce each
source once with its Chat Snippet (T12's artifact written for a model):

```python
def format_sources(chunks: list[RetrievedChunk]) -> str:
    parts = []
    for i, chunk in enumerate(chunks, start=1):
        parts.append(
            f"### Source: {chunk.filename}\nAbout this source: {chunk.chat_snippet}\n"
            f"Chunk [{i}]:\n{chunk.text}"
        )
    return "\n\n".join(parts)
```

The user turn is then `## Sources`, the formatted chunks, `## The Chat Thread so far` (the last
10 messages as `Question:` / `Answer:` lines), and `## The question to answer now`. The system
prompt says: answer only from the sources, end factual sentences with `[n]`, never invent a marker.

### 4. Async generators: consuming a token stream

T11's `OpenRouterClient.stream(request)` is an async generator yielding text deltas. You consume
it with `async for`, accumulating the full text as you go:

```python
async def fake_stream(request) -> AsyncIterator[str]:
    for piece in ["Hello ", "[1].\n\nMore", " text."]:
        yield piece


text = ""
async for delta in fake_stream(request):
    text += delta
```

A function with `yield` inside `async def` is an async generator. Anything that takes a
`ChatStreamer = Callable[[ChatCompletionRequest], AsyncIterator[str]]` accepts the real client
and this fake alike, which is how the route test runs without a key.

### 5. Releasing paragraphs, not tokens

Tokens arrive a few characters at a time. Pushing each one to the browser is noisy, and Markdown
rendered mid-word flickers. The `AnswerChunker` buffers and releases one paragraph when the blank
line after it arrives, so nothing shown is ever revised:

```python
class AnswerChunker:
    def __init__(self) -> None:
        self.buffer = ""

    def push(self, delta: str) -> list[str]:
        self.buffer += delta
        *done, self.buffer = self.buffer.split("\n\n")
        return [p.strip() for p in done if p.strip()]

    def flush(self) -> list[str]:
        last, self.buffer = self.buffer.strip(), ""
        return [last] if last else []
```

Try it: `push("First para\n\nSecond ")` returns `["First para"]`, `push("para\n\nTail")` returns
`["Second para"]`, `flush()` returns `["Tail"]`. The `*done, self.buffer = ...` line is star
unpacking: everything before the last split goes to `done`, the unfinished tail stays buffered.

### 6. Publishing on the T06 bus

Every paragraph becomes an app event on the Notebook's topic, through `publish_app_event` and a
commit (`pg_notify` is transactional, so the commit is what delivers it). The SSE route of T06
forwards it to every browser watching that Notebook. Three event types: `chat-answer-chunk`
(`streamId`, `index`, `text`), `chat-answer-completed` (`messageId`, `questionId`, `citations`),
`chat-answer-failed` (`reason`). `streamId` is minted before the answer exists, so clients can
group chunks; `index` lets a client that joined late notice the gap and reload the Thread.

```python
await publish_app_event(
    db,
    AppEventDraft(
        type="chat-answer-chunk",
        topic=notebook_topic(notebook_id),
        data={
            "notebookId": str(notebook_id),
            "threadId": str(thread_id),
            "streamId": stream_id,
            "index": 0,
            "text": "First para",
        },
    ),
)
await db.commit()
```

Try it: with the server running, `curl -N -b cookies.txt localhost:3000/events` in one terminal,
then ask a question from another: the chunk frames appear before the HTTP response returns.

### 7. Reading markers back and pinning them

A regex finds `[2]` and `[1, 3]`. A marker is resolved only by indexing into the retrieved list,
so an answer can never cite something it was not shown; `[9]` with three Chunks is ignored and the
prose is kept as written:

```python
MARKER_GROUP = re.compile(r"\[\s*(\d{1,3}(?:\s*,\s*\d{1,3})*)\s*\]")


def markers(answer: str, n_chunks: int) -> list[int]:
    found: set[int] = set()
    for m in MARKER_GROUP.finditer(answer):
        for part in m.group(1).split(","):
            k = int(part)
            if 1 <= k <= n_chunks:
                found.add(k)
    return sorted(found)


markers("Revenue grew [2]. Costs fell [1, 3]. Bogus [9].", 3)  # [1, 2, 3]
```

Then one query over `chunk_ranges` (T13 writes it) fills in `char_start` and `char_end` so the
frontend can scroll the Converted Markdown to the cited passage. A Chunk with no row keeps nulls.
`dataclasses.replace(citation, char_start=..., char_end=...)` returns an updated copy of a frozen
dataclass.

### 8. Injected dependencies in a dataclass

The chat module needs three things from outside: a streamer, an embedder and a model name. Put
them in a dataclass built once in the lifespan (`app.state.chat`) and read through a `Depends`:

```python
@dataclass
class ChatDeps:
    stream: ChatStreamer
    embed: Embedder  # Callable[[list[str]], Awaitable[list[list[float]]]]
    model: str


def get_chat_deps(request: Request) -> ChatDeps | None:
    return getattr(request.app.state, "chat", None)
```

When there is no `OPENROUTER_API_KEY`, `app.state.chat` is `None` and the route answers 503. In a
test, `app.state.chat = ChatDeps(stream=fake_stream, embed=fake_embed, model="m")` makes the whole
route run offline, where `fake_embed` returns `[[0.0] * 2560]`.

### 9. One transaction for the exchange

T15's `append_question_and_answer` inserts the question, the answer and its Citations and commits
once. The question's `seq` is lower than the answer's because `chat_messages.seq` is a sequence
column, which is why `list_chat_messages` orders by `seq` and not by `created_at` (both rows share
a timestamp). Read the history **before** inserting, or the question would appear in its own
history.

## What to build

1. **`chat/retrieval.py`: `RetrievedChunk` and `retrieve_chunks`.** A frozen dataclass with
   `chunk_id`, `document_id`, `document_version_id`, `filename`, `heading_path: list[str]`, `text`,
   `chat_snippet: str | None`, `similarity: float`, and the function of tutorial item 2, default
   `limit=12`. Convert `heading_path` with `list(row.heading_path)` and `similarity` with `float()`.

   **DONE WHEN:** a test seeds one `ready` Version with one chunk (T13's test seed, zero vector
   is fine) and retrieval returns that chunk with `similarity` close to 0; a Version in status
   `embedding` returns nothing:

   ```python
   chunks = await retrieve_chunks(db, notebook_id, [0.0] * 2560)
   assert len(chunks) == 1 and abs(chunks[0].similarity) < 1e-6
   ```

2. **`chat/citations.py`: markers in, Citations out.** `ResolvedCitation(marker, chunk, char_start=None,
   char_end=None)` as a frozen dataclass; `CITATION_INSTRUCTIONS`, the two prompt bullets that ask
   for `[n]` after every factual sentence and forbid invented markers; `resolve_citation_markers(answer,
   chunks)` returning one Citation per distinct marker, sorted; `locate_citations(db, citations)`:
   ```python
   rows = await db.execute(
       text(
           "SELECT chunk_id, char_start, char_end FROM chunk_ranges WHERE chunk_id = ANY(CAST(:ids AS uuid[]))"
       ),
       {"ids": [c.chunk.chunk_id for c in citations]},
   )
   ```

   **DONE WHEN:** marker resolution keeps the markers that name a chunk, in order, and after
   `locate_citations` a chunk with a `chunk_ranges` row has integer `char_start` and `char_end`:

   ```python
   citations = resolve_citation_markers("A [2]. B [1, 2]. C [9][0].", [c1, c2])
   assert [c.marker for c in citations] == [1, 2]
   assert citations[1].chunk is c2
   ```

3. **`chat/streaming.py`: `AnswerChunker` and `AnswerStream`.** The chunker of tutorial item 5
   (also normalise `\r\n` to `\n`). `AnswerStream(db, notebook_id, thread_id)` holds a fresh
   `streamId`, an `index` counter and the identity dict; `chunk(text)`, `completed(message_id,
   question_id, citations)` and `failed(reason)` each publish one event and commit. Serialise
   Citations with `c.model_dump(by_alias=True, mode="json")` so UUIDs become strings.

   **DONE WHEN:** the chunker test of item 5 passes, and in a test with a real `db` publishing a
   chunk and then querying raises nothing (the event payload is below Postgres' 8000-byte limit
   for a paragraph):

   ```python
   await AnswerStream(db, notebook_id, thread_id).chunk("hi")
   await db.execute(text("SELECT 1"))
   ```

4. **`chat/chat_service.py`: `ChatDeps`, the prompt, `stream_answer`.** `ChatDeps` of item 8;
   `NO_SOURCES_ANSWER`, a fixed sentence the application says when nothing was retrieved;
   `CHAT_SYSTEM_PROMPT` including `CITATION_INSTRUCTIONS`; `format_sources` and `format_history`;
   then:
   ```python
   async def stream_answer(
       db, deps, notebook_id, question, history, on_chunk
   ) -> GroundedAnswer:
       (query_embedding,) = await deps.embed([question])
       chunks = await retrieve_chunks(db, notebook_id, query_embedding)
       if not chunks:
           await on_chunk(NO_SOURCES_ANSWER)
           return GroundedAnswer(NO_SOURCES_ANSWER, [])
       request = ChatCompletionRequest(
           deps.model, CHAT_SYSTEM_PROMPT, build_user_turn(chunks, history, question)
       )
       chunker, text = AnswerChunker(), ""
       async for delta in deps.stream(request):
           text += delta
           for piece in chunker.push(delta):
               await on_chunk(piece)
       for piece in chunker.flush():
           await on_chunk(piece)
       if not text.strip():
           raise RuntimeError("The model returned no content.")
       return GroundedAnswer(
           text, await locate_citations(db, resolve_citation_markers(text, chunks))
       )
   ```
   `on_chunk` is `Callable[[str], Awaitable[None]]`, which is `AnswerStream.chunk` in the route and a
   list-appending coroutine in tests. Raise on failure so the route records nothing.

   **DONE WHEN:** with `fake_stream` yielding `"Para one [1].\n\nPara two."` and one seeded chunk,
   `stream_answer` calls `on_chunk` twice and returns one Citation for marker 1; with no seeded
   chunk it returns `NO_SOURCES_ANSWER` without calling `deps.stream` (make the fake raise if called).

5. **The route in `chat/chat_router.py`.** Replace T15's 503 placeholder on
   `POST /notebooks/{notebookId}/threads/{threadId}/messages` (status 201, `SendChatMessageResponse`):
   ```python
   thread = await repo.find_chat_thread(notebook_id, thread_id)
   if thread is None:
       raise HTTPException(404, "Chat Thread not found.")
   if chat is None:
       raise HTTPException(
           503, "Chat is not configured on this server: OPENROUTER_API_KEY is not set."
       )
   history = await repo.list_chat_messages(thread.id)
   stream = AnswerStream(db, thread.notebook_id, thread.id)
   try:
       answer = await stream_answer(
           db, chat, thread.notebook_id, body.content, history, stream.chunk
       )
   except Exception as err:
       log.exception("A chat answer could not be generated.")
       await stream.failed(str(err))
       raise HTTPException(
           502,
           "The answer could not be generated. Nothing was recorded; please ask again.",
       ) from None
   question, recorded = await repo.append_question_and_answer(
       thread.id, user.id, body.content, answer.text, answer.citations
   )
   await stream.completed(recorded.id, question.id, recorded.citations)
   return SendChatMessageResponse(question=question, answer=recorded)
   ```
   `chat: ChatDeps | None = Depends(get_chat_deps)` and `db: AsyncSession = Depends(get_db)` are
   route parameters; the same session is used by the repository, the stream and retrieval.

   **DONE WHEN:** asking answers 404 for an unknown Thread, 503 with no key, and 201
   `{"question": {...}, "answer": {...}}` with a fake:

   ```sh
   curl -b cookies.txt -X POST localhost:3000/notebooks/<nb>/threads/<thread>/messages \
     -H 'content-type: application/json' -d '{"content":"hi"}'
   ```

6. **Lifespan wiring in `app/main.py`.** After T11's client and embedder are built:
   ```python
   app.state.chat = (
       ChatDeps(client.stream, embed, task_models.chat_answer)
       if client and embed
       else None
   )
   ```

   **DONE WHEN:** starting the server with `OPENROUTER_API_KEY` set logs no error and
   `GET /notebooks/{nb}/threads/{t}/messages` still works; without the key, asking answers 503.

7. **Tests, one per pattern.** In `test/test_chat_pure.py`: marker resolution (step 2) and the
   chunker (step 3), no database. In `test/test_chat_route.py`: 503 without deps; then set
   `app.state.chat = ChatDeps(stream=fake_stream, embed=fake_embed, model="m")` on the app the
   client wraps, ask in a Notebook with no `ready` Document, and assert 201, the answer content is
   `NO_SOURCES_ANSWER`, both rows carry the asker and `citations == []`, and
   `GET .../messages` lists roles `["user", "assistant"]`.

   **DONE WHEN:** both test files are green in under five seconds:

   ```sh
   uv run pytest test/test_chat_pure.py test/test_chat_route.py -q
   ```

## Acceptance

- With a real key and a `ready` Document, asking a question returns an answer whose `citations`
  open the right Version and chunk, and the chunks appear on `/events` before the 201.

## References

- Node: `apps/backend/src/chat/{answer-question,citations,retrieval,streaming,routes}.ts`.
- Reference: `BACKEND/reference-backend/src/chat/`; tests in `test/test_chat_pure.py` and
  `test/test_chat_route.py`.
