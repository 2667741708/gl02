"""INT-30 R2G read-only Blender/export contract preflight.

No .blend save and no GLB export. The script opens the R2F candidate in
Blender background mode, audits exportability, then writes md/json reports.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
BLENDER = Path(r"D:\Program Files\Blender Foundation\Blender 5.2\blender.exe")
STAGE_ID = "INT-30_R2G_ISOLATED_GLB_WEB_PREVIEW"
INPUT_BLEND = HERE / "work" / "INT_30_20260718_R2F_LAYER_OVERLAY_RUNTIME_READY" / "INT_30_R2F_LAYER_OVERLAY_RUNTIME_READY_CANDIDATE.blend"
OUTPUT_DIR = HERE / "work" / "INT_30_20260718_R2G_ISOLATED_GLB_WEB_PREVIEW"
FORMAL_GLB = ROOT / "高炉前端数据" / "models" / "gl02_blast_furnace.glb"

EXPECTED_INPUT_SHA256 = "1d292e8cc6ad5f845827cdd4c5f18b7e6eda496703870816caaef181af9fb3e5"
EXPECTED_FORMAL_GLB_SHA256 = "808960f1b2703e7fb27df35f1b1b1a17063b9b10d2267acba593fc3872b62af6"
R1_MATERIAL_NAME = "SURF20_R5_aged_painted_carbon_steel_shared_world"
R1_LOCK = {
    "decision_id": "VB-DEC-MAT-001",
    "carrier": "SURF-20 R5",
    "carrier_sha256": "4f1dae2804300c2c99462b4a5d7967abd9085a3ffd7170ae26af4e105290471b",
    "B": 0.16,
    "D_m": 0.10,
    "N": 0.45,
    "metallic": 0.06,
    "roughness_range": [0.56, 0.82],
    "mapping_scale": 0.085,
}

LAYERS = [f"L{i}" for i in range(7, 17)]
BANDS = [f"APPROX_GL02_TEMP_LAYER_BAND_{layer}" for layer in LAYERS]
GROUPS = [f"GL02_FURNACE_TEMP_LAYER_{layer}" for layer in LAYERS]
LAYER_SENSOR_GROUPS = [f"GL02_SENSOR_LAYER_{layer}" for layer in LAYERS]
PRESSURE_PREFIX = "GL02_INT30_PRESSURE_"
INT20_SOLIDS = [
    "APPROX_GL02_INT10_STEEL_SHELL_FULL",
    "APPROX_GL02_INT10_STEEL_SHELL_HALF",
    "APPROX_GL02_INT10_STEEL_SHELL_QUARTER",
    "APPROX_GL02_INT10_COOLING_WALL_FULL",
    "APPROX_GL02_INT10_COOLING_WALL_HALF",
    "APPROX_GL02_INT10_COOLING_WALL_QUARTER",
    "APPROX_GL02_INT10_REFRACTORY_LINING_FULL",
    "APPROX_GL02_INT10_REFRACTORY_LINING_HALF",
    "APPROX_GL02_INT10_REFRACTORY_LINING_QUARTER",
    "APPROX_GL02_INT10_PROCESS_SPACE_FULL",
    "APPROX_GL02_INT10_PROCESS_SPACE_HALF",
    "APPROX_GL02_INT10_PROCESS_SPACE_QUARTER",
]
FIVE_SHELL = [
    "APPROX_GL02_FURNACE_HEARTH",
    "APPROX_GL02_FURNACE_BOSH",
    "APPROX_GL02_FURNACE_BELLY",
    "APPROX_GL02_FURNACE_SHAFT",
    "APPROX_GL02_FURNACE_THROAT",
]
EXPORT_OPTIONS_RECOMMENDED = {
    "export_format": "GLB",
    "use_selection": False,
    "use_visible": False,
    "use_renderable": False,
    "use_active_collection": False,
    "use_active_scene": True,
    "export_cameras": False,
    "export_lights": False,
    "export_extras": True,
    "export_yup": True,
    "export_apply": False,
    "export_animations": False,
    "export_texcoords": True,
    "export_normals": True,
    "export_materials": "EXPORT",
    "export_image_format": "AUTO",
    "export_unused_images": False,
    "export_unused_textures": False,
    "export_draco_mesh_compression_enable": False,
    "export_meshopt_compression_enable": False,
}


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def hash_payload(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()


def now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def rel(path: Path) -> str:
    try:
        return path.resolve().relative_to(ROOT.resolve()).as_posix()
    except ValueError:
        return str(path.resolve())


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def write_text(path: Path, value: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(value, encoding="utf-8")


def host_main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--blender", type=Path, default=BLENDER)
    parser.add_argument("--input-blend", type=Path, default=INPUT_BLEND)
    parser.add_argument("--output-dir", type=Path, default=OUTPUT_DIR)
    args = parser.parse_args()

    blender = args.blender.resolve()
    input_blend = args.input_blend.resolve()
    output_dir = args.output_dir.resolve()
    if output_dir.name != "INT_30_20260718_R2G_ISOLATED_GLB_WEB_PREVIEW":
        raise RuntimeError(f"Refusing unexpected output dir: {output_dir}")
    if not blender.is_file():
        raise FileNotFoundError(blender)
    input_before = sha256_file(input_blend)
    glb_before = sha256_file(FORMAL_GLB)
    if input_before != EXPECTED_INPUT_SHA256:
        raise RuntimeError(f"Input SHA mismatch: {input_before}")
    if glb_before != EXPECTED_FORMAL_GLB_SHA256:
        raise RuntimeError(f"Formal GLB SHA mismatch: {glb_before}")
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "reports").mkdir(exist_ok=True)

    command = [
        str(blender),
        "--background",
        str(input_blend),
        "--python",
        str(Path(__file__).resolve()),
        "--",
        "--audit",
        "--output-dir",
        str(output_dir),
    ]
    proc = subprocess.run(command, cwd=str(HERE), capture_output=True, text=True)
    write_text(output_dir / "reports" / "r2g_blender_audit.stdout.log", proc.stdout)
    write_text(output_dir / "reports" / "r2g_blender_audit.stderr.log", proc.stderr)
    if proc.returncode != 0 or "Traceback (most recent call last)" in proc.stderr:
        raise RuntimeError(f"Blender audit failed with {proc.returncode}; see {output_dir / 'reports'}")

    report = json.loads((output_dir / "R2G_BLEND_EXPORT_PREFLIGHT.json").read_text(encoding="utf-8"))
    input_after = sha256_file(input_blend)
    glb_after = sha256_file(FORMAL_GLB)
    report["host_protection"] = {
        "input_blend": {"path": rel(input_blend), "sha256_before": input_before, "sha256_after": input_after, "unchanged": input_before == input_after},
        "formal_glb": {"path": rel(FORMAL_GLB), "sha256_before": glb_before, "sha256_after": glb_after, "unchanged": glb_before == glb_after},
        "no_blend_saved_by_stage": not any(output_dir.rglob("*.blend")) and not any(output_dir.rglob("*.blend1")),
        "no_glb_exported_by_stage": not any(output_dir.rglob("*.glb")),
    }
    report["assertions"]["host_readonly_pass"] = all(report["host_protection"].values()) if False else (
        report["host_protection"]["input_blend"]["unchanged"]
        and report["host_protection"]["formal_glb"]["unchanged"]
        and report["host_protection"]["no_blend_saved_by_stage"]
        and report["host_protection"]["no_glb_exported_by_stage"]
    )
    report["assertions"]["preflight_audit_pass"] = all(report["assertions"].values())
    write_json(output_dir / "R2G_BLEND_EXPORT_PREFLIGHT.json", report)
    write_markdown(output_dir / "R2G_BLEND_EXPORT_PREFLIGHT.md", report)
    print(json.dumps({"stage": STAGE_ID, "status": "readonly_preflight_written", "json": rel(output_dir / "R2G_BLEND_EXPORT_PREFLIGHT.json")}, ensure_ascii=False))
    return 0


def blender_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--audit", action="store_true")
    parser.add_argument("--output-dir", type=Path, required=True)
    argv = sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else []
    return parser.parse_args(argv)


def blender_main() -> int:
    args = blender_args()
    if not args.audit:
        raise RuntimeError("Missing --audit")
    import bpy

    report = blender_audit(bpy)
    write_json(args.output_dir / "R2G_BLEND_EXPORT_PREFLIGHT.json", report)
    return 0


def blender_audit(bpy: Any) -> dict[str, Any]:
    scene = bpy.context.scene
    bands = [object_record(bpy, name) for name in BANDS]
    groups = [object_record(bpy, name) for name in GROUPS]
    band_materials = {name: material_record(bpy, object_record(bpy, name).get("materials", [None])[0]) for name in BANDS}
    material_names = sorted([mat.name for mat in bpy.data.materials])
    mesh_records = {name: mesh_record(bpy, name) for name in BANDS}
    r1_material = material_record(bpy, R1_MATERIAL_NAME)
    export_sets = build_export_sets(bpy)
    uv_audit = uv_export_audit(bpy)
    extras_audit = extras_export_audit(bpy)
    risks = risk_register(r1_material, uv_audit)
    assertions = {
        "all_115_sensors_present": export_sets["sensors"]["count"] == 115,
        "all_80_body_temp_sensors_present": export_sets["body_temperature_sensors"]["count"] == 80,
        "all_18_pressure_objects_present": export_sets["pressure"]["count"] == 18,
        "all_12_int20_solids_present": export_sets["int20_solids"]["count"] == 12,
        "five_furnace_shell_objects_present": export_sets["five_shell"]["count"] == 5,
        "ten_canonical_bands_present": all(item["present"] for item in bands),
        "ten_canonical_groups_present": all(item["present"] for item in groups),
        "band_default_hidden": all(item.get("hide_viewport") and item.get("hide_render") for item in bands if item["present"]),
        "band_names_canonical_for_frontend_regex": [item["name"] for item in bands] == BANDS,
        "band_extras_present": all(extras_audit["bands"].get(name, {}).get("has_runtime_metadata") for name in BANDS),
        "band_uv_present": all(uv_audit["bands"].get(name, {}).get("uv_layer_count", 0) >= 1 for name in BANDS),
        "r1_material_present": r1_material["present"],
        "r1_material_is_procedural_node_graph": bool(r1_material.get("procedural_nodes")),
        "direct_gltf_r1_bake_required_or_frontend_adapter_required": bool(r1_material.get("unsupported_or_lossy_for_gltf")),
        "recommended_export_options_keep_hidden_bands_exportable": EXPORT_OPTIONS_RECOMMENDED["use_visible"] is False and EXPORT_OPTIONS_RECOMMENDED["use_renderable"] is False,
        "recommended_export_options_keep_extras": EXPORT_OPTIONS_RECOMMENDED["export_extras"] is True,
        "no_blend_save_or_glb_export_attempted": True,
    }
    report = {
        "schema_version": "bf3d.int30_r2g.blend_export_preflight.v1",
        "stage": STAGE_ID,
        "status": "readonly_preflight_audit_only",
        "approval": "not_granted_future_candidate_not_approved",
        "generated_at": now_iso(),
        "input": {"path": rel(INPUT_BLEND), "expected_sha256": EXPECTED_INPUT_SHA256},
        "blender": {"version": bpy.app.version_string, "background": bpy.app.background},
        "scene": {
            "name": scene.name,
            "object_count": len(bpy.data.objects),
            "mesh_count": len(bpy.data.meshes),
            "material_count": len(bpy.data.materials),
            "unit_system": scene.unit_settings.system,
            "materials": material_names,
        },
        "export_contract": {
            "recommended_options": EXPORT_OPTIONS_RECOMMENDED,
            "hidden_object_policy": "Use use_visible=false and use_renderable=false so default-hidden runtime bands are still included in the GLB node graph; frontend/runtime must keep them hidden by extras or object name until selected.",
            "selection_policy": "Use use_selection=false; selection state in Blender must not determine handoff content.",
            "extras_policy": "Use export_extras=true to preserve band runtime metadata and layer links.",
            "do_not_export_in_this_stage": True,
        },
        "export_sets": export_sets,
        "bands": {"objects": bands, "groups": groups, "meshes": mesh_records, "materials": band_materials},
        "extras_audit": extras_audit,
        "uv_and_texture_audit": uv_audit,
        "r1_material_lock": R1_LOCK,
        "r1_material_gltf_loss_audit": r1_material,
        "risk_register": risks,
        "recommended_gates_before_any_r2g_candidate": recommended_gates(),
        "assertions": assertions,
    }
    report["assertions"]["preflight_audit_pass"] = all(assertions.values())
    return report


def object_record(bpy: Any, name: str) -> dict[str, Any]:
    obj = bpy.data.objects.get(name)
    if obj is None:
        return {"name": name, "present": False}
    return {
        "name": name,
        "present": True,
        "type": obj.type,
        "parent": obj.parent.name if obj.parent else None,
        "hide_viewport": bool(obj.hide_viewport),
        "hide_render": bool(obj.hide_render),
        "matrix_world": [round(float(v), 8) for row in obj.matrix_world for v in row],
        "materials": [slot.material.name for slot in obj.material_slots if slot.material],
        "custom_properties": clean_custom_props(obj),
        "collections": sorted([col.name for col in obj.users_collection]),
        "data_name": obj.data.name if getattr(obj, "data", None) else None,
    }


def mesh_record(bpy: Any, object_name: str) -> dict[str, Any]:
    obj = bpy.data.objects.get(object_name)
    if obj is None or obj.type != "MESH":
        return {"object": object_name, "present": False}
    mesh = obj.data
    return {
        "object": object_name,
        "mesh": mesh.name,
        "vertices": len(mesh.vertices),
        "edges": len(mesh.edges),
        "polygons": len(mesh.polygons),
        "uv_layers": [uv.name for uv in mesh.uv_layers],
        "vertex_hash": hash_payload([[round(float(c), 7) for c in v.co] for v in mesh.vertices]),
        "polygon_hash": hash_payload([list(poly.vertices) for poly in mesh.polygons]),
    }


def clean_custom_props(obj: Any) -> dict[str, Any]:
    result = {}
    for key in obj.keys():
        if key == "_RNA_UI":
            continue
        value = obj[key]
        try:
            json.dumps(value)
            result[key] = value
        except TypeError:
            result[key] = str(value)
    return result


def material_record(bpy: Any, name: str | None) -> dict[str, Any]:
    if not name:
        return {"name": None, "present": False}
    mat = bpy.data.materials.get(name)
    if mat is None:
        return {"name": name, "present": False}
    nodes = []
    links = []
    images = []
    procedural = []
    lossy = []
    if mat.use_nodes and mat.node_tree:
        for node in sorted(mat.node_tree.nodes, key=lambda item: item.name):
            nodes.append({"name": node.name, "type": node.bl_idname, "label": node.label})
            if node.bl_idname in {"ShaderNodeTexNoise", "ShaderNodeTexVoronoi", "ShaderNodeBump", "ShaderNodeValToRGB", "ShaderNodeMapping", "ShaderNodeTexCoord", "ShaderNodeMath", "ShaderNodeMix", "ShaderNodeMixRGB"}:
                procedural.append({"name": node.name, "type": node.bl_idname})
            if node.bl_idname not in {"ShaderNodeOutputMaterial", "ShaderNodeBsdfPrincipled", "ShaderNodeTexImage", "ShaderNodeNormalMap"}:
                lossy.append({"name": node.name, "type": node.bl_idname, "reason": "glTF exporter will not preserve this procedural node as an equivalent runtime shader graph"})
            if node.bl_idname == "ShaderNodeTexImage" and getattr(node, "image", None):
                images.append({"node": node.name, "image": node.image.name, "filepath": node.image.filepath})
        for link in mat.node_tree.links:
            links.append({"from": f"{link.from_node.name}.{link.from_socket.name}", "to": f"{link.to_node.name}.{link.to_socket.name}"})
    return {
        "name": mat.name,
        "present": True,
        "use_nodes": bool(mat.use_nodes),
        "blend_method": mat.blend_method,
        "use_screen_refraction": bool(getattr(mat, "use_screen_refraction", False)),
        "show_transparent_back": bool(getattr(mat, "show_transparent_back", False)),
        "node_count": len(nodes),
        "nodes": nodes,
        "links": links,
        "image_textures": images,
        "procedural_nodes": procedural,
        "unsupported_or_lossy_for_gltf": lossy,
        "gltf_direct_export_conclusion": "lossy_or_incomplete" if lossy else "basic_pbr_exportable",
    }


def build_export_sets(bpy: Any) -> dict[str, Any]:
    sensors = sorted([obj.name for obj in bpy.data.objects if obj.name.startswith("SENSOR_")])
    body = sorted([obj.name for obj in bpy.data.objects if obj.name.startswith("SENSOR_T_body_")])
    pressure = sorted([obj.name for obj in bpy.data.objects if obj.name.startswith(PRESSURE_PREFIX)])
    return {
        "sensors": {"count": len(sensors), "names_hash": hash_payload(sensors), "sample": sensors[:8]},
        "body_temperature_sensors": {"count": len(body), "names_hash": hash_payload(body), "layer_counts": {layer: len([name for name in body if name.startswith(f"SENSOR_T_body_{layer}_")]) for layer in LAYERS}},
        "pressure": {"count": len(pressure), "names_hash": hash_payload(pressure), "names": pressure},
        "int20_solids": {"count": len([name for name in INT20_SOLIDS if bpy.data.objects.get(name)]), "names": [name for name in INT20_SOLIDS if bpy.data.objects.get(name)]},
        "five_shell": {"count": len([name for name in FIVE_SHELL if bpy.data.objects.get(name)]), "names": [name for name in FIVE_SHELL if bpy.data.objects.get(name)]},
        "canonical_bands": {"count": len([name for name in BANDS if bpy.data.objects.get(name)]), "names": [name for name in BANDS if bpy.data.objects.get(name)]},
        "canonical_groups": {"count": len([name for name in GROUPS if bpy.data.objects.get(name)]), "names": [name for name in GROUPS if bpy.data.objects.get(name)]},
        "sensor_layer_groups": {"count": len([name for name in LAYER_SENSOR_GROUPS if bpy.data.objects.get(name)]), "names": [name for name in LAYER_SENSOR_GROUPS if bpy.data.objects.get(name)]},
    }


def uv_export_audit(bpy: Any) -> dict[str, Any]:
    bands = {}
    for name in BANDS:
        obj = bpy.data.objects.get(name)
        if obj and obj.type == "MESH":
            mesh = obj.data
            bands[name] = {
                "uv_layer_count": len(mesh.uv_layers),
                "uv_layers": [uv.name for uv in mesh.uv_layers],
                "material_slots": [slot.material.name for slot in obj.material_slots if slot.material],
                "has_image_textures": any(material_record(bpy, slot.material.name)["image_textures"] for slot in obj.material_slots if slot.material),
            }
        else:
            bands[name] = {"uv_layer_count": 0, "uv_layers": [], "material_slots": []}
    r1 = material_record(bpy, R1_MATERIAL_NAME)
    return {
        "bands": bands,
        "r1_material": {
            "material": R1_MATERIAL_NAME,
            "image_textures": r1.get("image_textures", []),
            "procedural_nodes": r1.get("procedural_nodes", []),
            "direct_texture_slots_ready": bool(r1.get("image_textures")),
            "conclusion": "R1 shell has procedural node graph and no complete baked PBR texture set detected; direct GLB export will not preserve exact R1 rough micro-surface without baking or a frontend material adapter.",
        },
    }


def extras_export_audit(bpy: Any) -> dict[str, Any]:
    bands = {}
    for name in BANDS:
        obj = bpy.data.objects.get(name)
        props = clean_custom_props(obj) if obj else {}
        bands[name] = {
            "custom_properties": props,
            "has_runtime_metadata": any(key in props for key in ["bf3d_layer_id", "layer_id", "source_sensor_group", "default_visible", "runtime_ready"]),
            "default_hidden_in_blender": bool(obj.hide_viewport and obj.hide_render) if obj else False,
        }
    groups = {name: clean_custom_props(bpy.data.objects[name]) if bpy.data.objects.get(name) else {} for name in GROUPS}
    return {"bands": bands, "groups": groups}


def risk_register(r1_material: dict[str, Any], uv_audit: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        {
            "id": "R2G-RISK-R1-PROCEDURAL-LOSS",
            "severity": "high",
            "risk": "Blender procedural nodes for the locked R1 surface will not be faithfully represented by a direct glTF material export.",
            "evidence": [item["type"] for item in r1_material.get("procedural_nodes", [])],
            "mitigation": "Before any GLB candidate approval, bake R1 into glTF-readable PBR textures or preserve the frontend runtime material adapter with explicit parity evidence.",
        },
        {
            "id": "R2G-RISK-HIDDEN-BAND-EXPORT",
            "severity": "medium",
            "risk": "If export uses visible/renderable-only filtering, default-hidden canonical layer bands will be omitted.",
            "mitigation": "Use use_visible=false and use_renderable=false; verify exported GLB contains all ten APPROX_GL02_TEMP_LAYER_BAND_L7-L16 nodes and extras.",
        },
        {
            "id": "R2G-RISK-TRANSPARENT-OVERLAY-SORTING",
            "severity": "medium",
            "risk": "Semi-transparent diagnostic bands may sort differently in Three.js than Blender.",
            "mitigation": "Run a browser preview with selected L7/L10/L13/L16 states, depthWrite/depthTest policy, and sensor readability checks.",
        },
        {
            "id": "R2G-RISK-UNBAKED-BAND-MATERIALS",
            "severity": "low",
            "risk": "Band materials are diagnostic and should not be interpreted as production shell material.",
            "mitigation": "Keep band material names and extras diagnostic; frontend should default-hide and recolor selected layer by state.",
        },
    ]


def recommended_gates() -> list[dict[str, Any]]:
    return [
        {"id": "exported_node_contract", "required": True, "check": "GLB contains 115 SENSOR_ nodes, 80 SENSOR_T_body nodes, 18 pressure nodes, 12 INT20 solids, five furnace shell nodes, 10 canonical band meshes and 10 layer groups."},
        {"id": "extras_contract", "required": True, "check": "export_extras=true preserves layer id, height, source sensor group, default_visible/runtime metadata."},
        {"id": "r1_parity_contract", "required": True, "check": "R1 VB-DEC-MAT-001 visual parity is proven after export by baked PBR or runtime adapter; no flattening of B=.16/D=.10m/N=.45."},
        {"id": "validator_contract", "required": True, "check": "glTF Validator errors=0; warnings triaged, especially transparency/material warnings."},
        {"id": "threejs_runtime_contract", "required": True, "check": "Frontend preview defaults bands hidden, selected layer only visible, sensors readable, L7/L10/L13/L16 tested, no GLB production replacement."},
        {"id": "performance_contract", "required": True, "check": "Layer overlays add expected 2112 vertices / 2944 triangles and selected-state draw call remains bounded."},
    ]


def write_markdown(path: Path, report: dict[str, Any]) -> None:
    risks = "\n".join([f"- `{item['id']}` ({item['severity']}): {item['risk']} Mitigation: {item['mitigation']}" for item in report["risk_register"]])
    gates = "\n".join([f"- `{item['id']}`: {item['check']}" for item in report["recommended_gates_before_any_r2g_candidate"]])
    assertions = "\n".join([f"- `{key}`: `{value}`" for key, value in report["assertions"].items()])
    lossy = report["r1_material_gltf_loss_audit"].get("unsupported_or_lossy_for_gltf", [])
    lossy_lines = "\n".join([f"- `{item['type']}` `{item['name']}`: {item['reason']}" for item in lossy]) or "- none"
    lines = [
        "# R2G Blend Export Preflight",
        "",
        f"- Stage: `{STAGE_ID}`",
        "- Status: `readonly_preflight_audit_only`",
        "- Approval: `not_granted_future_candidate_not_approved`",
        f"- Input: `{report['input']['path']}`",
        f"- Input SHA unchanged: `{report['host_protection']['input_blend']['sha256_after']}`",
        f"- Formal GLB unchanged: `{report['host_protection']['formal_glb']['sha256_after']}`",
        "",
        "## Export Contract",
        "",
        "- Recommended exporter options are recorded in JSON under `export_contract.recommended_options`.",
        "- Hidden bands require `use_visible=false` and `use_renderable=false`; otherwise default-hidden runtime overlays may be omitted.",
        "- Runtime layer metadata requires `export_extras=true`.",
        "- This stage did not export a GLB and did not save the blend.",
        "",
        "## Structure Coverage",
        "",
        f"- Sensors: `{report['export_sets']['sensors']['count']}`",
        f"- Body-temperature sensors: `{report['export_sets']['body_temperature_sensors']['count']}`",
        f"- Pressure objects: `{report['export_sets']['pressure']['count']}`",
        f"- INT20 solids: `{report['export_sets']['int20_solids']['count']}`",
        f"- Five furnace shell objects: `{report['export_sets']['five_shell']['count']}`",
        f"- Canonical bands: `{report['export_sets']['canonical_bands']['count']}`",
        f"- Canonical layer groups: `{report['export_sets']['canonical_groups']['count']}`",
        "",
        "## R1 Material Risk",
        "",
        "Locked R1 `VB-DEC-MAT-001` remains a procedural Blender node graph. Direct glTF export is expected to be lossy unless R1 is baked to PBR textures or preserved by a frontend runtime material adapter.",
        "",
        "Lossy/procedural nodes detected:",
        lossy_lines,
        "",
        "## UV And Texture Readiness",
        "",
        "- Canonical bands have UV layers and diagnostic materials suitable for structural/runtime preview.",
        "- R1 material does not have a complete baked image texture set detected in this audit.",
        "- Direct production GLB handoff should remain blocked until R1 visual parity is proven after export.",
        "",
        "## Risks",
        "",
        risks,
        "",
        "## Required Gates Before Any Future R2G Candidate",
        "",
        gates,
        "",
        "## Assertions",
        "",
        assertions,
    ]
    write_text(path, "\n".join(lines) + "\n")


if __name__ == "__main__":
    if "--" in sys.argv and "--audit" in sys.argv:
        raise SystemExit(blender_main())
    raise SystemExit(host_main())
