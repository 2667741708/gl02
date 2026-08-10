from __future__ import annotations

import csv
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


MODULE_DIR = Path(__file__).resolve().parent
ROOT_DIR = MODULE_DIR.parents[0]
DEFAULT_CONFIG = ROOT_DIR / "config" / "sync_config.json"


@dataclass(frozen=True)
class SensorPoint:
    variable_name: str
    chinese_name: str
    branch: str
    short_name: str
    tag_long_name: str
    description: str
    status_usage: str
    is_derived: bool = False


def load_config(path: str | Path = DEFAULT_CONFIG) -> dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _short_number(short_name: str) -> int:
    return int(short_name.rsplit("T", 1)[1])


def _short_prefix(short_name: str) -> str:
    return short_name.rsplit("T", 1)[0] + "T"


def load_explicit_points(config: dict[str, Any]) -> list[SensorPoint]:
    tsv_path = ROOT_DIR.parents[0] / config["point_catalog_tsv"]
    points: list[SensorPoint] = []
    with tsv_path.open("r", encoding="utf-8", newline="") as fh:
        reader = csv.DictReader(fh, delimiter="\t")
        for row in reader:
            short_name = row["短名"].strip()
            tag = row["点ID/长名"].strip()
            is_derived = short_name == "派生" or not tag.startswith("\\")
            points.append(
                SensorPoint(
                    variable_name=row["变量名"].strip(),
                    chinese_name=row["中文名/标高"].strip(),
                    branch=row["节点分支"].strip(),
                    short_name=short_name,
                    tag_long_name=tag,
                    description=row["描述"].strip(),
                    status_usage=row["状态/用途"].strip(),
                    is_derived=is_derived,
                )
            )
    return points


def expand_body_ranges(config: dict[str, Any]) -> list[SensorPoint]:
    sectors = list("ABCDEFGH")
    points: list[SensorPoint] = []
    for item in config.get("body_temperature_ranges", []):
        start = item["short_start"]
        end = item["short_end"]
        prefix = _short_prefix(start)
        start_no = _short_number(start)
        end_no = _short_number(end)
        if end_no - start_no + 1 != len(sectors):
            raise ValueError(f"Body range must contain 8 sectors: {start}..{end}")
        layer = item["variable_prefix"].rsplit("L", 1)[1]
        for offset, sector in enumerate(sectors):
            short_name = f"{prefix}{start_no + offset:04d}"
            points.append(
                SensorPoint(
                    variable_name=f"T_body_L{layer}_{sector}",
                    chinese_name=item["label"].replace("A-H", sector),
                    branch=item["branch"],
                    short_name=short_name,
                    tag_long_name=f"\\冀南钢铁\\SIO\\GL02\\BT\\{short_name}",
                    description=f"{item['description_prefix']}{sector}",
                    status_usage=item["usage"],
                    is_derived=False,
                )
            )
    return points


def load_points(config_path: str | Path = DEFAULT_CONFIG, include_derived: bool = True) -> list[SensorPoint]:
    config = load_config(config_path)
    points = load_explicit_points(config) + expand_body_ranges(config)
    seen: set[str] = set()
    deduped: list[SensorPoint] = []
    for point in points:
        if point.variable_name in seen:
            continue
        if point.is_derived and not include_derived:
            continue
        seen.add(point.variable_name)
        deduped.append(point)
    return deduped


def physical_points(config_path: str | Path = DEFAULT_CONFIG) -> list[SensorPoint]:
    return [point for point in load_points(config_path, include_derived=False) if not point.is_derived]


def point_by_variable(config_path: str | Path = DEFAULT_CONFIG) -> dict[str, SensorPoint]:
    return {point.variable_name: point for point in load_points(config_path, include_derived=True)}
