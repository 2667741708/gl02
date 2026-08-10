from __future__ import annotations

import importlib.util
import sys
from datetime import date, datetime, timedelta
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SERVICE = ROOT / "自动诊断服务"
sys.path.insert(0, str(SERVICE))
import local_pg_ws_bridge as bridge  # noqa: E402
import diagnosis_scheduler as scheduler  # noqa: E402
import pandas as pd  # noqa: E402


def load_replay():
    path = ROOT / "tools" / "replay_abc33_rules.py"
    spec = importlib.util.spec_from_file_location("replay_abc33_rules", path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


class Result:
    def __init__(self, rows):
        self.rows = rows

    def fetchone(self):
        return self.rows[0] if self.rows else None

    def fetchall(self):
        return self.rows


class FakeConnection:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def execute(self, query, params=None):
        self.calls.append((" ".join(query.split()), params))
        return Result(self.responses.pop(0))


def test_empty_production_history_does_not_expose_internal_abc_inputs():
    payload = bridge.empty_history_payload()
    assert "Q_blast" in payload
    assert "Q_N2" not in payload
    assert "Q_soft_water" not in payload


def test_baseline_lookup_is_as_of_evaluation_day():
    conn = FakeConnection([
        [{"day": date(2026, 8, 7)}],
        [{"variable_name": "P_top", "median_ref": 250, "iqr_ref": 4, "p25": 248, "p75": 252,
          "coverage_ratio": .99, "sample_count": 42000, "baseline_day": date(2026, 8, 7),
          "baseline_window_start": datetime(2026, 7, 8), "baseline_window_end": datetime(2026, 8, 6, 23, 59),
          "updated_at": datetime(2026, 8, 7, 0, 5)}],
    ])
    result = bridge.fetch_abc_baselines(conn, datetime(2026, 8, 7, 12))
    assert result["P_top"]["p25"] == 248
    assert conn.calls[0][1] == (date(2026, 8, 7),)


def test_internal_history_has_complete_minute_grid_and_keeps_gaps():
    end = datetime(2026, 8, 8, 12, 2)
    conn = FakeConnection([
        [{"variable_name": "Q_N2", "tag_long_name": "tag-n2"}],
        [
            {"tag_long_name": "tag-n2", "minute_ts": end-timedelta(minutes=2), "value": 10},
            {"tag_long_name": "tag-n2", "minute_ts": end, "value": 12},
        ],
    ])
    history = bridge.fetch_abc_history(conn, end-timedelta(minutes=2), end)
    assert len(history["timestamps"]) == 3
    assert history["Q_N2"] == [10.0, None, 12.0]
    assert "date_trunc('minute', ts)" in conn.calls[1][0]


def test_bridge_aligned_current_never_mixes_different_minutes():
    history = {
        "timestamps": ["2026-08-08 12:00:00", "2026-08-08 12:01:00"],
        "T_top_A": [120.0, None],
        "T_top_B": [121.0, 122.0],
        "T_top_C": [123.0, 124.0],
        "T_top_D": [125.0, 126.0],
    }
    current = bridge.abc_aligned_current(history)
    assert "T_top_A" not in current
    assert current["T_top_B"] == 122.0


def test_replay_window_preserves_90_minute_alignment_and_fresh_value():
    replay = load_replay()
    anchor = datetime(2026, 8, 8, 12, 0)
    samples = [(anchor-timedelta(minutes=2), 1.0), (anchor, 2.0)]
    indexed = {"P_top": ([item[0] for item in samples], samples)}
    current, history, age = replay._window(indexed, anchor)
    assert len(history["timestamps"]) == 90
    assert history["P_top"][-3:] == [1.0, None, 2.0]
    assert current["P_top"] == 2.0
    assert age == 0.0


def test_replay_supports_bounded_small_window_dry_run(monkeypatch):
    replay = load_replay()
    monkeypatch.setattr(sys, "argv", ["replay_abc33_rules.py", "--hours", "2", "--max-batches", "5",
                                     "--max-samples-per-feature", "100"])
    args = replay.arguments()
    assert args.hours == 2
    assert args.max_batches == 5
    assert args.max_samples_per_feature == 100


def test_rule_shadow_evaluation_requires_explicit_cli_switch(monkeypatch):
    replay = load_replay()
    monkeypatch.setattr(sys, "argv", ["replay_abc33_rules.py", "--hours", "1"])
    assert replay.arguments().evaluate_rules_shadow is False
    monkeypatch.setattr(sys, "argv", ["replay_abc33_rules.py", "--hours", "1", "--evaluate-rules-shadow"])
    assert replay.arguments().evaluate_rules_shadow is True


def test_replay_percentiles_include_distribution_boundaries():
    replay = load_replay()
    values = [0.0, 10.0, 20.0, 30.0, 40.0]
    assert replay._percentile(values, 0.0) == 0.0
    assert replay._percentile(values, 0.5) == 20.0
    assert replay._percentile(values, 1.0) == 40.0


def test_scheduler_contract_has_90_timestamps_and_same_minute_current():
    end = datetime(2026, 8, 8, 12, 0)
    frame = pd.DataFrame({
        "timestamp": [end-timedelta(minutes=1), end],
        "T_top_A": [120.0, None],
        "T_top_B": [121.0, 122.0],
        "Q_N2": [10.0, 11.0],
    })
    current, history = scheduler.build_abc_runtime_inputs(frame, end)
    assert len(history["timestamps"]) == 90
    assert history["evaluation_ts"].startswith("2026-08-08T12:00")
    assert "T_top_A" not in current
    assert current["T_top_B"] == 122.0
    assert current["Q_N2"] == 11.0
    assert history["T_top_A"][-2:] == [120.0, None]
