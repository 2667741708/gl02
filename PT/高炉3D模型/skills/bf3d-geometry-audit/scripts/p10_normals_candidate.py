"""Create a P10 candidate that changes only the five shell-zone normals."""

from __future__ import annotations

import argparse
import hashlib
import json
import struct
import sys
from pathlib import Path

import bpy

sys.path.insert(0, str(Path(__file__).resolve().parent))
import p00_import_audit as p00


def parse_args() -> argparse.Namespace:
    argv = sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else []
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-glb", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--resolution", type=int, default=768)
    return parser.parse_args(argv)


def mesh_geometry_sha256(mesh: bpy.types.Mesh) -> str:
    digest = hashlib.sha256()
    for vertex in mesh.vertices:
        digest.update(struct.pack("<3d", *(float(value) for value in vertex.co)))
    for polygon in mesh.polygons:
        digest.update(struct.pack("<I", len(polygon.vertices)))
        for index in polygon.vertices:
            digest.update(struct.pack("<I", int(index)))
    return digest.hexdigest()


def zone_snapshot() -> dict[str, object]:
    result: dict[str, object] = {}
    for name in sorted(p00.PROCESS_ZONES):
        obj = bpy.data.objects.get(name)
        if obj is None or obj.type != "MESH":
            result[name] = {"missing": True}
            continue
        mesh = obj.data
        result[name] = {
            "mesh": mesh.name,
            "vertices": len(mesh.vertices),
            "edges": len(mesh.edges),
            "polygons": len(mesh.polygons),
            "geometry_sha256": mesh_geometry_sha256(mesh),
            "attributes": sorted(attribute.name for attribute in mesh.attributes),
            "smooth_polygons": sum(bool(polygon.use_smooth) for polygon in mesh.polygons),
            "aabb": [
                [round(float(value), 9) for value in bound]
                for bound in p00.object_bounds([obj])
            ],
        }
    return result


