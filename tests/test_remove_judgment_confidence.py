from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "tools" / "patch_remove_judgment_confidence.py"
SPEC = importlib.util.spec_from_file_location("patch_remove_judgment_confidence", MODULE_PATH)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class JudgmentConfidenceRemovalTests(unittest.TestCase):
    def test_canonical_page_has_no_visible_label(self) -> None:
        page = (
            ROOT / "高炉前端数据" / "frontend_dashboard_v3.server.html"
        ).read_text(encoding="utf-8")
        self.assertNotIn(MODULE.LABEL, page)
        self.assertIn(MODULE.MARKER, page)
        self.assertIn(
            '<div className="cockpit-decision-meta"><span>建议：', page
        )

    def test_balanced_jsx_blocks_are_removed_without_losing_sibling(self) -> None:
        source = """<body><div className=\"confidence\"><span>判断把握</span><div className=\"bar\"><div className=\"bar-fill\"></div></div><span>100%</span></div><span>建议：15 min 复查</span></body>"""
        patched, counts = MODULE.patch_text(source)
        self.assertNotIn(MODULE.LABEL, patched)
        self.assertNotIn("100%", patched)
        self.assertIn("建议：15 min 复查", patched)
        self.assertEqual(counts["confidence_blocks"], 1)

    def test_patch_is_idempotent(self) -> None:
        source = f"<body><span>建议：15 min 复查</span><!-- {MODULE.MARKER} --></body>"
        first, first_counts = MODULE.patch_text(source)
        second, second_counts = MODULE.patch_text(first)
        self.assertEqual(first, second)
        self.assertFalse(first_counts["changed"])
        self.assertFalse(second_counts["changed"])


if __name__ == "__main__":
    unittest.main()
