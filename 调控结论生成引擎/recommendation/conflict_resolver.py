"""跨炉况、跨调剂手段的通用冲突处理。"""

from __future__ import annotations

import json
from copy import deepcopy
from typing import Any


ACTIVE_STATUSES = {"eligible", "manual_confirm"}


def _block(action: dict[str, Any], reason: str) -> None:
    action["status"] = "blocked"
    action.setdefault("blocking_reasons", []).append(reason)
    action["blocking_reasons"] = list(dict.fromkeys(action["blocking_reasons"]))


def resolve_action_conflicts(
    actions: list[dict[str, Any]],
    diagnosis: dict[str, Any],
    safety_result: dict[str, Any],
) -> list[dict[str, Any]]:
    """让安全/失常/减量动作优先于相反方向，不靠两两组合枚举。"""
    resolved = [deepcopy(action) for action in actions]
    by_id = {str(action.get("id")): action for action in resolved}

    forbidden_ids = set(safety_result.get("forbidden_ids") or [])
    for action_id in forbidden_ids:
        action = by_id.get(action_id)
        if action:
            _block(action, "该动作被当前安全门禁阻断")

    direction_pairs = (
        ("LOW-BLAST-UP-GATE", {"LOW-BLAST-DOWN-02", "LOW-BLAST-DOWN-04", "LOW-BLAST-DOWN-05"}, "已有减风处置优先，当前不得同时加风"),
        ("LOW-O2-UP-GATE", {"LOW-O2-DOWN-01", "EDGE-O2-BLOCK"}, "已有减氧/富氧阻断处置优先，当前不得同时加氧"),
        ("LOW-PCI-UP-02", {"LOW-PCI-DOWN-02", "LOW-PCI-DOWN-05"}, "减少或停止喷煤规则优先，当前增煤候选被阻断"),
    )
    for increase_id, decrease_ids, reason in direction_pairs:
        increase = by_id.get(increase_id)
        if not increase:
            continue
        opposite_is_active = any(
            by_id.get(action_id, {}).get("status") in ACTIVE_STATUSES
            for action_id in decrease_ids
        )
        if opposite_is_active:
            _block(increase, reason)

    # 相同动作可由主、次炉况同时触发；合并时保留全部证据和最严格状态。
    precedence = {"eligible": 0, "needs_data": 1, "manual_confirm": 2, "blocked": 3}
    deduplicated: dict[str, dict[str, Any]] = {}
    for action in resolved:
        action_id = str(action.get("id"))
        current = deduplicated.get(action_id)
        if current is None:
            deduplicated[action_id] = action
            continue
        current["trigger_evidence"] = list(
            {
                json.dumps(item, ensure_ascii=False, sort_keys=True, default=str): item
                for item in current.get("trigger_evidence", []) + action.get("trigger_evidence", [])
            }.values()
        )
        current["missing_inputs"] = list(
            dict.fromkeys(current.get("missing_inputs", []) + action.get("missing_inputs", []))
        )
        current["blocking_reasons"] = list(
            dict.fromkeys(current.get("blocking_reasons", []) + action.get("blocking_reasons", []))
        )
        if precedence.get(str(action.get("status")), 0) > precedence.get(str(current.get("status")), 0):
            current["status"] = action["status"]
    return list(deduplicated.values())
