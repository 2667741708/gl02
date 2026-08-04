"""Frozen-model prospective prediction and delayed-label settlement.

The prediction ledger is append-only and contains no current-heat target.
Labels are joined later by ``settle_ledger`` after their availability time.

Requirement:
    REQ-SI-PROSPECTIVE-RUNNER-V1-20260727
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from datetime import datetime
from pathlib import Path
from typing import Any, Sequence

import joblib
import numpy as np
import pandas as pd

from .formal_dataset import canonicalize_history_features, sha256_file
from .train_v3 import TARGET
from .train_v6 import _history_baseline, metrics
from .v4_features import build_v4_feature_blocks
from .v5_features import (
    derive_temporal_spatial_neurons,
    load_temporal_statistics,
    pivot_temporal_statistics,
)
from .v6_features import (
    attach_published_chemistry_history,
    derive_heat_state_neurons,
    derive_multiscale_neurons,
)
from .v10_features import (
    derive_lag_band_neurons,
    derive_spatial_field_modes,
)
from .v13_features import derive_lag_moment_neurons


SUPPORTED_PROTOCOL_IDS = {
    "SI-PROSPECTIVE-BLIND-V1-20260727",
    "SI-PROSPECTIVE-BLIND-V2-HISTORYFIX-20260727",
    "SI-PROSPECTIVE-BLIND-V3-HISTORYFIXR12-20260727",
    "SI-PROSPECTIVE-BLIND-V4-LAGMOMENT-20260727",
}
LEDGER_SCHEMA = "si_prospective_prediction_ledger.v1"


def _read_protocol(path: Path) -> dict[str, Any]:
    protocol = json.loads(path.read_text(encoding="utf-8"))
    if protocol.get("protocol_id") not in SUPPORTED_PROTOCOL_IDS:
        raise ValueError(f"未知前瞻协议：{protocol.get('protocol_id')}")
    return protocol


def _model_path(protocol_path: Path, candidate: dict[str, Any]) -> Path:
    return (protocol_path.parent / candidate["model_path"]).resolve()


def load_frozen_models(
    protocol_path: Path,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Verify frozen hashes before unpickling model artifacts."""

    protocol = _read_protocol(protocol_path)
    bundles: dict[str, Any] = {}
    for candidate in protocol["frozen_candidates"]:
        path = _model_path(protocol_path, candidate)
        if not path.is_file():
            raise RuntimeError(f"冻结模型不存在：{path}")
        actual = sha256_file(path)
        expected = str(candidate["model_sha256"]).lower()
        if actual != expected:
            raise RuntimeError(
                f"冻结模型SHA-256不一致：{candidate['candidate_id']}"
            )
        bundles[candidate["candidate_id"]] = joblib.load(path)
    return protocol, bundles


