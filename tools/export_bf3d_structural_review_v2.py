"""Export clean Blender/Web assets for GL02 material and structural review.

Requirement:
    REQ-BF3D-CLEAN-STRUCTURAL-REVIEW-20260719

This exporter corrects the V1 delivery boundary.  The V1 GLB retained the
operational base scene (sensors, process guides and legacy animation meshes)
and depended on Three.js to hide those objects.  A direct Blender import does
not run that controller.

Outputs:
    - material-review GLB: five R2J closed shell entities carrying the R5 PBR
      exterior; no sensors, rings, guides, particles or process decoration.
    - structural-review GLB: a physically opened half-section of R2J/R2K with
      material-specific Web PBR textures; no runtime clipping is required.
    - review Blend: full and section collections, packed textures, camera and
      lighting, ready to open directly in Blender.

All dimensions and internal material identities remain E/illustrative and are
not construction data.  Historical V1 and formal GLBs are never overwritten.
"""

from __future__ import annotations

import hashlib
import json
import math
import struct
from collections import Counter
from pathlib import Path

import bmesh
import bpy
import numpy as np
from mathutils import Matrix, Vector


ROOT = Path(r"D:\文件\冀南钢铁运行中第二版本")
BASE_GLB = (
    ROOT
    / "PT"
    / "高炉3D模型"
    / "work"
    / "INT_30_20260718_R2H_WEB_DETAIL_NORMAL"
    / "input"
    / "INT_30_R2G_BASE_R1_R5_UNCHANGED.glb"
)
R2K_BLEND = (
    ROOT
    / "PT"
    / "高炉3D模型"
    / "work"
    / "INT_30_20260719_R2K_WALL_INTERNAL_SOLIDS"
    / "blends"
    / "INT_30_R2K_WALL_INTERNAL_SOLIDS_CANDIDATE.blend"
)
FORMAL_GLB = ROOT / "高炉前端数据" / "models" / "gl02_blast_furnace.glb"
V1_GLB = (
    ROOT
    / "高炉前端数据"
    / "models"
    / "gl02_blast_furnace_structural_review.v1.glb"
)
MATERIAL_GLB = (
    ROOT
    / "高炉前端数据"
    / "models"
    / "gl02_blast_furnace_material_review.v2.glb"
)
STRUCTURAL_GLB = (
    ROOT
    / "高炉前端数据"
    / "models"
    / "gl02_blast_furnace_structural_review.v2.glb"
)
REVIEW_BLEND = (
    ROOT
    / "高炉前端数据"
    / "models"
    / "gl02_blast_furnace_structural_review.v2.blend"
)
STAGE = (
    ROOT
    / "PT"
    / "高炉3D模型"
    / "work"
    / "WEB_60_20260719_R2P_CLEAN_STRUCTURAL_REVIEW"
)
TEXTURE_DIR = STAGE / "textures"
PREVIEW_DIR = STAGE / "renders"
MANIFEST_PATH = STRUCTURAL_GLB.with_suffix(".manifest.json")
STAGE_MANIFEST_PATH = STAGE / "clean_structural_review_manifest.json"

EXPECTED_BASE_SHA256 = (
    "9db82c83f2e3c8c78aff38c2b71810fcabb8394806f765d94280bedb0145f952"
)
EXPECTED_R2K_SHA256 = (
    "51fb6f57fe06ff923de5ea823aca8ba0fb51382d757b768a0669ce74b85bba68"
)
EXPECTED_FORMAL_SHA256 = (
    "808960f1b2703e7fb27df35f1b1b1a17063b9b10d2267acba593fc3872b62af6"
)
EXPECTED_V1_SHA256 = (
    "859819f415feee0533018daf3290c65c69b607352d8e8e34735e952d8f3772fd"
)

REQUIREMENT_ID = "REQ-BF3D-CLEAN-STRUCTURAL-REVIEW-20260719"
ASSET_ID = "GL02_CLEAN_STRUCTURAL_REVIEW_V2"
ZONES = ("HEARTH", "BOSH", "BELLY", "SHAFT", "THROAT")
STRUCTURAL_PREFIXES = (
    "R2J_ASM_GL02_FURNACE_",
    "R2K_L02_BACKFILL_40MM_CLOSED_ENTITY_E",
    "R2K_L04_HOTFACE_EMBED_40MM_CLOSED_ENTITY_E",
    "R2K_L05_RESIDUAL_REFRACTORY_CLOSED_ENTITY_E",
    "R2K_L06_IRREGULAR_SKULL_STATE_LAYER_MISSING_E",
    "SM_BF3D_GL02_CST_",
)
FORBIDDEN_TOKENS = (
    "SENSOR_",
    "PRESSURE",
    "FLOW",
    "STREAMLINE",
    "BURDEN",
    "TEMP_LAYER",
    "PARTICLE",
    "GUIDE",
    "REFERENCE_BAND",
    "STIFFENER_RING",
    "COOLING_BAND",
    "ACCESS_TOWER",
    "SUPPORT_FRAME",
    "SKULL_STATE_LAYER_MISSING",
)


def sha256(path: Path) -> str:
    """Return the lower-case SHA-256 digest of *path*."""

    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def rel(path: Path) -> str:
    """Return a repository-relative POSIX path."""

    return path.relative_to(ROOT).as_posix()


