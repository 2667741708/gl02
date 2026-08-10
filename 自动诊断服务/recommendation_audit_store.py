"""Immutable, full-fidelity persistence for recommendation-engine decisions.

The audit store records the complete multi-condition bundle and also materialises
every action into a queryable row.  It never executes a process-control command.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
from collections import Counter
from datetime import datetime
from typing import Any, Mapping


AUDIT_SCHEMA_VERSION = "recommendation_audit.v2"
AUDIT_BATCH_TABLE = "bf_assistant.recommendation_audit_batches"
AUDIT_ACTION_TABLE = "bf_assistant.recommendation_audit_actions"
GUIDANCE_TABLE = "bf_assistant.foreman_operational_guidance"
GUIDANCE_VARIABLES = {"P_blast_cold", "PCI_set"}
ACTION_STATUSES = {"eligible", "blocked", "needs_data", "manual_confirm"}
EXPECTED_CONDITION_LABELS = {
    "normal",
    "lowline",
    "edge",
    "center",
    "channel",
    "cold",
    "hot",
    "column",
}
REQUIRED_ACTION_FIELDS = {
    "id",
    "scheme",
    "status",
    "name",
    "user_facing_text",
    "source_document",
    "source_refs",
    "trigger_evidence",
    "required_inputs",
    "preconditions",
    "blocking_reasons",
    "delta",
    "sequence",
    "missing_inputs",
    "observation_window",
    "approval",
    "operator_confirm_required",
    "read_only",
    "legacy_stage",
    "control_variable",
    "control_label",
    "current_value",
    "recommended_change",
    "recommended_target",
    "unit",
    "step_tier",
    "effective_at",
    "limit_snapshot",
}


class RecommendationAuditValidationError(ValueError):
    """Raised before a partial or non-auditable recommendation can be stored."""


def _json_default(value: Any) -> str:
    if isinstance(value, datetime):
        return value.isoformat()
    return str(value)


def _json_safe(value: Any) -> Any:
    if isinstance(value, float) and not math.isfinite(value):
        return None
    if isinstance(value, Mapping):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]
    return value


def canonical_json(value: Any) -> str:
    return json.dumps(
        _json_safe(value),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=_json_default,
        allow_nan=False,
    )


def payload_sha256(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest().upper()


def _json_param(value: Any) -> str:
    return canonical_json(value)


def _mapping(value: object) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _list(value: object) -> list[Any]:
    return list(value) if isinstance(value, list) else []


def validate_recommendation_bundle(bundle: Mapping[str, Any]) -> list[dict[str, Any]]:
    """Validate the eight-condition contract and return flattened action rows."""

    conditions = bundle.get("conditions")
    if not isinstance(conditions, list):
        raise RecommendationAuditValidationError("recommendation bundle has no conditions array")

    labels = [str(item.get("label") or "") for item in conditions if isinstance(item, Mapping)]
    if len(conditions) != len(EXPECTED_CONDITION_LABELS) or set(labels) != EXPECTED_CONDITION_LABELS:
        raise RecommendationAuditValidationError(
            f"recommendation bundle must contain exactly eight furnace conditions: {labels}"
        )

    flattened: list[dict[str, Any]] = []
    for condition_index, condition_obj in enumerate(conditions):
        if not isinstance(condition_obj, Mapping):
            raise RecommendationAuditValidationError(f"condition #{condition_index} is not an object")
        condition = dict(condition_obj)
        recommendation = _mapping(condition.get("recommendation"))
        actions = recommendation.get("actions")
        if not isinstance(actions, list) or not actions:
            raise RecommendationAuditValidationError(
                f"condition {condition.get('label')} has no recommendation actions"
            )
        for action_index, action_obj in enumerate(actions):
            if not isinstance(action_obj, Mapping):
                raise RecommendationAuditValidationError(
                    f"condition {condition.get('label')} action #{action_index} is not an object"
                )
            action = dict(action_obj)
            missing_fields = sorted(REQUIRED_ACTION_FIELDS.difference(action))
            if missing_fields:
                raise RecommendationAuditValidationError(
                    f"action {action.get('id')} is missing audit fields: {missing_fields}"
                )
            status = str(action.get("status") or "")
            if status not in ACTION_STATUSES:
                raise RecommendationAuditValidationError(
                    f"action {action.get('id')} has unsupported status: {status}"
                )
            if action.get("read_only") is not True:
                raise RecommendationAuditValidationError(
                    f"action {action.get('id')} is not explicitly read-only"
                )
            if status == "blocked" and not _list(action.get("blocking_reasons")):
                raise RecommendationAuditValidationError(
                    f"blocked action {action.get('id')} has no blocking reason"
                )
            if status == "needs_data" and not _list(action.get("missing_inputs")):
                raise RecommendationAuditValidationError(
                    f"needs_data action {action.get('id')} has no missing inputs"
                )
            flattened.append(
                {
                    "condition_index": condition_index,
                    "condition": condition,
                    "recommendation": recommendation,
                    "action_index": action_index,
                    "action": action,
                }
            )
    return flattened


def build_audit_identity(
    diagnosis: Mapping[str, Any],
    bundle: Mapping[str, Any],
    *,
    diagnosis_snapshot_id: int | str | None,
    furnace_id: str,
) -> tuple[str, dict[str, Any]]:
    engine_meta = _mapping(bundle.get("engine_meta"))
    identity = {
        "audit_schema_version": AUDIT_SCHEMA_VERSION,
        "furnace_id": furnace_id,
        "diagnosis_snapshot_id": str(diagnosis_snapshot_id or ""),
        "diagnosis_ts": str(
            diagnosis.get("diagnosis_ts")
            or diagnosis.get("timestamp")
            or bundle.get("timestamp")
            or ""
        ),
        "engine_name": str(engine_meta.get("name") or ""),
        "engine_version": str(engine_meta.get("version") or ""),
        "policy_sha256": str(engine_meta.get("policy_sha256") or ""),
    }
    if not identity["diagnosis_snapshot_id"] and not identity["diagnosis_ts"]:
        raise RecommendationAuditValidationError("diagnosis snapshot identity is missing")
    if not identity["engine_name"] or not identity["engine_version"]:
        raise RecommendationAuditValidationError("recommendation engine provenance is incomplete")
    if not identity["policy_sha256"]:
        raise RecommendationAuditValidationError("recommendation policy SHA-256 is missing")
    return payload_sha256(identity), identity


def _decode_jsonb(value: Any) -> dict[str, Any]:
    if isinstance(value, Mapping):
        return dict(value)
    if isinstance(value, str):
        loaded = json.loads(value)
        return dict(loaded) if isinstance(loaded, Mapping) else {}
    return {}


def _guidance_number(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def normalize_foreman_guidance_request(request: Mapping[str, Any]) -> dict[str, Any]:
    body = _mapping(request)
    current = _mapping(body.get("current"))
    computed = _mapping(body.get("computed"))
    guidance = _mapping(body.get("guidance"))
    limits = _mapping(body.get("limits"))
    pressure_limits = _mapping(limits.get("P_blast_cold"))
    pci_limits = _mapping(limits.get("PCI_set"))
    current_pressure = _guidance_number(current.get("P_blast_cold"))
    current_pci = _guidance_number(current.get("PCI_set"))
    computed_pressure = _guidance_number(computed.get("P_blast_cold")) or current_pressure
    computed_pci = _guidance_number(computed.get("PCI_set")) or current_pci
    pressure_target = _guidance_number(guidance.get("P_blast_cold"))
    pci_target = _guidance_number(guidance.get("PCI_set"))
    pressure_source = "foreman_manual" if pressure_target is not None else "computed_fallback"
    pci_source = "foreman_manual" if pci_target is not None else "computed_fallback"
    pressure_target = pressure_target if pressure_target is not None else computed_pressure
    pci_target = pci_target if pci_target is not None else computed_pci
    diagnosis_ts = str(body.get("diagnosis_ts") or "").strip()
    if not diagnosis_ts:
        raise RecommendationAuditValidationError("diagnosis_ts is required for foreman guidance")
    if pressure_target is None:
        raise RecommendationAuditValidationError("P_blast_cold has no manual or computed fallback value")
    if pci_target is None:
        raise RecommendationAuditValidationError("PCI_set has no manual or computed fallback value")
    if pressure_target < 400:
        raise RecommendationAuditValidationError("P_blast_cold guidance cannot be below 400 kPa")
    pressure_max = _guidance_number(pressure_limits.get("normal_q3") or pressure_limits.get("hard_max"))
    if pressure_max is not None and pressure_target > pressure_max + 1e-6:
        raise RecommendationAuditValidationError("P_blast_cold guidance exceeds the current dynamic Q3 limit")
    if pci_target < 0 or pci_target > 45:
        raise RecommendationAuditValidationError("PCI_set guidance must be within 0-45 t/h")
    return {
        "furnace_id": str(body.get("furnace_id") or os.getenv("BF_FURNACE_ID", "GL02")).strip() or "GL02",
        "diagnosis_snapshot_id": body.get("diagnosis_snapshot_id"),
        "diagnosis_ts": diagnosis_ts,
        "diagnosis_main_label": str(body.get("diagnosis_main_label") or ""),
        "diagnosis_score": _guidance_number(body.get("diagnosis_score")),
        "cold_pressure_computed_target": computed_pressure,
        "cold_pressure_guidance_target": pressure_target,
        "cold_pressure_effective_at": body.get("cold_pressure_effective_at"),
        "pci_computed_target": computed_pci,
        "pci_guidance_target": pci_target,
        "pci_effective_at": body.get("pci_effective_at"),
        "pressure_limit_snapshot": pressure_limits,
        "pci_limit_snapshot": pci_limits,
        "pressure_source": pressure_source,
        "pci_source": pci_source,
        "approval_status": "confirmed",
        "entered_by": str(body.get("entered_by") or "值班工长"),
        "operator_note": str(body.get("operator_note") or ""),
        "request_payload": _json_safe(body),
    }


def persist_foreman_guidance(conn: Any, request: Mapping[str, Any]) -> dict[str, Any]:
    record = normalize_foreman_guidance_request(request)
    row = conn.execute(
        f"""
        INSERT INTO {GUIDANCE_TABLE} (
            furnace_id, diagnosis_snapshot_id, diagnosis_ts, diagnosis_main_label,
            diagnosis_score, cold_pressure_computed_target, cold_pressure_guidance_target,
            cold_pressure_effective_at, pci_computed_target, pci_guidance_target,
            pci_effective_at, pressure_limit_snapshot, pci_limit_snapshot,
            pressure_source, pci_source, approval_status, entered_by, operator_note,
            request_payload
        ) VALUES (
            %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
            %s::jsonb, %s::jsonb, %s, %s, %s, %s, %s, %s::jsonb
        )
        RETURNING id, furnace_id, diagnosis_snapshot_id, diagnosis_ts,
                  cold_pressure_computed_target, cold_pressure_guidance_target,
                  cold_pressure_effective_at, pci_computed_target,
                  pci_guidance_target, pci_effective_at, pressure_source,
                  pci_source, approval_status, entered_by, operator_note, created_at
        """,
        (
            record["furnace_id"], record["diagnosis_snapshot_id"], record["diagnosis_ts"],
            record["diagnosis_main_label"], record["diagnosis_score"],
            record["cold_pressure_computed_target"], record["cold_pressure_guidance_target"],
            record["cold_pressure_effective_at"], record["pci_computed_target"],
            record["pci_guidance_target"], record["pci_effective_at"],
            _json_param(record["pressure_limit_snapshot"]), _json_param(record["pci_limit_snapshot"]),
            record["pressure_source"], record["pci_source"], record["approval_status"],
            record["entered_by"], record["operator_note"], _json_param(record["request_payload"]),
        ),
    ).fetchone()
    conn.commit()
    return {"state": "saved", "read_only": True, "guidance": dict(row) if row else record}


def latest_foreman_guidance(conn: Any, furnace_id: str | None = None) -> dict[str, Any]:
    row = conn.execute(
        f"""
        SELECT id, furnace_id, diagnosis_snapshot_id, diagnosis_ts,
               cold_pressure_computed_target, cold_pressure_guidance_target,
               cold_pressure_effective_at, pci_computed_target,
               pci_guidance_target, pci_effective_at, pressure_source,
               pci_source, approval_status, entered_by, operator_note, created_at
        FROM {GUIDANCE_TABLE}
        WHERE furnace_id = %s AND approval_status = 'confirmed'
        ORDER BY created_at DESC, id DESC
        LIMIT 1
        """,
        (str(furnace_id or os.getenv("BF_FURNACE_ID", "GL02")).strip() or "GL02",),
    ).fetchone()
    if not row:
        return {"state": "none", "read_only": True, "fallback_policy": "computed_cold_pressure_when_no_foreman_guidance"}
    item = dict(row)
    return {
        "state": "confirmed", "read_only": True,
        "fallback_policy": "computed_cold_pressure_when_no_foreman_guidance",
        "id": item.get("id"), "diagnosis_ts": item.get("diagnosis_ts"),
        "entered_by": item.get("entered_by"), "operator_note": item.get("operator_note"),
        "targets": {"P_blast_cold": item.get("cold_pressure_guidance_target"), "PCI_set": item.get("pci_guidance_target")},
        "computed_targets": {"P_blast_cold": item.get("cold_pressure_computed_target"), "PCI_set": item.get("pci_computed_target")},
        "sources": {"P_blast_cold": item.get("pressure_source"), "PCI_set": item.get("pci_source")},
        "effective_at": {"P_blast_cold": item.get("cold_pressure_effective_at"), "PCI_set": item.get("pci_effective_at")},
        "created_at": item.get("created_at"),
    }

def persist_recommendation_bundle(
    conn: Any,
    diagnosis: Mapping[str, Any],
    current_values: Mapping[str, Any] | None,
    bundle: Mapping[str, Any],
    *,
    diagnosis_snapshot_id: int | str | None,
    furnace_id: str | None = None,
    write_source: str = "ws_bridge",
) -> dict[str, Any]:
    """Insert one immutable batch and all actions, or return the existing batch.

    The idempotency key intentionally excludes live values and output hashes.  For a
    given diagnosis snapshot, engine version and policy hash, the first committed
    bundle becomes the immutable auditable decision shown to every later caller.
    """

    furnace = str(furnace_id or os.getenv("BF_FURNACE_ID", "GL02")).strip() or "GL02"
    diagnosis_obj = dict(diagnosis)
    current_obj = dict(current_values or {})
    bundle_obj = dict(bundle)
    flattened = validate_recommendation_bundle(bundle_obj)
    idempotency_key, identity = build_audit_identity(
        diagnosis_obj,
        bundle_obj,
        diagnosis_snapshot_id=diagnosis_snapshot_id,
        furnace_id=furnace,
    )
    engine_meta = _mapping(bundle_obj.get("engine_meta"))
    statuses = Counter(str(item["action"]["status"]) for item in flattened)
    status_counts = {status: int(statuses.get(status, 0)) for status in sorted(ACTION_STATUSES)}
    diagnosis_ts = (
        diagnosis_obj.get("diagnosis_ts")
        or diagnosis_obj.get("timestamp")
        or bundle_obj.get("timestamp")
    )
    diagnosis_snapshot_id_value = int(diagnosis_snapshot_id) if diagnosis_snapshot_id is not None else None
    source_context = {
        "diagnosis_source": diagnosis_obj.get("source") or {},
        "write_source": write_source,
        "identity": identity,
    }
    data_quality = {
        "data_coverage": diagnosis_obj.get("data_coverage") or {},
        "missing_variables": diagnosis_obj.get("missing_variables") or [],
        "source_lag_seconds": diagnosis_obj.get("source_lag_seconds"),
    }
    input_payload = {"diagnosis": diagnosis_obj, "current_values": current_obj}
    bundle_hash = payload_sha256(bundle_obj)
    input_hash = payload_sha256(input_payload)

    insert_batch_sql = f"""
        INSERT INTO {AUDIT_BATCH_TABLE} (
            audit_schema_version, idempotency_key, furnace_id,
            diagnosis_snapshot_id, diagnosis_ts, diagnosis_main_label,
            diagnosis_secondary_label, diagnosis_scores, diagnosis_payload,
            current_values, data_quality, source_context, input_payload_sha256,
            recommendation_payload_sha256, engine_name, engine_version,
            recommendation_schema_version, policy_source, policy_sha256,
            condition_count, action_count, status_counts,
            recommendation_bundle, write_source, read_only
        ) VALUES (
            %s, %s, %s,
            %s, %s, %s,
            %s, %s::jsonb, %s::jsonb,
            %s::jsonb, %s::jsonb, %s::jsonb, %s,
            %s, %s, %s,
            %s, %s, %s,
            %s, %s, %s::jsonb,
            %s::jsonb, %s, true
        )
        ON CONFLICT (idempotency_key) DO NOTHING
        RETURNING id, recommendation_bundle, action_count, status_counts, created_at
    """
    batch_params = (
        AUDIT_SCHEMA_VERSION,
        idempotency_key,
        furnace,
        diagnosis_snapshot_id_value,
        diagnosis_ts,
        str(diagnosis_obj.get("main_label") or bundle_obj.get("main_label") or "normal"),
        diagnosis_obj.get("secondary_label") or bundle_obj.get("secondary_label"),
        _json_param(diagnosis_obj.get("raw_scores") or {}),
        _json_param(diagnosis_obj),
        _json_param(current_obj),
        _json_param(data_quality),
        _json_param(source_context),
        input_hash,
        bundle_hash,
        str(engine_meta.get("name") or ""),
        str(engine_meta.get("version") or ""),
        str(bundle_obj.get("schema_version") or ""),
        str(engine_meta.get("policy_source") or ""),
        str(engine_meta.get("policy_sha256") or ""),
        len(bundle_obj.get("conditions") or []),
        len(flattened),
        _json_param(status_counts),
        _json_param(bundle_obj),
        write_source,
    )

    with conn.transaction():
        inserted = conn.execute(insert_batch_sql, batch_params).fetchone()
        created = inserted is not None
        if created:
            batch_row = inserted
            batch_id = int(batch_row["id"])
            for item in flattened:
                condition = item["condition"]
                action = item["action"]
                conn.execute(
                    f"""
                    INSERT INTO {AUDIT_ACTION_TABLE} (
                        batch_id, furnace_id, diagnosis_snapshot_id, diagnosis_ts,
                        condition_index, condition_label, condition_display_name,
                        condition_score, condition_role, condition_scope,
                        action_index, action_id, scheme, status, action_name,
                        user_facing_text, source_document, source_refs,
                        trigger_evidence, required_inputs, preconditions,
                        blocking_reasons, delta, sequence_plan, missing_inputs,
                        observation_window, approval, operator_confirm_required,
                        read_only, legacy_stage, control_variable, control_label,
                        current_value, recommended_change, recommended_target, unit,
                        step_tier, effective_at, limit_snapshot,
                        action_payload_sha256, action_payload
                    ) VALUES (
                        %s, %s, %s, %s,
                        %s, %s, %s,
                        %s, %s, %s,
                        %s, %s, %s, %s, %s,
                        %s, %s, %s::jsonb,
                        %s::jsonb, %s::jsonb, %s::jsonb,
                        %s::jsonb, %s::jsonb, %s::jsonb, %s::jsonb,
                        %s::jsonb, %s::jsonb, %s,
                        true, %s, %s, %s,
                        %s, %s, %s, %s,
                        %s::jsonb, %s, %s::jsonb,
                        %s, %s::jsonb
                    )
                    """,
                    (
                        batch_id,
                        furnace,
                        diagnosis_snapshot_id_value,
                        diagnosis_ts,
                        int(item["condition_index"]),
                        str(condition.get("label") or ""),
                        str(condition.get("display_name") or ""),
                        condition.get("score"),
                        str(condition.get("role") or "watch"),
                        str(condition.get("scope") or "hypothetical"),
                        int(item["action_index"]),
                        str(action.get("id") or ""),
                        str(action.get("scheme") or ""),
                        str(action.get("status") or ""),
                        str(action.get("name") or ""),
                        str(action.get("user_facing_text") or ""),
                        str(action.get("source_document") or ""),
                        _json_param(action.get("source_refs") or []),
                        _json_param(action.get("trigger_evidence") or []),
                        _json_param(action.get("required_inputs") or []),
                        _json_param(action.get("preconditions") or []),
                        _json_param(action.get("blocking_reasons") or []),
                        _json_param(action.get("delta")),
                        _json_param(action.get("sequence") or {}),
                        _json_param(action.get("missing_inputs") or []),
                        _json_param(action.get("observation_window")),
                        _json_param(action.get("approval") or {}),
                        bool(action.get("operator_confirm_required")),
                        str(action.get("legacy_stage") or ""),
                        str(action.get("control_variable") or ""),
                        str(action.get("control_label") or ""),
                        action.get("current_value"),
                        action.get("recommended_change"),
                        action.get("recommended_target"),
                        str(action.get("unit") or ""),
                        _json_param(action.get("step_tier") or {}),
                        action.get("effective_at"),
                        _json_param(action.get("limit_snapshot") or {}),
                        payload_sha256(action),
                        _json_param(action),
                    ),
                )
        else:
            batch_row = conn.execute(
                f"""
                SELECT id, recommendation_bundle, action_count, status_counts, created_at
                FROM {AUDIT_BATCH_TABLE}
                WHERE idempotency_key = %s
                """,
                (idempotency_key,),
            ).fetchone()
            if batch_row is None:
                raise RuntimeError("recommendation audit idempotency conflict has no persisted row")
            batch_id = int(batch_row["id"])

        count_row = conn.execute(
            f"SELECT count(*) AS count FROM {AUDIT_ACTION_TABLE} WHERE batch_id = %s",
            (batch_id,),
        ).fetchone()
        persisted_action_count = int(count_row["count"] if count_row else 0)
        expected_action_count = int(batch_row["action_count"])
        if persisted_action_count != expected_action_count:
            raise RuntimeError(
                f"recommendation audit batch {batch_id} action count mismatch: "
                f"expected={expected_action_count} actual={persisted_action_count}"
            )

    persisted_bundle = _decode_jsonb(batch_row["recommendation_bundle"])
    persisted_status_counts = _decode_jsonb(batch_row["status_counts"])
    return {
        "state": "persisted",
        "audit_schema_version": AUDIT_SCHEMA_VERSION,
        "batch_id": batch_id,
        "created": created,
        "immutable": True,
        "idempotency_key": idempotency_key,
        "condition_count": len(persisted_bundle.get("conditions") or []),
        "action_count": persisted_action_count,
        "status_counts": persisted_status_counts,
        "created_at": batch_row.get("created_at") if isinstance(batch_row, Mapping) else None,
        "bundle": persisted_bundle,
        "read_only": True,
    }
