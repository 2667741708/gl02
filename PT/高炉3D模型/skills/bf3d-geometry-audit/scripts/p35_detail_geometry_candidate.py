"""Build the non-destructive P35 shell-weld and tuyere-detail candidate.

The script is intentionally additive.  It creates three aggregate mesh objects
and twenty-six logical tuyere anchors, while leaving every pre-existing mesh,
UV layer, material assignment, object matrix, and sensor transform unchanged.
The coarse ``APPROX_GL02_cooling_bands_and_seams`` object is retained as a
hidden/export-excluded rollback backup.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import struct
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable, Sequence

import bmesh
import bpy
from mathutils import Matrix, Vector
from mathutils.bvhtree import BVHTree


HERE = Path(__file__).resolve().parent
SKILLS_DIR = Path(__file__).resolve().parents[2]
UV_DIR = SKILLS_DIR / "bf3d-uv-bake" / "scripts"
MATERIAL_DIR = SKILLS_DIR / "bf3d-industrial-materials" / "scripts"
sys.path[:0] = [str(HERE), str(UV_DIR), str(MATERIAL_DIR)]
import p00_import_audit as p00  # noqa: E402
import p21_shaft_bake_test as p21  # noqa: E402
import p30_shell_material_candidate as p30  # noqa: E402


ACCEPTED_INPUT_STAGES = {
    "P32_EQUIPMENT_MATERIAL_CANDIDATE",
    "P32_EQUIPMENT_MATERIAL_APPROVED",
}
OUTPUT_STAGE = "P35_DETAIL_GEOMETRY_CANDIDATE"
BACKUP_OBJECT = "APPROX_GL02_cooling_bands_and_seams"
DETAIL_COLLECTION = "P35_NONDESTRUCTIVE_DETAILS"
ANCHOR_COLLECTION = "P35_TUYERE_ANCHORS"
WELD_OBJECT = "APPROX_GL02_P35_shell_welds"
BODY_OBJECT = "APPROX_GL02_P35_tuyere_flange_bodies"
BOLT_OBJECT = "APPROX_GL02_P35_tuyere_bolts"
NEW_MESH_OBJECTS = (WELD_OBJECT, BODY_OBJECT, BOLT_OBJECT)
ANCHOR_PREFIX = "APPROX_GL02_P35_TUYERE_"

WELD_MATERIAL = "P35_dark_shell_weld"
FLANGE_MATERIAL = "P35_tuyere_flange_steel"
BOLT_MATERIAL = "P35_tuyere_fastener_steel"
NEW_MATERIALS = (WELD_MATERIAL, FLANGE_MATERIAL, BOLT_MATERIAL)

PROFILE: tuple[tuple[float, float], ...] = (
    (0.0, 2.05),
    (4.8, 2.35),
    (8.8, 2.95),
    (13.8, 4.15),
    (18.6, 4.46),
    (24.5, 4.05),
    (30.6, 3.36),
    (35.2, 2.78),
    (37.2, 2.42),
    (40.0, 2.18),
)
HORIZONTAL_WELD_ELEVATIONS_M = (
    10.4,
    12.8,
    15.2,
    17.6,
    20.0,
    22.4,
    24.8,
    29.6,
    32.0,
    34.4,
)
VERTICAL_BAND_BOUNDARIES_M = (
    10.4,
    12.8,
    15.2,
    17.6,
    20.0,
    22.4,
    24.8,
    27.171,
    29.6,
    32.0,
    34.4,
)
PROFILE_BREAKS_M = (13.8, 18.6, 24.5, 30.6)
LAYER_13_ELEVATION_M = 27.171
TRIANGLE_BUDGET = 32_600
SENSOR_CLEARANCE_M = 0.02
EXPECTED_TRIANGLES = 31_680

TUYERE_COUNT = 26
TUYERE_HEIGHT_M = 8.2
TUYERE_BLENDER_Z = TUYERE_HEIGHT_M - 20.0
TUYERE_SHELL_RADIUS_M = 2.86
TUYERE_START_RADIUS_M = 2.8886
TUYERE_AXIS_RADIAL = 0.977864
TUYERE_AXIS_VERTICAL = 0.209243
TUYERE_ANGLE_START_DEG = -90.0
TUYERE_ANGLE_STEP_DEG = 360.0 / TUYERE_COUNT


def parse_args() -> argparse.Namespace:
    argv = sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else []
    parser = argparse.ArgumentParser(description="Create the additive GL02 P35 detail-geometry candidate.")
    parser.add_argument("--source-glb", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    return parser.parse_args(argv)


def radius_at(height_m: float) -> float:
    if height_m <= PROFILE[0][0]:
        return PROFILE[0][1]
    if height_m >= PROFILE[-1][0]:
        return PROFILE[-1][1]
    for (h0, r0), (h1, r1) in zip(PROFILE, PROFILE[1:]):
        if h0 <= height_m <= h1:
            amount = (height_m - h0) / (h1 - h0)
            return r0 + (r1 - r0) * amount
    raise RuntimeError(f"Profile interpolation failed at {height_m}")


def srgb(hex_color: str) -> tuple[float, float, float, float]:
    text = hex_color.lstrip("#")
    channels = [int(text[index : index + 2], 16) / 255.0 for index in (0, 2, 4)]

    def linear(channel: float) -> float:
        return channel / 12.92 if channel <= 0.04045 else ((channel + 0.055) / 1.055) ** 2.4

    return tuple(linear(channel) for channel in channels) + (1.0,)


def create_material(
    name: str,
    color: str,
    metallic: float,
    roughness: float,
) -> bpy.types.Material:
    if bpy.data.materials.get(name) is not None:
        raise RuntimeError(f"P35 material already exists: {name}")
    material = bpy.data.materials.new(name)
    material.use_nodes = True
    material.diffuse_color = srgb(color)
    nodes = material.node_tree.nodes
    links = material.node_tree.links
    principled = nodes.get("Principled BSDF")
    if principled is None:
        nodes.clear()
        principled = nodes.new("ShaderNodeBsdfPrincipled")
        principled.name = "Principled BSDF"
        output = nodes.new("ShaderNodeOutputMaterial")
        output.name = "Material Output"
        links.new(principled.outputs["BSDF"], output.inputs["Surface"])
    principled.inputs["Base Color"].default_value = srgb(color)
    principled.inputs["Metallic"].default_value = metallic
    principled.inputs["Roughness"].default_value = roughness
    principled.inputs["Alpha"].default_value = 1.0
    emission = principled.inputs.get("Emission Color") or principled.inputs.get("Emission")
    if emission is not None:
        emission.default_value = (0.0, 0.0, 0.0, 1.0)
    if "Emission Strength" in principled.inputs:
        principled.inputs["Emission Strength"].default_value = 0.0
    material["bf3d_stage"] = OUTPUT_STAGE
    material["bf3d_opaque"] = True
    return material


@dataclass
class Geometry:
    vertices: list[tuple[float, float, float]] = field(default_factory=list)
    faces: list[tuple[int, int, int]] = field(default_factory=list)
    smooth: list[bool] = field(default_factory=list)

    def add(
        self,
        vertices: Iterable[Sequence[float]],
        faces: Iterable[Sequence[int]],
        smooth: Iterable[bool] | bool = True,
    ) -> None:
        local_vertices = [tuple(float(value) for value in vertex) for vertex in vertices]
        local_faces = [tuple(int(index) for index in face) for face in faces]
        offset = len(self.vertices)
        self.vertices.extend(local_vertices)
        self.faces.extend(tuple(offset + index for index in face) for face in local_faces)
        if isinstance(smooth, bool):
            self.smooth.extend([smooth] * len(local_faces))
        else:
            flags = [bool(value) for value in smooth]
            if len(flags) != len(local_faces):
                raise ValueError("Smooth flag count does not match face count")
            self.smooth.extend(flags)


def cap_faces(ring: Sequence[int], positive_axis: bool) -> list[tuple[int, int, int]]:
    """Triangulate a convex cap without adding a center vertex."""

    result: list[tuple[int, int, int]] = []
    for index in range(1, len(ring) - 1):
        face = (ring[0], ring[index], ring[index + 1])
        result.append(face if positive_axis else (face[0], face[2], face[1]))
    return result


def ring_basis(angle_deg: float) -> tuple[Vector, Vector]:
    theta = math.radians(angle_deg)
    radial = Vector((math.cos(theta), math.sin(theta), 0.0))
    circumferential = Vector((-math.sin(theta), math.cos(theta), 0.0))
    return radial, circumferential


def tuyere_frame(angle_deg: float) -> tuple[Vector, Vector, Vector, Vector]:
    radial, circumferential = ring_basis(angle_deg)
    axis = (radial * TUYERE_AXIS_RADIAL + Vector((0.0, 0.0, 1.0)) * TUYERE_AXIS_VERTICAL).normalized()
    plane_vertical = axis.cross(circumferential).normalized()
    start = radial * TUYERE_START_RADIUS_M + Vector((0.0, 0.0, TUYERE_BLENDER_Z))
    return start, axis, circumferential, plane_vertical


def ellipse_torus(
    center_radius: float,
    center_z: float,
    radial_radius: float,
    vertical_radius: float,
    ring_segments: int,
    tube_segments: int,
) -> tuple[list[tuple[float, float, float]], list[tuple[int, int, int]], list[bool]]:
    vertices: list[tuple[float, float, float]] = []
    for ring_index in range(ring_segments):
        theta = 2.0 * math.pi * ring_index / ring_segments
        radial = Vector((math.cos(theta), math.sin(theta), 0.0))
        for tube_index in range(tube_segments):
            phi = 2.0 * math.pi * tube_index / tube_segments
            point = (
                radial * (center_radius + radial_radius * math.cos(phi))
                + Vector((0.0, 0.0, center_z + vertical_radius * math.sin(phi)))
            )
            vertices.append(tuple(point))
    faces: list[tuple[int, int, int]] = []
    for ring_index in range(ring_segments):
        next_ring = (ring_index + 1) % ring_segments
        for tube_index in range(tube_segments):
            next_tube = (tube_index + 1) % tube_segments
            a = ring_index * tube_segments + tube_index
            b = next_ring * tube_segments + tube_index
            c = next_ring * tube_segments + next_tube
            d = ring_index * tube_segments + next_tube
            faces.extend(((a, b, c), (a, c, d)))
    return vertices, faces, [True] * len(faces)


def oriented_torus(
    center: Vector,
    axis: Vector,
    plane_u: Vector,
    plane_v: Vector,
    major_radius: float,
    tube_radius: float,
    ring_segments: int,
    tube_segments: int,
) -> tuple[list[tuple[float, float, float]], list[tuple[int, int, int]], list[bool]]:
    vertices: list[tuple[float, float, float]] = []
    for ring_index in range(ring_segments):
        theta = 2.0 * math.pi * ring_index / ring_segments
        ring_direction = (plane_u * math.cos(theta) + plane_v * math.sin(theta)).normalized()
        for tube_index in range(tube_segments):
            phi = 2.0 * math.pi * tube_index / tube_segments
            point = (
                center
                + ring_direction * (major_radius + tube_radius * math.cos(phi))
                + axis * (tube_radius * math.sin(phi))
            )
            vertices.append(tuple(point))
    faces: list[tuple[int, int, int]] = []
    for ring_index in range(ring_segments):
        next_ring = (ring_index + 1) % ring_segments
        for tube_index in range(tube_segments):
            next_tube = (tube_index + 1) % tube_segments
            a = ring_index * tube_segments + tube_index
            b = next_ring * tube_segments + tube_index
            c = next_ring * tube_segments + next_tube
            d = ring_index * tube_segments + next_tube
            faces.extend(((a, b, c), (a, c, d)))
    return vertices, faces, [True] * len(faces)


def path_tube(
    centers: Sequence[Vector],
    angle_deg: float,
    outward_radius: float,
    tangent_radius: float,
    sides: int,
) -> tuple[list[tuple[float, float, float]], list[tuple[int, int, int]], list[bool]]:
    if len(centers) < 2:
        raise ValueError("A path tube requires at least two center points")
    radial, circumferential = ring_basis(angle_deg)
    vertices: list[tuple[float, float, float]] = []
    for index, center in enumerate(centers):
        if index == 0:
            path_tangent = (centers[1] - center).normalized()
        elif index == len(centers) - 1:
            path_tangent = (center - centers[index - 1]).normalized()
        else:
            path_tangent = (centers[index + 1] - centers[index - 1]).normalized()
        outward = circumferential.cross(path_tangent).normalized()
        if outward.dot(radial) < 0.0:
            outward.negate()
        for side in range(sides):
            phi = 2.0 * math.pi * side / sides
            point = center + outward * (outward_radius * math.cos(phi)) + circumferential * (
                tangent_radius * math.sin(phi)
            )
            vertices.append(tuple(point))

    faces: list[tuple[int, int, int]] = []
    smooth: list[bool] = []
    for row in range(len(centers) - 1):
        for side in range(sides):
            next_side = (side + 1) % sides
            a = row * sides + side
            b = row * sides + next_side
            c = (row + 1) * sides + next_side
            d = (row + 1) * sides + side
            faces.extend(((a, b, c), (a, c, d)))
            smooth.extend((True, True))
    start_cap = cap_faces(tuple(range(sides)), positive_axis=False)
    end_offset = (len(centers) - 1) * sides
    end_cap = cap_faces(tuple(end_offset + index for index in range(sides)), positive_axis=True)
    faces.extend(start_cap)
    faces.extend(end_cap)
    smooth.extend([False] * (len(start_cap) + len(end_cap)))
    return vertices, faces, smooth


def oriented_cylinder(
    start: Vector,
    end: Vector,
    radius: float,
    sides: int,
    plane_u: Vector,
    plane_v: Vector,
) -> tuple[list[tuple[float, float, float]], list[tuple[int, int, int]], list[bool]]:
    vertices: list[tuple[float, float, float]] = []
    for center in (start, end):
        for side in range(sides):
            phi = 2.0 * math.pi * side / sides
            vertices.append(tuple(center + plane_u * (radius * math.cos(phi)) + plane_v * (radius * math.sin(phi))))
    faces: list[tuple[int, int, int]] = []
    smooth: list[bool] = []
    for side in range(sides):
        next_side = (side + 1) % sides
        faces.extend(((side, next_side, sides + next_side), (side, sides + next_side, sides + side)))
        smooth.extend((True, True))
    start_cap = cap_faces(tuple(range(sides)), positive_axis=False)
    end_cap = cap_faces(tuple(sides + side for side in range(sides)), positive_axis=True)
    faces.extend(start_cap)
    faces.extend(end_cap)
    smooth.extend([False] * (len(start_cap) + len(end_cap)))
    return vertices, faces, smooth


def oriented_frustum(
    start: Vector,
    end: Vector,
    start_radius: float,
    end_radius: float,
    sides: int,
    plane_u: Vector,
    plane_v: Vector,
) -> tuple[list[tuple[float, float, float]], list[tuple[int, int, int]], list[bool]]:
    vertices: list[tuple[float, float, float]] = []
    for center, radius in ((start, start_radius), (end, end_radius)):
        for side in range(sides):
            phi = 2.0 * math.pi * side / sides
            vertices.append(tuple(center + plane_u * (radius * math.cos(phi)) + plane_v * (radius * math.sin(phi))))
    faces: list[tuple[int, int, int]] = []
    smooth: list[bool] = []
    for side in range(sides):
        next_side = (side + 1) % sides
        faces.extend(((side, next_side, sides + next_side), (side, sides + next_side, sides + side)))
        smooth.extend((True, True))
    start_cap = cap_faces(tuple(range(sides)), positive_axis=False)
    end_cap = cap_faces(tuple(sides + side for side in range(sides)), positive_axis=True)
    faces.extend(start_cap)
    faces.extend(end_cap)
    smooth.extend([False] * (len(start_cap) + len(end_cap)))
    return vertices, faces, smooth


def oriented_annular_cylinder(
    start: Vector,
    end: Vector,
    outer_radius: float,
    inner_radius: float,
    sides: int,
    plane_u: Vector,
    plane_v: Vector,
) -> tuple[list[tuple[float, float, float]], list[tuple[int, int, int]], list[bool]]:
    vertices: list[tuple[float, float, float]] = []
    for center, radius in (
        (start, outer_radius),
        (end, outer_radius),
        (start, inner_radius),
        (end, inner_radius),
    ):
        for side in range(sides):
            phi = 2.0 * math.pi * side / sides
            vertices.append(tuple(center + plane_u * (radius * math.cos(phi)) + plane_v * (radius * math.sin(phi))))
    start_outer = 0
    end_outer = sides
    start_inner = sides * 2
    end_inner = sides * 3
    faces: list[tuple[int, int, int]] = []
    smooth: list[bool] = []
    for side in range(sides):
        next_side = (side + 1) % sides
        faces.extend(
            (
                (start_outer + side, start_outer + next_side, end_outer + next_side),
                (start_outer + side, end_outer + next_side, end_outer + side),
                (start_inner + side, end_inner + side, end_inner + next_side),
                (start_inner + side, end_inner + next_side, start_inner + next_side),
            )
        )
        smooth.extend((True, True, True, True))
        faces.extend(
            (
                (start_outer + side, start_inner + side, start_inner + next_side),
                (start_outer + side, start_inner + next_side, start_outer + next_side),
                (end_outer + side, end_outer + next_side, end_inner + next_side),
                (end_outer + side, end_inner + next_side, end_inner + side),
            )
        )
        smooth.extend((False, False, False, False))
    return vertices, faces, smooth


def beveled_hex_prism(
    center: Vector,
    axis: Vector,
    plane_u: Vector,
    plane_v: Vector,
    circumradius: float,
    thickness: float,
    bevel: float,
    rotation_rad: float,
) -> tuple[list[tuple[float, float, float]], list[tuple[int, int, int]], list[bool]]:
    sides = 6
    half = thickness * 0.5
    rings = (
        (-half, circumradius - bevel),
        (-half + bevel, circumradius),
        (half - bevel, circumradius),
        (half, circumradius - bevel),
    )
    vertices: list[tuple[float, float, float]] = []
    for along, radius in rings:
        ring_center = center + axis * along
        for side in range(sides):
            phi = rotation_rad + 2.0 * math.pi * side / sides
            vertices.append(
                tuple(ring_center + plane_u * (radius * math.cos(phi)) + plane_v * (radius * math.sin(phi)))
            )
    faces: list[tuple[int, int, int]] = []
    for ring_index in range(len(rings) - 1):
        first = ring_index * sides
        second = (ring_index + 1) * sides
        for side in range(sides):
            next_side = (side + 1) % sides
            faces.extend(
                (
                    (first + side, first + next_side, second + next_side),
                    (first + side, second + next_side, second + side),
                )
            )
    faces.extend(cap_faces(tuple(range(sides)), positive_axis=False))
    last = (len(rings) - 1) * sides
    faces.extend(cap_faces(tuple(last + side for side in range(sides)), positive_axis=True))
    return vertices, faces, [False] * len(faces)


def sample_band(start_m: float, end_m: float) -> list[float]:
    usable_start = start_m + 0.04
    usable_end = end_m - 0.04
    anchors = [usable_start]
    anchors.extend(value for value in PROFILE_BREAKS_M if usable_start < value < usable_end)
    anchors.append(usable_end)
    samples: list[float] = [anchors[0]]
    for left, right in zip(anchors, anchors[1:]):
        segments = max(1, math.ceil((right - left) / 0.60))
        for index in range(1, segments + 1):
            samples.append(left + (right - left) * index / segments)
    return samples


def create_mesh_object(
    name: str,
    geometry: Geometry,
    material: bpy.types.Material,
    collection: bpy.types.Collection,
) -> bpy.types.Object:
    if bpy.data.objects.get(name) is not None or bpy.data.meshes.get(f"{name}_mesh") is not None:
        raise RuntimeError(f"P35 output already exists: {name}")
    mesh = bpy.data.meshes.new(f"{name}_mesh")
    mesh.from_pydata(geometry.vertices, [], geometry.faces)
    mesh.update(calc_edges=True)
    if len(mesh.polygons) != len(geometry.smooth):
        raise RuntimeError(f"Polygon count mismatch for {name}")
    for polygon, use_smooth in zip(mesh.polygons, geometry.smooth):
        polygon.use_smooth = use_smooth
    mesh.materials.append(material)
    mesh["bf3d_stage"] = OUTPUT_STAGE
    obj = bpy.data.objects.new(name, mesh)
    collection.objects.link(obj)
    obj["bf3d_stage"] = OUTPUT_STAGE
    obj["bf3d_additive_detail"] = True
    obj["bf3d_export_include"] = True
    return obj


def ensure_collection(name: str, parent: bpy.types.Collection) -> bpy.types.Collection:
    if bpy.data.collections.get(name) is not None:
        raise RuntimeError(f"P35 collection already exists: {name}")
    collection = bpy.data.collections.new(name)
    parent.children.link(collection)
    return collection


def build_geometry() -> tuple[Geometry, Geometry, Geometry, dict[str, Any]]:
    welds = Geometry()
    bodies = Geometry()
    bolts = Geometry()

    for height_m in HORIZONTAL_WELD_ELEVATIONS_M:
        welds.add(
            *ellipse_torus(
                center_radius=radius_at(height_m) + 0.006,
                center_z=height_m - 20.0,
                radial_radius=0.012,
                vertical_radius=0.018,
                ring_segments=64,
                tube_segments=6,
            )
        )

    max_vertical_sample_m = 0.0
    vertical_piece_count = 0
    vertical_sample_counts: list[dict[str, Any]] = []
    for band_index, (start_m, end_m) in enumerate(zip(VERTICAL_BAND_BOUNDARIES_M, VERTICAL_BAND_BOUNDARIES_M[1:])):
        elevations = sample_band(start_m, end_m)
        max_vertical_sample_m = max(
            max_vertical_sample_m,
            max(right - left for left, right in zip(elevations, elevations[1:])),
        )
        base_angle = 22.5 if band_index % 2 == 0 else 11.25
        vertical_sample_counts.append(
            {
                "band_m": [start_m, end_m],
                "angles_deg": [base_angle + 45.0 * index for index in range(8)],
                "sample_elevations_m": elevations,
            }
        )
        for seam_index in range(8):
            angle_deg = base_angle + 45.0 * seam_index
            radial, _ = ring_basis(angle_deg)
            centers = [
                radial * (radius_at(height_m) + 0.006) + Vector((0.0, 0.0, height_m - 20.0))
                for height_m in elevations
            ]
            welds.add(*path_tube(centers, angle_deg, outward_radius=0.010, tangent_radius=0.012, sides=6))
            vertical_piece_count += 1

    logical_tuyeres: list[dict[str, Any]] = []
    for index in range(TUYERE_COUNT):
        angle_deg = TUYERE_ANGLE_START_DEG + TUYERE_ANGLE_STEP_DEG * index
        start, axis, plane_u, plane_v = tuyere_frame(angle_deg)

        welds.add(
            *oriented_torus(
                center=start + axis * 0.025,
                axis=axis,
                plane_u=plane_u,
                plane_v=plane_v,
                major_radius=0.112,
                tube_radius=0.011,
                ring_segments=16,
                tube_segments=6,
            )
        )
        bodies.add(
            *oriented_cylinder(
                start + axis * 0.025,
                start + axis * 0.185,
                radius=0.112,
                sides=16,
                plane_u=plane_u,
                plane_v=plane_v,
            )
        )
        bodies.add(
            *oriented_annular_cylinder(
                start + axis * 0.185,
                start + axis * 0.225,
                outer_radius=0.170,
                inner_radius=0.056,
                sides=20,
                plane_u=plane_u,
                plane_v=plane_v,
            )
        )
        bodies.add(
            *oriented_frustum(
                start + axis * 0.225,
                start + axis * 0.405,
                start_radius=0.105,
                end_radius=0.064,
                sides=16,
                plane_u=plane_u,
                plane_v=plane_v,
            )
        )

        bolt_head_center = start + axis * 0.235
        for bolt_index in range(6):
            phi = 2.0 * math.pi * bolt_index / 6
            center = bolt_head_center + plane_u * (0.125 * math.cos(phi)) + plane_v * (0.125 * math.sin(phi))
            bolts.add(
                *beveled_hex_prism(
                    center=center,
                    axis=axis,
                    plane_u=plane_u,
                    plane_v=plane_v,
                    circumradius=0.014,
                    thickness=0.020,
                    bevel=0.0025,
                    rotation_rad=phi + math.radians(30.0),
                )
            )
        logical_tuyeres.append(
            {
                "index": index + 1,
                "angle_deg": angle_deg,
                "height_m": TUYERE_HEIGHT_M,
                "start": [float(value) for value in start],
                "axis": [float(value) for value in axis],
                "sleeve_along_m": [0.025, 0.185],
                "flange_center_along_m": 0.205,
                "nozzle_along_m": [0.225, 0.405],
                "bolt_count": 6,
            }
        )

    design = {
        "profile": [{"height_m": height, "radius_m": radius} for height, radius in PROFILE],
        "horizontal_welds": {
            "count": len(HORIZONTAL_WELD_ELEVATIONS_M),
            "elevations_m": list(HORIZONTAL_WELD_ELEVATIONS_M),
            "excluded_layer_ring_m": LAYER_13_ELEVATION_M,
            "center_offset_m": 0.006,
            "segments": [64, 6],
            "ellipse_m": {"radial": 0.012, "vertical": 0.018},
        },
        "vertical_welds": {
            "piece_count": vertical_piece_count,
            "band_boundaries_m": list(VERTICAL_BAND_BOUNDARIES_M),
            "end_shortening_m": 0.04,
            "profile_breaks_m": list(PROFILE_BREAKS_M),
            "max_actual_sample_spacing_m": max_vertical_sample_m,
            "segments": 6,
            "ellipse_m": {"outward": 0.010, "tangent": 0.012},
            "bands": vertical_sample_counts,
        },
        "tuyeres": {
            "count": len(logical_tuyeres),
            "height_m": TUYERE_HEIGHT_M,
            "blender_z": TUYERE_BLENDER_Z,
            "shell_radius_m": TUYERE_SHELL_RADIUS_M,
            "start_radius_m": TUYERE_START_RADIUS_M,
            "axis": {"radial": TUYERE_AXIS_RADIAL, "vertical": TUYERE_AXIS_VERTICAL},
            "root_weld": {"along_m": 0.025, "major_radius_m": 0.112, "tube_radius_m": 0.011, "segments": [16, 6]},
            "sleeve": {"along_m": [0.025, 0.185], "radius_m": 0.112, "segments": 16},
            "flange": {
                "center_along_m": 0.205,
                "thickness_m": 0.040,
                "outer_radius_m": 0.170,
                "inner_radius_m": 0.056,
                "segments": 20,
            },
            "nozzle": {
                "along_m": [0.225, 0.405],
                "radii_m": [0.105, 0.064],
                "segments": 16,
            },
            "bolts": {
                "per_flange": 6,
                "total": TUYERE_COUNT * 6,
                "pitch_radius_m": 0.125,
                "hex_circumradius_m": 0.014,
                "thickness_m": 0.020,
                "bevel_m": 0.0025,
            },
            "items": logical_tuyeres,
        },
    }
    return welds, bodies, bolts, design


def matrix_hash_for_objects(names: Sequence[str]) -> str:
    digest = hashlib.sha256()
    for name in sorted(names):
        obj = bpy.data.objects.get(name)
        if obj is None:
            digest.update(f"MISSING:{name}".encode("utf-8"))
            continue
        digest.update(name.encode("utf-8"))
        digest.update(struct.pack("<16d", *(float(value) for row in obj.matrix_world for value in row)))
    return digest.hexdigest()


def mesh_hash_for_datablocks(names: Sequence[str], include_uv: bool) -> str:
    digest = hashlib.sha256()
    for name in sorted(names):
        mesh = bpy.data.meshes.get(name)
        if mesh is None:
            digest.update(f"MISSING:{name}".encode("utf-8"))
            continue
        digest.update(name.encode("utf-8"))
        digest.update(p21.geometry_sha256(mesh).encode("ascii"))
        if include_uv:
            digest.update(p21.uv_sha256(mesh).encode("ascii"))
    return digest.hexdigest()


def material_hash_for_datablocks(names: Sequence[str]) -> str:
    digest = hashlib.sha256()
    for name in sorted(names):
        material = bpy.data.materials.get(name)
        if material is None:
            digest.update(f"MISSING:{name}".encode("utf-8"))
            continue
        digest.update(name.encode("utf-8"))
        digest.update(p30.material_hash(material).encode("ascii"))
    return digest.hexdigest()


def vector_list(vector: Vector) -> list[float]:
    return [round(float(value), 9) for value in vector]


def aabb(objects: Sequence[bpy.types.Object]) -> tuple[Vector, Vector]:
    return p00.object_bounds([obj for obj in objects if obj.type == "MESH"])


def topology_for_object(obj: bpy.types.Object) -> dict[str, Any]:
    bm = bmesh.new()
    bm.from_mesh(obj.data)
    report = {
        "object": obj.name,
        "mesh": obj.data.name,
        "vertices": len(bm.verts),
        "edges": len(bm.edges),
        "faces": len(bm.faces),
        "triangles": sum(max(0, len(face.verts) - 2) for face in bm.faces),
        "boundary_edges": sum(1 for edge in bm.edges if edge.is_boundary),
        "non_manifold_edges": sum(1 for edge in bm.edges if not edge.is_manifold),
        "zero_area_faces": sum(1 for face in bm.faces if face.calc_area() <= 1e-12),
        "loose_vertices": sum(1 for vertex in bm.verts if not vertex.link_edges),
    }
    bm.free()
    return report


def sensor_clearance(
    sensor_records: Sequence[dict[str, Any]],
    detail_objects: Sequence[bpy.types.Object],
) -> dict[str, Any]:
    bvhs: list[tuple[str, BVHTree]] = []
    for obj in detail_objects:
        world_vertices = [obj.matrix_world @ vertex.co for vertex in obj.data.vertices]
        polygons = [tuple(int(index) for index in polygon.vertices) for polygon in obj.data.polygons]
        bvhs.append((obj.name, BVHTree.FromPolygons(world_vertices, polygons, all_triangles=True)))
    minimum = math.inf
    nearest: dict[str, Any] | None = None
    for sensor in sensor_records:
        point = Vector(sensor["world_position"])
        for object_name, tree in bvhs:
            match = tree.find_nearest(point)
            if match is None:
                continue
            location, _normal, face_index, distance = match
            if distance < minimum:
                minimum = float(distance)
                nearest = {
                    "sensor": sensor["name"],
                    "detail_object": object_name,
                    "distance_m": float(distance),
                    "nearest_point": vector_list(location),
                    "face_index": int(face_index),
                }
    return {
        "required_minimum_m": SENSOR_CLEARANCE_M,
        "actual_minimum_m": minimum if math.isfinite(minimum) else None,
        "nearest": nearest,
    }


def material_report(material: bpy.types.Material) -> dict[str, Any]:
    principled = material.node_tree.nodes.get("Principled BSDF")
    emission = principled.inputs.get("Emission Color") or principled.inputs.get("Emission")
    return {
        "name": material.name,
        "base_color": [float(value) for value in principled.inputs["Base Color"].default_value],
        "metallic": float(principled.inputs["Metallic"].default_value),
        "roughness": float(principled.inputs["Roughness"].default_value),
        "alpha": float(principled.inputs["Alpha"].default_value),
        "emission": [float(value) for value in emission.default_value] if emission is not None else None,
        "emission_strength": float(principled.inputs["Emission Strength"].default_value)
        if "Emission Strength" in principled.inputs
        else 0.0,
        "sha256": p30.material_hash(material),
    }


def cooling_snapshot(obj: bpy.types.Object) -> dict[str, Any]:
    return {
        "object": obj.name,
        "mesh": obj.data.name,
        "geometry_sha256": p21.geometry_sha256(obj.data),
        "uv_sha256": p21.uv_sha256(obj.data),
        "matrix": [round(float(value), 9) for row in obj.matrix_world for value in row],
        "material_slots": [material.name if material else None for material in obj.data.materials],
        "hide_viewport": bool(obj.hide_viewport),
        "hide_render": bool(obj.hide_render),
        "export_exclude": bool(obj.get("export_exclude", False)),
    }


def main() -> int:
    args = parse_args()
    output_dir = args.output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    source_glb = args.source_glb.resolve()
    input_blend = Path(bpy.data.filepath).resolve()
    if not source_glb.is_file():
        raise FileNotFoundError(source_glb)
    if not input_blend.is_file():
        raise FileNotFoundError("P35 requires a saved P32 checkpoint")

    scene = bpy.context.scene
    input_stage = str(scene.get("bf3d_stage", ""))
    if input_stage not in ACCEPTED_INPUT_STAGES:
        raise RuntimeError(f"Expected one of {sorted(ACCEPTED_INPUT_STAGES)}, got {input_stage!r}")
    for name in (*NEW_MESH_OBJECTS, *(f"{ANCHOR_PREFIX}{index:02d}" for index in range(1, TUYERE_COUNT + 1))):
        if bpy.data.objects.get(name) is not None:
            raise RuntimeError(f"P35 object already exists: {name}")

    source_hash_before = p00.sha256_file(source_glb)
    source = p00.source_node_contract(p00.read_glb_json(source_glb))
    imported_before = p00.imported_contract(source)
    original_object_names = tuple(sorted(obj.name for obj in bpy.data.objects))
    original_mesh_names = tuple(sorted(mesh.name for mesh in bpy.data.meshes))
    original_material_names = tuple(sorted(material.name for material in bpy.data.materials))
    protected_before = {
        "geometry_sha256": mesh_hash_for_datablocks(original_mesh_names, include_uv=False),
        "uv_sha256": mesh_hash_for_datablocks(original_mesh_names, include_uv=True),
        "matrix_sha256": matrix_hash_for_objects(original_object_names),
        "material_sha256": material_hash_for_datablocks(original_material_names),
    }
    bounds_before = aabb(list(bpy.data.objects))

    cooling = bpy.data.objects.get(BACKUP_OBJECT)
    if cooling is None or cooling.type != "MESH":
        raise RuntimeError(f"Missing original cooling/seam backup object: {BACKUP_OBJECT}")
    cooling_before = cooling_snapshot(cooling)

    weld_material = create_material(WELD_MATERIAL, "#292A27", metallic=0.18, roughness=0.80)
    flange_material = create_material(FLANGE_MATERIAL, "#3B413E", metallic=0.72, roughness=0.48)
    bolt_material = create_material(BOLT_MATERIAL, "#59615E", metallic=0.86, roughness=0.38)
    weld_geometry, body_geometry, bolt_geometry, design = build_geometry()

    details = ensure_collection(DETAIL_COLLECTION, scene.collection)
    anchors = ensure_collection(ANCHOR_COLLECTION, details)
    weld_object = create_mesh_object(WELD_OBJECT, weld_geometry, weld_material, details)
    body_object = create_mesh_object(BODY_OBJECT, body_geometry, flange_material, details)
    bolt_object = create_mesh_object(BOLT_OBJECT, bolt_geometry, bolt_material, details)
    weld_object["bf3d_horizontal_weld_count"] = len(HORIZONTAL_WELD_ELEVATIONS_M)
    weld_object["bf3d_vertical_weld_piece_count"] = 80
    weld_object["bf3d_tuyere_root_weld_count"] = TUYERE_COUNT
    body_object["bf3d_tuyere_body_count"] = TUYERE_COUNT
    bolt_object["bf3d_bolt_count"] = TUYERE_COUNT * 6

    anchor_names: list[str] = []
    for item in design["tuyeres"]["items"]:
        name = f"{ANCHOR_PREFIX}{int(item['index']):02d}"
        empty = bpy.data.objects.new(name, None)
        anchors.objects.link(empty)
        empty.empty_display_type = "ARROWS"
        empty.empty_display_size = 0.16
        empty.location = Vector(item["start"])
        axis = Vector(item["axis"])
        empty.rotation_mode = "QUATERNION"
        empty.rotation_quaternion = axis.to_track_quat("X", "Z")
        empty["bf3d_stage"] = OUTPUT_STAGE
        empty["bf3d_object_type"] = "logical_tuyere_anchor"
        empty["bf3d_tuyere_index"] = int(item["index"])
        empty["bf3d_angle_deg"] = float(item["angle_deg"])
        empty["bf3d_height_m"] = TUYERE_HEIGHT_M
        empty["bf3d_axis_world"] = item["axis"]
        # Blender ID properties do not portably support arrays of strings.
        empty["bf3d_detail_meshes_json"] = json.dumps(list(NEW_MESH_OBJECTS), ensure_ascii=False)
        empty["bf3d_export_include"] = True
        anchor_names.append(name)

    cooling.hide_viewport = True
    cooling.hide_render = True
    cooling["export_exclude"] = True
    cooling["bf3d_export_exclude"] = True
    cooling["bf3d_p35_hidden_backup"] = True
    cooling["bf3d_replaced_by"] = WELD_OBJECT
    cooling_after = cooling_snapshot(cooling)

    bpy.context.view_layer.update()
    imported_after = p00.imported_contract(source)
    protected_after = {
        "geometry_sha256": mesh_hash_for_datablocks(original_mesh_names, include_uv=False),
        "uv_sha256": mesh_hash_for_datablocks(original_mesh_names, include_uv=True),
        "matrix_sha256": matrix_hash_for_objects(original_object_names),
        "material_sha256": material_hash_for_datablocks(original_material_names),
    }
    bounds_after = aabb(list(bpy.data.objects))
    aabb_delta = max(
        abs(float(before) - float(after))
        for before_vector, after_vector in zip(bounds_before, bounds_after)
        for before, after in zip(before_vector, after_vector)
    )
    topology = [topology_for_object(obj) for obj in (weld_object, body_object, bolt_object)]
    topology_totals = {
        key: sum(int(item[key]) for item in topology)
        for key in (
            "vertices",
            "edges",
            "faces",
            "triangles",
            "boundary_edges",
            "non_manifold_edges",
            "zero_area_faces",
            "loose_vertices",
        )
    }
    clearance = sensor_clearance(imported_after["sensor_records"], (weld_object, body_object, bolt_object))
    source_hash_after = p00.sha256_file(source_glb)
    new_material_report = [
        material_report(material)
        for material in (weld_material, flange_material, bolt_material)
    ]
    material_ok = all(
        item["alpha"] == 1.0
        and item["emission_strength"] == 0.0
        and item["emission"] is not None
        and max(item["emission"][:3]) == 0.0
        for item in new_material_report
    )

    assertions = [
        {"id": "input_stage_is_p32", "ok": input_stage in ACCEPTED_INPUT_STAGES, "detail": input_stage},
        {
            "id": "source_glb_matches_lock",
            "ok": source_hash_before == p00.EXPECTED_SOURCE_SHA256,
            "detail": {"expected": p00.EXPECTED_SOURCE_SHA256, "actual": source_hash_before},
        },
        {
            "id": "source_glb_unchanged",
            "ok": source_hash_after == source_hash_before,
            "detail": {"before": source_hash_before, "after": source_hash_after},
        },
        {
            "id": "original_geometry_unchanged",
            "ok": protected_before["geometry_sha256"] == protected_after["geometry_sha256"],
            "detail": {"before": protected_before["geometry_sha256"], "after": protected_after["geometry_sha256"]},
        },
        {
            "id": "original_uv_unchanged",
            "ok": protected_before["uv_sha256"] == protected_after["uv_sha256"],
            "detail": {"before": protected_before["uv_sha256"], "after": protected_after["uv_sha256"]},
        },
        {
            "id": "original_matrices_unchanged",
            "ok": protected_before["matrix_sha256"] == protected_after["matrix_sha256"],
            "detail": {"before": protected_before["matrix_sha256"], "after": protected_after["matrix_sha256"]},
        },
        {
            "id": "original_materials_unchanged",
            "ok": protected_before["material_sha256"] == protected_after["material_sha256"],
            "detail": {"before": protected_before["material_sha256"], "after": protected_after["material_sha256"]},
        },
        {
            "id": "sensor_contract_unchanged",
            "ok": imported_before["sensor_records"] == imported_after["sensor_records"]
            and imported_after["sensor_count"] == 115
            and imported_after["body_sensor_count"] == 80,
            "detail": {
                "sensor_count": imported_after["sensor_count"],
                "body_sensor_count": imported_after["body_sensor_count"],
                "matrix_mismatches": imported_after["matrix_mismatches"][:8],
            },
        },
        {
            "id": "ten_layer_groups_preserved",
            "ok": all(item["exists"] and len(item["children"]) == 8 for item in imported_after["layer_groups"].values()),
            "detail": {name: len(item["children"]) for name, item in imported_after["layer_groups"].items()},
        },
        {
            "id": "old_cooling_mesh_unchanged",
            "ok": cooling_before["geometry_sha256"] == cooling_after["geometry_sha256"]
            and cooling_before["uv_sha256"] == cooling_after["uv_sha256"]
            and cooling_before["matrix"] == cooling_after["matrix"]
            and cooling_before["material_slots"] == cooling_after["material_slots"],
            "detail": {"before": cooling_before, "after": cooling_after},
        },
        {
            "id": "old_cooling_mesh_hidden_export_backup",
            "ok": cooling_after["hide_viewport"] and cooling_after["hide_render"] and cooling_after["export_exclude"],
            "detail": cooling_after,
        },
        {
            "id": "only_three_new_mesh_objects",
            "ok": sorted(obj.name for obj in (weld_object, body_object, bolt_object)) == sorted(NEW_MESH_OBJECTS),
            "detail": list(NEW_MESH_OBJECTS),
        },
        {
            "id": "twenty_six_logical_tuyere_anchors",
            "ok": len(anchor_names) == TUYERE_COUNT and len(set(anchor_names)) == TUYERE_COUNT,
            "detail": anchor_names,
        },
        {
            "id": "tuyere_body_count_26",
            "ok": int(body_object["bf3d_tuyere_body_count"]) == 26,
            "detail": int(body_object["bf3d_tuyere_body_count"]),
        },
        {
            "id": "flange_bolt_count_156",
            "ok": int(bolt_object["bf3d_bolt_count"]) == 156,
            "detail": int(bolt_object["bf3d_bolt_count"]),
        },
        {
            "id": "vertical_profile_sampling_at_most_0_60m",
            "ok": float(design["vertical_welds"]["max_actual_sample_spacing_m"]) <= 0.6000001,
            "detail": float(design["vertical_welds"]["max_actual_sample_spacing_m"]),
        },
        {
            "id": "l13_ring_not_duplicated",
            "ok": all(abs(height - LAYER_13_ELEVATION_M) > 1e-6 for height in HORIZONTAL_WELD_ELEVATIONS_M),
            "detail": list(HORIZONTAL_WELD_ELEVATIONS_M),
        },
        {
            "id": "new_geometry_closed_manifold",
            "ok": topology_totals["boundary_edges"] == 0 and topology_totals["non_manifold_edges"] == 0,
            "detail": topology_totals,
        },
        {
            "id": "new_geometry_has_no_degenerate_or_loose_elements",
            "ok": topology_totals["zero_area_faces"] == 0 and topology_totals["loose_vertices"] == 0,
            "detail": topology_totals,
        },
        {
            "id": "triangle_count_matches_design",
            "ok": topology_totals["triangles"] == EXPECTED_TRIANGLES,
            "detail": {"expected": EXPECTED_TRIANGLES, "actual": topology_totals["triangles"]},
        },
        {
            "id": "triangle_budget_at_most_32600",
            "ok": topology_totals["triangles"] <= TRIANGLE_BUDGET,
            "detail": {"budget": TRIANGLE_BUDGET, "actual": topology_totals["triangles"]},
        },
        {
            "id": "sensor_clearance_at_least_0_02m",
            "ok": clearance["actual_minimum_m"] is not None
            and float(clearance["actual_minimum_m"]) + 1e-9 >= SENSOR_CLEARANCE_M,
            "detail": clearance,
        },
        {
            "id": "global_aabb_unchanged",
            "ok": aabb_delta <= 1e-9,
            "detail": {
                "before": [vector_list(bounds_before[0]), vector_list(bounds_before[1])],
                "after": [vector_list(bounds_after[0]), vector_list(bounds_after[1])],
                "max_abs_delta_m": aabb_delta,
            },
        },
        {
            "id": "new_materials_opaque_non_emissive",
            "ok": material_ok,
            "detail": new_material_report,
        },
    ]
    ok = all(bool(item["ok"]) for item in assertions)
    candidate = None
    if ok:
        scene["bf3d_stage"] = OUTPUT_STAGE
        scene["bf3d_parent_checkpoint"] = str(input_blend)
        scene["bf3d_source_glb"] = str(source_glb)
        scene["bf3d_change_dimension"] = "additive_profile_welds_and_tuyere_hard_surface_details_only"
        scene["bf3d_triangle_budget"] = TRIANGLE_BUDGET
        scene["bf3d_requires_fixed_camera_review"] = True
        scene["bf3d_p35_backup_object"] = BACKUP_OBJECT
        candidate_path = output_dir / "P35_DETAIL_GEOMETRY_CANDIDATE.blend"
        bpy.ops.wm.save_as_mainfile(filepath=str(candidate_path), check_existing=False)
        candidate = {
            "path": str(candidate_path),
            "bytes": candidate_path.stat().st_size,
            "sha256": p00.sha256_file(candidate_path),
        }

    report = {
        "schema_version": 1,
        "stage": OUTPUT_STAGE,
        "status": "candidate_ready_for_visual_review" if ok else "fail",
        "input_checkpoint": {
            "path": str(input_blend),
            "bytes": input_blend.stat().st_size,
            "sha256": p00.sha256_file(input_blend),
            "stage": input_stage,
        },
        "source_glb": {
            "path": str(source_glb),
            "sha256_before": source_hash_before,
            "sha256_after": source_hash_after,
        },
        "candidate": candidate,
        "single_changed_dimension": (
            "Add profile-conforming shell welds and explicit tuyere flange/nozzle/bolt geometry; "
            "retain the coarse cooling mesh as a hidden rollback backup."
        ),
        "protected_originals": {
            "object_count": len(original_object_names),
            "mesh_count": len(original_mesh_names),
            "material_count": len(original_material_names),
            "before": protected_before,
            "after": protected_after,
        },
        "backup": {"before": cooling_before, "after": cooling_after},
        "new_objects": {
            "meshes": list(NEW_MESH_OBJECTS),
            "logical_tuyere_anchors": anchor_names,
            "collections": [DETAIL_COLLECTION, ANCHOR_COLLECTION],
        },
        "materials": new_material_report,
        "design": design,
        "topology": {"objects": topology, "totals": topology_totals, "triangle_budget": TRIANGLE_BUDGET},
        "sensor_clearance": clearance,
        "assertions": assertions,
        "approval": "pending_fixed_camera_global_shell_and_tuyere_detail_visual_review",
        "notes": [
            "The P35 geometry is approximate visualization detail, not an authoritative fabrication drawing.",
            "No original mesh, UV, material, object matrix, sensor, process-zone, or L7-L16 layer node is modified.",
            "The old cooling/seam mesh is hidden and export-excluded but remains intact in the candidate for rollback.",
            "P35 must not be promoted until global and CAM_DETAIL_SHELL/CAM_DETAIL_TUYERE comparisons pass.",
        ],
    }
    report_path = output_dir / "p35_detail_geometry_candidate.json"
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(
        json.dumps(
            {
                "status": report["status"],
                "candidate": candidate,
                "report": str(report_path),
                "triangles": topology_totals["triangles"],
                "sensor_clearance_m": clearance["actual_minimum_m"],
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0 if ok else 2


if __name__ == "__main__":
    raise SystemExit(main())
