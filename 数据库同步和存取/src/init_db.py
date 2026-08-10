from __future__ import annotations

import argparse
import json
from pathlib import Path

from catalog import load_points
from store import connect, ensure_schema, insert_instruction, summary, upsert_registry


ROOT_DIR = Path(__file__).resolve().parents[0].parent
DEFAULT_INSTRUCTION = ROOT_DIR / "明确指令.md"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Initialize the local/220.12 GL02 required-points database.")
    parser.add_argument("--db", default="")
    parser.add_argument("--config", default=str(ROOT_DIR / "config" / "sync_config.json"))
    parser.add_argument("--instruction", default=str(DEFAULT_INSTRUCTION))
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    points = load_points(args.config, include_derived=True)
    conn = connect(args.db or None, args.config)
    ensure_schema(conn, args.config)
    upsert_registry(conn, points)

    instruction_path = Path(args.instruction)
    if instruction_path.exists():
        insert_instruction(
            conn,
            "用户明确指令：220.12 数据库同步和存取",
            instruction_path.read_text(encoding="utf-8"),
            str(instruction_path),
        )

    print(json.dumps({"ok": True, "db_summary": summary(conn)}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
