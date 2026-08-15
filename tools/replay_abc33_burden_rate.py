"""Replay the A2/B4/B5 burden-rate factors from an exported MES event CSV."""
from __future__ import annotations

import argparse
import csv
import json
import sys
from datetime import datetime
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SERVICE = ROOT / "自动诊断服务"
sys.path.insert(0, str(SERVICE))

from abc_burden_rate import calculate_burden_rate_snapshot


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("csv_path", type=Path, help="UTF-8 CSV containing event_ts, charge, fetched_at and updated_at")
    parser.add_argument("--evaluation-ts", help="Plant local time; defaults to the newest event timestamp")
    parser.add_argument("--output", type=Path, help="Optional UTF-8 JSON output path")
    args = parser.parse_args()
    with args.csv_path.open("r", encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    if not rows:
        raise SystemExit("event CSV is empty")
    evaluation = (
        datetime.fromisoformat(args.evaluation_ts)
        if args.evaluation_ts
        else max(datetime.fromisoformat(str(row["event_ts"])) for row in rows)
    )
    result = calculate_burden_rate_snapshot(rows, evaluation)
    encoded = json.dumps(result, ensure_ascii=False, indent=2, default=str)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(encoded + "\n", encoding="utf-8")
    print(encoded)


if __name__ == "__main__":
    main()
