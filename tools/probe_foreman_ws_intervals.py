from __future__ import annotations

import json
import time
from datetime import datetime

import websocket


def parse_timestamp(value: str) -> float | None:
    if not value:
        return None
    text = value.replace("Z", "+00:00")
    try:
        return datetime.fromisoformat(text).timestamp()
    except ValueError:
        return None


def capture(url: str, seconds: float = 12.0) -> dict:
    try:
        ws = websocket.create_connection(url, timeout=8, origin="http://10.30.220.12:8093")
    except Exception as exc:
        return {"url": url, "error": f"connect: {exc}"}
    frames = []
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        remaining = max(0.1, min(2.0, deadline - time.monotonic()))
        ws.settimeout(remaining)
        try:
            raw = ws.recv()
        except Exception:
            continue
        try:
            message = json.loads(raw)
        except (TypeError, json.JSONDecodeError):
            continue
        if message.get("type") not in {"init", "tick"}:
            continue
        frames.append({"type": message.get("type"), "timestamp": message.get("timestamp", "")})
    ws.close()
    stamps = [parse_timestamp(item["timestamp"]) for item in frames]
    stamps = [stamp for stamp in stamps if stamp is not None]
    deltas = [round((right - left) * 1000, 3) for left, right in zip(stamps, stamps[1:])]
    return {
        "url": url,
        "frame_count": len(frames),
        "first_frames": frames[:3],
        "last_frames": frames[-3:],
        "deltas_ms": deltas,
        "distinct_deltas_ms": sorted(set(deltas)),
    }


def main() -> None:
    print(json.dumps({"captures": [capture("ws://10.30.220.12:8768", seconds=70.0)]}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
