-- REQ-QA-KEYWORD-SOURCE-RELEASE-20260917. Candidate only; requires explicit DB authorization.
-- Keep archived source, vectors and prior binding inside the controlled database.
BEGIN;
CREATE TABLE IF NOT EXISTS bf_assistant.qa_knowledge_source_releases (
    release_id text PRIMARY KEY,
    doc_id text NOT NULL REFERENCES bf_assistant.rag_document(doc_id),
    state text NOT NULL CHECK (state IN ('applied', 'rolled_back')),
    before_snapshot_json jsonb NOT NULL,
    before_snapshot_sha256 text NOT NULL CHECK (before_snapshot_sha256 ~ '^[0-9a-f]{64}$'),
    after_snapshot_sha256 text NOT NULL CHECK (after_snapshot_sha256 ~ '^[0-9a-f]{64}$'),
    manifest_sha256 text NOT NULL CHECK (manifest_sha256 ~ '^[0-9a-f]{64}$'),
    plan_sha256 text NOT NULL CHECK (plan_sha256 ~ '^[0-9a-f]{64}$'),
    applied_at timestamptz NOT NULL,
    rolled_back_at timestamptz
);
CREATE TABLE IF NOT EXISTS bf_assistant.qa_knowledge_source_bindings (
    doc_id text PRIMARY KEY REFERENCES bf_assistant.rag_document(doc_id),
    release_id text NOT NULL REFERENCES bf_assistant.qa_knowledge_source_releases(release_id),
    authority_sha256 text NOT NULL CHECK (authority_sha256 ~ '^[0-9a-f]{64}$'),
    manifest_sha256 text NOT NULL CHECK (manifest_sha256 ~ '^[0-9a-f]{64}$'),
    manifest_text text NOT NULL
);
COMMIT;
