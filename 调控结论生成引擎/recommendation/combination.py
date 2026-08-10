"""主、次炉况的通用组合摘要。"""

from __future__ import annotations

from typing import Any


DISPLAY_LABELS = {
    "normal": "正常顺行",
    "cold": "热制度下行",
    "hot": "热制度上行",
    "lowline": "低料线",
    "edge": "边缘发展",
    "center": "中心发展",
    "channel": "管道",
    "column": "悬料",
}


def apply_combination_rules(
    recommendation: dict[str, Any], diagnosis_result: dict[str, Any]
) -> dict[str, Any]:
    """对任意主次炉况生成组合标识；动作冲突由通用解析器处理。"""
    main_label = str(diagnosis_result.get("main_label") or "normal")
    secondary_label = diagnosis_result.get("secondary_label")
    main_name = DISPLAY_LABELS.get(main_label, main_label)
    recommendation["explanation"] = (
        f"当前主要炉况为{main_name}。建议已按三规二制的动作资格、顺序、"
        "安全门禁和审批边界逐条评估。"
    )

    if secondary_label and secondary_label != main_label:
        secondary_label = str(secondary_label)
        secondary_name = DISPLAY_LABELS.get(secondary_label, secondary_label)
        recommendation["combined_mode"] = f"{secondary_label}_plus_{main_label}"
        recommendation["explanation"] = (
            f"当前主要炉况为{main_name}，同时伴随{secondary_name}。"
            "引擎已合并两类候选，保留缺失步骤，并让安全、失常和减量规则"
            "优先于相反方向动作。"
        )

    return recommendation
