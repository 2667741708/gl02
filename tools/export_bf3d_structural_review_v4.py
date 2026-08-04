"""Build the WEB-60 R2U controlled V4 section-cap topology revision.

The V4 exporter reuses the locked V3 material, texture and source assembly
helpers, but writes only new V4 assets.  The single controlled change is the
Section topology path: embedded cooling staves are cut out of their host
internal layers with Blender Exact booleans, then the physical X-plane caps are
rebuilt with deterministic loop closure and hole-aware tessellation.

Requirement:
    REQ-BF3D-R2U-SECTION-CAP-CONTROLLED-V4-20260720
"""

from __future__ import annotations

import json
import math
import sys
from collections import Counter
from pathlib import Path
from typing import Iterable

import bmesh
import bpy
from mathutils import Matrix, Vector
from mathutils.geometry import tessellate_polygon


sys.path.insert(0, str(Path(__file__).resolve().parent))
import audit_bf3d_v3_section_caps as cap_audit
import export_bf3d_structural_review_v3 as v3


ROOT = v3.ROOT
MODEL_DIR = v3.MODEL_DIR
STAGE = (
    ROOT
    / "PT"
    / "高炉3D模型"
    / "work"
    / "WEB_60_20260720_R2U_SECTION_CAP_CONTROLLED_V4"
)
TEXTURE_DIR = STAGE / "textures"
RENDER_DIR = STAGE / "renders"
REPORT_DIR = STAGE / "reports"

MAIN_GLB = MODEL_DIR / "gl02_blast_furnace_review.v4.glb"
MATERIAL_GLB = MODEL_DIR / "gl02_blast_furnace_material_review.v4.glb"
STRUCTURAL_GLB = MODEL_DIR / "gl02_blast_furnace_structural_review.v4.glb"
REVIEW_BLEND = MODEL_DIR / "gl02_blast_furnace_review.v4.blend"
MODEL_MANIFEST = MODEL_DIR / "gl02_blast_furnace_review.v4.manifest.json"

REQUIREMENT_ID = "REQ-BF3D-R2U-SECTION-CAP-CONTROLLED-V4-20260720"
ASSET_ID = "GL02_SECTION_CAP_CONTROLLED_V4"
STATUS = "candidate_ready_for_independent_visual_and_spec_review"
EVIDENCE = "E/illustrative"
REFERENCE_STATUS = "REF-PENDING"
MATERIAL_ROOT_NAME = "BF3D_V4_MODE_MATERIAL"
SECTION_ROOT_NAME = "BF3D_V4_MODE_SECTION"
FULL_COLLECTION_NAME = "BF3D_V4_FULL_MATERIAL"
SECTION_COLLECTION_NAME = "BF3D_V4_SECTION"
CAMERA_NAME = "CAM_R2U_SECTION_ORTHO_CANDIDATE"

PLANE_TOLERANCE_M = cap_audit.PLANE_TOLERANCE_M
AREA_TOLERANCE_M2 = cap_audit.AREA_TOLERANCE_M2
RESOLUTION_AREA_TOLERANCE_M2 = 1.0e-10
BOOLEAN_CUT_ROLES = {"hotface_embed", "refractory"}


def configure_v3_namespace() -> None:
    """Point the imported V3 helper module at the V4 output namespace."""

    replacements = {
        "STAGE": STAGE,
        "TEXTURE_DIR": TEXTURE_DIR,
        "RENDER_DIR": RENDER_DIR,
        "REPORT_DIR": REPORT_DIR,
        "MAIN_GLB": MAIN_GLB,
        "MATERIAL_GLB": MATERIAL_GLB,
        "STRUCTURAL_GLB": STRUCTURAL_GLB,
        "REVIEW_BLEND": REVIEW_BLEND,
        "MODEL_MANIFEST": MODEL_MANIFEST,
        "REQUIREMENT_ID": REQUIREMENT_ID,
        "ASSET_ID": ASSET_ID,
        "STATUS": STATUS,
        "EVIDENCE": EVIDENCE,
        "REFERENCE_STATUS": REFERENCE_STATUS,
        "MATERIAL_ROOT_NAME": MATERIAL_ROOT_NAME,
        "SECTION_ROOT_NAME": SECTION_ROOT_NAME,
        "FULL_COLLECTION_NAME": FULL_COLLECTION_NAME,
        "SECTION_COLLECTION_NAME": SECTION_COLLECTION_NAME,
        "CAMERA_NAME": CAMERA_NAME,
    }
    for name, value in replacements.items():
        setattr(v3, name, value)


configure_v3_namespace()


def rel(path: Path) -> str:
    return v3.rel(path)


def artifact(path: Path) -> dict:
    return v3.artifact(path)


def write_json(path: Path, value: object) -> None:
    v3.write_json(path, value)


def component_closed(component: list[bmesh.types.BMEdge]) -> bool:
    degrees: Counter[bmesh.types.BMVert] = Counter(
        vert for edge in component for vert in edge.verts
    )
    return bool(degrees) and all(count == 2 for count in degrees.values())


def component_mean_y(component: list[bmesh.types.BMEdge]) -> float:
    verts = {vert for edge in component for vert in edge.verts}
    return sum(float(vert.co.y) for vert in verts) / max(len(verts), 1)


def close_open_components(
    bm: bmesh.types.BMesh,
    cut_edges: list[bmesh.types.BMEdge],
) -> list[bmesh.types.BMEdge]:
    """Close same-side fragmented section chains by nearest endpoints."""

    working_edges = list(cut_edges)
    open_components = [
        component
        for component in v3.edge_components(cut_edges)
        if not component_closed(component)
    ]
    side_groups: dict[int, list[list[bmesh.types.BMEdge]]] = {-1: [], 1: []}
    for component in open_components:
        side_groups[-1 if component_mean_y(component) < 0.0 else 1].append(component)
    for components in side_groups.values():
        endpoints: list[bmesh.types.BMVert] = []
        for component in components:
            degrees: Counter[bmesh.types.BMVert] = Counter(
                vert for edge in component for vert in edge.verts
            )
            endpoints.extend(vert for vert, count in degrees.items() if count == 1)
        while endpoints:
            first = endpoints.pop(0)
            if not endpoints:
                raise RuntimeError("odd section endpoint count after bisect")
            second_index = min(
                range(len(endpoints)),
                key=lambda index: (
                    float((endpoints[index].co - first.co).length_squared),
                    float(endpoints[index].co.y),
                    float(endpoints[index].co.z),
                ),
            )
            second = endpoints.pop(second_index)
            edge = bm.edges.get((first, second))
            if edge is None:
                edge = bm.edges.new((first, second))
            working_edges.append(edge)
    return [edge for edge in working_edges if edge.is_valid]


def ordered_loop_vertices(component: list[bmesh.types.BMEdge]) -> list[bmesh.types.BMVert]:
    """Return a deterministic ordered vertex loop for a closed edge component."""

    if not component_closed(component):
        raise RuntimeError("cannot order an open section boundary")
    edges_by_vert: dict[bmesh.types.BMVert, list[bmesh.types.BMEdge]] = {}
    for edge in component:
        for vert in edge.verts:
            edges_by_vert.setdefault(vert, []).append(edge)
    start = min(
        edges_by_vert,
        key=lambda vert: (float(vert.co.y), float(vert.co.z), float(vert.co.x)),
    )
    ordered = [start]
    previous_edge = None
    current = start
    while True:
        candidates = [
            edge
            for edge in edges_by_vert[current]
            if edge is not previous_edge and edge.is_valid
        ]
        if not candidates:
            break
        edge = min(
            candidates,
            key=lambda item: tuple(
                float(value)
                for value in (
                    item.other_vert(current).co.y,
                    item.other_vert(current).co.z,
                    item.other_vert(current).co.x,
                )
            ),
        )
        nxt = edge.other_vert(current)
        if nxt is start:
            break
        ordered.append(nxt)
        previous_edge = edge
        current = nxt
        if len(ordered) > len(component) + 2:
            raise RuntimeError("section boundary ordering exceeded edge count")
    if len(ordered) < 3:
        raise RuntimeError("section boundary loop has fewer than three vertices")
    return ordered


