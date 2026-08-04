"""Diagnose UV degeneracy that prevents Blender glTF tangent export.

Requirement:
    REQ-BF3D-R2V-GLTF-PORTABILITY-TANGENT-BUDGET-20260720

Run with Blender:

    blender --background --python tools/diagnose_bf3d_v4_tangent_uv.py -- \
      --blend 高炉前端数据/models/gl02_blast_furnace_review.v4.blend \
      --output PT/高炉3D模型/work/.../reports/v4_tangent_uv_diagnosis.json

The script is read-only.  It opens the saved Blend, traces each material's
normal-map UV source, and counts normal-mapped polygons whose UV polygon area is
zero.  Such faces can cause Blender's glTF exporter to omit explicit tangents
for an entire mesh.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import sys
from pathlib import Path
from typing import Any

import bmesh
import bpy


REQUIREMENT_ID = "REQ-BF3D-R2V-GLTF-PORTABILITY-TANGENT-BUDGET-20260720"
SCHEMA_VERSION = "bf3d.v4_tangent_uv_diagnosis.v1"
AREA_EPSILON = 1.0e-12


def sha256_file(path: Path) -> str:
    """Return the lowercase SHA-256 digest of a file."""

    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def uv_polygon_area(
    mesh: bpy.types.Mesh,
    polygon: bpy.types.MeshPolygon,
    uv_layer: bpy.types.MeshUVLoopLayer,
) -> float:
    """Return absolute 2D shoelace area for one polygon's UV loop."""

    points = [
        uv_layer.data[loop_index].uv
        for loop_index in polygon.loop_indices
    ]
    if len(points) < 3:
        return 0.0
    area_twice = 0.0
    for index, point in enumerate(points):
        next_point = points[(index + 1) % len(points)]
        area_twice += float(point.x) * float(next_point.y)
        area_twice -= float(next_point.x) * float(point.y)
    return abs(area_twice) * 0.5


def uv_loop_triangle_area(
    triangle: bpy.types.MeshLoopTriangle,
    uv_layer: bpy.types.MeshUVLoopLayer,
) -> float:
    """Return 2D UV area for one evaluated loop triangle."""

    first, second, third = (
        uv_layer.data[loop_index].uv for loop_index in triangle.loops
    )
    return abs(
        (float(second.x) - float(first.x))
        * (float(third.y) - float(first.y))
        - (float(third.x) - float(first.x))
        * (float(second.y) - float(first.y))
    ) * 0.5


def linked_node(
    socket: bpy.types.NodeSocket | None,
) -> bpy.types.Node | None:
    """Return the first node linked to an input socket."""

    if socket is None or not socket.is_linked or not socket.links:
        return None
    return socket.links[0].from_node


def material_normal_uv(
    material: bpy.types.Material,
) -> dict[str, Any] | None:
    """Trace a Principled normal map and return its UV source."""

    if not material.use_nodes or material.node_tree is None:
        return None
    nodes = material.node_tree.nodes
    output = next(
        (
            node
            for node in nodes
            if node.bl_idname == "ShaderNodeOutputMaterial"
            and getattr(node, "is_active_output", False)
        ),
        None,
    )
    if output is None:
        output = next(
            (node for node in nodes if node.bl_idname == "ShaderNodeOutputMaterial"),
            None,
        )
    surface = output.inputs.get("Surface") if output is not None else None
    shader = linked_node(surface)
    if shader is None or shader.bl_idname != "ShaderNodeBsdfPrincipled":
        return None
    normal_node = linked_node(shader.inputs.get("Normal"))
    if normal_node is None or normal_node.bl_idname != "ShaderNodeNormalMap":
        return None
    image_node = linked_node(normal_node.inputs.get("Color"))
    if image_node is None or image_node.bl_idname != "ShaderNodeTexImage":
        return None
    vector_node = linked_node(image_node.inputs.get("Vector"))
    uv_map = ""
    source = "active_render_uv"
    if vector_node is not None and vector_node.bl_idname == "ShaderNodeUVMap":
        uv_map = str(vector_node.uv_map)
        source = "ShaderNodeUVMap"
    return {
        "normal_map_node": normal_node.name,
        "image_node": image_node.name,
        "image": image_node.image.name if image_node.image else None,
        "uv_map": uv_map,
        "uv_source": source,
    }


def active_render_uv_name(mesh: bpy.types.Mesh) -> str | None:
    """Return the active-render UV layer name."""

    for layer in mesh.uv_layers:
        if layer.active_render:
            return layer.name
    return mesh.uv_layers.active.name if mesh.uv_layers.active else None


