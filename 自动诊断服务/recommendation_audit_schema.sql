-- REQ-RECOMMENDATION-FULL-AUDIT-20260806
-- Full-fidelity, append-only recommendation decision audit schema.

CREATE SCHEMA IF NOT EXISTS bf_assistant;

CREATE TABLE IF NOT EXISTS bf_assistant.recommendation_audit_schema_versions (
    version text PRIMARY KEY,
    description text NOT NULL,
    installed_at timestamptz NOT NULL DEFAULT clock_timestamp()
);

CREATE TABLE IF NOT EXISTS bf_assistant.recommendation_audit_batches (
    id bigserial PRIMARY KEY,
    audit_schema_version text NOT NULL,
    idempotency_key text NOT NULL UNIQUE CHECK (idempotency_key ~ '^[0-9A-F]{64}$'),
    furnace_id text NOT NULL DEFAULT 'GL02',
    diagnosis_snapshot_id bigint,
    diagnosis_ts timestamptz NOT NULL,
    diagnosis_main_label text NOT NULL,
    diagnosis_secondary_label text,
    diagnosis_scores jsonb NOT NULL DEFAULT '{}'::jsonb CHECK (jsonb_typeof(diagnosis_scores) = 'object'),
    diagnosis_payload jsonb NOT NULL CHECK (jsonb_typeof(diagnosis_payload) = 'object'),
    current_values jsonb NOT NULL DEFAULT '{}'::jsonb CHECK (jsonb_typeof(current_values) = 'object'),
    data_quality jsonb NOT NULL DEFAULT '{}'::jsonb CHECK (jsonb_typeof(data_quality) = 'object'),
    source_context jsonb NOT NULL DEFAULT '{}'::jsonb CHECK (jsonb_typeof(source_context) = 'object'),
    input_payload_sha256 text NOT NULL CHECK (input_payload_sha256 ~ '^[0-9A-F]{64}$'),
    recommendation_payload_sha256 text NOT NULL CHECK (recommendation_payload_sha256 ~ '^[0-9A-F]{64}$'),
    engine_name text NOT NULL,
    engine_version text NOT NULL,
    recommendation_schema_version text NOT NULL,
    policy_source text NOT NULL,
    policy_sha256 text NOT NULL CHECK (policy_sha256 ~ '^[0-9A-F]{64}$'),
    condition_count smallint NOT NULL CHECK (condition_count = 8),
    action_count integer NOT NULL CHECK (action_count > 0),
    status_counts jsonb NOT NULL CHECK (jsonb_typeof(status_counts) = 'object'),
    recommendation_bundle jsonb NOT NULL CHECK (jsonb_typeof(recommendation_bundle) = 'object'),
    write_source text NOT NULL,
    read_only boolean NOT NULL DEFAULT true CHECK (read_only),
    created_at timestamptz NOT NULL DEFAULT clock_timestamp()
);

CREATE INDEX IF NOT EXISTS idx_recommendation_audit_batches_diagnosis
    ON bf_assistant.recommendation_audit_batches (diagnosis_ts DESC, id DESC);
CREATE INDEX IF NOT EXISTS idx_recommendation_audit_batches_engine
    ON bf_assistant.recommendation_audit_batches (engine_version, policy_sha256, diagnosis_ts DESC);
CREATE INDEX IF NOT EXISTS idx_recommendation_audit_batches_snapshot
    ON bf_assistant.recommendation_audit_batches (diagnosis_snapshot_id, engine_version, policy_sha256);

