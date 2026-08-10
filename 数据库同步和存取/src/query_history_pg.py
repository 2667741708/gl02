from __future__ import annotations

import argparse
import csv
import json
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from catalog import point_by_variable
from pg_store import connect, ensure_schema


ROOT_DIR = Path(__file__).resolve().parents[0].parent


def parse_time(value: str | None) -> datetime | None:
    if not value:
        return None
    text = value.replace("T", " ")
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M"):
        try:
            return datetime.strptime(text, fmt).replace(second=0, microsecond=0)
        except ValueError:
            continue
    raise argparse.ArgumentTypeError(f"Unsupported time: {value}")


def derive_t_top(rows_by_var: dict[str, list[dict[str, Any]]]) -> list[dict[str, Any]]:
    sources = ["T_top_A", "T_top_B", "T_top_C", "T_top_D"]
    by_ts: dict[str, list[float]] = {}
    for source in sources:
        for row in rows_by_var.get(source, []):
            if row["value"] is not None:
                by_ts.setdefault(row["ts"], []).append(float(row["value"]))
    return [{"variable_name": "T_top", "ts": ts, "value": sum(values) / len(values), "quality": "DERIVED_AVERAGE"} for ts, values in sorted(by_ts.items()) if values]


def query_rows(variables: list[str], start: datetime, end: datetime, config: str) -> list[dict[str, Any]]:
    conn = connect(config)
    ensure_schema(conn, config)
    points = point_by_variable(config)
    needed = set(variables)
    if "T_top" in needed:
        needed.update(["T_top_A", "T_top_B", "T_top_C", "T_top_D"])
    physical = [points[name] for name in needed if name in points and not points[name].is_derived]
    tag_to_var = {point.tag_long_name: point.variable_name for point in physical}
    if not tag_to_var:
        return []
    records = conn.execute(
        """
        SELECT tag_long_name, ts, value, quality
        FROM bf_sensor.one_minute_values
        WHERE tag_long_name = ANY(%s)
          AND ts >= %s
          AND ts <= %s
        ORDER BY ts ASC, tag_long_name ASC
        """,
        (list(tag_to_var.keys()), start, end),
    ).fetchall()
    rows_by_var: dict[str, list[dict[str, Any]]] = {}
    for record in records:
        variable = tag_to_var[str(record["tag_long_name"])]
        row = {
            "variable_name": variable,
            "ts": record["ts"].strftime("%Y-%m-%d %H:%M:%S"),
            "value": record["value"],
            "quality": record["quality"],
        }
        rows_by_var.setdefault(variable, []).append(row)
    if "T_top" in variables:
        rows_by_var["T_top"] = derive_t_top(rows_by_var)

    output: list[dict[str, Any]] = []
    for variable in variables:
        output.extend(rows_by_var.get(variable, []))
    return output


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Query required-point history from PostgreSQL.")
    parser.add_argument("--config", default=str(ROOT_DIR / "config" / "sync_config.json"))
    parser.add_argument("--variables", required=True, help="Comma-separated variable names, e.g. PI,T_top,GasUtil")
    parser.add_argument("--start", default="")
    parser.add_argument("--end", default="")
    parser.add_argument("--hours", type=float, default=8)
    parser.add_argument("--format", choices=["json", "csv"], default="json")
    parser.add_argument("--out", default="")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    end = parse_time(args.end) or datetime.now().replace(second=0, microsecond=0)
    start = parse_time(args.start)
    if start is None:
        start = end - timedelta(hours=args.hours)
    variables = [item.strip() for item in args.variables.split(",") if item.strip()]
    rows = query_rows(variables, start, end, args.config)

    if args.format == "csv":
        target = Path(args.out) if args.out else None
        fh = target.open("w", encoding="utf-8-sig", newline="") if target else sys.stdout
        writer = csv.DictWriter(fh, fieldnames=["variable_name", "ts", "value", "quality"])
        writer.writeheader()
        writer.writerows(rows)
        if target:
            fh.close()
    else:
        payload = {
            "ok": True,
            "start": start.strftime("%Y-%m-%d %H:%M:%S"),
            "end": end.strftime("%Y-%m-%d %H:%M:%S"),
            "variables": variables,
            "rows": rows,
        }
        text = json.dumps(payload, ensure_ascii=False, indent=2)
        if args.out:
            Path(args.out).write_text(text + "\n", encoding="utf-8")
        else:
            print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
