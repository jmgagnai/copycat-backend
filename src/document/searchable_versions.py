SEARCHABLE_VERSIONS_CTE = """
  searchable_versions AS (
    SELECT
      d.id AS document_id, d.notebook_id, d.filename, d.created_at AS document_created_at,
      v.id AS version_id, v.version_number, v.mime_type, v.size_bytes,
      v.created_at AS version_created_at, v.ingestion_status, v.abstract, v.chat_snippet
    FROM documents d
    JOIN LATERAL (
      SELECT id, version_number, mime_type, size_bytes, created_at, ingestion_status, abstract, chat_snippet
      FROM document_versions
      WHERE document_id = d.id AND deleted_at IS NULL
      ORDER BY version_number DESC
      LIMIT 1
    ) v ON true
    WHERE d.notebook_id = CAST(:notebook_id AS uuid)
      AND d.deleted_at IS NULL
      AND v.ingestion_status = 'ready'
  )
"""
