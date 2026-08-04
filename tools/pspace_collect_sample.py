# -*- coding: utf-8 -*-
"""Read a small, safe sample from the pSpace/PythonAPI data server.

The script is intentionally conservative: it only performs read operations,
limits tag discovery, limits returned history rows, and writes sampled data to
CSV under the project directory.
"""

from __future__ import annotations

import argparse
import csv
import os
import sys
from collections import deque
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any


DEFAULT_SDK_ROOT = Path(r"D:\文件\数据库连接方式\pythonSDK(1)")
DEFAULT_OUTPUT_DIR = Path(__file__).resolve().parents[1] / "高炉传感器数据"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Collect a bounded pSpace data sample.")
    parser.add_argument("--sdk-root", default=os.getenv("PSPACE_SDK_ROOT", str(DEFAULT_SDK_ROOT)))
    parser.add_argument("--server", default=os.getenv("PSPACE_SERVER", "10.22.181.244"))
    parser.add_argument("--port", default=os.getenv("PSPACE_PORT", "8889"))
    parser.add_argument("--user", default=os.getenv("PSPACE_USER"))
    parser.add_argument("--password", default=os.getenv("PSPACE_PASSWORD"))
    parser.add_argument("--root-tag", default=os.getenv("PSPACE_ROOT_TAG", "/"))
    parser.add_argument("--match", default=os.getenv("PSPACE_MATCH"), help="Only read tags containing this text.")
    parser.add_argument("--tag", action="append", default=None, help="Explicit tag name to read; can be repeated.")
    parser.add_argument("--max-tags", type=int, default=int(os.getenv("PSPACE_MAX_TAGS", "20")))
    parser.add_argument("--history-minutes", type=int, default=int(os.getenv("PSPACE_HISTORY_MINUTES", "10")))
    parser.add_argument("--max-values", type=int, default=int(os.getenv("PSPACE_MAX_VALUES", "200")))
    parser.add_argument("--output-dir", default=os.getenv("PSPACE_OUTPUT_DIR", str(DEFAULT_OUTPUT_DIR)))
    return parser.parse_args()


def load_sdk(sdk_root: Path):
    if not sdk_root.exists():
        raise FileNotFoundError(f"SDK root does not exist: {sdk_root}")

    sys.path.insert(0, str(sdk_root))
    from PythonAPI.PsServer import PsObject
    from PythonAPI import Type as T

    return PsObject, T


def require_credentials(args: argparse.Namespace) -> None:
    if not args.user or not args.password:
        raise SystemExit(
            "Missing pSpace credentials. Set PSPACE_USER and PSPACE_PASSWORD, "
            "or pass --user and --password."
        )


def connect(PsObject, T, args: argparse.Namespace):
    pspace = PsObject()
    result = pspace.Connect(
        {
            "ServerIP": args.server,
            "ServerPort": args.port,
            "UserName": args.user,
            "Password": args.password,
        }
    )
    if result.get(T.Return) != 0:
        raise RuntimeError(f"Connect failed: return={result.get(T.Return)} error={result.get(T.Error)}")
    return pspace, result


def query_children(pspace, T, parent: str) -> list[tuple[int, str]]:
    result = pspace.QueryTag({T.QueryTagLongName: parent})
    if result.get(T.Return) != 0:
        return []

    children: list[tuple[int, str]] = []
    count = int(result.get(T.QueryTagPropNum, 0) or 0)
    for index in range(count):
        item = result.get(index, {})
        name = item.get(T.QueryTagPropName)
        tag_id = item.get(T.QueryTagPropID)
        if name:
            children.append((int(tag_id or 0), str(name)))
    return children


def discover_tags(pspace, T, root_tag: str, max_tags: int, match: str | None = None) -> list[tuple[int, str]]:
    queue: deque[str] = deque([root_tag])
    seen: set[str] = set()
    found: list[tuple[int, str]] = []

    while queue and len(found) < max_tags:
        parent = queue.popleft()
        for tag_id, child in query_children(pspace, T, parent):
            if child in seen:
                continue
            seen.add(child)
            if match is None or match in child:
                found.append((tag_id, child))
            queue.append(child)
            if len(found) >= max_tags:
                break
    return found


