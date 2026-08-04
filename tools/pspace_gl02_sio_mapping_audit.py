# -*- coding: utf-8 -*-
"""Audit dashboard sensor mappings against only ``\\冀南钢铁\\SIO\\GL02``.

The script is read-only against pSpace. It writes local CSV/JSON/Markdown
reports so we can review possible dashboard-to-pSpace mappings without touching
the data collection servers or the active 8092 mapping file.
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import re
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT_DIR = Path(__file__).resolve().parents[1]
TOOLS_DIR = ROOT_DIR / "tools"
sys.path.insert(0, str(TOOLS_DIR))

from pspace_8092_realtime_bridge import (  # noqa: E402
    SENSORS,
    SENSOR_BY_ID,
    find_sdk_root,
    get_tag_props,
    load_sdk,
    mapped_tags,
    query_all_tag_names,
    read_realtime,
    score_sensor,
)
from pspace_collect_gl01_5d import connect_pspace, read_pspace_config  # noqa: E402


SIO_ROOT = r"\冀南钢铁\SIO\GL02"
EQ_ROOT = r"\冀南二期\EQ\SI0\GL02"


@dataclass(frozen=True)
class ManualCandidate:
    sensor_id: str
    tags: tuple[str, ...]
    confidence: str
    note: str
    derive: str = ""


MANUAL_CANDIDATES: tuple[ManualCandidate, ...] = (
    ManualCandidate("L", (rf"{SIO_ROOT}\LD\SIO_GL02_LD_T0046",), "high", "高炉炉体料位雷达探尺，SIO 下最直接的雷达探尺点。"),
    ManualCandidate("L_south", (), "none", "SIO 下未发现可明确区分南尺/1#探尺的点；不要用 EQ 的 1#探尺料线混入。"),
    ManualCandidate("L_north", (), "none", "SIO 下未发现可明确区分北尺/2#探尺的点；不要用 EQ 的 2#探尺料线混入。"),
    ManualCandidate("Hopper_weight", (), "none", "SIO 下未发现可靠的炉顶料罐实际重量；喷吹罐重量不是炉顶罐重，不建议替代。"),
    ManualCandidate(
        "Hopper_weight_set",
        (
            rf"{SIO_ROOT}\LD\SIO_GL02_LD_T0115",
            rf"{SIO_ROOT}\LD\SIO_GL02_LD_T0116",
            rf"{SIO_ROOT}\LD\SIO_GL02_LD_T0117",
            rf"{SIO_ROOT}\LD\SIO_GL02_LD_T0119",
            rf"{SIO_ROOT}\LD\SIO_GL02_LD_T0120",
            rf"{SIO_ROOT}\LD\SIO_GL02_LD_T0121",
            rf"{SIO_ROOT}\LD\SIO_GL02_LD_T0122",
            rf"{SIO_ROOT}\LD\SIO_GL02_LD_T0123",
            rf"{SIO_ROOT}\LD\SIO_GL02_LD_T0124",
            rf"{SIO_ROOT}\LD\SIO_GL02_LD_T0125",
            rf"{SIO_ROOT}\LD\SIO_GL02_LD_T0126",
        ),
        "medium",
        "1-11号布料重量设定；可求和作为罐重设定代理值，但它不是实际罐重。",
        "sum",
    ),
    ManualCandidate("P_top", (rf"{SIO_ROOT}\LD\SIO_GL02_LD_T0034",), "high", "顶压平均，适合作为页面“顶压”。"),
    ManualCandidate("P_top_gas_A", (rf"{SIO_ROOT}\LD\SIO_GL02_LD_T0067",), "high", "上升管煤气压力A。"),
    ManualCandidate("P_top_gas_B", (rf"{SIO_ROOT}\LD\SIO_GL02_LD_T0068",), "high", "上升管煤气压力B。"),
    ManualCandidate("P_top_gas_C", (rf"{SIO_ROOT}\LD\SIO_GL02_LD_T0069",), "high", "上升管煤气压力C。"),
    ManualCandidate("P_top_gas_D", (rf"{SIO_ROOT}\LD\SIO_GL02_LD_T0070",), "high", "上升管煤气压力D。"),
    ManualCandidate(
        "T_top",
        (
            rf"{SIO_ROOT}\LD\SIO_GL02_LD_T0040",
            rf"{SIO_ROOT}\LD\SIO_GL02_LD_T0043",
            rf"{SIO_ROOT}\LD\SIO_GL02_LD_T0064",
            rf"{SIO_ROOT}\LD\SIO_GL02_LD_T0072",
        ),
        "medium",
        "四个点描述均为“上升管煤气温度”，可求平均作为综合顶温；单点没有 A/B/C/D 标签，方向需现场确认。",
        "avg",
    ),
    ManualCandidate("T_top_A", (rf"{SIO_ROOT}\LD\SIO_GL02_LD_T0040",), "low", "仅按四个上升管煤气温度点的出现顺序暂配；描述不含 A。"),
    ManualCandidate("T_top_B", (rf"{SIO_ROOT}\LD\SIO_GL02_LD_T0043",), "low", "仅按四个上升管煤气温度点的出现顺序暂配；描述不含 B。"),
    ManualCandidate("T_top_C", (rf"{SIO_ROOT}\LD\SIO_GL02_LD_T0064",), "low", "仅按四个上升管煤气温度点的出现顺序暂配；描述不含 C。"),
    ManualCandidate("T_top_D", (rf"{SIO_ROOT}\LD\SIO_GL02_LD_T0072",), "low", "仅按四个上升管煤气温度点的出现顺序暂配；描述不含 D。"),
    ManualCandidate("P_blast_cold", (rf"{SIO_ROOT}\RF\SIO_GL02_RF_T0047",), "high", "冷风管道压力，适合作为冷风压力。"),
    ManualCandidate("P_blast", (rf"{SIO_ROOT}\BT\SIO_GL02_BT_T0149",), "high", "高炉本体热风压力，适合作为热风压力。"),
    ManualCandidate("T_blast", (rf"{SIO_ROOT}\BT\SIO_GL02_BT_T0006",), "high", "热风温度，明确对应风温。"),
    ManualCandidate("Q_blast", (rf"{SIO_ROOT}\RF\SIO_GL02_RF_T0073",), "high", "冷风管道流量，适合作为风量；旧自动规则容易被“总管流量/水流量”干扰。"),
    ManualCandidate("PCI_rate", (rf"{SIO_ROOT}\PC\SIO_GL02_PC_T0007",), "medium", "喷煤量累积瞬时值，当前值量级接近喷煤瞬时量；需注意名称含“累积”。"),
    ManualCandidate("PCI_set", (rf"{SIO_ROOT}\PC\SIO_GL02_PC_T0001",), "medium", "一小时喷煤重量设定执行变量，适合作为喷煤设定代理。"),
    ManualCandidate("Q_O2", (rf"{SIO_ROOT}\CX\SIO_GL02_CX_T0288",), "medium", "槽下富氧流量，SIO 下找到的富氧流量候选；需确认单位和页面期望是否一致。"),
    ManualCandidate("PI", (rf"{SIO_ROOT}\BT\SIO_GL02_BT_T0101",), "high", "透气性指数，明确对应透指。"),
    ManualCandidate("GasUtil", (), "none", "SIO 下未发现可靠“煤气利用率/CO利用率”点；制粉或布袋 CO/CO2 含量不能替代炉顶煤气利用率。"),
    ManualCandidate("DP_upper", (rf"{SIO_ROOT}\BT\SIO_GL02_BT_T0135",), "high", "上部压差，明确对应。"),
    ManualCandidate("DP_lower", (rf"{SIO_ROOT}\BT\SIO_GL02_BT_T0102",), "high", "下部压差，明确对应。"),
    ManualCandidate("DP_total", (rf"{SIO_ROOT}\BT\SIO_GL02_BT_T0132",), "high", "全炉压差，明确对应；也可由上部压差+下部压差校验。"),
    ManualCandidate("T_taphole_1", (rf"{SIO_ROOT}\BT\SIO_GL02_BT_T0001",), "high", "1号出铁口温度。"),
    ManualCandidate("T_taphole_2", (rf"{SIO_ROOT}\BT\SIO_GL02_BT_T0002",), "high", "2号出铁口温度。"),
    ManualCandidate("T_taphole_3", (rf"{SIO_ROOT}\BT\SIO_GL02_BT_T0011",), "high", "3号出铁口温度。"),
)


EXTRA_ALIASES: dict[str, tuple[str, ...]] = {
    "Q_blast": ("冷风管道流量", "送风流量", "鼓风量", "入炉风量"),
    "P_blast_cold": ("冷风管道压力",),
    "P_blast": ("高炉本体热风压力",),
    "T_top": ("上升管煤气温度", "炉喉温度"),
    "T_top_A": ("上升管煤气温度", "炉喉温度A"),
    "T_top_B": ("上升管煤气温度", "炉喉温度B"),
    "T_top_C": ("上升管煤气温度", "炉喉温度C"),
    "T_top_D": ("上升管煤气温度", "炉喉温度D"),
    "P_top": ("顶压平均", "顶压"),
    "Q_O2": ("富氧流量",),
}


def normalize(value: str) -> str:
    value = value.lower().replace("＃", "#").replace("－", "-")
    return re.sub(r"[\s_（）()：:，,。/\\\-#]+", "", value)


def is_sio_tag(tag: str) -> bool:
    return tag.startswith(SIO_ROOT + "\\")


def is_eq_tag(tag: str) -> bool:
    return tag.startswith(EQ_ROOT + "\\")


def root_status(tag: str | None) -> str:
    if not tag:
        return ""
    if is_sio_tag(tag):
        return "SIO"
    if is_eq_tag(tag):
        return "EQ"
    return "OTHER"


def safe_value(values: dict[str, Any], meta: dict[str, Any], tag: str) -> dict[str, Any]:
    return {
        "value": values.get(tag),
        "timestamp": (meta.get("timestamps") or {}).get(tag, ""),
        "quality": (meta.get("qualities") or {}).get(tag, ""),
        "error": (meta.get("errors") or {}).get(tag, ""),
    }


def resolve_connection(args: argparse.Namespace) -> dict[str, str]:
    config = read_pspace_config(args.pspace_config)
    connection = {
        "server": args.pspace_server or config.get("ip") or "10.22.181.243",
        "port": str(args.pspace_port or config.get("port") or "8889"),
        "user": args.pspace_user or config.get("username") or "",
        "password": args.pspace_password or config.get("password") or "",
    }
    if not connection["user"] or not connection["password"]:
        raise SystemExit("Missing pSpace credentials. Set PSPACE_USER/PSPACE_PASSWORD or PSPACE_CONFIG.")
    return connection


def score_extra(sensor_id: str, tag: str, props: dict[str, str]) -> tuple[int, list[str]]:
    text = normalize(" ".join([tag, props.get("name", ""), props.get("description", ""), props.get("unit", "")]))
    score = 0
    matched: list[str] = []
    for alias in EXTRA_ALIASES.get(sensor_id, ()):
        key = normalize(alias)
        if key and key in text:
            score += max(5, len(key))
            matched.append(alias)
    return score, matched


def build_candidate_rows(tags: list[str], props_by_tag: dict[str, dict[str, str]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for tag in tags:
        props = props_by_tag[tag]
        for sensor in SENSORS:
            if sensor.derived_from:
                continue
            score, matched = score_sensor(sensor, tag, props)
            extra_score, extra_matched = score_extra(sensor.sensor_id, tag, props)
            score += extra_score
            matched.extend(extra_matched)
            if score >= 4 and matched:
                rows.append(
                    {
                        "sensor_id": sensor.sensor_id,
                        "display_name": sensor.display_name,
                        "unit": sensor.unit,
                        "candidate_tag": tag,
                        "candidate_name": props.get("name", ""),
                        "candidate_description": props.get("description", ""),
                        "candidate_unit": props.get("unit", ""),
                        "score": score,
                        "matched": "|".join(dict.fromkeys(matched)),
                        "candidate_source": "auto_sio_scan",
                    }
                )
    rows.sort(key=lambda row: (row["sensor_id"], -int(row["score"]), row["candidate_tag"]))
    return rows


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--sdk-root", default=os.getenv("PSPACE_SDK_ROOT"))
    parser.add_argument(
        "--pspace-config",
        default=os.getenv("PSPACE_CONFIG", str(ROOT_DIR / "ghsc" / "src" / "main" / "resources" / "application-prod.yml")),
    )
    parser.add_argument("--pspace-server", default=os.getenv("PSPACE_SERVER", "10.22.181.243"))
    parser.add_argument("--pspace-port", default=os.getenv("PSPACE_PORT", "8889"))
    parser.add_argument("--pspace-user", default=os.getenv("PSPACE_USER"))
    parser.add_argument("--pspace-password", default=os.getenv("PSPACE_PASSWORD"))
    parser.add_argument("--current-map", default=str(ROOT_DIR / "高炉前端数据" / "pspace_8092_sensor_map.json"))
    parser.add_argument("--out-dir", default=str(ROOT_DIR / "logs"))
    parser.add_argument("--top-auto", type=int, default=8)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    sdk_root = find_sdk_root(args.sdk_root)
    PsObject, T = load_sdk(sdk_root)
    connection = resolve_connection(args)
    pspace = connect_pspace(PsObject, T, connection)

    all_tags = query_all_tag_names(pspace, T)
    sio_tags = [tag for tag in all_tags if is_sio_tag(tag)]
    props_by_tag = {tag: get_tag_props(pspace, T, tag) for tag in sio_tags}
    auto_candidates = build_candidate_rows(sio_tags, props_by_tag)

    current_map_path = Path(args.current_map)
    current_map = json.loads(current_map_path.read_text(encoding="utf-8")) if current_map_path.exists() else {"sensors": {}}
    current_tags = mapped_tags(current_map)

    manual_by_id = {item.sensor_id: item for item in MANUAL_CANDIDATES}
    read_tags: list[str] = []
    for item in MANUAL_CANDIDATES:
        read_tags.extend(item.tags)
    for row in auto_candidates[:200]:
        read_tags.append(row["candidate_tag"])
    read_tags = list(dict.fromkeys(tag for tag in read_tags if tag))
    values, meta = read_realtime(pspace, T, {tag: tag for tag in read_tags})

    audit_rows: list[dict[str, Any]] = []
    proposed_sensors: dict[str, Any] = {}
    for sensor in SENSORS:
        item = manual_by_id.get(sensor.sensor_id)
        current_tag = current_tags.get(sensor.sensor_id, "")
        current_root = root_status(current_tag)
        current_item = (current_map.get("sensors") or {}).get(sensor.sensor_id, {})
        current_desc = current_item.get("description", "") if isinstance(current_item, dict) else ""

        auto_for_sensor = [row for row in auto_candidates if row["sensor_id"] == sensor.sensor_id][: args.top_auto]
        manual_tags = list(item.tags) if item else []
        recommended = manual_tags[0] if manual_tags else ""
        recommended_props = props_by_tag.get(recommended, {}) if recommended else {}
        value_info = safe_value(values, meta, recommended) if recommended else {"value": "", "timestamp": "", "quality": "", "error": ""}
        confidence = item.confidence if item else ("candidate" if auto_for_sensor else "none")
        note = item.note if item else ("仅自动候选，需要人工确认。" if auto_for_sensor else "SIO 下未找到候选。")
        derive = item.derive if item else ""

        if item and item.tags and item.derive:
            if sensor.sensor_id == "Hopper_weight_set":
                derived_ids: list[str] = []
                for index, tag in enumerate(item.tags, 1):
                    child_id = f"Hopper_weight_set_{index:02d}"
                    derived_ids.append(child_id)
                    child_props = props_by_tag.get(tag, {})
                    proposed_sensors[child_id] = {
                        "tag": tag,
                        "description": child_props.get("description", ""),
                        "name": child_props.get("name", ""),
                        "unit": child_props.get("unit", ""),
                        "source": "sio_gl02_audit_proposed",
                        "confidence": "medium",
                        "note": "布料重量设定子项，用于求和生成罐重设定代理值。",
                    }
                proposed_sensors[sensor.sensor_id] = {
                    "derived_from": derived_ids,
                    "derive": item.derive,
                    "description": note,
                    "source": "sio_gl02_audit_proposed",
                }
            else:
                derived_from = list(sensor.derived_from) if sensor.derived_from else list(item.tags)
                proposed_sensors[sensor.sensor_id] = {
                    "derived_from": derived_from,
                    "derive": item.derive,
                    "description": note,
                    "source": "sio_gl02_audit_proposed",
                }
        elif recommended:
            proposed_sensors[sensor.sensor_id] = {
                "tag": recommended,
                "description": recommended_props.get("description", ""),
                "name": recommended_props.get("name", ""),
                "unit": recommended_props.get("unit", ""),
                "source": "sio_gl02_audit_proposed",
                "confidence": confidence,
                "note": note,
            }

        audit_rows.append(
            {
                "sensor_id": sensor.sensor_id,
                "display_name": sensor.display_name,
                "unit": sensor.unit,
                "current_root": current_root,
                "current_tag": current_tag,
                "current_description": current_desc,
                "recommended_tag": recommended,
                "recommended_name": recommended_props.get("name", ""),
                "recommended_description": recommended_props.get("description", ""),
                "recommended_unit": recommended_props.get("unit", ""),
                "confidence": confidence,
                "derive": derive,
                "value": value_info.get("value", ""),
                "timestamp": value_info.get("timestamp", ""),
                "quality": value_info.get("quality", ""),
                "note": note,
                "auto_candidates": " || ".join(
                    f"{row['candidate_tag']} [{row['candidate_description']}; score={row['score']}; match={row['matched']}]"
                    for row in auto_for_sensor
                ),
            }
        )

    candidate_csv = out_dir / f"gl02_sio_only_candidates_{stamp}.csv"
    with candidate_csv.open("w", newline="", encoding="utf-8-sig") as handle:
        fieldnames = [
            "sensor_id",
            "display_name",
            "unit",
            "candidate_tag",
            "candidate_name",
            "candidate_description",
            "candidate_unit",
            "score",
            "matched",
            "candidate_source",
        ]
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(auto_candidates)

    audit_csv = out_dir / f"gl02_sio_mapping_audit_{stamp}.csv"
    with audit_csv.open("w", newline="", encoding="utf-8-sig") as handle:
        fieldnames = list(audit_rows[0].keys()) if audit_rows else []
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(audit_rows)

    proposed_map = {
        "version": 1,
        "scope": SIO_ROOT,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "note": "Proposed SIO-only mapping. Review low/medium confidence rows before replacing the active map.",
        "sensors": proposed_sensors,
    }
    proposed_json = out_dir / f"pspace_8092_sensor_map_sio_gl02_proposed_{stamp}.json"
    proposed_json.write_text(json.dumps(proposed_map, ensure_ascii=False, indent=2), encoding="utf-8")

    report_md = out_dir / f"gl02_sio_mapping_audit_{stamp}.md"
    eq_count = sum(1 for row in audit_rows if row["current_root"] == "EQ")
    sio_current_count = sum(1 for row in audit_rows if row["current_root"] == "SIO")
    high_count = sum(1 for row in audit_rows if row["confidence"] == "high")
    medium_count = sum(1 for row in audit_rows if row["confidence"] == "medium")
    low_count = sum(1 for row in audit_rows if row["confidence"] == "low")
    none_count = sum(1 for row in audit_rows if row["confidence"] == "none")

    lines: list[str] = [
        "# GL02 SIO 测点映射审查",
        "",
        f"生成时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        f"pSpace 连接：{connection['server']}:{connection['port']}（只读）",
        f"固定根节点：`{SIO_ROOT}`",
        "",
        "## 结论摘要",
        "",
        f"- 当前 active map 中仍有 {eq_count} 个页面变量直接指向 `{EQ_ROOT}`。",
        f"- 当前 active map 中已有 {sio_current_count} 个页面变量指向 `{SIO_ROOT}`。",
        f"- 本次 SIO-only 建议映射：高置信 {high_count} 个，中置信 {medium_count} 个，低置信 {low_count} 个，未找到可靠候选 {none_count} 个。",
        "- 低置信的顶温 A-D 只按四个“上升管煤气温度”点暂配，描述没有 A/B/C/D，界面展示前应现场确认方向。",
        "- 未找到可靠候选的变量不要从 EQ 或无关 SIO 点自动补齐，避免把制粉、喷吹、铁水罐或水系统变量误当作炉顶/炉况变量。",
        "",
        "## 页面变量到 SIO GL02 的建议对应",
        "",
        "| 页面变量 | 显示名 | 当前根 | 建议 SIO 测点 | 描述 | 置信度 | 当前值 | 备注 |",
        "|---|---|---:|---|---|---|---:|---|",
    ]
    for row in audit_rows:
        value = row["value"]
        if isinstance(value, float):
            value_text = f"{value:.4g}"
        else:
            value_text = "" if value in (None, "") else str(value)
        tag_text = f"`{row['recommended_tag']}`" if row["recommended_tag"] else ""
        lines.append(
            "| "
            + " | ".join(
                [
                    f"`{row['sensor_id']}`",
                    row["display_name"],
                    row["current_root"] or "",
                    tag_text,
                    (row["recommended_description"] or "").replace("|", "/"),
                    row["confidence"],
                    value_text,
                    row["note"].replace("|", "/"),
                ]
            )
            + " |"
        )
    lines.extend(
        [
            "",
            "## 输出文件",
            "",
            f"- 审查总表：`{audit_csv}`",
            f"- 自动候选：`{candidate_csv}`",
            f"- 建议映射 JSON：`{proposed_json}`",
        ]
    )
    report_md.write_text("\n".join(lines) + "\n", encoding="utf-8")

    summary_json = out_dir / f"gl02_sio_mapping_audit_{stamp}.json"
    summary_json.write_text(
        json.dumps(
            {
                "server": connection["server"],
                "port": connection["port"],
                "scope": SIO_ROOT,
                "sio_tag_count": len(sio_tags),
                "current_eq_count": eq_count,
                "current_sio_count": sio_current_count,
                "confidence_counts": {"high": high_count, "medium": medium_count, "low": low_count, "none": none_count},
                "audit_csv": str(audit_csv),
                "candidate_csv": str(candidate_csv),
                "proposed_json": str(proposed_json),
                "report_md": str(report_md),
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    print(json.dumps(json.loads(summary_json.read_text(encoding="utf-8")), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
