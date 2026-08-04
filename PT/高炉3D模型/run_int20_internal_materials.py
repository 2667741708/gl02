from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
STAGE = "INT-20"
REQUIREMENT_ID = "REQ-BF3D-10STAGE-EXECUTION-20260718"
BLENDER = Path(r"D:\Program Files\Blender Foundation\Blender 5.2\blender.exe")
INPUT_BLEND = ROOT / "PT" / "高炉3D模型" / "work" / "INT_10_20260718_R1" / "INT_10_INTERNAL_GRAYBOX_CANDIDATE.blend"
INPUT_SHA256 = "ee8387959d26612d2f03d2ff05651419fbdcb087cb546f4a8293d957233553fe"
INT10_REPORT = ROOT / "PT" / "高炉3D模型" / "work" / "INT_10_20260718_R1" / "int10_internal_graybox_report.json"
INT10_MANIFEST = ROOT / "PT" / "高炉3D模型" / "work" / "INT_10_20260718_R1" / "int10_structure_manifest.json"
WORK = ROOT / "PT" / "高炉3D模型" / "work" / "INT_20_20260718_R1"
OUTPUT_BLEND = WORK / "INT_20_INTERNAL_MATERIAL_CUTAWAY_CANDIDATE.blend"
INNER_SCRIPT = WORK / "_int20_blender_stage.py"
REOPEN_SCRIPT = WORK / "_int20_reopen_validate.py"


