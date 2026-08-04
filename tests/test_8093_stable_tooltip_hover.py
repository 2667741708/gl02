from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from tools.remote_deploy_8093_stable_tooltip_hover import (
    HOVER_ASSET,
    HOVER_TAG,
    PREAMBLE_MARKER,
    deploy,
    patch_page,
)


ROOT = Path(__file__).resolve().parents[1]
HOVER = ROOT / "高炉前端数据" / "assets" / "bf3d-tooltip-stable-hover-8093.js"


def fixture_page() -> str:
    return """
<html><body>
<script>
function cadSensorTooltip(buf, id) { return `${id}`; }
const viewerApi = { THREE, camera, renderer };
window.__BF_RENDER_APP__ && window.__BF_RENDER_APP__();
(function () { if (window.__BF_CAD_TOOLTIP_SMOOTH_COORD_FIX__) return; })();
(function () { if (window.__BF_CAD_TOOLTIP_LOCAL_COORD_FIX__) return; })();
</script>
</body></html>
"""


class StableTooltipHoverContractTest(unittest.TestCase):
    def test_runtime_has_one_writer_one_coordinate_space_and_hysteresis(self) -> None:
        source = HOVER.read_text(encoding="utf-8")
        self.assertIn('SCHEMA = "bf3d.tooltip.stable-hover.8093.v1"', source)
        self.assertIn("singleWriter: true", source)
        self.assertIn('coordinateSpace: "viewport-fixed"', source)
        self.assertIn('selectionPolicy: "screen-space-hysteresis"', source)
        self.assertIn("enterRadiusPx: 30", source)
        self.assertIn("exitRadiusPx: 46", source)
        self.assertIn("switchMarginPx: 12", source)
        self.assertIn("switchDwellMs: 140", source)
        self.assertIn("event.stopImmediatePropagation()", source)
        self.assertIn('tip.style.setProperty("position", "fixed", "important")', source)
        self.assertIn('viewer.controls?.addEventListener?.("change", onControlChange)', source)
        self.assertIn("requestAnimationFrame(update)", source)
        self.assertIn("pointFocusEnabled: false", source)
        self.assertIn('if (typeof nextDispose === "function")', source)
        self.assertLess(
            source.index('if (typeof nextDispose === "function")'),
            source.index("installedViewer = viewer"),
        )
        self.assertIn("viewer.camera.position.clone()", source)
        self.assertNotIn("new viewer.THREE", source)
        self.assertIn(
            "window.__BF3D_HOVER_SINGLE_OWNER_8093__ &&\n      viewer &&",
            source,
        )
        self.assertNotIn("if (window.__BF3D_HOVER_SINGLE_OWNER_8093__) {", source)
        self.assertNotIn("setInterval(", source)
        self.assertNotIn("event.clientX +", source)

    def test_runtime_enlarges_8093_billboards_without_changing_shared_adapter(self) -> None:
        source = HOVER.read_text(encoding="utf-8")
        self.assertIn(
            'EMPHASIS_REQ_ID = "REQ-BF3D-8093-BILLBOARD-EMPHASIS-20260802"',
            source,
        )
        self.assertIn("BILLBOARD_SCALE_MULTIPLIER = 1.22", source)
        self.assertIn("function installBillboardEmphasis(viewer, host)", source)
        self.assertIn("setEmphasizedBillboardScale", source)
        self.assertIn("billboardEmphasisScale: BILLBOARD_SCALE_MULTIPLIER", source)
        self.assertIn('host.dataset.billboardEmphasis = "moderate-8093"', source)

    def test_patch_disables_legacy_writers_before_render_and_exposes_buffer(self) -> None:
        patched = patch_page(fixture_page())
        render_call = "window.__BF_RENDER_APP__ && window.__BF_RENDER_APP__();"
        self.assertEqual(patched.count(PREAMBLE_MARKER), 1)
        self.assertLess(patched.index(PREAMBLE_MARKER), patched.index(render_call))
        self.assertIn("window.__BF_CAD_TOOLTIP_SMOOTH_COORD_FIX__ = true", patched)
        self.assertIn("window.__BF_CAD_TOOLTIP_LOCAL_COORD_FIX__ = true", patched)
        self.assertIn("getBuffer: () => bufRef.current", patched)
        self.assertEqual(patched.count(HOVER_ASSET), 1)
        self.assertIn(HOVER_TAG, patched)

    def test_patch_is_idempotent(self) -> None:
        once = patch_page(fixture_page())
        twice = patch_page(once)
        self.assertEqual(twice.count(PREAMBLE_MARKER), 1)
        self.assertEqual(twice.count(HOVER_ASSET), 1)
        self.assertEqual(twice.count("getBuffer: () => bufRef.current"), 1)

    def test_patch_accepts_remote_direct_viewer_with_existing_buffer_getter(self) -> None:
        source = fixture_page().replace(
            "const viewerApi = { THREE, camera, renderer };",
            "window.__BF_CAD_FURNACE_VIEWER = { sensorObjects, camera, renderer, getBuffer: () => bufRef.current };",
        )
        patched = patch_page(source)
        self.assertIn("getBuffer: () => bufRef.current", patched)
        self.assertEqual(patched.count(PREAMBLE_MARKER), 1)
        self.assertEqual(patched.count(HOVER_ASSET), 1)

    def test_deploy_preserves_8094_and_shared_assets(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            frontend = root / "frontend"
            assets = frontend / "assets"
            assets.mkdir(parents=True)
            page_8093 = frontend / "frontend_dashboard_v3.server.html"
            page_8094 = frontend / "frontend_dashboard_v3.8094_preview.server.html"
            shared = assets / "bf3d-furnace-body-billboard-adapter.js"
            camera_8094 = assets / "bf3d-surface-camera-guard-8094.js"
            page_8093.write_text(fixture_page(), encoding="utf-8")
            page_8094.write_text("8094-page-baseline", encoding="utf-8")
            shared.write_text("shared-adapter-baseline", encoding="utf-8")
            camera_8094.write_text("8094-camera-baseline", encoding="utf-8")

            result = deploy(root, HOVER)

            self.assertTrue(result["deployed"])
            self.assertTrue(result["single_writer"])
            self.assertTrue(result["8094_unchanged"])
            self.assertFalse(result["point_focus_enabled"])
            self.assertEqual(page_8094.read_text(encoding="utf-8"), "8094-page-baseline")
            self.assertEqual(shared.read_text(encoding="utf-8"), "shared-adapter-baseline")
            self.assertEqual(camera_8094.read_text(encoding="utf-8"), "8094-camera-baseline")
            self.assertTrue(Path(result["backup"]).is_dir())


if __name__ == "__main__":
    unittest.main()
