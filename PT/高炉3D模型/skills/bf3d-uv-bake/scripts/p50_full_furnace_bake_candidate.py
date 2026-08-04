"""Build a guarded, shared-atlas PBR bake candidate for the five GL02 shell zones.

This stage intentionally stops at a BLEND candidate.  It never overwrites the
production GLB and it does not claim glTF approval; P60 owns export/validator
and browser handoff.
"""

from __future__ import annotations

import argparse
import json
import math
import statistics
import sys
import time
from pathlib import Path
from typing import Any

import bpy
import numpy as np


SKILL_ROOT = Path(__file__).resolve().parents[2]
AUDIT_DIR = SKILL_ROOT / "bf3d-geometry-audit" / "scripts"
UV_DIR = SKILL_ROOT / "bf3d-uv-bake" / "scripts"
sys.path[:0] = [str(AUDIT_DIR), str(UV_DIR)]
import p00_import_audit as p00  # noqa: E402
import p20_shaft_uv_candidate as p20  # noqa: E402
import p21_shaft_bake_test as p21  # noqa: E402


TARGETS = (
    "APPROX_GL02_FURNACE_HEARTH",
    "APPROX_GL02_FURNACE_BOSH",
    "APPROX_GL02_FURNACE_BELLY",
    "APPROX_GL02_FURNACE_SHAFT",
    "APPROX_GL02_FURNACE_THROAT",
)
EXPECTED_LAYERS = tuple(f"L{index}" for index in range(7, 17))
EXPECTED_SECTORS = tuple("ABCDEFGH")
UV_NAME = "P50_UV0"
SOURCE_MATERIAL_NAME = "APPROX_matte_weathered_steel"
BAKED_MATERIAL_NAME = "P50_GL02_FULL_FURNACE_BAKED_STEEL"
EXPECTED_INPUT_SHA256 = "03635cf6608a54c4a671fb4d84adcb9451a36fe47cea7b564af2d4d3b69b2256"
ALLOWED_INPUT_STAGES = {
    "P40_FIXED_LOOKDEV_CANDIDATE",
    "P40_LOOKDEV_APPROVED",
    "P40_FIXED_LOOKDEV_APPROVED",
}
PROCEDURAL_NODE_TYPES = {
    "ShaderNodeTexNoise",
    "ShaderNodeTexVoronoi",
    "ShaderNodeTexMusgrave",
    "ShaderNodeTexWave",
    "ShaderNodeTexMagic",
    "ShaderNodeTexGradient",
    "ShaderNodeTexWhiteNoise",
}
NORMAL_BAKE_ENCODING_AMPLIFICATION = 4.0
NORMAL_RUNTIME_SCALE = 1.0 / NORMAL_BAKE_ENCODING_AMPLIFICATION
NORMAL_MIN_XY_RANGE = 2.0 / 255.0
NORMAL_MIN_XY_STD_NORM = 1.0 / 510.0
AO_MODE = "local_contact_whitelist_v1"
AO_DETAIL_OCCLUDERS = (
    "APPROX_GL02_P35_shell_welds",
    "APPROX_GL02_shell_stiffener_rings",
    "APPROX_GL02_P35_tuyere_flange_bodies",
    "APPROX_GL02_P35_tuyere_bolts",
)
AO_DISTANCE_M = 0.12
AO_STRENGTH = 0.28
AO_FLOOR = 0.78
AO_MIN_ACTIVE_VALUE = 0.775
AO_MIN_MEAN = 0.94
AO_MAX_MEAN = 0.998
AO_MIN_MEDIAN = 0.97
AO_MIN_STD = 0.004
AO_MAX_STD = 0.06
AO_DARK_THRESHOLD = 0.98
AO_MIN_DARK_RATIO = 0.005
AO_MAX_DARK_RATIO = 0.18
AO_DEEP_THRESHOLD = 0.82
AO_MAX_DEEP_RATIO = 0.02
AO_MIN_RANGE = 0.03
METALLIC_EXPOSURE_RAMP_LOW = 0.15
METALLIC_EXPOSURE_RAMP_HIGH = 0.85
METALLIC_EXPOSURE_RAMP_LOW_VALUE = 0.08
METALLIC_EXPOSURE_RAMP_HIGH_VALUE = 1.0
METALLIC_COATED_STEEL_VALUE = 0.04
METALLIC_BARE_STEEL_VALUE = 0.62
METALLIC_MAX_ACTIVE_VALUE = 0.66
METALLIC_MIN_P95_P05_SPREAD = 0.18
METALLIC_MAX_P95_P05_SPREAD = 0.62
METALLIC_NEAR_BINARY_LOW = 0.06
METALLIC_NEAR_BINARY_HIGH = 0.80
METALLIC_MAX_NEAR_BINARY_RATIO = 0.12
METALLIC_ADJACENT_LARGE_DELTA = 0.25
METALLIC_MAX_ADJACENT_DELTA_P95 = 0.36
METALLIC_MAX_ADJACENT_LARGE_DELTA_RATIO = 0.10
METALLIC_LOCAL_IMPULSE_DELTA = 0.20
METALLIC_MAX_LOCAL_IMPULSE_RATIO = 0.08
ATLAS_LAYOUT_ID = "object_grouped_3col_v1"
ATLAS_REFERENCE_SIZE = 1024
ATLAS_REFERENCE_MARGIN_PX = 4
ATLAS_OUTER_MARGIN_PX = 6
ATLAS_ISLAND_GAP_PX = 10
ATLAS_MIN_ACTIVE_PIXEL_RATIO = 0.55
ATLAS_MAX_DENSITY_RELATIVE_SPREAD = 0.005
ATLAS_COLUMNS = (
    (
        ("APPROX_GL02_FURNACE_HEARTH", 0, 90),
        ("APPROX_GL02_FURNACE_HEARTH", 1, 90),
    ),
    (
        ("APPROX_GL02_FURNACE_BOSH", 0, 0),
        ("APPROX_GL02_FURNACE_BOSH", 1, 0),
        ("APPROX_GL02_FURNACE_BELLY", 0, 0),
        ("APPROX_GL02_FURNACE_SHAFT", 0, 0),
        ("APPROX_GL02_FURNACE_SHAFT", 1, 0),
        ("APPROX_GL02_FURNACE_SHAFT", 2, 0),
    ),
    (
        ("APPROX_GL02_FURNACE_THROAT", 0, 90),
        ("APPROX_GL02_FURNACE_THROAT", 1, 90),
    ),
)


def parse_args() -> argparse.Namespace:
    argv = sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else []
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-glb", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--texture-size", type=int, default=512)
    parser.add_argument("--margin", type=int, default=8)
    parser.add_argument("--samples", type=int, default=16)
    parser.add_argument("--render-size", type=int, default=640)
    parser.add_argument("--skip-render", action="store_true")
    args = parser.parse_args(argv)
    if args.texture_size < 64 or args.texture_size > 4096 or args.texture_size & (args.texture_size - 1):
        parser.error("--texture-size must be a power of two between 64 and 4096")
    if args.margin < 2 or args.margin * 8 >= args.texture_size:
        parser.error("--margin must leave usable atlas space")
    if args.samples < 1:
        parser.error("--samples must be positive")
    return args


def matrix_values(obj: bpy.types.Object) -> list[float]:
    return [round(float(obj.matrix_world[row][column]), 9) for row in range(4) for column in range(4)]


def custom_properties(obj: bpy.types.Object) -> dict[str, Any]:
    return {
        key: p00.json_value(value)
        for key, value in sorted(obj.items())
        if not key.startswith("_")
    }


def layer_snapshot() -> dict[str, Any]:
    result: dict[str, Any] = {}
    for layer in EXPECTED_LAYERS:
        group_name = f"GL02_FURNACE_TEMP_LAYER_{layer}"
        band_name = f"APPROX_GL02_TEMP_LAYER_BAND_{layer}"
        sensor_group_name = f"GL02_SENSOR_LAYER_{layer}"
        group = bpy.data.objects.get(group_name)
        band = bpy.data.objects.get(band_name)
        sensor_group = bpy.data.objects.get(sensor_group_name)
        result[layer] = {
            "group": {
                "exists": group is not None,
                "parent": group.parent.name if group and group.parent else None,
                "matrix": matrix_values(group) if group else None,
                "properties": custom_properties(group) if group else None,
            },
            "band": {
                "exists": band is not None,
                "parent": band.parent.name if band and band.parent else None,
                "matrix": matrix_values(band) if band else None,
                "properties": custom_properties(band) if band else None,
                "hide_render": bool(band.hide_render) if band else None,
                "hide_viewport": bool(band.hide_viewport) if band else None,
                "geometry_sha256": p21.geometry_sha256(band.data) if band and band.type == "MESH" else None,
                "materials": [material.name if material else None for material in band.data.materials]
                if band and band.type == "MESH"
                else None,
            },
            "sensor_group": {
                "exists": sensor_group is not None,
                "children": sorted(child.name for child in sensor_group.children) if sensor_group else [],
            },
        }
    return result


def exact_layer_contract(snapshot: dict[str, Any]) -> bool:
    for layer in EXPECTED_LAYERS:
        item = snapshot[layer]
        expected_sensors = sorted(f"SENSOR_T_body_{layer}_{sector}" for sector in EXPECTED_SECTORS)
        if not item["group"]["exists"] or not item["band"]["exists"]:
            return False
        if item["band"]["parent"] != f"GL02_FURNACE_TEMP_LAYER_{layer}":
            return False
        if item["band"]["properties"].get("layer_id") != layer:
            return False
        if item["sensor_group"]["children"] != expected_sensors:
            return False
    return True


def hide_render_snapshot() -> dict[str, bool]:
    return {
        obj.name: bool(obj.hide_render)
        for obj in sorted(bpy.data.objects, key=lambda item: item.name)
    }


def restore_hide_render(snapshot: dict[str, bool]) -> None:
    if set(snapshot) != {obj.name for obj in bpy.data.objects}:
        raise RuntimeError("Object set changed while restoring hide_render state")
    for name, hidden in snapshot.items():
        bpy.data.objects[name].hide_render = hidden


def mesh_geometry_snapshot() -> dict[str, str]:
    return {
        obj.name: p21.geometry_sha256(obj.data)
        for obj in sorted(bpy.data.objects, key=lambda item: item.name)
        if obj.type == "MESH"
    }


def clear_uv_layers(mesh: bpy.types.Mesh) -> None:
    while mesh.uv_layers:
        mesh.uv_layers.remove(mesh.uv_layers[0])


