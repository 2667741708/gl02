"""Deployment contracts for the isolated 8094 multi-condition preview."""

from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PATCHER_PATH = ROOT / "tools" / "patch_8094_multi_condition_review.py"
SOURCE_PATH = ROOT / "高炉前端数据" / "frontend_dashboard_v3.server.html"


def load_patcher():
    spec = importlib.util.spec_from_file_location("patch_8094_multi_condition_review", PATCHER_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader
    spec.loader.exec_module(module)
    return module


class Patch8094MultiConditionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.patcher = load_patcher()
        cls.source = SOURCE_PATH.read_text(encoding="utf-8")

    def legacy_target(self) -> str:
        block = self.patcher.extract_feature_block(self.source)
        target = self.source.replace(block.replace(
            f"    /* {self.patcher.REQ_MARKER} */\n    /* {self.patcher.DEPLOY_MARKER} */",
            f"    /* {self.patcher.REQ_MARKER} */",
            1,
        ), self.patcher.LEGACY_ASSIGNMENT, 1)
        self.assertNotIn(self.patcher.REQ_MARKER, target)
        markers = ["<!-- 8094-ONLY-SENTINEL -->"]
        markers.extend(
            f"<!-- {marker} -->"
            for marker in self.patcher.REQUIRED_BASELINE_MARKERS
            if marker not in target
        )
        return target.replace("</head>", "".join(markers) + "</head>", 1)

    def test_patch_preserves_8094_content_and_switches_preview_ws(self) -> None:
        patched, report = self.patcher.patch_text(self.legacy_target(), self.source)
        self.assertEqual(report["mode"], "insert")
        self.assertIn("8094-ONLY-SENTINEL", patched)
        self.assertIn(self.patcher.DEPLOY_MARKER, patched)
        self.assertIn(self.patcher.WS_8769, patched)
        self.assertNotIn(self.patcher.WS_8768, patched)

    def test_patch_is_idempotent(self) -> None:
        first, _ = self.patcher.patch_text(self.legacy_target(), self.source)
        second, report = self.patcher.patch_text(first, self.source)
        self.assertEqual(report["mode"], "replace")
        self.assertEqual(first, second)

    def test_patch_can_keep_shared_ws_8768_for_dual_port_sync(self) -> None:
        patched, report = self.patcher.patch_text(
            self.legacy_target(), self.source, ws_port=8768
        )
        self.assertEqual(report["default_ws_8768_count"], 1)
        self.assertEqual(report["default_ws_8769_count"], 0)
        self.assertIn(self.patcher.WS_8768, patched)
        self.assertNotIn(self.patcher.WS_8769, patched)

    def test_deploy_scripts_keep_shared_services_protected(self) -> None:
        deploy = (ROOT / "tools" / "remote_deploy_8094_multi_condition_review.ps1").read_text(encoding="utf-8")
        runner = (ROOT / "tools" / "run_22012_8094_ws8769.ps1").read_text(encoding="utf-8")
        self.assertIn("V4PreviewWs8769", deploy)
        self.assertIn("sharedProxySha256", deploy)
        self.assertIn("pid8768Unchanged", deploy)
        self.assertIn('BF_WS_PORT = "8769"', runner)
        self.assertIn("BF_RECOMMENDATION_ENGINE_DIR", runner)


if __name__ == "__main__":
    unittest.main(verbosity=2)