def now_iso() -> str:
    return datetime.now(timezone(timedelta(hours=8))).isoformat(timespec="seconds")


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def write_json(path: Path, data: object) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def build_inner_script() -> str:
    config = {
        "root": str(ROOT),
        "stage": STAGE,
        "requirement_id": REQUIREMENT_ID,
        "input_blend": str(INPUT_BLEND),
        "input_sha256": INPUT_SHA256,
        "int10_report": str(INT10_REPORT),
        "int10_manifest": str(INT10_MANIFEST),
        "work": str(WORK),
        "output_blend": str(OUTPUT_BLEND),
    }
    return """
import bpy
import json
import math
import hashlib
from pathlib import Path
from mathutils import Vector

CFG = __INT20_CONFIG__
WORK = Path(CFG["work"])
RENDERS = WORK / "renders"
RENDERS.mkdir(parents=True, exist_ok=True)

def now_label():
    import datetime
    return datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=8))).isoformat(timespec="seconds")

def read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))

def sha256_file(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()

def rounded_matrix(obj):
    return [round(v, 7) for row in obj.matrix_world for v in row]

def mesh_signature(obj):
    if obj.type != "MESH" or not obj.data:
        return None
    mesh = obj.data
    h = hashlib.sha256()
    h.update(str(len(mesh.vertices)).encode())
    h.update(str(len(mesh.edges)).encode())
    h.update(str(len(mesh.polygons)).encode())
    for v in mesh.vertices:
        h.update(("%0.7f,%0.7f,%0.7f;" % (v.co.x, v.co.y, v.co.z)).encode())
    for p in mesh.polygons:
        h.update((",".join(str(i) for i in p.vertices) + ";").encode())
    return h.hexdigest()

def protected_snapshot():
    sensors = sorted([o for o in bpy.data.objects if o.name.startswith("SENSOR_")], key=lambda o: o.name)
    body = [o for o in sensors if o.name.startswith("SENSOR_T_body_")]
    layer_groups = sorted(set(
        [o.name for o in bpy.data.objects if o.name.startswith("GL02_SENSOR_LAYER_L")]
        + [c.name for c in bpy.data.collections if c.name.startswith("GL02_SENSOR_LAYER_L")]
    ))
    segments = sorted([o.name for o in bpy.data.objects if o.name.startswith("APPROX_GL02_FURNACE_")])
    sensor_sig = {o.name: {"parent": o.parent.name if o.parent else None, "matrix": rounded_matrix(o)} for o in sensors}
    return {
        "sensor_count": len(sensors),
        "body_temp_sensor_count": len(body),
        "layer_group_count": len(layer_groups),
        "layer_groups": layer_groups,
        "furnace_segment_count": len(segments),
        "furnace_segments": segments,
        "sensor_signature_sha256": hashlib.sha256(json.dumps(sensor_sig, sort_keys=True).encode()).hexdigest(),
    }

def object_signature(names):
    out = {}
    for name in sorted(names):
        obj = bpy.data.objects.get(name)
        if not obj:
            out[name] = None
        else:
            out[name] = {
                "type": obj.type,
                "parent": obj.parent.name if obj.parent else None,
                "matrix": rounded_matrix(obj),
                "mesh_geometry_sha256": mesh_signature(obj),
            }
    return out

def ensure_collection(name):
    coll = bpy.data.collections.get(name)
    if not coll:
        coll = bpy.data.collections.new(name)
        bpy.context.scene.collection.children.link(coll)
    return coll

def link_to_collection(obj, coll):
    if obj.name not in coll.objects:
        try:
            coll.objects.link(obj)
        except RuntimeError:
            pass

def create_principled_material(name, base_color, metallic, roughness, alpha=1.0, noise=False, bump=False):
    mat = bpy.data.materials.get(name) or bpy.data.materials.new(name)
    mat.use_nodes = True
    mat.diffuse_color = base_color
    mat["bf3d_stage"] = CFG["stage"]
    mat["confidence"] = "E"
    mat["derivation"] = "illustrative_material_lookdev"
    mat["not_as_built"] = True
    if alpha < 1.0:
        try:
            mat.blend_method = "BLEND"
            mat.use_screen_refraction = True
        except Exception:
            pass
        try:
            mat.surface_render_method = "BLENDED"
        except Exception:
            pass
        mat.show_transparent_back = True
    nodes = mat.node_tree.nodes
    bsdf = nodes.get("Principled BSDF") or next((node for node in nodes if node.type == "BSDF_PRINCIPLED"), None)
    if bsdf:
        for key, value in {
            "Base Color": base_color,
            "Metallic": metallic,
            "Roughness": roughness,
            "Alpha": alpha,
        }.items():
            if key in bsdf.inputs:
                bsdf.inputs[key].default_value = value
    if noise and bsdf:
        noise_node = nodes.new(type="ShaderNodeTexNoise")
        noise_node.inputs["Scale"].default_value = 34.0
        noise_node.inputs["Detail"].default_value = 8.0
        noise_node.inputs["Roughness"].default_value = 0.58
        ramp = nodes.new(type="ShaderNodeValToRGB")
        ramp.color_ramp.elements[0].position = 0.22
        ramp.color_ramp.elements[0].color = (base_color[0] * 0.72, base_color[1] * 0.72, base_color[2] * 0.72, alpha)
        ramp.color_ramp.elements[1].position = 1.0
        ramp.color_ramp.elements[1].color = (min(base_color[0] * 1.22, 1.0), min(base_color[1] * 1.18, 1.0), min(base_color[2] * 1.12, 1.0), alpha)
        mat.node_tree.links.new(noise_node.outputs.get("Fac"), ramp.inputs.get("Fac"))
        mat.node_tree.links.new(ramp.outputs.get("Color"), bsdf.inputs.get("Base Color"))
    if bump and bsdf:
        noise_bump = nodes.new(type="ShaderNodeTexNoise")
        noise_bump.inputs["Scale"].default_value = 96.0
        noise_bump.inputs["Detail"].default_value = 6.0
        bump_node = nodes.new(type="ShaderNodeBump")
        bump_node.inputs["Strength"].default_value = 0.045
        bump_node.inputs["Distance"].default_value = 0.055
        mat.node_tree.links.new(noise_bump.outputs.get("Fac"), bump_node.inputs.get("Height"))
        mat.node_tree.links.new(bump_node.outputs.get("Normal"), bsdf.inputs.get("Normal"))
    return mat

materials = {
    "steel_shell": create_principled_material("MI_INT20_STEEL_SHELL_DARK_GRAY_MATTE", (0.118, 0.126, 0.124, 1), 0.55, 0.82, 1.0, True, True),
    "cooling_wall": create_principled_material("MI_INT20_COOLING_WALL_DARK_COPPER_STAVE", (0.42, 0.205, 0.115, 1), 0.25, 0.78, 1.0, True, True),
    "refractory_lining": create_principled_material("MI_INT20_REFRACTORY_WARM_GRAY_BROWN_ROUGH", (0.47, 0.405, 0.32, 1), 0.02, 0.93, 1.0, True, True),
    "process_space": create_principled_material("MI_INT20_PROCESS_SPACE_DARK_TRANSLUCENT", (0.045, 0.055, 0.058, 0.36), 0.0, 0.72, 0.36, False, False),
    "brick_seam": create_principled_material("MI_INT20_BRICK_JOINT_DARK_DUST", (0.17, 0.145, 0.115, 1), 0.0, 0.96, 1.0, False, False),
    "stave_seam": create_principled_material("MI_INT20_COOLING_STAVE_JOINT_DARK_OXIDE", (0.12, 0.067, 0.046, 1), 0.0, 0.9, 1.0, False, False),
    "skull": create_principled_material("MI_INT20_PROTECTIVE_SKULL_SKIN_DARK_MATTE", (0.19, 0.175, 0.15, 0.58), 0.0, 0.88, 0.58, True, False),
}

int10_manifest = read_json(CFG["int10_manifest"])
int10_report = read_json(CFG["int10_report"])
layer_object_names = {}
for layer in int10_manifest["layers"]:
    layer_object_names[layer["layer_id"]] = list(layer["objects"].values())
all_int10_names = [name for names in layer_object_names.values() for name in names]
before_protected = protected_snapshot()
before_int10_sig = object_signature(all_int10_names)

for name in int10_report.get("hidden_explanatory_objects", []):
    obj = bpy.data.objects.get(name)
    if obj:
        obj.hide_viewport = True
        obj.hide_render = True
        obj["bf3d_int20_hidden_old_explanatory"] = True

material_assignment = {}
for layer_id, names in layer_object_names.items():
    mat = materials[layer_id]
    for name in names:
        obj = bpy.data.objects.get(name)
        if not obj:
            continue
        if obj.type == "MESH":
            obj.data.materials.clear()
            obj.data.materials.append(mat)
        obj["bf3d_int20_material_family"] = layer_id
        obj["confidence"] = "E"
        obj["derivation"] = "illustrative_material_assignment_on_INT10_geometry"
        obj["thickness_claim"] = "not_measured_not_as_built"
        material_assignment[name] = mat.name

aux_coll = ensure_collection("INT20_INTERNAL_MATERIAL_DETAILS")
diagnostic_coll = ensure_collection("INT20_MATERIAL_DIAGNOSTIC_SWATCHES")
aux_objects = []

profile = int10_manifest["analytic_profiles"]
def interp_radius(z, key):
    pts = sorted((p["z_blender_m"], p[key]) for p in profile)
    if z <= pts[0][0]:
        return pts[0][1]
    if z >= pts[-1][0]:
        return pts[-1][1]
    for (z0, r0), (z1, r1) in zip(pts, pts[1:]):
        if z0 <= z <= z1:
            t = (z - z0) / (z1 - z0)
            return r0 + (r1 - r0) * t
    return pts[-1][1]

def tag_aux(obj, family, note):
    obj["bf3d_stage"] = CFG["stage"]
    obj["confidence"] = "E"
    obj["derivation"] = "illustrative"
    obj["not_as_built"] = True
    obj["material_family"] = family
    obj["note"] = note
    link_to_collection(obj, aux_coll)
    aux_objects.append(obj.name)

for idx, z in enumerate([-16.0, -11.0, -6.0, -1.0, 4.0, 9.0, 14.0, 18.0]):
    r = interp_radius(z, "refractory_outer_r_m") + 0.012
    bpy.ops.mesh.primitive_torus_add(major_radius=r, minor_radius=0.014, major_segments=144, minor_segments=6, location=(0, 0, z))
    obj = bpy.context.object
    obj.name = f"APPROX_GL02_INT20_REFRACTORY_BRICK_JOINT_RING_{idx:02d}"
    obj.data.name = obj.name + "_MESH"
    obj.data.materials.append(materials["brick_seam"])
    tag_aux(obj, "refractory_lining", "illustrative horizontal brick joint ring; no real brick course dimension claimed")

for idx, deg in enumerate(range(0, 360, 30)):
    angle = math.radians(deg)
    curve = bpy.data.curves.new(f"APPROX_GL02_INT20_COOLING_STAVE_VERTICAL_JOINT_{idx:02d}_CURVE", "CURVE")
    curve.dimensions = "3D"
    curve.resolution_u = 2
    curve.bevel_depth = 0.018
    curve.bevel_resolution = 2
    spl = curve.splines.new("POLY")
    spl.points.add(len(profile) - 1)
    for pnt, prof in zip(spl.points, profile):
        z = prof["z_blender_m"]
        r = prof["cooling_outer_r_m"] + 0.018
        pnt.co = (r * math.cos(angle), r * math.sin(angle), z, 1)
    obj = bpy.data.objects.new(f"APPROX_GL02_INT20_COOLING_STAVE_VERTICAL_JOINT_{idx:02d}", curve)
    bpy.context.scene.collection.objects.link(obj)
    obj.data.materials.append(materials["stave_seam"])
    tag_aux(obj, "cooling_wall", "illustrative cooling wall/stave visual division; no equipment record dimension claimed")

bpy.ops.mesh.primitive_torus_add(major_radius=interp_radius(-4.0, "process_outer_r_m") + 0.02, minor_radius=0.035, major_segments=144, minor_segments=8, location=(0, 0, -4.0))
skull = bpy.context.object
skull.name = "APPROX_GL02_INT20_PROTECTIVE_SKULL_SKIN_REFERENCE"
skull.data.name = skull.name + "_MESH"
skull.scale.z = 0.24
skull.data.materials.append(materials["skull"])
tag_aux(skull, "process_space", "illustrative protective skull/slag skin cue; no real thickness or condition claimed")

swatches = []
for idx, (family, mat) in enumerate([
    ("steel_shell", materials["steel_shell"]),
    ("cooling_wall", materials["cooling_wall"]),
    ("refractory_lining", materials["refractory_lining"]),
    ("process_space", materials["process_space"]),
]):
    bpy.ops.mesh.primitive_cube_add(size=0.9, location=(-1.8 + idx * 1.2, 0, 1.0))
    cube = bpy.context.object
    cube.name = f"APPROX_GL02_INT20_MATERIAL_SWATCH_{family.upper()}"
    cube.data.name = cube.name + "_MESH"
    cube.data.materials.append(mat)
    cube.hide_viewport = True
    cube.hide_render = True
    cube["bf3d_stage"] = CFG["stage"]
    cube["confidence"] = "E"
    cube["derivation"] = "illustrative"
    cube["diagnostic_only"] = True
    link_to_collection(cube, diagnostic_coll)
    swatches.append(cube.name)
    font_curve = bpy.data.curves.new(cube.name + "_LABEL_CURVE", "FONT")
    font_curve.body = family
    font_curve.align_x = "CENTER"
    font_curve.size = 0.18
    text_obj = bpy.data.objects.new(f"APPROX_GL02_INT20_LABEL_{family.upper()}", font_curve)
    text_obj.location = (cube.location.x, -0.56, 0.34)
    text_obj.rotation_euler[0] = math.radians(90)
    bpy.context.scene.collection.objects.link(text_obj)
    text_obj.hide_viewport = True
    text_obj.hide_render = True
    text_obj["bf3d_stage"] = CFG["stage"]
    text_obj["confidence"] = "E"
    text_obj["derivation"] = "illustrative"
    text_obj["diagnostic_only"] = True
    link_to_collection(text_obj, diagnostic_coll)
    swatches.append(text_obj.name)

def look_at(obj, target):
    loc = Vector(obj.location)
    direction = Vector(target) - loc
    obj.rotation_euler = direction.to_track_quat("-Z", "Y").to_euler()

def ensure_camera(name, location, target, lens=70):
    cam = bpy.data.objects.get(name)
    if not cam:
        data = bpy.data.cameras.new(name + "_DATA")
        cam = bpy.data.objects.new(name, data)
        bpy.context.scene.collection.objects.link(cam)
    cam.location = location
    cam.data.lens = lens
    cam.data.sensor_width = 32
    look_at(cam, target)
    return cam

def ensure_area_light(name, location, power, size, target=(0,0,0)):
    obj = bpy.data.objects.get(name)
    if not obj:
        data = bpy.data.lights.new(name + "_DATA", "AREA")
        obj = bpy.data.objects.new(name, data)
        bpy.context.scene.collection.objects.link(obj)
    obj.location = location
    obj.hide_viewport = False
    obj.hide_render = False
    obj.data.energy = power
    obj.data.size = size
    look_at(obj, target)
    return obj

for obj in bpy.data.objects:
    if obj.type == "LIGHT":
        obj.hide_render = True
ensure_area_light("INT20_LOOKDEV_KEY_AREA", (-7, -10, 14), 520, 7.5, (0, 0, 0))
ensure_area_light("INT20_LOOKDEV_FILL_AREA", (9, 7, 8), 160, 11, (0, 0, 0))

scene = bpy.context.scene
scene["bf3d_stage"] = "INT_20_INTERNAL_MATERIAL_CUTAWAY_CANDIDATE"
try:
    scene.render.engine = "BLENDER_EEVEE"
except Exception:
    pass
try:
    scene.eevee.taa_render_samples = 64
except Exception:
    pass
scene.render.resolution_x = 1280
scene.render.resolution_y = 720
scene.render.film_transparent = False
world = scene.world or bpy.data.worlds.new("INT20_WORLD")
scene.world = world
world.color = (0.54, 0.56, 0.56)
try:
    scene.view_settings.view_transform = "AgX"
    scene.view_settings.look = "Medium Low Contrast"
    scene.view_settings.exposure = 0
    scene.view_settings.gamma = 1
except Exception:
    pass

def set_visibility(mode):
    for name in all_int10_names + aux_objects + swatches:
        obj = bpy.data.objects.get(name)
        if obj:
            obj.hide_viewport = True
            obj.hide_render = True
    def show(name):
        obj = bpy.data.objects.get(name)
        if obj:
            obj.hide_viewport = False
            obj.hide_render = False
    if mode in ("front", "side"):
        for name in layer_object_names["steel_shell"]:
            if name.endswith("_FULL"):
                show(name)
    elif mode == "half":
        for names in layer_object_names.values():
            for name in names:
                if name.endswith("_HALF"):
                    show(name)
        for name in aux_objects:
            show(name)
    elif mode in ("quarter", "closeup"):
        for names in layer_object_names.values():
            for name in names:
                if name.endswith("_QUARTER"):
                    show(name)
        for name in aux_objects:
            show(name)
    elif mode == "diagnostic":
        for name in swatches:
            show(name)

render_specs = [
    ("FRONT", "front", "INT20_CAM_FRONT", (0, -31, 2.6), (0, 0, 0), 78),
    ("SIDE", "side", "INT20_CAM_SIDE", (-31, 0, 2.6), (0, 0, 0), 78),
    ("HALF_CUT", "half", "INT20_CAM_HALF_CUT", (0, -28, 1.5), (0, 0, -1.5), 70),
    ("QUARTER_CUT", "quarter", "INT20_CAM_QUARTER_CUT", (18, -24, 2.0), (0, 0, -0.8), 66),
    ("CUTAWAY_CLOSEUP", "half", "INT20_CAM_CUTAWAY_CLOSEUP", (5.5, -16.0, -2.2), (1.0, 0.0, -2.8), 74),
    ("MATERIAL_DIAGNOSTIC_COLORCARD", "diagnostic", "INT20_CAM_MATERIAL_COLORCARD", (0, -8.5, 1.45), (0, 0, 0.85), 48),
]

evidence = []
for render_id, mode, cam_name, loc, target, lens in render_specs:
    set_visibility(mode)
    cam = ensure_camera(cam_name, loc, target, lens)
    scene.camera = cam
    out = RENDERS / f"INT20_{render_id}.png"
    scene.render.filepath = str(out)
    bpy.ops.render.render(write_still=True)
    evidence.append({
        "id": render_id.lower(),
        "file": out.name,
        "path": str(out),
        "camera": cam.name,
        "mode": mode,
        "lookdev": "neutral_area_lights_agx_no_bloom",
        "resolution_px": [scene.render.resolution_x, scene.render.resolution_y],
        "bytes": out.stat().st_size if out.exists() else 0,
        "sha256": sha256_file(out) if out.exists() else None,
    })

for name in all_int10_names + aux_objects + swatches:
    obj = bpy.data.objects.get(name)
    if obj:
        obj.hide_viewport = False
        obj.hide_render = False
for name in int10_report.get("hidden_explanatory_objects", []):
    obj = bpy.data.objects.get(name)
    if obj:
        obj.hide_viewport = True
        obj.hide_render = True

after_protected = protected_snapshot()
after_int10_sig = object_signature(all_int10_names)
int10_geometry_matrix_names_preserved = before_int10_sig == after_int10_sig
protected_contract = {
    "sensor_count_before": before_protected["sensor_count"],
    "sensor_count_after": after_protected["sensor_count"],
    "body_temp_sensor_count_before": before_protected["body_temp_sensor_count"],
    "body_temp_sensor_count_after": after_protected["body_temp_sensor_count"],
    "layer_group_count_before": before_protected["layer_group_count"],
    "layer_group_count_after": after_protected["layer_group_count"],
    "furnace_segment_count_before": before_protected["furnace_segment_count"],
    "furnace_segment_count_after": after_protected["furnace_segment_count"],
    "sensor_signature_before": before_protected["sensor_signature_sha256"],
    "sensor_signature_after": after_protected["sensor_signature_sha256"],
    "names_parents_matrices_unchanged": before_protected["sensor_signature_sha256"] == after_protected["sensor_signature_sha256"],
    "l7_l16_groups_present": all(f"GL02_SENSOR_LAYER_L{i}" in after_protected["layer_groups"] for i in range(7, 17)),
    "five_furnace_segments_present": after_protected["furnace_segment_count"] >= 5,
    "old_55_explanatory_objects_hidden_count": len([name for name in int10_report.get("hidden_explanatory_objects", []) if bpy.data.objects.get(name) and bpy.data.objects[name].hide_render]),
    "old_55_explanatory_objects_expected_count": len(int10_report.get("hidden_explanatory_objects", [])),
}

material_manifest = {
    "schema_version": "bf3d.int20.material_manifest.v1",
    "requirement_id": CFG["requirement_id"],
    "stage": CFG["stage"],
    "status": "candidate_ready_for_review",
    "confidence_contract": {
        "confidence": "E",
        "derivation": "illustrative",
        "engineering_dimensions_claimed": False,
        "materials_claimed_as_built": False,
    },
    "material_families": {
        "steel_shell": {"material": materials["steel_shell"].name, "intent": "dark gray matte industrial steel shell"},
        "cooling_wall": {"material": materials["cooling_wall"].name, "intent": "dark copper/red brown cooling wall/stave cue"},
        "refractory_lining": {"material": materials["refractory_lining"].name, "intent": "warm gray brown rough refractory lining with restrained brick joints"},
        "process_space": {"material": materials["process_space"].name, "intent": "dark translucent process space"},
    },
    "int10_object_material_assignment": material_assignment,
    "int20_illustrative_objects": sorted(aux_objects + swatches),
    "auxiliary_object_contract": {
        "name_prefix": "APPROX_GL02_INT20_*",
        "confidence": "E",
        "derivation": "illustrative",
        "not_as_built": True,
        "real_thickness_claimed": False,
    },
}
Path(WORK / "int20_material_manifest.json").write_text(json.dumps(material_manifest, ensure_ascii=False, indent=2), encoding="utf-8")

bpy.ops.wm.save_as_mainfile(filepath=CFG["output_blend"])

candidate_sha = sha256_file(CFG["output_blend"])
assertions = {
    "input_sha256_matches": sha256_file(CFG["input_blend"]) == CFG["input_sha256"],
    "protected_contract_pass": protected_contract["sensor_count_after"] == 115
        and protected_contract["body_temp_sensor_count_after"] == 80
        and protected_contract["names_parents_matrices_unchanged"]
        and protected_contract["l7_l16_groups_present"]
        and protected_contract["five_furnace_segments_present"]
        and protected_contract["old_55_explanatory_objects_hidden_count"] == protected_contract["old_55_explanatory_objects_expected_count"],
    "int10_12_geometry_matrix_names_preserved": int10_geometry_matrix_names_preserved,
    "material_assignment_pass": len(material_assignment) == 12
        and all(name in material_assignment for name in all_int10_names),
    "e_boundary_pass": all((bpy.data.objects[name].get("confidence") == "E" and bpy.data.objects[name].get("derivation") == "illustrative") for name in aux_objects),
    "renders_exist_pass": all(item["bytes"] > 0 for item in evidence) and len(evidence) >= 6,
}
assertions["machine_assertions_pass_before_reopen"] = all(assertions.values())
report = {
    "schema_version": "bf3d.int20.machine_report.v1",
    "requirement_id": CFG["requirement_id"],
    "stage": CFG["stage"],
    "status": "candidate_ready_for_review",
    "approval": "not_granted_requires_visual_and_spec_review",
    "generated_at": now_label(),
    "single_changed_dimension": "internal_four_layer_materials_and_readable_cutaway_only",
    "input": {
        "path": CFG["input_blend"],
        "sha256": sha256_file(CFG["input_blend"]),
        "expected_sha256": CFG["input_sha256"],
        "sha256_match": sha256_file(CFG["input_blend"]) == CFG["input_sha256"],
        "read_only_source": True,
        "predecessor_gate": "BASE-00 and INT-10 reported approved by task payload",
    },
    "candidate": {
        "path": CFG["output_blend"],
        "bytes": Path(CFG["output_blend"]).stat().st_size,
        "sha256": candidate_sha,
    },
    "blender": {
        "version": bpy.app.version_string,
        "binary_path": bpy.app.binary_path,
        "background": bpy.app.background,
        "render_engine": scene.render.engine,
        "render_device": "background_eevee_cpu_or_default",
    },
    "protected_contract": protected_contract,
    "int10_contract": {
        "expected_int10_object_count": 12,
        "observed_int10_object_count": len([name for name in all_int10_names if bpy.data.objects.get(name)]),
        "geometry_matrix_names_preserved": int10_geometry_matrix_names_preserved,
        "assigned_material_count": len(material_assignment),
    },
    "e_boundary": {
        "confidence": "E",
        "derivation": "illustrative",
        "auxiliary_objects": sorted(aux_objects),
        "engineering_thickness_claimed": False,
        "materials_claimed_as_built": False,
    },
    "formal_asset_changes": {
        "formal_glb_modified": False,
        "p40_modified": False,
        "p50_modified": False,
        "p60_modified": False,
        "frontend_modified": False,
    },
    "evidence_renders": evidence,
    "material_manifest": str(WORK / "int20_material_manifest.json"),
    "assertions": assertions,
    "known_issues": [
        "INT-20 materials are illustrative LookDev materials, not measured as-built metallurgy or lining state.",
        "Added brick joints, cooling stave joints and skull cue are visual readability aids only; no true equipment layout, thickness or wear condition is claimed.",
        "GLB/P40/P50/P60 formal assets were intentionally untouched.",
    ],
}
Path(WORK / "int20_machine_report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
print("INT20_STAGE_COMPLETE", json.dumps({"candidate": CFG["output_blend"], "renders": len(evidence), "assertions_pass": assertions["machine_assertions_pass_before_reopen"]}, ensure_ascii=False))
""".replace("__INT20_CONFIG__", json.dumps(config, ensure_ascii=False))


