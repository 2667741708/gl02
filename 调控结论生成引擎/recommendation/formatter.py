"""完整动作契约与旧前端动作数组的双向兼容格式化。"""

from __future__ import annotations

from typing import Any

from .action_contract import validate_action_contract


class RecommendationFormatter:
    """保留完整动作，同时派生旧版三组数组，避免现有页面中断。"""

    @staticmethod
    def _legacy_item(action: dict[str, Any]) -> dict[str, Any]:
        status = str(action.get("status"))
        if status == "blocked":
            reason = "；".join(action.get("blocking_reasons") or [])
        elif status == "needs_data":
            reason = "缺少数据：" + "、".join(action.get("missing_inputs") or [])
        elif status == "manual_confirm":
            reason = "属于人工/专项流程，必须完成现场审批"
        else:
            reason = "触发证据与前置条件已满足，仍须遵守现场审批边界"
        return {
            "id": action["id"],
            "text": action["user_facing_text"],
            "reason": reason,
            "source": "safety_gate" if action["scheme"] == "safety" else "three_rules_two_systems",
            "status": status,
            "scheme": action["scheme"],
            "source_refs": list(action.get("source_refs") or []),
            "sequence": dict(action.get("sequence") or {}),
            "missing_inputs": list(action.get("missing_inputs") or []),
            "blocking_reasons": list(action.get("blocking_reasons") or []),
            "delta": action.get("delta"),
            "observation_window": action.get("observation_window"),
            "approval": action.get("approval"),
            "read_only": True,
        }

    @staticmethod
    def format(raw_recommendation: dict[str, Any]) -> dict[str, Any]:
        final_output = raw_recommendation.copy()
        actions = [dict(action) for action in final_output.get("actions", [])]
        for action in actions:
            validate_action_contract(action)

        immediate: list[dict[str, Any]] = []
        followup: list[dict[str, Any]] = []
        forbidden: list[dict[str, Any]] = []
        for action in actions:
            legacy = RecommendationFormatter._legacy_item(action)
            if action["status"] == "blocked":
                forbidden.append(legacy)
            elif action.get("legacy_stage") == "immediate":
                immediate.append(legacy)
            else:
                followup.append(legacy)

        counts = {status: 0 for status in ("eligible", "blocked", "needs_data", "manual_confirm")}
        for action in actions:
            counts[action["status"]] += 1
        final_output["actions"] = actions
        final_output["immediate_actions"] = immediate
        final_output["followup_actions"] = followup
        final_output["forbidden_actions"] = forbidden
        final_output["needs_data_actions"] = [
            RecommendationFormatter._legacy_item(action)
            for action in actions
            if action["status"] == "needs_data"
        ]
        final_output["action_status_counts"] = counts
        final_output["operator_confirm_required"] = any(
            action.get("approval", {}).get("required")
            and action["status"] in {"eligible", "manual_confirm"}
            for action in actions
        )
        return final_output
