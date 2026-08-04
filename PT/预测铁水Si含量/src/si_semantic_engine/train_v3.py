"""Train formal-meltno representative and distribution Si models.

The input dataset must be produced by ``build_formal_si_dataset_v3.py``.
Training is chronological and grouped by official MES melt number.  The
next-sample task is refused unless the strict label contract reports real
sample-time pairs.

Requirements:
    REQ-SI-FORMAL-LABEL-CONTRACT-V3-20260726
    REQ-SI-FORMAL-DATASET-V3-20260726
    REQ-SI-FORMAL-TRAINING-V3-20260726
"""

from __future__ import annotations

import argparse
import hashlib
import json
import platform
from datetime import datetime
from pathlib import Path
from typing import Any, Mapping, Sequence

import joblib
import numpy as np
import pandas as pd
import sklearn
from sklearn.ensemble import ExtraTreesRegressor
from sklearn.impute import SimpleImputer
from sklearn.linear_model import Ridge
from sklearn.metrics import mean_absolute_error, mean_squared_error
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

from .formal_dataset import sha256_file
from .formal_labels import (
    DISTRIBUTION_TASK,
    NEXT_SAMPLE_TASK,
    REPRESENTATIVE_TASK,
    validate_training_task,
)


REQUIREMENT_ID = "REQ-SI-FORMAL-TRAINING-V3-20260726"
RANDOM_STATE = 20260726
TARGET = "target__Si_representative"
DISTRIBUTION_TARGETS = (
    "target__Si_p10",
    "target__Si_p50",
    "target__Si_p90",
)


def _write_json(path: Path, payload: Any) -> None:
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, default=str),
        encoding="utf-8",
    )


def _candidate_features(frame: pd.DataFrame) -> list[str]:
    return sorted(
        column
        for column in frame.columns
        if column.startswith("sensor__")
        or (
            column.startswith("history__")
            and column
            not in {
                "history__previous_meltno",
                "history__available_heat_count",
            }
        )
    )


def _usable_features(
    train: pd.DataFrame,
    candidates: Sequence[str],
    min_non_null_ratio: float = 0.50,
) -> tuple[list[str], dict[str, Any]]:
    usable: list[str] = []
    dropped: dict[str, str] = {}
    numeric = train[list(candidates)].apply(pd.to_numeric, errors="coerce")
    for column in candidates:
        series = numeric[column]
        ratio = float(series.notna().mean())
        if ratio < min_non_null_ratio:
            dropped[column] = f"train_non_null_ratio={ratio:.6f}"
            continue
        if int(series.nunique(dropna=True)) <= 1:
            dropped[column] = "train_zero_variance"
            continue
        usable.append(column)
    if not usable:
        raise RuntimeError("训练集没有通过覆盖率和方差门禁的输入特征")
    return usable, {
        "candidate_count": len(candidates),
        "usable_count": len(usable),
        "dropped_count": len(dropped),
        "minimum_train_non_null_ratio": min_non_null_ratio,
        "dropped": dropped,
    }


def _numeric(frame: pd.DataFrame, columns: Sequence[str]) -> pd.DataFrame:
    return frame[list(columns)].apply(pd.to_numeric, errors="coerce")


def _ridge() -> Pipeline:
    return Pipeline(
        [
            ("imputer", SimpleImputer(strategy="median")),
            ("scaler", StandardScaler()),
            ("model", Ridge(alpha=20.0)),
        ]
    )


def _extra_trees() -> Pipeline:
    return Pipeline(
        [
            ("imputer", SimpleImputer(strategy="median")),
            (
                "model",
                ExtraTreesRegressor(
                    n_estimators=500,
                    min_samples_leaf=3,
                    max_features=0.70,
                    random_state=RANDOM_STATE,
                    n_jobs=-1,
                ),
            ),
        ]
    )


def _metrics(actual: np.ndarray, predicted: np.ndarray) -> dict[str, float]:
    residual = np.asarray(predicted) - np.asarray(actual)
    return {
        "rows": int(len(actual)),
        "mae": float(mean_absolute_error(actual, predicted)),
        "rmse": float(mean_squared_error(actual, predicted) ** 0.5),
        "bias": float(np.mean(residual)),
        "hit_rate_abs_le_005": float(
            np.mean(np.abs(residual) <= 0.05)
        ),
        "hit_rate_abs_le_010": float(
            np.mean(np.abs(residual) <= 0.10)
        ),
    }


