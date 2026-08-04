"""Load and reshape immutable V4 temporal statistics for V5 experiments.

Requirement:
    REQ-SI-TEMPORAL-SEMANTIC-V5-20260727
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Sequence

import numpy as np
import pandas as pd

from .extract_v4_temporal_stats import WINDOWS_MINUTES
from .formal_dataset import sha256_file


TEMPORAL_STATISTICS = (
    "count",
    "mean",
    "std",
    "min",
    "max",
    "slope_per_min",
    "coverage_ratio",
    "range",
    "cv",
)
WINDOW_COLUMN_PATTERN = re.compile(r"^w(?P<minutes>\d+)_")


def available_windows_minutes(
    columns: Sequence[str],
) -> tuple[int, ...]:
    """Discover complete temporal windows from an extracted table."""

    statistics_by_window: dict[int, set[str]] = {}
    for column in columns:
        match = WINDOW_COLUMN_PATTERN.match(str(column))
        if not match:
            continue
        window = int(match.group("minutes"))
        statistic = str(column)[match.end() :]
        statistics_by_window.setdefault(window, set()).add(statistic)
    windows = tuple(
        sorted(
            window
            for window, statistics in statistics_by_window.items()
            if set(TEMPORAL_STATISTICS).issubset(statistics)
        )
    )
    if not windows:
        raise ValueError("多窗口统计中没有完整的时间窗口")
    return windows


def load_temporal_statistics(directory: Path) -> tuple[pd.DataFrame, dict]:
    """Load only a completed, hashed extraction."""

    manifest_path = directory / "manifest.json"
    if not manifest_path.exists():
        raise RuntimeError(f"多窗口统计尚未完成：{manifest_path}")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    part_items = manifest.get("parts", [])
    part_names = [item["name"] for item in part_items]
    if not part_names:
        raise RuntimeError("多窗口统计manifest没有分片")
    missing = [
        name for name in part_names if not (directory / name).exists()
    ]
    if missing:
        raise RuntimeError(f"多窗口统计缺少分片：{missing[:5]}")
    hash_mismatches = [
        item["name"]
        for item in part_items
        if not item.get("sha256")
        or sha256_file(directory / item["name"]) != item["sha256"]
    ]
    if hash_mismatches:
        raise RuntimeError(
            f"多窗口统计分片SHA-256校验失败：{hash_mismatches[:5]}"
        )
    frames = [pd.read_parquet(directory / name) for name in part_names]
    output = pd.concat(frames, ignore_index=True)
    if len(output) != int(manifest["total_rows"]):
        raise RuntimeError("多窗口统计总行数与manifest不一致")
    key = ["official_meltno", "sensor_id"]
    if output[key].duplicated().any():
        raise RuntimeError("多窗口统计存在重复炉次/传感器")
    return output, manifest


def pivot_temporal_statistics(
    long_frame: pd.DataFrame,
    heat_rows: pd.DataFrame,
    *,
    statistics: Sequence[str] = TEMPORAL_STATISTICS,
    windows_minutes: Sequence[int] | None = None,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Pivot 133-point long statistics into one row per official heat."""

    required_heat = {"official_meltno", "prediction_cutoff_ts"}
    required_long = {
        "official_meltno",
        "feature_cutoff_ts",
        "sensor_id",
        "variable_name",
    }
    missing_heat = sorted(required_heat - set(heat_rows))
    missing_long = sorted(required_long - set(long_frame))
    if missing_heat:
        raise ValueError(f"炉次表缺少字段：{missing_heat}")
    if missing_long:
        raise ValueError(f"多窗口统计缺少字段：{missing_long}")
    windows = (
        tuple(int(value) for value in windows_minutes)
        if windows_minutes is not None
        else available_windows_minutes(long_frame.columns)
    )
    selected_values = [
        f"w{window}_{statistic}"
        for window in windows
        for statistic in statistics
    ]
    missing_values = sorted(set(selected_values) - set(long_frame))
    if missing_values:
        raise ValueError(f"多窗口统计值缺失：{missing_values[:10]}")

    long = long_frame.copy()
    long["feature_cutoff_ts"] = pd.to_datetime(
        long["feature_cutoff_ts"], errors="raise"
    )
    heats = heat_rows[
        ["official_meltno", "prediction_cutoff_ts"]
    ].copy()
    heats["prediction_cutoff_ts"] = pd.to_datetime(
        heats["prediction_cutoff_ts"], errors="raise"
    )
    cutoff = long[
        ["official_meltno", "feature_cutoff_ts"]
    ].drop_duplicates()
    if cutoff["official_meltno"].duplicated().any():
        raise RuntimeError("同一炉次出现多个统计截止时刻")
    aligned = heats.merge(
        cutoff,
        on="official_meltno",
        how="left",
        validate="one_to_one",
    )
    if aligned["feature_cutoff_ts"].isna().any():
        raise RuntimeError("多窗口统计未覆盖全部训练炉次")
    if bool(
        (
            aligned["prediction_cutoff_ts"]
            != aligned["feature_cutoff_ts"]
        ).any()
    ):
        raise RuntimeError("多窗口统计截止时刻与MES开铁时刻不一致")
    if long[
        ["official_meltno", "variable_name"]
    ].duplicated().any():
        raise RuntimeError("同一炉次存在重复variable_name")

    pivoted = long.pivot(
        index="official_meltno",
        columns="variable_name",
        values=selected_values,
    )
    pivoted.columns = [
        f"temporal__{variable_name}__{statistic}"
        for statistic, variable_name in pivoted.columns
    ]
    pivoted = pivoted.reset_index()
    ordered = heats[["official_meltno"]].merge(
        pivoted,
        on="official_meltno",
        how="left",
        validate="one_to_one",
    )
    feature_columns = [
        column for column in ordered if column.startswith("temporal__")
    ]
    ordered[feature_columns] = ordered[feature_columns].replace(
        [np.inf, -np.inf], np.nan
    )
    if ordered.drop(columns=["official_meltno"]).isna().all(axis=1).any():
        raise RuntimeError("多窗口宽表存在整炉全空")
    return ordered.drop(columns=["official_meltno"]), {
        "heat_rows": len(ordered),
        "physical_sensor_count": int(long["sensor_id"].nunique()),
        "semantic_variable_count": int(long["variable_name"].nunique()),
        "feature_count": len(feature_columns),
        "windows_minutes": list(windows),
        "statistics": list(statistics),
        "cutoff_alignment": "exact_match_to_MES_opentime",
    }


