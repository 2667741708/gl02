# -*- coding: utf-8 -*-
"""Collect pSpace processed history into CSV shards."""

from __future__ import annotations

import argparse
import csv
import json
import os
import re
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any


ROOT_DIR = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT_ROOT = ROOT_DIR / "高炉传感器数据"
DEFAULT_CONFIG_CANDIDATES = (
    Path(
        r"D:\文件\数据库连接方式"
        r"\6fa205f28f4a16b9eeb5de12e1e8397c_4050532619208701304_m_ghsc"
        r"\ghsc\src\main\resources\application-prod.yml"
    ),
    Path(
        r"D:\文件\数据库连接方式"
        r"\6fa205f28f4a16b9eeb5de12e1e8397c_4050532619208701304_m_ghsc"
        r"\ghsc\src\main\resources\application-dev.yml"
    ),
)
DEFAULT_SDK_CANDIDATES = (
    Path(os.getenv("PSPACE_SDK_ROOT", "")) if os.getenv("PSPACE_SDK_ROOT") else None,
    ROOT_DIR / "pythonSDK(1)",
    ROOT_DIR / "PythonAPI",
    Path(r"D:\文件\数据库连接方式\pythonSDK(1)"),
)

DATA_FIELDS = [
    "tag",
    "name",
    "description",
    "unit",
    "path_group",
    "timestamp",
    "one_minute_average_value",
    "value",
    "aggregate",
    "interval_seconds",
    "quality",
    "value_type",
]
MANIFEST_FIELDS = ["tag", "name", "description", "unit", "path_group"]
ERROR_FIELDS = ["tag", "error_type", "message", "batch_index"]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Collect pSpace processed history.")
    parser.add_argument("--sdk-root", default=os.getenv("PSPACE_SDK_ROOT"))
    parser.add_argument("--pspace-config", default=os.getenv("PSPACE_CONFIG"))
    parser.add_argument("--pspace-server", default=os.getenv("PSPACE_SERVER"))
    parser.add_argument("--pspace-port", default=os.getenv("PSPACE_PORT"))
    parser.add_argument("--pspace-user", default=os.getenv("PSPACE_USER"))
    parser.add_argument("--pspace-password", default=os.getenv("PSPACE_PASSWORD"))
    parser.add_argument("--scope", default=os.getenv("PSPACE_SCOPE", "GL01"))
    parser.add_argument("--root-path", default=os.getenv("PSPACE_ROOT_PATH"), help="Only collect tags under this pSpace node.")
    parser.add_argument("--days", type=float, default=float(os.getenv("PSPACE_DAYS", "5")))
    parser.add_argument("--start-time", help="Optional start time: YYYY-mm-dd HH:MM:SS.")
    parser.add_argument("--end-time", help="Optional end time: YYYY-mm-dd HH:MM:SS.")
    parser.add_argument("--interval-seconds", type=int, default=int(os.getenv("PSPACE_INTERVAL_SECONDS", "60")))
    parser.add_argument("--aggregate", default=os.getenv("PSPACE_AGGREGATE", "PS_HIS_AVERAGE"))
    parser.add_argument("--batch-size", type=int, default=int(os.getenv("PSPACE_BATCH_SIZE", "50")))
    parser.add_argument(
        "--split-mode",
        choices=("shard", "per-tag"),
        default=os.getenv("PSPACE_SPLIT_MODE", "shard"),
        help="Write batch shards or one CSV per tag.",
    )
    parser.add_argument("--max-tags", type=int, help="Limit selected tags for smoke tests.")
    parser.add_argument("--tag", action="append", help="Explicit tag long name. Can be repeated.")
    parser.add_argument("--out-root", default=os.getenv("PSPACE_OUTPUT_ROOT", str(DEFAULT_OUTPUT_ROOT)))
    parser.add_argument("--out-dir", default=os.getenv("PSPACE_OUTPUT_DIR"))
    parser.add_argument("--manifest-only", action="store_true")
    return parser.parse_args()


def clean_config_value(raw: str) -> str:
    value = raw.split("#", 1)[0].strip()
    if len(value) >= 2 and value[0] in {"'", '"'} and value[-1] == value[0]:
        return value[1:-1]
    return value