def main() -> int:
    args = parse_args()
    source_glb = args.source_glb.resolve()
    output_dir = args.output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    input_blend = Path(bpy.data.filepath).resolve()
    if not input_blend.is_file():
        raise FileNotFoundError("P10 requires a saved P00 blend input")
    if bpy.context.scene.get("bf3d_stage") != "P00_SOURCE_LOCKED":
        raise RuntimeError(f"Expected a P00_SOURCE_LOCKED scene, got {bpy.context.scene.get('bf3d_stage')!r}")
    source_hash_before = p00.sha256_file(source_glb)
    source = p00.source_node_contract(p00.read_glb_json(source_glb))
    imported_before = p00.imported_contract(source)
    zones_before = zone_snapshot()

    changed: list[dict[str, object]] = []
    for name in sorted(p00.PROCESS_ZONES):
        obj = bpy.data.objects.get(name)
        if obj is None or obj.type != "MESH":
            continue
        mesh = obj.data
        custom_normal = mesh.attributes.get("custom_normal")
        if custom_normal is not None:
            mesh.attributes.remove(custom_normal)
        for polygon in mesh.polygons:
            polygon.use_smooth = True
        mesh.update()
        changed.append({"object": name, "removed_custom_normal": custom_normal is not None})
    bpy.context.view_layer.update()

    imported_after = p00.imported_contract(source)
    zones_after = zone_snapshot()
    source_hash_after = p00.sha256_file(source_glb)
    assertions = [
        {"id": "input_is_p00_checkpoint", "ok": bpy.context.scene.get("bf3d_stage") == "P00_SOURCE_LOCKED"},
        {"id": "source_glb_matches_locked_sha", "ok": source_hash_before == p00.EXPECTED_SOURCE_SHA256, "detail": source_hash_before},
        {"id": "source_glb_unchanged", "ok": source_hash_after == source_hash_before, "detail": {"before": source_hash_before, "after": source_hash_after}},
        {"id": "five_zones_changed", "ok": len(changed) == 5, "detail": changed},
        {"id": "all_zone_custom_normals_present_before", "ok": all("custom_normal" in item.get("attributes", []) for item in zones_before.values()), "detail": {name: "custom_normal" in item.get("attributes", []) for name, item in zones_before.items()}},
        {"id": "all_zone_custom_normals_removed_after", "ok": all("custom_normal" not in item.get("attributes", []) for item in zones_after.values()), "detail": {name: "custom_normal" in item.get("attributes", []) for name, item in zones_after.items()}},
        {"id": "zone_geometry_unchanged", "ok": all(zones_before[name].get("geometry_sha256") == zones_after[name].get("geometry_sha256") for name in zones_before), "detail": {name: {"before": zones_before[name].get("geometry_sha256"), "after": zones_after[name].get("geometry_sha256")} for name in zones_before}},
        {"id": "zone_aabb_unchanged", "ok": all(zones_before[name].get("aabb") == zones_after[name].get("aabb") for name in zones_before)},
        {"id": "sensor_contract_unchanged", "ok": imported_before["sensor_records"] == imported_after["sensor_records"]},
        {"id": "sensor_count_115", "ok": imported_after["sensor_count"] == 115, "detail": imported_after["sensor_count"]},
        {"id": "body_sensor_count_80", "ok": imported_after["body_sensor_count"] == 80, "detail": imported_after["body_sensor_count"]},
        {"id": "no_sensor_matrix_mismatches", "ok": not imported_after["matrix_mismatches"], "detail": imported_after["matrix_mismatches"][:8]},
        {"id": "five_process_zones_preserved", "ok": all(imported_after["process_zones"].values())},
        {"id": "ten_layer_groups_preserved", "ok": all(item["exists"] and len(item["children"]) == 8 for item in imported_after["layer_groups"].values())},
    ]
    contract_ok = all(bool(item["ok"]) for item in assertions)
    candidate_path = output_dir / "P10_NORMALS_CANDIDATE.blend"
    candidate = None
    if contract_ok:
        scene = bpy.context.scene
        scene["bf3d_stage"] = "P10_NORMALS_CANDIDATE"
        scene["bf3d_parent_checkpoint"] = str(input_blend)
        scene["bf3d_source_glb"] = str(source_glb)
        scene["bf3d_change_dimension"] = "shell_zone_normals_only"
        bpy.ops.wm.save_as_mainfile(filepath=str(candidate_path), check_existing=False)
        candidate = {"path": str(candidate_path), "bytes": candidate_path.stat().st_size, "sha256": p00.sha256_file(candidate_path)}

    renders: list[dict[str, object]] = []
    render_error = None
    if contract_ok:
        try:
            renders = p00.render_clay_views(output_dir, max(256, min(args.resolution, 2048)), prefix="P10")
        except Exception as exc:  # noqa: BLE001
            render_error = {"type": type(exc).__name__, "message": str(exc)}
    status = "candidate_ready_for_visual_review" if contract_ok and render_error is None and len(renders) == 5 else "fail"
    report = {
        "schema_version": 1,
        "stage": "P10_NORMALS_CANDIDATE",
        "status": status,
        "single_changed_dimension": "Remove imported custom_normal attributes on five process-zone meshes and recalculate smooth geometry normals.",
        "input_checkpoint": {"path": str(input_blend), "bytes": input_blend.stat().st_size, "sha256": p00.sha256_file(input_blend)},
        "source_glb": {"path": str(source_glb), "sha256": source_hash_before},
        "candidate": candidate,
        "changed": changed,
        "zones_before": zones_before,
        "zones_after": zones_after,
        "assertions": assertions,
        "renders": renders,
        "render_error": render_error,
        "approval": "pending_visual_comparison",
    }
    report_path = output_dir / "p10_normals_candidate.json"
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": status, "report": str(report_path), "candidate": candidate, "renders": len(renders)}, ensure_ascii=False, indent=2))
    return 0 if status == "candidate_ready_for_visual_review" else 2


if __name__ == "__main__":
    raise SystemExit(main())
