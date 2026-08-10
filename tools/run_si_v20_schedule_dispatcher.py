#!/usr/bin/env python3
"""Ask the local V20 API to execute every due configurable schedule."""

from __future__ import annotations

import argparse
import json
import sys
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


def dispatch(base_url: str, timeout: float) -> dict[str, Any]:
    request = Request(
        f"{base_url.rstrip('/')}/api/si-v20/schedule/dispatch",
        data=b"{}",
        headers={"Content-Type": "application/json; charset=utf-8"},
        method="POST",
    )
    try:
        with urlopen(request, timeout=timeout) as response:  # noqa: S310 - local operator endpoint.
            data = json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"schedule dispatcher HTTP {exc.code}: {detail[:500]}") from exc
    except URLError as exc:
        raise RuntimeError(f"schedule dispatcher unavailable: {exc.reason}") from exc
    if not data.get("ok") and data.get("due_count", 0) == 0:
        raise RuntimeError(str(data.get("error") or "schedule dispatcher failed"))
    return data


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="每分钟检查V20数据库定时配置并执行到期的影子预测。")
    parser.add_argument("--base-url", default="http://127.0.0.1:8093")
    parser.add_argument("--timeout", type=float, default=45.0)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)
    result = (
        {"ok": True, "schema": "ops.si-v20.schedule-dispatch.dry-run.v1", "base_url": args.base_url}
        if args.dry_run
        else dispatch(args.base_url, args.timeout)
    )
    print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:  # noqa: BLE001
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False), file=sys.stderr)
        raise SystemExit(1) from exc
