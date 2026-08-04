"""Strict MES label contract for formal heat-level Si experiments.

The contract deliberately separates three prediction tasks:

* ``heat_representative_si``: one representative Si value for an official heat;
* ``next_sample_si``: the next chronologically sampled Si value;
* ``heat_si_distribution``: the within-heat Si distribution.

An official ``meltno`` is mandatory.  This module never derives a heat number
from a sample number and never substitutes result/judgement time for sample
time.

Requirement:
    REQ-SI-FORMAL-LABEL-CONTRACT-V3-20260726
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

import numpy as np
import pandas as pd


CONTRACT_VERSION = "si_label_contract.v3"
REPRESENTATIVE_TASK = "heat_representative_si"
NEXT_SAMPLE_TASK = "next_sample_si"
DISTRIBUTION_TASK = "heat_si_distribution"
SUPPORTED_TASKS = (
    REPRESENTATIVE_TASK,
    NEXT_SAMPLE_TASK,
    DISTRIBUTION_TASK,
)


@dataclass(frozen=True)
class LabelBuildResult:
    """Normalized sample labels, heat targets, next-sample targets and audit."""

    samples: pd.DataFrame
    heat_targets: pd.DataFrame
    next_sample_targets: pd.DataFrame
    audit: dict[str, Any]


def _require_columns(frame: pd.DataFrame, required: set[str], name: str) -> None:
    missing = sorted(required - set(frame.columns))
    if missing:
        raise ValueError(f"{name}缺少字段：{', '.join(missing)}")


def _finite_number(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if np.isfinite(number) else None


def _quantile(values: pd.Series, probability: float) -> float:
    return float(np.quantile(values.to_numpy(dtype=float), probability))


def _stage_for_sample(
    sample_ts: pd.Timestamp | pd.NaT,
    open_ts: pd.Timestamp | pd.NaT,
    close_ts: pd.Timestamp | pd.NaT,
) -> str:
    if pd.isna(sample_ts):
        return "unknown_missing_sample_time"
    if pd.isna(open_ts):
        return "unknown_missing_heat_open_time"
    if sample_ts < open_ts:
        return "pre_tap"
    if pd.isna(close_ts):
        return "tapping_close_time_missing"
    if sample_ts <= close_ts:
        return "tapping"
    return "post_tap"


def normalize_formal_samples(frame: pd.DataFrame) -> pd.DataFrame:
    """Normalize sample rows while enforcing official heat identity.

    Required fields come from the official MES relation
    ``t_qpes_inner_batch.heatno -> t_ipes_cond.meltno``.  Rows without that
    identity are rejected instead of being repaired from sample-number text.
    """

    required = {
        "official_meltno",
        "batchno",
        "si_pct",
        "result_ts",
        "sample_ts",
        "open_ts",
        "close_ts",
        "tank_no",
        "taphole_id",
    }
    _require_columns(frame, required, "正式试样数据")
    samples = frame.copy()
    for column in ("sample_ts", "result_ts", "open_ts", "close_ts"):
        samples[column] = pd.to_datetime(samples[column], errors="coerce")
    for column in ("si_pct", "c_pct", "mn_pct", "p_pct", "s_pct"):
        if column in samples.columns:
            samples[column] = pd.to_numeric(samples[column], errors="coerce")

    samples["official_meltno"] = (
        samples["official_meltno"].astype("string").str.strip()
    )
    samples["batchno"] = samples["batchno"].astype("string").str.strip()
    official = (
        samples["official_meltno"].notna()
        & samples["official_meltno"].str.match(r"^\d+#\d{8}-\d+$", na=False)
    )
    valid_si = samples["si_pct"].map(_finite_number).notna()
    samples = samples.loc[official & valid_si].copy()
    if samples.empty:
        raise ValueError("没有同时具备MES正式meltno和有效Si的试样")

    samples["sample_time_status"] = np.where(
        samples["sample_ts"].notna(),
        "actual_mes_takesampletime",
        "missing_source",
    )
    tank_text = samples["tank_no"].astype("string").str.strip()
    samples["tank_no_status"] = np.where(
        tank_text.notna() & tank_text.ne(""),
        "exact_batchno_join",
        "missing_source",
    )
    taphole_text = samples["taphole_id"].astype("string").str.strip()
    samples["taphole_id_status"] = np.where(
        taphole_text.notna() & taphole_text.ne(""),
        "explicit_source",
        "missing_source",
    )
    samples["tapping_stage"] = [
        _stage_for_sample(sample_ts, open_ts, close_ts)
        for sample_ts, open_ts, close_ts in zip(
            samples["sample_ts"],
            samples["open_ts"],
            samples["close_ts"],
        )
    ]
    samples["label_identity_source"] = (
        "MES.t_qpes_inner_batch.heatno_exact_join"
    )
    samples["sample_time_fallback_used"] = False
    samples["contract_version"] = CONTRACT_VERSION
    return samples.sort_values(
        ["open_ts", "official_meltno", "result_ts", "batchno"],
        kind="stable",
    ).reset_index(drop=True)


def build_heat_targets(samples: pd.DataFrame) -> pd.DataFrame:
    """Build representative and distribution targets per official heat."""

    _require_columns(
        samples,
        {
            "official_meltno",
            "batchno",
            "si_pct",
            "result_ts",
            "sample_ts",
            "open_ts",
            "close_ts",
            "tank_no",
            "taphole_id",
        },
        "标准化试样数据",
    )
    rows: list[dict[str, Any]] = []
    for meltno, group in samples.groupby("official_meltno", sort=False):
        values = group["si_pct"].dropna().astype(float)
        if values.empty:
            continue
        open_values = group["open_ts"].dropna()
        close_values = group["close_ts"].dropna()
        result_values = group["result_ts"].dropna()
        sample_values = group["sample_ts"].dropna()
        tanks = sorted(
            {
                str(value).strip()
                for value in group["tank_no"].dropna()
                if str(value).strip()
            }
        )
        tapholes = sorted(
            {
                str(value).strip()
                for value in group["taphole_id"].dropna()
                if str(value).strip()
            }
        )
        rows.append(
            {
                "official_meltno": str(meltno),
                "prediction_cutoff_ts": (
                    open_values.min() if not open_values.empty else pd.NaT
                ),
                "open_ts": open_values.min() if not open_values.empty else pd.NaT,
                "close_ts": (
                    close_values.max() if not close_values.empty else pd.NaT
                ),
                "label_available_ts": (
                    result_values.max() if not result_values.empty else pd.NaT
                ),
                "label_first_result_ts": (
                    result_values.min() if not result_values.empty else pd.NaT
                ),
                "result_at_or_before_cutoff_count": int(
                    (
                        group["result_ts"].notna()
                        & group["open_ts"].notna()
                        & (group["result_ts"] <= group["open_ts"])
                    ).sum()
                ),
                "target__Si_representative": float(values.median()),
                "target__Si_mean": float(values.mean()),
                "target__Si_min": float(values.min()),
                "target__Si_p10": _quantile(values, 0.10),
                "target__Si_p50": _quantile(values, 0.50),
                "target__Si_p90": _quantile(values, 0.90),
                "target__Si_max": float(values.max()),
                "target__Si_std": (
                    float(values.std(ddof=0)) if len(values) > 1 else 0.0
                ),
                "target__Si_spread": float(values.max() - values.min()),
                "target__Si_sample_count": int(len(values)),
                "actual_sample_time_count": int(len(sample_values)),
                "actual_sample_time_coverage": float(
                    len(sample_values) / len(group)
                ),
                "tank_no_count": len(tanks),
                "tank_nos": "|".join(tanks),
                "taphole_id_count": len(tapholes),
                "taphole_ids": "|".join(tapholes),
                "representative_target_definition": (
                    "median_of_all_valid_Si_samples_exactly_joined_to_official_meltno"
                ),
                "distribution_target_definition": (
                    "empirical_min_p10_p50_p90_max_std_spread_within_official_meltno"
                ),
                "contract_version": CONTRACT_VERSION,
            }
        )
    return pd.DataFrame(rows).sort_values(
        ["prediction_cutoff_ts", "official_meltno"],
        kind="stable",
    ).reset_index(drop=True)


def build_next_sample_targets(samples: pd.DataFrame) -> pd.DataFrame:
    """Create next-sample targets only when true sample timestamps exist."""

    eligible = samples.loc[
        samples["sample_ts"].notna() & samples["si_pct"].notna()
    ].copy()
    if eligible.empty:
        return pd.DataFrame(
            columns=[
                "official_meltno",
                "current_batchno",
                "current_sample_ts",
                "current_Si",
                "next_batchno",
                "next_sample_ts",
                "target__next_sample_Si",
                "contract_version",
            ]
        )
    eligible = eligible.sort_values(
        ["official_meltno", "sample_ts", "batchno"],
        kind="stable",
    )
    rows: list[dict[str, Any]] = []
    for meltno, group in eligible.groupby("official_meltno", sort=False):
        records = group.to_dict("records")
        for current, following in zip(records, records[1:]):
            rows.append(
                {
                    "official_meltno": str(meltno),
                    "current_batchno": current["batchno"],
                    "current_sample_ts": current["sample_ts"],
                    "current_Si": float(current["si_pct"]),
                    "next_batchno": following["batchno"],
                    "next_sample_ts": following["sample_ts"],
                    "target__next_sample_Si": float(following["si_pct"]),
                    "contract_version": CONTRACT_VERSION,
                }
            )
    return pd.DataFrame(rows)


def build_label_contract(frame: pd.DataFrame) -> LabelBuildResult:
    """Build all target tables and a machine-readable readiness audit."""

    normalized = normalize_formal_samples(frame)
    heat_targets = build_heat_targets(normalized)
    next_targets = build_next_sample_targets(normalized)
    sample_count = len(normalized)
    timed_count = int(normalized["sample_ts"].notna().sum())
    tank_count = int(
        normalized["tank_no"].astype("string").str.strip().ne("").sum()
    )
    taphole_count = int(
        normalized["taphole_id"].astype("string").str.strip().ne("").sum()
    )
    prospective_heat = (
        heat_targets["prediction_cutoff_ts"].notna()
        & heat_targets["label_available_ts"].notna()
        & (
            heat_targets["label_available_ts"]
            > heat_targets["prediction_cutoff_ts"]
        )
    )
    heat_with_open = int(prospective_heat.sum())
    distribution_heats = int(
        (
            prospective_heat
            & (heat_targets["target__Si_sample_count"] >= 2)
        ).sum()
    )
    result_at_or_before_cutoff = int(
        (
            normalized["result_ts"].notna()
            & normalized["open_ts"].notna()
            & (normalized["result_ts"] <= normalized["open_ts"])
        ).sum()
    )
    audit = {
        "requirement_id": "REQ-SI-FORMAL-LABEL-CONTRACT-V3-20260726",
        "contract_version": CONTRACT_VERSION,
        "official_sample_rows": sample_count,
        "official_heat_rows": int(len(heat_targets)),
        "sample_time": {
            "actual_rows": timed_count,
            "coverage_ratio": timed_count / sample_count if sample_count else 0.0,
            "fallback_to_result_time": False,
        },
        "tank_no": {
            "exact_batchno_join_rows": tank_count,
            "coverage_ratio": tank_count / sample_count if sample_count else 0.0,
        },
        "taphole_id": {
            "explicit_rows": taphole_count,
            "coverage_ratio": (
                taphole_count / sample_count if sample_count else 0.0
            ),
        },
        "label_timing": {
            "result_at_or_before_cutoff_rows": result_at_or_before_cutoff,
            "fully_available_at_or_before_cutoff_heats": int(
                (
                    heat_targets["label_available_ts"]
                    <= heat_targets["prediction_cutoff_ts"]
                ).sum()
            ),
            "training_policy": (
                "exclude heats whose complete target is already available "
                "at or before prediction cutoff"
            ),
        },
        "task_readiness": {
            REPRESENTATIVE_TASK: {
                "ready": heat_with_open > 0,
                "eligible_rows": heat_with_open,
                "cutoff": "MES.t_ipes_cond.opentime",
            },
            NEXT_SAMPLE_TASK: {
                "ready": len(next_targets) > 0,
                "eligible_rows": int(len(next_targets)),
                "blocked_reason": (
                    None
                    if len(next_targets)
                    else "MES takesampletime has no usable chronological pairs"
                ),
            },
            DISTRIBUTION_TASK: {
                "ready": distribution_heats > 0,
                "eligible_rows": distribution_heats,
                "minimum_samples_per_heat": 2,
            },
        },
    }
    return LabelBuildResult(normalized, heat_targets, next_targets, audit)


def validate_training_task(
    audit: Mapping[str, Any],
    task: str,
) -> None:
    """Reject training when the selected target is not contract-ready."""

    if task not in SUPPORTED_TASKS:
        raise ValueError(f"不支持的Si目标：{task}")
    readiness = audit.get("task_readiness", {}).get(task, {})
    if not readiness.get("ready"):
        reason = readiness.get("blocked_reason") or "label contract not ready"
        raise RuntimeError(f"{task}训练被标签合同阻止：{reason}")
