from __future__ import annotations

import json
import sys
from datetime import datetime, timedelta
from pathlib import Path
from urllib.request import urlopen

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "自动诊断服务"))

from abc_burden_rate import calculate_burden_rate_snapshot


def main() -> int:
    url = "http://10.30.220.12:8093/api/furnace-rules/A6/detail"
    with urlopen(url, timeout=20) as response:
        payload = json.load(response)
    evaluation = datetime.fromisoformat(str(payload["evaluation_ts"]))
    review = payload["sensor_review"]
    metrics = [*review.get("main_metrics", []), *review.get("other_metrics", [])]
    rows = []
    for metric in metrics:
        if metric.get("variable_name") not in {"L_south", "L_north", "Hopper_weight"}:
            continue
        for point in metric.get("series_60m") or []:
            rows.append({"variable_name": metric["variable_name"], "ts": point["ts"], "value": point["value"]})
    snapshot = calculate_burden_rate_snapshot(rows, evaluation)
    output = {
        "schema": "abc33.probe-burden-rate.http-audit.v1",
        "evaluation_ts": evaluation,
        "source": snapshot["source_dataset"],
        "latest_event_ts": snapshot["latest_event_ts"],
        "fresh": snapshot["fresh"],
        "values": {key: value for key, value in snapshot["values"].items() if key.startswith("BurdenRate_")},
        "counts": snapshot["interval_counts"],
        "coverage": snapshot["coverage_by_window"],
        "recent_events": [item for item in snapshot["detected_events"] if item["event_ts"] > evaluation.replace(tzinfo=None)-timedelta(minutes=30)],
        "availability": snapshot["availability"],
        "weight_threshold": snapshot["policy_version"]["ore_weight_threshold_t"],
        "weight_threshold_source": snapshot["policy_version"]["ore_weight_threshold_source"],
    }
    print(json.dumps(output, ensure_ascii=False, default=str, indent=2))
    required_from_60m = (
        "BurdenRateHalfHourDev", "BurdenRateHalfHourSlow", "BurdenRateHalfHourFast",
    )
    return 0 if all(snapshot["availability"][name] for name in required_from_60m) else 1


if __name__ == "__main__":
    raise SystemExit(main())
