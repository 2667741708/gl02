from __future__ import annotations

import importlib
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "高炉前端数据" / "智能助手" / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))


def _module():
    return importlib.import_module("abc_score_explanation")


def _label(term: str) -> str:
    return {"x": "压差", "y": "透气性"}.get(term, term)


def test_a_backward_compatible_entrypoint_remains_a_only() -> None:
    module = _module()
    result = module.build_a_score_explanation(
        category="A",
        score=70,
        status="ready",
        weights={"x": 6, "y": 4},
        contributions={"x": 2, "y": 1},
        label_for=_label,
    )
    assert result is not None
    assert result["state"] == "needs_attention"
    assert result["total_current_deduction_points"] == 30
    assert module.build_a_score_explanation(
        category="B", score=50, status="ready", weights={"x": 1}, contributions={"x": 0.5}, label_for=_label
    ) is None


def test_b_and_c_explanations_use_contribution_semantics_and_thresholds() -> None:
    module = _module()
    below = module.build_score_explanation(
        category="B",
        score=39,
        status="ready",
        weights={"x": 10},
        contributions={"x": 3.9},
        label_for=_label,
    )
    assert below is not None
    assert below["state"] == "below_threshold"
    assert below["score_semantics"] == "risk"

    danger = module.build_score_explanation(
        category="C",
        score=40,
        status="ready",
        weights={"x": 6, "y": 4},
        contributions={"x": 3, "y": 1},
        label_for=_label,
    )
    assert danger is not None
    assert danger["state"] == "needs_attention"
    assert danger["score_semantics"] == "danger"
    assert danger["total_current_contribution_points"] == 40
    assert [item["label"] for item in danger["important_factors"]] == ["压差", "透气性"]
