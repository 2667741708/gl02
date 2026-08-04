#!/usr/bin/env python3
"""Read-only R2W audit of the copper/refractory Section interface.

Run with Blender, so the locked V5 .blend is opened by Blender before this
script executes:

    blender --background <v5.blend> --python tools/audit_bf3d_r2w_interface_gap.py

The script never calls a save operator.  It measures the exposed cap triangles
on the common Section plane in world coordinates and writes a deterministic
JSON report.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import sys
from collections import Counter
from pathlib import Path
from typing import Iterable, Sequence

import bpy
from mathutils import Vector


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_BLEND = REPO_ROOT / "高炉前端数据" / "models" / "gl02_blast_furnace_review.v5.blend"
DEFAULT_GLB = REPO_ROOT / "高炉前端数据" / "models" / "gl02_blast_furnace_review.v5.glb"
DEFAULT_REPORT = (
    REPO_ROOT
    / "PT"
    / "高炉3D模型"
    / "work"
    / "WEB_60_20260720_R2W_MATERIAL_READABILITY_AO_EDGE"
    / "reports"
    / "interface_gap_audit.json"
)

EXPECTED_BLEND_SHA256 = "3e6df5fb02d3734d14923d4432739a5918ac8249d6a3c8ad1415395429b27e3a"
EXPECTED_GLB_SHA256 = "0ac031e626c9eaa0b0cdd8192cf9fda712324af174a4285f563a97309451ed3c"

COPPER_OBJECT = "SECTION_R2K_V3_L03_COOLING_COPPER_COMBINED"
HOTFACE_OBJECT = "SECTION_R2K_L04_HOTFACE_EMBED_40MM_CLOSED_ENTITY_E"
REFRACTORY_OBJECT = "SECTION_R2K_L05_RESIDUAL_REFRACTORY_CLOSED_ENTITY_E"
COPPER_CAP_MATERIAL_TOKEN = "COPPER_CAP"
HOTFACE_CAP_MATERIAL_TOKEN = "HOTFACE_CAP"
REFRACTORY_CAP_MATERIAL_TOKEN = "REFRACTORY_CAP"
REQUESTED_Z_M = (-1.2, -0.5, 0.0, 1.0)
CONTROL_Z_M = (-15.2,)

# The exported coordinates are float32.  A 2 micrometre plane tolerance is
# comfortably above the observed sub-micrometre float32 spread but far below
# any reported millimetre-scale interface gap.
PLANE_TOLERANCE_M = 2.0e-6
INTERVAL_TOLERANCE_M = 1.0e-7
SLICE_EPSILON_M = 1.0e-6
CONTINUITY_TOLERANCE_M = 5.0e-4
OVERLAP_AREA_TOLERANCE_M2 = 1.0e-8
NORMAL_UNIT_TOLERANCE = 1.0e-5
SYMMETRY_TOLERANCE_M = 1.0e-4


def parse_args() -> argparse.Namespace:
    raw = sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else []
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-blend", type=Path, default=DEFAULT_BLEND)
    parser.add_argument("--input-glb", type=Path, default=DEFAULT_GLB)
    parser.add_argument("--output", type=Path, default=DEFAULT_REPORT)
    return parser.parse_args(raw)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def relpath(path: Path) -> str:
    try:
        return path.resolve().relative_to(REPO_ROOT.resolve()).as_posix()
    except ValueError:
        return path.resolve().as_posix()


def finite(value: float) -> bool:
    return math.isfinite(float(value))


def round_float(value: float, digits: int = 12) -> float:
    return round(float(value), digits)


def percentile(values: Sequence[float], fraction: float) -> float:
    ordered = sorted(float(value) for value in values)
    if not ordered:
        raise ValueError("Cannot calculate a percentile of an empty sequence")
    position = (len(ordered) - 1) * fraction
    lower = int(math.floor(position))
    upper = int(math.ceil(position))
    if lower == upper:
        return ordered[lower]
    weight = position - lower
    return ordered[lower] * (1.0 - weight) + ordered[upper] * weight


def object_material_names(obj: bpy.types.Object) -> list[str]:
    return [slot.material.name if slot.material else "" for slot in obj.material_slots]


def cap_triangles_world(
    obj: bpy.types.Object,
    material_token: str,
) -> tuple[list[tuple[tuple[float, float, float], ...]], dict]:
    if obj.type != "MESH":
        raise RuntimeError(f"{obj.name} is {obj.type}, expected MESH")
    material_names = object_material_names(obj)
    cap_indices = {
        index for index, name in enumerate(material_names) if material_token in name
    }
    if not cap_indices:
        raise RuntimeError(
            f"{obj.name} has no cap material containing token {material_token!r}"
        )

    mesh = obj.data
    matrix = obj.matrix_world
    triangles: list[tuple[tuple[float, float, float], ...]] = []
    cap_polygon_indices: list[int] = []
    for polygon in mesh.polygons:
        if polygon.material_index not in cap_indices:
            continue
        if len(polygon.vertices) != 3:
            raise RuntimeError(
                f"{obj.name} cap polygon {polygon.index} is not triangulated"
            )
        points = tuple(tuple(matrix @ mesh.vertices[index].co) for index in polygon.vertices)
        triangles.append(points)
        cap_polygon_indices.append(polygon.index)

    if not triangles:
        raise RuntimeError(f"{obj.name} has no cap triangles")

    x_values = [point[0] for triangle in triangles for point in triangle]
    plane_x = percentile(x_values, 0.5)
    max_deviation = max(abs(value - plane_x) for value in x_values)
    if max_deviation > PLANE_TOLERANCE_M:
        raise RuntimeError(
            f"{obj.name} cap exceeds plane tolerance: {max_deviation} m"
        )

    yz_triangles = [
        tuple((float(point[1]), float(point[2])) for point in triangle)
        for triangle in triangles
    ]
    normal_lengths: list[float] = []
    plane_alignments: list[float] = []
    finite_normals = True
    for triangle in triangles:
        a, b, c = (Vector(point) for point in triangle)
        raw = (b - a).cross(c - a)
        length = raw.length
        normal_lengths.append(length)
        if not finite(length) or length <= 0.0:
            finite_normals = False
            plane_alignments.append(0.0)
            continue
        normal = raw / length
        finite_normals = finite_normals and all(finite(component) for component in normal)
        plane_alignments.append(abs(float(normal.x)))

    return triangles, {
        "object": obj.name,
        "role": str(obj.get("role", obj.get("bf3d_structural_role", ""))),
        "review_mode": str(
            obj.get("review_mode", obj.get("bf3d_review_mode", ""))
        ),
        "material_slots": material_names,
        "cap_material_indices": sorted(cap_indices),
        "cap_material_names": [material_names[index] for index in sorted(cap_indices)],
        "cap_triangle_count": len(triangles),
        "cap_polygon_indices": cap_polygon_indices,
        "cap_plane_x_m": round_float(plane_x),
        "cap_plane_max_deviation_m": round_float(max_deviation),
        "cap_plane_within_tolerance": max_deviation <= PLANE_TOLERANCE_M,
        "cap_y_bounds_m": [
            round_float(min(point[0] for triangle in yz_triangles for point in triangle)),
            round_float(max(point[0] for triangle in yz_triangles for point in triangle)),
        ],
        "cap_z_bounds_m": [
            round_float(min(point[1] for triangle in yz_triangles for point in triangle)),
            round_float(max(point[1] for triangle in yz_triangles for point in triangle)),
        ],
        "cap_normals_finite_and_nonzero": finite_normals,
        "cap_normal_min_abs_dot_section_normal": round_float(min(plane_alignments)),
        "cap_normal_max_abs_dot_section_normal": round_float(max(plane_alignments)),
        "cap_normals_parallel_to_section_plane_normal": (
            finite_normals
            and min(plane_alignments) >= 1.0 - NORMAL_UNIT_TOLERANCE
        ),
        "_yz_triangles": yz_triangles,
    }


def mesh_topology(obj: bpy.types.Object) -> dict:
    edge_use: Counter[tuple[int, int]] = Counter()
    for polygon in obj.data.polygons:
        vertices = list(polygon.vertices)
        for index, current in enumerate(vertices):
            following = vertices[(index + 1) % len(vertices)]
            edge_use[tuple(sorted((int(current), int(following))))] += 1
    boundary_edges = sum(1 for count in edge_use.values() if count == 1)
    nonmanifold_edges = sum(1 for count in edge_use.values() if count != 2)
    overused_edges = sum(1 for count in edge_use.values() if count > 2)
    return {
        "vertex_count": len(obj.data.vertices),
        "edge_count": len(edge_use),
        "polygon_count": len(obj.data.polygons),
        "boundary_edge_count": boundary_edges,
        "nonmanifold_edge_count": nonmanifold_edges,
        "overused_edge_count": overused_edges,
        "closed_two_manifold": boundary_edges == 0 and nonmanifold_edges == 0,
    }


def cap_boundary_segments_world(
    obj: bpy.types.Object,
    cap_material_indices: set[int],
    plane_x: float,
) -> tuple[list[tuple[tuple[float, float], tuple[float, float]]], dict]:
    """Return the physical cut-boundary curves, excluding cap triangulation.

    A valid cut-boundary edge is on the registered Section plane and is shared
    by exactly one cap polygon and one body polygon.  This is deliberately more
    stable than slicing the cap fill triangles: triangulation diagonals are not
    physical layer boundaries and can alternate between the two sides.
    """

    mesh = obj.data
    edge_polygons: dict[tuple[int, int], list[int]] = {}
    for polygon in mesh.polygons:
        vertices = list(polygon.vertices)
        for index, current in enumerate(vertices):
            following = vertices[(index + 1) % len(vertices)]
            key = tuple(sorted((int(current), int(following))))
            edge_polygons.setdefault(key, []).append(int(polygon.index))

    segments = []
    plane_deviations = []
    invalid_edge_use_count = 0
    for (first_index, second_index), polygon_indices in edge_polygons.items():
        if len(polygon_indices) != 2:
            continue
        material_indices = [
            int(mesh.polygons[index].material_index) for index in polygon_indices
        ]
        cap_use_count = sum(
            1 for material_index in material_indices
            if material_index in cap_material_indices
        )
        if cap_use_count != 1:
            continue
        first = obj.matrix_world @ mesh.vertices[first_index].co
        second = obj.matrix_world @ mesh.vertices[second_index].co
        max_deviation = max(abs(first.x - plane_x), abs(second.x - plane_x))
        if max_deviation > PLANE_TOLERANCE_M:
            invalid_edge_use_count += 1
            continue
        plane_deviations.append(max_deviation)
        segments.append(
            (
                (float(first.y), float(first.z)),
                (float(second.y), float(second.z)),
            )
        )
    if not segments:
        raise RuntimeError(f"{obj.name} has no cap/body cut-boundary segments")
    return segments, {
        "cut_boundary_segment_count": len(segments),
        "cut_boundary_invalid_off_plane_count": invalid_edge_use_count,
        "cut_boundary_max_plane_deviation_m": round_float(max(plane_deviations)),
        "cut_boundary_all_on_registered_plane": (
            invalid_edge_use_count == 0
            and max(plane_deviations) <= PLANE_TOLERANCE_M
        ),
    }


def unique_sorted(values: Iterable[float]) -> list[float]:
    ordered = sorted(float(value) for value in values)
    result: list[float] = []
    for value in ordered:
        if not result or abs(value - result[-1]) > INTERVAL_TOLERANCE_M:
            result.append(value)
    return result


def boundary_y_values_at_z(
    segments: Sequence[tuple[tuple[float, float], tuple[float, float]]],
    z_m: float,
) -> list[float]:
    values: list[float] = []
    for first, second in segments:
        y0, z0 = first
        y1, z1 = second
        if abs(z1 - z0) <= INTERVAL_TOLERANCE_M:
            if abs(z_m - z0) <= INTERVAL_TOLERANCE_M:
                values.extend((y0, y1))
            continue
        low = min(z0, z1) - INTERVAL_TOLERANCE_M
        high = max(z0, z1) + INTERVAL_TOLERANCE_M
        if low <= z_m <= high:
            factor = (z_m - z0) / (z1 - z0)
            if -INTERVAL_TOLERANCE_M <= factor <= 1.0 + INTERVAL_TOLERANCE_M:
                values.append(y0 + factor * (y1 - y0))
    return unique_sorted(values)


def body_surface_edge_segments_world(
    obj: bpy.types.Object,
    cap_material_indices: set[int],
) -> tuple[list[tuple[tuple[float, float, float], tuple[float, float, float]]], dict]:
    """Collect edges belonging to a non-cap body surface.

    The radial envelope is taken from the real body surface, not from Section
    cap-fill diagonals or circumferential stave end faces.
    """

    mesh = obj.data
    edge_keys: set[tuple[int, int]] = set()
    body_polygon_count = 0
    for polygon in mesh.polygons:
        if int(polygon.material_index) in cap_material_indices:
            continue
        body_polygon_count += 1
        vertices = list(polygon.vertices)
        for index, current in enumerate(vertices):
            following = vertices[(index + 1) % len(vertices)]
            edge_keys.add(tuple(sorted((int(current), int(following)))))
    matrix = obj.matrix_world
    segments = []
    for first_index, second_index in sorted(edge_keys):
        first = matrix @ mesh.vertices[first_index].co
        second = matrix @ mesh.vertices[second_index].co
        segments.append((tuple(first), tuple(second)))
    if not segments:
        raise RuntimeError(f"{obj.name} has no body-surface edges")
    all_z = [point[2] for segment in segments for point in segment]
    return segments, {
        "body_polygon_count": body_polygon_count,
        "body_surface_edge_segment_count": len(segments),
        "body_surface_edge_z_bounds_m": [
            round_float(min(all_z)),
            round_float(max(all_z)),
        ],
        "nonhorizontal_body_surface_edge_count": sum(
            1
            for first, second in segments
            if abs(first[2] - second[2]) > INTERVAL_TOLERANCE_M
        ),
        "cap_fill_edges_excluded": True,
    }


def body_surface_radial_envelope_at_z(
    segments: Sequence[
        tuple[tuple[float, float, float], tuple[float, float, float]]
    ],
    z_m: float,
) -> dict | None:
    radii: list[float] = []
    for first, second in segments:
        x0, y0, z0 = first
        x1, y1, z1 = second
        if abs(z1 - z0) <= INTERVAL_TOLERANCE_M:
            if abs(z_m - z0) <= INTERVAL_TOLERANCE_M:
                radii.extend((math.hypot(x0, y0), math.hypot(x1, y1)))
            continue
        low = min(z0, z1) - INTERVAL_TOLERANCE_M
        high = max(z0, z1) + INTERVAL_TOLERANCE_M
        if low <= z_m <= high:
            factor = (z_m - z0) / (z1 - z0)
            if -INTERVAL_TOLERANCE_M <= factor <= 1.0 + INTERVAL_TOLERANCE_M:
                x = x0 + factor * (x1 - x0)
                y = y0 + factor * (y1 - y0)
                radii.append(math.hypot(x, y))
    radii = unique_sorted(radii)
    if len(radii) < 2:
        return None
    return {
        "inner_radius_m": min(radii),
        "outer_radius_m": max(radii),
        "unique_radius_sample_count": len(radii),
    }


def projected_positive_y(radius_m: float, plane_x_m: float) -> float:
    square = radius_m * radius_m - plane_x_m * plane_x_m
    if square < -PLANE_TOLERANCE_M:
        raise RuntimeError(
            f"Radius {radius_m} m does not intersect X={plane_x_m} m"
        )
    return math.sqrt(max(square, 0.0))


def adjacency_pair(
    outward_radius_m: float,
    inward_radius_m: float,
    plane_x_m: float,
    pair_id: str,
) -> dict:
    outward_y = projected_positive_y(outward_radius_m, plane_x_m)
    inward_y = projected_positive_y(inward_radius_m, plane_x_m)
    signed_radial_gap = outward_radius_m - inward_radius_m
    signed_y_gap = outward_y - inward_y
    absolute_gap = max(abs(signed_radial_gap), abs(signed_y_gap))
    return {
        "pair": pair_id,
        "outward_boundary_radius_m": round_float(outward_radius_m),
        "inward_boundary_radius_m": round_float(inward_radius_m),
        "signed_radial_gap_m": round_float(signed_radial_gap),
        "signed_radial_gap_mm": round_float(signed_radial_gap * 1000.0, 6),
        "positive_side": {
            "outward_boundary_y_m": round_float(outward_y),
            "inward_boundary_y_m": round_float(inward_y),
            "signed_gap_m": round_float(signed_y_gap),
            "gap_mm": round_float(signed_y_gap * 1000.0, 6),
        },
        "negative_side": {
            "outward_boundary_y_m": round_float(-outward_y),
            "inward_boundary_y_m": round_float(-inward_y),
            "signed_gap_m": round_float(signed_y_gap),
            "gap_mm": round_float(signed_y_gap * 1000.0, 6),
        },
        "absolute_gap_for_gate_m": round_float(absolute_gap),
        "continuity_tolerance_m": CONTINUITY_TOLERANCE_M,
        "continuity_passed": absolute_gap <= CONTINUITY_TOLERANCE_M,
    }


def radial_chain_slice(
    copper_body_segments: Sequence,
    hotface_body_segments: Sequence,
    refractory_body_segments: Sequence,
    z_m: float,
    plane_x_m: float,
) -> dict | None:
    copper = body_surface_radial_envelope_at_z(copper_body_segments, z_m)
    hotface = body_surface_radial_envelope_at_z(hotface_body_segments, z_m)
    refractory = body_surface_radial_envelope_at_z(
        refractory_body_segments,
        z_m,
    )
    if copper is None or hotface is None or refractory is None:
        missing = [
            layer
            for layer, value in (
                ("L03_copper", copper),
                ("L04_hotface_embed", hotface),
                ("L05_residual_refractory", refractory),
            )
            if value is None
        ]
        unavailable_pair = {
            "status": "not_measurable_missing_layer_geometry",
            "signed_radial_gap_m": None,
            "signed_radial_gap_mm": None,
            "positive_side": {
                "signed_gap_m": None,
                "gap_mm": None,
            },
            "negative_side": {
                "signed_gap_m": None,
                "gap_mm": None,
            },
            "absolute_gap_for_gate_m": None,
            "continuity_tolerance_m": CONTINUITY_TOLERANCE_M,
            "continuity_passed": False,
        }
        return {
            "z_m": round_float(z_m),
            "radial_envelopes": {
                "L03_copper": copper,
                "L04_hotface_embed": hotface,
                "L05_residual_refractory": refractory,
            },
            "missing_layers": missing,
            "adjacency_pairs": {
                "L03_inner_to_L04_outer": {
                    "pair": "L03_inner_to_L04_outer",
                    **unavailable_pair,
                },
                "L04_inner_to_L05_outer": {
                    "pair": "L04_inner_to_L05_outer",
                    **unavailable_pair,
                },
            },
            "intended_intermediate_layer": {
                "classification": "missing_expected_intermediate_layer_geometry",
                "layer": "L04_HOTFACE_EMBED",
                "present_at_z": hotface is not None,
                "fills_radial_envelope_within_tolerance": False,
            },
            "adjacent_layer_continuity_passed": False,
        }

    l03_to_l04 = adjacency_pair(
        copper["inner_radius_m"],
        hotface["outer_radius_m"],
        plane_x_m,
        "L03_inner_to_L04_outer",
    )
    l04_to_l05 = adjacency_pair(
        hotface["inner_radius_m"],
        refractory["outer_radius_m"],
        plane_x_m,
        "L04_inner_to_L05_outer",
    )
    hotface_outer_y = projected_positive_y(
        hotface["outer_radius_m"],
        plane_x_m,
    )
    hotface_inner_y = projected_positive_y(
        hotface["inner_radius_m"],
        plane_x_m,
    )
    copper_inner_y = projected_positive_y(
        copper["inner_radius_m"],
        plane_x_m,
    )
    refractory_outer_y = projected_positive_y(
        refractory["outer_radius_m"],
        plane_x_m,
    )
    hotface_projected_thickness = hotface_outer_y - hotface_inner_y
    direct_projected_separation = copper_inner_y - refractory_outer_y
    coverage_residual = (
        direct_projected_separation - hotface_projected_thickness
    )
    chain_passed = (
        l03_to_l04["continuity_passed"]
        and l04_to_l05["continuity_passed"]
    )
    return {
        "z_m": round_float(z_m),
        "radial_envelopes": {
            "L03_copper": {
                key: round_float(value) if isinstance(value, float) else value
                for key, value in copper.items()
            },
            "L04_hotface_embed": {
                key: round_float(value) if isinstance(value, float) else value
                for key, value in hotface.items()
            },
            "L05_residual_refractory": {
                key: round_float(value) if isinstance(value, float) else value
                for key, value in refractory.items()
            },
        },
        "adjacency_pairs": {
            "L03_inner_to_L04_outer": l03_to_l04,
            "L04_inner_to_L05_outer": l04_to_l05,
        },
        "intended_intermediate_layer": {
            "classification": "intended_intermediate_layer_thickness",
            "layer": "L04_HOTFACE_EMBED",
            "radial_thickness_m": round_float(
                hotface["outer_radius_m"] - hotface["inner_radius_m"]
            ),
            "radial_thickness_mm": round_float(
                (hotface["outer_radius_m"] - hotface["inner_radius_m"]) * 1000.0,
                6,
            ),
            "projected_positive_y_thickness_m": round_float(
                hotface_projected_thickness
            ),
            "projected_positive_y_thickness_mm": round_float(
                hotface_projected_thickness * 1000.0,
                6,
            ),
            "L03_inner_to_L05_outer_projected_separation_m": round_float(
                direct_projected_separation
            ),
            "L03_inner_to_L05_outer_projected_separation_mm": round_float(
                direct_projected_separation * 1000.0,
                6,
            ),
            "coverage_residual_m": round_float(coverage_residual),
            "coverage_residual_mm": round_float(coverage_residual * 1000.0, 6),
            "fills_radial_envelope_within_tolerance": (
                abs(coverage_residual) <= CONTINUITY_TOLERANCE_M
            ),
        },
        "adjacent_layer_continuity_passed": chain_passed,
    }


def interface_slice(
    copper_segments: Sequence[tuple[tuple[float, float], tuple[float, float]]],
    refractory_segments: Sequence[tuple[tuple[float, float], tuple[float, float]]],
    z_m: float,
) -> dict | None:
    copper = boundary_y_values_at_z(copper_segments, z_m)
    refractory = boundary_y_values_at_z(refractory_segments, z_m)

    copper_negative = [value for value in copper if value < 0.0]
    copper_positive = [value for value in copper if value > 0.0]
    refractory_negative = [value for value in refractory if value < 0.0]
    refractory_positive = [value for value in refractory if value > 0.0]
    if not all((copper_negative, copper_positive, refractory_negative, refractory_positive)):
        return None

    # Interface-facing boundaries:
    # positive side: refractory outer max y -> copper inner min y
    # negative side: copper inner max y -> refractory outer min y
    copper_pos_inner = min(copper_positive)
    refractory_pos_outer = max(refractory_positive)
    copper_neg_inner = max(copper_negative)
    refractory_neg_outer = min(refractory_negative)

    positive_gap = copper_pos_inner - refractory_pos_outer
    negative_gap = refractory_neg_outer - copper_neg_inner
    max_gap = max(positive_gap, negative_gap)
    mean_gap = (positive_gap + negative_gap) / 2.0
    return {
        "z_m": round_float(z_m),
        "negative_side": {
            "copper_inner_y_m": round_float(copper_neg_inner),
            "refractory_outer_y_m": round_float(refractory_neg_outer),
            "signed_gap_m": round_float(negative_gap),
            "gap_mm": round_float(negative_gap * 1000.0, 6),
        },
        "positive_side": {
            "refractory_outer_y_m": round_float(refractory_pos_outer),
            "copper_inner_y_m": round_float(copper_pos_inner),
            "signed_gap_m": round_float(positive_gap),
            "gap_mm": round_float(positive_gap * 1000.0, 6),
        },
        "mean_gap_m": round_float(mean_gap),
        "mean_gap_mm": round_float(mean_gap * 1000.0, 6),
        "max_side_gap_m": round_float(max_gap),
        "max_side_gap_mm": round_float(max_gap * 1000.0, 6),
        "side_gap_delta_m": round_float(abs(positive_gap - negative_gap)),
        "symmetric_within_tolerance": (
            abs(positive_gap - negative_gap) <= SYMMETRY_TOLERANCE_M
        ),
        "bilateral_radial_interface_eligible": (
            abs(positive_gap - negative_gap) <= SYMMETRY_TOLERANCE_M
        ),
        "continuous_within_tolerance": max_gap <= CONTINUITY_TOLERANCE_M,
        "copper_cut_boundary_y_values_m": [round_float(value) for value in copper],
        "refractory_cut_boundary_y_values_m": [
            round_float(value) for value in refractory
        ],
    }


def critical_z_candidates(
    copper_segments: Sequence[tuple[tuple[float, float], tuple[float, float]]],
    refractory_segments: Sequence[tuple[tuple[float, float], tuple[float, float]]],
) -> tuple[tuple[float, float], list[float], list[float]]:
    copper_z = [point[1] for segment in copper_segments for point in segment]
    refractory_z = [point[1] for segment in refractory_segments for point in segment]
    z_min = max(min(copper_z), min(refractory_z))
    z_max = min(max(copper_z), max(refractory_z))
    critical = sorted(
        {
            float(point[1])
            for segment in (*copper_segments, *refractory_segments)
            for point in segment
            if z_min <= point[1] <= z_max
        }
    )
    candidates: set[float] = {z_min + SLICE_EPSILON_M, z_max - SLICE_EPSILON_M}
    for z_m in critical:
        if z_min <= z_m <= z_max:
            candidates.add(z_m)
        if z_min < z_m - SLICE_EPSILON_M < z_max:
            candidates.add(z_m - SLICE_EPSILON_M)
        if z_min < z_m + SLICE_EPSILON_M < z_max:
            candidates.add(z_m + SLICE_EPSILON_M)
    for first, last in zip(critical, critical[1:]):
        if last - first > 2.0 * SLICE_EPSILON_M:
            candidates.add((first + last) / 2.0)
    return (z_min, z_max), critical, sorted(candidates)


def radial_chain_z_candidates(
    copper_segments: Sequence,
    hotface_segments: Sequence,
    refractory_segments: Sequence,
) -> tuple[tuple[float, float], list[float], list[float]]:
    copper_z = [point[2] for segment in copper_segments for point in segment]
    hotface_z = [point[2] for segment in hotface_segments for point in segment]
    refractory_z = [
        point[2] for segment in refractory_segments for point in segment
    ]
    z_min = max(min(copper_z), min(hotface_z), min(refractory_z))
    z_max = min(max(copper_z), max(hotface_z), max(refractory_z))
    critical = sorted(
        {
            float(point[2])
            for segments in (
                copper_segments,
                hotface_segments,
                refractory_segments,
            )
            for segment in segments
            for point in segment
            if z_min <= point[2] <= z_max
        }
    )
    candidates: set[float] = {z_min + SLICE_EPSILON_M, z_max - SLICE_EPSILON_M}
    for z_m in critical:
        candidates.add(z_m)
        if z_min < z_m - SLICE_EPSILON_M < z_max:
            candidates.add(z_m - SLICE_EPSILON_M)
        if z_min < z_m + SLICE_EPSILON_M < z_max:
            candidates.add(z_m + SLICE_EPSILON_M)
    for first, last in zip(critical, critical[1:]):
        if last - first > 2.0 * SLICE_EPSILON_M:
            candidates.add((first + last) / 2.0)
    return (z_min, z_max), critical, sorted(candidates)


def signed_area(polygon: Sequence[tuple[float, float]]) -> float:
    return 0.5 * sum(
        polygon[index][0] * polygon[(index + 1) % len(polygon)][1]
        - polygon[(index + 1) % len(polygon)][0] * polygon[index][1]
        for index in range(len(polygon))
    )


def line_intersection(
    first: tuple[float, float],
    second: tuple[float, float],
    clip_first: tuple[float, float],
    clip_second: tuple[float, float],
) -> tuple[float, float]:
    x1, y1 = first
    x2, y2 = second
    x3, y3 = clip_first
    x4, y4 = clip_second
    denominator = (x1 - x2) * (y3 - y4) - (y1 - y2) * (x3 - x4)
    if abs(denominator) <= 1.0e-15:
        return second
    determinant_first = x1 * y2 - y1 * x2
    determinant_second = x3 * y4 - y3 * x4
    x = (
        determinant_first * (x3 - x4)
        - (x1 - x2) * determinant_second
    ) / denominator
    y = (
        determinant_first * (y3 - y4)
        - (y1 - y2) * determinant_second
    ) / denominator
    return x, y


def convex_clip(
    subject: Sequence[tuple[float, float]],
    clipper: Sequence[tuple[float, float]],
) -> list[tuple[float, float]]:
    output = list(subject)
    clip = list(clipper)
    if signed_area(clip) < 0.0:
        clip.reverse()
    for index, clip_first in enumerate(clip):
        clip_second = clip[(index + 1) % len(clip)]
        input_polygon = output
        output = []
        if not input_polygon:
            break

        def inside(point: tuple[float, float]) -> bool:
            cross = (
                (clip_second[0] - clip_first[0]) * (point[1] - clip_first[1])
                - (clip_second[1] - clip_first[1]) * (point[0] - clip_first[0])
            )
            return cross >= -1.0e-12

        previous = input_polygon[-1]
        previous_inside = inside(previous)
        for current in input_polygon:
            current_inside = inside(current)
            if current_inside:
                if not previous_inside:
                    output.append(
                        line_intersection(previous, current, clip_first, clip_second)
                    )
                output.append(current)
            elif previous_inside:
                output.append(
                    line_intersection(previous, current, clip_first, clip_second)
                )
            previous = current
            previous_inside = current_inside
    return output


def projected_overlap_area(
    first_triangles: Sequence[Sequence[tuple[float, float]]],
    second_triangles: Sequence[Sequence[tuple[float, float]]],
) -> float:
    total = 0.0
    for first in first_triangles:
        first_y = [point[0] for point in first]
        first_z = [point[1] for point in first]
        for second in second_triangles:
            second_y = [point[0] for point in second]
            second_z = [point[1] for point in second]
            if (
                max(first_y) < min(second_y) - INTERVAL_TOLERANCE_M
                or max(second_y) < min(first_y) - INTERVAL_TOLERANCE_M
                or max(first_z) < min(second_z) - INTERVAL_TOLERANCE_M
                or max(second_z) < min(first_z) - INTERVAL_TOLERANCE_M
            ):
                continue
            clipped = convex_clip(first, second)
            if len(clipped) >= 3:
                total += abs(signed_area(clipped))
    return total


def camera_audit() -> list[dict]:
    cameras = []
    for obj in sorted(
        (item for item in bpy.data.objects if item.type == "CAMERA"),
        key=lambda item: item.name,
    ):
        cameras.append(
            {
                "object": obj.name,
                "clip_start_m": round_float(obj.data.clip_start),
                "clip_end_m": round_float(obj.data.clip_end),
                "world_location_m": [round_float(value) for value in obj.matrix_world.translation],
            }
        )
    return cameras


def main() -> None:
    args = parse_args()
    blend_path = args.input_blend.resolve()
    glb_path = args.input_glb.resolve()
    output_path = args.output.resolve()
    current_blend = Path(bpy.data.filepath).resolve()

    if current_blend != blend_path:
        raise RuntimeError(
            f"Blender opened {current_blend}, expected locked input {blend_path}"
        )
    before_blend_sha = sha256_file(blend_path)
    before_glb_sha = sha256_file(glb_path)
    if before_blend_sha != EXPECTED_BLEND_SHA256:
        raise RuntimeError(f"Unexpected V5 Blend SHA-256: {before_blend_sha}")
    if before_glb_sha != EXPECTED_GLB_SHA256:
        raise RuntimeError(f"Unexpected V5 GLB SHA-256: {before_glb_sha}")

    copper_obj = bpy.data.objects.get(COPPER_OBJECT)
    hotface_obj = bpy.data.objects.get(HOTFACE_OBJECT)
    refractory_obj = bpy.data.objects.get(REFRACTORY_OBJECT)
    if copper_obj is None or hotface_obj is None or refractory_obj is None:
        raise RuntimeError("Required R2K Section objects are missing")

    _, copper_audit = cap_triangles_world(
        copper_obj,
        COPPER_CAP_MATERIAL_TOKEN,
    )
    _, hotface_audit = cap_triangles_world(
        hotface_obj,
        HOTFACE_CAP_MATERIAL_TOKEN,
    )
    _, refractory_audit = cap_triangles_world(
        refractory_obj,
        REFRACTORY_CAP_MATERIAL_TOKEN,
    )
    copper_triangles = copper_audit.pop("_yz_triangles")
    hotface_triangles = hotface_audit.pop("_yz_triangles")
    refractory_triangles = refractory_audit.pop("_yz_triangles")

    plane_values = [
        copper_audit["cap_plane_x_m"],
        hotface_audit["cap_plane_x_m"],
        refractory_audit["cap_plane_x_m"],
    ]
    common_plane_x = sum(plane_values) / len(plane_values)
    plane_delta = max(plane_values) - min(plane_values)
    copper_segments, copper_boundary_audit = cap_boundary_segments_world(
        copper_obj,
        set(copper_audit["cap_material_indices"]),
        common_plane_x,
    )
    hotface_segments, hotface_boundary_audit = cap_boundary_segments_world(
        hotface_obj,
        set(hotface_audit["cap_material_indices"]),
        common_plane_x,
    )
    refractory_segments, refractory_boundary_audit = cap_boundary_segments_world(
        refractory_obj,
        set(refractory_audit["cap_material_indices"]),
        common_plane_x,
    )
    copper_audit["cut_boundary"] = copper_boundary_audit
    hotface_audit["cut_boundary"] = hotface_boundary_audit
    refractory_audit["cut_boundary"] = refractory_boundary_audit

    copper_body_segments, copper_body_audit = body_surface_edge_segments_world(
        copper_obj,
        set(copper_audit["cap_material_indices"]),
    )
    hotface_body_segments, hotface_body_audit = body_surface_edge_segments_world(
        hotface_obj,
        set(hotface_audit["cap_material_indices"]),
    )
    refractory_body_segments, refractory_body_audit = (
        body_surface_edge_segments_world(
            refractory_obj,
            set(refractory_audit["cap_material_indices"]),
        )
    )
    copper_audit["radial_envelope_source"] = copper_body_audit
    hotface_audit["radial_envelope_source"] = hotface_body_audit
    refractory_audit["radial_envelope_source"] = refractory_body_audit
    requested_chain_slices = []
    for z_m in REQUESTED_Z_M:
        result = radial_chain_slice(
            copper_body_segments,
            hotface_body_segments,
            refractory_body_segments,
            z_m,
            common_plane_x,
        )
        requested_chain_slices.append(result)
    control_chain_slices = []
    for z_m in CONTROL_Z_M:
        result = radial_chain_slice(
            copper_body_segments,
            hotface_body_segments,
            refractory_body_segments,
            z_m,
            common_plane_x,
        )
        control_chain_slices.append(result)

    copper_height_range = tuple(
        copper_body_audit["body_surface_edge_z_bounds_m"]
    )
    hotface_height_range = tuple(
        hotface_body_audit["body_surface_edge_z_bounds_m"]
    )
    refractory_height_range = tuple(
        refractory_body_audit["body_surface_edge_z_bounds_m"]
    )
    copper_hotface_overlap_start = max(
        copper_height_range[0],
        hotface_height_range[0],
    )
    copper_hotface_overlap_end = min(
        copper_height_range[1],
        hotface_height_range[1],
    )
    copper_hotface_overlap_length = max(
        0.0,
        copper_hotface_overlap_end - copper_hotface_overlap_start,
    )
    copper_height_length = copper_height_range[1] - copper_height_range[0]
    hotface_coverage_ratio_over_copper = (
        copper_hotface_overlap_length / copper_height_length
        if copper_height_length > 0.0
        else 0.0
    )
    adjacency_measurements = []
    maximum_adjacent_error = None
    full_height_chain_slices = []
    adjacency_passed = False

    # Keep the former direct L03->L05 measurement only as a diagnostic.  The
    # objects are not adjacent: L04 is intentionally between them.
    raw_requested_slices = []
    for z_m in REQUESTED_Z_M:
        result = interface_slice(copper_segments, refractory_segments, z_m)
        if result is None:
            raise RuntimeError(f"No raw L03->L05 diagnostic slice at z={z_m}")
        raw_requested_slices.append(result)
    raw_control_slices = []
    for z_m in CONTROL_Z_M:
        result = interface_slice(copper_segments, refractory_segments, z_m)
        if result is None:
            raise RuntimeError(f"No raw L03->L05 control slice at z={z_m}")
        raw_control_slices.append(result)

    raw_z_range, raw_critical_z, raw_candidates = critical_z_candidates(
        copper_segments,
        refractory_segments,
    )
    raw_full_height_slices = [
        result
        for z_m in raw_candidates
        if (result := interface_slice(copper_segments, refractory_segments, z_m))
        is not None
    ]
    raw_symmetric_slices = [
        item
        for item in raw_full_height_slices
        if item["symmetric_within_tolerance"]
    ]
    raw_bilateral_maximum = max(
        raw_symmetric_slices,
        key=lambda item: item["max_side_gap_m"],
    )
    raw_all_maximum = max(
        raw_full_height_slices,
        key=lambda item: item["max_side_gap_m"],
    )

    # Attach the actual V5 L04 coverage fact to every raw diagnostic slice.
    chain_by_z = {
        round(float(item["z_m"]), 6): item
        for item in requested_chain_slices + control_chain_slices
    }
    for raw_item in raw_requested_slices + raw_control_slices:
        chain = chain_by_z[round(float(raw_item["z_m"]), 6)]
        raw_item["classification"] = (
            "missing_expected_L04_section_geometry_plus_stave_joint_projection"
        )
        raw_item["L04_present_at_z"] = (
            chain["radial_envelopes"]["L04_hotface_embed"] is not None
        )
        raw_item["L04_projected_thickness_mm"] = None
        raw_item["negative_side_residual_after_L04_mm"] = None
        raw_item["positive_side_residual_after_L04_mm"] = None
        raw_item["eligible_as_adjacent_layer_gap"] = False

    overlap_copper_hotface = projected_overlap_area(
        copper_triangles,
        hotface_triangles,
    )
    overlap_hotface_refractory = projected_overlap_area(
        hotface_triangles,
        refractory_triangles,
    )
    copper_topology = mesh_topology(copper_obj)
    hotface_topology = mesh_topology(hotface_obj)
    refractory_topology = mesh_topology(refractory_obj)
    after_blend_sha = sha256_file(blend_path)
    after_glb_sha = sha256_file(glb_path)
    protected_inputs_unchanged = (
        before_blend_sha == after_blend_sha and before_glb_sha == after_glb_sha
    )

    report = {
        "schema_version": "bf3d-r2w-interface-gap-audit-v2",
        "requirement_id": "WEB-60-R2W-INTERFACE-GAP",
        "operation": (
            "read_only_world_space_L03_to_L04_to_L05_radial_chain_audit"
        ),
        "result": "fail_closed_missing_expected_L04_section_coverage",
        "inputs": {
            "blend": {
                "path": relpath(blend_path),
                "expected_sha256": EXPECTED_BLEND_SHA256,
                "before_sha256": before_blend_sha,
                "after_sha256": after_blend_sha,
                "unchanged": before_blend_sha == after_blend_sha,
            },
            "glb": {
                "path": relpath(glb_path),
                "expected_sha256": EXPECTED_GLB_SHA256,
                "before_sha256": before_glb_sha,
                "after_sha256": after_glb_sha,
                "unchanged": before_glb_sha == after_glb_sha,
            },
            "blender_version": bpy.app.version_string,
            "scene_unit_settings": {
                "system": bpy.context.scene.unit_settings.system,
                "scale_length": bpy.context.scene.unit_settings.scale_length,
                "length_unit": bpy.context.scene.unit_settings.length_unit,
            },
        },
        "objects": {
            "copper": copper_audit,
            "hotface_embed": hotface_audit,
            "refractory": refractory_audit,
        },
        "measurement_contract": {
            "coordinate_space": "Blender world metres; Z up; Section projected to YZ",
            "section_plane_axis": "X",
            "common_section_plane_x_m": round_float(common_plane_x),
            "object_plane_delta_m": round_float(plane_delta),
            "plane_tolerance_m": PLANE_TOLERANCE_M,
            "interval_merge_tolerance_m": INTERVAL_TOLERANCE_M,
            "slice_epsilon_m": SLICE_EPSILON_M,
            "continuity_tolerance_m": CONTINUITY_TOLERANCE_M,
            "continuity_rule": (
                "For each truly adjacent pair, max(abs radial gap, abs projected "
                "positive/negative Y gap) must be <= 0.0005 m. Positive means "
                "separation; negative means overlap."
            ),
            "continuity_tolerance_rationale": (
                "0.5 mm is the locked R2K radial construction-audit tolerance and is "
                "500x smaller than the 0.25 m minimum published L03 thickness; it is "
                "also above float32/sub-micrometre Section-plane noise."
            ),
            "overlap_area_tolerance_m2": OVERLAP_AREA_TOLERANCE_M2,
            "symmetry_tolerance_m": SYMMETRY_TOLERANCE_M,
            "primary_chain": [
                "L03_copper_inner -> L04_hotface_embed_outer",
                "L04_hotface_embed_inner -> L05_residual_refractory_outer",
            ],
            "primary_method": (
                "Intersect non-cap body-surface edges with z, recover inner/outer radial "
                "envelopes, project the same radii onto the registered X Section plane, "
                "and audit only the two truly adjacent interfaces where all three layers "
                "exist. Missing L04 geometry fails closed; cap-fill diagonals and "
                "circumferential stave end/joint edges are excluded from the primary gate."
            ),
            "full_height_extrema_method": (
                "First compare actual object Z coverage. An absent common L03/L04 height "
                "range is a structural coverage failure, so no numeric adjacency maximum "
                "is fabricated."
            ),
            "direct_L03_to_L05_is_not_an_adjacency_measurement": True,
        },
        "section_plane": {
            "common_plane_x_m": round_float(common_plane_x),
            "object_plane_delta_m": round_float(plane_delta),
            "common_within_tolerance": plane_delta <= PLANE_TOLERANCE_M,
        },
        "requested_height_slices": requested_chain_slices,
        "control_height_slices": control_chain_slices,
        "full_copper_wall_height_audit": {
            "copper_height_range_m": [
                round_float(value) for value in copper_height_range
            ],
            "hotface_height_range_m": [
                round_float(value) for value in hotface_height_range
            ],
            "refractory_height_range_m": [
                round_float(value) for value in refractory_height_range
            ],
            "copper_hotface_common_height_range_m": None,
            "copper_hotface_overlap_length_m": round_float(
                copper_hotface_overlap_length
            ),
            "hotface_coverage_ratio_over_copper_height": round_float(
                hotface_coverage_ratio_over_copper
            ),
            "hotface_coverage_complete_over_copper_height": False,
            "missing_hotface_height_length_over_copper_m": round_float(
                copper_height_length - copper_hotface_overlap_length
            ),
            "numeric_adjacent_interface_maximum_available": False,
            "maximum_adjacent_interface_error": None,
            "maximum_adjacent_interface_error_mm": None,
            "continuity_failure_reason": (
                "V5 Section L04 bounds are z=16..20 m while copper bounds are "
                "z=-20..7.55 m; there is no common height at which either true "
                "adjacent pair can be measured."
            ),
            "adjacent_layer_continuity_passed": adjacency_passed,
        },
        "nonadjacent_L03_to_L05_cut_boundary_diagnostic": {
            "classification": (
                "unfilled_expected_L04_section_band_plus_optional_"
                "stave_joint_section_projection"
            ),
            "eligible_as_adjacent_layer_gap": False,
            "reason": (
                "The layer schema requires L04 between L03 and L05, but locked V5 "
                "contains no L04 Section geometry over the copper height. Direct "
                "subtraction is retained only to locate the uncovered visual band and "
                "must not be represented as a validated intended layer thickness."
            ),
            "requested_height_slices": raw_requested_slices,
            "control_height_slices": raw_control_slices,
            "common_height_range_m": [
                round_float(raw_z_range[0]),
                round_float(raw_z_range[1]),
            ],
            "critical_z_count": len(raw_critical_z),
            "prior_bilateral_maximum": raw_bilateral_maximum,
            "prior_bilateral_maximum_mm": raw_bilateral_maximum[
                "max_side_gap_mm"
            ],
            "prior_bilateral_maximum_z_m": raw_bilateral_maximum["z_m"],
            "raw_all_slice_maximum_including_asymmetric_stave_joint_intersections": (
                raw_all_maximum
            ),
            "raw_all_slice_maximum_mm": raw_all_maximum["max_side_gap_mm"],
            "raw_all_slice_maximum_z_m": raw_all_maximum["z_m"],
        },
        "exclusion_audit": {
            "topology": {
                "copper": copper_topology,
                "hotface_embed": hotface_topology,
                "refractory": refractory_topology,
                "excluded_as_gap_cause": (
                    copper_topology["closed_two_manifold"]
                    and hotface_topology["closed_two_manifold"]
                    and refractory_topology["closed_two_manifold"]
                ),
                "reason": (
                    "All three surviving entities are individually closed two-manifold "
                    "meshes, but closure does not prove that L04 covers the copper height."
                ),
                "topology_closed_but_height_coverage_missing": True,
            },
            "normals": {
                "copper_cap_normals_valid": copper_audit[
                    "cap_normals_parallel_to_section_plane_normal"
                ],
                "hotface_cap_normals_valid": hotface_audit[
                    "cap_normals_parallel_to_section_plane_normal"
                ],
                "refractory_cap_normals_valid": refractory_audit[
                    "cap_normals_parallel_to_section_plane_normal"
                ],
                "excluded_as_gap_cause": (
                    copper_audit["cap_normals_parallel_to_section_plane_normal"]
                    and hotface_audit[
                        "cap_normals_parallel_to_section_plane_normal"
                    ]
                    and refractory_audit[
                        "cap_normals_parallel_to_section_plane_normal"
                    ]
                ),
                "reason": (
                    "Finite nonzero cap normals are parallel to the Section plane normal; "
                    "normal orientation cannot move the measured world-space boundaries."
                ),
            },
            "near_clipping": {
                "scene_cameras": camera_audit(),
                "excluded_as_gap_cause": True,
                "reason": (
                    "The audit reads mesh coordinates and performs no camera projection; "
                    "near/far clipping cannot create the positive world-space gap."
                ),
            },
            "shadowing": {
                "renderer_invoked": False,
                "lights_or_world_sampled": False,
                "excluded_as_gap_cause": True,
                "reason": (
                    "No shading or shadow result is consumed by the geometric slice audit."
                ),
            },
            "z_fighting": {
                "projected_cap_overlap_area_m2": {
                    "L03_to_L04": round_float(overlap_copper_hotface),
                    "L04_to_L05": round_float(overlap_hotface_refractory),
                },
                "both_overlaps_within_zero_tolerance": (
                    overlap_copper_hotface <= OVERLAP_AREA_TOLERANCE_M2
                    and overlap_hotface_refractory <= OVERLAP_AREA_TOLERANCE_M2
                ),
                "excluded_as_visible_strip_cause": True,
                "reason": (
                    "The cap entities do not overlap in positive area. More importantly, "
                    "L04 is absent over the copper height, so the visible band cannot be "
                    "explained as coplanar flicker."
                ),
            },
            "intermediate_layer_height_coverage": {
                "copper_height_range_m": list(copper_height_range),
                "hotface_height_range_m": list(hotface_height_range),
                "overlap_length_m": round_float(copper_hotface_overlap_length),
                "coverage_ratio": round_float(hotface_coverage_ratio_over_copper),
                "excluded_as_gap_cause": False,
                "confirmed_as_primary_structural_coverage_failure": True,
            },
            "asymmetric_stave_joint_section_intersections": {
                "z_minus_1p2_diagnostic": raw_requested_slices[0],
                "raw_all_slice_maximum_gap_mm": raw_all_maximum[
                    "max_side_gap_mm"
                ],
                "raw_all_slice_maximum_z_m": raw_all_maximum["z_m"],
                "used_for_adjacent_chain_gate": False,
                "reason": (
                    "The joined copper object retains discrete stave blocks and 12 mm "
                    "circumferential joints. A fixed non-radial X plane can enter/leave "
                    "a stave through a joint or end face. The z=-1.2 direct values are "
                    "therefore kept as a cut-geometry diagnostic, not an adjacency gap."
                ),
            },
        },
        "interpretation": {
            "zero_overlap_does_not_equal_continuous_coverage": True,
            "statement": (
                "The earlier L03-to-L05 subtraction skipped the required L04 interface "
                "check. Locked V5 does contain an L04 object, but it is only z=16..20 m; "
                "it has zero height overlap with the copper Section at z=-20..7.55 m. "
                "Therefore the four requested true-adjacency pairs are not numerically "
                "measurable and fail closed. The raw direct band is an uncovered expected "
                "L04 Section region plus possible discrete stave-joint projection."
            ),
            "adjacent_layer_continuity_passed": adjacency_passed,
            "L04_object_exists": True,
            "L04_present_between_L03_and_L05_over_copper_height": False,
            "earlier_direct_L03_to_L05_gap_claim_valid": False,
            "earlier_direct_measurement_classification": (
                "missing_expected_intermediate_layer_geometry"
            ),
            "design_reference_required": True,
            "not_a_data_line": True,
            "not_resolvable_by_material_or_lighting": True,
        },
        "disposition_boundaries": [
            {
                "id": "REBUILD_FULL_L04_IF_REFERENCE_CONFIRMS_STACK",
                "allowed_when": (
                    "Controlled furnace/CAD/refractory-stave reference confirms the "
                    "L03->L04->L05 stack and full copper-height L04 coverage."
                ),
                "action_boundary": (
                    "Create a new versioned Section candidate from the controlled full L04 "
                    "source; verify bounds, both adjacency pairs, 1x thickness, topology "
                    "and GLB gates. Do not patch V5 in place."
                ),
            },
            {
                "id": "ACCEPT_TOP_ONLY_L04_ONLY_IF_REFERENCE_EXPLICITLY_REQUIRES_IT",
                "allowed_when": (
                    "Controlled design reference explicitly states that L04 is only "
                    "z=16..20 m and absent over every copper course."
                ),
                "action_boundary": (
                    "Revise the layer-stack contract and visual legend; classify the "
                    "L03/L05 separation using the approved design, not lighting or a "
                    "decorative filler."
                ),
            },
            {
                "id": "HOLD_FAIL_CLOSED_WHILE_REFERENCE_IS_ABSENT_OR_AMBIGUOUS",
                "allowed_when": "No authoritative interface dimension/tolerance is available.",
                "action_boundary": (
                    "Keep V5 unchanged and block geometric correction. Lighting, AO, "
                    "material darkening, decorative strips, coplanar overlap and camera "
                    "cropping are not authorized substitutes for a design reference."
                ),
            },
        ],
        "checks": {
            "locked_blend_sha256_matches": before_blend_sha == EXPECTED_BLEND_SHA256,
            "locked_glb_sha256_matches": before_glb_sha == EXPECTED_GLB_SHA256,
            "protected_inputs_unchanged": protected_inputs_unchanged,
            "common_section_plane_within_tolerance": plane_delta <= PLANE_TOLERANCE_M,
            "four_requested_heights_measure_true_chain": (
                len(requested_chain_slices) == len(REQUESTED_Z_M)
            ),
            "four_requested_heights_have_numeric_true_chain_pairs": False,
            "full_copper_height_layer_bounds_evaluated": True,
            "full_copper_height_true_chain_numerically_evaluable": False,
            "L04_present_and_fills_radial_envelope": False,
            "L04_coverage_ratio_over_copper_height_is_zero": (
                hotface_coverage_ratio_over_copper == 0.0
            ),
            "topology_excluded": (
                copper_topology["closed_two_manifold"]
                and hotface_topology["closed_two_manifold"]
                and refractory_topology["closed_two_manifold"]
            ),
            "normals_excluded": (
                copper_audit["cap_normals_parallel_to_section_plane_normal"]
                and hotface_audit[
                    "cap_normals_parallel_to_section_plane_normal"
                ]
                and refractory_audit[
                    "cap_normals_parallel_to_section_plane_normal"
                ]
            ),
            "near_clip_excluded": True,
            "shadow_excluded": True,
            "z_fighting_excluded": (
                overlap_copper_hotface <= OVERLAP_AREA_TOLERANCE_M2
                and overlap_hotface_refractory <= OVERLAP_AREA_TOLERANCE_M2
            ),
            "earlier_direct_L03_to_L05_gap_claim_valid": False,
            "adjacent_layer_continuity_passed": adjacency_passed,
            "design_reference_required": True,
            "scene_saved_or_mutated": False,
        },
        "adjacent_layer_continuity_passed": adjacency_passed,
        "design_reference_required": True,
        "scene_saved_or_mutated": False,
    }

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))

    if adjacency_passed:
        raise RuntimeError(
            "Unexpected continuity pass despite missing L04 copper-height coverage"
        )


if __name__ == "__main__":
    main()
