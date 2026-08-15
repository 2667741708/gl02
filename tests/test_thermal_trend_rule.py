from __future__ import annotations

import importlib.util
import json
import uuid
from datetime import datetime, timezone
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "高炉前端数据" / "智能助手" / "backend"
MODULE_PATH = BACKEND / "thermal_trend_rule.py"
CONFIG_PATH = BACKEND / "config" / "thermal_trend_rule.v1.json"


def load_module():
    spec = importlib.util.spec_from_file_location("thermal_trend_rule_under_test", MODULE_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_production_config_is_valid_and_has_eight_weighted_metrics() -> None:
    module = load_module()
    config = module.load_config(CONFIG_PATH)

    assert config["requirement_id"] == "REQ-8093-THERMAL-TREND-20260813"
    assert len(config["metrics"]) == 8
    assert sum(float(item["weight"]) for item in config["metrics"]) == pytest.approx(100.0)
    assert config["window_minutes"] == 30
    baseline = config["baseline_monitoring"]
    assert len(baseline["metrics"]) == 8
    assert baseline["top_temperature"]["normal_max_pair_delta"] == 5
    assert baseline["top_temperature"]["alarm_max_pair_delta"] == 10


def test_invalid_weight_total_is_rejected() -> None:
    module = load_module()
    config = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    config["metrics"][0]["weight"] = 19

    with pytest.raises(ValueError, match="权重合计"):
        module.validate_config(config)


def test_condition_is_atomic_and_expires() -> None:
    module = load_module()
    temp_dir = ROOT / ".pytest_tmp_thermal_trend"
    temp_dir.mkdir(exist_ok=True)
    path = temp_dir / f"condition-{uuid.uuid4().hex}.json"
    now = datetime(2026, 8, 14, 0, 0, tzinfo=timezone.utc)
    try:
        active = module.write_condition(
            path,
            state="not_drained",
            actor="test-operator",
            role="operator",
            ttl_minutes=30,
            reason="fixture",
            now=now,
        )
        expired = module.read_condition(
            path,
            now=datetime(2026, 8, 14, 1, 0, tzinfo=timezone.utc),
        )

        assert active["active"] is True
        assert active["state"] == "not_drained"
        assert expired["active"] is False
        assert expired["state"] == "unknown"
    finally:
        path.unlink(missing_ok=True)


def test_proxy_keeps_thermal_routes_and_authorization_contract() -> None:
    source = (BACKEND / "ollama_proxy_server.py").read_text(encoding="utf-8")

    for route in (
        '"/api/thermal-trend"',
        '"/api/admin/thermal-trend/config"',
        '"/api/admin/thermal-trend/config/publish"',
        '"/api/thermal-trend/condition"',
    ):
        assert route in source
    assert '_abc_admin_write_required("publish-thermal-trend-config")' in source
    assert '_abc_operator_write_required("confirm-thermal-trend-condition")' in source
    assert '"automatic_control": "prohibited"' in MODULE_PATH.read_text(encoding="utf-8")


def test_foreman_frontend_and_backend_keep_baseline_monitoring_contract() -> None:
    module_source = MODULE_PATH.read_text(encoding="utf-8")
    frontend_source = (ROOT / "高炉前端数据" / "assets" / "abc-furnace-rules-production.js").read_text(
        encoding="utf-8"
    )

    assert "def _baseline_monitoring" in module_source
    assert '"baseline_monitoring": baseline_monitoring' in module_source
    assert "current_monitoring" in module_source
    assert "['FOREMAN','工长偏好']" in frontend_source
    assert "fetch('/api/thermal-trend'" in frontend_source
    assert "baselineMonitoringHtmlSafe" in frontend_source
    assert "基准偏差预警" in frontend_source
    assert "炉温趋势研判" in frontend_source
    assert "abc33-foreman-subtabs" in frontend_source
    assert "const rows=[...items].sort" in frontend_source
