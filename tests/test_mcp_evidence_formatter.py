from __future__ import annotations

import importlib
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "高炉前端数据" / "智能助手" / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))


def _proxy():
    return importlib.import_module("ollama_proxy_server")


def test_latest_sensor_answer_includes_unit_time_quality_collection_and_source() -> None:
    payload = {"ok": True, "items": [{
        "requested_variable": "P_top", "ok": True, "variable": {"unit": ""},
        "latest": {"value": 255.4, "ts": "2026-08-14T00:20:00", "quality": "Good", "collected_at": "2026-08-14T00:21:00"},
        "source": {"profile": "bf_sensor_postgresql", "read_policy": "readonly", "dsn_env": "SECRET"},
    }]}
    answer = _proxy().deterministic_mcp_answer("query_gl02_sensors", json.dumps(payload, ensure_ascii=False))
    for token in ("P_top", "kPa", "数据时间", "质量 Good", "采集时间", "来源：bf_sensor_postgresql / readonly"):
        assert token in answer
    assert "SECRET" not in answer


def test_statistics_answer_contains_complete_t2_contract_and_cv() -> None:
    stats = {"count": 60, "avg": 250.0, "min": 240.0, "max": 260.0, "stddev": 5.0,
             "slope_per_min": -0.2, "first": {"ts": "t1", "value": 252.0},
             "last": {"ts": "t2", "value": 248.0}, "delta": -4.0, "trend": "下降"}
    payload = {"ok": True, "start_time": "2026-08-14T00:00:00+08:00", "end_time": "2026-08-14T01:00:00+08:00",
               "items": [{"requested_variable": "P_top", "ok": True, "variable": {"unit": "kPa"},
                          "statistics": stats, "source": {"profile": "bf_sensor_postgresql", "read_policy": "readonly"}}]}
    answer = _proxy().deterministic_mcp_answer("query_gl02_sensors", json.dumps(payload, ensure_ascii=False))
    for token in ("样本数 60", "STDDEV_POP 5kPa", "极差 20kPa", "首值 252kPa", "末值 248kPa",
                  "变化量 -4kPa", "每分钟斜率 -0.2kPa/min", "CV = STDDEV_POP ÷ 均值 × 100% = 2%"):
        assert token in answer
