# Lessons learnt

* use `uv` package manager and `ruff`, `pyright` checkers
* `async` code by default, strong typing with `pydantic`
* define `FastAPI` routing, `SSE` streaming endpoints and use powerful DI for session management
* Modern `SqlAlchemy` entity mapping, generate events with `pg_notify`
* Use postgreSQL tables to manage job queues and make them restartable (`procrastinate`)
* Simple tests with `pytest`, with minimal mocking
* use of `Docling` and opensource LLMs (`qwen`/`mistral`), validating them as viable solutions
* _Don't do it:_ `RAG` implementation is tedious without the `langchain` package

<br>

---

### What next ?

* more advanced architecture (ex: domain driven design, test driven design, ..) ; use abstract classes
* more advanced testing: pure (more simple) unit tests, validation with test containers
* database migrations with `Alembic`
* simplify the RAG code with `langchain`, add hybrid search, reranking, question rewriting, observability with `langfuse` or `phoenix`
* remove scaling limitations (document size, number of documents, number of users)