def check_locked(path: Path, expected: str, label: str) -> None:
    """Fail closed when a controlled source or rollback asset drifts."""

    if not path.is_file():
        raise RuntimeError(f"{label} is missing: {path}")
    actual = sha256(path)
    if actual != expected:
        raise RuntimeError(
            f"{label} SHA-256 drifted: expected={expected}, actual={actual}"
        )


def reset_scene() -> None:
    """Remove the startup scene and all unused scene datablocks."""

    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete(use_global=False)
    for block in (bpy.data.meshes, bpy.data.curves, bpy.data.cameras, bpy.data.lights):
        for item in list(block):
            if item.users == 0:
                block.remove(item)


def import_r5_material_source() -> dict[str, bpy.types.Material]:
    """Import the controlled R5 base and return one exterior material per zone."""

    bpy.ops.import_scene.gltf(filepath=str(BASE_GLB))
    result: dict[str, bpy.types.Material] = {}
    for zone in ZONES:
        obj = bpy.data.objects.get(f"APPROX_GL02_FURNACE_{zone}")
        if obj is None or obj.type != "MESH" or not obj.material_slots:
            raise RuntimeError(f"missing R5 material source for {zone}")
        material = obj.material_slots[0].material
        if material is None:
            raise RuntimeError(f"R5 material is empty for {zone}")
        result[zone] = material
    return result


def append_structural_objects() -> list[bpy.types.Object]:
    """Append only the five R2J entities and R2K structural layer objects."""

    with bpy.data.libraries.load(str(R2K_BLEND), link=False) as (source, target):
        target.objects = [
            name
            for name in source.objects
            if any(name.startswith(prefix) for prefix in STRUCTURAL_PREFIXES)
        ]
    appended = [obj for obj in target.objects if obj is not None]
    for obj in appended:
        if not obj.users_collection:
            bpy.context.scene.collection.objects.link(obj)
    if len([obj for obj in appended if obj.name.startswith("R2J_ASM_")]) != 5:
        raise RuntimeError("R2J five-zone entity count is not 5")
    if len([obj for obj in appended if obj.name.startswith("SM_BF3D_GL02_CST_")]) != 560:
        raise RuntimeError("R2K cooling stave count is not 560")
    return appended


def object_is_alive(obj: bpy.types.Object | None) -> bool:
    """Return whether *obj* remains linked to the current scene."""

    if obj is None:
        return False
    try:
        return obj.name in bpy.context.scene.objects
    except ReferenceError:
        return False


def role_for(obj: bpy.types.Object) -> str:
    """Map source names to stable review roles."""

    name = obj.name.removeprefix("SECTION_")
    if name.startswith("R2J_ASM_"):
        return "steel_shell"
    if name.startswith("R2K_L02_"):
        return "backfill"
    if name.startswith("R2K_L04_"):
        return "hotface_embed"
    if name.startswith("R2K_L05_"):
        return "refractory"
    if name.startswith("R2K_L06_"):
        return "skull_optional_missing"
    if name.startswith("SM_BF3D_GL02_CST_") or name.startswith(
        "R2K_V2_L03_COOLING_"
    ):
        return "cooling_stave"
    return "unknown"


def join_stave_family(
    objects: list[bpy.types.Object], token: str, output_name: str
) -> bpy.types.Object:
    """Merge one cooling-stave family into a Web-efficient mesh."""

    staves = [
        obj
        for obj in objects
        if object_is_alive(obj)
        and obj.type == "MESH"
        and obj.name.startswith("SM_BF3D_GL02_CST_")
        and token in obj.name
    ]
    if not staves:
        raise RuntimeError(f"no cooling staves found for {token}")
    bpy.ops.object.select_all(action="DESELECT")
    for obj in staves:
        obj.hide_set(False)
        obj.hide_viewport = False
        obj.select_set(True)
    bpy.context.view_layer.objects.active = staves[0]
    bpy.ops.object.join()
    joined = bpy.context.view_layer.objects.active
    joined.name = output_name
    joined.data.name = f"{output_name}_MESH"
    joined["bf3d_source_object_count"] = len(staves)
    joined["bf3d_cooling_family"] = token.lower()
    return joined


def clear_non_structural_scene_objects(
    structural: list[bpy.types.Object],
) -> None:
    """Physically delete the imported operational scene after material transfer."""

    keep = {obj.name for obj in structural if object_is_alive(obj)}
    for obj in list(bpy.context.scene.objects):
        if obj.name not in keep:
            bpy.data.objects.remove(obj, do_unlink=True)


def bind_r5_exterior(
    objects: list[bpy.types.Object],
    r5_materials: dict[str, bpy.types.Material],
) -> None:
    """Bind the approved R5 Web PBR material to each R2J exterior slot."""

    for zone in ZONES:
        matches = [
            obj
            for obj in objects
            if object_is_alive(obj)
            and obj.name.startswith(f"R2J_ASM_GL02_FURNACE_{zone}_SHELL_")
        ]
        if len(matches) != 1:
            raise RuntimeError(f"R2J entity mismatch for {zone}: {len(matches)}")
        entity = matches[0]
        if not entity.material_slots:
            raise RuntimeError(f"R2J entity has no material slots: {entity.name}")
        entity.data.materials[0] = r5_materials[zone]
        entity["bf3d_r5_surface_source"] = "R2G_R2H_baked_R5_Web_PBR"
        entity["bf3d_zone"] = zone


