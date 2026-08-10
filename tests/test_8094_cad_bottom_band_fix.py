import unittest

from tools.patch_8094_cad_bottom_band import MARKER, REVISION_MARKER, STYLE_ID, patch_page


BASE_PAGE = """<!doctype html>
<html><head><style id=\"ops-cad-ghost-bands-fix\"></style></head>
<body>
<script>/* OPS-8093-CAD-GHOST-BANDS-FIX */</script>
</body></html>"""

LEGACY_PAGE = BASE_PAGE.replace(
    "</body>",
    f"""<!-- {MARKER}: keep the 8094 CAD canvas flush with the stage bottom. -->
<script>(function () {{ window.__BF_CAD_BOTTOM_BAND_FIX_20260804__ = true; }})();</script>
</body>""",
)


class CadBottomBandPatchTests(unittest.TestCase):
    def test_inserts_scoped_bottom_zero_override(self):
        patched, changed = patch_page(BASE_PAGE)

        self.assertTrue(changed)
        self.assertIn(MARKER, patched)
        self.assertIn(REVISION_MARKER, patched)
        self.assertIn(f'style.id = "{STYLE_ID}"', patched)
        self.assertIn(".overview-furnace-panel-v12 > .panel-body", patched)
        self.assertIn("padding-bottom: 0 !important", patched)
        self.assertIn("inset: 2% 24% 0 24% !important", patched)
        self.assertIn("inset: 4% 24% 0 24% !important", patched)
        self.assertIn("bottom: 0 !important", patched)
        self.assertEqual(patched.count(MARKER), 1)

    def test_is_idempotent(self):
        once, changed_once = patch_page(BASE_PAGE)
        twice, changed_twice = patch_page(once)

        self.assertTrue(changed_once)
        self.assertFalse(changed_twice)
        self.assertEqual(once, twice)

    def test_upgrades_legacy_stage_only_patch_to_panel_body_fix(self):
        patched, changed = patch_page(LEGACY_PAGE)

        self.assertTrue(changed)
        self.assertIn(REVISION_MARKER, patched)
        self.assertIn("padding-bottom: 0 !important", patched)
        self.assertNotIn("window.__BF_CAD_BOTTOM_BAND_FIX_20260804__ = true", patched)
        self.assertEqual(patched.count(MARKER), 1)

    def test_rejects_unrelated_page(self):
        with self.assertRaises(ValueError):
            patch_page("<html><body></body></html>")


if __name__ == "__main__":
    unittest.main()