def _spatial_summary(
    frame: pd.DataFrame,
    columns: Sequence[str],
    prefix: str,
) -> dict[str, pd.Series]:
    available = [column for column in columns if column in frame]
    if len(available) < 2:
        return {}
    values = frame[available].apply(pd.to_numeric, errors="coerce")
    return {
        f"{prefix}__mean": values.mean(axis=1),
        f"{prefix}__std": values.std(axis=1),
        f"{prefix}__range": values.max(axis=1) - values.min(axis=1),
        f"{prefix}__max": values.max(axis=1),
        f"{prefix}__min": values.min(axis=1),
        f"{prefix}__coverage": values.notna().mean(axis=1),
    }


def derive_temporal_spatial_neurons(
    temporal: pd.DataFrame,
    *,
    windows_minutes: Sequence[int] | None = None,
) -> pd.DataFrame:
    """Aggregate temporal behavior across furnace layers and sectors."""

    output: dict[str, pd.Series] = {}
    spatial_groups: dict[str, list[str]] = {}
    for layer in range(7, 17):
        spatial_groups[f"body_L{layer}"] = [
            f"T_body_L{layer}_{sector}" for sector in "ABCDEFGH"
        ]
    for height in ("lower", "middle", "upper"):
        spatial_groups[f"static_{height}"] = [
            f"P_static_{height}_{sector}" for sector in "ABCDEF"
        ]
    spatial_groups["top_temperature"] = [
        f"T_top_{sector}" for sector in "ABCD"
    ]
    spatial_groups["top_pressure"] = [
        f"P_top_gas_{sector}" for sector in "ABCD"
    ]

    windows = (
        tuple(int(value) for value in windows_minutes)
        if windows_minutes is not None
        else available_windows_minutes(
            [
                column.removeprefix("temporal__").split("__", 1)[-1]
                for column in temporal.columns
                if column.startswith("temporal__")
            ]
        )
    )

    for window in windows:
        for statistic in ("mean", "std", "slope_per_min", "range"):
            for group_name, variables in spatial_groups.items():
                columns = [
                    f"temporal__{variable}__w{window}_{statistic}"
                    for variable in variables
                ]
                output.update(
                    _spatial_summary(
                        temporal,
                        columns,
                        (
                            f"temporal_spatial__{group_name}"
                            f"__w{window}_{statistic}"
                        ),
                    )
                )

    for window in windows:
        for sector in "ABCDEFGH":
            lower = (
                f"temporal__T_body_L7_{sector}__w{window}_mean"
            )
            upper = (
                f"temporal__T_body_L16_{sector}__w{window}_mean"
            )
            if lower in temporal and upper in temporal:
                output[
                    "temporal_spatial__body_vertical_"
                    f"L16_minus_L7_{sector}__w{window}_mean"
                ] = (
                    pd.to_numeric(temporal[upper], errors="coerce")
                    - pd.to_numeric(temporal[lower], errors="coerce")
                )
    return pd.DataFrame(output, index=temporal.index)


def select_train_correlated_features(
    train: pd.DataFrame,
    target: pd.Series,
    candidates: Sequence[str],
    *,
    top_k: int,
    minimum_non_null_ratio: float = 0.50,
) -> tuple[list[str], pd.DataFrame]:
    """Rank candidate neurons using training data only."""

    if top_k <= 0:
        raise ValueError("top_k必须大于0")
    numeric = train[list(candidates)].apply(
        pd.to_numeric, errors="coerce"
    ).replace([np.inf, -np.inf], np.nan)
    coverage = numeric.notna().mean()
    variable = numeric.nunique(dropna=True) > 1
    eligible = coverage.index[
        (coverage >= minimum_non_null_ratio) & variable
    ].tolist()
    correlations = numeric[eligible].corrwith(
        pd.to_numeric(target, errors="coerce"),
        method="spearman",
    )
    ranking = pd.DataFrame(
        {
            "feature": eligible,
            "spearman": correlations.reindex(eligible).to_numpy(float),
            "abs_spearman": correlations.reindex(eligible).abs().to_numpy(
                float
            ),
            "train_non_null_ratio": coverage.reindex(eligible).to_numpy(
                float
            ),
        }
    ).sort_values(
        ["abs_spearman", "feature"],
        ascending=[False, True],
        kind="stable",
    )
    selected = ranking["feature"].head(min(top_k, len(ranking))).tolist()
    return selected, ranking.reset_index(drop=True)
