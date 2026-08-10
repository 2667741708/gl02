"""Idempotently add confirmed GL02 foreman points and hourly coal storage."""

from __future__ import annotations

import argparse
import csv
import json
import shutil
from datetime import datetime
from pathlib import Path


MARKER_BEGIN = "-- FOREMAN-COAL-HOURLY-20260806-BEGIN"
MARKER_END = "-- FOREMAN-COAL-HOURLY-20260806-END"
SYNC_IMPORT = "from coal_hourly import refresh_coal_injection_hourly"
SYNC_MARKER_BEGIN = "    # FOREMAN-COAL-HOURLY-20260806-BEGIN"
SYNC_MARKER_END = "    # FOREMAN-COAL-HOURLY-20260806-END"
LIGHT_SUMMARY_MARKER = "        # FOREMAN-SYNC-LIGHT-SUMMARY-20260806"

HEADERS = ["变量名", "中文名/标高", "节点分支", "短名", "点ID/长名", "描述", "状态/用途"]

POINT_ROWS = [
    ("CO_top", "一氧化碳", "CC/GF2", "SIO_CC_GF2_T0112", r"\冀南钢铁\SIO\CC\GF2\SIO_CC_GF2_T0112", "2号炉干法除尘_一氧化碳", "2号炉pSpace实测确认；跨子树明确可用；现场画面口径单位%"),
    ("CO2_top", "二氧化碳", "CC/GF2", "SIO_CC_GF2_T0113", r"\冀南钢铁\SIO\CC\GF2\SIO_CC_GF2_T0113", "2号炉干法除尘_二氧化碳", "2号炉pSpace实测确认；跨子树明确可用；单位%"),
    ("H2_top", "氢气", "CC/GF2", "SIO_CC_GF2_T0111", r"\冀南钢铁\SIO\CC\GF2\SIO_CC_GF2_T0111", "2号炉干法除尘_氢气", "2号炉pSpace实测确认；跨子树明确可用；现场画面口径单位%"),
    ("PCI_previous_hour", "上小时喷煤量", "PC", "SIO_GL02_PC_T0004", r"\冀南钢铁\SIO\GL02\PC\SIO_GL02_PC_T0004", "2号炉喷吹_上小时喷煤量累计", "2号炉SIO实测确认；单位t；按整点归属上一完整小时"),
    ("BlastEnergy", "鼓风动能", "BT", "SIO_GL02_BT_T0136", r"\冀南钢铁\SIO\GL02\BT\SIO_GL02_BT_T0136", "2号炉本体_鼓风动能", "2号炉SIO实测确认；工长趋势显示"),
    ("BlastSpeedStd", "标准风速", "BT", "SIO_GL02_BT_T0133", r"\冀南钢铁\SIO\GL02\BT\SIO_GL02_BT_T0133", "2号炉本体_标准风速", "2号炉SIO实测确认；单位m/s"),
    ("BlastSpeedActual", "实际风速", "BT", "SIO_GL02_BT_T0134", r"\冀南钢铁\SIO\GL02\BT\SIO_GL02_BT_T0134", "2号炉本体_实际风速", "2号炉SIO实测确认；单位m/s"),
    ("Q_soft_water", "软水流量", "BT", "SIO_GL02_BT_T0056", r"\冀南钢铁\SIO\GL02\BT\SIO_GL02_BT_T0056", "2号炉本体_软水回水主管流量", "2号炉SIO实测确认；单位m3/h"),
    ("P_soft_water", "软水压力", "BT", "SIO_GL02_BT_T0137", r"\冀南钢铁\SIO\GL02\BT\SIO_GL02_BT_T0137", "2号炉本体_软水给水总管压力", "2号炉SIO实测确认；单位MPa"),
    ("Q_high_pressure_water", "高压水流量", "BT", "SIO_GL02_BT_T0021", r"\冀南钢铁\SIO\GL02\BT\SIO_GL02_BT_T0021", "2号炉本体_高压水流量", "2号炉SIO实测确认；单位m3/h"),
    ("P_high_pressure_water", "高压水压力", "BT", "SIO_GL02_BT_T0148", r"\冀南钢铁\SIO\GL02\BT\SIO_GL02_BT_T0148", "2号炉本体_高压供水压力", "2号炉SIO实测确认；单位MPa"),
    ("P_medium_pressure_water", "中压水压力", "BT", "SIO_GL02_BT_T0147", r"\冀南钢铁\SIO\GL02\BT\SIO_GL02_BT_T0147", "2号炉本体_中压供水压力", "2号炉SIO实测确认；单位MPa"),
    ("ExpansionTankLevel", "膨胀罐液位", "BT", "SIO_GL02_BT_T0097", r"\冀南钢铁\SIO\GL02\BT\SIO_GL02_BT_T0097", "2号炉本体_膨胀罐液位", "2号炉SIO实测确认；单位m"),
    ("Hopper_weight", "罐重", "LD", "SIO_GL02_LD_T0059", r"\冀南钢铁\SIO\GL02\LD\SIO_GL02_LD_T0059", "2号炉炉顶_称量罐实际重量称重", "2号炉SIO实测确认；单位t"),
    ("Q_N2", "氮气流量", "LD", "SIO_GL02_LD_T0045", r"\冀南钢铁\SIO\GL02\LD\SIO_GL02_LD_T0045", "2号炉炉顶_进下阀箱和进气密箱氮气流量", "2号炉SIO实测确认；单位Nm3/h"),
    ("P_N2", "氮气压力", "LD", "SIO_GL02_LD_T0073", r"\冀南钢铁\SIO\GL02\LD\SIO_GL02_LD_T0073", "2号炉炉顶_氮气总管调压阀后压力", "2号炉SIO实测确认；单位kPa"),
    ("P_O2_valve_in", "阀前富氧压力", "CX", "SIO_GL02_CX_T0289", r"\冀南钢铁\SIO\GL02\CX\SIO_GL02_CX_T0289", "2号炉槽下_富氧压力", "2号炉SIO实测确认；单位MPa"),
    ("P_O2_valve_out", "阀后富氧压力", "CX", "SIO_GL02_CX_T0291", r"\冀南钢铁\SIO\GL02\CX\SIO_GL02_CX_T0291", "2号炉槽下_阀后富氧", "2号炉SIO实测确认；单位MPa"),
    ("PCI_current_hour", "本小时喷煤量", "PC", "派生", "PCI_rate integral from hour start", "喷煤实际速率从本小时整点按真实时间间隔积分", "派生实时计算；单位t；无直接pSpace点位时使用"),
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True, help="数据库同步和存取目录")
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args()


