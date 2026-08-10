from __future__ import annotations

import argparse
import csv
import json
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from catalog import point_by_variable
from store import connect, ensure_schema


ROOT_DIR = Path(__file__).resolve().parents[0].parent


def parse_time(value: str | None) -> str | None:
    if not value:
        return None
    text = value.replace("T", " ")
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M"):
        try:
            return datetime.strptime(text, fmt).strftime("%Y-%m-%d %H:%M:%S")
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
    return [{"variable_name": "T_top", "ts": ts, "value": sum(values) / len(values)} for ts, values in sorted(by_ts.items()) if values]


def query_rows(conn: sqlite3.Connection, variables: list[str], start: str, end: str, config: str) -> list[dict[str, Any]]:
    points = point_by_variable(config)
    needed = set(variables)
    if "T_top" in needed:
        needed.update(["T_top_A", "T_top_B", "T_top_C", "T_top_D"])
    physical = [points[name] for name in needed if name in points and not points[name].is_derived]
    tag_to_var = {point.tag_long_name: point.variable_name for point in physical}
    if not tag_to_var:
        return []
    placeholders = ",".join("?" for _ in tag_to_var)
    records = conn.execute(
        f"""
        SELECT tag_long_name, ts, value, quality
        FROM one_minute_values
        WHERE tag_long_name IN ({placeholders})
          AND ts >= ?
          AND ts <= ?
        ORDER BY ts ASC, tag_long_name ASC
        """,
        [*tag_to_var.keys(), start, end],
    ).fetchall()
    rows_by_var: dict[str, list[dict[str, Any]]] = {}
    for record in records:
        variable = tag_to_var[str(record["tag_long_name"])]
        row = {
            "variable_name": variable,
            "ts": record["ts"],
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
    parser = argparse.ArgumentParser(description="Query required-point history from the local/220.12 database.")
    parser.add_argument("--db", default="")
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
    end = parse_time(args.end) or datetime.now().replace(second=0, microsecond=0).strftime("%Y-%m-%d %H:%M:%S")
    start = parse_time(args.start)
    if start is None:
        start = (datetime.strptime(end, "%Y-%m-%d %H:%M:%S") - timedelta(hours=args.hours)).strftime("%Y-%m-%d %H:%M:%S")
    variables = [item.strip() for item in args.variables.split(",") if item.strip()]
    conn = connect(args.db or None, args.config)
    ensure_schema(conn, args.config)
    rows = query_rows(conn, variables, start, end, args.config)

    if args.format == "csv":
        if args.out:
            fh = Path(args.out).open("w", encoding="utf-8-sig", newline="")
            close = True
        else:
            fh = None
            close = False
        fieldnames = ["variable_name", "ts", "value", "quality"]
        writer = csv.DictWriter(fh or __import__("sys").stdout, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
        if close:
            fh.close()
    else:
        payload = {"ok": True, "start": start, "end": end, "variables": variables, "rows": rows}
        text = json.dumps(payload, ensure_ascii=False, indent=2)
        if args.out:
            Path(args.out).write_text(text + "\n", encoding="utf-8")
        else:
            print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
