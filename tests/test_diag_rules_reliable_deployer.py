from __future__ import annotations

import importlib.util
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PYTHON_ENTRY = ROOT / "tools" / "deploy_diag_rules_rssh.py"
NODE_TRANSPORT = ROOT / "tools" / "reliable_ssh_22012_cli.mjs"


def load_module():
    spec = importlib.util.spec_from_file_location("deploy_diag_rules_rssh", PYTHON_ENTRY)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_transport_reuses_reliable_ssh_identity_route_and_audit() -> None:
    text = NODE_TRANSPORT.read_text(encoding="utf-8")
    assert "ReliableSshClient" in text
    assert "verifyConfiguredRoute(config)" in text
    assert "verifyIdentity" in text
    assert "createAuditLogger" in text
    assert text.count('client.invoke({ operation: "probe_identity" })') == 1
    assert "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAI" in text
    assert "password-file" in text
    assert "JNgt@" not in text
    assert "password =" not in text.lower()
    assert "password:" not in text.lower()


def test_transport_uploads_one_package_and_executes_exact_argv() -> None:
    text = NODE_TRANSPORT.read_text(encoding="utf-8")
    assert 'operation: "write_file"' in text
    assert 'atomic: true' in text
    assert 'operation: "process"' in text
    assert 'program: "powershell.exe"' in text
    assert 'args: ["-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", launch]' in text
    assert "remote_deploy_diag_rules.ps1" in text


def test_python_entry_uses_reliable_transport_not_paramiko() -> None:
    text = PYTHON_ENTRY.read_text(encoding="utf-8")
    assert "reliable_ssh_22012_cli.mjs" in text
    assert '"transport": "reliable_ssh_10_30_220_12"' in text
    assert '"apply-package"' in text
    assert '"read"' not in text
    assert "paramiko" not in text
    assert "remote_22012_exec" not in text


def test_package_contains_manifest_installer_and_nine_files(tmp_path: Path) -> None:
    module = load_module()
    package, manifest = module.build_package(
        tmp_path,
        "diag-20260806-1635-0123456789",
        "diag_rules_20260806-1635-0123456789",
        r"C:\Users\Administrator\AppData\Local\Temp\diag_rules_test",
    )
    assert package.is_file()
    assert manifest["targets"] == [8093, 8094]
    assert len(manifest["files"]) == 9
    import zipfile

    with zipfile.ZipFile(package) as archive:
        names = set(archive.namelist())
    assert "manifest.json" in names
    assert "remote_deploy_diag_rules.ps1" in names
    assert "build_diag_proxy_payload.py" in names
    assert "build_8093_diag_single_payload.py" in names
    assert len(names) == 13

def test_cli_is_dry_run_without_apply() -> None:
    text = PYTHON_ENTRY.read_text(encoding="utf-8")
    assert 'parser.add_argument("--apply"' in text
    assert "if not args.apply:" in text
    assert "run_transport(" in text
