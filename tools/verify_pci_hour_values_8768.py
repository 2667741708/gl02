"""Read the existing 8768 history and reproduce hour coal totals."""

from __future__ import annotations

import asyncio
import json
from datetime import datetime, timedelta

import websockets


def parse_ts(value: str) -> datetime:
    return datetime.fromisoformat(str(value).replace("Z", "+00:00"))


async def main() -> None:
    async with websockets.connect("ws://127.0.0.1:8768", open_timeout=8, max_size=30_000_000) as ws:
        payload = json.loads(await asyncio.wait_for(ws.recv(), timeout=45))
    history = payload.get("history") or {}
    timestamps = history.get("timestamps") or []
    rates = history.get("PCI_rate") or []
    pairs = []
    for ts, value in zip(timestamps, rates):
        try:
            number = float(value)
            pairs.append((parse_ts(ts), number))
        except (TypeError, ValueError):
            continue
    latest = pairs[-1][0] if pairs else parse_ts(payload["timestamp"])
    hour_start = latest.replace(minute=0, second=0, microsecond=0)
    previous_start = hour_start - timedelta(hours=1)
    current = sum(value / 60 for ts, value in pairs if hour_start <= ts <= latest)
    previous = sum(value / 60 for ts, value in pairs if previous_start <= ts < hour_start)
    print(json.dumps({
        "latest": latest.isoformat(sep=" "),
        "rate_samples": len(pairs),
        "latest_rate": pairs[-1][1] if pairs else None,
        "current_hour_integral_t": current,
        "previous_hour_integral_t": previous,
        "current_hour_sample_count": sum(1 for ts, _ in pairs if hour_start <= ts <= latest),
        "previous_hour_sample_count": sum(1 for ts, _ in pairs if previous_start <= ts < hour_start),
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
