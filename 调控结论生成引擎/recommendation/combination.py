"""主炉况与次炉况组合修正规则。"""

from __future__ import annotations

from typing import Any


def apply_combination_rules(
    recommendation: dict[str, Any], diagnosis_result: dict[str, Any]
) -> dict[str, Any]:
    """按主次炉况组合修正目标和解释。"""
    main_label = diagnosis_result.get("main_label")
    secondary_label = diagnosis_result.get("secondary_label")

    if {main_label, secondary_label} == {"cold", "lowline"}:
        recommendation["goal"] = "先稳顺行、控料速、控顶温，再逐步补热。"
        recommendation["combined_mode"] = "lowline_plus_cold"
        recommendation["explanation"] = (
            "当前炉温不足且伴随低料线，必须优先控制料速和料柱稳定，"
            "严禁在料线未恢复前大幅提产。"
        )

    if main_label == "cold" and secondary_label == "edge":
        recommendation["combined_mode"] = "edge_plus_cold"
        recommendation["explanation"] = (
            "边缘气流过旺且炉凉，应在补热的同时加强上部布料抑制边缘，"
            "防止热量进一步流失。"
        )

    return recommendation
