from __future__ import annotations

import argparse
import json
import os
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[3]
DEFAULT_SDK_ROOT = ROOT / "pythonSDK(1)"
DEFAULT_CONFIG = ROOT / "ghsc" / "src" / "main" / "resources" / "application-prod.yml"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Isolated pSpace query helper for GL02 MCP.")
    parser.add_argument("action", choices=("latest", "history"))
    parser.add_argument("--tag", action="append", required=True, dest="tags")
    parser.add_argument("--start", default="")
    parser.add_argument("--end", default="")
    parser.add_argument("--limit", type=int, default=500)
    parser.add_argument("--server", default=os.getenv("PSPACE_SERVER", "10.22.181.243"))
    parser.add_argument("--port", default=os.getenv("PSPACE_PORT", "8889"))
    parser.add_argument("--sdk-root", default=os.getenv("PSPACE_SDK_ROOT", str(DEFAULT_SDK_ROOT)))
    parser.add_argument("--config", default=os.getenv("PSPACE_CONFIG", str(DEFAULT_CONFIG)))
    parser.add_argument("--interval-seconds", type=int, default=int(os.getenv("BF_MCP_PSPACE_INTERVAL_SECONDS", "60")))
    parser.add_argument("--aggregate", default=os.getenv("BF_MCP_PSPACE_AGGREGATE", "PS_HIS_AVERAGE"))
    return parser.parse_args()


def clean_config_value(raw: str) -> str:
    value = raw.split("#", 1)[0].strip()
    if len(value) >= 2 and value[0] in {"'", '"'} and value[-1] == value[0]:
        return value[1:-1]
    return value


def read_pspace_config(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}
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
    return values


def parse_dt(value: str) -> datetime:
    dt = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    if dt.tzinfo:
        dt = dt.astimezone(timezone(timedelta(hours=8))).replace(tzinfo=None)
    return dt


def ps_time(value: datetime) -> str:
    return value.strftime("%Y/%m/%d %H:%M:%S.000")


def numeric_items(mapping: dict[str, Any] | dict[int, Any]):
    def sort_key(item):
        try:
            return int(item[0])
        except Exception:
            return 10**12

    for key, value in sorted(mapping.items(), key=sort_key):
        try:
            int(key)
        except Exception:
            continue
        yield key, value


def main() -> None:
    args = parse_args()
    config = read_pspace_config(Path(args.config))
    sdk_root = Path(args.sdk_root)
    sys.path.insert(0, str(sdk_root))
    from PythonAPI.PsServer import PsObject
    from PythonAPI import Type as T

    connection = {
        T.ServerDict: args.server or config.get("ip") or "10.22.181.243",
        T.ServerPortDict: str(args.port or config.get("port") or "8889"),
        T.UserDict: os.getenv("PSPACE_USER") or config.get("username") or "",
        T.PassDict: os.getenv("PSPACE_PASSWORD") or config.get("password") or "",
    }
    pspace = PsObject()
    try:
        result = pspace.Connect(connection)
        if result.get(T.Return) != 0:
            raise RuntimeError(f"Connect failed: return={result.get(T.Return)} error={result.get(T.Error)}")
        if args.action == "latest":
            raw = pspace.RealReadList({T.RealReadListTagNameBuffer: args.tags})
            latest_by_tag: dict[str, dict[str, Any]] = {}
            for _, item in numeric_items(raw):
                if not isinstance(item, dict):
                    continue
                tag = str(item.get(T.TagLongNameDict, "") or "")
                if not tag:
                    continue
                latest_by_tag[tag] = {
                    "ts": item.get(T.PsRealReadListTimeStamp, ""),
                    "value": item.get(T.PsRealReadListValueDict, None),
                    "quality": item.get(T.PsRealReadListListQualityDict, ""),
                    "value_type": "",
                    "aggregate": "REALTIME",
                    "interval_seconds": 0,
                    "source_server": f"{connection[T.ServerDict]}:{connection[T.ServerPortDict]}",
                }
            latest = latest_by_tag.get(args.tags[0]) if len(args.tags) == 1 else None
            print(json.dumps({"ok": True, "latest": latest, "latest_by_tag": latest_by_tag}, ensure_ascii=False, default=str))
            return
        if len(args.tags) != 1:
            raise ValueError("history action accepts exactly one --tag")
        tag = args.tags[0]
        start = parse_dt(args.start)
        end = parse_dt(args.end)
        raw = pspace.HisReadProcessed(
            {
                T.HisReadProcessedTagNameBuffer: [tag],
                T.HisReadProcessedstartTime: ps_time(start),
                T.HisReadProcessedendTime: ps_time(end),
                T.HisReadProcessedInterval: int(args.interval_seconds),
                T.HisReadProcessedStatistics: [args.aggregate],
            }
        )
        records = raw.get(tag, {})
        rows = []
        if isinstance(records, dict):
            for _, rec in numeric_items(records):
                if not isinstance(rec, dict):
                    continue
                rows.append(
                    {
                        "ts": rec.get(T.TimeStamp, ""),
                        "value": rec.get(T.ValueDict, None),
                        "quality": rec.get(T.QualityDict, ""),
                        "value_type": rec.get(T.ReadTypeDict, ""),
                        "aggregate": args.aggregate,
                        "interval_seconds": int(args.interval_seconds),
                        "source_server": f"{connection[T.ServerDict]}:{connection[T.ServerPortDict]}",
                    }
                )
                if len(rows) >= args.limit:
                    break
        print(json.dumps({"ok": True, "count": len(rows), "data": rows}, ensure_ascii=False, default=str))
    finally:
        try:
            pspace.CloseConnect()
        except Exception:
            pass


if __name__ == "__main__":
    main()
