import unittest

from tools.patch_8094_cad_bottom_band import MARKER, STYLE_ID, patch_page


BASE_PAGE = """<!doctype html>
<html><head><style id=\"ops-cad-ghost-bands-fix\"></style></head>
<body>
<script>/* OPS-8093-CAD-GHOST-BANDS-FIX */</script>
</body></html>"""


class CadBottomBandPatchTests(unittest.TestCase):
    def test_inserts_scoped_bottom_zero_override(self):
        patched, changed = patch_page(BASE_PAGE)

        self.assertTrue(changed)
        self.assertIn(MARKER, patched)
        self.assertIn(f'style.id = "{STYLE_ID}"', patched)
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

    def test_rejects_unrelated_page(self):
        with self.assertRaises(ValueError):
            patch_page("<html><body></body></html>")


if __name__ == "__main__":
    unittest.main()
