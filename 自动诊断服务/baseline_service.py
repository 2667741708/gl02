from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd
import yaml

from service_config import load_config, project_path


def _iqr(series: pd.Series) -> float:
    q1 = series.quantile(0.25)
    q3 = series.quantile(0.75)
    return float(q3 - q1)


def build_baseline_meta(history: pd.DataFrame) -> dict[str, dict[str, float]]:
    excluded = {"timestamp"}
    result: dict[str, dict[str, float]] = {}
    if history is None or history.empty:
        return result
    for col in history.columns:
        if col in excluded:
            continue
        series = pd.to_numeric(history[col], errors="coerce").dropna()
        if len(series) < 10:
            continue
        result[col] = {
            "median_ref": round(float(series.median()), 6),
            "iqr_ref": round(max(_iqr(series), 1e-6), 6),
        }
    return result


def write_runtime_baseline(meta: dict[str, Any], target: str | Path | None = None) -> Path:
    config = load_config()
    runtime_dir = project_path(config["paths"]["runtime_dir"])
    runtime_dir.mkdir(parents=True, exist_ok=True)
    path = Path(target) if target else runtime_dir / "baseline_runtime.yaml"
    path.write_text(yaml.safe_dump(meta, allow_unicode=True, sort_keys=True), encoding="utf-8")
    return path
