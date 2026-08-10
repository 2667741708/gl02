from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "tools" / "pspace_8092_realtime_bridge.py"


def load_bridge_module():
    spec = importlib.util.spec_from_file_location("pspace_billboard_bridge_test", MODULE_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class FakeTypes:
    Return = "return"
    Error = "error"
    RealReadListTagNameBuffer = "tag_names"
    TagLongNameDict = "tag"
    PsRealReadListValueDict = "value"
    PsRealReadListTimeStamp = "timestamp"
    PsRealReadListListQualityDict = "quality"


class FakePspace:
    def __init__(self):
        self.batch_sizes = []

    def RealReadList(self, request):
        tags = request[FakeTypes.RealReadListTagNameBuffer]
        self.batch_sizes.append(len(tags))
        result = {FakeTypes.Return: 0}
        result.update(
            {
                index: {
                FakeTypes.TagLongNameDict: tag,
                FakeTypes.PsRealReadListValueDict: float(index + 1),
                FakeTypes.PsRealReadListTimeStamp: "2026/07/26 12:00:05.000",
                FakeTypes.PsRealReadListListQualityDict: "Good",
                }
                for index, tag in enumerate(tags)
            }
        )
        return result


def test_billboard_stream_publishes_133_physical_points_with_point_meta():
    bridge_module = load_bridge_module()
    mapping = bridge_module.normalize_confirmed_sio_gl02_mapping(
        {},
        bridge_module.DEFAULT_SIO_GL02_ROOT,
    )
    mapping.update(
        {
            "pspace_server": "fixture",
            "pspace_port": "8889",
            "pspace_source": "fixture:8889",
            "poll_seconds": 1.0,
        }
    )
    pspace = FakePspace()
    bridge = bridge_module.DashboardBridge(
        pspace,
        FakeTypes,
        mapping,
        history_limit=8,
        poll_seconds=1.0,
        diagnosis_enabled=False,
        qa_db_path=ROOT / "logs" / "unused_billboard_bridge_test.sqlite3",
        snapshot_interval_seconds=0,
        source_label="fixture:8889",
    )

    frame = bridge.read_frame()

    assert frame["type"] == "tick"
    assert len(frame["values"]) == 157
    assert len(frame["point_meta"]) == 133
    assert set(frame["point_meta"]) == set(bridge_module.BILLBOARD_SENSOR_IDS)
    assert frame["data_quality"]["billboard_expected"] == 133
    assert frame["data_quality"]["billboard_mapped"] == 133
    assert frame["data_quality"]["billboard_missing"] == []
    assert frame["values"]["T_throat_A"] is not None
    assert frame["values"]["P_static_lower_A"] is not None
    assert frame["values"]["P_static_upper_F"] is not None
    assert frame["values"]["PCI_previous_hour"] is not None
    assert frame["values"]["BlastEnergy"] is not None
    assert frame["values"]["BlastSpeedStd"] is not None
    assert frame["values"]["BlastSpeedActual"] is not None
    assert frame["values"]["CO2_top"] is not None
    assert frame["values"]["CO_top"] is not None
    assert frame["values"]["H2_top"] is not None
    for sensor_id in (
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
        assert frame["values"][sensor_id] is not None
    assert frame["point_meta"]["P_static_middle_C"] == {
        "timestamp": "2026/07/26 12:00:05.000",
        "quality": "Good",
    }
    assert all("tag" not in item for item in frame["point_meta"].values())
    assert pspace.batch_sizes == [100, 52]
