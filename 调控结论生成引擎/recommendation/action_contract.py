"""三规二制建议动作的稳定返回契约。"""

from __future__ import annotations

from copy import deepcopy
from typing import Any


ACTION_STATUSES = {"eligible", "blocked", "needs_data", "manual_confirm"}


def build_action(
    definition: dict[str, Any],
    *,
    status: str,
    trigger_evidence: list[dict[str, Any]] | None = None,
    missing_inputs: list[str] | None = None,
    blocking_reasons: list[str] | None = None,
    precondition_states: list[bool | None] | None = None,
) -> dict[str, Any]:
    """把策略目录定义物化为每个字段都稳定存在的动作对象。"""
    if status not in ACTION_STATUSES:
        raise ValueError(f"unsupported action status: {status}")

    descriptions = list(definition.get("preconditions") or [])
    states = list(precondition_states or [])
    preconditions = [
        {
            "description": description,
            "satisfied": states[index] if index < len(states) else None,
        }
        for index, description in enumerate(descriptions)
    ]
    approval = deepcopy(definition.get("approval") or {})
    approval.setdefault("required", True)
    approval.setdefault("role", "值班工长")
    approval.setdefault("kind", "parameter_change")

    return {
        "id": str(definition["id"]),
        "scheme": str(definition.get("scheme") or "integrated"),
        "status": status,
        "name": str(definition.get("name") or definition["id"]),
        "user_facing_text": str(definition.get("user_facing_text") or ""),
        "source_document": str(definition.get("source_document") or ""),
        "source_refs": list(definition.get("source_refs") or []),
        "trigger_evidence": deepcopy(trigger_evidence or []),
        "required_inputs": list(definition.get("required_inputs") or []),
        "preconditions": preconditions,
        "blocking_reasons": list(blocking_reasons or []),
        "delta": deepcopy(definition.get("delta")),
        "sequence": {
            "rank": int(definition.get("sequence_rank", 999)),
            "group": str(definition.get("sequence_group") or definition.get("scheme") or "integrated"),
            "depends_on": list(definition.get("depends_on") or []),
            "skip_if_unavailable": True,
        },
        "missing_inputs": list(dict.fromkeys(missing_inputs or [])),
        "observation_window": deepcopy(definition.get("observation_window")),
        "approval": approval,
        "operator_confirm_required": bool(approval["required"]),
        "read_only": True,
        "legacy_stage": str(definition.get("legacy_stage") or "followup"),
    }


def validate_action_contract(action: dict[str, Any]) -> None:
    """在格式化前快速拒绝缺字段或互相矛盾的动作。"""
    required = {
        "id",
        "scheme",
        "status",
        "name",
        "user_facing_text",
        "source_refs",
        "trigger_evidence",
        "preconditions",
        "blocking_reasons",
        "delta",
        "sequence",
        "missing_inputs",
        "observation_window",
        "approval",
        "read_only",
    }
    missing_keys = sorted(required.difference(action))
    if missing_keys:
        raise ValueError(f"action {action.get('id')} missing keys: {missing_keys}")
    if action["status"] not in ACTION_STATUSES:
        raise ValueError(f"action {action.get('id')} has invalid status")
    if action["status"] == "blocked" and not action["blocking_reasons"]:
        raise ValueError(f"blocked action {action.get('id')} has no blocking reason")
    if action["status"] == "needs_data" and not action["missing_inputs"]:
        raise ValueError(f"needs_data action {action.get('id')} has no missing inputs")
    if action["read_only"] is not True:
        raise ValueError(f"action {action.get('id')} must remain read-only")
    if "control_variable" in action:
        control_required = {
            "control_label",
            "current_value",
            "recommended_change",
            "recommended_target",
            "unit",
            "step_tier",
            "effective_at",
            "limit_snapshot",
        }
        missing_control = sorted(control_required.difference(action))
        if missing_control:
            raise ValueError(
                f"scoped action {action.get('id')} missing control keys: {missing_control}"
            )
        if action["control_variable"] not in {"P_blast_cold", "PCI_set"}:
            raise ValueError(f"unsupported foreman control: {action['control_variable']}")
        if action.get("approval", {}).get("required") is not True:
            raise ValueError(f"scoped action {action.get('id')} requires foreman approval")
