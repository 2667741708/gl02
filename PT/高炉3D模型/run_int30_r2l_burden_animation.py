#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""INT-30 R2L: E级炉料动画 Blender 候选构建器。

本脚本只在隔离 work 目录内生成 Blender 候选、渲染证据和机器报告。
不导出、不替换、不触碰正式 GLB。
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
STAGE = ROOT / "PT" / "高炉3D模型" / "work" / "INT_30_20260719_R2L_BURDEN_ANIMATION_PROTOTYPE"
SCRIPTS = STAGE / "scripts"
BLENDS = STAGE / "blends"
RENDERS = STAGE / "renders"
REPORTS = STAGE / "reports"
LOGS = STAGE / "logs"

INPUT_BLEND = ROOT / "PT" / "高炉3D模型" / "work" / "INT_30_20260719_R2J_FIVE_ZONE_SHELL_ENTITY_ROLLOUT" / "blends" / "INT_30_R2J_R4_FIVE_ZONE_SHELL_ENTITY_ROLLOUT_CANDIDATE.blend"
INPUT_SHA256 = "72e76ace4817fe26e947833a8ff9b1df3226c260b58ecf85ac03c61fa3c32cc4"
FORMAL_GLB = ROOT / "高炉前端数据" / "models" / "gl02_blast_furnace.glb"
FORMAL_GLB_SHA256 = "808960f1b2703e7fb27df35f1b1b1a17063b9b10d2267acba593fc3872b62af6"
BLENDER = Path(r"D:\Program Files\Blender Foundation\Blender 5.2\blender.exe")
R1_NODE_GRAPH_HASH = "6bf8bd2fcf7712081d1ad2620c3133a984ada8c9b3927b59aa86131ba3b134a6"

BUILD_SCRIPT = SCRIPTS / "r2l_build_burden_animation.py"
REOPEN_SCRIPT = SCRIPTS / "r2l_reopen_validate.py"
CANDIDATE_BLEND = BLENDS / "INT_30_R2L_BURDEN_ANIMATION_PROTOTYPE_CANDIDATE.blend"


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def ensure_dirs() -> None:
    for p in (STAGE, SCRIPTS, BLENDS, RENDERS, REPORTS, LOGS, RENDERS / "preview_seq"):
        p.mkdir(parents=True, exist_ok=True)


