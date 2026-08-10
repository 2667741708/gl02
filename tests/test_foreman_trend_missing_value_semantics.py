from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_missing_values_are_not_coerced_to_zero():
    source = (ROOT / "高炉前端数据" / "assets" / "foreman-trend-preview.js").read_text(encoding="utf-8")
    assert "if (value === null || value === undefined || value === '') return null;" in source


def test_confirmed_foreman_pspace_fields_are_in_existing_8770_stream():
    source = (ROOT / "tools" / "pspace_8092_realtime_bridge.py").read_text(encoding="utf-8")
    for sensor_id in (
        "PCI_previous_hour",
        "BlastEnergy",
        "BlastSpeedStd",
        "BlastSpeedActual",
        "Q_soft_water",
        "P_soft_water",
        "Q_high_pressure_water",
        "P_high_pressure_water",
        "P_medium_pressure_water",
        "ExpansionTankLevel",
        "Q_N2",
        "P_N2",
        "P_O2_valve_in",
        "P_O2_valve_out",
    ):
        assert f'"{sensor_id}"' in source
    assert "SENSORS + BILLBOARD_EXTRA_SENSORS + FOREMAN_EXTRA_SENSORS" in source
    assert '"SIO_GL02_PC_T0004"' in source
    assert '"PCI_current_hour"' not in source
    frontend = (ROOT / "高炉前端数据" / "assets" / "foreman-trend-preview.js").read_text(encoding="utf-8")
    assert "m('氮气压力', ['P_N2', 'nitrogen_pressure']" in frontend
