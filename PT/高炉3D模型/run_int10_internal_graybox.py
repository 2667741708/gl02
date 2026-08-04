"""Build the isolated INT-10 four-layer internal graybox candidate.

This file is both the host-side runner and the Blender-side implementation.
The host process verifies the approved P40 input hash and launches Blender 5.2
in background mode. Blender writes only into work/INT_10_20260718_R1.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
DEFAULT_BLENDER = Path(r"D:\Program Files\Blender Foundation\Blender 5.2\blender.exe")
DEFAULT_INPUT = (
    HERE
    / "work"
    / "P40_FIXED_LOOKDEV_20260717_P36_FINAL"
    / "P40_LOOKDEV_APPROVED.blend"
)
DEFAULT_OUTPUT = HERE / "work" / "INT_10_20260718_R1"
EXPECTED_INPUT_SHA256 = "03635cf6608a54c4a671fb4d84adcb9451a36fe47cea7b564af2d4d3b69b2256"
REQUIREMENT_ID = "REQ-BF3D-10STAGE-EXECUTION-20260718"
STAGE_ID = "INT-10"

PROFILE = [
    {"h_m": 0.0, "r_m": 2.05, "zone": "hearth"},
    {"h_m": 4.8, "r_m": 2.35, "zone": "hearth"},
    {"h_m": 8.8, "r_m": 2.95, "zone": "tuyere"},
    {"h_m": 13.8, "r_m": 4.15, "zone": "bosh"},
    {"h_m": 18.6, "r_m": 4.46, "zone": "belly"},
    {"h_m": 24.5, "r_m": 4.05, "zone": "lower_stack"},
    {"h_m": 30.6, "r_m": 3.36, "zone": "upper_stack"},
    {"h_m": 35.2, "r_m": 2.78, "zone": "lower_throat"},
    {"h_m": 37.2, "r_m": 2.42, "zone": "throat"},
    {"h_m": 40.0, "r_m": 2.18, "zone": "top"},
]

PROTECTED_SEGMENTS = [
    "APPROX_GL02_FURNACE_HEARTH",
    "APPROX_GL02_FURNACE_BOSH",
    "APPROX_GL02_FURNACE_BELLY",
    "APPROX_GL02_FURNACE_SHAFT",
    "APPROX_GL02_FURNACE_THROAT",
]
PROTECTED_LAYER_GROUPS = [f"GL02_SENSOR_LAYER_L{layer}" for layer in range(7, 17)]
PROTECTED_LAYER_BANDS = [
    f"APPROX_GL02_TEMP_LAYER_BAND_L{layer}" for layer in range(7, 17)
]

EXPLANATORY_INTERNAL_TOKENS = (
    "burden_column_layered_charge",
    "cohesive_zone_softening_melting_band",
    "countercurrent_gas_flow_streamlines",
    "hot_blast_raceway_plumes",
    "hot_metal_dripping_",
    "hearth_molten_iron_pool",
    "hearth_slag_layer",
    "cold_blast_supply_flow",
    "internal_burden_reference_bands",
    "temp_layer_band_",
)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def write_json(path: Path, value: Any) -> None:
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def host_main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--blender", type=Path, default=DEFAULT_BLENDER)
    parser.add_argument("--input-blend", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--width", type=int, default=1280)
    parser.add_argument("--height", type=int, default=720)
    parser.add_argument(
        "--rehash-only",
        action="store_true",
        help="Refresh artifact_sha256.json for an existing completed INT-10 run.",
    )
    args = parser.parse_args()

    blender = args.blender.resolve()
    input_blend = args.input_blend.resolve()
    output_dir = args.output_dir.resolve()
    script = Path(__file__).resolve()

    if args.rehash_only:
        report_path = output_dir / "int10_internal_graybox_report.json"
        if not report_path.is_file():
            raise FileNotFoundError(report_path)
        artifact_records = []
        for artifact in sorted(
            [path for path in output_dir.rglob("*") if path.is_file()]
        ):
            if artifact.name == "artifact_sha256.json":
                continue
            artifact_records.append(
                {
                    "path": artifact.relative_to(output_dir).as_posix(),
                    "bytes": artifact.stat().st_size,
                    "sha256": sha256_file(artifact),
                }
            )
        manifest_path = output_dir / "artifact_sha256.json"
        write_json(
            manifest_path,
            {
                "schema_version": 1,
                "requirement_id": REQUIREMENT_ID,
                "stage": STAGE_ID,
                "generated_at": utc_now_iso(),
                "artifacts": artifact_records,
            },
        )
        print(
            json.dumps(
                {
                    "status": "artifact_hash_manifest_refreshed",
                    "manifest": str(manifest_path),
                    "artifact_count": len(artifact_records),
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return 0

    for required in (blender, input_blend, script):
        if not required.is_file():
            raise FileNotFoundError(required)
    actual_input_sha256 = sha256_file(input_blend)
    if actual_input_sha256 != EXPECTED_INPUT_SHA256:
        raise RuntimeError(
            "P40 approved input hash mismatch: "
            f"expected={EXPECTED_INPUT_SHA256} actual={actual_input_sha256}"
        )
    if output_dir.exists():
        blocking_outputs = [
            output_dir / "INT_10_INTERNAL_GRAYBOX_CANDIDATE.blend",
            output_dir / "int10_internal_graybox_report.json",
            output_dir / "int10_structure_manifest.json",
        ]
        if any(path.exists() for path in blocking_outputs):
            raise FileExistsError(
                "INT-10 candidate output already exists; refusing to overwrite: "
                f"{output_dir}"
            )
    else:
        output_dir.mkdir(parents=True, exist_ok=False)

    command = [
        str(blender),
        "--background",
        str(input_blend),
        "--python",
        str(script),
        "--",
        "--inside-blender",
        "--input-blend",
        str(input_blend),
        "--output-dir",
        str(output_dir),
        "--width",
        str(args.width),
        "--height",
        str(args.height),
    ]
    command_record = {
        "requirement_id": REQUIREMENT_ID,
        "stage": STAGE_ID,
        "started_at": utc_now_iso(),
        "cwd": str(ROOT),
        "command_argv": command,
        "input_sha256": actual_input_sha256,
    }
    write_json(output_dir / "command.json", command_record)

    completed = subprocess.run(
        command,
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    (output_dir / "blender_stdout.log").write_text(
        completed.stdout or "", encoding="utf-8"
    )
    (output_dir / "blender_stderr.log").write_text(
        completed.stderr or "", encoding="utf-8"
    )

    report_path = output_dir / "int10_internal_graybox_report.json"
    if completed.returncode != 0:
        write_json(
            output_dir / "execution_failed.json",
            {
                **command_record,
                "finished_at": utc_now_iso(),
                "returncode": completed.returncode,
                "status": "failed",
                "report_exists": report_path.is_file(),
            },
        )
        print(completed.stdout)
        print(completed.stderr, file=sys.stderr)
        return completed.returncode
    if not report_path.is_file():
        raise FileNotFoundError(report_path)

    report = json.loads(report_path.read_text(encoding="utf-8"))
    candidate_path = Path(report["candidate"]["path"])
    render_paths = [Path(item["path"]) for item in report["evidence_renders"]]
    required_artifacts = [candidate_path, *render_paths]
    for artifact in required_artifacts:
        if not artifact.is_file() or artifact.stat().st_size <= 1024:
            raise RuntimeError(f"Missing or empty INT-10 artifact: {artifact}")

    report["execution"] = {
        "finished_at": utc_now_iso(),
        "returncode": completed.returncode,
        "command_record": str(output_dir / "command.json"),
        "stdout_log": str(output_dir / "blender_stdout.log"),
        "stderr_log": str(output_dir / "blender_stderr.log"),
        "artifact_hash_manifest": str(output_dir / "artifact_sha256.json"),
    }
    report["candidate"]["bytes"] = candidate_path.stat().st_size
    report["candidate"]["sha256"] = sha256_file(candidate_path)
    for item in report["evidence_renders"]:
        render_path = Path(item["path"])
        item["bytes"] = render_path.stat().st_size
        item["sha256"] = sha256_file(render_path)
    write_json(report_path, report)

    artifact_records = []
    for artifact in sorted(
        [path for path in output_dir.rglob("*") if path.is_file()]
    ):
        if artifact.name == "artifact_sha256.json":
            continue
        artifact_records.append(
            {
                "path": artifact.relative_to(output_dir).as_posix(),
                "bytes": artifact.stat().st_size,
                "sha256": sha256_file(artifact),
            }
        )
    write_json(
        output_dir / "artifact_sha256.json",
        {
            "schema_version": 1,
            "requirement_id": REQUIREMENT_ID,
            "stage": STAGE_ID,
            "generated_at": utc_now_iso(),
            "artifacts": artifact_records,
        },
    )

    print(
        json.dumps(
            {
                "status": report["status"],
                "approval": report["approval"],
                "candidate": report["candidate"],
                "report": str(report_path),
                "render_count": len(report["evidence_renders"]),
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


def blender_args() -> argparse.Namespace:
    argv = sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else []
    parser = argparse.ArgumentParser()
    parser.add_argument("--inside-blender", action="store_true")
    parser.add_argument("--input-blend", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--width", required=True, type=int)
    parser.add_argument("--height", required=True, type=int)
    return parser.parse_args(argv)


def blender_main() -> int:
    import bmesh
    import bpy
    from mathutils import Vector

    args = blender_args()
    output_dir = args.output_dir.resolve()
    render_dir = output_dir / "renders"
    render_dir.mkdir(parents=True, exist_ok=True)
    input_blend = args.input_blend.resolve()

    if sha256_file(input_blend) != EXPECTED_INPUT_SHA256:
        raise RuntimeError("Approved P40 hash changed between host and Blender launch")
    if Path(bpy.data.filepath).resolve() != input_blend:
        raise RuntimeError(
            f"Blender opened unexpected input: {bpy.data.filepath}"
        )

    def matrix_values(obj: Any) -> list[float]:
        return [
            round(float(value), 9)
            for row in obj.matrix_world
            for value in row
        ]

    def protected_snapshot() -> dict[str, Any]:
        sensors = sorted(
            obj.name for obj in bpy.data.objects if obj.name.startswith("SENSOR_")
        )
        required_names = (
            sensors
            + PROTECTED_SEGMENTS
            + PROTECTED_LAYER_GROUPS
            + PROTECTED_LAYER_BANDS
        )
        records = {}
        missing = []
        for name in required_names:
            obj = bpy.data.objects.get(name)
            if obj is None:
                missing.append(name)
                continue
            records[name] = {
                "parent": obj.parent.name if obj.parent else None,
                "matrix_world": matrix_values(obj),
                "type": obj.type,
            }
        payload = {
            "sensor_names": sensors,
            "records": records,
            "missing": missing,
        }
        payload["sha256"] = hashlib.sha256(
            json.dumps(
                payload,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
        ).hexdigest()
        return payload

    before = protected_snapshot()
    if before["missing"]:
        raise RuntimeError(f"Protected nodes missing: {before['missing']}")
    if len(before["sensor_names"]) != 115:
        raise RuntimeError(
            f"Expected 115 sensors, found {len(before['sensor_names'])}"
        )
    if bpy.data.collections.get("INT10_INTERNAL_GRAYBOX"):
        raise RuntimeError("Input already contains INT10_INTERNAL_GRAYBOX")

    object_count_before = len(bpy.data.objects)
    mesh_count_before = len(bpy.data.meshes)
    material_count_before = len(bpy.data.materials)

    scene = bpy.context.scene
    scene.render.engine = "BLENDER_EEVEE"
    scene.render.resolution_x = args.width
    scene.render.resolution_y = args.height
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = "PNG"
    scene.render.film_transparent = False
    scene.view_settings.view_transform = "AgX"
    scene.view_settings.look = "AgX - Medium Low Contrast"
    scene.view_settings.exposure = 0.0
    scene.world.use_nodes = True
    background = scene.world.node_tree.nodes.get("Background")
    if background:
        background.inputs["Color"].default_value = (0.12, 0.12, 0.12, 1.0)
        background.inputs["Strength"].default_value = 0.72

    neutral_collection = bpy.data.collections.get("P40_LOOKDEV_NEUTRAL")
    presentation_collection = bpy.data.collections.get(
        "P40_PRESENTATION_INDUSTRIAL"
    )
    if neutral_collection is None or presentation_collection is None:
        raise RuntimeError("Approved P40 neutral/presentation light rigs are missing")
    for obj in neutral_collection.objects:
        obj.hide_render = False
        obj.hide_viewport = False
    for obj in presentation_collection.objects:
        obj.hide_render = True
        obj.hide_viewport = True

    master = bpy.data.collections.new("INT10_INTERNAL_GRAYBOX")
    scene.collection.children.link(master)
    master["bf3d_stage"] = STAGE_ID
    master["bf3d_requirement_id"] = REQUIREMENT_ID
    master["bf3d_confidence"] = "E"
    master["bf3d_derivation"] = "illustrative_graybox"
    master["bf3d_not_for_construction"] = True

    layer_specs = [
        {
            "id": "steel_shell",
            "collection": "INT10_L01_STEEL_SHELL",
            "material": "MI_INT10_STEEL_GRAYBOX",
            "color": (0.20, 0.23, 0.24),
            "metallic": 0.35,
            "roughness": 0.74,
        },
        {
            "id": "cooling_wall",
            "collection": "INT10_L02_COOLING_WALL",
            "material": "MI_INT10_COOLING_GRAYBOX",
            "color": (0.34, 0.24, 0.16),
            "metallic": 0.28,
            "roughness": 0.72,
        },
        {
            "id": "refractory_lining",
            "collection": "INT10_L03_REFRACTORY_LINING",
            "material": "MI_INT10_REFRACTORY_GRAYBOX",
            "color": (0.38, 0.27, 0.17),
            "metallic": 0.0,
            "roughness": 0.92,
        },
        {
            "id": "process_space",
            "collection": "INT10_L04_PROCESS_SPACE",
            "material": "MI_INT10_PROCESS_SPACE_GRAYBOX",
            "color": (0.19, 0.075, 0.035),
            "metallic": 0.0,
            "roughness": 0.70,
        },
    ]

    def new_material(spec: dict[str, Any]) -> Any:
        material = bpy.data.materials.new(spec["material"])
        material.use_nodes = True
        material.diffuse_color = (*spec["color"], 1.0)
        material["bf3d_confidence"] = "E"
        material["bf3d_derivation"] = "illustrative_graybox"
        material["bf3d_not_engineering_material"] = True
        nodes = material.node_tree.nodes
        links = material.node_tree.links
        nodes.clear()
        output = nodes.new("ShaderNodeOutputMaterial")
        output.location = (260.0, 0.0)
        bsdf = nodes.new("ShaderNodeBsdfPrincipled")
        bsdf.location = (0.0, 0.0)
        links.new(bsdf.outputs["BSDF"], output.inputs["Surface"])
        bsdf.inputs["Base Color"].default_value = (*spec["color"], 1.0)
        bsdf.inputs["Metallic"].default_value = spec["metallic"]
        bsdf.inputs["Roughness"].default_value = spec["roughness"]
        return material

    layer_runtime: dict[str, dict[str, Any]] = {}
    for spec in layer_specs:
        collection = bpy.data.collections.new(spec["collection"])
        master.children.link(collection)
        collection["bf3d_layer_id"] = spec["id"]
        collection["bf3d_confidence"] = "E"
        collection["bf3d_derivation"] = "illustrative_graybox"
        layer_runtime[spec["id"]] = {
            "spec": spec,
            "collection": collection,
            "material": new_material(spec),
            "objects": {},
        }

    def shell_thickness(h_m: float) -> float:
        if h_m <= 4.8:
            return 0.065
        if h_m <= 18.6:
            return 0.055
        return 0.045

    def cooling_thickness(h_m: float) -> float:
        if h_m <= 4.8:
            return 0.38
        if h_m <= 8.8:
            return 0.34
        if h_m <= 30.6:
            return 0.32
        if h_m <= 35.2:
            return 0.26
        return 0.22

    def refractory_thickness(h_m: float) -> float:
        if h_m <= 4.8:
            return 0.85
        if h_m <= 8.8:
            return 0.70
        if h_m <= 18.6:
            return 0.60
        if h_m <= 30.6:
            return 0.48
        return 0.35

    gaps_m = {
        "shell_to_cooling": 0.04,
        "cooling_to_refractory": 0.04,
        "refractory_to_process": 0.03,
    }
    analytic_profiles = []
    for item in PROFILE:
        h_m = float(item["h_m"])
        shell_outer = float(item["r_m"])
        shell_inner = shell_outer - shell_thickness(h_m)
        cooling_outer = shell_inner - gaps_m["shell_to_cooling"]
        cooling_inner = cooling_outer - cooling_thickness(h_m)
        refractory_outer = (
            cooling_inner - gaps_m["cooling_to_refractory"]
        )
        refractory_inner = refractory_outer - refractory_thickness(h_m)
        process_outer = (
            refractory_inner - gaps_m["refractory_to_process"]
        )
        if process_outer <= 0.45:
            raise RuntimeError(
                f"Process-space radius is not positive enough at h={h_m}: "
                f"{process_outer}"
            )
        analytic_profiles.append(
            {
                **item,
                "z_blender_m": h_m - 20.0,
                "steel_outer_r_m": shell_outer,
                "steel_inner_r_m": shell_inner,
                "cooling_outer_r_m": cooling_outer,
                "cooling_inner_r_m": cooling_inner,
                "refractory_outer_r_m": refractory_outer,
                "refractory_inner_r_m": refractory_inner,
                "process_outer_r_m": process_outer,
                "steel_thickness_m": shell_thickness(h_m),
                "cooling_thickness_m": cooling_thickness(h_m),
                "refractory_thickness_m": refractory_thickness(h_m),
            }
        )

    z_values = [item["z_blender_m"] for item in analytic_profiles]
    layer_profile_pairs = {
        "steel_shell": (
            [item["steel_outer_r_m"] for item in analytic_profiles],
            [item["steel_inner_r_m"] for item in analytic_profiles],
        ),
        "cooling_wall": (
            [item["cooling_outer_r_m"] for item in analytic_profiles],
            [item["cooling_inner_r_m"] for item in analytic_profiles],
        ),
        "refractory_lining": (
            [item["refractory_outer_r_m"] for item in analytic_profiles],
            [item["refractory_inner_r_m"] for item in analytic_profiles],
        ),
        "process_space": (
            [item["process_outer_r_m"] for item in analytic_profiles],
            None,
        ),
    }

    variants = {
        "full": {
            "angle_start_deg": 0.0,
            "angle_coverage_deg": 360.0,
            "segments": 96,
        },
        "half": {
            "angle_start_deg": 22.5,
            "angle_coverage_deg": 180.0,
            "segments": 48,
        },
        "quarter": {
            "angle_start_deg": 67.5,
            "angle_coverage_deg": 270.0,
            "segments": 72,
        },
    }

    def recalculate_normals(mesh: Any) -> None:
        bm = bmesh.new()
        bm.from_mesh(mesh)
        bmesh.ops.recalc_face_normals(bm, faces=list(bm.faces))
        bm.to_mesh(mesh)
        bm.free()
        mesh.update()

    def make_annular_mesh(
        name: str,
        outer_radii: list[float],
        inner_radii: list[float],
        variant: dict[str, Any],
    ) -> Any:
        full = math.isclose(variant["angle_coverage_deg"], 360.0)
        segment_count = int(variant["segments"])
        ring_count = segment_count if full else segment_count + 1
        start = math.radians(float(variant["angle_start_deg"]))
        coverage = math.radians(float(variant["angle_coverage_deg"]))
        angles = [
            start + coverage * index / segment_count
            for index in range(ring_count)
        ]
        vertices: list[tuple[float, float, float]] = []
        outer_indices: list[list[int]] = []
        inner_indices: list[list[int]] = []
        for z, outer_radius, inner_radius in zip(
            z_values, outer_radii, inner_radii
        ):
            outer_ring = []
            inner_ring = []
            for angle in angles:
                outer_ring.append(len(vertices))
                vertices.append(
                    (
                        outer_radius * math.cos(angle),
                        outer_radius * math.sin(angle),
                        z,
                    )
                )
            for angle in angles:
                inner_ring.append(len(vertices))
                vertices.append(
                    (
                        inner_radius * math.cos(angle),
                        inner_radius * math.sin(angle),
                        z,
                    )
                )
            outer_indices.append(outer_ring)
            inner_indices.append(inner_ring)

        faces: list[tuple[int, ...]] = []
        for height_index in range(len(z_values) - 1):
            for segment_index in range(segment_count):
                next_index = (
                    (segment_index + 1) % ring_count
                    if full
                    else segment_index + 1
                )
                faces.append(
                    (
                        outer_indices[height_index][segment_index],
                        outer_indices[height_index][next_index],
                        outer_indices[height_index + 1][next_index],
                        outer_indices[height_index + 1][segment_index],
                    )
                )
                faces.append(
                    (
                        inner_indices[height_index][next_index],
                        inner_indices[height_index][segment_index],
                        inner_indices[height_index + 1][segment_index],
                        inner_indices[height_index + 1][next_index],
                    )
                )
        for segment_index in range(segment_count):
            next_index = (
                (segment_index + 1) % ring_count
                if full
                else segment_index + 1
            )
            faces.append(
                (
                    outer_indices[0][next_index],
                    outer_indices[0][segment_index],
                    inner_indices[0][segment_index],
                    inner_indices[0][next_index],
                )
            )
            top = len(z_values) - 1
            faces.append(
                (
                    outer_indices[top][segment_index],
                    outer_indices[top][next_index],
                    inner_indices[top][next_index],
                    inner_indices[top][segment_index],
                )
            )
        if not full:
            for height_index in range(len(z_values) - 1):
                faces.append(
                    (
                        outer_indices[height_index][0],
                        inner_indices[height_index][0],
                        inner_indices[height_index + 1][0],
                        outer_indices[height_index + 1][0],
                    )
                )
                end = ring_count - 1
                faces.append(
                    (
                        inner_indices[height_index][end],
                        outer_indices[height_index][end],
                        outer_indices[height_index + 1][end],
                        inner_indices[height_index + 1][end],
                    )
                )
        mesh = bpy.data.meshes.new(name + "_MESH")
        mesh.from_pydata(vertices, [], faces)
        recalculate_normals(mesh)
        return mesh

    def make_process_mesh(
        name: str,
        outer_radii: list[float],
        variant: dict[str, Any],
    ) -> Any:
        full = math.isclose(variant["angle_coverage_deg"], 360.0)
        segment_count = int(variant["segments"])
        ring_count = segment_count if full else segment_count + 1
        start = math.radians(float(variant["angle_start_deg"]))
        coverage = math.radians(float(variant["angle_coverage_deg"]))
        angles = [
            start + coverage * index / segment_count
            for index in range(ring_count)
        ]
        vertices: list[tuple[float, float, float]] = []
        rings: list[list[int]] = []
        for z, radius in zip(z_values, outer_radii):
            ring = []
            for angle in angles:
                ring.append(len(vertices))
                vertices.append(
                    (
                        radius * math.cos(angle),
                        radius * math.sin(angle),
                        z,
                    )
                )
            rings.append(ring)
        axis_indices = []
        for z in z_values:
            axis_indices.append(len(vertices))
            vertices.append((0.0, 0.0, z))

        faces: list[tuple[int, ...]] = []
        for height_index in range(len(z_values) - 1):
            for segment_index in range(segment_count):
                next_index = (
                    (segment_index + 1) % ring_count
                    if full
                    else segment_index + 1
                )
                faces.append(
                    (
                        rings[height_index][segment_index],
                        rings[height_index][next_index],
                        rings[height_index + 1][next_index],
                        rings[height_index + 1][segment_index],
                    )
                )
        for segment_index in range(segment_count):
            next_index = (
                (segment_index + 1) % ring_count
                if full
                else segment_index + 1
            )
            faces.append(
                (
                    axis_indices[0],
                    rings[0][next_index],
                    rings[0][segment_index],
                )
            )
            top = len(z_values) - 1
            faces.append(
                (
                    axis_indices[top],
                    rings[top][segment_index],
                    rings[top][next_index],
                )
            )
        if not full:
            end = ring_count - 1
            for height_index in range(len(z_values) - 1):
                faces.append(
                    (
                        axis_indices[height_index],
                        rings[height_index][0],
                        rings[height_index + 1][0],
                        axis_indices[height_index + 1],
                    )
                )
                faces.append(
                    (
                        rings[height_index][end],
                        axis_indices[height_index],
                        axis_indices[height_index + 1],
                        rings[height_index + 1][end],
                    )
                )
        mesh = bpy.data.meshes.new(name + "_MESH")
        mesh.from_pydata(vertices, [], faces)
        recalculate_normals(mesh)
        return mesh

    created_objects = []
    for layer_id, runtime in layer_runtime.items():
        outer_radii, inner_radii = layer_profile_pairs[layer_id]
        for variant_name, variant in variants.items():
            object_name = (
                f"APPROX_GL02_INT10_{layer_id.upper()}_{variant_name.upper()}"
            )
            if inner_radii is None:
                mesh = make_process_mesh(object_name, outer_radii, variant)
            else:
                mesh = make_annular_mesh(
                    object_name, outer_radii, inner_radii, variant
                )
            obj = bpy.data.objects.new(object_name, mesh)
            runtime["collection"].objects.link(obj)
            obj.data.materials.append(runtime["material"])
            obj["bf3d_layer_id"] = layer_id
            obj["bf3d_variant"] = variant_name
            obj["bf3d_confidence"] = "E"
            obj["bf3d_derivation"] = "illustrative_graybox"
            obj["bf3d_not_for_construction"] = True
            obj["bf3d_profile_source"] = "furnace_profile.gl02.yaml"
            obj.hide_render = True
            obj.hide_viewport = True
            runtime["objects"][variant_name] = obj
            created_objects.append(obj)

    hidden_explanatory_objects = []
    for obj in bpy.data.objects:
        lowered = obj.name.lower()
        if any(token in lowered for token in EXPLANATORY_INTERNAL_TOKENS):
            obj.hide_render = True
            obj.hide_viewport = True
            hidden_explanatory_objects.append(obj.name)

    source_mesh_visibility = {}
    for obj in bpy.data.objects:
        if obj in created_objects or obj.type != "MESH":
            continue
        source_mesh_visibility[obj.name] = {
            "hide_render": bool(obj.hide_render),
            "hide_viewport": bool(obj.hide_viewport),
        }
        obj.hide_render = True
        obj.hide_viewport = True

    def show_variant(
        variant_name: str, visible_layer_ids: list[str]
    ) -> None:
        for layer_id, runtime in layer_runtime.items():
            for name, obj in runtime["objects"].items():
                visible = (
                    name == variant_name and layer_id in visible_layer_ids
                )
                obj.hide_render = not visible
                obj.hide_viewport = not visible

    render_specs = [
        {
            "id": "front",
            "file": "INT10_FRONT.png",
            "camera": "CAM_GLOBAL_FRONT",
            "variant": "full",
            "visible_layers": ["steel_shell"],
            "purpose": "full_external_envelope_front",
        },
        {
            "id": "side",
            "file": "INT10_SIDE.png",
            "camera": "CAM_GLOBAL_LEFT",
            "variant": "full",
            "visible_layers": ["steel_shell"],
            "purpose": "full_external_envelope_side",
        },
        {
            "id": "half_cut",
            "file": "INT10_HALF_CUT.png",
            "camera": "CAM_GLOBAL_FRONT",
            "variant": "half",
            "visible_layers": [
                "steel_shell",
                "cooling_wall",
                "refractory_lining",
                "process_space",
            ],
            "purpose": "half_section_four_layer_readability",
        },
        {
            "id": "quarter_cut",
            "file": "INT10_QUARTER_CUT.png",
            "camera": "CAM_GLOBAL_RIGHT",
            "variant": "quarter",
            "visible_layers": [
                "steel_shell",
                "cooling_wall",
                "refractory_lining",
                "process_space",
            ],
            "purpose": "quarter_section_four_layer_readability",
        },
    ]

    evidence_renders = []
    for spec in render_specs:
        camera = bpy.data.objects.get(spec["camera"])
        if camera is None or camera.type != "CAMERA":
            raise RuntimeError(f"Fixed P40 camera missing: {spec['camera']}")
        show_variant(spec["variant"], spec["visible_layers"])
        scene.camera = camera
        render_path = render_dir / spec["file"]
        scene.render.filepath = str(render_path)
        bpy.ops.render.render(write_still=True)
        if not render_path.is_file() or render_path.stat().st_size <= 1024:
            raise RuntimeError(f"Render failed: {render_path}")
        evidence_renders.append(
            {
                **spec,
                "path": str(render_path),
                "resolution_px": [args.width, args.height],
                "engine": "BLENDER_EEVEE",
                "lookdev": "P40_NEUTRAL_APPROVED",
                "old_explanatory_objects_hidden": True,
            }
        )

    show_variant(
        "quarter",
        [
            "steel_shell",
            "cooling_wall",
            "refractory_lining",
            "process_space",
        ],
    )
    scene.camera = bpy.data.objects["CAM_GLOBAL_RIGHT"]
    scene["bf3d_stage"] = "INT_10_INTERNAL_GRAYBOX_CANDIDATE"
    scene["bf3d_requirement_id"] = REQUIREMENT_ID
    scene["bf3d_status"] = "candidate_ready_for_visual_review"
    scene["bf3d_approval"] = "not_granted_visual_review_required"
    scene["bf3d_input_sha256"] = EXPECTED_INPUT_SHA256
    scene["bf3d_change_dimension"] = "internal_four_layer_graybox_only"
    scene["bf3d_not_for_construction"] = True

    after = protected_snapshot()
    protected_contract = {
        "sensor_count_before": len(before["sensor_names"]),
        "sensor_count_after": len(after["sensor_names"]),
        "protected_segment_count": len(PROTECTED_SEGMENTS),
        "protected_layer_group_count": len(PROTECTED_LAYER_GROUPS),
        "protected_layer_band_count": len(PROTECTED_LAYER_BANDS),
        "before_sha256": before["sha256"],
        "after_sha256": after["sha256"],
        "names_parents_matrices_unchanged": before["sha256"] == after["sha256"],
        "missing_before": before["missing"],
        "missing_after": after["missing"],
    }
    if not protected_contract["names_parents_matrices_unchanged"]:
        raise RuntimeError("Protected names, parents or matrices changed")

    def mesh_audit(obj: Any) -> dict[str, Any]:
        bm = bmesh.new()
        bm.from_mesh(obj.data)
        non_manifold_edges = sum(1 for edge in bm.edges if not edge.is_manifold)
        result = {
            "vertices": len(bm.verts),
            "edges": len(bm.edges),
            "faces": len(bm.faces),
            "non_manifold_edges": non_manifold_edges,
        }
        bm.free()
        return result

    object_audits = {
        obj.name: mesh_audit(obj) for obj in created_objects
    }
    if any(item["non_manifold_edges"] for item in object_audits.values()):
        raise RuntimeError("One or more INT-10 meshes are non-manifold")

    structure_manifest = {
        "schema_version": "bf3d.int10.structure.v1",
        "requirement_id": REQUIREMENT_ID,
        "stage": STAGE_ID,
        "status": "candidate_ready_for_visual_review",
        "confidence_contract": {
            "evidence": "E",
            "derivation": "illustrative_graybox",
            "engineering_dimensions_claimed": False,
            "materials_claimed_as_built": False,
        },
        "coordinate_contract": {
            "blender_axis": "Z-up",
            "unit": "m",
            "height_rule": "z_blender_m = plant_elevation_m - 20.0",
            "profile_confidence": "approximate_until_real_cad_dimensions",
        },
        "source_profile": PROFILE,
        "analytic_profiles": analytic_profiles,
        "radial_visual_separation_gaps_m": gaps_m,
        "variants": variants,
        "layers": [
            {
                "order_outside_to_inside": index + 1,
                "layer_id": spec["id"],
                "collection": spec["collection"],
                "material": spec["material"],
                "objects": {
                    name: runtime["objects"][name].name
                    for name in ("full", "half", "quarter")
                },
                "confidence": "E",
                "derivation": "illustrative_graybox",
            }
            for index, (spec, runtime) in enumerate(
                (
                    (entry, layer_runtime[entry["id"]])
                    for entry in layer_specs
                )
            )
        ],
        "thickness_assumptions": {
            "steel_shell_m": {
                "hearth": 0.065,
                "bosh_belly": 0.055,
                "stack_throat": 0.045,
                "source": "furnace_profile.gl02.yaml industrial_shell baseline",
                "confidence": "E",
            },
            "cooling_wall_m": {
                "hearth": 0.38,
                "tuyere": 0.34,
                "bosh_to_lower_stack": 0.32,
                "upper_stack": 0.26,
                "throat": 0.22,
                "source": "illustrative INT-10 graybox assumption",
                "confidence": "E",
            },
            "refractory_lining_m": {
                "hearth": 0.85,
                "tuyere": 0.70,
                "bosh_belly": 0.60,
                "stack": 0.48,
                "throat": 0.35,
                "source": "illustrative INT-10 graybox assumption",
                "confidence": "E",
            },
        },
        "mesh_audit": object_audits,
    }
    structure_manifest_path = output_dir / "int10_structure_manifest.json"
    write_json(structure_manifest_path, structure_manifest)

    candidate_path = output_dir / "INT_10_INTERNAL_GRAYBOX_CANDIDATE.blend"
    bpy.ops.wm.save_as_mainfile(
        filepath=str(candidate_path), check_existing=False
    )
    if not candidate_path.is_file():
        raise RuntimeError("Blender candidate was not saved")

    all_created_names = sorted(obj.name for obj in created_objects)
    report = {
        "schema_version": "bf3d.int10.graybox.v1",
        "requirement_id": REQUIREMENT_ID,
        "stage": STAGE_ID,
        "status": "candidate_ready_for_visual_review",
        "approval": "not_granted_visual_review_required",
        "generated_at": utc_now_iso(),
        "single_changed_dimension": "internal_four_layer_graybox_only",
        "input": {
            "path": str(input_blend),
            "sha256": EXPECTED_INPUT_SHA256,
            "approval_record": str(
                input_blend.parent / "p40_visual_review.json"
            ),
            "approval_state": "approved",
            "read_only_source": True,
        },
        "blender": {
            "version": bpy.app.version_string,
            "binary_path": bpy.app.binary_path,
            "background": bool(bpy.app.background),
            "render_engine": scene.render.engine,
        },
        "lookdev_camera_contract": {
            "preset": str(
                HERE / "web" / "presets" / "lookdev_camera_v1.json"
            ),
            "lookdev": "P40 neutral approved",
            "view_transform": "AgX",
            "look": "AgX - Medium Low Contrast",
            "exposure_ev": 0.0,
            "cameras_used": sorted(
                {item["camera"] for item in evidence_renders}
            ),
        },
        "candidate": {
            "path": str(candidate_path),
            "bytes": candidate_path.stat().st_size,
            "sha256": None,
        },
        "structure_manifest": str(structure_manifest_path),
        "created_collection": master.name,
        "created_layer_collections": [
            spec["collection"] for spec in layer_specs
        ],
        "created_object_count": len(created_objects),
        "created_objects": all_created_names,
        "object_counts": {
            "before": object_count_before,
            "after": len(bpy.data.objects),
            "delta": len(bpy.data.objects) - object_count_before,
        },
        "mesh_counts": {
            "before": mesh_count_before,
            "after": len(bpy.data.meshes),
            "delta": len(bpy.data.meshes) - mesh_count_before,
        },
        "material_counts": {
            "before": material_count_before,
            "after": len(bpy.data.materials),
            "delta": len(bpy.data.materials) - material_count_before,
        },
        "protected_contract": protected_contract,
        "geometry_checks": {
            "all_created_meshes_manifold": all(
                item["non_manifold_edges"] == 0
                for item in object_audits.values()
            ),
            "minimum_process_radius_m": min(
                item["process_outer_r_m"] for item in analytic_profiles
            ),
            "positive_layer_thicknesses": all(
                item["steel_thickness_m"] > 0
                and item["cooling_thickness_m"] > 0
                and item["refractory_thickness_m"] > 0
                for item in analytic_profiles
            ),
            "minimum_analytic_radial_clearance_m": min(gaps_m.values()),
            "obvious_radial_intersections_by_contract": False,
        },
        "hidden_explanatory_objects": sorted(
            set(hidden_explanatory_objects)
        ),
        "hidden_explanatory_object_count": len(
            set(hidden_explanatory_objects)
        ),
        "source_meshes_hidden_for_graybox_evidence_count": len(
            source_mesh_visibility
        ),
        "evidence_renders": evidence_renders,
        "stop_lines": [
            "Do not promote this candidate without independent visual review.",
            "Do not replace the formal GLB from this INT-10 stage.",
            "Do not relabel E/illustrative thicknesses or materials as measured/as-built.",
            "Stop if any of the 115 sensors, five furnace segments, ten L7-L16 groups or ten layer bands change name, parent or world matrix.",
            "Engineering drawings or an approved survey are required before layer thicknesses become M/engineering-confirmed.",
        ],
        "production_blockers": [
            "actual_shell_and_lining_thicknesses_pending_engineering_drawing",
            "cooling_stave_material_and_segment_layout_pending_equipment_record",
            "skull_and_residual_lining_state_pending_model_or_measurement",
            "candidate_pending_visual_review",
        ],
        "formal_asset_changes": {
            "formal_glb_modified": False,
            "p40_input_modified": False,
            "p50_modified": False,
            "p60_modified": False,
            "frontend_modified": False,
        },
    }
    report_path = output_dir / "int10_internal_graybox_report.json"
    write_json(report_path, report)
    print(
        json.dumps(
            {
                "status": report["status"],
                "approval": report["approval"],
                "candidate": str(candidate_path),
                "report": str(report_path),
                "render_count": len(evidence_renders),
                "protected_contract": protected_contract,
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    if "--inside-blender" in sys.argv:
        raise SystemExit(blender_main())
    raise SystemExit(host_main())