def _split_conformal_radius(
    actual: np.ndarray,
    predicted: np.ndarray,
    coverage: float = 0.80,
) -> float:
    scores = np.sort(np.abs(np.asarray(actual) - np.asarray(predicted)))
    if not len(scores):
        raise ValueError("验证集为空，不能校准预测区间")
    rank = min(
        len(scores),
        int(np.ceil((len(scores) + 1) * coverage)),
    )
    return float(scores[rank - 1])


def _model_hashes(directory: Path) -> dict[str, Any]:
    output: dict[str, Any] = {}
    for path in sorted(item for item in directory.rglob("*") if item.is_file()):
        if path.name in {"run_manifest.json", "sha256sums.json"}:
            continue
        relative = path.relative_to(directory).as_posix()
        output[relative] = {
            "bytes": path.stat().st_size,
            "sha256": sha256_file(path),
        }
    return output


def _distribution_metrics(
    actual: np.ndarray,
    predicted: np.ndarray,
) -> dict[str, Any]:
    metrics: dict[str, Any] = {}
    for index, name in enumerate(("p10", "p50", "p90")):
        metrics[name] = _metrics(actual[:, index], predicted[:, index])
    metrics["ordered_prediction_ratio"] = float(
        np.mean(
            (predicted[:, 0] <= predicted[:, 1])
            & (predicted[:, 1] <= predicted[:, 2])
        )
    )
    metrics["mean_predicted_p10_p90_width"] = float(
        np.mean(predicted[:, 2] - predicted[:, 0])
    )
    metrics["actual_p10_p90_inside_predicted_band_ratio"] = float(
        np.mean(
            (actual[:, 0] >= predicted[:, 0])
            & (actual[:, 2] <= predicted[:, 2])
        )
    )
    return metrics