CREATE TABLE IF NOT EXISTS bf_assistant.recommendation_audit_actions (
    id bigserial PRIMARY KEY,
    batch_id bigint NOT NULL REFERENCES bf_assistant.recommendation_audit_batches(id) ON DELETE RESTRICT,
    furnace_id text NOT NULL,
    diagnosis_snapshot_id bigint,
    diagnosis_ts timestamptz NOT NULL,
    condition_index smallint NOT NULL CHECK (condition_index BETWEEN 0 AND 7),
    condition_label text NOT NULL CHECK (condition_label IN ('normal','lowline','edge','center','channel','cold','hot','column')),
    condition_display_name text NOT NULL,
    condition_score double precision NOT NULL,
    condition_role text NOT NULL CHECK (condition_role IN ('main','secondary','watch')),
    condition_scope text NOT NULL CHECK (condition_scope IN ('active','supporting','hypothetical')),
    action_index smallint NOT NULL CHECK (action_index >= 0),
    action_id text NOT NULL,
    scheme text NOT NULL,
    status text NOT NULL CHECK (status IN ('eligible','blocked','needs_data','manual_confirm')),
    action_name text NOT NULL,
    user_facing_text text NOT NULL,
    source_document text NOT NULL,
    source_refs jsonb NOT NULL CHECK (jsonb_typeof(source_refs) = 'array'),
    trigger_evidence jsonb NOT NULL CHECK (jsonb_typeof(trigger_evidence) = 'array'),
    required_inputs jsonb NOT NULL CHECK (jsonb_typeof(required_inputs) = 'array'),
    preconditions jsonb NOT NULL CHECK (jsonb_typeof(preconditions) = 'array'),
    blocking_reasons jsonb NOT NULL CHECK (jsonb_typeof(blocking_reasons) = 'array'),
    delta jsonb,
    sequence_plan jsonb NOT NULL CHECK (jsonb_typeof(sequence_plan) = 'object'),
    missing_inputs jsonb NOT NULL CHECK (jsonb_typeof(missing_inputs) = 'array'),
    observation_window jsonb,
    approval jsonb NOT NULL CHECK (jsonb_typeof(approval) = 'object'),
    operator_confirm_required boolean NOT NULL,
    read_only boolean NOT NULL DEFAULT true CHECK (read_only),
    legacy_stage text NOT NULL,
    control_variable text CHECK (control_variable IS NULL OR control_variable IN ('P_blast_cold','PCI_set')),
    control_label text,
    current_value double precision,
    recommended_change double precision,
    recommended_target double precision,
    unit text,
    step_tier jsonb CHECK (step_tier IS NULL OR jsonb_typeof(step_tier) = 'object'),
    effective_at timestamptz,
    limit_snapshot jsonb CHECK (limit_snapshot IS NULL OR jsonb_typeof(limit_snapshot) = 'object'),
    action_payload_sha256 text NOT NULL CHECK (action_payload_sha256 ~ '^[0-9A-F]{64}$'),
    action_payload jsonb NOT NULL CHECK (jsonb_typeof(action_payload) = 'object'),
    created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    UNIQUE (batch_id, condition_label, action_id),
    UNIQUE (batch_id, condition_index, action_index)
);

ALTER TABLE bf_assistant.recommendation_audit_actions
    ADD COLUMN IF NOT EXISTS control_variable text;
ALTER TABLE bf_assistant.recommendation_audit_actions
    ADD COLUMN IF NOT EXISTS control_label text;
ALTER TABLE bf_assistant.recommendation_audit_actions
    ADD COLUMN IF NOT EXISTS current_value double precision;
ALTER TABLE bf_assistant.recommendation_audit_actions
    ADD COLUMN IF NOT EXISTS recommended_change double precision;
ALTER TABLE bf_assistant.recommendation_audit_actions
    ADD COLUMN IF NOT EXISTS recommended_target double precision;
ALTER TABLE bf_assistant.recommendation_audit_actions
    ADD COLUMN IF NOT EXISTS unit text;
ALTER TABLE bf_assistant.recommendation_audit_actions
    ADD COLUMN IF NOT EXISTS step_tier jsonb;
ALTER TABLE bf_assistant.recommendation_audit_actions
    ADD COLUMN IF NOT EXISTS effective_at timestamptz;
ALTER TABLE bf_assistant.recommendation_audit_actions
    ADD COLUMN IF NOT EXISTS limit_snapshot jsonb;

CREATE INDEX IF NOT EXISTS idx_recommendation_audit_actions_lookup
    ON bf_assistant.recommendation_audit_actions (diagnosis_ts DESC, condition_label, status);
CREATE INDEX IF NOT EXISTS idx_recommendation_audit_actions_batch
    ON bf_assistant.recommendation_audit_actions (batch_id, condition_index, action_index);
CREATE INDEX IF NOT EXISTS idx_recommendation_audit_actions_approval
    ON bf_assistant.recommendation_audit_actions (operator_confirm_required, diagnosis_ts DESC);
CREATE INDEX IF NOT EXISTS idx_recommendation_audit_actions_control
    ON bf_assistant.recommendation_audit_actions (control_variable, diagnosis_ts DESC, status);

