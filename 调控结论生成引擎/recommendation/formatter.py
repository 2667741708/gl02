"""调控建议前端输出格式化。"""

from __future__ import annotations

from typing import Any


class RecommendationFormatter:
    """把安全门禁动作合并到标准即时动作列表。"""

    @staticmethod
    def format(raw_recommendation: dict[str, Any]) -> dict[str, Any]:
        final_output = raw_recommendation.copy()
        immediate = [dict(item) for item in final_output.get("immediate_actions", [])]
        for text in reversed(final_output.pop("forced_actions", [])):
            immediate.insert(
                0,
                {
                    "id": "safety_forced",
                    "text": text,
                    "reason": "触发安全红线约束",
                    "source": "safety_gate",
                },
            )
        final_output["immediate_actions"] = immediate
        return final_output
