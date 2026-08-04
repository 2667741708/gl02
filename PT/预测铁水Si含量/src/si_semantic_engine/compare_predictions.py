"""Paired comparison of immutable heat-level prediction artifacts."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Sequence

import numpy as np
import pandas as pd

from .train_v6 import metrics


def paired_comparison(
    actual: np.ndarray,
    prediction_a: np.ndarray,
    prediction_b: np.ndarray,
    *,
    bootstrap_repeats: int = 20000,
    random_state: int = 20260727,
) -> dict:
    actual = np.asarray(actual, dtype=float)
    prediction_a = np.asarray(prediction_a, dtype=float)
    prediction_b = np.asarray(prediction_b, dtype=float)
    if not (
        actual.shape == prediction_a.shape == prediction_b.shape
    ):
        raise ValueError("配对比较数组形状不一致")
    error_a = np.abs(actual - prediction_a)
    error_b = np.abs(actual - prediction_b)
    hit_a = (error_a <= 0.02).astype(float)
    hit_b = (error_b <= 0.02).astype(float)
    rng = np.random.default_rng(random_state)
    indices = rng.integers(
        0, len(actual), size=(bootstrap_repeats, len(actual))
    )
    mae_delta = (error_b - error_a)[indices].mean(axis=1)
    hit_delta = (hit_b - hit_a)[indices].mean(axis=1)
    return {
        "rows": int(len(actual)),
        "candidate_a": metrics(actual, prediction_a),
        "candidate_b": metrics(actual, prediction_b),
        "delta_b_minus_a": {
            "mae": float(np.mean(error_b - error_a)),
            "mae_paired_bootstrap_95pct": [
                float(np.quantile(mae_delta, 0.025)),
                float(np.quantile(mae_delta, 0.975)),
            ],
            "hit_rate_abs_le_002": float(
                np.mean(hit_b - hit_a)
            ),
            "hit_rate_abs_le_002_paired_bootstrap_95pct": [
                float(np.quantile(hit_delta, 0.025)),
                float(np.quantile(hit_delta, 0.975)),
            ],
        },
        "interpretation": {
            "negative_mae_delta_favors_b": True,
            "positive_hit_delta_favors_b": True,
            "bootstrap_repeats": bootstrap_repeats,
            "random_state": random_state,
        },
    }


def compare_files(
    *,
    candidate_a_path: Path,
    candidate_a_column: str,
    candidate_b_path: Path,
    candidate_b_column: str,
    target_column: str,
) -> dict:
    a = pd.read_csv(
        candidate_a_path, low_memory=False, encoding="utf-8-sig"
    )
    b = pd.read_csv(
        candidate_b_path, low_memory=False, encoding="utf-8-sig"
    )
    required_a = {
        "official_meltno",
        "prediction_cutoff_ts",
        target_column,
        candidate_a_column,
    }
    required_b = {"official_meltno", candidate_b_column}
    if missing := sorted(required_a - set(a)):
        raise ValueError(f"候选A缺少字段：{missing}")
    if missing := sorted(required_b - set(b)):
        raise ValueError(f"候选B缺少字段：{missing}")
    a_view = a[
        [
            "official_meltno",
            "prediction_cutoff_ts",
            target_column,
            candidate_a_column,
        ]
    ].rename(
        columns={
            target_column: "__target",
            candidate_a_column: "__prediction_a",
        }
    )
    b_view = b[
        ["official_meltno", candidate_b_column]
    ].rename(columns={candidate_b_column: "__prediction_b"})
    paired = a_view.merge(
        b_view,
        on="official_meltno",
        how="inner",
        validate="one_to_one",
    )
    if len(paired) != len(a) or len(paired) != len(b):
        raise RuntimeError("两个候选的炉次集合不一致")
    result = paired_comparison(
        paired["__target"].to_numpy(float),
        paired["__prediction_a"].to_numpy(float),
        paired["__prediction_b"].to_numpy(float),
    )
    paired["prediction_month"] = pd.to_datetime(
        paired["prediction_cutoff_ts"], errors="raise"
    ).dt.to_period("M").astype(str)
    result["monthly"] = {
        month: paired_comparison(
            group["__target"].to_numpy(float),
            group["__prediction_a"].to_numpy(float),
            group["__prediction_b"].to_numpy(float),
            bootstrap_repeats=5000,
        )
        for month, group in paired.groupby(
            "prediction_month", sort=True
        )
    }
    result["candidate_a_artifact"] = str(candidate_a_path.resolve())
    result["candidate_b_artifact"] = str(candidate_b_path.resolve())
    result["candidate_a_column"] = candidate_a_column
    result["candidate_b_column"] = candidate_b_column
    return result


def parser() -> argparse.ArgumentParser:
    cli = argparse.ArgumentParser(
        description="对两个不可变炉次预测文件做配对bootstrap比较。"
    )
    cli.add_argument("--candidate-a", type=Path, required=True)
    cli.add_argument("--column-a", required=True)
    cli.add_argument("--candidate-b", type=Path, required=True)
    cli.add_argument("--column-b", required=True)
    cli.add_argument(
        "--target-column",
        default="target__Si_representative",
    )
    cli.add_argument("--output", type=Path, required=True)
    return cli


def main(argv: Sequence[str] | None = None) -> int:
    args = parser().parse_args(argv)
    result = compare_files(
        candidate_a_path=args.candidate_a,
        candidate_a_column=args.column_a,
        candidate_b_path=args.candidate_b,
        candidate_b_column=args.column_b,
        target_column=args.target_column,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(result, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
