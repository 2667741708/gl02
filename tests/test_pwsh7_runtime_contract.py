from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_agents_requires_pwsh7_without_windows_powershell_fallback() -> None:
    agents = (ROOT / "AGENTS.md").read_text(encoding="utf-8")
    assert "PowerShell 7 UTF-8 强制运行时" in agents
    assert "不允许静默回退到 5.1" in agents
    assert "verify_pwsh7_utf8.ps1" in agents


def test_local_core_entrypoints_use_pwsh7() -> None:
    start_script = (ROOT / "start_v3_full.ps1").read_text(encoding="utf-8-sig")
    hidden_runner = (ROOT / "tools" / "run_hidden_ps1.vbs").read_text(encoding="utf-8")
    assert "PSEdition -ne 'Core'" in start_script
    assert 'Start-Process -FilePath "pwsh.exe"' in start_script
    assert "powershell.exe" not in start_script.lower()
    assert r"C:\Program Files\PowerShell\7\pwsh.exe" in hidden_runner
    assert "powershell.exe" not in hidden_runner.lower()


def test_local_start_defaults_to_native_postgresql_without_embedded_credentials() -> None:
    start_script = (ROOT / "start_v3_full.ps1").read_text(encoding="utf-8-sig")
    assert '$env:GL02_LOCAL_PGHOST = "127.0.0.1"' in start_script
    assert '$env:GL02_LOCAL_PGPORT = "18000"' in start_script
    assert '$env:GL02_LOCAL_PGDATABASE = "bf_trend"' in start_script
    assert '$env:GL02_LOCAL_PGUSER = "postgres"' in start_script
    assert "$env:GL02_PGPASSWORD = $env:GL02_LOCAL_PGPASSWORD" in start_script
    assert "BF_USE_EXISTING_PG_ENV" in start_script
    assert "15432" not in start_script
    assert "gl02_local_sync" not in start_script


def test_runtime_verifier_checks_utf8_and_core() -> None:
    verifier = (ROOT / "tools" / "verify_pwsh7_utf8.ps1").read_text(encoding="utf-8")
    assert "$PSVersionTable.PSEdition -ne 'Core'" in verifier
    assert "UTF8Encoding]::new($false)" in verifier
    assert "冀南钢铁_pwsh7_utf8_probe.txt" in verifier
    assert "Language.Parser]::ParseFile" in verifier
    assert "SilentlyContinue" not in verifier


def test_windows_terminal_migrator_defaults_to_pwsh7_without_deleting_ps51() -> None:
    migrator = (ROOT / "tools" / "set_windows_terminal_pwsh7_default.ps1").read_text(
        encoding="utf-8"
    )
    assert r"C:\Program Files\PowerShell\7\pwsh.exe" in migrator
    assert "$settings.defaultProfile = $profileGuid" in migrator
    assert "$profile.hidden = $true" in migrator
    assert "Remove-Item -LiteralPath $settingsPath" not in migrator
