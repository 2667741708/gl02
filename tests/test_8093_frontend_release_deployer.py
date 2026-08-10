import importlib.util
import json
import tempfile
import unittest
import zipfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BUILDER = ROOT / "tools" / "build_8093_frontend_release.py"
DEPLOYER = ROOT / "tools" / "remote_guarded_deploy_8093_frontend_release.ps1"


def load_builder():
    spec = importlib.util.spec_from_file_location("build_8093_frontend_release", BUILDER)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


class FrontendReleaseBuilderTests(unittest.TestCase):
    def test_release_contains_page_model_and_manifest(self):
        module = load_builder()
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "release.zip"
            result = module.build_release("20260806_170000_no_sim_133_r1", output)
            self.assertTrue(output.is_file())
            self.assertEqual(result["release_id"], "20260806_170000_no_sim_133_r1")
            with zipfile.ZipFile(output) as archive:
                names = set(archive.namelist())
                self.assertIn("release-manifest.json", names)
                self.assertIn("payload/frontend_dashboard_v3.server.html", names)
                self.assertIn("payload/models/GL02_FURNACE_BODY_R1.glb", names)
                manifest = json.loads(archive.read("release-manifest.json"))
            self.assertFalse(manifest["deployment_mutex_required"])
            self.assertTrue(any(item["mode"] == "verify_only" for item in manifest["files"]))

    def test_deployer_has_rollback_downgrade_and_isolation_without_mutex(self):
        script = DEPLOYER.read_text(encoding="utf-8")
        self.assertIn("downgrade rejected", script)
        self.assertIn("rollbackApplied", script)
        self.assertIn("BFV4PreviewProxy8093HealthCheck", script)
        self.assertIn("protected PID changed", script)
        self.assertIn("deployment_mutex_used = $false", script)
        self.assertNotIn("Threading.Mutex", script)
        self.assertNotIn("WaitOne", script)


if __name__ == "__main__":
    unittest.main()
