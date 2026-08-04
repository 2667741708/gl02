from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from tools.remote_deploy_8093_physical_points_overview import (
    CAMERA_TAG,
    FILTER_TAG,
    deploy,
    patch_page,
)


ROOT = Path(__file__).resolve().parents[1]
FILTER = ROOT / "高炉前端数据" / "assets" / "bf3d-physical-point-filter-8093.js"
CAMERA = ROOT / "高炉前端数据" / "assets" / "bf3d-surface-camera-guard-8093.js"


class PhysicalPointsOverviewContractTest(unittest.TestCase):
    def test_filter_keeps_exact_measured_121_contract(self) -> None:
        source = FILTER.read_text(encoding="utf-8")
        self.assertIn("bf3d.measured-point-filter.8093.v2", source)
        self.assertIn("bodyTemperature: 80", source)
        self.assertIn("staticPressure: 18", source)
        self.assertIn("tapholeTemperature: 2", source)
        self.assertIn("equipmentMeasurement: 21", source)
        self.assertIn("shellPhysical: 100", source)
        self.assertIn("visible: 121", source)
        self.assertIn("excluded: 12", source)
        self.assertIn("viewer.billboardEntries.splice", source)
        self.assertIn("viewer.hitObjects.splice", source)
        self.assertIn('host.dataset.abstractPointCount = "0"', source)
        for point_id in (
            "DP_upper",
            "DP_lower",
            "DP_total",
            "PI",
            "GasUtil",
            "TFT",
            "PCI_set",
            "L",
            "P_top",
            "P_static_20m35",
            "P_static_23m49",
            "P_static_28m98",
        ):
            self.assertIn(f'"{point_id}"', source)

    def test_camera_is_overview_only_and_has_no_point_focus_api(self) -> None:
        source = CAMERA.read_text(encoding="utf-8")
        self.assertIn('SCHEMA = "bf3d.camera.overview-only.8093.v4"', source)
        self.assertIn("OVERVIEW_FIT_MARGIN = 1.0", source)
        self.assertIn("OVERVIEW_ORBIT_MARGIN = 1.12", source)
        self.assertIn("fullOrbitRadius * OVERVIEW_ORBIT_MARGIN", source)
        self.assertIn("bodySphere.radius / Math.sin(limitingHalfFov) * OVERVIEW_FIT_MARGIN", source)
        self.assertIn("pointFocusEnabled: false", source)
        self.assertIn("viewer.controls.target.copy(bodyCenter)", source)
        self.assertIn("viewer.controls.minDistance = fullOrbitRadius", source)
        self.assertIn("viewer.controls.minAzimuthAngle = -Infinity", source)
        self.assertIn("viewer.controls.maxAzimuthAngle = Infinity", source)
        self.assertNotIn("focusById", source)
        self.assertNotIn("focusEntry", source)
        self.assertNotIn("surfaceAtCameraAzimuth", source)

    def test_page_patch_orders_filter_before_camera(self) -> None:
        source = (
            '<script type="module" src="assets/bf3d-furnace-body-billboard-adapter.js?v=old"></script>\n'
            '<script type="module" src="assets/bf3d-surface-camera-guard-8093.js?v=old"></script>\n'
        )
        patched = patch_page(source)
        self.assertIn(FILTER_TAG, patched)
        self.assertIn(CAMERA_TAG, patched)
        self.assertLess(patched.index(FILTER_TAG), patched.index(CAMERA_TAG))

    def test_deploy_changes_only_8093_page_and_assets(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            frontend = root / "frontend"
            assets = frontend / "assets"
            assets.mkdir(parents=True)
            page_8093 = frontend / "frontend_dashboard_v3.server.html"
            page_8094 = frontend / "frontend_dashboard_v3.8094_preview.server.html"
            page_8093.write_text(
                '<script type="module" src="assets/bf3d-furnace-body-billboard-adapter.js?v=old"></script>\n'
                '<script type="module" src="assets/bf3d-surface-camera-guard-8093.js?v=old"></script>\n',
                encoding="utf-8",
            )
            page_8094.write_text("8094-page-baseline", encoding="utf-8")
            (assets / "bf3d-furnace-body-billboard-adapter.js").write_text(
                "shared-adapter-baseline", encoding="utf-8"
            )
            (assets / "bf3d-surface-camera-guard-8094.js").write_text(
                "8094-camera-baseline", encoding="utf-8"
            )
            (assets / "bf3d-surface-camera-guard-8093.js").write_text(
                "old-8093-camera", encoding="utf-8"
            )

            result = deploy(root, FILTER, CAMERA)

            self.assertTrue(result["deployed"])
            self.assertTrue(result["8094_unchanged"])
            self.assertFalse(result["point_focus_enabled"])
            self.assertEqual(page_8094.read_text(encoding="utf-8"), "8094-page-baseline")
            self.assertEqual(
                (assets / "bf3d-furnace-body-billboard-adapter.js").read_text(
                    encoding="utf-8"
                ),
                "shared-adapter-baseline",
            )
            self.assertEqual(
                (assets / "bf3d-surface-camera-guard-8094.js").read_text(
                    encoding="utf-8"
                ),
                "8094-camera-baseline",
            )
            self.assertTrue(Path(result["backup"]).is_dir())


if __name__ == "__main__":
    unittest.main()