def recover_single_island_design(obj: bpy.types.Object) -> dict[str, Any]:
    """Recover P20 design metadata after its one-island minimum-gap edge case.

    P20 has already finished creating the UVs and seam flags before its final
    ``min(gaps)`` call.  A two-row cylindrical/frustum object has one island,
    therefore no pairwise gap exists.  This function reconstructs only the
    report metadata needed by the shared P50 repacker; it does not modify UVs.
    """

    mesh = obj.data
    uv_layer = mesh.uv_layers.get(UV_NAME)
    if uv_layer is None:
        raise RuntimeError(f"{obj.name} did not retain the P20 UV after the one-island edge case")
    world_by_vertex = {
        vertex.index: obj.matrix_world @ vertex.co
        for vertex in mesh.vertices
    }
    center_x = statistics.mean(float(value.x) for value in world_by_vertex.values())
    center_y = statistics.mean(float(value.y) for value in world_by_vertex.values())
    row_vertices: dict[float, list[int]] = {}
    for vertex in mesh.vertices:
        world = world_by_vertex[vertex.index]
        row_vertices.setdefault(round(float(world.z), 6), []).append(vertex.index)
    if len(row_vertices) != 2:
        raise RuntimeError(
            f"Single-island recovery expected two profile rows, got {len(row_vertices)} on {obj.name}"
        )
    rows = []
    for z_value in sorted(row_vertices):
        radii = [
            math.hypot(
                float(world_by_vertex[index].x) - center_x,
                float(world_by_vertex[index].y) - center_y,
            )
            for index in row_vertices[z_value]
        ]
        rows.append(
            {
                "index": len(rows),
                "z": z_value,
                "radius": statistics.mean(radii),
                "vertices": len(row_vertices[z_value]),
            }
        )
    lower, upper = rows
    dr = float(upper["radius"]) - float(lower["radius"])
    dz = float(upper["z"]) - float(lower["z"])
    slant = math.hypot(dz, dr)
    q_value = abs(dr)
    mapping = "annular_sector" if q_value > 1e-9 else "cylinder_fallback"
    sector_angle = math.tau * q_value / slant if q_value > 1e-9 else 0.0
    raw_coordinates = []
    seam_faces = 0
    for polygon in mesh.polygons:
        values = [
            p20.phase_u(world_by_vertex[mesh.loops[index].vertex_index], center_x, center_y)
            for index in polygon.loop_indices
        ]
        wraps_seam = max(values) - min(values) > 0.5
        seam_faces += int(wraps_seam)
        for loop_index, phase in zip(polygon.loop_indices, values):
            if wraps_seam and phase < 0.5:
                phase += 1.0
            world = world_by_vertex[mesh.loops[loop_index].vertex_index]
            radius = math.hypot(float(world.x) - center_x, float(world.y) - center_y)
            if mapping == "annular_sector":
                rho = slant * radius / q_value
                psi = sector_angle * (phase - 0.5)
                raw_x = rho * math.sin(psi)
                raw_y = math.copysign(1.0, dr) * rho * math.cos(psi)
            else:
                raw_x = math.tau * radius * (phase - 0.5)
                raw_y = float(world.z) - float(lower["z"])
            raw_coordinates.append((raw_x, raw_y))
    min_x = min(value[0] for value in raw_coordinates)
    max_x = max(value[0] for value in raw_coordinates)
    min_y = min(value[1] for value in raw_coordinates)
    max_y = max(value[1] for value in raw_coordinates)
    width = max_x - min_x
    height = max_y - min_y
    available = 1.0 - 2.0 * p20.MARGIN
    scale = min(available / width, available / height)
    packed = {
        "band": 0,
        "min_u": 0.5 - width * scale * 0.5,
        "max_u": 0.5 + width * scale * 0.5,
        "min_v": p20.MARGIN,
        "max_v": p20.MARGIN + height * scale,
    }
    vertical_seams = sum(1 for edge in mesh.edges if edge.use_seam)
    band = {
        "index": 0,
        "lower_row": 0,
        "upper_row": 1,
        "z0": float(lower["z"]),
        "z1": float(upper["z"]),
        "r0": float(lower["radius"]),
        "r1": float(upper["radius"]),
        "dr": dr,
        "slant_m": slant,
        "sector_angle_rad": sector_angle,
        "mapping": mapping,
        "orientation_flip_x": False,
        "raw_bounds_m": {
            "min_x": min_x,
            "max_x": max_x,
            "min_y": min_y,
            "max_y": max_y,
        },
        "raw_width_m": width,
        "raw_height_m": height,
        "packed_bounds": packed,
    }
    return {
        "profile_rows": rows,
        "bands": [band],
        "island_bounds": [packed],
        "island_count": 1,
        "island_gap": p20.ISLAND_GAP,
        "minimum_packed_gap": None,
        "uv_units_per_meter": scale,
        "seam_location": "Blender +Y / default camera back side",
        "seam_faces": seam_faces,
        "vertical_seam_edges": vertical_seams,
        "horizontal_seam_edges": 0,
        "seam_edges": vertical_seams,
        "center_world_xy": [center_x, center_y],
        "compatibility_note": "Recovered metadata after P20 one-island empty-gap edge case.",
    }


def polygon_band_index(obj: bpy.types.Object, design: dict[str, Any], polygon: bpy.types.MeshPolygon) -> int:
    row_by_z = {
        round(float(row["z"]), 6): int(row["index"])
        for row in design["profile_rows"]
    }
    rows = [
        row_by_z[round(float((obj.matrix_world @ obj.data.vertices[index].co).z), 6)]
        for index in polygon.vertices
    ]
    return min(rows)