def smooth_noise(seed: int, size: int, passes: int = 4) -> np.ndarray:
    """Create deterministic tileable low-frequency noise without extra packages."""

    rng = np.random.default_rng(seed)
    value = rng.random((size, size), dtype=np.float32)
    for _ in range(passes):
        value = (
            value
            + np.roll(value, 1, axis=0)
            + np.roll(value, -1, axis=0)
            + np.roll(value, 1, axis=1)
            + np.roll(value, -1, axis=1)
        ) / 5.0
    value -= value.min()
    value /= max(float(value.max()), 1e-6)
    return value


def normal_from_height(height: np.ndarray, strength: float) -> np.ndarray:
    """Convert a tileable scalar height image to an OpenGL (+Y) normal texture."""

    dx = np.roll(height, -1, axis=1) - np.roll(height, 1, axis=1)
    dy = np.roll(height, -1, axis=0) - np.roll(height, 1, axis=0)
    nx = -dx * strength
    ny = -dy * strength
    nz = np.ones_like(height)
    length = np.sqrt(nx * nx + ny * ny + nz * nz)
    normal = np.stack((nx / length, ny / length, nz / length), axis=-1)
    return normal * 0.5 + 0.5


def texture_rgba(rgb: np.ndarray) -> np.ndarray:
    """Append an opaque alpha channel to an HxWx3 float image."""

    alpha = np.ones((*rgb.shape[:2], 1), dtype=np.float32)
    return np.concatenate((np.clip(rgb, 0.0, 1.0), alpha), axis=-1)


def write_image(name: str, rgba: np.ndarray, colorspace: str) -> bpy.types.Image:
    """Write an embedded-source PNG and return its Blender image datablock."""

    height, width = rgba.shape[:2]
    path = TEXTURE_DIR / f"{name}.png"
    image = bpy.data.images.new(name, width=width, height=height, alpha=True)
    image.colorspace_settings.name = colorspace
    image.filepath_raw = str(path)
    image.file_format = "PNG"
    image.pixels.foreach_set(rgba.astype(np.float32).ravel())
    image.save()
    return image


