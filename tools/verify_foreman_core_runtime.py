#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Verify that foreman core variables are present in the live 8767 WebSocket frame.

Requirement: REQ-20260516-FOREMAN-CORE-VARS
Docs: docs/test_reference.md#test-20260516-foreman-core-vars-工长核心诊断变量接入验证
"""

from __future__ import annotations

import argparse
import asyncio
import json
from typing import Any

import websockets

from verify_foreman_core_variables import EXPECTED_CORE_IDS


async def read_first_frame(url: str, timeout: float) -> dict[str, Any]:
    async with websockets.connect(url, open_timeout=timeout) as ws:
        raw = await asyncio.wait_for(ws.recv(), timeout=timeout)
    return json.loads(raw)


def summarize_series(history: dict[str, Any], values: dict[str, Any], variable: str) -> dict[str, Any]:
    series = history.get(variable)
    if not isinstance(series, list):
        series = []
    non_null = sum(item is not None for item in series)
    return {
        "in_history": variable in history,
        "history_len": len(series),
        "non_null": non_null,
        "in_values": variable in values,
        "current_is_not_null": values.get(variable) is not None,
    }


async def run(url: str, timeout: float, min_non_null: int) -> dict[str, Any]:
    frame = await read_first_frame(url, timeout)
    history = frame.get("history") if isinstance(frame.get("history"), dict) else {}
    values = frame.get("values") if isinstance(frame.get("values"), dict) else {}
    variables = {variable: summarize_series(history, values, variable) for variable in EXPECTED_CORE_IDS}
    missing = [variable for variable, item in variables.items() if not item["in_history"] or item["non_null"] < min_non_null]
    return {
        "ok": not missing,
        "url": url,
        "type": frame.get("type"),
        "timestamp": frame.get("timestamp"),
        "expected_core_count": len(EXPECTED_CORE_IDS),
        "missing_or_empty": missing,
        "variables": variables,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify live 8767 WebSocket foreman core variables.")
    parser.add_argument("--url", default="ws://127.0.0.1:8767")
    parser.add_argument("--timeout", type=float, default=10.0)
    parser.add_argument("--min-non-null", type=int, default=1)
    args = parser.parse_args()
    result = asyncio.run(run(args.url, args.timeout, args.min_non_null))
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
