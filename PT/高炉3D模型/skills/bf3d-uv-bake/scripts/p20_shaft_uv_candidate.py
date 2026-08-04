"""Create an analytic, texel-density-aware UV candidate for the shaft only."""

from __future__ import annotations

import argparse
import json
import math
import statistics
import sys
from pathlib import Path

import bpy
from mathutils import Vector

AUDIT_SCRIPT_DIR = Path(__file__).resolve().parents[2] / "bf3d-geometry-audit" / "scripts"
sys.path.insert(0, str(AUDIT_SCRIPT_DIR))
import p00_import_audit as p00  # noqa: E402


TARGET = "APPROX_GL02_FURNACE_SHAFT"
UV_NAME = "BF3D_UV0"
MARGIN = 0.04
# Two 16 px bake dilations need a 32 px total gutter between neighbouring islands.
ISLAND_GAP = max(32.0 / 4096.0, 0.008)
SEAM_TOLERANCE = 1e-5


def parse_args() -> argparse.Namespace:
    argv = sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else []
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-glb", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--resolution", type=int, default=768)
    return parser.parse_args(argv)


def geometry_sha256(mesh: bpy.types.Mesh) -> str:
    import hashlib
    import struct

    digest = hashlib.sha256()
    for vertex in mesh.vertices:
        digest.update(struct.pack("<3d", *(float(value) for value in vertex.co)))
    for polygon in mesh.polygons:
        digest.update(struct.pack("<I", len(polygon.vertices)))
        for index in polygon.vertices:
            digest.update(struct.pack("<I", int(index)))
    return digest.hexdigest()


def phase_u(co: Vector, center_x: float, center_y: float) -> float:
    """Return a clockwise phase with Blender +Y fixed at the intentional seam."""

    return (math.atan2(float(co.x) - center_x, float(co.y) - center_y) % math.tau) / math.tau


def signed_loop_area(loop_indices: list[int], coordinates: dict[int, tuple[float, float]]) -> float:
    values = [coordinates[index] for index in loop_indices]
    return sum(
        values[index][0] * values[(index + 1) % len(values)][1]
        - values[(index + 1) % len(values)][0] * values[index][1]
        for index in range(len(values))
    ) * 0.5


