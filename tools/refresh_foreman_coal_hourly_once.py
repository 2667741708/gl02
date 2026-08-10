"""One-shot PostgreSQL-only refresh of 2# furnace hourly coal records."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timedelta
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True, help="数据库同步和存取目录")
    parser.add_argument("--hours", type=int, default=3)
    args = parser.parse_args()
    root = args.root.resolve()
    sys.path.insert(0, str(root / "src"))
    from coal_hourly import refresh_coal_injection_hourly
    from pg_store import connect

    config = root / "config" / "sync_config.json"
    conn = connect(config)
    table_name = conn.execute("SELECT to_regclass('bf_sensor.coal_injection_hourly') AS name").fetchone()["name"]
    if table_name is None:
        raise RuntimeError("bf_sensor.coal_injection_hourly is not initialized")
    now = datetime.now().replace(microsecond=0)
    result = refresh_coal_injection_hourly(conn, now - timedelta(hours=max(1, args.hours)), now)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result.get("status") == "ok" else 2


if __name__ == "__main__":
    raise SystemExit(main())
