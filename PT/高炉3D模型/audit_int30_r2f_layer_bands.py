"""Read-only Blender audit for INT-30 R2F temperature-layer overlays.

The script never saves the opened Blend. It records canonical L7-L16 band
objects, their meshes, materials, collections, transforms and custom
properties so the controller can decide whether to reuse or append P36 data.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import struct
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import bpy


BAND_NAMES = [f"APPROX_GL02_TEMP_LAYER_BAND_L{i}" for i in range(7, 17)]
GROUP_NAMES = [f"GL02_FURNACE_TEMP_LAYER_L{i}" for i in range(7, 17)]
MATERIAL_NAMES = [f"BF3D_TEMP_LAYER_HIGHLIGHT_L{i}" for i in range(7, 17)]


def blender_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--label", required=True)
    argv = sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else []
    return parser.parse_args(argv)


def mesh_hash(mesh: Any) -> str:
    digest = hashlib.sha256()
    digest.update(mesh.name.encode("utf-8"))
    digest.update(struct.pack("<III", len(mesh.vertices), len(mesh.edges), len(mesh.polygons)))
    for vertex in mesh.vertices:
        digest.update(struct.pack("<3d", *(round(float(v), 9) for v in vertex.co)))
    for polygon in mesh.polygons:
        digest.update(struct.pack("<I", len(polygon.vertices)))
        for index in polygon.vertices:
            digest.update(struct.pack("<I", int(index)))
    return digest.hexdigest()


def safe_value(value: Any) -> Any:
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    if hasattr(value, "to_list"):
        return value.to_list()
    try:
        return list(value)
    except TypeError:
        return str(value)


def object_record(name: str) -> dict[str, Any]:
    obj = bpy.data.objects.get(name)
    if obj is None:
        return {"name": name, "exists": False}
    mesh = obj.data if obj.type == "MESH" else None
    return {
        "name": name,
        "exists": True,
        "type": obj.type,
        "data_name": getattr(mesh, "name", None),
        "mesh_hash": mesh_hash(mesh) if mesh else None,
        "vertices": len(mesh.vertices) if mesh else None,
        "edges": len(mesh.edges) if mesh else None,
        "polygons": len(mesh.polygons) if mesh else None,
        "matrix_world": [round(float(v), 9) for row in obj.matrix_world for v in row],
        "parent": obj.parent.name if obj.parent else None,
        "collections": sorted(collection.name for collection in obj.users_collection),
        "materials": [slot.material.name for slot in obj.material_slots if slot.material],
        "hide_viewport": bool(obj.hide_viewport),
        "hide_render": bool(obj.hide_render),
        "hide_get": bool(obj.hide_get()),
        "custom_properties": {
            key: safe_value(obj[key])
            for key in sorted(obj.keys())
            if key != "_RNA_UI"
        },
    }


def collection_record(name: str) -> dict[str, Any]:
    collection = bpy.data.collections.get(name)
    if collection is None:
        return {"name": name, "exists": False}
    return {
        "name": name,
        "exists": True,
        "objects": sorted(obj.name for obj in collection.objects),
        "children": sorted(child.name for child in collection.children),
        "custom_properties": {
            key: safe_value(collection[key])
            for key in sorted(collection.keys())
            if key != "_RNA_UI"
        },
    }


def material_record(name: str) -> dict[str, Any]:
    material = bpy.data.materials.get(name)
    if material is None:
        return {"name": name, "exists": False}
    return {
        "name": name,
        "exists": True,
        "use_nodes": bool(material.use_nodes),
        "blend_method": getattr(material, "surface_render_method", None),
        "custom_properties": {
            key: safe_value(material[key])
            for key in sorted(material.keys())
            if key != "_RNA_UI"
        },
    }


def main() -> int:
    args = blender_args()
    bands = [object_record(name) for name in BAND_NAMES]
    groups = [collection_record(name) for name in GROUP_NAMES]
    materials = [material_record(name) for name in MATERIAL_NAMES]
    report = {
        "schema_version": "bf3d.int30.r2f.band_preflight.v1",
        "generated_at": datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds"),
        "label": args.label,
        "blend_filepath": bpy.data.filepath,
        "bands": bands,
        "groups": groups,
        "materials": materials,
        "summary": {
            "band_count": sum(1 for item in bands if item["exists"]),
            "group_count": sum(1 for item in groups if item["exists"]),
            "material_count": sum(1 for item in materials if item["exists"]),
            "all_bands_default_hidden": all(
                item.get("hide_viewport") and item.get("hide_render")
                for item in bands
                if item["exists"]
            ),
            "duplicate_suffix_objects": sorted(
                obj.name
                for obj in bpy.data.objects
                if obj.name.startswith("APPROX_GL02_TEMP_LAYER_BAND_")
                and obj.name not in BAND_NAMES
            ),
        },
        "read_only": True,
        "blend_saved": False,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report["summary"], ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
