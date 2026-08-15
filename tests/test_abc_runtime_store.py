from __future__ import annotations

import importlib
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SERVICE = ROOT / "自动诊断服务"
if str(SERVICE) not in sys.path:
    sys.path.insert(0, str(SERVICE))

abc_runtime_store = importlib.import_module("abc_runtime_store")


class _Row:
    def fetchone(self):
        return {"id": 17}


class _Connection:
    def __init__(self):
        self.calls: list[tuple[str, tuple]] = []
        self.committed = False

    def execute(self, sql: str, params: tuple):
        self.calls.append((sql, params))
        return _Row()

    def commit(self):
        self.committed = True


def test_conflict_refreshes_catalog_metadata_and_public_bundle():
    conn = _Connection()
    bundle = {
        "evaluation_ts": "2026-08-10 12:38:00",
        "catalog_version": "abc33-catalog.v3.handbook64-guidance",
        "config_version": "abc33-rules.v1",
        "config_hash": "same-config-hash",
        "quality": {"coverage_ratio": 1.0, "data_age_seconds": 10.0},
        "public": {"rules": []},
        "evaluations": [],
    }

    assert abc_runtime_store.persist_bundle(conn, bundle) == 17
    sql = conn.calls[0][0]
    assert "catalog_version=excluded.catalog_version" in sql
    assert "config_version=excluded.config_version" in sql
    assert "coverage_ratio=excluded.coverage_ratio" in sql
    assert "data_age_seconds=excluded.data_age_seconds" in sql
    assert "public_bundle=excluded.public_bundle" in sql
    assert conn.committed is True
