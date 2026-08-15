from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Any


DEFAULT_VARIABLES = (
    "P_top",
    "DP_total",
    "P_blast",
    "T_blast",
    "Q_blast",
    "PCI_rate",
    "GasUtil",
    "PI",
    "L",
    "Q_O2",
    "O2_rate",
    "Hopper_weight",
    "L_south",
    "L_north",
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Read-only pSpace history probe for foreman curves.")
    parser.add_argument("--project-root", required=True)
    parser.add_argument("--start", required=True, help="Local pSpace time: YYYY-mm-dd HH:MM:SS")
    parser.add_argument("--end", required=True, help="Local pSpace time: YYYY-mm-dd HH:MM:SS")
    parser.add_argument("--variable", action="append", dest="variables")
    parser.add_argument("--batch-size", type=int, default=1)
    return parser.parse_args()


def import_windows_environment(names: tuple[str, ...]) -> None:
    if os.name != "nt":
        return
    import winreg

    locations = (
        (winreg.HKEY_LOCAL_MACHINE, r"SYSTEM\CurrentControlSet\Control\Session Manager\Environment"),
        (winreg.HKEY_CURRENT_USER, "Environment"),
    )
    for name in names:
        if os.getenv(name):
            continue
        for hive, key_path in locations:
            try:
                with winreg.OpenKey(hive, key_path) as key:
                    value, _ = winreg.QueryValueEx(key, name)
            except OSError:
                continue
            if value:
                os.environ[name] = str(value)
                break


def serialise_run(
    points_by_tag: dict[str, Any],
    series: dict[str, dict[str, float]],
    audits: dict[str, dict[str, dict[str, Any]]],
    errors: dict[str, str],
) -> dict[str, Any]:
    rows = []
    for tag, point in sorted(points_by_tag.items(), key=lambda item: item[1].variable_name):
        values = []
        for timestamp, value in sorted(series.get(tag, {}).items()):
            audit = audits.get(tag, {}).get(timestamp, {})
            values.append(
                {
                    "ts": timestamp,
                    "value": value,
                    "sample_count": audit.get("sample_count"),
                    "numeric_sample_count": audit.get("numeric_sample_count"),
                    "coverage_ratio": audit.get("coverage_ratio"),
                    "min_value": audit.get("min_value"),
                    "max_value": audit.get("max_value"),
                }
            )
        rows.append(
            {
                "variable_name": point.variable_name,
                "short_name": point.short_name,
                "tag_long_name": tag,
                "values": values,
                "error": errors.get(tag),
            }
        )
    return {"rows": rows, "errors": errors}


def main() -> int:
    args = parse_args()
    root = Path(args.project_root)
    sync_root = root / "数据库同步和存取"
    sync_src = sync_root / "src"
    for candidate in (
        root / "trend_analysis" / "trend_backend",
        root / "趋势分析" / "trend_backend",
        sync_src,
    ):
        if candidate.exists() and str(candidate) not in sys.path:
            sys.path.insert(0, str(candidate))

    import catalog
    import pspace_history
    import raw_minute_pipeline

    import_windows_environment(
        ("PSPACE_SERVER", "PSPACE_PORT", "PSPACE_USER", "PSPACE_PASSWORD", "PSPACE_SDK_ROOT")
    )
    variables = set(args.variables or DEFAULT_VARIABLES)
    points = [point for point in catalog.physical_points(sync_root / "config" / "sync_config.json") if point.variable_name in variables]
    points_by_tag = {point.tag_long_name: point for point in points}
    if not points_by_tag:
        raise RuntimeError("No requested physical points were found in sync_config.json")

    config_candidates = (
        root / "ghsc" / "src" / "main" / "resources" / "application-prod.yml",
        root / "ghsc" / "src" / "main" / "resources" / "application-dev.yml",
    )
    connection = None
    last_error = None
    for config_path in (*config_candidates, None):
        try:
            connection = pspace_history.resolve_connection(config_path=config_path)
            break
        except RuntimeError as exc:
            last_error = exc
    if connection is None:
        raise RuntimeError("pSpace connection settings are unavailable") from last_error

    start = datetime.fromisoformat(args.start)
    end = datetime.fromisoformat(args.end)
    PsObject, T = pspace_history.load_sdk(root / "pythonSDK(1)")
    series, audits, _raw_records, errors = raw_minute_pipeline.fetch_raw_history_concurrent(
        PsObject,
        T,
        connection,
        list(points_by_tag),
        start,
        end,
        pspace_history=pspace_history,
        target_interval_seconds=60,
        source_interval_seconds=5,
        batch_size=max(1, args.batch_size),
        max_workers=1,
        raw_max_values=20000,
        raw_bounds=0,
    )
    payload = {
        "schema": "bf.pspace-foreman-history-probe.v1",
        "read_only": True,
        "database_writes": 0,
        "start": args.start,
        "end": args.end,
        "batch_size": args.batch_size,
        "requested_variables": sorted(variables),
        **serialise_run(points_by_tag, series, audits, errors),
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2, default=str))
    return 0 if not errors else 2


if __name__ == "__main__":
    raise SystemExit(main())