def read_rows(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle, delimiter="\t"))


def patched_catalog_text(path: Path) -> tuple[str, list[str]]:
    rows = read_rows(path)
    existing = {row["变量名"]: row for row in rows}
    added: list[str] = []
    for values in POINT_ROWS:
        candidate = dict(zip(HEADERS, values))
        current = existing.get(candidate["变量名"])
        if current:
            if any(current.get(key, "").strip() != candidate[key] for key in HEADERS):
                raise RuntimeError(f"Existing point conflicts with confirmed mapping: {candidate['变量名']}")
            continue
        rows.append(candidate)
        existing[candidate["变量名"]] = candidate
        added.append(candidate["变量名"])
    lines = ["\t".join(HEADERS)]
    lines.extend("\t".join(row.get(header, "") for header in HEADERS) for row in rows)
    return "\n".join(lines) + "\n", added


def patch_sync_text(text: str) -> str:
    if SYNC_IMPORT not in text:
        anchor = "from catalog import load_config, physical_points\n"
        if anchor not in text:
            raise RuntimeError("sync import anchor not found")
        text = text.replace(anchor, anchor + SYNC_IMPORT + "\n", 1)
    if SYNC_MARKER_BEGIN not in text:
        anchor = "    return {\n        \"inserted_rows\": inserted_total,\n"
        if anchor not in text:
            raise RuntimeError("sync return anchor not found")
        block = (
            f"{SYNC_MARKER_BEGIN}\n"
            "    coal_hourly = refresh_coal_injection_hourly(conn, start, end)\n"
            f"{SYNC_MARKER_END}\n"
        )
        text = text.replace(anchor, block + anchor, 1)
        summary_anchor = '        "source_options": source_options,\n'
        text = text.replace(summary_anchor, summary_anchor + '        "coal_injection_hourly": coal_hourly,\n', 1)
    if LIGHT_SUMMARY_MARKER not in text:
        heavy_summary = '        "summary": summary(conn),\n'
        if heavy_summary not in text:
            raise RuntimeError("sync heavy-summary anchor not found")
        light_summary = (
            f"{LIGHT_SUMMARY_MARKER}\n"
            '        "summary": {\n'
            '            "physical_points": len(points),\n'
            '            "current_window_rows_written": inserted_total,\n'
            '            "current_window_raw_rows_written": raw_written_total,\n'
            '            "failed_chunks": failed_chunks,\n'
            '        },\n'
        )
        text = text.replace(heavy_summary, light_summary, 1)
    return text


def write_atomic(path: Path, text: str) -> None:
    temporary = path.with_suffix(path.suffix + ".foreman.tmp")
    temporary.write_text(text, encoding="utf-8", newline="\n")
    temporary.replace(path)


def main() -> int:
    args = parse_args()
    root = args.root.resolve()
    catalog = root / "config" / "点位清单.tsv"
    schema = root / "schema" / "postgresql_required_points.sql"
    sync = root / "src" / "sync_from_243_pg.py"
    coal_module = root / "src" / "coal_hourly.py"
    this_root = Path(__file__).resolve().parents[1]
    migration = this_root / "tools" / "sql" / "foreman_coal_hourly_20260806.sql"
    module_source = this_root / "tools" / "foreman_coal_hourly_store.py"
    for required in (catalog, schema, sync, migration, module_source):
        if not required.is_file():
            raise FileNotFoundError(required)

    catalog_text, added = patched_catalog_text(catalog)
    schema_text = schema.read_text(encoding="utf-8")
    if MARKER_BEGIN not in schema_text:
        schema_text = schema_text.rstrip() + "\n\n" + MARKER_BEGIN + "\n" + migration.read_text(encoding="utf-8").rstrip() + "\n" + MARKER_END + "\n"
    sync_text = patch_sync_text(sync.read_text(encoding="utf-8"))

    result = {
        "root": str(root),
        "dry_run": args.dry_run,
        "point_rows_added": added,
        "point_total_after": len(read_rows(catalog)) + len(added),
        "schema_marker": MARKER_BEGIN,
        "sync_marker": SYNC_MARKER_BEGIN.strip(),
    }
    if args.dry_run:
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup = root / "backups" / f"foreman_points_coal_{stamp}"
    backup.mkdir(parents=True, exist_ok=False)
    for source in (catalog, schema, sync):
        shutil.copy2(source, backup / source.name)
    if coal_module.exists():
        shutil.copy2(coal_module, backup / coal_module.name)

    write_atomic(catalog, catalog_text)
    write_atomic(schema, schema_text)
    write_atomic(sync, sync_text)
    shutil.copy2(module_source, coal_module)
    result["backup"] = str(backup)
    result["deployed_module"] = str(coal_module)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