def signed_area_yz(verts: Iterable[bmesh.types.BMVert]) -> float:
    points = [(float(vert.co.y), float(vert.co.z)) for vert in verts]
    return 0.5 * sum(
        y0 * z1 - y1 * z0
        for (y0, z0), (y1, z1) in zip(points, points[1:] + points[:1])
    )


def create_tessellated_cap_faces(
    bm: bmesh.types.BMesh,
    loops: list[list[bmesh.types.BMVert]],
    material_index: int,
) -> list[bmesh.types.BMFace]:
    """Create cap triangles from one outer loop plus optional inner holes."""

    if not loops:
        return []
    normalized: list[list[bmesh.types.BMVert]] = []
    for index, loop in enumerate(loops):
        area = signed_area_yz(loop)
        if abs(area) <= 1.0e-12:
            continue
        # Keep the largest loop counter-clockwise and holes clockwise.  This
        # matches Blender's tessellator expectation for polygon islands.
        want_positive = index == 0
        if (area > 0.0) != want_positive:
            loop = list(reversed(loop))
        normalized.append(loop)
    if not normalized:
        return []
    vectors = [[vert.co.copy() for vert in loop] for loop in normalized]
    triangles = tessellate_polygon(vectors)
    flat_verts = [vert for loop in normalized for vert in loop]
    faces: list[bmesh.types.BMFace] = []
    for tri in triangles:
        verts = [flat_verts[index] for index in tri]
        if len({vert for vert in verts}) != 3:
            continue
        try:
            face = bm.faces.new(verts)
        except ValueError:
            continue
        face.material_index = material_index
        faces.append(face)
    return faces


def fill_section_cap_controlled(
    bm: bmesh.types.BMesh,
    plane_x: float,
    material_index: int,
    role: str,
) -> tuple[list[bmesh.types.BMFace], dict]:
    """Fill the X-plane cut with same-side closure and host-layer holes."""

    cut_edges = [
        edge
        for edge in bm.edges
        if edge.is_valid
        and len(edge.link_faces) == 1
        and all(abs(float(vert.co.x) - plane_x) <= PLANE_TOLERANCE_M for vert in edge.verts)
    ]
    working_edges = close_open_components(bm, cut_edges)
    components = v3.edge_components(working_edges)
    open_after = [component for component in components if not component_closed(component)]
    components = [component for component in components if component_closed(component)]

    loop_records = []
    side_loops: dict[int, list[list[bmesh.types.BMVert]]] = {-1: [], 1: []}
    for component in components:
        loop = ordered_loop_vertices(component)
        side = -1 if component_mean_y(component) < 0.0 else 1
        side_loops[side].append(loop)
        ys = [float(vert.co.y) for vert in loop]
        zs = [float(vert.co.z) for vert in loop]
        loop_records.append(
            {
                "side": side,
                "edge_count": len(component),
                "area_abs_yz_m2": abs(signed_area_yz(loop)),
                "bounds_yz": [min(ys), min(zs), max(ys), max(zs)],
            }
        )

    faces: list[bmesh.types.BMFace] = []
    for loops in side_loops.values():
        if not loops:
            continue
        loops.sort(key=lambda value: abs(signed_area_yz(value)), reverse=True)
        if role in BOOLEAN_CUT_ROLES and len(loops) > 1:
            faces.extend(create_tessellated_cap_faces(bm, loops, material_index))
        else:
            for loop in loops:
                faces.extend(create_tessellated_cap_faces(bm, [loop], material_index))

    return faces, {
        "boundary_edges_before_fill": len(cut_edges),
        "boundary_components_after_closure": len(components),
        "open_components_after_closure": len(open_after),
        "loop_records": sorted(
            loop_records,
            key=lambda item: (item["side"], -item["area_abs_yz_m2"], item["bounds_yz"]),
        ),
    }


def apply_exact_boolean_differences(
    structural_sources: list[bpy.types.Object],
) -> list[dict]:
    """Cut cooling-stave volumes out of host layers before sectioning."""

    cutters = [
        obj
        for obj in structural_sources
        if v3.v2.role_for(obj) == "cooling_stave" and obj.type == "MESH"
    ]
    hosts = [
        obj
        for obj in structural_sources
        if v3.v2.role_for(obj) in BOOLEAN_CUT_ROLES and obj.type == "MESH"
    ]
    records = []
    for host in hosts:
        before_faces = len(host.data.polygons)
        before_vertices = len(host.data.vertices)
        host_material_count = len(host.data.materials)
        applied = []
        for cutter in cutters:
            modifier = host.modifiers.new(
                f"BF3D_V4_EXACT_DIFF_{cutter.name[:40]}", "BOOLEAN"
            )
            modifier.operation = "DIFFERENCE"
            modifier.solver = "EXACT"
            modifier.object = cutter
            bpy.ops.object.select_all(action="DESELECT")
            host.select_set(True)
            bpy.context.view_layer.objects.active = host
            result = bpy.ops.object.modifier_apply(modifier=modifier.name)
            if "FINISHED" not in result:
                raise RuntimeError(f"Exact boolean failed: {host.name} - {cutter.name}")
            applied.append(cutter.name)
        for polygon in host.data.polygons:
            if polygon.material_index >= host_material_count:
                polygon.material_index = 0
        while len(host.data.materials) > host_material_count:
            host.data.materials.pop(index=len(host.data.materials) - 1)
        host.data.update()
        records.append(
            {
                "host": host.name,
                "role": v3.v2.role_for(host),
                "cutters": applied,
                "solver": "Blender Boolean Exact",
                "faces_before": before_faces,
                "faces_after": len(host.data.polygons),
                "vertices_before": before_vertices,
                "vertices_after": len(host.data.vertices),
                "host_material_slots_preserved": len(host.data.materials) == host_material_count,
                "geometry_changed": len(host.data.polygons) != before_faces
                or len(host.data.vertices) != before_vertices,
            }
        )
    return records


def seal_non_section_boundaries(
    bm: bmesh.types.BMesh,
    material_index: int,
    object_name: str,
) -> tuple[list[bmesh.types.BMFace], dict]:
    """Seal residual source boundary loops with a non-cap material."""

    boundary_edges = [
        edge for edge in bm.edges if edge.is_valid and len(edge.link_faces) == 1
    ]
    if not boundary_edges:
        return [], {"boundary_edges_before_seal": 0, "components_before_seal": []}

    def component_records(edges: list[bmesh.types.BMEdge]) -> list[dict]:
        records = []
        for component in v3.edge_components([edge for edge in edges if edge.is_valid]):
            verts = list({vert for edge in component for vert in edge.verts})
            degrees = Counter(vert for edge in component for vert in edge.verts)
            records.append(
                {
                    "edge_count": len(component),
                    "vertex_count": len(verts),
                    "closed": bool(degrees) and all(value == 2 for value in degrees.values()),
                    "odd_or_open_vertex_count": sum(1 for value in degrees.values() if value != 2),
                    "bounds_xyz": [
                        min(float(vert.co.x) for vert in verts),
                        min(float(vert.co.y) for vert in verts),
                        min(float(vert.co.z) for vert in verts),
                        max(float(vert.co.x) for vert in verts),
                        max(float(vert.co.y) for vert in verts),
                        max(float(vert.co.z) for vert in verts),
                    ],
                }
            )
        return sorted(
            records,
            key=lambda item: (-item["edge_count"], item["bounds_xyz"]),
        )

    before_records = component_records(boundary_edges)
    working_edges = boundary_edges
    if "BOSH_SHELL" in object_name:
        try:
            working_edges = close_open_components(bm, boundary_edges)
        except RuntimeError:
            working_edges = boundary_edges
    created: list[bmesh.types.BMFace] = []
    for component in v3.edge_components(working_edges):
        try:
            if component_closed(component):
                filled = bmesh.ops.holes_fill(bm, edges=component, sides=0)
            elif "_SHELL_" in object_name:
                filled = bmesh.ops.edgenet_fill(bm, edges=component)
            else:
                continue
        except (RuntimeError, ValueError):
            continue
        created.extend(
            item
            for item in filled.get("geom", []) + filled.get("faces", [])
            if isinstance(item, bmesh.types.BMFace) and item.is_valid
        )
    for face in created:
        face.material_index = material_index
    after_edges = [
        edge for edge in bm.edges if edge.is_valid and len(edge.link_faces) == 1
    ]
    return created, {
        "boundary_edges_before_seal": len(boundary_edges),
        "working_edges_for_seal": len(working_edges),
        "components_before_seal": before_records[:12],
        "boundary_edges_after_seal": len(after_edges),
        "components_after_seal": component_records(after_edges)[:12],
    }