def build_uv(obj: bpy.types.Object) -> dict[str, object]:
    mesh = obj.data
    if mesh.uv_layers:
        raise RuntimeError(f"{TARGET} already has UV layers: {[layer.name for layer in mesh.uv_layers]}")
    world_by_vertex = {vertex.index: obj.matrix_world @ vertex.co for vertex in mesh.vertices}
    center_x = statistics.mean(float(co.x) for co in world_by_vertex.values())
    center_y = statistics.mean(float(co.y) for co in world_by_vertex.values())
    row_vertices: dict[float, list[int]] = {}
    for vertex in mesh.vertices:
        world = world_by_vertex[vertex.index]
        row_vertices.setdefault(round(float(world.z), 6), []).append(vertex.index)
    if len(row_vertices) < 2:
        raise RuntimeError("The shaft mesh does not contain enough profile rows")
    row_data: list[dict[str, object]] = []
    for z_value in sorted(row_vertices):
        radii = [
            math.hypot(float(world_by_vertex[index].x) - center_x, float(world_by_vertex[index].y) - center_y)
            for index in row_vertices[z_value]
        ]
        row_data.append(
            {
                "index": len(row_data),
                "z": z_value,
                "radius": statistics.mean(radii),
                "vertices": len(row_vertices[z_value]),
            }
        )
    row_index_by_z = {float(row["z"]): int(row["index"]) for row in row_data}

    bands: list[dict[str, object]] = []
    for index in range(len(row_data) - 1):
        lower = row_data[index]
        upper = row_data[index + 1]
        dr = float(upper["radius"]) - float(lower["radius"])
        dz = float(upper["z"]) - float(lower["z"])
        slant = math.hypot(dz, dr)
        q_value = abs(dr)
        bands.append(
            {
                "index": index,
                "lower_row": index,
                "upper_row": index + 1,
                "z0": float(lower["z"]),
                "z1": float(upper["z"]),
                "r0": float(lower["radius"]),
                "r1": float(upper["radius"]),
                "dr": dr,
                "slant_m": slant,
                "sector_angle_rad": math.tau * q_value / slant if q_value > 1e-9 else 0.0,
                "mapping": "annular_sector" if q_value > 1e-9 else "cylinder_fallback",
            }
        )

    raw_coordinates: dict[int, tuple[float, float]] = {}
    loop_band: dict[int, int] = {}
    seam_faces = 0
    for polygon in mesh.polygons:
        vertex_indices = [mesh.loops[loop_index].vertex_index for loop_index in polygon.loop_indices]
        row_indices = [row_index_by_z[round(float(world_by_vertex[index].z), 6)] for index in vertex_indices]
        if max(row_indices) - min(row_indices) != 1:
            raise RuntimeError(f"Polygon {polygon.index} does not belong to one adjacent profile band: {row_indices}")
        band_index = min(row_indices)
        band = bands[band_index]
        base_values = [phase_u(world_by_vertex[index], center_x, center_y) for index in vertex_indices]
        wraps_seam = max(base_values) - min(base_values) > 0.5
        seam_faces += int(wraps_seam)
        for loop_index, base_u in zip(polygon.loop_indices, base_values):
            vertex_index = mesh.loops[loop_index].vertex_index
            world = world_by_vertex[vertex_index]
            if wraps_seam and base_u < 0.5:
                base_u += 1.0
            radius = math.hypot(float(world.x) - center_x, float(world.y) - center_y)
            if band["mapping"] == "annular_sector":
                q_value = abs(float(band["dr"]))
                rho = float(band["slant_m"]) * radius / q_value
                psi = float(band["sector_angle_rad"]) * (base_u - 0.5)
                raw_x = rho * math.sin(psi)
                raw_y = math.copysign(1.0, float(band["dr"])) * rho * math.cos(psi)
            else:
                raw_x = math.tau * radius * (base_u - 0.5)
                raw_y = 0.0 if row_indices[vertex_indices.index(vertex_index)] == band_index else float(band["slant_m"])
            raw_coordinates[loop_index] = (raw_x, raw_y)
            loop_band[loop_index] = band_index

    for band in bands:
        band_index = int(band["index"])
        positive = 0
        negative = 0
        for polygon in mesh.polygons:
            if loop_band[polygon.loop_indices[0]] != band_index:
                continue
            signed = signed_loop_area(list(polygon.loop_indices), raw_coordinates)
            positive += int(signed > 1e-12)
            negative += int(signed < -1e-12)
        flip_x = negative > positive
        band["orientation_flip_x"] = flip_x
        if flip_x:
            for loop_index in [index for index, value in loop_band.items() if value == band_index]:
                raw_x, raw_y = raw_coordinates[loop_index]
                raw_coordinates[loop_index] = (-raw_x, raw_y)

    for band in bands:
        band_index = int(band["index"])
        points = [raw_coordinates[index] for index, value in loop_band.items() if value == band_index]
        min_x = min(value[0] for value in points)
        max_x = max(value[0] for value in points)
        min_y = min(value[1] for value in points)
        max_y = max(value[1] for value in points)
        band["raw_bounds_m"] = {"min_x": min_x, "max_x": max_x, "min_y": min_y, "max_y": max_y}
        band["raw_width_m"] = max_x - min_x
        band["raw_height_m"] = max_y - min_y

    available = 1.0 - 2.0 * MARGIN
    max_width = max(float(band["raw_width_m"]) for band in bands)
    sum_heights = sum(float(band["raw_height_m"]) for band in bands)
    texel_scale = min(available / max_width, (available - ISLAND_GAP * (len(bands) - 1)) / sum_heights)
    uv_layer = mesh.uv_layers.new(name=UV_NAME, do_init=False)
    cursor_v = MARGIN
    island_bounds: list[dict[str, object]] = []
    for band in bands:
        band_index = int(band["index"])
        raw_bounds = band["raw_bounds_m"]
        center_raw_x = (float(raw_bounds["min_x"]) + float(raw_bounds["max_x"])) * 0.5
        for loop_index in [index for index, value in loop_band.items() if value == band_index]:
            raw_x, raw_y = raw_coordinates[loop_index]
            u_value = 0.5 + (raw_x - center_raw_x) * texel_scale
            v_value = cursor_v + (raw_y - float(raw_bounds["min_y"])) * texel_scale
            uv_layer.uv[loop_index].vector = (u_value, v_value)
        island_width = float(band["raw_width_m"]) * texel_scale
        island_height = float(band["raw_height_m"]) * texel_scale
        packed = {
            "band": band_index,
            "min_u": 0.5 - island_width * 0.5,
            "max_u": 0.5 + island_width * 0.5,
            "min_v": cursor_v,
            "max_v": cursor_v + island_height,
        }
        island_bounds.append(packed)
        band["packed_bounds"] = packed
        cursor_v += island_height + ISLAND_GAP

    vertical_seam_edges = 0
    horizontal_seam_edges = 0
    internal_rows = {round(float(row["z"]), 6) for row in row_data[1:-1]}
    for edge in mesh.edges:
        edge.use_seam = False
        worlds = [world_by_vertex[index] for index in edge.vertices]
        values = [phase_u(world, center_x, center_y) for world in worlds]
        same_height = abs(float(worlds[0].z) - float(worlds[1].z)) <= 1e-6
        is_vertical_seam = not same_height and all(min(value, 1.0 - value) < SEAM_TOLERANCE for value in values)
        is_horizontal_seam = same_height and round(float(worlds[0].z), 6) in internal_rows
        if is_vertical_seam or is_horizontal_seam:
            edge.use_seam = True
            vertical_seam_edges += int(is_vertical_seam)
            horizontal_seam_edges += int(is_horizontal_seam)
    mesh.uv_layers.active = uv_layer
    uv_layer.active_render = True
    mesh.update()
    minimum_gap = min(
        float(island_bounds[index + 1]["min_v"]) - float(island_bounds[index]["max_v"])
        for index in range(len(island_bounds) - 1)
    )
    return {
        "profile_rows": row_data,
        "bands": bands,
        "island_bounds": island_bounds,
        "island_count": len(island_bounds),
        "island_gap": ISLAND_GAP,
        "minimum_packed_gap": minimum_gap,
        "uv_units_per_meter": texel_scale,
        "seam_location": "Blender +Y / default camera back side",
        "seam_faces": seam_faces,
        "vertical_seam_edges": vertical_seam_edges,
        "horizontal_seam_edges": horizontal_seam_edges,
        "seam_edges": vertical_seam_edges + horizontal_seam_edges,
        "center_world_xy": [center_x, center_y],
    }


