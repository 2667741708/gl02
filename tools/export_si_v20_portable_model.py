#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Export the selected V20 history-Si ExtraTrees model to portable gzip JSON.

The online 8093/8094 service uses this artifact without importing sklearn,
joblib, pandas or numpy.  Export verification compares portable traversal with
the original estimator on the recorded V20 dataset.

Requirement: REQ-SI-V20-8093-8094-SHADOW-WORKBENCH-20260808.
"""

from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import math
from pathlib import Path
from typing import Any

import joblib
import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_BUNDLE = (
    ROOT
    / "PT"
    / "预测铁水Si含量"
    / "reports"
    / "experiments"
    / "EXP-SI-V20-OPEN-MINUS-20260807"
    / "quick60_history_pci_training_ablationselect"
    / "selected_v20_open_minus.joblib"
)
DEFAULT_DATASET = (
    ROOT
    / "PT"
    / "预测铁水Si含量"
    / "reports"
    / "experiments"
    / "EXP-SI-V20-OPEN-MINUS-20260807"
    / "quick60_history_pci"
    / "v20_open_minus_dataset.csv"
)
DEFAULT_OUTPUT = (
    ROOT
    / "高炉前端数据"
    / "智能助手"
    / "backend"
    / "models"
    / "si_v20_history_portable_v1.json.gz"
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="导出 V20 历史Si便携模型并核对预测一致性。")
    parser.add_argument("--bundle", type=Path, default=DEFAULT_BUNDLE)
    parser.add_argument("--dataset", type=Path, default=DEFAULT_DATASET)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--verify-rows", type=int, default=256)
    return parser.parse_args()


def _tree_payload(estimator: Any) -> dict[str, Any]:
    tree = estimator.tree_
    return {
        "children_left": tree.children_left.astype(int).tolist(),
        "children_right": tree.children_right.astype(int).tolist(),
        "feature": tree.feature.astype(int).tolist(),
        "threshold": tree.threshold.astype(float).tolist(),
        "value": tree.value[:, 0, 0].astype(float).tolist(),
    }


def _portable_predict(payload: dict[str, Any], row: list[float]) -> float:
    total = 0.0
    trees = payload["trees"]
    for tree in trees:
        node = 0
        while tree["children_left"][node] != tree["children_right"][node]:
            feature = tree["feature"][node]
            node = (
                tree["children_left"][node]
                if row[feature] <= tree["threshold"][node]
                else tree["children_right"][node]
            )
        total += tree["value"][node]
    return total / len(trees)


def main() -> int:
    args = parse_args()
    bundle = joblib.load(args.bundle)
    model = bundle.get("model")
    if type(model).__name__ != "ExtraTreesRegressor":
        raise RuntimeError(f"只支持 ExtraTreesRegressor，当前为 {type(model).__name__}")
    features = [str(item) for item in bundle.get("feature_columns", [])]
    fill_values = {
        str(key): float(value)
        for key, value in dict(bundle.get("fill_values", {})).items()
    }
    if not features:
        raise RuntimeError("V20 bundle 缺少 feature_columns")
    payload: dict[str, Any] = {
        "schema": "bf.si.v20.portable_extra_trees.v1",
        "source_schema": str(bundle.get("schema", "")),
        "requirement_id": "REQ-SI-V20-8093-8094-SHADOW-WORKBENCH-20260808",
        "model_name": str(bundle.get("model_name", "v20_history")),
        "lead_minutes": int(bundle.get("lead_minutes", 60)),
        "target": str(bundle.get("target", "target__Si_mean")),
        "feature_columns": features,
        "fill_values": fill_values,
        "residual_quantiles": {
            str(key): (float(value) if isinstance(value, (int, float, np.number)) else str(value))
            for key, value in dict(bundle.get("residual_quantiles", {})).items()
        },
        "metrics": bundle.get("metrics", {}),
        "tree_count": len(model.estimators_),
        "trees": [_tree_payload(item) for item in model.estimators_],
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    encoded = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    with gzip.open(args.output, "wb", compresslevel=9) as handle:
        handle.write(encoded)

    frame = pd.read_csv(args.dataset)
    verify_count = max(1, min(int(args.verify_rows), len(frame)))
    verify = frame.tail(verify_count).copy()
    matrix = verify.reindex(columns=features).apply(pd.to_numeric, errors="coerce")
    matrix = matrix.fillna(pd.Series({name: fill_values.get(name, 0.0) for name in features}))
    native = model.predict(matrix)
    portable = np.asarray(
        [_portable_predict(payload, [float(value) for value in row]) for row in matrix.to_numpy()],
        dtype=float,
    )
    delta = np.abs(native - portable)
    max_delta = float(delta.max()) if len(delta) else 0.0
    if not math.isfinite(max_delta) or max_delta > 1e-12:
        raise RuntimeError(f"便携模型预测不一致，max_abs_delta={max_delta}")
    sha256 = hashlib.sha256(args.output.read_bytes()).hexdigest().upper()
    audit = {
        "schema": "bf.si.v20.portable_export_audit.v1",
        "artifact": str(args.output),
        "sha256": sha256,
        "compressed_bytes": args.output.stat().st_size,
        "tree_count": len(model.estimators_),
        "feature_count": len(features),
        "verification_rows": verify_count,
        "max_abs_prediction_delta": max_delta,
        "status": "verified_equivalent",
    }
    audit_path = args.output.with_suffix(args.output.suffix + ".audit.json")
    audit_path.write_text(json.dumps(audit, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(audit, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