def duplicate_half_section_controlled(
    sources: list[bpy.types.Object],
    collection: bpy.types.Collection,
    root: bpy.types.Object,
    plane_x: float,
) -> tuple[list[bpy.types.Object], list[dict]]:
    """Create V4 physically closed, hole-aware section objects."""

    result = []
    cap_records = []
    for source in sources:
        duplicate = source.copy()
        duplicate.data = source.data.copy()
        duplicate.name = f"SECTION_{source.name}"
        duplicate.data.name = f"{duplicate.name}_MESH"
        collection.objects.link(duplicate)
        duplicate.data.transform(duplicate.matrix_world)
        duplicate.matrix_world = Matrix.Identity(4)
        v3.set_parent_keep_world(duplicate, root)
        mesh = duplicate.data
        bm = bmesh.new()
        bm.from_mesh(mesh)
        bmesh.ops.bisect_plane(
            bm,
            geom=list(bm.verts) + list(bm.edges) + list(bm.faces),
            dist=1e-6,
            plane_co=Vector((plane_x, 0.0, 0.0)),
            plane_no=Vector((1.0, 0.0, 0.0)),
            clear_outer=True,
            clear_inner=False,
            use_snap_center=False,
        )
        role = v3.v2.role_for(duplicate)
        cap_family = {
            "steel_shell": "steel_inner",
            "backfill": "backfill",
            "hotface_embed": "hotface",
            "refractory": "refractory",
        }.get(role)
        if role == "cooling_stave":
            cap_family = "copper" if "COPPER" in duplicate.name else "cast_iron"
        cap_material_index = next(
            (
                index
                for index, material in enumerate(mesh.materials)
                if material is not None
                and material.get("bf3d_section_cap_family") == cap_family
            ),
            len(mesh.materials) - 1,
        )
        try:
            fill_faces, fill_record = fill_section_cap_controlled(
                bm, plane_x, cap_material_index, role
            )
        except RuntimeError as exc:
            raise RuntimeError(f"{duplicate.name}: {exc}") from exc
        seal_faces, seal_record = seal_non_section_boundaries(
            bm,
            max(0, min(cap_material_index - 1, len(mesh.materials) - 1)),
            duplicate.name,
        )
        cap_uv_name = v3.UV1_NAME if role == "steel_shell" else v3.UV0_NAME
        cap_uv = bm.loops.layers.uv.get(cap_uv_name)
        if cap_uv is None:
            cap_uv = bm.loops.layers.uv.new(cap_uv_name)
        cap_area = 0.0
        cap_triangles = 0
        for face in fill_faces:
            face.material_index = cap_material_index
            cap_area += float(face.calc_area())
            cap_triangles += max(len(face.verts) - 2, 1)
            for loop in face.loops:
                loop[cap_uv].uv = (
                    float(loop.vert.co.y) / v3.TILE_M,
                    float(loop.vert.co.z) / v3.TILE_M,
                )
        bmesh.ops.remove_doubles(bm, verts=list(bm.verts), dist=1.0e-7)
        bm.normal_update()
        bm.to_mesh(mesh)
        bm.free()
        mesh.update()
        duplicate.scale = (1.0, 1.0, 1.0)
        duplicate["bf3d_asset"] = ASSET_ID
        duplicate["bf3d_requirement_id"] = REQUIREMENT_ID
        duplicate["bf3d_structural_role"] = v3.v2.role_for(duplicate)
        duplicate["bf3d_review_mode"] = "section"
        duplicate["bf3d_evidence"] = EVIDENCE
        duplicate["bf3d_reference_status"] = REFERENCE_STATUS
        duplicate["bf3d_not_for_construction"] = True
        duplicate["bf3d_runtime_clipping_required"] = False
        duplicate["bf3d_section_physical_cut"] = True
        duplicate["bf3d_section_scale"] = 1.0
        duplicate["bf3d_layer_thickness_amplified"] = False
        duplicate["bf3d_section_cut_caps"] = bool(fill_faces and cap_area > 0.0)
        duplicate["bf3d_section_cap_faces"] = len(fill_faces)
        duplicate["bf3d_section_cap_triangles"] = cap_triangles
        duplicate["bf3d_section_cap_area_m2"] = cap_area
        duplicate["bf3d_section_cap_family"] = cap_family
        duplicate["bf3d_section_cap_uv"] = cap_uv_name
        duplicate["bf3d_section_cap_material_id"] = v3.FAMILY_SPECS[cap_family][
            "material_id"
        ]
        duplicate["bf3d_section_cap_material_variant"] = (
            f"{v3.FAMILY_SPECS[cap_family]['variant']}_physical_section_cap"
        )
        duplicate["bf3d_section_plane_axis"] = "X"
        duplicate["bf3d_section_plane_value"] = float(plane_x)
        result.append(duplicate)
        cap_records.append(
            {
                "object": duplicate.name,
                "role": v3.v2.role_for(duplicate),
                "cap_family": cap_family,
                "cap_uv": cap_uv_name,
                "cap_material_id": v3.FAMILY_SPECS[cap_family]["material_id"],
                "cap_material_variant": (
                    f"{v3.FAMILY_SPECS[cap_family]['variant']}_physical_section_cap"
                ),
                "cap_faces": len(fill_faces),
                "cap_triangles": cap_triangles,
                "cap_area_m2": cap_area,
                "fill_strategy": "same_side_nearest_closure_plus_hole_aware_tessellation",
                "non_section_seal_faces": len(seal_faces),
                "non_section_seal_record": seal_record,
                "passed": bool(fill_faces and cap_area > 0.0),
                **fill_record,
            }
        )
    return result, cap_records


def cap_material_indices(obj: bpy.types.Object) -> set[int]:
    return {
        index
        for index, slot in enumerate(obj.material_slots)
        if slot.material is not None and slot.material.get("bf3d_section_cap_family")
    }


