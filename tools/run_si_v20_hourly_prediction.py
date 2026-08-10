#!/usr/bin/env python3
"""Run one idempotent whole-hour V20 shadow prediction through the local API."""

from __future__ import annotations

import argparse
from datetime import datetime
import json
import sys
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


def floor_hour(value: datetime) -> datetime:
    return value.replace(minute=0, second=0, microsecond=0)


def post_hourly_prediction(base_url: str, cutoff: datetime, timeout: float) -> dict[str, Any]:
    payload = json.dumps(
        {"cutoff_ts": cutoff.isoformat(sep=" ")},
        ensure_ascii=False,
    ).encode("utf-8")
    request = Request(
        f"{base_url.rstrip('/')}/api/si-v20/hourly-predict",
        data=payload,
        headers={"Content-Type": "application/json; charset=utf-8"},
        method="POST",
    )
    try:
        with urlopen(request, timeout=timeout) as response:  # noqa: S310 - operator-provided local endpoint.
            data = json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"hourly prediction HTTP {exc.code}: {detail[:500]}") from exc
    except URLError as exc:
        raise RuntimeError(f"hourly prediction endpoint unavailable: {exc.reason}") from exc
    if not data.get("ok"):
        raise RuntimeError(str(data.get("error") or "hourly prediction failed"))
    return data


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="按整点数据截止生成一次V20生产影子预测；重复运行同一整点会返回原记录。"
    )
    parser.add_argument("--base-url", default="http://127.0.0.1:8093")
    parser.add_argument("--cutoff-ts", help="可选整点截止时间，默认服务器当前小时。")
    parser.add_argument("--timeout", type=float, default=30.0)
    parser.add_argument("--dry-run", action="store_true", help="只输出将要请求的截止时间，不调用API。")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    cutoff = datetime.fromisoformat(args.cutoff_ts.replace("T", " ")) if args.cutoff_ts else floor_hour(datetime.now())
    if cutoff.minute or cutoff.second or cutoff.microsecond:
        raise SystemExit("--cutoff-ts必须是整点，例如2026-08-09 20:00:00")
    if args.dry_run:
        result: dict[str, Any] = {
            "ok": True,
            "schema": "ops.si-v20.hourly-runner.dry-run.v1",
            "base_url": args.base_url,
            "cutoff_ts": cutoff.isoformat(sep=" "),
            "writes_prediction_audit_only": True,
        }
    else:
        result = post_hourly_prediction(args.base_url, cutoff, args.timeout)
    print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:  # noqa: BLE001 - scheduler must return a concise nonzero failure.
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False), file=sys.stderr)
        raise SystemExit(1) from exc
