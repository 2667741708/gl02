from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "高炉前端数据" / "智能助手" / "mcp" / "imes_web_mcp_server.py"
SPEC = importlib.util.spec_from_file_location("imes_web_mcp_server_tests", MODULE_PATH)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


def test_web_dataset_catalog_is_allowlisted_and_readonly():
    result = MODULE.list_imes_web_datasets()
    assert result["ok"] is True
    assert result["read_policy"] == "readonly"
    assert len(result["datasets"]) == 12
    assert {item["dataset"] for item in result["datasets"]} >= {"output", "heat_lab", "slag_lab"}


def test_web_query_requires_captcha_without_leaking_credentials(monkeypatch):
    monkeypatch.delenv("IMES_WEB_SESSION_COOKIE", raising=False)
    monkeypatch.delenv("IMES_WEB_CAPTCHA", raising=False)
    result = MODULE.query_imes_web_dataset("output", "2026-08-05", "2026-08-05")
    assert result["ok"] is False
    assert result["error"] == "IMES_WEB_CAPTCHA_REQUIRED"
    assert "password" not in str(result).lower()


def test_web_query_rejects_unknown_dataset_before_network():
    result = MODULE.query_imes_web_dataset("arbitrary_sql", "2026-08-05", "2026-08-05")
    assert result["ok"] is False
    assert result["error"] == "UNKNOWN_IMES_WEB_DATASET"
