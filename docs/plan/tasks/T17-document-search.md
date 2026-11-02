# T17 — Keyword search: stub both routes (search itself dropped)

| Mode | Effort | Priority | Depends on | Unblocks | Learning value |
| --- | --- | --- | --- | --- | --- |
| Stub | 0.1 day | P2 | T04 | T19 | — |

## Why it is dropped

The full task (1.5 days) is Postgres full-text search end to end: `websearch_to_tsquery`, stored
`tsvector` columns, `ts_headline`, trigram similarity for typo correction. It is good SQL learning
and almost no Python learning, and nothing you keep depends on it. Thread search (T18) is a repeat
of it and is dropped with it.

## What you need to know

### 1. Query parameters

A function parameter that is not in the path becomes a query parameter. `Annotated[str, Query()]`
adds validation and a description; a default makes it optional.

```python
from typing import Annotated
from fastapi import Query


async def search(
    q: Annotated[str, Query(max_length=1000)] = "", exact: str = "false"
) -> dict: ...
```

### 2. Returning a plain dict

A route may return a dict instead of a DTO. With `response_model` set, FastAPI validates it
against the DTO; without, it is serialised as is. The empty shape of both search responses is the
same four keys, so one constant serves both routes.

```python
EMPTY_SEARCH = {"correctedQuery": None, "words": [], "total": 0, "results": []}
```

### 3. The 404 check

Every route nested under a Notebook asks `NotebookRepository.notebook_exists` first, so an unknown
or deleted Notebook answers 404 and not an empty result.

## What to build

1. **The two stub routes** in `src/search/search_router.py`:
   ```python
   router = APIRouter(tags=["search"])
   NotebookId = Annotated[uuid.UUID, Path(alias="notebookId")]
   EMPTY_SEARCH = {"correctedQuery": None, "words": [], "total": 0, "results": []}

   @router.get("/notebooks/{notebookId}/search")
   async def search_notebook(*, notebook_id: NotebookId, q: str = "", exact: str = "false",
                             _: CurrentUser, notebooks: NotebookRepository = Depends()) -> dict:
       if not await notebooks.notebook_exists(notebook_id):
           raise HTTPException(404, "Notebook not found.")
       return EMPTY_SEARCH

   @router.get("/notebooks/{notebookId}/search/threads")
   async def search_chat_threads(...) -> dict:   # same body
   ```
   Make sure the router is included in `app/main.py` (see `routers.py`).

   **DONE WHEN:** both routes print the empty result:

   ```sh
   curl -b cookies.txt "localhost:3000/notebooks/<nb>/search?q=hello"
   curl -b cookies.txt "localhost:3000/notebooks/<nb>/search/threads?q=hello"
   # both print: {"correctedQuery":null,"words":[],"total":0,"results":[]}
   ```

2. **Delete the unused entities** `src/search/citation_entity.py` and `src/search/keyword_entity.py`
   (see T02); keep `search_dto.py` only if something imports it.

   **DONE WHEN:** the search prints nothing:

   ```sh
   grep -rn "citation_entity\|keyword_entity" src
   ```

3. **One test** in `test/test_search_route.py`: sign in, create a Notebook, `GET .../search?q=x`
   is 200 with `total == 0`; an unknown Notebook id is 404.

   **DONE WHEN:** the test file is green:

   ```sh
   uv run pytest test/test_search_route.py -q
   ```

## If you pick it up later

`GET /notebooks/{nb}/search?q=&exact=` is full-text search over the Chunks of each Document's
latest `ready` Version, with typo correction against the Notebook's word list (NOTEBOOKS
`docs/search.md`). It needs no OpenRouter key.

1. DTOs: `TextSegment` (`text`, `match`), `SearchMatch` (`versionId`, `chunkId`, `charStart`, `charEnd`),
   `DocumentSearchResult` (`documentId`, `filename`, `title`, `headingPath`, `match`, `excerpt`).
2. `search/keywords.py`: `TEXT_SEARCH_CONFIG = "simple_unaccent"`, the private-use delimiters for
   `ts_headline`, `segments(headline)`, `excerpt(headline, source)`, `names_a_word(db, query)`.
3. `search/plain_text.py::plain_text(markdown)`: strip Markdown markers for the excerpt.
4. `search/correction.py`: `correct(db, notebook_id, query)` over `notebook_words` with `%` and
   `similarity() >= 0.4`; `searched_words(query)`.
5. `search/search_repository.py::search_chunks(notebook_id, query, typed)`: the `SEARCH_CHUNKS_SQL`
   over `searchable_versions`, ordered "matched as typed first, then rank", `COUNT(*) OVER ()`,
   limit 20; one `ts_headline` query over the plain texts; ranges from `chunk_ranges`.
6. Tests: seed a `ready` Version with one chunk and a `chunk_ranges` row; `etretat` finds
   `Étretat`; `famus` is corrected to `famous`; `exact=true` is not.

Reference: `BACKEND/reference-backend/src/search/` (the whole folder can be copied as is);
Node `apps/backend/src/search/`; `docs/search.md`.
