"""高炉调控结论生成引擎入口。"""

from __future__ import annotations

import datetime
from typing import Any

from .action_templates import ACTION_TEMPLATES
from .combination import apply_combination_rules
from .formatter import RecommendationFormatter
from .safety_gate import evaluate_safety_gate
from .severity_mapper import map_severity


class RecommendationEngine:
    """将标准炉况诊断转换为带安全门禁的结构化调控建议。"""

    def __init__(self) -> None:
        self.templates = ACTION_TEMPLATES
        self.formatter = RecommendationFormatter()

    def generate(self, diagnosis_result: dict[str, Any]) -> dict[str, Any]:
        """生成目标、动作、禁止项、复查周期和安全警示。"""
        main_label = str(diagnosis_result.get("main_label") or "normal")
        main_score = diagnosis_result.get("main_score", 0)
        severity = map_severity(main_score)
        template = self.templates.get(main_label, self.templates["normal"])

        recommendation: dict[str, Any] = {
            "timestamp": diagnosis_result.get("timestamp")
            or datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "main_label": main_label,
            "secondary_label": diagnosis_result.get("secondary_label"),
            "severity": severity,
            "goal": template["goal"],
            "immediate_actions": [dict(item) for item in template["immediate_actions"]],
            "followup_actions": [dict(item) for item in template["followup_actions"]],
            "forbidden_actions": [dict(item) for item in template["forbidden_actions"]],
            "observe_items": list(template["observe_items"]),
            "recheck_minutes": template["recheck_minutes"].get(severity, 15),
            "operator_confirm_required": bool(template["confirm_required"]),
            "combined_mode": None,
            "explanation": f"当前主要炉况为{main_label}，严重程度为{severity}。",
        }

        safety_result = evaluate_safety_gate(diagnosis_result)
        recommendation["safety_gate_passed"] = safety_result["safety_gate_passed"]
        recommendation["safety_warnings"] = safety_result["safety_warnings"]
        recommendation["forced_actions"] = safety_result["forced_actions"]
        forbidden_ids = set(safety_result.get("forbidden_ids", []))
        recommendation["immediate_actions"] = [
            item
            for item in recommendation["immediate_actions"]
            if item.get("id") not in forbidden_ids
        ]
        recommendation = apply_combination_rules(recommendation, diagnosis_result)
        return self.formatter.format(recommendation)