CREATE TABLE IF NOT EXISTS bf_assistant.foreman_operational_guidance (
    id bigserial PRIMARY KEY,
    furnace_id text NOT NULL DEFAULT 'GL02',
    diagnosis_snapshot_id bigint,
    diagnosis_ts timestamptz NOT NULL,
    diagnosis_main_label text,
    diagnosis_score double precision,
    cold_pressure_computed_target double precision,
    cold_pressure_guidance_target double precision NOT NULL CHECK (cold_pressure_guidance_target >= 400),
    cold_pressure_effective_at timestamptz,
    pci_computed_target double precision,
    pci_guidance_target double precision NOT NULL CHECK (pci_guidance_target >= 0 AND pci_guidance_target <= 45),
    pci_effective_at timestamptz,
    pressure_limit_snapshot jsonb NOT NULL DEFAULT '{}'::jsonb CHECK (jsonb_typeof(pressure_limit_snapshot) = 'object'),
    pci_limit_snapshot jsonb NOT NULL DEFAULT '{}'::jsonb CHECK (jsonb_typeof(pci_limit_snapshot) = 'object'),
    pressure_source text NOT NULL CHECK (pressure_source IN ('foreman_manual', 'computed_fallback')),
    pci_source text NOT NULL CHECK (pci_source IN ('foreman_manual', 'computed_fallback')),
    approval_status text NOT NULL CHECK (approval_status IN ('confirmed', 'rejected')),
    entered_by text NOT NULL DEFAULT '值班工长',
    operator_note text NOT NULL DEFAULT '',
    request_payload jsonb NOT NULL DEFAULT '{}'::jsonb CHECK (jsonb_typeof(request_payload) = 'object'),
    created_at timestamptz NOT NULL DEFAULT clock_timestamp()
);

CREATE INDEX IF NOT EXISTS idx_foreman_guidance_latest
    ON bf_assistant.foreman_operational_guidance (furnace_id, diagnosis_ts DESC, created_at DESC, id DESC);
CREATE INDEX IF NOT EXISTS idx_foreman_guidance_effective
    ON bf_assistant.foreman_operational_guidance (furnace_id, cold_pressure_effective_at DESC, pci_effective_at DESC);
CREATE OR REPLACE FUNCTION bf_assistant.reject_recommendation_audit_mutation()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    RAISE EXCEPTION 'recommendation audit records are append-only; append a new version instead';
END;
$$;

DROP TRIGGER IF EXISTS trg_recommendation_audit_batches_immutable
    ON bf_assistant.recommendation_audit_batches;
CREATE TRIGGER trg_recommendation_audit_batches_immutable
BEFORE UPDATE OR DELETE OR TRUNCATE ON bf_assistant.recommendation_audit_batches
FOR EACH STATEMENT EXECUTE FUNCTION bf_assistant.reject_recommendation_audit_mutation();

DROP TRIGGER IF EXISTS trg_recommendation_audit_actions_immutable
    ON bf_assistant.recommendation_audit_actions;
CREATE TRIGGER trg_recommendation_audit_actions_immutable
BEFORE UPDATE OR DELETE OR TRUNCATE ON bf_assistant.recommendation_audit_actions
FOR EACH STATEMENT EXECUTE FUNCTION bf_assistant.reject_recommendation_audit_mutation();

DROP TRIGGER IF EXISTS trg_foreman_operational_guidance_immutable
    ON bf_assistant.foreman_operational_guidance;
CREATE TRIGGER trg_foreman_operational_guidance_immutable
BEFORE UPDATE OR DELETE OR TRUNCATE ON bf_assistant.foreman_operational_guidance
FOR EACH STATEMENT EXECUTE FUNCTION bf_assistant.reject_recommendation_audit_mutation();
CREATE OR REPLACE VIEW bf_assistant.recommendation_audit_action_detail AS
SELECT
    b.id AS audit_batch_id,
    b.audit_schema_version,
    b.idempotency_key,
    b.engine_name,
    b.engine_version,
    b.policy_sha256,
    b.recommendation_schema_version,
    b.write_source,
    a.*
FROM bf_assistant.recommendation_audit_batches b
JOIN bf_assistant.recommendation_audit_actions a ON a.batch_id = b.id;

COMMENT ON TABLE bf_assistant.recommendation_audit_batches IS
    'Immutable full recommendation bundles. Runtime roles may INSERT/SELECT but never UPDATE/DELETE.';
COMMENT ON TABLE bf_assistant.recommendation_audit_actions IS
    'One queryable row per furnace-condition recommendation action, with full original action_payload.';
COMMENT ON COLUMN bf_assistant.recommendation_audit_actions.status IS
    'One of eligible, blocked, needs_data, manual_confirm; all statuses are audit-retained.';
COMMENT ON COLUMN bf_assistant.recommendation_audit_actions.read_only IS
    'True means the record is advice only and is not a process-control command.';

INSERT INTO bf_assistant.recommendation_audit_schema_versions (version, description)
VALUES ('recommendation_audit.v1', 'Full bundle plus one immutable row per recommendation action')
ON CONFLICT (version) DO NOTHING;

INSERT INTO bf_assistant.recommendation_audit_schema_versions (version, description)
VALUES ('recommendation_audit.v2', 'Materialised cold-blast pressure and PCI setpoint control fields')
ON CONFLICT (version) DO NOTHING;
