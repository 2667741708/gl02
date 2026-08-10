#!/usr/bin/env python3
"""Verify an isolated 8094 recommendation package without production writes."""

from __future__ import annotations

import argparse
import importlib
import json
import os
import sys
from pathlib import Path


LABELS = {"normal", "lowline", "edge", "center", "channel", "cold", "hot", "column"}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--preview-root", type=Path, required=True)
    parser.add_argument("--engine-dir", type=Path, required=True)
    args = parser.parse_args()
    preview_root = args.preview_root.resolve()
    engine_dir = args.engine_dir.resolve()
    os.environ["BF_RECOMMENDATION_ENGINE_DIR"] = str(engine_dir)
    sys.path.insert(0, str(preview_root))
    adapter = importlib.import_module("recommendation_adapter")
    bundle = adapter.generate_recommendation_bundle(
        {
            "diagnosis_ts": "2026-08-05T13:00:00+08:00",
            "main_label": "cold",
            "main_score": 76,
            "secondary_label": "lowline",
            "raw_scores": {
                "normal": 20,
                "lowline": 54,
                "edge": 31,
                "center": 18,
                "channel": 12,
                "cold": 76,
                "hot": 9,
                "column": 14,
            },
        },
        {"P_top": 180, "T_top": 108, "T_blast": 1120, "GasUtil": 42, "L": 2.0},
    )
    conditions = bundle.get("conditions") or []
    if bundle.get("schema_version") != "multi_condition_recommendation.v1":
        raise SystemExit("unexpected recommendation bundle schema")
    if {item.get("label") for item in conditions} != LABELS or len(conditions) != 8:
        raise SystemExit("recommendation bundle does not contain all eight conditions")
    if conditions[0].get("scope") != "active":
        raise SystemExit("first condition is not the active plan")
    if not all(item.get("read_only") and item.get("recommendation", {}).get("actions") for item in conditions):
        raise SystemExit("one or more condition plans are incomplete")
    print(
        json.dumps(
            {
                "ok": True,
                "schema_version": bundle["schema_version"],
                "condition_count": len(conditions),
                "engine_version": bundle.get("engine_meta", {}).get("version"),
                "read_only": bundle.get("engine_meta", {}).get("read_only"),
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
