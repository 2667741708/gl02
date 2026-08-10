"""Patch the remote 8094/8768 runtime without replacing unrelated features."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
from datetime import datetime
from pathlib import Path


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def atomic_text(path: Path, text: str) -> None:
    temp = path.with_name(path.name + ".abc33.tmp")
    temp.write_text(text, encoding="utf-8", newline="\n")
    os.replace(temp, path)


def patch_bridge(path: Path) -> None:
    text = path.read_text(encoding="utf-8")
    if "from abc_rule_engine import evaluate as evaluate_abc" not in text:
        text = text.replace("\nHOST =", "\nfrom abc_rule_engine import evaluate as evaluate_abc  # ABC33\nfrom abc_runtime_store import persist_bundle as persist_abc_bundle  # ABC33\n\nHOST =", 1)
    if "internal_abc = payload.pop(\"abc_rule_bundle_internal\"" not in text:
        text = text.replace("    payload = dict(row.get(\"diagnosis_json\") or {}) if include_diagnosis_json else {}\n", "    payload = dict(row.get(\"diagnosis_json\") or {}) if include_diagnosis_json else {}\n    internal_abc = payload.pop(\"abc_rule_bundle_internal\", None)\n    payload.pop(\"abc_rule_bundle_admin\", None)\n", 1)
    marker = "    if include_diagnosis_json:\n"
    if "payload[\"abc_rule_bundle\"]" not in text:
        block = """    try:\n        if isinstance(internal_abc, dict) and internal_abc.get(\"evaluations\"):\n            abc_internal = internal_abc\n        else:\n            features = payload.get(\"feature_snapshot\") or row.get(\"feature_snapshot\") or {}\n            coverage = (row.get(\"data_coverage\") or {}).get(\"coverage_ratio\", 0.0)\n            abc_internal = evaluate_abc(features, quality={\"coverage_ratio\": coverage, \"data_age_seconds\": row.get(\"source_lag_seconds\")}, timestamp=timestamp)\n        if audit_conn is not None and abc_internal.get(\"evaluations\"):\n            try:\n                persist_abc_bundle(audit_conn, abc_internal, source_snapshot_id=row.get(\"id\"))\n            except Exception:\n                pass\n        payload[\"abc_rule_bundle\"] = abc_internal.get(\"public\", {\"schema_version\": \"abc_rule_bundle.v1\", \"rules\": [], \"alerts\": []})\n    except Exception as exc:\n        payload[\"abc_rule_bundle\"] = {\"schema_version\": \"abc_rule_bundle.v1\", \"state\": \"needs_data\", \"error_type\": type(exc).__name__, \"rules\": [], \"alerts\": []}\n"""
        if marker not in text:
            raise RuntimeError("bridge marker not found")
        text = text.replace(marker, block + marker, 1)
    atomic_text(path, text)


def patch_proxy(path: Path, service_dir: str) -> None:
    text = path.read_text(encoding="utf-8")
    if "from abc_rule_engine import public_rule" not in text:
        text = text.replace("INDEX_FILE = os.environ.get(\"BF_INDEX_FILE\", \"frontend_dashboard_v3.server.html\")\n", "INDEX_FILE = os.environ.get(\"BF_INDEX_FILE\", \"frontend_dashboard_v3.server.html\")\nABC_SERVICE_DIR = BASE_DIR.parent / \"自动诊断服务\"\nif str(ABC_SERVICE_DIR) not in sys.path:\n    sys.path.insert(0, str(ABC_SERVICE_DIR))\nfrom abc_rule_engine import public_rule, load_config as load_abc_config  # ABC33\nfrom abc_rule_catalog import RULE_BY_ID  # ABC33\nABC_CONFIG_PATH = ABC_SERVICE_DIR / \"config\" / \"abc_furnace_rules.v1.json\"\n", 1)
    if 'parsed.path == "/api/furnace-rules/latest"' not in text:
        route = '''        if parsed.path == "/api/furnace-rules/latest":\n            self.handle_furnace_rules_latest()\n            return\n        if parsed.path.startswith("/api/furnace-rules/") and parsed.path.endswith("/detail"):\n            self.handle_furnace_rule_detail(unquote(parsed.path).split("/")[3])\n            return\n        if parsed.path.startswith("/api/furnace-rules/") and parsed.path.endswith("/trends"):\n            self.handle_furnace_rule_trends(unquote(parsed.path).split("/")[3])\n            return\n        if parsed.path.startswith("/api/admin/furnace-rules/evaluations/"):\n            self.handle_admin_furnace_rule_detail(unquote(parsed.path))\n            return\n'''
        anchor = '        if parsed.path == "/api/qa/bootstrap":\n'
        if anchor not in text:
            raise RuntimeError("proxy GET route anchor not found")
        text = text.replace(anchor, route + anchor, 1)
    if "def _abc_admin_required" not in text:
        methods = '''    def _abc_connection(self):\n        return _assistant_raw_pg_connect()\n\n    def _abc_admin_required(self) -> bool:\n        session = self.current_review_session()\n        role = str((session or {}).get("role") or "")\n        if not session or not ("admin" in role.lower() or "管理" in role):\n            self.send_json({"ok": False, "error": "admin_required"}, status=403)\n            return False\n        return True\n\n    def handle_furnace_rules_latest(self) -> None:\n        try:\n            with self._abc_connection() as conn:\n                row = conn.execute("SELECT id,evaluation_ts,catalog_version,config_version,public_bundle FROM bf_sensor.abc_rule_evaluation_batches ORDER BY evaluation_ts DESC LIMIT 1").fetchone()\n            if not row:\n                self.send_json({"ok": True, "schema_version": "abc_rule_bundle.v1", "state": "needs_data", "rules": [], "alerts": []})\n                return\n            data = dict(row) if isinstance(row, Mapping) else {"id": row[0], "evaluation_ts": row[1], "catalog_version": row[2], "config_version": row[3], "public_bundle": row[4]}\n            self.send_json({"ok": True, "evaluation_id": data.get("id"), "evaluation_ts": data.get("evaluation_ts"), "catalog_version": data.get("catalog_version"), "config_version": data.get("config_version"), **(data.get("public_bundle") or {})})\n        except Exception as exc:\n            self.send_json({"ok": False, "state": "needs_data", "error_type": type(exc).__name__}, status=503)\n\n    def handle_furnace_rule_detail(self, rule_id: str) -> None:\n        if rule_id not in RULE_BY_ID:\n            self.send_json({"ok": False, "error": "unknown_rule"}, status=404)\n            return\n        try:\n            with self._abc_connection() as conn:\n                row = conn.execute("SELECT i.batch_id,b.evaluation_ts,i.public_detail FROM bf_sensor.abc_rule_evaluation_items i JOIN bf_sensor.abc_rule_evaluation_batches b ON b.id=i.batch_id WHERE i.rule_id=%s ORDER BY b.evaluation_ts DESC LIMIT 1", (rule_id,)).fetchone()\n            if not row:\n                self.send_json({"ok": True, "state": "needs_data", "rule_id": rule_id})\n                return\n            data = dict(row) if isinstance(row, Mapping) else {"batch_id": row[0], "evaluation_ts": row[1], "public_detail": row[2]}\n            self.send_json({"ok": True, "schema_version": "furnace_rule_detail.v1", "evaluation_id": data.get("batch_id"), "evaluation_ts": data.get("evaluation_ts"), "detail": public_rule(data.get("public_detail") or {"rule_id": rule_id})})\n        except Exception as exc:\n            self.send_json({"ok": False, "error_type": type(exc).__name__}, status=503)\n\n    def handle_furnace_rule_trends(self, rule_id: str) -> None:\n        if rule_id not in RULE_BY_ID:\n            self.send_json({"ok": False, "error": "unknown_rule"}, status=404)\n            return\n        try:\n            with self._abc_connection() as conn:\n                rows = conn.execute("SELECT b.evaluation_ts,i.score,i.confidence,i.status FROM bf_sensor.abc_rule_evaluation_items i JOIN bf_sensor.abc_rule_evaluation_batches b ON b.id=i.batch_id WHERE i.rule_id=%s ORDER BY b.evaluation_ts DESC LIMIT 72", (rule_id,)).fetchall()\n            points = [dict(row) if isinstance(row, Mapping) else {"evaluation_ts": row[0], "score": row[1], "confidence": row[2], "status": row[3]} for row in reversed(rows)]\n            self.send_json({"ok": True, "schema_version": "furnace_rule_trends.v1", "rule_id": rule_id, "points": points})\n        except Exception as exc:\n            self.send_json({"ok": False, "error_type": type(exc).__name__}, status=503)\n\n    def handle_admin_furnace_rule_detail(self, path: str) -> None:\n        if not self._abc_admin_required():\n            return\n        parts = path.split("/")\n        if len(parts) < 7:\n            self.send_json({"ok": False, "error": "invalid_path"}, status=400)\n            return\n        try:\n            evaluation_id = int(parts[5])\n        except ValueError:\n            self.send_json({"ok": False, "error": "invalid_evaluation_id"}, status=400)\n            return\n        rule_id = parts[6]\n        with self._abc_connection() as conn:\n            row = conn.execute("SELECT * FROM bf_sensor.abc_rule_evaluation_items WHERE batch_id=%s AND rule_id=%s", (evaluation_id, rule_id)).fetchone()\n        if not row:\n            self.send_json({"ok": False, "error": "not_found"}, status=404)\n            return\n        self.send_json({"ok": True, "schema_version": "furnace_rule_admin_detail.v1", "evaluation": dict(row) if isinstance(row, Mapping) else {"rule_id": rule_id}} , headers={"Cache-Control": "no-store"})\n\n'''
        anchor = "    def current_review_session(self) -> dict[str, Any] | None:\n"
        if anchor not in text:
            raise RuntimeError("proxy method anchor not found")
        text = text.replace(anchor, methods + anchor, 1)
    if 'rel == "furnace-rule-admin.html"' not in text:
        anchor = "        target = (BASE_DIR / rel).resolve()\n"
        text = text.replace(anchor, '        if rel == "furnace-rule-admin.html" and not self._abc_admin_required():\n            return\n' + anchor, 1)
    atomic_text(path, text)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", required=True)
    parser.add_argument("--payload", required=True)
    args = parser.parse_args()
    root = Path(args.root)
    payload = Path(args.payload)
    service = root / "自动诊断服务"
    frontend = root / "高炉前端数据"
    backend = frontend / "智能助手" / "backend"
    page = frontend / "frontend_dashboard_v3.8094_preview.server.html"
    bridge = service / "local_pg_ws_bridge.py"
    proxy = backend / "ollama_proxy_server.py"
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup = root / "backups" / "abc33_8094" / stamp
    backup.mkdir(parents=True, exist_ok=True)
    targets = [bridge, proxy, page]
    for target in targets:
        shutil.copy2(target, backup / target.name)
    patch_bridge(bridge)
    patch_proxy(proxy, str(service))
    asset = frontend / "assets" / "abc-furnace-rules-production.js"
    asset.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(payload / "abc-furnace-rules-production.js", asset)
    shutil.copy2(payload / "furnace-rule-admin.html", frontend / "furnace-rule-admin.html")
    shutil.copy2(payload / "abc_rule_catalog.py", service / "abc_rule_catalog.py")
    shutil.copy2(payload / "abc_feature_builder.py", service / "abc_feature_builder.py")
    shutil.copy2(payload / "abc_rule_engine.py", service / "abc_rule_engine.py")
    shutil.copy2(payload / "abc_runtime_store.py", service / "abc_runtime_store.py")
    (service / "config").mkdir(parents=True, exist_ok=True)
    shutil.copy2(payload / "abc_furnace_rules.v1.json", service / "config" / "abc_furnace_rules.v1.json")
    original_page_text = page.read_text(encoding="utf-8")
    script = '<script src="assets/abc-furnace-rules-production.js?v=abc33-20260808-r2"></script>'
    page_text = original_page_text.replace(
        '<script src="assets/abc-furnace-rules-production.js?v=abc33-20260808"></script>',
        script,
    )
    if script not in page_text:
        if "</body>" not in page_text:
            raise RuntimeError("8094 page has no body marker")
        page_text = page_text.replace("</body>", script + "\n</body>", 1)
    if page_text != original_page_text:
        atomic_text(page, page_text)
    print(json.dumps({"ok": True, "backup": str(backup), "bridge_sha256": sha(bridge), "proxy_sha256": sha(proxy), "page_sha256": sha(page), "catalog_sha256": sha(service / "abc_rule_catalog.py")}, ensure_ascii=False))


if __name__ == "__main__":
    main()
