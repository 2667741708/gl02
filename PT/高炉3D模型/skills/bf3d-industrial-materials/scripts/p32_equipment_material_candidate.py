"""Refine opaque GL02 equipment materials without changing geometry or sensors."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import bpy

AUDIT_DIR = Path(__file__).resolve().parents[2] / "bf3d-geometry-audit" / "scripts"
UV_DIR = Path(__file__).resolve().parents[2] / "bf3d-uv-bake" / "scripts"
sys.path[:0] = [str(AUDIT_DIR), str(UV_DIR), str(Path(__file__).resolve().parent)]
import p00_import_audit as p00  # noqa: E402
import p21_shaft_bake_test as p21  # noqa: E402
import p30_shell_material_candidate as p30  # noqa: E402


SPECS = {
    "dark_structural_rings": {
        "colors": ("#303A3E", "#4A5559"), "metallic": (0.42, 0.58), "roughness": (0.52, 0.64), "scale": 11.0, "bump": 0.0012,
    },
    "cooling_band_accents": {
        "colors": ("#606C72", "#838D91"), "metallic": (0.40, 0.56), "roughness": (0.50, 0.62), "scale": 15.0, "bump": 0.0009,
    },
    "maintenance_platforms": {
        "colors": ("#303638", "#474D4D"), "metallic": (0.45, 0.62), "roughness": (0.58, 0.70), "scale": 8.0, "bump": 0.0018,
    },
    "service_tower": {
        "colors": ("#3A454B", "#536067"), "metallic": (0.38, 0.54), "roughness": (0.56, 0.68), "scale": 9.0, "bump": 0.0014,
    },
    "top_gas_pipework": {
        "colors": ("#3E4947", "#5C6561"), "metallic": (0.55, 0.70), "roughness": (0.43, 0.56), "scale": 10.0, "bump": 0.0012,
    },
    "tuyere_and_bustle_pipe": {
        "colors": ("#373532", "#685742"), "metallic": (0.68, 0.82), "roughness": (0.38, 0.51), "scale": 13.0, "bump": 0.0008,
    },
    "hot_taphole_lining": {
        "colors": ("#3A2219", "#673822"), "metallic": (0.04, 0.10), "roughness": (0.65, 0.79), "scale": 12.0, "bump": 0.0018,
        "emission": "#E2551D", "emission_strength": 0.36,
    },
    "taphole_number_marker_hot": {
        "colors": ("#393B37", "#5F5246"), "metallic": (0.22, 0.44), "roughness": (0.58, 0.72), "scale": 10.0, "bump": 0.0015,
    },
}


def parse_args() -> argparse.Namespace:
    argv = sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else []
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-glb", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    return parser.parse_args(argv)


def set_map_range(node, minimum: float, maximum: float) -> None:
    node.inputs["From Min"].default_value = 0.0
    node.inputs["From Max"].default_value = 1.0
    node.inputs["To Min"].default_value = minimum
    node.inputs["To Max"].default_value = maximum
    node.clamp = True


def rebuild_material(material: bpy.types.Material, spec: dict[str, object]) -> None:
    material.use_nodes = True
    nodes = material.node_tree.nodes
    links = material.node_tree.links
    nodes.clear()
    output = p21.new_node(nodes, "ShaderNodeOutputMaterial", "P32_OUTPUT")
    principled = p21.new_node(nodes, "ShaderNodeBsdfPrincipled", "P32_PRINCIPLED")
    geometry = p21.new_node(nodes, "ShaderNodeNewGeometry", "P32_WORLD_POSITION")
    noise = p21.new_node(nodes, "ShaderNodeTexNoise", "P32_FIXED_MICRO_VARIATION")
    noise.noise_dimensions = "4D"
    noise.inputs["Scale"].default_value = float(spec["scale"])
    noise.inputs["Detail"].default_value = 3.0
    noise.inputs["Roughness"].default_value = 0.58
    noise.inputs["W"].default_value = 0.60716
    links.new(geometry.outputs["Position"], noise.inputs["Vector"])

    colors = p21.new_node(nodes, "ShaderNodeValToRGB", "P32_COLOR_VARIATION")
    colors.color_ramp.elements[0].position = 0.28
    colors.color_ramp.elements[0].color = p21.srgb(str(spec["colors"][0]))
    colors.color_ramp.elements[1].position = 0.72
    colors.color_ramp.elements[1].color = p21.srgb(str(spec["colors"][1]))
    links.new(noise.outputs["Fac"], colors.inputs["Fac"])
    links.new(colors.outputs["Color"], principled.inputs["Base Color"])

    metallic = p21.new_node(nodes, "ShaderNodeMapRange", "P32_METALLIC_RANGE")
    set_map_range(metallic, *[float(value) for value in spec["metallic"]])
    links.new(noise.outputs["Fac"], metallic.inputs["Value"])
    links.new(metallic.outputs["Result"], principled.inputs["Metallic"])

    roughness = p21.new_node(nodes, "ShaderNodeMapRange", "P32_ROUGHNESS_RANGE")
    set_map_range(roughness, *[float(value) for value in spec["roughness"]])
    links.new(noise.outputs["Fac"], roughness.inputs["Value"])
    links.new(roughness.outputs["Result"], principled.inputs["Roughness"])

    bump = p21.new_node(nodes, "ShaderNodeBump", "P32_MICRO_BUMP")
    bump.inputs["Strength"].default_value = 0.16
    bump.inputs["Distance"].default_value = float(spec["bump"])
    links.new(noise.outputs["Fac"], bump.inputs["Height"])
    links.new(bump.outputs["Normal"], principled.inputs["Normal"])

    emission_socket = principled.inputs.get("Emission Color") or principled.inputs.get("Emission")
    if emission_socket is not None:
        emission_socket.default_value = p21.srgb(str(spec.get("emission", "#000000")))
    if "Emission Strength" in principled.inputs:
        principled.inputs["Emission Strength"].default_value = float(spec.get("emission_strength", 0.0))
    principled.inputs["Alpha"].default_value = 1.0
    links.new(principled.outputs["BSDF"], output.inputs["Surface"])
    material.diffuse_color = (*p21.srgb(str(spec["colors"][0]))[:3], 1.0)


def main() -> int:
    args = parse_args()
    output_dir = args.output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    source_glb = args.source_glb.resolve()
    input_blend = Path(bpy.data.filepath).resolve()
    scene = bpy.context.scene
    if scene.get("bf3d_stage") != "P30_MATERIAL_APPROVED":
        raise RuntimeError(f"Expected P30_MATERIAL_APPROVED, got {scene.get('bf3d_stage')!r}")

    source = p00.source_node_contract(p00.read_glb_json(source_glb))
    sensors_before = p00.imported_contract(source)["sensor_records"]
    geometry_before = p30.scene_mesh_sha256(False)
    uv_before = p30.scene_mesh_sha256(True)
    matrices_before = p21.scene_matrix_sha256()
    material_hashes_before = {material.name: p30.material_hash(material) for material in bpy.data.materials}
    shell_hash_before = material_hashes_before[p30.SHELL_MATERIAL]
    sensor_hash_before = material_hashes_before["live_sensor_cyan"]

    missing = sorted(set(SPECS) - set(material_hashes_before))
    if missing:
        raise RuntimeError(f"Missing equipment materials: {missing}")
    for name, spec in SPECS.items():
        rebuild_material(bpy.data.materials[name], spec)

    geometry_after = p30.scene_mesh_sha256(False)
    uv_after = p30.scene_mesh_sha256(True)
    matrices_after = p21.scene_matrix_sha256()
    imported_after = p00.imported_contract(source)
    material_hashes_after = {material.name: p30.material_hash(material) for material in bpy.data.materials}
    changed = sorted(name for name, value in material_hashes_before.items() if material_hashes_after.get(name) != value)
    assertions = [
        {"id": "input_stage_is_p30_approved", "ok": scene.get("bf3d_stage") == "P30_MATERIAL_APPROVED"},
        {"id": "source_glb_matches_lock", "ok": p00.sha256_file(source_glb) == p00.EXPECTED_SOURCE_SHA256},
        {"id": "geometry_unchanged", "ok": geometry_before == geometry_after, "detail": {"before": geometry_before, "after": geometry_after}},
        {"id": "uv_unchanged", "ok": uv_before == uv_after, "detail": {"before": uv_before, "after": uv_after}},
        {"id": "matrices_unchanged", "ok": matrices_before == matrices_after, "detail": {"before": matrices_before, "after": matrices_after}},
        {"id": "sensor_contract_unchanged", "ok": sensors_before == imported_after["sensor_records"] and imported_after["sensor_count"] == 115 and imported_after["body_sensor_count"] == 80},
        {"id": "shell_material_unchanged", "ok": material_hashes_after[p30.SHELL_MATERIAL] == shell_hash_before},
        {"id": "sensor_material_unchanged", "ok": material_hashes_after["live_sensor_cyan"] == sensor_hash_before},
        {"id": "only_allowed_equipment_materials_changed", "ok": set(changed) == set(SPECS), "detail": changed},
        {"id": "taphole_marker_no_longer_emissive", "ok": bpy.data.materials["taphole_number_marker_hot"].node_tree.nodes["P32_PRINCIPLED"].inputs["Emission Strength"].default_value == 0.0},
        {"id": "taphole_lining_emission_is_restrained", "ok": bpy.data.materials["hot_taphole_lining"].node_tree.nodes["P32_PRINCIPLED"].inputs["Emission Strength"].default_value <= 0.4},
    ]
    ok = all(bool(item["ok"]) for item in assertions)
    candidate = None
    if ok:
        scene["bf3d_stage"] = "P32_EQUIPMENT_MATERIAL_CANDIDATE"
        scene["bf3d_parent_checkpoint"] = str(input_blend)
        scene["bf3d_change_dimension"] = "opaque_equipment_material_families_only"
        scene["bf3d_requires_bake"] = True
        candidate_path = output_dir / "P32_EQUIPMENT_MATERIAL_CANDIDATE.blend"
        bpy.ops.wm.save_as_mainfile(filepath=str(candidate_path), check_existing=False)
        candidate = {"path": str(candidate_path), "bytes": candidate_path.stat().st_size, "sha256": p00.sha256_file(candidate_path)}

    report = {
        "schema_version": 1,
        "stage": "P32_EQUIPMENT_MATERIAL_CANDIDATE",
        "status": "candidate_ready_for_visual_review" if ok else "fail",
        "input_checkpoint": {"path": str(input_blend), "sha256": p00.sha256_file(input_blend)},
        "candidate": candidate,
        "single_changed_dimension": "Opaque external equipment and taphole material families only.",
        "requires_bake": True,
        "material_parameters": SPECS,
        "assertions": assertions,
        "approval": "pending_fixed_camera_visual_review",
    }
    report_path = output_dir / "p32_equipment_material_candidate.json"
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": report["status"], "candidate": candidate, "report": str(report_path)}, ensure_ascii=False, indent=2))
    return 0 if ok else 2


if __name__ == "__main__":
    raise SystemExit(main())