def run_experiment(
    dataset_path: Path,
    dataset_manifest_path: Path,
    output_dir: Path,
) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    models_dir = output_dir / "models"
    models_dir.mkdir(exist_ok=True)
    dataset_manifest = json.loads(
        dataset_manifest_path.read_text(encoding="utf-8")
    )
    audit = dataset_manifest["label_audit"]
    validate_training_task(audit, REPRESENTATIVE_TASK)
    validate_training_task(audit, DISTRIBUTION_TASK)
    next_sample_gate: dict[str, Any]
    try:
        validate_training_task(audit, NEXT_SAMPLE_TASK)
    except RuntimeError as exc:
        next_sample_gate = {
            "trained": False,
            "status": "blocked_by_label_contract",
            "reason": str(exc),
        }
    else:
        next_sample_gate = {
            "trained": False,
            "status": "not_implemented_in_v3_run",
            "reason": "contract ready but a separate next-sample run is required",
        }

    frame = pd.read_csv(dataset_path, low_memory=False, encoding="utf-8-sig")
    frame["prediction_cutoff_ts"] = pd.to_datetime(
        frame["prediction_cutoff_ts"], errors="raise"
    )
    frame = frame.sort_values(
        ["experiment_row_index", "prediction_cutoff_ts"],
        kind="stable",
    ).reset_index(drop=True)
    if frame["official_meltno"].duplicated().any():
        raise RuntimeError("同一正式meltno跨行出现，违反炉次分组合同")
    split_frames = {
        name: frame.loc[frame["experiment_split"] == name].copy()
        for name in ("train", "validation", "test")
    }
    if any(part.empty for part in split_frames.values()):
        raise RuntimeError("训练、验证或测试时间段为空")
    candidates = _candidate_features(frame)
    features, feature_audit = _usable_features(
        split_frames["train"],
        candidates,
    )

    train = split_frames["train"]
    validation = split_frames["validation"]
    test = split_frames["test"]
    models: dict[str, Any] = {
        "ridge": _ridge(),
        "extra_trees": _extra_trees(),
    }
    representative_metrics: dict[str, Any] = {}
    predictions: dict[str, dict[str, np.ndarray]] = {}
    for name, model in models.items():
        model.fit(_numeric(train, features), train[TARGET].to_numpy(float))
        predictions[name] = {}
        representative_metrics[name] = {}
        for split_name, part in (
            ("validation", validation),
            ("test", test),
        ):
            prediction = model.predict(_numeric(part, features))
            predictions[name][split_name] = prediction
            representative_metrics[name][split_name] = _metrics(
                part[TARGET].to_numpy(float),
                prediction,
            )

    train_median = float(train[TARGET].median())
    baseline_metrics: dict[str, Any] = {}
    baseline_predictions: dict[str, np.ndarray] = {}
    for split_name, part in (("validation", validation), ("test", test)):
        prior = pd.to_numeric(
            part.get("history__previous_Si_median_6"),
            errors="coerce",
        ).fillna(train_median)
        prediction = prior.to_numpy(float)
        baseline_predictions[split_name] = prediction
        baseline_metrics[split_name] = _metrics(
            part[TARGET].to_numpy(float),
            prediction,
        )
    representative_metrics["previous_si_baseline"] = baseline_metrics
    selected_name = min(
        ("ridge", "extra_trees", "previous_si_baseline"),
        key=lambda name: (
            representative_metrics[name]["validation"]["mae"],
            -representative_metrics[name]["validation"][
                "hit_rate_abs_le_005"
            ],
            name,
        ),
    )
    if selected_name == "previous_si_baseline":
        selected_validation = baseline_predictions["validation"]
        selected_test = baseline_predictions["test"]
        selected_model: Any = {
            "type": "previous_si_baseline",
            "fallback_train_median": train_median,
        }
    else:
        selected_validation = predictions[selected_name]["validation"]
        selected_test = predictions[selected_name]["test"]
        selected_model = models[selected_name]
    radius80 = _split_conformal_radius(
        validation[TARGET].to_numpy(float),
        selected_validation,
        coverage=0.80,
    )
    representative_metrics["selected"] = {
        "model": selected_name,
        "conformal_p10_p90_radius": radius80,
        "validation_interval_coverage": float(
            np.mean(
                np.abs(
                    validation[TARGET].to_numpy(float)
                    - selected_validation
                )
                <= radius80
            )
        ),
        "test_interval_coverage": float(
            np.mean(
                np.abs(test[TARGET].to_numpy(float) - selected_test)
                <= radius80
            )
        ),
        "test_mean_interval_width": 2.0 * radius80,
    }

    joblib.dump(selected_model, models_dir / "representative_selected.joblib")
    if selected_name != "previous_si_baseline":
        importance_model = selected_model.named_steps["model"]
        importances = getattr(importance_model, "feature_importances_", None)
    else:
        importances = None
    feature_importance = (
        sorted(
            (
                {"feature": feature, "importance": float(importance)}
                for feature, importance in zip(features, importances)
            ),
            key=lambda item: item["importance"],
            reverse=True,
        )
        if importances is not None
        else []
    )

    distribution_frame = frame.loc[
        frame["target__Si_sample_count"] >= 2
    ].copy()
    distribution_splits = {
        name: distribution_frame.loc[
            distribution_frame["experiment_split"] == name
        ].copy()
        for name in ("train", "validation", "test")
    }
    if any(part.empty for part in distribution_splits.values()):
        raise RuntimeError("整炉Si分布任务的训练、验证或测试集为空")
    distribution_model = _extra_trees()
    distribution_model.fit(
        _numeric(distribution_splits["train"], features),
        distribution_splits["train"][
            list(DISTRIBUTION_TARGETS)
        ].to_numpy(float),
    )
    distribution_metrics: dict[str, Any] = {}
    distribution_predictions: dict[str, np.ndarray] = {}
    for split_name in ("validation", "test"):
        part = distribution_splits[split_name]
        raw_prediction = distribution_model.predict(_numeric(part, features))
        ordered_prediction = np.sort(raw_prediction, axis=1)
        distribution_predictions[split_name] = ordered_prediction
        distribution_metrics[split_name] = _distribution_metrics(
            part[list(DISTRIBUTION_TARGETS)].to_numpy(float),
            ordered_prediction,
        )
    joblib.dump(distribution_model, models_dir / "distribution_p10_p50_p90.joblib")

    representative_output = test[
        [
            "official_meltno",
            "prediction_cutoff_ts",
            TARGET,
            "target__Si_sample_count",
        ]
    ].copy()
    representative_output["prediction__Si_representative"] = selected_test
    representative_output["prediction__P10"] = selected_test - radius80
    representative_output["prediction__P90"] = selected_test + radius80
    representative_output["absolute_error"] = np.abs(
        representative_output[TARGET]
        - representative_output["prediction__Si_representative"]
    )
    representative_output.to_csv(
        output_dir / "representative_predictions_test.csv",
        index=False,
        encoding="utf-8-sig",
    )
    distribution_test = distribution_splits["test"]
    distribution_output = distribution_test[
        [
            "official_meltno",
            "prediction_cutoff_ts",
            *DISTRIBUTION_TARGETS,
            "target__Si_sample_count",
        ]
    ].copy()
    distribution_output[
        [
            "prediction__Si_p10",
            "prediction__Si_p50",
            "prediction__Si_p90",
        ]
    ] = distribution_predictions["test"]
    distribution_output.to_csv(
        output_dir / "distribution_predictions_test.csv",
        index=False,
        encoding="utf-8-sig",
    )

    metrics = {
        "requirement_id": REQUIREMENT_ID,
        "model_status": "experimental_offline_formal_contract",
        "representative_task": representative_metrics,
        "distribution_task": distribution_metrics,
        "next_sample_task": next_sample_gate,
    }
    _write_json(output_dir / "metrics.json", metrics)
    _write_json(output_dir / "backtest_metrics.json", metrics)
    _write_json(
        output_dir / "calibration_report.json",
        {
            "representative_interval": {
                "method": "split_conformal_symmetric_80_percent",
                "validation_rows": int(len(validation)),
                "radius": radius80,
                "validation_coverage": representative_metrics["selected"][
                    "validation_interval_coverage"
                ],
                "test_coverage": representative_metrics["selected"][
                    "test_interval_coverage"
                ],
                "test_mean_width": representative_metrics["selected"][
                    "test_mean_interval_width"
                ],
            },
            "distribution": {
                "method": (
                    "multioutput_extra_trees_empirical_p10_p50_p90_"
                    "with_rowwise_ordering"
                ),
                "validation": distribution_metrics["validation"],
                "test": distribution_metrics["test"],
                "calibration_status": (
                    "failed_for_online_use_low_actual_band_containment"
                ),
            },
            "online_allowed": False,
        },
    )
    _write_json(
        output_dir / "feature_contract.json",
        {
            "cutoff": "strictly before MES t_ipes_cond.opentime",
            "official_group_key": "MES meltno",
            "feature_count": len(features),
            "features": features,
            "feature_audit": feature_audit,
            "target_contract": {
                REPRESENTATIVE_TASK: (
                    "median of all valid Si samples exactly joined to official meltno"
                ),
                DISTRIBUTION_TASK: list(DISTRIBUTION_TARGETS),
                NEXT_SAMPLE_TASK: next_sample_gate,
            },
        },
    )
    _write_json(
        output_dir / "feature_importance.json",
        feature_importance[:100],
    )
    model_config = {
        "model_id": "gl02_formal_meltno_si_v3",
        "model_version": output_dir.name,
        "model_status": "experimental_offline_formal_contract",
        "selected_representative_model": selected_name,
        "representative_interval": {
            "method": "split_conformal_symmetric_80_percent",
            "radius": radius80,
        },
        "distribution_model": "extra_trees_multioutput_p10_p50_p90",
        "online_allowed": False,
        "blocked_online_reason": (
            "offline experiment; requires shadow time-out validation and "
            "sample-time source remediation"
        ),
    }
    _write_json(output_dir / "model_config.json", model_config)

    report_lines = [
        "# 正式炉次 Si V3 训练报告",
        "",
        f"- 数据集：`{dataset_path}`",
        f"- 正式炉次：{len(frame)}",
        f"- 可用特征：{len(features)}",
        f"- 代表 Si 选中模型：`{selected_name}`",
        (
            f"- 代表 Si 测试 MAE："
            f"{representative_metrics[selected_name]['test']['mae']:.6f}%"
        ),
        (
            f"- 代表 Si 测试 ±0.05 命中率："
            f"{representative_metrics[selected_name]['test']['hit_rate_abs_le_005']:.2%}"
        ),
        f"- 80%共形区间半径：{radius80:.6f}%",
        (
            f"- 80%共形区间测试覆盖率："
            f"{representative_metrics['selected']['test_interval_coverage']:.2%}"
        ),
        (
            f"- 分布任务测试 P50 MAE："
            f"{distribution_metrics['test']['p50']['mae']:.6f}%"
        ),
        "",
        "## 数据合同门禁",
        "",
        "- 炉次只使用 MES 正式 meltno，不从试样号推断。",
        "- 特征只取 MES 开铁时刻之前的 PostgreSQL 数据。",
        "- 结果时间没有替代真实取样时间。",
        f"- 下一次试样任务：{next_sample_gate['status']}。",
        "- 当前模型仍为离线实验状态，不接入生产 MCP 或调节建议。",
        "",
    ]
    (output_dir / "report.md").write_text(
        "\n".join(report_lines),
        encoding="utf-8",
    )
    model_card_lines = [
        "# gl02_formal_meltno_si_v3 模型卡",
        "",
        "- 状态：`experimental_offline_formal_contract`",
        "- 炉次身份：MES正式`meltno`",
        "- 代表目标：同炉全部有效Si试样中位数",
        "- 分布目标：同炉经验P10/P50/P90",
        "- 预测截止：MES开铁时刻，输入严格早于截止",
        f"- 训练/验证/测试：{len(train)}/{len(validation)}/{len(test)}炉",
        f"- 输入特征：{len(features)}",
        f"- 代表模型：`{selected_name}`",
        (
            f"- 测试MAE："
            f"{representative_metrics[selected_name]['test']['mae']:.6f}% Si"
        ),
        (
            f"- 测试±0.05命中率："
            f"{representative_metrics[selected_name]['test']['hit_rate_abs_le_005']:.2%}"
        ),
        (
            f"- 80%区间测试覆盖/宽度："
            f"{representative_metrics['selected']['test_interval_coverage']:.2%} / "
            f"{representative_metrics['selected']['test_mean_interval_width']:.6f}% Si"
        ),
        "",
        "## 已知限制",
        "",
        "- MES真实取样时间缺失，下一试样任务被合同阻止。",
        "- 当前权限面没有可信铁口编号和按试样出铁阶段。",
        "- 只完成一次固定时间外切分，尚未完成滚动月份回测。",
        "- 分布带完整包住实际P10-P90比例偏低，分布未通过上线校准。",
        "- 不含经过炉次谱系确认的炉料化学成分。",
        "",
        "## 允许用途",
        "",
        "仅限授权本机离线研究；禁止接生产MCP、自动预警、调节量建议和生产写入。",
        "",
    ]
    (output_dir / "model_card.md").write_text(
        "\n".join(model_card_lines),
        encoding="utf-8",
    )
    manifest = {
        "requirement_id": REQUIREMENT_ID,
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "input": {
            "dataset": {
                "path": str(dataset_path.resolve()),
                "sha256": sha256_file(dataset_path),
            },
            "manifest": {
                "path": str(dataset_manifest_path.resolve()),
                "sha256": sha256_file(dataset_manifest_path),
            },
        },
        "runtime": {
            "python": platform.python_version(),
            "scikit_learn": sklearn.__version__,
            "random_state": RANDOM_STATE,
        },
        "split_counts": {
            name: int(len(part)) for name, part in split_frames.items()
        },
        "feature_count": len(features),
        "selected_representative_model": selected_name,
        "artifacts": _model_hashes(output_dir),
    }
    _write_json(output_dir / "run_manifest.json", manifest)
    _write_json(output_dir / "sha256sums.json", _model_hashes(output_dir))
    return metrics


def parser() -> argparse.ArgumentParser:
    cli = argparse.ArgumentParser(
        description="训练MES正式炉次代表Si与整炉Si分布V3模型。"
    )
    cli.add_argument("--dataset", type=Path, required=True)
    cli.add_argument("--dataset-manifest", type=Path, required=True)
    cli.add_argument("--output-dir", type=Path, required=True)
    return cli


def main(argv: Sequence[str] | None = None) -> int:
    args = parser().parse_args(argv)
    metrics = run_experiment(
        args.dataset,
        args.dataset_manifest,
        args.output_dir,
    )
    print(json.dumps(metrics, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
