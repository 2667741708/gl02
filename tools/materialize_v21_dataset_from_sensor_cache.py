"""Materialize V21 datasets by merging a local sensor cache into a base dataset.

This is a local/offline helper.  It avoids repeating slow 220.12 reads for
history and PCI when only the sensor-window cache changes.

Requirement: REQ-SI-V21-SENSOR-CACHE-20260808.
"""

from __future__ import annotations

import argparse
from datetime import datetime
import json
from pathlib import Path
import sys
from typing import Any

import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

from build_open_minus_si_dataset_v20 import CORE_SENSOR_NAMES  # noqa: E402
from build_v20_sensor_window_cache import _safe_feature_token  # noqa: E402


TARGET_PREFIXES = ("target__",)


def _json_default(value: Any) -> Any:
    if isinstance(value, (datetime, pd.Timestamp)):
        return value.isoformat()
    if isinstance(value, np.generic):
        return value.item()
    return str(value)


def _sensor_feature_columns(frame: pd.DataFrame) -> list[str]:
    return [column for column in frame.columns if str(column).startswith("v20_sensor__")]


def _allowed_sensor_tokens_from_audit(audit_path: Path, *, scope: str) -> set[str]:
    if scope == "all":
        return set()
    payload = json.loads(audit_path.read_text(encoding="utf-8"))
    sensor_audit = payload.get("sensor_audit") or []
    if scope == "core28":
        names = {
            str(item.get("short_name"))
            for item in sensor_audit
            if str(item.get("variable_name")) in set(CORE_SENSOR_NAMES)
        }
    else:
        raise ValueError(f"unsupported sensor variable scope: {scope}")
    return {_safe_feature_token(name) for name in names if name and name != "None"}


def _filter_cache_columns(
    cache: pd.DataFrame,
    *,
    audit_path: Path | None,
    sensor_variable_scope: str,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    feature_columns = _sensor_feature_columns(cache)
    if sensor_variable_scope == "all":
        return cache[["official_meltno", "v20_sample_id", *feature_columns]].copy(), {
            "sensor_variable_scope": "all",
            "sensor_feature_columns": len(feature_columns),
        }
    if audit_path is None:
        raise ValueError("--sensor-audit is required when filtering cache by variable scope")
    allowed_tokens = _allowed_sensor_tokens_from_audit(audit_path, scope=sensor_variable_scope)
    keep_features = []
    for column in feature_columns:
        parts = str(column).split("__")
        token = parts[1] if len(parts) >= 3 else ""
        if token in allowed_tokens:
            keep_features.append(column)
    return cache[["official_meltno", "v20_sample_id", *keep_features]].copy(), {
        "sensor_variable_scope": sensor_variable_scope,
        "sensor_tokens": sorted(allowed_tokens),
        "sensor_count": len(allowed_tokens),
        "sensor_feature_columns": len(keep_features),
    }


def materialize(args: argparse.Namespace) -> dict[str, Any]:
    output_dir = args.output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    base = pd.read_csv(args.base_dataset.resolve(), low_memory=False)
    cache = pd.read_csv(args.sensor_cache.resolve(), low_memory=False)
    if "v20_sample_id" not in base.columns or "v20_sample_id" not in cache.columns:
        raise ValueError("both base dataset and sensor cache must include v20_sample_id")
    base["v20_sample_id"] = base["v20_sample_id"].astype(str)
    cache["v20_sample_id"] = cache["v20_sample_id"].astype(str)
    base_no_sensor = base.drop(columns=_sensor_feature_columns(base), errors="ignore")
    filtered_cache, filter_audit = _filter_cache_columns(
        cache,
        audit_path=args.sensor_audit.resolve() if args.sensor_audit else None,
        sensor_variable_scope=args.sensor_variable_scope,
    )
    duplicate_rows = int(filtered_cache.duplicated(subset=["v20_sample_id"]).sum())
    if duplicate_rows:
        raise ValueError(f"sensor cache has duplicate v20_sample_id rows: {duplicate_rows}")
    feature_columns = _sensor_feature_columns(filtered_cache)
    for column in feature_columns:
        filtered_cache[column] = pd.to_numeric(filtered_cache[column], errors="coerce")
    merged = base_no_sensor.merge(
        filtered_cache.drop(columns=["official_meltno"], errors="ignore"),
        on="v20_sample_id",
        how="left",
        validate="one_to_one",
    )
    merged = merged.replace([np.inf, -np.inf], np.nan)
    missing_feature_rows = int(merged[feature_columns].isna().all(axis=1).sum()) if feature_columns else len(merged)
    dataset_path = output_dir / "v20_open_minus_dataset.csv"
    labels_path = output_dir / "v20_open_minus_labels.csv"
    audit_path = output_dir / "v21_cache_merge_audit.json"
    target_columns = [column for column in merged.columns if str(column).startswith(TARGET_PREFIXES)]
    label_columns = [
        column
        for column in [
            "official_meltno",
            "v20_sample_id",
            "work_date",
            "open_ts",
            "prediction_cutoff_ts",
            "lead_minutes",
            *target_columns,
        ]
        if column in merged.columns
    ]
    merged.to_csv(dataset_path, index=False, encoding="utf-8-sig")
    merged[label_columns].to_csv(labels_path, index=False, encoding="utf-8-sig")
    audit = {
        "schema": "bf.si.v21.cache_dataset_merge.v1",
        "requirement_id": "REQ-SI-V21-SENSOR-CACHE-20260808",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "base_dataset": str(args.base_dataset.resolve()),
        "sensor_cache": str(args.sensor_cache.resolve()),
        "sensor_audit": str(args.sensor_audit.resolve()) if args.sensor_audit else None,
        "output_dataset": str(dataset_path),
        "rows": int(len(merged)),
        "base_columns_after_sensor_drop": int(len(base_no_sensor.columns)),
        "sensor_feature_columns": int(len(feature_columns)),
        "missing_all_sensor_feature_rows": missing_feature_rows,
        **filter_audit,
    }
    audit_path.write_text(
        json.dumps(audit, ensure_ascii=False, indent=2, default=_json_default),
        encoding="utf-8",
    )
    return {
        "ok": True,
        "dataset": str(dataset_path),
        "labels": str(labels_path),
        "audit": str(audit_path),
        "rows": int(len(merged)),
        "sensor_feature_columns": int(len(feature_columns)),
    }


def parser() -> argparse.ArgumentParser:
    cli = argparse.ArgumentParser(description="Merge a V21 sensor cache into a V20 base dataset.")
    cli.add_argument("--base-dataset", type=Path, required=True)
    cli.add_argument("--sensor-cache", type=Path, required=True)
    cli.add_argument("--sensor-audit", type=Path)
    cli.add_argument(
        "--sensor-variable-scope",
        choices=("all", "core28"),
        default="all",
        help="Optionally filter cached sensor columns by variable_name in the cache audit.",
    )
    cli.add_argument("--output-dir", type=Path, required=True)
    return cli


def main() -> int:
    args = parser().parse_args()
    print(json.dumps(materialize(args), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
