from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime, timedelta
from pathlib import Path

from service_config import PROJECT_ROOT, load_config
from store import DiagnosisStore


def reconcile(config_path: str | Path | None = None, dry_run: bool = True) -> dict:
    config = load_config(config_path) if config_path else load_config()
    store = DiagnosisStore(config_path)
    latest_ts = store.latest_data_ts()
    if latest_ts is None:
        return {"ok": False, "error": "NO_LOCAL_DATA"}
    variables = config.get("pspace_reconcile", {}).get("sample_variables", [])
    local_start = latest_ts - timedelta(minutes=5)
    local = store.fetch_wide_frame(local_start, latest_ts, variables=variables)
    local_latest = {}
    if not local.empty:
        for var in variables:
            if var in local.columns and local[var].notna().any():
                local_latest[var] = float(local[var].dropna().iloc[-1])
    return {
        "ok": True,
        "dry_run": dry_run,
        "message": "pSpace reconciliation is explicit-only. This dry-run reports local sample values; production补漏可调用 existing MCP pSpace helper.",
        "latest_local_ts": latest_ts,
        "variables": variables,
        "local_latest": local_latest,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Low-frequency PostgreSQL/pSpace reconciliation helper.")
    parser.add_argument("--config", default="")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    print(json.dumps(reconcile(args.config or None, dry_run=args.dry_run), ensure_ascii=False, default=str, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
