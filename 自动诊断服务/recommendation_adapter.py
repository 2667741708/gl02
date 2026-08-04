"""把数据库炉况诊断适配为完整调控结论。

对应需求：REQ-OPT-FULL-ENGINE-20260715。
该模块只生成只读建议，不执行任何生产控制写入。
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_ENGINE_DIR = PROJECT_ROOT / "调控结论生成引擎"
ENGINE_DIR = Path(os.getenv("BF_RECOMMENDATION_ENGINE_DIR", str(DEFAULT_ENGINE_DIR))).resolve()
if str(ENGINE_DIR) not in sys.path:
    sys.path.insert(0, str(ENGINE_DIR))

from recommendation.core import RecommendationEngine  # noqa: E402


ENGINE_NAME = "blast_furnace_recommendation_engine"
ENGINE_VERSION = "v4-complete"
_ENGINE = RecommendationEngine()


def _finite(value: object) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if number == number and number not in (float("inf"), float("-inf")) else None


def _first_number(*values: object, default: float = 0.0) -> float:
    for value in values:
        number = _finite(value)
        if number is not None:
            return number
    return default


def build_features_snapshot(
    diagnosis: dict[str, Any], current_values: dict[str, Any] | None = None
) -> dict[str, Any]:
    """兼容数据库 ``feature_snapshot`` 与历史引擎 ``features_snapshot`` 字段。"""
    current = current_values or {}
    stored = diagnosis.get("features_snapshot") or diagnosis.get("feature_snapshot") or {}
    features = dict(stored) if isinstance(stored, dict) else {}

    top_candidates = [
        features.get("Ttop_max15"),
        features.get("T_top_max15"),
        features.get("T_top_effective"),
        features.get("T_top"),
        current.get("T_top"),
        current.get("T_top_A"),
        current.get("T_top_B"),
        current.get("T_top_C"),
        current.get("T_top_D"),
    ]
    top_values = [number for number in (_finite(value) for value in top_candidates) if number is not None]
    p_top = _first_number(features.get("P_top"), current.get("P_top"))
    line = _first_number(features.get("L_current"), current.get("L"), default=1.5)

    features["high_pressure_flag"] = int(
        bool(features.get("high_pressure_flag")) or p_top > 200.0
    )
    features["probe_stall_flag"] = int(bool(features.get("probe_stall_flag", 0)))
    features["tuyere_abnormal_flag"] = int(bool(features.get("tuyere_abnormal_flag", 0)))
    features["TRT_running_flag"] = int(bool(features.get("TRT_running_flag", 0)))
    features["Ttop_max15"] = max(top_values) if top_values else 0.0
    features["DeltaL"] = _first_number(features.get("DeltaL"), default=line - 1.5)
    return features


def generate_recommendation(
    diagnosis: dict[str, Any], current_values: dict[str, Any] | None = None
) -> dict[str, Any]:
    """使用完整建议引擎生成结构化建议并附带可审计元数据。"""
    normalized = dict(diagnosis)
    normalized["features_snapshot"] = build_features_snapshot(normalized, current_values)
    recommendation = _ENGINE.generate(normalized)
    recommendation["engine_meta"] = {
        "name": ENGINE_NAME,
        "version": ENGINE_VERSION,
        "source": "diagnosis_snapshot",
        "read_only": True,
    }
    return recommendation