def polygon_uv_area(mesh: bpy.types.Mesh, uv_layer: bpy.types.MeshUVLoopLayer, polygon: bpy.types.MeshPolygon) -> float:
    values = [uv_layer.uv[index].vector for index in polygon.loop_indices]
    return abs(sum(float(values[index].x) * float(values[(index + 1) % len(values)].y) - float(values[(index + 1) % len(values)].x) * float(values[index].y) for index in range(len(values)))) * 0.5


def polygon_world_area(obj: bpy.types.Object, polygon: bpy.types.MeshPolygon) -> float:
    mesh = obj.data
    points = [obj.matrix_world @ mesh.vertices[index].co for index in polygon.vertices]
    origin = points[0]
    return sum(float((points[index] - origin).cross(points[index + 1] - origin).length) * 0.5 for index in range(1, len(points) - 1))


def uv_island_count(mesh: bpy.types.Mesh) -> int:
    edge_index_by_key = {tuple(sorted(edge.vertices)): edge.index for edge in mesh.edges}
    edge_faces: dict[int, list[int]] = {}
    for polygon in mesh.polygons:
        vertices = list(polygon.vertices)
        for index, vertex in enumerate(vertices):
            key = tuple(sorted((vertex, vertices[(index + 1) % len(vertices)])))
            edge_faces.setdefault(edge_index_by_key[key], []).append(polygon.index)
    adjacency = {polygon.index: set() for polygon in mesh.polygons}
    for edge_index, faces in edge_faces.items():
        if mesh.edges[edge_index].use_seam or len(faces) != 2:
            continue
        adjacency[faces[0]].add(faces[1])
        adjacency[faces[1]].add(faces[0])
    unseen = set(adjacency)
    islands = 0
    while unseen:
        islands += 1
        stack = [unseen.pop()]
        while stack:
            face = stack.pop()
            connected = adjacency[face] & unseen
            unseen.difference_update(connected)
            stack.extend(connected)
    return islands


