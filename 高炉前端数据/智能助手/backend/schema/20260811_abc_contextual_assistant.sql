-- REQ-ABC33-EXPLANATION-CONTEXT-20260811
-- Owner-only, additive and idempotent. Rollback disables the feature; do not
-- drop these immutable audit tables when rolling application code back.
BEGIN;

ALTER TABLE bf_assistant.qa_conversations
    ADD COLUMN IF NOT EXISTS owner_subject text;
ALTER TABLE bf_assistant.qa_conversations
    ADD COLUMN IF NOT EXISTS owner_role text;

CREATE UNIQUE INDEX IF NOT EXISTS uq_qa_shared_guest_room
    ON bf_assistant.qa_conversations(owner_subject)
    WHERE owner_role = 'anonymous_guest';

CREATE TABLE IF NOT EXISTS bf_assistant.qa_context_snapshots (
    id bigserial PRIMARY KEY,
    context_hash text NOT NULL UNIQUE,
    source_type text NOT NULL,
    source_id text NOT NULL,
    source_version text,
    context_json text NOT NULL,
    context_summary_json text NOT NULL,
    context_type text NOT NULL DEFAULT 'abc_rule_explanation',
    context_key text NOT NULL,
    schema_version text NOT NULL,
    furnace_id text NOT NULL DEFAULT 'GL02',
    source_ref_id text NOT NULL,
    evaluation_id bigint,
    source_ts text,
    payload_json text NOT NULL,
    payload_size_bytes bigint NOT NULL,
    created_at text NOT NULL
);
ALTER TABLE bf_assistant.qa_context_snapshots ADD COLUMN IF NOT EXISTS context_type text;
ALTER TABLE bf_assistant.qa_context_snapshots ADD COLUMN IF NOT EXISTS context_key text;
ALTER TABLE bf_assistant.qa_context_snapshots ADD COLUMN IF NOT EXISTS schema_version text;
ALTER TABLE bf_assistant.qa_context_snapshots ADD COLUMN IF NOT EXISTS furnace_id text;
ALTER TABLE bf_assistant.qa_context_snapshots ADD COLUMN IF NOT EXISTS source_ref_id text;
ALTER TABLE bf_assistant.qa_context_snapshots ADD COLUMN IF NOT EXISTS evaluation_id bigint;
ALTER TABLE bf_assistant.qa_context_snapshots ADD COLUMN IF NOT EXISTS source_ts text;
ALTER TABLE bf_assistant.qa_context_snapshots ADD COLUMN IF NOT EXISTS payload_json text;
ALTER TABLE bf_assistant.qa_context_snapshots ADD COLUMN IF NOT EXISTS payload_size_bytes bigint;
UPDATE bf_assistant.qa_context_snapshots SET
    context_type = COALESCE(context_type, 'abc_rule_explanation'),
    context_key = COALESCE(context_key, source_type || ':' || source_id),
    schema_version = COALESCE(schema_version, source_version, 'legacy'),
    furnace_id = COALESCE(furnace_id, 'GL02'),
    source_ref_id = COALESCE(source_ref_id, source_id),
    payload_json = COALESCE(payload_json, context_json, '{}'),
    payload_size_bytes = COALESCE(payload_size_bytes, octet_length(COALESCE(payload_json, context_json, '{}')));
ALTER TABLE bf_assistant.qa_context_snapshots ALTER COLUMN context_type SET DEFAULT 'abc_rule_explanation';
ALTER TABLE bf_assistant.qa_context_snapshots ALTER COLUMN furnace_id SET DEFAULT 'GL02';
ALTER TABLE bf_assistant.qa_context_snapshots ALTER COLUMN context_type SET NOT NULL;
ALTER TABLE bf_assistant.qa_context_snapshots ALTER COLUMN context_key SET NOT NULL;
ALTER TABLE bf_assistant.qa_context_snapshots ALTER COLUMN schema_version SET NOT NULL;
ALTER TABLE bf_assistant.qa_context_snapshots ALTER COLUMN furnace_id SET NOT NULL;
ALTER TABLE bf_assistant.qa_context_snapshots ALTER COLUMN source_ref_id SET NOT NULL;
ALTER TABLE bf_assistant.qa_context_snapshots ALTER COLUMN payload_json SET NOT NULL;
ALTER TABLE bf_assistant.qa_context_snapshots ALTER COLUMN payload_size_bytes SET NOT NULL;
CREATE UNIQUE INDEX IF NOT EXISTS uq_qa_context_snapshots_context_hash
    ON bf_assistant.qa_context_snapshots(context_hash);