def read_pspace_config(explicit: str | None) -> dict[str, str]:
    candidates: list[Path] = []
    if explicit:
        candidates.append(Path(explicit))
    candidates.extend(path for path in DEFAULT_CONFIG_CANDIDATES if path.exists())

    for path in candidates:
        if not path.exists():
            continue
        values: dict[str, str] = {}
        in_pspace = False
        for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
            if re.match(r"^pspace\s*:\s*$", line):
                in_pspace = True
                continue
            if in_pspace and line.strip() and not line[:1].isspace():
                break
            if not in_pspace:
                continue
            stripped = line.strip()
            if not stripped or stripped.startswith("#") or ":" not in stripped:
                continue
            key, raw_value = stripped.split(":", 1)
            key = key.strip()
            if key in {"ip", "port", "username", "password"}:
                values[key] = clean_config_value(raw_value)
        if values:
            return values
    return {}


def find_sdk_root(explicit: str | None) -> Path:
    candidates: list[Path] = []
    if explicit:
        candidates.append(Path(explicit))
    candidates.extend(path for path in DEFAULT_SDK_CANDIDATES if path is not None)

    for path in candidates:
        if (path / "PythonAPI" / "PsServer.py").exists():
            return path
        if path.name == "PythonAPI" and (path / "PsServer.py").exists():
            return path.parent
    raise FileNotFoundError("Cannot find pSpace PythonAPI SDK. Set PSPACE_SDK_ROOT.")


def load_sdk(sdk_root: Path):
    sys.path.insert(0, str(sdk_root))
    from PythonAPI.PsServer import PsObject
    from PythonAPI import Type as T

    return PsObject, T


def resolve_connection(args: argparse.Namespace) -> dict[str, str]:
    config = read_pspace_config(args.pspace_config)
    resolved = {
        "server": args.pspace_server or config.get("ip") or "10.22.181.243",
        "port": str(args.pspace_port or config.get("port") or "8889"),
        "user": args.pspace_user or config.get("username") or "",
        "password": args.pspace_password or config.get("password") or "",
    }
    if not resolved["user"] or not resolved["password"]:
        raise SystemExit("Missing pSpace credentials. Set PSPACE_USER/PSPACE_PASSWORD or PSPACE_CONFIG.")
    return resolved


def connect_pspace(PsObject, T, connection: dict[str, str]):
    pspace = PsObject()
    result = pspace.Connect(
        {
            T.ServerDict: connection["server"],
            T.ServerPortDict: connection["port"],
            T.UserDict: connection["user"],
            T.PassDict: connection["password"],
        }
    )
    if result.get(T.Return) != 0:
        raise RuntimeError(f"pSpace Connect failed: return={result.get(T.Return)} error={result.get(T.Error)}")
    return pspace


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


def query_all_tag_names(pspace, T) -> list[str]:
    result = pspace.QueryTag({T.QueryTagLongName: "/"})
    if result.get(T.Return) != 0:
        raise RuntimeError(f"QueryTag('/') failed: return={result.get(T.Return)} error={result.get(T.Error)}")
    count = int(result.get(T.QueryTagPropNum, 0) or 0)
    return [str(result.get(i, {}).get(T.QueryTagPropName, "") or "") for i in range(count)]


def normalize_root_path(value: str | None) -> str:
    if not value:
        return ""
    normalized = value.strip().strip("\\")
    return f"\\{normalized}" if normalized else ""


def is_under_root(tag: str, root_path: str) -> bool:
    if not root_path:
        return True
    return tag == root_path or tag.startswith(f"{root_path}\\")


def looks_like_leaf_tag(tag: str, scope: str, root_path: str = "") -> bool:
    if not is_under_root(tag, root_path):
        return False
    prefix_marker = f"\\{scope}\\"
    if prefix_marker not in tag:
        return False
    rest = tag.split(prefix_marker, 1)[1]
    parts = [part for part in rest.split("\\") if part]
    if len(parts) < 2:
        return False
    leaf = parts[-1]
    return bool(re.search(r"(?:^|_)T\d{3,}$", leaf, flags=re.IGNORECASE))


def path_group_for(tag: str, scope: str) -> str:
    parts = [part for part in tag.split("\\") if part]
    try:
        index = parts.index(scope)
    except ValueError:
        return ""
    return parts[index + 1] if index + 1 < len(parts) else ""