def build_shared_atlas_uv(
    targets: list[bpy.types.Object],
    texture_size: int,
    margin_px: int,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Repack the ten P20 shell islands into the guarded three-column layout.

    The layout keeps one UV scale across every furnace zone.  The hearth and
    throat islands rotate counter-clockwise by 90 degrees (positive
    determinant); no island is mirrored.  Padding is normalized from the
    approved 1K/4 px bake contract so the same UV layout can be reused by
    higher-resolution derivative bakes.
    """

    p20.UV_NAME = UV_NAME
    p20.MARGIN = 0.04
    p20.ISLAND_GAP = max(2.0 * margin_px / texture_size, 0.008)
    designs: dict[str, Any] = {}
    old_uv_names: dict[str, list[str]] = {}
    for obj in targets:
        old_uv_names[obj.name] = [layer.name for layer in obj.data.uv_layers]
        clear_uv_layers(obj.data)
        try:
            designs[obj.name] = p20.build_uv(obj)
        except ValueError as exc:
            if "min() iterable argument is empty" not in str(exc):
                raise
            designs[obj.name] = recover_single_island_design(obj)

    reference_outer_margin = ATLAS_OUTER_MARGIN_PX / ATLAS_REFERENCE_SIZE
    reference_island_gap = ATLAS_ISLAND_GAP_PX / ATLAS_REFERENCE_SIZE
    # If a caller requests proportionally more bake dilation than the approved
    # 1K contract, enlarge the padding instead of silently producing overlap.
    outer_margin = max(
        reference_outer_margin,
        (float(margin_px) + 2.0) / float(texture_size),
    )
    island_gap = max(
        reference_island_gap,
        (2.0 * float(margin_px) + 2.0) / float(texture_size),
    )
    bake_margin_uv = float(margin_px) / float(texture_size)

    band_lookup: dict[
        tuple[str, int],
        tuple[bpy.types.Object, dict[str, Any], dict[str, Any]],
    ] = {}
    for obj in targets:
        design = designs[obj.name]
        for band in design["bands"]:
            key = (obj.name, int(band["index"]))
            if key in band_lookup:
                raise RuntimeError(f"Duplicate P50 UV island before packing: {key}")
            band_lookup[key] = (obj, design, band)

    expected_layout_entries = [
        entry
        for column in ATLAS_COLUMNS
        for entry in column
    ]
    expected_keys = [(name, band_index) for name, band_index, _ in expected_layout_entries]
    actual_keys = sorted(band_lookup)
    if sorted(expected_keys) != actual_keys or len(set(expected_keys)) != 10:
        raise RuntimeError(
            "P50 three-column layout contract mismatch: "
            f"expected={sorted(expected_keys)}, actual={actual_keys}"
        )

    column_specs: list[dict[str, Any]] = []
    for column_index, entries in enumerate(ATLAS_COLUMNS):
        island_specs = []
        for object_name, band_index, rotation_degrees in entries:
            _, _, band = band_lookup[(object_name, band_index)]
            raw_width = float(band["raw_width_m"])
            raw_height = float(band["raw_height_m"])
            if rotation_degrees == 90:
                packed_width = raw_height
                packed_height = raw_width
            elif rotation_degrees == 0:
                packed_width = raw_width
                packed_height = raw_height
            else:
                raise RuntimeError(f"Unsupported P50 island rotation: {rotation_degrees}")
            island_specs.append(
                {
                    "object": object_name,
                    "band": band_index,
                    "rotation_degrees": rotation_degrees,
                    "raw_width_m": raw_width,
                    "raw_height_m": raw_height,
                    "packed_width_m": packed_width,
                    "packed_height_m": packed_height,
                }
            )
        column_specs.append(
            {
                "index": column_index,
                "islands": island_specs,
                "max_width_m": max(item["packed_width_m"] for item in island_specs),
                "total_height_m": sum(item["packed_height_m"] for item in island_specs),
            }
        )

    available_width = (
        1.0
        - 2.0 * outer_margin
        - island_gap * (len(column_specs) - 1)
    )
    if available_width <= 0.0:
        raise RuntimeError("P50 atlas has no usable width after three-column padding")
    width_scale_cap = available_width / sum(
        float(column["max_width_m"])
        for column in column_specs
    )
    height_scale_caps = []
    for column in column_specs:
        available_height = (
            1.0
            - 2.0 * outer_margin
            - island_gap * (len(column["islands"]) - 1)
        )
        if available_height <= 0.0:
            raise RuntimeError(f"P50 atlas column {column['index']} has no usable height")
        height_scale_caps.append(
            available_height / float(column["total_height_m"])
        )
    uv_units_per_meter = min(width_scale_cap, *height_scale_caps)
    if uv_units_per_meter <= 0.0:
        raise RuntimeError("P50 atlas scale is not positive")

    packed_columns_width = (
        sum(float(column["max_width_m"]) * uv_units_per_meter for column in column_specs)
        + island_gap * (len(column_specs) - 1)
    )
    cursor_u = outer_margin + (
        (1.0 - 2.0 * outer_margin - packed_columns_width) * 0.5
    )
    atlas_islands: list[dict[str, Any]] = []
    packed_columns: list[dict[str, Any]] = []
    intra_column_gaps = []
    for column, height_scale_cap in zip(column_specs, height_scale_caps):
        column_width = float(column["max_width_m"]) * uv_units_per_meter
        column_content_height = (
            float(column["total_height_m"]) * uv_units_per_meter
            + island_gap * (len(column["islands"]) - 1)
        )
        cursor_v = outer_margin + (
            (1.0 - 2.0 * outer_margin - column_content_height) * 0.5
        )
        column_bounds = {
            "index": int(column["index"]),
            "min_u": cursor_u,
            "max_u": cursor_u + column_width,
            "min_v": cursor_v,
            "max_v": cursor_v + column_content_height,
            "max_width_m": float(column["max_width_m"]),
            "total_height_m": float(column["total_height_m"]),
            "height_scale_cap": float(height_scale_cap),
            "islands": [],
        }
        previous_max_v = None
        for island_spec in column["islands"]:
            object_name = str(island_spec["object"])
            band_index = int(island_spec["band"])
            rotation_degrees = int(island_spec["rotation_degrees"])
            obj, design, band = band_lookup[(object_name, band_index)]
            old_bounds = band["packed_bounds"]
            old_center_u = (
                float(old_bounds["min_u"]) + float(old_bounds["max_u"])
            ) * 0.5
            old_center_v = (
                float(old_bounds["min_v"]) + float(old_bounds["max_v"])
            ) * 0.5
            old_scale = float(design["uv_units_per_meter"])
            island_width = float(island_spec["packed_width_m"]) * uv_units_per_meter
            island_height = float(island_spec["packed_height_m"]) * uv_units_per_meter
            island_center_u = cursor_u + column_width * 0.5
            island_center_v = cursor_v + island_height * 0.5
            new_bounds = {
                "object": object_name,
                "band": band_index,
                "column": int(column["index"]),
                "rotation_degrees": rotation_degrees,
                "min_u": island_center_u - island_width * 0.5,
                "max_u": island_center_u + island_width * 0.5,
                "min_v": island_center_v - island_height * 0.5,
                "max_v": island_center_v + island_height * 0.5,
            }
            if previous_max_v is not None:
                intra_column_gaps.append(float(new_bounds["min_v"]) - previous_max_v)
            previous_max_v = float(new_bounds["max_v"])
            uv_layer = obj.data.uv_layers[UV_NAME]
            for polygon in obj.data.polygons:
                if polygon_band_index(obj, design, polygon) != band_index:
                    continue
                for loop_index in polygon.loop_indices:
                    old_uv = uv_layer.uv[loop_index].vector.copy()
                    raw_x = (float(old_uv.x) - old_center_u) / old_scale
                    raw_y = (float(old_uv.y) - old_center_v) / old_scale
                    if rotation_degrees == 90:
                        # Counter-clockwise rotation, determinant +1.
                        packed_x, packed_y = -raw_y, raw_x
                    else:
                        packed_x, packed_y = raw_x, raw_y
                    uv_layer.uv[loop_index].vector = (
                        island_center_u + packed_x * uv_units_per_meter,
                        island_center_v + packed_y * uv_units_per_meter,
                    )
            band["packed_bounds"] = new_bounds
            band["atlas_column"] = int(column["index"])
            band["rotation_degrees"] = rotation_degrees
            atlas_islands.append(new_bounds)
            column_bounds["islands"].append(
                {
                    "object": object_name,
                    "band": band_index,
                    "rotation_degrees": rotation_degrees,
                }
            )
            cursor_v = float(new_bounds["max_v"]) + island_gap
        packed_columns.append(column_bounds)
        cursor_u += column_width + island_gap

    for obj in targets:
        design = designs[obj.name]
        design["uv_units_per_meter"] = uv_units_per_meter
        design["island_gap"] = island_gap
        design["minimum_packed_gap"] = island_gap
        design["island_bounds"] = [
            island for island in atlas_islands if island["object"] == obj.name
        ]
        obj.data.uv_layers.active = obj.data.uv_layers[UV_NAME]
        obj.data.uv_layers[UV_NAME].active_render = True
        obj.data.update()

    metrics = {
        obj.name: p20.uv_metrics(obj, designs[obj.name])
        for obj in targets
    }
    density_values = [
        float(item["density"]["median_uv_per_meter"])
        for item in metrics.values()
    ]
    column_gaps = [
        float(packed_columns[index + 1]["min_u"])
        - float(packed_columns[index]["max_u"])
        for index in range(len(packed_columns) - 1)
    ]
    minimum_gap = min([*column_gaps, *intra_column_gaps])
    outer_margins = [
        value
        for island in atlas_islands
        for value in (
            float(island["min_u"]),
            1.0 - float(island["max_u"]),
            float(island["min_v"]),
            1.0 - float(island["max_v"]),
        )
    ]
    expanded_overlap_pairs = []
    pairwise_separations = []
    for first_index, first in enumerate(atlas_islands):
        for second in atlas_islands[first_index + 1 :]:
            separation_u = max(
                float(second["min_u"]) - float(first["max_u"]),
                float(first["min_u"]) - float(second["max_u"]),
                0.0,
            )
            separation_v = max(
                float(second["min_v"]) - float(first["max_v"]),
                float(first["min_v"]) - float(second["max_v"]),
                0.0,
            )
            pairwise_separations.append(max(separation_u, separation_v))
            expanded_intersects = (
                float(first["min_u"]) - bake_margin_uv
                < float(second["max_u"]) + bake_margin_uv
                and float(first["max_u"]) + bake_margin_uv
                > float(second["min_u"]) - bake_margin_uv
                and float(first["min_v"]) - bake_margin_uv
                < float(second["max_v"]) + bake_margin_uv
                and float(first["max_v"]) + bake_margin_uv
                > float(second["min_v"]) - bake_margin_uv
            )
            if expanded_intersects:
                expanded_overlap_pairs.append(
                    {
                        "first": [first["object"], first["band"]],
                        "second": [second["object"], second["band"]],
                    }
                )
    layout_keys = [
        (str(island["object"]), int(island["band"]))
        for island in atlas_islands
    ]
    orientation_counts = {
        "positive": sum(int(item["orientation"]["positive"]) for item in metrics.values()),
        "negative": sum(int(item["orientation"]["negative"]) for item in metrics.values()),
        "zero": sum(int(item["orientation"]["zero"]) for item in metrics.values()),
    }
    atlas = {
        "layout_id": ATLAS_LAYOUT_ID,
        "layout_reference_size": ATLAS_REFERENCE_SIZE,
        "layout_reference_margin_px": ATLAS_REFERENCE_MARGIN_PX,
        "uv_layer": UV_NAME,
        "objects": [obj.name for obj in targets],
        "old_uv_layers": old_uv_names,
        "islands": atlas_islands,
        "island_count": len(atlas_islands),
        "unique_island_count": len(set(layout_keys)),
        "expected_layout_keys": [[name, band_index] for name, band_index in expected_keys],
        "actual_layout_keys": [[name, band_index] for name, band_index in layout_keys],
        "layout_keys_match": sorted(layout_keys) == sorted(expected_keys),
        "columns": packed_columns,
        "column_count": len(packed_columns),
        "column_gaps_uv": column_gaps,
        "minimum_column_gap_uv": min(column_gaps),
        "intra_column_gaps_uv": intra_column_gaps,
        "minimum_intra_column_gap_uv": min(intra_column_gaps),
        "outer_margin_uv": outer_margin,
        "required_outer_margin_uv": outer_margin,
        "minimum_outer_margin_uv": min(outer_margins),
        "bake_margin_uv": bake_margin_uv,
        "required_gap_uv": island_gap,
        "minimum_gap_uv": minimum_gap,
        "pair_count": len(pairwise_separations),
        "minimum_pairwise_separation_uv": min(pairwise_separations),
        "expanded_overlap_pairs": expanded_overlap_pairs,
        "expanded_pair_count": len(pairwise_separations),
        "all_expanded_pairs_disjoint": not expanded_overlap_pairs,
        "orientation_counts": orientation_counts,
        "positive_orientation_only": (
            orientation_counts["negative"] == 0 and orientation_counts["zero"] == 0
        ),
        "uv_units_per_meter": uv_units_per_meter,
        "effective_texels_per_meter": uv_units_per_meter * texture_size,
        "width_scale_cap": width_scale_cap,
        "height_scale_caps": height_scale_caps,
        "density_relative_spread": (
            max(density_values) / min(density_values) - 1.0
            if min(density_values) > 0.0
            else math.inf
        ),
        "last_island_max_v": max(float(item["max_v"]) for item in atlas_islands),
    }
    return {"designs": designs, "metrics": metrics}, atlas


def find_material_socket(nodes: bpy.types.Nodes, node_name: str, preferred: str | None = None):
    node = nodes.get(node_name)
    if node is None:
        raise RuntimeError(f"Missing protected P30 node: {node_name}")
    if preferred and node.outputs.get(preferred):
        return node.outputs[preferred]
    if not node.outputs:
        raise RuntimeError(f"P30 node has no output: {node_name}")
    return node.outputs[0]


def amplify_normal_for_8bit_bake(nodes: bpy.types.Nodes) -> dict[str, float]:
    """Encode the approved subtle P30 bump above the 8-bit normal-map floor.

    P30 deliberately uses a very small 0.003 m bump distance for lookdev.  A
    direct 8-bit tangent-normal bake quantizes that signal to one flat
    ``(128, 128, 255)`` value.  The bake source therefore amplifies only the
    encoded normal amplitude; the baked material applies the reciprocal
    Normal Map strength so the reconstructed shading remains subtle.
    """

    bump = nodes.get("P30_MICRO_BUMP")
    if bump is None or bump.bl_idname != "ShaderNodeBump":
        raise RuntimeError("Missing protected P30 micro-bump node")
    distance = bump.inputs.get("Distance")
    strength = bump.inputs.get("Strength")
    if distance is None or strength is None:
        raise RuntimeError("P30 micro-bump inputs are incomplete")
    original_distance = float(distance.default_value)
    if original_distance <= 0.0:
        raise RuntimeError(f"P30 micro-bump distance must be positive, got {original_distance}")
    encoded_distance = original_distance * NORMAL_BAKE_ENCODING_AMPLIFICATION
    distance.default_value = encoded_distance
    return {
        "source_strength": float(strength.default_value),
        "source_distance": original_distance,
        "encoded_distance": encoded_distance,
        "encoding_amplification": NORMAL_BAKE_ENCODING_AMPLIFICATION,
        "runtime_normal_scale": NORMAL_RUNTIME_SCALE,
    }


def calibrate_metallic_for_bake(
    nodes: bpy.types.Nodes,
    links: bpy.types.NodeLinks,
) -> dict[str, Any]:
    """Soften only the transient P50 metallic bake graph.

    The approved P30 lookdev graph intentionally has a high-contrast exposed
    steel response.  At atlas resolution its nested masks quantize into dense
    near-binary pixels, which read as salt-and-pepper shimmer at browser
    distance.  P50 widens the final exposure transition and caps bare steel at
    a stable industrial value without touching P30/P40 or the rust/dust masks.
    """

    exposure = nodes.get("P30_METAL_EXPOSURE_MASK")
    mix = nodes.get("P30_METAL_COAT_STEEL")
    meso = nodes.get("P30_MESO")
    directional = nodes.get("P30_DIRECTIONAL_WEAR_WEIGHT")
    if exposure is None or exposure.bl_idname != "ShaderNodeValToRGB":
        raise RuntimeError("Missing protected P30 metallic exposure ramp")
    if mix is None or mix.bl_idname != "ShaderNodeMix":
        raise RuntimeError("Missing protected P30 coated/bare steel mix")
    if meso is None or meso.outputs.get("Fac") is None:
        raise RuntimeError("Missing protected P30 meso noise output")
    if directional is None or directional.outputs.get("Result") is None:
        raise RuntimeError("Missing protected P30 directional wear output")
    ramp = exposure.color_ramp
    if len(ramp.elements) != 2:
        raise RuntimeError(
            f"P30 metallic exposure ramp must have two elements, got {len(ramp.elements)}"
        )
    low, high = sorted(ramp.elements, key=lambda element: element.position)
    original = {
        "interpolation": ramp.interpolation,
        "low_position": float(low.position),
        "high_position": float(high.position),
        "low_value": float(low.color[0]),
        "high_value": float(high.color[0]),
        "coated_steel": float(mix.inputs[2].default_value),
        "bare_steel": float(mix.inputs[3].default_value),
        "exposure_input": [
            link.from_node.name
            for link in exposure.inputs["Fac"].links
        ],
    }
    continuous = nodes.new("ShaderNodeMath")
    continuous.name = "P50_METALLIC_CONTINUOUS_EXPOSURE"
    continuous.label = continuous.name
    continuous.operation = "MULTIPLY"
    links.new(meso.outputs["Fac"], continuous.inputs[0])
    links.new(directional.outputs["Result"], continuous.inputs[1])
    for link in list(exposure.inputs["Fac"].links):
        links.remove(link)
    links.new(continuous.outputs[0], exposure.inputs["Fac"])
    ramp.interpolation = "EASE"
    low.position = METALLIC_EXPOSURE_RAMP_LOW
    high.position = METALLIC_EXPOSURE_RAMP_HIGH
    low.color = (
        METALLIC_EXPOSURE_RAMP_LOW_VALUE,
        METALLIC_EXPOSURE_RAMP_LOW_VALUE,
        METALLIC_EXPOSURE_RAMP_LOW_VALUE,
        1.0,
    )
    high.color = (
        METALLIC_EXPOSURE_RAMP_HIGH_VALUE,
        METALLIC_EXPOSURE_RAMP_HIGH_VALUE,
        METALLIC_EXPOSURE_RAMP_HIGH_VALUE,
        1.0,
    )
    mix.inputs[2].default_value = METALLIC_COATED_STEEL_VALUE
    mix.inputs[3].default_value = METALLIC_BARE_STEEL_VALUE
    return {
        "scope": "P50 transient bake graph only",
        "source_node": exposure.name,
        "mix_node": mix.name,
        "original": original,
        "calibrated": {
            "interpolation": ramp.interpolation,
            "low_position": float(low.position),
            "high_position": float(high.position),
            "low_value": float(low.color[0]),
            "high_value": float(high.color[0]),
            "coated_steel": float(mix.inputs[2].default_value),
            "bare_steel": float(mix.inputs[3].default_value),
            "exposure_input": continuous.name,
        },
        "protected_downstream_masks": [
            "P30_METAL_OXIDATION",
            "P30_METAL_DRY_DUST",
            "P30_METAL_WATER",
        ],
    }


def make_bake_source(
    material: bpy.types.Material,
    ao_samples: int,
) -> tuple[bpy.types.Material, dict[str, Any]]:
    baked_source = material.copy()
    baked_source.name = "P50_TRANSIENT_FULL_FURNACE_BAKE_SOURCE"
    baked_source.use_nodes = True
    nodes = baked_source.node_tree.nodes
    links = baked_source.node_tree.links
    output = nodes.get("P30_OUTPUT")
    principled = nodes.get("P30_PRINCIPLED")
    if output is None or principled is None:
        raise RuntimeError("The approved P30 shell material graph is not present")
    emission = nodes.new("ShaderNodeEmission")
    emission.name = "P50_BAKE_EMISSION"
    emission.inputs["Strength"].default_value = 1.0
    image_target = nodes.new("ShaderNodeTexImage")
    image_target.name = "P50_ACTIVE_BAKE_TARGET"
    local_ao = nodes.new("ShaderNodeAmbientOcclusion")
    local_ao.name = "P50_LOCAL_CONTACT_AO"
    local_ao.samples = ao_samples
    local_ao.inside = False
    local_ao.only_local = False
    local_ao.inputs["Color"].default_value = (1.0, 1.0, 1.0, 1.0)
    local_ao.inputs["Distance"].default_value = AO_DISTANCE_M
    ao_remap = nodes.new("ShaderNodeMath")
    ao_remap.name = "P50_AO_STRENGTH_REMAP"
    ao_remap.operation = "MULTIPLY_ADD"
    ao_remap.inputs[1].default_value = AO_STRENGTH
    ao_remap.inputs[2].default_value = 1.0 - AO_STRENGTH
    links.new(local_ao.outputs["AO"], ao_remap.inputs[0])
    ao_floor = nodes.new("ShaderNodeMath")
    ao_floor.name = "P50_AO_FLOOR"
    ao_floor.operation = "MAXIMUM"
    ao_floor.inputs[1].default_value = AO_FLOOR
    links.new(ao_remap.outputs[0], ao_floor.inputs[0])
    normal_encoding = amplify_normal_for_8bit_bake(nodes)
    metallic_calibration = calibrate_metallic_for_bake(nodes, links)
    return baked_source, {
        "nodes": nodes,
        "links": links,
        "output": output,
        "principled": principled,
        "emission": emission,
        "image_target": image_target,
        "BaseColor": find_material_socket(nodes, "P30_COLOR_WATER_STREAK", "Color"),
        "Roughness": find_material_socket(nodes, "P30_ROUGHNESS_FINAL"),
        "Metallic": find_material_socket(nodes, "P30_METAL_WATER", "Result"),
        "AO": ao_floor.outputs[0],
        "ao_policy": {
            "mode": AO_MODE,
            "detail_occluders": list(AO_DETAIL_OCCLUDERS),
            "distance_m": AO_DISTANCE_M,
            "strength": AO_STRENGTH,
            "floor": AO_FLOOR,
            "samples": int(local_ao.samples),
            "inside": bool(local_ao.inside),
            "only_local": bool(local_ao.only_local),
            "selected_to_active": False,
            "cage_extrusion_m": 0.0,
            "max_ray_distance_m": 0.0,
        },
        "ao_visibility_audit": [],
        "normal_encoding": normal_encoding,
        "metallic_calibration": metallic_calibration,
    }


def configure_cycles(samples: int) -> dict[str, Any]:
    device = p21.configure_cycles(True)
    scene = bpy.context.scene
    scene.cycles.samples = samples
    scene.cycles.use_denoising = False
    return device


def create_image(name: str, size: int, colorspace: str) -> bpy.types.Image:
    existing = bpy.data.images.get(name)
    if existing:
        bpy.data.images.remove(existing)
    image = bpy.data.images.new(
        name,
        width=size,
        height=size,
        alpha=True,
        float_buffer=False,
        is_data=colorspace != "sRGB",
    )
    image.generated_color = (0.0, 0.0, 0.0, 0.0)
    image.colorspace_settings.name = colorspace
    return image


def activate_target(graph: dict[str, Any], image: bpy.types.Image) -> None:
    nodes = graph["nodes"]
    image_target = graph["image_target"]
    for node in nodes:
        node.select = False
    image_target.image = image
    image_target.select = True
    nodes.active = image_target


def select_only(obj: bpy.types.Object) -> None:
    if bpy.context.object and bpy.context.object.mode != "OBJECT":
        bpy.ops.object.mode_set(mode="OBJECT")
    bpy.ops.object.select_all(action="DESELECT")
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj


def suffix_for_size(size: int) -> str:
    return f"{size // 1024}K" if size >= 1024 and size % 1024 == 0 else f"{size}px"


def save_image(image: bpy.types.Image, path: Path, colorspace: str) -> dict[str, Any]:
    image.filepath_raw = str(path)
    image.file_format = "PNG"
    image.save()
    result = {
        "path": str(path),
        "bytes": path.stat().st_size,
        "sha256": p00.sha256_file(path),
        "width": int(image.size[0]),
        "height": int(image.size[1]),
        "colorspace": colorspace,
    }
    return result


def connect_emit(graph: dict[str, Any], source_socket) -> None:
    output = graph["output"]
    emission = graph["emission"]
    links = graph["links"]
    for link in list(output.inputs["Surface"].links):
        links.remove(link)
    for link in list(emission.inputs["Color"].links):
        links.remove(link)
    links.new(source_socket, emission.inputs["Color"])
    links.new(emission.outputs["Emission"], output.inputs["Surface"])


def restore_principled(graph: dict[str, Any]) -> None:
    output = graph["output"]
    links = graph["links"]
    for link in list(output.inputs["Surface"].links):
        links.remove(link)
    links.new(graph["principled"].outputs["BSDF"], output.inputs["Surface"])


def bake_local_contact_ao(
    targets: list[bpy.types.Object],
    graph: dict[str, Any],
    margin: int,
) -> None:
    graph["ao_visibility_audit"].clear()
    mesh_names = {
        obj.name
        for obj in bpy.data.objects
        if obj.type == "MESH"
    }
    missing = set(AO_DETAIL_OCCLUDERS) - mesh_names
    if missing:
        raise RuntimeError(f"Missing AO detail occluders: {sorted(missing)}")

    for index, target in enumerate(targets):
        before = hide_render_snapshot()
        allowed = {target.name, *AO_DETAIL_OCCLUDERS}
        entry: dict[str, Any] = {
            "target": target.name,
            "allowed_meshes": sorted(allowed),
        }
        try:
            for obj in bpy.data.objects:
                if obj.type == "MESH":
                    obj.hide_render = obj.name not in allowed
            visible_meshes = sorted(
                obj.name
                for obj in bpy.data.objects
                if obj.type == "MESH" and not obj.hide_render
            )
            entry.update(
                {
                    "visible_meshes": visible_meshes,
                    "visible_meshes_exact": visible_meshes == sorted(allowed),
                    "platform_excluded": bool(
                        bpy.data.objects["APPROX_GL02_maintenance_platforms"].hide_render
                    ),
                    "sensors_excluded": not any(
                        name.startswith("SENSOR_") for name in visible_meshes
                    ),
                    "temperature_bands_excluded": not any(
                        name.startswith("APPROX_GL02_TEMP_LAYER_BAND_")
                        for name in visible_meshes
                    ),
                }
            )
            select_only(target)
            bpy.ops.object.bake(
                type="EMIT",
                margin=margin,
                margin_type="EXTEND",
                use_selected_to_active=False,
                cage_extrusion=0.0,
                max_ray_distance=0.0,
                use_clear=index == 0,
                target="IMAGE_TEXTURES",
                save_mode="INTERNAL",
                uv_layer=UV_NAME,
            )
        finally:
            restore_hide_render(before)
            entry["hide_render_restored"] = hide_render_snapshot() == before
            graph["ao_visibility_audit"].append(entry)


def bake_channels(
    targets: list[bpy.types.Object],
    source_material: bpy.types.Material,
    graph: dict[str, Any],
    texture_dir: Path,
    size: int,
    margin: int,
) -> tuple[dict[str, bpy.types.Image], dict[str, dict[str, Any]], dict[str, float]]:
    for obj in targets:
        obj.data.materials.clear()
        obj.data.materials.append(source_material)
    images: dict[str, bpy.types.Image] = {}
    files: dict[str, dict[str, Any]] = {}
    timings: dict[str, float] = {}
    suffix = suffix_for_size(size)
    graph["ao_visibility_audit"].clear()

    for channel in ("BaseColor", "Roughness", "Metallic", "AO"):
        colorspace = "sRGB" if channel == "BaseColor" else "Non-Color"
        image = create_image(f"P50_GL02_{channel}_{suffix}", size, colorspace)
        images[channel] = image
        activate_target(graph, image)
        connect_emit(graph, graph[channel])
        started = time.perf_counter()
        if channel == "AO":
            bake_local_contact_ao(targets, graph, margin)
        else:
            for index, obj in enumerate(targets):
                select_only(obj)
                bpy.ops.object.bake(
                    type="EMIT",
                    margin=margin,
                    margin_type="EXTEND",
                    use_selected_to_active=False,
                    use_clear=index == 0,
                    target="IMAGE_TEXTURES",
                    save_mode="INTERNAL",
                    uv_layer=UV_NAME,
                )
        timings[channel] = time.perf_counter() - started
        files[channel] = save_image(
            image,
            texture_dir / f"P50_GL02_{channel}_{suffix}.png",
            colorspace,
        )

    restore_principled(graph)
    normal = create_image(f"P50_GL02_NormalGL_{suffix}", size, "Non-Color")
    images["NormalGL"] = normal
    activate_target(graph, normal)
    started = time.perf_counter()
    for index, obj in enumerate(targets):
        select_only(obj)
        bpy.ops.object.bake(
            type="NORMAL",
            normal_space="TANGENT",
            normal_r="POS_X",
            normal_g="POS_Y",
            normal_b="POS_Z",
            margin=margin,
            margin_type="ADJACENT_FACES",
            use_selected_to_active=False,
            use_clear=index == 0,
            target="IMAGE_TEXTURES",
            save_mode="INTERNAL",
            uv_layer=UV_NAME,
        )
    timings["NormalGL"] = time.perf_counter() - started
    files["NormalGL"] = save_image(
        normal,
        texture_dir / f"P50_GL02_NormalGL_{suffix}.png",
        "Non-Color",
    )
    return images, files, timings


def image_array(image: bpy.types.Image) -> np.ndarray:
    values = np.empty(len(image.pixels), dtype=np.float32)
    image.pixels.foreach_get(values)
    return values.reshape((-1, 4))


def disk_image_array(path: Path, colorspace: str) -> np.ndarray:
    loaded = bpy.data.images.load(str(path), check_existing=False)
    try:
        loaded.colorspace_settings.name = colorspace
        return image_array(loaded)
    finally:
        bpy.data.images.remove(loaded)


def normal_variation_metrics(
    image: bpy.types.Image,
    active: np.ndarray,
) -> dict[str, Any]:
    """Measure tangent X/Y variation so an 8-bit flat normal cannot pass."""

    values = image_array(image)
    rgb = values[active, :3] if np.any(active) else values[:, :3]
    xy = rgb[:, :2]
    xy_min = np.min(xy, axis=0)
    xy_max = np.max(xy, axis=0)
    xy_std = np.std(xy, axis=0)
    centered = xy - np.median(xy, axis=0)
    radial_deviation = np.linalg.norm(centered, axis=1)
    return {
        "xy_range": [float(value) for value in xy_max - xy_min],
        "xy_std": [float(value) for value in xy_std],
        "xy_std_norm": float(np.linalg.norm(xy_std)),
        "radial_deviation_p95": float(np.quantile(radial_deviation, 0.95)),
        "required_xy_range": NORMAL_MIN_XY_RANGE,
        "required_xy_std_norm": NORMAL_MIN_XY_STD_NORM,
    }


def ao_quality_metrics(
    image: bpy.types.Image,
    active: np.ndarray,
) -> dict[str, Any]:
    values = image_array(image)
    samples = values[active, 0] if np.any(active) else values[:, 0]
    if samples.size == 0:
        raise RuntimeError("AO quality metrics require active atlas pixels")
    minimum = float(np.min(samples))
    maximum = float(np.max(samples))
    mean = float(np.mean(samples))
    median = float(np.median(samples))
    standard_deviation = float(np.std(samples))
    return {
        "active_min": minimum,
        "active_max": maximum,
        "active_mean": mean,
        "active_median": median,
        "active_std": standard_deviation,
        "active_range": maximum - minimum,
        "active_percentiles": {
            f"p{quantile:02d}": float(np.quantile(samples, quantile / 100.0))
            for quantile in (1, 5, 25, 50, 75, 95, 99)
        },
        "dark_threshold": AO_DARK_THRESHOLD,
        "dark_ratio": float(np.mean(samples < AO_DARK_THRESHOLD)),
        "deep_threshold": AO_DEEP_THRESHOLD,
        "deep_ratio": float(np.mean(samples < AO_DEEP_THRESHOLD)),
        "nonwhite_ratio": float(np.mean(samples < (1.0 - 0.5 / 255.0))),
        "gate": {
            "minimum_active_value": AO_MIN_ACTIVE_VALUE,
            "minimum_mean": AO_MIN_MEAN,
            "maximum_mean": AO_MAX_MEAN,
            "minimum_median": AO_MIN_MEDIAN,
            "minimum_std": AO_MIN_STD,
            "maximum_std": AO_MAX_STD,
            "minimum_dark_ratio": AO_MIN_DARK_RATIO,
            "maximum_dark_ratio": AO_MAX_DARK_RATIO,
            "maximum_deep_ratio": AO_MAX_DEEP_RATIO,
            "minimum_range": AO_MIN_RANGE,
        },
    }


def metallic_quality_metrics(
    image: bpy.types.Image,
    active: np.ndarray,
) -> dict[str, Any]:
    """Measure distribution and local continuity on active atlas islands."""

    width = int(image.size[0])
    height = int(image.size[1])
    values = image_array(image)[:, 0].reshape((height, width))
    mask = active.reshape((height, width))
    samples = values[mask]
    if samples.size == 0:
        raise RuntimeError("Metallic quality metrics require active atlas pixels")
    p05, p50, p95, p99 = (
        float(value) for value in np.quantile(samples, (0.05, 0.50, 0.95, 0.99))
    )
    adjacent = []
    vertical_mask = mask[:-1, :] & mask[1:, :]
    horizontal_mask = mask[:, :-1] & mask[:, 1:]
    adjacent.append(np.abs(values[:-1, :] - values[1:, :])[vertical_mask])
    adjacent.append(np.abs(values[:, :-1] - values[:, 1:])[horizontal_mask])
    adjacent_delta = np.concatenate(adjacent)
    interior_mask = (
        mask[1:-1, 1:-1]
        & mask[:-2, 1:-1]
        & mask[2:, 1:-1]
        & mask[1:-1, :-2]
        & mask[1:-1, 2:]
    )
    neighbor_mean = (
        values[:-2, 1:-1]
        + values[2:, 1:-1]
        + values[1:-1, :-2]
        + values[1:-1, 2:]
    ) * 0.25
    local_deviation = np.abs(values[1:-1, 1:-1] - neighbor_mean)[interior_mask]
    return {
        "active_percentiles": {
            "p05": p05,
            "p50": p50,
            "p95": p95,
            "p99": p99,
        },
        "p95_p05_spread": p95 - p05,
        "near_binary_thresholds": {
            "low": METALLIC_NEAR_BINARY_LOW,
            "high": METALLIC_NEAR_BINARY_HIGH,
        },
        "near_binary_ratio": float(
            np.mean(
                (samples <= METALLIC_NEAR_BINARY_LOW)
                | (samples >= METALLIC_NEAR_BINARY_HIGH)
            )
        ),
        "near_low_ratio": float(np.mean(samples <= METALLIC_NEAR_BINARY_LOW)),
        "near_high_ratio": float(np.mean(samples >= METALLIC_NEAR_BINARY_HIGH)),
        "adjacent_sample_count": int(adjacent_delta.size),
        "adjacent_delta_mean": float(np.mean(adjacent_delta)),
        "adjacent_delta_p95": float(np.quantile(adjacent_delta, 0.95)),
        "adjacent_delta_p99": float(np.quantile(adjacent_delta, 0.99)),
        "adjacent_large_delta_threshold": METALLIC_ADJACENT_LARGE_DELTA,
        "adjacent_large_delta_ratio": float(
            np.mean(adjacent_delta >= METALLIC_ADJACENT_LARGE_DELTA)
        ),
        "local_sample_count": int(local_deviation.size),
        "local_deviation_p95": float(np.quantile(local_deviation, 0.95)),
        "local_impulse_threshold": METALLIC_LOCAL_IMPULSE_DELTA,
        "local_impulse_ratio": float(
            np.mean(local_deviation >= METALLIC_LOCAL_IMPULSE_DELTA)
        ),
    }


def pack_orm(
    images: dict[str, bpy.types.Image],
    texture_dir: Path,
    size: int,
) -> tuple[bpy.types.Image, dict[str, Any]]:
    ao = image_array(images["AO"])
    roughness = image_array(images["Roughness"])
    metallic = image_array(images["Metallic"])
    packed = np.empty_like(ao)
    packed[:, 0] = ao[:, 0]
    packed[:, 1] = roughness[:, 0]
    packed[:, 2] = metallic[:, 0]
    packed[:, 3] = 1.0
    orm = create_image(f"P50_GL02_ORM_{suffix_for_size(size)}", size, "Non-Color")
    orm.alpha_mode = "CHANNEL_PACKED"
    orm.pixels.foreach_set(packed.reshape(-1))
    orm.update()
    info = save_image(
        orm,
        texture_dir / f"P50_GL02_ORM_{suffix_for_size(size)}.png",
        "Non-Color",
    )
    max_error = max(
        float(np.max(np.abs(packed[:, 0] - ao[:, 0]))),
        float(np.max(np.abs(packed[:, 1] - roughness[:, 0]))),
        float(np.max(np.abs(packed[:, 2] - metallic[:, 0]))),
    )
    ao_disk = disk_image_array(Path(images["AO"].filepath_raw), "Non-Color")
    orm_disk = disk_image_array(Path(info["path"]), "Non-Color")
    disk_r_vs_ao_max_error = float(
        np.max(np.abs(orm_disk[:, 0] - ao_disk[:, 0]))
    )
    return orm, {
        **info,
        "channel_mapping": "R=AO,G=Roughness,B=Metallic,A=1",
        "in_memory_max_channel_error": max_error,
        "disk_r_vs_ao_max_error": disk_r_vs_ao_max_error,
        "disk_r_gate_max_error": 1.0 / 255.0,
    }


def build_baked_material(images: dict[str, bpy.types.Image]) -> tuple[bpy.types.Material, dict[str, Any]]:
    existing = bpy.data.materials.get(BAKED_MATERIAL_NAME)
    if existing:
        bpy.data.materials.remove(existing)
    material = bpy.data.materials.new(BAKED_MATERIAL_NAME)
    material.use_nodes = True
    material.diffuse_color = (0.064, 0.087, 0.078, 0.88)
    if hasattr(material, "surface_render_method"):
        material.surface_render_method = "DITHERED"
    nodes = material.node_tree.nodes
    links = material.node_tree.links
    nodes.clear()
    output = nodes.new("ShaderNodeOutputMaterial")
    output.name = "P50_OUTPUT"
    principled = nodes.new("ShaderNodeBsdfPrincipled")
    principled.name = "P50_PRINCIPLED"
    principled.inputs["Alpha"].default_value = 0.88
    if principled.inputs.get("Emission Strength"):
        principled.inputs["Emission Strength"].default_value = 0.0
    links.new(principled.outputs["BSDF"], output.inputs["Surface"])

    base = nodes.new("ShaderNodeTexImage")
    base.name = "P50_BASE_COLOR_SRGB"
    base.image = images["BaseColor"]
    links.new(base.outputs["Color"], principled.inputs["Base Color"])

    orm = nodes.new("ShaderNodeTexImage")
    orm.name = "P50_ORM_NON_COLOR_R_AO_G_ROUGHNESS_B_METALLIC"
    orm.image = images["ORM"]
    separate = nodes.new("ShaderNodeSeparateColor")
    separate.name = "P50_ORM_CHANNELS"
    separate.mode = "RGB"
    links.new(orm.outputs["Color"], separate.inputs["Color"])
    links.new(separate.outputs["Green"], principled.inputs["Roughness"])
    links.new(separate.outputs["Blue"], principled.inputs["Metallic"])

    normal_texture = nodes.new("ShaderNodeTexImage")
    normal_texture.name = "P50_OPENGL_NORMAL_NON_COLOR"
    normal_texture.image = images["NormalGL"]
    normal_map = nodes.new("ShaderNodeNormalMap")
    normal_map.name = "P50_OPENGL_PLUS_Y_NORMAL"
    normal_map.space = "TANGENT"
    normal_map.inputs["Strength"].default_value = NORMAL_RUNTIME_SCALE
    links.new(normal_texture.outputs["Color"], normal_map.inputs["Color"])
    links.new(normal_map.outputs["Normal"], principled.inputs["Normal"])

    audit_nodes = {}
    for channel in ("AO", "Roughness", "Metallic"):
        node = nodes.new("ShaderNodeTexImage")
        node.name = f"P50_AUDIT_{channel.upper()}_NON_COLOR"
        node.image = images[channel]
        node.hide = True
        audit_nodes[channel] = node.name

    material["bf3d_role"] = "full_furnace_standard_principled_pbr"
    material["bf3d_base_color_colorspace"] = "sRGB"
    material["bf3d_normal_colorspace"] = "Non-Color"
    material["bf3d_normal_convention"] = "OpenGL +Y"
    material["bf3d_normal_encoding_amplification"] = NORMAL_BAKE_ENCODING_AMPLIFICATION
    material["bf3d_normal_runtime_scale"] = NORMAL_RUNTIME_SCALE
    material["bf3d_orm_colorspace"] = "Non-Color"
    material["bf3d_orm_mapping"] = "R=AO,G=Roughness,B=Metallic"
    material["bf3d_ao_mode"] = AO_MODE
    material["bf3d_ao_distance_m"] = AO_DISTANCE_M
    material["bf3d_ao_strength"] = AO_STRENGTH
    material["bf3d_ao_floor"] = AO_FLOOR
    material["bf3d_uv_layer"] = UV_NAME
    graph = {
        "nodes": sorted(node.name for node in nodes),
        "node_types": sorted(node.bl_idname for node in nodes),
        "procedural_nodes": sorted(
            node.name for node in nodes if node.bl_idname in PROCEDURAL_NODE_TYPES
        ),
        "audit_texture_nodes": audit_nodes,
        "normal_map_strength": float(normal_map.inputs["Strength"].default_value),
    }
    return material, graph


def render_preview(output_dir: Path, size: int) -> dict[str, Any]:
    scene = bpy.context.scene
    camera = bpy.data.objects.get("CAM_GLOBAL_FRONT")
    if camera is None or camera.type != "CAMERA":
        return {"status": "skipped", "reason": "CAM_GLOBAL_FRONT not found"}
    scene.camera = camera
    scene.render.engine = "BLENDER_EEVEE"
    scene.render.resolution_x = size
    scene.render.resolution_y = max(1, round(size * 9 / 16))
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = "PNG"
    path = output_dir / "renders" / "P50_FULL_FURNACE_BAKED_front.png"
    path.parent.mkdir(parents=True, exist_ok=True)
    scene.render.filepath = str(path)
    bpy.ops.render.render(write_still=True)
    return {
        "status": "rendered",
        "path": str(path),
        "bytes": path.stat().st_size,
        "sha256": p00.sha256_file(path),
    }


def main() -> int:
    args = parse_args()
    output_dir = args.output_dir.resolve()
    texture_dir = output_dir / "textures"
    texture_dir.mkdir(parents=True, exist_ok=True)
    source_glb = args.source_glb.resolve()
    input_blend = Path(bpy.data.filepath).resolve()
    input_stage = str(bpy.context.scene.get("bf3d_stage", ""))
    if input_stage not in ALLOWED_INPUT_STAGES:
        raise RuntimeError(f"Expected P40 lookdev input, got {input_stage!r}")
    input_sha256 = p00.sha256_file(input_blend)
    if input_sha256 != EXPECTED_INPUT_SHA256:
        raise RuntimeError(
            f"P50 input checkpoint lock mismatch: expected {EXPECTED_INPUT_SHA256}, got {input_sha256}"
        )
    targets = [bpy.data.objects.get(name) for name in TARGETS]
    if any(obj is None or obj.type != "MESH" for obj in targets):
        raise RuntimeError(f"Missing one or more furnace shell targets: {TARGETS}")
    targets = list(targets)  # narrow Optional type for Blender/Python
    source_material = bpy.data.materials.get(SOURCE_MATERIAL_NAME)
    if source_material is None:
        raise RuntimeError(f"Missing protected source material: {SOURCE_MATERIAL_NAME}")
    if any(source_material not in obj.data.materials[:] for obj in targets):
        raise RuntimeError("All five shell targets must still use the approved P30 material")
    detail_occluders = [bpy.data.objects.get(name) for name in AO_DETAIL_OCCLUDERS]
    if any(obj is None or obj.type != "MESH" for obj in detail_occluders):
        raise RuntimeError(
            f"Missing one or more local-contact AO occluders: {AO_DETAIL_OCCLUDERS}"
        )

    source_contract = p00.source_node_contract(p00.read_glb_json(source_glb))
    imported_before = p00.imported_contract(source_contract)
    layers_before = layer_snapshot()
    geometry_before = {obj.name: p21.geometry_sha256(obj.data) for obj in targets}
    scene_geometry_before = mesh_geometry_snapshot()
    matrices_before = p21.scene_matrix_sha256()
    slots_before = p21.material_slots()
    hide_render_before = hide_render_snapshot()

    uv_report, atlas = build_shared_atlas_uv(targets, args.texture_size, args.margin)
    transient_material, source_graph = make_bake_source(source_material, args.samples)
    device = configure_cycles(args.samples)
    try:
        images, files, timings = bake_channels(
            targets,
            transient_material,
            source_graph,
            texture_dir,
            args.texture_size,
            args.margin,
        )
    except RuntimeError as gpu_error:
        if device.get("used") != "OPTIX":
            raise
        device["bake_fallback_reason"] = str(gpu_error)
        device = {**device, **p21.configure_cycles(False), "fallback_from": "OPTIX"}
        bpy.context.scene.cycles.samples = args.samples
        images, files, timings = bake_channels(
            targets,
            transient_material,
            source_graph,
            texture_dir,
            args.texture_size,
            args.margin,
        )
    orm, orm_info = pack_orm(images, texture_dir, args.texture_size)
    images["ORM"] = orm
    files["ORM"] = orm_info
    active_pixels = image_array(images["AO"])[:, 0] > 0.5
    image_metrics = {
        name: p21.image_metrics(image, active_pixels)
        for name, image in images.items()
    }
    image_metrics["NormalGL"].update(
        normal_variation_metrics(images["NormalGL"], active_pixels)
    )
    image_metrics["AO"].update(
        ao_quality_metrics(images["AO"], active_pixels)
    )
    image_metrics["Metallic"].update(
        metallic_quality_metrics(images["Metallic"], active_pixels)
    )
    baked_material, baked_graph = build_baked_material(images)
    for obj in targets:
        obj.data.materials.clear()
        obj.data.materials.append(baked_material)
    if transient_material.users == 0:
        bpy.data.materials.remove(transient_material)
    if source_material.users == 0:
        bpy.data.materials.remove(source_material)

    imported_after = p00.imported_contract(source_contract)
    layers_after = layer_snapshot()
    geometry_after = {obj.name: p21.geometry_sha256(obj.data) for obj in targets}
    scene_geometry_after = mesh_geometry_snapshot()
    matrices_after = p21.scene_matrix_sha256()
    slots_after = p21.material_slots()
    hide_render_after = hide_render_snapshot()
    changed_slots = sorted(
        name for name in slots_before if slots_before.get(name) != slots_after.get(name)
    )
    scene_geometry_mismatches = sorted(
        name
        for name in set(scene_geometry_before) | set(scene_geometry_after)
        if scene_geometry_before.get(name) != scene_geometry_after.get(name)
    )
    ao_visibility_audit = source_graph["ao_visibility_audit"]
    ao_visibility_exact = (
        len(ao_visibility_audit) == len(TARGETS)
        and all(
            item.get("allowed_meshes")
            == sorted({item.get("target"), *AO_DETAIL_OCCLUDERS})
            and item.get("visible_meshes_exact")
            and item.get("platform_excluded")
            and item.get("sensors_excluded")
            and item.get("temperature_bands_excluded")
            and item.get("hide_render_restored")
            for item in ao_visibility_audit
        )
    )
    all_uv_metrics = uv_report["metrics"]
    all_bounds_inside = all(
        item["bounds"]["min_u"] >= -1e-7
        and item["bounds"]["max_u"] <= 1.0 + 1e-7
        and item["bounds"]["min_v"] >= -1e-7
        and item["bounds"]["max_v"] <= 1.0 + 1e-7
        for item in all_uv_metrics.values()
    )
    all_zero_area_free = all(item["zero_area_faces"] == 0 for item in all_uv_metrics.values())
    all_non_seam_continuous = all(
        item["non_seam_max_uv_discontinuity"] <= 1e-5
        for item in all_uv_metrics.values()
    )
    colorspaces = {
        name: image.colorspace_settings.name
        for name, image in images.items()
    }
    assertions = [
        {"id": "input_stage_is_allowed_p40", "ok": input_stage in ALLOWED_INPUT_STAGES, "detail": input_stage},
        {
            "id": "input_checkpoint_matches_lock",
            "ok": input_sha256 == EXPECTED_INPUT_SHA256,
            "detail": input_sha256,
        },
        {
            "id": "source_glb_matches_lock",
            "ok": p00.sha256_file(source_glb) == p00.EXPECTED_SOURCE_SHA256,
            "detail": p00.sha256_file(source_glb),
        },
        {
            "id": "sensor_contract_unchanged",
            "ok": imported_before["sensor_records"] == imported_after["sensor_records"]
            and imported_after["sensor_count"] == 115
            and imported_after["body_sensor_count"] == 80,
        },
        {
            "id": "p36_ten_layers_preserved",
            "ok": exact_layer_contract(layers_before)
            and layers_before == layers_after,
        },
        {
            "id": "five_shell_geometries_unchanged",
            "ok": geometry_before == geometry_after,
            "detail": {"before": geometry_before, "after": geometry_after},
        },
        {
            "id": "all_scene_mesh_geometries_unchanged",
            "ok": not scene_geometry_mismatches,
            "detail": scene_geometry_mismatches,
        },
        {
            "id": "object_matrices_unchanged",
            "ok": matrices_before == matrices_after,
            "detail": {"before": matrices_before, "after": matrices_after},
        },
        {
            "id": "all_hide_render_states_restored_exactly",
            "ok": hide_render_before == hide_render_after,
            "detail": {
                "changed": sorted(
                    name
                    for name in set(hide_render_before) | set(hide_render_after)
                    if hide_render_before.get(name) != hide_render_after.get(name)
                )
            },
        },
        {
            "id": "local_contact_ao_whitelist_is_exact_per_shell",
            "ok": ao_visibility_exact,
            "detail": ao_visibility_audit,
        },
        {
            "id": "local_contact_ao_parameters_are_exact",
            "ok": source_graph["ao_policy"]
            == {
                "mode": AO_MODE,
                "detail_occluders": list(AO_DETAIL_OCCLUDERS),
                "distance_m": AO_DISTANCE_M,
                "strength": AO_STRENGTH,
                "floor": AO_FLOOR,
                "samples": args.samples,
                "inside": False,
                "only_local": False,
                "selected_to_active": False,
                "cage_extrusion_m": 0.0,
                "max_ray_distance_m": 0.0,
            },
            "detail": source_graph["ao_policy"],
        },
        {
            "id": "only_five_shell_material_slots_changed",
            "ok": changed_slots == sorted(TARGETS),
            "detail": changed_slots,
        },
        {
            "id": "five_shells_share_one_standard_material",
            "ok": all(
                [material.name if material else None for material in obj.data.materials]
                == [BAKED_MATERIAL_NAME]
                for obj in targets
            ),
        },
        {
            "id": "five_shells_have_one_p50_uv_layer",
            "ok": all([layer.name for layer in obj.data.uv_layers] == [UV_NAME] for obj in targets),
            "detail": {obj.name: [layer.name for layer in obj.data.uv_layers] for obj in targets},
        },
        {"id": "uv_bounds_inside_unit_square", "ok": all_bounds_inside},
        {"id": "uv_has_no_zero_area_faces", "ok": all_zero_area_free},
        {"id": "uv_is_continuous_across_non_seams", "ok": all_non_seam_continuous},
        {
            "id": "object_grouped_three_column_layout_is_exact",
            "ok": atlas["layout_id"] == ATLAS_LAYOUT_ID
            and atlas["column_count"] == 3
            and atlas["layout_keys_match"],
            "detail": {
                "layout_id": atlas["layout_id"],
                "column_count": atlas["column_count"],
                "columns": atlas["columns"],
            },
        },
        {
            "id": "atlas_has_exactly_ten_unique_islands",
            "ok": atlas["island_count"] == 10
            and atlas["unique_island_count"] == 10
            and atlas["layout_keys_match"],
            "detail": {
                "island_count": atlas["island_count"],
                "unique_island_count": atlas["unique_island_count"],
                "expected": atlas["expected_layout_keys"],
                "actual": atlas["actual_layout_keys"],
            },
        },
        {
            "id": "atlas_rotations_are_positive_and_never_mirrored",
            "ok": atlas["positive_orientation_only"]
            and all(
                int(island["rotation_degrees"]) in {0, 90}
                for island in atlas["islands"]
            ),
            "detail": {
                "orientation_counts": atlas["orientation_counts"],
                "rotations": [
                    [
                        island["object"],
                        island["band"],
                        island["rotation_degrees"],
                    ]
                    for island in atlas["islands"]
                ],
            },
        },
        {
            "id": "atlas_islands_respect_outer_boundary",
            "ok": atlas["minimum_outer_margin_uv"] + 1e-8
            >= atlas["required_outer_margin_uv"],
            "detail": {
                "minimum_outer_margin_uv": atlas["minimum_outer_margin_uv"],
                "required_outer_margin_uv": atlas["required_outer_margin_uv"],
                "minimum_outer_margin_px": (
                    atlas["minimum_outer_margin_uv"] * args.texture_size
                ),
                "required_outer_margin_px": (
                    atlas["required_outer_margin_uv"] * args.texture_size
                ),
            },
        },
        {
            "id": "atlas_columns_and_islands_keep_bake_safe_gaps",
            "ok": atlas["minimum_column_gap_uv"] + 1e-8
            >= atlas["required_gap_uv"]
            and atlas["minimum_intra_column_gap_uv"] + 1e-8
            >= atlas["required_gap_uv"],
            "detail": {
                "column_gaps_uv": atlas["column_gaps_uv"],
                "intra_column_gaps_uv": atlas["intra_column_gaps_uv"],
                "required_gap_uv": atlas["required_gap_uv"],
                "minimum_gap_px": atlas["minimum_gap_uv"] * args.texture_size,
            },
        },
        {
            "id": "all_45_expanded_island_pairs_do_not_overlap",
            "ok": atlas["expanded_pair_count"] == 45
            and atlas["all_expanded_pairs_disjoint"],
            "detail": {
                "expanded_pair_count": atlas["expanded_pair_count"],
                "bake_margin_uv": atlas["bake_margin_uv"],
                "expanded_overlap_pairs": atlas["expanded_overlap_pairs"],
            },
        },
        {
            "id": "cross_zone_texel_density_within_half_percent",
            "ok": atlas["density_relative_spread"]
            <= ATLAS_MAX_DENSITY_RELATIVE_SPREAD,
            "detail": {
                "density_relative_spread": atlas["density_relative_spread"],
                "maximum_allowed": ATLAS_MAX_DENSITY_RELATIVE_SPREAD,
                "effective_texels_per_meter": atlas["effective_texels_per_meter"],
            },
        },
        {
            "id": "six_required_maps_exist",
            "ok": set(files) == {"BaseColor", "Roughness", "Metallic", "AO", "NormalGL", "ORM"}
            and all(Path(item["path"]).is_file() for item in files.values()),
            "detail": sorted(files),
        },
        {
            "id": "texture_dimensions_are_exact",
            "ok": all(
                item["width"] == args.texture_size and item["height"] == args.texture_size
                for item in image_metrics.values()
            ),
        },
        {
            "id": "texture_colorspaces_are_gltf_safe",
            "ok": colorspaces.get("BaseColor") == "sRGB"
            and all(colorspaces.get(name) == "Non-Color" for name in ("Roughness", "Metallic", "AO", "NormalGL", "ORM")),
            "detail": colorspaces,
        },
        {
            "id": "all_maps_are_finite_and_cover_uv",
            "ok": all(
                item["finite"] and item["active_pixel_ratio"] > 0.05
                for item in image_metrics.values()
            ),
            "detail": {
                name: {
                    "finite": item["finite"],
                    "active_pixel_ratio": item["active_pixel_ratio"],
                }
                for name, item in image_metrics.items()
            },
        },
        {
            "id": "atlas_active_pixel_ratio_meets_55_percent",
            "ok": image_metrics["BaseColor"]["active_pixel_ratio"]
            >= ATLAS_MIN_ACTIVE_PIXEL_RATIO,
            "detail": {
                "actual": image_metrics["BaseColor"]["active_pixel_ratio"],
                "minimum_required": ATLAS_MIN_ACTIVE_PIXEL_RATIO,
                "measurement_mask": "AO channel > 0.5",
            },
        },
        {
            "id": "roughness_remains_matte",
            "ok": image_metrics["Roughness"]["rgb_min"][0] >= 0.45
            and image_metrics["Roughness"]["rgb_max"][0] <= 1.0,
            "detail": image_metrics["Roughness"],
        },
        {
            "id": "metallic_mask_is_bounded_and_varied",
            "ok": image_metrics["Metallic"]["rgb_min"][0] >= 0.0
            and image_metrics["Metallic"]["rgb_max"][0] <= METALLIC_MAX_ACTIVE_VALUE
            and image_metrics["Metallic"]["p95_p05_spread"]
            >= METALLIC_MIN_P95_P05_SPREAD,
            "detail": image_metrics["Metallic"],
        },
        {
            "id": "metallic_calibration_is_transient_and_exact",
            "ok": source_graph["metallic_calibration"]["scope"]
            == "P50 transient bake graph only"
            and source_graph["metallic_calibration"]["original"]["exposure_input"]
            == ["P30_EXPOSED_STEEL_MASK"]
            and source_graph["metallic_calibration"]["calibrated"]["exposure_input"]
            == "P50_METALLIC_CONTINUOUS_EXPOSURE"
            and source_graph["metallic_calibration"]["calibrated"]["interpolation"]
            == "EASE"
            and math.isclose(
                source_graph["metallic_calibration"]["calibrated"]["low_position"],
                METALLIC_EXPOSURE_RAMP_LOW,
                abs_tol=1e-6,
            )
            and math.isclose(
                source_graph["metallic_calibration"]["calibrated"]["high_position"],
                METALLIC_EXPOSURE_RAMP_HIGH,
                abs_tol=1e-6,
            )
            and math.isclose(
                source_graph["metallic_calibration"]["calibrated"]["bare_steel"],
                METALLIC_BARE_STEEL_VALUE,
                abs_tol=1e-6,
            ),
            "detail": source_graph["metallic_calibration"],
        },
        {
            "id": "metallic_distribution_avoids_near_binary_salt_and_pepper",
            "ok": image_metrics["Metallic"]["p95_p05_spread"]
            <= METALLIC_MAX_P95_P05_SPREAD
            and image_metrics["Metallic"]["near_binary_ratio"]
            <= METALLIC_MAX_NEAR_BINARY_RATIO
            and image_metrics["Metallic"]["active_percentiles"]["p99"]
            <= METALLIC_MAX_ACTIVE_VALUE,
            "detail": {
                "p95_p05_spread": image_metrics["Metallic"]["p95_p05_spread"],
                "maximum_p95_p05_spread": METALLIC_MAX_P95_P05_SPREAD,
                "near_binary_ratio": image_metrics["Metallic"]["near_binary_ratio"],
                "maximum_near_binary_ratio": METALLIC_MAX_NEAR_BINARY_RATIO,
                "near_binary_thresholds": image_metrics["Metallic"]["near_binary_thresholds"],
                "p99": image_metrics["Metallic"]["active_percentiles"]["p99"],
                "maximum_active_value": METALLIC_MAX_ACTIVE_VALUE,
            },
        },
        {
            "id": "metallic_local_transitions_are_spatially_stable",
            "ok": image_metrics["Metallic"]["adjacent_delta_p95"]
            <= METALLIC_MAX_ADJACENT_DELTA_P95
            and image_metrics["Metallic"]["adjacent_large_delta_ratio"]
            <= METALLIC_MAX_ADJACENT_LARGE_DELTA_RATIO
            and image_metrics["Metallic"]["local_impulse_ratio"]
            <= METALLIC_MAX_LOCAL_IMPULSE_RATIO,
            "detail": {
                "adjacent_delta_p95": image_metrics["Metallic"]["adjacent_delta_p95"],
                "maximum_adjacent_delta_p95": METALLIC_MAX_ADJACENT_DELTA_P95,
                "adjacent_large_delta_threshold": METALLIC_ADJACENT_LARGE_DELTA,
                "adjacent_large_delta_ratio": image_metrics["Metallic"]["adjacent_large_delta_ratio"],
                "maximum_adjacent_large_delta_ratio": METALLIC_MAX_ADJACENT_LARGE_DELTA_RATIO,
                "local_impulse_threshold": METALLIC_LOCAL_IMPULSE_DELTA,
                "local_impulse_ratio": image_metrics["Metallic"]["local_impulse_ratio"],
                "maximum_local_impulse_ratio": METALLIC_MAX_LOCAL_IMPULSE_RATIO,
            },
        },
        {
            "id": "normal_is_opengl_plus_y",
            "ok": 0.25 <= image_metrics["NormalGL"]["rgb_mean"][0] <= 0.75
            and 0.25 <= image_metrics["NormalGL"]["rgb_mean"][1] <= 0.75
            and image_metrics["NormalGL"]["rgb_mean"][2] >= 0.65,
            "detail": image_metrics["NormalGL"],
        },
        {
            "id": "normal_contains_quantization_safe_microdetail",
            "ok": min(image_metrics["NormalGL"]["xy_range"]) >= NORMAL_MIN_XY_RANGE
            and image_metrics["NormalGL"]["xy_std_norm"] >= NORMAL_MIN_XY_STD_NORM,
            "detail": {
                "xy_range": image_metrics["NormalGL"]["xy_range"],
                "xy_std": image_metrics["NormalGL"]["xy_std"],
                "xy_std_norm": image_metrics["NormalGL"]["xy_std_norm"],
                "radial_deviation_p95": image_metrics["NormalGL"]["radial_deviation_p95"],
                "required_xy_range": NORMAL_MIN_XY_RANGE,
                "required_xy_std_norm": NORMAL_MIN_XY_STD_NORM,
            },
        },
        {
            "id": "local_contact_ao_is_nonwhite_and_varied",
            "ok": image_metrics["AO"]["active_range"] >= AO_MIN_RANGE
            and image_metrics["AO"]["active_std"] >= AO_MIN_STD
            and image_metrics["AO"]["nonwhite_ratio"] >= AO_MIN_DARK_RATIO,
            "detail": image_metrics["AO"],
        },
        {
            "id": "local_contact_ao_distribution_is_bounded",
            "ok": image_metrics["AO"]["active_min"] >= AO_MIN_ACTIVE_VALUE
            and image_metrics["AO"]["active_max"] <= 1.0 + 1e-6
            and AO_MIN_MEAN
            <= image_metrics["AO"]["active_mean"]
            <= AO_MAX_MEAN
            and image_metrics["AO"]["active_median"] >= AO_MIN_MEDIAN
            and image_metrics["AO"]["active_std"] <= AO_MAX_STD
            and AO_MIN_DARK_RATIO
            <= image_metrics["AO"]["dark_ratio"]
            <= AO_MAX_DARK_RATIO
            and image_metrics["AO"]["deep_ratio"] <= AO_MAX_DEEP_RATIO,
            "detail": image_metrics["AO"],
        },
        {
            "id": "orm_channels_are_exact_in_memory",
            "ok": orm_info["in_memory_max_channel_error"] <= 1e-8,
            "detail": orm_info,
        },
        {
            "id": "orm_r_matches_saved_ao_channel",
            "ok": orm_info["disk_r_vs_ao_max_error"]
            <= orm_info["disk_r_gate_max_error"] + 1e-8,
            "detail": orm_info,
        },
        {
            "id": "baked_material_has_no_procedural_nodes",
            "ok": not baked_graph["procedural_nodes"],
            "detail": baked_graph,
        },
    ]
    ok = all(bool(item["ok"]) for item in assertions)
    candidate = None
    preview: dict[str, Any] = {"status": "not_run"}
    if ok:
        scene = bpy.context.scene
        scene["bf3d_stage"] = "P50_FULL_FURNACE_BAKE_CANDIDATE"
        scene["bf3d_parent_checkpoint"] = str(input_blend)
        scene["bf3d_change_dimension"] = "five_shell_zone_shared_atlas_uv_and_standard_pbr_bake_only"
        scene["bf3d_bake_resolution"] = args.texture_size
        scene["bf3d_bake_margin_px"] = args.margin
        scene["bf3d_atlas_layout"] = ATLAS_LAYOUT_ID
        scene["bf3d_atlas_island_count"] = atlas["island_count"]
        scene["bf3d_atlas_column_count"] = atlas["column_count"]
        scene["bf3d_atlas_active_pixel_ratio"] = image_metrics["BaseColor"]["active_pixel_ratio"]
        scene["bf3d_bake_normal_convention"] = "OpenGL +Y"
        scene["bf3d_bake_normal_encoding_amplification"] = NORMAL_BAKE_ENCODING_AMPLIFICATION
        scene["bf3d_runtime_normal_scale"] = NORMAL_RUNTIME_SCALE
        scene["bf3d_bake_metallic_bare_steel"] = METALLIC_BARE_STEEL_VALUE
        scene["bf3d_bake_metallic_transition"] = "wide_ease_web_stable"
        scene["bf3d_bake_orm_mapping"] = "R=AO,G=Roughness,B=Metallic"
        scene["bf3d_bake_ao_mode"] = AO_MODE
        scene["bf3d_bake_ao_distance_m"] = AO_DISTANCE_M
        scene["bf3d_bake_ao_strength"] = AO_STRENGTH
        scene["bf3d_bake_ao_floor"] = AO_FLOOR
        scene["bf3d_bake_ao_samples"] = args.samples
        bpy.ops.file.pack_all()
        candidate_path = output_dir / "P50_FULL_FURNACE_BAKE_CANDIDATE.blend"
        bpy.ops.wm.save_as_mainfile(filepath=str(candidate_path), check_existing=False)
        candidate = {
            "path": str(candidate_path),
            "bytes": candidate_path.stat().st_size,
            "sha256": p00.sha256_file(candidate_path),
        }
        if not args.skip_render:
            try:
                preview = render_preview(output_dir, args.render_size)
            except Exception as exc:  # pragma: no cover - render backend dependent
                preview = {"status": "failed", "reason": str(exc)}

    status = "candidate_ready_for_visual_review" if ok else "fail"
    report = {
        "schema_version": 1,
        "stage": "P50_FULL_FURNACE_BAKE_CANDIDATE",
        "status": status,
        "input_checkpoint": {
            "path": str(input_blend),
            "sha256": input_sha256,
            "stage": input_stage,
        },
        "candidate": candidate,
        "single_changed_dimension": "Five shell-zone UVs and baked standard Principled material only.",
        "targets": list(TARGETS),
        "uv": uv_report,
        "atlas": atlas,
        "texture_size": args.texture_size,
        "margin_px": args.margin,
        "cycles_samples": args.samples,
        "device": device,
        "timings_seconds": timings,
        "textures": files,
        "image_metrics": image_metrics,
        "material_graph": baked_graph,
        "normal_policy": {
            **source_graph["normal_encoding"],
            "gate": {
                "minimum_xy_range": NORMAL_MIN_XY_RANGE,
                "minimum_xy_std_norm": NORMAL_MIN_XY_STD_NORM,
            },
            "reason": (
                "Encode the approved subtle P30 bump above the 8-bit quantization "
                "floor, then reconstruct its intended intensity with reciprocal "
                "Normal Map strength."
            ),
        },
        "metallic_policy": {
            **source_graph["metallic_calibration"],
            "gate": {
                "maximum_active_value": METALLIC_MAX_ACTIVE_VALUE,
                "minimum_p95_p05_spread": METALLIC_MIN_P95_P05_SPREAD,
                "maximum_p95_p05_spread": METALLIC_MAX_P95_P05_SPREAD,
                "maximum_near_binary_ratio": METALLIC_MAX_NEAR_BINARY_RATIO,
                "maximum_adjacent_delta_p95": METALLIC_MAX_ADJACENT_DELTA_P95,
                "maximum_adjacent_large_delta_ratio": METALLIC_MAX_ADJACENT_LARGE_DELTA_RATIO,
                "maximum_local_impulse_ratio": METALLIC_MAX_LOCAL_IMPULSE_RATIO,
            },
            "reason": (
                "Preserve low-metal rust/dust while replacing dense near-binary "
                "bare-steel speckle with a wider continuous EASE response that "
                "remains stable at browser viewing distance."
            ),
        },
        "ao_policy": {
            **source_graph["ao_policy"],
            "visibility_audit": ao_visibility_audit,
            "distribution": image_metrics["AO"],
            "reason": (
                "Bake only close shell weld, stiffener-ring and tuyere contact "
                "occlusion while excluding platforms, towers, internals, sensors "
                "and L7-L16 diagnostic overlays."
            ),
            "gate_basis": (
                "The 0.998 upper mean accepts intentionally sparse whitelisted "
                "contact shadows; nonwhite-ratio, dark-ratio, standard-deviation "
                "and active-range gates still reject a neutral all-white AO map."
            ),
        },
        "preservation": {
            "sensor_count": imported_after["sensor_count"],
            "body_sensor_count": imported_after["body_sensor_count"],
            "temperature_layers": list(EXPECTED_LAYERS),
            "p36_snapshot_unchanged": layers_before == layers_after,
            "hide_render_snapshot_unchanged": hide_render_before == hide_render_after,
            "scene_geometry_mismatches": scene_geometry_mismatches,
            "object_matrices_unchanged": matrices_before == matrices_after,
        },
        "assertions": assertions,
        "preview": preview,
        "approval": "pending_uv_seam_material_and_gltf_handoff_review",
        "explicit_non_claims": [
            "This is not a production GLB.",
            (
                f"This {texture_label(args.texture_size)} local-contact AO output is a "
                "candidate only and does not grant P50 approval."
            ),
            "glTF Validator, KTX2/Meshopt and browser performance belong to P60.",
            "Platforms, towers, internals, sensors and L7-L16 overlays are deliberately excluded from AO.",
        ],
    }
    report_path = output_dir / "p50_full_furnace_bake_candidate.json"
    report_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    manifest = {
        "schema_version": 1,
        "stage": "P50_FULL_FURNACE_BAKE_CANDIDATE",
        "candidate": candidate,
        "atlas": {
            "layout_id": atlas["layout_id"],
            "uv_layer": UV_NAME,
            "targets": list(TARGETS),
            "texture_size": args.texture_size,
            "margin_px": args.margin,
            "island_count": atlas["island_count"],
            "unique_island_count": atlas["unique_island_count"],
            "column_count": atlas["column_count"],
            "minimum_gap_uv": atlas["minimum_gap_uv"],
            "minimum_outer_margin_uv": atlas["minimum_outer_margin_uv"],
            "texels_per_meter": atlas["effective_texels_per_meter"],
            "active_pixel_ratio": image_metrics["BaseColor"]["active_pixel_ratio"],
        },
        "maps": files,
        "semantics": {
            "BaseColor": {"colorspace": "sRGB", "lighting_baked": False},
            "Roughness": {"colorspace": "Non-Color"},
            "Metallic": {
                "colorspace": "Non-Color",
                "bare_steel_cap": METALLIC_BARE_STEEL_VALUE,
                "transition": "wide EASE",
                "source_scope": "P50 transient bake graph only",
            },
            "AO": {
                "colorspace": "Non-Color",
                "mode": AO_MODE,
                "distance_m": AO_DISTANCE_M,
                "strength": AO_STRENGTH,
                "floor": AO_FLOOR,
                "detail_occluders": list(AO_DETAIL_OCCLUDERS),
            },
            "NormalGL": {
                "colorspace": "Non-Color",
                "convention": "OpenGL +Y",
                "encoding_amplification": NORMAL_BAKE_ENCODING_AMPLIFICATION,
                "runtime_scale": NORMAL_RUNTIME_SCALE,
            },
            "ORM": {
                "colorspace": "Non-Color",
                "channels": {"R": "AO", "G": "Roughness", "B": "Metallic", "A": 1},
            },
        },
        "preserved_contract": {
            "sensors": 115,
            "body_temperature_sensors": 80,
            "temperature_layers": list(EXPECTED_LAYERS),
        },
        "next_gate": "P60 uncompressed GLB export, glTF Validator and Three.js browser verification",
    }
    manifest_path = output_dir / "p50_texture_manifest.json"
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(
        json.dumps(
            {
                "status": status,
                "report": str(report_path),
                "manifest": str(manifest_path),
                "candidate": candidate,
                "device": device,
                "timings_seconds": timings,
                "preview": preview,
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0 if ok else 2


if __name__ == "__main__":
    raise SystemExit(main())
