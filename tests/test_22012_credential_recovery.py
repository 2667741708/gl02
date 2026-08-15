from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
RESTORE = ROOT / "tools" / "restore_22012_ssh_secret_from_windows_credential.ps1"
CONFIGURE = ROOT / "tools" / "configure_22012_reliable_ssh_secret.ps1"


def test_windows_credential_restore_is_fixed_scope_and_secret_safe() -> None:
    source = RESTORE.read_text(encoding="utf-8")
    assert "TERMSRV/10.30.220.12" in source
    assert "ValidateSet('administrator')" in source
    assert "CredReadW" in source
    assert "CredFree" in source
    assert "reliable-ssh-10-30-220-12.password" in source
    assert "ReliableSshPasswordFile" in source
    assert "SourceAcl.AreAccessRulesProtected" in source
    assert "password_value_emitted = $false" in source
    assert "CredentialBlobSize" not in source.split("ConvertTo-Json", 1)[1]
    assert "inheritance:r" in source
    assert "*S-1-5-18:(F)" in source


def test_configure_script_rejects_redaction_marker_on_reuse() -> None:
    source = CONFIGURE.read_text(encoding="utf-8")
    assert "stored in the protected Codex" in source
    assert "Protected password file contains the redaction marker" in source
    assert "password_value_emitted = $false" in source
