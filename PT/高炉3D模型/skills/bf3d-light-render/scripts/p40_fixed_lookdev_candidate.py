"""Create fixed GL02 LookDev cameras, two light rigs and repeatable render evidence."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import struct
import sys
import time
from pathlib import Path

import bpy
from mathutils import Vector

AUDIT_DIR = Path(__file__).resolve().parents[2] / "bf3d-geometry-audit" / "scripts"
UV_DIR = Path(__file__).resolve().parents[2] / "bf3d-uv-bake" / "scripts"
MATERIAL_DIR = Path(__file__).resolve().parents[2] / "bf3d-industrial-materials" / "scripts"
sys.path[:0] = [str(AUDIT_DIR), str(UV_DIR), str(MATERIAL_DIR)]
import p00_import_audit as p00  # noqa: E402
import p21_shaft_bake_test as p21  # noqa: E402
import p30_shell_material_candidate as p30  # noqa: E402

CAMERA_NAMES = (
    "CAM_GLOBAL_FRONT",
    "CAM_GLOBAL_BACK",
    "CAM_GLOBAL_LEFT",
    "CAM_GLOBAL_RIGHT",
    "CAM_DETAIL_SHELL",
    "CAM_DETAIL_TUYERE",
    "CAM_DETAIL_TAPHOLE",
)

ALLOWED_INPUT_STAGES = {
    "P30_SHELL_MATERIAL_CANDIDATE",
    "P30_MATERIAL_APPROVED",
    "P32_EQUIPMENT_MATERIAL_CANDIDATE",
    "P32_EQUIPMENT_MATERIAL_APPROVED",
    "P35_DETAIL_GEOMETRY_CANDIDATE",
    "P35_DETAIL_GEOMETRY_APPROVED",
    "P36_LAYER_SEGMENTATION_CANDIDATE",
    "P36_LAYER_SEGMENTATION_APPROVED",
}

GLOBAL_FIT_EXCLUDE_TOKENS = (
    "access_tower_and_bridges",
    "gas_uptakes_and_downcomer",
)

GLOBAL_LOOKDEV_HIDE_TOKENS = (
    "burden_column_layered_charge_coke",
    "burden_column_layered_charge_ore",
    "cohesive_zone_softening_melting_band",
    "cold_blast_supply_flow",
    "countercurrent_gas_flow_streamlines",
    "hearth_molten_iron_pool",
    "hearth_slag_layer",
    "hot_blast_raceway_plumes",
    "internal_burden_reference",
    "hot_metal_dripping_droplet_",
    "shell_ash_deposit_streaks",
    "shell_local_heat_patina",
    "temp_layer_band",
)

SHOT_VISIBILITY_RULES = {
    "CAM_GLOBAL_FRONT": {"mode": "blacklist", "tokens": GLOBAL_LOOKDEV_HIDE_TOKENS + GLOBAL_FIT_EXCLUDE_TOKENS},
    "CAM_GLOBAL_BACK": {"mode": "blacklist", "tokens": GLOBAL_LOOKDEV_HIDE_TOKENS + GLOBAL_FIT_EXCLUDE_TOKENS},
    "CAM_GLOBAL_LEFT": {"mode": "blacklist", "tokens": GLOBAL_LOOKDEV_HIDE_TOKENS + GLOBAL_FIT_EXCLUDE_TOKENS},
    "CAM_GLOBAL_RIGHT": {
        "mode": "blacklist",
        "tokens": GLOBAL_LOOKDEV_HIDE_TOKENS + GLOBAL_FIT_EXCLUDE_TOKENS,
    },
    "CAM_DETAIL_SHELL": {
        "mode": "whitelist",
        "names": (
            "APPROX_GL02_FURNACE_SHAFT",
            "APPROX_GL02_cooling_bands_and_seams",
            "APPROX_GL02_shell_stiffener_rings",
            "APPROX_GL02_P35_shell_welds",
        ),
    },
    "CAM_DETAIL_TUYERE": {
        "mode": "whitelist",
        "names": (
            "APPROX_GL02_FURNACE_HEARTH",
            "APPROX_GL02_bustle_pipe_and_tuyere_stocks",
            "APPROX_GL02_P35_shell_welds",
            "APPROX_GL02_P35_tuyere_flange_bodies",
            "APPROX_GL02_P35_tuyere_bolts",
        ),
    },
    "CAM_DETAIL_TAPHOLE": {
        "mode": "whitelist",
        "names": (
            "APPROX_GL02_FURNACE_HEARTH",
            "APPROX_GL02_TAPHole_2_prominent_outlet",
            "APPROX_GL02_two_physical_tapholes",
            "SENSOR_T_taphole_2",
        ),
    },
}


def parse_args() -> argparse.Namespace:
    argv = sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else []
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-glb", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--width", type=int, default=960)
    parser.add_argument("--height", type=int, default=540)
    parser.add_argument("--cycles-samples", type=int, default=64)
    parser.add_argument("--camera-names", default=",".join(CAMERA_NAMES))
    parser.add_argument("--skip-cycles", action="store_true")
    return parser.parse_args(argv)


def collection(name: str) -> bpy.types.Collection:
    existing = bpy.data.collections.get(name)
    if existing:
        for obj in list(existing.objects):
            bpy.data.objects.remove(obj, do_unlink=True)
        bpy.data.collections.remove(existing)
    result = bpy.data.collections.new(name)
    bpy.context.scene.collection.children.link(result)
    return result


def object_points(objects: list[bpy.types.Object]) -> list[Vector]:
    return [obj.matrix_world @ Vector(corner) for obj in objects for corner in obj.bound_box]


def bounds_from_objects(objects: list[bpy.types.Object]) -> tuple[Vector, Vector]:
    points = object_points(objects)
    return (
        Vector(tuple(min(float(point[axis]) for point in points) for axis in range(3))),
        Vector(tuple(max(float(point[axis]) for point in points) for axis in range(3))),
    )


def look_at(obj: bpy.types.Object, target: Vector) -> None:
    obj.rotation_euler = (target - obj.location).to_track_quat("-Z", "Y").to_euler()


def add_sun(target_collection: bpy.types.Collection, name: str, location: Vector, target: Vector, energy: float, color) -> bpy.types.Object:
    data = bpy.data.lights.new(name, type="SUN")
    data.energy = energy
    data.angle = math.radians(8.0)
    data.color = color
    obj = bpy.data.objects.new(name, data)
    target_collection.objects.link(obj)
    obj.location = location
    look_at(obj, target)
    return obj


def add_area(target_collection: bpy.types.Collection, name: str, location: Vector, target: Vector, energy: float, size: float, color) -> bpy.types.Object:
    data = bpy.data.lights.new(name, type="AREA")
    data.energy = energy
    data.shape = "DISK"
    data.size = size
    data.color = color
    obj = bpy.data.objects.new(name, data)
    target_collection.objects.link(obj)
    obj.location = location
    look_at(obj, target)
    return obj


def create_rigs(center: Vector, span: float) -> tuple[bpy.types.Collection, bpy.types.Collection]:
    neutral = collection("P40_LOOKDEV_NEUTRAL")
    presentation = collection("P40_PRESENTATION_INDUSTRIAL")
    add_sun(neutral, "P40_NEUTRAL_KEY", center + Vector((span, -span, span)), center, 2.25, (1.0, 1.0, 1.0))
    add_sun(neutral, "P40_NEUTRAL_FILL", center + Vector((-span, -span * 0.25, span * 0.35)), center, 1.05, (0.96, 0.98, 1.0))
    add_sun(neutral, "P40_NEUTRAL_RIM", center + Vector((span * 0.25, span, span)), center, 1.35, (0.90, 0.95, 1.0))
    add_area(neutral, "P40_NEUTRAL_TOP", center + Vector((0.0, 0.0, span * 1.25)), center, span * 85.0, span * 0.75, (1.0, 1.0, 1.0))

    add_sun(presentation, "P40_PRESENT_KEY_WARM", center + Vector((span, -span, span)), center, 2.90, (1.0, 0.80, 0.64))
    add_sun(presentation, "P40_PRESENT_FILL", center + Vector((-span, -span * 0.25, span * 0.35)), center, 1.22, (0.90, 0.95, 1.0))
    add_sun(presentation, "P40_PRESENT_RIM_COOL", center + Vector((span * 0.25, span, span)), center, 2.05, (0.48, 0.70, 1.0))
    add_area(presentation, "P40_PRESENT_TOP_SOFT", center + Vector((0.0, 0.0, span * 1.20)), center, span * 92.0, span * 0.60, (1.0, 0.95, 0.88))
    add_area(presentation, "P40_PRESENT_FRONT_FILL", center + Vector((0.0, -span, span * 0.08)), center, span * 68.0, span * 0.62, (0.88, 0.94, 1.0))
    return neutral, presentation


def new_camera(target_collection: bpy.types.Collection, name: str) -> bpy.types.Object:
    data = bpy.data.cameras.new(name)
    data.type = "ORTHO"
    data.clip_start = 0.05
    data.clip_end = 1000.0
    obj = bpy.data.objects.new(name, data)
    target_collection.objects.link(obj)
    return obj


def fit_camera(camera: bpy.types.Object, target_objects: list[bpy.types.Object], target: Vector, direction: Vector, aspect: float, margin: float) -> None:
    minimum, maximum = bounds_from_objects(target_objects)
    span = max(float(value) for value in maximum - minimum)
    camera.location = target + direction.normalized() * max(span * 2.4, 30.0)
    look_at(camera, target)
    # Newly-created object transforms are not guaranteed to be reflected in
    # matrix_world until the dependency graph is evaluated.  Without this
    # update the bounds were projected through the camera's previous matrix,
    # producing an apparently valid but severely cropped ortho_scale.
    bpy.context.view_layer.update()
    inverse = camera.matrix_world.inverted()
    projected = [inverse @ point for point in object_points(target_objects)]
    width = max(float(point.x) for point in projected) - min(float(point.x) for point in projected)
    height = max(float(point.y) for point in projected) - min(float(point.y) for point in projected)
    # Blender's ortho_scale is the horizontal camera-frame span.  The visible
    # vertical span is ortho_scale / aspect, so a 16:9 render must multiply
    # the projected height by the aspect ratio instead of treating
    # ortho_scale as a vertical measure.
    camera.data.ortho_scale = max(width, height * aspect) * margin


def matching_meshes(*tokens: str) -> list[bpy.types.Object]:
    lowered = tuple(token.lower() for token in tokens)
    return [obj for obj in bpy.data.objects if obj.type == "MESH" and any(token in obj.name.lower() for token in lowered)]


def create_cameras(full_objects: list[bpy.types.Object], center: Vector, span: float, aspect: float) -> tuple[dict[str, bpy.types.Object], dict[str, object]]:
    cameras_collection = collection("P40_FIXED_CAMERAS")
    cameras = {name: new_camera(cameras_collection, name) for name in CAMERA_NAMES}
    directions = {
        "CAM_GLOBAL_FRONT": Vector((0.382683, -0.923880, 0.0)),
        "CAM_GLOBAL_BACK": Vector((-0.382683, 0.923880, 0.0)),
        "CAM_GLOBAL_LEFT": Vector((-0.923880, -0.382683, 0.0)),
        "CAM_GLOBAL_RIGHT": Vector((0.923880, 0.382683, 0.0)),
    }
    full_minimum, full_maximum = bounds_from_objects(full_objects)
    full_vertical_span = float(full_maximum.z - full_minimum.z)
    for name, direction in directions.items():
        fit_camera(cameras[name], full_objects, center, direction, aspect, 1.15)
        cameras[name].data.ortho_scale = max(
            float(cameras[name].data.ortho_scale),
            full_vertical_span * aspect * 1.15,
            84.0,
        )

    for name in directions:
        if cameras[name].data.ortho_scale < full_vertical_span * aspect * 1.12:
            raise RuntimeError(
                f"{name} cropped: ortho_scale={cameras[name].data.ortho_scale:.6f}, "
                f"required>={full_vertical_span * aspect * 1.12:.6f}"
            )

    shell_target = Vector((0.0, -3.4, 8.2))
    shell_objects = matching_meshes("furnace_shaft", "shell_ash", "shell_local_heat")
    cameras["CAM_DETAIL_SHELL"].location = Vector((0.0, -35.0, 8.5))
    look_at(cameras["CAM_DETAIL_SHELL"], shell_target)
    cameras["CAM_DETAIL_SHELL"].data.ortho_scale = 6.2

    tuyere_objects = matching_meshes("bustle_pipe_and_tuyere", "hot_blast_raceway")
    if not tuyere_objects:
        raise RuntimeError("Unable to locate tuyere/bustle objects")
    # Exact connected-component anchor for the front (negative-Y) tuyere cap.
    tuyere_target = Vector((0.0, -3.449, -11.68))
    cameras["CAM_DETAIL_TUYERE"].location = Vector((5.4, -32.2, 1.8))
    look_at(cameras["CAM_DETAIL_TUYERE"], tuyere_target)
    cameras["CAM_DETAIL_TUYERE"].data.ortho_scale = 2.0

    taphole_objects = matching_meshes("taphole_2_prominent", "sensor_t_taphole_2")
    if not taphole_objects:
        raise RuntimeError("Unable to locate taphole objects")
    tap_target = Vector((0.0, -3.60045, -17.24))
    cameras["CAM_DETAIL_TAPHOLE"].location = Vector((0.0, -33.60045, -17.24))
    look_at(cameras["CAM_DETAIL_TAPHOLE"], tap_target)
    cameras["CAM_DETAIL_TAPHOLE"].data.ortho_scale = 2.4

    metadata = {}
    for name, camera in cameras.items():
        metadata[name] = {
            "location": [round(float(value), 6) for value in camera.location],
            "rotation_euler": [round(float(value), 6) for value in camera.rotation_euler],
            "type": camera.data.type,
            "ortho_scale": round(float(camera.data.ortho_scale), 6),
            "clip_start": float(camera.data.clip_start),
            "clip_end": float(camera.data.clip_end),
        }
    return cameras, metadata


def set_rig(neutral: bpy.types.Collection, presentation: bpy.types.Collection, mode: str) -> None:
    for obj in neutral.objects:
        obj.hide_render = mode != "neutral"
        obj.hide_viewport = mode != "neutral"
    for obj in presentation.objects:
        obj.hide_render = mode != "presentation"
        obj.hide_viewport = mode != "presentation"


def set_color_management(mode: str) -> None:
    scene = bpy.context.scene
    scene.view_settings.view_transform = "AgX"
    scene.view_settings.look = "AgX - Medium Low Contrast" if mode == "neutral" else "AgX - Medium High Contrast"
    scene.view_settings.exposure = 0.0 if mode == "neutral" else 0.38
    scene.world.use_nodes = True
    background = scene.world.node_tree.nodes.get("Background")
    if mode == "neutral":
        background.inputs["Color"].default_value = (0.12, 0.12, 0.12, 1.0)
        background.inputs["Strength"].default_value = 0.72
    else:
        background.inputs["Color"].default_value = (0.010, 0.015, 0.021, 1.0)
        background.inputs["Strength"].default_value = 0.52


def configure_eevee(width: int, height: int) -> None:
    scene = bpy.context.scene
    scene.render.engine = "BLENDER_EEVEE"
    scene.render.resolution_x = width
    scene.render.resolution_y = height
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = "PNG"
    scene.render.film_transparent = False


def configure_optix(samples: int) -> dict[str, object]:
    scene = bpy.context.scene
    scene.render.engine = "CYCLES"
    scene.cycles.samples = samples
    scene.cycles.use_denoising = True
    result: dict[str, object] = {"requested": "OPTIX", "used": "CPU", "samples": samples, "devices": []}
    try:
        preferences = bpy.context.preferences.addons["cycles"].preferences
        preferences.compute_device_type = "OPTIX"
        preferences.get_devices()
        for device in preferences.devices:
            device.use = device.type == "OPTIX"
            result["devices"].append({"name": device.name, "type": device.type, "use": bool(device.use)})
        if any(item["type"] == "OPTIX" and item["use"] for item in result["devices"]):
            scene.cycles.device = "GPU"
            result["used"] = "OPTIX"
        else:
            scene.cycles.device = "CPU"
            result["fallback_reason"] = "No OptiX device enabled"
    except Exception as exc:  # pragma: no cover - device dependent
        scene.cycles.device = "CPU"
        result["fallback_reason"] = str(exc)
    return result


def render_one(path: Path, camera: bpy.types.Object) -> dict[str, object]:
    scene = bpy.context.scene
    scene.camera = camera
    scene.render.filepath = str(path)
    rule = SHOT_VISIBILITY_RULES.get(camera.name, {"mode": "blacklist", "tokens": ()})
    hide_tokens = tuple(token.lower() for token in rule.get("tokens", ()))
    whitelist = {name.lower() for name in rule.get("names", ())}
    mesh_visibility = {obj.name: bool(obj.hide_render) for obj in bpy.data.objects if obj.type == "MESH"}
    hidden_for_shot = []
    visible_for_shot = []
    for obj in bpy.data.objects:
        if obj.type != "MESH":
            continue
        should_hide = (
            obj.name.lower() not in whitelist
            if rule["mode"] == "whitelist"
            else any(token in obj.name.lower() for token in hide_tokens)
        )
        if should_hide:
            obj.hide_render = True
            hidden_for_shot.append(obj.name)
        elif not obj.hide_render:
            visible_for_shot.append(obj.name)
    bpy.context.view_layer.update()
    started = time.perf_counter()
    try:
        bpy.ops.render.render(write_still=True)
    finally:
        for name, hidden in mesh_visibility.items():
            obj = bpy.data.objects.get(name)
            if obj is not None:
                obj.hide_render = hidden
    return {
        "path": str(path),
        "bytes": path.stat().st_size,
        "sha256": p00.sha256_file(path),
        "seconds": round(time.perf_counter() - started, 4),
        "hidden_for_shot": sorted(hidden_for_shot),
        "visible_mesh_names": sorted(visible_for_shot),
        "visibility_mode": rule["mode"],
    }


def original_matrix_hash(original_names: list[str]) -> str:
    digest = hashlib.sha256()
    for name in sorted(original_names):
        obj = bpy.data.objects.get(name)
        if obj is None:
            digest.update(f"MISSING:{name}".encode("utf-8"))
            continue
        digest.update(name.encode("utf-8"))
        digest.update(struct.pack("<16d", *(float(value) for row in obj.matrix_world for value in row)))
    return digest.hexdigest()


def main() -> int:
    args = parse_args()
    selected_camera_names = tuple(name.strip() for name in args.camera_names.split(",") if name.strip())
    invalid_camera_names = sorted(set(selected_camera_names) - set(CAMERA_NAMES))
    if not selected_camera_names or invalid_camera_names:
        raise RuntimeError(f"Invalid camera selection: {invalid_camera_names or selected_camera_names}")
    output_dir = args.output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    source_glb = args.source_glb.resolve()
    input_blend = Path(bpy.data.filepath).resolve()
    scene = bpy.context.scene
    if scene.get("bf3d_stage") not in ALLOWED_INPUT_STAGES:
        raise RuntimeError(f"Expected an approved/candidate material-detail checkpoint, got {scene.get('bf3d_stage')!r}")
    source = p00.source_node_contract(p00.read_glb_json(source_glb))
    imported_before = p00.imported_contract(source)
    sensors_before = imported_before["sensor_records"]
    original_names = [obj.name for obj in bpy.data.objects]
    matrices_before = original_matrix_hash(original_names)
    geometry_before = p30.scene_mesh_sha256(False)
    uv_before = p30.scene_mesh_sha256(True)
    materials_before = {material.name: p30.material_hash(material) for material in bpy.data.materials}
    full_objects = [obj for obj in bpy.data.objects if obj.type == "MESH" and not obj.name.startswith(p00.INTERNAL_RENDER_PREFIXES[1:])]
    global_objects = [
        obj
        for obj in full_objects
        if not any(token in obj.name.lower() for token in GLOBAL_FIT_EXCLUDE_TOKENS)
    ]
    minimum, maximum = bounds_from_objects(global_objects)
    center = (minimum + maximum) * 0.5
    span = max(float(value) for value in maximum - minimum)
    neutral, presentation = create_rigs(center, span)
    cameras, camera_metadata = create_cameras(global_objects, center, span, args.width / args.height)

    matrices_after = original_matrix_hash(original_names)
    geometry_after = p30.scene_mesh_sha256(False)
    uv_after = p30.scene_mesh_sha256(True)
    materials_after = {material.name: p30.material_hash(material) for material in bpy.data.materials}
    imported_after = p00.imported_contract(source)
    assertions = [
        {"id": "input_stage_is_supported", "ok": scene.get("bf3d_stage") in ALLOWED_INPUT_STAGES},
        {"id": "source_glb_matches_lock", "ok": p00.sha256_file(source_glb) == p00.EXPECTED_SOURCE_SHA256},
        {"id": "original_object_matrices_unchanged", "ok": matrices_before == matrices_after, "detail": {"before": matrices_before, "after": matrices_after}},
        {"id": "geometry_unchanged", "ok": geometry_before == geometry_after},
        {"id": "uv_unchanged", "ok": uv_before == uv_after},
        {"id": "materials_unchanged", "ok": materials_before == materials_after},
        {"id": "sensors_unchanged", "ok": sensors_before == imported_after["sensor_records"] and imported_after["sensor_count"] == 115 and imported_after["body_sensor_count"] == 80},
        {"id": "all_seven_fixed_cameras_created", "ok": all(name in bpy.data.objects for name in CAMERA_NAMES), "detail": camera_metadata},
        {"id": "two_separate_light_rigs_created", "ok": len(neutral.objects) >= 4 and len(presentation.objects) >= 4, "detail": {"neutral": [obj.name for obj in neutral.objects], "presentation": [obj.name for obj in presentation.objects]}},
        {"id": "all_cameras_have_positive_scale", "ok": all(camera.data.ortho_scale > 0.1 for camera in cameras.values())},
        {"id": "global_context_objects_excluded_from_camera_fit_only", "ok": len(global_objects) < len(full_objects), "detail": {"excluded": sorted(obj.name for obj in full_objects if obj not in global_objects)}},
        {"id": "detail_shots_use_strict_whitelists", "ok": all(SHOT_VISIBILITY_RULES[name]["mode"] == "whitelist" for name in ("CAM_DETAIL_SHELL", "CAM_DETAIL_TUYERE", "CAM_DETAIL_TAPHOLE"))},
    ]
    ok = all(bool(item["ok"]) for item in assertions)
    candidate = None
    if ok:
        scene["bf3d_stage"] = "P40_FIXED_LOOKDEV_CANDIDATE"
        scene["bf3d_parent_checkpoint"] = str(input_blend)
        scene["bf3d_change_dimension"] = "fixed_cameras_and_light_rigs_only"
        scene["bf3d_render_color_management"] = "AgX"
        scene["bf3d_threejs_target"] = "sRGB output + ACES tone mapping; no compositor effects"
        set_rig(neutral, presentation, "presentation")
        set_color_management("presentation")
        configure_eevee(args.width, args.height)
        scene.camera = cameras["CAM_GLOBAL_FRONT"]
        candidate_path = output_dir / "P40_FIXED_LOOKDEV_CANDIDATE.blend"
        bpy.ops.wm.save_as_mainfile(filepath=str(candidate_path), check_existing=False)
        candidate = {"path": str(candidate_path), "bytes": candidate_path.stat().st_size, "sha256": p00.sha256_file(candidate_path)}

    renders: dict[str, object] = {"eevee": {"neutral": [], "presentation": []}, "cycles": []}
    if ok:
        configure_eevee(args.width, args.height)
        for mode, rig in (("neutral", neutral), ("presentation", presentation)):
            set_rig(neutral, presentation, mode)
            set_color_management(mode)
            render_dir = output_dir / "renders" / "eevee" / mode
            render_dir.mkdir(parents=True, exist_ok=True)
            for name in selected_camera_names:
                item = render_one(render_dir / f"P40_{mode.upper()}_{name}.png", cameras[name])
                item["camera"] = name
                item["lighting"] = mode
                item["engine"] = "BLENDER_EEVEE"
                renders["eevee"][mode].append(item)

        set_rig(neutral, presentation, "presentation")
        set_color_management("presentation")
        if args.skip_cycles:
            cycles_device = {"requested": "OPTIX", "used": "skipped_for_preview"}
        else:
            cycles_device = configure_optix(args.cycles_samples)
            scene.render.resolution_x = max(640, args.width * 2 // 3)
            scene.render.resolution_y = max(360, args.height * 2 // 3)
            cycles_dir = output_dir / "renders" / "cycles" / "presentation"
            cycles_dir.mkdir(parents=True, exist_ok=True)
            for name in (
                "CAM_GLOBAL_FRONT",
                "CAM_DETAIL_SHELL",
                "CAM_DETAIL_TUYERE",
                "CAM_DETAIL_TAPHOLE",
            ):
                if name not in selected_camera_names:
                    continue
                item = render_one(cycles_dir / f"P40_CYCLES_PRESENTATION_{name}.png", cameras[name])
                item["camera"] = name
                item["lighting"] = "presentation"
                item["engine"] = "CYCLES"
                renders["cycles"].append(item)
    else:
        cycles_device = {"requested": "OPTIX", "used": "not_run"}

    expected_cycles = 0 if args.skip_cycles else len(
        set(selected_camera_names)
        & {"CAM_GLOBAL_FRONT", "CAM_DETAIL_SHELL", "CAM_DETAIL_TUYERE", "CAM_DETAIL_TAPHOLE"}
    )
    expected_renders = len(selected_camera_names) * 2 + expected_cycles
    actual_renders = len(renders["eevee"]["neutral"]) + len(renders["eevee"]["presentation"]) + len(renders["cycles"])
    render_assertions = [
        {"id": "full_render_matrix_created", "ok": actual_renders == expected_renders, "detail": {"expected": expected_renders, "actual": actual_renders}},
        {"id": "all_render_files_nonempty", "ok": all(item["bytes"] > 1024 for mode in renders["eevee"].values() for item in mode) and all(item["bytes"] > 1024 for item in renders["cycles"])},
        {"id": "cycles_used_optix", "ok": args.skip_cycles or cycles_device.get("used") == "OPTIX", "detail": cycles_device},
    ]
    status = "candidate_ready_for_visual_review" if ok and all(bool(item["ok"]) for item in render_assertions) else "fail"
    report = {
        "schema_version": 1,
        "stage": "P40_FIXED_LOOKDEV_CANDIDATE",
        "status": status,
        "input_checkpoint": {"path": str(input_blend), "sha256": p00.sha256_file(input_blend)},
        "candidate": candidate,
        "single_changed_dimension": "Fixed cameras, neutral light rig and industrial presentation light rig only.",
        "resolution": {"eevee": [args.width, args.height], "cycles": [max(640, args.width * 2 // 3), max(360, args.height * 2 // 3)]},
        "selected_camera_names": list(selected_camera_names),
        "preview_only": bool(args.skip_cycles or set(selected_camera_names) != set(CAMERA_NAMES)),
        "color_management": {"view_transform": "AgX", "neutral_look": "Medium Low Contrast", "presentation_look": "Medium High Contrast"},
        "cycles_device": cycles_device,
        "cameras": camera_metadata,
        "assertions": assertions + render_assertions,
        "renders": renders,
        "approval": "pending_four_global_three_detail_visual_review",
    }
    report_path = output_dir / "p40_fixed_lookdev_candidate.json"
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": status, "report": str(report_path), "candidate": candidate, "cycles_device": cycles_device, "render_count": actual_renders}, ensure_ascii=False, indent=2))
    return 0 if status == "candidate_ready_for_visual_review" else 2


if __name__ == "__main__":
    raise SystemExit(main())
