"""Leakage-aware V1 heat-level dataset preparation.

This module converts the existing sample-level audit dataset into one row per
temporary heat group. It does not standardize, impute, select model features or
fit a model; those operations belong to each experiment's training split.

Requirement:
    REQ-SI-EXPERIMENT-V1-20260726
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd


TARGET_COLUMN = "target__Si_median"


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def heat_group_from_sample_no(value: Any) -> str | None:
    """Return the temporary heat key encoded in the audited sample number."""

    text = str(value or "").strip()
    if text.count("-") < 2:
        return None
    prefix, suffix = text.rsplit("-", 1)
    if not prefix or not suffix.isdigit():
        return None
    return prefix


def _read_source(path: Path) -> pd.DataFrame:
    return pd.read_csv(path, low_memory=False, encoding="utf-8-sig")


def _build_label_groups(labels: pd.DataFrame) -> pd.DataFrame:
    required = {"si_sample_no", "si_result_ts", "hot_metal_si_pct"}
    missing = sorted(required - set(labels.columns))
    if missing:
        raise ValueError(f"标签文件缺少字段：{', '.join(missing)}")
    frame = labels.copy()
    frame["temporary_heat_group"] = frame["si_sample_no"].map(
        heat_group_from_sample_no
    )
    frame["si_result_ts"] = pd.to_datetime(frame["si_result_ts"], errors="coerce")
    frame["hot_metal_si_pct"] = pd.to_numeric(
        frame["hot_metal_si_pct"], errors="coerce"
    )
    frame = frame.dropna(
        subset=["temporary_heat_group", "si_result_ts", "hot_metal_si_pct"]
    )
    grouped = (
        frame.groupby("temporary_heat_group", as_index=False)
        .agg(
            target__Si_median=("hot_metal_si_pct", "median"),
            target__Si_min=("hot_metal_si_pct", "min"),
            target__Si_max=("hot_metal_si_pct", "max"),
            target__Si_sample_count=("hot_metal_si_pct", "size"),
            label__si_result_min_ts=("si_result_ts", "min"),
            label__si_result_max_ts=("si_result_ts", "max"),
        )
        .sort_values(
            ["label__si_result_max_ts", "temporary_heat_group"],
            kind="stable",
        )
        .reset_index(drop=True)
    )
    grouped["target__Si_spread"] = (
        grouped["target__Si_max"] - grouped["target__Si_min"]
    )
    return grouped


def _earliest_safe_feature_rows(features: pd.DataFrame) -> pd.DataFrame:
    required = {"si_sample_no", "feature_end_ts"}
    missing = sorted(required - set(features.columns))
    if missing:
        raise ValueError(f"特征文件缺少字段：{', '.join(missing)}")
    frame = features.copy()
    frame["temporary_heat_group"] = frame["si_sample_no"].map(
        heat_group_from_sample_no
    )
    frame["feature_end_ts"] = pd.to_datetime(
        frame["feature_end_ts"], errors="coerce"
    )
    frame = frame.dropna(subset=["temporary_heat_group", "feature_end_ts"])
    frame = frame.sort_values(
        ["feature_end_ts", "si_sample_no"], kind="stable"
    )
    frame = frame.drop_duplicates("temporary_heat_group", keep="first")
    return frame.reset_index(drop=True)


def _attach_available_history(
    heat_rows: pd.DataFrame, all_label_groups: pd.DataFrame
) -> pd.DataFrame:
    """Attach only Si labels published before the current feature cutoff."""

    rows = heat_rows.sort_values(
        ["feature_end_ts", "temporary_heat_group"], kind="stable"
    ).copy()
    label_rows = all_label_groups.sort_values(
        ["label__si_result_max_ts", "temporary_heat_group"], kind="stable"
    ).to_dict("records")
    available_values: list[float] = []
    available_groups: list[str] = []
    cursor = 0
    outputs: list[dict[str, Any]] = []
    for _, row in rows.iterrows():
        cutoff = row["feature_end_ts"]
        while (
            cursor < len(label_rows)
            and label_rows[cursor]["label__si_result_max_ts"] <= cutoff
        ):
            available_values.append(float(label_rows[cursor][TARGET_COLUMN]))
            available_groups.append(
                str(label_rows[cursor]["temporary_heat_group"])
            )
            cursor += 1
        recent = available_values[-6:]
        recent_groups = available_groups[-6:]
        previous_one = recent[-1] if recent else np.nan
        previous_three = recent[-3:]
        previous_six = recent[-6:]
        if len(previous_three) >= 2:
            slope_three = float(
                np.polyfit(
                    np.arange(len(previous_three), dtype=float),
                    np.asarray(previous_three, dtype=float),
                    1,
                )[0]
            )
        else:
            slope_three = np.nan
        outputs.append(
            {
                "temporary_heat_group": row["temporary_heat_group"],
                "history__available_heat_count": len(available_values),
                "history__previous_heat_group": (
                    recent_groups[-1] if recent_groups else None
                ),
                "history__previous_Si_1": previous_one,
                "history__previous_Si_median_3": (
                    float(np.median(previous_three))
                    if previous_three
                    else np.nan
                ),
                "history__previous_Si_slope_3": slope_three,
                "history__previous_Si_median_6": (
                    float(np.median(previous_six)) if previous_six else np.nan
                ),
            }
        )
    history = pd.DataFrame(outputs)
    return rows.merge(
        history,
        on="temporary_heat_group",
        how="left",
        validate="one_to_one",
    )


def assign_chronological_splits(
    frame: pd.DataFrame,
    train_ratio: float = 0.70,
    validation_ratio: float = 0.15,
) -> pd.DataFrame:
    if not 0 < train_ratio < 1:
        raise ValueError("train_ratio 必须在0到1之间")
    if not 0 < validation_ratio < 1:
        raise ValueError("validation_ratio 必须在0到1之间")
    if train_ratio + validation_ratio >= 1:
        raise ValueError("训练和验证比例之和必须小于1")
    ordered = frame.sort_values(
        ["feature_end_ts", "temporary_heat_group"], kind="stable"
    ).reset_index(drop=True)
    count = len(ordered)
    if count < 30:
        raise ValueError("炉次样本少于30，不能执行固定三段时间切分")
    train_end = int(np.floor(count * train_ratio))
    validation_end = int(np.floor(count * (train_ratio + validation_ratio)))
    split = np.full(count, "test", dtype=object)
    split[:train_end] = "train"
    split[train_end:validation_end] = "validation"
    ordered["experiment_split"] = split
    ordered["experiment_row_index"] = np.arange(count, dtype=int)
    return ordered


def build_heat_level_dataset(
    labels_path: Path,
    features_path: Path,
    train_ratio: float = 0.70,
    validation_ratio: float = 0.15,
) -> pd.DataFrame:
    labels = _read_source(labels_path)
    features = _read_source(features_path)
    label_groups = _build_label_groups(labels)
    feature_rows = _earliest_safe_feature_rows(features)
    target_columns = {
        "hot_metal_c_pct",
        "hot_metal_si_pct",
        "hot_metal_mn_pct",
        "hot_metal_p_pct",
        "hot_metal_s_pct",
        "si_result_ts",
        "si_publish_date",
        "hot_metal_tank_no",
        "shift_name",
    }
    feature_rows = feature_rows.drop(
        columns=[name for name in target_columns if name in feature_rows.columns]
    )
    merged = feature_rows.merge(
        label_groups,
        on="temporary_heat_group",
        how="inner",
        validate="one_to_one",
    )
    merged = _attach_available_history(merged, label_groups)
    return assign_chronological_splits(
        merged,
        train_ratio=train_ratio,
        validation_ratio=validation_ratio,
    )


def write_prepared_dataset(
    frame: pd.DataFrame,
    output_dir: Path,
    labels_path: Path,
    features_path: Path,
    train_ratio: float,
    validation_ratio: float,
) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    dataset_path = output_dir / "heat_level_dataset.csv"
    split_path = output_dir / "split_manifest.csv"
    frame.to_csv(dataset_path, index=False, encoding="utf-8-sig")
    split_columns = [
        "temporary_heat_group",
        "feature_end_ts",
        "label__si_result_min_ts",
        "label__si_result_max_ts",
        "target__Si_sample_count",
        "experiment_split",
        "experiment_row_index",
    ]
    frame[split_columns].to_csv(
        split_path, index=False, encoding="utf-8-sig"
    )
    split_counts = {
        str(key): int(value)
        for key, value in frame["experiment_split"].value_counts().items()
    }
    manifest = {
        "requirement_id": "REQ-SI-EXPERIMENT-V1-20260726",
        "dataset_status": "experimental_v1_proxy_alignment",
        "source": {
            "labels": {
                "path": str(labels_path.resolve()),
                "bytes": labels_path.stat().st_size,
                "sha256": sha256_file(labels_path),
            },
            "features": {
                "path": str(features_path.resolve()),
                "bytes": features_path.stat().st_size,
                "sha256": sha256_file(features_path),
            },
        },
        "shape": {
            "heat_rows": int(len(frame)),
            "columns": int(len(frame.columns)),
            "split_counts": split_counts,
        },
        "split_policy": {
            "order": "feature_end_ts ascending",
            "train_ratio": train_ratio,
            "validation_ratio": validation_ratio,
            "test_ratio": 1.0 - train_ratio - validation_ratio,
            "group_key": "temporary_heat_group",
        },
        "alignment_warnings": [
            "temporary_heat_group is derived from si_sample_no, not official meltno",
            "feature_end_ts is based on result timestamp minus a fixed 120 minute safety lag",
            "the dataset contains no exact burden chemistry lineage",
            "the dataset contains snapshot/rule features rather than complete 1-minute windows",
        ],
        "artifacts": {
            dataset_path.name: {
                "bytes": dataset_path.stat().st_size,
                "sha256": sha256_file(dataset_path),
            },
            split_path.name: {
                "bytes": split_path.stat().st_size,
                "sha256": sha256_file(split_path),
            },
        },
    }
    manifest_path = output_dir / "manifest.json"
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return manifest

