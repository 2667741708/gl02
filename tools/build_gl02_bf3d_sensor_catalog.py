#!/usr/bin/env python3
"""Build the GL02 3D sensor catalog from the read-only sensor registry.

The database is authoritative for point identifiers and raw metadata. Units and
3D display semantics are deliberately kept in separate controlled documents.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import psycopg
from psycopg.rows import dict_row


LAYER_SEMANTICS: dict[int, dict[str, Any]] = {
    7: {"elevation_m": 16.860, "process_zone": "炉腹", "zone_segment": "下部", "abbr": "腹下"},
    8: {"elevation_m": 18.335, "process_zone": "炉腹", "zone_segment": "上部", "abbr": "腹上"},
    9: {"elevation_m": 20.125, "process_zone": "炉腰", "zone_segment": None, "abbr": "炉腰"},
    10: {"elevation_m": 21.860, "process_zone": "炉身", "zone_segment": "下部", "abbr": "身下"},
    11: {"elevation_m": 23.711, "process_zone": "炉身", "zone_segment": "下部", "abbr": "身下"},
    12: {"elevation_m": 25.441, "process_zone": "炉身", "zone_segment": "下部", "abbr": "身下"},
    13: {"elevation_m": 27.171, "process_zone": "炉身", "zone_segment": "下部", "abbr": "身下"},
    14: {"elevation_m": 28.901, "process_zone": "炉身", "zone_segment": "中部", "abbr": "身中"},
    15: {"elevation_m": 30.631, "process_zone": "炉身", "zone_segment": "上部", "abbr": "身上"},
    16: {"elevation_m": 32.361, "process_zone": "炉身", "zone_segment": "上部", "abbr": "身上"},
}


STATIC_PRESSURE_SEMANTICS: dict[str, dict[str, Any]] = {
    "lower": {
        "elevation_m": 20.350,
        "process_zone": "炉身",
        "zone_segment": "下部",
        "abbr": "身下",
        "source_zone_raw": "炉腰部",
    },
    "middle": {
        "elevation_m": 23.488,
        "process_zone": "炉身",
        "zone_segment": "中部",
        "abbr": "身中",
        "source_zone_raw": "炉身下部",
    },
    "upper": {
        "elevation_m": 28.976,
        "process_zone": "炉身",
        "zone_segment": "上部",
        "abbr": "身上",
        "source_zone_raw": "炉身中部",
    },
}


UNIT_DEFINITIONS: dict[str, dict[str, Any]] = {
    "temperature_c": {
        "quantity": "temperature",
        "normalized_unit": "°C",
        "display_unit": "℃",
        "conversion": "identity",
        "authority": "GL02受控单位契约",
    },
    "pressure_kpa": {
        "quantity": "pressure",
        "normalized_unit": "kPa",
        "display_unit": "kPa",
        "conversion": "identity",
        "authority": "GL02受控单位契约",
    },
    "blast_flow_nm3_min": {
        "quantity": "volumetric_flow",
        "normalized_unit": "Nm³/min",
        "display_unit": "Nm³/min",
        "conversion": "identity",
        "authority": "GL02受控单位契约",
    },
    "oxygen_flow_nm3_h": {
        "quantity": "volumetric_flow",
        "normalized_unit": "Nm³/h",
        "display_unit": "Nm³/h",
        "conversion": "identity",
        "authority": "GL02受控单位契约",
    },
    "length_m": {
        "quantity": "length",
        "normalized_unit": "m",
        "display_unit": "m",
        "conversion": "identity",
        "authority": "GL02受控单位契约",
    },
    "mass_flow_t_h": {
        "quantity": "mass_flow",
        "normalized_unit": "t/h",
        "display_unit": "t/h",
        "conversion": "identity",
        "authority": "GL02受控单位契约",
    },
    "percent": {
        "quantity": "percentage",
        "normalized_unit": "%",
        "display_unit": "%",
        "conversion": "identity",
        "authority": "GL02受控单位契约",
    },
    "ratio_to_percent": {
        "quantity": "ratio",
        "normalized_unit": "1",
        "display_unit": "%",
        "conversion": "display_value = source_value * 100",
        "authority": "GL02受控单位契约",
    },
    "dimensionless": {
        "quantity": "dimensionless",
        "normalized_unit": "1",
        "display_unit": "",
        "conversion": "identity",
        "authority": "GL02受控单位契约",
    },
}


EXACT_SEMANTICS: dict[str, dict[str, Any]] = {
    "DP_lower": {"short": "下部压差", "name": "高炉下部压差", "zone": "炉腹至炉身下部"},
    "DP_total": {"short": "全炉压差", "name": "高炉总压差", "zone": "全炉"},
    "DP_upper": {"short": "上部压差", "name": "高炉上部压差", "zone": "炉身中上部至炉顶"},
    "GasUtil": {"short": "煤气利用", "name": "煤气利用率", "zone": "炉顶煤气系统"},
    "L": {"short": "总料线", "name": "高炉总料线", "zone": "炉喉"},
    "L_north": {"short": "北料线", "name": "炉喉北侧料线", "zone": "炉喉", "orientation": "北"},
    "L_south": {"short": "南料线", "name": "炉喉南侧料线", "zone": "炉喉", "orientation": "南"},
    "O2_rate": {"short": "富氧率", "name": "送风富氧率", "zone": "风口送风系统"},
    "P_blast": {"short": "热风压", "name": "热风压力", "zone": "风口送风系统"},
    "P_blast_cold": {"short": "冷风压", "name": "冷风压力", "zone": "冷风送风系统"},
    "P_top": {"short": "炉顶压", "name": "炉顶压力", "zone": "炉顶"},
    "PCI_rate": {"short": "喷煤率", "name": "喷煤率", "zone": "风口喷煤系统"},
    "PCI_set": {"short": "喷煤设定", "name": "喷煤设定值", "zone": "风口喷煤系统"},
    "PI": {"short": "透气指数", "name": "高炉透气性指数", "zone": "全炉"},
    "Q_blast": {"short": "鼓风量", "name": "高炉鼓风流量", "zone": "风口送风系统"},
    "Q_O2": {"short": "氧气量", "name": "富氧流量", "zone": "风口送风系统"},
    "T_blast": {"short": "热风温", "name": "热风温度", "zone": "风口送风系统"},
    "T_taphole_1": {
        "short": "南铁口温",
        "name": "南出铁口温度",
        "zone": "炉缸出铁口",
        "orientation": "南",
    },
    "T_taphole_2": {
        "short": "北铁口温",
        "name": "北出铁口温度",
        "zone": "炉缸出铁口",
        "orientation": "北",
    },
    "TFT": {"short": "理论燃温", "name": "理论燃烧温度", "zone": "风口回旋区"},
}


FORMAL_STATIC_PRESSURE: dict[str, dict[str, Any]] = {
    "P_static_20m35": {
        "short": "身下静压·20.35",
        "name": "炉身下部 20.35 米静压力",
        "zone": "炉身",
        "segment": "下部",
        "elevation_m": 20.350,
    },
    "P_static_23m49": {
        "short": "身中静压·23.49",
        "name": "炉身中部 23.49 米静压力",
        "zone": "炉身",
        "segment": "中部",
        "elevation_m": 23.488,
    },
    "P_static_28m98": {
        "short": "身上静压·28.98",
        "name": "炉身上部 28.98 米静压力",
        "zone": "炉身",
        "segment": "上部",
        "elevation_m": 28.976,
    },
}


def parse_args() -> argparse.Namespace:
    workspace = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default=os.getenv("GL02_PGHOST", "10.30.220.12"))
    parser.add_argument("--port", type=int, default=int(os.getenv("GL02_PGPORT", "5432")))
    parser.add_argument("--database", default=os.getenv("GL02_PGDATABASE", "bf_trend"))
    parser.add_argument("--user", default=os.getenv("GL02_PGUSER"))
    parser.add_argument("--password", default=os.getenv("GL02_PGPASSWORD"))
    parser.add_argument(
        "--source-manifest",
        type=Path,
        default=workspace
        / "PT"
        / "高炉3D模型"
        / "模型资产库"
        / "09_高炉本体133点Billboard"
        / "sensor_billboards.v1.json",
    )
    parser.add_argument(
        "--static-pressure-reference",
        type=Path,
        default=workspace
        / "高炉前端数据"
        / "智能助手"
        / "mcp"
        / "gl02_static_pressure_points.json",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=workspace / "PT" / "高炉3D模型" / "docs",
    )
    return parser.parse_args()


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def fetch_registry(args: argparse.Namespace) -> list[dict[str, Any]]:
    if not args.user or not args.password:
        raise RuntimeError("需要通过 GL02_PGUSER/GL02_PGPASSWORD 提供只读数据库凭据")
    query = """
        SELECT variable_name, chinese_name, branch, short_name, tag_long_name,
               description, status_usage, is_derived, is_enabled, updated_at
        FROM bf_sensor.sensor_registry
        WHERE is_enabled IS TRUE
          AND COALESCE(is_derived, FALSE) IS FALSE
        ORDER BY variable_name
    """
    with psycopg.connect(
        host=args.host,
        port=args.port,
        dbname=args.database,
        user=args.user,
        password=args.password,
        connect_timeout=8,
        row_factory=dict_row,
    ) as connection:
        with connection.cursor() as cursor:
            cursor.execute(query)
            rows = cursor.fetchall()
    for row in rows:
        if row.get("updated_at") is not None:
            row["updated_at"] = row["updated_at"].isoformat()
    return rows


def runtime_to_canonical(runtime_id: str) -> str:
    pressure = re.fullmatch(
        r"GL02_INT30_PRESSURE_(LOWER|MIDDLE|UPPER)_([A-F])", runtime_id
    )
    if pressure:
        return f"P_static_{pressure.group(1).lower()}_{pressure.group(2)}"
    if runtime_id.startswith("SENSOR_"):
        return runtime_id.removeprefix("SENSOR_")
    raise ValueError(f"无法从 Billboard ID 映射数据库变量：{runtime_id}")


def unit_key(variable_name: str) -> str:
    if variable_name == "GasUtil":
        return "ratio_to_percent"
    if variable_name == "PI":
        return "dimensionless"
    if variable_name == "O2_rate":
        return "percent"
    if variable_name in {"PCI_rate", "PCI_set"}:
        return "mass_flow_t_h"
    if variable_name == "Q_blast":
        return "blast_flow_nm3_min"
    if variable_name == "Q_O2":
        return "oxygen_flow_nm3_h"
    if variable_name in {"L", "L_north", "L_south"}:
        return "length_m"
    if variable_name.startswith(("P_", "DP_")):
        return "pressure_kpa"
    if variable_name.startswith("T_") or variable_name == "TFT":
        return "temperature_c"
    raise ValueError(f"缺少单位映射：{variable_name}")


def semantic_for(variable_name: str) -> dict[str, Any]:
    body = re.fullmatch(r"T_body_L(7|8|9|10|11|12|13|14|15|16)_([A-H])", variable_name)
    if body:
        layer = int(body.group(1))
        orientation = body.group(2)
        meta = LAYER_SEMANTICS[layer]
        zone_label = meta["process_zone"] + (meta["zone_segment"] or "")
        return {
            "semantic_rule": "body_temperature_layer",
            "semantic_abbreviation_cn": f"{meta['abbr']}温·L{layer}{orientation}",
            "semantic_name_cn": f"{zone_label} L{layer} 层 {orientation} 方位温度",
            "process_zone": meta["process_zone"],
            "zone_segment": meta["zone_segment"],
            "layer_id": f"L{layer}",
            "elevation_m": meta["elevation_m"],
            "orientation": orientation,
            "orientation_authority": "relative_position_only",
        }

    static_pressure = re.fullmatch(r"P_static_(lower|middle|upper)_([A-F])", variable_name)
    if static_pressure:
        level = static_pressure.group(1)
        orientation = static_pressure.group(2)
        meta = STATIC_PRESSURE_SEMANTICS[level]
        zone_label = meta["process_zone"] + meta["zone_segment"]
        return {
            "semantic_rule": "static_pressure_18_standardized_height",
            "semantic_abbreviation_cn": f"{meta['abbr']}静压·{orientation}",
            "semantic_name_cn": f"{zone_label} {meta['elevation_m']:.3f} 米 {orientation} 点静压力",
            "process_zone": meta["process_zone"],
            "zone_segment": meta["zone_segment"],
            "layer_id": f"SP_{level.upper()}",
            "elevation_m": meta["elevation_m"],
            "orientation": orientation,
            "orientation_authority": "relative_position_only",
            "source_zone_raw": meta["source_zone_raw"],
            "semantic_resolution": (
                "显示与3D建模采用受控高度契约的炉身下/中/上；"
                "数据库原始 description 保留，不覆盖"
            ),
        }

    if variable_name in FORMAL_STATIC_PRESSURE:
        meta = FORMAL_STATIC_PRESSURE[variable_name]
        return {
            "semantic_rule": "formal_static_pressure_height",
            "semantic_abbreviation_cn": meta["short"],
            "semantic_name_cn": meta["name"],
            "process_zone": meta["zone"],
            "zone_segment": meta["segment"],
            "layer_id": None,
            "elevation_m": meta["elevation_m"],
            "orientation": None,
        }

    top_gas = re.fullmatch(r"P_top_gas_([A-D])", variable_name)
    if top_gas:
        orientation = top_gas.group(1)
        return {
            "semantic_rule": "top_gas_pressure",
            "semantic_abbreviation_cn": f"顶煤压·{orientation}",
            "semantic_name_cn": f"炉顶煤气压力 {orientation}",
            "process_zone": "炉顶",
            "zone_segment": None,
            "layer_id": None,
            "elevation_m": None,
            "orientation": orientation,
            "orientation_authority": "relative_position_only",
        }

    throat = re.fullmatch(r"T_throat_([A-D])", variable_name)
    if throat:
        orientation = throat.group(1)
        return {
            "semantic_rule": "throat_temperature",
            "semantic_abbreviation_cn": f"喉温·{orientation}",
            "semantic_name_cn": f"炉喉 {orientation} 方位温度",
            "process_zone": "炉喉",
            "zone_segment": None,
            "layer_id": None,
            "elevation_m": None,
            "orientation": orientation,
            "orientation_authority": "relative_position_only",
        }

    top_temperature = re.fullmatch(r"T_top_([A-D])", variable_name)
    if top_temperature:
        orientation = top_temperature.group(1)
        return {
            "semantic_rule": "top_temperature",
            "semantic_abbreviation_cn": f"顶温·{orientation}",
            "semantic_name_cn": f"炉顶 {orientation} 方位温度",
            "process_zone": "炉顶",
            "zone_segment": None,
            "layer_id": None,
            "elevation_m": None,
            "orientation": orientation,
            "orientation_authority": "relative_position_only",
        }

    if variable_name in EXACT_SEMANTICS:
        meta = EXACT_SEMANTICS[variable_name]
        return {
            "semantic_rule": "exact_process_semantic",
            "semantic_abbreviation_cn": meta["short"],
            "semantic_name_cn": meta["name"],
            "process_zone": meta["zone"],
            "zone_segment": None,
            "layer_id": None,
            "elevation_m": None,
            "orientation": meta.get("orientation"),
        }

    raise ValueError(f"缺少工艺语义映射：{variable_name}")


def markdown_table(points: list[dict[str, Any]]) -> str:
    lines = [
        "# GL02 高炉 3D 传感器点位清单",
        "",
        "> 本清单由 `bf_sensor.sensor_registry` 的启用、非派生物理点只读生成。"
        "数据库字段负责点位身份与原始中文描述；单位和 3D 工艺语义分别由独立受控文件维护。",
        "",
        "## 权威文件",
        "",
        "- 点位机器清单：`GL02传感器点位清单.v1.json`",
        "- 单位映射：`GL02传感器单位映射.v1.json`",
        "- 工艺语义映射：`GL02传感器语义映射.v1.json`",
        "- 原综合契约：`GL02数据映射附件.md`",
        "",
        "## 炉体温度分层",
        "",
        "| 层号 | 标高 m | 标准工艺部位 | Billboard 中文前缀 |",
        "|---|---:|---|---|",
    ]
    for layer, meta in LAYER_SEMANTICS.items():
        zone = meta["process_zone"] + (meta["zone_segment"] or "")
        lines.append(f"| L{layer} | {meta['elevation_m']:.3f} | {zone} | {meta['abbr']}温 |")

    lines.extend(
        [
            "",
            "## 18 个静压力点的统一语义",
            "",
            "| 数据库组 | 标高 m | 统一显示/建模语义 | 数据库原描述中的部位 | 方位 |",
            "|---|---:|---|---|---|",
        ]
    )
    for level, meta in STATIC_PRESSURE_SEMANTICS.items():
        zone = meta["process_zone"] + meta["zone_segment"]
        lines.append(
            f"| `P_static_{level}_A-F` | {meta['elevation_m']:.3f} | "
            f"{zone} | {meta['source_zone_raw']} | A-F（相对方位） |"
        )
    lines.extend(
        [
            "",
            "说明：数据库的 `description` 原文不会被改写；3D 标签统一采用"
            " 20.350/23.488/28.976 m 对应炉身下部/中部/上部的受控显示语义。",
            "",
            "## 133 个物理点",
            "",
            "| # | 数据绑定 ID | Billboard ID | 中文缩写 | 工艺部位 | 层/标高 | 单位 | 数据库中文名 |",
            "|---:|---|---|---|---|---|---|---|",
        ]
    )
    for index, point in enumerate(points, start=1):
        semantic = point["semantic"]
        unit = point["unit"]
        zone = semantic["process_zone"] + (semantic.get("zone_segment") or "")
        level = semantic.get("layer_id") or ""
        if semantic.get("elevation_m") is not None:
            level = f"{level} / {semantic['elevation_m']:.3f}m" if level else f"{semantic['elevation_m']:.3f}m"
        db_name = (point["database"].get("chinese_name") or "").replace("|", "／")
        lines.append(
            f"| {index} | `{point['canonical_id']}` | `{point['runtime_id']}` | "
            f"{semantic['semantic_abbreviation_cn']} | {zone} | {level or '—'} | "
            f"{unit['display_unit'] or '无量纲'} | {db_name or '—'} |"
        )
    lines.extend(
        [
            "",
            "## 使用边界",
            "",
            "- A-H、A-F 为相对方位编码，不得直接解释为厂区绝对方位角。",
            "- `T_taphole_1/2` 按当前受控合同分别显示为南/北出铁口。",
            "- 数据库当前无单位字段，单位以独立单位映射文件为准；变更单位时必须同步版本和验证报告。",
            "- `GasUtil` 数据内部保持 0-1 比例，界面显示时乘以 100 并使用 `%`。",
            "",
        ]
    )
    return "\n".join(lines)


def main() -> None:
    args = parse_args()
    source_manifest = read_json(args.source_manifest)
    pressure_reference = read_json(args.static_pressure_reference)
    registry_rows = fetch_registry(args)

    if len(registry_rows) != 133:
        raise RuntimeError(f"数据库启用非派生物理点应为 133，实际为 {len(registry_rows)}")

    registry_by_id = {row["variable_name"]: row for row in registry_rows}
    if len(registry_by_id) != 133:
        raise RuntimeError("数据库 variable_name 不唯一")

    runtime_by_canonical: dict[str, dict[str, Any]] = {}
    for point in source_manifest["points"]:
        canonical_id = runtime_to_canonical(point["id"])
        if canonical_id in runtime_by_canonical:
            raise RuntimeError(f"Billboard canonical ID 重复：{canonical_id}")
        runtime_by_canonical[canonical_id] = point

    registry_ids = set(registry_by_id)
    billboard_ids = set(runtime_by_canonical)
    if registry_ids != billboard_ids:
        missing_in_billboard = sorted(registry_ids - billboard_ids)
        missing_in_registry = sorted(billboard_ids - registry_ids)
        raise RuntimeError(
            "数据库与 Billboard 点位集合不一致："
            f"missing_in_billboard={missing_in_billboard}, "
            f"missing_in_registry={missing_in_registry}"
        )

    pressure_reference_by_id = {
        item["variable_name"]: item for item in pressure_reference["variables"]
    }
    generated_at = datetime.now(timezone.utc).isoformat()
    points: list[dict[str, Any]] = []
    unit_points: list[dict[str, Any]] = []
    semantic_points: list[dict[str, Any]] = []

    for canonical_id in sorted(registry_ids):
        database = registry_by_id[canonical_id]
        runtime = runtime_by_canonical[canonical_id]
        semantic = semantic_for(canonical_id)
        resolved_unit_key = unit_key(canonical_id)
        unit = UNIT_DEFINITIONS[resolved_unit_key]
        source_kind = runtime["source_kind"]

        unit_status = "controlled_mapping_database_has_no_unit_column"
        if source_kind == "static_pressure_18":
            unit_status = "configured_kpa_source_metadata_blank_unconfirmed"
            if canonical_id not in pressure_reference_by_id:
                raise RuntimeError(f"18 点静压力参考清单缺少：{canonical_id}")

        database_payload = {
            "variable_name": database["variable_name"],
            "chinese_name": database["chinese_name"],
            "branch": database["branch"],
            "short_name": database["short_name"],
            "tag_long_name": database["tag_long_name"],
            "description": database["description"],
            "status_usage": database["status_usage"],
            "is_derived": database["is_derived"],
            "is_enabled": database["is_enabled"],
            "updated_at": database["updated_at"],
        }
        unit_payload = {
            "unit_key": resolved_unit_key,
            "normalized_unit": unit["normalized_unit"],
            "display_unit": unit["display_unit"],
            "conversion": unit["conversion"],
            "unit_status": unit_status,
        }
        point_payload = {
            "canonical_id": canonical_id,
            "runtime_id": runtime["id"],
            "data_binding_key": canonical_id,
            "source_kind": source_kind,
            "category": runtime["category"],
            "database": database_payload,
            "semantic": semantic,
            "unit": unit_payload,
            "model": {
                "position": runtime["position"],
                "coordinate_authority": runtime["coordinate_authority"],
                "body_model": source_manifest["body_model"],
            },
        }
        if canonical_id in pressure_reference_by_id:
            reference = pressure_reference_by_id[canonical_id]
            point_payload["static_pressure_reference"] = {
                "height_m": reference["height_m"],
                "position": reference["position"],
                "source_branch": reference["source_branch"],
                "source_description_raw": reference["description"],
                "unit_from_reference": reference["unit"],
                "confidence": reference["confidence"],
            }
        points.append(point_payload)
        unit_points.append(
            {
                "canonical_id": canonical_id,
                "unit_key": resolved_unit_key,
                **unit_payload,
            }
        )
        semantic_points.append(
            {
                "canonical_id": canonical_id,
                "runtime_id": runtime["id"],
                **semantic,
                "database_chinese_name_raw": database["chinese_name"],
                "database_description_raw": database["description"],
            }
        )

    registry_digest_payload = json.dumps(
        registry_rows, ensure_ascii=False, sort_keys=True, default=str
    ).encode("utf-8")
    registry_digest = hashlib.sha256(registry_digest_payload).hexdigest()
    counts_by_zone = dict(
        sorted(Counter(point["semantic"]["process_zone"] for point in points).items())
    )
    counts_by_source_kind = dict(
        sorted(Counter(point["source_kind"] for point in points).items())
    )

    catalog = {
        "schema": "gl02.bf3d.sensor_point_catalog.v1",
        "generated_at": generated_at,
        "authority": {
            "point_identity": "bf_sensor.sensor_registry",
            "point_query": "is_enabled=true AND coalesce(is_derived,false)=false",
            "database_unit_column_present": False,
            "unit_mapping": "GL02传感器单位映射.v1.json",
            "semantic_mapping": "GL02传感器语义映射.v1.json",
            "model_coordinate_source": str(args.source_manifest),
            "registry_snapshot_sha256": registry_digest,
        },
        "counts": {
            "database_physical_points": len(registry_rows),
            "formal_sensor_115": counts_by_source_kind.get("formal_sensor_115", 0),
            "static_pressure_18": counts_by_source_kind.get("static_pressure_18", 0),
            "total": len(points),
        },
        "counts_by_process_zone": counts_by_zone,
        "points": points,
    }

    units = {
        "schema": "gl02.bf3d.sensor_unit_mapping.v1",
        "generated_at": generated_at,
        "database_fact": (
            "bf_sensor.sensor_registry 当前没有 unit 字段；本文件是显示、接口和3D标签的受控单位合同"
        ),
        "definitions": UNIT_DEFINITIONS,
        "counts": {
            "mapped_points": len(unit_points),
            "unique_unit_keys": len(set(item["unit_key"] for item in unit_points)),
        },
        "points": unit_points,
    }

    semantics = {
        "schema": "gl02.bf3d.sensor_semantic_mapping.v1",
        "generated_at": generated_at,
        "authority": {
            "raw_point_metadata": "bf_sensor.sensor_registry",
            "body_layer_contract": "GL02数据映射附件.md / L7-L16",
            "static_pressure_contract": str(args.static_pressure_reference),
            "orientation_boundary": "A-H/A-F are relative positions, not absolute plant azimuths",
        },
        "body_layer_semantics": {f"L{key}": value for key, value in LAYER_SEMANTICS.items()},
        "static_pressure_display_semantics": STATIC_PRESSURE_SEMANTICS,
        "counts": {
            "mapped_points": len(semantic_points),
            "chinese_abbreviations": sum(
                bool(re.search(r"[\u3400-\u9fff]", item["semantic_abbreviation_cn"]))
                for item in semantic_points
            ),
            "process_zones": len(counts_by_zone),
        },
        "points": semantic_points,
    }

    output_dir = args.output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    catalog_path = output_dir / "GL02传感器点位清单.v1.json"
    unit_path = output_dir / "GL02传感器单位映射.v1.json"
    semantic_path = output_dir / "GL02传感器语义映射.v1.json"
    markdown_path = output_dir / "GL02传感器点位清单.md"
    report_path = output_dir / "GL02传感器点位清单.生成报告.json"

    write_json(catalog_path, catalog)
    write_json(unit_path, units)
    write_json(semantic_path, semantics)
    markdown_path.write_text(markdown_table(points), encoding="utf-8")
    report = {
        "schema": "gl02.bf3d.sensor_catalog_build_report.v1",
        "generated_at": generated_at,
        "outputs": {
            "catalog": str(catalog_path),
            "units": str(unit_path),
            "semantics": str(semantic_path),
            "markdown": str(markdown_path),
        },
        "checks": {
            "database_count_133": len(registry_rows) == 133,
            "billboard_count_133": len(runtime_by_canonical) == 133,
            "database_billboard_ids_match": registry_ids == billboard_ids,
            "formal_sensor_count_115": counts_by_source_kind.get("formal_sensor_115") == 115,
            "static_pressure_count_18": counts_by_source_kind.get("static_pressure_18") == 18,
            "all_units_mapped": len(unit_points) == 133,
            "all_semantics_mapped": len(semantic_points) == 133,
            "all_cn_abbreviations": semantics["counts"]["chinese_abbreviations"] == 133,
        },
    }
    report["passed"] = all(report["checks"].values())
    write_json(report_path, report)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    if not report["passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
