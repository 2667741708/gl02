from __future__ import annotations

import json
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
TOOLS = ROOT / "tools"
MIGRATION = TOOLS / "remote_migrate_8093_runtime_to_pwsh7.ps1"
PROBE = TOOLS / "remote_probe_8093_pwsh7_runtime_migration.ps1"
CONFIG = TOOLS / "service_configs" / "22012_BFV4PreviewProxy8093.json"


def test_local_pwsh7_migration_contract_verifier_passes() -> None:
    result = subprocess.run(
        [
            "pwsh.exe",
            "-NoLogo",
            "-NoProfile",
            "-File",
            str(TOOLS / "verify_8093_pwsh7_runtime_migration.ps1"),
        ],
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert json.loads(result.stdout)["ok"] is True


def test_migration_is_single_target_hash_bound_and_rollback_capable() -> None:
    text = MIGRATION.read_text(encoding="utf-8")
    assert "ops.8093.pwsh7-runtime-migration.operation.v1" in text
    assert "AllowedTargets" in text
    assert "ExpectedTargetSha256" in text
    assert "ExpectedStagedSha256" in text
    assert "Global\\BFV4PreviewProxy8093Deployment" in text
    assert "Export-ScheduledTask" in text
    assert "Register-ScheduledTask" in text
    assert "Restore-FromManifest" in text
    assert "protected_before" in text
    assert "protected_after" in text
    for port in (8093, 8768, 8094, 8770, 5432, 8892, 11434):
        assert str(port) in text


def test_old_tasks_are_exact_and_probe_is_read_only() -> None:
    migration = MIGRATION.read_text(encoding="utf-8")
    probe = PROBE.read_text(encoding="utf-8")
    assert "task_path = '\\'" in migration
    assert "task_name = 'BlastFurnaceV3Proxy8093'" in migration
    assert "task_name = 'BlastFurnace8093Proxy_NewProject'" in migration
    assert "run_proxy_8093.ps1" in migration
    assert "run_proxy_8093_db.ps1" in migration
    for forbidden in (
        "Disable-ScheduledTask",
        "Set-ScheduledTask",
        "Register-ScheduledTask",
        "Stop-Service",
        "Start-Service",
        "Restart-Service",
        "Remove-Item",
    ):
        assert forbidden not in probe


def test_service_config_documents_live_patch_only_pwsh7_contract() -> None:
    config = json.loads(CONFIG.read_text(encoding="utf-8"))
    assert config["serviceName"] == "BFV4PreviewProxy8093"
    assert config["runnerShell"] == "C:/Program Files/PowerShell/7/pwsh.exe"
    assert config["migrationPolicy"]["liveConfigIsAuthoritative"] is True
    assert config["migrationPolicy"]["doNotOverwriteProductionConfig"] is True
    identities = {(item["path"], item["name"]) for item in config["legacyTasks"]}
    assert ("\\", "BlastFurnaceV3Proxy8093") in identities
    assert ("\\", "BlastFurnace8093Proxy_NewProject") in identities
