"""Print world-space bounds for candidate detail-camera subjects and blockers."""

from __future__ import annotations

import json

import bpy
from mathutils import Vector


TOKENS = (
    "taphole",
    "tuyere",
    "bustle",
    "raceway",
    "platform",
    "support",
    "column",
    "shell",
    "tower",
    "pipe",
    "duct",
    "chute",
)


def bounds(obj: bpy.types.Object) -> dict[str, list[float]]:
    points = [obj.matrix_world @ Vector(corner) for corner in obj.bound_box]
    minimum = [min(float(point[axis]) for point in points) for axis in range(3)]
    maximum = [max(float(point[axis]) for point in points) for axis in range(3)]
    return {
        "min": [round(value, 6) for value in minimum],
        "max": [round(value, 6) for value in maximum],
        "center": [round((minimum[index] + maximum[index]) * 0.5, 6) for index in range(3)],
        "size": [round(maximum[index] - minimum[index], 6) for index in range(3)],
    }


records = []
for obj in bpy.data.objects:
    if obj.type != "MESH":
        continue
    object_bounds = bounds(obj)
    is_large_or_offset = (
        object_bounds["size"][2] > 25.0
        or object_bounds["max"][0] > 5.5
        or object_bounds["min"][0] < -5.5
        or object_bounds["max"][1] > 5.5
        or object_bounds["min"][1] < -5.5
    )
    if not any(token in obj.name.lower() for token in TOKENS) and not is_large_or_offset:
        continue
    records.append(
        {
            "name": obj.name,
            "bounds": object_bounds,
            "materials": [slot.material.name if slot.material else None for slot in obj.material_slots],
            "hide_render": bool(obj.hide_render),
        }
    )

print("BF3D_FEATURE_OBJECTS=" + json.dumps(records, ensure_ascii=False, indent=2))
