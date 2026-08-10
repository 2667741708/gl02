from pathlib import Path
import unittest

from tools.patch_8094_cad_bottom_band import MARKER, REVISION_MARKER, patch_page


ROOT = Path(__file__).resolve().parents[1]


class GuardedCadBottomBandTests(unittest.TestCase):
    def test_shared_patcher_supports_8093_page_contract(self):
        source = """<html><head><style id=\"ops-cad-ghost-bands-fix\"></style></head>
        <body><script>/* OPS-8093-CAD-GHOST-BANDS-FIX */</script></body></html>"""
        patched, changed = patch_page(source)

        self.assertTrue(changed)
        self.assertIn(MARKER, patched)
        self.assertIn(REVISION_MARKER, patched)
        self.assertIn("padding-bottom: 0 !important", patched)
        self.assertIn("bottom: 0 !important", patched)

    def test_guarded_deployer_preserves_8768_and_8094(self):
        script = (ROOT / "tools" / "remote_guarded_deploy_8093_cad_bottom_band.ps1").read_text(encoding="utf-8")

        self.assertIn("manage_22012_managed_services.ps1", script)
        self.assertIn("22012_BFV4PreviewProxy8093.json", script)
        self.assertIn('-Action stop', script)
        self.assertIn('-Action start', script)
        self.assertIn("finally", script)
        self.assertIn("pid_8768_unchanged", script)
        self.assertIn("protected_8094_hashes_unchanged", script)
        self.assertIn("$serviceBefore.Status.ToString()", script)
        self.assertIn('$task8094After.State.ToString() -eq "Running"', script)
        self.assertIn("$isolationFailures", script)
        self.assertIn("pid_before", script)
        self.assertIn("hashes_after", script)
        self.assertIn(MARKER, script)
        self.assertIn(REVISION_MARKER, script)

    def test_8094_restart_requires_bottom_band_marker(self):
        script = (ROOT / "tools" / "restart_22012_8094_preview.ps1").read_text(encoding="utf-8")

        self.assertIn(MARKER, script)
        self.assertIn(REVISION_MARKER, script)
        self.assertIn("HasCadBottomBandFix", script)
        self.assertIn("Process8093Unchanged", script)
        self.assertIn("Stop-Process -Id $stillListening.OwningProcess -Force", script)
        self.assertIn("Process8094Changed", script)
        self.assertIn("RemovedOrphanPids", script)
        self.assertIn("Invoke-HttpWithRetry", script)


if __name__ == "__main__":
    unittest.main()
