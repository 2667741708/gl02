-- Synthetic tables for an isolated disposable local PostgreSQL cluster only.
CREATE SCHEMA bf_assistant;
CREATE EXTENSION IF NOT EXISTS vector;
CREATE TABLE bf_assistant.rag_document (
    doc_id text PRIMARY KEY, title text NOT NULL, source_file text NOT NULL,
    knowledge_category text NOT NULL, task_scope_json text NOT NULL, version text NOT NULL,
    authority_level text NOT NULL, full_text text NOT NULL, content_hash text NOT NULL,
    created_at text NOT NULL, updated_at text NOT NULL
);
CREATE TABLE bf_assistant.rag_chunk (
    chunk_id text PRIMARY KEY, doc_id text NOT NULL REFERENCES bf_assistant.rag_document(doc_id) ON DELETE CASCADE,
    parent_chunk_id text, title text NOT NULL, content text NOT NULL, enriched_content text NOT NULL,
    summary text, keywords_json text NOT NULL, entities_json text NOT NULL, phenomenon_json text NOT NULL,
    parameter_names_json text NOT NULL, chunk_type text NOT NULL, token_count integer NOT NULL,
    source_file text NOT NULL, knowledge_category text NOT NULL, task_scope_json text NOT NULL,
    authority_level text NOT NULL, source_priority integer NOT NULL, content_hash text NOT NULL,
    created_at text NOT NULL, search_text text
);
CREATE TABLE bf_assistant.rag_chunk_embedding (
    chunk_id text PRIMARY KEY REFERENCES bf_assistant.rag_chunk(chunk_id) ON DELETE CASCADE,
    embedding_model text NOT NULL, embedding vector NOT NULL, embedding_dimension integer NOT NULL,
    embedding_text_hash text NOT NULL, updated_at text NOT NULL
);
