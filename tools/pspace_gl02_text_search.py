# -*- coding: utf-8 -*-
"""Search GL02 pSpace tag names/descriptions by literal keywords."""

from __future__ import annotations

import argparse
import csv
import json
import os
import re
import statistics
import sys
from datetime import datetime
from pathlib import Path
from typing import Any


ROOT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT_DIR / "tools"))

from pspace_8092_realtime_bridge import (  # noqa: E402
    find_sdk_root,
    get_tag_props,
    load_sdk,
    numeric_items,
    parse_history_timestamp,
    query_all_tag_names,
    read_history_raw,
    read_realtime,
    to_float,
)
from pspace_8092_realtime_bridge import connect_pspace as bridge_connect_pspace  # noqa: E402


class BridgeArgs:
    pspace_server: str
    pspace_port: str
    pspace_user: str | None
    pspace_password: str | None


def normalize(value: str) -> str:
    value = value.lower().replace("＃", "#")
    return re.sub(r"[\s_（）()：:，,。/\\\-]+", "", value)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--sdk-root", default=os.getenv("PSPACE_SDK_ROOT"))
    parser.add_argument("--pspace-server", default=os.getenv("PSPACE_SERVER", "10.22.181.244"))
    parser.add_argument("--pspace-port", default=os.getenv("PSPACE_PORT", "8889"))
    parser.add_argument("--pspace-user", default=os.getenv("PSPACE_USER"))
    parser.add_argument("--pspace-password", default=os.getenv("PSPACE_PASSWORD"))
    parser.add_argument("--scope", default="GL02")
    parser.add_argument("--keywords", required=True, help="Comma-separated keyword list.")
    parser.add_argument("--history-hours", type=int, default=0)
    parser.add_argument("--history-max-values", type=int, default=4000)
    parser.add_argument("--out-dir", default=str(ROOT_DIR / "logs"))
    return parser.parse_args()


def connect(args: argparse.Namespace):
    sdk_root = find_sdk_root(args.sdk_root)
    PsObject, T = load_sdk(sdk_root)
    bridge_args = BridgeArgs()
    bridge_args.pspace_server = args.pspace_server
    bridge_args.pspace_port = str(args.pspace_port)
    bridge_args.pspace_user = args.pspace_user
    bridge_args.pspace_password = args.pspace_password
    if not bridge_args.pspace_user or not bridge_args.pspace_password:
        raise SystemExit("Missing PSPACE_USER/PSPACE_PASSWORD.")
    return bridge_connect_pspace(PsObject, T, bridge_args), T


def value_by_tag(pspace, T, tags: list[str]) -> dict[str, dict[str, Any]]:
    if not tags:
        return {}

    try:
        values, meta = read_realtime(pspace, T, {tag: tag for tag in tags})
        return {
            tag: {
                "value": values.get(tag),
                "timestamp": (meta.get("timestamps") or {}).get(tag, ""),
                "quality": (meta.get("qualities") or {}).get(tag, ""),
                "error": (meta.get("errors") or {}).get(tag, ""),
            }
            for tag in tags
        }
    except Exception as batch_exc:
        rows: dict[str, dict[str, Any]] = {}
        for tag in tags:
            try:
                values, meta = read_realtime(pspace, T, {tag: tag})
                rows[tag] = {
                    "value": values.get(tag),
                    "timestamp": (meta.get("timestamps") or {}).get(tag, ""),
                    "quality": (meta.get("qualities") or {}).get(tag, ""),
                    "error": (meta.get("errors") or {}).get(tag, ""),
                }
            except Exception as tag_exc:
                rows[tag] = {
                    "value": None,
                    "timestamp": "",
                    "quality": "",
                    "error": f"batch={type(batch_exc).__name__}; tag={type(tag_exc).__name__}: {tag_exc}",
                }
        return rows


def history_by_tag(pspace, T, tags: list[str], hours: int, max_values: int) -> dict[str, dict[str, Any]]:
    if hours <= 0 or not tags:
        return {}
    result = read_history_raw(pspace, T, {tag: tag for tag in tags}, hours, max_values)
    out: dict[str, dict[str, Any]] = {}
    for tag in tags:
        records = result.get(tag, {})
        values: list[float] = []
        latest_ts = ""
        latest_value: float | None = None
        if isinstance(records, dict):
            for _, record in numeric_items(records):
                if not isinstance(record, dict):
                    continue
                value = to_float(record.get(T.HisReadRawValueDict))
                ts = parse_history_timestamp(record.get(T.HisReadRawTimeStamp, ""))
                if value is None or ts is None:
                    continue
                values.append(value)
                latest_ts = ts.strftime("%Y-%m-%d %H:%M:%S")
                latest_value = value
        out[tag] = {
            "history_count": len(values),
            "history_latest_timestamp": latest_ts,
            "history_latest_value": latest_value,
            "history_min": min(values) if values else None,
            "history_max": max(values) if values else None,
            "history_mean": statistics.fmean(values) if values else None,
        }
    return out


def main() -> int:
    args = parse_args()
    keywords = [keyword.strip() for keyword in args.keywords.split(",") if keyword.strip()]
    normalized_keywords = [(keyword, normalize(keyword)) for keyword in keywords]
    pspace, T = connect(args)
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    csv_path = out_dir / f"gl02_text_search_{stamp}.csv"
    json_path = out_dir / f"gl02_text_search_{stamp}.json"

    rows: list[dict[str, Any]] = []
    tag_names = [name for name in query_all_tag_names(pspace, T) if args.scope in name and name.count("\\") >= 4]
    for tag in tag_names:
        props = get_tag_props(pspace, T, tag)
        text = " ".join([tag, props.get("name", ""), props.get("description", ""), props.get("unit", "")])
        haystack = normalize(text)
        matched = [keyword for keyword, normalized in normalized_keywords if normalized and normalized in haystack]
        if not matched:
            continue
        rows.append(
            {
                "tag": tag,
                "name": props.get("name", ""),
                "description": props.get("description", ""),
                "unit": props.get("unit", ""),
                "matched": "|".join(matched),
            }
        )

    rows.sort(key=lambda row: (row["description"], row["tag"]))
    tags = [row["tag"] for row in rows]
    realtime = value_by_tag(pspace, T, tags)
    history = history_by_tag(pspace, T, tags, args.history_hours, args.history_max_values)
    for row in rows:
        tag = row["tag"]
        row.update(realtime.get(tag, {}))
        row.update(history.get(tag, {}))

    fieldnames = [
        "tag",
        "name",
        "description",
        "unit",
        "matched",
        "value",
        "timestamp",
        "quality",
        "error",
        "history_count",
        "history_latest_timestamp",
        "history_latest_value",
        "history_min",
        "history_max",
        "history_mean",
    ]
    with csv_path.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    json_path.write_text(json.dumps({"rows": rows, "csv": str(csv_path)}, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"csv": str(csv_path), "json": str(json_path), "matches": len(rows)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