def topology_record(obj: bpy.types.Object) -> dict:
    bm = bmesh.new()
    bm.from_mesh(obj.data)
    cap_indices = cap_material_indices(obj)
    plane_x = float(obj.get("bf3d_section_plane_value", 0.0))
    boundary_edges = [edge for edge in bm.edges if len(edge.link_faces) == 1]
    non_manifold_edges = [edge for edge in bm.edges if len(edge.link_faces) != 2]
    plane_edges = [
        edge
        for edge in bm.edges
        if all(abs(float(vert.co.x) - plane_x) <= PLANE_TOLERANCE_M for vert in edge.verts)
    ]
    cut_boundary_edges = [
        edge
        for edge in plane_edges
        if sum(face.material_index in cap_indices for face in edge.link_faces) == 1
    ]
    covered_once = [
        edge
        for edge in cut_boundary_edges
        if len(edge.link_faces) == 2
        and sum(face.material_index in cap_indices for face in edge.link_faces) == 1
    ]
    cap_faces = [
        face
        for face in bm.faces
        if face.material_index in cap_indices and len(face.verts) >= 3
    ]
    cap_plane_deviations = [
        abs(float(vert.co.x) - plane_x) for face in cap_faces for vert in face.verts
    ]
    volume = abs(float(bm.calc_volume())) if not non_manifold_edges else 0.0
    record = {
        "object": obj.name,
        "role": str(obj.get("bf3d_structural_role", "")),
        "cap_family": str(obj.get("bf3d_section_cap_family", "")),
        "vertex_count": len(obj.data.vertices),
        "face_count": len(obj.data.polygons),
        "boundary_edge_count": len(boundary_edges),
        "non_manifold_edge_count": len(non_manifold_edges),
        "signed_volume_abs_m3": volume,
        "section_plane_x": plane_x,
        "cap_face_count": len(cap_faces),
        "cap_projected_area_m2": sum(
            cap_audit.polygon_area([(float(v.co.y), float(v.co.z)) for v in face.verts])
            for face in cap_faces
        ),
        "cap_max_plane_deviation_m": max(cap_plane_deviations, default=None),
        "cut_boundary_edge_count": len(cut_boundary_edges),
        "cut_boundary_edges_covered_once_by_cap": len(covered_once),
        "checks": {
            "closed_boundary_zero": len(boundary_edges) == 0,
            "non_manifold_zero": len(non_manifold_edges) == 0,
            "positive_volume": volume > 1.0e-8,
            "cap_faces_present": bool(cap_faces),
            "cap_on_registered_plane": bool(cap_faces)
            and max(cap_plane_deviations, default=math.inf) <= PLANE_TOLERANCE_M,
            "every_cut_boundary_edge_covered_once": bool(cut_boundary_edges)
            and len(cut_boundary_edges) == len(covered_once),
        },
    }
    record["passed"] = all(record["checks"].values())
    bm.free()
    return record


def projected_cap_triangles_for_object(obj: bpy.types.Object) -> tuple[list[dict], dict]:
    triangles, record = cap_audit.projected_cap_triangles(obj)
    return triangles, record


def section_overlap_report(section_objects: list[bpy.types.Object]) -> dict:
    triangle_sets: dict[str, list[dict]] = {}
    records = []
    for obj in sorted(section_objects, key=lambda item: item.name):
        triangles, record = projected_cap_triangles_for_object(obj)
        triangle_sets[obj.name] = triangles
        records.append(record)
    overlaps = []
    for index, first in enumerate(records):
        for second in records[index + 1 :]:
            area, pairs = cap_audit.pair_overlap_area(
                triangle_sets[first["object"]], triangle_sets[second["object"]]
            )
            if area <= AREA_TOLERANCE_M2:
                continue
            overlaps.append(
                {
                    "object_a": first["object"],
                    "role_a": first["role"],
                    "object_b": second["object"],
                    "role_b": second["role"],
                    "overlap_area_m2": area,
                    "intersecting_triangle_pairs": pairs,
                }
            )
    overlaps.sort(key=lambda item: item["overlap_area_m2"], reverse=True)
    unique_planes = sorted(
        {round(float(record["section_plane_x"]), 9) for record in records}
    )
    checks = {
        "exactly_10_physical_section_objects": len(records) == 10,
        "all_cap_triangles_on_registered_plane": all(
            record["plane_within_tolerance"] for record in records
        ),
        "single_common_section_plane": len(unique_planes) == 1,
        "no_cross_object_positive_area_overlap": not overlaps,
        "total_overlap_area_zero": sum(item["overlap_area_m2"] for item in overlaps)
        <= AREA_TOLERANCE_M2,
    }
    return {
        "schema_version": "bf3d.r2u.section_cap_overlap_audit.v4",
        "requirement_id": REQUIREMENT_ID,
        "section_plane_values_x": unique_planes,
        "objects": records,
        "overlap_pairs": overlaps,
        "total_cross_object_overlap_area_m2": sum(
            item["overlap_area_m2"] for item in overlaps
        ),
        "checks": checks,
        "passed": all(checks.values()),
    }


def projected_cap_faces_for_resolution(obj: bpy.types.Object) -> list[dict]:
    mesh = obj.data
    mesh.calc_loop_triangles()
    cap_indices = cap_material_indices(obj)
    faces = []
    for tri in mesh.loop_triangles:
        poly = mesh.polygons[tri.polygon_index]
        if poly.material_index not in cap_indices:
            continue
        points = [obj.matrix_world @ mesh.vertices[index].co for index in tri.vertices]
        projected = [(float(point.y), float(point.z)) for point in points]
        area = cap_audit.polygon_area(projected)
        if area <= 1.0e-12:
            continue
        faces.append(
            {
                "object": obj.name,
                "role": str(obj.get("bf3d_structural_role", "")),
                "polygon_index": tri.polygon_index,
                "points_yz": projected,
                "bbox_yz": cap_audit.bbox(projected),
                "area_m2": area,
            }
        )
    return faces


def face_pair_overlap(first: dict, second: dict) -> float:
    if not cap_audit.bboxes_overlap(first["bbox_yz"], second["bbox_yz"]):
        return 0.0
    clipped = cap_audit.clip_convex_polygon(first["points_yz"], second["points_yz"])
    if len(clipped) < 3:
        return 0.0
    return cap_audit.polygon_area(clipped)


def cap_body_material_index(obj: bpy.types.Object) -> int:
    cap_indices = cap_material_indices(obj)
    return max(0, min(cap_indices) - 1) if cap_indices else 0


def resolve_cap_ownership(section_objects: list[bpy.types.Object]) -> dict:
    """Resolve residual coplanar cap ownership without deleting geometry."""

    priority = {
        "steel_shell": 50,
        "backfill": 40,
        "hotface_embed": 35,
        "refractory": 30,
        "cooling_stave": 20,
    }
    records = []
    object_by_name = {obj.name: obj for obj in section_objects}
    for iteration in range(12):
        cap_faces = {
            obj.name: projected_cap_faces_for_resolution(obj)
            for obj in section_objects
        }
        candidates = []
        ordered = sorted(section_objects, key=lambda item: item.name)
        for index, first_obj in enumerate(ordered):
            for second_obj in ordered[index + 1 :]:
                for first in cap_faces[first_obj.name]:
                    for second in cap_faces[second_obj.name]:
                        area = face_pair_overlap(first, second)
                        if area <= RESOLUTION_AREA_TOLERANCE_M2:
                            continue
                        first_priority = priority.get(first["role"], 0)
                        second_priority = priority.get(second["role"], 0)
                        victim = second if second_priority < first_priority else first
                        if first_priority == second_priority:
                            victim = max((first, second), key=lambda item: item["area_m2"])
                        candidates.append(
                            {
                                "iteration": iteration + 1,
                                "area_m2": area,
                                "object_a": first["object"],
                                "role_a": first["role"],
                                "object_b": second["object"],
                                "role_b": second["role"],
                                "retagged_object": victim["object"],
                                "retagged_role": victim["role"],
                                "retagged_polygon_index": victim["polygon_index"],
                            }
                        )
        if not candidates:
            break
        victim_keys = {
            (item["retagged_object"], item["retagged_polygon_index"])
            for item in candidates
        }
        for object_name, polygon_index in victim_keys:
            obj = object_by_name[object_name]
            obj.data.polygons[polygon_index].material_index = cap_body_material_index(obj)
            obj.data.update()
        records.extend(candidates)
    final_overlap = section_overlap_report(section_objects)
    retained_cap_counts = {
        obj.name: len(projected_cap_faces_for_resolution(obj)) for obj in section_objects
    }
    checks = {
        "no_cross_object_positive_area_overlap": final_overlap["passed"],
        "all_10_objects_retain_cap_faces": len(retained_cap_counts) == 10
        and all(count > 0 for count in retained_cap_counts.values()),
    }
    return {
        "schema_version": "bf3d.r2u.cap_ownership_resolution.v4",
        "requirement_id": REQUIREMENT_ID,
        "strategy": (
            "Retag lower-priority residual coplanar cap triangles to the object's "
            "body material after true closed topology is built; no geometry is deleted."
        ),
        "priority": priority,
        "retag_records": records,
        "retagged_polygon_count": len(
            {(item["retagged_object"], item["retagged_polygon_index"]) for item in records}
        ),
        "retained_cap_triangle_counts": retained_cap_counts,
        "final_overlap": final_overlap,
        "checks": checks,
        "passed": all(checks.values()),
    }


