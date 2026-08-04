"""Probe Blender, glTF importer, render engines, and Cycles compute devices.

Run inside Blender with ``--background --factory-startup --python``.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import bpy


def parse_args() -> argparse.Namespace:
    argv = sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else []
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", required=True, type=Path)
    return parser.parse_args(argv)


def cycle_devices() -> dict[str, object]:
    addon = bpy.context.preferences.addons.get("cycles")
    if addon is None:
        return {"available": False, "backends": {}}
    preferences = addon.preferences
    backends: dict[str, object] = {}
    for backend in ("OPTIX", "CUDA", "HIP", "ONEAPI", "METAL", "NONE"):
        try:
            preferences.compute_device_type = backend
            preferences.get_devices()
            backends[backend] = [
                {
                    "name": device.name,
                    "type": device.type,
                    "id": device.id,
                    "use": bool(device.use),
                }
                for device in preferences.devices
            ]
        except (AttributeError, RuntimeError, TypeError) as exc:
            backends[backend] = {"error": str(exc)}
    return {"available": True, "backends": backends}


def main() -> int:
    args = parse_args()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    engine_items = bpy.types.RenderSettings.bl_rna.properties["engine"].enum_items
    try:
        importer_properties = sorted(bpy.ops.import_scene.gltf.get_rna_type().properties.keys())
    except (AttributeError, RuntimeError) as exc:
        importer_properties = [f"ERROR: {exc}"]
    report = {
        "blender": {
            "version": bpy.app.version_string,
            "version_tuple": list(bpy.app.version),
            "build_hash": bpy.app.build_hash.decode("ascii", "replace") if isinstance(bpy.app.build_hash, bytes) else str(bpy.app.build_hash),
            "build_date": bpy.app.build_date.decode("ascii", "replace") if isinstance(bpy.app.build_date, bytes) else str(bpy.app.build_date),
            "background": bool(bpy.app.background),
            "binary_path": bpy.app.binary_path,
        },
        "render_engines": [{"identifier": item.identifier, "name": item.name} for item in engine_items],
        "gltf_import_properties": importer_properties,
        "cycles": cycle_devices(),
    }
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
