CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS pg_trgm;

CREATE TABLE IF NOT EXISTS knowledge_chunk (
    id BIGSERIAL PRIMARY KEY,
    chunk_uid TEXT NOT NULL UNIQUE,
    tenant_id BIGINT NOT NULL DEFAULT 1,
    project_id BIGINT NULL,
    knowledge_base_id BIGINT NULL,
    knowledge_document_id BIGINT NULL,
    file_id BIGINT NOT NULL,
    doc_type TEXT NOT NULL,
    source_type TEXT NULL,
    source_title TEXT NULL,
    section_path TEXT NULL,
    page_start INT NULL,
    page_end INT NULL,
    chunk_index INT NOT NULL DEFAULT 0,
    chunk_text TEXT NOT NULL,
    metadata_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    embedding_model TEXT NULL,
    embedding vector(1024) NULL,
    search_vector tsvector GENERATED ALWAYS AS (
        setweight(to_tsvector('simple', coalesce(source_title, '')), 'A') ||
        setweight(to_tsvector('simple', coalesce(section_path, '')), 'B') ||
        setweight(to_tsvector('simple', coalesce(chunk_text, '')), 'C')
    ) STORED,
    status TEXT NOT NULL DEFAULT 'indexed',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_knowledge_chunk_tenant_doc_type
    ON knowledge_chunk (tenant_id, doc_type, status);

CREATE INDEX IF NOT EXISTS idx_knowledge_chunk_project
    ON knowledge_chunk (project_id, status);

CREATE INDEX IF NOT EXISTS idx_knowledge_chunk_kb
    ON knowledge_chunk (knowledge_base_id, status);

CREATE INDEX IF NOT EXISTS idx_knowledge_chunk_search_vector
    ON knowledge_chunk USING GIN (search_vector);

CREATE INDEX IF NOT EXISTS idx_knowledge_chunk_text_trgm
    ON knowledge_chunk USING GIN (chunk_text gin_trgm_ops);

CREATE INDEX IF NOT EXISTS idx_knowledge_chunk_embedding
    ON knowledge_chunk USING ivfflat (embedding vector_cosine_ops)
    WITH (lists = 100);

CREATE TABLE IF NOT EXISTS rag_retrieval_log (
    id BIGSERIAL PRIMARY KEY,
    tenant_id BIGINT NOT NULL DEFAULT 1,
    project_id BIGINT NULL,
    chapter_id BIGINT NULL,
    query_text TEXT NOT NULL,
    backend TEXT NOT NULL,
    keyword_count INT NOT NULL DEFAULT 0,
    vector_count INT NOT NULL DEFAULT 0,
    merged_count INT NOT NULL DEFAULT 0,
    returned_count INT NOT NULL DEFAULT 0,
    rerank_model TEXT NULL,
    source_mix_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    score_trace_json JSONB NOT NULL DEFAULT '[]'::jsonb,
    degraded BOOLEAN NOT NULL DEFAULT false,
    degraded_reason TEXT NULL,
    fallback_used BOOLEAN NOT NULL DEFAULT false,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_rag_retrieval_log_project
    ON rag_retrieval_log (project_id, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_rag_retrieval_log_chapter
    ON rag_retrieval_log (chapter_id, created_at DESC);
