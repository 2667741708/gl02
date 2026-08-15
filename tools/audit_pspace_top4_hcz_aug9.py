# -*- coding: utf-8 -*-
"""Read the four GL02 top-temperature tags from pSpace for the HCZ event.

This script is intentionally read-only. It is designed to run from the 220.12
project root, where the pSpace SDK and trend backend are available.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import sys
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any


TOP_TAGS = {
    "T_top_A": r"\冀南钢铁\SIO\GL02\LD\SIO_GL02_LD_T0040",
    "T_top_B": r"\冀南钢铁\SIO\GL02\LD\SIO_GL02_LD_T0064",
    "T_top_C": r"\冀南钢铁\SIO\GL02\LD\SIO_GL02_LD_T0072",
    "T_top_D": r"\冀南钢铁\SIO\GL02\LD\SIO_GL02_LD_T0043",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--start", default="2026-08-09 20:00:00")
    parser.add_argument("--end", default="2026-08-10 07:00:00")
    parser.add_argument("--step-seconds", type=int, default=60)
    return parser.parse_args()


def find_project_root() -> Path:
    candidates = [Path.cwd(), Path(__file__).resolve().parents[1]]
    for candidate in candidates:
        if (candidate / "趋势分析" / "trend_backend").is_dir():
            return candidate
    raise RuntimeError("220.12 project root with trend backend was not found")


def find_sdk_root(project_root: Path) -> Path:
    candidates = [
        project_root / "pythonSDK(1)",
        Path(r"F:\高炉炼铁项目-real-sensor-v2_V3\pythonSDK(1)"),
        Path(r"F:\pythonSDK(1)"),
    ]
    for candidate in candidates:
        if (candidate / "PythonAPI" / "PsServer.py").is_file():
            return candidate
    raise RuntimeError("pSpace PythonAPI SDK was not found in the controlled candidates")


def finite_number(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def hour_floor(value: datetime) -> datetime:
    return value.replace(minute=0, second=0, microsecond=0)


def round_value(value: float | None) -> float | None:
    return None if value is None else round(value, 3)


def sha256_json(value: Any) -> str:
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def main() -> int:
    args = parse_args()
    start = datetime.strptime(args.start, "%Y-%m-%d %H:%M:%S")
    end = datetime.strptime(args.end, "%Y-%m-%d %H:%M:%S")
    if end <= start:
        raise ValueError("end must be later than start")
    if args.step_seconds <= 0:
        raise ValueError("step-seconds must be positive")

    root = find_project_root()
    backend = root / "趋势分析" / "trend_backend"
    sys.path.insert(0, str(backend))
    import pspace_history  # type: ignore  # noqa: E402

    config_candidates = [
        root / "ghsc" / "src" / "main" / "resources" / "application-prod.yml",
        root / "ghsc" / "src" / "main" / "resources" / "application-dev.yml",
    ]
    config_path = next((path for path in config_candidates if path.exists()), config_candidates[-1])
    connection = pspace_history.resolve_connection(
        config_path=config_path,
        server="10.22.181.243",
        port="8889",
    )
    sdk_root = find_sdk_root(root)
    ps_object, constants = pspace_history.load_sdk(sdk_root)
    pspace = pspace_history.connect_pspace(ps_object, constants, connection)
    try:
        raw_result = pspace_history.read_processed_batch(
            pspace,
            constants,
            list(TOP_TAGS.values()),
            start,
            end,
            args.step_seconds,
            "PS_HIS_AVERAGE",
        )
    finally:
        pspace_history.close_pspace(pspace)

    series, qualities, errors = pspace_history.parse_processed_result(
        raw_result,
        constants,
        list(TOP_TAGS.values()),
    )
    hourly_values: dict[datetime, dict[str, list[float]]] = defaultdict(lambda: defaultdict(list))
    point_counts: dict[str, int] = {}
    for variable_name, tag in TOP_TAGS.items():
        count = 0
        for ts_text, raw_value in sorted(series.get(tag, {}).items()):
            ts = pspace_history.parse_timestamp(ts_text)
            value = finite_number(raw_value)
            if ts is None or value is None or ts < start or ts >= end:
                continue
            hourly_values[hour_floor(ts)][variable_name].append(value)
            count += 1
        point_counts[variable_name] = count

    hours = []
    current = hour_floor(start)
    final_hour = hour_floor(end - timedelta(microseconds=1))
    while current <= final_hour:
        point_means: dict[str, float | None] = {}
        counts: dict[str, int] = {}
        for variable_name in TOP_TAGS:
            values = hourly_values.get(current, {}).get(variable_name, [])
            counts[variable_name] = len(values)
            point_means[variable_name] = round_value(sum(values) / len(values)) if values else None
        valid_means = [value for value in point_means.values() if value is not None]
        hours.append(
            {
                "hour": current.strftime("%Y-%m-%d %H:%M:%S"),
                "point_means_c": point_means,
                "four_point_mean_c": round_value(sum(valid_means) / len(valid_means)) if len(valid_means) == 4 else None,
                "sample_counts": counts,
            }
        )
        current += timedelta(hours=1)

    evidence = {
        "schema": "bf.hcz.pspace-top4-audit.v1",
        "read_only": True,
        "source": "pSpace 10.22.181.243:8889 processed history PS_HIS_AVERAGE",
        "window": {"start": args.start, "end_exclusive": args.end, "step_seconds": args.step_seconds},
        "tags": TOP_TAGS,
        "point_counts": point_counts,
        "hourly": hours,
        "quality_keys": {tag: len(value or {}) for tag, value in (qualities or {}).items()},
        "errors": errors or {},
    }
    evidence["evidence_sha256"] = sha256_json(evidence)
    print(json.dumps(evidence, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
