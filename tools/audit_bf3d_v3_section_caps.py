"""Audit coplanar overlap between the physical section caps in the V3 review asset.

This script is intentionally read-only.  Run it with Blender so the saved V3
``.blend`` remains the authoritative geometry source:

    blender --background gl02_blast_furnace_review.v3.blend \
      --python tools/audit_bf3d_v3_section_caps.py -- \
      --output <report.json>

Requirement:
    REQ-BF3D-R2U-SECTION-CAP-CONTROLLED-V4-20260720

Traceability:
    PT/高炉3D模型/十阶段多智能体执行台账.md
    PT/高炉3D模型/工业级高炉数字孪生视觉规范（Visual Bible）.md
    PT/高炉3D模型/总设计详细规划.md
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import sys
from collections import defaultdict
from pathlib import Path
from typing import Iterable

import bpy
from mathutils import Vector


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_BLEND = (
    ROOT
    / "高炉前端数据"
    / "models"
    / "gl02_blast_furnace_review.v3.blend"
)
DEFAULT_GLB = (
    ROOT
    / "高炉前端数据"
    / "models"
    / "gl02_blast_furnace_review.v3.glb"
)
DEFAULT_FORMAL_GLB = (
    ROOT / "高炉前端数据" / "models" / "gl02_blast_furnace.glb"
)
DEFAULT_OUTPUT = (
    ROOT
    / "PT"
    / "高炉3D模型"
    / "work"
    / "WEB_60_20260720_R2U_SECTION_CAP_CONTROLLED_V4"
    / "reports"
    / "v3_section_cap_overlap_audit.json"
)

REQUIREMENT_ID = "REQ-BF3D-R2U-SECTION-CAP-CONTROLLED-V4-20260720"
PLANE_TOLERANCE_M = 2.0e-5
AREA_TOLERANCE_M2 = 1.0e-6


def sha256(path: Path) -> str:
    """Return a deterministic SHA-256 digest for one input artifact."""

    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def polygon_signed_area(points: list[tuple[float, float]]) -> float:
    """Return signed area for a polygon projected to the section Y/Z plane."""

    return 0.5 * sum(
        x0 * y1 - x1 * y0
        for (x0, y0), (x1, y1) in zip(points, points[1:] + points[:1])
    )


def polygon_area(points: list[tuple[float, float]]) -> float:
    """Return absolute projected polygon area."""

    return abs(polygon_signed_area(points))


def cross_2d(
    origin: tuple[float, float],
    edge_end: tuple[float, float],
    point: tuple[float, float],
) -> float:
    """Return the signed 2D cross product relative to one directed edge."""

    return (edge_end[0] - origin[0]) * (point[1] - origin[1]) - (
        edge_end[1] - origin[1]
    ) * (point[0] - origin[0])


def ensure_ccw(points: list[tuple[float, float]]) -> list[tuple[float, float]]:
    """Normalize polygon winding for half-plane clipping."""

    if polygon_signed_area(points) < 0.0:
        return list(reversed(points))
    return points


def clip_convex_polygon(
    subject: list[tuple[float, float]],
    clip: list[tuple[float, float]],
) -> list[tuple[float, float]]:
    """Clip one convex polygon by another using Sutherland-Hodgman."""

    output = ensure_ccw(subject)
    clip_ccw = ensure_ccw(clip)
    epsilon = 1.0e-12
    for clip_a, clip_b in zip(clip_ccw, clip_ccw[1:] + clip_ccw[:1]):
        if not output:
            break
        input_points = output
        output = []
        previous = input_points[-1]
        previous_distance = cross_2d(clip_a, clip_b, previous)
        previous_inside = previous_distance >= -epsilon
        for current in input_points:
            current_distance = cross_2d(clip_a, clip_b, current)
            current_inside = current_distance >= -epsilon
            if current_inside != previous_inside:
                denominator = previous_distance - current_distance
                if abs(denominator) > epsilon:
                    fraction = previous_distance / denominator
                    output.append(
                        (
                            previous[0]
                            + fraction * (current[0] - previous[0]),
                            previous[1]
                            + fraction * (current[1] - previous[1]),
                        )
                    )
            if current_inside:
                output.append(current)
            previous = current
            previous_distance = current_distance
            previous_inside = current_inside
    return output


def bbox(
    points: Iterable[tuple[float, float]],
) -> tuple[float, float, float, float]:
    """Return min-y, min-z, max-y and max-z for projected points."""

    values = list(points)
    return (
        min(point[0] for point in values),
        min(point[1] for point in values),
        max(point[0] for point in values),
        max(point[1] for point in values),
    )


def bboxes_overlap(
    first: tuple[float, float, float, float],
    second: tuple[float, float, float, float],
) -> bool:
    """Return whether two projected boxes overlap with positive area."""

    return (
        min(first[2], second[2]) - max(first[0], second[0]) > 1.0e-10
        and min(first[3], second[3]) - max(first[1], second[1]) > 1.0e-10
    )


def section_objects() -> list[bpy.types.Object]:
    """Return the ten physical V3 section objects in stable name order."""

    return sorted(
        (
            obj
            for obj in bpy.data.objects
            if obj.type == "MESH"
            and str(obj.get("bf3d_review_mode", "")).lower() == "section"
            and bool(obj.get("bf3d_section_physical_cut", False))
        ),
        key=lambda item: item.name,
    )


def cap_material_indices(obj: bpy.types.Object) -> set[int]:
    """Return material-slot indices explicitly tagged as section-cap families."""

    indices: set[int] = set()
    for index, slot in enumerate(obj.material_slots):
        material = slot.material
        if material is not None and material.get("bf3d_section_cap_family"):
            indices.add(index)
    return indices


def projected_cap_triangles(
    obj: bpy.types.Object,
) -> tuple[list[dict], dict]:
    """Extract cap loop triangles and per-object geometry statistics."""

    mesh = obj.data
    mesh.calc_loop_triangles()
    cap_indices = cap_material_indices(obj)
    if not cap_indices:
        raise RuntimeError(f"No tagged section-cap material on {obj.name}")

    triangles = []
    plane_values: list[float] = []
    projected_points: list[tuple[float, float]] = []
    material_names: set[str] = set()
    for triangle in mesh.loop_triangles:
        polygon = mesh.polygons[triangle.polygon_index]
        if polygon.material_index not in cap_indices:
            continue
        points_world = [
            obj.matrix_world @ mesh.vertices[index].co
            for index in triangle.vertices
        ]
        projected = [(float(point.y), float(point.z)) for point in points_world]
        area_m2 = polygon_area(projected)
        if area_m2 <= 1.0e-12:
            continue
        plane_values.extend(float(point.x) for point in points_world)
        projected_points.extend(projected)
        material = obj.material_slots[polygon.material_index].material
        if material is not None:
            material_names.add(material.name)
        triangles.append(
            {
                "points_yz": projected,
                "bbox_yz": bbox(projected),
                "area_m2": area_m2,
            }
        )

    if not triangles:
        raise RuntimeError(f"No physical cap triangles found on {obj.name}")

    expected_plane = float(obj.get("bf3d_section_plane_value", 0.0))
    max_plane_deviation = max(abs(value - expected_plane) for value in plane_values)
    return triangles, {
        "object": obj.name,
        "role": str(obj.get("bf3d_structural_role", "")),
        "cap_family": str(obj.get("bf3d_section_cap_family", "")),
        "cap_materials": sorted(material_names),
        "triangle_count": len(triangles),
        "projected_area_m2": sum(item["area_m2"] for item in triangles),
        "largest_triangles_yz": [
            {
                "area_m2": item["area_m2"],
                "points_yz": item["points_yz"],
            }
            for item in sorted(
                triangles, key=lambda value: value["area_m2"], reverse=True
            )[:8]
        ],
        "bounds_yz": bbox(projected_points),
        "section_plane_x": expected_plane,
        "max_plane_deviation_m": max_plane_deviation,
        "plane_within_tolerance": max_plane_deviation <= PLANE_TOLERANCE_M,
    }


def pair_overlap_area(first: list[dict], second: list[dict]) -> tuple[float, int]:
    """Return accumulated positive-area overlap for two triangle sets."""

    total = 0.0
    intersections = 0
    for first_triangle in first:
        for second_triangle in second:
            if not bboxes_overlap(
                first_triangle["bbox_yz"], second_triangle["bbox_yz"]
            ):
                continue
            clipped = clip_convex_polygon(
                first_triangle["points_yz"], second_triangle["points_yz"]
            )
            if len(clipped) < 3:
                continue
            area_m2 = polygon_area(clipped)
            if area_m2 > 1.0e-10:
                total += area_m2
                intersections += 1
    return total, intersections


def build_report() -> dict:
    """Build the read-only overlap audit report for the loaded V3 Blend."""

    objects = section_objects()
    triangle_sets: dict[str, list[dict]] = {}
    records = []
    for obj in objects:
        triangles, record = projected_cap_triangles(obj)
        triangle_sets[obj.name] = triangles
        records.append(record)

    overlaps = []
    role_area = defaultdict(float)
    for index, first in enumerate(records):
        for second in records[index + 1 :]:
            area_m2, triangle_pairs = pair_overlap_area(
                triangle_sets[first["object"]], triangle_sets[second["object"]]
            )
            if area_m2 <= AREA_TOLERANCE_M2:
                continue
            role_pair = " + ".join(sorted((first["role"], second["role"])))
            role_area[role_pair] += area_m2
            overlaps.append(
                {
                    "object_a": first["object"],
                    "role_a": first["role"],
                    "object_b": second["object"],
                    "role_b": second["role"],
                    "overlap_area_m2": area_m2,
                    "intersecting_triangle_pairs": triangle_pairs,
                }
            )

    overlaps.sort(key=lambda item: item["overlap_area_m2"], reverse=True)
    total_overlap = sum(item["overlap_area_m2"] for item in overlaps)
    unique_planes = sorted(
        {
            round(float(record["section_plane_x"]), 9)
            for record in records
        }
    )
    checks = {
        "exactly_10_physical_section_objects": len(objects) == 10,
        "all_cap_triangles_on_registered_plane": all(
            record["plane_within_tolerance"] for record in records
        ),
        "single_common_section_plane": len(unique_planes) == 1,
        "no_cross_object_positive_area_overlap": not overlaps,
    }
    return {
        "schema_version": "bf3d.r2u.section_cap_overlap_audit.v1",
        "requirement_id": REQUIREMENT_ID,
        "mode": "read_only_saved_blend_audit",
        "inputs": {
            "blend": {
                "path": str(DEFAULT_BLEND.relative_to(ROOT)).replace("\\", "/"),
                "bytes": DEFAULT_BLEND.stat().st_size,
                "sha256": sha256(DEFAULT_BLEND),
            },
            "review_glb": {
                "path": str(DEFAULT_GLB.relative_to(ROOT)).replace("\\", "/"),
                "bytes": DEFAULT_GLB.stat().st_size,
                "sha256": sha256(DEFAULT_GLB),
            },
            "formal_glb": {
                "path": str(DEFAULT_FORMAL_GLB.relative_to(ROOT)).replace(
                    "\\", "/"
                ),
                "bytes": DEFAULT_FORMAL_GLB.stat().st_size,
                "sha256": sha256(DEFAULT_FORMAL_GLB),
            },
            "blender_version": bpy.app.version_string,
        },
        "tolerances": {
            "plane_m": PLANE_TOLERANCE_M,
            "positive_overlap_area_m2": AREA_TOLERANCE_M2,
        },
        "section_plane_values_x": unique_planes,
        "objects": records,
        "overlap_pairs": overlaps,
        "overlap_area_by_role_pair_m2": dict(sorted(role_area.items())),
        "total_cross_object_overlap_area_m2": total_overlap,
        "checks": checks,
        "passed": all(checks.values()),
        "diagnosis": (
            "no_cross_object_cap_overlap_detected"
            if not overlaps
            else "cross_object_coplanar_cap_overlap_confirmed"
        ),
        "scene_saved_or_mutated": False,
    }


def parse_args(argv: list[str]) -> argparse.Namespace:
    """Parse arguments after Blender's ``--`` separator."""

    parser = argparse.ArgumentParser(
        description="Audit positive-area overlap among V3 physical section caps."
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT,
        help="JSON report destination.",
    )
    return parser.parse_args(argv)


def main() -> int:
    """Run the audit and write a deterministic JSON evidence report."""

    script_args = sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else []
    args = parse_args(script_args)
    report = build_report()
    output = args.output.resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["checks"]["exactly_10_physical_section_objects"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
