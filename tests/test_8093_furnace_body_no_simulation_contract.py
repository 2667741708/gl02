from __future__ import annotations

import hashlib
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from tools.patch_8093_furnace_body_no_simulation import (
    ADAPTER_ASSET,
    CAMERA_ASSET,
    CAMERA_ASSET_VERSION,
    FAVICON_MARKER,
    NO_SIM_STYLE_ID,
    patch_page,
)


OLD_ROWS = (
    "['P_static_20m35', '20.35米静压', 'kPa'], ['P_static_23m49', "
    "'23.49米静压', 'kPa'], ['P_static_28m98', '28.98米静压', 'kPa']"
)
OLD_VIEWER = (
    "window.__BF_CAD_FURNACE_VIEWER = { sensorObjects, hitObjects, camera, "
    "renderer, modelUrl: 'models/gl02_blast_furnace.glb', sensorCount: "
    "sensorObjects.length, hitCount: hitObjects.length, mappedCount }"
)
OLD_VIEWER_HOVER = OLD_VIEWER[:-2] + ", hoverRadiusPx: 42 }"


class FurnaceBodyNoSimulationContractTest(unittest.TestCase):
    def test_patch_syncs_viewer_and_omits_simulation_runtime(self) -> None:
        source = (
            "<html><head></head><body>"
            + OLD_ROWS
            + OLD_VIEWER
            + OLD_VIEWER_HOVER
            + "</body></html>"
        )
        expected = hashlib.sha256(source.encode("utf-8")).hexdigest()
        with tempfile.TemporaryDirectory() as temporary:
            page = Path(temporary) / "frontend_dashboard_v3.server.html"
            backup_dir = Path(temporary) / "backups"
            page.write_text(source, encoding="utf-8")
            result = patch_page(page, backup_dir, expected)
            output = page.read_text(encoding="utf-8")
        self.assertEqual(result["viewer_contract_replacements"], 2)
        self.assertIn("scene, model, baseModel: model, controls", output)
        self.assertIn(ADAPTER_ASSET, output)
        self.assertIn(CAMERA_ASSET, output)
        self.assertIn(CAMERA_ASSET_VERSION, output)
        self.assertIn(NO_SIM_STYLE_ID, output)
        self.assertIn(FAVICON_MARKER, output)
        self.assertIn("P_static_upper_F", output)
        self.assertNotIn("assets/bf3d-internal-simulation.js", output)
        self.assertNotIn("assets/bf3d-internal-simulation.css", output)

    def test_8093_camera_entry_uses_independent_overview_only_runtime(self) -> None:
        entry = (
            ROOT
            / "高炉前端数据"
            / "assets"
            / "bf3d-surface-camera-guard-8093.js"
        ).read_text(encoding="utf-8")
        shared = (
            ROOT
            / "高炉前端数据"
            / "assets"
            / "bf3d-surface-camera-guard-8094.js"
        ).read_text(encoding="utf-8")
        self.assertIn('SCHEMA = "bf3d.camera.overview-only.8093.v3"', entry)
        self.assertIn('mode: "overview"', entry)
        self.assertIn("bodySphere.radius + bodySphere.center.distanceTo(bodyCenter) + safetyGap", entry)
        self.assertIn("viewer.controls.target.copy(bodyCenter)", entry)
        self.assertIn("viewer.controls.minAzimuthAngle = -Infinity", entry)
        self.assertIn("viewer.controls.maxAzimuthAngle = Infinity", entry)
        self.assertIn("pointFocusEnabled: false", entry)
        self.assertNotIn("surfaceAtCameraAzimuth", entry)
        self.assertNotIn("focusEntry", entry)
        self.assertNotIn("exitFocus", entry)
        self.assertNotIn("focusById", entry)
        self.assertIn('SAFE_NEAR_PLANE = 0.05', entry)
        self.assertNotIn("__BF3D_SURFACE_CAMERA_GUARD_SCOPE__", entry)
        self.assertNotIn('import("./bf3d-surface-camera-guard-8094.js', entry)
        self.assertIn("PORT_SCOPE", shared)
        self.assertIn("surfaceCameraGuard${PORT_SCOPE}", shared)
        self.assertIn('PORT_SCOPE === "8093" ? 0.05 : null', shared)
        self.assertIn("bf3d.surface-camera-shell-guard.${PORT_SCOPE}.v1", shared)

    def test_dual_camera_harness_uses_production_furnace_body_asset(self) -> None:
        harness = (
            ROOT / "高炉前端数据" / "bf3d_8093_dual_camera_harness.html"
        ).read_text(encoding="utf-8")
        self.assertIn('id:"GL02_FURNACE_BODY_R1"', harness)
        self.assertIn(
            'url:"../PT/高炉3D模型/模型资产库/09_高炉本体133点Billboard_cn/GL02_FURNACE_BODY_R1.glb"',
            harness,
        )
        self.assertIn("bytes:8229120", harness)
        self.assertIn(
            'sha256:"150df18b68f0410b9a168f80c2df34efda86384fc51d37226f81c2acd244ed53"',
            harness,
        )
        self.assertIn('host.dataset.modelAssetVerified="true"', harness)
        self.assertNotIn(
            'new GLTFLoader().loadAsync("./models/gl02_blast_furnace.glb")',
            harness,
        )


if __name__ == "__main__":
    unittest.main()
