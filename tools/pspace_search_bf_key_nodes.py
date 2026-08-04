# -*- coding: utf-8 -*-
"""Search pSpace blast-furnace key signal nodes and write a compact report."""

from __future__ import annotations

import argparse
import csv
import json
import os
import re
import sys
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any


ROOT_DIR = Path(__file__).resolve().parents[1]
TOOLS_DIR = ROOT_DIR / "tools"
sys.path.insert(0, str(TOOLS_DIR))

from pspace_collect_gl01_5d import (  # noqa: E402
    connect_pspace,
    find_sdk_root,
    get_tag_props,
    load_sdk,
    numeric_items,
    query_all_tag_names,
    read_pspace_config,
)
from pspace_8092_realtime_bridge import read_realtime  # noqa: E402


CATEGORY_RULES: dict[str, dict[str, tuple[str, ...]]] = {
    "顶温/综合顶温": {
        "include": ("顶温", "综合顶温", "炉顶温度", "炉顶煤气温度", "炉喉温度", "顶温平均值", "选择的炉顶温度", "TI433001"),
        "exclude": ("拱顶温度", "罐顶温度", "除尘"),
    },
    "上升管煤气温度": {
        "include": ("上升管煤气温度",),
        "exclude": (),
    },
    "鼓风量/风量": {
        "include": ("鼓风量", "风量", "送风流量", "冷风管道流量", "冷风总管流量", "热风总管流量", "轴流压缩机送风流量", "FE425001", "HS_FE425001"),
        "exclude": ("累计", "阀位", "开度", "调节阀", "水流量", "煤气流量", "氮气流量", "压缩空气流量"),
    },
    "鼓风压力/热风压力": {
        "include": ("鼓风压力", "热风压力", "风压", "送风压力", "冷风压力", "冷风总管压力", "热风总管压力", "冷风管道压力", "PT425002"),
        "exclude": ("差压", "压差", "除尘", "煤气", "氮气", "水压"),
    },
    "风温": {
        "include": ("风温", "热风温度", "送风温度", "热风总管温度", "TE425001"),
        "exclude": ("炉顶", "炉喉", "拱顶", "煤气", "水温", "轴承"),
    },
    "煤气利用率": {
        "include": ("煤气利用率", "煤气利用", "CO利用率", "CO2利用率", "利用率", "MQLY"),
        "exclude": ("状态", "报警", "阀", "除尘"),
    },
    "喷煤量": {
        "include": ("喷煤量", "喷吹量", "煤粉喷吹量", "给煤量", "瞬时煤比", "煤比"),
        "exclude": ("累计", "氮气", "压力", "温度", "罐重"),
    },
    "顶压": {
        "include": ("顶压", "炉顶压力", "炉顶煤气压力"),
        "exclude": ("压差", "差压", "除尘", "布袋", "报警"),
    },
    "压差": {
        "include": ("压差", "差压"),
        "exclude": ("流量差压", "孔板", "除尘", "阀"),
    },
    "透气性指数": {
        "include": ("透气性", "透气性指数"),
        "exclude": ("报警", "状态"),
    },
    "探尺/料面": {
        "include": ("探尺", "雷达探尺", "料面", "料线", "料位", "料面深度", "料面距离", "料位深度", "料位距离"),
        "exclude": ("报警", "状态", "故障", "到位", "允许"),
    },
}


FIELDNAMES = [
    "category",
    "root_node",
    "subsystem",
    "tag",
    "name",
    "description",
    "unit",
    "matched",
    "value",
    "timestamp",
    "quality",
    "error",
]


def normalize(value: str) -> str:
    value = value.lower().replace("＃", "#")
    return re.sub(r"[\s_（）()：:，,。/\\\-#]+", "", value)


def path_parts(tag: str) -> list[str]:
    return [part for part in tag.split("\\") if part]


def is_leaf_like(tag: str) -> bool:
    parts = path_parts(tag)
    if len(parts) < 3:
        return False
    leaf = parts[-1]
    return bool(re.search(r"(?:^|_)T\d{3,}$", leaf, flags=re.IGNORECASE))


