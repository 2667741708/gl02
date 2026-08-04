"""Rebuild formal Si V3 targets/splits from hashed local extraction artifacts.

Use this entry when only label-contract logic changes and the remote read-only
sources are temporarily unreachable.  It never connects to a database.

Requirement:
    REQ-SI-FORMAL-DATASET-V3-20260726
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Sequence

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
MODULE_ROOT = ROOT / "PT" / "预测铁水Si含量"
MODULE_SRC = MODULE_ROOT / "src"
if str(MODULE_SRC) not in sys.path:
    sys.path.insert(0, str(MODULE_SRC))

from si_semantic_engine.formal_dataset import (  # noqa: E402
    assemble_formal_dataset,
    sha256_file,
    write_dataset_artifacts,
)
from si_semantic_engine.formal_labels import build_label_contract  # noqa: E402


DEFAULT_DIR = MODULE_ROOT / "data" / "processed" / "formal_v3_20260726"


def run(output_dir: Path, min_sensor_last_values: int) -> dict:
    output_dir = output_dir.resolve()
    samples_path = output_dir / "formal_samples.csv"
    sensors_path = output_dir / "formal_sensor_features.csv"
    manifest_path = output_dir / "manifest.json"
    for path in (samples_path, sensors_path, manifest_path):
        if not path.is_file():
            raise FileNotFoundError(path)
    source_hashes = {
        samples_path.name: sha256_file(samples_path),
        sensors_path.name: sha256_file(sensors_path),
    }
    previous_manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    samples = pd.read_csv(samples_path, low_memory=False, encoding="utf-8-sig")
    sensors = pd.read_csv(sensors_path, low_memory=False, encoding="utf-8-sig")
    labels = build_label_contract(samples)
    dataset = assemble_formal_dataset(
        labels.heat_targets,
        sensors,
        min_sensor_last_values=min_sensor_last_values,
    )
    source_metadata = dict(previous_manifest.get("source_metadata", {}))
    source_metadata["local_contract_rebuild"] = {
        "database_connections": 0,
        "input_hashes_before_rebuild": source_hashes,
        "reason": "label timing gate changed; remote SSH temporarily unavailable",
    }
    return write_dataset_artifacts(
        samples=labels.samples,
        heat_targets=labels.heat_targets,
        next_sample_targets=labels.next_sample_targets,
        sensor_features=sensors,
        dataset=dataset,
        audit=labels.audit,
        output_dir=output_dir,
        source_metadata=source_metadata,
    )


def parser() -> argparse.ArgumentParser:
    cli = argparse.ArgumentParser(
        description="不连接数据库，使用已有哈希产物重建正式Si V3标签与切分。"
    )
    cli.add_argument("--output-dir", type=Path, default=DEFAULT_DIR)
    cli.add_argument("--min-sensor-last-values", type=int, default=100)
    return cli


def main(argv: Sequence[str] | None = None) -> int:
    args = parser().parse_args(argv)
    manifest = run(args.output_dir, args.min_sensor_last_values)
    print(json.dumps(manifest["shape"], ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

