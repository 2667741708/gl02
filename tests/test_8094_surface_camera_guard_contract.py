from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from tools.patch_8094_surface_camera_guard import GUARD_ASSET, REQ_ID, patch_page


GUARD = ROOT / "高炉前端数据" / "assets" / "bf3d-surface-camera-guard-8094.js"


class SurfaceCameraGuardContractTest(unittest.TestCase):
    def test_guard_targets_surface_and_replaces_centre_wheel_dolly(self) -> None:
        source = GUARD.read_text(encoding="utf-8")
        self.assertIn(REQ_ID, source)
        self.assertIn("__BF3D_SURFACE_CAMERA_GUARD_8094__", source)
        self.assertIn('mode: "furnace-surface"', source)
        self.assertIn("viewer.controls.target.copy(surface.target)", source)
        self.assertIn("firstShellHit(from, direction, distance + safetyGap)", source)
        self.assertIn('host.removeEventListener("wheel", viewer.__bf3dWheelZoomHandler, true)', source)
        self.assertIn('host.dataset.wheelZoom = "surface-shell-guard-8094"', source)
        self.assertNotIn("const target = bodyCenter", source)

    def test_page_patcher_is_idempotent_and_backed_up(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            page = root / "frontend_dashboard_v3.8094_preview.server.html"
            backup_dir = root / "backups"
            page.write_text(
                '<script type="module" src="assets/bf3d-furnace-body-billboard-adapter.js"></script>\n'
                '<script type="module" src="assets/bf3d-internal-simulation.js"></script>\n',
                encoding="utf-8",
            )
            first = patch_page(page, backup_dir)
            second = patch_page(page, backup_dir)
            updated = page.read_text(encoding="utf-8")
            self.assertTrue(first["changed"])
            self.assertFalse(second["changed"])
            self.assertEqual(updated.count(GUARD_ASSET), 1)
            self.assertTrue(Path(str(first["backup"])).is_file())


if __name__ == "__main__":
    unittest.main()
