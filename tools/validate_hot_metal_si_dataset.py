# -*- coding: utf-8 -*-
"""Validate the local hot-metal Si dataset artifacts and leakage boundaries.

Requirement:
    REQ-HOT-METAL-SI-DATASET-20260719
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DATASET_DIR = ROOT / "reports" / "铁水硅炉况传感器数据集_20260719"
REQUIRED_FILES = {
    "hot_metal_si_labels.csv",
    "hot_metal_si_dataset_full.csv",
    "hot_metal_si_dataset_numeric.csv",
    "hot_metal_si_dataset_training_ready.csv",
    "data_dictionary.csv",
    "quality_report.md",
    "manifest.json",
}
DISPLAY_BY_KEY = {
    "cold": "热制度下行",
    "hot": "热制度上行",
}


def sha256_file(path: Path) -> str:
    """Return the SHA-256 digest of one artifact."""

    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def csv_shape(path: Path) -> tuple[list[str], int]:
    """Read a CSV header and count data rows without loading the full file."""

    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.reader(handle)
        header = next(reader)
        return header, sum(1 for _ in reader)


def parse_timestamp(value: str) -> datetime:
    """Parse a required dataset timestamp."""

    return datetime.fromisoformat(value.strip())


def validate_full_rows(
    path: Path,
    expected_rows: int,
    feature_lag_minutes: int,
    max_diagnosis_lag_minutes: int,
    max_sensor_lag_minutes: int,
) -> tuple[list[str], dict[str, Any]]:
    """Check identifiers, time ordering, lag limits, and display mapping."""

    sample_ids: set[str] = set()
    matched = 0
    duplicate_ids = 0
    leakage_rows = 0
    diagnosis_lag_violations = 0
    sensor_age_violations = 0
    display_mapping_violations = 0
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        columns = list(reader.fieldnames or [])
        row_count = 0
        for row in reader:
            row_count += 1
            sample_id = row["si_sample_id"]
            if sample_id in sample_ids:
                duplicate_ids += 1
            sample_ids.add(sample_id)
            result_ts = parse_timestamp(row["si_result_ts"])
            feature_end_ts = parse_timestamp(row["feature_end_ts"])
            expected_end = result_ts.timestamp() - feature_lag_minutes * 60
            if abs(feature_end_ts.timestamp() - expected_end) > 0.5:
                leakage_rows += 1
            diagnosis_text = row.get("diagnosis__ts", "").strip()
            if diagnosis_text:
                matched += 1
                diagnosis_ts = parse_timestamp(diagnosis_text)
                lag_seconds = (feature_end_ts - diagnosis_ts).total_seconds()
                if (
                    lag_seconds < 0
                    or lag_seconds > max_diagnosis_lag_minutes * 60
                ):
                    diagnosis_lag_violations += 1
                max_age_text = row.get("sensor__max_age_seconds", "").strip()
                if max_age_text and float(max_age_text) > max_sensor_lag_minutes * 60:
                    sensor_age_violations += 1
                key = row.get("diagnosis__main_label_key", "")
                expected_display = DISPLAY_BY_KEY.get(key)
                if expected_display and row.get(
                    "diagnosis__main_label_display"
                ) != expected_display:
                    display_mapping_violations += 1
        if row_count != expected_rows:
            raise AssertionError(
                f"full CSV row count {row_count} != manifest {expected_rows}"
            )
    metrics = {
        "rows": expected_rows,
        "unique_sample_ids": len(sample_ids),
        "diagnosis_matched_rows": matched,
        "duplicate_sample_ids": duplicate_ids,
        "feature_cutoff_violations": leakage_rows,
        "diagnosis_lag_violations": diagnosis_lag_violations,
        "sensor_age_violations": sensor_age_violations,
        "display_mapping_violations": display_mapping_violations,
    }
    return columns, metrics


def validate_training_rows(
    path: Path,
    expected_rows: int,
    min_training_sensors: int,
) -> dict[str, int]:
    """Ensure every strict-training row satisfies its documented gate."""

    violations = 0
    row_count = 0
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            row_count += 1
            if not row.get("diagnosis__ts", "").strip():
                violations += 1
            if int(float(row.get("sensor__available_count") or 0)) < min_training_sensors:
                violations += 1
    if row_count != expected_rows:
        raise AssertionError(
            f"training CSV row count {row_count} != manifest {expected_rows}"
        )
    return {"rows": row_count, "gate_violations": violations}


def validate(dataset_dir: Path) -> dict[str, Any]:
    """Run all offline validation checks and return a machine-readable summary."""

    missing = sorted(
        name for name in REQUIRED_FILES if not (dataset_dir / name).is_file()
    )
    if missing:
        raise FileNotFoundError(f"missing dataset artifacts: {', '.join(missing)}")
    manifest = json.loads((dataset_dir / "manifest.json").read_text(encoding="utf-8"))
    artifact_errors: list[str] = []
    for name, expected in manifest.get("artifacts", {}).items():
        path = dataset_dir / name
        if not path.is_file():
            artifact_errors.append(f"missing:{name}")
            continue
        if path.stat().st_size != int(expected["bytes"]):
            artifact_errors.append(f"size:{name}")
        if sha256_file(path) != expected["sha256"]:
            artifact_errors.append(f"sha256:{name}")

    shape = manifest["shape"]
    alignment = manifest["alignment"]
    full_columns, full_metrics = validate_full_rows(
        dataset_dir / "hot_metal_si_dataset_full.csv",
        int(shape["rows"]),
        int(alignment["feature_lag_minutes"]),
        int(alignment["max_diagnosis_lag_minutes"]),
        int(alignment["max_sensor_lag_minutes"]),
    )
    training_rule = str(shape["training_ready_rule"])
    min_training_sensors = int(training_rule.rsplit(">=", 1)[1].strip())
    training_metrics = validate_training_rows(
        dataset_dir / "hot_metal_si_dataset_training_ready.csv",
        int(shape["training_ready_rows"]),
        min_training_sensors,
    )
    labels_header, labels_rows = csv_shape(dataset_dir / "hot_metal_si_labels.csv")
    numeric_header, numeric_rows = csv_shape(
        dataset_dir / "hot_metal_si_dataset_numeric.csv"
    )
    dictionary_header, dictionary_rows = csv_shape(
        dataset_dir / "data_dictionary.csv"
    )
    errors = list(artifact_errors)
    if len(full_columns) != int(shape["full_columns"]):
        errors.append("full_column_count")
    if len(numeric_header) != int(shape["numeric_columns"]):
        errors.append("numeric_column_count")
    if labels_rows != int(shape["rows"]):
        errors.append("labels_row_count")
    if numeric_rows != int(shape["rows"]):
        errors.append("numeric_row_count")
    if dictionary_rows != int(shape["full_columns"]):
        errors.append("dictionary_row_count")
    for metric_name in (
        "duplicate_sample_ids",
        "feature_cutoff_violations",
        "diagnosis_lag_violations",
        "sensor_age_violations",
        "display_mapping_violations",
    ):
        if full_metrics[metric_name]:
            errors.append(metric_name)
    if full_metrics["diagnosis_matched_rows"] != int(
        shape["diagnosis_matched_rows"]
    ):
        errors.append("diagnosis_match_count")
    if training_metrics["gate_violations"]:
        errors.append("training_gate_violations")
    return {
        "status": "PASS" if not errors else "FAIL",
        "dataset_dir": str(dataset_dir),
        "artifact_errors": artifact_errors,
        "errors": errors,
        "full": full_metrics,
        "training": training_metrics,
        "labels_columns": len(labels_header),
        "dictionary_columns": len(dictionary_header),
    }


def main() -> int:
    """CLI entrypoint."""

    cli = argparse.ArgumentParser(
        description="离线验证铁水硅—炉况—传感器数据集的文件、行列、时间和训练门禁。"
    )
    cli.add_argument("--dataset-dir", type=Path, default=DEFAULT_DATASET_DIR)
    args = cli.parse_args()
    try:
        result = validate(args.dataset_dir.resolve())
    except (OSError, ValueError, KeyError, AssertionError) as exc:
        result = {
            "status": "FAIL",
            "dataset_dir": str(args.dataset_dir.resolve()),
            "error_type": type(exc).__name__,
            "error": str(exc),
        }
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["status"] == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())
