from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from tools.remote_deploy_8093_dual_camera_modes import NEW_MARKER, OLD_MARKER, deploy


class DualCameraDeploymentTest(unittest.TestCase):
    def test_deploy_replaces_only_8093_files_and_creates_backup(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            data_root = root / "高炉前端数据"
            asset_root = data_root / "assets"
            asset_root.mkdir(parents=True)
            page_8093 = data_root / "frontend_dashboard_v3.server.html"
            page_8094 = data_root / "frontend_dashboard_v3.8094_preview.server.html"
            runtime_8093 = asset_root / "bf3d-surface-camera-guard-8093.js"
            runtime_8094 = asset_root / "bf3d-surface-camera-guard-8094.js"
            payload = root / "payload.js"
            page_8093.write_text(f"<script src='{OLD_MARKER}'></script>", encoding="utf-8")
            page_8094.write_text("8094-page-baseline", encoding="utf-8")
            runtime_8093.write_text("8093-old-runtime", encoding="utf-8")
            runtime_8094.write_text("8094-shared-runtime-baseline", encoding="utf-8")
            payload.write_text(
                "\n".join(
                    (
                        "bf3d.camera.dual-mode.8093.v2",
                        "fullOrbitRadius",
                        "surfaceAtCameraAzimuth",
                        "dynamic-azimuth-shell-raycast",
                        "focusById(id)",
                        "exitFocus",
                    )
                ),
                encoding="utf-8",
            )

            result = deploy(root, payload)

            self.assertTrue(result["deployed"])
            self.assertTrue(result["8094_unchanged"])
            self.assertIn(NEW_MARKER, page_8093.read_text(encoding="utf-8"))
            self.assertEqual(page_8094.read_text(encoding="utf-8"), "8094-page-baseline")
            self.assertEqual(
                runtime_8094.read_text(encoding="utf-8"),
                "8094-shared-runtime-baseline",
            )
            self.assertIn(
                "bf3d.camera.dual-mode.8093.v2",
                runtime_8093.read_text(encoding="utf-8"),
            )
            self.assertTrue(Path(result["backup"]).is_dir())


if __name__ == "__main__":
    unittest.main()
