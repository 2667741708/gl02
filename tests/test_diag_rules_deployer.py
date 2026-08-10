from __future__ import annotations

import importlib.util
from datetime import datetime
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "tools" / "deploy_diag_rules.py"
REMOTE_SCRIPT = ROOT / "tools" / "remote_deploy_diag_rules.ps1"


def load_module():
    spec = importlib.util.spec_from_file_location("deploy_diag_rules", MODULE_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_bundle_is_exact_and_does_not_include_8768_runtime() -> None:
    module = load_module()
    relative = {path.as_posix() for path in module.BUNDLE_FILES}
    assert len(relative) == 8
    assert "高炉前端数据/智能助手/backend/diag_ai_evidence.py" in relative
    assert "高炉前端数据/智能助手/backend/diagnosis_model_review.py" in relative
    assert "高炉前端数据/assets/bf-diagnosis-manual-score-local.js" in relative
    assert "自动诊断服务/local_pg_ws_bridge.py" not in relative
    assert not any(path.startswith("炉况规则引擎/") for path in relative)


def test_asset_version_is_ascii_cache_key() -> None:
    module = load_module()
    version = module.deployment_version(datetime(2026, 8, 6, 16, 35))
    assert version.startswith("diag-20260806-1635-")
    assert version.isascii()
    assert len(version.rsplit("-", 1)[-1]) == 10


def test_replace_asset_version_updates_all_four_assets(tmp_path: Path) -> None:
    module = load_module()
    proxy = tmp_path / "proxy.py"
    proxy.write_text(
        "\n".join(
            f'<script src="/assets/{asset}?v=old-r1"></script>'
            for asset in module.ASSET_NAMES
        ),
        encoding="utf-8",
    )
    module.replace_asset_version(proxy, "diag-20260806-1635-0123456789")
    text = proxy.read_text(encoding="utf-8")
    assert "old-r1" not in text
    assert text.count("diag-20260806-1635-0123456789") == 4


def test_manifest_has_only_allow_listed_target_pair(tmp_path: Path) -> None:
    module = load_module()
    proxy = tmp_path / "ollama_proxy_server.py"
    proxy.write_text("print('ok')", encoding="utf-8")
    manifest, uploads = module.make_manifest(
        "diag_rules_20260806-1635-0123456789",
        "diag-20260806-1635-0123456789",
        r"C:\Users\Administrator\AppData\Local\Temp\diag_rules_test",
        proxy,
    )
    assert manifest["schema"] == "bf_diag_rules_deploy.v1"
    assert manifest["targets"] == [8093, 8094]
    assert len(manifest["files"]) == 9
    assert len(uploads) == 9
    assert all(".." not in item["targetRelative"] for item in manifest["files"])


def test_remote_script_protects_non_target_services_and_rolls_back() -> None:
    text = REMOTE_SCRIPT.read_text(encoding="utf-8")
    assert "Global\\BFDiagnosisRulesDeployment" in text
    assert "Invoke-8093Manager 'stop'" in text
    assert "Restart-8094" in text
    assert "rollbackApplied" in text
    assert "Install-Atomically $entry.backup" in text
    assert "Assert-ProtectedPids $before @(8768, 8770, 11434)" in text
    assert "Stop-Service -Name 'BFV4PreviewWs8768'" not in text
    assert "Stop-Process -Name python" not in text
    assert 'Wait-HttpMarker 8093 "/api/diagnosis-core-evidence' not in text
    assert 'Wait-HttpMarker 8094 "/api/diagnosis-core-evidence' not in text


def test_cli_requires_apply_for_mutation() -> None:
    text = MODULE_PATH.read_text(encoding="utf-8")
    assert 'parser.add_argument("--apply"' in text
    assert '"mode": "apply" if args.apply else "dry_run"' in text
    assert "if not args.apply:" in text
    assert "check_tcp(args.host, port)" in text
    assert "remote.connect(connection_args(args))" in text
