from __future__ import annotations

import asyncio
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "高炉前端数据" / "智能助手" / "backend"))
import qa_time_window_plan as temporal

ANCHOR = datetime(2026, 9, 16, 10, 0, tzinfo=timezone(timedelta(hours=8)))


def comparison(variables=None):
    return temporal.build_time_window_plan("对比最近30分钟和前30分钟的炉顶压力。", variables or ["P_top"], anchor=ANCHOR)


def stats(step, variable="P_top", avg=100, unit="kPa"):
    return {"ok": True, "variable": {"variable_name": variable, "unit": unit},
            "start_time": step["arguments"]["start_time"], "end_time": step["arguments"]["end_time"],
            "statistics": {"count": 30, "avg": avg}, "source": {"type": "postgresql"}}


def payload(step, **kwargs):
    return {"ok": True, "items": [{"requested_variable": "P_top", "result": stats(step, **kwargs)}]}


def baseline():
    plan = temporal.build_time_window_plan("全炉压差最近一小时相对历史基线偏高吗？", ["DP_total"], anchor=ANCHOR)
    step = plan["steps"][0]
    result = stats(step, variable="DP_total", avg=12)
    result.pop("statistics")
    result.update({"data_limited": False, "features": {"range": {"count": 60, "avg": 12},
        "baseline_30d": {"baseline_window_start": "2026-08-17T00:00:00+08:00", "baseline_window_end": "2026-09-16T00:00:00+08:00",
                         "baseline_days": 30, "variable_name": "DP_total", "median_ref": 10, "iqr_ref": 2, "p90": 11, "coverage_ratio": .95, "sample_count": 41040}},
                   "baseline_source": {"type": "postgresql", "table": "daily_baselines"}})
    return plan, result


def test_adjacent_windows_independently_match_boundary_samples():
    plan = comparison()
    recent, previous = plan["steps"]
    assert recent["arguments"]["start_time"] == "2026-09-16T09:30:00+08:00"
    assert recent["arguments"]["end_time"] == "2026-09-16T09:59:59+08:00"
    assert previous["arguments"]["start_time"] == "2026-09-16T09:00:00+08:00"
    assert previous["arguments"]["end_time"] == "2026-09-16T09:29:59+08:00"
    # Independent discrete minute-sample membership: boundary occurs only once.
    points = [ANCHOR - timedelta(minutes=i) for i in range(61)]
    sets = [{point for point in points if datetime.fromisoformat(s["arguments"]["start_time"]) <= point <= datetime.fromisoformat(s["arguments"]["end_time"])} for s in plan["steps"]]
    assert not sets[0] & sets[1]
    assert len(sets[0]) == len(sets[1]) == 30
    assert ANCHOR - timedelta(minutes=30) in sets[0]


def test_unequal_windows_and_timezone_use_one_anchor():
    plan = temporal.build_time_window_plan("比较最近半小时与前一小时炉顶压力", ["P_top"], anchor=ANCHOR.astimezone(timezone.utc))
    assert plan["anchor"] == ANCHOR.isoformat()
    assert plan["windows"][1]["start"] == "2026-09-16T08:30:00+08:00"


def test_comparison_arithmetic_independent_of_model():
    plan = comparison()
    answer = temporal.format_time_window_answer(plan, {"recent": payload(plan["steps"][0], avg=120), "previous": payload(plan["steps"][1], avg=100)})
    assert answer["complete"] and answer["covered"] == answer["required"] == 2
    assert "= 20 kPa" in answer["answer"] and "20%" in answer["answer"]
    assert "样本数 30" in answer["answer"] and "postgresql" in answer["answer"]


@pytest.mark.parametrize("mutation", ["missing", "wrong_variable", "wrong_time", "zero_count", "nan", "unit"])
def test_missing_or_conflicting_window_never_claims_complete(mutation):
    plan = comparison()
    previous = payload(plan["steps"][1])
    item = previous["items"][0]["result"]
    if mutation == "missing":
        previous = {"ok": False}
    elif mutation == "wrong_variable":
        item["variable"]["variable_name"] = "DP_total"
    elif mutation == "wrong_time":
        item["start_time"] = "2026-09-16T08:00:00+08:00"
    elif mutation == "zero_count":
        item["statistics"]["count"] = 0
    elif mutation == "nan":
        item["statistics"]["avg"] = float("nan")
    else:
        item["variable"]["unit"] = "Pa"
    answer = temporal.format_time_window_answer(plan, {"recent": payload(plan["steps"][0]), "previous": previous})
    assert not answer["complete"]
    assert "均值差" not in answer["answer"]
    assert "证据不完整" in answer["answer"]


