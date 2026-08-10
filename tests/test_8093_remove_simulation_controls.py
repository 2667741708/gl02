from __future__ import annotations

import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from tools.patch_local_8093_remove_simulation_controls import (
    BLOCK_IDS,
    PRESERVED_ASSETS,
    REMOVED_LINKS,
    REMOVED_SCRIPTS,
    REQ_ID,
    patch_text,
)


class RemoveSimulationControlsTest(unittest.TestCase):
    def test_removes_controls_review_and_simulation_but_preserves_runtime(self) -> None:
        blocks = "\n".join(
            f'<script id="{element_id}">window.bad=true;</script>'
            for element_id in BLOCK_IDS
        )
        source = "\n".join(
            [
                "<html><head>",
                *REMOVED_LINKS,
                "</head><body>",
                blocks,
                *REMOVED_SCRIPTS,
                *[f'<script src="assets/{asset}"></script>' for asset in PRESERVED_ASSETS],
                "  <!-- REQ-BF3D-LOCAL-133-BILLBOARD-PREVIEW-20260806 -->",
                "</body></html>",
            ]
        )
        output, _ = patch_text(source)
        self.assertIn(REQ_ID, output)
        for marker in (*REMOVED_LINKS, *REMOVED_SCRIPTS, *BLOCK_IDS):
            self.assertNotIn(marker, output)
        for asset in PRESERVED_ASSETS:
            self.assertIn(asset, output)

    def test_current_local_page_has_no_removed_runtime(self) -> None:
        page = (
            ROOT / "高炉前端数据" / "frontend_dashboard_v3.server.html"
        ).read_text(encoding="utf-8")
        updated, _ = patch_text(page)
        for marker in (*REMOVED_LINKS, *REMOVED_SCRIPTS, *BLOCK_IDS):
            self.assertNotIn(marker, updated)
        for asset in PRESERVED_ASSETS:
            self.assertIn(asset, updated)


if __name__ == "__main__":
    unittest.main()