CREATE TABLE IF NOT EXISTS bf_assistant.qa_conversation_origins (
    conversation_id text PRIMARY KEY REFERENCES bf_assistant.qa_conversations(id) ON DELETE CASCADE,
    source_type text NOT NULL,
    source_id text NOT NULL,
    evaluation_id bigint,
    context_snapshot_id bigint NOT NULL REFERENCES bf_assistant.qa_context_snapshots(id),
    reuse_policy text NOT NULL DEFAULT 'same_rule_active',
    source_page text,
    source_ref_id text NOT NULL,
    source_title text,
    initial_evaluation_id bigint,
    initial_context_snapshot_id bigint REFERENCES bf_assistant.qa_context_snapshots(id),
    return_route text,
    operator_id text,
    shift_key text,
    created_at text NOT NULL,
    updated_at text NOT NULL
);
ALTER TABLE bf_assistant.qa_conversation_origins
    ADD COLUMN IF NOT EXISTS operator_id text;
ALTER TABLE bf_assistant.qa_conversation_origins
    ADD COLUMN IF NOT EXISTS shift_key text;
ALTER TABLE bf_assistant.qa_conversation_origins ADD COLUMN IF NOT EXISTS source_page text;
ALTER TABLE bf_assistant.qa_conversation_origins ADD COLUMN IF NOT EXISTS source_ref_id text;
ALTER TABLE bf_assistant.qa_conversation_origins ADD COLUMN IF NOT EXISTS source_title text;
ALTER TABLE bf_assistant.qa_conversation_origins ADD COLUMN IF NOT EXISTS initial_evaluation_id bigint;
ALTER TABLE bf_assistant.qa_conversation_origins ADD COLUMN IF NOT EXISTS initial_context_snapshot_id bigint;
ALTER TABLE bf_assistant.qa_conversation_origins ADD COLUMN IF NOT EXISTS return_route text;
UPDATE bf_assistant.qa_conversation_origins SET
    source_ref_id = COALESCE(source_ref_id, source_id),
    initial_evaluation_id = COALESCE(initial_evaluation_id, evaluation_id),
    initial_context_snapshot_id = COALESCE(initial_context_snapshot_id, context_snapshot_id);
ALTER TABLE bf_assistant.qa_conversation_origins ALTER COLUMN source_ref_id SET NOT NULL;

CREATE TABLE IF NOT EXISTS bf_assistant.qa_message_context_snapshots (
    id bigserial PRIMARY KEY,
    conversation_id text NOT NULL REFERENCES bf_assistant.qa_conversations(id) ON DELETE CASCADE,
    message_id bigint REFERENCES bf_assistant.qa_messages(id) ON DELETE CASCADE,
    context_snapshot_id bigint NOT NULL REFERENCES bf_assistant.qa_context_snapshots(id),
    usage_kind text NOT NULL DEFAULT 'assistant_prompt',
    created_at text NOT NULL,
    UNIQUE(message_id, context_snapshot_id, usage_kind)
);
ALTER TABLE bf_assistant.qa_message_context_snapshots ADD COLUMN IF NOT EXISTS usage_kind text;
UPDATE bf_assistant.qa_message_context_snapshots
    SET usage_kind = COALESCE(usage_kind, 'assistant_prompt');
ALTER TABLE bf_assistant.qa_message_context_snapshots ALTER COLUMN usage_kind SET DEFAULT 'assistant_prompt';
ALTER TABLE bf_assistant.qa_message_context_snapshots ALTER COLUMN usage_kind SET NOT NULL;
CREATE UNIQUE INDEX IF NOT EXISTS uq_qa_message_context_snapshots_usage
    ON bf_assistant.qa_message_context_snapshots(message_id, context_snapshot_id, usage_kind);

