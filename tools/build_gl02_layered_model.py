r"""Build and install the traceable layered GL02 GLB model.

The source-of-truth generator currently lives in ``D:\文件\pythonCAD``.
This wrapper regenerates its artifacts, validates the layered GLB contract,
backs up the active model, installs the new GLB, and writes a version manifest.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import struct
import subprocess
import sys
from datetime import datetime
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_GENERATOR_ROOT = Path(r"D:\文件\pythonCAD")
DEFAULT_TARGET = ROOT / "高炉前端数据" / "models" / "gl02_blast_furnace.glb"
MANIFEST_PATH = ROOT / "高炉前端数据" / "models" / "gl02_blast_furnace.manifest.json"
BACKUP_DIR = ROOT / "logs" / "model_backups"

PROCESS_ZONE_NODES = {
    "APPROX_GL02_FURNACE_HEARTH",
    "APPROX_GL02_FURNACE_BOSH",
    "APPROX_GL02_FURNACE_BELLY",
    "APPROX_GL02_FURNACE_SHAFT",
    "APPROX_GL02_FURNACE_THROAT",
}
LAYER_GROUP_NODES = {f"GL02_SENSOR_LAYER_L{layer}" for layer in range(7, 17)}


def read_glb_json(path: Path) -> dict:
    """Read and validate the JSON chunk of a glTF 2.0 GLB."""

    blob = path.read_bytes()
    magic, version, total_length = struct.unpack("<4sII", blob[:12])
    if magic != b"glTF" or version != 2 or total_length != len(blob):
        raise ValueError(f"invalid glTF 2.0 GLB: {path}")
    json_length, chunk_type = struct.unpack("<II", blob[12:20])
    if chunk_type != 0x4E4F534A:
        raise ValueError(f"GLB first chunk is not JSON: {path}")
    return json.loads(blob[20 : 20 + json_length].decode("utf-8"))


def validate_layered_contract(path: Path) -> dict:
    """Validate process zones, sensor layer groups, and sensor identity."""

    gltf = read_glb_json(path)
    nodes = gltf.get("nodes", [])
    by_name = {node.get("name", ""): node for node in nodes}
    missing_zones = sorted(PROCESS_ZONE_NODES - by_name.keys())
    missing_layers = sorted(LAYER_GROUP_NODES - by_name.keys())
    sensor_nodes = [node for node in nodes if node.get("name", "").startswith("SENSOR_")]
    body_nodes = [node for node in sensor_nodes if node.get("extras", {}).get("group") == "BODY_TEMP"]
    bad_layers = {
        name: len(by_name[name].get("children", []))
        for name in sorted(LAYER_GROUP_NODES & by_name.keys())
        if len(by_name[name].get("children", [])) != 8
    }
    if missing_zones or missing_layers or len(sensor_nodes) != 115 or len(body_nodes) != 80 or bad_layers:
        raise ValueError(
            "layered GLB contract failed: "
            f"missing_zones={missing_zones}, missing_layers={missing_layers}, "
            f"sensors={len(sensor_nodes)}, body_sensors={len(body_nodes)}, bad_layers={bad_layers}"
        )
    return {
        "nodes": len(nodes),
        "meshes": len(gltf.get("meshes", [])),
        "materials": len(gltf.get("materials", [])),
        "sensor_nodes": len(sensor_nodes),
        "body_sensor_nodes": len(body_nodes),
        "process_zones": sorted(PROCESS_ZONE_NODES),
        "sensor_layers": sorted(LAYER_GROUP_NODES, key=lambda value: int(value.rsplit("L", 1)[1])),
        "generator": gltf.get("asset", {}).get("generator", ""),
    }


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(description="Regenerate and install the layered GL02 browser model.")
    parser.add_argument("--generator-root", type=Path, default=DEFAULT_GENERATOR_ROOT)
    parser.add_argument("--target", type=Path, default=DEFAULT_TARGET)
    parser.add_argument("--skip-generate", action="store_true", help="Validate and install the existing generator output.")
    parser.add_argument("--check-only", action="store_true", help="Validate without replacing the active model.")
    args = parser.parse_args()

    generator_root = args.generator_root.resolve()
    source = generator_root / "output" / "glb" / "gl02_blast_furnace.glb"
    generator = generator_root / "src" / "generate_gl02_cad.py"
    venv_python = generator_root / ".venv" / "Scripts" / "python.exe"
    python_exe = venv_python if venv_python.is_file() else Path(sys.executable)
    if not args.skip_generate:
        if not generator.is_file():
            raise FileNotFoundError(f"GL02 generator entry is missing: {generator}")
        subprocess.run([str(python_exe), str(generator)], cwd=generator_root, check=True)
    if not source.is_file():
        raise FileNotFoundError(f"generated GLB is missing: {source}")

    contract = validate_layered_contract(source)
    result = {
        "ok": True,
        "check_only": args.check_only,
        "source": str(source),
        "source_bytes": source.stat().st_size,
        "source_sha256": sha256(source),
        "contract": contract,
    }
    if not args.check_only:
        target = args.target.resolve()
        target.parent.mkdir(parents=True, exist_ok=True)
        backup = None
        if target.exists():
            stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            BACKUP_DIR.mkdir(parents=True, exist_ok=True)
            backup = BACKUP_DIR / f"{target.stem}.backup_{stamp}{target.suffix}"
            shutil.copy2(target, backup)
        shutil.copy2(source, target)
        installed = validate_layered_contract(target)
        manifest = {
            "schema_version": 1,
            "model_id": "GL02_LAYERED_FURNACE",
            "generated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
            "source_generator_root": str(generator_root),
            "source_entry": str(generator),
            "target": str(target.relative_to(ROOT)),
            "bytes": target.stat().st_size,
            "sha256": sha256(target),
            "coordinate_confidence": "approximate_until_real_cad_dimensions",
            **installed,
        }
        MANIFEST_PATH.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        result.update({"target": str(target), "backup": str(backup) if backup else None, "manifest": str(MANIFEST_PATH)})
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