def make_family_textures(
    key: str,
    base_color: tuple[float, float, float],
    seed: int,
    *,
    brick: bool = False,
    metallic_mottle: bool = False,
) -> tuple[bpy.types.Image, bpy.types.Image]:
    """Generate deterministic illustrative BaseColor and Normal textures."""

    size = 512
    low = smooth_noise(seed, size, 7)
    fine = smooth_noise(seed + 1000, size, 2)
    height = 0.62 * low + 0.38 * fine
    base = np.asarray(base_color, dtype=np.float32)[None, None, :]
    variation = (height[..., None] - 0.5) * (0.26 if metallic_mottle else 0.18)
    rgb = base * (1.0 + variation)

    if brick:
        yy, xx = np.indices((size, size))
        brick_h = 64
        brick_w = 128
        offset = ((yy // brick_h) % 2) * (brick_w // 2)
        mortar = ((yy % brick_h) < 5) | (((xx + offset) % brick_w) < 5)
        height = np.where(mortar, height * 0.20, 0.72 + height * 0.28)
        rgb = np.where(mortar[..., None], rgb * 0.48, rgb)
        pores = np.random.default_rng(seed + 77).random((size, size)) > 0.992
        rgb = np.where(pores[..., None], rgb * 0.34, rgb)
        height = np.where(pores, height * 0.35, height)
    elif metallic_mottle:
        oxide = smooth_noise(seed + 31, size, 10)
        rgb *= (0.78 + 0.32 * oxide[..., None])

    normal_strength = 7.5 if brick else 4.5
    base_image = write_image(
        f"BF3D_V2_{key}_BaseColor_512", texture_rgba(rgb), "sRGB"
    )
    normal_rgb = normal_from_height(height, normal_strength)
    normal_image = write_image(
        f"BF3D_V2_{key}_NormalGL_512",
        texture_rgba(normal_rgb),
        "Non-Color",
    )
    return base_image, normal_image


def build_pbr_material(
    name: str,
    material_id: str,
    base_image: bpy.types.Image,
    normal_image: bpy.types.Image,
    metallic: float,
    roughness: float,
    normal_strength: float,
) -> bpy.types.Material:
    """Build one glTF-compatible Principled PBR material."""

    material = bpy.data.materials.new(name)
    material.use_nodes = True
    material.diffuse_color = (0.3, 0.3, 0.3, 1.0)
    material["bf3d_material_id"] = material_id
    material["bf3d_evidence"] = "illustrative"
    material["bf3d_not_for_construction"] = True
    nodes = material.node_tree.nodes
    links = material.node_tree.links
    nodes.clear()
    output = nodes.new("ShaderNodeOutputMaterial")
    output.location = (540, 0)
    bsdf = nodes.new("ShaderNodeBsdfPrincipled")
    bsdf.location = (250, 0)
    bsdf.inputs["Metallic"].default_value = metallic
    bsdf.inputs["Roughness"].default_value = roughness
    base = nodes.new("ShaderNodeTexImage")
    base.image = base_image
    base.extension = "REPEAT"
    base.location = (-420, 140)
    normal_tex = nodes.new("ShaderNodeTexImage")
    normal_tex.image = normal_image
    normal_tex.extension = "REPEAT"
    normal_tex.location = (-420, -160)
    normal = nodes.new("ShaderNodeNormalMap")
    normal.inputs["Strength"].default_value = normal_strength
    normal.location = (-80, -140)
    links.new(base.outputs["Color"], bsdf.inputs["Base Color"])
    links.new(normal_tex.outputs["Color"], normal.inputs["Color"])
    links.new(normal.outputs["Normal"], bsdf.inputs["Normal"])
    links.new(bsdf.outputs["BSDF"], output.inputs["Surface"])
    return material


def create_material_library() -> dict[str, bpy.types.Material]:
    """Create the V2 material-specific PBR library."""

    specs = {
        "steel_inner": ((0.20, 0.23, 0.24), 101, False, True, 0.82, 0.58, 0.55),
        "steel_cut": ((0.36, 0.38, 0.39), 102, False, True, 0.88, 0.42, 0.35),
        "backfill": ((0.34, 0.32, 0.28), 201, False, False, 0.00, 0.88, 0.70),
        "backfill_cut": ((0.43, 0.40, 0.34), 202, False, False, 0.00, 0.82, 0.55),
        "hotface": ((0.22, 0.16, 0.12), 301, False, False, 0.00, 0.76, 0.82),
        "hotface_cut": ((0.34, 0.23, 0.16), 302, False, False, 0.00, 0.68, 0.62),
        "refractory": ((0.43, 0.32, 0.24), 401, True, False, 0.00, 0.86, 0.78),
        "refractory_cut": ((0.55, 0.42, 0.31), 402, True, False, 0.00, 0.80, 0.62),
        "cast_iron": ((0.22, 0.24, 0.23), 501, False, True, 0.78, 0.72, 0.68),
        "cast_iron_cut": ((0.35, 0.37, 0.36), 502, False, True, 0.82, 0.48, 0.42),
        "copper": ((0.37, 0.24, 0.17), 601, False, True, 0.88, 0.58, 0.62),
        "copper_cut": ((0.56, 0.34, 0.22), 602, False, True, 0.92, 0.38, 0.38),
    }
    result: dict[str, bpy.types.Material] = {}
    for key, (
        color,
        seed,
        brick,
        metallic_mottle,
        metallic,
        roughness,
        normal_strength,
    ) in specs.items():
        base, normal = make_family_textures(
            key.upper(),
            color,
            seed,
            brick=brick,
            metallic_mottle=metallic_mottle,
        )
        result[key] = build_pbr_material(
            f"BF3D_V2_{key.upper()}_PBR_E",
            {
                "steel_inner": "MAT-STEEL-INNER-E",
                "steel_cut": "MAT-STEEL-CUT-E",
                "backfill": "MAT-BACKFILL-CASTABLE-E",
                "backfill_cut": "MAT-BACKFILL-CUT-E",
                "hotface": "MAT-HOTFACE-SINTERED-E",
                "hotface_cut": "MAT-HOTFACE-CUT-E",
                "refractory": "MAT-REFRACTORY-001-E",
                "refractory_cut": "MAT-REFRACTORY-CUT-E",
                "cast_iron": "MAT-COOL-CAST-001-E",
                "cast_iron_cut": "MAT-COOL-CAST-CUT-E",
                "copper": "MAT-COOL-COPPER-001-E",
                "copper_cut": "MAT-COOL-COPPER-CUT-E",
            }[key],
            base,
            normal,
            metallic,
            roughness,
            normal_strength,
        )
    return result


def set_material_slots(
    obj: bpy.types.Object, materials: list[bpy.types.Material]
) -> None:
    """Replace all material slots while preserving face material indices."""

    data = obj.data
    while len(data.materials) < len(materials):
        data.materials.append(materials[len(data.materials)])
    for index, material in enumerate(materials):
        data.materials[index] = material
    while len(data.materials) > len(materials):
        data.materials.pop(index=len(data.materials) - 1)
    for polygon in data.polygons:
        polygon.material_index = min(polygon.material_index, len(materials) - 1)


def apply_material_library(
    objects: list[bpy.types.Object],
    materials: dict[str, bpy.types.Material],
) -> None:
    """Assign concrete internal material families to R2J/R2K objects."""

    for obj in objects:
        if not object_is_alive(obj) or obj.type != "MESH":
            continue
        role = role_for(obj)
        if role == "steel_shell":
            exterior = obj.material_slots[0].material
            if exterior is None:
                raise RuntimeError(f"missing exterior material on {obj.name}")
            set_material_slots(
                obj, [exterior, materials["steel_inner"], materials["steel_cut"]]
            )
        elif role == "backfill":
            set_material_slots(obj, [materials["backfill"], materials["backfill_cut"]])
        elif role == "hotface_embed":
            set_material_slots(obj, [materials["hotface"], materials["hotface_cut"]])
        elif role == "refractory":
            set_material_slots(
                obj, [materials["refractory"], materials["refractory_cut"]]
            )
        elif role == "cooling_stave":
            if "COPPER" in obj.name:
                set_material_slots(obj, [materials["copper"], materials["copper_cut"]])
            else:
                set_material_slots(
                    obj, [materials["cast_iron"], materials["cast_iron_cut"]]
                )


def ensure_uv(obj: bpy.types.Object, tile_m: float = 0.45) -> None:
    """Create physical cylindrical UVs only when a mesh has no usable UV map."""

    if obj.type != "MESH":
        return
    mesh = obj.data
    if mesh.uv_layers and len(mesh.uv_layers.active.data) == len(mesh.loops):
        return
    uv_layer = mesh.uv_layers.new(name="BF3D_PHYSICAL_UV")
    world = obj.matrix_world
    for loop in mesh.loops:
        point = world @ mesh.vertices[loop.vertex_index].co
        radius = max(math.hypot(point.x, point.y), tile_m)
        angle = math.atan2(point.y, point.x)
        uv_layer.data[loop.index].uv = (
            angle * radius / tile_m,
            point.z / tile_m,
        )


def mark_metadata(objects: list[bpy.types.Object], section: bool) -> None:
    """Attach review-only glTF extras to exported structural objects."""

    for obj in objects:
        if not object_is_alive(obj):
            continue
        obj["bf3d_asset"] = ASSET_ID
        obj["bf3d_requirement_id"] = REQUIREMENT_ID
        obj["bf3d_structural_role"] = role_for(obj)
        obj["bf3d_review_mode"] = "structural_section" if section else "material"
        obj["bf3d_evidence"] = "illustrative"
        obj["bf3d_not_for_construction"] = True
        obj["bf3d_runtime_guides_removed"] = True
        obj["bf3d_runtime_clipping_required"] = False if section else None


def create_collection(name: str) -> bpy.types.Collection:
    """Create and link a named root collection."""

    collection = bpy.data.collections.new(name)
    bpy.context.scene.collection.children.link(collection)
    return collection


def move_to_collection(
    obj: bpy.types.Object, destination: bpy.types.Collection
) -> None:
    """Move one object to exactly one review collection."""

    for collection in list(obj.users_collection):
        collection.objects.unlink(obj)
    destination.objects.link(obj)


def bounds(objects: list[bpy.types.Object]) -> tuple[Vector, Vector]:
    """Return world-space minimum and maximum bounds."""

    points = [
        obj.matrix_world @ Vector(corner)
        for obj in objects
        if object_is_alive(obj)
        for corner in obj.bound_box
    ]
    if not points:
        raise RuntimeError("cannot compute bounds for empty object list")
    minimum = Vector(
        (
            min(point.x for point in points),
            min(point.y for point in points),
            min(point.z for point in points),
        )
    )
    maximum = Vector(
        (
            max(point.x for point in points),
            max(point.y for point in points),
            max(point.z for point in points),
        )
    )
    return minimum, maximum


def duplicate_half_section(
    sources: list[bpy.types.Object],
    collection: bpy.types.Collection,
    plane_x: float,
) -> list[bpy.types.Object]:
    """Create a physically cut half-section by deleting the +X half.

    The output is deliberately an inspection mesh, not a construction solid.
    Cut boundaries are triangulated and receive each object's dedicated
    cut-face material so the nested wall layers remain readable without
    Blender/Three.js runtime clipping.
    """

    result: list[bpy.types.Object] = []
    for source in sources:
        duplicate = source.copy()
        duplicate.data = source.data.copy()
        duplicate.name = f"SECTION_{source.name}"
        duplicate.data.name = f"{duplicate.name}_MESH"
        collection.objects.link(duplicate)
        duplicate.data.transform(duplicate.matrix_world)
        duplicate.matrix_world = Matrix.Identity(4)
        mesh = duplicate.data
        bm = bmesh.new()
        bm.from_mesh(mesh)
        bisected = bmesh.ops.bisect_plane(
            bm,
            geom=list(bm.verts) + list(bm.edges) + list(bm.faces),
            dist=1e-6,
            plane_co=Vector((plane_x, 0.0, 0.0)),
            plane_no=Vector((1.0, 0.0, 0.0)),
            clear_outer=True,
            clear_inner=False,
            use_snap_center=False,
        )
        cut_edges = [
            item
            for item in bisected.get("geom_cut", [])
            if isinstance(item, bmesh.types.BMEdge) and item.is_valid
        ]
        fill_faces: list[bmesh.types.BMFace] = []
        if cut_edges:
            filled = bmesh.ops.triangle_fill(
                bm, edges=cut_edges, use_beauty=True
            )
            fill_faces = [
                item
                for item in filled.get("geom", [])
                if isinstance(item, bmesh.types.BMFace) and item.is_valid
            ]
        cut_material_index = max(len(duplicate.data.materials) - 1, 0)
        uv_layer = bm.loops.layers.uv.verify()
        for face in fill_faces:
            face.material_index = cut_material_index
            for loop in face.loops:
                loop[uv_layer].uv = (
                    loop.vert.co.y / 0.45,
                    loop.vert.co.z / 0.45,
                )
        bm.normal_update()
        bm.to_mesh(mesh)
        bm.free()
        mesh.update()
        duplicate["bf3d_section_physical_cut"] = True
        duplicate["bf3d_section_cut_caps"] = bool(fill_faces)
        duplicate["bf3d_section_plane_axis"] = "X"
        duplicate["bf3d_section_plane_value"] = round(float(plane_x), 6)
        result.append(duplicate)
    return result


def export_selected(path: Path, objects: list[bpy.types.Object]) -> None:
    """Export an exact object allow-list as an embedded binary glTF."""

    path.parent.mkdir(parents=True, exist_ok=True)
    bpy.ops.object.select_all(action="DESELECT")
    for obj in objects:
        obj.hide_set(False)
        obj.hide_viewport = False
        obj.hide_render = False
        obj.select_set(True)
    props = {
        prop.identifier for prop in bpy.ops.export_scene.gltf.get_rna_type().properties
    }
    requested = {
        "filepath": str(path),
        "export_format": "GLB",
        "use_selection": True,
        "export_extras": True,
        "export_cameras": False,
        "export_lights": False,
        "export_apply": True,
        "export_yup": True,
        "export_materials": "EXPORT",
        "export_image_format": "AUTO",
        "export_texcoords": True,
        "export_normals": True,
        "export_tangents": True,
        "export_attributes": False,
        "export_skins": False,
        "export_animations": False,
    }
    kwargs = {key: value for key, value in requested.items() if key in props}
    result = bpy.ops.export_scene.gltf(**kwargs)
    if "FINISHED" not in result or not path.is_file():
        raise RuntimeError(f"glTF export failed for {path}: {result}")


def read_glb_json(path: Path) -> dict:
    """Read and decode the JSON chunk from a GLB v2 file."""

    with path.open("rb") as stream:
        magic, version, total_length = struct.unpack("<4sII", stream.read(12))
        if magic != b"glTF" or version != 2:
            raise RuntimeError(f"not a GLB v2 file: {path}")
        if total_length != path.stat().st_size:
            raise RuntimeError(f"GLB header length mismatch: {path}")
        chunk_length, chunk_type = struct.unpack("<I4s", stream.read(8))
        if chunk_type != b"JSON":
            raise RuntimeError(f"GLB first chunk is not JSON: {path}")
        payload = stream.read(chunk_length).decode("utf-8").rstrip(" \t\r\n\x00")
        return json.loads(payload)


def forbidden_names(glb_json: dict) -> list[str]:
    """Return every exported node/mesh/material name containing a banned token."""

    names = []
    for key in ("nodes", "meshes", "materials"):
        names.extend(item.get("name", "") for item in glb_json.get(key, []))
    return sorted(
        {
            name
            for name in names
            if any(token in name.upper() for token in FORBIDDEN_TOKENS)
        }
    )


def summarize_glb(path: Path) -> dict:
    """Summarize one output GLB for the controlled manifest."""

    glb = read_glb_json(path)
    roles = Counter()
    for node in glb.get("nodes", []):
        role = (node.get("extras") or {}).get("bf3d_structural_role")
        if role:
            roles[role] += 1
    return {
        "path": rel(path),
        "bytes": path.stat().st_size,
        "sha256": sha256(path),
        "nodes": len(glb.get("nodes", [])),
        "meshes": len(glb.get("meshes", [])),
        "materials": len(glb.get("materials", [])),
        "textures": len(glb.get("textures", [])),
        "images": len(glb.get("images", [])),
        "roles": dict(sorted(roles.items())),
        "material_names": [
            material.get("name", "") for material in glb.get("materials", [])
        ],
        "forbidden_names": forbidden_names(glb),
    }


def look_at(obj: bpy.types.Object, target: Vector) -> None:
    """Aim a -Z camera/light axis toward *target*."""

    obj.rotation_euler = (target - obj.location).to_track_quat("-Z", "Y").to_euler()


def setup_review_scene(
    full_collection: bpy.types.Collection,
    section_collection: bpy.types.Collection,
    section_objects: list[bpy.types.Object],
) -> tuple[bpy.types.Object, list[bpy.types.Object]]:
    """Create a restrained section-review camera and three-point lighting."""

    full_collection.hide_viewport = True
    full_collection.hide_render = True
    section_collection.hide_viewport = False
    section_collection.hide_render = False
    minimum, maximum = bounds(section_objects)
    center = (minimum + maximum) * 0.5
    height = maximum.z - minimum.z
    width = max(maximum.y - minimum.y, maximum.x - minimum.x)
    camera_data = bpy.data.cameras.new("BF3D_V2_SECTION_CAMERA")
    camera = bpy.data.objects.new("BF3D_V2_SECTION_CAMERA", camera_data)
    bpy.context.scene.collection.objects.link(camera)
    camera.location = (
        center.x + max(height * 1.30, width * 2.4),
        center.y - width * 0.12,
        center.z + height * 0.02,
    )
    camera_data.lens = 58
    camera_data.sensor_width = 36
    look_at(camera, center)
    bpy.context.scene.camera = camera

    lights: list[bpy.types.Object] = []
    light_specs = (
        ("BF3D_V2_KEY", "AREA", 26000.0, 18.0, (1.0, 0.78, 0.58), (0.75, -0.45, 0.38)),
        ("BF3D_V2_FILL", "AREA", 14000.0, 16.0, (0.58, 0.72, 1.0), (0.45, 0.70, 0.05)),
        ("BF3D_V2_RIM", "AREA", 19000.0, 18.0, (0.85, 0.92, 1.0), (-0.55, -0.45, 0.48)),
        ("BF3D_V2_INSIDE", "POINT", 12000.0, 10.0, (1.0, 0.55, 0.28), (0.08, 0.02, 0.08)),
    )
    for name, kind, energy, size, color, direction in light_specs:
        data = bpy.data.lights.new(name, kind)
        data.energy = energy
        if kind == "AREA":
            data.shape = "DISK"
            data.size = size
        else:
            data.shadow_soft_size = size
        data.color = color
        light = bpy.data.objects.new(name, data)
        bpy.context.scene.collection.objects.link(light)
        light.location = (
            center.x + direction[0] * max(height, width),
            center.y + direction[1] * max(height, width),
            center.z + direction[2] * height,
        )
        look_at(light, center)
        lights.append(light)

    world = bpy.context.scene.world or bpy.data.worlds.new("BF3D_V2_WORLD")
    bpy.context.scene.world = world
    world.use_nodes = True
    background = world.node_tree.nodes.get("Background")
    background.inputs["Color"].default_value = (0.025, 0.032, 0.045, 1.0)
    background.inputs["Strength"].default_value = 0.32

    scene = bpy.context.scene
    scene.render.engine = "BLENDER_EEVEE"
    scene.render.resolution_x = 1200
    scene.render.resolution_y = 900
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = "PNG"
    scene.render.film_transparent = False
    scene.view_settings.look = "AgX - Medium High Contrast"
    scene.view_settings.exposure = 0.15
    return camera, lights


def render_review(path: Path) -> None:
    """Render the current prepared review scene to *path*."""

    path.parent.mkdir(parents=True, exist_ok=True)
    bpy.context.scene.render.filepath = str(path)
    bpy.ops.render.render(write_still=True)
    if not path.is_file():
        raise RuntimeError(f"review render was not created: {path}")


def save_review_blend() -> None:
    """Pack generated textures and save the directly-openable review Blend."""

    REVIEW_BLEND.parent.mkdir(parents=True, exist_ok=True)
    bpy.ops.file.pack_all()
    result = bpy.ops.wm.save_as_mainfile(filepath=str(REVIEW_BLEND), check_existing=False)
    if "FINISHED" not in result or not REVIEW_BLEND.is_file():
        raise RuntimeError(f"failed to save review Blend: {result}")


def build_manifest(
    material_summary: dict,
    structural_summary: dict,
    structural_objects: list[bpy.types.Object],
) -> dict:
    """Build the V2 delivery manifest and strict asset-level checks."""

    required_material_ids = {
        "MAT-STEEL-INNER-E",
        "MAT-STEEL-CUT-E",
        "MAT-BACKFILL-CASTABLE-E",
        "MAT-HOTFACE-SINTERED-E",
        "MAT-REFRACTORY-001-E",
        "MAT-COOL-CAST-001-E",
        "MAT-COOL-COPPER-001-E",
    }
    present_material_ids = {
        material.get("bf3d_material_id")
        for material in bpy.data.materials
        if material.get("bf3d_material_id")
    }
    checks = {
        "material_glb_exactly_five_shell_entities": (
            material_summary["roles"] == {"steel_shell": 5}
            and material_summary["nodes"] == 5
        ),
        "structural_glb_exact_roles": structural_summary["roles"]
        == {
            "backfill": 1,
            "cooling_stave": 2,
            "hotface_embed": 1,
            "refractory": 1,
            "steel_shell": 5,
        },
        "structural_glb_exactly_ten_nodes": structural_summary["nodes"] == 10,
        "material_glb_has_no_forbidden_geometry": not material_summary[
            "forbidden_names"
        ],
        "structural_glb_has_no_forbidden_geometry": not structural_summary[
            "forbidden_names"
        ],
        "no_sensor_objects_in_scene": not any(
            obj.name.startswith("SENSOR_") for obj in bpy.context.scene.objects
        ),
        "no_curve_or_line_objects_in_scene": not any(
            obj.type in {"CURVE", "GREASEPENCIL"} for obj in structural_objects
        ),
        "all_section_objects_are_physically_cut": all(
            bool(obj.get("bf3d_section_physical_cut")) for obj in structural_objects
        ),
        "all_r2k_section_objects_have_cut_caps": all(
            bool(obj.get("bf3d_section_cut_caps"))
            for obj in structural_objects
            if role_for(obj) != "steel_shell"
        ),
        "r2j_entities_retain_three_material_boundaries": all(
            len(obj.material_slots) == 3
            for obj in structural_objects
            if role_for(obj) == "steel_shell"
        ),
        "required_internal_material_ids_present": required_material_ids
        <= present_material_ids,
        "material_glb_contains_textures": material_summary["textures"] >= 1,
        "structural_glb_contains_material_textures": structural_summary["textures"] >= 10,
        "blend_saved_and_nonempty": REVIEW_BLEND.is_file()
        and REVIEW_BLEND.stat().st_size > 1_000_000,
        "formal_glb_unchanged": sha256(FORMAL_GLB) == EXPECTED_FORMAL_SHA256,
        "v1_glb_unchanged": sha256(V1_GLB) == EXPECTED_V1_SHA256,
    }
    return {
        "schema_version": "bf3d.clean_structural_review_asset.v2",
        "requirement_id": REQUIREMENT_ID,
        "asset_id": ASSET_ID,
        "status": "controlled_local_review_asset",
        "evidence": "illustrative",
        "not_for_construction": True,
        "correction": {
            "root_cause": (
                "V1 retained operational scene meshes and relied on Three.js "
                "visibility/clipping; direct Blender import therefore exposed them."
            ),
            "asset_level_removal": [
                "115 sensor render/pick objects",
                "burden reference rings",
                "gas/blast flow lines",
                "temperature highlight rings",
                "legacy process particles and decorative meshes",
                "access/support geometry outside the R5/R2J/R2K review scope",
                "optional missing skull placeholder",
            ],
            "runtime_clipping_required_for_v2_section": False,
        },
        "provenance": {
            "r5_web_base": {"path": rel(BASE_GLB), "sha256": sha256(BASE_GLB)},
            "r2j_r2k_blend": {"path": rel(R2K_BLEND), "sha256": sha256(R2K_BLEND)},
        },
        "outputs": {
            "material_review_glb": material_summary,
            "structural_section_glb": structural_summary,
            "direct_open_blend": {
                "path": rel(REVIEW_BLEND),
                "bytes": REVIEW_BLEND.stat().st_size,
                "sha256": sha256(REVIEW_BLEND),
            },
            "section_preview": {
                "path": rel(PREVIEW_DIR / "BF3D_V2_STRUCTURAL_SECTION.png"),
                "bytes": (PREVIEW_DIR / "BF3D_V2_STRUCTURAL_SECTION.png").stat().st_size,
                "sha256": sha256(PREVIEW_DIR / "BF3D_V2_STRUCTURAL_SECTION.png"),
            },
        },
        "rollback": {
            "formal_glb": rel(FORMAL_GLB),
            "formal_glb_sha256": sha256(FORMAL_GLB),
            "v1_review_glb": rel(V1_GLB),
            "v1_review_glb_sha256": sha256(V1_GLB),
            "historical_files_overwritten": False,
        },
        "material_identity": {
            "exterior": "R5/R2H baked coarse steel-shell PBR",
            "inner_steel": "MAT-STEEL-INNER-E",
            "backfill": "MAT-BACKFILL-CASTABLE-E",
            "cast_iron_cooling": "MAT-COOL-CAST-001-E",
            "copper_cooling": "MAT-COOL-COPPER-001-E",
            "refractory": "MAT-REFRACTORY-001-E",
            "hotface": "MAT-HOTFACE-SINTERED-E",
        },
        "checks": checks,
        "all_checks_pass": all(checks.values()),
    }


def main() -> None:
    """Build clean V2 assets and fail closed on any contract regression."""

    STAGE.mkdir(parents=True, exist_ok=True)
    TEXTURE_DIR.mkdir(parents=True, exist_ok=True)
    PREVIEW_DIR.mkdir(parents=True, exist_ok=True)
    check_locked(BASE_GLB, EXPECTED_BASE_SHA256, "R5 Web base")
    check_locked(R2K_BLEND, EXPECTED_R2K_SHA256, "R2K candidate")
    check_locked(FORMAL_GLB, EXPECTED_FORMAL_SHA256, "formal rollback GLB")
    check_locked(V1_GLB, EXPECTED_V1_SHA256, "V1 review rollback GLB")

    reset_scene()
    r5_materials = import_r5_material_source()
    structural = append_structural_objects()
    bind_r5_exterior(structural, r5_materials)
    copper = join_stave_family(
        structural, "COPPER", "R2K_V2_L03_COOLING_COPPER_COMBINED"
    )
    cast_iron = join_stave_family(
        structural, "CASTIRON", "R2K_V2_L03_COOLING_CASTIRON_COMBINED"
    )
    structural = [
        obj
        for obj in structural
        if object_is_alive(obj)
        and not obj.name.startswith("SM_BF3D_GL02_CST_")
    ]
    structural.extend([copper, cast_iron])
    structural = list({obj.as_pointer(): obj for obj in structural}.values())
    structural = [
        obj for obj in structural if role_for(obj) != "skull_optional_missing"
    ]
    clear_non_structural_scene_objects(structural)

    materials = create_material_library()
    apply_material_library(structural, materials)
    for obj in structural:
        ensure_uv(obj)
    mark_metadata(structural, section=False)

    full_collection = create_collection("BF3D_V2_FULL_MATERIAL_REVIEW")
    for obj in structural:
        move_to_collection(obj, full_collection)
    shell_objects = [obj for obj in structural if role_for(obj) == "steel_shell"]
    export_selected(MATERIAL_GLB, shell_objects)

    minimum, maximum = bounds(structural)
    plane_x = (minimum.x + maximum.x) * 0.5
    section_collection = create_collection("BF3D_V2_STRUCTURAL_SECTION")
    section_objects = duplicate_half_section(structural, section_collection, plane_x)
    mark_metadata(section_objects, section=True)
    export_selected(STRUCTURAL_GLB, section_objects)

    setup_review_scene(full_collection, section_collection, section_objects)
    render_review(PREVIEW_DIR / "BF3D_V2_STRUCTURAL_SECTION.png")
    save_review_blend()

    material_summary = summarize_glb(MATERIAL_GLB)
    structural_summary = summarize_glb(STRUCTURAL_GLB)
    manifest = build_manifest(
        material_summary, structural_summary, section_objects
    )
    if not manifest["all_checks_pass"]:
        raise RuntimeError(
            "clean structural-review V2 contract failed: "
            + json.dumps(manifest["checks"], ensure_ascii=False)
        )
    text = json.dumps(manifest, ensure_ascii=False, indent=2) + "\n"
    MANIFEST_PATH.write_text(text, encoding="utf-8")
    STAGE_MANIFEST_PATH.write_text(text, encoding="utf-8")
    print("BF3D_CLEAN_STRUCTURAL_REVIEW_V2=" + json.dumps(manifest, ensure_ascii=False))


if __name__ == "__main__":
    main()
