from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def read(relative: str) -> str:
    return (ROOT / relative).read_text(encoding="utf-8")


def test_guarded_deployer_is_one_file_pwsh7_and_protects_all_ports() -> None:
    source = read("tools/remote_guarded_deploy_8093_guest_ui_recovery.ps1")
    assert "PowerShell 7 Core or later is required" in source
    assert "Global\\BFV4PreviewProxy8093Deployment" in source
    assert "$Changes.Count -ne 1" in source
    assert "frontend_dashboard_v3.server.html" in source
    assert "rollback_applied = $false" in source
    assert "guard_restored = $true" in source
    for port in (8094, 8768, 8770, 5432, 11434, 8892):
        assert str(port) in source
    assert "powershell.exe" not in source


def test_git_save_stages_only_the_dashboard_after_runtime_acceptance() -> None:
    source = read("tools/remote_record_8093_guest_ui_git_version.ps1")
    assert "git add ." not in source
    assert "git add -A" not in source
    assert "add -- $RelativePath" in source
    assert "diff --cached --name-only" in source
    assert "fix: restore anonymous 8093 assistant UI" in source
    assert "Guest bootstrap failed after Git save" in source


def test_artifact_builder_excludes_unrelated_execution_trace() -> None:
    source = read("tools/build_8093_guest_frontend_recovery_artifact.py")
    assert "excluded_unrelated_execution_trace" in source
    assert 'if "function qaMergeExecutionTrace" in artifact' in source
    assert "production baseline mismatch" in source