def _available_history_for_predictions(
    prediction_rows: pd.DataFrame,
    all_heat_targets: pd.DataFrame,
) -> pd.DataFrame:
    """Derive legacy V3 history without requiring the current heat label."""

    required_predictions = {"official_meltno", "prediction_cutoff_ts"}
    required_targets = {
        "official_meltno",
        "prediction_cutoff_ts",
        "label_available_ts",
        TARGET,
    }
    if missing := sorted(required_predictions - set(prediction_rows)):
        raise ValueError(f"预测炉次缺少字段：{missing}")
    if missing := sorted(required_targets - set(all_heat_targets)):
        raise ValueError(f"历史目标缺少字段：{missing}")
    targets = all_heat_targets[list(required_targets)].copy()
    targets["prediction_cutoff_ts"] = pd.to_datetime(
        targets["prediction_cutoff_ts"], errors="coerce"
    )
    targets["label_available_ts"] = pd.to_datetime(
        targets["label_available_ts"], errors="coerce"
    )
    targets[TARGET] = pd.to_numeric(targets[TARGET], errors="coerce")
    targets = targets.dropna(
        subset=[
            "official_meltno",
            "prediction_cutoff_ts",
            "label_available_ts",
            TARGET,
        ]
    )
    target_records = targets.to_dict("records")
    output: list[dict[str, Any]] = []
    predictions = prediction_rows[
        ["official_meltno", "prediction_cutoff_ts"]
    ].copy()
    predictions["prediction_cutoff_ts"] = pd.to_datetime(
        predictions["prediction_cutoff_ts"], errors="raise"
    )
    for current in predictions.to_dict("records"):
        cutoff = current["prediction_cutoff_ts"]
        meltno = str(current["official_meltno"])
        available = [
            item
            for item in target_records
            if str(item["official_meltno"]) != meltno
            and item["prediction_cutoff_ts"] < cutoff
            and item["label_available_ts"] <= cutoff
        ]
        available.sort(
            key=lambda item: (
                item["prediction_cutoff_ts"],
                str(item["official_meltno"]),
            )
        )
        values = [float(item[TARGET]) for item in available]
        recent3 = values[-3:]
        recent6 = values[-6:]
        slope3 = (
            float(
                np.polyfit(
                    np.arange(len(recent3), dtype=float),
                    np.asarray(recent3, dtype=float),
                    1,
                )[0]
            )
            if len(recent3) >= 2
            else np.nan
        )
        output.append(
            {
                "official_meltno": meltno,
                "history__available_heat_count": len(available),
                "history__previous_meltno": (
                    str(available[-1]["official_meltno"])
                    if available
                    else None
                ),
                "history__previous_Si_1": (
                    values[-1] if values else np.nan
                ),
                "history__previous_Si_median_3": (
                    float(np.median(recent3)) if recent3 else np.nan
                ),
                "history__previous_Si_slope_3": slope3,
                "history__previous_Si_median_6": (
                    float(np.median(recent6)) if recent6 else np.nan
                ),
            }
        )
    return canonicalize_history_features(pd.DataFrame(output))