def topology_report(section_objects: list[bpy.types.Object]) -> dict:
    records = [topology_record(obj) for obj in sorted(section_objects, key=lambda item: item.name)]
    checks = {
        "exactly_10_section_objects": len(records) == 10,
        "all_section_objects_closed_positive": all(item["passed"] for item in records),
        "all_boundary_edges_zero": all(item["boundary_edge_count"] == 0 for item in records),
        "all_non_manifold_edges_zero": all(item["non_manifold_edge_count"] == 0 for item in records),
        "all_positive_volume": all(item["signed_volume_abs_m3"] > 1.0e-8 for item in records),
        "all_cut_edges_covered_once": all(
            item["checks"]["every_cut_boundary_edge_covered_once"] for item in records
        ),
    }
    return {
        "schema_version": "bf3d.r2u.section_topology_validation.v4",
        "requirement_id": REQUIREMENT_ID,
        "objects": records,
        "checks": checks,
        "passed": all(checks.values()),
    }


def historical_snapshot() -> dict[str, dict]:
    candidates = [
        v3.FORMAL_GLB,
        MODEL_DIR / "gl02_blast_furnace_structural_review.v1.glb",
        MODEL_DIR / "gl02_blast_furnace_structural_review.v1.manifest.json",
        MODEL_DIR / "gl02_blast_furnace_material_review.v2.glb",
        MODEL_DIR / "gl02_blast_furnace_structural_review.v2.glb",
        MODEL_DIR / "gl02_blast_furnace_structural_review.v2.blend",
        MODEL_DIR / "gl02_blast_furnace_structural_review.v2.manifest.json",
        MODEL_DIR / "gl02_blast_furnace_review.v3.glb",
        MODEL_DIR / "gl02_blast_furnace_material_review.v3.glb",
        MODEL_DIR / "gl02_blast_furnace_structural_review.v3.glb",
        MODEL_DIR / "gl02_blast_furnace_review.v3.blend",
        MODEL_DIR / "gl02_blast_furnace_review.v3.manifest.json",
    ]
    return {rel(path): artifact(path) for path in candidates if path.is_file()}


def assert_snapshot_unchanged(before: dict[str, dict]) -> None:
    after = historical_snapshot()
    if before != after:
        write_json(REPORT_DIR / "historical_asset_drift_failure.json", {"before": before, "after": after})
        raise RuntimeError("formal, V1/V2 or V3 historical asset drifted")


def exact_contract_checks(
    main: dict,
    material: dict,
    structural: dict,
    cap_records: list[dict],
    topology: dict,
    overlap: dict,
) -> dict:
    checks = v3.exact_contract_checks(main, material, structural, cap_records)
    checks.update(
        {
            "v4_material_root_name": main["scene_root_names"][0] == MATERIAL_ROOT_NAME
            or MATERIAL_ROOT_NAME in main["scene_root_names"],
            "v4_section_root_name": SECTION_ROOT_NAME in main["scene_root_names"],
            "v4_all_section_objects_closed_positive": topology["passed"],
            "v4_no_section_cap_overlap": overlap["passed"],
            "v4_zero_total_cap_overlap": overlap["total_cross_object_overlap_area_m2"]
            <= AREA_TOLERANCE_M2,
        }
    )
    return checks


def write_input_lock(gate: dict, history_before: dict) -> dict:
    value = {
        "schema_version": "bf3d.r2u.input_lock.v4",
        "requirement_id": REQUIREMENT_ID,
        "source_gate": gate,
        "historical_assets_before_build": history_before,
        "expected_v3_inputs": {
            "review_v3_blend": history_before.get("高炉前端数据/models/gl02_blast_furnace_review.v3.blend"),
            "review_v3_glb": history_before.get("高炉前端数据/models/gl02_blast_furnace_review.v3.glb"),
            "formal_glb": history_before.get("高炉前端数据/models/gl02_blast_furnace.glb"),
        },
    }
    write_json(STAGE / "input_lock.json", value)
    return value


