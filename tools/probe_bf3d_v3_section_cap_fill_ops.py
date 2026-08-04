"""Compare Blender BMesh fill operators on the saved V3 section boundaries.

The probe deletes only cap faces on in-memory BMesh copies, evaluates several
fill operators, measures projected cap area and cross-object overlap, and exits
without saving the loaded Blend.

Requirement:
    REQ-BF3D-R2U-SECTION-CAP-CONTROLLED-V4-20260720
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import bmesh
import bpy


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import audit_bf3d_v3_section_caps as audit


DEFAULT_OUTPUT = (
    ROOT
    / "PT"
    / "高炉3D模型"
    / "work"
    / "WEB_60_20260720_R2U_SECTION_CAP_CONTROLLED_V4"
    / "reports"
    / "section_cap_fill_operator_probe.json"
)
REQUIREMENT_ID = "REQ-BF3D-R2U-SECTION-CAP-CONTROLLED-V4-20260720"
METHODS = (
    "close_open_nearest_then_fill",
    "current_cap_logic",
    "bridge_open_use_pairs",
    "bridge_open_twist_plus_1",
    "bridge_open_twist_minus_1",
    "triangle_fill_components",
    "edgeloop_fill",
    "edgenet_fill",
    "holes_fill",
    "contextual_create",
)


def component_closed(component: list[bmesh.types.BMEdge]) -> bool:
    """Return whether every vertex has degree two inside one edge component."""

    degrees: dict[bmesh.types.BMVert, int] = {}
    for edge in component:
        for vertex in edge.verts:
            degrees[vertex] = degrees.get(vertex, 0) + 1
    return bool(degrees) and all(value == 2 for value in degrees.values())


def component_mean_y(component: list[bmesh.types.BMEdge]) -> float:
    """Return mean section-plane Y for deterministic component ordering."""

    vertices = {vertex for edge in component for vertex in edge.verts}
    return sum(float(vertex.co.y) for vertex in vertices) / max(
        len(vertices), 1
    )


def bridge_cap_logic(
    bm: bmesh.types.BMesh,
    edges: list[bmesh.types.BMEdge],
    *,
    use_pairs: bool,
    twist_offset: int,
) -> None:
    """Apply the V3 closed-fill/open-bridge strategy with one bridge variant."""

    components = edge_components(edges)
    closed = [component for component in components if component_closed(component)]
    opened = [
        component for component in components if not component_closed(component)
    ]
    for component in closed:
        bmesh.ops.triangle_fill(
            bm,
            edges=component,
            use_beauty=True,
            use_dissolve=False,
        )
    opened.sort(key=component_mean_y)
    for index in range(0, len(opened) - 1, 2):
        bmesh.ops.bridge_loops(
            bm,
            edges=opened[index] + opened[index + 1],
            use_pairs=use_pairs,
            twist_offset=twist_offset,
        )


def close_open_nearest_then_fill(
    bm: bmesh.types.BMesh,
    edges: list[bmesh.types.BMEdge],
) -> None:
    """Close fragmented coplanar chains by nearest endpoints, then triangulate.

    Split normals/UV seams leave some physical shell cut boundaries as several
    disconnected chains.  Grouping by the negative/positive wall side prevents
    any new edge from crossing the furnace cavity.
    """

    components = edge_components(edges)
    working_edges = list(edges)
    open_components = [
        component for component in components if not component_closed(component)
    ]
    side_groups: dict[int, list[list[bmesh.types.BMEdge]]] = {-1: [], 1: []}
    for component in open_components:
        side = -1 if component_mean_y(component) < 0.0 else 1
        side_groups[side].append(component)

    for side_components in side_groups.values():
        endpoints: list[bmesh.types.BMVert] = []
        for component in side_components:
            degrees: dict[bmesh.types.BMVert, int] = {}
            for edge in component:
                for vertex in edge.verts:
                    degrees[vertex] = degrees.get(vertex, 0) + 1
            endpoints.extend(
                vertex for vertex, degree in degrees.items() if degree == 1
            )
        while endpoints:
            first = endpoints.pop(0)
            if not endpoints:
                raise RuntimeError("Odd endpoint count in one section side")
            second_index = min(
                range(len(endpoints)),
                key=lambda index: (
                    float((endpoints[index].co - first.co).length_squared),
                    float(endpoints[index].co.y),
                    float(endpoints[index].co.z),
                ),
            )
            second = endpoints.pop(second_index)
            existing = bm.edges.get((first, second))
            if existing is None:
                existing = bm.edges.new((first, second))
            working_edges.append(existing)

    for component in edge_components(working_edges):
        if not component_closed(component):
            raise RuntimeError(
                "Nearest-endpoint reconstruction left an open boundary"
            )
        bmesh.ops.triangle_fill(
            bm,
            edges=component,
            use_beauty=True,
            use_dissolve=False,
        )


def edge_components(
    edges: list[bmesh.types.BMEdge],
) -> list[list[bmesh.types.BMEdge]]:
    """Return connected components restricted to the supplied edge set."""

    remaining = set(edges)
    result = []
    while remaining:
        seed = remaining.pop()
        component = [seed]
        stack = [seed]
        while stack:
            current = stack.pop()
            for vertex in current.verts:
                for edge in vertex.link_edges:
                    if edge not in remaining:
                        continue
                    remaining.remove(edge)
                    component.append(edge)
                    stack.append(edge)
        result.append(component)
    return result


def create_faces(
    bm: bmesh.types.BMesh,
    edges: list[bmesh.types.BMEdge],
    method: str,
    material_index: int,
) -> list[bmesh.types.BMFace]:
    """Create cap faces with one candidate BMesh operator."""

    before = set(bm.faces)
    if method == "close_open_nearest_then_fill":
        close_open_nearest_then_fill(bm, edges)
    elif method == "current_cap_logic":
        bridge_cap_logic(
            bm,
            edges,
            use_pairs=False,
            twist_offset=0,
        )
    elif method == "bridge_open_use_pairs":
        bridge_cap_logic(
            bm,
            edges,
            use_pairs=True,
            twist_offset=0,
        )
    elif method == "bridge_open_twist_plus_1":
        bridge_cap_logic(
            bm,
            edges,
            use_pairs=False,
            twist_offset=1,
        )
    elif method == "bridge_open_twist_minus_1":
        bridge_cap_logic(
            bm,
            edges,
            use_pairs=False,
            twist_offset=-1,
        )
    elif method == "triangle_fill_components":
        for component in edge_components(edges):
            bmesh.ops.triangle_fill(
                bm,
                edges=component,
                use_beauty=True,
                use_dissolve=False,
            )
    elif method == "edgeloop_fill":
        bmesh.ops.edgeloop_fill(
            bm,
            edges=edges,
            mat_nr=material_index,
            use_smooth=False,
        )
    elif method == "edgenet_fill":
        bmesh.ops.edgenet_fill(
            bm,
            edges=edges,
            mat_nr=material_index,
            use_smooth=False,
            sides=0,
        )
    elif method == "holes_fill":
        bmesh.ops.holes_fill(bm, edges=edges, sides=0)
    elif method == "contextual_create":
        bmesh.ops.contextual_create(
            bm,
            geom=edges,
            mat_nr=material_index,
            use_smooth=False,
        )
    else:
        raise ValueError(f"Unsupported method: {method}")
    created = [face for face in bm.faces if face not in before and face.is_valid]
    for face in created:
        face.material_index = material_index
    return created


def projected_triangles(
    obj: bpy.types.Object,
    method: str,
) -> tuple[list[dict], dict]:
    """Evaluate one fill method on an in-memory copy of one section mesh."""

    cap_indices = audit.cap_material_indices(obj)
    if not cap_indices:
        raise RuntimeError(f"No cap material on {obj.name}")
    cap_index = min(cap_indices)
    plane_x = float(obj.get("bf3d_section_plane_value", 0.0))
    bm = bmesh.new()
    bm.from_mesh(obj.data)
    cap_faces = [
        face for face in bm.faces if face.material_index in cap_indices
    ]
    # Preserve the original cut boundary.  ``FACES`` also removes now-unused
    # edges/vertices and would turn the probe into a different topology.
    bmesh.ops.delete(bm, geom=cap_faces, context="FACES_ONLY")
    boundary_edges = [
        edge
        for edge in bm.edges
        if edge.is_valid
        and len(edge.link_faces) == 1
        and all(
            abs(float(vertex.co.x) - plane_x) <= audit.PLANE_TOLERANCE_M
            for vertex in edge.verts
        )
    ]
    components = edge_components(boundary_edges)
    error = None
    created: list[bmesh.types.BMFace] = []
    try:
        created = create_faces(bm, boundary_edges, method, cap_index)
    except (RuntimeError, ValueError) as exc:
        error = f"{type(exc).__name__}: {exc}"

    valid_created = [face for face in created if face.is_valid]
    if valid_created:
        bmesh.ops.triangulate(
            bm,
            faces=valid_created,
            quad_method="BEAUTY",
            ngon_method="BEAUTY",
        )
    cap_triangles = []
    plane_deviations = []
    for face in bm.faces:
        if not face.is_valid or face.material_index != cap_index:
            continue
        points_world = [obj.matrix_world @ vertex.co for vertex in face.verts]
        if len(points_world) != 3:
            continue
        projected = [
            (float(point.y), float(point.z)) for point in points_world
        ]
        area_m2 = audit.polygon_area(projected)
        if area_m2 <= 1.0e-12:
            continue
        plane_deviations.extend(
            abs(float(point.x) - plane_x) for point in points_world
        )
        cap_triangles.append(
            {
                "points_yz": projected,
                "bbox_yz": audit.bbox(projected),
                "area_m2": area_m2,
            }
        )

    record = {
        "object": obj.name,
        "role": str(obj.get("bf3d_structural_role", "")),
        "method": method,
        "boundary_edge_count": len(boundary_edges),
        "boundary_component_count": len(components),
        "boundary_component_edge_counts": sorted(
            len(component) for component in components
        ),
        "boundary_components": [
            {
                "edge_count": len(component),
                "closed": component_closed(component),
                "mean_y": component_mean_y(component),
                "bounds_yz": audit.bbox(
                    (
                        (float(vertex.co.y), float(vertex.co.z))
                        for edge in component
                        for vertex in edge.verts
                    )
                ),
            }
            for component in sorted(
                components,
                key=lambda value: (
                    component_mean_y(value),
                    len(value),
                ),
            )
        ],
        "created_face_count_before_triangulation": len(valid_created),
        "triangle_count": len(cap_triangles),
        "projected_area_m2": sum(
            triangle["area_m2"] for triangle in cap_triangles
        ),
        "max_plane_deviation_m": max(plane_deviations, default=None),
        "error": error,
        "passed_local": bool(cap_triangles) and error is None,
    }
    bm.free()
    return cap_triangles, record


def method_report(
    objects: list[bpy.types.Object],
    method: str,
) -> dict:
    """Return per-object and cross-object metrics for one fill method."""

    triangle_sets = {}
    records = []
    for obj in objects:
        triangles, record = projected_triangles(obj, method)
        triangle_sets[obj.name] = triangles
        records.append(record)

    overlaps = []
    for index, first in enumerate(records):
        for second in records[index + 1 :]:
            overlap_area, triangle_pairs = audit.pair_overlap_area(
                triangle_sets[first["object"]],
                triangle_sets[second["object"]],
            )
            if overlap_area <= audit.AREA_TOLERANCE_M2:
                continue
            overlaps.append(
                {
                    "object_a": first["object"],
                    "role_a": first["role"],
                    "object_b": second["object"],
                    "role_b": second["role"],
                    "overlap_area_m2": overlap_area,
                    "intersecting_triangle_pairs": triangle_pairs,
                }
            )
    overlaps.sort(key=lambda item: item["overlap_area_m2"], reverse=True)
    checks = {
        "all_10_objects_created_caps": len(records) == 10
        and all(record["passed_local"] for record in records),
        "no_cross_object_positive_area_overlap": not overlaps,
    }
    return {
        "method": method,
        "objects": records,
        "overlap_pairs": overlaps,
        "total_cross_object_overlap_area_m2": sum(
            item["overlap_area_m2"] for item in overlaps
        ),
        "checks": checks,
        "passed": all(checks.values()),
    }


def parse_args(argv: list[str]) -> argparse.Namespace:
    """Parse command arguments after Blender's ``--`` separator."""

    parser = argparse.ArgumentParser(
        description="Probe BMesh fill operators for V3 section caps."
    )
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    return parser.parse_args(argv)


def main() -> int:
    """Run every candidate fill operator without saving the loaded scene."""

    args = parse_args(
        sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else []
    )
    objects = audit.section_objects()
    report = {
        "schema_version": "bf3d.r2u.section_cap_fill_operator_probe.v1",
        "requirement_id": REQUIREMENT_ID,
        "mode": "read_only_in_memory_probe",
        "blender_version": bpy.app.version_string,
        "section_object_count": len(objects),
        "methods": [method_report(objects, method) for method in METHODS],
        "scene_saved_or_mutated": False,
    }
    report["passing_methods"] = [
        item["method"] for item in report["methods"] if item["passed"]
    ]
    output = args.output.resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
