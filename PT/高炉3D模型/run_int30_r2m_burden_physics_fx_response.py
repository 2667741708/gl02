#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""INT-30 R2M: R2L 炉料物理/FX/软熔带响应视觉候选。

只写入本阶段隔离目录；不导出、不替换、不触碰正式 GLB。
"""

from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
STAGE = ROOT / "PT" / "高炉3D模型" / "work" / "INT_30_20260719_R2M_BURDEN_PHYSICS_FX_RESPONSE"
SCRIPTS = STAGE / "scripts"
BLENDS = STAGE / "blends"
RENDERS = STAGE / "renders"
REPORTS = STAGE / "reports"
LOGS = STAGE / "logs"

INPUT_BLEND = ROOT / "PT" / "高炉3D模型" / "work" / "INT_30_20260719_R2L_BURDEN_ANIMATION_PROTOTYPE" / "blends" / "INT_30_R2L_BURDEN_ANIMATION_PROTOTYPE_CANDIDATE.blend"
INPUT_SHA256 = "c8a9bf6fe2d5093d7ba137695b7d696816abd0442da8ad170b1df2f9edc57095"
FORMAL_GLB = ROOT / "高炉前端数据" / "models" / "gl02_blast_furnace.glb"
FORMAL_GLB_SHA256 = "808960f1b2703e7fb27df35f1b1b1a17063b9b10d2267acba593fc3872b62af6"
R1_NODE_GRAPH_HASH = "6bf8bd2fcf7712081d1ad2620c3133a984ada8c9b3927b59aa86131ba3b134a6"
BLENDER = Path(r"D:\Program Files\Blender Foundation\Blender 5.2\blender.exe")

BUILD_SCRIPT = SCRIPTS / "r2m_build_burden_physics_fx_response.py"
REOPEN_SCRIPT = SCRIPTS / "r2m_reopen_validate.py"
CANDIDATE_BLEND = BLENDS / "INT_30_R2M_BURDEN_PHYSICS_FX_RESPONSE_CANDIDATE.blend"


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def ensure_dirs() -> None:
    for p in (STAGE, SCRIPTS, BLENDS, RENDERS, REPORTS, LOGS, RENDERS / "preview_seq"):
        p.mkdir(parents=True, exist_ok=True)


def run(cmd: list[str], log_name: str, timeout: int) -> None:
    log_path = LOGS / log_name
    with log_path.open("w", encoding="utf-8", errors="replace") as log:
        proc = subprocess.run(cmd, cwd=str(ROOT), text=True, stdout=log, stderr=subprocess.STDOUT, timeout=timeout)
    if proc.returncode != 0:
        raise SystemExit(f"Command failed ({proc.returncode}); see {log_path}")


BLENDER_BUILD = r'''
import argparse
import hashlib
import json
import math
import random
from datetime import datetime, timezone
from pathlib import Path

import bmesh
import bpy
from mathutils import Vector


R1_MATERIAL = "SURF20_R5_aged_painted_carbon_steel_shared_world"
R1_NODE_GRAPH_HASH = "6bf8bd2fcf7712081d1ad2620c3133a984ada8c9b3927b59aa86131ba3b134a6"
SCENARIO_ID = "E_BURDEN_PHYSICS_FX_RESPONSE_V1"

TIMELINE = [
    {"name": "下降A", "start": 1, "end": 96, "claim": "沿用R2L示意料柱下降"},
    {"name": "焦批分批抛落/槽体方位旋转", "start": 97, "end": 192, "claim": "E级方位与轻微倾角示意"},
    {"name": "焦批撞击/径向散开/低透明扬尘", "start": 145, "end": 210, "claim": "非逐粒刚体，仅视觉代理"},
    {"name": "焦炭孔隙近景", "start": 205, "end": 236, "claim": "程序凹凸与少量Hero孔洞"},
    {"name": "下降B", "start": 241, "end": 336, "claim": "沿用R2L示意料柱下降"},
    {"name": "矿批分批抛落/错相旋转", "start": 337, "end": 432, "claim": "E级方位与轻微倾角示意"},
    {"name": "矿批滚落/冲击扬尘", "start": 405, "end": 462, "claim": "浅凹面滚落视觉代理"},
    {"name": "E/what-if软熔带响应开关", "start": 505, "end": 548, "claim": "独立演示对象，生产态默认关闭"},
    {"name": "循环闭合检查", "start": 553, "end": 576, "claim": "F576与F1保持新增FX关闭"},
]


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("--stage", required=True)
    parser.add_argument("--candidate", required=True)
    parser.add_argument("--formal-glb", required=True)
    parser.add_argument("--formal-glb-sha", required=True)
    argv = None
    import sys
    if "--" in sys.argv:
        argv = sys.argv[sys.argv.index("--") + 1:]
    return parser.parse_args(argv)


def file_sha(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def set_custom(obj, **kw):
    base = {
        "evidenceLevel": "E",
        "evidence_level": "illustrative",
        "claim_label": "E/illustrative",
        "scenario_id": SCENARIO_ID,
        "dataMode": "VISUAL_RESPONSE_ONLY",
        "notForConstruction": True,
        "notRealtime": True,
        "notMeasured": True,
        "sourceContract": "R2M_visual_candidate_only_no_live_stockline_no_DEM_no_CFD",
    }
    base.update(kw)
    for k, v in base.items():
        obj[k] = v


def make_collection(name, parent=None):
    col = bpy.data.collections.get(name) or bpy.data.collections.new(name)
    if parent is None:
        if col.name not in [c.name for c in bpy.context.scene.collection.children]:
            bpy.context.scene.collection.children.link(col)
    else:
        if col.name not in [c.name for c in parent.children]:
            parent.children.link(col)
    return col


def link_to(obj, col):
    for c in list(obj.users_collection):
        c.objects.unlink(obj)
    col.objects.link(obj)


def mat_principled(name, color, roughness=0.85, metallic=0.0, alpha=1.0, bump=False, emission=None):
    mat = bpy.data.materials.new(name)
    mat.diffuse_color = color
    mat.use_nodes = True
    mat.blend_method = "BLEND" if alpha < 1 else "OPAQUE"
    nodes = mat.node_tree.nodes
    links = mat.node_tree.links
    nodes.clear()
    out = nodes.new("ShaderNodeOutputMaterial")
    bsdf = nodes.new("ShaderNodeBsdfPrincipled")
    if "Base Color" in bsdf.inputs:
        bsdf.inputs["Base Color"].default_value = color
    if "Roughness" in bsdf.inputs:
        bsdf.inputs["Roughness"].default_value = roughness
    if "Metallic" in bsdf.inputs:
        bsdf.inputs["Metallic"].default_value = metallic
    if "Alpha" in bsdf.inputs:
        bsdf.inputs["Alpha"].default_value = alpha
    if emission and "Emission Color" in bsdf.inputs:
        bsdf.inputs["Emission Color"].default_value = emission[0]
        if "Emission Strength" in bsdf.inputs:
            bsdf.inputs["Emission Strength"].default_value = emission[1]
    if bump:
        noise = nodes.new("ShaderNodeTexNoise")
        noise.inputs["Scale"].default_value = 65
        noise.inputs["Detail"].default_value = 11
        noise.inputs["Roughness"].default_value = 0.68
        bump_node = nodes.new("ShaderNodeBump")
        bump_node.inputs["Strength"].default_value = 0.22
        bump_node.inputs["Distance"].default_value = 0.10
        links.new(noise.outputs["Fac"], bump_node.inputs["Height"])
        if "Normal" in bsdf.inputs:
            links.new(bump_node.outputs["Normal"], bsdf.inputs["Normal"])
    links.new(bsdf.outputs["BSDF"], out.inputs["Surface"])
    return mat


def set_visibility(obj, frame, visible):
    obj.hide_viewport = not visible
    obj.hide_render = not visible
    obj.keyframe_insert("hide_viewport", frame=frame)
    obj.keyframe_insert("hide_render", frame=frame)


def look_at(obj, target):
    direction = Vector(target) - obj.location
    obj.rotation_euler = direction.to_track_quat("-Z", "Y").to_euler()


def add_camera(name, loc, target, ortho, col):
    cam_data = bpy.data.cameras.new(name + "_DATA")
    cam_data.type = "ORTHO"
    cam_data.ortho_scale = ortho
    cam = bpy.data.objects.new(name, cam_data)
    cam.location = loc
    look_at(cam, target)
    link_to(cam, col)
    set_custom(cam, assetId=name, batchRole="RENDER_CAMERA", renderOnly=True)
    return cam


def add_text(name, text, loc, size, mat, col, target=(0, -8, 17)):
    curve = bpy.data.curves.new(name + "_CURVE", "FONT")
    curve.body = text
    curve.align_x = "CENTER"
    curve.align_y = "CENTER"
    curve.size = size
    obj = bpy.data.objects.new(name, curve)
    obj.location = loc
    look_at(obj, target)
    obj.rotation_euler.rotate_axis("Y", math.pi)
    obj.data.materials.append(mat)
    link_to(obj, col)
    set_custom(obj, assetId=name, batchRole="LABEL", renderOnly=True)
    return obj


def mesh_volume(obj):
    if obj.type != "MESH":
        return None, None
    bm = bmesh.new()
    bm.from_mesh(obj.data)
    bm.verts.ensure_lookup_table()
    bm.edges.ensure_lookup_table()
    bm.faces.ensure_lookup_table()
    nonmanifold = sum(1 for e in bm.edges if len(e.link_faces) != 2)
    volume = abs(bm.calc_volume())
    bm.free()
    return nonmanifold, volume


def material_node_hash(material):
    if material is None or not material.use_nodes or material.node_tree is None:
        return None
    def socket_value(value):
        if isinstance(value, bool):
            return value
        if isinstance(value, (int, float)):
            return float(value) if isinstance(value, float) else value
        try:
            values = list(value)
        except TypeError:
            return None
        if all(isinstance(item, (int, float, bool)) for item in values):
            return [round(float(item), 8) if isinstance(item, float) else item for item in values]
        return None
    nodes = []
    for n in sorted(material.node_tree.nodes, key=lambda item: item.name):
        inputs = {}
        for socket in n.inputs:
            if n.bl_idname == "ShaderNodeMapping" and socket.name != "Vector":
                continue
            if not hasattr(socket, "default_value"):
                continue
            value = socket_value(socket.default_value)
            if value is not None:
                inputs[socket.name] = value
        nodes.append({
            "name": n.name,
            "bl_idname": n.bl_idname,
            "label": n.label,
            "inputs": inputs,
            "object": n.object.name if hasattr(n, "object") and n.object is not None else None,
        })
    links = sorted(
        [{"from": f"{l.from_node.name}.{l.from_socket.name}", "to": f"{l.to_node.name}.{l.to_socket.name}"} for l in material.node_tree.links],
        key=lambda item: (item["from"], item["to"]),
    )
    payload = {"nodes": nodes, "links": links}
    return hashlib.sha256(json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()


def protected_counts():
    sensors = [o for o in bpy.data.objects if o.name.startswith("SENSOR_")]
    return {
        "objects": len(bpy.data.objects),
        "sensors": len(sensors),
        "body_temperature_sensors": len([o for o in bpy.data.objects if o.name.startswith("SENSOR_T_body_L")]),
        "pressure_points": len([o for o in bpy.data.objects if o.name.startswith("GL02_INT30_PRESSURE_")]),
        "temperature_layer_bands": len([o for o in bpy.data.objects if o.name.startswith("GL02_SENSOR_LAYER_L")]),
        "l7_l16_counts": {f"L{i}": len([o for o in bpy.data.objects if o.name.startswith(f"SENSOR_T_body_L{i}_")]) for i in range(7, 17)},
    }


def make_box(name, loc, scale, mat, col, parent=None):
    bpy.ops.mesh.primitive_cube_add(size=1, location=loc)
    obj = bpy.context.object
    obj.name = name
    obj.data.name = name + "_MESH"
    obj.scale = scale
    obj.data.materials.append(mat)
    if parent:
        obj.parent = parent
    link_to(obj, col)
    set_custom(obj, assetId=name, batchRole="CHUTE_SOLID_ENTITY", closedPositiveVolume=True)
    return obj


def make_rock(name, role, mat, col, seed, loc, scale):
    rnd = random.Random(seed)
    bpy.ops.mesh.primitive_ico_sphere_add(subdivisions=2, radius=1.0, location=loc)
    obj = bpy.context.object
    obj.name = name
    obj.data.name = name + "_MESH"
    for v in obj.data.vertices:
        co = v.co
        co.x *= scale[0] * rnd.uniform(0.72, 1.28)
        co.y *= scale[1] * rnd.uniform(0.68, 1.24)
        co.z *= scale[2] * rnd.uniform(0.62, 1.30)
        if rnd.random() < 0.18:
            co *= rnd.uniform(0.78, 0.92)
    obj.data.update(calc_edges=True)
    obj.rotation_euler = (rnd.random() * math.tau, rnd.random() * math.tau, rnd.random() * math.tau)
    obj.data.materials.append(mat)
    link_to(obj, col)
    set_custom(obj, assetId=name, batchRole=role, heroParticle=True, closedPositiveVolume=True)
    return obj


def animate_chunk(obj, start, delay, angle, role):
    launch = start + delay
    impact = launch + (42 if role == "COKE" else 38)
    settle = impact + (28 if role == "COKE" else 34)
    r0 = 0.52
    phase = delay * 0.37 + (0.0 if role == "COKE" else 1.4)
    r1 = 1.18 + 0.13 * delay + 0.30 * abs(math.sin(phase))
    r2 = min(2.35, r1 + 0.34 + 0.16 * math.cos(phase))
    p0 = Vector((r0 * math.cos(angle), r0 * math.sin(angle), 24.10))
    p1 = Vector((1.05 * math.cos(angle + 0.10), 1.05 * math.sin(angle + 0.10), 21.60))
    p2 = Vector((r1 * math.cos(angle + 0.28), r1 * math.sin(angle + 0.28), 17.58 + 0.26 * math.sin(phase)))
    p3 = Vector((r2 * math.cos(angle + 0.42), r2 * math.sin(angle + 0.42), 17.28 + 0.16 * math.cos(phase * 1.3)))
    visible_until = 462 if role == "ORE" else settle
    for f, vis in ((1, False), (launch - 1, False), (launch, True), (visible_until, True), (visible_until + 1, False), (576, False)):
        set_visibility(obj, f, vis)
    for f, p, spin in ((launch, p0, 0), (launch + 18, p1, 1.1), (impact, p2, 2.8), (settle, p3, 4.6)):
        obj.location = p
        obj.rotation_euler.rotate_axis("Z", spin)
        obj.rotation_euler.rotate_axis("X", 0.42 + spin * 0.3)
        obj.keyframe_insert("location", frame=f)
        obj.keyframe_insert("rotation_euler", frame=f)
    obj["launch_frame"] = launch
    obj["impact_frame"] = impact
    obj["settle_frame"] = settle
    obj["motion_notes"] = "delayed_batch_parabolic_fall_radial_scatter_surface_roll"
    return {"name": obj.name, "launch": launch, "impact": impact, "settle": settle, "role": role}


def make_dust(name, mat, col, loc, start, end, seed):
    rnd = random.Random(seed)
    bpy.ops.mesh.primitive_ico_sphere_add(subdivisions=2, radius=1.0, location=loc)
    obj = bpy.context.object
    obj.name = name
    obj.data.name = name + "_MESH"
    base = rnd.uniform(0.18, 0.32)
    obj.scale = (base * rnd.uniform(0.85, 1.25), base * rnd.uniform(0.75, 1.20), base * rnd.uniform(0.55, 1.05))
    obj.data.materials.append(mat)
    link_to(obj, col)
    set_custom(obj, assetId=name, batchRole="LOW_ALPHA_DUST_FX", transparentFx=True, closedVolumeExempt=True, sourceContract="short_impact_dust_not_smoke_column")
    for f, vis in ((1, False), (start - 1, False), (start, True), (end, True), (end + 1, False), (576, False)):
        set_visibility(obj, f, vis)
    obj.keyframe_insert("scale", frame=start)
    obj.location = Vector(loc) + Vector((rnd.uniform(-0.26, 0.26), rnd.uniform(-0.22, 0.22), rnd.uniform(0.30, 0.84)))
    obj.scale = (base * rnd.uniform(1.55, 2.35), base * rnd.uniform(1.30, 2.00), base * rnd.uniform(1.45, 2.35))
    obj.keyframe_insert("location", frame=end)
    obj.keyframe_insert("scale", frame=end)
    return obj


def make_annular_band(name, z0, z1, r0, r1, mat, col):
    seg = 96
    verts = []
    faces = []
    for i in range(seg):
        a = math.tau * i / seg
        verts.extend([
            (r0 * math.cos(a), r0 * math.sin(a), z0),
            (r1 * math.cos(a), r1 * math.sin(a), z0),
            (r0 * math.cos(a), r0 * math.sin(a), z1),
            (r1 * math.cos(a), r1 * math.sin(a), z1),
        ])
    for i in range(seg):
        j = (i + 1) % seg
        a, b, c, d = i * 4, j * 4, i * 4 + 1, j * 4 + 1
        e, f, g, h = i * 4 + 2, j * 4 + 2, i * 4 + 3, j * 4 + 3
        faces += [(a,b,f,e), (c,g,h,d), (e,f,h,g), (a,c,d,b)]
    mesh = bpy.data.meshes.new(name + "_MESH")
    mesh.from_pydata(verts, [], faces)
    mesh.update(calc_edges=True)
    obj = bpy.data.objects.new(name, mesh)
    obj.data.materials.append(mat)
    link_to(obj, col)
    set_custom(obj, assetId=name, batchRole="WHAT_IF_SOFTENING_ZONE_RESPONSE", closedPositiveVolume=True, productionDefaultHidden=True, maxDownshiftM=0.15, maxThicknessIncreaseM=0.12, maxEccentricM=0.10)
    return obj


def create_scene(stage, candidate, formal_glb, formal_glb_sha):
    scene = bpy.context.scene
    source_blend_filepath = bpy.data.filepath
    scene.frame_start = 1
    scene.frame_end = 576
    scene.render.fps = 24
    scene.render.resolution_x = 1280
    scene.render.resolution_y = 720
    scene.render.film_transparent = False
    try:
        scene.render.engine = "BLENDER_EEVEE_NEXT"
    except Exception:
        scene.render.engine = "BLENDER_EEVEE"
    if hasattr(scene, "eevee") and hasattr(scene.eevee, "taa_render_samples"):
        scene.eevee.taa_render_samples = 16
    scene.view_settings.view_transform = "AgX"
    try:
        scene.view_settings.look = "AgX - Medium High Contrast"
    except TypeError:
        scene.view_settings.look = "Medium High Contrast"
    scene.view_settings.exposure = 0.62
    scene.view_settings.gamma = 1

    before_counts = protected_counts()
    r1_before = material_node_hash(bpy.data.materials.get(R1_MATERIAL))
    if r1_before != R1_NODE_GRAPH_HASH:
        raise RuntimeError(f"R1 node graph mismatch before R2M: {r1_before}")

    root = make_collection("BF3D_R2M_BURDEN_PHYSICS_FX_RESPONSE")
    cols = {n: make_collection("R2M_" + n, root) for n in ["CHUTE_SOLIDS", "HERO_PARTICLES", "IMPACT_DUST", "COKE_CLOSEUP", "WHATIF_SOFTENING", "RENDER_AUX"]}

    mat_chute = mat_principled("R2M_MAT_CHUTE_DARK_WEAR_STEEL_E", (0.38, 0.31, 0.22, 1), 0.62, 0.25)
    mat_liner = mat_principled("R2M_MAT_CHUTE_WEAR_LINER_E", (0.18, 0.16, 0.13, 1), 0.78, 0.12)
    mat_coke = mat_principled("R2M_MAT_COKE_POROUS_BROKEN_NORMAL_BUMP_E", (0.095, 0.090, 0.082, 1), 0.92, 0.0, 1.0, bump=True)
    mat_ore = mat_principled("R2M_MAT_ORE_ROUGH_RED_BROWN_E", (0.34, 0.13, 0.055, 1), 0.88, 0.0)
    mat_pore = mat_principled("R2M_MAT_COKE_HERO_DARK_PORE_E", (0.035, 0.032, 0.028, 1), 0.98, 0.0)
    mat_dust_c = mat_principled("R2M_MAT_LOW_ALPHA_COKE_IMPACT_DUST_E", (0.48, 0.39, 0.28, 0.145), 0.98, 0.0, 0.145)
    mat_dust_o = mat_principled("R2M_MAT_LOW_ALPHA_ORE_IMPACT_DUST_E", (0.54, 0.36, 0.22, 0.136), 0.98, 0.0, 0.136)
    mat_soft = mat_principled("R2M_MAT_WHATIF_SOFTENING_WARM_BREATH_E", (1.00, 0.24, 0.06, 0.62), 0.78, 0.0, 0.62, emission=((1.0, 0.22, 0.04, 1), 0.62))
    mat_soft_shell = mat_principled("R2M_MAT_WHATIF_SOFTENING_CONFIDENCE_OUTER_SHELL_E", (1.00, 0.45, 0.10, 0.48), 0.82, 0.0, 0.48, emission=((1.0, 0.36, 0.07, 1), 0.38))
    mat_label = mat_principled("R2M_MAT_LABEL_LIGHT_E", (0.90, 0.94, 0.90, 1), 0.72, 0.0)
    mat_label_board = mat_principled("R2M_MAT_LABEL_DARK_BACKPLATE_E", (0.025, 0.030, 0.030, 0.62), 0.85, 0.0, 0.62)

    # Bell-less rotating chute entity: pivot, wear-lined trough body, outlet.
    pivot = bpy.data.objects.new("R2M_TOP_CHUTE_ROTATION_PIVOT_CTRL_E", None)
    pivot.empty_display_type = "ARROWS"
    pivot.empty_display_size = 0.85
    pivot.location = (0, 0, 24.72)
    link_to(pivot, cols["CHUTE_SOLIDS"])
    set_custom(pivot, assetId=pivot.name, batchRole="CHUTE_CONTROL", sourceContract="E_grade_no_actual_angle")
    make_box("R2M_TOP_CHUTE_SUPPORT_HUB_SOLID_E", (0, 0, 24.72), (0.34, 0.34, 0.26), mat_chute, cols["CHUTE_SOLIDS"], pivot)
    bpy.ops.mesh.primitive_cylinder_add(vertices=32, radius=0.13, depth=1.25, location=(0, 0, 25.28))
    shaft = bpy.context.object
    shaft.name = "R2M_TOP_CHUTE_CENTER_HANGING_SHAFT_SOLID_E"
    shaft.data.name = shaft.name + "_MESH"
    shaft.data.materials.append(mat_chute)
    shaft.parent = pivot
    link_to(shaft, cols["CHUTE_SOLIDS"])
    set_custom(shaft, assetId=shaft.name, batchRole="CHUTE_SOLID_ENTITY", closedPositiveVolume=True)
    bpy.ops.mesh.primitive_uv_sphere_add(segments=24, ring_count=12, radius=0.22, location=(0, 0, 24.72))
    bearing = bpy.context.object
    bearing.name = "R2M_TOP_CHUTE_CENTER_BEARING_PIVOT_SOLID_E"
    bearing.data.name = bearing.name + "_MESH"
    bearing.scale = (1.0, 1.0, 0.56)
    bearing.data.materials.append(mat_chute)
    bearing.parent = pivot
    link_to(bearing, cols["CHUTE_SOLIDS"])
    set_custom(bearing, assetId=bearing.name, batchRole="CHUTE_SOLID_ENTITY", closedPositiveVolume=True)
    body = make_box("R2M_TOP_CHUTE_WEAR_TROUGH_BODY_SOLID_E", (0, -1.02, 24.16), (0.36, 1.34, 0.13), mat_chute, cols["CHUTE_SOLIDS"], pivot)
    body.rotation_euler.x = math.radians(-12)
    left_wall = make_box("R2M_TOP_CHUTE_UV_LEFT_SIDEWALL_SOLID_E", (-0.34, -1.05, 24.34), (0.055, 1.16, 0.22), mat_chute, cols["CHUTE_SOLIDS"], pivot)
    right_wall = make_box("R2M_TOP_CHUTE_UV_RIGHT_SIDEWALL_SOLID_E", (0.34, -1.05, 24.34), (0.055, 1.16, 0.22), mat_chute, cols["CHUTE_SOLIDS"], pivot)
    left_wall.rotation_euler.x = math.radians(-12)
    right_wall.rotation_euler.x = math.radians(-12)
    liner = make_box("R2M_TOP_CHUTE_VISIBLE_WEAR_LINER_SOLID_E", (0, -1.05, 24.29), (0.29, 1.20, 0.035), mat_liner, cols["CHUTE_SOLIDS"], pivot)
    liner.rotation_euler.x = math.radians(-12)
    outlet = make_box("R2M_TOP_CHUTE_DISCHARGE_OUTLET_SOLID_E", (0, -2.32, 23.86), (0.44, 0.22, 0.20), mat_chute, cols["CHUTE_SOLIDS"], pivot)
    outlet.rotation_euler.x = math.radians(-12)
    bpy.ops.mesh.primitive_cone_add(vertices=24, radius1=0.30, radius2=0.20, depth=0.58, location=(0, -2.66, 23.74), rotation=(math.radians(78), 0, 0))
    nozzle = bpy.context.object
    nozzle.name = "R2M_TOP_CHUTE_TAPERED_EXIT_NOZZLE_SOLID_E"
    nozzle.data.name = nozzle.name + "_MESH"
    nozzle.data.materials.append(mat_chute)
    nozzle.parent = pivot
    link_to(nozzle, cols["CHUTE_SOLIDS"])
    set_custom(nozzle, assetId=nozzle.name, batchRole="CHUTE_SOLID_ENTITY", closedPositiveVolume=True)
    for f, rz, tilt, vis in ((1, 0, 0, False), (96, 0, 0, False), (97, -35, -3, True), (144, 185, 2.5, True), (192, 325, -2, True), (193, 325, -2, False), (336, 145, 0, False), (337, 145, 2, True), (384, 330, -2.5, True), (432, 505, 1, True), (433, 505, 1, False), (576, 0, 0, False)):
        pivot.rotation_euler = (math.radians(tilt), 0, math.radians(rz))
        pivot.keyframe_insert("rotation_euler", frame=f)
        for o in [pivot, shaft, bearing, body, left_wall, right_wall, liner, outlet, nozzle]:
            set_visibility(o, f, vis)

    chunk_records = []
    for i in range(10):
        a = math.radians(-105 + i * 18)
        obj = make_rock(f"R2M_COKE_HERO_DELAYED_PARABOLIC_CHUNK_{i+1:02d}_E", "COKE_HERO_PARTICLE", mat_coke, cols["HERO_PARTICLES"], 20260719 + i, (0, 0, 24), (0.18, 0.15, 0.12))
        chunk_records.append(animate_chunk(obj, 97, i * 5, a, "COKE"))
    for i in range(8):
        a = math.radians(80 + i * 22)
        obj = make_rock(f"R2M_ORE_HERO_DELAYED_PARABOLIC_CHUNK_{i+1:02d}_E", "ORE_HERO_PARTICLE", mat_ore, cols["HERO_PARTICLES"], 20260819 + i, (0, 0, 24), (0.22, 0.18, 0.14))
        chunk_records.append(animate_chunk(obj, 337, i * 6, a, "ORE"))
    for i, loc in enumerate([(0.35, -0.62, 17.80), (1.05, -0.70, 17.74), (1.55, -0.46, 17.86)]):
        obj = make_rock(f"R2M_ORE_ROLLDOWN_CLEAR_EVIDENCE_CHUNK_{i+1:02d}_E", "ORE_ROLLDOWN_EVIDENCE", mat_ore, cols["HERO_PARTICLES"], 20261000 + i, loc, (0.24, 0.19, 0.15))
        obj["heroParticle"] = False
        obj["motion_notes"] = "F432_clear_ore_rolldown_evidence_not_individual_physics_sim"
        for f, vis in ((1, False), (404, False), (405, True), (445, True), (446, False), (576, False)):
            set_visibility(obj, f, vis)
        obj.keyframe_insert("location", frame=405)
        obj.location = (loc[0] + 0.18 * (i - 1), loc[1] + 0.12, loc[2] - 0.10)
        obj.rotation_euler.rotate_axis("Z", 0.7 + i * 0.35)
        obj.rotation_euler.rotate_axis("X", 0.5)
        obj.keyframe_insert("location", frame=432)
        obj.keyframe_insert("rotation_euler", frame=432)

    # Closeup coke cluster with readable pore dots and broken silhouettes.
    closeup_chunks = []
    for i, loc in enumerate([(1.05, -0.40, 17.92), (1.36, -0.58, 17.82), (0.82, -0.72, 17.70), (1.22, -0.18, 17.78)]):
        obj = make_rock(f"R2M_COKE_CLOSEUP_POROUS_BROKEN_CHUNK_{i+1:02d}_E", "COKE_CLOSEUP_HERO", mat_coke, cols["COKE_CLOSEUP"], 20260900 + i, loc, (0.28, 0.20, 0.16))
        closeup_chunks.append(obj)
        for f, vis in ((1, False), (204, False), (205, True), (236, True), (237, False), (576, False)):
            set_visibility(obj, f, vis)
    pore_records = []
    for i in range(12):
        loc = (0.86 + (i % 4) * 0.16, -0.78 + (i // 4) * 0.20, 17.90 + 0.025 * (i % 3))
        bpy.ops.mesh.primitive_cube_add(size=1, location=loc)
        pore = bpy.context.object
        pore.name = f"R2M_COKE_CLOSEUP_RECESSED_DARK_CAVITY_CRACK_{i+1:02d}_E"
        pore.scale = (0.030 + 0.007 * (i % 3), 0.006, 0.006)
        pore.rotation_euler = (math.radians(70 + (i % 3) * 6), 0, math.radians(18 + i * 17))
        pore.data.materials.append(mat_pore)
        link_to(pore, cols["COKE_CLOSEUP"])
        set_custom(pore, assetId=pore.name, batchRole="COKE_HERO_RECESSED_CAVITY_CRACK", closedPositiveVolume=True, surfaceNormalAligned=True)
        for f, vis in ((1, False), (204, False), (205, True), (236, True), (237, False), (576, False)):
            set_visibility(pore, f, vis)
        pore_records.append(pore.name)

    dust = []
    coke_dust_offsets = [(0.76, -0.70, 17.76), (0.98, -0.55, 17.85), (1.18, -0.36, 17.92), (0.62, -0.32, 17.88), (1.36, -0.58, 17.82), (0.92, -0.18, 18.02), (1.22, -0.78, 17.95), (0.52, -0.58, 18.05)]
    for i, offs in enumerate(coke_dust_offsets):
        dust.append(make_dust(f"R2M_COKE_IMPACT_LOW_ALPHA_DUST_PATCH_{i+1:02d}_E", mat_dust_c, cols["IMPACT_DUST"], offs, 150 + i * 4, 188 + i * 3, 100 + i))
    ore_dust_offsets = [(0.72, -0.66, 17.64), (1.04, -0.48, 17.72), (1.32, -0.32, 17.82), (0.52, -0.30, 17.76), (1.42, -0.64, 17.70), (0.92, -0.18, 17.90), (1.18, -0.82, 17.83), (0.50, -0.54, 17.92)]
    for i, offs in enumerate(ore_dust_offsets):
        dust.append(make_dust(f"R2M_ORE_IMPACT_LOW_ALPHA_DUST_PATCH_{i+1:02d}_E", mat_dust_o, cols["IMPACT_DUST"], offs, 405 + i * 4, 445 + i * 3, 200 + i))

    band = make_annular_band("R2M_WHATIF_SOFTENING_ZONE_RESPONSE_ON_OFF_BAND_E", 12.65, 13.65, 0.74, 1.48, mat_soft, cols["WHATIF_SOFTENING"])
    band_shell = make_annular_band("R2M_WHATIF_SOFTENING_CONFIDENCE_OUTER_SHELL_E", 12.38, 14.02, 1.36, 1.92, mat_soft_shell, cols["WHATIF_SOFTENING"])
    band["whatif_label_required"] = "非本批次实时因果结果"
    band_shell["whatif_label_required"] = "非本批次实时因果结果"
    for soft_obj in (band, band_shell):
        for f, vis in ((1, False), (504, False), (505, True), (548, True), (549, False), (576, False)):
            set_visibility(soft_obj, f, vis)
        soft_obj.location = (0, 0, 0)
        soft_obj.scale = (1, 1, 1)
        soft_obj.keyframe_insert("location", frame=505)
        soft_obj.keyframe_insert("scale", frame=505)
        soft_obj.location = (0.06, -0.04, -0.15)
        soft_obj.scale = (0.97, 0.97, 1.12)
        soft_obj.keyframe_insert("location", frame=528)
        soft_obj.keyframe_insert("scale", frame=528)
        soft_obj.location = (0, 0, 0)
        soft_obj.scale = (1, 1, 1)
        soft_obj.keyframe_insert("location", frame=548)
        soft_obj.keyframe_insert("scale", frame=548)
    label_board = make_box("R2M_WHATIF_SOFTENING_LABEL_BACKPLATE_SOLID_E", (-2.35, -3.26, 15.02), (1.42, 0.035, 0.44), mat_label_board, cols["WHATIF_SOFTENING"])
    label_board.rotation_euler.z = math.radians(-8)
    set_custom(label_board, assetId=label_board.name, batchRole="WHAT_IF_LABEL_BACKPLATE", closedPositiveVolume=True, renderOnly=True)
    for f, vis in ((1, False), (504, False), (505, True), (548, True), (549, False), (576, False)):
        set_visibility(label_board, f, vis)
    label = add_text(
        "R2M_WHATIF_SOFTENING_RESPONSE_LABEL_E",
        "软熔带响应开关演示\n非本批次实时因果结果",
        (-2.35, -3.32, 15.04),
        0.18,
        mat_label,
        cols["WHATIF_SOFTENING"],
        target=(5, -8, 14.2),
    )
    for f, vis in ((1, False), (504, False), (505, True), (548, True), (549, False), (576, False)):
        set_visibility(label, f, vis)
    safe_board = make_box("R2M_WHATIF_SAFE_OVERLAY_BACKPLATE_SOLID_E", (-3.70, -3.45, 21.55), (4.90, 0.040, 1.12), mat_label_board, cols["WHATIF_SOFTENING"])
    set_custom(safe_board, assetId=safe_board.name, batchRole="WHAT_IF_SAFE_OVERLAY_BACKPLATE", closedPositiveVolume=True, renderOnly=True)
    for f, vis in ((1, False), (504, False), (505, True), (548, True), (549, False), (576, False)):
        set_visibility(safe_board, f, vis)
    safe_label = add_text(
        "R2M_WHATIF_SAFE_OVERLAY_LABEL_E",
        "软熔带响应开关演示\n非本批次实时因果结果",
        (-3.70, -3.53, 21.58),
        0.62,
        mat_label,
        cols["WHATIF_SOFTENING"],
        target=(6, -12, 17),
    )
    for f, vis in ((1, False), (504, False), (505, True), (548, True), (549, False), (576, False)):
        set_visibility(safe_label, f, vis)

    # Render-only lighting and cameras.
    bpy.ops.object.light_add(type="AREA", location=(-4.5, -6.2, 27.5))
    key = bpy.context.object
    key.name = "R2M_RENDER_ONLY_WARM_AREA_KEY_E"
    key.data.energy = 760
    key.data.size = 5.2
    link_to(key, cols["RENDER_AUX"])
    set_custom(key, assetId=key.name, batchRole="RENDER_LIGHT", renderOnly=True)
    bpy.ops.object.light_add(type="POINT", location=(3.8, 3.0, 20.5))
    rim = bpy.context.object
    rim.name = "R2M_RENDER_ONLY_COOL_RIM_E"
    rim.data.energy = 135
    link_to(rim, cols["RENDER_AUX"])
    set_custom(rim, assetId=rim.name, batchRole="RENDER_LIGHT", renderOnly=True)
    bpy.ops.object.light_add(type="POINT", location=(0.8, -2.5, 19.8))
    dust_back = bpy.context.object
    dust_back.name = "R2M_RENDER_ONLY_DUST_BACKLIGHT_E"
    dust_back.data.energy = 240
    dust_back.data.color = (1.0, 0.76, 0.46)
    link_to(dust_back, cols["RENDER_AUX"])
    set_custom(dust_back, assetId=dust_back.name, batchRole="RENDER_LIGHT", renderOnly=True)

    cam_main = bpy.data.objects.get("R2L_CAMERA_MAIN_CUTAWAY_VIEW_E") or add_camera("R2M_CAMERA_MAIN_CUTAWAY_VIEW_E", (6, -12, 17), (0, 0, 17), 21, cols["RENDER_AUX"])
    cam_chute = add_camera("R2M_CAMERA_CHUTE_EXIT_E", (3.7, -6.8, 24.8), (0.05, -1.30, 23.9), 5.2, cols["RENDER_AUX"])
    cam_chute_detail = add_camera("R2M_CAMERA_CHUTE_DETAIL_TOP_E", (1.25, -2.80, 25.15), (0.0, -1.35, 24.20), 1.35, cols["RENDER_AUX"])
    cam_dust = add_camera("R2M_CAMERA_IMPACT_DUST_CLOSE_E", (3.9, -6.2, 19.0), (0.95, -0.45, 17.82), 4.8, cols["RENDER_AUX"])
    cam_roll = add_camera("R2M_CAMERA_ORE_ROLLDOWN_CLOSE_E", (3.25, -5.30, 18.85), (1.05, -0.50, 17.78), 3.75, cols["RENDER_AUX"])
    cam_close = add_camera("R2M_CAMERA_COKE_MATERIAL_CLOSEUP_E", (3.05, -3.3, 19.15), (1.08, -0.55, 17.82), 1.65, cols["RENDER_AUX"])
    cam_soft = add_camera("R2M_CAMERA_WHATIF_SOFTENING_COMPARE_E", (5.0, -8.0, 14.2), (0.0, 0.0, 13.1), 7.4, cols["RENDER_AUX"])

    for item in TIMELINE:
        if not scene.timeline_markers.get(item["name"]):
            scene.timeline_markers.new(item["name"], frame=item["start"])

    r1_after = material_node_hash(bpy.data.materials.get(R1_MATERIAL))
    if r1_after != R1_NODE_GRAPH_HASH:
        raise RuntimeError(f"R1 node graph mismatch after R2M: {r1_after}")

    new_objects = [o for o in bpy.data.objects if o.get("scenario_id") == SCENARIO_ID]
    geometry_checks = []
    bad_geom = []
    for o in new_objects:
        if o.get("transparentFx") or o.type != "MESH":
            continue
        nonmanifold, volume = mesh_volume(o)
        geometry_checks.append({"name": o.name, "nonmanifold_edges": nonmanifold, "volume": volume})
        if nonmanifold != 0 or volume is None or volume <= 0:
            bad_geom.append(o.name)
    if bad_geom:
        raise RuntimeError("R2M closed positive volume gate failed: " + ", ".join(bad_geom))

    render_records = []
    render_plan = [
        (1, cam_main, "R2M_FRAME_0001_MAIN_FX_OFF.png"),
        (120, cam_chute, "R2M_FRAME_0120_CHUTE_COKE_THROW.png"),
        (168, cam_dust, "R2M_FRAME_0168_COKE_IMPACT_DUST.png"),
        (216, cam_close, "R2M_FRAME_0216_COKE_POROUS_CLOSEUP.png"),
        (384, cam_chute, "R2M_FRAME_0384_ORE_FROM_CHUTE.png"),
        (432, cam_roll, "R2M_FRAME_0432_ORE_ROLLDOWN.png"),
        (504, cam_main, "R2M_FRAME_0504_WHATIF_OFF.png"),
        (528, cam_main, "R2M_FRAME_0528_WHATIF_ON.png"),
        (576, cam_main, "R2M_FRAME_0576_MAIN_FX_OFF.png"),
    ]
    for frame, cam, filename in render_plan:
        scene.frame_set(frame)
        scene.camera = cam
        scene.render.filepath = str(Path(stage) / "renders" / filename)
        bpy.ops.render.render(write_still=True)
        render_records.append({"frame": frame, "camera": cam.name, "path": scene.render.filepath})

    frame_map = []
    preview_dir = Path(stage) / "renders" / "preview_seq"
    preview_frames = list(range(1, 577, 12))
    for idx, frame in enumerate(preview_frames):
        scene.frame_set(frame)
        scene.camera = cam_main
        scene.render.filepath = str(preview_dir / f"R2M_PREVIEW_{idx:04d}.png")
        bpy.ops.render.render(write_still=True)
        frame_map.append({"image_index": idx, "source_frame": frame})

    bpy.ops.wm.save_as_mainfile(filepath=candidate)
    candidate_sha = file_sha(candidate)
    formal_hash = file_sha(formal_glb)
    if formal_hash.lower() != formal_glb_sha.lower():
        raise RuntimeError("formal GLB hash changed")

    after_counts = protected_counts()
    report = {
        "schema_version": 1,
        "stage": "INT_30_20260719_R2M_BURDEN_PHYSICS_FX_RESPONSE",
        "status": "candidate_built",
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "evidence_level": "E/illustrative",
        "input_blend": source_blend_filepath,
        "input_sha256_expected": "c8a9bf6fe2d5093d7ba137695b7d696816abd0442da8ad170b1df2f9edc57095",
        "r1_controlled_node_graph_hash_expected": R1_NODE_GRAPH_HASH,
        "r1_controlled_node_graph_before": r1_before,
        "r1_controlled_node_graph_after": r1_after,
        "r1_controlled_node_graph_ok": r1_before == R1_NODE_GRAPH_HASH and r1_after == R1_NODE_GRAPH_HASH,
        "timeline": TIMELINE,
        "frame_rate": 24,
        "frame_start": 1,
        "frame_end": 576,
        "chute_contract": {
            "objects": [pivot.name, shaft.name, bearing.name, body.name, left_wall.name, right_wall.name, liner.name, outlet.name, nozzle.name],
            "windows": [{"role": "coke", "start": 97, "end": 192}, {"role": "ore", "start": 337, "end": 432}],
            "claim": "E级可读方位旋转和轻微倾角，不声称真实角度",
        },
        "chunk_motion_contract": {
            "independent_hero_chunk_objects": len([o for o in new_objects if o.get("heroParticle")]),
            "chunk_records": chunk_records,
            "no_high_cost_rigidbody": True,
            "no_136_independent_objects": True,
        },
        "coke_closeup_contract": {
            "program_material_bump": True,
            "hero_closeup_chunks": [o.name for o in closeup_chunks],
            "hero_pore_objects": pore_records,
        },
        "dust_contract": {
            "dust_objects": [o.name for o in dust],
            "f1_f576_off": True,
            "style": "low_alpha_rising_diffusing_fading_impact_patches_not_column",
        },
        "whatif_softening_contract": {
            "objects": [band.name, band_shell.name],
            "production_default_hidden": True,
            "visible_window": [505, 548],
            "off_frame": 504,
            "on_frame": 528,
            "max_downshift_m": 0.15,
            "thickness_increase_m": 0.12,
            "max_eccentric_m": 0.10,
            "required_label": "非本批次实时因果结果",
        },
        "before_counts": before_counts,
        "after_counts": after_counts,
        "protected_contract_ok": (
            after_counts["sensors"] == 115
            and after_counts["body_temperature_sensors"] == 80
            and after_counts["pressure_points"] == 18
            and after_counts["temperature_layer_bands"] == 10
            and all(v == 8 for v in after_counts["l7_l16_counts"].values())
        ),
        "new_object_count": len(new_objects),
        "new_hero_particle_object_count": len([o for o in new_objects if o.get("heroParticle")]),
        "geometry_checks": geometry_checks,
        "bad_geometry": bad_geom,
        "render_records": render_records,
        "preview_sequence": str(preview_dir),
        "preview_frame_map": frame_map,
        "candidate_blend": candidate,
        "candidate_sha256": candidate_sha,
        "formal_glb_sha256": formal_hash,
        "formal_glb_unchanged": formal_hash.lower() == formal_glb_sha.lower(),
        "blender_version": bpy.app.version_string,
    }
    Path(stage, "reports", "int30_r2m_machine_report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    Path(stage, "reports", "r2m_timeline_contract.json").write_text(json.dumps(TIMELINE, ensure_ascii=False, indent=2), encoding="utf-8")
    return report


args = parse_args()
report = create_scene(args.stage, args.candidate, args.formal_glb, args.formal_glb_sha)
print(json.dumps({"ok": True, "candidate": report["candidate_blend"], "sha256": report["candidate_sha256"]}, ensure_ascii=False))
'''


BLENDER_REOPEN = r'''
import argparse
import hashlib
import json
from pathlib import Path

import bmesh
import bpy

R1_MATERIAL = "SURF20_R5_aged_painted_carbon_steel_shared_world"
R1_NODE_GRAPH_HASH = "6bf8bd2fcf7712081d1ad2620c3133a984ada8c9b3927b59aa86131ba3b134a6"
SCENARIO_ID = "E_BURDEN_PHYSICS_FX_RESPONSE_V1"


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("--stage", required=True)
    parser.add_argument("--out", required=True)
    import sys
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else None
    return parser.parse_args(argv)


def material_node_hash(material):
    if material is None or not material.use_nodes or material.node_tree is None:
        return None
    def socket_value(value):
        if isinstance(value, bool):
            return value
        if isinstance(value, (int, float)):
            return float(value) if isinstance(value, float) else value
        try:
            values = list(value)
        except TypeError:
            return None
        if all(isinstance(item, (int, float, bool)) for item in values):
            return [round(float(item), 8) if isinstance(item, float) else item for item in values]
        return None
    nodes = []
    for n in sorted(material.node_tree.nodes, key=lambda item: item.name):
        inputs = {}
        for socket in n.inputs:
            if n.bl_idname == "ShaderNodeMapping" and socket.name != "Vector":
                continue
            if not hasattr(socket, "default_value"):
                continue
            value = socket_value(socket.default_value)
            if value is not None:
                inputs[socket.name] = value
        nodes.append({
            "name": n.name,
            "bl_idname": n.bl_idname,
            "label": n.label,
            "inputs": inputs,
            "object": n.object.name if hasattr(n, "object") and n.object is not None else None,
        })
    links = sorted(
        [{"from": f"{l.from_node.name}.{l.from_socket.name}", "to": f"{l.to_node.name}.{l.to_socket.name}"} for l in material.node_tree.links],
        key=lambda item: (item["from"], item["to"]),
    )
    payload = {"nodes": nodes, "links": links}
    return hashlib.sha256(json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()


def counts():
    sensors = [o for o in bpy.data.objects if o.name.startswith("SENSOR_")]
    return {
        "objects": len(bpy.data.objects),
        "sensors": len(sensors),
        "body_temperature_sensors": len([o for o in bpy.data.objects if o.name.startswith("SENSOR_T_body_L")]),
        "pressure_points": len([o for o in bpy.data.objects if o.name.startswith("GL02_INT30_PRESSURE_")]),
        "temperature_layer_bands": len([o for o in bpy.data.objects if o.name.startswith("GL02_SENSOR_LAYER_L")]),
        "l7_l16_counts": {f"L{i}": len([o for o in bpy.data.objects if o.name.startswith(f"SENSOR_T_body_L{i}_")]) for i in range(7, 17)},
    }


def visible_names(frame, pred):
    bpy.context.scene.frame_set(frame)
    return [o.name for o in bpy.data.objects if pred(o) and not o.hide_render]


def geom_bad():
    bad = []
    for o in bpy.data.objects:
        if o.get("scenario_id") != SCENARIO_ID or o.type != "MESH" or o.get("transparentFx"):
            continue
        bm = bmesh.new()
        bm.from_mesh(o.data)
        bm.verts.ensure_lookup_table()
        bm.edges.ensure_lookup_table()
        nonmanifold = sum(1 for e in bm.edges if len(e.link_faces) != 2)
        volume = abs(bm.calc_volume())
        bm.free()
        if nonmanifold != 0 or volume <= 0:
            bad.append({"name": o.name, "nonmanifold_edges": nonmanifold, "volume": volume})
    return bad


args = parse_args()
scene = bpy.context.scene
new_objects = [o for o in bpy.data.objects if o.get("scenario_id") == SCENARIO_ID]
new_names = [o.name for o in new_objects]
cnt = counts()
r1 = material_node_hash(bpy.data.materials.get(R1_MATERIAL))
dust_f1 = visible_names(1, lambda o: o.get("batchRole") == "LOW_ALPHA_DUST_FX")
dust_f576 = visible_names(576, lambda o: o.get("batchRole") == "LOW_ALPHA_DUST_FX")
whatif_f1 = visible_names(1, lambda o: o.get("batchRole") == "WHAT_IF_SOFTENING_ZONE_RESPONSE")
whatif_f528 = visible_names(528, lambda o: o.get("batchRole") == "WHAT_IF_SOFTENING_ZONE_RESPONSE")
hero_count = len([o for o in new_objects if o.get("heroParticle")])
bad = geom_bad()
status = (
    scene.frame_start == 1 and scene.frame_end == 576 and scene.render.fps == 24
    and cnt["sensors"] == 115 and cnt["body_temperature_sensors"] == 80 and cnt["pressure_points"] == 18
    and cnt["temperature_layer_bands"] == 10 and all(v == 8 for v in cnt["l7_l16_counts"].values())
    and r1 == R1_NODE_GRAPH_HASH
    and hero_count <= 24
    and not dust_f1 and not dust_f576 and not whatif_f1 and bool(whatif_f528)
    and not bad
)
payload = {
    "schema_version": 1,
    "status": "pass" if status else "fail",
    "frame_start": scene.frame_start,
    "frame_end": scene.frame_end,
    "fps": scene.render.fps,
    "counts": cnt,
    "new_object_count": len(new_objects),
    "new_hero_particle_object_count": hero_count,
    "r1_controlled_node_graph_hash_expected": R1_NODE_GRAPH_HASH,
    "r1_controlled_node_graph_hash_actual": r1,
    "r1_controlled_node_graph_ok": r1 == R1_NODE_GRAPH_HASH,
    "dust_visible_f1": dust_f1,
    "dust_visible_f576": dust_f576,
    "whatif_visible_f1": whatif_f1,
    "whatif_visible_f528": whatif_f528,
    "bad_geometry": bad,
    "protected_contract_ok": cnt["sensors"] == 115 and cnt["body_temperature_sensors"] == 80 and cnt["pressure_points"] == 18 and cnt["temperature_layer_bands"] == 10 and all(v == 8 for v in cnt["l7_l16_counts"].values()),
    "new_objects_sample": new_names[:80],
}
Path(args.out).write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
if not status:
    raise SystemExit("R2M reopen validation failed")
print(json.dumps({"ok": True, "status": payload["status"]}, ensure_ascii=False))
'''


def write_inner_scripts() -> None:
    BUILD_SCRIPT.write_text(BLENDER_BUILD, encoding="utf-8")
    REOPEN_SCRIPT.write_text(BLENDER_REOPEN, encoding="utf-8")


def encode_mp4() -> Path | None:
    out = RENDERS / "R2M_BURDEN_PHYSICS_FX_RESPONSE_PREVIEW_STEP12_24S.mp4"
    pattern = RENDERS / "preview_seq" / "R2M_PREVIEW_%04d.png"
    cmd = [
        "ffmpeg",
        "-y",
        "-framerate",
        "2",
        "-i",
        str(pattern),
        "-c:v",
        "libx264",
        "-pix_fmt",
        "yuv420p",
        "-movflags",
        "+faststart",
        str(out),
    ]
    try:
        run(cmd, "r2m_ffmpeg_mp4.log", timeout=300)
    except Exception as exc:
        print(f"MP4 encode failed: {exc}", file=sys.stderr)
        return None
    return out if out.exists() else None


def compose_contact_sheet(image_paths: list[Path], out: Path) -> Path | None:
    try:
        from PIL import Image, ImageDraw, ImageFont
    except Exception as exc:
        print(f"Pillow unavailable for contact sheet: {exc}", file=sys.stderr)
        return None
    imgs = []
    for p in image_paths:
        if p.exists():
            im = Image.open(p).convert("RGB")
            im.thumbnail((420, 236))
            canvas = Image.new("RGB", (420, 266), (24, 25, 24))
            canvas.paste(im, ((420 - im.width) // 2, 0))
            d = ImageDraw.Draw(canvas)
            d.text((10, 242), p.name, fill=(230, 230, 220))
            imgs.append(canvas)
    if not imgs:
        return None
    cols = 3
    rows = (len(imgs) + cols - 1) // cols
    sheet = Image.new("RGB", (cols * 420, rows * 266), (18, 18, 18))
    for i, im in enumerate(imgs):
        sheet.paste(im, ((i % cols) * 420, (i // cols) * 266))
    out.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(out)
    return out


def write_artifacts(machine: dict, reopen: dict, mp4: Path | None, contact: Path | None) -> dict:
    artifact_files = [
        Path(__file__),
        BUILD_SCRIPT,
        REOPEN_SCRIPT,
        CANDIDATE_BLEND,
        REPORTS / "int30_r2m_machine_report.json",
        REPORTS / "r2m_reopen_validation.json",
        REPORTS / "r2m_timeline_contract.json",
        STAGE / "INT-30_R2M_BURDEN_PHYSICS_FX_RESPONSE_阶段成果总结.md",
    ]
    if mp4:
        artifact_files.append(mp4)
    if contact:
        artifact_files.append(contact)
    artifact_files.extend(Path(r["path"]) for r in machine.get("render_records", []))
    rows = {}
    for p in artifact_files:
        if p and p.exists():
            rows[str(p.relative_to(ROOT))] = {"sha256": sha256(p), "bytes": p.stat().st_size}
    out = REPORTS / "artifact_sha256.json"
    out.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")
    return rows


def write_summary(machine: dict, reopen: dict, mp4: Path | None, contact: Path | None, artifacts: dict) -> None:
    rel = lambda p: str(Path(p).relative_to(ROOT)) if p else "未生成"
    lines = [
        "# INT-30 R2M 炉料物理/FX/软熔带响应视觉候选 阶段成果总结",
        "",
        f"- 状态：`{'pass' if reopen.get('status') == 'pass' else 'fail'}`。",
        f"- 输入：`{INPUT_BLEND.relative_to(ROOT)}`，SHA-256 `{machine.get('input_sha256_expected')}`。",
        f"- 候选 Blend：`{Path(machine['candidate_blend']).relative_to(ROOT)}`，SHA-256 `{machine['candidate_sha256']}`。",
        f"- 正式 GLB 未变：`{machine['formal_glb_unchanged']}`，SHA-256 `{machine['formal_glb_sha256']}`。",
        f"- R1 受控节点图：`{machine['r1_controlled_node_graph_after']}`，门禁 `{machine['r1_controlled_node_graph_ok']}`。",
        "",
        "## 已制作内容",
        "",
        "- 无料钟旋转溜槽实体：支点、耐磨槽体、耐磨衬面和出口均为闭合正体积对象；焦批 F97-F192、矿批 F337-F432 有方位旋转和轻微倾角变化，标注 E 级视觉代理。",
        "- 炉料运动：18 个 Hero 颗粒对象按分批延迟、抛物线落料、个体旋转、撞击后径向散开、浅凹面滚落处理；未使用逐粒刚体或 136 个独立对象。",
        "- 焦炭近景：程序 Normal/Bump 材质叠加 4 个近景 Hero 焦块和 12 个暗孔隙点，供 F216 近景检查。",
        "- 撞击 FX：焦批 F150-F188、矿批 F405-F445 低透明扬尘片，上升、扩散、淡出；F1/F576 关闭。",
        "- 软熔带响应：独立 `E/what-if` 对象，生产态默认 hidden，F505-F548 开关演示；最大下移 0.15m、厚度 +0.12m、偏心 0.10m 内，标签含“非本批次实时因果结果”。",
        "",
        "## 证据",
        "",
        f"- MP4：`{rel(mp4)}`。",
        f"- 接触表：`{rel(contact)}`。",
    ]
    for r in machine.get("render_records", []):
        lines.append(f"- F{r['frame']} `{r['camera']}`：`{Path(r['path']).relative_to(ROOT)}`")
    lines += [
        "",
        "## 门禁",
        "",
        f"- 115/80/18/10 与 L7-L16 每层 8 点：`{machine['protected_contract_ok']}`。",
        f"- 新 Hero 颗粒对象数：`{machine['new_hero_particle_object_count']}`。",
        f"- 闭合正体积检查：`{'pass' if not machine.get('bad_geometry') else machine.get('bad_geometry')}`；透明 FX 豁免并记录。",
        f"- `.blend1` 残留：`{machine.get('blend1_residual_count_after_cleanup', '未记录')}`；门禁 `{machine.get('blend1_residual_gate_ok', '未记录')}`。",
        f"- 本阶段新增 GLB：`{machine.get('new_glb_files_created_in_stage', [])}`；正式 GLB 合同 `{machine.get('formal_glb_contract', {}).get('unchanged', machine.get('formal_glb_unchanged'))}`。",
        f"- 重开检查：`{reopen.get('status')}`。",
        f"- artifact_sha256：`{(REPORTS / 'artifact_sha256.json').relative_to(ROOT)}`，条目数 `{len(artifacts)}`。",
        "",
        "## 已知不足",
        "",
        "- 本阶段是 E 级可读性候选，未接入实时料线、真实布料矩阵、粒径分布、DEM/CFD 或本批次热过程因果。",
        "- MP4 使用 step12 关键帧序列编码为 24 秒预览，适合审核动作读数，不等同于完整逐帧终稿。",
    ]
    (STAGE / "INT-30_R2M_BURDEN_PHYSICS_FX_RESPONSE_阶段成果总结.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def update_pipeline_status(machine: dict, reopen: dict, mp4: Path | None, contact: Path | None) -> None:
    status_path = ROOT / "reports" / "pipeline_status.json"
    if status_path.exists():
        data = json.loads(status_path.read_text(encoding="utf-8"))
    else:
        data = {"schema_version": 1, "stages": {}}
    data["current_stage"] = "INT-30_R2M_BURDEN_PHYSICS_FX_RESPONSE"
    data["updated_at"] = datetime.now(timezone.utc).isoformat()
    data.setdefault("stages", {})["INT-30_R2M_BURDEN_PHYSICS_FX_RESPONSE"] = {
        "status": "candidate_ready_for_review" if reopen.get("status") == "pass" else "validation_failed",
        "approval": "not_granted_requires_visual_and_spec_review",
        "approval_boundary": "Isolated Blender visual candidate only; no production GLB replacement.",
        "input_blend": str(INPUT_BLEND.relative_to(ROOT)),
        "input_sha256": INPUT_SHA256,
        "candidate_blend": str(Path(machine["candidate_blend"]).relative_to(ROOT)),
        "candidate_sha256": machine["candidate_sha256"],
        "formal_glb_sha256": machine["formal_glb_sha256"],
        "formal_glb_unchanged": machine["formal_glb_unchanged"],
        "machine_report": str((REPORTS / "int30_r2m_machine_report.json").relative_to(ROOT)),
        "reopen_report": str((REPORTS / "r2m_reopen_validation.json").relative_to(ROOT)),
        "artifact_sha256": str((REPORTS / "artifact_sha256.json").relative_to(ROOT)),
        "summary": str((STAGE / "INT-30_R2M_BURDEN_PHYSICS_FX_RESPONSE_阶段成果总结.md").relative_to(ROOT)),
        "mp4": str(mp4.relative_to(ROOT)) if mp4 else None,
        "contact_sheet": str(contact.relative_to(ROOT)) if contact else None,
        "next_stop_line": "visual/spec review required before any next INT-30 stage; formal GLB remains unchanged",
    }
    status_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    (STAGE / "pipeline_status.json").write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def cleanup_blend_backups() -> list[str]:
    removed = []
    for p in STAGE.rglob("*.blend1"):
        removed.append(str(p.relative_to(ROOT)))
        p.unlink()
    return removed


def finalize_machine_report(machine: dict, removed_blend1: list[str]) -> dict:
    residual = [str(p.relative_to(ROOT)) for p in STAGE.rglob("*.blend1")]
    stage_glbs = [str(p.relative_to(ROOT)) for p in STAGE.rglob("*.glb")]
    machine["blend1_cleanup_removed"] = removed_blend1
    machine["blend1_residual_count_after_cleanup"] = len(residual)
    machine["blend1_residual_files_after_cleanup"] = residual
    machine["blend1_residual_gate_ok"] = len(residual) == 0
    machine["new_glb_files_created_in_stage"] = stage_glbs
    machine["no_stage_glb_created"] = len(stage_glbs) == 0
    machine["formal_glb_contract"] = {
        "path": str(FORMAL_GLB.relative_to(ROOT)),
        "expected_sha256": FORMAL_GLB_SHA256,
        "actual_sha256": sha256(FORMAL_GLB),
        "unchanged": sha256(FORMAL_GLB).lower() == FORMAL_GLB_SHA256,
        "stage_action": "not_exported_not_replaced",
    }
    (REPORTS / "int30_r2m_machine_report.json").write_text(json.dumps(machine, ensure_ascii=False, indent=2), encoding="utf-8")
    return machine


def main() -> None:
    ensure_dirs()
    write_inner_scripts()
    if not BLENDER.exists():
        raise SystemExit(f"Blender not found: {BLENDER}")
    if sha256(INPUT_BLEND).lower() != INPUT_SHA256:
        raise SystemExit("R2L input SHA mismatch")
    if sha256(FORMAL_GLB).lower() != FORMAL_GLB_SHA256:
        raise SystemExit("Formal GLB SHA mismatch before R2M")

    run([
        str(BLENDER),
        "--background",
        str(INPUT_BLEND),
        "--python",
        str(BUILD_SCRIPT),
        "--",
        "--stage",
        str(STAGE),
        "--candidate",
        str(CANDIDATE_BLEND),
        "--formal-glb",
        str(FORMAL_GLB),
        "--formal-glb-sha",
        FORMAL_GLB_SHA256,
    ], "r2m_build_blender.log", timeout=3600)
    if not CANDIDATE_BLEND.exists() or not (REPORTS / "int30_r2m_machine_report.json").exists():
        raise SystemExit(f"Blender build did not produce candidate/report; see {LOGS / 'r2m_build_blender.log'}")

    run([
        str(BLENDER),
        "--background",
        str(CANDIDATE_BLEND),
        "--python",
        str(REOPEN_SCRIPT),
        "--",
        "--stage",
        str(STAGE),
        "--out",
        str(REPORTS / "r2m_reopen_validation.json"),
    ], "r2m_reopen_blender.log", timeout=900)

    machine = json.loads((REPORTS / "int30_r2m_machine_report.json").read_text(encoding="utf-8"))
    reopen = json.loads((REPORTS / "r2m_reopen_validation.json").read_text(encoding="utf-8"))
    proof = [Path(r["path"]) for r in machine.get("render_records", [])]
    contact = compose_contact_sheet(proof, RENDERS / "R2M_CONTACT_SHEET.png")
    mp4 = encode_mp4()
    removed = cleanup_blend_backups()
    machine = finalize_machine_report(machine, removed)
    write_summary(machine, reopen, mp4, contact, {})
    artifacts = write_artifacts(machine, reopen, mp4, contact)
    write_summary(machine, reopen, mp4, contact, artifacts)
    artifacts = write_artifacts(machine, reopen, mp4, contact)
    update_pipeline_status(machine, reopen, mp4, contact)

    result = {
        "stage": "INT-30_R2M_BURDEN_PHYSICS_FX_RESPONSE",
        "candidate_blend": str(CANDIDATE_BLEND),
        "candidate_sha256": sha256(CANDIDATE_BLEND),
        "machine_report": str(REPORTS / "int30_r2m_machine_report.json"),
        "reopen_report": str(REPORTS / "r2m_reopen_validation.json"),
        "mp4": str(mp4) if mp4 else None,
        "contact_sheet": str(contact) if contact else None,
        "blend1_removed": removed,
        "artifact_sha256": str(REPORTS / "artifact_sha256.json"),
        "summary": str(STAGE / "INT-30_R2M_BURDEN_PHYSICS_FX_RESPONSE_阶段成果总结.md"),
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