def non_seam_uv_discontinuity(mesh: bpy.types.Mesh, uv_layer: bpy.types.MeshUVLoopLayer) -> float:
    edge_by_key = {tuple(sorted(edge.vertices)): edge for edge in mesh.edges}
    samples: dict[tuple[int, int], list[dict[int, Vector]]] = {}
    for polygon in mesh.polygons:
        loops = list(polygon.loop_indices)
        for index, loop_index in enumerate(loops):
            next_loop = loops[(index + 1) % len(loops)]
            vertex = mesh.loops[loop_index].vertex_index
            next_vertex = mesh.loops[next_loop].vertex_index
            key = tuple(sorted((vertex, next_vertex)))
            samples.setdefault(key, []).append(
                {
                    vertex: uv_layer.uv[loop_index].vector.copy(),
                    next_vertex: uv_layer.uv[next_loop].vector.copy(),
                }
            )
    maximum = 0.0
    for key, face_samples in samples.items():
        edge = edge_by_key[key]
        if edge.use_seam or len(face_samples) != 2:
            continue
        for vertex in key:
            maximum = max(maximum, float((face_samples[0][vertex] - face_samples[1][vertex]).length))
    return maximum


def uv_metrics(obj: bpy.types.Object, uv_design: dict[str, object]) -> dict[str, object]:
    mesh = obj.data
    uv_layer = mesh.uv_layers.get(UV_NAME)
    values = [uv_layer.uv[index].vector.copy() for index in range(len(mesh.loops))]
    densities: list[float] = []
    density_by_band: dict[int, list[float]] = {int(band["index"]): [] for band in uv_design["bands"]}
    row_index_by_z = {round(float(row["z"]), 6): int(row["index"]) for row in uv_design["profile_rows"]}
    zero_area_faces = 0
    signed_orientations = {"positive": 0, "negative": 0, "zero": 0}
    for polygon in mesh.polygons:
        uv_area = polygon_uv_area(mesh, uv_layer, polygon)
        world_area = polygon_world_area(obj, polygon)
        if uv_area <= 1e-12 or world_area <= 1e-12:
            zero_area_faces += 1
        else:
            density = math.sqrt(uv_area / world_area)
            densities.append(density)
            rows = [row_index_by_z[round(float((obj.matrix_world @ mesh.vertices[index].co).z), 6)] for index in polygon.vertices]
            density_by_band[min(rows)].append(density)
        uv = [uv_layer.uv[index].vector for index in polygon.loop_indices]
        signed = sum(float(uv[index].x) * float(uv[(index + 1) % len(uv)].y) - float(uv[(index + 1) % len(uv)].x) * float(uv[index].y) for index in range(len(uv))) * 0.5
        signed_orientations["positive" if signed > 1e-12 else "negative" if signed < -1e-12 else "zero"] += 1
    median_density = statistics.median(densities)
    deviations = [abs(value / median_density - 1.0) for value in densities]
    band_density = []
    for band_index, band_values in sorted(density_by_band.items()):
        average = statistics.mean(band_values)
        band_density.append(
            {
                "band": band_index,
                "faces": len(band_values),
                "average_uv_per_meter": average,
                "relative_deviation_from_global_median": abs(average / median_density - 1.0),
            }
        )
    return {
        "uv_layer": UV_NAME,
        "loops": len(values),
        "faces": len(mesh.polygons),
        "island_count": uv_island_count(mesh),
        "non_seam_max_uv_discontinuity": non_seam_uv_discontinuity(mesh, uv_layer),
        "overlap_face_pairs_by_packed_island_bounds": 0,
        "bounds": {
            "min_u": min(float(value.x) for value in values),
            "max_u": max(float(value.x) for value in values),
            "min_v": min(float(value.y) for value in values),
            "max_v": max(float(value.y) for value in values),
        },
        "zero_area_faces": zero_area_faces,
        "density": {
            "median_uv_per_meter": median_density,
            "min_uv_per_meter": min(densities),
            "max_uv_per_meter": max(densities),
            "max_relative_deviation": max(deviations),
            "p95_relative_deviation": sorted(deviations)[max(0, math.ceil(len(deviations) * 0.95) - 1)],
            "bands": band_density,
            "maximum_band_average_deviation": max(value["relative_deviation_from_global_median"] for value in band_density),
        },
        "orientation": signed_orientations,
    }


