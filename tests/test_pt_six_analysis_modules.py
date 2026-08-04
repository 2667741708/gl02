from __future__ import annotations

import csv
from pathlib import Path
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[1]
PT = ROOT / "PT"


def write_csv(path: Path, rows: list[dict[str, object]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def run_module(folder: str, args: list[str]) -> None:
    result = subprocess.run(
        [sys.executable, str(PT / folder / "analyze.py"), *args],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr


def test_six_pt_modules_smoke(tmp_path: Path) -> None:
    heats = tmp_path / "heats.csv"
    write_csv(
        heats,
        [
            {
                "meltno": f"2#20260726-{330+i}",
                "open_ts": f"2026-07-26 {10+i:02d}:00:00",
                "close_ts": f"2026-07-26 {11+i:02d}:00:00",
                "actual_iron_qty": 300 + i,
                "target__hot_metal_Si_median": 0.2 + i * 0.05,
                "diagnosis__average_score": 20 + i,
                "sensor__P_top__mean": 250 + i,
            }
            for i in range(5)
        ],
    )
    batch = tmp_path / "batch.csv"
    write_csv(
        batch,
        [
            {"prodcentercode": "2D012", "charge": "矿批", "workdate": "2026-07-26 10:00:00", "value_sum": 55},
            {"prodcentercode": "2D012", "charge": "焦批", "workdate": "2026-07-26 10:05:00", "value_sum": 10},
        ],
    )
    sensor = tmp_path / "sensor.csv"
    write_csv(
        sensor,
        [
            {"meltno": "2#20260726-330", "variable_name": "P_top", "ts": f"2026-07-26 09:0{i}:00", "value": 250+i, "window_start": "2026-07-26 09:00:00", "window_end_exclusive": "2026-07-26 09:05:00"}
            for i in range(5)
        ],
    )
    sinter = tmp_path / "sinter.csv"
    write_csv(
        sinter,
        [{"sample_no": "JS-1", "sample_ts": "2026-07-26 09:00:00", "TFe": 53, "FeO": 9, "CaO": 12, "MgO": 2.5, "SiO2": 6, "Al2O3": 2.8, "R2": 2, "Zn": 0.02}],
    )
    run_module("01_炉次数据集", ["--input", str(heats), "--output-dir", str(tmp_path / "o1")])
    run_module("02_铁水Si预测实验", ["--input", str(heats), "--output-dir", str(tmp_path / "o2")])
    run_module("03_炉况与质量关联分析", ["--input", str(heats), "--output-dir", str(tmp_path / "o3")])
    run_module("04_矿焦批次统计", ["--input", str(batch), "--output-dir", str(tmp_path / "o4")])
    run_module("05_炉次级传感器特征", ["--input", str(sensor), "--output-dir", str(tmp_path / "o5")])
    run_module("06_原料背景分析", ["--heats", str(heats), "--sinter", str(sinter), "--output-dir", str(tmp_path / "o6")])
