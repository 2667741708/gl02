"""Create a new formal snapshot with strict earlier-cutoff Si history."""

from __future__ import annotations

import argparse
import json
import shutil
from datetime import datetime
from pathlib import Path
from typing import Sequence

import numpy as np
import pandas as pd

from .formal_dataset import attach_available_si_history, sha256_file


HISTORY_PREFIX = "history__"


def repair_snapshot(source_dir: Path, output_dir: Path) -> dict:
    if output_dir.exists():
        raise FileExistsError(f"输出目录已存在：{output_dir}")
    dataset_path = source_dir / "formal_heat_training_dataset.csv"
    heat_targets_path = source_dir / "formal_heat_targets.csv"
    if not dataset_path.is_file():
        raise FileNotFoundError(dataset_path)
    if not heat_targets_path.is_file():
        raise FileNotFoundError(heat_targets_path)
    dataset = pd.read_csv(
        dataset_path, low_memory=False, encoding="utf-8-sig"
    )
    heat_targets = pd.read_csv(
        heat_targets_path, low_memory=False, encoding="utf-8-sig"
    )
    old_history_columns = [
        column for column in dataset if column.startswith(HISTORY_PREFIX)
    ]
    base = dataset.drop(columns=old_history_columns)
    history_full = attach_available_si_history(heat_targets)
    history = history_full[
        [
            "official_meltno",
            *[
                column
                for column in history_full
                if column.startswith(HISTORY_PREFIX)
            ],
        ]
    ].copy()
    repaired = base.merge(
        history,
        on="official_meltno",
        how="left",
        validate="one_to_one",
    )
    repaired = repaired.loc[:, dataset.columns]
    if len(repaired) != len(dataset):
        raise RuntimeError("历史修复改变了炉次数")
    if not base.equals(repaired.loc[:, base.columns]):
        raise RuntimeError("历史修复意外改变了非历史字段")
    output_dir.mkdir(parents=True)
    for source in source_dir.iterdir():
        if source.name in {
            "formal_heat_training_dataset.csv",
            "manifest.json",
        }:
            continue
        if source.is_file():
            shutil.copy2(source, output_dir / source.name)
    repaired_path = output_dir / "formal_heat_training_dataset.csv"
    repaired.to_csv(repaired_path, index=False, encoding="utf-8-sig")

    changes: dict[str, dict[str, float | int]] = {}
    old_indexed = dataset.set_index("official_meltno")
    new_indexed = repaired.set_index("official_meltno")
    changed_heat_ids: set[str] = set()
    for column in history.columns:
        if column == "official_meltno":
            continue
        if column == "history__previous_meltno":
            old_values = old_indexed[column].astype("string")
            new_values = new_indexed[column].astype("string")
            mismatch = (
                old_values.fillna("<NA>") != new_values.fillna("<NA>")
            )
            changed_heat_ids.update(
                str(value) for value in mismatch.index[mismatch]
            )
            changes[column] = {
                "changed_rows": int(mismatch.sum()),
                "max_absolute_change": 0.0,
            }
            continue
        old_values = pd.to_numeric(old_indexed[column], errors="coerce")
        new_values = pd.to_numeric(new_indexed[column], errors="coerce")
        difference = (old_values - new_values).abs()
        mismatch = (
            (difference.fillna(0.0) > 1e-12)
            | (old_values.isna() != new_values.isna())
        )
        changed_heat_ids.update(
            str(value) for value in mismatch.index[mismatch]
        )
        changes[column] = {
            "changed_rows": int(mismatch.sum()),
            "max_absolute_change": (
                float(difference.max(skipna=True))
                if np.isfinite(difference.max(skipna=True))
                else 0.0
            ),
        }
    files = {}
    for path in sorted(
        item for item in output_dir.iterdir() if item.is_file()
    ):
        files[path.name] = {
            "bytes": path.stat().st_size,
            "sha256": sha256_file(path),
        }
    manifest = {
        "requirement_id": "REQ-SI-STRICT-EARLIER-HISTORY-V3-20260727",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "status": "immutable_local_history_contract_repair",
        "source_snapshot": str(source_dir.resolve()),
        "source_manifest_sha256": sha256_file(
            source_dir / "manifest.json"
        ),
        "rows": len(repaired),
        "identity_preserved": {
            "official_meltno": True,
            "prediction_cutoff_ts": True,
            "experiment_split": True,
            "sensor_features": True,
            "targets": True,
        },
        "repair": {
            "rule": (
                "history heat prediction_cutoff_ts must be strictly less "
                "than current prediction_cutoff_ts and label must be "
                "available by current cutoff"
            ),
            "numeric_canonicalization": (
                "history Si floating features rounded to 12 decimals "
                "before persistence and inference"
            ),
            "changes": changes,
            "changed_heats": [
                {
                    "official_meltno": meltno,
                    "prediction_cutoff_ts": str(
                        new_indexed.at[meltno, "prediction_cutoff_ts"]
                    ),
                    "old_previous_meltno": (
                        None
                        if pd.isna(
                            old_indexed.at[
                                meltno, "history__previous_meltno"
                            ]
                        )
                        else str(
                            old_indexed.at[
                                meltno, "history__previous_meltno"
                            ]
                        )
                    ),
                    "new_previous_meltno": (
                        None
                        if pd.isna(
                            new_indexed.at[
                                meltno, "history__previous_meltno"
                            ]
                        )
                        else str(
                            new_indexed.at[
                                meltno, "history__previous_meltno"
                            ]
                        )
                    ),
                }
                for meltno in sorted(changed_heat_ids)
            ],
        },
        "files": files,
    }
    (output_dir / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return manifest


def parser() -> argparse.ArgumentParser:
    cli = argparse.ArgumentParser(
        description="生成严格更早炉次历史特征修复快照。"
    )
    cli.add_argument("--source-dir", type=Path, required=True)
    cli.add_argument("--output-dir", type=Path, required=True)
    return cli


def main(argv: Sequence[str] | None = None) -> int:
    args = parser().parse_args(argv)
    manifest = repair_snapshot(args.source_dir, args.output_dir)
    print(json.dumps(manifest["repair"], ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
