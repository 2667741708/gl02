"""将炉况诊断分数映射为建议严重度。"""


def map_severity(score: object) -> str:
    """返回 ``low/medium/high/critical`` 严重度。"""
    try:
        value = float(score)
    except (TypeError, ValueError):
        value = 0.0
    if value >= 85:
        return "critical"
    if value >= 75:
        return "high"
    if value >= 60:
        return "medium"
    return "low"