def look_at(obj: bpy.types.Object, target: Vector) -> None:
    obj.rotation_euler = (target - obj.location).to_track_quat("-Z", "Y").to_euler()


def make_checker_material() -> bpy.types.Material:
    checker = bpy.data.materials.new("P20_SHAFT_UV_CHECKER")
    checker.use_nodes = True
    nodes = checker.node_tree.nodes
    links = checker.node_tree.links
    for node in list(nodes):
        nodes.remove(node)
    output = nodes.new("ShaderNodeOutputMaterial")
    principled = nodes.new("ShaderNodeBsdfPrincipled")
    texcoord = nodes.new("ShaderNodeTexCoord")
    checker_node = nodes.new("ShaderNodeTexChecker")
    checker_node.inputs["Color1"].default_value = (0.018, 0.13, 0.16, 1.0)
    checker_node.inputs["Color2"].default_value = (0.72, 0.82, 0.80, 1.0)
    checker_node.inputs["Scale"].default_value = 32.0
    principled.inputs["Metallic"].default_value = 0.0
    principled.inputs["Roughness"].default_value = 1.0
    if "Specular IOR Level" in principled.inputs:
        principled.inputs["Specular IOR Level"].default_value = 0.0
    links.new(texcoord.outputs["UV"], checker_node.inputs["Vector"])
    links.new(checker_node.outputs["Color"], principled.inputs["Base Color"])
    links.new(principled.outputs["BSDF"], output.inputs["Surface"])
    return checker


def render_checker(output_dir: Path, resolution: int, shaft: bpy.types.Object) -> list[dict[str, object]]:
    scene = bpy.context.scene
    checker = make_checker_material()
    material_state = {obj.name: [material for material in obj.data.materials] for obj in bpy.data.objects if obj.type == "MESH"}
    hidden_state = {obj.name: bool(obj.hide_render) for obj in bpy.data.objects}
    for obj in bpy.data.objects:
        if obj.type != "MESH":
            continue
        obj.hide_render = obj != shaft
        if obj == shaft:
            obj.data.materials.clear()
            obj.data.materials.append(checker)
    scene.render.engine = "BLENDER_EEVEE"
    scene.render.resolution_x = resolution
    scene.render.resolution_y = resolution
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = "PNG"
    scene.render.film_transparent = False
    try:
        scene.view_settings.view_transform = "AgX"
    except TypeError:
        pass
    scene.view_settings.exposure = 0.55
    scene.world.use_nodes = True
    background = scene.world.node_tree.nodes.get("Background")
    background.inputs["Color"].default_value = (0.012, 0.018, 0.024, 1.0)
    background.inputs["Strength"].default_value = 0.45

    minimum, maximum = p00.object_bounds([shaft])
    center = (minimum + maximum) * 0.5
    size = maximum - minimum
    span = max(float(size.x), float(size.y), float(size.z), 1.0)
    distance = span * 2.2
    p00.add_sun_light("P20_KEY", center + Vector((span, -span, span)), center, 2.6, (1.0, 0.90, 0.80))
    p00.add_sun_light("P20_FILL", center + Vector((-span, -span * 0.3, span * 0.4)), center, 1.0, (0.75, 0.86, 1.0))
    p00.add_sun_light("P20_RIM", center + Vector((0.3 * span, span, span)), center, 1.7, (0.55, 0.72, 1.0))
    camera_data = bpy.data.cameras.new("P20_FIXED_CAMERA")
    camera_data.type = "ORTHO"
    camera = bpy.data.objects.new("P20_FIXED_CAMERA", camera_data)
    scene.collection.objects.link(camera)
    scene.camera = camera
    views = {
        "front": center + Vector((0.0, -distance, 0.0)),
        "back": center + Vector((0.0, distance, 0.0)),
        "left": center + Vector((-distance, 0.0, 0.0)),
        "right": center + Vector((distance, 0.0, 0.0)),
        "iso": center + Vector((distance * 0.75, -distance * 0.75, distance * 0.28)),
    }
    camera_data.ortho_scale = max(float(size.z), float(size.x), float(size.y)) * 1.16
    render_dir = output_dir / "renders"
    render_dir.mkdir(parents=True, exist_ok=True)
    results: list[dict[str, object]] = []
    for name, location in views.items():
        camera.location = location
        look_at(camera, center)
        path = render_dir / f"P20_SHAFT_UV_{name}.png"
        scene.render.filepath = str(path)
        bpy.ops.render.render(write_still=True)
        results.append({"view": name, "path": str(path), "sha256": p00.sha256_file(path)})
    for obj in bpy.data.objects:
        if obj.type == "MESH" and obj.name in material_state:
            obj.data.materials.clear()
            for material in material_state[obj.name]:
                obj.data.materials.append(material)
        if obj.name in hidden_state:
            obj.hide_render = hidden_state[obj.name]
    return results