def build_reopen_script() -> str:
    config = {
        "work": str(WORK),
        "output_blend": str(OUTPUT_BLEND),
    }
    return """
import bpy
import json
import hashlib
from pathlib import Path

CFG = __INT20_REOPEN_CONFIG__
WORK = Path(CFG["work"])

def matrix_sig(obj):
    return [round(v, 7) for row in obj.matrix_world for v in row]

sensors = sorted([o for o in bpy.data.objects if o.name.startswith("SENSOR_")], key=lambda o: o.name)
sensor_payload = {o.name: {"parent": o.parent.name if o.parent else None, "matrix": matrix_sig(o)} for o in sensors}
int10_objects = [o for o in bpy.data.objects if o.name.startswith("APPROX_GL02_INT10_")]
int20_aux = [o for o in bpy.data.objects if o.name.startswith("APPROX_GL02_INT20_")]
render_dir = WORK / "renders"
expected = [
    "INT20_FRONT.png",
    "INT20_SIDE.png",
    "INT20_HALF_CUT.png",
    "INT20_QUARTER_CUT.png",
    "INT20_CUTAWAY_CLOSEUP.png",
    "INT20_MATERIAL_DIAGNOSTIC_COLORCARD.png",
]
validation = {
    "schema_version": "bf3d.int20.reopen_validation.v1",
    "stage": "INT-20",
    "candidate_reopened_without_error": True,
    "scene_stage": bpy.context.scene.get("bf3d_stage"),
    "sensor_count": len(sensors),
    "sensor_signature_sha256": hashlib.sha256(json.dumps(sensor_payload, sort_keys=True).encode()).hexdigest(),
    "body_temp_sensor_count": len([o for o in sensors if o.name.startswith("SENSOR_T_body_")]),
    "int10_object_count": len(int10_objects),
    "int20_aux_or_diagnostic_object_count": len(int20_aux),
    "all_int20_aux_have_e_boundary": all(o.get("confidence") == "E" and o.get("derivation") == "illustrative" for o in int20_aux),
    "renders_present": {name: (render_dir / name).exists() and (render_dir / name).stat().st_size > 0 for name in expected},
}
validation["status"] = "pass" if (
    validation["sensor_count"] == 115
    and validation["body_temp_sensor_count"] == 80
    and validation["int10_object_count"] == 12
    and validation["all_int20_aux_have_e_boundary"]
    and all(validation["renders_present"].values())
) else "fail"
(WORK / "reopen_validation.json").write_text(json.dumps(validation, ensure_ascii=False, indent=2), encoding="utf-8")
print("INT20_REOPEN", json.dumps(validation, ensure_ascii=False))
""".replace("__INT20_REOPEN_CONFIG__", json.dumps(config, ensure_ascii=False))