def test_baseline_uses_separate_tool_and_independent_formula():
    plan, result = baseline()
    assert plan["steps"][0]["tool"] == "query_gl02_feature_statistics"
    result["features"]["z"] = {"z_range": 999}  # deliberately wrong upstream z
    answer = temporal.format_time_window_answer(plan, {"baseline_0": result})
    assert answer["complete"]
    assert "IQR=1" in answer["answer"] and "高于历史p90" in answer["answer"]
    assert "999" not in answer["answer"] and "不能据此认定生产异常" in answer["answer"]


@pytest.mark.parametrize("mutation", ["missing", "future", "overlap", "coverage", "zero_iqr", "truncated", "wrong_variable"])
def test_baseline_quality_and_temporal_gates(mutation):
    plan, result = baseline()
    ref = result["features"]["baseline_30d"]
    if mutation == "missing":
        result["features"]["baseline_30d"] = None
    elif mutation in ("future", "overlap"):
        ref["baseline_window_end"] = "2026-09-16T11:00:00+08:00" if mutation == "future" else "2026-09-16T09:30:00+08:00"
    elif mutation == "coverage":
        ref["coverage_ratio"] = .2
    elif mutation == "zero_iqr":
        ref["iqr_ref"] = 0
    elif mutation == "wrong_variable":
        ref["variable_name"] = "P_top"
    else:
        result["data_limited"] = True
    answer = temporal.format_time_window_answer(plan, {"baseline_0": result})
    assert not answer["complete"] and "均值 12" in answer["answer"]
    assert "相对基线中位数偏高" not in answer["answer"]


def test_multientity_completeness_requires_every_window():
    plan = comparison(["P_top", "DP_total"])
    answer = temporal.format_time_window_answer(plan, {step["id"]: payload(step) for step in plan["steps"]})
    assert not answer["complete"] and answer["required"] == 4 and answer["covered"] == 2
    assert "DP_total recent：未取得" in answer["answer"]


def test_executor_serial_no_replay_and_preserves_success():
    plan = comparison()
    events = []
    async def call(name, args):
        events.append(("call", args["start_time"]))
        if len([e for e in events if e[0] == "call"]) == 2:
            raise TimeoutError()
        return payload(plan["steps"][0], avg=120)
    answer = asyncio.run(temporal.execute_time_window_plan(plan, available_tools={"query_gl02_sensors"}, validate=lambda n, a: {"ok": True}, call=call,
        on_start=lambda item: events.append(("start", item["step_id"])), on_result=lambda item, result: events.append(("result", item["step_id"])), max_calls=3))
    assert [e[0] for e in events] == ["start", "call", "result", "start", "call", "result"]
    assert not answer["complete"] and "均值 120" in answer["answer"]
    assert answer["model_request_count"] == 0


def test_budget_and_unavailable_tools_do_not_call():
    async def forbidden(*args):
        pytest.fail("must not send")
    for tools, budget in ((set(), 3), ({"query_gl02_sensors"}, 1)):
        answer = asyncio.run(temporal.execute_time_window_plan(comparison(), available_tools=tools, validate=lambda n, a: {"ok": True}, call=forbidden,
            on_start=lambda i: None, on_result=lambda i, r: None, max_calls=budget))
        assert not answer["tool_used"] and not answer["complete"]


def test_unknown_and_quoted_instructions_do_not_guess():
    plan = temporal.build_time_window_plan("对比最近30分钟和前30分钟未知量", [], anchor=ANCHOR)
    assert plan["blocked_reason"] and not plan["steps"]
    assert temporal.build_time_window_plan('解释“对比最近30分钟和前30分钟炉顶压力”是什么意思', ["P_top"], anchor=ANCHOR) is None
    assert temporal.build_time_window_plan("现在炉顶压力是多少", ["P_top"], anchor=ANCHOR) is None
    with pytest.raises(ValueError):
        temporal.build_time_window_plan("最近一小时相对历史基线", ["P_top"], anchor=ANCHOR.replace(tzinfo=None))


@pytest.mark.parametrize("payload", [{"ok": True, "items": None}, {"ok": True, "items": [None]}, {"ok": True, "items": [{"requested_variable": "P_top", "result": "bad"}]}])
def test_malformed_tool_output_fails_closed(payload):
    answer = temporal.format_time_window_answer(comparison(), {"recent": payload})
    assert not answer["complete"] and "证据不完整" in answer["answer"]
