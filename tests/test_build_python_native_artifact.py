import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "tools" / "build_python_native_artifact.py"
PS_ENTRYPOINT = ROOT / "tools" / "build_python_native_artifact.ps1"


def _load_module():
    module_spec = importlib.util.spec_from_file_location("native_builder", SCRIPT)
    assert module_spec and module_spec.loader
    module = importlib.util.module_from_spec(module_spec)
    module_spec.loader.exec_module(module)
    return module


def _write_spec(tmp_path: Path, **overrides) -> Path:
    source = tmp_path / "入口.py"
    source.write_text("print('冀南钢铁')\n", encoding="utf-8")
    payload = {
        "schema_version": 1,
        "name": "native-demo",
        "mode": "nuitka-standalone",
        "entrypoint": source.name,
        "output_dir": "stage/native-demo",
        "source_confidential": True,
        "data_files": [],
        "stage_files": [],
        "service": {
            "command": ["native-demo.exe", "--serve"],
            "marker": "native-demo-v1",
            "rollback_target": "backups/native-demo",
        },
    }
    payload.update(overrides)
    spec_path = tmp_path / "native-build.json"
    spec_path.write_text(
        json.dumps(payload, ensure_ascii=False), encoding="utf-8"
    )
    return spec_path


@pytest.mark.parametrize(
    "mode", [
        "nuitka-accelerated",
        "nuitka-standalone",
        "nuitka-module",
        "cython-extension",
    ]
)
def test_plan_only_supports_all_modes_without_compiler(tmp_path: Path, mode: str) -> None:
    spec_path = _write_spec(tmp_path, mode=mode)
    result = subprocess.run(
        [sys.executable, str(SCRIPT), "--spec", str(spec_path), "--plan-only"],
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    assert result.returncode == 0, result.stderr
    plan = json.loads(result.stdout)
    assert plan["plan_only"] is True
    assert plan["mode"] == mode
    assert plan["python"]["target"] == "CPython 3.11 x64"
    assert "command" in plan


def test_default_action_is_plan_and_dependency_install_requires_build(
    tmp_path: Path,
) -> None:
    spec_path = _write_spec(tmp_path)
    default_result = subprocess.run(
        [sys.executable, str(SCRIPT), str(spec_path)],
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    install_result = subprocess.run(
        [sys.executable, str(SCRIPT), str(spec_path), "--install-build-deps"],
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    assert default_result.returncode == 0
    assert json.loads(default_result.stdout)["plan_only"] is True
    assert install_result.returncode != 0
    assert "only valid together with --build" in install_result.stderr


def test_source_confidential_rejects_python_in_stage_manifest(tmp_path: Path) -> None:
    leaked_source = tmp_path / "secret.py"
    leaked_source.write_text("TOKEN = 'not-for-stage'\n", encoding="utf-8")
    stage_manifest = tmp_path / "stage.json"
    stage_manifest.write_text(
        json.dumps(
            {"files": [{"source": "secret.py", "target": "runtime/secret.py"}]}
        ),
        encoding="utf-8",
    )
    spec_path = _write_spec(tmp_path, stage_manifest=stage_manifest.name)
    module = _load_module()
    with pytest.raises(module.NativeBuildError, match="forbids staging Python source"):
        module.load_build_spec(spec_path)


def test_manifest_contains_integrity_runtime_and_service_contract(tmp_path: Path) -> None:
    spec_path = _write_spec(tmp_path, source_confidential=False)
    module = _load_module()
    spec = module.load_build_spec(spec_path)
    artifact_root = spec["output_dir"]
    artifact_root.mkdir(parents=True)
    artifact = artifact_root / "native-demo.exe"
    artifact.write_bytes(b"native-artifact")
    data_source = tmp_path / "data.json"
    data_source.write_text('{"炉号": "1#"}\n', encoding="utf-8")
    spec["data_files"] = [
        {"source": data_source, "target": Path("data/data.json"), "kind": "file"}
    ]

    manifest_path = artifact_root / "native-demo.native-manifest.json"
    manifest = module.create_artifact_manifest(spec, artifact_root, manifest_path)
    assert manifest["tools"].keys() >= {"nuitka", "cython", "setuptools"}
    assert manifest["python"].keys() >= {"abi", "architecture", "bits"}
    assert manifest["source_files"][0]["sha256"] == module.sha256_file(
        spec["entrypoint"]
    )
    assert manifest["outputs"][0]["sha256"] == module.sha256_file(artifact)
    assert manifest["entrypoint"] == "native-demo.exe"
    assert manifest["data_files"][0]["sha256"] == module.sha256_file(data_source)
    assert manifest["service_command"] == ["native-demo.exe", "--serve"]
    assert manifest["service_marker"] == "native-demo-v1"
    assert manifest["rollback_target"] == "backups/native-demo"


def test_source_confidential_refuses_python_found_in_output(tmp_path: Path) -> None:
    spec_path = _write_spec(tmp_path)
    module = _load_module()
    spec = module.load_build_spec(spec_path)
    artifact_root = spec["output_dir"]
    artifact_root.mkdir(parents=True)
    (artifact_root / "native-demo.exe").write_bytes(b"native")
    (artifact_root / "leaked.py").write_text("SECRET = 1\n", encoding="utf-8")
    with pytest.raises(module.NativeBuildError, match="output contains Python source"):
        module.create_artifact_manifest(
            spec, artifact_root, artifact_root / "manifest.json"
        )


def test_accelerated_plan_uses_clean_temporary_compiler_directory(tmp_path: Path) -> None:
    spec_path = _write_spec(tmp_path, mode="nuitka-accelerated")
    module = _load_module()
    spec = module.load_build_spec(spec_path)
    command = module.planned_command(spec)
    assert "--module" not in command
    assert "--standalone" not in command
    assert any(value.endswith(".nuitka-temp") for value in command)


def test_build_refuses_nonempty_output_to_avoid_stale_artifacts(tmp_path: Path) -> None:
    spec_path = _write_spec(tmp_path, source_confidential=False)
    module = _load_module()
    spec = module.load_build_spec(spec_path)
    spec["output_dir"].mkdir(parents=True)
    (spec["output_dir"] / "stale.dll").write_bytes(b"stale")
    with pytest.raises(module.NativeBuildError, match="must be empty"):
        module._run_build(spec)


def test_powershell_entrypoint_enforces_core_utf8_and_delegates() -> None:
    content = PS_ENTRYPOINT.read_text(encoding="utf-8")
    assert "$PSVersionTable.PSEdition -ne 'Core'" in content
    assert "$PSVersionTable.PSVersion.Major -lt 7" in content
    assert "[Text.UTF8Encoding]::new($false)" in content
    assert "$PSDefaultParameterValues['*:Encoding'] = 'utf8'" in content
    assert "build_python_native_artifact.py" in content
    assert "--install-build-deps" in content
    assert "BootstrapPython311" in content
    assert "& $Conda create --prefix" in content
    assert "powershell.exe" not in content.casefold()