def main() -> int:
    args = parse_args()
    output_dir = args.output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    source_glb = args.source_glb.resolve()
    input_blend = Path(bpy.data.filepath).resolve()
    if bpy.context.scene.get("bf3d_stage") != "P10_NORMALS_CANDIDATE":
        raise RuntimeError(f"Expected P10_NORMALS_CANDIDATE, got {bpy.context.scene.get('bf3d_stage')!r}")
    shaft = bpy.data.objects.get(TARGET)
    if shaft is None or shaft.type != "MESH":
        raise RuntimeError(f"Missing target mesh: {TARGET}")
    source = p00.source_node_contract(p00.read_glb_json(source_glb))
    sensor_before = p00.imported_contract(source)["sensor_records"]
    geometry_before = geometry_sha256(shaft.data)
    all_uv_before = {obj.name: [layer.name for layer in obj.data.uv_layers] for obj in bpy.data.objects if obj.type == "MESH"}
    uv_design = build_uv(shaft)
    metrics = uv_metrics(shaft, uv_design)
    geometry_after = geometry_sha256(shaft.data)
    sensor_after = p00.imported_contract(source)["sensor_records"]
    other_uv_changes = {
        obj.name: {"before": all_uv_before[obj.name], "after": [layer.name for layer in obj.data.uv_layers]}
        for obj in bpy.data.objects
        if obj.type == "MESH" and obj.name != TARGET and all_uv_before[obj.name] != [layer.name for layer in obj.data.uv_layers]
    }
    bounds = metrics["bounds"]
    assertions = [
        {"id": "input_stage_is_p10_normals", "ok": bpy.context.scene.get("bf3d_stage") == "P10_NORMALS_CANDIDATE"},
        {"id": "source_glb_matches_lock", "ok": p00.sha256_file(source_glb) == p00.EXPECTED_SOURCE_SHA256},
        {"id": "shaft_geometry_unchanged", "ok": geometry_before == geometry_after, "detail": {"before": geometry_before, "after": geometry_after}},
        {"id": "sensors_unchanged", "ok": sensor_before == sensor_after},
        {"id": "only_shaft_received_uv", "ok": not other_uv_changes, "detail": other_uv_changes},
        {"id": "shaft_has_one_uv_layer", "ok": [layer.name for layer in shaft.data.uv_layers] == [UV_NAME], "detail": [layer.name for layer in shaft.data.uv_layers]},
        {"id": "uv_has_no_zero_area_faces", "ok": metrics["zero_area_faces"] == 0, "detail": metrics["zero_area_faces"]},
        {"id": "uv_stays_in_zero_one", "ok": bounds["min_u"] >= -1e-6 and bounds["max_u"] <= 1.0 + 1e-6 and bounds["min_v"] >= -1e-6 and bounds["max_v"] <= 1.0 + 1e-6, "detail": bounds},
        {"id": "uv_respects_margin", "ok": bounds["min_u"] >= MARGIN - 1e-4 and bounds["max_u"] <= 1.0 - MARGIN + 1e-4 and bounds["min_v"] >= MARGIN - 1e-4 and bounds["max_v"] <= 1.0 - MARGIN + 1e-4, "detail": bounds},
        {"id": "uv_has_exactly_three_islands", "ok": metrics["island_count"] == 3 and uv_design["island_count"] == 3, "detail": {"topology": metrics["island_count"], "design": uv_design["island_count"]}},
        {"id": "uv_islands_keep_two_sided_4k_16px_dilation", "ok": uv_design["minimum_packed_gap"] >= ISLAND_GAP - 1e-6, "detail": {"minimum": uv_design["minimum_packed_gap"], "required": ISLAND_GAP}},
        {"id": "non_seam_uv_edges_are_continuous", "ok": metrics["non_seam_max_uv_discontinuity"] <= 1e-6, "detail": metrics["non_seam_max_uv_discontinuity"]},
        {"id": "texel_density_face_deviation_within_3_percent", "ok": metrics["density"]["max_relative_deviation"] <= 0.03, "detail": metrics["density"]},
        {"id": "texel_density_band_average_within_2_percent", "ok": metrics["density"]["maximum_band_average_deviation"] <= 0.02, "detail": metrics["density"]["bands"]},
        {"id": "all_uv_faces_have_positive_orientation", "ok": metrics["orientation"]["positive"] == len(shaft.data.polygons) and metrics["orientation"]["negative"] == 0 and metrics["orientation"]["zero"] == 0, "detail": metrics["orientation"]},
        {"id": "expected_three_vertical_seams", "ok": uv_design["vertical_seam_edges"] == 3, "detail": uv_design["vertical_seam_edges"]},
        {"id": "expected_two_horizontal_ring_seams", "ok": uv_design["horizontal_seam_edges"] == 320, "detail": uv_design["horizontal_seam_edges"]},
        {"id": "expected_total_seam_edges", "ok": uv_design["seam_edges"] == 323, "detail": uv_design["seam_edges"]},
    ]
    ok = all(bool(item["ok"]) for item in assertions)
    candidate_path = output_dir / "P20_SHAFT_UV_CANDIDATE.blend"
    candidate = None
    if ok:
        scene = bpy.context.scene
        scene["bf3d_stage"] = "P20_SHAFT_UV_CANDIDATE"
        scene["bf3d_parent_checkpoint"] = str(input_blend)
        scene["bf3d_change_dimension"] = "shaft_uv_only"
        scene["bf3d_uv_target"] = TARGET
        bpy.ops.wm.save_as_mainfile(filepath=str(candidate_path), check_existing=False)
        candidate = {"path": str(candidate_path), "bytes": candidate_path.stat().st_size, "sha256": p00.sha256_file(candidate_path)}
    renders = render_checker(output_dir, max(256, min(args.resolution, 2048)), shaft) if ok else []
    status = "candidate_ready_for_visual_review" if ok and len(renders) == 5 else "fail"
    report = {
        "schema_version": 1,
        "stage": "P20_SHAFT_UV_CANDIDATE",
        "status": status,
        "single_changed_dimension": "Three exact annular-sector UV islands on APPROX_GL02_FURNACE_SHAFT only.",
        "input_checkpoint": {"path": str(input_blend), "sha256": p00.sha256_file(input_blend)},
        "candidate": candidate,
        "target": TARGET,
        "uv_design": uv_design,
        "uv_metrics": metrics,
        "assertions": assertions,
        "renders": renders,
        "approval": "pending_visual_checker_review",
    }
    report_path = output_dir / "p20_shaft_uv_candidate.json"
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": status, "report": str(report_path), "candidate": candidate, "uv_metrics": metrics}, ensure_ascii=False, indent=2))
    return 0 if status == "candidate_ready_for_visual_review" else 2


if __name__ == "__main__":
    raise SystemExit(main())
