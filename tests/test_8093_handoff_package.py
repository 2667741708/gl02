import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MANIFEST_PATH = ROOT / "tools" / "handoff" / "8093_handoff_manifest.json"


def load_manifest():
    return json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))


def test_handoff_manifest_has_supported_schema_and_required_surfaces():
    manifest = load_manifest()

    assert manifest["schema"] == "bf.8093.handoff-source-manifest.v1"
    assert ".codex/skills/deploy-8093-guarded-update" in manifest["includeDirectories"]
    assert "tools/remote_22012_session.py" in manifest["includeFiles"]
    assert "tools/service_configs/22012_BFV4PreviewProxy8093.json" in manifest["includeFiles"]
    assert "高炉前端数据/frontend_dashboard_v3.server.html" in manifest["includeFiles"]


def test_handoff_manifest_sources_exist_and_are_unique():
    manifest = load_manifest()
    files = manifest["includeFiles"]
    directories = manifest["includeDirectories"]

    assert len(files) == len(set(files))
    assert len(directories) == len(set(directories))
    assert all((ROOT / item).is_file() for item in files)
    assert all((ROOT / item).is_dir() for item in directories)
    assert (ROOT / manifest["readmeSource"]).is_file()


def test_handoff_manifest_excludes_credentials_and_runtime_evidence():
    manifest = load_manifest()
    selected = [item.replace("\\", "/").lower() for item in manifest["includeFiles"]]

    assert not any("数据库账号配置说明.md" in item for item in selected)
    assert not any("imes_web.local.env" in item for item in selected)
    assert not any("/logs/" in f"/{item}/" for item in selected)
    assert not any("/backups/" in f"/{item}/" for item in selected)
    assert not any(item.endswith((".env", ".key", ".pem", ".pfx", ".p12")) for item in selected)


def test_gitignore_covers_common_local_backup_variants_and_package_output():
    gitignore = (ROOT / ".gitignore").read_text(encoding="utf-8")

    for pattern in ("*.backup", "*.backup_*", "*.old", "*.orig", "*.save", "*~"):
        assert pattern in gitignore
    assert "/handoff_packages/" in gitignore
