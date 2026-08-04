# -*- coding: utf-8 -*-
"""Audit whether pSpace tag metadata carries GL02 furnace height labels.

This script is read-only. It is intended to be run on 10.30.220.12 through
tools/remote_22012_exec.py so it can reuse the server-side ghsc pSpace config
and Python SDK. It checks only GetTagProps and RealReadList for known GL02 BT
height-related tags.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any


SIO_ROOT = r"\冀南钢铁\SIO\GL02\BT"

STATIC_PRESSURE_TARGETS = [
    {
        "variable_name": "P_static_20m35",
        "tag": rf"{SIO_ROOT}\SIO_GL02_BT_T0152",
        "expected_height_m": 20.35,
        "expected_zone": "静压力",
    },
    {
        "variable_name": "P_static_23m49",
        "tag": rf"{SIO_ROOT}\SIO_GL02_BT_T0153",
        "expected_height_m": 23.49,
        "expected_zone": "静压力",
    },
    {
        "variable_name": "P_static_28m98",
        "tag": rf"{SIO_ROOT}\SIO_GL02_BT_T0154",
        "expected_height_m": 28.98,
        "expected_zone": "静压力",
    },
]

BODY_LAYER_SPECS = [
    (7, 16.860, "炉腹下", 155),
    (8, 18.335, "炉腹上", 163),
    (9, 20.125, "炉腰", 171),
    (10, 21.860, "炉身下", 179),
    (11, 23.711, "炉身下", 187),
    (12, 25.441, "炉身下", 195),
    (13, 27.171, "炉身下", 203),
    (14, 28.901, "炉身中", 211),
    (15, 30.631, "炉身上", 219),
    (16, 32.361, "炉身上", 227),
]

THROAT_TARGETS = [
    {
        "variable_name": f"T_throat_{sector}",
        "tag": rf"{SIO_ROOT}\SIO_GL02_BT_T{235 + index:04d}",
        "expected_height_m": 37.200,
        "expected_zone": "炉喉",
    }
    for index, sector in enumerate("ABCD")
]


def body_targets() -> list[dict[str, Any]]:
    targets: list[dict[str, Any]] = []
    for layer, height, zone, first_short_id in BODY_LAYER_SPECS:
        for offset, sector in enumerate("ABCDEFGH"):
            targets.append(
                {
                    "variable_name": f"T_body_L{layer}_{sector}",
                    "tag": rf"{SIO_ROOT}\SIO_GL02_BT_T{first_short_id + offset:04d}",
                    "expected_height_m": height,
                    "expected_zone": zone,
                }
            )
    return targets


def all_targets() -> list[dict[str, Any]]:
    return STATIC_PRESSURE_TARGETS + body_targets() + THROAT_TARGETS


def first_existing(paths: list[Path]) -> Path | None:
    for path in paths:
        if path.exists():
            return path
    return None


def resolve_runtime(root: Path | None = None) -> tuple[Path, Path, Path]:
    candidates = []
    if root:
        candidates.append(root)
    candidates.append(Path.cwd())
    env_root = os.getenv("BF_REMOTE_PROJECT_ROOT") or os.getenv("BF_22012_PROJECT_ROOT")
    if env_root:
        candidates.append(Path(env_root))
    candidates.extend(
        [
            Path(r"F:\高炉炼铁项目-real-sensor-v2_V3"),
            Path(r"F:\高炉炼铁项目-real-sensor-v2_V4_8093_PREVIEW"),
            Path(r"F:\高炉炼铁项目-real-sensor-v2_V3_AUTO_PREVIEW"),
        ]
    )

    roots: list[Path] = []
    seen: set[str] = set()
    for item in candidates:
        key = str(item).lower()
        if key not in seen and item.exists():
            roots.append(item)
            seen.add(key)

    trend_candidates: list[Path] = []
    sdk_candidates: list[Path] = []
    config_candidates: list[Path] = []
    for item in roots:
        trend_candidates.extend(
            [
                item / "trend_analysis" / "trend_backend",
                item / "趋势分析" / "trend_backend",
            ]
        )
        sdk_candidates.append(item / "pythonSDK(1)")
        config_candidates.extend(
            [
                item / "ghsc" / "src" / "main" / "resources" / "application-prod.yml",
                item / "ghsc" / "src" / "main" / "resources" / "application-dev.yml",
            ]
        )

    trend_backend = first_existing([p for p in trend_candidates if (p / "pspace_history.py").exists()])
    sdk_root = first_existing([p for p in sdk_candidates if (p / "PythonAPI" / "PsServer.py").exists()])
    config_path = first_existing(config_candidates)
    missing = []
    if trend_backend is None:
        missing.append("trend_backend/pspace_history.py")
    if sdk_root is None:
        missing.append("pythonSDK(1)/PythonAPI/PsServer.py")
    if config_path is None:
        missing.append("ghsc application yml")
    if missing:
        raise RuntimeError(f"missing runtime files: {', '.join(missing)}; roots={[str(r) for r in roots]}")
    return trend_backend, sdk_root, config_path


def height_tokens(height: float) -> set[str]:
    value = f"{height:.3f}".rstrip("0").rstrip(".")
    compact = value.replace(".", "")
    tokens = {f"{value}m", f"{value}M", f"{value}米", f"{height:.3f}m", f"{height:.3f}米"}
    if len(compact) >= 3:
        tokens.add(f"{compact[:2]}m{compact[2:]}")
    return tokens


def normalize(value: str) -> str:
    return re.sub(r"[\s_（）()：:，,。/\\\-]+", "", value.lower())


def metadata_has_height(text: str, expected_height: float) -> bool:
    normalized = normalize(text)
    return any(normalize(token) in normalized for token in height_tokens(expected_height))


def prop_text(props: dict[str, str]) -> str:
    return " ".join([props.get("name", ""), props.get("description", ""), props.get("unit", "")])


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=None)
    parser.add_argument("--server", default=os.getenv("PSPACE_SERVER", "10.22.181.243"))
    parser.add_argument("--port", default=os.getenv("PSPACE_PORT", "8889"))
    parser.add_argument("--out", type=Path, default=None)
    parser.add_argument("--include-rows", action="store_true")
    args = parser.parse_args()

    trend_backend, sdk_root, config_path = resolve_runtime(args.root)
    sys.path.insert(0, str(trend_backend))
    import pspace_history  # noqa: WPS433

    connection = pspace_history.resolve_connection(
        config_path=config_path,
        server=args.server,
        port=args.port,
    )
    PsObject, T = pspace_history.load_sdk(sdk_root)
    pspace = pspace_history.connect_pspace(PsObject, T, connection)
    targets = all_targets()
    tags = [target["tag"] for target in targets]
    try:
        realtime = pspace_history.read_realtime(pspace, T, tags)
        rows = []
        for target in targets:
            props = pspace_history.get_tag_props(pspace, T, target["tag"])
            text = prop_text(props)
            has_height = metadata_has_height(text, float(target["expected_height_m"]))
            latest = realtime.get(target["tag"], {})
            rows.append(
                {
                    **target,
                    "pspace_name": props.get("name", ""),
                    "pspace_description": props.get("description", ""),
                    "pspace_unit": props.get("unit", ""),
                    "pspace_metadata_has_expected_height": has_height,
                    "latest_value": latest.get("latest_value"),
                    "latest_time": str(latest.get("latest_time") or ""),
                    "latest_quality": str(latest.get("latest_quality") or ""),
                }
            )
    finally:
        pspace_history.close_pspace(pspace)

    by_group = Counter()
    group_with_height = Counter()
    group_latest_ok = Counter()
    sample_missing: dict[str, list[dict[str, Any]]] = defaultdict(list)
    sample_with_height: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        if row["variable_name"].startswith("T_body_"):
            group = "body_temperature"
        elif row["variable_name"].startswith("T_throat_"):
            group = "throat_temperature"
        else:
            group = "static_pressure"
        by_group[group] += 1
        if row["pspace_metadata_has_expected_height"]:
            group_with_height[group] += 1
            if len(sample_with_height[group]) < 5:
                sample_with_height[group].append(row)
        elif len(sample_missing[group]) < 5:
            sample_missing[group].append(row)
        if row["latest_time"] and not row["latest_quality"].lower().startswith("bad"):
            group_latest_ok[group] += 1

    report = {
        "ok": True,
        "checked_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "source": {
            "pspace_server": f"{connection['server']}:{connection['port']}",
            "trend_backend": str(trend_backend),
            "sdk_root": str(sdk_root),
            "config_path": str(config_path),
        },
        "total_targets": len(rows),
        "groups": {
            group: {
                "targets": by_group[group],
                "metadata_with_expected_height": group_with_height[group],
                "realtime_rows_with_non_bad_quality": group_latest_ok[group],
                "sample_with_height": sample_with_height[group],
                "sample_missing_height": sample_missing[group],
            }
            for group in ("static_pressure", "body_temperature", "throat_temperature")
        },
    }
    if args.include_rows:
        report["rows"] = rows
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps(report, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
