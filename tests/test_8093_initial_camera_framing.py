from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from tools.remote_deploy_8093_initial_camera_framing import CAMERA_TAG, deploy, patch_page


ROOT = Path(__file__).resolve().parents[1]
CAMERA = ROOT / "高炉前端数据" / "assets" / "bf3d-surface-camera-guard-8093.js"


class InitialCameraFramingContractTest(unittest.TestCase):
    def test_closer_fit_keeps_furnace_collision_radius(self) -> None:
        source = CAMERA.read_text(encoding="utf-8")
        self.assertIn('SCHEMA = "bf3d.camera.overview-only.8093.v4"', source)
        self.assertIn("OVERVIEW_FIT_MARGIN = 1.0", source)
        self.assertIn("OVERVIEW_ORBIT_MARGIN = 1.12", source)
        self.assertNotIn("Math.sin(limitingHalfFov) * 1.08", source)
        self.assertIn("viewer.controls.minDistance = fullOrbitRadius", source)
        self.assertIn('host.dataset.initialFraming = "closer-whole-furnace-r1"', source)

    def test_page_patch_updates_only_the_camera_tag(self) -> None:
        source = (
            '<script type="module" src="assets/bf3d-physical-point-filter-8093.js?v=keep"></script>\n'
            '<script type="module" src="assets/bf3d-surface-camera-guard-8093.js?v=old"></script>\n'
        )
        patched = patch_page(source)
        self.assertIn(CAMERA_TAG, patched)
        self.assertIn("bf3d-physical-point-filter-8093.js?v=keep", patched)

    def test_deploy_protects_model_and_other_runtime_assets(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            frontend = root / "frontend"
            assets = frontend / "assets"
            models = frontend / "models"
            assets.mkdir(parents=True)
            models.mkdir()
            page = frontend / "frontend_dashboard_v3.server.html"
            page.write_text(
                '<script type="module" src="assets/bf3d-surface-camera-guard-8093.js?v=old"></script>',
                encoding="utf-8",
            )
            (assets / "bf3d-surface-camera-guard-8093.js").write_text("old-camera", encoding="utf-8")
            protected = {
                frontend / "frontend_dashboard_v3.8094_preview.server.html": "8094-page",
                assets / "bf3d-furnace-body-billboard-adapter.js": "adapter",
                assets / "bf3d-physical-point-filter-8093.js": "filter",
                assets / "bf3d-tooltip-stable-hover-8093.js": "hover",
                assets / "bf3d-furnace-summary-readability-8093.css": "summary-css",
                assets / "bf3d-surface-camera-guard-8094.js": "8094-camera",
                models / "gl02_blast_furnace.glb": "controlled-model",
            }
            for path, content in protected.items():
                path.write_text(content, encoding="utf-8")

            result = deploy(root, CAMERA)

            self.assertTrue(result["deployed"])
            self.assertTrue(result["protected_unchanged"])
            self.assertTrue(result["min_distance_unchanged"])
            self.assertEqual(result["expected_linear_scale_gain_percent"], 8.0)
            for path, content in protected.items():
                self.assertEqual(path.read_text(encoding="utf-8"), content)


if __name__ == "__main__":
    unittest.main()
