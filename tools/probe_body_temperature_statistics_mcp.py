"""Call the read-only composite body-temperature MCP tool without the model."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any


def result_payload(result: Any) -> Any:
    structured = getattr(result, "structuredContent", None)
    if structured is not None:
        return structured
    text = "\n".join(
        getattr(item, "text", str(item)) for item in getattr(result, "content", []) or []
    )
    return json.loads(text)


async def run(server: Path, minutes: int, include_points: bool) -> dict[str, Any]:
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client

    end = datetime.now().astimezone().replace(second=0, microsecond=0)
    start = end - timedelta(minutes=minutes)
    arguments = {
        "start_layer": 7,
        "end_layer": 13,
        "start_time": start.isoformat(timespec="seconds"),
        "end_time": end.isoformat(timespec="seconds"),
        "positions": list("ABCDEFGH"),
        "rolling_window_minutes": 15,
        "require_all_positions": True,
        "include_point_statistics": include_points,
    }
    params = StdioServerParameters(command=sys.executable, args=[str(server)], env=dict(os.environ))
    started = time.perf_counter()
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            available = await session.list_tools()
            names = {tool.name for tool in available.tools}
            if "query_body_temperature_statistics" not in names:
                raise RuntimeError("composite body-temperature tool is not registered")
            result = await session.call_tool("query_body_temperature_statistics", arguments)
    payload = result_payload(result)
    if isinstance(payload, dict) and isinstance(payload.get("result"), dict):
        payload = payload["result"]
    if not isinstance(payload, dict):
        raise RuntimeError("tool result is not an object")
    layers = payload.get("layer_statistics") or []
    points = payload.get("point_statistics") or []
    source = payload.get("source") or {}
    return {
        "schema": "bf.body-temperature-composite-mcp-probe.v1",
        "ok": payload.get("ok") is True,
        "elapsed_ms": round((time.perf_counter() - started) * 1000, 1),
        "arguments": arguments,
        "layer_count": len(layers),
        "layer_ids": [item.get("layer") for item in layers],
        "layer_sample_counts": [
            (item.get("statistics") or {}).get("count") for item in layers
        ],
        "point_count": len(points),
        "data_quality": payload.get("data_quality"),
        "source": {
            "service": source.get("service"),
            "profile": source.get("profile"),
            "schema": source.get("schema"),
            "object": source.get("object"),
            "read_policy": source.get("read_policy"),
        },
        "production_write_performed": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--server", type=Path, required=True)
    parser.add_argument("--minutes", type=int, default=60)
    parser.add_argument("--include-points", action="store_true")
    args = parser.parse_args()
    report = asyncio.run(run(args.server.resolve(), args.minutes, args.include_points))
    print(json.dumps(report, ensure_ascii=False, indent=2, default=str))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