def run_command(command: list[str], stdout_path: Path, stderr_path: Path) -> int:
    with stdout_path.open("w", encoding="utf-8") as out, stderr_path.open("w", encoding="utf-8") as err:
        proc = subprocess.run(command, cwd=str(ROOT), stdout=out, stderr=err, text=True)
    return proc.returncode


def collect_artifacts() -> dict[str, dict[str, object]]:
    artifacts: dict[str, dict[str, object]] = {}
    for path in sorted(WORK.rglob("*")):
        if path.is_file():
            rel = path.relative_to(WORK).as_posix()
            artifacts[rel] = {
                "path": str(path),
                "bytes": path.stat().st_size,
                "sha256": sha256_file(path),
            }
    return artifacts


def main() -> int:
    WORK.mkdir(parents=True, exist_ok=True)
    (WORK / "renders").mkdir(parents=True, exist_ok=True)
    if not BLENDER.exists():
        raise FileNotFoundError(BLENDER)
    if not INPUT_BLEND.exists():
        raise FileNotFoundError(INPUT_BLEND)
    actual_input_sha = sha256_file(INPUT_BLEND)
    if actual_input_sha.lower() != INPUT_SHA256:
        raise RuntimeError(f"Input SHA-256 mismatch: {actual_input_sha}")

    INNER_SCRIPT.write_text(build_inner_script(), encoding="utf-8")
    REOPEN_SCRIPT.write_text(build_reopen_script(), encoding="utf-8")

    main_command = [
        str(BLENDER),
        "--background",
        str(INPUT_BLEND),
        "--python",
        str(INNER_SCRIPT),
    ]
    reopen_command = [
        str(BLENDER),
        "--background",
        str(OUTPUT_BLEND),
        "--python",
        str(REOPEN_SCRIPT),
    ]
    command_record = {
        "schema_version": 1,
        "stage": STAGE,
        "created_at": now_iso(),
        "cwd": str(ROOT),
        "commands": {
            "main": main_command,
            "reopen_validation": reopen_command,
        },
        "input_sha256": actual_input_sha,
    }
    write_json(WORK / "command.json", command_record)

    main_rc = run_command(main_command, WORK / "blender_stdout.log", WORK / "blender_stderr.log")
    if main_rc != 0:
        command_record["returncodes"] = {"main": main_rc, "reopen_validation": None}
        write_json(WORK / "command.json", command_record)
        return main_rc

    reopen_rc = run_command(reopen_command, WORK / "reopen_stdout.log", WORK / "reopen_stderr.log")
    command_record["returncodes"] = {"main": main_rc, "reopen_validation": reopen_rc}
    write_json(WORK / "command.json", command_record)

    report_path = WORK / "int20_machine_report.json"
    if report_path.exists():
        report = json.loads(report_path.read_text(encoding="utf-8"))
        reopen_validation = {}
        reopen_path = WORK / "reopen_validation.json"
        if reopen_path.exists():
            reopen_validation = json.loads(reopen_path.read_text(encoding="utf-8"))
        report["execution"] = {
            "finished_at": now_iso(),
            "returncode": main_rc,
            "reopen_returncode": reopen_rc,
            "command_record": str(WORK / "command.json"),
            "stdout_log": str(WORK / "blender_stdout.log"),
            "stderr_log": str(WORK / "blender_stderr.log"),
            "reopen_stdout_log": str(WORK / "reopen_stdout.log"),
            "reopen_stderr_log": str(WORK / "reopen_stderr.log"),
        }
        report.setdefault("assertions", {})["reopen_validation_pass"] = reopen_validation.get("status") == "pass"
        report["reopen_validation"] = reopen_validation
        report["assertions"]["machine_assertions_pass"] = all(bool(v) for v in report["assertions"].values())
        write_json(report_path, report)

    artifacts = collect_artifacts()
    write_json(WORK / "artifact_sha256.json", {
        "schema_version": 1,
        "stage": STAGE,
        "generated_at": now_iso(),
        "artifacts": artifacts,
    })
    return reopen_rc


if __name__ == "__main__":
    sys.exit(main())
