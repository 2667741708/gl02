"""Lightweight PostgreSQL health and active-session probe."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    args = parser.parse_args()
    root = args.root.resolve()
    sys.path.insert(0, str(root / "src"))
    from pg_store import connect

    conn = connect(root / "config" / "sync_config.json")
    health = conn.execute("SELECT now() AS db_now, current_database() AS database, current_user AS db_user").fetchone()
    sessions = conn.execute(
        """
        SELECT pid, usename, application_name, client_addr, state, wait_event_type,
               wait_event, now() - query_start AS query_age,
               left(regexp_replace(query, E'[\\n\\r\\t]+', ' ', 'g'), 220) AS query
        FROM pg_stat_activity
        WHERE datname = current_database()
          AND pid <> pg_backend_pid()
        ORDER BY query_start
        """
    ).fetchall()
    print(json.dumps({"health": dict(health), "sessions": [dict(row) for row in sessions]}, ensure_ascii=False, default=str, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
