from __future__ import annotations

import argparse
import json
from datetime import datetime, timedelta
from pathlib import Path

from data_quality_monitor import DataQualityMonitor
from store import DiagnosisStore


def create_tasks_from_quality(config_path: str | Path | None = None, write: bool = False) -> list[dict]:
    monitor = DataQualityMonitor(config_path)
    store = DiagnosisStore(config_path)
    variable_map = {}
    try:
        # tag -> variable, invert for task creation
        variable_map = {var: tag for tag, var in store.load_variable_map().items()}
    except Exception:
        variable_map = {}
    quality = monitor.check_all(write=False)
    tasks = []
    for item in quality:
        for variable in item.get("missing_variables", []):
            task = {
                "reason": f"missing_in_{item['window_kind']}",
                "variable_name": variable,
                "tag_long_name": variable_map.get(variable, ""),
                "start_ts": item["window_start"],
                "end_ts": item["window_end"],
            }
            tasks.append(task)
            if write:
                store.ensure_schema()
                store.create_backfill_task(**task)
    return tasks


def main() -> int:
    parser = argparse.ArgumentParser(description="Create backfill tasks for missing local database data.")
    parser.add_argument("--config", default="")
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args()
    tasks = create_tasks_from_quality(args.config or None, write=args.write)
    print(json.dumps({"ok": True, "count": len(tasks), "tasks": tasks}, ensure_ascii=False, default=str, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
