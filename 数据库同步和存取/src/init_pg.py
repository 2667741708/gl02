from __future__ import annotations

import argparse
import json
from pathlib import Path

from catalog import load_points, physical_points
from pg_store import apply_retention, connect, ensure_schema, insert_instruction, summary, upsert_registry


ROOT_DIR = Path(__file__).resolve().parents[0].parent
WORKSPACE_ROOT = ROOT_DIR.parents[0]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Initialize PostgreSQL storage for required GL02/GF2 1min points.")
    parser.add_argument("--config", default=str(ROOT_DIR / "config" / "sync_config.json"))
    parser.add_argument("--skip-retention", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    conn = connect(args.config)
    ensure_schema(conn, args.config)
    points = load_points(args.config, include_derived=True)
    upsert_registry(conn, points)

    instruction_path = WORKSPACE_ROOT / "数据库同步和存取" / "明确指令.md"
    if instruction_path.exists():
        insert_instruction(
            conn,
            "数据库同步和存取明确指令",
            instruction_path.read_text(encoding="utf-8"),
            str(instruction_path.relative_to(WORKSPACE_ROOT)),
        )
    dropped = 0 if args.skip_retention else apply_retention(conn, retain_years=3)
    payload = {
        "ok": True,
        "logical_points": len(points),
        "physical_points": len(physical_points(args.config)),
        "retention_years": 3,
        "dropped_old_partitions": dropped,
        "summary": summary(conn),
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
