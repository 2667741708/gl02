from __future__ import annotations

import importlib.util
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PATH = ROOT / "高炉前端数据" / "智能助手" / "backend" / "qa_evidence_claims.py"
SPEC = importlib.util.spec_from_file_location("qa_evidence_claims", PATH)
assert SPEC and SPEC.loader
claims = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(claims)


def test_reasonable_rounding_is_grounded() -> None:
    evidence = '{"P_top": {"avg": 42.500123, "count": 60}}'
    assert claims.answer_numbers_are_grounded("炉顶压力均值为42.5，样本数60。", evidence)


def test_same_number_on_wrong_object_is_rejected() -> None:
    evidence = '{"P_top": {"avg": 42.5}}'
    assert not claims.answer_numbers_are_grounded("炉顶温度均值为42.5。", evidence)


def test_added_threshold_is_rejected() -> None:
    evidence = '{"P_top": {"avg": 42.5}}'
    assert not claims.answer_numbers_are_grounded("炉顶压力均值为42.5，超过50时报警。", evidence)


def test_exact_question_number_remains_available() -> None:
    assert claims.answer_numbers_are_grounded("三个数的平均值为4。", "", "请计算2、4、6的平均值")