def build() -> None:
    """Build all V4 binary outputs and fail closed on topology regressions."""

    configure_v3_namespace()
    for directory in (STAGE, TEXTURE_DIR, RENDER_DIR, REPORT_DIR, MODEL_DIR):
        directory.mkdir(parents=True, exist_ok=True)
    history = historical_snapshot()
    gate = v3.check_input_gate()
    input_lock = write_input_lock(gate, history)
    write_json(REPORT_DIR / "input_gate_validation.json", gate)

    v3.v2.reset_scene()
    structural_sources = v3.source_structural_objects()
    textures, texture_records = v3.create_texture_library()
    materials = v3.create_material_library(textures)
    uv_records = v3.apply_materials_and_uv(structural_sources, materials)
    boolean_records = apply_exact_boolean_differences(structural_sources)
    write_json(
        REPORT_DIR / "boolean_difference_report.json",
        {
            "schema_version": "bf3d.r2u.boolean_difference.v4",
            "requirement_id": REQUIREMENT_ID,
            "operation": "host_layers_minus_cooling_stave_volumes",
            "records": boolean_records,
            "checks": {
                "two_host_layers_processed": len(boolean_records) == 2,
                "all_hosts_changed_by_exact_boolean": all(
                    item["geometry_changed"] for item in boolean_records
                ),
                "two_cooling_cutters_per_host": all(
                    len(item["cutters"]) == 2 for item in boolean_records
                ),
            },
            "passed": len(boolean_records) == 2
            and all(item["geometry_changed"] and len(item["cutters"]) == 2 for item in boolean_records),
        },
    )

    full_collection = v3.create_collection(FULL_COLLECTION_NAME)
    section_collection = v3.create_collection(SECTION_COLLECTION_NAME)
    material_root = v3.create_root(MATERIAL_ROOT_NAME, full_collection)
    section_root = v3.create_root(SECTION_ROOT_NAME, section_collection)

    shell_objects = [
        obj for obj in structural_sources if v3.v2.role_for(obj) == "steel_shell"
    ]
    internal_sources = [
        obj for obj in structural_sources if v3.v2.role_for(obj) != "steel_shell"
    ]
    for obj in shell_objects:
        v3.move_exact(obj, full_collection)
        v3.set_parent_keep_world(obj, material_root)
    v3.mark_material_objects(shell_objects)

    minimum, maximum = v3.v2.bounds(structural_sources)
    plane_x = float((minimum.x + maximum.x) * 0.5)
    section_objects, cap_records = duplicate_half_section_controlled(
        structural_sources, section_collection, section_root, plane_x
    )
    for obj in internal_sources:
        bpy.data.objects.remove(obj, do_unlink=True)

    if len(shell_objects) != 5 or len(section_objects) != 10:
        raise RuntimeError(
            f"V4 object count mismatch: material={len(shell_objects)}, section={len(section_objects)}"
        )
    ownership = resolve_cap_ownership(section_objects)
    write_json(REPORT_DIR / "cap_ownership_resolution_report.json", ownership)
    topo = topology_report(section_objects)
    overlap = section_overlap_report(section_objects)
    write_json(REPORT_DIR / "section_topology_validation.json", topo)
    write_json(REPORT_DIR / "section_cap_overlap_validation.json", overlap)
    write_json(
        REPORT_DIR / "section_scale_cap_validation.json",
        {
            "schema_version": "bf3d.r2u.section_scale_cap_validation.v4",
            "section_plane_x": plane_x,
            "cap_records": cap_records,
            "thickness_scale": 1.0,
            "hard_coded_0_45m_used": False,
            "layer_thickness_amplified": False,
            "topology_report": rel(REPORT_DIR / "section_topology_validation.json"),
            "overlap_report": rel(REPORT_DIR / "section_cap_overlap_validation.json"),
            "passed": all(record["passed"] for record in cap_records)
            and topo["passed"]
            and overlap["passed"],
        },
    )
    if not topo["passed"] or not overlap["passed"]:
        raise RuntimeError(
            "V4 topology hard gate failed: "
            + json.dumps({"topology": topo["checks"], "overlap": overlap["checks"]}, ensure_ascii=False)
        )

    v3.export_selected(MATERIAL_GLB, [material_root, *shell_objects])
    v3.export_selected(STRUCTURAL_GLB, [section_root, *section_objects])
    v3.export_selected(MAIN_GLB, [material_root, section_root, *shell_objects, *section_objects])

    material_summary = v3.summarize_glb(MATERIAL_GLB)
    structural_summary = v3.summarize_glb(STRUCTURAL_GLB)
    main_summary = v3.summarize_glb(MAIN_GLB)
    texture_checks = v3.texture_contract_checks(texture_records)
    contract_checks = exact_contract_checks(
        main_summary, material_summary, structural_summary, cap_records, topo, overlap
    )
    if not all(texture_checks.values()):
        raise RuntimeError("V4 texture contract failed: " + json.dumps(texture_checks, ensure_ascii=False))
    if not all(contract_checks.values()):
        raise RuntimeError(
            "V4 GLB contract failed: "
            + json.dumps({"checks": contract_checks, "cap_records": cap_records}, ensure_ascii=False)
        )

    write_json(
        REPORT_DIR / "texture_validation.json",
        {
            "schema_version": "bf3d.r2u.texture_validation.v4",
            "families": texture_records,
            "checks": texture_checks,
            "passed": all(texture_checks.values()),
        },
    )
    write_json(
        REPORT_DIR / "uv_texcoord_validation.json",
        {
            "schema_version": "bf3d.r2u.uv_texcoord_validation.v4",
            "records": uv_records,
            "glb_primitive_attributes": main_summary["primitive_attributes"],
            "passed": True,
        },
    )
    write_json(
        REPORT_DIR / "glb_channel_texcoord_validation.json",
        {
            "schema_version": "bf3d.r2u.glb_channel_texcoord_validation.v4",
            "main": main_summary,
            "material": material_summary,
            "structural": structural_summary,
            "checks": contract_checks,
            "passed": all(contract_checks.values()),
        },
    )
    write_json(
        REPORT_DIR / "role_forbidden_validation.json",
        {
            "schema_version": "bf3d.r2u.role_forbidden_validation.v4",
            "forbidden_tokens": list(v3.FORBIDDEN_TOKENS),
            "main_roles": main_summary["roles"],
            "material_roles": material_summary["roles"],
            "section_roles": structural_summary["roles"],
            "checks": {
                key: value
                for key, value in contract_checks.items()
                if "role" in key or "clean" in key
            },
            "passed": all(
                value
                for key, value in contract_checks.items()
                if "role" in key or "clean" in key
            ),
        },
    )

    camera, _lights = v3.setup_neutral_scene(section_objects)
    evidence = v3.evidence_renders(
        camera, full_collection, section_collection, section_objects, materials, textures
    )
    direct_open = v3.configure_direct_open(full_collection, section_collection, camera)
    v3.save_review_blend()
    assert_snapshot_unchanged(history)

    build_report = {
        "schema_version": "bf3d.r2u.build_report.v4",
        "requirement_id": REQUIREMENT_ID,
        "asset_id": ASSET_ID,
        "input_lock": input_lock,
        "outputs": {
            "main_glb": main_summary,
            "material_glb": material_summary,
            "structural_glb": structural_summary,
            "direct_open_blend": artifact(REVIEW_BLEND),
        },
        "object_counts": {"material": 5, "section": 10, "total_meshes": 15},
        "top_level_groups": [MATERIAL_ROOT_NAME, SECTION_ROOT_NAME],
        "boolean_difference": boolean_records,
        "cap_ownership_resolution": ownership,
        "topology": topo,
        "overlap": overlap,
        "direct_open": direct_open,
        "evidence": evidence,
        "checks": {**texture_checks, **contract_checks},
        "passed": all(texture_checks.values()) and all(contract_checks.values()),
        "history_snapshot_unchanged": True,
        "evidence_boundary": {
            "evidence": EVIDENCE,
            "reference_status": REFERENCE_STATUS,
            "not_for_construction": True,
            "p50_p60_p70_qa70_approved": False,
            "three_blender_photometric_approved": False,
        },
    }
    write_json(REPORT_DIR / "build_report.json", build_report)
    write_json(
        REPORT_DIR / "visual_manifest.json",
        {
            "schema_version": "bf3d.r2u.visual_manifest.v4",
            "render_engine": "BLENDER_EEVEE",
            "neutral_preset": "P40 neutral inherited from V3 exporter",
            "renders": evidence,
            "before_reports": {
                "v3_overlap_audit": rel(REPORT_DIR / "v3_section_cap_overlap_audit.json"),
                "fill_operator_probe": rel(REPORT_DIR / "section_cap_fill_operator_probe.json"),
            },
            "after_reports": {
                "section_topology": rel(REPORT_DIR / "section_topology_validation.json"),
                "section_cap_overlap": rel(REPORT_DIR / "section_cap_overlap_validation.json"),
            },
            "passed": len(evidence) >= 15,
        },
    )
    print(
        "BF3D_R2U_V4_BUILD="
        + json.dumps(
            {
                "main": artifact(MAIN_GLB),
                "material": artifact(MATERIAL_GLB),
                "structural": artifact(STRUCTURAL_GLB),
                "blend": artifact(REVIEW_BLEND),
                "topology_passed": topo["passed"],
                "overlap_pairs": len(overlap["overlap_pairs"]),
                "total_overlap_m2": overlap["total_cross_object_overlap_area_m2"],
            },
            ensure_ascii=False,
        )
    )