def build_inference_feature_frame(
    prediction_rows: pd.DataFrame,
    all_heat_targets: pd.DataFrame,
    samples: pd.DataFrame,
    catalog_path: Path,
    temporal_dir: Path,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Rebuild V10 features without reading current-heat target columns."""

    forbidden = [
        column
        for column in prediction_rows
        if column.startswith("target__")
    ]
    frame = prediction_rows.drop(columns=forbidden).copy()
    frame = frame.drop(
        columns=[
            column for column in frame if column.startswith("history__")
        ],
        errors="ignore",
    )
    if frame["official_meltno"].duplicated().any():
        raise ValueError("预测输入official_meltno必须唯一")
    frame["prediction_cutoff_ts"] = pd.to_datetime(
        frame["prediction_cutoff_ts"], errors="raise"
    )
    legacy_history = _available_history_for_predictions(
        frame, all_heat_targets
    )
    frame = frame.merge(
        legacy_history,
        on="official_meltno",
        how="left",
        validate="one_to_one",
    )
    v4_blocks, v4_audit = build_v4_feature_blocks(
        frame, all_heat_targets, catalog_path
    )
    temporal_long, temporal_manifest = load_temporal_statistics(
        temporal_dir
    )
    windows = tuple(
        int(value)
        for value in temporal_manifest["feature_contract"][
            "windows_minutes"
        ]
    )
    temporal, temporal_audit = pivot_temporal_statistics(
        temporal_long, frame, windows_minutes=windows
    )
    spatial = derive_temporal_spatial_neurons(
        temporal, windows_minutes=windows
    )
    multiscale = derive_multiscale_neurons(temporal)
    heat_state = derive_heat_state_neurons(temporal)
    chemistry, chemistry_audit = attach_published_chemistry_history(
        frame, samples
    )
    lag_bands = derive_lag_band_neurons(temporal)
    field_modes = derive_spatial_field_modes(temporal)
    lag_moments = derive_lag_moment_neurons(temporal)
    combined = pd.concat(
        [
            frame,
            *v4_blocks.values(),
            temporal,
            spatial,
            multiscale,
            heat_state,
            chemistry,
            lag_bands,
            field_modes,
            lag_moments,
        ],
        axis=1,
    ).replace([np.inf, -np.inf], np.nan)
    if any(column.startswith("target__") for column in combined):
        raise RuntimeError("推理特征意外包含当前炉target字段")
    return combined, {
        "rows": len(combined),
        "windows_minutes": list(windows),
        "v4": v4_audit,
        "temporal": temporal_audit,
        "chemistry": chemistry_audit,
        "lag_moment_feature_count": len(lag_moments.columns),
        "target_columns_removed": forbidden,
        "current_heat_target_used": False,
    }


def _require_features(
    frame: pd.DataFrame, features: Sequence[str], candidate: str
) -> None:
    missing = sorted(set(features) - set(frame))
    if missing:
        raise RuntimeError(
            f"{candidate}推理特征缺失{len(missing)}项：{missing[:10]}"
        )


def predict_frozen_candidates(
    frame: pd.DataFrame,
    protocol: dict[str, Any],
    bundles: dict[str, Any],
) -> pd.DataFrame:
    """Run frozen V9/V10 models on a target-free feature frame."""

    v9 = bundles["V9_POINT_MAE_CHAMPION"]
    v10 = bundles["V10_PRETEST_STABILITY_CHAMPION"]
    _require_features(frame, v9["direct_features"], "V9 direct")
    _require_features(frame, v9["thermal_features"], "V9 thermal")
    _require_features(frame, v10["features"], "V10")
    v9_baseline = _history_baseline(frame, fallback=v9["fallback"])
    direct = v9["direct_model"].predict(frame[v9["direct_features"]])
    thermal = (
        v9["thermal_model"].predict(frame[v9["thermal_features"]])
        + v9_baseline.to_numpy(float)
    )
    lgbm7 = (
        v9["lgbm_models"]["lgbm_huber7"].predict(
            frame[v9["thermal_features"]]
        )
        + v9_baseline.to_numpy(float)
    )
    lgbm15 = (
        v9["lgbm_models"]["lgbm_huber15_decay90"].predict(
            frame[v9["thermal_features"]]
        )
        + v9_baseline.to_numpy(float)
    )
    components = {
        "direct": np.asarray(direct, dtype=float),
        "thermal_xgb": np.asarray(thermal, dtype=float),
        "lgbm_huber7": np.asarray(lgbm7, dtype=float),
        "lgbm_huber15_decay90": np.asarray(lgbm15, dtype=float),
        "history": v9_baseline.to_numpy(float),
    }
    v9_point = sum(
        float(v9["weights"][name]) * values
        for name, values in components.items()
    )
    v10_baseline = _history_baseline(frame, fallback=v10["fallback"])
    v10_point = (
        v10["model"].predict(frame[v10["features"]])
        + v10_baseline.to_numpy(float)
    )
    distribution = np.sort(
        np.vstack(
            [
                model.predict(frame[v10["features"]])
                + v10_baseline.to_numpy(float)
                for model in v10["distribution_models"].values()
            ]
        ),
        axis=0,
    )
    output = frame[
        ["official_meltno", "prediction_cutoff_ts"]
    ].copy()
    output["prediction__v9_point"] = v9_point
    output["prediction__v9_direct"] = components["direct"]
    output["prediction__v9_thermal_xgb"] = components["thermal_xgb"]
    output["prediction__v9_lgbm_huber7"] = components["lgbm_huber7"]
    output["prediction__v9_lgbm_huber15_decay90"] = components[
        "lgbm_huber15_decay90"
    ]
    output["prediction__v9_history"] = components["history"]
    output["prediction__v10_point"] = v10_point
    output["prediction__v10_p10"] = distribution[0]
    output["prediction__v10_p50"] = distribution[1]
    output["prediction__v10_p90"] = distribution[2]
    if "V13_PRETEST_STABILITY_CHAMPION" in bundles:
        v13 = bundles["V13_PRETEST_STABILITY_CHAMPION"]
        _require_features(frame, v13["features"], "V13")
        v13_baseline = _history_baseline(
            frame, fallback=v13["fallback"]
        )
        v13_point = (
            v13["model"].predict(frame[v13["features"]])
            + v13_baseline.to_numpy(float)
        )
        v13_distribution = np.sort(
            np.vstack(
                [
                    model.predict(frame[v13["features"]])
                    + v13_baseline.to_numpy(float)
                    for model in v13[
                        "distribution_models"
                    ].values()
                ]
            ),
            axis=0,
        )
        output["prediction__v13_point"] = v13_point
        output["prediction__v13_p10"] = v13_distribution[0]
        output["prediction__v13_p50"] = v13_distribution[1]
        output["prediction__v13_p90"] = v13_distribution[2]
    output["protocol_id"] = protocol["protocol_id"]
    return output


def _canonical_json(payload: dict[str, Any]) -> str:
    return json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    )


def _prediction_id(payload: dict[str, Any]) -> str:
    identity = {
        "protocol_id": payload["protocol_id"],
        "official_meltno": payload["official_meltno"],
        "prediction_cutoff_ts": payload["prediction_cutoff_ts"],
    }
    return hashlib.sha256(_canonical_json(identity).encode("utf-8")).hexdigest()


def _load_ledger(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    records: list[dict[str, Any]] = []
    for line_number, line in enumerate(
        path.read_text(encoding="utf-8").splitlines(), start=1
    ):
        if not line.strip():
            continue
        try:
            records.append(json.loads(line))
        except json.JSONDecodeError as error:
            raise RuntimeError(
                f"预测账本第{line_number}行损坏"
            ) from error
    return records


def append_prediction_ledger(
    path: Path,
    predictions: pd.DataFrame,
    protocol: dict[str, Any],
    *,
    recorded_at: datetime,
    source_fingerprint: str,
    enforce_future_boundary: bool = True,
) -> dict[str, int]:
    """Append idempotent target-free prediction records."""

    existing = _load_ledger(path)
    by_id = {record["prediction_id"]: record for record in existing}
    if len(by_id) != len(existing):
        raise RuntimeError("预测账本存在重复prediction_id")
    boundary = pd.Timestamp(
        protocol["prospective_eligibility"][
            "prediction_cutoff_strictly_after"
        ]
    ).tz_localize(None)
    model_hashes = {
        candidate["candidate_id"]: candidate["model_sha256"]
        for candidate in protocol["frozen_candidates"]
    }
    appended: list[dict[str, Any]] = []
    skipped = 0
    for row in predictions.to_dict("records"):
        cutoff = pd.Timestamp(row["prediction_cutoff_ts"]).tz_localize(None)
        if enforce_future_boundary and not cutoff > boundary:
            raise ValueError(
                f"炉次{row['official_meltno']}不满足前瞻时间边界"
            )
        payload = {
            "schema": LEDGER_SCHEMA,
            "protocol_id": protocol["protocol_id"],
            "official_meltno": str(row["official_meltno"]),
            "prediction_cutoff_ts": cutoff.isoformat(),
            "recorded_at": recorded_at.isoformat(),
            "source_fingerprint": source_fingerprint,
            "model_sha256": model_hashes,
            "predictions": {
                key.removeprefix("prediction__"): float(value)
                for key, value in row.items()
                if str(key).startswith("prediction__")
            },
            "contains_current_heat_label": False,
        }
        payload["prediction_id"] = _prediction_id(payload)
        existing_record = by_id.get(payload["prediction_id"])
        if existing_record is not None:
            if _canonical_json(existing_record) != _canonical_json(payload):
                raise RuntimeError(
                    f"同一预测ID内容冲突：{payload['prediction_id']}"
                )
            skipped += 1
            continue
        appended.append(payload)
        by_id[payload["prediction_id"]] = payload
    if appended:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8", newline="\n") as handle:
            for payload in appended:
                handle.write(_canonical_json(payload) + "\n")
            handle.flush()
            os.fsync(handle.fileno())
    return {
        "existing": len(existing),
        "appended": len(appended),
        "idempotent_skipped": skipped,
        "total": len(existing) + len(appended),
    }


def settle_ledger(
    ledger_path: Path,
    heat_targets: pd.DataFrame,
    protocol_path: Path,
    *,
    as_of: datetime,
) -> dict[str, Any]:
    """Join delayed labels without modifying the prediction ledger."""

    protocol = _read_protocol(protocol_path)
    records = _load_ledger(ledger_path)
    targets = heat_targets[
        [
            "official_meltno",
            "prediction_cutoff_ts",
            "label_available_ts",
            TARGET,
        ]
    ].copy()
    targets["prediction_cutoff_ts"] = pd.to_datetime(
        targets["prediction_cutoff_ts"], errors="coerce"
    )
    targets["label_available_ts"] = pd.to_datetime(
        targets["label_available_ts"], errors="coerce"
    )
    targets[TARGET] = pd.to_numeric(targets[TARGET], errors="coerce")
    targets = targets.dropna(
        subset=[
            "official_meltno",
            "prediction_cutoff_ts",
            "label_available_ts",
            TARGET,
        ]
    )
    if targets["official_meltno"].duplicated().any():
        raise ValueError("结算标签official_meltno不唯一")
    target_map = targets.set_index("official_meltno").to_dict("index")
    as_of_ts = pd.Timestamp(as_of).tz_localize(None)
    settled: list[dict[str, Any]] = []
    rejected_after_label = 0
    for record in records:
        target = target_map.get(str(record["official_meltno"]))
        if target is None:
            continue
        label_available = pd.Timestamp(
            target["label_available_ts"]
        ).tz_localize(None)
        if label_available > as_of_ts:
            continue
        recorded = pd.Timestamp(record["recorded_at"]).tz_localize(None)
        if not recorded < label_available:
            rejected_after_label += 1
            continue
        settled.append(
            {
                **record,
                "actual": float(target[TARGET]),
                "label_available_ts": label_available.isoformat(),
            }
        )
    minimum_rows = int(
        protocol["prospective_eligibility"]["minimum_completed_heats"]
    )
    minimum_days = int(
        protocol["prospective_eligibility"][
            "minimum_calendar_span_days"
        ]
    )
    cutoffs = [
        pd.Timestamp(item["prediction_cutoff_ts"]).tz_localize(None)
        for item in settled
    ]
    span_days = (
        float((max(cutoffs) - min(cutoffs)).total_seconds() / 86400.0)
        if len(cutoffs) >= 2
        else 0.0
    )
    ready = len(settled) >= minimum_rows and span_days >= minimum_days
    result: dict[str, Any] = {
        "protocol_id": protocol["protocol_id"],
        "ledger_rows": len(records),
        "settled_rows": len(settled),
        "rejected_prediction_not_before_label": rejected_after_label,
        "calendar_span_days": span_days,
        "minimum_completed_heats": minimum_rows,
        "minimum_calendar_span_days": minimum_days,
        "evaluation_ready": ready,
        "metrics": {},
    }
    if ready:
        actual = np.asarray([item["actual"] for item in settled], dtype=float)
        point_candidates = ["v9_point", "v10_point"]
        if settled and all(
            "v13_point" in item["predictions"] for item in settled
        ):
            point_candidates.append("v13_point")
        for candidate in point_candidates:
            predicted = np.asarray(
                [item["predictions"][candidate] for item in settled],
                dtype=float,
            )
            result["metrics"][candidate] = metrics(actual, predicted)
        p10 = np.asarray(
            [item["predictions"]["v10_p10"] for item in settled]
        )
        p90 = np.asarray(
            [item["predictions"]["v10_p90"] for item in settled]
        )
        result["metrics"]["v10_distribution"] = {
            "p10_p90_coverage": float(
                np.mean((actual >= p10) & (actual <= p90))
            ),
            "mean_p10_p90_width": float(np.mean(p90 - p10)),
        }
        if "v13_point" in point_candidates:
            v13_p10 = np.asarray(
                [item["predictions"]["v13_p10"] for item in settled]
            )
            v13_p90 = np.asarray(
                [item["predictions"]["v13_p90"] for item in settled]
            )
            result["metrics"]["v13_distribution"] = {
                "p10_p90_coverage": float(
                    np.mean(
                        (actual >= v13_p10) & (actual <= v13_p90)
                    )
                ),
                "mean_p10_p90_width": float(
                    np.mean(v13_p90 - v13_p10)
                ),
            }
    return result


def _source_fingerprint(paths: Sequence[Path]) -> str:
    payload = [
        {"path": path.name, "sha256": sha256_file(path)} for path in paths
    ]
    return hashlib.sha256(_canonical_json({"inputs": payload}).encode()).hexdigest()


def parser() -> argparse.ArgumentParser:
    cli = argparse.ArgumentParser(
        description="冻结Si模型前瞻预测与延迟标签结算。"
    )
    subcommands = cli.add_subparsers(dest="command", required=True)
    predict = subcommands.add_parser("predict")
    predict.add_argument("--prediction-rows", type=Path, required=True)
    predict.add_argument("--heat-targets", type=Path, required=True)
    predict.add_argument("--samples", type=Path, required=True)
    predict.add_argument("--sensor-catalog", type=Path, required=True)
    predict.add_argument("--temporal-dir", type=Path, required=True)
    predict.add_argument("--protocol", type=Path, required=True)
    predict.add_argument("--ledger", type=Path, required=True)
    settle = subcommands.add_parser("settle")
    settle.add_argument("--ledger", type=Path, required=True)
    settle.add_argument("--heat-targets", type=Path, required=True)
    settle.add_argument("--protocol", type=Path, required=True)
    settle.add_argument("--output", type=Path, required=True)
    return cli


def main(argv: Sequence[str] | None = None) -> int:
    args = parser().parse_args(argv)
    if args.command == "predict":
        prediction_rows = pd.read_csv(
            args.prediction_rows, low_memory=False, encoding="utf-8-sig"
        )
        heat_targets = pd.read_csv(
            args.heat_targets, low_memory=False, encoding="utf-8-sig"
        )
        samples = pd.read_csv(
            args.samples, low_memory=False, encoding="utf-8-sig"
        )
        features, audit = build_inference_feature_frame(
            prediction_rows,
            heat_targets,
            samples,
            args.sensor_catalog,
            args.temporal_dir,
        )
        protocol, bundles = load_frozen_models(args.protocol)
        predictions = predict_frozen_candidates(
            features, protocol, bundles
        )
        fingerprint = _source_fingerprint(
            [
                args.prediction_rows,
                args.heat_targets,
                args.samples,
                args.temporal_dir / "manifest.json",
            ]
        )
        ledger_result = append_prediction_ledger(
            args.ledger,
            predictions,
            protocol,
            recorded_at=datetime.now().astimezone(),
            source_fingerprint=fingerprint,
        )
        print(
            json.dumps(
                {"features": audit, "ledger": ledger_result},
                ensure_ascii=False,
                indent=2,
                default=str,
            )
        )
        return 0
    heat_targets = pd.read_csv(
        args.heat_targets, low_memory=False, encoding="utf-8-sig"
    )
    result = settle_ledger(
        args.ledger,
        heat_targets,
        args.protocol,
        as_of=datetime.now().astimezone(),
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
