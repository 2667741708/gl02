"""按三规二制顺序排列候选动作，并保留被跳过步骤。"""

from __future__ import annotations

from typing import Any


SCHEME_ORDER = {
    "safety": 0,
    "upper": 10,
    "lower": 20,
    "burden": 30,
    "basicity": 40,
    "integrated": 50,
}


def plan_action_sequence(
    actions: list[dict[str, Any]], diagnosis: dict[str, Any]
) -> list[dict[str, Any]]:
    """安全动作优先；热制度链按原文章节顺序，不丢 blocked/needs_data。"""
    active = {
        str(diagnosis.get("main_label") or "normal"),
        str(diagnosis.get("secondary_label") or ""),
    }
    thermal_chain = "thermal_down" if "cold" in active else "thermal_up" if "hot" in active else None

    def sort_key(action: dict[str, Any]) -> tuple[int, int, str]:
        scheme = str(action.get("scheme") or "integrated")
        rank = int((action.get("sequence") or {}).get("rank", 999))
        if scheme == "safety":
            return (0, rank, str(action.get("id")))
        if thermal_chain:
            return (10 + rank, SCHEME_ORDER.get(scheme, 99), str(action.get("id")))
        return (SCHEME_ORDER.get(scheme, 99), rank, str(action.get("id")))

    planned = sorted(actions, key=sort_key)
    for position, action in enumerate(planned, start=1):
        sequence = action.setdefault("sequence", {})
        sequence["position"] = position
        sequence["active_chain"] = thermal_chain or "condition_specific"
    return planned
