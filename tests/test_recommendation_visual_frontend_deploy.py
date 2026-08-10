from __future__ import annotations

import importlib.util
import json
import zipfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BUILDER = ROOT / "tools" / "build_8093_8094_recommendation_visual_frontend.py"
DEPLOYER = ROOT / "tools" / "remote_deploy_8093_8094_recommendation_visual_frontend.ps1"


def _load_builder():
    spec = importlib.util.spec_from_file_location("recommendation_visual_builder", BUILDER)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_builder_creates_hash_bound_frontend_only_payload(tmp_path: Path) -> None:
    module = _load_builder()
    output = tmp_path / "visual-payload"
    report = module.build(output)
    archive = Path(report["archive"])
    assert archive.is_file()
    with zipfile.ZipFile(archive) as bundle:
        names = set(bundle.namelist())
        assert names == {
            "manifest.json",
            "source/frontend_dashboard_v3.server.html",
            "tools/patch_8094_multi_condition_review.py",
        }
        manifest = json.loads(bundle.read("manifest.json").decode("utf-8"))
    assert manifest["schema_version"] == "recommendation_visual_frontend_manifest.v1"
    assert manifest["service_restart_required"] is False
    assert manifest["shared_ws_port"] == 8768
    assert manifest["core_evidence_count"] == 19


def test_remote_deployer_is_hot_update_only_and_fails_closed() -> None:
    source = DEPLOYER.read_text(encoding="utf-8")
    assert "Install-FileAtomic $stage8094 $page8094" in source
    assert "Install-FileAtomic $stage8093 $page8093" in source
    assert source.index("Install-FileAtomic $stage8094 $page8094") < source.index(
        "Install-FileAtomic $stage8093 $page8093"
    )
    assert "serviceRestarted = $false" in source
    assert "pid8768Unchanged" in source
    assert "pid8093Unchanged" in source
    assert "pid8094Unchanged" in source
    assert "Frontend visual deployment failed; installed pages were rolled back" in source
    assert "Stop-Service" not in source
    assert "Start-Service" not in source
    assert "Remove-Item -LiteralPath $targetEngine" not in source
