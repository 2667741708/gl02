"""Create a non-production Blender showroom copy for interactive review."""

from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path

import bpy
from mathutils import Vector


def parse_args() -> argparse.Namespace:
    argv = sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else []
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", required=True, type=Path)
    return parser.parse_args(argv)


def bounds() -> tuple[Vector, Vector]:
    minimum = Vector((math.inf, math.inf, math.inf))
    maximum = Vector((-math.inf, -math.inf, -math.inf))
    for obj in bpy.data.objects:
        if obj.type != "MESH" or obj.name.startswith("BF3D_SHOWROOM_"):
            continue
        for corner in obj.bound_box:
            point = obj.matrix_world @ Vector(corner)
            for axis in range(3):
                minimum[axis] = min(minimum[axis], point[axis])
                maximum[axis] = max(maximum[axis], point[axis])
    return minimum, maximum


def look_at(obj: bpy.types.Object, target: Vector) -> None:
    obj.rotation_euler = (target - obj.location).to_track_quat("-Z", "Y").to_euler()


def add_area(collection: bpy.types.Collection, name: str, location: Vector, target: Vector, energy: float, size: float, color) -> bpy.types.Object:
    data = bpy.data.lights.new(name, type="AREA")
    data.energy = energy
    data.shape = "DISK"
    data.size = size
    data.color = color
    obj = bpy.data.objects.new(name, data)
    collection.objects.link(obj)
    obj.location = location
    look_at(obj, target)
    return obj


def add_sun(collection: bpy.types.Collection, name: str, location: Vector, target: Vector, energy: float, color) -> bpy.types.Object:
    data = bpy.data.lights.new(name, type="SUN")
    data.energy = energy
    data.angle = math.radians(8.0)
    data.color = color
    obj = bpy.data.objects.new(name, data)
    collection.objects.link(obj)
    obj.location = location
    look_at(obj, target)
    return obj


def material(name: str, base_color, metallic: float, roughness: float) -> bpy.types.Material:
    item = bpy.data.materials.get(name) or bpy.data.materials.new(name)
    item.use_nodes = True
    nodes = item.node_tree.nodes
    links = item.node_tree.links
    nodes.clear()
    output = nodes.new("ShaderNodeOutputMaterial")
    output.name = f"{name}_OUTPUT"
    principled = nodes.new("ShaderNodeBsdfPrincipled")
    principled.name = f"{name}_PRINCIPLED"
    links.new(principled.outputs["BSDF"], output.inputs["Surface"])
    principled.inputs["Base Color"].default_value = base_color
    principled.inputs["Metallic"].default_value = metallic
    principled.inputs["Roughness"].default_value = roughness
    return item