def is_furnace_part(part: str) -> bool:
    return bool(re.fullmatch(r"(?:GL|ZL)\d{2}", part, flags=re.IGNORECASE)) or "高炉" in part


def root_node_for(tag: str) -> str:
    parts = path_parts(tag)
    for index, part in enumerate(parts):
        if is_furnace_part(part):
            return "\\" + "\\".join(parts[: index + 1])
    for index, part in enumerate(parts):
        if "炼铁" in part:
            return "\\" + "\\".join(parts[: index + 1])
    if len(parts) >= 3:
        return "\\" + "\\".join(parts[:3])
    return "\\" + "\\".join(parts)


def subsystem_for(tag: str, root_node: str) -> str:
    root_parts = path_parts(root_node)
    parts = path_parts(tag)
    if len(parts) > len(root_parts):
        return parts[len(root_parts)]
    return ""


def should_scan(tag: str, all_nodes: set[str]) -> bool:
    if not is_leaf_like(tag):
        return False
    parts = path_parts(tag)
    if any(is_furnace_part(part) or "炼铁" in part for part in parts):
        return True
    root = root_node_for(tag)
    return root in all_nodes


def discover_nodes(all_tags: list[str]) -> tuple[set[str], dict[str, Counter[str]]]:
    nodes: set[str] = set()
    group_counts: dict[str, Counter[str]] = defaultdict(Counter)
    for tag in all_tags:
        parts = path_parts(tag)
        for index, part in enumerate(parts):
            if is_furnace_part(part) or "炼铁" in part:
                node = "\\" + "\\".join(parts[: index + 1])
                nodes.add(node)
                if is_leaf_like(tag) and len(parts) > index + 1:
                    group_counts[node][parts[index + 1]] += 1
                break
    return nodes, group_counts


def classify(tag: str, props: dict[str, str]) -> list[tuple[str, list[str]]]:
    text = " ".join([tag, props.get("name", ""), props.get("description", ""), props.get("unit", "")])
    haystack = normalize(text)
    matches: list[tuple[str, list[str]]] = []
    for category, rule in CATEGORY_RULES.items():
        matched = [word for word in rule["include"] if normalize(word) in haystack]
        if not matched:
            continue
        excluded = [word for word in rule["exclude"] if normalize(word) in haystack]
        if excluded:
            continue
        matches.append((category, matched))
    return matches


def read_values(pspace, T, tags: list[str]) -> dict[str, dict[str, Any]]:
    if not tags:
        return {}
    values, meta = read_realtime(pspace, T, {tag: tag for tag in tags})
    return {
        tag: {
            "value": values.get(tag),
            "timestamp": (meta.get("timestamps") or {}).get(tag, ""),
            "quality": (meta.get("qualities") or {}).get(tag, ""),
            "error": (meta.get("errors") or {}).get(tag, ""),
        }
        for tag in tags
    }


