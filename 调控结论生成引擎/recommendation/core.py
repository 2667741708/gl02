"""高炉调控结论生成引擎入口。"""

from __future__ import annotations

import datetime
from typing import Any

from .action_templates import ACTION_TEMPLATES
from .combination import apply_combination_rules
from .conflict_resolver import resolve_action_conflicts
from .formatter import RecommendationFormatter
from .policy_evaluator import evaluate_policy_actions, load_policy_catalog
from .safety_gate import evaluate_safety_gate
from .sequence_planner import plan_action_sequence
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

        safety_result = evaluate_safety_gate(diagnosis_result)
        actions = evaluate_policy_actions(diagnosis_result, safety_result)
        actions = resolve_action_conflicts(actions, diagnosis_result, safety_result)
        actions = plan_action_sequence(actions, diagnosis_result)
        recommendation: dict[str, Any] = {
            "timestamp": diagnosis_result.get("timestamp")
            or datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "schema_version": load_policy_catalog()["schema_version"],
            "main_label": main_label,
            "secondary_label": diagnosis_result.get("secondary_label"),
            "severity": severity,
            "goal": template["goal"],
            "actions": actions,
            "observe_items": list(template["observe_items"]),
            "recheck_minutes": template["recheck_minutes"].get(severity, 15),
            "operator_confirm_required": False,
            "combined_mode": None,
            "explanation": "",
        }

        recommendation["safety_gate_passed"] = safety_result["safety_gate_passed"]
        recommendation["safety_warnings"] = safety_result["safety_warnings"]
        recommendation = apply_combination_rules(recommendation, diagnosis_result)
        return self.formatter.format(recommendation)
