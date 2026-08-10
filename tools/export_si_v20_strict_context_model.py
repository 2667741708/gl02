"""Export the selected full-context V20/V21 LightGBM model for pure-Python serving.

The production workbench must not depend on scikit-learn/joblib at request time.
This exporter converts the frozen experimental model into a gzip JSON contract
that can be loaded by ``si_v20_strict_context.py``.

Requirement: REQ-SI-V20-STRICT-HOURLY-20260810.
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


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SOURCE = (
    ROOT
    / "PT"
    / "预测铁水Si含量"
    / "reports"
    / "experiments"
    / "EXP-SI-V21-SENSOR-CACHE-20260808"
    / "training_process133_60_lightgbm"
    / "selected_v20_open_minus.joblib"
)
DEFAULT_OUTPUT = (
    ROOT
    / "高炉前端数据"
    / "智能助手"
    / "backend"
    / "models"
    / "si_v20_strict_context_lgbm_v1.json.gz"
)


def json_value(value: Any) -> Any:
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    if isinstance(value, dict):
        return {str(key): json_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [json_value(item) for item in value]
    if hasattr(value, "item"):
        return json_value(value.item())
    return str(value)


def export_model(source: Path, output: Path) -> dict[str, Any]:
    payload = joblib.load(source)
    model = payload["model"]
    booster = model.booster_
    dump = booster.dump_model()
    feature_columns = [str(item) for item in payload["feature_columns"]]
    exported = {
        "schema": "bf.si.v20.strict_context_lightgbm.v1",
        "requirement_id": "REQ-SI-V20-STRICT-HOURLY-20260810",
        "source_schema": payload.get("schema"),
        "source_path": source.name,
        "model_name": payload.get("model_name") or "v20_lightgbm_huber",
        "lead_minutes": int(payload.get("lead_minutes") or 60),
        "target": payload.get("target") or "target__Si_mean",
        "feature_columns": feature_columns,
        "fill_values": json_value(payload.get("fill_values") or {}),
        "residual_quantiles": json_value(payload.get("residual_quantiles") or {}),
        "metrics": json_value(payload.get("metrics") or {}),
        "lightgbm": {
            "objective": dump.get("objective"),
            "average_output": bool(dump.get("average_output")),
            "feature_names": dump.get("feature_names") or feature_columns,
            "tree_info": dump.get("tree_info") or [],
        },
        "context_groups": {
            "scored": ["published_history_si", "pci_1_12h", "process133_sensor_windows"],
            "audited_optional": ["imes_sinter_chemistry_time_background"],
        },
        "status": "experimental_shadow",
    }
    encoded = json.dumps(exported, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    output.parent.mkdir(parents=True, exist_ok=True)
    with gzip.open(output, "wb", compresslevel=9) as handle:
        handle.write(encoded)
    return {
        "output": str(output),
        "feature_count": len(feature_columns),
        "tree_count": len(exported["lightgbm"]["tree_info"]),
        "sha256": hashlib.sha256(output.read_bytes()).hexdigest(),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    result = export_model(args.source.resolve(), args.output.resolve())
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
