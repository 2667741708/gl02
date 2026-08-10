"""Surgically fix ABC33 live-value/quality wiring on the 220.12 V4 runtime."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import py_compile
import shutil
from datetime import datetime
from pathlib import Path


MARKER = "BUG-ABC33-LIVE-DATA-WIRING-20260808-R1"
PAGE_VERSION = "abc33-20260808-r4-live-data-fix"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def atomic_text(path: Path, text: str) -> None:
    temp = path.with_name(path.name + ".abc33-live.tmp")
    temp.write_text(text, encoding="utf-8", newline="\n")
    os.replace(temp, path)


def patch_bridge(path: Path) -> None:
    text = path.read_text(encoding="utf-8")
    if MARKER in text:
        return
    import_anchor = "from abc_rule_engine import evaluate as evaluate_abc  # ABC33\n"
    if import_anchor not in text:
        raise RuntimeError("ABC33 bridge import anchor is missing")
    text = text.replace(
        import_anchor,
        "from abc_feature_builder import build_feature_snapshot as build_abc_feature_snapshot  # ABC33\n"
        + import_anchor,
        1,
    )
    old = '''        else:
            features = payload.get("feature_snapshot") or row.get("feature_snapshot") or {}
            coverage = (row.get("data_coverage") or {}).get("coverage_ratio", 0.0)
            abc_internal = evaluate_abc(features, quality={"coverage_ratio": coverage, "data_age_seconds": row.get("source_lag_seconds")}, timestamp=timestamp)
        if audit_conn is not None and abc_internal.get("evaluations"):
            try:
                persist_abc_bundle(audit_conn, abc_internal, source_snapshot_id=row.get("id"))
            except Exception:
                pass
        payload["abc_rule_bundle"] = abc_internal.get("public", {"schema_version": "abc_rule_bundle.v1", "rules": [], "alerts": []})
'''
    new = '''        else:
            # BUG-ABC33-LIVE-DATA-WIRING-20260808-R1: combine live raw values
            # with the legacy derived snapshot and read quality from the JSON
            # payload.  The previous adapter read unselected SQL columns,
            # forcing coverage to zero for every ABC rule.
            combined_values = dict(current_values or {})
            combined_values.update(payload.get("feature_snapshot") or row.get("feature_snapshot") or {})
            coverage_source = payload.get("data_coverage") or row.get("data_coverage") or {}
            coverage = finite_float(coverage_source.get("coverage_ratio"))
            source_age = finite_float(payload.get("source_lag_seconds"))
            if source_age is None:
                source_age = finite_float(row.get("source_lag_seconds"))
            abc_features, abc_quality = build_abc_feature_snapshot(
                combined_values,
                data_age_seconds=source_age,
                coverage_ratio=coverage if coverage is not None else 0.0,
            )
            abc_internal = evaluate_abc(abc_features, quality=abc_quality, timestamp=timestamp)
        if audit_conn is not None and abc_internal.get("evaluations"):
            persist_abc_bundle(audit_conn, abc_internal, source_snapshot_id=row.get("id"))
        payload["abc_rule_bundle"] = abc_internal.get("public", {"schema_version": "abc_rule_bundle.v1", "rules": [], "alerts": []})
'''
    if old not in text:
        raise RuntimeError("ABC33 zero-coverage block is missing or changed")
    atomic_text(path, text.replace(old, new, 1))


def patch_page(path: Path) -> None:
    text = path.read_text(encoding="utf-8")
    import re
    updated, count = re.subn(
        r'assets/abc-furnace-rules-production\.js\?v=[^"\']+',
        f"assets/abc-furnace-rules-production.js?v={PAGE_VERSION}",
        text,
        count=1,
    )
    if count != 1:
        raise RuntimeError("ABC33 page asset reference is missing")
    atomic_text(path, updated)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", required=True)
    parser.add_argument("--asset", required=True)
    args = parser.parse_args()
    root = Path(args.root)
    bridge = root / "自动诊断服务" / "local_pg_ws_bridge.py"
    page = root / "高炉前端数据" / "frontend_dashboard_v3.8094_preview.server.html"
    asset = root / "高炉前端数据" / "assets" / "abc-furnace-rules-production.js"
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup = root / "backups" / "abc33_live_data_fix_8094" / stamp
    backup.mkdir(parents=True, exist_ok=True)
    for source in (bridge, page, asset):
        shutil.copy2(source, backup / source.name)
    patch_bridge(bridge)
    shutil.copy2(Path(args.asset), asset)
    patch_page(page)
    py_compile.compile(str(bridge), doraise=True)
    print(json.dumps({
        "ok": True,
        "marker": MARKER,
        "version": PAGE_VERSION,
        "backup": str(backup),
        "bridge_sha256": sha256(bridge),
        "page_sha256": sha256(page),
        "asset_sha256": sha256(asset),
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
