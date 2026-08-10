"""Leakage-safe V20 features for pre-tap mean-Si prediction.

V20 is an offline/shadow experiment.  It targets the operational use case
"predict the target heat's arithmetic-mean Si before the heat opens" and keeps
the production V9/V13/V19 contracts untouched.

Requirement: REQ-SI-V20-OPEN-MINUS-HITRATE-20260807.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any

import numpy as np
import pandas as pd


V20_REQUIREMENT_ID = "REQ-SI-V20-OPEN-MINUS-HITRATE-20260807"
DEFAULT_LEAD_MINUTES = (120, 90, 60, 30, 15, 0)
DEFAULT_SENSOR_WINDOWS_MINUTES = (30, 60, 120, 240, 360, 480, 720)
DEFAULT_PCI_WINDOWS_HOURS = (1, 2, 4, 6, 8, 12)
TARGET_COLUMN = "target__Si_mean"


def as_timestamp(value: Any) -> pd.Timestamp | None:
    """Return a timezone-naive pandas Timestamp, or None for invalid values."""

    result = pd.to_datetime(value, errors="coerce")
    if pd.isna(result):
        return None
    return pd.Timestamp(result).tz_localize(None)


def as_number(value: Any) -> float | None:
    """Return a finite float, or None for null/non-finite values."""

    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if np.isfinite(result) else None


def parse_int_list(value: str | Iterable[int], *, default: Iterable[int]) -> tuple[int, ...]:
    """Parse comma-separated positive integer CLI values."""

    if isinstance(value, str):
        raw_values = [item.strip() for item in value.split(",") if item.strip()]
        parsed = [int(item) for item in raw_values]
    else:
        parsed = [int(item) for item in value]
    if not parsed:
        parsed = [int(item) for item in default]
    cleaned = sorted({item for item in parsed if item >= 0})
    if not cleaned:
        raise ValueError("integer list cannot be empty")
    return tuple(cleaned)


def compute_cutoff_ts(open_ts: Any, lead_minutes: int) -> pd.Timestamp:
    """Compute ``open_ts - lead_minutes`` for pre-tap prediction samples."""

    opened = as_timestamp(open_ts)
    if opened is None:
        raise ValueError("open_ts is required to compute V20 cutoff")
    if lead_minutes < 0:
        raise ValueError("lead_minutes must be non-negative")
    return opened - pd.Timedelta(minutes=int(lead_minutes))


def expand_lead_samples(
    heats: pd.DataFrame,
    lead_minutes: Iterable[int] = DEFAULT_LEAD_MINUTES,
) -> pd.DataFrame:
    """Expand one target heat row into one row per lead-time sample."""

    required = {"official_meltno", "open_ts"}
    missing = sorted(required - set(heats.columns))
    if missing:
        raise ValueError(f"V20 lead sample source missing columns: {', '.join(missing)}")
    rows: list[dict[str, Any]] = []
    for item in heats.to_dict("records"):
        open_ts = as_timestamp(item.get("open_ts"))
        if open_ts is None:
            continue
        for lead in lead_minutes:
            row = dict(item)
            row["lead_minutes"] = int(lead)
            row["prediction_cutoff_ts"] = compute_cutoff_ts(open_ts, int(lead))
            row["v20_sample_id"] = f"{str(item['official_meltno'])}__lead_{int(lead)}m"
            rows.append(row)
    output = pd.DataFrame(rows)
    if not output.empty:
        output["official_meltno"] = output["official_meltno"].astype(str)
        output["open_ts"] = pd.to_datetime(output["open_ts"], errors="coerce")
        output["prediction_cutoff_ts"] = pd.to_datetime(
            output["prediction_cutoff_ts"], errors="coerce"
        )
    return output


def _prepare_heat_frame(heats: pd.DataFrame) -> pd.DataFrame:
    required = {
        "official_meltno",
        "open_ts",
        "label_available_ts",
        TARGET_COLUMN,
    }
    missing = sorted(required - set(heats.columns))
    if missing:
        raise ValueError(f"V20 history source missing columns: {', '.join(missing)}")
    frame = heats.copy()
    frame["official_meltno"] = frame["official_meltno"].astype(str)
    frame["open_ts"] = pd.to_datetime(frame["open_ts"], errors="coerce")
    frame["label_available_ts"] = pd.to_datetime(
        frame["label_available_ts"], errors="coerce"
    )
    frame[TARGET_COLUMN] = pd.to_numeric(frame[TARGET_COLUMN], errors="coerce")
    frame = frame.dropna(subset=["official_meltno", "open_ts"])
    frame = frame.sort_values(["open_ts", "official_meltno"], kind="stable")
    frame = frame.drop_duplicates(subset=["official_meltno"], keep="last")
    frame["v20_heat_order"] = np.arange(len(frame), dtype=int)
    return frame.reset_index(drop=True)


def build_history_gap_features(
    samples: pd.DataFrame,
    all_heats: pd.DataFrame,
) -> pd.DataFrame:
    """Build previous published Si and unlabeled-gap features.

    Visibility rule:
    - the source heat must be a strictly earlier furnace heat;
    - the source heat's label publication timestamp must be <= sample cutoff;
    - the source heat must have a finite arithmetic mean Si.

    This makes "previous 1-5 heats" mean the 1st, 2nd, 3rd, 4th and 5th
    most recent *visible published* heat values as separate columns.  Aggregate
    mean/slope features are only extra summaries.
    """

    required_samples = {"official_meltno", "prediction_cutoff_ts"}
    missing = sorted(required_samples - set(samples.columns))
    if missing:
        raise ValueError(f"V20 history sample missing columns: {', '.join(missing)}")
    heats = _prepare_heat_frame(all_heats)
    heat_by_id = {
        str(item["official_meltno"]): item for item in heats.to_dict("records")
    }
    rows: list[dict[str, Any]] = []
    for sample in samples.to_dict("records"):
        meltno = str(sample["official_meltno"])
        cutoff = as_timestamp(sample.get("prediction_cutoff_ts"))
        target_meta = heat_by_id.get(meltno)
        target_open = as_timestamp(sample.get("open_ts"))
        if target_open is None and target_meta is not None:
            target_open = as_timestamp(target_meta.get("open_ts"))
        target_order = (
            int(target_meta["v20_heat_order"]) if target_meta is not None else None
        )
        row: dict[str, Any] = {"official_meltno": meltno}
        if sample.get("v20_sample_id") is not None:
            row["v20_sample_id"] = str(sample.get("v20_sample_id"))
        if cutoff is None or target_open is None:
            rows.append(_history_empty(row))
            continue
        earlier = heats.loc[heats["open_ts"] < target_open].copy()
        visible = earlier.loc[
            earlier["label_available_ts"].notna()
            & (earlier["label_available_ts"] <= cutoff)
            & earlier[TARGET_COLUMN].notna()
        ]
        visible = visible.sort_values(["open_ts", "official_meltno"], kind="stable")
        values = visible[TARGET_COLUMN].astype(float).to_list()
        row["v20_history__visible_label_count"] = float(len(values))
        for lag in range(1, 6):
            row[f"history_mean__Si_lag_{lag}"] = (
                float(values[-lag]) if len(values) >= lag else np.nan
            )
        recent3 = values[-3:]
        recent5 = values[-5:]
        row["history_mean__Si_mean_3"] = float(np.mean(recent3)) if recent3 else np.nan
        row["history_mean__Si_mean_5"] = float(np.mean(recent5)) if recent5 else np.nan
        row["history_mean__Si_slope_5"] = (
            float(np.polyfit(np.arange(len(recent5)), recent5, 1)[0])
            if len(recent5) >= 2
            else np.nan
        )
        if not visible.empty:
            latest = visible.iloc[-1]
            row["history_mean__previous_label_age_hours"] = (
                cutoff - latest["label_available_ts"]
            ).total_seconds() / 3600.0
            row["v20_history__latest_label_age_hours_from_open"] = (
                cutoff - latest["open_ts"]
            ).total_seconds() / 3600.0
            if target_order is not None:
                distance = int(target_order - int(latest["v20_heat_order"]))
                row["v20_history__latest_label_meltno_distance"] = float(distance)
                row["v20_history__unlabeled_heat_gap"] = float(max(distance - 1, 0))
            else:
                row["v20_history__latest_label_meltno_distance"] = np.nan
                row["v20_history__unlabeled_heat_gap"] = np.nan
        else:
            row["history_mean__previous_label_age_hours"] = np.nan
            row["v20_history__latest_label_age_hours_from_open"] = np.nan
            row["v20_history__latest_label_meltno_distance"] = np.nan
            row["v20_history__unlabeled_heat_gap"] = np.nan
        recent_heats = earlier.tail(5)
        visible_recent = set(visible["official_meltno"].tail(5).astype(str))
        row["v20_history__recent5_unpublished_count"] = float(
            sum(str(item) not in visible_recent for item in recent_heats["official_meltno"])
        )
        rows.append(row)
    return pd.DataFrame(rows)


def _history_empty(base: dict[str, Any]) -> dict[str, Any]:
    base["v20_history__visible_label_count"] = 0.0
    for lag in range(1, 6):
        base[f"history_mean__Si_lag_{lag}"] = np.nan
    base["history_mean__Si_mean_3"] = np.nan
    base["history_mean__Si_mean_5"] = np.nan
    base["history_mean__Si_slope_5"] = np.nan
    base["history_mean__previous_label_age_hours"] = np.nan
    base["v20_history__latest_label_age_hours_from_open"] = np.nan
    base["v20_history__latest_label_meltno_distance"] = np.nan
    base["v20_history__unlabeled_heat_gap"] = np.nan
    base["v20_history__recent5_unpublished_count"] = np.nan
    return base


def build_pci_window_features(
    samples: pd.DataFrame,
    minute_values: pd.DataFrame,
    *,
    windows_hours: Iterable[int] = DEFAULT_PCI_WINDOWS_HOURS,
    official_hourly: pd.DataFrame | None = None,
) -> pd.DataFrame:
    """Build strict pre-cutoff PCI-rate integral features.

    ``minute_values.value`` is assumed to be a rate in t/h.  A one-minute
    sample contributes ``value / 60`` tons.  Missing data remains missing via
    coverage features; it is never filled with zero.
    """

    required_samples = {"official_meltno", "prediction_cutoff_ts"}
    missing = sorted(required_samples - set(samples.columns))
    if missing:
        raise ValueError(f"V20 PCI sample missing columns: {', '.join(missing)}")
    required_values = {"official_meltno", "ts", "value"}
    missing = sorted(required_values - set(minute_values.columns))
    if missing:
        raise ValueError(f"V20 PCI minute source missing columns: {', '.join(missing)}")
    rates = minute_values.copy()
    rates["official_meltno"] = rates["official_meltno"].astype(str)
    if "v20_sample_id" in rates.columns:
        rates["v20_sample_id"] = rates["v20_sample_id"].astype(str)
    rates["ts"] = pd.to_datetime(rates["ts"], errors="coerce")
    rates["value"] = pd.to_numeric(rates["value"], errors="coerce")
    rates = rates.dropna(subset=["ts", "value"])
    windows = tuple(sorted({int(item) for item in windows_hours if int(item) > 0}))
    official = _prepare_official_hourly_pci(official_hourly)
    rows: list[dict[str, Any]] = []
    for sample in samples.to_dict("records"):
        meltno = str(sample["official_meltno"])
        sample_id = str(sample.get("v20_sample_id")) if sample.get("v20_sample_id") is not None else None
        cutoff = as_timestamp(sample.get("prediction_cutoff_ts"))
        row: dict[str, Any] = {"official_meltno": meltno}
        if sample.get("v20_sample_id") is not None:
            row["v20_sample_id"] = str(sample.get("v20_sample_id"))
        if cutoff is None:
            rows.append(row)
            continue
        if sample_id is not None and "v20_sample_id" in rates.columns:
            target_rates = rates.loc[rates["v20_sample_id"].eq(sample_id)]
        else:
            target_rates = rates.loc[rates["official_meltno"].eq(meltno)]
        for hours in windows:
            window_start = cutoff - pd.Timedelta(hours=hours)
            window = target_rates.loc[
                (target_rates["ts"] >= window_start) & (target_rates["ts"] < cutoff)
            ]
            stats = _rate_window_stats(window["ts"], window["value"], hours)
            prefix = f"v20_pci__{hours}h"
            for key, value in stats.items():
                row[f"{prefix}_{key}"] = value
        if official is not None and meltno in official:
            row.update(official[meltno])
        rows.append(row)
    return pd.DataFrame(rows)


def _prepare_official_hourly_pci(
    official_hourly: pd.DataFrame | None,
) -> dict[str, dict[str, float | str]] | None:
    if official_hourly is None or official_hourly.empty:
        return None
    frame = official_hourly.copy()
    frame["official_meltno"] = frame["official_meltno"].astype(str)
    output: dict[str, dict[str, float | str]] = {}
    for row in frame.to_dict("records"):
        meltno = str(row["official_meltno"])
        item: dict[str, float | str] = {}
        for column in (
            "v20_pci__previous_complete_hour_amount_t",
            "v20_pci__current_hour_amount_t",
            "v20_pci__previous_complete_hour_coverage_ratio",
            "v20_pci__current_hour_coverage_ratio",
        ):
            value = as_number(row.get(column))
            item[column] = value if value is not None else np.nan
        for column in (
            "v20_pci__previous_complete_hour_source",
            "v20_pci__current_hour_source",
        ):
            if column in row and row.get(column) is not None:
                item[column] = str(row.get(column))
        output[meltno] = item
    return output


def _rate_window_stats(ts: pd.Series, values: pd.Series, hours: int) -> dict[str, float]:
    numeric = pd.to_numeric(values, errors="coerce")
    times = pd.to_datetime(ts, errors="coerce")
    valid = pd.DataFrame({"ts": times, "value": numeric}).dropna()
    expected = float(hours * 60)
    if valid.empty:
        return {
            "amount_t": np.nan,
            "avg_tph": np.nan,
            "std_tph": np.nan,
            "coverage_minutes": 0.0,
            "coverage_ratio": 0.0,
            "slope_tph_per_hour": np.nan,
        }
    values_array = valid["value"].astype(float).to_numpy()
    amount = float(values_array.sum() / 60.0)
    slope = np.nan
    if len(valid) >= 2:
        minutes = (
            valid["ts"] - valid["ts"].min()
        ).dt.total_seconds().to_numpy(dtype=float) / 60.0
        if float(np.nanmax(minutes)) > 0.0:
            slope = float(np.polyfit(minutes / 60.0, values_array, 1)[0])
    return {
        "amount_t": amount,
        "avg_tph": float(np.mean(values_array)),
        "std_tph": float(np.std(values_array, ddof=1)) if len(values_array) >= 2 else 0.0,
        "coverage_minutes": float(len(values_array)),
        "coverage_ratio": float(min(len(values_array) / expected, 1.0)),
        "slope_tph_per_hour": slope,
    }


def pivot_sensor_window_rows(
    rows: pd.DataFrame,
    samples: pd.DataFrame,
    *,
    windows_minutes: Iterable[int] = DEFAULT_SENSOR_WINDOWS_MINUTES,
) -> pd.DataFrame:
    """Pivot long SQL sensor-window aggregates into one row per sample."""

    key_column = (
        "v20_sample_id"
        if "v20_sample_id" in samples.columns and "v20_sample_id" in rows.columns
        else "official_meltno"
    )
    output: dict[str, dict[str, Any]] = {}
    for sample in samples.to_dict("records"):
        key = str(sample[key_column])
        item: dict[str, Any] = {"official_meltno": str(sample["official_meltno"])}
        if "v20_sample_id" in sample and sample.get("v20_sample_id") is not None:
            item["v20_sample_id"] = str(sample.get("v20_sample_id"))
        output[key] = item
    if rows.empty:
        return pd.DataFrame(output.values())
    frame = rows.copy()
    frame["official_meltno"] = frame["official_meltno"].astype(str)
    if "v20_sample_id" in frame.columns:
        frame["v20_sample_id"] = frame["v20_sample_id"].astype(str)
    frame["short_name"] = frame["short_name"].astype(str)
    frame["window_minutes"] = pd.to_numeric(
        frame["window_minutes"], errors="coerce"
    ).astype("Int64")
    windows = {int(item) for item in windows_minutes}
    for item in frame.to_dict("records"):
        key = str(item[key_column])
        if key not in output:
            continue
        window = item.get("window_minutes")
        if pd.isna(window) or int(window) not in windows:
            continue
        name = _safe_feature_token(str(item["short_name"]))
        prefix = f"v20_sensor__{name}__{int(window)}m"
        for source, suffix in (
            ("avg_value", "mean"),
            ("std_value", "std"),
            ("min_value", "min"),
            ("max_value", "max"),
            ("last_value", "last"),
            ("coverage_minutes", "coverage_minutes"),
            ("coverage_ratio", "coverage_ratio"),
            ("slope_per_hour", "slope_per_hour"),
        ):
            value = item.get(source)
            number = as_number(value)
            output[key][f"{prefix}_{suffix}"] = number if number is not None else np.nan
    return pd.DataFrame(output.values())


def _safe_feature_token(value: str) -> str:
    return (
        value.strip()
        .replace(" ", "_")
        .replace("/", "_")
        .replace("\\", "_")
        .replace("%", "pct")
    )


def merge_feature_blocks(base: pd.DataFrame, *blocks: pd.DataFrame) -> pd.DataFrame:
    """Merge feature blocks by ``official_meltno`` and reject target leakage."""

    if "official_meltno" not in base.columns:
        raise ValueError("base frame must include official_meltno")
    result = base.copy()
    result["official_meltno"] = result["official_meltno"].astype(str)
    for block in blocks:
        if block is None or block.empty:
            continue
        if "official_meltno" not in block.columns:
            raise ValueError("feature block missing official_meltno")
        merge_keys = (
            ["v20_sample_id"]
            if "v20_sample_id" in result.columns and "v20_sample_id" in block.columns
            else ["official_meltno"]
        )
        forbidden = [
            column
            for column in block.columns
            if column != "official_meltno" and column.startswith("target__")
        ]
        if forbidden:
            raise ValueError(f"feature block contains target columns: {forbidden[:5]}")
        prepared = block.copy()
        prepared["official_meltno"] = prepared["official_meltno"].astype(str)
        if "v20_sample_id" in prepared.columns:
            prepared["v20_sample_id"] = prepared["v20_sample_id"].astype(str)
        duplicate_columns = [
            column
            for column in prepared.columns
            if column not in merge_keys and column in result.columns
        ]
        if duplicate_columns:
            prepared = prepared.drop(columns=duplicate_columns)
        result = result.merge(prepared, on=merge_keys, how="left", validate="many_to_one")
    return result.replace([np.inf, -np.inf], np.nan)


def regression_metrics(actual: pd.Series | np.ndarray, predicted: pd.Series | np.ndarray) -> dict[str, float]:
    """Common V20 regression metrics."""

    actual_values = pd.to_numeric(pd.Series(actual), errors="coerce").to_numpy(float)
    predicted_values = pd.to_numeric(pd.Series(predicted), errors="coerce").to_numpy(float)
    mask = np.isfinite(actual_values) & np.isfinite(predicted_values)
    if not mask.any():
        return {
            "n": 0.0,
            "mae": np.nan,
            "rmse": np.nan,
            "bias": np.nan,
            "hit_rate_abs_le_002": np.nan,
            "hit_rate_abs_le_005": np.nan,
            "corr": np.nan,
            "direction_accuracy": np.nan,
        }
    a = actual_values[mask]
    p = predicted_values[mask]
    error = p - a
    if len(a) >= 2 and np.std(a) > 0 and np.std(p) > 0:
        corr = float(np.corrcoef(a, p)[0, 1])
    else:
        corr = np.nan
    direction = np.nan
    if len(a) >= 2:
        actual_delta = np.diff(a)
        predicted_delta = np.diff(p)
        valid_direction = (actual_delta != 0) & (predicted_delta != 0)
        if valid_direction.any():
            direction = float(np.mean(np.sign(actual_delta[valid_direction]) == np.sign(predicted_delta[valid_direction])))
    return {
        "n": float(len(a)),
        "mae": float(np.mean(np.abs(error))),
        "rmse": float(np.sqrt(np.mean(error**2))),
        "bias": float(np.mean(error)),
        "hit_rate_abs_le_002": float(np.mean(np.abs(error) <= 0.02)),
        "hit_rate_abs_le_005": float(np.mean(np.abs(error) <= 0.05)),
        "corr": corr,
        "direction_accuracy": direction,
    }


def daily_metrics(frame: pd.DataFrame, *, actual_col: str, prediction_col: str) -> dict[str, dict[str, float]]:
    """Compute metrics grouped by calendar day from ``open_ts`` or cutoff."""

    if frame.empty:
        return {}
    work = frame.copy()
    time_col = "open_ts" if "open_ts" in work.columns else "prediction_cutoff_ts"
    work[time_col] = pd.to_datetime(work[time_col], errors="coerce")
    work["metric_day"] = work[time_col].dt.strftime("%Y-%m-%d")
    result: dict[str, dict[str, float]] = {}
    for day, group in work.groupby("metric_day", dropna=True):
        result[str(day)] = regression_metrics(group[actual_col], group[prediction_col])
    return result


def feature_coverage(frame: pd.DataFrame, columns: Iterable[str]) -> list[dict[str, Any]]:
    """Return per-feature non-null coverage and coarse source group."""

    rows: list[dict[str, Any]] = []
    count = max(len(frame), 1)
    for column in columns:
        if column not in frame.columns:
            continue
        non_null = int(frame[column].notna().sum())
        rows.append(
            {
                "feature": column,
                "non_null": non_null,
                "missing": int(len(frame) - non_null),
                "coverage": float(non_null / count),
                "source_group": feature_group(column),
            }
        )
    return rows


def feature_group(column: str) -> str:
    if column.startswith("history_mean__") or column.startswith("v20_history__"):
        return "published_history_si"
    if column.startswith("v20_pci__") or column.startswith("pci_context__"):
        return "pci"
    if column.startswith("v20_sensor__") or column.startswith("sensor__"):
        return "physical_sensor"
    if column.startswith("chem_context__"):
        return "imes_chemistry_time_background_low_confidence"
    if column.startswith("lead_") or column == "lead_minutes":
        return "prediction_protocol"
    return "base_or_other"


def candidate_status(
    validation_metrics: Mapping[str, float],
    baseline_metrics: Mapping[str, float],
    confirm_metrics: Mapping[str, float] | None = None,
    baseline_confirm_metrics: Mapping[str, float] | None = None,
) -> str:
    """Return the V20 shadow status from the documented acceptance rule."""

    if not validation_metrics or not baseline_metrics:
        return "experimental_offline"
    validation_ok = (
        validation_metrics.get("hit_rate_abs_le_005", -np.inf)
        >= baseline_metrics.get("hit_rate_abs_le_005", np.inf)
        and validation_metrics.get("mae", np.inf)
        <= baseline_metrics.get("mae", np.inf)
    )
    if confirm_metrics is None:
        return "experimental_offline"
    confirm_baseline = baseline_confirm_metrics or baseline_metrics
    confirm_ok = (
        confirm_metrics.get("hit_rate_abs_le_005", -np.inf) >= 0.60
        and confirm_metrics.get("mae", np.inf)
        <= confirm_baseline.get("mae", np.inf)
    )
    return "experimental_shadow_candidate" if validation_ok and confirm_ok else "experimental_offline"
