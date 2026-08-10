"""Use each sensor's own recent sample in the production 8768 bridge."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import py_compile
import shutil
from datetime import datetime
from pathlib import Path


MARKER = "BUG-ABC33-SPARSE-MINUTE-LATEST-20260808-R1"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", required=True)
    args = parser.parse_args()
    path = Path(args.root) / "自动诊断服务" / "local_pg_ws_bridge.py"
    text = path.read_text(encoding="utf-8")
    if MARKER in text:
        print(json.dumps({"ok": True, "state": "already_patched", "sha256": sha256(path)}))
        return
    old = '''    idx = len(timestamps) - 1
    return timestamps[idx], {var: (history.get(var) or [None])[idx] if history.get(var) else None for var in FRONTEND_VARIABLES}
'''
    new = '''    # BUG-ABC33-SPARSE-MINUTE-LATEST-20260808-R1: tags can land one or
    # two minutes apart.  Use each variable's own newest finite sample while
    # preserving the five-minute freshness gate.
    latest_ts = parse_ts(timestamps[-1])
    values: dict[str, Any] = {}
    for var in FRONTEND_VARIABLES:
        series = history.get(var) or []
        selected = None
        for idx in range(min(len(series), len(timestamps)) - 1, -1, -1):
            value = finite_float(series[idx])
            if value is None:
                continue
            sample_ts = parse_ts(timestamps[idx])
            age_seconds = max(0.0, (latest_ts - sample_ts).total_seconds())
            if age_seconds <= 300:
                selected = value
            break
        values[var] = selected
    return timestamps[-1], values
'''
    if old not in text:
        raise RuntimeError("latest_values exact-index block is missing or changed")
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup = Path(args.root) / "backups" / "abc33_recent_values_8768" / stamp
    backup.mkdir(parents=True, exist_ok=True)
    shutil.copy2(path, backup / path.name)
    temp = path.with_name(path.name + ".abc33-recent.tmp")
    temp.write_text(text.replace(old, new, 1), encoding="utf-8", newline="\n")
    os.replace(temp, path)
    py_compile.compile(str(path), doraise=True)
    print(json.dumps({"ok": True, "marker": MARKER, "backup": str(backup), "sha256": sha256(path)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
