"""Make ABC33 latest/detail selection deterministic when config versions share a timestamp."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import py_compile
import shutil
from datetime import datetime
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", required=True)
    args = parser.parse_args()
    root = Path(args.root)
    path = root / "高炉前端数据" / "智能助手" / "backend" / "ollama_proxy_server.py"
    text = path.read_text(encoding="utf-8")
    replacements = {
        "ORDER BY evaluation_ts DESC LIMIT 1": "ORDER BY evaluation_ts DESC, id DESC LIMIT 1",
        "WHERE i.rule_id=%s ORDER BY b.evaluation_ts DESC LIMIT 1": "WHERE i.rule_id=%s ORDER BY b.evaluation_ts DESC, b.id DESC LIMIT 1",
        "WHERE i.rule_id=%s ORDER BY b.evaluation_ts DESC LIMIT 72": "WHERE i.rule_id=%s ORDER BY b.evaluation_ts DESC, b.id DESC LIMIT 72",
    }
    updated = text
    for old, new in replacements.items():
        if new in updated:
            continue
        if old not in updated:
            raise RuntimeError(f"missing query anchor: {old}")
        updated = updated.replace(old, new, 1)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup = root / "backups" / "abc33_latest_batch_order_8094" / stamp
    backup.mkdir(parents=True, exist_ok=True)
    shutil.copy2(path, backup / path.name)
    temp = path.with_name(path.name + ".abc33-order.tmp")
    temp.write_text(updated, encoding="utf-8", newline="\n")
    os.replace(temp, path)
    py_compile.compile(str(path), doraise=True)
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    print(json.dumps({"ok": True, "backup": str(backup), "sha256": digest}, ensure_ascii=False))


if __name__ == "__main__":
    main()