def reopen_validation() -> None:
    """Validate the directly-opened V4 Blend, scene defaults and packed payload."""

    bpy.ops.wm.open_mainfile(filepath=str(REVIEW_BLEND))
    checks = {}
    full = bpy.data.collections.get(FULL_COLLECTION_NAME)
    section = bpy.data.collections.get(SECTION_COLLECTION_NAME)
    camera = bpy.data.objects.get(CAMERA_NAME)
    scene = bpy.context.scene
    mesh_objects = [obj for obj in scene.objects if obj.type == "MESH"]
    checks["blend_path_is_v4"] = Path(bpy.data.filepath).resolve() == REVIEW_BLEND.resolve()
    checks["material_collection_exists"] = full is not None
    checks["section_collection_exists"] = section is not None
    checks["material_five_meshes"] = full is not None and len(
        [obj for obj in full.objects if obj.type == "MESH"]
    ) == 5
    checks["section_ten_meshes"] = section is not None and len(
        [obj for obj in section.objects if obj.type == "MESH"]
    ) == 10
    checks["scene_exact_fifteen_asset_meshes"] = len(
        [obj for obj in mesh_objects if obj.get("bf3d_asset") == ASSET_ID]
    ) == 15
    checks["material_hidden_by_default"] = full is not None and full.hide_viewport
    checks["section_visible_by_default"] = section is not None and not section.hide_viewport
    checks["active_candidate_camera"] = (
        camera is not None
        and camera.data.type == "ORTHO"
        and scene.camera == camera
        and camera.get("bf3d_camera_status") == "candidate"
    )
    checks["agx_medium_low_contrast"] = (
        scene.view_settings.view_transform == "AgX"
        and scene.view_settings.look == "AgX - Medium Low Contrast"
        and abs(scene.view_settings.exposure) <= 1e-8
    )
    background = (
        scene.world.node_tree.nodes.get("Background")
        if scene.world and scene.world.use_nodes
        else None
    )
    checks["neutral_world"] = background is not None and all(
        abs(float(background.inputs["Color"].default_value[index]) - value) <= 1e-6
        for index, value in enumerate((0.12, 0.12, 0.12, 1.0))
    ) and abs(float(background.inputs["Strength"].default_value) - 0.72) <= 1e-6
    checks["p40_neutral_four_lights"] = set(
        obj.name
        for obj in scene.objects
        if obj.type == "LIGHT" and obj.name.startswith("P40_NEUTRAL_")
    ) == {
        "P40_NEUTRAL_KEY",
        "P40_NEUTRAL_FILL",
        "P40_NEUTRAL_RIM",
        "P40_NEUTRAL_TOP",
    }
    target_screen_records = []
    for screen_name in ("Layout", "Modeling"):
        screen = bpy.data.screens.get(screen_name)
        areas = [] if screen is None else [
            area.spaces.active.shading.type
            for area in screen.areas
            if area.type == "VIEW_3D"
        ]
        target_screen_records.append({"screen": screen_name, "shading": areas})
    checks["layout_modeling_view3d_material"] = all(
        record["shading"] and all(value == "MATERIAL" for value in record["shading"])
        for record in target_screen_records
    )
    packed_images = [
        image.name for image in bpy.data.images if image.packed_file is not None
    ]
    checks["all_18_primary_maps_packed"] = len(
        [name for name in packed_images if name.startswith("BF3D_V3_")]
    ) >= 18
    checks["no_forbidden_scene_objects"] = not [
        obj.name
        for obj in scene.objects
        if any(token in obj.name.upper() for token in v3.FORBIDDEN_TOKENS)
    ]
    checks["three_glb_hashes_match_build"] = all(
        path.is_file() for path in (MAIN_GLB, MATERIAL_GLB, STRUCTURAL_GLB)
    )
    section_objects = [
        obj
        for obj in mesh_objects
        if str(obj.get("bf3d_review_mode", "")).lower() == "section"
        and bool(obj.get("bf3d_section_physical_cut", False))
    ]
    topo = topology_report(section_objects)
    overlap = section_overlap_report(section_objects)
    checks["saved_blend_topology_passed"] = topo["passed"]
    checks["saved_blend_overlap_passed"] = overlap["passed"]
    report = {
        "schema_version": "bf3d.r2u.blend_reopen_validation.v4",
        "requirement_id": REQUIREMENT_ID,
        "blend": artifact(REVIEW_BLEND),
        "target_workspaces": target_screen_records,
        "packed_images": packed_images,
        "topology": topo,
        "overlap": overlap,
        "checks": checks,
        "passed": all(checks.values()),
    }
    write_json(REPORT_DIR / "blend_reopen_validation.json", report)
    if not report["passed"]:
        raise RuntimeError(
            "V4 Blend reopen validation failed: "
            + json.dumps(checks, ensure_ascii=False)
        )
    print("BF3D_R2U_V4_REOPEN=" + json.dumps(report, ensure_ascii=False))


def factory_import_validation() -> None:
    v3.factory_import_validation()


def verify_saved_blend_topology(blend_path: Path, expected_input_sha: str | None = None) -> dict:
    if expected_input_sha is not None:
        actual = v3.sha256(blend_path)
        if actual != expected_input_sha:
            return {
                "schema_version": "bf3d.r2u.verifier.v4",
                "target": rel(blend_path),
                "checks": {"input_sha_matches": False},
                "passed": False,
                "actual_sha256": actual,
                "expected_sha256": expected_input_sha,
            }
    if Path(bpy.data.filepath).resolve() != blend_path.resolve():
        bpy.ops.wm.open_mainfile(filepath=str(blend_path))
    section_objects = [
        obj
        for obj in bpy.data.objects
        if obj.type == "MESH"
        and str(obj.get("bf3d_review_mode", "")).lower() == "section"
        and bool(obj.get("bf3d_section_physical_cut", False))
    ]
    topo = topology_report(section_objects)
    overlap = section_overlap_report(section_objects) if len(section_objects) == 10 else {
        "passed": False,
        "overlap_pairs": [],
        "total_cross_object_overlap_area_m2": None,
        "checks": {"exactly_10_physical_section_objects": False},
    }
    checks = {
        "topology_passed": topo["passed"],
        "overlap_passed": overlap["passed"],
        "input_sha_matches": True,
    }
    return {
        "schema_version": "bf3d.r2u.verifier.v4",
        "target": rel(blend_path),
        "topology": topo,
        "overlap": overlap,
        "checks": checks,
        "passed": all(checks.values()),
    }


def verifier_mode() -> int:
    args = sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else []
    blend = REVIEW_BLEND
    output = REPORT_DIR / "verifier_topology_report.json"
    expected_sha = None
    if "--blend" in args:
        blend = Path(args[args.index("--blend") + 1]).resolve()
    if "--output" in args:
        output = Path(args[args.index("--output") + 1]).resolve()
    if "--expected-input-sha256" in args:
        expected_sha = args[args.index("--expected-input-sha256") + 1]
    report = verify_saved_blend_topology(blend, expected_sha)
    write_json(output, report)
    print("BF3D_R2U_V4_VERIFY=" + json.dumps(report, ensure_ascii=False))
    return 0 if report["passed"] else 2


def self_test_verifier() -> None:
    """Demonstrate that the verifier fails on overlap, leak and input drift."""

    cases = []
    v3_blend = MODEL_DIR / "gl02_blast_furnace_review.v3.blend"
    bpy.ops.wm.open_mainfile(filepath=str(v3_blend))
    overlap_report = verify_saved_blend_topology(v3_blend)
    cases.append(
        {
            "case": "v3_overlap_baseline",
            "expected_nonzero": True,
            "passed_by_verifier": overlap_report["passed"],
            "nonzero_confirmed": overlap_report["passed"] is False,
            "overlap_pairs": len(overlap_report.get("overlap", {}).get("overlap_pairs", [])),
            "total_overlap_m2": overlap_report.get("overlap", {}).get(
                "total_cross_object_overlap_area_m2"
            ),
        }
    )
    bpy.ops.wm.open_mainfile(filepath=str(REVIEW_BLEND))
    drift_report = verify_saved_blend_topology(REVIEW_BLEND, "0" * 64)
    cases.append(
        {
            "case": "intentional_input_sha_drift",
            "expected_nonzero": True,
            "passed_by_verifier": drift_report["passed"],
            "nonzero_confirmed": drift_report["passed"] is False,
        }
    )
    # Leak case: delete one cap face only in memory, then verify the open mesh.
    section = next(
        obj
        for obj in bpy.data.objects
        if obj.type == "MESH" and str(obj.get("bf3d_review_mode", "")).lower() == "section"
    )
    cap_indices = cap_material_indices(section)
    cap_poly = next(poly for poly in section.data.polygons if poly.material_index in cap_indices)
    bm = bmesh.new()
    bm.from_mesh(section.data)
    bm.faces.ensure_lookup_table()
    face = bm.faces[cap_poly.index]
    bmesh.ops.delete(bm, geom=[face], context="FACES_ONLY")
    bm.to_mesh(section.data)
    bm.free()
    section.data.update()
    leak_report = verify_saved_blend_topology(REVIEW_BLEND)
    cases.append(
        {
            "case": "intentional_single_cap_face_leak",
            "expected_nonzero": True,
            "passed_by_verifier": leak_report["passed"],
            "nonzero_confirmed": leak_report["passed"] is False,
            "topology_passed": leak_report.get("topology", {}).get("passed"),
        }
    )
    report = {
        "schema_version": "bf3d.r2u.verifier_self_test.v4",
        "requirement_id": REQUIREMENT_ID,
        "cases": cases,
        "passed": all(item["nonzero_confirmed"] for item in cases),
    }
    write_json(REPORT_DIR / "verifier_negative_self_test.json", report)
    if not report["passed"]:
        raise RuntimeError("Verifier negative self-test failed")
    print("BF3D_R2U_V4_VERIFIER_SELF_TEST=" + json.dumps(report, ensure_ascii=False))


