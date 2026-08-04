from __future__ import annotations

import argparse
from datetime import datetime, timedelta
import json
from urllib.request import Request, urlopen


def read_json(url: str, timeout: float) -> dict:
    with urlopen(Request(url, headers={"Accept": "application/json"}), timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8", errors="replace"))


def post_json(url: str, payload: dict, timeout: float) -> dict:
    req = Request(
        url,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/json", "Accept": "application/json"},
        method="POST",
    )
    with urlopen(req, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8", errors="replace"))


def smoke_payload() -> dict:
    cutoff = datetime.now().replace(second=0, microsecond=0)
    history = [1.0 + idx * 0.01 for idx in range(60)]
    return {
        "jobs": [
            {
                "job_id": "PI",
                "target": {"id": "PI", "name": "PI", "values": history},
                "covariates": [{"id": "DP_total", "name": "DP_total", "values": [180.0 + idx * 0.02 for idx in range(60)]}],
                "context_minutes": 60,
                "prediction_minutes": 5,
                "cutoff_time": cutoff.isoformat(),
                "future_timestamps": [(cutoff + timedelta(minutes=idx)).isoformat() for idx in range(1, 6)],
            }
        ]
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Check the V3 Chronos prediction service.")
    parser.add_argument("--url", default="http://127.0.0.1:8777")
    parser.add_argument("--timeout", type=float, default=20)
    parser.add_argument("--predict-smoke", action="store_true", help="Also POST a tiny prediction request.")
    args = parser.parse_args()

    base = args.url.rstrip("/")
    status = read_json(base + "/api/chronos/status", args.timeout)
    result = {
        "status": status,
    }
    if args.predict_smoke:
        prediction = post_json(base + "/api/chronos/predict", smoke_payload(), args.timeout)
        result["prediction"] = {
            "status": prediction.get("status"),
            "type": prediction.get("type"),
            "engine": prediction.get("engine"),
            "prediction_count": prediction.get("prediction_count"),
            "target_count": prediction.get("target_count"),
        }
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if status.get("ok") or status.get("engine") == "constant" else 1


if __name__ == "__main__":
    raise SystemExit(main())