def main() -> int:
    args = parse_args()
    output = args.output.resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    old = bpy.data.collections.get("BF3D_REALTIME_SHOWROOM")
    if old:
        for obj in list(old.objects):
            bpy.data.objects.remove(obj, do_unlink=True)
        bpy.data.collections.remove(old)
    collection = bpy.data.collections.new("BF3D_REALTIME_SHOWROOM")
    collection.color_tag = "COLOR_05"
    bpy.context.scene.collection.children.link(collection)
    minimum, maximum = bounds()
    center = (minimum + maximum) * 0.5
    size = maximum - minimum
    span = max(float(size.x), float(size.y), float(size.z), 1.0)

    target = bpy.data.objects.new("BF3D_SHOWROOM_TARGET", None)
    target.empty_display_type = "SPHERE"
    target.empty_display_size = span * 0.012
    target.location = center
    collection.objects.link(target)

    rig = bpy.data.objects.new("BF3D_SHOWROOM_CAMERA_RIG", None)
    rig.empty_display_type = "CIRCLE"
    rig.empty_display_size = span * 0.12
    rig.location = center
    collection.objects.link(rig)
    camera_data = bpy.data.cameras.new("BF3D_SHOWROOM_CAMERA")
    camera_data.lens = 52.0
    camera_data.sensor_width = 36.0
    camera_data.clip_start = 0.1
    camera_data.clip_end = span * 10.0
    camera = bpy.data.objects.new("BF3D_SHOWROOM_CAMERA", camera_data)
    collection.objects.link(camera)
    camera.parent = rig
    camera.location = Vector((span * 2.20, -span * 2.20, span * 0.52))
    constraint = camera.constraints.new("TRACK_TO")
    constraint.target = target
    constraint.track_axis = "TRACK_NEGATIVE_Z"
    constraint.up_axis = "UP_Y"
    rig.rotation_euler = (0.0, 0.0, 0.0)
    orbit_driver = rig.driver_add("rotation_euler", 2).driver
    orbit_driver.type = "SCRIPTED"
    orbit_driver.expression = f"{math.tau:.16f} * (frame - 1) / 360.0"

    floor_size = span * 0.95
    bpy.ops.mesh.primitive_cylinder_add(vertices=96, radius=floor_size, depth=span * 0.018, location=(center.x, center.y, minimum.z - span * 0.012))
    floor = bpy.context.object
    floor.name = "BF3D_SHOWROOM_PLATFORM"
    for parent in list(floor.users_collection):
        parent.objects.unlink(floor)
    collection.objects.link(floor)
    floor.data.materials.append(material("BF3D_SHOWROOM_PLATFORM_MAT", (0.027, 0.032, 0.035, 1.0), 0.42, 0.68))

    add_area(collection, "BF3D_SHOWROOM_KEY_WARM", center + Vector((span * 0.75, -span, span * 0.78)), center, span * 175.0, span * 0.52, (1.0, 0.82, 0.68))
    add_area(collection, "BF3D_SHOWROOM_FILL_NEUTRAL", center + Vector((-span * 0.88, -span * 0.32, span * 0.42)), center, span * 105.0, span * 0.72, (0.86, 0.93, 1.0))
    add_area(collection, "BF3D_SHOWROOM_RIM_COOL", center + Vector((span * 0.30, span, span * 0.68)), center, span * 145.0, span * 0.48, (0.56, 0.75, 1.0))
    add_area(collection, "BF3D_SHOWROOM_TOP_SOFT", center + Vector((0.0, 0.0, span * 1.18)), center, span * 90.0, span * 0.62, (0.96, 0.98, 1.0))
    add_sun(collection, "BF3D_SHOWROOM_SUN_KEY", center + Vector((span, -span, span)), center, 2.4, (1.0, 0.91, 0.82))
    add_sun(collection, "BF3D_SHOWROOM_SUN_FILL", center + Vector((-span, -span * 0.25, span * 0.35)), center, 1.0, (0.80, 0.90, 1.0))
    add_sun(collection, "BF3D_SHOWROOM_SUN_RIM", center + Vector((span * 0.25, span, span)), center, 1.6, (0.58, 0.76, 1.0))

    scene = bpy.context.scene
    scene.camera = camera
    scene.render.engine = "BLENDER_EEVEE"
    scene.render.resolution_x = 1280
    scene.render.resolution_y = 720
    scene.render.resolution_percentage = 100
    scene.render.film_transparent = False
    scene.render.image_settings.file_format = "PNG"
    scene.view_settings.view_transform = "AgX"
    scene.view_settings.look = "AgX - Medium High Contrast"
    scene.view_settings.exposure = 0.55
    scene.world.use_nodes = True
    background = scene.world.node_tree.nodes.get("Background")
    background.inputs["Color"].default_value = (0.018, 0.023, 0.028, 1.0)
    background.inputs["Strength"].default_value = 0.42
    scene.frame_start = 1
    scene.frame_end = 360
    scene.render.fps = 30
    scene.frame_set(1)
    scene.timeline_markers.new("按空格播放 360° 环绕", frame=1)
    scene["bf3d_showroom"] = True
    scene["bf3d_showroom_instructions"] = "空格：播放/暂停；小键盘0：相机视图；中键：旋转；滚轮：缩放；Z：切换着色。"
    scene["bf3d_showroom_source_stage"] = scene.get("bf3d_stage", "unknown")

    for screen in bpy.data.screens:
        for area in screen.areas:
            if area.type == "VIEW_3D":
                space = area.spaces.active
                space.shading.type = "RENDERED"
                space.shading.use_scene_lights = True
                space.shading.use_scene_world = True
                space.region_3d.view_perspective = "CAMERA"
    bpy.ops.wm.save_as_mainfile(filepath=str(output), check_existing=False)
    print(json.dumps({"status": "showroom_ready", "output": str(output), "center": list(center), "span": span}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
