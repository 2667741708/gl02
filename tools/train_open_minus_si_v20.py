"""Train and evaluate V20 open-minus mean-Si shadow models.

The default operational scene is ``lead_minutes == 60``: predict each heat's
arithmetic-mean Si one hour before opening.  Candidate selection uses
validation ±0.05 hit rate first, then MAE and daily stability.  The confirmation
window is reported after selection and is not used to pick the model.

Requirement: REQ-SI-V20-OPEN-MINUS-HITRATE-20260807.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import date, datetime
import json
from pathlib import Path
import sys
from typing import Any, Callable

import joblib
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.font_manager import FontProperties  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
from sklearn.ensemble import ExtraTreesRegressor, HistGradientBoostingRegressor  # noqa: E402
from sklearn.ensemble import RandomForestClassifier  # noqa: E402


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "PT" / "预测铁水Si含量" / "src"))

from si_semantic_engine.v20_open_minus_features import (  # noqa: E402
    TARGET_COLUMN,
    candidate_status,
    daily_metrics,
    feature_coverage,
    feature_group,
    regression_metrics,
)


try:  # pragma: no cover - optional dependency varies by workstation.
    import lightgbm as lgb  # type: ignore
except Exception:  # pragma: no cover
    lgb = None


DEFAULT_DATASET = (
    ROOT
    / "PT"
    / "预测铁水Si含量"
    / "reports"
    / "experiments"
    / "EXP-SI-V20-OPEN-MINUS-20260807"
    / "v20_open_minus_dataset.csv"
)
DEFAULT_OUTPUT = (
    ROOT
    / "PT"
    / "预测铁水Si含量"
    / "reports"
    / "experiments"
    / "EXP-SI-V20-OPEN-MINUS-20260807"
    / "training"
)
FONT_PATHS = (
    Path("C:/Windows/Fonts/simsun.ttc"),
    Path("C:/Windows/Fonts/simhei.ttf"),
    Path("C:/Windows/Fonts/msyh.ttc"),
)
RANDOM_STATE = 20260807


@dataclass
class CandidateResult:
    name: str
    model: Any
    feature_columns: list[str]
    fill_values: dict[str, float]
    validation_metrics: dict[str, float]
    confirm_metrics: dict[str, float]
    train_metrics: dict[str, float]
    predictions: pd.DataFrame
    importance: pd.DataFrame


class HistoryLagModel:
    """A model-like baseline using the latest visible published mean Si."""

    def fit(self, x: pd.DataFrame, y: pd.Series) -> "HistoryLagModel":
        self.fallback_ = float(pd.to_numeric(y, errors="coerce").median())
        return self

    def predict(self, x: pd.DataFrame) -> np.ndarray:
        if "history_mean__Si_lag_1" in x.columns:
            values = pd.to_numeric(x["history_mean__Si_lag_1"], errors="coerce")
        else:
            values = pd.Series(np.nan, index=x.index)
        return values.fillna(self.fallback_).to_numpy(float)


class TwoStageBandModel:
    """Low/mid/high Si classifier with one regressor per predicted band."""

    def __init__(self) -> None:
        self.classifier = RandomForestClassifier(
            n_estimators=240,
            min_samples_leaf=3,
            random_state=RANDOM_STATE,
            class_weight="balanced_subsample",
            n_jobs=-1,
        )
        self.global_regressor = _make_regressor("weighted_hgb")
        self.band_regressors: dict[int, Any] = {}
        self.band_fallbacks: dict[int, float] = {}

    @staticmethod
    def _band(y: pd.Series) -> np.ndarray:
        values = pd.to_numeric(y, errors="coerce").to_numpy(float)
        return np.where(values < 0.30, 0, np.where(values > 0.40, 2, 1))

    def fit(self, x: pd.DataFrame, y: pd.Series) -> "TwoStageBandModel":
        bands = self._band(y)
        self.classifier.fit(x, bands)
        sample_weight = _hit_weight(y)
        self.global_regressor.fit(x, y, sample_weight=sample_weight)
        for band in (0, 1, 2):
            mask = bands == band
            self.band_fallbacks[band] = float(pd.Series(y).loc[mask].median()) if mask.any() else float(pd.Series(y).median())
            if int(mask.sum()) >= 25:
                model = _make_regressor("weighted_hgb")
                model.fit(x.loc[mask], pd.Series(y).loc[mask], sample_weight=sample_weight[mask])
                self.band_regressors[band] = model
        return self

    def predict(self, x: pd.DataFrame) -> np.ndarray:
        probabilities = self.classifier.predict_proba(x)
        classes = list(self.classifier.classes_)
        global_prediction = self.global_regressor.predict(x)
        output = np.zeros(len(x), dtype=float)
        for class_index, band in enumerate(classes):
            if int(band) in self.band_regressors:
                band_prediction = self.band_regressors[int(band)].predict(x)
            else:
                band_prediction = np.full(len(x), self.band_fallbacks.get(int(band), np.nan))
                missing = ~np.isfinite(band_prediction)
                band_prediction[missing] = global_prediction[missing]
            output += probabilities[:, class_index] * band_prediction
        if not np.isfinite(output).all():
            output = np.where(np.isfinite(output), output, global_prediction)
        return output


def _json_default(value: Any) -> Any:
    if isinstance(value, (datetime, date, pd.Timestamp)):
        return value.isoformat()
    if isinstance(value, np.generic):
        return value.item()
    return str(value)


def chinese_font() -> FontProperties | None:
    for path in FONT_PATHS:
        if path.exists():
            return FontProperties(fname=str(path))
    return None


def _hit_weight(y: pd.Series) -> np.ndarray:
    values = pd.to_numeric(y, errors="coerce").to_numpy(float)
    median = float(np.nanmedian(values))
    spread = float(np.nanstd(values))
    if not np.isfinite(spread) or spread <= 0:
        return np.ones(len(values), dtype=float)
    band_bonus = np.where((values < 0.30) | (values > 0.40), 1.7, 1.0)
    distance_bonus = 1.0 + np.minimum(np.abs(values - median) / spread, 2.0) * 0.35
    return band_bonus * distance_bonus


def _make_regressor(kind: str) -> Any:
    if kind in {"lgbm_huber", "lgbm_hit_weighted"} and lgb is not None:
        return lgb.LGBMRegressor(
            objective="huber",
            alpha=0.8,
            n_estimators=420,
            learning_rate=0.035,
            num_leaves=23,
            min_child_samples=18,
            subsample=0.9,
            colsample_bytree=0.78,
            reg_alpha=0.05,
            reg_lambda=0.35,
            random_state=RANDOM_STATE,
            n_jobs=-1,
            verbosity=-1,
        )
    if kind in {"lgbm_huber", "lgbm_hit_weighted", "weighted_hgb", "hgb"}:
        return HistGradientBoostingRegressor(
            loss="absolute_error",
            learning_rate=0.045,
            max_iter=360,
            max_leaf_nodes=23,
            min_samples_leaf=14,
            l2_regularization=0.02,
            random_state=RANDOM_STATE,
        )
    return ExtraTreesRegressor(
        n_estimators=420,
        min_samples_leaf=3,
        max_features=0.72,
        random_state=RANDOM_STATE,
        n_jobs=-1,
    )


def load_dataset(path: Path, lead_minutes: int) -> pd.DataFrame:
    frame = pd.read_csv(path.resolve(), low_memory=False, encoding="utf-8-sig")
    frame["official_meltno"] = frame["official_meltno"].astype(str)
    frame["open_ts"] = pd.to_datetime(frame["open_ts"], errors="coerce")
    frame["prediction_cutoff_ts"] = pd.to_datetime(
        frame["prediction_cutoff_ts"], errors="coerce"
    )
    frame[TARGET_COLUMN] = pd.to_numeric(frame[TARGET_COLUMN], errors="coerce")
    frame = frame.loc[frame["lead_minutes"].astype(int).eq(int(lead_minutes))].copy()
    frame = frame.dropna(subset=["open_ts", "prediction_cutoff_ts", TARGET_COLUMN])
    frame = frame.sort_values(["open_ts", "official_meltno"], kind="stable").reset_index(drop=True)
    if frame.empty:
        raise RuntimeError(f"Dataset contains no rows for lead_minutes={lead_minutes}")
    return frame


def split_frame(
    frame: pd.DataFrame,
    *,
    train_end: str,
    validation_from: str,
    validation_to: str,
    confirm_from: str,
    confirm_to: str,
    min_validation_rows: int,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, dict[str, Any]]:
    dates = frame["open_ts"].dt.date
    train = frame.loc[dates <= pd.to_datetime(train_end).date()].copy()
    validation = frame.loc[
        (dates >= pd.to_datetime(validation_from).date())
        & (dates <= pd.to_datetime(validation_to).date())
    ].copy()
    confirm = frame.loc[
        (dates >= pd.to_datetime(confirm_from).date())
        & (dates <= pd.to_datetime(confirm_to).date())
    ].copy()
    audit = {
        "split_method": "fixed_dates",
        "train_end": train_end,
        "validation_from": validation_from,
        "validation_to": validation_to,
        "confirm_from": confirm_from,
        "confirm_to": confirm_to,
    }
    if len(train) >= 40 and len(validation) >= min_validation_rows and len(confirm) >= 1:
        return train, validation, confirm, audit
    unique_days = sorted(frame["open_ts"].dt.strftime("%Y-%m-%d").dropna().unique().tolist())
    if len(unique_days) >= 5:
        train_days = set(unique_days[:-4])
        validation_days = set(unique_days[-4:-2])
        confirm_days = set(unique_days[-2:])
        train = frame.loc[frame["open_ts"].dt.strftime("%Y-%m-%d").isin(train_days)].copy()
        validation = frame.loc[frame["open_ts"].dt.strftime("%Y-%m-%d").isin(validation_days)].copy()
        confirm = frame.loc[frame["open_ts"].dt.strftime("%Y-%m-%d").isin(confirm_days)].copy()
        audit.update(
            {
                "split_method": "rolling_day_fallback",
                "train_days": sorted(train_days),
                "validation_days": sorted(validation_days),
                "confirm_days": sorted(confirm_days),
            }
        )
        return train, validation, confirm, audit
    first = int(len(frame) * 0.60)
    second = int(len(frame) * 0.80)
    train = frame.iloc[: max(first, 1)].copy()
    validation = frame.iloc[max(first, 1) : max(second, first + 1)].copy()
    confirm = frame.iloc[max(second, first + 1) :].copy()
    if confirm.empty:
        confirm = validation.copy()
    audit.update({"split_method": "row_order_fallback"})
    return train, validation, confirm, audit


def select_feature_columns(frame: pd.DataFrame, feature_set: str) -> list[str]:
    blocked_exact = {
        "v20_sample_id",
        "official_meltno",
        "furnace_no",
        "work_date",
        "open_ts",
        "close_ts",
        "source_status",
        "source_updated_at",
        "label_available_ts",
        "prediction_cutoff_ts",
        "lead_minutes",
    }
    blocked_prefixes = ("target__", "actual__", "prediction__", "error__")
    numeric_candidates: list[str] = []
    for column in frame.columns:
        if column in blocked_exact or column.startswith(blocked_prefixes):
            continue
        if feature_set == "history" and feature_group(column) != "published_history_si":
            continue
        if feature_set == "history_pci" and feature_group(column) not in {"published_history_si", "pci", "prediction_protocol"}:
            continue
        if feature_set == "long_windows":
            group = feature_group(column)
            if group == "physical_sensor":
                if not any(token in column for token in ("__360m_", "__480m_", "__720m_")):
                    continue
            elif group not in {"published_history_si", "pci", "prediction_protocol"}:
                continue
        converted = pd.to_numeric(frame[column], errors="coerce")
        if converted.notna().any():
            numeric_candidates.append(column)
    return sorted(numeric_candidates)


def prepare_xy(
    train: pd.DataFrame,
    validation: pd.DataFrame,
    confirm: pd.DataFrame,
    feature_columns: list[str],
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.Series, pd.Series, pd.Series, dict[str, float]]:
    x_train = train[feature_columns].apply(pd.to_numeric, errors="coerce")
    x_validation = validation[feature_columns].apply(pd.to_numeric, errors="coerce")
    x_confirm = confirm[feature_columns].apply(pd.to_numeric, errors="coerce")
    keep_columns = [column for column in feature_columns if x_train[column].notna().any()]
    x_train = x_train[keep_columns]
    x_validation = x_validation[keep_columns]
    x_confirm = x_confirm[keep_columns]
    medians = x_train.median(numeric_only=True)
    medians = medians.fillna(0.0)
    fill_values = {str(key): float(value) for key, value in medians.items()}
    x_train = x_train.fillna(medians)
    x_validation = x_validation.fillna(medians)
    x_confirm = x_confirm.fillna(medians)
    y_train = pd.to_numeric(train[TARGET_COLUMN], errors="coerce")
    y_validation = pd.to_numeric(validation[TARGET_COLUMN], errors="coerce")
    y_confirm = pd.to_numeric(confirm[TARGET_COLUMN], errors="coerce")
    return x_train, x_validation, x_confirm, y_train, y_validation, y_confirm, fill_values


def model_importance(model: Any, feature_columns: list[str]) -> pd.DataFrame:
    values = None
    if hasattr(model, "feature_importances_"):
        values = getattr(model, "feature_importances_")
    elif hasattr(model, "model") and hasattr(model.model, "feature_importances_"):
        values = getattr(model.model, "feature_importances_")
    if values is None or len(values) != len(feature_columns):
        return pd.DataFrame(columns=["feature", "importance"])
    frame = pd.DataFrame({"feature": feature_columns, "importance": values})
    return frame.sort_values("importance", ascending=False).reset_index(drop=True)


def fit_candidate(
    name: str,
    train: pd.DataFrame,
    validation: pd.DataFrame,
    confirm: pd.DataFrame,
    *,
    feature_set: str,
) -> CandidateResult:
    feature_columns = select_feature_columns(train, feature_set)
    if name == "history_lag1_baseline":
        if "history_mean__Si_lag_1" not in feature_columns:
            feature_columns = ["history_mean__Si_lag_1"]
    if not feature_columns:
        raise RuntimeError(f"No numeric features available for candidate {name}")
    x_train, x_validation, x_confirm, y_train, y_validation, y_confirm, fill_values = prepare_xy(
        train,
        validation,
        confirm,
        feature_columns,
    )
    if name == "history_lag1_baseline":
        model = HistoryLagModel()
        sample_weight = None
    elif name == "two_stage_low_mid_high":
        model = TwoStageBandModel()
        sample_weight = None
    elif name == "v20_lightgbm_huber":
        model = _make_regressor("lgbm_huber")
        sample_weight = None
    elif name == "v20_hit_weighted_lightgbm":
        model = _make_regressor("lgbm_hit_weighted")
        sample_weight = _hit_weight(y_train)
    else:
        model = _make_regressor("extra_trees")
        sample_weight = None
    if sample_weight is None:
        model.fit(x_train, y_train)
    else:
        model.fit(x_train, y_train, sample_weight=sample_weight)
    train_pred = model.predict(x_train)
    validation_pred = model.predict(x_validation)
    confirm_pred = model.predict(x_confirm)
    predictions = pd.concat(
        [
            _prediction_frame(train, train_pred, name, "train"),
            _prediction_frame(validation, validation_pred, name, "validation"),
            _prediction_frame(confirm, confirm_pred, name, "confirm"),
        ],
        ignore_index=True,
    )
    return CandidateResult(
        name=name,
        model=model,
        feature_columns=list(x_train.columns),
        fill_values=fill_values,
        validation_metrics=regression_metrics(y_validation, validation_pred),
        confirm_metrics=regression_metrics(y_confirm, confirm_pred),
        train_metrics=regression_metrics(y_train, train_pred),
        predictions=predictions,
        importance=model_importance(model, list(x_train.columns)),
    )


def _prediction_frame(source: pd.DataFrame, predicted: np.ndarray, candidate: str, split: str) -> pd.DataFrame:
    columns = [
        column
        for column in (
            "official_meltno",
            "furnace_no",
            "work_date",
            "open_ts",
            "prediction_cutoff_ts",
            "lead_minutes",
            TARGET_COLUMN,
            "history_mean__Si_lag_1",
            "v20_history__unlabeled_heat_gap",
            "v20_history__latest_label_meltno_distance",
        )
        if column in source.columns
    ]
    output = source[columns].copy()
    output["candidate"] = candidate
    output["split"] = split
    output["prediction__Si_mean"] = predicted
    output["error__Si_mean"] = output["prediction__Si_mean"] - pd.to_numeric(output[TARGET_COLUMN], errors="coerce")
    output["hit_abs_le_005"] = output["error__Si_mean"].abs() <= 0.05
    output["hit_abs_le_002"] = output["error__Si_mean"].abs() <= 0.02
    return output


def selection_key(result: CandidateResult) -> tuple[float, float, float]:
    metrics = result.validation_metrics
    daily = daily_metrics(
        result.predictions.loc[result.predictions["split"].eq("validation")],
        actual_col=TARGET_COLUMN,
        prediction_col="prediction__Si_mean",
    )
    worst_daily_mae = max((item.get("mae", np.nan) for item in daily.values()), default=np.nan)
    if not np.isfinite(worst_daily_mae):
        worst_daily_mae = np.inf
    return (
        float(metrics.get("hit_rate_abs_le_005", -np.inf)),
        -float(metrics.get("mae", np.inf)),
        -float(worst_daily_mae),
    )


def candidate_summary(results: list[CandidateResult]) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for result in results:
        for split, metrics in (
            ("train", result.train_metrics),
            ("validation", result.validation_metrics),
            ("confirm", result.confirm_metrics),
        ):
            rows.append({"candidate": result.name, "split": split, **metrics})
    return pd.DataFrame(rows)


def plot_actual_vs_predicted(frame: pd.DataFrame, output: Path, title: str) -> None:
    if frame.empty:
        return
    work = frame.copy()
    work["open_ts"] = pd.to_datetime(work["open_ts"], errors="coerce")
    work = work.sort_values(["open_ts", "official_meltno"], kind="stable")
    font = chinese_font()
    x = range(len(work))
    fig, ax = plt.subplots(figsize=(16, 7), dpi=160)
    ax.plot(x, work[TARGET_COLUMN], marker="o", linewidth=1.8, label="实际平均Si")
    ax.plot(x, work["prediction__Si_mean"], marker="s", linewidth=1.6, label="V20预测平均Si")
    ax.set_xticks(list(x))
    ax.set_xticklabels(work["official_meltno"], rotation=45, ha="right", fontproperties=font)
    ax.set_ylabel("平均Si（%）", fontproperties=font)
    ax.set_title(title, fontproperties=font)
    ax.grid(alpha=0.25)
    ax.legend(prop=font)
    fig.tight_layout()
    output.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output)
    plt.close(fig)


def plot_error_histogram(frame: pd.DataFrame, output: Path) -> None:
    if frame.empty:
        return
    error = pd.to_numeric(frame["error__Si_mean"], errors="coerce").dropna()
    if error.empty:
        return
    font = chinese_font()
    fig, ax = plt.subplots(figsize=(10, 6), dpi=160)
    ax.hist(error, bins=18, color="#6aa6b8", alpha=0.82)
    ax.axvline(0.05, color="#c75c5c", linestyle="--", linewidth=1.2)
    ax.axvline(-0.05, color="#c75c5c", linestyle="--", linewidth=1.2)
    ax.axvline(0.0, color="#333333", linewidth=1.0)
    ax.set_title("V20确认集误差分布", fontproperties=font)
    ax.set_xlabel("预测 - 实际 Si", fontproperties=font)
    ax.set_ylabel("炉次数", fontproperties=font)
    fig.tight_layout()
    output.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output)
    plt.close(fig)


def lead_time_baseline_metrics(dataset_path: Path, output_dir: Path) -> pd.DataFrame:
    raw = pd.read_csv(dataset_path.resolve(), low_memory=False, encoding="utf-8-sig")
    rows: list[dict[str, Any]] = []
    if "history_mean__Si_lag_1" not in raw.columns:
        return pd.DataFrame()
    for lead, group in raw.groupby("lead_minutes"):
        metrics = regression_metrics(group[TARGET_COLUMN], group["history_mean__Si_lag_1"])
        rows.append({"lead_minutes": int(lead), "method": "history_lag1_baseline", **metrics})
    frame = pd.DataFrame(rows).sort_values("lead_minutes")
    frame.to_csv(output_dir / "lead_time_baseline_metrics.csv", index=False, encoding="utf-8-sig")
    return frame


def write_report(
    args: argparse.Namespace,
    selected: CandidateResult,
    results: list[CandidateResult],
    paths: dict[str, Path],
    split_audit: dict[str, Any],
) -> None:
    baseline = next(item for item in results if item.name == "history_lag1_baseline")
    status = candidate_status(
        selected.validation_metrics,
        baseline.validation_metrics,
        selected.confirm_metrics,
        baseline.confirm_metrics,
    )
    lines = [
        "# V20 开口前平均Si预测实验报告",
        "",
        f"- 生成时间：{datetime.now().isoformat(timespec='seconds')}",
        f"- 主提前量：开口前 {args.lead_minutes} 分钟",
        f"- 选择规则：验证集 ±0.05 命中率优先，其次 MAE 与逐日稳定性。",
        f"- 选中模型：`{selected.name}`",
        f"- 影子状态：`{status}`",
        f"- 切分：`{split_audit}`",
        "",
        "## 关键指标",
        "",
        f"- 验证集 ±0.05：{selected.validation_metrics.get('hit_rate_abs_le_005', np.nan):.2%}",
        f"- 验证集 MAE：{selected.validation_metrics.get('mae', np.nan):.4f}",
        f"- 确认集 ±0.05：{selected.confirm_metrics.get('hit_rate_abs_le_005', np.nan):.2%}",
        f"- 确认集 MAE：{selected.confirm_metrics.get('mae', np.nan):.4f}",
        "",
        "## 产物",
        "",
        f"- 逐炉预测：`{paths['predictions']}`",
        f"- 消融/候选对比：`{paths['comparison']}`",
        f"- 指标 JSON：`{paths['metrics']}`",
        f"- 确认集曲线：`{paths['confirm_plot']}`",
        f"- 误差分布：`{paths['error_plot']}`",
        "",
        "## 边界",
        "",
        "- 本轮仍是 experimental/offline，不替换生产模型、不写 220.12 业务表。",
        "- 炉料化学如存在，只作为低置信度时间背景，不代表该炉实际用料成分。",
    ]
    paths["report"].write_text("\n".join(lines) + "\n", encoding="utf-8")


def run(args: argparse.Namespace) -> dict[str, Any]:
    output_dir = args.output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    frame = load_dataset(args.dataset.resolve(), args.lead_minutes)
    train, validation, confirm, split_audit = split_frame(
        frame,
        train_end=args.train_end,
        validation_from=args.validation_from,
        validation_to=args.validation_to,
        confirm_from=args.confirm_from,
        confirm_to=args.confirm_to,
        min_validation_rows=args.min_validation_rows,
    )
    candidates = [
        ("history_lag1_baseline", "history"),
        ("v20_lightgbm_huber", "all"),
        ("v20_hit_weighted_lightgbm", "all"),
        ("v20_extra_trees", "all"),
        ("two_stage_low_mid_high", "all"),
    ]
    ablations = [
        ("ablation_history", "history"),
        ("ablation_history_pci", "history_pci"),
        ("ablation_long_windows", "long_windows"),
    ]
    if args.candidate_names:
        requested = {
            item.strip()
            for item in str(args.candidate_names).split(",")
            if item.strip()
        }
        known = {name for name, _feature_set in [*candidates, *ablations]}
        unknown = sorted(requested - known)
        if unknown:
            print(
                json.dumps(
                    {"event": "v20_candidate_names_unknown", "unknown": unknown},
                    ensure_ascii=False,
                ),
                flush=True,
            )
        candidates = [item for item in candidates if item[0] in requested]
        ablations = [item for item in ablations if item[0] in requested]
        if not candidates and not ablations:
            raise RuntimeError("No candidate models remained after --candidate-names filtering")
    results: list[CandidateResult] = []
    for name, feature_set in [*candidates, *ablations]:
        try:
            print(
                json.dumps(
                    {"event": "v20_candidate_start", "candidate": name, "feature_set": feature_set},
                    ensure_ascii=False,
                ),
                flush=True,
            )
            result = fit_candidate(name, train, validation, confirm, feature_set=feature_set)
            results.append(result)
            print(
                json.dumps(
                    {
                        "event": "v20_candidate_done",
                        "candidate": name,
                        "validation_hit_005": result.validation_metrics.get("hit_rate_abs_le_005"),
                        "confirm_hit_005": result.confirm_metrics.get("hit_rate_abs_le_005"),
                    },
                    ensure_ascii=False,
                ),
                flush=True,
            )
        except Exception as exc:
            print(
                json.dumps(
                    {"event": "v20_candidate_failed", "candidate": name, "error": str(exc)},
                    ensure_ascii=False,
                ),
                flush=True,
            )
    if not results:
        raise RuntimeError("No V20 candidate model could be trained")
    if args.allow_ablation_selection:
        selectable = results
    else:
        selectable = [item for item in results if not item.name.startswith("ablation_")]
    selected = max(selectable, key=selection_key)
    all_predictions = pd.concat([item.predictions for item in results], ignore_index=True)
    selected_predictions = selected.predictions.copy()
    comparison = candidate_summary(results)
    importance = selected.importance
    paths = {
        "model": output_dir / "selected_v20_open_minus.joblib",
        "predictions": output_dir / "v20_predictions.csv",
        "comparison": output_dir / "v20_ablation_comparison.csv",
        "all_predictions": output_dir / "v20_all_candidate_predictions.csv",
        "importance": output_dir / "v20_feature_importance.csv",
        "metrics": output_dir / "v20_metrics.json",
        "report": output_dir / "v20_experiment_report.md",
        "validation_plot": output_dir / "v20_validation_actual_vs_predicted.png",
        "confirm_plot": output_dir / "v20_confirm_actual_vs_predicted.png",
        "error_plot": output_dir / "v20_confirm_error_histogram.png",
    }
    selected_predictions.to_csv(paths["predictions"], index=False, encoding="utf-8-sig")
    all_predictions.to_csv(paths["all_predictions"], index=False, encoding="utf-8-sig")
    comparison.to_csv(paths["comparison"], index=False, encoding="utf-8-sig")
    importance.to_csv(paths["importance"], index=False, encoding="utf-8-sig")
    lead_metrics = lead_time_baseline_metrics(args.dataset.resolve(), output_dir)
    validation_rows = selected_predictions.loc[selected_predictions["split"].eq("validation")]
    confirm_rows = selected_predictions.loc[selected_predictions["split"].eq("confirm")]
    validation_residual = pd.to_numeric(
        validation_rows[TARGET_COLUMN], errors="coerce"
    ) - pd.to_numeric(validation_rows["prediction__Si_mean"], errors="coerce")
    residual_quantiles = {
        "q10": float(validation_residual.quantile(0.10)),
        "q50": float(validation_residual.quantile(0.50)),
        "q90": float(validation_residual.quantile(0.90)),
        "source": "validation residual empirical quantiles",
    }
    plot_actual_vs_predicted(
        validation_rows,
        paths["validation_plot"],
        f"V20验证集：开口前{args.lead_minutes}分钟平均Si预测 vs 实际",
    )
    plot_actual_vs_predicted(
        confirm_rows,
        paths["confirm_plot"],
        f"V20确认集：开口前{args.lead_minutes}分钟平均Si预测 vs 实际",
    )
    plot_error_histogram(confirm_rows, paths["error_plot"])
    baseline = next(item for item in results if item.name == "history_lag1_baseline")
    status = candidate_status(
        selected.validation_metrics,
        baseline.validation_metrics,
        selected.confirm_metrics,
        baseline.confirm_metrics,
    )
    metrics_payload = {
        "schema": "bf.si.v20.open_minus_training_metrics.v1",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "requirement_id": "REQ-SI-V20-OPEN-MINUS-HITRATE-20260807",
        "dataset": str(args.dataset.resolve()),
        "lead_minutes": args.lead_minutes,
        "split": split_audit,
        "selected_candidate": selected.name,
        "allow_ablation_selection": bool(args.allow_ablation_selection),
        "status": status,
        "candidate_metrics": comparison.to_dict("records"),
        "selected_daily_metrics": {
            "validation": daily_metrics(validation_rows, actual_col=TARGET_COLUMN, prediction_col="prediction__Si_mean"),
            "confirm": daily_metrics(confirm_rows, actual_col=TARGET_COLUMN, prediction_col="prediction__Si_mean"),
        },
        "residual_quantiles": residual_quantiles,
        "lead_time_baseline_metrics": lead_metrics.to_dict("records") if not lead_metrics.empty else [],
        "feature_coverage": feature_coverage(frame, selected.feature_columns),
    }
    paths["metrics"].write_text(
        json.dumps(metrics_payload, ensure_ascii=False, indent=2, default=_json_default),
        encoding="utf-8",
    )
    bundle = {
        "schema": "bf.si.v20.open_minus_model.v1",
        "requirement_id": "REQ-SI-V20-OPEN-MINUS-HITRATE-20260807",
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "status": status,
        "model_name": selected.name,
        "model": selected.model,
        "feature_columns": selected.feature_columns,
        "fill_values": selected.fill_values,
        "lead_minutes": args.lead_minutes,
        "target": TARGET_COLUMN,
        "metrics": metrics_payload,
        "residual_quantiles": residual_quantiles,
        "notes": [
            "offline/shadow only",
            "does not replace production V19",
            "chemistry features are low-confidence time background when present",
        ],
    }
    joblib.dump(bundle, paths["model"])
    write_report(args, selected, results, paths, split_audit)
    return {
        "ok": True,
        "selected_candidate": selected.name,
        "status": status,
        "validation_hit_005": selected.validation_metrics.get("hit_rate_abs_le_005"),
        "validation_mae": selected.validation_metrics.get("mae"),
        "confirm_hit_005": selected.confirm_metrics.get("hit_rate_abs_le_005"),
        "confirm_mae": selected.confirm_metrics.get("mae"),
        "model": str(paths["model"]),
        "predictions": str(paths["predictions"]),
        "comparison": str(paths["comparison"]),
        "report": str(paths["report"]),
        "confirm_plot": str(paths["confirm_plot"]),
    }


def parser() -> argparse.ArgumentParser:
    cli = argparse.ArgumentParser(description="Train V20 open-minus mean-Si models.")
    cli.add_argument("--dataset", type=Path, default=DEFAULT_DATASET)
    cli.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    cli.add_argument("--lead-minutes", type=int, default=60)
    cli.add_argument("--train-end", default="2026-07-31")
    cli.add_argument("--validation-from", default="2026-08-01")
    cli.add_argument("--validation-to", default="2026-08-05")
    cli.add_argument("--confirm-from", default="2026-08-06")
    cli.add_argument("--confirm-to", default="2026-08-07")
    cli.add_argument("--min-validation-rows", type=int, default=20)
    cli.add_argument(
        "--allow-ablation-selection",
        action="store_true",
        help="Allow ablation variants to be saved as the selected offline model.",
    )
    cli.add_argument(
        "--candidate-names",
        default="",
        help=(
            "Optional comma-separated candidate names to run. Useful for high-dimensional "
            "sensor-cache experiments where ExtraTrees/two-stage full candidates are too heavy."
        ),
    )
    return cli


def main() -> int:
    args = parser().parse_args()
    result = run(args)
    print(json.dumps(result, ensure_ascii=False, indent=2, default=_json_default))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