def get_tag_props(pspace, T, tag: str, scope: str) -> dict[str, str]:
    props: dict[str, str] = {
        "tag": tag,
        "name": "",
        "description": "",
        "unit": "",
        "path_group": path_group_for(tag, scope),
    }
    try:
        result = pspace.GetTagProps(
            {
                T.GetTagPropsTagLongName: tag,
                T.GetTagPropsPropIdsList: [
                    "PS_TAG_PROP_NAME",
                    "PS_TAG_PROP_DESCRIPTION",
                    "PS_TAG_PROP_ENGINEERINGUNIT",
                ],
            }
        )
    except Exception as exc:
        props["description"] = f"GetTagProps failed: {exc}"
        return props

    for _, item in numeric_items(result):
        if not isinstance(item, dict):
            continue
        prop_id = item.get(T.GetTagPropsPropId)
        value = str(item.get(T.GetTagPropsValues, "") or "")
        if prop_id == 2:
            props["name"] = value
        elif prop_id == 5:
            props["description"] = value
        elif prop_id == 85:
            props["unit"] = value
    return props


def parse_time(value: str) -> datetime:
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y/%m/%d %H:%M:%S", "%Y-%m-%d", "%Y/%m/%d"):
        try:
            return datetime.strptime(value, fmt)
        except ValueError:
            pass
    raise ValueError(f"Unsupported time format: {value}")


def resolve_time_window(args: argparse.Namespace) -> tuple[datetime, datetime]:
    end_time = parse_time(args.end_time) if args.end_time else datetime.now()
    start_time = parse_time(args.start_time) if args.start_time else end_time - timedelta(days=args.days)
    if start_time >= end_time:
        raise SystemExit("start-time must be earlier than end-time.")
    return start_time, end_time


def format_ps_time(value: datetime) -> str:
    return value.strftime("%Y/%m/%d %H:%M:%S.000")


def discover_tags(pspace, T, args: argparse.Namespace) -> list[str]:
    if args.tag:
        tags = [tag for tag in args.tag if tag]
    else:
        root_path = normalize_root_path(args.root_path)
        tags = [tag for tag in query_all_tag_names(pspace, T) if looks_like_leaf_tag(tag, args.scope, root_path)]
    tags = sorted(dict.fromkeys(tags))
    if args.max_tags is not None:
        tags = tags[: args.max_tags]
    return tags


def read_processed(pspace, T, tags: list[str], start_time: datetime, end_time: datetime, interval: int, aggregate: str):
    return pspace.HisReadProcessed(
        {
            T.HisReadProcessedTagNameBuffer: tags,
            T.HisReadProcessedstartTime: format_ps_time(start_time),
            T.HisReadProcessedendTime: format_ps_time(end_time),
            T.HisReadProcessedInterval: interval,
            T.HisReadProcessedStatistics: [aggregate] * len(tags),
        }
    )


def rows_and_errors_from_result(
    result: dict[str, Any],
    T,
    tags: list[str],
    batch_index: int,
    tag_metadata: dict[str, dict[str, str]],
    aggregate: str,
    interval_seconds: int,
):
    rows: list[dict[str, Any]] = []
    errors: list[dict[str, str]] = []
    for tag in tags:
        records = result.get(tag)
        if not isinstance(records, dict):
            errors.append(
                {
                    "tag": tag,
                    "error_type": "missing_result",
                    "message": f"result_return={result.get(T.Return)}",
                    "batch_index": str(batch_index),
                }
            )
            continue

        item_error = records.get("Error")
        if item_error not in (None, 0, "0", ""):
            errors.append(
                {
                    "tag": tag,
                    "error_type": "api_error",
                    "message": str(item_error),
                    "batch_index": str(batch_index),
                }
            )

        tag_row_count = 0
        for _, record in numeric_items(records):
            if not isinstance(record, dict):
                continue
            metadata = tag_metadata.get(tag, {})
            rows.append(
                {
                    "tag": tag,
                    "name": metadata.get("name", ""),
                    "description": metadata.get("description", ""),
                    "unit": metadata.get("unit", ""),
                    "path_group": metadata.get("path_group", ""),
                    "timestamp": record.get(T.TimeStamp, ""),
                    "one_minute_average_value": record.get(T.ValueDict, ""),
                    "value": record.get(T.ValueDict, ""),
                    "aggregate": aggregate,
                    "interval_seconds": interval_seconds,
                    "quality": record.get(T.QualityDict, ""),
                    "value_type": record.get(T.ReadTypeDict, ""),
                }
            )
            tag_row_count += 1
        if tag_row_count == 0 and not item_error:
            errors.append(
                {
                    "tag": tag,
                    "error_type": "no_data",
                    "message": "No processed history rows returned.",
                    "batch_index": str(batch_index),
                }
            )
    return rows, errors