def numeric_items(mapping: dict[str, Any] | dict[int, Any]):
    def sort_key(item):
        key, _ = item
        try:
            return int(key)
        except (TypeError, ValueError):
            return 10**12

    for key, value in sorted(mapping.items(), key=sort_key):
        try:
            int(key)
        except (TypeError, ValueError):
            continue
        yield key, value


def collect_realtime(pspace, T, tag_names: list[str]) -> list[dict[str, Any]]:
    if not tag_names:
        return []
    result = pspace.RealReadList({T.RealReadListTagNameBuffer: tag_names})
    rows: list[dict[str, Any]] = []
    for _, item in numeric_items(result):
        if not isinstance(item, dict):
            continue
        rows.append(
            {
                "source": "realtime",
                "tag": item.get(T.TagLongNameDict, ""),
                "timestamp": item.get(T.PsRealReadListTimeStamp, ""),
                "value": item.get(T.PsRealReadListValueDict, ""),
                "quality": item.get(T.PsRealReadListListQualityDict, ""),
                "data_type": "",
                "error": item.get("ErrorInfo", ""),
            }
        )
    return rows


def collect_history(pspace, T, tag_names: list[str], minutes: int, max_values: int) -> list[dict[str, Any]]:
    if not tag_names or minutes <= 0:
        return []

    end_time = datetime.now()
    start_time = end_time - timedelta(minutes=minutes)
    result = pspace.HisReadRaw(
        {
            T.HisReadRawTagLongName: tag_names,
            T.HisReadRawstartTime: start_time.strftime("%Y/%m/%d %H:%M:%S.000"),
            T.HisReadRawendTime: end_time.strftime("%Y/%m/%d %H:%M:%S.000"),
            T.HisReadRawMaxValues: max_values,
            T.HisReadRawBounds: 0,
        }
    )

    rows: list[dict[str, Any]] = []
    for tag_name in tag_names:
        records = result.get(tag_name, {})
        if not isinstance(records, dict):
            continue
        if "ErrorInfo" in records:
            rows.append(
                {
                    "source": "history",
                    "tag": tag_name,
                    "timestamp": "",
                    "value": "",
                    "quality": "",
                    "data_type": "",
                    "error": records.get("ErrorInfo", records.get("Error", "")),
                }
            )
            continue
        for _, record in numeric_items(records):
            if not isinstance(record, dict):
                continue
            rows.append(
                {
                    "source": "history",
                    "tag": tag_name,
                    "timestamp": record.get(T.HisReadRawTimeStamp, ""),
                    "value": record.get(T.HisReadRawValueDict, ""),
                    "quality": record.get(T.HisReadRawQualityDict, ""),
                    "data_type": record.get(T.ReadTypeDict, ""),
                    "error": "",
                }
            )
    return rows


def write_csv(rows: list[dict[str, Any]], output_dir: Path) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / f"pspace_sample_{datetime.now():%Y%m%d_%H%M%S}.csv"
    fields = ["source", "tag", "timestamp", "value", "quality", "data_type", "error"]
    with output_path.open("w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
    return output_path


def main() -> int:
    args = parse_args()
    require_credentials(args)
    PsObject, T = load_sdk(Path(args.sdk_root))

    pspace = None
    try:
        pspace, connect_result = connect(PsObject, T, args)
        print(f"connected handle={connect_result.get('Handle')}")
        print(f"server_time={pspace.GetServerTime()}")

        if args.tag:
            tags = [(0, tag) for tag in args.tag]
            print(f"explicit_tags={len(tags)}")
        else:
            tags = discover_tags(pspace, T, args.root_tag, args.max_tags, args.match)
        print(f"discovered_tags={len(tags)}")
        for tag_id, tag_name in tags[:10]:
            print(f"tag id={tag_id} name={tag_name}")

        tag_names = [name for _, name in tags]
        rows = []
        rows.extend(collect_realtime(pspace, T, tag_names))
        rows.extend(collect_history(pspace, T, tag_names, args.history_minutes, args.max_values))

        output_path = write_csv(rows, Path(args.output_dir))
        print(f"rows={len(rows)}")
        print(f"output={output_path}")
        return 0
    finally:
        if pspace is not None:
            try:
                pspace.CloseConnect()
            except Exception:
                pass


if __name__ == "__main__":
    raise SystemExit(main())
