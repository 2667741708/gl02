from __future__ import annotations

import importlib.util
import sys
from datetime import datetime
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "高炉前端数据" / "智能助手" / "backend" / "hcz_upward_rule_api.py"


def load_module():
    name = "hcz_upward_rule_api_test"
    spec = importlib.util.spec_from_file_location(name, MODULE_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    module.clear_cache()
    return module


class FakeConnection:
    def __init__(self, rows):
        self.rows = rows
        self.calls = []

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return None

    def execute(self, sql, params):
        self.calls.append((sql, params))
        if "max(v.ts)" in sql:
            return FakeCursor([{"latest_ts": datetime(2026, 8, 10, 12, 45)}])
        return FakeCursor(self.rows)


class FakeCursor:
    def __init__(self, rows):
        self.rows = rows

    def fetchone(self):
        return self.rows[0] if self.rows else None

    def fetchall(self):
        return self.rows


def test_adapter_uses_registry_hourly_aggregation_and_read_only_source(monkeypatch) -> None:
    module = load_module()
    captured = {}

    def fake_evaluate(rows, *, evaluation_time):
        captured["rows"] = rows
        captured["evaluation_time"] = evaluation_time
        return {"ok": True, "status": "not_triggered", "triggered": False}

    monkeypatch.setattr(module, "evaluate_hcz_upward_rule", fake_evaluate)
    connection = FakeConnection([{"bucket": datetime(2026, 8, 10, 12), "variable_name": "DP_total", "value": 1.0, "sample_count": 45}])

    result = module.evaluate_latest(lambda: connection)

    assert result["source"]["read_only"] is True
    assert result["source"]["hourly_record_count"] == 1
    assert result["source"]["variable_count"] == 65
    assert captured["evaluation_time"] == datetime(2026, 8, 10, 12)
    assert "GROUP BY date_trunc('hour', v.ts)" in connection.calls[1][0]
    assert not any(word in connection.calls[1][0].upper() for word in ("INSERT", "UPDATE", "DELETE"))
    assert result["source"]["gas_utilisation_normalised"] is True


def test_adapter_cache_avoids_requery(monkeypatch) -> None:
    module = load_module()
    monkeypatch.setattr(
        module,
        "evaluate_hcz_upward_rule",
        lambda *_args, **_kwargs: {"ok": True, "status": "not_triggered", "triggered": False},
    )
    connection = FakeConnection([])

    first = module.evaluate_latest(lambda: connection)
    second = module.evaluate_latest(lambda: connection)

    assert first["cache"] == "miss"
    assert second["cache"] == "hit"
    assert len(connection.calls) == 2


def test_adapter_raises_safe_error_when_latest_data_missing() -> None:
    module = load_module()

    class EmptyConnection(FakeConnection):
        def execute(self, sql, params):
            return FakeCursor([{"latest_ts": None}])

    try:
        module.evaluate_latest(lambda: EmptyConnection([]))
    except module.HczUpwardRuleDataError as exc:
        assert "没有可用" in str(exc)
    else:
        raise AssertionError("missing latest data was accepted")


def test_8093_server_exposes_read_only_rule_route_and_static_page() -> None:
    server = (MODULE_PATH.parent / "ollama_proxy_server.py").read_text(encoding="utf-8")
    page = (ROOT / "高炉前端数据" / "hcz_upward_rule.html").read_text(encoding="utf-8")

    assert 'parsed.path == "/api/hcz-upward-rule"' in server
    assert 'parsed.path == "/api/hcz-rule-sensitivity"' in server
    assert "hcz_upward_rule_api.evaluate_latest(self.pg_connect)" in server
    assert "hcz_upward_rule_api.evaluate_sensitivity(self.pg_connect, query_string)" in server
    assert 'fetch(`/api/hcz-upward-rule?t=${Date.now()}`' in (
        ROOT / "高炉前端数据" / "assets" / "hcz-upward-rule.js"
    ).read_text(encoding="utf-8")
    assert "严格AND组合" in page
    assert "禁止自动控制" in page
    assert "只读试算" in page


def test_rule_config_uses_cold_blast_pressure_source() -> None:
    config = (ROOT / "炉况规则引擎" / "config" / "hcz_upward_expert_rule.yaml").read_text(encoding="utf-8")

    assert "label: 冷风风压" in config
    assert "variables: [P_blast_cold]" in config
    assert "label: 热风压力" not in config


def test_adapter_converts_gas_util_fraction_to_percentage_points(monkeypatch) -> None:
    module = load_module()
    captured = {}

    def fake_evaluate(rows, *, evaluation_time):
        captured["rows"] = rows
        return {"ok": True, "status": "not_triggered", "triggered": False}

    monkeypatch.setattr(module, "evaluate_hcz_upward_rule", fake_evaluate)
    connection = FakeConnection([
        {"bucket": datetime(2026, 8, 10, 12), "variable_name": "GasUtil", "value": 0.456, "sample_count": 60},
    ])

    module.evaluate_latest(lambda: connection)

    assert captured["rows"][0]["value"] == 45.6


def test_sensitivity_api_reuses_read_only_history_and_validates_query(monkeypatch) -> None:
    module = load_module()
    captured = {}

    def fake_sensitivity(rows, hours, *, threshold_overrides):
        captured["rows"] = rows
        captured["hours"] = hours
        captured["threshold_overrides"] = threshold_overrides
        return {"ok": True, "baseline": {}, "scenario": {}, "comparison": {}}

    monkeypatch.setattr(module, "evaluate_hcz_rule_sensitivity", fake_sensitivity)
    connection = FakeConnection([
        {"bucket": datetime(2026, 8, 10, 12), "variable_name": "GasUtil", "value": 0.45, "sample_count": 60},
    ])

    first = module.evaluate_sensitivity(
        lambda: connection,
        "days=7&top_temperature_delta_c=10&required_consecutive_hours=8",
    )
    second = module.evaluate_sensitivity(
        lambda: connection,
        "days=7&top_temperature_delta_c=9",
    )

    assert first["source"]["read_only"] is True
    assert first["source"]["history_cache"] == "miss"
    assert second["source"]["history_cache"] == "hit"
    assert len(connection.calls) == 2
    assert len(captured["hours"]) == 7 * 24
    assert captured["rows"][0]["value"] == 45.0
    assert captured["threshold_overrides"]["top_temperature_delta_c"] == 9.0
    assert not any(word in connection.calls[1][0].upper() for word in ("INSERT", "UPDATE", "DELETE"))

    try:
        module.evaluate_sensitivity(lambda: connection, "days=91")
    except module.HczRuleSensitivityValidationError:
        pass
    else:
        raise AssertionError("out-of-range sensitivity history was accepted")