def tangent_calculation_probe(
    source: bpy.types.Mesh,
    *,
    triangulate: bool,
) -> dict[str, Any]:
    """Run Blender's tangent calculation on a disposable mesh copy."""

    candidate = source.copy()
    try:
        polygons_before = len(candidate.polygons)
        if triangulate:
            working = bmesh.new()
            working.from_mesh(candidate)
            bmesh.ops.triangulate(
                working,
                faces=list(working.faces),
                quad_method="BEAUTY",
                ngon_method="BEAUTY",
            )
            working.normal_update()
            working.to_mesh(candidate)
            working.free()
            candidate.update()
        try:
            candidate.calc_tangents()
            success = True
            error_type = None
            error_message = None
        except Exception as exc:  # Blender exposes a RuntimeError without details.
            success = False
            error_type = type(exc).__name__
            error_message = str(exc)
        return {
            "triangulated_before_probe": triangulate,
            "polygons_before": polygons_before,
            "polygons_after": len(candidate.polygons),
            "success": success,
            "error_type": error_type,
            "error_message": error_message,
        }
    finally:
        bpy.data.meshes.remove(candidate)


def diagnose_object(obj: bpy.types.Object) -> dict[str, Any]:
    """Return tangent-relevant UV diagnostics for a mesh object."""

    mesh = obj.data
    mesh.calc_loop_triangles()
    active_render = active_render_uv_name(mesh)
    material_records: list[dict[str, Any]] = []
    total_normal_mapped_polygons = 0
    total_degenerate_polygons = 0
    total_normal_mapped_triangles = 0
    total_degenerate_triangles = 0
    for slot_index, slot in enumerate(obj.material_slots):
        material = slot.material
        if material is None:
            continue
        normal = material_normal_uv(material)
        if normal is None:
            continue
        uv_name = normal["uv_map"] or active_render
        uv_layer = mesh.uv_layers.get(uv_name) if uv_name else None
        polygons = [
            polygon
            for polygon in mesh.polygons
            if polygon.material_index == slot_index
        ]
        triangles = [
            triangle
            for triangle in mesh.loop_triangles
            if mesh.polygons[triangle.polygon_index].material_index == slot_index
        ]
        degenerate: list[dict[str, Any]] = []
        nonzero_areas: list[float] = []
        for polygon in polygons:
            area = (
                uv_polygon_area(mesh, polygon, uv_layer)
                if uv_layer is not None
                else 0.0
            )
            if (
                uv_layer is None
                or not math.isfinite(area)
                or area <= AREA_EPSILON
            ):
                degenerate.append(
                    {
                        "polygon_index": polygon.index,
                        "loop_total": polygon.loop_total,
                        "material_index": polygon.material_index,
                        "mesh_area": float(polygon.area),
                        "uv_area": area,
                    }
                )
            else:
                nonzero_areas.append(area)
        degenerate_triangles: list[dict[str, Any]] = []
        nonzero_triangle_areas: list[float] = []
        for triangle in triangles:
            triangle_area = (
                uv_loop_triangle_area(triangle, uv_layer)
                if uv_layer is not None
                else 0.0
            )
            if (
                uv_layer is None
                or not math.isfinite(triangle_area)
                or triangle_area <= AREA_EPSILON
            ):
                degenerate_triangles.append(
                    {
                        "triangle_index": triangle.index,
                        "polygon_index": triangle.polygon_index,
                        "loops": list(triangle.loops),
                        "uv_area": triangle_area,
                    }
                )
            else:
                nonzero_triangle_areas.append(triangle_area)
        total_normal_mapped_polygons += len(polygons)
        total_degenerate_polygons += len(degenerate)
        total_normal_mapped_triangles += len(triangles)
        total_degenerate_triangles += len(degenerate_triangles)
        material_records.append(
            {
                "slot_index": slot_index,
                "material": material.name,
                "normal_map": normal,
                "resolved_uv_layer": uv_name,
                "uv_layer_exists": uv_layer is not None,
                "polygon_count": len(polygons),
                "degenerate_uv_polygon_count": len(degenerate),
                "degenerate_uv_polygons": degenerate[:100],
                "minimum_nonzero_uv_area": (
                    min(nonzero_areas) if nonzero_areas else None
                ),
                "loop_triangle_count": len(triangles),
                "degenerate_uv_loop_triangle_count": len(
                    degenerate_triangles
                ),
                "degenerate_uv_loop_triangles": degenerate_triangles[:100],
                "minimum_nonzero_uv_loop_triangle_area": (
                    min(nonzero_triangle_areas)
                    if nonzero_triangle_areas
                    else None
                ),
            }
        )
    return {
        "object": obj.name,
        "mesh": mesh.name,
        "vertices": len(mesh.vertices),
        "edges": len(mesh.edges),
        "polygons": len(mesh.polygons),
        "uv_layers": [
            {
                "name": layer.name,
                "active": layer.active,
                "active_render": layer.active_render,
            }
            for layer in mesh.uv_layers
        ],
        "active_render_uv": active_render,
        "normal_mapped_polygon_count": total_normal_mapped_polygons,
        "degenerate_normal_mapped_polygon_count": total_degenerate_polygons,
        "normal_mapped_loop_triangle_count": total_normal_mapped_triangles,
        "degenerate_normal_mapped_loop_triangle_count": (
            total_degenerate_triangles
        ),
        "tangent_calculation_probe_original": tangent_calculation_probe(
            mesh, triangulate=False
        ),
        "tangent_calculation_probe_triangulated": tangent_calculation_probe(
            mesh, triangulate=True
        ),
        "materials": material_records,
    }


