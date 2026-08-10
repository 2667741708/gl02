"""Deploy the fail-closed ABC33 shadow-validation release gate."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import py_compile
import re
import shutil
from datetime import datetime
from pathlib import Path


VERSION = "abc33-20260808-r5-shadow-gate"


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def replace(path: Path, data: bytes) -> None:
    temp = path.with_name(path.name + ".abc33-shadow.tmp")
    temp.write_bytes(data)
    os.replace(temp, path)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", required=True)
    parser.add_argument("--payload", required=True)
    args = parser.parse_args()
    root, payload = Path(args.root), Path(args.payload)
    targets = {
        root / "自动诊断服务" / "abc_rule_engine.py": payload / "abc_rule_engine.py",
        root / "自动诊断服务" / "config" / "abc_furnace_rules.v1.json": payload / "abc_furnace_rules.v1.json",
        root / "高炉前端数据" / "assets" / "abc-furnace-rules-production.js": payload / "abc-furnace-rules-production.js",
    }
    page = root / "高炉前端数据" / "frontend_dashboard_v3.8094_preview.server.html"
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup = root / "backups" / "abc33_shadow_gate_8094" / stamp
    backup.mkdir(parents=True, exist_ok=True)
    for target in (*targets, page):
        shutil.copy2(target, backup / target.name)
    for target, source in targets.items():
        replace(target, source.read_bytes())
    page_text = page.read_text(encoding="utf-8")
    page_text, count = re.subn(r'assets/abc-furnace-rules-production\.js\?v=[^"\']+', f"assets/abc-furnace-rules-production.js?v={VERSION}", page_text, count=1)
    if count != 1:
        raise RuntimeError("ABC33 page reference missing")
    replace(page, page_text.encode("utf-8"))
    py_compile.compile(str(root / "自动诊断服务" / "abc_rule_engine.py"), doraise=True)
    json.loads((root / "自动诊断服务" / "config" / "abc_furnace_rules.v1.json").read_text(encoding="utf-8"))
    print(json.dumps({"ok": True, "version": VERSION, "backup": str(backup), "hashes": {str(path.relative_to(root)): sha(path) for path in (*targets, page)}}, ensure_ascii=False))


if __name__ == "__main__":
    main()