def write_tree_markdown(path: Path, nodes: set[str], group_counts: dict[str, Counter[str]], rows: list[dict[str, Any]]) -> None:
    by_node_category: dict[str, dict[str, list[dict[str, Any]]]] = defaultdict(lambda: defaultdict(list))
    for row in rows:
        by_node_category[row["root_node"]][row["category"]].append(row)

    lines: list[str] = []
    lines.append("# 高炉关键指标节点检索")
    lines.append("")
    lines.append(f"生成时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    lines.append("")
    lines.append("## 已识别节点")
    lines.append("")
    for node in sorted(nodes):
        count = sum(group_counts.get(node, Counter()).values())
        lines.append(f"- `{node}`：叶子测点约 {count} 个")
        for group, group_count in sorted(group_counts.get(node, Counter()).items()):
            lines.append(f"  - `{group}`：{group_count}")
    lines.append("")
    lines.append("## 关键指标节点树")
    lines.append("")

    for node in sorted(by_node_category):
        lines.append(f"### `{node}`")
        lines.append("")
        for category in sorted(by_node_category[node]):
            lines.append(f"- {category}")
            category_rows = sorted(
                by_node_category[node][category],
                key=lambda row: (row.get("subsystem", ""), row.get("description", ""), row.get("tag", "")),
            )
            for row in category_rows:
                desc = row.get("description") or row.get("name") or ""
                unit = f" {row.get('unit')}" if row.get("unit") else ""
                value = row.get("value")
                value_text = "" if value is None or value == "" else f"；当前值={value}{unit}"
                lines.append(f"  - `{row['subsystem']}` / `{row['name']}`：{desc}{value_text}")
                lines.append(f"    - `{row['tag']}`")
        lines.append("")

    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--sdk-root", default=os.getenv("PSPACE_SDK_ROOT"))
    parser.add_argument("--pspace-config", default=os.getenv("PSPACE_CONFIG", str(ROOT_DIR / "ghsc" / "src" / "main" / "resources" / "application-prod.yml")))
    parser.add_argument("--pspace-server", default=os.getenv("PSPACE_SERVER"))
    parser.add_argument("--pspace-port", default=os.getenv("PSPACE_PORT"))
    parser.add_argument("--pspace-user", default=os.getenv("PSPACE_USER"))
    parser.add_argument("--pspace-password", default=os.getenv("PSPACE_PASSWORD"))
    parser.add_argument("--out-dir", default=str(ROOT_DIR / "高炉传感器数据"))
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    config = read_pspace_config(args.pspace_config)
    connection = {
        "server": args.pspace_server or config.get("ip") or "10.22.181.243",
        "port": str(args.pspace_port or config.get("port") or "8889"),
        "user": args.pspace_user or config.get("username") or "",
        "password": args.pspace_password or config.get("password") or "",
    }
    if not connection["user"] or not connection["password"]:
        raise SystemExit("Missing pSpace credentials. Set PSPACE_USER/PSPACE_PASSWORD or PSPACE_CONFIG.")

    sdk_root = find_sdk_root(args.sdk_root)
    PsObject, T = load_sdk(sdk_root)
    pspace = connect_pspace(PsObject, T, connection)

    all_tags = query_all_tag_names(pspace, T)
    nodes, group_counts = discover_nodes(all_tags)
    scan_tags = [tag for tag in all_tags if should_scan(tag, nodes)]

    rows: list[dict[str, Any]] = []
    for tag in scan_tags:
        props = get_tag_props(pspace, T, tag, "")
        for category, matched in classify(tag, props):
            root_node = root_node_for(tag)
            rows.append(
                {
                    "category": category,
                    "root_node": root_node,
                    "subsystem": subsystem_for(tag, root_node),
                    "tag": tag,
                    "name": props.get("name", ""),
                    "description": props.get("description", ""),
                    "unit": props.get("unit", ""),
                    "matched": "|".join(matched),
                }
            )

    unique_tags = list(dict.fromkeys(row["tag"] for row in rows))
    values = read_values(pspace, T, unique_tags)
    for row in rows:
        row.update(values.get(row["tag"], {}))

    rows.sort(key=lambda row: (row["root_node"], row["category"], row["subsystem"], row["tag"]))

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    csv_path = out_dir / f"高炉关键指标节点检索_{stamp}.csv"
    json_path = out_dir / f"高炉关键指标节点检索_{stamp}.json"
    md_path = out_dir / f"高炉关键指标节点检索_{stamp}.md"

    with csv_path.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDNAMES)
        writer.writeheader()
        writer.writerows(rows)

    category_counts = Counter(row["category"] for row in rows)
    node_counts = Counter(row["root_node"] for row in rows)
    json_path.write_text(
        json.dumps(
            {
                "server": connection["server"],
                "port": connection["port"],
                "all_tag_count": len(all_tags),
                "scan_tag_count": len(scan_tags),
                "discovered_nodes": sorted(nodes),
                "category_counts": dict(category_counts),
                "node_counts": dict(node_counts),
                "csv": str(csv_path),
                "markdown": str(md_path),
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    write_tree_markdown(md_path, nodes, group_counts, rows)

    print(
        json.dumps(
            {
                "all_tag_count": len(all_tags),
                "scan_tag_count": len(scan_tags),
                "match_count": len(rows),
                "node_count": len(nodes),
                "category_counts": dict(category_counts),
                "csv": str(csv_path),
                "markdown": str(md_path),
                "json": str(json_path),
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
