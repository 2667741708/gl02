"""Leakage-safe formal heat dataset assembly for Si V3.

Requirement:
    REQ-SI-FORMAL-DATASET-V3-20260726
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Mapping, Sequence

import numpy as np
import pandas as pd


HISTORY_FLOAT_COLUMNS = (
    "history__previous_Si_1",
    "history__previous_Si_median_3",
    "history__previous_Si_slope_3",
    "history__previous_Si_median_6",
)
HISTORY_NUMERIC_DECIMALS = 12


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def canonicalize_history_features(frame: pd.DataFrame) -> pd.DataFrame:
    """Make history floats invariant to CSV parser round-trip details."""

    output = frame.copy()
    for column in HISTORY_FLOAT_COLUMNS:
        if column in output:
            output[column] = pd.to_numeric(
                output[column], errors="coerce"
            ).round(HISTORY_NUMERIC_DECIMALS)
    return output


def attach_available_si_history(heat_rows: pd.DataFrame) -> pd.DataFrame:
    """Attach only completed labels from strictly earlier official heats."""

    required = {
        "official_meltno",
        "prediction_cutoff_ts",
        "label_available_ts",
        "target__Si_representative",
    }
    missing = sorted(required - set(heat_rows.columns))
    if missing:
        raise ValueError(f"正式炉次目标缺少字段：{', '.join(missing)}")
    ordered = heat_rows.copy()
    ordered["prediction_cutoff_ts"] = pd.to_datetime(
        ordered["prediction_cutoff_ts"], errors="coerce"
    )
    ordered["label_available_ts"] = pd.to_datetime(
        ordered["label_available_ts"], errors="coerce"
    )
    ordered = ordered.dropna(
        subset=[
            "official_meltno",
            "prediction_cutoff_ts",
            "target__Si_representative",
        ]
    ).sort_values(
        ["prediction_cutoff_ts", "official_meltno"],
        kind="stable",
    )

    prior_rows: list[dict[str, Any]] = []
    history_rows: list[dict[str, Any]] = []
    for row in ordered.to_dict("records"):
        cutoff = row["prediction_cutoff_ts"]
        available = [
            item
            for item in prior_rows
            if item["prediction_cutoff_ts"] < cutoff
            if pd.notna(item["label_available_ts"])
            and item["label_available_ts"] <= cutoff
        ]
        recent = available[-6:]
        values = [
            float(item["target__Si_representative"]) for item in recent
        ]
        previous_three = values[-3:]
        previous_six = values[-6:]
        slope_three = (
            float(
                np.polyfit(
                    np.arange(len(previous_three), dtype=float),
                    np.asarray(previous_three, dtype=float),
                    1,
                )[0]
            )
            if len(previous_three) >= 2
            else np.nan
        )
        history_rows.append(
            {
                "official_meltno": row["official_meltno"],
                "history__available_heat_count": len(available),
                "history__previous_meltno": (
                    recent[-1]["official_meltno"] if recent else None
                ),
                "history__previous_Si_1": (
                    values[-1] if values else np.nan
                ),
                "history__previous_Si_median_3": (
                    float(np.median(previous_three))
                    if previous_three
                    else np.nan
                ),
                "history__previous_Si_slope_3": slope_three,
                "history__previous_Si_median_6": (
                    float(np.median(previous_six))
                    if previous_six
                    else np.nan
                ),
            }
        )
        prior_rows.append(row)
    return canonicalize_history_features(
        ordered.merge(
            pd.DataFrame(history_rows),
            on="official_meltno",
            how="left",
            validate="one_to_one",
        )
    )


def assign_heat_time_splits(
    frame: pd.DataFrame,
    train_ratio: float = 0.70,
    validation_ratio: float = 0.15,
) -> pd.DataFrame:
    """Assign one official heat to exactly one chronological split."""

    if not 0 < train_ratio < 1:
        raise ValueError("train_ratio必须在0到1之间")
    if not 0 < validation_ratio < 1:
        raise ValueError("validation_ratio必须在0到1之间")
    if train_ratio + validation_ratio >= 1:
        raise ValueError("训练与验证比例之和必须小于1")
    ordered = frame.sort_values(
        ["prediction_cutoff_ts", "official_meltno"],
        kind="stable",
    ).reset_index(drop=True)
    if ordered["official_meltno"].duplicated().any():
        raise ValueError("正式炉次数据集存在重复meltno")
    if len(ordered) < 30:
        raise ValueError("正式炉次数少于30，不能执行固定时间外切分")
    train_end = int(np.floor(len(ordered) * train_ratio))
    validation_end = int(
        np.floor(len(ordered) * (train_ratio + validation_ratio))
    )
    split = np.full(len(ordered), "test", dtype=object)
    split[:train_end] = "train"
    split[train_end:validation_end] = "validation"
    ordered["experiment_split"] = split
    ordered["experiment_row_index"] = np.arange(len(ordered), dtype=int)
    return ordered


def assemble_formal_dataset(
    heat_targets: pd.DataFrame,
    sensor_features: pd.DataFrame,
    *,
    min_sensor_last_values: int = 100,
    train_ratio: float = 0.70,
    validation_ratio: float = 0.15,
) -> pd.DataFrame:
    """Join official heat targets with strictly pre-cutoff sensor features."""

    required_sensor = {
        "official_meltno",
        "feature_cutoff_ts",
        "sensor__available_last_count",
    }
    missing = sorted(required_sensor - set(sensor_features.columns))
    if missing:
        raise ValueError(f"传感器特征缺少字段：{', '.join(missing)}")
    targets = attach_available_si_history(heat_targets)
    targets = targets.loc[
        targets["label_available_ts"] > targets["prediction_cutoff_ts"]
    ].copy()
    targets["label_time_status"] = "complete_target_available_after_cutoff"
    features = sensor_features.copy()
    features["feature_cutoff_ts"] = pd.to_datetime(
        features["feature_cutoff_ts"], errors="coerce"
    )
    merged = targets.merge(
        features,
        on="official_meltno",
        how="inner",
        validate="one_to_one",
    )
    mismatch = (
        merged["prediction_cutoff_ts"] != merged["feature_cutoff_ts"]
    )
    if bool(mismatch.any()):
        raise ValueError("传感器特征截止时刻与MES开铁预测截止时刻不一致")
    merged = merged.loc[
        merged["sensor__available_last_count"] >= min_sensor_last_values
    ].copy()
    merged["feature_boundary"] = (
        "all_sensor_observations_strictly_before_MES_opentime"
    )
    return assign_heat_time_splits(
        merged,
        train_ratio=train_ratio,
        validation_ratio=validation_ratio,
    )


def write_dataset_artifacts(
    *,
    samples: pd.DataFrame,
    heat_targets: pd.DataFrame,
    next_sample_targets: pd.DataFrame,
    sensor_features: pd.DataFrame,
    dataset: pd.DataFrame,
    audit: Mapping[str, Any],
    output_dir: Path,
    source_metadata: Mapping[str, Any],
) -> dict[str, Any]:
    """Persist immutable local artifacts and their hashes."""

    output_dir.mkdir(parents=True, exist_ok=True)
    frames = {
        "formal_samples.csv": samples,
        "formal_heat_targets.csv": heat_targets,
        "formal_next_sample_targets.csv": next_sample_targets,
        "formal_sensor_features.csv": sensor_features,
        "formal_heat_training_dataset.csv": dataset,
        "formal_split_manifest.csv": dataset[
            [
                "official_meltno",
                "prediction_cutoff_ts",
                "label_available_ts",
                "target__Si_sample_count",
                "experiment_split",
                "experiment_row_index",
            ]
        ],
    }
    artifacts: dict[str, Any] = {}
    for name, frame in frames.items():
        path = output_dir / name
        frame.to_csv(path, index=False, encoding="utf-8-sig")
        artifacts[name] = {
            "rows": int(len(frame)),
            "columns": int(len(frame.columns)),
            "bytes": path.stat().st_size,
            "sha256": sha256_file(path),
        }
    split_counts = {
        str(key): int(value)
        for key, value in dataset["experiment_split"].value_counts().items()
    }
    manifest = {
        "requirement_id": "REQ-SI-FORMAL-DATASET-V3-20260726",
        "dataset_status": "experimental_v3_formal_meltno",
        "read_only_sources": True,
        "writes_production": False,
        "source_metadata": dict(source_metadata),
        "label_audit": dict(audit),
        "shape": {
            "training_heat_rows": int(len(dataset)),
            "columns": int(len(dataset.columns)),
            "split_counts": split_counts,
            "unique_official_meltno": int(
                dataset["official_meltno"].nunique()
            ),
        },
        "leakage_contract": {
            "group_key": "MES official_meltno",
            "split_order": "MES t_ipes_cond.opentime ascending",
            "feature_cutoff": "strictly before MES t_ipes_cond.opentime",
            "sample_time_fallback_used": False,
            "sample_number_heat_inference_used": False,
            "previous_Si_visibility": (
                "only earlier heats whose MES result_ts is <= current cutoff"
            ),
        },
        "artifacts": artifacts,
    }
    manifest_path = output_dir / "manifest.json"
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2, default=str),
        encoding="utf-8",
    )
    return manifest