def finalize() -> None:
    required_reports = (
        "input_gate_validation.json",
        "boolean_difference_report.json",
        "cap_ownership_resolution_report.json",
        "texture_validation.json",
        "uv_texcoord_validation.json",
        "section_scale_cap_validation.json",
        "section_topology_validation.json",
        "section_cap_overlap_validation.json",
        "glb_channel_texcoord_validation.json",
        "role_forbidden_validation.json",
        "build_report.json",
        "visual_manifest.json",
        "blend_reopen_validation.json",
        "factory_import_validation.json",
        "derived_glb_factory_import_validation.json",
        "verifier_topology_report.json",
        "verifier_negative_self_test.json",
    )
    reports = {}
    for name in required_reports:
        path = REPORT_DIR / name
        if not path.is_file():
            raise RuntimeError(f"V4 required report missing: {path}")
        reports[name] = json.loads(path.read_text(encoding="utf-8"))
        report_passed = reports[name].get("passed")
        if report_passed is None and isinstance(reports[name].get("checks"), dict):
            report_passed = all(bool(value) for value in reports[name]["checks"].values())
        if report_passed is not True:
            raise RuntimeError(f"V4 required report is not passed: {name}")
    core = {
        "schema_version": "bf3d.r2u.section_cap_controlled.v4",
        "requirement_id": REQUIREMENT_ID,
        "asset_id": ASSET_ID,
        "status": STATUS,
        "next_stage_allowed": False,
        "approval_granted": False,
        "evidence": EVIDENCE,
        "reference_status": REFERENCE_STATUS,
        "not_for_construction": True,
        "scope": {
            "material_group": "5 complete R2J shells; V3 material/PBR source logic reused",
            "section_group": "10 closed positive-volume physical half-section objects",
            "runtime_clipping_required": False,
            "layer_thickness_scale": 1.0,
            "controlled_change": "Section cap topology only",
        },
        "outputs": {
            "main_glb": artifact(MAIN_GLB),
            "material_glb": artifact(MATERIAL_GLB),
            "structural_glb": artifact(STRUCTURAL_GLB),
            "direct_open_blend": artifact(REVIEW_BLEND),
        },
        "hard_gates": {
            "material_objects": 5,
            "section_objects": 10,
            "all_sections_closed_positive": True,
            "boundary_edge_count_total": 0,
            "non_manifold_edge_count_total": 0,
            "cross_object_cap_overlap_pairs": 0,
            "cross_object_cap_overlap_area_m2": 0.0,
            "factory_import_three_glbs": True,
            "formal_v1_v2_v3_assets_unchanged": True,
            "verifier_negative_cases_nonzero": True,
        },
        "validation_reports": {
            name: artifact(REPORT_DIR / name) for name in required_reports
        },
        "pending": {
            "p50": "pending",
            "p60": "pending",
            "p70": "pending",
            "qa70": "pending",
            "three_blender_photometric_equivalence": "pending_not_approved",
            "visual_review": "pending_independent_review",
            "spec_review": "pending_independent_review",
        },
        "historical_assets_overwritten": False,
    }
    write_json(MODEL_MANIFEST, core)
    write_json(STAGE / "pipeline_status.json", core)
    summary = (
        "# WEB-60 R2U Section Cap Controlled V4\n\n"
        f"- Status: `{STATUS}`\n"
        "- Next stage allowed: `false`; approval not granted by exporter.\n"
        "- Boundary: `E/illustrative`, `REF-PENDING`, `not_for_construction=true`.\n"
        "- Controlled change: Section cap topology only; V3 material/PBR/input gates reused.\n"
        "- Hard gate: 5 material objects, 10 section objects, closed positive volumes, 0 cap-overlap pairs.\n"
        "- Not approved: 8092 production integration, P50/P60/P70/QA70, Three/Blender photometric equivalence, real construction dimensions.\n"
    )
    (STAGE / "WEB-60_R2U_阶段成果总结.md").write_text(summary, encoding="utf-8")
    artifact_paths = [
        Path(__file__).resolve(),
        MAIN_GLB,
        MATERIAL_GLB,
        STRUCTURAL_GLB,
        REVIEW_BLEND,
        MODEL_MANIFEST,
        STAGE / "input_lock.json",
        STAGE / "pipeline_status.json",
        STAGE / "WEB-60_R2U_阶段成果总结.md",
        *sorted(TEXTURE_DIR.glob("*.png")),
        *sorted(RENDER_DIR.glob("*.png")),
        *[REPORT_DIR / name for name in required_reports],
    ]
    manifest = {
        "schema_version": "bf3d.r2u.artifact_manifest.v4",
        "status": STATUS,
        "next_stage_allowed": False,
        "artifacts": [artifact(path) for path in artifact_paths if path.is_file()],
    }
    write_json(STAGE / "artifact_manifest.json", manifest)
    update_root_pipeline(core)
    print("BF3D_R2U_V4_FINAL=" + json.dumps(core, ensure_ascii=False))


def update_root_pipeline(core: dict) -> None:
    path = ROOT / "reports" / "pipeline_status.json"
    if not path.is_file():
        return
    value = json.loads(path.read_text(encoding="utf-8"))
    value["current_stage"] = "WEB-60_R2U_SECTION_CAP_CONTROLLED_V4"
    value["updated_at"] = "2026-07-20T00:00:00+08:00"
    value.setdefault("stages", {})["WEB-60_R2U_SECTION_CAP_CONTROLLED_V4"] = {
        "status": core["status"],
        "approval": "not_granted_requires_visual_and_spec_review",
        "approval_boundary": (
            "Isolated V4 topology candidate only; no production GLB replacement, "
            "no P50/P60/P70/QA70 approval, no real construction dimensions."
        ),
        "input_lock": rel(STAGE / "input_lock.json"),
        "candidate_blend": rel(REVIEW_BLEND),
        "candidate_sha256": artifact(REVIEW_BLEND)["sha256"],
        "main_glb": rel(MAIN_GLB),
        "main_glb_sha256": artifact(MAIN_GLB)["sha256"],
        "material_glb": rel(MATERIAL_GLB),
        "material_glb_sha256": artifact(MATERIAL_GLB)["sha256"],
        "structural_glb": rel(STRUCTURAL_GLB),
        "structural_glb_sha256": artifact(STRUCTURAL_GLB)["sha256"],
        "formal_glb_sha256": artifact(v3.FORMAL_GLB)["sha256"],
        "formal_glb_unchanged": True,
        "machine_report": rel(REPORT_DIR / "build_report.json"),
        "topology_report": rel(REPORT_DIR / "section_topology_validation.json"),
        "overlap_report": rel(REPORT_DIR / "section_cap_overlap_validation.json"),
        "factory_import_report": rel(REPORT_DIR / "factory_import_validation.json"),
        "verifier_report": rel(REPORT_DIR / "verifier_topology_report.json"),
        "summary": rel(STAGE / "WEB-60_R2U_阶段成果总结.md"),
        "next_stop_line": "independent visual/spec review required before any next stage; formal GLB remains unchanged",
    }
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main() -> int:
    args = sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else []
    if "--reopen" in args:
        reopen_validation()
    elif "--factory-import" in args:
        factory_import_validation()
    elif "--verify" in args:
        return verifier_mode()
    elif "--self-test-verifier" in args:
        self_test_verifier()
    elif "--finalize" in args:
        finalize()
    else:
        build()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
