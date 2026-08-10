from __future__ import annotations

import csv
import importlib.util
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "tools" / "apply_foreman_points_and_coal_storage.py"
SPEC = importlib.util.spec_from_file_location("foreman_points_patch", MODULE_PATH)
assert SPEC and SPEC.loader
PATCH = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(PATCH)


def test_confirmed_point_rows_are_unique_and_gl02_scoped() -> None:
    names = [row[0] for row in PATCH.POINT_ROWS]
    assert len(names) == len(set(names))
    assert "PCI_previous_hour" in names
    assert "PCI_current_hour" in names
    assert "CO_top" in names
    assert "CO2_top" in names
    assert "H2_top" in names
    for variable, _, _, short_name, tag, _, _ in PATCH.POINT_ROWS:
        if variable == "PCI_current_hour":
            assert short_name == "派生"
            assert not tag.startswith("\\")
        elif variable in {"CO_top", "CO2_top", "H2_top"}:
            assert tag.startswith("\\冀南钢铁\\SIO\\CC\\GF2\\")
            assert short_name in tag
        else:
            assert tag.startswith("\\冀南钢铁\\SIO\\GL02\\")
            assert short_name in tag


def test_catalog_patch_is_idempotent(tmp_path: Path) -> None:
    catalog = tmp_path / "点位清单.tsv"
    with catalog.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=PATCH.HEADERS, delimiter="\t", lineterminator="\n")
        writer.writeheader()
        writer.writerow(dict(zip(PATCH.HEADERS, ("PCI_rate", "喷煤实际速率", "PC", "SIO_GL02_PC_T0007", r"\冀南钢铁\SIO\GL02\PC\SIO_GL02_PC_T0007", "2号炉喷吹_喷煤量累积瞬时值", "单位t/h"))))

    first_text, first_added = PATCH.patched_catalog_text(catalog)
    catalog.write_text(first_text, encoding="utf-8")
    second_text, second_added = PATCH.patched_catalog_text(catalog)
    assert len(first_added) == len(PATCH.POINT_ROWS)
    assert second_added == []
    assert second_text == first_text


def test_sync_patch_adds_one_refresh_call() -> None:
    source = (
        "from catalog import load_config, physical_points\n"
        "\n"
        "def sync_window():\n"
        "    return {\n"
        "        \"inserted_rows\": inserted_total,\n"
        "        \"source_options\": source_options,\n"
        "        \"summary\": summary(conn),\n"
        "    }\n"
    )
    once = PATCH.patch_sync_text(source)
    twice = PATCH.patch_sync_text(once)
    assert once == twice
    assert once.count(PATCH.SYNC_IMPORT) == 1
    assert once.count("refresh_coal_injection_hourly(conn, start, end)") == 1
    assert once.count('"coal_injection_hourly": coal_hourly') == 1
    assert once.count(PATCH.LIGHT_SUMMARY_MARKER) == 1
    assert '"summary": summary(conn)' not in once


def test_hourly_schema_exposes_amount_and_current_hour_views() -> None:
    sql = (ROOT / "tools" / "sql" / "foreman_coal_hourly_20260806.sql").read_text(encoding="utf-8")
    assert "bf_sensor.coal_injection_hourly" in sql
    assert "bf_sensor.v_coal_injection_hourly" in sql
    assert "bf_sensor.v_coal_injection_current_hour" in sql
    assert "metered_amount_t" in sql
    assert "integrated_amount_t" in sql


def test_registry_deploy_registers_all_foreman_points_before_sync_restart() -> None:
    init_text = (ROOT / "tools" / "init_foreman_points_pg_light.py").read_text(encoding="utf-8")
    deploy_text = (ROOT / "tools" / "remote_deploy_foreman_points_coal_20260806.ps1").read_text(encoding="utf-8")
    for variable in ("CO_top", "CO2_top", "H2_top", "BlastEnergy", "BlastSpeedStd", "BlastSpeedActual"):
        assert variable in init_text
    assert "confirmed == 19" in init_text
    assert "return 0 if confirmed == 19 else 2" in init_text
    register_pos = deploy_text.index("init_foreman_points_pg_light.py")
    sync_pos = deploy_text.index("Start-SyncTasks")
    assert register_pos < sync_pos
    assert "confirmed_foreman_points -ne 19" in deploy_text
    assert "Relative = 'run_realtime_sync_pg_bg.ps1'" in deploy_text
    assert "Relative = 'config\\sync_config.json'" in deploy_text


def test_foreman_pspace_extra_deploy_contract_covers_requested_points() -> None:
    deploy_text = (ROOT / "tools" / "remote_deploy_foreman_pspace_extra_metrics_20260806.ps1").read_text(encoding="utf-8")
    bridge_text = (ROOT / "tools" / "pspace_8092_realtime_bridge.py").read_text(encoding="utf-8")
    html_text = (ROOT / "高炉前端数据" / "foreman_trend_preview.html").read_text(encoding="utf-8")
    requested_tags = (
        "SIO_GL02_BT_T0136", "SIO_GL02_BT_T0133", "SIO_GL02_BT_T0134",
        "SIO_GL02_BT_T0056", "SIO_GL02_BT_T0137", "SIO_GL02_BT_T0021",
        "SIO_GL02_BT_T0148", "SIO_GL02_BT_T0147", "SIO_GL02_BT_T0097",
        "SIO_GL02_LD_T0059", "SIO_GL02_LD_T0045", "SIO_GL02_LD_T0073",
        "SIO_GL02_CX_T0289", "SIO_GL02_CX_T0291", "SIO_CC_GF2_T0111",
        "SIO_CC_GF2_T0112", "SIO_CC_GF2_T0113",
    )
    for tag in requested_tags:
        assert tag in bridge_text
        assert tag in deploy_text
    assert "20260806-pspace-extra-r3" in html_text
    assert "Start-ScheduledTask" in deploy_text
