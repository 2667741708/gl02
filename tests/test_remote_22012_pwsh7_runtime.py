from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_remote_exec_defaults_to_staged_pwsh7_file() -> None:
    source = (ROOT / "tools" / "remote_22012_exec.py").read_text(encoding="utf-8")
    assert 'default="pwsh"' in source
    assert r'C:\Program Files\PowerShell\7\pwsh.exe' in source
    assert "-File '{wrapper_path}'" in source
    assert "EncodedCommand" not in source
    assert "import base64" not in source
    assert "sftp.remove(remote_path)" in source


def test_remote_ps1_payload_is_not_inlined_after_wrapper_preamble() -> None:
    source = (ROOT / "tools" / "remote_22012_exec.py").read_text(encoding="utf-8")
    assert 'body = f\'& "{payload_path}"\'' in source
    smoke = (ROOT / "tools" / "remote_smoke_22012_pwsh7.ps1").read_text(encoding="utf-8")
    assert smoke.startswith("[CmdletBinding()]\nparam()")
    assert "冀南钢铁：远端中文执行正常" in smoke


def test_remote_installer_verifies_hash_signature_and_protected_ports() -> None:
    installer = (ROOT / "tools" / "remote_install_22012_pwsh7.ps1").read_text(
        encoding="utf-8"
    )
    assert "D11942DF52FD12470169797ABFA4781D9480EFDC81000BA4FA55A5B921ED8DD0" in installer
    assert "Get-AuthenticodeSignature" in installer
    assert "CN=Microsoft Corporation" in installer
    assert "@(8093, 8094, 8768, 8770, 5432" in installer
    assert "reboot_required" in installer
