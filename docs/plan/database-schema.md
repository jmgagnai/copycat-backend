# Database schema

The application's Postgres schema as of migration `0020`, derived from
`apps/backend/src/db/migrations/`. There are no views. Not shown:
`schema_migrations` (the migration runner's bookkeeping, `src/db/migrate.ts`)
and the `pgboss` schema, which pg-boss owns and migrates itself.

```mermaid
erDiagram
    users {
        uuid id PK
        text email UK
        text password_hash
        timestamptz created_at
    }

    notebooks {
        uuid id PK
        text title
        timestamptz created_at
        timestamptz deleted_at "soft delete"
    }

    documents {
        uuid id PK
        uuid notebook_id FK
        text filename "unique per notebook while undeleted"
        timestamptz created_at
        timestamptz deleted_at "soft delete"
    }

    document_versions {
        uuid id PK
        uuid document_id FK "UK with version_number"
        int version_number
        text mime_type
        bigint size_bytes
        text storage_key
        text ingestion_status "queued..ready | failed"
        text markdown "Converted Markdown"
        text ingestion_error "operator-only"
        text failure_reason "user-facing, only when failed"
        text failed_at "stage it failed in"
        jsonb metadata
        text chat_snippet
        text executive_summary
        text abstract
        jsonb section_summaries "stage 2 work-in-progress"
        jsonb artifact_warnings
        timestamptz converted_at
        timestamptz summarized_at
        timestamptz embedded_at
        timestamptz chunk_ranges_located_at
        timestamptz created_at
        timestamptz deleted_at "soft delete (dormant)"
    }

    chunks {
        uuid id PK
        uuid document_version_id FK "UK with chunk_index"
        int chunk_index
        text_array heading_path
        text text
        vector embedding "vector(2560)"
        tsvector search_vector "generated, simple_unaccent"
        timestamptz created_at
    }

    chunk_ranges {
        uuid chunk_id PK, FK
        int char_start
        int char_end
    }

    chat_threads {
        uuid id PK
        uuid notebook_id FK
        uuid created_by FK "author, attribution only"
        text title
        timestamptz created_at
        timestamptz deleted_at "soft delete"
    }

    chat_messages {
        uuid id PK
        uuid chat_thread_id FK
        uuid asked_by FK
        text role "user | assistant"
        text content
        bigserial seq "message order"
        tsvector search_vector "generated, simple_unaccent"
        timestamptz created_at
    }

    citations {
        uuid id PK
        uuid chat_message_id FK "UK with marker"
        uuid document_version_id FK "pinned, never re-derived"
        uuid chunk_id FK
        int marker "[n] in the answer, > 0"
        int char_start "nullable"
        int char_end "nullable"
        timestamptz created_at
    }

    notebook_words {
        uuid notebook_id FK
        text word "trigger-maintained, no unique key"
    }

    notebooks ||--o{ documents : "contains"
    documents ||--|{ document_versions : "versioned as"
    document_versions ||--o{ chunks : "split into (cascade)"
    chunks ||--o| chunk_ranges : "located at (cascade)"
    notebooks ||--o{ chat_threads : "has (cascade)"
    users ||--o{ chat_threads : "created_by"
    chat_threads ||--o{ chat_messages : "contains (cascade)"
    users ||--o{ chat_messages : "asked_by"
    chat_messages ||--o{ citations : "cites (cascade)"
    document_versions ||--o{ citations : "cited by (restrict)"
    chunks ||--o{ citations : "cited by (restrict)"
    notebooks ||--o{ notebook_words : "vocabulary (cascade)"
```

## Notes the diagram can't carry

- **Triggers.** `AFTER INSERT` on `chunks` and on `chat_messages` adds the
  row's lexemes to `notebook_words` (`notebook_words_from_chunk`,
  `notebook_words_from_message` → `add_notebook_words`, filtered by
  `is_notebook_word`).
- **No ANN index on `chunks.embedding`.** Similarity search is an exact scan
  (ADR-0005).
- **Partial indexes on live rows.** `notebooks`, `documents`,
  `document_versions` and `chat_threads` index only `deleted_at IS NULL`.
- **Extensions.** `vector`, `unaccent`, `pg_trgm`, `btree_gin`, plus the
  `simple_unaccent` text search configuration.
