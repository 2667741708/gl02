import asyncio
import json
import time

import websockets


async def probe(port: int) -> dict:
    url = f"ws://127.0.0.1:{port}"
    started = time.monotonic()
    async with websockets.connect(url, open_timeout=8, max_size=30_000_000) as ws:
        opened = time.monotonic()
        raw = await asyncio.wait_for(ws.recv(), timeout=45)
        received = time.monotonic()
        payload = json.loads(raw)
        return {
            "port": port,
            "handshake_seconds": round(opened - started, 3),
            "first_frame_seconds": round(received - opened, 3),
            "type": payload.get("type"),
            "timestamp": payload.get("timestamp"),
            "value_count": len(payload.get("values") or {}),
            "source": payload.get("source"),
            "replay_mode": (payload.get("replay") or {}).get("mode"),
        }


async def main() -> None:
    results = []
    for port in (8768, 8770):
        results.append(await probe(port))
    print(json.dumps(results, ensure_ascii=False, indent=2, default=str))


if __name__ == "__main__":
    asyncio.run(main())
