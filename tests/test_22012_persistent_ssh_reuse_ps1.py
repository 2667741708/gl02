from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
REMOTE_PROBE = ROOT / "tools" / "remote_probe_22012_persistent_session.ps1"
LOCAL_VERIFY = ROOT / "tools" / "verify_22012_persistent_ssh_reuse.ps1"


def test_remote_probe_requires_pwsh7_and_emits_utf8_contract() -> None:
    text = REMOTE_PROBE.read_text(encoding="utf-8")
    assert "$PSVersionTable.PSEdition -ne 'Core'" in text
    assert "[Text.UTF8Encoding]::new($false)" in text
    assert "bf.remote.pwsh-file-probe.v1" in text


def test_local_verifier_runs_same_independent_script_twice() -> None:
    text = LOCAL_VERIFY.read_text(encoding="utf-8")
    assert "Invoke-ReusedProbe -Label 'reuse-1'" in text
    assert "Invoke-ReusedProbe -Label 'reuse-2'" in text
    assert "'--script', $ProbeScript" in text
    assert "independent_utf8_ps1_via_pwsh_file_twice" in text
    assert "connection_id" in text
    assert "request_count" in text


def test_benchmark_is_local_and_never_restarts_production() -> None:
    text = LOCAL_VERIFY.read_text(encoding="utf-8")
    assert "LOCALAPPDATA" in text
    assert "production_write_performed = $false" in text
    assert "service_restart_performed = $false" in text
    assert "Stop-Service" not in text
    assert "Restart-Service" not in text
