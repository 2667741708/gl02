from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import pytest


ROOT = Path(__file__).resolve().parents[1]
TOOLS = ROOT / "tools"
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

from timeseries_leaderboard import SCHEMA, build_leaderboard  # noqa: E402
from timeseries_sidecar_service import LeaderboardStore  # noqa: E402


def row(model: str, variant: str, target: str, cutoff: str, mae: float, direction: float) -> dict:
    return {
        "model": model,
        "variant": variant,
        "target_id": target,
        "cutoff": cutoff,
        "failed": False,
        "aggregation": "1min",
        "mae": mae,
        "rmse": mae * 1.1,
        "iqr_nmae": mae / 2.0,
        "mase": mae,
        "std_ratio": 0.8,
        "diff_std_ratio": 0.7,
        "direction_accuracy": direction,
        "coverage_p10_p90": 0.8,
        "wis_80": mae * 1.2,
        "mae_m00_30": mae * 0.8,
        "mae_m31_60": mae,
        "mae_m61_120": mae * 1.2,
        "latency_ms": 10.0,
        "missing_ratio": 0.0,
    }


def test_build_leaderboard_uses_only_common_complete_cutoffs() -> None:
    rows = []
    for model, mae, direction in (("model_a", 1.0, 0.55), ("model_b", 1.5, 0.60)):
        for target in ("x", "y"):
            rows.append(row(model, "target_only", target, "2026-08-01 00:00:00", mae, direction))
    rows.append(row("model_a", "target_only", "x", "2026-08-01 01:00:00", 0.1, 0.9))

    result = build_leaderboard([pd.DataFrame(rows)], target_count=2)

    assert result["schema"] == SCHEMA
    assert result["common_cutoffs"] == ["2026-08-01 00:00:00"]
    assert result["winners"]["overall"] == "model_a::target_only"
    assert result["winners"]["direction"] == "model_b::target_only"


def test_leaderboard_store_reloads_and_rejects_wrong_schema(tmp_path: Path) -> None:
    path = tmp_path / "leaderboard.json"
    path.write_text('{"schema":"bf.timeseries.leaderboard.v1","entries":[]}', encoding="utf-8")
    store = LeaderboardStore(path)
    assert store.status()["available"] is True

    path.write_text('{"schema":"wrong"}', encoding="utf-8")
    store.cache = None
    assert store.status()["available"] is False


def test_build_leaderboard_rejects_missing_metric() -> None:
    invalid = pd.DataFrame([row("model_a", "target_only", "x", "2026-08-01 00:00:00", 1.0, 0.5)]).drop(columns=["wis_80"])
    with pytest.raises(ValueError, match="wis_80"):
        build_leaderboard([invalid], target_count=1)
