"""Leakage-safe context features for the mean-Si V19 ablation experiment.

This module is deliberately independent from V9/V13 feature contracts.  It
only creates an additional, keyed feature frame that an offline V19 runner
may merge into the existing heat table.

Requirement: REQ-SI-V19-CONTEXT-ABLATION-20260806.
The burden-chemistry fields are time-background features only: no
batch-to-heat lineage is implied by this module.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any

import numpy as np
import pandas as pd


V19_REQUIREMENT_ID = "REQ-SI-V19-CONTEXT-ABLATION-20260806"
CHEMISTRY_FIELDS = (
    "tfe",
    "feo",
    "sio2",
    "al2o3",
    "cao",
    "mgo",
    "p",
    "s",
    "tio2",
    "mno",
    "zn",
    "cr",
    "r2",
    "mgal",
    "alsi",
    "qd",
)
CHEMISTRY_MACHINES = ("JS1", "JS2")


def _timestamp(value: Any) -> pd.Timestamp | None:
    result = pd.to_datetime(value, errors="coerce")
    if pd.isna(result):
        return None
    return pd.Timestamp(result).tz_localize(None)


def _number(value: Any) -> float | None:
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if np.isfinite(result) else None


def _empty_context(keys: Iterable[Any]) -> pd.DataFrame:
    return pd.DataFrame({"official_meltno": [str(key) for key in keys]})


def build_mean_si_history_context(
    heat_targets: pd.DataFrame,
) -> pd.DataFrame:
    """Build previous-heat arithmetic-mean Si features without target leakage.

    Inputs must contain ``official_meltno``, ``prediction_cutoff_ts``,
    ``label_available_ts`` and ``target__Si_mean``.  A candidate row can only
    see a different heat whose cutoff is strictly earlier and whose label was
    published by the candidate cutoff.
    """

    required = {
        "official_meltno",
        "prediction_cutoff_ts",
        "label_available_ts",
        "target__Si_mean",
    }
    missing = sorted(required - set(heat_targets.columns))
    if missing:
        raise ValueError(f"平均Si历史特征缺少字段：{', '.join(missing)}")
    frame = heat_targets.copy()
    frame["official_meltno"] = frame["official_meltno"].astype(str)
    frame["prediction_cutoff_ts"] = pd.to_datetime(
        frame["prediction_cutoff_ts"], errors="coerce"
    )
    frame["label_available_ts"] = pd.to_datetime(
        frame["label_available_ts"], errors="coerce"
    )
    frame["target__Si_mean"] = pd.to_numeric(
        frame["target__Si_mean"], errors="coerce"
    )
    if frame["official_meltno"].duplicated().any():
        raise ValueError("平均Si历史特征要求official_meltno唯一")
    ordered = frame.sort_values(
        ["prediction_cutoff_ts", "official_meltno"], kind="stable"
    )
    prior: list[dict[str, Any]] = []
    rows: list[dict[str, Any]] = []
    for item in ordered.to_dict("records"):
        cutoff = item["prediction_cutoff_ts"]
        available = [
            earlier
            for earlier in prior
            if earlier["prediction_cutoff_ts"] < cutoff
            and pd.notna(earlier["label_available_ts"])
            and earlier["label_available_ts"] <= cutoff
            and np.isfinite(float(earlier["target__Si_mean"]))
        ]
        values = [float(earlier["target__Si_mean"]) for earlier in available]
        row: dict[str, Any] = {
            "official_meltno": str(item["official_meltno"]),
            "history_mean__available_heat_count": len(available),
        }
        for lag in range(1, 6):
            row[f"history_mean__Si_lag_{lag}"] = (
                values[-lag] if len(values) >= lag else np.nan
            )
        recent = values[-5:]
        row["history_mean__Si_mean_3"] = (
            float(np.mean(values[-3:])) if len(values) >= 1 else np.nan
        )
        row["history_mean__Si_mean_5"] = (
            float(np.mean(recent)) if recent else np.nan
        )
        row["history_mean__Si_slope_5"] = (
            float(np.polyfit(np.arange(len(recent)), recent, 1)[0])
            if len(recent) >= 2
            else np.nan
        )
        if available:
            row["history_mean__previous_label_age_hours"] = (
                cutoff - available[-1]["label_available_ts"]
            ).total_seconds() / 3600.0
        else:
            row["history_mean__previous_label_age_hours"] = np.nan
        rows.append(row)
        prior.append(item)
    return pd.DataFrame(rows)


def _hour_stats(values: pd.Series, *, total_scale: float = 60.0) -> dict[str, float]:
    numeric = pd.to_numeric(values, errors="coerce").dropna()
    coverage = float(len(numeric))
    if numeric.empty:
        return {"total": np.nan, "average": np.nan, "coverage_minutes": 0.0}
    return {
        "total": float(numeric.sum() / total_scale),
        "average": float(numeric.mean()),
        "coverage_minutes": coverage,
    }


def build_pci_context_features(
    heat_targets: pd.DataFrame,
    minute_values: pd.DataFrame,
    official_values: pd.DataFrame | None = None,
) -> pd.DataFrame:
    """Build current/previous clock-hour PCI features.

    ``minute_values`` contains ``official_meltno``, ``ts`` and ``value`` for
    the historical PCI rate fallback.  Optional ``official_values`` may carry
    ``pci_current_hour`` and ``pci_previous_hour`` values from the formal
    database points.  Missing official values fall back to strict integration
    of the minute rate; values are never replaced with zero.
    """

    required_targets = {"official_meltno", "prediction_cutoff_ts"}
    missing = sorted(required_targets - set(heat_targets.columns))
    if missing:
        raise ValueError(f"喷煤特征目标缺少字段：{', '.join(missing)}")
    required_values = {"official_meltno", "ts", "value"}
    missing = sorted(required_values - set(minute_values.columns))
    if missing:
        raise ValueError(f"喷煤分钟值缺少字段：{', '.join(missing)}")
    rates = minute_values.copy()
    rates["official_meltno"] = rates["official_meltno"].astype(str)
    rates["ts"] = pd.to_datetime(rates["ts"], errors="coerce")
    rates["value"] = pd.to_numeric(rates["value"], errors="coerce")
    rates = rates.dropna(subset=["ts", "value"])
    official = None
    if official_values is not None:
        official = official_values.copy()
        official["official_meltno"] = official["official_meltno"].astype(str)
        for column in ("pci_current_hour", "pci_previous_hour"):
            if column in official:
                official[column] = pd.to_numeric(official[column], errors="coerce")
    rows: list[dict[str, Any]] = []
    for item in heat_targets.to_dict("records"):
        meltno = str(item["official_meltno"])
        cutoff = _timestamp(item["prediction_cutoff_ts"])
        row: dict[str, Any] = {"official_meltno": meltno}
        if cutoff is None:
            rows.append(row)
            continue
        target_rates = rates.loc[rates["official_meltno"].eq(meltno)]
        hour_start = cutoff.floor("h")
        current = target_rates.loc[
            (target_rates["ts"] >= hour_start) & (target_rates["ts"] < cutoff)
        ]
        previous = target_rates.loc[
            (target_rates["ts"] >= hour_start - pd.Timedelta(hours=1))
            & (target_rates["ts"] < hour_start)
        ]
        current_stats = _hour_stats(current["value"])
        previous_stats = _hour_stats(previous["value"])
        row.update(
            {
                f"pci_context__current_hour_{key}": value
                for key, value in current_stats.items()
            }
        )
        row.update(
            {
                f"pci_context__previous_hour_{key}": value
                for key, value in previous_stats.items()
            }
        )
        current_total = current_stats["total"]
        previous_total = previous_stats["total"]
        row["pci_context__current_previous_delta"] = (
            current_total - previous_total
            if np.isfinite(current_total) and np.isfinite(previous_total)
            else np.nan
        )
        row["pci_context__current_previous_ratio"] = (
            current_total / previous_total
            if np.isfinite(current_total)
            and np.isfinite(previous_total)
            and previous_total != 0
            else np.nan
        )
        row["pci_context__source_official"] = 0.0
        if official is not None and meltno in set(official["official_meltno"]):
            official_row = official.loc[
                official["official_meltno"].eq(meltno)
            ].iloc[0]
            direct_current = _number(official_row.get("pci_current_hour"))
            direct_previous = _number(official_row.get("pci_previous_hour"))
            if direct_current is not None:
                row["pci_context__current_hour_total"] = direct_current
                row["pci_context__source_official"] = 1.0
            if direct_previous is not None:
                row["pci_context__previous_hour_total"] = direct_previous
                row["pci_context__source_official"] = 1.0
        rows.append(row)
    output = pd.DataFrame(rows)
    if not output.empty:
        current = output["pci_context__current_hour_total"]
        previous = output["pci_context__previous_hour_total"]
        output["pci_context__current_previous_delta"] = current - previous
        output["pci_context__current_previous_ratio"] = current.where(
            previous.eq(0) | previous.isna(), current / previous
        )
    return output


def build_chemistry_context_features(
    heat_targets: pd.DataFrame,
    chemistry_rows: pd.DataFrame,
    *,
    stale_hours: float = 48.0,
) -> pd.DataFrame:
    """Build publication-time IMES chemistry background features.

    The input rows must contain ``published_ts`` and ``machine`` plus the
    lower-case fields in :data:`CHEMISTRY_FIELDS`.  Only rows published by the
    prediction cutoff are considered.  ``lineage_confidence`` is always zero
    because this view has no verified batch-to-heat lineage.
    """

    required = {"official_meltno", "prediction_cutoff_ts"}
    missing = sorted(required - set(heat_targets.columns))
    if missing:
        raise ValueError(f"炉料化学目标缺少字段：{', '.join(missing)}")
    required_rows = {"published_ts", "machine", *CHEMISTRY_FIELDS}
    missing = sorted(required_rows - set(chemistry_rows.columns))
    if missing:
        raise ValueError(f"炉料化学记录缺少字段：{', '.join(missing)}")
    chemistry = chemistry_rows.copy()
    chemistry["published_ts"] = pd.to_datetime(
        chemistry["published_ts"], errors="coerce"
    )
    chemistry["machine"] = chemistry["machine"].astype(str).str.upper()
    for field in CHEMISTRY_FIELDS:
        chemistry[field] = pd.to_numeric(chemistry[field], errors="coerce")
    chemistry = chemistry.dropna(subset=["published_ts"])
    rows: list[dict[str, Any]] = []
    for item in heat_targets.to_dict("records"):
        meltno = str(item["official_meltno"])
        cutoff = _timestamp(item["prediction_cutoff_ts"])
        row: dict[str, Any] = {
            "official_meltno": meltno,
            "chem_context__lineage_confidence": 0.0,
            "chem_context__stale_hours_limit": float(stale_hours),
        }
        if cutoff is None:
            rows.append(row)
            continue
        visible = chemistry.loc[chemistry["published_ts"] <= cutoff]
        recent_12 = visible.loc[
            visible["published_ts"] >= cutoff - pd.Timedelta(hours=12)
        ]
        recent_24 = visible.loc[
            visible["published_ts"] >= cutoff - pd.Timedelta(hours=24)
        ]
        for machine in CHEMISTRY_MACHINES:
            machine_rows = visible.loc[visible["machine"].eq(machine)]
            latest = machine_rows.iloc[-1] if not machine_rows.empty else None
            for field in CHEMISTRY_FIELDS:
                row[f"chem_context__{field}__latest__{machine}"] = (
                    float(latest[field])
                    if latest is not None and pd.notna(latest[field])
                    else np.nan
                )
            row[f"chem_context__latest_age_hours__{machine}"] = (
                (cutoff - latest["published_ts"]).total_seconds() / 3600.0
                if latest is not None
                else np.nan
            )
        for window_name, window_rows in (("12h", recent_12), ("24h", recent_24)):
            row[f"chem_context__sample_count__{window_name}"] = float(
                len(window_rows)
            )
            for field in CHEMISTRY_FIELDS:
                row[f"chem_context__{field}__mean__{window_name}"] = (
                    float(window_rows[field].mean())
                    if window_rows[field].notna().any()
                    else np.nan
                )
                row[f"chem_context__{field}__std__{window_name}"] = (
                    float(window_rows[field].std(ddof=1))
                    if window_rows[field].notna().sum() >= 2
                    else np.nan
                )
        ages = [
            row[f"chem_context__latest_age_hours__{machine}"]
            for machine in CHEMISTRY_MACHINES
        ]
        row["chem_context__stale_flag"] = float(
            not any(np.isfinite(age) and age <= stale_hours for age in ages)
        )
        rows.append(row)
    return pd.DataFrame(rows)


def merge_v19_context_features(
    base: pd.DataFrame,
    *context_frames: pd.DataFrame,
) -> pd.DataFrame:
    """Merge keyed V19 blocks and reject duplicate or target-bearing columns."""

    output = base.copy()
    if output["official_meltno"].astype(str).duplicated().any():
        raise ValueError("V19特征合并要求基础炉次键唯一")
    for context in context_frames:
        if context.empty:
            continue
        if "official_meltno" not in context:
            raise ValueError("V19上下文特征缺少official_meltno")
        context = context.copy()
        context["official_meltno"] = context["official_meltno"].astype(str)
        if context["official_meltno"].duplicated().any():
            raise ValueError("V19上下文特征official_meltno重复")
        forbidden = [column for column in context if column.startswith("target__")]
        if forbidden:
            raise ValueError(f"V19上下文特征包含目标字段：{forbidden}")
        duplicate = sorted(
            set(output.columns).intersection(context.columns) - {"official_meltno"}
        )
        if duplicate:
            raise ValueError(f"V19上下文特征列重复：{duplicate}")
        output = output.merge(
            context, on="official_meltno", how="left", validate="one_to_one"
        )
    return output


def context_feature_groups(frame: pd.DataFrame) -> dict[str, list[str]]:
    """Return deterministic feature groups for V19 ablation recipes."""

    return {
        "history_si": sorted(
            column for column in frame if column.startswith("history_mean__")
        ),
        "pci": sorted(
            column for column in frame if column.startswith("pci_context__")
        ),
        "chemistry": sorted(
            column for column in frame if column.startswith("chem_context__")
        ),
    }