def build_parser() -> argparse.ArgumentParser:
    """Create the Blender-side CLI parser."""

    parser = argparse.ArgumentParser(
        description=(
            "Diagnose normal-mapped polygons with degenerate UV area in a "
            "saved BF3D V4 Blend."
        )
    )
    parser.add_argument("--blend", required=True, help="V4 Blend path.")
    parser.add_argument("--output", required=True, help="JSON output path.")
    parser.add_argument(
        "--expected-input-sha256",
        help="Optional fail-closed V4 Blend SHA-256.",
    )
    return parser


def main() -> int:
    """Open the Blend, run the read-only diagnosis, and write JSON evidence."""

    raw_args = sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else []
    args = build_parser().parse_args(raw_args)
    blend = Path(args.blend).resolve()
    output = Path(args.output).resolve()
    if not blend.is_file():
        raise RuntimeError(f"Blend does not exist: {blend}")
    actual_sha256 = sha256_file(blend)
    if (
        args.expected_input_sha256
        and actual_sha256 != args.expected_input_sha256.lower()
    ):
        raise RuntimeError(
            "Blend SHA-256 mismatch: "
            f"expected={args.expected_input_sha256.lower()}, "
            f"actual={actual_sha256}"
        )
    bpy.ops.wm.open_mainfile(filepath=str(blend))
    objects = sorted(
        (
            obj
            for obj in bpy.data.objects
            if obj.type == "MESH" and obj.name.startswith("SECTION_")
        ),
        key=lambda item: item.name,
    )
    records = [diagnose_object(obj) for obj in objects]
    total_normal_mapped = sum(
        record["normal_mapped_polygon_count"] for record in records
    )
    total_degenerate = sum(
        record["degenerate_normal_mapped_polygon_count"] for record in records
    )
    total_triangles = sum(
        record["normal_mapped_loop_triangle_count"] for record in records
    )
    total_degenerate_triangles = sum(
        record["degenerate_normal_mapped_loop_triangle_count"]
        for record in records
    )
    report = {
        "schema_version": SCHEMA_VERSION,
        "requirement_id": REQUIREMENT_ID,
        "input": {
            "path": blend.as_posix(),
            "bytes": blend.stat().st_size,
            "sha256": actual_sha256,
        },
        "section_object_count": len(objects),
        "objects": records,
        "summary": {
            "normal_mapped_polygon_count": total_normal_mapped,
            "degenerate_normal_mapped_polygon_count": total_degenerate,
            "normal_mapped_loop_triangle_count": total_triangles,
            "degenerate_normal_mapped_loop_triangle_count": (
                total_degenerate_triangles
            ),
            "objects_with_degenerate_normal_mapped_uv": sum(
                1
                for record in records
                if record["degenerate_normal_mapped_polygon_count"] > 0
            ),
            "objects_with_degenerate_normal_mapped_loop_triangles": sum(
                1
                for record in records
                if record[
                    "degenerate_normal_mapped_loop_triangle_count"
                ]
                > 0
            ),
            "objects_passing_original_blender_tangent_calculation": sum(
                1
                for record in records
                if record["tangent_calculation_probe_original"]["success"]
            ),
            "objects_passing_triangulated_blender_tangent_calculation": sum(
                1
                for record in records
                if record["tangent_calculation_probe_triangulated"]["success"]
            ),
        },
        "diagnosis_completed": len(objects) == 10,
        "explicit_tangent_export_expected_without_uv_repair": (
            total_degenerate_triangles == 0
        ),
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(
        "BF3D_V4_TANGENT_UV_DIAGNOSIS="
        + json.dumps(
            {
                "section_objects": len(objects),
                **report["summary"],
                "output": output.as_posix(),
            },
            ensure_ascii=False,
        )
    )
    return 0 if report["diagnosis_completed"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
