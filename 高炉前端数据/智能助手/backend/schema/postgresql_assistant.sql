-- 智能助手 PostgreSQL schema 初始化脚本
-- 运行方式：由数据库 owner / 管理员在 bf_trend 库中执行。
-- 默认 schema 为 bf_assistant；如需改名，请同步设置 BF_ASSISTANT_PG_SCHEMA。
-- 如果应用账号不是执行本脚本的账号，请按现场账号替换并执行末尾 GRANT 示例。

CREATE SCHEMA IF NOT EXISTS bf_assistant;
SET search_path TO bf_assistant, bf_sensor, public;

CREATE TABLE IF NOT EXISTS bf_assistant.furnace_snapshots (
    id bigserial PRIMARY KEY,
    source_time text NOT NULL,
    created_at text NOT NULL,
    values_json text NOT NULL,
    diagnosis_json text NOT NULL,
    recommendation_json text NOT NULL,
    data_quality_json text NOT NULL,
    payload_json text NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_furnace_snapshots_created
    ON bf_assistant.furnace_snapshots(created_at DESC);

CREATE TABLE IF NOT EXISTS bf_assistant.qa_conversations (
    id text PRIMARY KEY,
    title text NOT NULL,
    created_at text NOT NULL,
    updated_at text NOT NULL,
    last_user_at text,
    project_id bigint,
    status text NOT NULL DEFAULT 'active',
    is_pinned integer NOT NULL DEFAULT 0,
    is_unread integer NOT NULL DEFAULT 0,
    archived_at text
);
CREATE INDEX IF NOT EXISTS idx_qa_conversations_updated
    ON bf_assistant.qa_conversations(updated_at DESC);

CREATE TABLE IF NOT EXISTS bf_assistant.qa_messages (
    id bigserial PRIMARY KEY,
    conversation_id text NOT NULL REFERENCES bf_assistant.qa_conversations(id) ON DELETE CASCADE,
    role text NOT NULL,
    content text NOT NULL,
    created_at text NOT NULL,
    snapshot_id bigint,
    hidden_context_json text
);
CREATE INDEX IF NOT EXISTS idx_qa_messages_conversation
    ON bf_assistant.qa_messages(conversation_id, id);

CREATE TABLE IF NOT EXISTS bf_assistant.period_reports (
    id bigserial PRIMARY KEY,
    furnace_id text NOT NULL DEFAULT 'GL02',
    period_kind text NOT NULL CHECK (period_kind IN ('hourly', 'daily', 'weekly', 'monthly')),
    period_start text NOT NULL,
    period_end text NOT NULL,
    timezone text NOT NULL DEFAULT 'Asia/Shanghai',
    title text NOT NULL,
    report_markdown text NOT NULL,
    markdown_path text,
    docx_path text,
    metrics_json text,
    diagnosis_json text,
    recommendation_json text,
    sensor_refs_json text,
    source_snapshot_min_id bigint,
    source_snapshot_max_id bigint,
    created_at text NOT NULL,
    updated_at text NOT NULL,
    UNIQUE (furnace_id, period_kind, period_start, period_end)
);
CREATE INDEX IF NOT EXISTS idx_period_reports_range
    ON bf_assistant.period_reports(furnace_id, period_kind, period_start, period_end);

CREATE TABLE IF NOT EXISTS bf_assistant.report_template (
    id bigserial PRIMARY KEY,
    code text NOT NULL UNIQUE,
    name text NOT NULL,
    report_type text NOT NULL CHECK (report_type IN ('hourly', 'daily', 'weekly', 'monthly')),
    description text,
    template_schema text,
    render_type text NOT NULL DEFAULT 'json_card',
    enabled integer NOT NULL DEFAULT 1,
    created_at text NOT NULL,
    updated_at text NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_report_template_type
    ON bf_assistant.report_template(report_type, enabled, updated_at);

CREATE TABLE IF NOT EXISTS bf_assistant.report_instance (
    id bigserial PRIMARY KEY,
    template_id bigint NOT NULL REFERENCES bf_assistant.report_template(id),
    period_report_id bigint,
    furnace_id text NOT NULL DEFAULT 'GL02',
    report_type text NOT NULL CHECK (report_type IN ('hourly', 'daily', 'weekly', 'monthly')),
    time_start text NOT NULL,
    time_end text NOT NULL,
    title text NOT NULL,
    summary text,
    content_json text,
    content_markdown text NOT NULL,
    preview_html text,
    markdown_path text,
    docx_path text,
    created_by text,
    created_at text NOT NULL,
    updated_at text NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_report_instance_range
    ON bf_assistant.report_instance(furnace_id, report_type, time_start, time_end, id);

CREATE TABLE IF NOT EXISTS bf_assistant.qa_projects (
    id bigserial PRIMARY KEY,
    furnace_id text NOT NULL DEFAULT 'GL02',
    name text NOT NULL,
    folder_path text NOT NULL,
    description text,
    created_by text,
    status text NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'archived')),
    is_pinned integer NOT NULL DEFAULT 0,
    archived_at text,
    created_at text NOT NULL,
    updated_at text NOT NULL,
    UNIQUE (furnace_id, folder_path)
);
CREATE INDEX IF NOT EXISTS idx_qa_projects_status
    ON bf_assistant.qa_projects(furnace_id, status, updated_at);

CREATE TABLE IF NOT EXISTS bf_assistant.project_assets (
    id bigserial PRIMARY KEY,
    project_id bigint NOT NULL REFERENCES bf_assistant.qa_projects(id) ON DELETE CASCADE,
    asset_type text NOT NULL CHECK (asset_type IN ('period_report', 'markdown_file', 'docx_file', 'folder', 'txt_file', 'pdf_file', 'spreadsheet_file', 'csv_file', 'other')),
    asset_ref_id text NOT NULL DEFAULT '',
    file_path text NOT NULL DEFAULT '',
    display_name text NOT NULL,
    default_include_mode text NOT NULL DEFAULT 'summary' CHECK (default_include_mode IN ('summary', 'full_text', 'selected_sections', 'citation_only')),
    created_at text NOT NULL,
    updated_at text NOT NULL,
    UNIQUE(project_id, asset_type, asset_ref_id, file_path)
);
CREATE INDEX IF NOT EXISTS idx_project_assets_project
    ON bf_assistant.project_assets(project_id, asset_type, updated_at);

CREATE TABLE IF NOT EXISTS bf_assistant.qa_message_context_refs (
    id bigserial PRIMARY KEY,
    conversation_id text,
    message_id bigint,
    project_id bigint,
    ref_type text NOT NULL CHECK (ref_type IN ('period_report', 'project_asset', 'project_file', 'manual_text')),
    ref_id text,
    insert_mode text NOT NULL CHECK (insert_mode IN ('summary', 'full_text', 'selected_sections', 'citation_only', 'manual_edited')),
    inserted_title text,
    inserted_text text,
    source_path text,
    created_at text NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_qa_message_context_refs_message
    ON bf_assistant.qa_message_context_refs(conversation_id, message_id, ref_type);

CREATE TABLE IF NOT EXISTS bf_assistant.rag_document (
    doc_id text PRIMARY KEY,
    title text NOT NULL,
    source_file text NOT NULL,
    knowledge_category text NOT NULL,
    task_scope_json text NOT NULL,
    version text NOT NULL DEFAULT 'v1.0',
    authority_level text NOT NULL DEFAULT 'knowledge_doc',
    full_text text NOT NULL,
    content_hash text NOT NULL,
    created_at text NOT NULL,
    updated_at text NOT NULL
);

CREATE TABLE IF NOT EXISTS bf_assistant.rag_chunk (
    chunk_id text PRIMARY KEY,
    doc_id text NOT NULL REFERENCES bf_assistant.rag_document(doc_id) ON DELETE CASCADE,
    parent_chunk_id text,
    title text NOT NULL,
    content text NOT NULL,
    enriched_content text NOT NULL,
    summary text,
    keywords_json text NOT NULL,
    entities_json text NOT NULL,
    phenomenon_json text NOT NULL,
    parameter_names_json text NOT NULL,
    chunk_type text NOT NULL,
    token_count integer NOT NULL,
    source_file text NOT NULL,
    knowledge_category text NOT NULL,
    task_scope_json text NOT NULL,
    authority_level text NOT NULL,
    source_priority integer NOT NULL DEFAULT 50,
    content_hash text NOT NULL,
    created_at text NOT NULL,
    search_text text GENERATED ALWAYS AS (
        coalesce(title, '') || ' ' || coalesce(enriched_content, '')
    ) STORED
);
CREATE INDEX IF NOT EXISTS idx_rag_chunk_doc
    ON bf_assistant.rag_chunk(doc_id);
CREATE INDEX IF NOT EXISTS idx_rag_chunk_category
    ON bf_assistant.rag_chunk(knowledge_category, source_priority DESC);

-- 可选 pgvector 语义检索索引。
-- 如果当前数据库账号没有 CREATE EXTENSION 权限，请先由库 owner 执行：
--   CREATE EXTENSION IF NOT EXISTS vector;
-- 然后再执行下方建表语句。8092 运行期也会尝试自动创建该表；
-- pgvector 不可用时会自动回退到 PostgreSQL rag_chunk + TF-IDF/关键词检索。
CREATE EXTENSION IF NOT EXISTS vector;
CREATE TABLE IF NOT EXISTS bf_assistant.rag_chunk_embedding (
    chunk_id text PRIMARY KEY REFERENCES bf_assistant.rag_chunk(chunk_id) ON DELETE CASCADE,
    embedding_model text NOT NULL,
    embedding vector NOT NULL,
    embedding_dimension integer NOT NULL,
    embedding_text_hash text NOT NULL,
    updated_at text NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_rag_chunk_embedding_model
    ON bf_assistant.rag_chunk_embedding(embedding_model);
-- PostgreSQL 安装的 pgvector 版本支持 HNSW 时建议启用：
-- CREATE INDEX IF NOT EXISTS idx_rag_chunk_embedding_hnsw
--     ON bf_assistant.rag_chunk_embedding
--     USING hnsw (embedding vector_cosine_ops);

CREATE TABLE IF NOT EXISTS bf_assistant.rag_query_log (
    query_id text PRIMARY KEY,
    user_query text NOT NULL,
    intent_type text NOT NULL,
    retrieved_chunk_ids_json text NOT NULL,
    created_at text NOT NULL
);

-- 如应用账号不是 schema owner，请替换 app_user 后执行：
-- GRANT USAGE ON SCHEMA bf_assistant TO app_user;
-- GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA bf_assistant TO app_user;
-- GRANT USAGE, SELECT, UPDATE ON ALL SEQUENCES IN SCHEMA bf_assistant TO app_user;
-- ALTER DEFAULT PRIVILEGES IN SCHEMA bf_assistant GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO app_user;
-- ALTER DEFAULT PRIVILEGES IN SCHEMA bf_assistant GRANT USAGE, SELECT, UPDATE ON SEQUENCES TO app_user;