def write_csv(path: Path, fieldnames: list[str], rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def safe_filename(value: str, max_length: int = 80) -> str:
    value = re.sub(r'[<>:"/\\|?*\x00-\x1f]+', "_", value)
    value = re.sub(r"\s+", "_", value).strip("._ ")
    if not value:
        return "sensor"
    return value[:max_length].rstrip("._ ")


class Collector:
    def __init__(
        self,
        pspace,
        T,
        args: argparse.Namespace,
        output_dir: Path,
        start_time: datetime,
        end_time: datetime,
        tag_metadata: dict[str, dict[str, str]],
        tag_indexes: dict[str, int],
    ):
        self.pspace = pspace
        self.T = T
        self.args = args
        self.output_dir = output_dir
        self.start_time = start_time
        self.end_time = end_time
        self.tag_metadata = tag_metadata
        self.tag_indexes = tag_indexes
        self.file_index = 0
        self.total_rows = 0
        self.errors: list[dict[str, str]] = []
        self.batch_stats: list[dict[str, Any]] = []
        self.successful_tags: set[str] = set()

    def next_csv_path(self) -> Path:
        self.file_index += 1
        prefix = safe_filename(self.args.scope.lower())
        return self.output_dir / f"{prefix}_processed_{self.file_index:03d}.csv"

    def per_tag_csv_path(self, tag: str) -> Path:
        metadata = self.tag_metadata.get(tag, {})
        index = self.tag_indexes.get(tag, 0)
        leaf = tag.rsplit("\\", 1)[-1]
        path_group = metadata.get("path_group", "")
        description = metadata.get("description", "")
        label = safe_filename("_".join(part for part in (path_group, leaf, description) if part), 120)
        return self.output_dir / f"{index:04d}_{label}.csv"

    def write_rows(self, rows: list[dict[str, Any]]) -> None:
        if not rows:
            return
        if self.args.split_mode == "per-tag":
            grouped: dict[str, list[dict[str, Any]]] = {}
            for row in rows:
                grouped.setdefault(str(row["tag"]), []).append(row)
            for tag, tag_rows in grouped.items():
                write_csv(self.per_tag_csv_path(tag), DATA_FIELDS, tag_rows)
                self.file_index += 1
            return

        csv_path = self.next_csv_path()
        write_csv(csv_path, DATA_FIELDS, rows)

    def collect_batch(self, tags: list[str], batch_index: int) -> None:
        if not tags:
            return
        started = time.perf_counter()
        try:
            result = read_processed(
                self.pspace,
                self.T,
                tags,
                self.start_time,
                self.end_time,
                self.args.interval_seconds,
                self.args.aggregate,
            )
        except Exception as exc:
            if len(tags) > 1:
                middle = len(tags) // 2
                self.collect_batch(tags[:middle], batch_index)
                self.collect_batch(tags[middle:], batch_index)
                return
            self.errors.append(
                {
                    "tag": tags[0],
                    "error_type": "exception",
                    "message": str(exc),
                    "batch_index": str(batch_index),
                }
            )
            return

        result_code = result.get(self.T.Return)
        if result_code not in (0, -19997) and len(tags) > 1:
            middle = len(tags) // 2
            self.collect_batch(tags[:middle], batch_index)
            self.collect_batch(tags[middle:], batch_index)
            return
        if result_code not in (0, -19997):
            self.errors.append(
                {
                    "tag": tags[0],
                    "error_type": "read_failed",
                    "message": f"result_return={result_code} error={result.get(self.T.Error, '')}",
                    "batch_index": str(batch_index),
                }
            )
            return

        rows, errors = rows_and_errors_from_result(
            result,
            self.T,
            tags,
            batch_index,
            self.tag_metadata,
            self.args.aggregate,
            self.args.interval_seconds,
        )
        self.errors.extend(errors)
        if rows:
            self.write_rows(rows)
            self.total_rows += len(rows)
            self.successful_tags.update(row["tag"] for row in rows)
        self.batch_stats.append(
            {
                "batch_index": batch_index,
                "tag_count": len(tags),
                "row_count": len(rows),
                "result_return": result_code,
                "elapsed_seconds": round(time.perf_counter() - started, 3),
            }
        )


def output_prefix(scope: str) -> str:
    return safe_filename(scope.lower())


def write_manifest(pspace, T, tags: list[str], scope: str, output_dir: Path) -> list[dict[str, str]]:
    manifest = [get_tag_props(pspace, T, tag, scope) for tag in tags]
    write_csv(output_dir / f"{output_prefix(scope)}_tag_manifest.csv", MANIFEST_FIELDS, manifest)
    return manifest


def chunked(values: list[str], size: int):
    for index in range(0, len(values), size):
        yield values[index : index + size]


def main() -> int:
    args = parse_args()
    if args.batch_size <= 0:
        raise SystemExit("batch-size must be greater than 0.")
    if args.interval_seconds <= 0:
        raise SystemExit("interval-seconds must be greater than 0.")

    start_time, end_time = resolve_time_window(args)
    output_dir = Path(args.out_dir) if args.out_dir else Path(args.out_root) / f"{args.scope}_processed_{datetime.now():%Y%m%d_%H%M%S}"
    output_dir.mkdir(parents=True, exist_ok=True)

    sdk_root = find_sdk_root(args.sdk_root)
    connection = resolve_connection(args)
    PsObject, T = load_sdk(sdk_root)

    pspace = None
    started_at = datetime.now()
    try:
        pspace = connect_pspace(PsObject, T, connection)
        tags = discover_tags(pspace, T, args)
        manifest = write_manifest(pspace, T, tags, args.scope, output_dir)

        tag_metadata = {row["tag"]: row for row in manifest}
        tag_indexes = {tag: index for index, tag in enumerate(tags, 1)}
        collector = Collector(pspace, T, args, output_dir, start_time, end_time, tag_metadata, tag_indexes)
        if not args.manifest_only:
            for batch_index, batch_tags in enumerate(chunked(tags, args.batch_size), 1):
                collector.collect_batch(batch_tags, batch_index)

        prefix = output_prefix(args.scope)
        write_csv(output_dir / f"{prefix}_errors.csv", ERROR_FIELDS, collector.errors)
        failed_tags = {row["tag"] for row in collector.errors if row["error_type"] != "no_data"}
        no_data_tags = {row["tag"] for row in collector.errors if row["error_type"] == "no_data"}
        summary = {
            "started_at": started_at.isoformat(timespec="seconds"),
            "finished_at": datetime.now().isoformat(timespec="seconds"),
            "server": connection["server"],
            "port": connection["port"],
            "scope": args.scope,
            "root_path": normalize_root_path(args.root_path),
            "start_time": start_time.strftime("%Y-%m-%d %H:%M:%S"),
            "end_time": end_time.strftime("%Y-%m-%d %H:%M:%S"),
            "days": args.days,
            "interval_seconds": args.interval_seconds,
            "aggregate": args.aggregate,
            "batch_size": args.batch_size,
            "split_mode": args.split_mode,
            "selected_tag_count": len(tags),
            "manifest_rows": len(manifest),
            "successful_tag_count": len(collector.successful_tags),
            "no_data_tag_count": len(no_data_tags),
            "failed_tag_count": len(failed_tags),
            "total_rows": collector.total_rows,
            "processed_file_count": collector.file_index,
            "output_dir": str(output_dir),
            "manifest": str(output_dir / f"{prefix}_tag_manifest.csv"),
            "errors": str(output_dir / f"{prefix}_errors.csv"),
            "batch_stats": collector.batch_stats,
        }
        summary_path = output_dir / f"{prefix}_collect_summary.json"
        summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps({"output_dir": str(output_dir), "summary": str(summary_path), "rows": collector.total_rows}, ensure_ascii=False))
        return 0
    finally:
        if pspace is not None:
            try:
                pspace.CloseConnect()
            except Exception:
                pass


if __name__ == "__main__":
    raise SystemExit(main())
