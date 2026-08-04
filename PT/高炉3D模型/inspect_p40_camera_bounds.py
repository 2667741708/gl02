"""Inspect evaluated render-visible mesh bounds in a saved P40 Blender file."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import bpy
from mathutils import Vector


SCRIPT_DIR = (
    Path(__file__).resolve().parent
    / "skills"
    / "bf3d-light-render"
    / "scripts"
)
sys.path.insert(0, str(SCRIPT_DIR))
import p40_fixed_lookdev_candidate as p40  # noqa: E402


def main() -> None:
    argv = sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else []
    camera_name = argv[0] if argv else "CAM_GLOBAL_FRONT"
    camera = bpy.data.objects[camera_name]
    rule = p40.SHOT_VISIBILITY_RULES[camera_name]
    hide_tokens = tuple(token.lower() for token in rule.get("tokens", ()))
    whitelist = {name.lower() for name in rule.get("names", ())}
    depsgraph = bpy.context.evaluated_depsgraph_get()
    bpy.context.view_layer.update()
    inverse = camera.matrix_world.inverted()
    aspect = bpy.context.scene.render.resolution_x / bpy.context.scene.render.resolution_y
    horizontal_limit = float(camera.data.ortho_scale) * 0.5
    vertical_limit = horizontal_limit / aspect
    rows = []
    all_x: list[float] = []
    all_y: list[float] = []
    for obj in bpy.data.objects:
        if obj.type != "MESH" or obj.hide_render:
            continue
        should_hide = (
            obj.name.lower() not in whitelist
            if rule["mode"] == "whitelist"
            else any(token in obj.name.lower() for token in hide_tokens)
        )
        if should_hide:
            continue
        evaluated = obj.evaluated_get(depsgraph)
        mesh = evaluated.to_mesh()
        try:
            projected = [
                inverse @ (evaluated.matrix_world @ vertex.co)
                for vertex in mesh.vertices
            ]
        finally:
            evaluated.to_mesh_clear()
        if not projected:
            continue
        xs = [float(point.x) for point in projected]
        ys = [float(point.y) for point in projected]
        all_x.extend(xs)
        all_y.extend(ys)
        rows.append(
            {
                "name": obj.name,
                "min_x": min(xs),
                "max_x": max(xs),
                "min_y": min(ys),
                "max_y": max(ys),
                "outside": (
                    min(xs) < -horizontal_limit
                    or max(xs) > horizontal_limit
                    or min(ys) < -vertical_limit
                    or max(ys) > vertical_limit
                ),
            }
        )
    rows.sort(key=lambda row: max(abs(row["min_y"]), abs(row["max_y"])), reverse=True)
    payload = {
        "camera": camera_name,
        "ortho_scale": float(camera.data.ortho_scale),
        "aspect": aspect,
        "limits": {
            "x": [-horizontal_limit, horizontal_limit],
            "y": [-vertical_limit, vertical_limit],
        },
        "actual": {
            "min_x": min(all_x),
            "max_x": max(all_x),
            "min_y": min(all_y),
            "max_y": max(all_y),
            "required_ortho_scale": max(
                max(all_x) - min(all_x),
                (max(all_y) - min(all_y)) * aspect,
            ),
            "center_offset_y": (max(all_y) + min(all_y)) * 0.5,
        },
        "outside": [row for row in rows if row["outside"]],
        "vertical_extremes": rows[:12],
    }
    print("P40_CAMERA_BOUNDS_JSON")
    print(json.dumps(payload, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