def write_file(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def run(cmd: list[str], log_name: str, timeout: int = 1800) -> None:
    log_path = LOGS / log_name
    with log_path.open("w", encoding="utf-8", errors="replace") as log:
        proc = subprocess.run(
            cmd,
            cwd=str(ROOT),
            text=True,
            stdout=log,
            stderr=subprocess.STDOUT,
            timeout=timeout,
        )
    if proc.returncode != 0:
        raise SystemExit(f"Command failed ({proc.returncode}); see {log_path}")


BLENDER_BUILD = r'''
import argparse
import hashlib
import json
import math
import os
import random
from pathlib import Path

import bpy
import bmesh
from mathutils import Euler, Vector


META_COMMON = {
    "evidenceLevel": "E",
    "evidence": "illustrative",
    "evidence_level": "illustrative",
    "claim_label": "E/illustrative",
    "scenario_id": "E_BURDEN_LOOP_V1",
    "dataMode": "ILLUSTRATIVE_LOOP",
    "notForConstruction": True,
    "dataQuality": "missing",
    "seed": 20260719,
    "forbiddenClaims": (
        "not realtime; not measured stockline; not measured layer thickness; "
        "not measured particle size; not measured chute trajectory; "
        "not heat-batch attribution; not DEM/CFD"
    ),
}

R1_MATERIAL = "SURF20_R5_aged_painted_carbon_steel_shared_world"
R1_NODE_GRAPH_HASH = "6bf8bd2fcf7712081d1ad2620c3133a984ada8c9b3927b59aa86131ba3b134a6"
SOURCE_R2J_SHA256 = "72e76ace4817fe26e947833a8ff9b1df3226c260b58ecf85ac03c61fa3c32cc4"

TIMELINE = [
    {"name": "下降A", "start": 1, "end": 96, "claim": "示意料柱下降，不由L/L_south/L_north驱动"},
    {"name": "焦批落料/溜槽360", "start": 97, "end": 192, "claim": "焦批落料事件示意，workdate/workdate2未确认为入炉瞬间"},
    {"name": "焦批沉降", "start": 193, "end": 240, "claim": "焦炭层沉降示意，层厚归一化"},
    {"name": "下降B", "start": 241, "end": 336, "claim": "示意料柱下降，不由质量平衡驱动"},
    {"name": "矿批落料/错180再360", "start": 337, "end": 432, "claim": "矿批落料事件示意，通道量不当作化学成分"},
    {"name": "矿批沉降", "start": 433, "end": 480, "claim": "矿石层沉降示意，粒径/堆密度未校准"},
    {"name": "审计静止", "start": 481, "end": 552, "claim": "给审核员检查对象、材质和标签"},
    {"name": "遮罩内重排/循环闭合", "start": 553, "end": 576, "claim": "F576与F1视觉同态，避免循环跳变"},
]


def parse_args():
    import sys
    parser = argparse.ArgumentParser()
    parser.add_argument("--stage", required=True)
    parser.add_argument("--candidate", required=True)
    parser.add_argument("--formal-glb", required=True)
    parser.add_argument("--formal-glb-sha", required=True)
    parser.add_argument("--review-keyframes-only", action="store_true")
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else None
    return parser.parse_args(argv)


def file_sha(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def set_custom(obj, **kw):
    data = dict(META_COMMON)
    data.update(kw)
    for k, v in data.items():
        obj[k] = v


def make_collection(name, parent=None):
    col = bpy.data.collections.get(name)
    if col is None:
        col = bpy.data.collections.new(name)
    if parent is None:
        if col.name not in [c.name for c in bpy.context.scene.collection.children]:
            try:
                bpy.context.scene.collection.children.link(col)
            except RuntimeError:
                pass
    else:
        if col.name not in [c.name for c in parent.children]:
            try:
                parent.children.link(col)
            except RuntimeError:
                pass
    return col


def link_to(obj, col):
    for c in obj.users_collection:
        c.objects.unlink(obj)
    col.objects.link(obj)


def material(name, color, roughness=0.85, metallic=0.0, alpha=1.0):
    mat = bpy.data.materials.new(name)
    mat.diffuse_color = color
    mat.use_nodes = True
    mat.blend_method = "BLEND" if alpha < 1.0 else "OPAQUE"
    if hasattr(mat, "use_screen_refraction"):
        mat.use_screen_refraction = False
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
    links.new(bsdf.outputs["BSDF"], out.inputs["Surface"])
    return mat


def mesh_hash(obj):
    me = obj.data
    payload = []
    for v in me.vertices:
        payload.append((round(v.co.x, 5), round(v.co.y, 5), round(v.co.z, 5)))
    for p in me.polygons:
        payload.append(tuple(p.vertices))
    return hashlib.sha256(repr(payload).encode("utf-8")).hexdigest()


def visible_state_signature(scene, objects, frame):
    scene.frame_set(frame)
    rows = []
    for obj in sorted(objects, key=lambda item: item.name):
        if obj.hide_render:
            continue
        rows.append({
            "name": obj.name,
            "type": obj.type,
            "matrix_world": [round(float(v), 7) for row in obj.matrix_world for v in row],
            "data": obj.data.name if obj.data is not None else None,
        })
    payload = json.dumps(rows, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return {
        "frame": frame,
        "visible_object_count": len(rows),
        "sha256": hashlib.sha256(payload.encode("utf-8")).hexdigest(),
    }


def material_graph_hash(prefixes=("R1", "ROUGH", "SHELL", "FURNACE"), locked_names=None):
    rows = []
    for mat in bpy.data.materials:
        if locked_names is not None and mat.name not in locked_names:
            continue
        n = mat.name.upper()
        if not any(p in n for p in prefixes):
            continue
        rows.append([mat.name, tuple(round(x, 6) for x in mat.diffuse_color)])
        if mat.use_nodes and mat.node_tree:
            for node in mat.node_tree.nodes:
                vals = []
                for inp in node.inputs:
                    dv = getattr(inp, "default_value", None)
                    if isinstance(dv, (float, int, bool, str)):
                        vals.append((inp.name, dv))
                    elif hasattr(dv, "__iter__"):
                        try:
                            vals.append((inp.name, tuple(round(float(x), 6) for x in dv)))
                        except Exception:
                            pass
                rows.append([mat.name, node.name, node.bl_idname, vals])
    return hashlib.sha256(json.dumps(rows, ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest()


def serializable_socket_value(value):
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


def controlled_r1_node_graph(material):
    """Exact R2F/R2D canonical serialization for VB-DEC-MAT-001."""
    if material is None or not material.use_nodes or material.node_tree is None:
        return {"material": material.name if material else None, "hash": None}
    nodes = []
    for node in sorted(material.node_tree.nodes, key=lambda item: item.name):
        inputs = {}
        for socket in node.inputs:
            if node.bl_idname == "ShaderNodeMapping" and socket.name != "Vector":
                continue
            if not hasattr(socket, "default_value"):
                continue
            value = serializable_socket_value(socket.default_value)
            if value is not None:
                inputs[socket.name] = value
        nodes.append({
            "name": node.name,
            "bl_idname": node.bl_idname,
            "label": node.label,
            "inputs": inputs,
            "object": node.object.name if hasattr(node, "object") and node.object is not None else None,
        })
    links = sorted(
        [{
            "from": f"{link.from_node.name}.{link.from_socket.name}",
            "to": f"{link.to_node.name}.{link.to_socket.name}",
        } for link in material.node_tree.links],
        key=lambda item: (item["from"], item["to"]),
    )
    payload = {"nodes": nodes, "links": links}
    return {
        "material": material.name,
        "hash": hashlib.sha256(
            json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest(),
        "node_count": len(nodes),
        "link_count": len(links),
    }


def edge_nonmanifold_and_volume(obj):
    bm = bmesh.new()
    bm.from_mesh(obj.data)
    bm.verts.ensure_lookup_table()
    bm.edges.ensure_lookup_table()
    bm.faces.ensure_lookup_table()
    nonmanifold = sum(1 for e in bm.edges if len(e.link_faces) != 2)
    volume = abs(bm.calc_volume())
    bm.free()
    return nonmanifold, volume


def burden_radius(z):
    # E级解释性内腔半径，不用于工程尺寸。
    if z < 10:
        return 1.72 + (z - 7.0) * 0.10
    if z < 16:
        return 2.02 + (z - 10.0) * 0.055
    if z < 22:
        return 2.35 - (z - 16.0) * 0.085
    return 1.84


def make_irregular_disc(name, z0, z1, role, mat, col, seed, segments=96):
    rnd = random.Random(seed)
    verts = []
    top = []
    bottom = []
    rbase0 = burden_radius(z0)
    rbase1 = burden_radius(z1)
    phase = rnd.random() * math.tau
    amp = 0.055 if role == "ORE" else 0.075
    for i in range(segments):
        a = math.tau * i / segments
        radial_noise = (
            0.045 * math.sin(5 * a + phase)
            + 0.025 * math.sin(11 * a + phase * 0.7)
            + rnd.uniform(-0.018, 0.018)
        )
        rt = max(0.5, rbase1 + radial_noise)
        rb = max(0.5, rbase0 + radial_noise * 0.65)
        top_z = z1 + amp * math.sin(3 * a + phase) + 0.025 * math.sin(9 * a)
        bot_z = z0 + 0.020 * math.sin(4 * a + phase * 1.3)
        top.append(len(verts)); verts.append((rt * math.cos(a), rt * math.sin(a), top_z))
        bottom.append(len(verts)); verts.append((rb * math.cos(a), rb * math.sin(a), bot_z))
    top_center = len(verts); verts.append((0, 0, z1 + 0.02))
    bottom_center = len(verts); verts.append((0, 0, z0 - 0.01))
    faces = []
    for i in range(segments):
        j = (i + 1) % segments
        faces.append((bottom[i], bottom[j], top[j], top[i]))
        faces.append((top_center, top[i], top[j]))
        faces.append((bottom_center, bottom[j], bottom[i]))
    mesh = bpy.data.meshes.new(name + "_MESH")
    mesh.from_pydata(verts, [], faces)
    mesh.update(calc_edges=True)
    obj = bpy.data.objects.new(name, mesh)
    obj.data.materials.append(mat)
    link_to(obj, col)
    set_custom(obj, assetId=name, batchRole=role, layerSemantic="alternating_ore_coke_e_grade", sourceContract="no_L_no_density_no_chute_matrix")
    return obj


def make_rock_mesh(name, role):
    rnd = random.Random(1001 if role == "COKE" else 2002)
    verts = []
    faces = []
    # Low-poly distorted octahedron.
    base = [(1,0,0),(-1,0,0),(0,1,0),(0,-1,0),(0,0,1),(0,0,-1)]
    for x, y, z in base:
        s = 1.0 + rnd.uniform(-0.25, 0.28)
        verts.append((x*s, y*s, z*s))
    faces += [(4,0,2),(4,2,1),(4,1,3),(4,3,0),(5,2,0),(5,1,2),(5,3,1),(5,0,3)]
    mesh = bpy.data.meshes.new(name)
    mesh.from_pydata(verts, [], faces)
    mesh.update(calc_edges=True)
    return mesh


def add_particles(prefix, role, mat, col, start, end, angle_offset):
    rnd = random.Random(7300 + (0 if role == "COKE" else 500))
    count = 64 if role == "COKE" else 72
    verts = []
    target_verts = []
    settled_verts = []
    faces = []
    base = [(1,0,0),(-1,0,0),(0,1,0),(0,-1,0),(0,0,1),(0,0,-1)]
    base_faces = [(4,0,2),(4,2,1),(4,1,3),(4,3,0),(5,2,0),(5,1,2),(5,3,1),(5,0,3)]
    for i in range(count):
        a0 = angle_offset + math.tau * (i / count) * 0.85 + rnd.uniform(-0.18, 0.18)
        r0 = rnd.uniform(0.35, 1.15)
        a1 = angle_offset + math.tau * (i / count) + rnd.uniform(-0.28, 0.28)
        r1 = rnd.uniform(0.25, 1.95)
        z_top = rnd.uniform(23.8, 25.2)
        z_bottom = rnd.uniform(17.35, 18.00)
        sc = rnd.uniform(0.18, 0.34) if role == "COKE" else rnd.uniform(0.14, 0.27)
        scale = Vector((
            sc * rnd.uniform(0.7, 1.5),
            sc * rnd.uniform(0.65, 1.35),
            sc * rnd.uniform(0.6, 1.2),
        ))
        rotation = Euler((rnd.random() * math.tau, rnd.random() * math.tau, rnd.random() * math.tau))
        start_center = Vector((r0 * math.cos(a0), r0 * math.sin(a0), z_top))
        target_center = Vector((r1 * math.cos(a1), r1 * math.sin(a1), z_bottom))
        settle_center = Vector((
            (r1 * 0.92) * math.cos(a1 + rnd.uniform(-0.06, 0.06)),
            (r1 * 0.92) * math.sin(a1 + rnd.uniform(-0.06, 0.06)),
            rnd.uniform(17.25, 17.58),
        ))
        offset = len(verts)
        for local in base:
            p = Vector(local)
            p.x *= scale.x * rnd.uniform(0.82, 1.18)
            p.y *= scale.y * rnd.uniform(0.82, 1.18)
            p.z *= scale.z * rnd.uniform(0.82, 1.18)
            p.rotate(rotation)
            verts.append(tuple(start_center + p))
            target_verts.append(tuple(target_center + p))
            settled_verts.append(tuple(settle_center + p * rnd.uniform(0.56, 0.72)))
        faces.extend(tuple(offset + index for index in face) for face in base_faces)

    mesh = bpy.data.meshes.new(prefix + "_POOL_MESH")
    mesh.from_pydata(verts, [], faces)
    mesh.materials.append(mat)
    mesh.update(calc_edges=True)
    obj = bpy.data.objects.new(prefix + "_MORPH_POOL_E", mesh)
    link_to(obj, col)
    basis = obj.shape_key_add(name="Basis")
    target_key = obj.shape_key_add(name="FALL_TARGET")
    settle_key = obj.shape_key_add(name="SETTLE_TARGET")
    for index, co in enumerate(target_verts):
        target_key.data[index].co = co
    for index, co in enumerate(settled_verts):
        settle_key.data[index].co = co
    target_key.value = 0.0
    target_key.keyframe_insert("value", frame=start)
    impact_frame = max(start + 12, end - 48)
    target_key.value = 1.0
    target_key.keyframe_insert("value", frame=impact_frame)
    target_key.keyframe_insert("value", frame=end)
    settle_key.value = 0.0
    settle_key.keyframe_insert("value", frame=impact_frame)
    settle_key.value = 1.0
    settle_end = min(end + 16, 575)
    settle_key.keyframe_insert("value", frame=settle_end)
    for f, visible in (
        (1, False),
        (start - 1, False),
        (start, True),
        (settle_end, True),
        (settle_end + 1, False),
        (576, False),
    ):
        set_visibility(obj, f, visible)
    set_custom(
        obj,
        assetId=obj.name,
        batchRole=role,
        particleProxy=True,
        particlePool=True,
        particleCount=count,
        poolImplementation="single_mesh_morph_pool",
        eventFrameStart=start,
        eventFrameEnd=end,
        sourceContract="MES_event_time_unverified_visual_proxy",
    )
    return [obj]


def set_visibility(obj, frame, visible):
    obj.hide_viewport = not visible
    obj.hide_render = not visible
    obj.keyframe_insert("hide_viewport", frame=frame)
    obj.keyframe_insert("hide_render", frame=frame)


def create_falling_streams(prefix, role, mat, col, start, end, angle_offset):
    # R2 的贯穿全高曲线看起来像管线/面条。R3 仅保留共享低模块粒，
    # 不再用连续曲线冒充块料流；参数保留用于稳定调用合同。
    return []


def add_camera(name, loc, rot_deg, lens, col):
    cam_data = bpy.data.cameras.new(name + "_DATA")
    cam_data.lens = lens
    obj = bpy.data.objects.new(name, cam_data)
    obj.location = loc
    obj.rotation_euler = tuple(math.radians(x) for x in rot_deg)
    link_to(obj, col)
    set_custom(obj, assetId=name, batchRole="RENDER_CAMERA", renderOnly=True, sourceContract="lookdev_evidence_camera")
    return obj


def create_text(name, text, loc, size, mat, col):
    curve = bpy.data.curves.new(name + "_CURVE", "FONT")
    curve.body = text
    curve.align_x = "LEFT"
    curve.align_y = "CENTER"
    curve.size = size
    obj = bpy.data.objects.new(name, curve)
    obj.location = loc
    obj.rotation_euler = (math.radians(70), 0, math.radians(0))
    obj.data.materials.append(mat)
    link_to(obj, col)
    set_custom(obj, assetId=name, batchRole="LABEL", labelPurpose="evidence_disclaimer")
    return obj


def create_arc_curve(name, z, radius, start_deg, end_deg, mat, col, bevel=0.025, steps=72):
    curve = bpy.data.curves.new(name + "_CURVE", "CURVE")
    curve.dimensions = "3D"
    curve.bevel_depth = bevel
    curve.resolution_u = 2
    spl = curve.splines.new("POLY")
    spl.points.add(steps)
    for i in range(steps + 1):
        t = i / steps
        a = math.radians(start_deg + (end_deg - start_deg) * t)
        spl.points[i].co = (radius * math.cos(a), radius * math.sin(a), z, 1.0)
    obj = bpy.data.objects.new(name, curve)
    obj.data.materials.append(mat)
    link_to(obj, col)
    set_custom(obj, assetId=name, batchRole="OPEN_SHELL_CONTEXT", renderOnly=True, sourceContract="R2L_240_degree_back_shell_frame_with_120_degree_front_opening")
    return obj


def main():
    args = parse_args()
    source_blend_path = Path(bpy.data.filepath)
    source_blend_sha256 = file_sha(source_blend_path)
    if source_blend_sha256 != SOURCE_R2J_SHA256:
        raise RuntimeError(
            f"R2J source SHA mismatch inside Blender: "
            f"{source_blend_sha256} != {SOURCE_R2J_SHA256}"
        )
    stage = Path(args.stage)
    renders = stage / "renders"
    reports = stage / "reports"
    candidate = Path(args.candidate)
    reports.mkdir(parents=True, exist_ok=True)
    renders.mkdir(parents=True, exist_ok=True)
    (renders / "preview_seq").mkdir(parents=True, exist_ok=True)

    bpy.context.preferences.filepaths.save_version = 0
    scene = bpy.context.scene
    scene.frame_start = 1
    scene.frame_end = 576
    scene.frame_current = 1
    scene.render.fps = 24
    scene.render.resolution_x = 1280
    scene.render.resolution_y = 720
    scene.render.film_transparent = False
    if hasattr(scene, "eevee") and hasattr(scene.eevee, "taa_render_samples"):
        scene.eevee.taa_render_samples = 16
    try:
        scene.render.engine = "BLENDER_EEVEE_NEXT"
    except Exception:
        scene.render.engine = "BLENDER_EEVEE"

    locked_material_names = [
        mat.name for mat in bpy.data.materials
        if any(p in mat.name.upper() for p in ("R1", "ROUGH", "SHELL", "FURNACE"))
    ]
    before_material_hash = material_graph_hash(locked_names=locked_material_names)
    r1_controlled_before = controlled_r1_node_graph(bpy.data.materials.get(R1_MATERIAL))
    if r1_controlled_before.get("hash") != R1_NODE_GRAPH_HASH:
        raise RuntimeError(
            f"R1 canonical node graph mismatch before build: "
            f"{r1_controlled_before.get('hash')} != {R1_NODE_GRAPH_HASH}"
        )
    before_counts = {
        "objects": len(bpy.data.objects),
        "sensors": len([o for o in bpy.data.objects if o.name.startswith("SENSOR_")]),
        "body_temperature_sensors": len([o for o in bpy.data.objects if o.name.startswith("SENSOR_T_body_L")]),
        "pressure_points": len([o for o in bpy.data.objects if o.name.startswith("GL02_INT30_PRESSURE_")]),
        "temperature_layer_bands": len([o for o in bpy.data.objects if o.name.startswith("APPROX_GL02_TEMP_LAYER_BAND_L")]),
        "l7_l16_counts": {f"L{i}": len([o for o in bpy.data.objects if o.name.startswith(f"SENSOR_T_body_L{i}_")]) for i in range(7, 17)},
    }

    root = make_collection("BF3D_R2L_BURDEN_SYSTEM")
    cols = {name: make_collection(name, root) for name in ["BURDEN_SURFACE", "BURDEN_COKE", "BURDEN_ORE", "TOP_CHARGING", "RENDER_ONLY_AUX"]}

    old_hidden = []
    for obj in bpy.data.objects:
        lname = obj.name.lower()
        if (
            "burden_column_layered_charge" in lname
            or "internal_burden_reference_bands" in lname
            or "cohesive_zone" in lname
            or "countercurrent_gas_flow_streamlines" in lname
        ):
            obj.hide_viewport = True
            obj.hide_render = True
            old_hidden.append(obj.name)

    render_occluders_hidden = []
    render_cutaway_context_enabled = []
    for obj in bpy.data.objects:
        n = obj.name
        if (
            n.startswith("APPROX_GL02_FURNACE_")
            or n.startswith("R2J_ASM_GL02_FURNACE_")
            or n.startswith("R2J_SOLO_GL02_FURNACE_")
            or n.startswith("APPROX_GL02_INT10_")
            or n.startswith("APPROX_GL02_INT20_")
            or n.startswith("R2I_")
        ):
            obj.hide_render = True
            render_occluders_hidden.append(n)

    # Evidence images must be readable: hide every legacy/non-R2L object in render.
    # Counts, data, transforms and materials remain untouched.
    for obj in bpy.data.objects:
        if not obj.name.startswith("R2L_"):
            obj.hide_render = True

    mat_coke = material("R2L_MAT_COKE_DEEP_GRAY_POROUS_E", (0.115, 0.108, 0.096, 1), 0.84, 0.0)
    mat_ore = material("R2L_MAT_ORE_RED_BROWN_ROUGH_E", (0.30, 0.12, 0.055, 1), 0.88, 0.0)
    mat_fines = material("R2L_MAT_BURDEN_DUST_FINE_E", (0.30, 0.245, 0.18, 1), 0.96, 0.0)
    mat_chute = material("R2L_MAT_CHUTE_AUDIT_WARM_DARK_METAL_E", (0.42, 0.32, 0.22, 1), 0.64, 0.22)
    mat_coke_stream = material("R2L_MAT_COKE_FALLING_STREAM_VISIBLE_E", (0.13, 0.12, 0.105, 1), 0.9, 0.0)
    mat_ore_stream = material("R2L_MAT_ORE_FALLING_STREAM_VISIBLE_E", (0.38, 0.14, 0.06, 1), 0.86, 0.0)
    mat_label = material("R2L_MAT_LABEL_WHITE_E", (0.88, 0.93, 0.92, 1), 0.7, 0.0)
    mat_mask = material("R2L_MAT_LOOP_RESET_MASK_BLUEGRAY_E", (0.12, 0.18, 0.22, 0.46), 0.9, 0.0, 0.46)
    mat_outline = material("R2L_MAT_CUTAWAY_CONTEXT_DARK_AMBER_E", (0.36, 0.24, 0.13, 0.82), 0.72, 0.08, 0.82)

    # Ten alternating compact layer solids inside the process void.
    layers = []
    z = 8.0
    for idx in range(10):
        role = "COKE" if idx % 2 == 0 else "ORE"
        thick = 0.90 if role == "COKE" else 0.78
        name = f"R2L_BURDEN_{idx+1:02d}_{role}_IRREGULAR_LAYER_E"
        layer = make_irregular_disc(name, z, z + thick, role, mat_coke if role == "COKE" else mat_ore, cols["BURDEN_COKE" if role == "COKE" else "BURDEN_ORE"], 20260719 + idx)
        layer.keyframe_insert("location", frame=1)
        layer.location.z = -0.72
        layer.keyframe_insert("location", frame=96)
        layer.keyframe_insert("location", frame=240)
        layer.location.z = -1.42
        layer.keyframe_insert("location", frame=336)
        layer.keyframe_insert("location", frame=552)
        layer.location.z = 0.0
        layer.keyframe_insert("location", frame=576)
        layers.append(layer)
        z += thick + 0.08

    surface = make_irregular_disc("R2L_BURDEN_SURFACE_ASYMMETRIC_SHALLOW_DEPRESSION_E", 17.15, 17.35, "SURFACE", mat_fines, cols["BURDEN_SURFACE"], 20260719 + 300, segments=112)
    surface.scale.z = 1.0
    surface.keyframe_insert("location", frame=1)
    surface.location.z = -0.72
    surface.keyframe_insert("location", frame=96)
    surface.keyframe_insert("location", frame=240)
    surface.location.z = -1.42
    surface.keyframe_insert("location", frame=336)
    surface.keyframe_insert("location", frame=552)
    surface.location.z = 0.0
    surface.keyframe_insert("location", frame=576)
    set_custom(surface, assetId=surface.name, batchRole="SURFACE", sourceContract="main_L_stockline_not_calibrated_disabled")

    # Settling caps: visible only during event settlement, not present at loop endpoints.
    coke_cap = make_irregular_disc("R2L_SETTLED_COKE_CAP_VISIBLE_F193_F240_E", 17.35, 17.82, "COKE", mat_coke, cols["BURDEN_COKE"], 20260719 + 500)
    ore_cap = make_irregular_disc("R2L_SETTLED_ORE_CAP_VISIBLE_F433_F480_E", 17.25, 17.66, "ORE", mat_ore, cols["BURDEN_ORE"], 20260719 + 600)
    for obj, a, b in ((coke_cap, 193, 240), (ore_cap, 433, 480)):
        for f, visible in ((1, False), (a-1, False), (a, True), (b, True), (b+1, False), (576, False)):
            set_visibility(obj, f, visible)
        obj.scale = (0.78, 0.78, 0.12); obj.keyframe_insert("scale", frame=a)
        obj.location = (0.12, -0.08, 0.10); obj.keyframe_insert("location", frame=a)
        obj.scale = (1.08, 1.03, 0.82); obj.keyframe_insert("scale", frame=a + 12)
        obj.location = (-0.06, 0.04, 0.04); obj.keyframe_insert("location", frame=a + 12)
        obj.scale = (1.0, 1.0, 1.0); obj.keyframe_insert("scale", frame=b)
        obj.location = (0.0, 0.0, 0.0); obj.keyframe_insert("location", frame=b)

    coke_particles = add_particles("R2L_CHARGING_COKE_CHUNK", "COKE", mat_coke, cols["TOP_CHARGING"], 97, 192, 0.0)
    ore_particles = add_particles("R2L_CHARGING_ORE_CHUNK", "ORE", mat_ore, cols["TOP_CHARGING"], 337, 432, math.pi)
    coke_streams = create_falling_streams("R2L_CHARGING_COKE_FALL_STREAM", "COKE", mat_coke_stream, cols["TOP_CHARGING"], 97, 192, math.radians(-90))
    ore_streams = create_falling_streams("R2L_CHARGING_ORE_FALL_STREAM", "ORE", mat_ore_stream, cols["TOP_CHARGING"], 337, 432, math.radians(-90))

    # Chute indicator.
    bpy.ops.mesh.primitive_cone_add(vertices=6, radius1=0.18, radius2=0.05, depth=2.8, location=(0, 0, 24.0), rotation=(math.radians(72), 0, 0))
    chute = bpy.context.object
    chute.name = "R2L_TOP_ROTATING_CHUTE_PATH_INDICATOR_E"
    chute.data.name = chute.name + "_MESH"
    chute.data.materials.append(mat_chute)
    link_to(chute, cols["TOP_CHARGING"])
    set_custom(chute, assetId=chute.name, batchRole="CHUTE_PATH_INDICATOR", sourceContract="no_real_chute_angle_matrix")
    for f, rz, vis in ((1, 0, False), (96, 0, False), (97, 0, True), (192, 360, True), (193, 360, False), (336, 180, False), (337, 180, True), (432, 540, True), (433, 540, False), (576, 0, False)):
        chute.rotation_euler.z = math.radians(rz)
        chute.hide_viewport = not vis
        chute.hide_render = not vis
        chute.keyframe_insert("rotation_euler", frame=f)
        chute.keyframe_insert("hide_viewport", frame=f)
        chute.keyframe_insert("hide_render", frame=f)

    # Reset mask communicates that the last segment is a loop closure, not physical transport.
    bpy.ops.mesh.primitive_cube_add(size=1, location=(0, -2.85, 17.2))
    mask = bpy.context.object
    mask.name = "R2L_RENDER_ONLY_LOOP_RESET_MASK_F553_F576_E"
    mask.scale = (2.9, 0.04, 5.4)
    mask.data.materials.append(mat_mask)
    link_to(mask, cols["RENDER_ONLY_AUX"])
    set_custom(mask, assetId=mask.name, batchRole="LOOP_RESET_MASK", sourceContract="render_only_loop_closure_disclaimer")
    for f, vis in ((1, False), (552, False), (553, True), (575, True), (576, False)):
        set_visibility(mask, f, vis)

    disclaimer = create_text(
        "R2L_EVIDENCE_DISCLAIMER_LABEL_E",
        "R2L 炉料动画：E/illustrative\\n非实时/非实测料线/非真实布料轨迹\\nworkdate与料线语义待现场对表",
        (-4.6, -3.2, 22.4),
        0.26,
        mat_label,
        cols["RENDER_ONLY_AUX"],
    )
    disclaimer.hide_render = True
    for f in (1, 576):
        disclaimer.keyframe_insert("location", frame=f)

    # Low-occlusion render-only silhouette to keep furnace context after hiding full shells.
    for idx, zc in enumerate([8.0, 10.5, 13.0, 15.5, 18.0, 20.5, 23.0]):
        # Main camera is at -Y; leave a 120 degree front opening from -150 to -30 degrees.
        ring = create_arc_curve(
            f"R2L_RENDER_ONLY_OPEN_SHELL_RING_{idx:02d}_E",
            zc,
            burden_radius(zc) + 0.32,
            -30,
            210,
            mat_outline,
            cols["RENDER_ONLY_AUX"],
            bevel=0.026,
        )
        render_cutaway_context_enabled.append(ring.name)
    for idx, a in enumerate([math.radians(28), math.radians(152), math.radians(268)]):
        zmid = 15.5
        r = burden_radius(zmid) + 0.22
        bpy.ops.mesh.primitive_cube_add(size=1, location=(r * math.cos(a), r * math.sin(a), zmid))
        rod = bpy.context.object
        rod.name = f"R2L_RENDER_ONLY_CUTAWAY_CONTEXT_VERTICAL_{idx:02d}_E"
        rod.dimensions = (0.045, 0.045, 15.2)
        rod.rotation_euler.z = a
        rod.data.materials.append(mat_outline)
        link_to(rod, cols["RENDER_ONLY_AUX"])
        set_custom(rod, assetId=rod.name, batchRole="CUTAWAY_CONTEXT", renderOnly=True, sourceContract="new_low_occlusion_context_not_measured_shell")
        render_cutaway_context_enabled.append(rod.name)

    # Camera and lights.
    bpy.ops.object.light_add(type="AREA", location=(-4.0, -6.0, 27.0))
    key = bpy.context.object
    key.name = "R2L_RENDER_ONLY_WARM_SOFTBOX_E"
    key.data.energy = 550
    key.data.size = 5.0
    link_to(key, cols["RENDER_ONLY_AUX"])
    set_custom(key, assetId=key.name, batchRole="RENDER_LIGHT", renderOnly=True, sourceContract="lookdev_evidence_light")
    bpy.ops.object.light_add(type="POINT", location=(3.0, 4.0, 21.0))
    rim = bpy.context.object
    rim.name = "R2L_RENDER_ONLY_COOL_RIM_E"
    rim.data.energy = 110
    link_to(rim, cols["RENDER_ONLY_AUX"])
    set_custom(rim, assetId=rim.name, batchRole="RENDER_LIGHT", renderOnly=True, sourceContract="lookdev_evidence_light")
    def look_at(obj, target):
        direction = Vector(target) - obj.location
        obj.rotation_euler = direction.to_track_quat("-Z", "Y").to_euler()

    cam_main = add_camera("R2L_CAMERA_MAIN_CUTAWAY_VIEW_E", (6.0, -12.0, 17.0), (62, 0, 42), 48, cols["RENDER_ONLY_AUX"])
    cam_main.data.type = "ORTHO"
    cam_main.data.ortho_scale = 21.0
    look_at(cam_main, (0.0, 0.0, 17.0))
    cam_top = add_camera("R2L_CAMERA_TOP_F144_E", (0.0, -0.2, 31.0), (0, 0, 0), 45, cols["RENDER_ONLY_AUX"])
    cam_top.data.type = "ORTHO"
    cam_top.data.ortho_scale = 6.4
    cam_top.rotation_euler = (0, 0, 0)
    look_at(cam_top, (0, 0, 18.0))
    cam_close = add_camera("R2L_CAMERA_MATERIAL_CLOSEUP_E", (3.25, -3.15, 15.8), (72, 0, 35), 80, cols["RENDER_ONLY_AUX"])
    cam_close.data.type = "ORTHO"
    cam_close.data.ortho_scale = 3.0
    look_at(cam_close, (1.15, -0.45, 14.8))
    scene.camera = cam_main

    # Markers.
    for item in TIMELINE:
        scene.timeline_markers.new(item["name"], frame=item["start"])

    after_material_hash = material_graph_hash(locked_names=locked_material_names)
    if before_material_hash != after_material_hash:
        raise RuntimeError("R1/shell material graph hash changed; aborting R2L")
    r1_controlled_after = controlled_r1_node_graph(bpy.data.materials.get(R1_MATERIAL))
    if r1_controlled_after.get("hash") != R1_NODE_GRAPH_HASH:
        raise RuntimeError(
            f"R1 canonical node graph mismatch after build: "
            f"{r1_controlled_after.get('hash')} != {R1_NODE_GRAPH_HASH}"
        )

    geometry_checks = []
    for obj in layers + [surface, coke_cap, ore_cap] + coke_particles + ore_particles:
        nonmanifold, volume = edge_nonmanifold_and_volume(obj)
        geometry_checks.append({"name": obj.name, "nonmanifold_edges": nonmanifold, "volume": volume, "mesh_hash": mesh_hash(obj)})
        if nonmanifold != 0 or volume <= 0:
            raise RuntimeError(f"Invalid burden solid {obj.name}: nonmanifold={nonmanifold} volume={volume}")

    r2l_objects_for_loop = [o for o in bpy.data.objects if o.name.startswith("R2L_")]
    loop_visible_f1 = visible_state_signature(scene, r2l_objects_for_loop, 1)
    loop_visible_f576 = visible_state_signature(scene, r2l_objects_for_loop, 576)
    loop_visible_state_ok = loop_visible_f1["sha256"] == loop_visible_f576["sha256"]
    if not loop_visible_state_ok:
        raise RuntimeError(
            f"F1/F576 visible-state mismatch: "
            f"{loop_visible_f1['sha256']} != {loop_visible_f576['sha256']}"
        )

    bpy.ops.wm.save_as_mainfile(filepath=str(candidate))

    # Render proof frames.
    proof_frames = [1, 144, 216, 384, 432, 576]
    render_records = []
    scene.camera = cam_main
    for f in proof_frames:
        scene.frame_set(f)
        scene.render.filepath = str(renders / f"R2L_FRAME_{f:04d}_MAIN.png")
        bpy.ops.render.render(write_still=True)
        render_records.append({"frame": f, "camera": cam_main.name, "path": scene.render.filepath})
    scene.camera = cam_top
    scene.frame_set(144)
    scene.render.filepath = str(renders / "R2L_FRAME_0144_TOP.png")
    bpy.ops.render.render(write_still=True)
    render_records.append({"frame": 144, "camera": cam_top.name, "path": scene.render.filepath})
    scene.camera = cam_close
    scene.frame_set(216)
    scene.render.filepath = str(renders / "R2L_FRAME_0216_MATERIAL_CLOSEUP.png")
    bpy.ops.render.render(write_still=True)
    render_records.append({"frame": 216, "camera": cam_close.name, "path": scene.render.filepath})

    # Short stepped preview sequence: every 12 timeline frames, 48 images.
    scene.camera = cam_main
    for f in range(1, 577, 12):
        scene.frame_set(f)
        scene.render.filepath = str(renders / "preview_seq" / f"R2L_PREVIEW_{f:04d}.png")
        bpy.ops.render.render(write_still=True)

    after_counts = {
        "objects": len(bpy.data.objects),
        "sensors": len([o for o in bpy.data.objects if o.name.startswith("SENSOR_")]),
        "body_temperature_sensors": len([o for o in bpy.data.objects if o.name.startswith("SENSOR_T_body_L")]),
        "pressure_points": len([o for o in bpy.data.objects if o.name.startswith("GL02_INT30_PRESSURE_")]),
        "temperature_layer_bands": len([o for o in bpy.data.objects if o.name.startswith("APPROX_GL02_TEMP_LAYER_BAND_L")]),
        "l7_l16_counts": {f"L{i}": len([o for o in bpy.data.objects if o.name.startswith(f"SENSOR_T_body_L{i}_")]) for i in range(7, 17)},
    }
    protected_ok = (
        before_counts["sensors"] == after_counts["sensors"] == 115
        and before_counts["body_temperature_sensors"] == after_counts["body_temperature_sensors"] == 80
        and before_counts["pressure_points"] == after_counts["pressure_points"] == 18
        and before_counts["temperature_layer_bands"] == after_counts["temperature_layer_bands"] == 10
        and all(v == 8 for v in after_counts["l7_l16_counts"].values())
    )
    if not protected_ok:
        raise RuntimeError(f"protected contract failed before={before_counts} after={after_counts}")

    new_objects = [o for o in bpy.data.objects if o.name.startswith("R2L_")]
    metadata_fail = [o.name for o in new_objects if o.get("claim_label") != "E/illustrative" or o.get("scenario_id") != "E_BURDEN_LOOP_V1"]
    if metadata_fail:
        raise RuntimeError("metadata failed: " + ", ".join(metadata_fail[:10]))

    formal_hash = file_sha(args.formal_glb)
    if formal_hash.lower() != args.formal_glb_sha.lower():
        raise RuntimeError("formal GLB hash changed")

    report = {
        "schema_version": 1,
        "stage": "INT_30_20260719_R2L_BURDEN_ANIMATION_PROTOTYPE",
        "status": "candidate_built",
        "created_at_utc": __import__("datetime").datetime.now(__import__("datetime").timezone.utc).isoformat(),
        "scenario_id": "E_BURDEN_LOOP_V1",
        "source_blend": str(source_blend_path),
        "source_blend_sha256_expected": SOURCE_R2J_SHA256,
        "source_blend_sha256_actual": source_blend_sha256,
        "source_blend_sha256_ok": source_blend_sha256 == SOURCE_R2J_SHA256,
        "evidence_level": "E/illustrative",
        "data_mode": "ILLUSTRATIVE_LOOP",
        "forbidden_claims": [
            "No live L/L_south/L_north stockline geometry.",
            "No measured layer thickness or mass-balance descent.",
            "No verified actual furnace-top charging instant from workdate/workdate2.",
            "No real chute angle matrix, DEM/CFD or particle-size distribution.",
            "No heat-batch attribution.",
            "value_01..24 are not treated as chemical composition.",
        ],
        "timeline": TIMELINE,
        "frame_rate": 24,
        "frame_start": 1,
        "frame_end": 576,
        "old_internal_illustrative_objects_hidden": old_hidden,
        "render_occluders_hidden": render_occluders_hidden,
        "render_cutaway_context_enabled": render_cutaway_context_enabled,
        "new_object_count": len(new_objects),
        "new_particle_proxy_count": sum(
            int(obj.get("particleCount", 0))
            for obj in coke_particles + ore_particles
        ),
        "new_particle_pool_object_count": len(coke_particles) + len(ore_particles),
        "new_falling_stream_count": len(coke_streams) + len(ore_streams),
        "new_layer_count": len(layers),
        "geometry_checks": geometry_checks,
        "before_counts": before_counts,
        "after_counts": after_counts,
        "protected_contract_ok": protected_ok,
        "r1_material_hash_before": before_material_hash,
        "r1_material_hash_after": after_material_hash,
        "r1_controlled_material": R1_MATERIAL,
        "r1_controlled_node_graph_hash_expected": R1_NODE_GRAPH_HASH,
        "r1_controlled_node_graph_before": r1_controlled_before,
        "r1_controlled_node_graph_after": r1_controlled_after,
        "r1_controlled_node_graph_ok": (
            r1_controlled_before.get("hash") == R1_NODE_GRAPH_HASH
            and r1_controlled_after.get("hash") == R1_NODE_GRAPH_HASH
        ),
        "loop_visible_state_f1": loop_visible_f1,
        "loop_visible_state_f576": loop_visible_f576,
        "loop_visible_state_ok": loop_visible_state_ok,
        "render_records": render_records,
        "preview_sequence": str(renders / "preview_seq"),
        "candidate_blend": str(candidate),
        "candidate_sha256": file_sha(candidate),
        "formal_glb_sha256": formal_hash,
        "formal_glb_unchanged": formal_hash.lower() == args.formal_glb_sha.lower(),
        "blender_version": bpy.app.version_string,
    }
    (reports / "int30_r2l_machine_report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    (reports / "r2l_timeline_contract.json").write_text(json.dumps(TIMELINE, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
'''


BLENDER_REOPEN = r'''
import argparse, json, hashlib
from pathlib import Path
import bpy, bmesh

R1_MATERIAL = "SURF20_R5_aged_painted_carbon_steel_shared_world"
R1_NODE_GRAPH_HASH = "6bf8bd2fcf7712081d1ad2620c3133a984ada8c9b3927b59aa86131ba3b134a6"
EXPECTED_MARKERS = {
    "下降A": 1,
    "焦批落料/溜槽360": 97,
    "焦批沉降": 193,
    "下降B": 241,
    "矿批落料/错180再360": 337,
    "矿批沉降": 433,
    "审计静止": 481,
    "遮罩内重排/循环闭合": 553,
}


def parse_args():
    import sys
    p = argparse.ArgumentParser()
    p.add_argument("--stage", required=True)
    p.add_argument("--formal-glb", required=True)
    p.add_argument("--formal-glb-sha", required=True)
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else None
    return p.parse_args(argv)


def sha(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def volume_nonmanifold(obj):
    bm = bmesh.new()
    bm.from_mesh(obj.data)
    bm.edges.ensure_lookup_table()
    nonmanifold = sum(1 for e in bm.edges if len(e.link_faces) != 2)
    volume = abs(bm.calc_volume())
    bm.free()
    return volume, nonmanifold


def serializable_socket_value(value):
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


def controlled_r1_hash(material):
    if material is None or not material.use_nodes or material.node_tree is None:
        return None
    nodes = []
    for node in sorted(material.node_tree.nodes, key=lambda item: item.name):
        inputs = {}
        for socket in node.inputs:
            if node.bl_idname == "ShaderNodeMapping" and socket.name != "Vector":
                continue
            if not hasattr(socket, "default_value"):
                continue
            value = serializable_socket_value(socket.default_value)
            if value is not None:
                inputs[socket.name] = value
        nodes.append({
            "name": node.name,
            "bl_idname": node.bl_idname,
            "label": node.label,
            "inputs": inputs,
            "object": node.object.name if hasattr(node, "object") and node.object is not None else None,
        })
    links = sorted(
        [{
            "from": f"{link.from_node.name}.{link.from_socket.name}",
            "to": f"{link.to_node.name}.{link.to_socket.name}",
        } for link in material.node_tree.links],
        key=lambda item: (item["from"], item["to"]),
    )
    payload = {"nodes": nodes, "links": links}
    return hashlib.sha256(
        json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def visible_state_signature(scene, objects, frame):
    scene.frame_set(frame)
    rows = []
    for obj in sorted(objects, key=lambda item: item.name):
        if obj.hide_render:
            continue
        rows.append({
            "name": obj.name,
            "type": obj.type,
            "matrix_world": [round(float(v), 7) for row in obj.matrix_world for v in row],
            "data": obj.data.name if obj.data is not None else None,
        })
    payload = json.dumps(rows, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


args = parse_args()
stage = Path(args.stage)
reports = stage / "reports"
objects = [o for o in bpy.data.objects if o.name.startswith("R2L_")]
layers = [
    o for o in objects
    if "IRREGULAR_LAYER" in o.name
    or "BURDEN_SURFACE" in o.name
    or "SETTLED_" in o.name
    or "MORPH_POOL" in o.name
]
bad_meta = [o.name for o in objects if o.get("evidence_level") != "illustrative" or o.get("claim_label") != "E/illustrative" or o.get("scenario_id") != "E_BURDEN_LOOP_V1"]
bad_geom = []
for o in layers:
    if o.type == "MESH":
        v, n = volume_nonmanifold(o)
        if v <= 0 or n != 0:
            bad_geom.append({"name": o.name, "volume": v, "nonmanifold": n})
markers = {m.name: m.frame for m in bpy.context.scene.timeline_markers}
r1_actual_hash = controlled_r1_hash(bpy.data.materials.get(R1_MATERIAL))
loop_f1 = visible_state_signature(bpy.context.scene, objects, 1)
loop_f576 = visible_state_signature(bpy.context.scene, objects, 576)
frame_contract_ok = (
    bpy.context.scene.frame_start == 1
    and bpy.context.scene.frame_end == 576
    and bpy.context.scene.render.fps == 24
    and markers == EXPECTED_MARKERS
)
r1_controlled_ok = r1_actual_hash == R1_NODE_GRAPH_HASH
loop_visible_state_ok = loop_f1 == loop_f576
counts = {
    "objects": len(bpy.data.objects),
    "r2l_objects": len(objects),
    "sensors": len([o for o in bpy.data.objects if o.name.startswith("SENSOR_")]),
    "body_temperature_sensors": len([o for o in bpy.data.objects if o.name.startswith("SENSOR_T_body_L")]),
    "pressure_points": len([o for o in bpy.data.objects if o.name.startswith("GL02_INT30_PRESSURE_")]),
    "temperature_layer_bands": len([o for o in bpy.data.objects if o.name.startswith("APPROX_GL02_TEMP_LAYER_BAND_L")]),
    "l7_l16_counts": {f"L{i}": len([o for o in bpy.data.objects if o.name.startswith(f"SENSOR_T_body_L{i}_")]) for i in range(7,17)},
}
protected_ok = counts["sensors"] == 115 and counts["body_temperature_sensors"] == 80 and counts["pressure_points"] == 18 and counts["temperature_layer_bands"] == 10 and all(v == 8 for v in counts["l7_l16_counts"].values())
report = {
    "schema_version": 1,
    "status": "pass" if (
        not bad_meta
        and not bad_geom
        and protected_ok
        and frame_contract_ok
        and r1_controlled_ok
        and loop_visible_state_ok
        and sha(args.formal_glb).lower() == args.formal_glb_sha.lower()
    ) else "fail",
    "frame_start": bpy.context.scene.frame_start,
    "frame_end": bpy.context.scene.frame_end,
    "fps": bpy.context.scene.render.fps,
    "markers": markers,
    "expected_markers": EXPECTED_MARKERS,
    "frame_contract_ok": frame_contract_ok,
    "r1_controlled_material": R1_MATERIAL,
    "r1_controlled_node_graph_hash_expected": R1_NODE_GRAPH_HASH,
    "r1_controlled_node_graph_hash_actual": r1_actual_hash,
    "r1_controlled_node_graph_ok": r1_controlled_ok,
    "loop_visible_state_f1": loop_f1,
    "loop_visible_state_f576": loop_f576,
    "loop_visible_state_ok": loop_visible_state_ok,
    "counts": counts,
    "bad_meta": bad_meta,
    "bad_geom": bad_geom,
    "protected_contract_ok": protected_ok,
    "formal_glb_sha256": sha(args.formal_glb),
    "formal_glb_unchanged": sha(args.formal_glb).lower() == args.formal_glb_sha.lower(),
    "candidate_blend": bpy.data.filepath,
}
(reports / "r2l_reopen_validation.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
if report["status"] != "pass":
    raise SystemExit("R2L reopen validation failed")
'''


def annotate_evidence_images(image_paths: list[Path]) -> None:
    try:
        from PIL import Image, ImageDraw, ImageFont
    except Exception:
        return
    font_path = Path(r"C:\Windows\Fonts\simsun.ttc")
    try:
        font = ImageFont.truetype(str(font_path), 20) if font_path.exists() else ImageFont.load_default()
        label = "E级示意 | 非实时 | 非实测料线、层厚与布料轨迹"
    except Exception:
        font = ImageFont.load_default()
        label = "E/illustrative | non-live | non-measured"
    for path in image_paths:
        if not path.exists():
            continue
        image = Image.open(path).convert("RGBA")
        overlay = Image.new("RGBA", image.size, (0, 0, 0, 0))
        draw = ImageDraw.Draw(overlay)
        bbox = draw.textbbox((0, 0), label, font=font)
        width = bbox[2] - bbox[0]
        height = bbox[3] - bbox[1]
        x, y, pad = 16, 14, 10
        draw.rounded_rectangle(
            (x - pad, y - pad, x + width + pad, y + height + pad),
            radius=6,
            fill=(10, 15, 18, 205),
            outline=(235, 170, 65, 225),
            width=1,
        )
        draw.text((x, y), label, font=font, fill=(244, 239, 224, 255))
        Image.alpha_composite(image, overlay).convert("RGB").save(path)


def compose_contact_sheet(image_paths: list[Path], out_path: Path) -> None:
    try:
        from PIL import Image, ImageDraw
    except Exception:
        return
    thumbs = []
    for path in image_paths:
        im = Image.open(path).convert("RGB")
        im.thumbnail((420, 236))
        canvas = Image.new("RGB", (420, 276), (18, 21, 24))
        canvas.paste(im, (0, 0))
        d = ImageDraw.Draw(canvas)
        d.text((8, 246), path.name, fill=(230, 235, 235))
        thumbs.append(canvas)
    cols = 3
    rows = (len(thumbs) + cols - 1) // cols
    sheet = Image.new("RGB", (cols * 420, rows * 276), (8, 10, 12))
    for i, im in enumerate(thumbs):
        sheet.paste(im, ((i % cols) * 420, (i // cols) * 276))
    sheet.save(out_path)


def make_mp4() -> Path | None:
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        return None
    seq = RENDERS / "preview_seq" / "R2L_PREVIEW_%04d.png"
    out = RENDERS / "R2L_BURDEN_LOOP_PREVIEW_STEP12_24S.mp4"
    cmd = [
        ffmpeg,
        "-y",
        "-framerate",
        "2",
        "-start_number",
        "1",
        "-i",
        str(seq),
        "-vf",
        "scale=trunc(iw/2)*2:trunc(ih/2)*2,fps=24",
        "-c:v",
        "libx264",
        "-pix_fmt",
        "yuv420p",
        str(out),
    ]
    # ffmpeg's %04d source is contiguous only if renamed. Build a concat list instead.
    list_file = RENDERS / "preview_seq" / "r2l_preview_concat.txt"
    files = sorted((RENDERS / "preview_seq").glob("R2L_PREVIEW_*.png"))
    with list_file.open("w", encoding="utf-8") as f:
        for p in files:
            f.write(f"file '{p.as_posix()}'\n")
            f.write("duration 0.5\n")
        if files:
            f.write(f"file '{files[-1].as_posix()}'\n")
    cmd = [
        ffmpeg,
        "-y",
        "-f",
        "concat",
        "-safe",
        "0",
        "-i",
        str(list_file),
        "-vf",
        "scale=trunc(iw/2)*2:trunc(ih/2)*2,fps=24",
        "-c:v",
        "libx264",
        "-pix_fmt",
        "yuv420p",
        str(out),
    ]
    run(cmd, "r2l_ffmpeg_mp4.log", timeout=300)
    return out


def write_stage_summary(report: dict, reopen: dict, mp4: Path | None, contact: Path | None) -> None:
    summary = STAGE / "INT-30_R2L_BURDEN_ANIMATION_PROTOTYPE_阶段成果总结.md"
    lines = [
        "# INT-30 R2L 炉料动画原型阶段成果总结",
        "",
        f"- 生成时间：{datetime.now(timezone.utc).isoformat()}",
        "- 阶段性质：Blender 候选 / E级 illustrative / 不进入生产 GLB。",
        f"- 输入：`{INPUT_BLEND.relative_to(ROOT)}`",
        f"- 输入 SHA256：`{INPUT_SHA256}`",
        f"- 候选 Blend：`{Path(report['candidate_blend']).relative_to(ROOT)}`",
        f"- 候选 SHA256：`{report['candidate_sha256']}`",
        f"- 正式 GLB 未改变：`{report['formal_glb_unchanged']}` / `{report['formal_glb_sha256']}`",
        "",
        "## 本阶段实际做了什么",
        "",
        "- 新建 `BF3D_R2L_BURDEN_SYSTEM` 根集合，包含 `BURDEN_SURFACE`、`BURDEN_COKE`、`BURDEN_ORE`、`TOP_CHARGING`、`RENDER_ONLY_AUX`。",
        "- 生成 10 个交替矿/焦不规则炉料层、一个浅凹料面、焦批/矿批落料颗粒代理、旋转溜槽路径指示和循环重排遮罩。",
        "- 时间轴固定为 24fps、F1–F576，约 24 秒循环。",
        "- 旧的固定炉料环、固定软熔带和蓝色气流示意对象沿用 R2J 输入资产已有隐藏状态；其名称、几何、变换、材质和可见性不在本阶段改写。",
        "",
        "## 严格禁止外推的声明",
        "",
    ]
    for claim in report["forbidden_claims"]:
        lines.append(f"- {claim}")
    lines += [
        "",
        "## 关键时间段",
        "",
        "| 帧段 | 内容 | 数据边界 |",
        "|---|---|---|",
    ]
    for item in report["timeline"]:
        lines.append(f"| F{item['start']}–F{item['end']} | {item['name']} | {item['claim']} |")
    lines += [
        "",
        "## 机器验收结果",
        "",
        f"- 保护合同：`{report['protected_contract_ok']}`；115点、80个测温点、18个静压力点、10个L7-L16层带保持。",
        f"- 新对象数：`{report['new_object_count']}`；颗粒代理实例：`{report['new_particle_proxy_count']}`，由 `{report['new_particle_pool_object_count']}` 个共享 Morph 固定池承载；主炉料层数：`{report['new_layer_count']}`。",
        f"- R1 受控节点图哈希：`{report['r1_controlled_node_graph_after']['hash']}`；固定合同通过：`{report['r1_controlled_node_graph_ok']}`。",
        f"- F1/F576 可见状态签名同态：`{report['loop_visible_state_ok']}`。",
        f"- 复开验证：`{reopen['status']}`。",
        "- 所有新炉料实体：闭合、正体积、非流形边为 0。",
        "- R1/炉壳材质图哈希在构建前后未变化。",
        "",
        "## 可查看证据",
        "",
        f"- 接触表：`{contact.relative_to(ROOT) if contact and contact.exists() else '未生成'}`",
        f"- MP4 预览：`{mp4.relative_to(ROOT) if mp4 and mp4.exists() else '未生成'}`",
        f"- 机器报告：`{(REPORTS / 'int30_r2l_machine_report.json').relative_to(ROOT)}`",
        f"- 复开报告：`{(REPORTS / 'r2l_reopen_validation.json').relative_to(ROOT)}`",
    ]
    summary.write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_pipeline_status(report: dict, reopen: dict, mp4: Path | None, contact: Path | None) -> None:
    status = {
        "schema_version": 1,
        "current_stage": "INT-30_R2L_BURDEN_ANIMATION_PROTOTYPE",
        "status": "candidate_built_pending_external_review",
        "approval_boundary": "Only an isolated Blender candidate for E/illustrative burden animation. No GLB/Web/8092/production replacement is approved.",
        "candidate_blend": str(Path(report["candidate_blend"]).relative_to(ROOT)),
        "candidate_sha256": report["candidate_sha256"],
        "machine_report": str((REPORTS / "int30_r2l_machine_report.json").relative_to(ROOT)),
        "reopen_validation": str((REPORTS / "r2l_reopen_validation.json").relative_to(ROOT)),
        "formal_glb_sha256": report["formal_glb_sha256"],
        "formal_glb_unchanged": report["formal_glb_unchanged"],
        "evidence_level": "E/illustrative",
        "scenario_id": "E_BURDEN_LOOP_V1",
        "frame_contract": "24fps F1-F576 24s loop",
        "contact_sheet": str(contact.relative_to(ROOT)) if contact else None,
        "mp4_preview": str(mp4.relative_to(ROOT)) if mp4 else None,
        "next_stop_line": "Requires independent visual/spec review and user approval before any integration, GLB export or data-driven upgrade.",
    }
    (STAGE / "pipeline_status.json").write_text(json.dumps(status, ensure_ascii=False, indent=2), encoding="utf-8")


def main() -> None:
    ensure_dirs()
    if not BLENDER.exists():
        raise SystemExit(f"Blender not found: {BLENDER}")
    if sha256(INPUT_BLEND).lower() != INPUT_SHA256:
        raise SystemExit("Input R2J blend SHA mismatch")
    if sha256(FORMAL_GLB).lower() != FORMAL_GLB_SHA256:
        raise SystemExit("Formal GLB SHA mismatch before build")

    write_file(BUILD_SCRIPT, BLENDER_BUILD)
    write_file(REOPEN_SCRIPT, BLENDER_REOPEN)
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
    ], "r2l_build_blender.log", timeout=2400)
    if not CANDIDATE_BLEND.exists():
        raise SystemExit(f"Build did not create candidate blend; see {LOGS / 'r2l_build_blender.log'}")
    if not (REPORTS / "int30_r2l_machine_report.json").exists():
        raise SystemExit(f"Build did not create machine report; see {LOGS / 'r2l_build_blender.log'}")

    run([
        str(BLENDER),
        "--background",
        str(CANDIDATE_BLEND),
        "--python",
        str(REOPEN_SCRIPT),
        "--",
        "--stage",
        str(STAGE),
        "--formal-glb",
        str(FORMAL_GLB),
        "--formal-glb-sha",
        FORMAL_GLB_SHA256,
    ], "r2l_reopen_blender.log", timeout=600)

    report = json.loads((REPORTS / "int30_r2l_machine_report.json").read_text(encoding="utf-8"))
    reopen = json.loads((REPORTS / "r2l_reopen_validation.json").read_text(encoding="utf-8"))
    proof = [
        RENDERS / "R2L_FRAME_0001_MAIN.png",
        RENDERS / "R2L_FRAME_0144_MAIN.png",
        RENDERS / "R2L_FRAME_0216_MAIN.png",
        RENDERS / "R2L_FRAME_0384_MAIN.png",
        RENDERS / "R2L_FRAME_0432_MAIN.png",
        RENDERS / "R2L_FRAME_0576_MAIN.png",
        RENDERS / "R2L_FRAME_0144_TOP.png",
        RENDERS / "R2L_FRAME_0216_MATERIAL_CLOSEUP.png",
    ]
    annotate_evidence_images(
        [p for p in proof if p.exists()]
        + sorted((RENDERS / "preview_seq").glob("R2L_PREVIEW_*.png"))
    )
    contact = RENDERS / "R2L_CONTACT_SHEET.png"
    compose_contact_sheet([p for p in proof if p.exists()], contact)
    mp4 = make_mp4()

    write_pipeline_status(report, reopen, mp4, contact if contact.exists() else None)
    write_stage_summary(report, reopen, mp4, contact if contact.exists() else None)

    artifacts = {}
    for p in [
        Path(__file__).resolve(),
        CANDIDATE_BLEND,
        BUILD_SCRIPT,
        REOPEN_SCRIPT,
        REPORTS / "int30_r2l_machine_report.json",
        REPORTS / "r2l_reopen_validation.json",
        REPORTS / "r2l_timeline_contract.json",
        STAGE / "pipeline_status.json",
        STAGE / "INT-30_R2L_BURDEN_ANIMATION_PROTOTYPE_阶段成果总结.md",
        contact,
        mp4,
    ]:
        if p and p.exists():
            artifacts[str(p.relative_to(ROOT))] = {"sha256": sha256(p), "bytes": p.stat().st_size}
    for p in sorted(RENDERS.glob("R2L_FRAME_*.png")):
        artifacts[str(p.relative_to(ROOT))] = {"sha256": sha256(p), "bytes": p.stat().st_size}
    (REPORTS / "artifact_sha256.json").write_text(json.dumps(artifacts, ensure_ascii=False, indent=2), encoding="utf-8")

    blend1 = list(STAGE.rglob("*.blend1"))
    if blend1:
        raise SystemExit(f".blend1 backup files are forbidden: {blend1}")
    if sha256(FORMAL_GLB).lower() != FORMAL_GLB_SHA256:
        raise SystemExit("Formal GLB SHA mismatch after build")

    print(json.dumps({
        "status": "ok",
        "candidate": str(CANDIDATE_BLEND),
        "candidate_sha256": sha256(CANDIDATE_BLEND),
        "contact_sheet": str(contact),
        "mp4": str(mp4) if mp4 else None,
        "machine_report": str(REPORTS / "int30_r2l_machine_report.json"),
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
