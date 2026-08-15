#!/usr/bin/env python3
"""Build auditable native artifacts from a UTF-8 JSON specification.

REQ-NATIVE-BUILD-001: provide a plan-first, Python 3.11 x64 build entrypoint
for Nuitka standalone/module and Cython extension artifacts.  The tool never
installs build dependencies unless ``--install-build-deps`` is explicit.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import importlib.util
import json
import os
import platform
import shutil
import subprocess
import sys
import sysconfig
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence


SUPPORTED_MODES = {
    "nuitka-accelerated",
    "nuitka-standalone",
    "nuitka-module",
    "cython-extension",
}
MODE_DEPENDENCIES = {
    "nuitka-accelerated": ("Nuitka", "ordered-set", "zstandard"),
    "nuitka-standalone": ("Nuitka", "ordered-set", "zstandard"),
    "nuitka-module": ("Nuitka", "ordered-set", "zstandard"),
    "cython-extension": ("Cython", "setuptools", "wheel"),
}


class NativeBuildError(RuntimeError):
    """Raised for an invalid build specification or unsafe build request."""


def sha256_file(path: Path) -> str:
    """Return the lower-case SHA-256 digest of one file."""

    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _read_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except FileNotFoundError as exc:
        raise NativeBuildError(f"JSON file does not exist: {path}") from exc
    except json.JSONDecodeError as exc:
        raise NativeBuildError(
            f"Invalid JSON in {path} at line {exc.lineno}, column {exc.colno}: {exc.msg}"
        ) from exc


def _write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
        newline="\n",
    )


def _resolve_path(value: str, base_dir: Path) -> Path:
    candidate = Path(os.path.expandvars(os.path.expanduser(value)))
    if not candidate.is_absolute():
        candidate = base_dir / candidate
    return candidate.resolve()


def _safe_stage_target(value: str) -> Path:
    target = Path(value)
    if target.is_absolute() or ".." in target.parts:
        raise NativeBuildError(f"Stage target must be a safe relative path: {value!r}")
    if str(target) in {"", "."}:
        raise NativeBuildError("Stage target must not be empty")
    return target


def _normalise_stage_item(item: Any, base_dir: Path, label: str) -> dict[str, Any]:
    if isinstance(item, str):
        source_text = item
        target_text = Path(item).name
    elif isinstance(item, Mapping):
        source_text = item.get("source") or item.get("path")
        if not isinstance(source_text, str) or not source_text:
            raise NativeBuildError(f"{label} item requires a non-empty 'source'")
        target_text = item.get("target") or Path(source_text).name
    else:
        raise NativeBuildError(f"{label} entries must be strings or objects")

    if not isinstance(target_text, str):
        raise NativeBuildError(f"{label} target must be a string")
    source = _resolve_path(source_text, base_dir)
    if not source.exists():
        raise NativeBuildError(f"{label} source does not exist: {source}")
    target = _safe_stage_target(target_text)
    return {
        "source": source,
        "target": target,
        "kind": "directory" if source.is_dir() else "file",
    }


def _load_stage_manifest(value: Any, base_dir: Path) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, Mapping):
        files = value.get("files", value.get("stage_files", []))
        if not isinstance(files, list):
            raise NativeBuildError("stage_manifest.files must be a list")
        return files
    if not isinstance(value, str):
        raise NativeBuildError("stage_manifest must be a JSON path, object, or list")
    manifest_path = _resolve_path(value, base_dir)
    manifest = _read_json(manifest_path)
    if isinstance(manifest, list):
        return manifest
    if isinstance(manifest, Mapping):
        files = manifest.get("files", manifest.get("stage_files", []))
        if isinstance(files, list):
            return files
    raise NativeBuildError(f"Stage manifest must contain a list of files: {manifest_path}")


def _contains_python_source(path: Path) -> bool:
    if path.is_file():
        return path.suffix.casefold() in {".py", ".pyw"}
    return any(
        child.suffix.casefold() in {".py", ".pyw"}
        for child in path.rglob("*")
        if child.is_file()
    )


def load_build_spec(spec_path: Path) -> dict[str, Any]:
    """Load and validate a build spec, resolving its paths relative to itself."""

    spec_path = spec_path.resolve()
    raw = _read_json(spec_path)
    if not isinstance(raw, Mapping):
        raise NativeBuildError("Build specification root must be a JSON object")

    mode = raw.get("mode")
    if mode not in SUPPORTED_MODES:
        raise NativeBuildError(
            f"Unsupported mode {mode!r}; expected one of {sorted(SUPPORTED_MODES)}"
        )
    entrypoint_text = raw.get("entrypoint") or raw.get("source")
    if not isinstance(entrypoint_text, str) or not entrypoint_text:
        raise NativeBuildError("Build specification requires 'entrypoint' (a .py file)")
    entrypoint = _resolve_path(entrypoint_text, spec_path.parent)
    if not entrypoint.is_file():
        raise NativeBuildError(f"Entrypoint does not exist or is not a file: {entrypoint}")
    if entrypoint.suffix.casefold() not in {".py", ".pyw"}:
        raise NativeBuildError(f"Entrypoint must be a Python source file: {entrypoint}")

    name = raw.get("name") or entrypoint.stem
    if not isinstance(name, str) or not name.strip():
        raise NativeBuildError("Artifact 'name' must be a non-empty string")
    output_dir_text = raw.get("output_dir", f"dist/native/{name}")
    if not isinstance(output_dir_text, str) or not output_dir_text:
        raise NativeBuildError("output_dir must be a non-empty path string")
    output_dir = _resolve_path(output_dir_text, spec_path.parent)

    data_raw = raw.get("data_files", [])
    stage_raw = raw.get("stage_files", raw.get("stage", []))
    if not isinstance(data_raw, list) or not isinstance(stage_raw, list):
        raise NativeBuildError("data_files and stage_files must be lists")
    stage_raw = list(stage_raw) + _load_stage_manifest(
        raw.get("stage_manifest"), spec_path.parent
    )
    data_files = [
        _normalise_stage_item(item, spec_path.parent, "data_files") for item in data_raw
    ]
    stage_files = [
        _normalise_stage_item(item, spec_path.parent, "stage_files") for item in stage_raw
    ]

    source_confidential_value = raw.get(
        "source_confidential", raw.get("source-confidential", False)
    )
    if not isinstance(source_confidential_value, bool):
        raise NativeBuildError("source_confidential must be a JSON boolean")
    source_confidential = source_confidential_value
    if source_confidential:
        for item in data_files + stage_files:
            if _contains_python_source(item["source"]) or item["target"].suffix.casefold() in {
                ".py",
                ".pyw",
            }:
                raise NativeBuildError(
                    "source_confidential forbids staging Python source: "
                    f"{item['source']} -> {item['target']}"
                )
        declared_outputs = raw.get("outputs", [])
        if not isinstance(declared_outputs, list):
            raise NativeBuildError("outputs must be a list when supplied")
        for value in declared_outputs:
            output_value = value.get("path") if isinstance(value, Mapping) else value
            if isinstance(output_value, str) and Path(output_value).suffix.casefold() in {
                ".py",
                ".pyw",
            }:
                raise NativeBuildError(
                    f"source_confidential forbids a Python source output: {output_value}"
                )

    service_raw = raw.get("service", {})
    if not isinstance(service_raw, Mapping):
        raise NativeBuildError("service must be an object")
    service_command = service_raw.get("command", raw.get("service_command", []))
    if isinstance(service_command, str):
        service_command = [service_command]
    if not isinstance(service_command, list) or not all(
        isinstance(value, str) for value in service_command
    ):
        raise NativeBuildError("service.command must be a string or a list of strings")

    build_args = raw.get("build_args", [])
    if not isinstance(build_args, list) or not all(
        isinstance(value, str) for value in build_args
    ):
        raise NativeBuildError("build_args must be a list of strings")

    extra_sources_raw = raw.get("source_files", [])
    if not isinstance(extra_sources_raw, list) or not all(
        isinstance(value, str) and value for value in extra_sources_raw
    ):
        raise NativeBuildError("source_files must be a list of path strings")
    source_files = [entrypoint]
    for value in extra_sources_raw:
        source_path = _resolve_path(value, spec_path.parent)
        if not source_path.is_file():
            raise NativeBuildError(f"Declared source file does not exist: {source_path}")
        if source_path not in source_files:
            source_files.append(source_path)

    module_name = raw.get("module_name", entrypoint.stem)
    if not isinstance(module_name, str) or not module_name.strip():
        raise NativeBuildError("module_name must be a non-empty string")

    return {
        "spec_path": spec_path,
        "name": name.strip(),
        "mode": mode,
        "entrypoint": entrypoint,
        "source_files": source_files,
        "module_name": module_name.strip(),
        "output_dir": output_dir,
        "source_confidential": source_confidential,
        "data_files": data_files,
        "stage_files": stage_files,
        "build_args": build_args,
        "artifact_entrypoint": raw.get("artifact_entrypoint"),
        "service": {
            "command": service_command,
            "marker": service_raw.get("marker", raw.get("service_marker")),
            "rollback_target": service_raw.get(
                "rollback_target", raw.get("rollback_target")
            ),
        },
    }


def python_runtime() -> dict[str, Any]:
    """Describe the active interpreter and whether it matches Python 3.11 x64."""

    bits = 64 if sys.maxsize > 2**32 else 32
    architecture = platform.machine() or platform.architecture()[0]
    compatible = sys.version_info[:2] == (3, 11) and bits == 64
    abi = sysconfig.get_config_var("SOABI") or getattr(
        sys.implementation, "cache_tag", None
    )
    return {
        "implementation": platform.python_implementation(),
        "version": platform.python_version(),
        "abi": abi,
        "cache_tag": getattr(sys.implementation, "cache_tag", None),
        "architecture": architecture,
        "bits": bits,
        "executable": str(Path(sys.executable).resolve()),
        "target": "CPython 3.11 x64",
        "target_compatible": compatible,
    }


def _require_target_runtime(runtime: Mapping[str, Any]) -> None:
    if not runtime["target_compatible"]:
        raise NativeBuildError(
            "Native builds require CPython 3.11 x64; current runtime is "
            f"{runtime['implementation']} {runtime['version']} {runtime['bits']}-bit. "
            "Use --plan-only for validation on a non-build host."
        )


def tool_versions() -> dict[str, str | None]:
    """Return installed build-tool versions without importing build packages."""

    versions: dict[str, str | None] = {}
    for display, distribution in (
        ("nuitka", "Nuitka"),
        ("cython", "Cython"),
        ("setuptools", "setuptools"),
        ("wheel", "wheel"),
        ("ordered-set", "ordered-set"),
        ("zstandard", "zstandard"),
    ):
        try:
            versions[display] = importlib.metadata.version(distribution)
        except importlib.metadata.PackageNotFoundError:
            versions[display] = None
    return versions


def _missing_dependencies(mode: str) -> list[str]:
    return [
        package
        for package in MODE_DEPENDENCIES[mode]
        if importlib.util.find_spec(package.replace("-", "_").lower()) is None
        and importlib.util.find_spec(package.replace("-", "_")) is None
    ]


def ensure_build_dependencies(mode: str, install: bool) -> None:
    """Check mode dependencies, installing them only after explicit opt-in."""

    missing = _missing_dependencies(mode)
    if not missing:
        return
    if not install:
        raise NativeBuildError(
            "Missing build dependencies: "
            + ", ".join(missing)
            + ". Re-run with --install-build-deps to install explicitly."
        )
    subprocess.run(
        [sys.executable, "-m", "pip", "install", *missing],
        check=True,
    )
    remaining = _missing_dependencies(mode)
    if remaining:
        raise NativeBuildError(
            "Build dependencies are still unavailable after installation: "
            + ", ".join(remaining)
        )


def _nuitka_command(spec: Mapping[str, Any]) -> list[str]:
    command = [sys.executable, "-m", "nuitka"]
    if spec["mode"] == "nuitka-standalone":
        command.append("--standalone")
    elif spec["mode"] == "nuitka-module":
        command.append("--module")
    compiler_output = (
        spec["output_dir"] / ".nuitka-temp"
        if spec["mode"] == "nuitka-accelerated"
        else spec["output_dir"]
    )
    command.append(f"--output-dir={compiler_output}")
    if spec["mode"] == "nuitka-standalone":
        for item in spec["data_files"]:
            option = "--include-data-dir" if item["kind"] == "directory" else "--include-data-files"
            command.append(f"{option}={item['source']}={item['target'].as_posix()}")
    command.extend(spec["build_args"])
    command.append(str(spec["entrypoint"]))
    return command


def planned_command(spec: Mapping[str, Any]) -> list[str]:
    """Create the mode-specific command shown by plan-only output."""

    if spec["mode"].startswith("nuitka-"):
        return _nuitka_command(spec)
    return [
        sys.executable,
        "<generated-setup.py>",
        "build_ext",
        "--build-lib",
        str(spec["output_dir"]),
        "--build-temp",
        "<temporary-build-dir>",
        *spec["build_args"],
    ]


def create_plan(spec: Mapping[str, Any]) -> dict[str, Any]:
    """Return a serialisable plan that does not require a compiler."""

    runtime = python_runtime()
    return {
        "schema_version": 1,
        "plan_only": True,
        "name": spec["name"],
        "mode": spec["mode"],
        "spec_path": str(spec["spec_path"]),
        "entrypoint": str(spec["entrypoint"]),
        "output_dir": str(spec["output_dir"]),
        "source_confidential": spec["source_confidential"],
        "python": runtime,
        "tools": tool_versions(),
        "required_build_dependencies": list(MODE_DEPENDENCIES[spec["mode"]]),
        "command": planned_command(spec),
        "data_files": [
            {"source": str(item["source"]), "target": item["target"].as_posix()}
            for item in spec["data_files"]
        ],
        "stage_files": [
            {"source": str(item["source"]), "target": item["target"].as_posix()}
            for item in spec["stage_files"]
        ],
        "service": spec["service"],
    }


def _stage_items(items: Iterable[Mapping[str, Any]], artifact_root: Path) -> None:
    for item in items:
        destination = artifact_root / item["target"]
        destination.parent.mkdir(parents=True, exist_ok=True)
        if item["source"].is_dir():
            shutil.copytree(item["source"], destination, dirs_exist_ok=True)
        else:
            shutil.copy2(item["source"], destination)


def _cython_setup_text(spec: Mapping[str, Any]) -> str:
    module_name = spec["module_name"]
    module_json = json.dumps(module_name, ensure_ascii=False)
    source_json = json.dumps(str(spec["entrypoint"]), ensure_ascii=False)
    return (
        "from setuptools import Extension, setup\n"
        "from Cython.Build import cythonize\n\n"
        f"extensions = [Extension({module_json}, [{source_json}])]\n"
        "setup(ext_modules=cythonize(extensions, language_level=3))\n"
    )


def _run_build(spec: Mapping[str, Any]) -> Path:
    output_dir: Path = spec["output_dir"]
    if output_dir.exists() and any(output_dir.iterdir()):
        raise NativeBuildError(
            f"Output directory must be empty for a reproducible native build: {output_dir}"
        )
    output_dir.mkdir(parents=True, exist_ok=True)
    if spec["mode"].startswith("nuitka-"):
        subprocess.run(_nuitka_command(spec), check=True, cwd=spec["spec_path"].parent)
        if spec["mode"] == "nuitka-accelerated":
            compiler_output = output_dir / ".nuitka-temp"
            candidates = sorted(compiler_output.glob("*.exe"))
            if len(candidates) != 1:
                raise NativeBuildError(
                    f"Could not identify one Nuitka accelerated executable in {compiler_output}"
                )
            destination = output_dir / candidates[0].name
            shutil.copy2(candidates[0], destination)
            shutil.rmtree(compiler_output)
            _stage_items(spec["stage_files"], output_dir)
            return output_dir
        if spec["mode"] == "nuitka-standalone":
            expected = output_dir / f"{spec['entrypoint'].stem}.dist"
            if expected.is_dir():
                artifact_root = expected
            else:
                candidates = sorted(output_dir.glob("*.dist"))
                if len(candidates) != 1:
                    raise NativeBuildError(
                        f"Could not identify one Nuitka standalone output in {output_dir}"
                    )
                artifact_root = candidates[0]
            _stage_items(spec["stage_files"], artifact_root)
            return artifact_root
        _stage_items([*spec["data_files"], *spec["stage_files"]], output_dir)
        return output_dir

    with tempfile.TemporaryDirectory(prefix="native-cython-") as temp_text:
        temp_dir = Path(temp_text)
        setup_path = temp_dir / "setup.py"
        setup_path.write_text(_cython_setup_text(spec), encoding="utf-8", newline="\n")
        command = [
            sys.executable,
            str(setup_path),
            "build_ext",
            "--build-lib",
            str(output_dir),
            "--build-temp",
            str(temp_dir / "build"),
            *spec["build_args"],
        ]
        subprocess.run(command, check=True, cwd=spec["spec_path"].parent)
    _stage_items([*spec["data_files"], *spec["stage_files"]], output_dir)
    return output_dir


def _file_records(root: Path, exclude: Path | None = None) -> list[dict[str, Any]]:
    records = []
    for path in sorted(child for child in root.rglob("*") if child.is_file()):
        if exclude is not None and path.resolve() == exclude.resolve():
            continue
        records.append(
            {
                "path": path.relative_to(root).as_posix(),
                "sha256": sha256_file(path),
                "size": path.stat().st_size,
            }
        )
    return records


def _data_records(spec: Mapping[str, Any]) -> list[dict[str, Any]]:
    records = []
    for item in spec["data_files"]:
        record: dict[str, Any] = {
            "source": str(item["source"]),
            "target": item["target"].as_posix(),
            "kind": item["kind"],
        }
        if item["source"].is_file():
            record["sha256"] = sha256_file(item["source"])
        else:
            record["files"] = _file_records(item["source"])
        records.append(record)
    return records


def create_artifact_manifest(
    spec: Mapping[str, Any], artifact_root: Path, manifest_path: Path
) -> dict[str, Any]:
    """Create the post-build integrity and service handoff manifest."""

    if spec["source_confidential"]:
        leaked = sorted(
            path
            for path in artifact_root.rglob("*")
            if path.is_file() and path.suffix.casefold() in {".py", ".pyw"}
        )
        if leaked:
            joined = ", ".join(str(path) for path in leaked[:5])
            raise NativeBuildError(
                f"source_confidential output contains Python source; refusing manifest: {joined}"
            )

    outputs = _file_records(artifact_root, exclude=manifest_path)
    if not outputs:
        raise NativeBuildError(f"Build produced no files in {artifact_root}")
    source_records = [
        {"path": str(source), "sha256": sha256_file(source)}
        for source in spec["source_files"]
    ]
    entrypoint = spec["artifact_entrypoint"]
    if not entrypoint:
        command = spec["service"]["command"]
        entrypoint = command[0] if command else outputs[0]["path"]
    service = dict(spec["service"])
    payload = {
        "schema_version": 1,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "name": spec["name"],
        "mode": spec["mode"],
        "source_confidential": spec["source_confidential"],
        "python": python_runtime(),
        "tools": tool_versions(),
        "build_spec": {
            "path": str(spec["spec_path"]),
            "sha256": sha256_file(spec["spec_path"]),
        },
        "source_files": source_records,
        "source_sha256": {
            item["path"]: item["sha256"] for item in source_records
        },
        "artifact_root": str(artifact_root.resolve()),
        "outputs": outputs,
        "output_sha256": {item["path"]: item["sha256"] for item in outputs},
        "entrypoint": entrypoint,
        "data_files": _data_records(spec),
        "service": service,
        "service_command": service["command"],
        "service_marker": service["marker"],
        "rollback_target": service["rollback_target"],
    }
    return payload


def build_artifact(
    spec: Mapping[str, Any], install_build_deps: bool, manifest_path: Path
) -> dict[str, Any]:
    """Validate the host, build, stage, and write an integrity manifest."""

    _require_target_runtime(python_runtime())
    ensure_build_dependencies(spec["mode"], install_build_deps)
    artifact_root = _run_build(spec)
    manifest = create_artifact_manifest(spec, artifact_root, manifest_path)
    _write_json(manifest_path, manifest)
    return manifest


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Plan or build a Python 3.11 x64 native artifact from a UTF-8 JSON spec. "
            "The default action is plan-only and never installs packages."
        )
    )
    parser.add_argument("build_spec", nargs="?", help="Path to the JSON build spec")
    parser.add_argument("--spec", dest="spec_option", help="Path to the JSON build spec")
    action = parser.add_mutually_exclusive_group()
    action.add_argument(
        "--plan-only",
        action="store_true",
        help="Validate and print a build plan without requiring compilers (default)",
    )
    action.add_argument("--build", action="store_true", help="Execute the native build")
    parser.add_argument(
        "--install-build-deps",
        action="store_true",
        help="Explicitly allow pip to install missing mode-specific build dependencies",
    )
    parser.add_argument("--plan-output", help="Optional UTF-8 JSON path for the plan")
    parser.add_argument("--manifest", help="Post-build artifact manifest path")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8")
    parser = _parser()
    args = parser.parse_args(argv)
    spec_value = args.spec_option or args.build_spec
    if not spec_value:
        parser.error("a build spec is required (positional or --spec)")
    if args.spec_option and args.build_spec:
        parser.error("provide the build spec either positionally or with --spec, not both")
    if args.install_build_deps and not args.build:
        parser.error("--install-build-deps is only valid together with --build")

    try:
        spec_path = Path(spec_value)
        spec = load_build_spec(spec_path)
        if not args.build:
            plan = create_plan(spec)
            if args.plan_output:
                _write_json(_resolve_path(args.plan_output, Path.cwd()), plan)
            print(json.dumps(plan, ensure_ascii=False, indent=2))
            return 0
        manifest_path = (
            _resolve_path(args.manifest, Path.cwd())
            if args.manifest
            else spec["output_dir"] / f"{spec['name']}.native-manifest.json"
        )
        manifest = build_artifact(spec, args.install_build_deps, manifest_path)
        print(json.dumps(manifest, ensure_ascii=False, indent=2))
        return 0
    except (NativeBuildError, subprocess.CalledProcessError) as exc:
        print(f"native artifact build failed: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