CREATE TABLE IF NOT EXISTS bf_assistant.abc_rule_ai_explanations (
    id bigserial PRIMARY KEY,
    context_snapshot_id bigint NOT NULL REFERENCES bf_assistant.qa_context_snapshots(id),
    rule_id text NOT NULL,
    evaluation_id bigint NOT NULL,
    context_hash text NOT NULL,
    operator_explanation_json text NOT NULL,
    assistant_context_json text NOT NULL,
    analysis_text text,
    analysis_json text,
    prompt_version text NOT NULL DEFAULT 'abc_rule_explanation.v1',
    model_name text NOT NULL DEFAULT '',
    state text NOT NULL DEFAULT 'context_ready',
    generation_state text NOT NULL DEFAULT 'context_ready',
    attempt_count bigint NOT NULL DEFAULT 0,
    last_error_code text,
    generation_started_at text,
    generation_completed_at text,
    claim_token text,
    lease_expires_at text,
    created_at text NOT NULL,
    updated_at text NOT NULL,
    UNIQUE(context_snapshot_id, prompt_version, model_name)
);
ALTER TABLE bf_assistant.abc_rule_ai_explanations ADD COLUMN IF NOT EXISTS analysis_json text;
ALTER TABLE bf_assistant.abc_rule_ai_explanations ADD COLUMN IF NOT EXISTS prompt_version text;
ALTER TABLE bf_assistant.abc_rule_ai_explanations ADD COLUMN IF NOT EXISTS model_name text;
ALTER TABLE bf_assistant.abc_rule_ai_explanations ADD COLUMN IF NOT EXISTS state text;
ALTER TABLE bf_assistant.abc_rule_ai_explanations ADD COLUMN IF NOT EXISTS generation_state text;
ALTER TABLE bf_assistant.abc_rule_ai_explanations ADD COLUMN IF NOT EXISTS attempt_count bigint;
ALTER TABLE bf_assistant.abc_rule_ai_explanations ADD COLUMN IF NOT EXISTS last_error_code text;
ALTER TABLE bf_assistant.abc_rule_ai_explanations ADD COLUMN IF NOT EXISTS generation_started_at text;
ALTER TABLE bf_assistant.abc_rule_ai_explanations ADD COLUMN IF NOT EXISTS generation_completed_at text;
ALTER TABLE bf_assistant.abc_rule_ai_explanations ADD COLUMN IF NOT EXISTS claim_token text;
ALTER TABLE bf_assistant.abc_rule_ai_explanations ADD COLUMN IF NOT EXISTS lease_expires_at text;
UPDATE bf_assistant.abc_rule_ai_explanations SET
    prompt_version = COALESCE(prompt_version, 'abc_rule_explanation.v1'),
    model_name = COALESCE(model_name, ''),
    state = COALESCE(state, 'context_ready'),
    generation_state = COALESCE(generation_state, state, 'context_ready'),
    attempt_count = COALESCE(attempt_count, 0);
ALTER TABLE bf_assistant.abc_rule_ai_explanations ALTER COLUMN prompt_version SET DEFAULT 'abc_rule_explanation.v1';
ALTER TABLE bf_assistant.abc_rule_ai_explanations ALTER COLUMN model_name SET DEFAULT '';
ALTER TABLE bf_assistant.abc_rule_ai_explanations ALTER COLUMN state SET DEFAULT 'context_ready';
ALTER TABLE bf_assistant.abc_rule_ai_explanations ALTER COLUMN generation_state SET DEFAULT 'context_ready';
ALTER TABLE bf_assistant.abc_rule_ai_explanations ALTER COLUMN attempt_count SET DEFAULT 0;
ALTER TABLE bf_assistant.abc_rule_ai_explanations ALTER COLUMN prompt_version SET NOT NULL;
ALTER TABLE bf_assistant.abc_rule_ai_explanations ALTER COLUMN model_name SET NOT NULL;
ALTER TABLE bf_assistant.abc_rule_ai_explanations ALTER COLUMN state SET NOT NULL;
ALTER TABLE bf_assistant.abc_rule_ai_explanations ALTER COLUMN generation_state SET NOT NULL;
ALTER TABLE bf_assistant.abc_rule_ai_explanations ALTER COLUMN attempt_count SET NOT NULL;
CREATE UNIQUE INDEX IF NOT EXISTS uq_abc_rule_ai_explanations_cache
    ON bf_assistant.abc_rule_ai_explanations(context_snapshot_id, prompt_version, model_name);

CREATE INDEX IF NOT EXISTS idx_qa_context_snapshots_source
    ON bf_assistant.qa_context_snapshots(source_type, source_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_qa_context_snapshots_evaluation
    ON bf_assistant.qa_context_snapshots(evaluation_id);
CREATE INDEX IF NOT EXISTS idx_qa_conversation_origins_lookup
    ON bf_assistant.qa_conversation_origins(source_type, source_id, evaluation_id, updated_at DESC);
CREATE INDEX IF NOT EXISTS idx_qa_conversation_origins_reuse
    ON bf_assistant.qa_conversation_origins(source_type, source_id, operator_id, shift_key, updated_at DESC);
CREATE INDEX IF NOT EXISTS idx_qa_message_context_snapshots_conversation
    ON bf_assistant.qa_message_context_snapshots(conversation_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_abc_rule_ai_explanations_lookup
    ON bf_assistant.abc_rule_ai_explanations(rule_id, evaluation_id, updated_at DESC);

COMMIT;
