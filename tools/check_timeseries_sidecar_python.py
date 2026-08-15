from __future__ import annotations

import argparse
import json
from urllib.request import Request, urlopen


def read_json(url: str, timeout: float) -> dict:
    with urlopen(Request(url, headers={"Accept": "application/json"}), timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8", errors="replace"))


def main() -> int:
    parser = argparse.ArgumentParser(description="Check the 8778 time-series benchmark sidecar.")
    parser.add_argument("--url", default="http://127.0.0.1:8778")
    parser.add_argument("--timeout", type=float, default=10.0)
    args = parser.parse_args()
    base = args.url.rstrip("/")
    result = {
        "status": read_json(base + "/api/timeseries/status", args.timeout),
        "models": read_json(base + "/api/timeseries/models", args.timeout),
        "leaderboard": read_json(base + "/api/timeseries/leaderboard", args.timeout),
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))
    valid = result["status"].get("ok") and result["leaderboard"].get("schema") == "bf.timeseries.leaderboard.v1"
    return 0 if valid else 1


if __name__ == "__main__":
    raise SystemExit(main())
