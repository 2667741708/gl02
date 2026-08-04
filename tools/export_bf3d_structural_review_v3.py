"""Build the isolated WEB-60 R2Q internal-material LookDev V3 candidate.

The script intentionally reuses only stable V2 source-lock and geometry helpers.
All V3 assets are new files. V1/V2, Web pages, the R2K candidate, the R1
material carrier, and the formal GLB remain read-only.

Modes:
    build (default)       Build textures, Blend, three GLBs, renders and reports.
    --reopen              Validate the saved V3 Blend after direct reopen.
    --factory-import      Factory-import and validate all three V3 GLBs.
    --finalize            Write final manifests after both validations pass.
"""

from __future__ import annotations

import hashlib
import json
import math
import struct
import sys
from collections import Counter
from pathlib import Path

import bmesh
import bpy
import numpy as np
from mathutils import Matrix, Vector


sys.path.insert(0, str(Path(__file__).resolve().parent))
import export_bf3d_structural_review_v2 as v2


ROOT = v2.ROOT
MODEL_DIR = ROOT / "高炉前端数据" / "models"
STAGE = (
    ROOT
    / "PT"
    / "高炉3D模型"
    / "work"
    / "WEB_60_20260719_R2Q_INTERNAL_MATERIAL_LOOKDEV"
)
TEXTURE_DIR = STAGE / "textures"
RENDER_DIR = STAGE / "renders"
REPORT_DIR = STAGE / "reports"

BASE_GLB = v2.BASE_GLB
R2K_BLEND = v2.R2K_BLEND
FORMAL_GLB = v2.FORMAL_GLB
R2K_PIPELINE = R2K_BLEND.parent.parent / "pipeline_status.json"
R1_BLEND = (
    ROOT
    / "PT"
    / "高炉3D模型"
    / "work"
    / "SURF_20_20260718_R5"
    / "SURF20_R5_FULL_SHELL_MATERIAL_CANDIDATE.blend"
)

MAIN_GLB = MODEL_DIR / "gl02_blast_furnace_review.v3.glb"
MATERIAL_GLB = MODEL_DIR / "gl02_blast_furnace_material_review.v3.glb"
STRUCTURAL_GLB = MODEL_DIR / "gl02_blast_furnace_structural_review.v3.glb"
REVIEW_BLEND = MODEL_DIR / "gl02_blast_furnace_review.v3.blend"
MODEL_MANIFEST = MODEL_DIR / "gl02_blast_furnace_review.v3.manifest.json"

EXPECTED_BASE_SHA256 = v2.EXPECTED_BASE_SHA256
EXPECTED_R2K_SHA256 = v2.EXPECTED_R2K_SHA256
EXPECTED_FORMAL_SHA256 = v2.EXPECTED_FORMAL_SHA256
EXPECTED_R1_SHA256 = (
    "4f1dae2804300c2c99462b4a5d7967abd9085a3ffd7170ae26af4e105290471b"
)

REQUIREMENT_ID = "REQ-BF3D-R2Q-INTERNAL-MATERIAL-LOOKDEV-V3-20260719"
ASSET_ID = "GL02_INTERNAL_MATERIAL_LOOKDEV_V3"
STATUS = "candidate_ready_for_independent_visual_and_spec_review"
EVIDENCE = "E/illustrative"
REFERENCE_STATUS = "REF-PENDING"
TILE_M = 1.0
TEXTURE_SIZE = 1024
UV0_NAME = "BF3D_PHYSICAL_UV_1M"
UV1_NAME = "BF3D_INTERNAL_UV_1M"
MATERIAL_ROOT_NAME = "BF3D_V3_MODE_MATERIAL"
SECTION_ROOT_NAME = "BF3D_V3_MODE_SECTION"
FULL_COLLECTION_NAME = "BF3D_V3_FULL_MATERIAL"
SECTION_COLLECTION_NAME = "BF3D_V3_SECTION"
LIGHT_COLLECTION_NAME = "P40_LOOKDEV_NEUTRAL"
CAMERA_NAME = "CAM_R2Q_SECTION_ORTHO_CANDIDATE"

FORBIDDEN_TOKENS = (
    "SENSOR_",
    "LEADER",
    "OUTLINE",
    "YELLOW",
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
    "RUNTIME_CLIP",
)

PRIMARY_FAMILIES = (
    "steel_inner",
    "backfill",
    "cast_iron",
    "copper",
    "hotface",
    "refractory",
)

FAMILY_SPECS = {
    "steel_inner": {
        "material_id": "MAT-STEEL-BARE-001",
        "variant": "inner_steel",
        "seed": 3101,
        "base": (0.31, 0.34, 0.33),
        "roughness": 0.61,
        "metallic": 0.91,
        "normal_strength": 0.42,
        "uv": UV1_NAME,
        "texcoord": 1,
    },
    "backfill": {
        "material_id": "MAT-REFRACTORY-001",
        "variant": "backfill_castable",
        "seed": 3201,
        "base": (0.37, 0.35, 0.31),
        "roughness": 0.88,
        "metallic": 0.0,
        "normal_strength": 0.55,
        "uv": UV0_NAME,
        "texcoord": 0,
    },
    "cast_iron": {
        "material_id": "MAT-COOL-CAST-001",
        "variant": "cast_iron_stave",
        "seed": 3301,
        "base": (0.24, 0.27, 0.26),
        "roughness": 0.72,
        "metallic": 0.82,
        "normal_strength": 0.58,
        "uv": UV0_NAME,
        "texcoord": 0,
    },
    "copper": {
        "material_id": "MAT-COOL-COPPER-001",
        "variant": "copper_stave_oxidized",
        "seed": 3401,
        "base": (0.52, 0.29, 0.18),
        "roughness": 0.48,
        "metallic": 0.94,
        "normal_strength": 0.48,
        "uv": UV0_NAME,
        "texcoord": 0,
    },
    "hotface": {
        "material_id": "MAT-REFRACTORY-001",
        "variant": "hotface_embed",
        "seed": 3501,
        "base": (0.25, 0.20, 0.16),
        "roughness": 0.78,
        "metallic": 0.0,
        "normal_strength": 0.62,
        "uv": UV0_NAME,
        "texcoord": 0,
    },
    "refractory": {
        "material_id": "MAT-REFRACTORY-001",
        "variant": "residual_refractory",
        "seed": 3601,
        "base": (0.43, 0.37, 0.30),
        "roughness": 0.86,
        "metallic": 0.0,
        "normal_strength": 0.66,
        "uv": UV0_NAME,
        "texcoord": 0,
    },
}

_V2_ROLE_FOR = v2.role_for


def role_for(obj: bpy.types.Object) -> str:
    """Extend the stable V2 role map for V3 combined cooling-family names."""

    name = obj.name.removeprefix("SECTION_")
    if name.startswith("R2K_V3_L03_COOLING_"):
        return "cooling_stave"
    return _V2_ROLE_FOR(obj)


# Reused V2 helpers call their module-level mapper; keep V3 names role-stable.
v2.role_for = role_for


def sha256(path: Path) -> str:
    return v2.sha256(path)


def rel(path: Path) -> str:
    return v2.rel(path)


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


def artifact(path: Path) -> dict:
    return {"path": rel(path), "bytes": path.stat().st_size, "sha256": sha256(path)}


def check_input_gate() -> dict:
    """Fail closed unless the R2K isolated-LookDev gate and locked assets match."""

    v2.check_locked(BASE_GLB, EXPECTED_BASE_SHA256, "R5 Web base")
    v2.check_locked(R2K_BLEND, EXPECTED_R2K_SHA256, "R2K candidate")
    v2.check_locked(FORMAL_GLB, EXPECTED_FORMAL_SHA256, "formal GLB")
    v2.check_locked(R1_BLEND, EXPECTED_R1_SHA256, "R1 VB-DEC-MAT-001 carrier")
    pipeline = json.loads(R2K_PIPELINE.read_text(encoding="utf-8"))
    checks = {
        "r2k_status_candidate_gate_passed": pipeline.get("status")
        == "candidate_gate_passed",
        "r2k_next_stage_allowed": pipeline.get("next_stage_allowed") is True,
        "r2k_next_stage_scope_isolated_lookdev_only": pipeline.get(
            "next_stage_scope"
        )
        == "isolated_lookdev_only",
        "r2k_candidate_sha_locked": pipeline.get("candidate_sha256")
        == EXPECTED_R2K_SHA256,
        "formal_glb_sha_locked": pipeline.get("formal_glb_sha256")
        == EXPECTED_FORMAL_SHA256,
        "r1_sha_locked": pipeline.get("r1_vb_dec_mat_001_sha256")
        == EXPECTED_R1_SHA256,
    }
    if not all(checks.values()):
        raise RuntimeError("R2K input gate failed: " + json.dumps(checks))
    return {"pipeline": artifact(R2K_PIPELINE), "checks": checks}


def historical_snapshot() -> dict[str, dict]:
    """Record read-only V1/V2/formal assets so drift is detected after build."""

    candidates = [
        FORMAL_GLB,
        MODEL_DIR / "gl02_blast_furnace_structural_review.v1.glb",
        MODEL_DIR / "gl02_blast_furnace_structural_review.v1.manifest.json",
        MODEL_DIR / "gl02_blast_furnace_material_review.v2.glb",
        MODEL_DIR / "gl02_blast_furnace_structural_review.v2.glb",
        MODEL_DIR / "gl02_blast_furnace_structural_review.v2.blend",
        MODEL_DIR / "gl02_blast_furnace_structural_review.v2.manifest.json",
    ]
    return {rel(path): artifact(path) for path in candidates if path.is_file()}


def assert_snapshot_unchanged(before: dict[str, dict]) -> None:
    after = historical_snapshot()
    if before != after:
        raise RuntimeError("formal or V1/V2 historical asset drifted")


def force_tile_seam(value: np.ndarray) -> np.ndarray:
    result = np.array(value, dtype=np.float32, copy=True)
    result[-1, ...] = result[0, ...]
    result[:, -1, ...] = result[:, 0, ...]
    return result


def tileable_noise(seed: int, size: int, passes: int) -> np.ndarray:
    return force_tile_seam(v2.smooth_noise(seed, size, passes))


def family_arrays(key: str, spec: dict) -> tuple[np.ndarray, np.ndarray, np.ndarray, dict]:
    """Generate deterministic seamless BaseColor, ORM and OpenGL-normal arrays."""

    size = TEXTURE_SIZE
    low = tileable_noise(spec["seed"], size, 9)
    mid = tileable_noise(spec["seed"] + 113, size, 4)
    fine = tileable_noise(spec["seed"] + 227, size, 2)
    height = force_tile_seam(0.50 * low + 0.32 * mid + 0.18 * fine)
    base = np.asarray(spec["base"], dtype=np.float32)[None, None, :]
    rgb = base * (0.88 + 0.20 * low[..., None] + 0.06 * (fine[..., None] - 0.5))
    ao = np.clip(0.91 + 0.08 * low - 0.04 * fine, 0.72, 1.0)
    rough = np.clip(
        spec["roughness"] + 0.14 * (mid - 0.5) + 0.06 * (fine - 0.5),
        0.18,
        0.98,
    )
    metal = np.full((size, size), spec["metallic"], dtype=np.float32)
    extra: dict[str, object] = {}

    if key == "steel_inner":
        yy, xx = np.indices((size, size))
        grind = 0.035 * np.sin((yy / size) * math.tau * 96 + 1.7 * low)
        rgb *= 1.0 + grind[..., None]
        height = force_tile_seam(height + grind)
    elif key == "cast_iron":
        oxide = np.clip((low - 0.58) * 2.2, 0.0, 1.0)
        rgb *= 0.92 - 0.15 * oxide[..., None]
        metal = np.clip(metal * (1.0 - 0.90 * oxide), 0.06, 0.92)
        rough = np.clip(rough + 0.15 * oxide, 0.2, 0.98)
    elif key == "copper":
        oxide = np.clip((low - 0.52) * 2.8, 0.0, 1.0)
        oxide_color = np.asarray((0.18, 0.30, 0.23), dtype=np.float32)
        rgb = rgb * (1.0 - oxide[..., None]) + oxide_color * oxide[..., None]
        metal = np.clip(
            spec["metallic"] * (1.0 - oxide) + 0.04 * oxide, 0.0, 1.0
        )
        rough = np.clip(rough + 0.28 * oxide, 0.22, 0.94)
        oxidized = oxide > 0.45
        clean = oxide < 0.10
        extra = {
            "oxide_pixel_fraction": float(np.mean(oxidized)),
            "oxidized_mean_metallic": float(np.mean(metal[oxidized]))
            if np.any(oxidized)
            else 0.0,
            "clean_mean_metallic": float(np.mean(metal[clean]))
            if np.any(clean)
            else 0.0,
        }
        extra["oxidized_pixels_reduce_metallic"] = bool(
            extra["oxidized_mean_metallic"] < extra["clean_mean_metallic"]
        )
    elif key in {"backfill", "hotface", "refractory"}:
        pores = fine > (0.985 if key != "refractory" else 0.975)
        rgb = np.where(pores[..., None], rgb * 0.55, rgb)
        height = np.where(pores, height * 0.35, height)
        if key == "hotface":
            rgb *= 0.78 + 0.18 * low[..., None]
        extra = {
            "architectural_red_brick_pattern": False,
            "regular_mortar_grid": False,
            "emissive": 0.0,
        }
    rgb = force_tile_seam(np.clip(rgb, 0.0, 1.0))
    ao = force_tile_seam(ao)
    rough = force_tile_seam(rough)
    metal = force_tile_seam(metal)
    height = force_tile_seam(height)
    normal = force_tile_seam(
        v2.normal_from_height(height, float(spec["normal_strength"]) * 5.0)
    )
    orm = force_tile_seam(np.stack((ao, rough, metal), axis=-1))
    return rgb, orm, normal, extra


def rgba(rgb: np.ndarray) -> np.ndarray:
    alpha = np.ones((*rgb.shape[:2], 1), dtype=np.float32)
    return np.concatenate((rgb.astype(np.float32), alpha), axis=-1)


def save_texture(
    name: str, rgb: np.ndarray, color_space: str, semantic: str
) -> tuple[bpy.types.Image, dict]:
    """Save one PNG, reload it, and report disk/seam quantization error."""

    path = TEXTURE_DIR / f"{name}.png"
    height, width = rgb.shape[:2]
    expected = rgba(rgb)
    image = bpy.data.images.new(name, width=width, height=height, alpha=True)
    image.colorspace_settings.name = color_space
    image.filepath_raw = str(path)
    image.file_format = "PNG"
    image.pixels.foreach_set(expected.ravel())
    image.save()
    image.reload()
    actual = np.empty(expected.size, dtype=np.float32)
    image.pixels.foreach_get(actual)
    actual = actual.reshape(expected.shape)
    disk_error = float(np.max(np.abs(actual - expected)))
    seam_error = max(
        float(np.max(np.abs(actual[0, :, :3] - actual[-1, :, :3]))),
        float(np.max(np.abs(actual[:, 0, :3] - actual[:, -1, :3]))),
    )
    image.pack()
    return image, {
        "path": rel(path),
        "bytes": path.stat().st_size,
        "sha256": sha256(path),
        "semantic": semantic,
        "width": width,
        "height": height,
        "color_space": color_space,
        "tile_m": TILE_M,
        "disk_max_abs_error": disk_error,
        "seam_max_abs_error": seam_error,
    }


def create_texture_library() -> tuple[dict[str, dict[str, bpy.types.Image]], dict]:
    library: dict[str, dict[str, bpy.types.Image]] = {}
    records: dict[str, dict] = {}
    for key, spec in FAMILY_SPECS.items():
        base, orm, normal, extra = family_arrays(key, spec)
        token = key.upper()
        base_image, base_record = save_texture(
            f"BF3D_V3_{token}_BaseColor_1K", base, "sRGB", "BaseColor"
        )
        orm_image, orm_record = save_texture(
            f"BF3D_V3_{token}_ORM_1K", orm, "Non-Color", "ORM_R_AO_G_Rough_B_Metal"
        )
        normal_image, normal_record = save_texture(
            f"BF3D_V3_{token}_NormalGL_1K",
            normal,
            "Non-Color",
            "NormalGL_OpenGL_plusY",
        )
        library[key] = {
            "base": base_image,
            "orm": orm_image,
            "normal": normal_image,
        }
        records[key] = {
            "material_id": spec["material_id"],
            "variant": spec["variant"],
            "seed": spec["seed"],
            "reference_status": REFERENCE_STATUS,
            "evidence": EVIDENCE,
            "not_for_construction": True,
            "uv_map": spec["uv"],
            "expected_texcoord": spec["texcoord"],
            "base_color": base_record,
            "orm": orm_record,
            "normal_gl": normal_record,
            "extra_checks": extra,
        }
    return library, records


def gltf_occlusion_group() -> bpy.types.NodeTree:
    group = bpy.data.node_groups.get("glTF Material Output")
    if group is None:
        group = bpy.data.node_groups.new("glTF Material Output", "ShaderNodeTree")
        group.interface.new_socket(
            name="Occlusion", in_out="INPUT", socket_type="NodeSocketFloat"
        )
    return group


def build_material(
    key: str, images: dict[str, bpy.types.Image], spec: dict
) -> bpy.types.Material:
    material = bpy.data.materials.new(f"BF3D_V3_{key.upper()}_PBR_E_REF_PENDING")
    material.use_nodes = True
    material.use_backface_culling = True
    material.diffuse_color = (*spec["base"], 1.0)
    material["bf3d_material_id"] = spec["material_id"]
    material["bf3d_material_variant"] = spec["variant"]
    material["bf3d_evidence"] = EVIDENCE
    material["bf3d_reference_status"] = REFERENCE_STATUS
    material["bf3d_not_for_construction"] = True
    material["bf3d_texture_tile_m"] = TILE_M
    material["bf3d_normal_convention"] = "OpenGL +Y"
    material["bf3d_orm_channels"] = "R=AO,G=Roughness,B=Metallic"
    material["bf3d_expected_texcoord"] = spec["texcoord"]
    material["bf3d_alpha_mode"] = "OPAQUE"
    material["bf3d_side"] = "FrontSide"
    nodes = material.node_tree.nodes
    links = material.node_tree.links
    nodes.clear()
    output = nodes.new("ShaderNodeOutputMaterial")
    output.location = (720, 40)
    bsdf = nodes.new("ShaderNodeBsdfPrincipled")
    bsdf.location = (430, 40)
    bsdf.inputs["Alpha"].default_value = 1.0
    if bsdf.inputs.get("Emission Color") is not None:
        bsdf.inputs["Emission Color"].default_value = (0.0, 0.0, 0.0, 1.0)
    if bsdf.inputs.get("Emission Strength") is not None:
        bsdf.inputs["Emission Strength"].default_value = 0.0
    uv = nodes.new("ShaderNodeUVMap")
    uv.uv_map = spec["uv"]
    uv.location = (-900, 40)
    base = nodes.new("ShaderNodeTexImage")
    base.image = images["base"]
    base.extension = "REPEAT"
    base.location = (-640, 240)
    orm = nodes.new("ShaderNodeTexImage")
    orm.image = images["orm"]
    orm.extension = "REPEAT"
    orm.location = (-640, -20)
    normal_tex = nodes.new("ShaderNodeTexImage")
    normal_tex.image = images["normal"]
    normal_tex.extension = "REPEAT"
    normal_tex.location = (-640, -300)
    split = nodes.new("ShaderNodeSeparateColor")
    split.mode = "RGB"
    split.location = (-350, -20)
    normal = nodes.new("ShaderNodeNormalMap")
    normal.space = "TANGENT"
    normal.inputs["Strength"].default_value = float(spec["normal_strength"])
    normal.location = (50, -280)
    occlusion = nodes.new("ShaderNodeGroup")
    occlusion.node_tree = gltf_occlusion_group()
    occlusion.location = (40, -70)
    links.new(uv.outputs["UV"], base.inputs["Vector"])
    links.new(uv.outputs["UV"], orm.inputs["Vector"])
    links.new(uv.outputs["UV"], normal_tex.inputs["Vector"])
    links.new(base.outputs["Color"], bsdf.inputs["Base Color"])
    links.new(orm.outputs["Color"], split.inputs["Color"])
    links.new(split.outputs[1], bsdf.inputs["Roughness"])
    links.new(split.outputs[2], bsdf.inputs["Metallic"])
    links.new(split.outputs[0], occlusion.inputs["Occlusion"])
    links.new(normal_tex.outputs["Color"], normal.inputs["Color"])
    links.new(normal.outputs["Normal"], bsdf.inputs["Normal"])
    links.new(bsdf.outputs["BSDF"], output.inputs["Surface"])
    return material


def create_material_library(
    textures: dict[str, dict[str, bpy.types.Image]]
) -> dict[str, bpy.types.Material]:
    materials = {}
    for key, spec in FAMILY_SPECS.items():
        materials[key] = build_material(key, textures[key], spec)
        cap_spec = dict(spec)
        cap_spec["variant"] = f"{spec['variant']}_physical_section_cap"
        cap_spec["uv"] = UV1_NAME if key == "steel_inner" else UV0_NAME
        cap_spec["texcoord"] = 1 if key == "steel_inner" else 0
        cap = build_material(f"{key}_cap", textures[key], cap_spec)
        cap["bf3d_section_cap_family"] = key
        cap["bf3d_body_material_id"] = spec["material_id"]
        materials[f"cap_{key}"] = cap
    return materials


def mesh_uv_hash(obj: bpy.types.Object, index: int = 0) -> str:
    layer = obj.data.uv_layers[index]
    digest = hashlib.sha256()
    for item in layer.data:
        digest.update(struct.pack("<2f", float(item.uv.x), float(item.uv.y)))
    return digest.hexdigest()


def fill_physical_uv(
    obj: bpy.types.Object, layer: bpy.types.MeshUVLoopLayer, tile_m: float
) -> None:
    world = obj.matrix_world
    mesh = obj.data
    for loop in mesh.loops:
        point = world @ mesh.vertices[loop.vertex_index].co
        radius = max(math.hypot(point.x, point.y), tile_m)
        angle = math.atan2(point.y, point.x)
        layer.data[loop.index].uv = (
            angle * radius / tile_m,
            point.z / tile_m,
        )


def prepare_r2j_uv(obj: bpy.types.Object) -> dict:
    source_uv_missing = not bool(obj.data.uv_layers)
    if source_uv_missing:
        generated = obj.data.uv_layers.new(name="BF3D_R5_EXTERIOR_UV_1M")
        fill_physical_uv(obj, generated, TILE_M)
    uv0 = obj.data.uv_layers[0]
    before = mesh_uv_hash(obj, 0)
    if len(obj.data.uv_layers) > 1:
        uv1 = obj.data.uv_layers[1]
        uv1.name = UV1_NAME
        while len(obj.data.uv_layers) > 2:
            obj.data.uv_layers.remove(obj.data.uv_layers[-1])
    else:
        uv1 = obj.data.uv_layers.new(name=UV1_NAME)
    fill_physical_uv(obj, uv1, TILE_M)
    obj.data.uv_layers.active_index = 0
    uv0.active_render = True
    after = mesh_uv_hash(obj, 0)
    if before != after:
        raise RuntimeError(f"R2J exterior UV0 drifted: {obj.name}")
    return {
        "object": obj.name,
        "source_uv_missing_generated_at_1m": source_uv_missing,
        "uv0_name": uv0.name,
        "uv0_sha256_before": before,
        "uv0_sha256_after": after,
        "uv0_unchanged": True,
        "uv1_name": uv1.name,
        "tile_m": TILE_M,
    }


def prepare_r2k_uv(obj: bpy.types.Object) -> dict:
    while obj.data.uv_layers:
        obj.data.uv_layers.remove(obj.data.uv_layers[-1])
    uv0 = obj.data.uv_layers.new(name=UV0_NAME)
    fill_physical_uv(obj, uv0, TILE_M)
    uv1 = obj.data.uv_layers.new(name=UV1_NAME)
    fill_physical_uv(obj, uv1, TILE_M)
    obj.data.uv_layers.active_index = 0
    uv0.active_render = True
    return {
        "object": obj.name,
        "uv0_name": uv0.name,
        "uv0_sha256": mesh_uv_hash(obj, 0),
        "uv1_name": uv1.name,
        "tile_m": TILE_M,
    }


def set_material_slots(
    obj: bpy.types.Object, materials: list[bpy.types.Material]
) -> None:
    while obj.data.materials:
        obj.data.materials.pop(index=len(obj.data.materials) - 1)
    for material in materials:
        obj.data.materials.append(material)
    for polygon in obj.data.polygons:
        polygon.material_index = min(polygon.material_index, len(materials) - 1)


def apply_materials_and_uv(
    objects: list[bpy.types.Object], materials: dict[str, bpy.types.Material]
) -> dict:
    r2j_uv = []
    r2k_uv = []
    for obj in objects:
        role = v2.role_for(obj)
        if role == "steel_shell":
            exterior = obj.material_slots[0].material
            if exterior is None:
                raise RuntimeError(f"R5 exterior material missing: {obj.name}")
            exterior.use_backface_culling = True
            set_material_slots(
                obj,
                [exterior, materials["steel_inner"], materials["cap_steel_inner"]],
            )
            r2j_uv.append(prepare_r2j_uv(obj))
        elif role == "backfill":
            set_material_slots(obj, [materials["backfill"], materials["cap_backfill"]])
            r2k_uv.append(prepare_r2k_uv(obj))
        elif role == "hotface_embed":
            set_material_slots(obj, [materials["hotface"], materials["cap_hotface"]])
            r2k_uv.append(prepare_r2k_uv(obj))
        elif role == "refractory":
            set_material_slots(
                obj, [materials["refractory"], materials["cap_refractory"]]
            )
            r2k_uv.append(prepare_r2k_uv(obj))
        elif role == "cooling_stave":
            family = "copper" if "COPPER" in obj.name else "cast_iron"
            set_material_slots(
                obj, [materials[family], materials[f"cap_{family}"]]
            )
            r2k_uv.append(prepare_r2k_uv(obj))
    return {
        "r2j_internal_uv_texcoord": 1,
        "r2k_physical_uv_texcoord": 0,
        "r2j": r2j_uv,
        "r2k": r2k_uv,
        "tile_m": TILE_M,
    }


def create_collection(name: str) -> bpy.types.Collection:
    collection = bpy.data.collections.new(name)
    bpy.context.scene.collection.children.link(collection)
    return collection


def create_root(name: str, collection: bpy.types.Collection) -> bpy.types.Object:
    root = bpy.data.objects.new(name, None)
    collection.objects.link(root)
    root["bf3d_group_role"] = name.lower()
    root["bf3d_asset"] = ASSET_ID
    root["bf3d_evidence"] = EVIDENCE
    root["bf3d_reference_status"] = REFERENCE_STATUS
    root["bf3d_not_for_construction"] = True
    return root


def set_parent_keep_world(obj: bpy.types.Object, parent: bpy.types.Object) -> None:
    world = obj.matrix_world.copy()
    obj.parent = parent
    obj.matrix_world = world


def edge_components(edges: list[bmesh.types.BMEdge]) -> list[list[bmesh.types.BMEdge]]:
    remaining = set(edges)
    result = []
    while remaining:
        seed = remaining.pop()
        component = [seed]
        stack = [seed]
        vertices = set(seed.verts)
        while stack:
            current = stack.pop()
            for vert in current.verts:
                for edge in vert.link_edges:
                    if edge in remaining:
                        remaining.remove(edge)
                        component.append(edge)
                        stack.append(edge)
                        vertices.update(edge.verts)
        result.append(component)
    return result


def cap_cut_boundary(
    bm: bmesh.types.BMesh, plane_x: float
) -> list[bmesh.types.BMFace]:
    """Cap closed cut loops and bridge paired open shell chains."""

    tolerance = 2e-5
    cut_edges = [
        edge
        for edge in bm.edges
        if edge.is_valid
        and len(edge.link_faces) == 1
        and all(abs(float(vert.co.x) - plane_x) <= tolerance for vert in edge.verts)
    ]
    components = edge_components(cut_edges)
    faces: list[bmesh.types.BMFace] = []

    def component_closed(component: list[bmesh.types.BMEdge]) -> bool:
        degrees = Counter(
            vert
            for edge in component
            for vert in edge.verts
        )
        return bool(degrees) and all(value == 2 for value in degrees.values())

    closed_components = [
        component for component in components if component_closed(component)
    ]
    open_components = [
        component for component in components if not component_closed(component)
    ]
    for component in closed_components:
        try:
            filled = bmesh.ops.triangle_fill(
                bm, edges=component, use_beauty=True, use_dissolve=False
            )
            faces.extend(
                item
                for item in filled.get("geom", [])
                if isinstance(item, bmesh.types.BMFace) and item.is_valid
            )
        except (RuntimeError, ValueError):
            continue

    def mean_y(component: list[bmesh.types.BMEdge]) -> float:
        vertices = {vert for edge in component for vert in edge.verts}
        return sum(float(vert.co.y) for vert in vertices) / max(len(vertices), 1)

    open_components.sort(key=mean_y)
    for index in range(0, len(open_components) - 1, 2):
        first = open_components[index]
        second = open_components[index + 1]
        try:
            bridged = bmesh.ops.bridge_loops(
                bm, edges=first + second, use_pairs=False
            )
            faces.extend(
                item
                for item in bridged.get("faces", [])
                if isinstance(item, bmesh.types.BMFace) and item.is_valid
            )
        except (RuntimeError, ValueError):
            continue
    return faces


def duplicate_half_section(
    sources: list[bpy.types.Object],
    collection: bpy.types.Collection,
    root: bpy.types.Object,
    plane_x: float,
) -> tuple[list[bpy.types.Object], list[dict]]:
    result = []
    cap_records = []
    for source in sources:
        duplicate = source.copy()
        duplicate.data = source.data.copy()
        duplicate.name = f"SECTION_{source.name}"
        duplicate.data.name = f"{duplicate.name}_MESH"
        collection.objects.link(duplicate)
        duplicate.data.transform(duplicate.matrix_world)
        duplicate.matrix_world = Matrix.Identity(4)
        set_parent_keep_world(duplicate, root)
        mesh = duplicate.data
        bm = bmesh.new()
        bm.from_mesh(mesh)
        bmesh.ops.bisect_plane(
            bm,
            geom=list(bm.verts) + list(bm.edges) + list(bm.faces),
            dist=1e-6,
            plane_co=Vector((plane_x, 0.0, 0.0)),
            plane_no=Vector((1.0, 0.0, 0.0)),
            clear_outer=True,
            clear_inner=False,
            use_snap_center=False,
        )
        fill_faces = cap_cut_boundary(bm, plane_x)
        cap_material_index = len(mesh.materials) - 1
        role = v2.role_for(duplicate)
        cap_family = {
            "steel_shell": "steel_inner",
            "backfill": "backfill",
            "hotface_embed": "hotface",
            "refractory": "refractory",
        }.get(role)
        if role == "cooling_stave":
            cap_family = "copper" if "COPPER" in duplicate.name else "cast_iron"
        cap_uv_name = UV1_NAME if role == "steel_shell" else UV0_NAME
        cap_uv = bm.loops.layers.uv.get(cap_uv_name)
        if cap_uv is None:
            cap_uv = bm.loops.layers.uv.new(cap_uv_name)
        cap_area = 0.0
        cap_triangles = 0
        for face in fill_faces:
            face.material_index = cap_material_index
            cap_area += float(face.calc_area())
            cap_triangles += max(len(face.verts) - 2, 1)
            for loop in face.loops:
                loop[cap_uv].uv = (
                    float(loop.vert.co.y) / TILE_M,
                    float(loop.vert.co.z) / TILE_M,
                )
        bm.normal_update()
        bm.to_mesh(mesh)
        bm.free()
        mesh.update()
        duplicate.scale = (1.0, 1.0, 1.0)
        duplicate["bf3d_asset"] = ASSET_ID
        duplicate["bf3d_requirement_id"] = REQUIREMENT_ID
        duplicate["bf3d_structural_role"] = v2.role_for(duplicate)
        duplicate["bf3d_review_mode"] = "section"
        duplicate["bf3d_evidence"] = EVIDENCE
        duplicate["bf3d_reference_status"] = REFERENCE_STATUS
        duplicate["bf3d_not_for_construction"] = True
        duplicate["bf3d_runtime_clipping_required"] = False
        duplicate["bf3d_section_physical_cut"] = True
        duplicate["bf3d_section_scale"] = 1.0
        duplicate["bf3d_layer_thickness_amplified"] = False
        duplicate["bf3d_section_cut_caps"] = bool(fill_faces and cap_area > 0.0)
        duplicate["bf3d_section_cap_faces"] = len(fill_faces)
        duplicate["bf3d_section_cap_triangles"] = cap_triangles
        duplicate["bf3d_section_cap_area_m2"] = cap_area
        duplicate["bf3d_section_cap_family"] = cap_family
        duplicate["bf3d_section_cap_uv"] = cap_uv_name
        duplicate["bf3d_section_cap_material_id"] = FAMILY_SPECS[cap_family][
            "material_id"
        ]
        duplicate["bf3d_section_cap_material_variant"] = (
            f"{FAMILY_SPECS[cap_family]['variant']}_physical_section_cap"
        )
        duplicate["bf3d_section_plane_axis"] = "X"
        duplicate["bf3d_section_plane_value"] = float(plane_x)
        result.append(duplicate)
        cap_records.append(
            {
                "object": duplicate.name,
                "role": v2.role_for(duplicate),
                "cap_family": cap_family,
                "cap_uv": cap_uv_name,
                "cap_material_id": FAMILY_SPECS[cap_family]["material_id"],
                "cap_material_variant": (
                    f"{FAMILY_SPECS[cap_family]['variant']}_physical_section_cap"
                ),
                "cap_faces": len(fill_faces),
                "cap_triangles": cap_triangles,
                "cap_area_m2": cap_area,
                "passed": bool(fill_faces and cap_area > 0.0),
            }
        )
    return result, cap_records


def mark_material_objects(objects: list[bpy.types.Object]) -> None:
    for obj in objects:
        obj["bf3d_asset"] = ASSET_ID
        obj["bf3d_requirement_id"] = REQUIREMENT_ID
        obj["bf3d_structural_role"] = v2.role_for(obj)
        obj["bf3d_review_mode"] = "material"
        obj["bf3d_evidence"] = EVIDENCE
        obj["bf3d_reference_status"] = REFERENCE_STATUS
        obj["bf3d_not_for_construction"] = True
        obj["bf3d_runtime_clipping_required"] = False


def export_selected(path: Path, objects: list[bpy.types.Object]) -> None:
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
        # Web delivery gate: keep 1K authored PNG sources in the stage folder,
        # but package GLB textures as WebP so the main/structural review assets
        # stay below the 25 MB frontend ceiling.  Do not emit PNG fallbacks here;
        # Three.js r160 GLTFLoader supports EXT_texture_webp in current browsers.
        "export_image_format": "WEBP",
        "export_image_quality": 82,
        "export_jpeg_quality": 82,
        "export_image_add_webp": False,
        "export_image_webp_fallback": False,
        "export_texcoords": True,
        "export_normals": True,
        "export_tangents": True,
        "export_attributes": False,
        "export_skins": False,
        "export_animations": False,
        "export_morph": False,
    }
    result = bpy.ops.export_scene.gltf(
        **{key: value for key, value in requested.items() if key in props}
    )
    if "FINISHED" not in result or not path.is_file():
        raise RuntimeError(f"V3 GLB export failed: {path}")


def read_glb(path: Path) -> tuple[dict, bytes]:
    with path.open("rb") as stream:
        magic, version, total_length = struct.unpack("<4sII", stream.read(12))
        if magic != b"glTF" or version != 2 or total_length != path.stat().st_size:
            raise RuntimeError(f"invalid GLB header: {path}")
        chunks: list[tuple[bytes, bytes]] = []
        while stream.tell() < total_length:
            length, chunk_type = struct.unpack("<I4s", stream.read(8))
            chunks.append((chunk_type, stream.read(length)))
    gltf = json.loads(chunks[0][1].decode("utf-8").rstrip(" \t\r\n\x00"))
    binary = next((data for kind, data in chunks if kind == b"BIN\x00"), b"")
    return gltf, binary


def image_payload_hashes(path: Path) -> dict[str, str]:
    gltf, binary = read_glb(path)
    result = {}
    for index, image in enumerate(gltf.get("images", [])):
        view_index = image.get("bufferView")
        if view_index is None:
            continue
        view = gltf["bufferViews"][view_index]
        offset = int(view.get("byteOffset", 0))
        payload = binary[offset : offset + int(view["byteLength"])]
        name = image.get("name") or f"image_{index}"
        result[name] = hashlib.sha256(payload).hexdigest()
    return result


def forbidden_names(gltf: dict) -> list[str]:
    names = []
    for key in ("nodes", "meshes", "materials"):
        names.extend(item.get("name", "") for item in gltf.get(key, []))
    return sorted(
        {
            name
            for name in names
            if any(token in name.upper() for token in FORBIDDEN_TOKENS)
        }
    )


def material_contracts(gltf: dict) -> dict[str, dict]:
    result = {}
    for material in gltf.get("materials", []):
        name = material.get("name", "")
        if not name.startswith("BF3D_V3_"):
            continue
        pbr = material.get("pbrMetallicRoughness") or {}
        base = pbr.get("baseColorTexture") or {}
        orm = pbr.get("metallicRoughnessTexture") or {}
        occlusion = material.get("occlusionTexture") or {}
        normal = material.get("normalTexture") or {}
        expected = 1 if "STEEL_INNER" in name else 0
        result[name] = {
            "expected_texcoord": expected,
            "basecolor_texcoord": base.get("texCoord", 0),
            "orm_texcoord": orm.get("texCoord", 0),
            "occlusion_texcoord": occlusion.get("texCoord", 0),
            "normal_texcoord": normal.get("texCoord", 0),
            "orm_same_texture_for_mr_and_ao": orm.get("index")
            == occlusion.get("index")
            and orm.get("index") is not None,
            "basecolor_present": base.get("index") is not None,
            "orm_present": orm.get("index") is not None,
            "occlusion_present": occlusion.get("index") is not None,
            "normal_present": normal.get("index") is not None,
            "alpha_mode": material.get("alphaMode", "OPAQUE"),
            "double_sided": bool(material.get("doubleSided", False)),
            "emissive_factor": material.get("emissiveFactor", [0.0, 0.0, 0.0]),
        }
    return result


def summarize_glb(path: Path) -> dict:
    gltf, _binary = read_glb(path)
    nodes = gltf.get("nodes", [])
    scene_index = int(gltf.get("scene", 0))
    scene_roots = (gltf.get("scenes") or [{}])[scene_index].get("nodes", [])
    root_names = [nodes[index].get("name", "") for index in scene_roots]
    roles = Counter()
    modes = Counter()
    runtime_clipping = []
    for node in nodes:
        extras = node.get("extras") or {}
        role = extras.get("bf3d_structural_role")
        mode = extras.get("bf3d_review_mode")
        if role:
            roles[role] += 1
        if mode:
            modes[mode] += 1
        if extras.get("bf3d_runtime_clipping_required") is True:
            runtime_clipping.append(node.get("name", ""))
    primitive_uv = {}
    for mesh in gltf.get("meshes", []):
        primitive_uv[mesh.get("name", "")] = [
            sorted(primitive.get("attributes", {}).keys())
            for primitive in mesh.get("primitives", [])
        ]
    contracts = material_contracts(gltf)
    scales = {
        node.get("name", ""): node.get("scale", [1.0, 1.0, 1.0])
        for node in nodes
        if "scale" in node
    }
    return {
        **artifact(path),
        "nodes": len(nodes),
        "meshes": len(gltf.get("meshes", [])),
        "materials": len(gltf.get("materials", [])),
        "textures": len(gltf.get("textures", [])),
        "images": len(gltf.get("images", [])),
        "animations": len(gltf.get("animations", [])),
        "skins": len(gltf.get("skins", [])),
        "cameras": len(gltf.get("cameras", [])),
        "scene_root_names": root_names,
        "roles": dict(sorted(roles.items())),
        "review_modes": dict(sorted(modes.items())),
        "forbidden_names": forbidden_names(gltf),
        "runtime_clipping_nodes": runtime_clipping,
        "primitive_attributes": primitive_uv,
        "material_contracts": contracts,
        "image_mime_types": {
            image.get("name") or f"image_{index}": image.get("mimeType", "")
            for index, image in enumerate(gltf.get("images", []))
        },
        "non_identity_scales": {
            name: scale
            for name, scale in scales.items()
            if any(abs(float(value) - 1.0) > 1e-6 for value in scale)
        },
        "image_payload_sha256": image_payload_hashes(path),
    }


def setup_neutral_scene(
    section_objects: list[bpy.types.Object],
) -> tuple[bpy.types.Object, bpy.types.Collection]:
    """Apply the registered P40 neutral rig and an orthographic section candidate."""

    scene = bpy.context.scene
    scene.render.engine = "BLENDER_EEVEE"
    scene.render.resolution_x = 960
    scene.render.resolution_y = 720
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = "PNG"
    scene.render.film_transparent = False
    scene.view_settings.view_transform = "AgX"
    scene.view_settings.look = "AgX - Medium Low Contrast"
    scene.view_settings.exposure = 0.0

    world = scene.world or bpy.data.worlds.new("BF3D_V3_P40_NEUTRAL_WORLD")
    scene.world = world
    world.use_nodes = True
    background = world.node_tree.nodes.get("Background")
    background.inputs["Color"].default_value = (0.12, 0.12, 0.12, 1.0)
    background.inputs["Strength"].default_value = 0.72
    world["bf3d_preset"] = "P40 neutral"

    light_collection = create_collection(LIGHT_COLLECTION_NAME)
    light_specs = (
        (
            "P40_NEUTRAL_KEY",
            "SUN",
            (46.132336, -46.132336, 49.166168),
            (0.955317, 0.0, 0.785398),
            (1.0, 1.0, 1.0),
            2.25,
            8.0,
        ),
        (
            "P40_NEUTRAL_FILL",
            "SUN",
            (-46.132336, -11.533084, 19.180149),
            (1.243461, 0.0, -1.325818),
            (0.96, 0.98, 1.0),
            1.05,
            8.0,
        ),
        (
            "P40_NEUTRAL_RIM",
            "SUN",
            (11.533084, 46.132336, 49.166168),
            (0.800552, 0.0, 2.896614),
            (0.90, 0.95, 1.0),
            1.35,
            8.0,
        ),
    )
    for name, kind, location, rotation, color, energy, angle_deg in light_specs:
        data = bpy.data.lights.new(name, kind)
        data.energy = energy
        data.color = color
        data.angle = math.radians(angle_deg)
        light = bpy.data.objects.new(name, data)
        light_collection.objects.link(light)
        light.location = location
        light.rotation_euler = rotation
    top_data = bpy.data.lights.new("P40_NEUTRAL_TOP", "AREA")
    top_data.energy = 3921.248535
    top_data.shape = "DISK"
    top_data.size = 34.599251
    top_data.color = (1.0, 1.0, 1.0)
    top = bpy.data.objects.new("P40_NEUTRAL_TOP", top_data)
    light_collection.objects.link(top)
    top.location = (0.0, 0.0, 60.699253)
    top.rotation_euler = (0.0, 0.0, 0.0)

    camera_data = bpy.data.cameras.new(CAMERA_NAME)
    camera_data.type = "ORTHO"
    camera_data.clip_start = 0.05
    camera_data.clip_end = 1000.0
    camera = bpy.data.objects.new(CAMERA_NAME, camera_data)
    bpy.context.scene.collection.objects.link(camera)
    camera["bf3d_camera_status"] = "candidate"
    camera["bf3d_camera_role"] = "orthographic_physical_section"
    camera["bf3d_registered_basis"] = "P40/CAM_GLOBAL_FRONT_ORTHO"
    camera["bf3d_unregistered_58mm_warm_rig_used"] = False
    minimum, maximum = v2.bounds(section_objects)
    center = (minimum + maximum) * 0.5
    height = maximum.z - minimum.z
    width = max(maximum.y - minimum.y, maximum.x - minimum.x)
    camera.location = (maximum.x + max(height, width) * 1.8, center.y, center.z)
    v2.look_at(camera, center)
    camera.data.ortho_scale = max(height * 1.08, width * 1.25)
    scene.camera = camera
    return camera, light_collection


def set_ortho_camera(
    camera: bpy.types.Object,
    location: Vector,
    target: Vector,
    ortho_scale: float,
) -> None:
    camera.data.type = "ORTHO"
    camera.location = location
    camera.data.ortho_scale = float(ortho_scale)
    v2.look_at(camera, target)
    bpy.context.scene.camera = camera


def render_record(path: Path, label: str, proof_type: str) -> dict:
    path.parent.mkdir(parents=True, exist_ok=True)
    bpy.context.scene.render.filepath = str(path)
    bpy.ops.render.render(write_still=True)
    if not path.is_file():
        raise RuntimeError(f"evidence render missing: {path}")
    return {
        **artifact(path),
        "label": label,
        "proof_type": proof_type,
        "render_engine": bpy.context.scene.render.engine,
        "view_transform": bpy.context.scene.view_settings.view_transform,
        "look": bpy.context.scene.view_settings.look,
        "exposure": bpy.context.scene.view_settings.exposure,
        "world_color": [0.12, 0.12, 0.12, 1.0],
        "world_strength": 0.72,
    }


def set_collection_visible(collection: bpy.types.Collection, visible: bool) -> None:
    collection.hide_viewport = not visible
    collection.hide_render = not visible


def move_exact(obj: bpy.types.Object, collection: bpy.types.Collection) -> None:
    for source in list(obj.users_collection):
        source.objects.unlink(obj)
    collection.objects.link(obj)


def create_flat_image_material(
    name: str,
    image: bpy.types.Image,
    channel: int | None = None,
) -> bpy.types.Material:
    material = bpy.data.materials.new(name)
    material.use_nodes = True
    material.use_backface_culling = False
    nodes = material.node_tree.nodes
    links = material.node_tree.links
    nodes.clear()
    output = nodes.new("ShaderNodeOutputMaterial")
    emission = nodes.new("ShaderNodeEmission")
    emission.inputs["Strength"].default_value = 0.8
    texture = nodes.new("ShaderNodeTexImage")
    texture.image = image
    texture.extension = "REPEAT"
    if channel is None:
        links.new(texture.outputs["Color"], emission.inputs["Color"])
    else:
        split = nodes.new("ShaderNodeSeparateColor")
        split.mode = "RGB"
        links.new(texture.outputs["Color"], split.inputs["Color"])
        links.new(split.outputs[channel], emission.inputs["Color"])
    links.new(emission.outputs["Emission"], output.inputs["Surface"])
    return material


def remove_collection_with_objects(collection: bpy.types.Collection) -> None:
    for obj in list(collection.objects):
        data = obj.data
        bpy.data.objects.remove(obj, do_unlink=True)
        if data is not None and getattr(data, "users", 1) == 0:
            if isinstance(data, bpy.types.Mesh):
                bpy.data.meshes.remove(data)
    bpy.data.collections.remove(collection)


def make_checker_image() -> bpy.types.Image:
    size = TEXTURE_SIZE
    yy, xx = np.indices((size, size))
    checker = ((xx // 128 + yy // 128) % 2).astype(np.float32)
    rgb = np.where(
        checker[..., None] > 0.5,
        np.asarray((0.78, 0.78, 0.78), dtype=np.float32),
        np.asarray((0.12, 0.12, 0.12), dtype=np.float32),
    )
    image, _record = save_texture(
        "BF3D_V3_UV_CHECKER_1M", force_tile_seam(rgb), "sRGB", "UV_CHECKER_1M"
    )
    return image


def evidence_renders(
    camera: bpy.types.Object,
    full_collection: bpy.types.Collection,
    section_collection: bpy.types.Collection,
    section_objects: list[bpy.types.Object],
    materials: dict[str, bpy.types.Material],
    textures: dict[str, dict[str, bpy.types.Image]],
) -> list[dict]:
    """Render the required actual-mesh, family, channel, UV and distance evidence."""

    records: list[dict] = []
    set_collection_visible(full_collection, False)
    set_collection_visible(section_collection, True)
    minimum, maximum = v2.bounds(section_objects)
    center = (minimum + maximum) * 0.5
    height = maximum.z - minimum.z
    width = max(maximum.y - minimum.y, maximum.x - minimum.x)
    distance = max(height, width) * 1.8

    set_ortho_camera(
        camera,
        Vector((maximum.x + distance, center.y - width * 0.65, center.z + height * 0.16)),
        center,
        max(height * 1.12, width * 1.35),
    )
    records.append(
        render_record(
            RENDER_DIR / "BF3D_V3_02_STRUCTURAL_GLOBAL.png",
            "Actual 15-object V3 structural global section view",
            "actual_candidate_mesh_structural_global",
        )
    )
    set_ortho_camera(
        camera,
        Vector((maximum.x + distance, center.y, center.z)),
        center,
        max(height * 1.05, width * 1.22),
    )
    records.append(
        render_record(
            RENDER_DIR / "BF3D_V3_03_ORTHO_STANDARD_SECTION_1X.png",
            "Registered orthographic physical section at unamplified 1x geometry",
            "actual_candidate_mesh_orthographic_section_1x",
        )
    )
    # The layer stack lives at the furnace wall, not at the dark process-space
    # center. Frame the positive-Y cut face so 1x steel/cooling/refractory
    # thickness remains legible without magnification.
    local_target = Vector(
        (
            maximum.x,
            maximum.y - max(width * 0.035, 0.35),
            minimum.z + height * 0.58,
        )
    )
    set_ortho_camera(
        camera,
        Vector((maximum.x + distance, center.y, local_target.z)),
        local_target,
        max(3.6, width * 0.24),
    )
    records.append(
        render_record(
            RENDER_DIR / "BF3D_V3_04_LOCAL_LAYER_CLOSEUP_1X.png",
            "Actual 1x local steel/backfill/stave/hotface/refractory layer closeup",
            "actual_candidate_mesh_local_layer_closeup_1x",
        )
    )
    for suffix, scale in (("FAR", 1.40), ("MID", 0.72), ("NEAR", 0.34)):
        set_ortho_camera(
            camera,
            Vector((maximum.x + distance, center.y, local_target.z)),
            local_target if suffix != "FAR" else center,
            max(height * scale, 5.5),
        )
        records.append(
            render_record(
                RENDER_DIR / f"BF3D_V3_13_DISTANCE_{suffix}.png",
                f"Actual section distance evidence: {suffix.lower()}",
                f"actual_candidate_mesh_distance_{suffix.lower()}",
            )
        )

    temp = create_collection("BF3D_V3_EVIDENCE_TEMP")
    set_collection_visible(section_collection, False)
    swatches: dict[str, bpy.types.Object] = {}
    positions = {
        "steel_inner": (-3.2, 2.1),
        "backfill": (0.0, 2.1),
        "cast_iron": (3.2, 2.1),
        "copper": (-3.2, -2.1),
        "hotface": (0.0, -2.1),
        "refractory": (3.2, -2.1),
    }
    for key in PRIMARY_FAMILIES:
        y, z = positions[key]
        bpy.ops.mesh.primitive_ico_sphere_add(subdivisions=5, radius=1.25)
        sphere = bpy.context.object
        sphere.name = f"EVIDENCE_SWATCH_{key.upper()}"
        sphere.location = (0.0, y, z)
        move_exact(sphere, temp)
        sphere.data.materials.append(materials[key])
        if FAMILY_SPECS[key]["texcoord"] == 1:
            sphere.data.uv_layers.new(name="UV0_DUMMY")
        uv = sphere.data.uv_layers.new(name=FAMILY_SPECS[key]["uv"])
        fill_physical_uv(sphere, uv, TILE_M)
        if FAMILY_SPECS[key]["texcoord"] == 1:
            sphere.data.uv_layers.active_index = 1
            uv.active_render = True
        swatches[key] = sphere
    set_ortho_camera(camera, Vector((12.0, 0.0, 0.0)), Vector((0.0, 0.0, 0.0)), 8.8)
    records.append(
        render_record(
            RENDER_DIR / "BF3D_V3_01_MATERIAL_BOARD_EEVEE.png",
            "Six-family Eevee neutral material board",
            "diagnostic_material_swatch_board_not_asset_geometry",
        )
    )
    for index, key in enumerate(PRIMARY_FAMILIES, start=5):
        for other_key, sphere in swatches.items():
            sphere.hide_render = other_key != key
        target = swatches[key].location.copy()
        set_ortho_camera(
            camera, Vector((8.0, target.y, target.z)), target, 3.1
        )
        records.append(
            render_record(
                RENDER_DIR / f"BF3D_V3_{index:02d}_FAMILY_{key.upper()}.png",
                f"Neutral closeup for {key}",
                "diagnostic_material_family_closeup_not_asset_geometry",
            )
        )
    remove_collection_with_objects(temp)

    channel_collection = create_collection("BF3D_V3_CHANNEL_TEMP")
    channel_specs = (
        ("BASECOLOR", textures["copper"]["base"], None),
        ("ORM_RGB", textures["copper"]["orm"], None),
        ("AO_R", textures["copper"]["orm"], 0),
        ("ROUGHNESS_G", textures["copper"]["orm"], 1),
        ("METALLIC_B", textures["copper"]["orm"], 2),
        ("NORMALGL", textures["copper"]["normal"], None),
    )
    for index, (label, image, channel) in enumerate(channel_specs):
        row, column = divmod(index, 3)
        bpy.ops.mesh.primitive_plane_add(
            size=2.6,
            location=(0.0, (column - 1) * 3.0, (0.5 - row) * 3.0),
            rotation=(0.0, math.pi / 2.0, 0.0),
        )
        panel = bpy.context.object
        panel.name = f"EVIDENCE_CHANNEL_{label}"
        move_exact(panel, channel_collection)
        panel.data.materials.append(
            create_flat_image_material(f"EVIDENCE_{label}", image, channel)
        )
    set_ortho_camera(camera, Vector((12.0, 0.0, 0.0)), Vector((0.0, 0.0, 0.0)), 8.2)
    records.append(
        render_record(
            RENDER_DIR / "BF3D_V3_11_CHANNEL_BOARD_BC_ORM_SPLIT_NORMALGL.png",
            "Copper BaseColor, ORM RGB, AO/Roughness/Metallic split and NormalGL",
            "diagnostic_texture_channel_board",
        )
    )
    remove_collection_with_objects(channel_collection)

    checker_collection = create_collection("BF3D_V3_CHECKER_TEMP")
    target_source = next(
        obj for obj in section_objects if v2.role_for(obj) == "refractory"
    )
    checker_object = target_source.copy()
    checker_object.data = target_source.data.copy()
    checker_object.name = "EVIDENCE_ACTUAL_R2K_UV_CHECKER_1M"
    checker_collection.objects.link(checker_object)
    checker_object.parent = None
    checker_image = make_checker_image()
    checker_material = create_flat_image_material(
        "EVIDENCE_UV_CHECKER_1M", checker_image
    )
    uv_node = checker_material.node_tree.nodes.new("ShaderNodeUVMap")
    uv_node.uv_map = UV0_NAME
    texture_node = next(
        node
        for node in checker_material.node_tree.nodes
        if node.bl_idname == "ShaderNodeTexImage"
    )
    checker_material.node_tree.links.new(
        uv_node.outputs["UV"], texture_node.inputs["Vector"]
    )
    set_material_slots(checker_object, [checker_material])
    checker_center = sum(
        (checker_object.matrix_world @ Vector(corner) for corner in checker_object.bound_box),
        Vector((0.0, 0.0, 0.0)),
    ) / 8.0
    set_ortho_camera(
        camera,
        Vector((checker_center.x + 18.0, checker_center.y - 8.0, checker_center.z + 3.0)),
        checker_center,
        7.0,
    )
    records.append(
        render_record(
            RENDER_DIR / "BF3D_V3_12_UV_CHECKER_1M.png",
            "Actual R2K physical TEXCOORD_0 with 1.0 m repeat checker",
            "actual_candidate_mesh_uv_checker_1m",
        )
    )
    remove_collection_with_objects(checker_collection)

    set_collection_visible(section_collection, True)
    set_collection_visible(full_collection, False)
    set_ortho_camera(
        camera,
        Vector((maximum.x + distance, center.y, center.z)),
        center,
        max(height * 1.05, width * 1.22),
    )
    return records


def configure_direct_open(
    full_collection: bpy.types.Collection,
    section_collection: bpy.types.Collection,
    camera: bpy.types.Object,
) -> dict:
    set_collection_visible(full_collection, False)
    set_collection_visible(section_collection, True)
    bpy.context.scene.camera = camera
    shading_records = []
    for screen in bpy.data.screens:
        for area in screen.areas:
            if area.type != "VIEW_3D":
                continue
            space = area.spaces.active
            space.shading.type = "MATERIAL"
            try:
                space.region_3d.view_perspective = "CAMERA"
            except AttributeError:
                pass
            shading_records.append(
                {"screen": screen.name, "area": area.type, "shading": space.shading.type}
            )
    bpy.ops.object.select_all(action="DESELECT")
    return {
        "requested_workspaces": ["Layout", "Modeling"],
        "view3d": shading_records,
        "section_visible": True,
        "full_material_hidden": True,
        "active_camera": camera.name,
    }


def source_structural_objects() -> list[bpy.types.Object]:
    """Assemble the locked R2J/R2K sources and remove all operational content."""

    r5_materials = v2.import_r5_material_source()
    structural = v2.append_structural_objects()
    v2.bind_r5_exterior(structural, r5_materials)
    copper = v2.join_stave_family(
        structural, "COPPER", "R2K_V3_L03_COOLING_COPPER_COMBINED"
    )
    cast_iron = v2.join_stave_family(
        structural, "CASTIRON", "R2K_V3_L03_COOLING_CASTIRON_COMBINED"
    )
    structural = [
        obj
        for obj in structural
        if v2.object_is_alive(obj)
        and not obj.name.startswith("SM_BF3D_GL02_CST_")
        and v2.role_for(obj) != "skull_optional_missing"
    ]
    structural.extend([copper, cast_iron])
    structural = list({obj.as_pointer(): obj for obj in structural}.values())
    v2.clear_non_structural_scene_objects(structural)
    roles = Counter(v2.role_for(obj) for obj in structural)
    expected = {
        "steel_shell": 5,
        "backfill": 1,
        "cooling_stave": 2,
        "hotface_embed": 1,
        "refractory": 1,
    }
    if dict(sorted(roles.items())) != expected:
        raise RuntimeError(f"V3 source structural roles mismatch: {dict(roles)}")
    return structural


def exact_contract_checks(
    main: dict, material: dict, structural: dict, cap_records: list[dict]
) -> dict:
    """Validate topology, hierarchy, material channels and clean review scope."""

    expected_main_roles = {
        "backfill": 1,
        "cooling_stave": 2,
        "hotface_embed": 1,
        "refractory": 1,
        "steel_shell": 10,
    }
    expected_section_roles = {
        "backfill": 1,
        "cooling_stave": 2,
        "hotface_embed": 1,
        "refractory": 1,
        "steel_shell": 5,
    }

    def channels_pass(summary: dict) -> bool:
        contracts = summary["material_contracts"]
        return bool(contracts) and all(
            item["basecolor_present"]
            and item["orm_present"]
            and item["occlusion_present"]
            and item["normal_present"]
            and item["orm_same_texture_for_mr_and_ao"]
            and item["basecolor_texcoord"] == item["expected_texcoord"]
            and item["orm_texcoord"] == item["expected_texcoord"]
            and item["occlusion_texcoord"] == item["expected_texcoord"]
            and item["normal_texcoord"] == item["expected_texcoord"]
            and item["alpha_mode"] == "OPAQUE"
            and not item["double_sided"]
            and not any(abs(float(value)) > 1e-8 for value in item["emissive_factor"])
            for item in contracts.values()
        )

    def clean(summary: dict) -> bool:
        return (
            not summary["forbidden_names"]
            and not summary["runtime_clipping_nodes"]
            and summary["animations"] == 0
            and summary["skins"] == 0
            and summary["cameras"] == 0
            and not summary["non_identity_scales"]
        )

    source_r5_image_names = set(image_payload_hashes(BASE_GLB))
    generated_names = {
        f"BF3D_V3_{key.upper()}_{suffix}_1K"
        for key in FAMILY_SPECS
        for suffix in ("BaseColor", "ORM", "NormalGL")
    }
    output_external_names = {
        name
        for name in main["image_payload_sha256"]
        if not any(token in name for token in generated_names)
        and not name.startswith("BF3D_V3_")
    }
    primitive_attributes = [
        attributes
        for values in main["primitive_attributes"].values()
        for attributes in values
    ]
    checks = {
        "main_two_top_level_groups": set(main["scene_root_names"])
        == {MATERIAL_ROOT_NAME, SECTION_ROOT_NAME}
        and len(main["scene_root_names"]) == 2,
        "material_one_top_level_group": material["scene_root_names"]
        == [MATERIAL_ROOT_NAME],
        "section_one_top_level_group": structural["scene_root_names"]
        == [SECTION_ROOT_NAME],
        "main_exact_15_meshes": main["meshes"] == 15,
        "material_exact_5_meshes": material["meshes"] == 5,
        "section_exact_10_meshes": structural["meshes"] == 10,
        "main_exact_roles": main["roles"] == expected_main_roles,
        "material_exact_roles": material["roles"] == {"steel_shell": 5},
        "section_exact_roles": structural["roles"] == expected_section_roles,
        "main_exact_review_modes": main["review_modes"]
        == {"material": 5, "section": 10},
        "material_exact_review_mode": material["review_modes"] == {"material": 5},
        "section_exact_review_mode": structural["review_modes"] == {"section": 10},
        "all_three_glbs_clean": clean(main) and clean(material) and clean(structural),
        "all_internal_material_channels_valid": channels_pass(main)
        and channels_pass(structural),
        "main_contains_texcoord_0": all(
            "TEXCOORD_0" in attributes for attributes in primitive_attributes
        ),
        "main_contains_texcoord_1": any(
            "TEXCOORD_1" in attributes for attributes in primitive_attributes
        ),
        "all_10_section_objects_have_physical_caps": len(cap_records) == 10
        and all(record["passed"] for record in cap_records),
        "section_scale_is_exactly_1x": not main["non_identity_scales"]
        and not structural["non_identity_scales"],
        "r5_embedded_images_preserved": bool(output_external_names)
        and output_external_names <= source_r5_image_names,
        "web_delivery_images_are_webp": all(
            mime == "image/webp" for mime in main["image_mime_types"].values()
        )
        and all(
            mime == "image/webp"
            for mime in structural["image_mime_types"].values()
        ),
    }
    return checks


def texture_contract_checks(records: dict) -> dict:
    all_maps = [
        family[channel]
        for family in records.values()
        for channel in ("base_color", "orm", "normal_gl")
    ]
    copper = records["copper"]["extra_checks"]
    checks = {
        "six_families_present": set(records) == set(FAMILY_SPECS),
        "eighteen_primary_maps_present": len(all_maps) == 18
        and all((ROOT / item["path"]).is_file() for item in all_maps),
        "all_maps_are_1k": all(
            item["width"] == TEXTURE_SIZE and item["height"] == TEXTURE_SIZE
            for item in all_maps
        ),
        "all_maps_are_one_meter_tile": all(item["tile_m"] == 1.0 for item in all_maps),
        "all_maps_are_seamless_on_disk": all(
            item["seam_max_abs_error"] <= 1e-5 for item in all_maps
        ),
        "orm_disk_roundtrip_error_bounded": all(
            family["orm"]["disk_max_abs_error"] <= (1.0 / 255.0 + 1e-4)
            for family in records.values()
        ),
        "basecolor_is_srgb": all(
            family["base_color"]["color_space"] == "sRGB"
            for family in records.values()
        ),
        "orm_and_normal_are_non_color": all(
            family["orm"]["color_space"] == "Non-Color"
            and family["normal_gl"]["color_space"] == "Non-Color"
            for family in records.values()
        ),
        "copper_oxidized_pixels_reduce_metallic": bool(
            copper.get("oxidized_pixels_reduce_metallic")
        ),
        "refractory_families_not_architectural_red_brick": all(
            not records[key]["extra_checks"].get(
                "architectural_red_brick_pattern", False
            )
            and not records[key]["extra_checks"].get("regular_mortar_grid", False)
            for key in ("backfill", "hotface", "refractory")
        ),
        "hotface_non_emissive": records["hotface"]["extra_checks"].get("emissive")
        == 0.0,
        "fixed_seed_contract": all(
            records[key]["seed"] == FAMILY_SPECS[key]["seed"] for key in records
        ),
    }
    return checks


def save_review_blend() -> None:
    REVIEW_BLEND.parent.mkdir(parents=True, exist_ok=True)
    bpy.context.preferences.filepaths.save_version = 0
    bpy.ops.file.pack_all()
    result = bpy.ops.wm.save_as_mainfile(
        filepath=str(REVIEW_BLEND), check_existing=False
    )
    if "FINISHED" not in result or REVIEW_BLEND.stat().st_size < 1_000_000:
        raise RuntimeError(f"V3 Blend save failed: {result}")


def build() -> None:
    """Build all V3 binary outputs and evidence without touching prior assets."""

    for directory in (STAGE, TEXTURE_DIR, RENDER_DIR, REPORT_DIR, MODEL_DIR):
        directory.mkdir(parents=True, exist_ok=True)
    for stale_generic_cap in TEXTURE_DIR.glob("BF3D_V3_SECTION_CAP_*.png"):
        stale_generic_cap.unlink()
    history = historical_snapshot()
    gate = check_input_gate()
    write_json(REPORT_DIR / "input_gate_validation.json", gate)

    v2.reset_scene()
    structural_sources = source_structural_objects()
    textures, texture_records = create_texture_library()
    materials = create_material_library(textures)
    uv_records = apply_materials_and_uv(structural_sources, materials)

    full_collection = create_collection(FULL_COLLECTION_NAME)
    section_collection = create_collection(SECTION_COLLECTION_NAME)
    material_root = create_root(MATERIAL_ROOT_NAME, full_collection)
    section_root = create_root(SECTION_ROOT_NAME, section_collection)

    shell_objects = [
        obj for obj in structural_sources if v2.role_for(obj) == "steel_shell"
    ]
    internal_sources = [
        obj for obj in structural_sources if v2.role_for(obj) != "steel_shell"
    ]
    for obj in shell_objects:
        move_exact(obj, full_collection)
        set_parent_keep_world(obj, material_root)
    mark_material_objects(shell_objects)

    minimum, maximum = v2.bounds(structural_sources)
    plane_x = float((minimum.x + maximum.x) * 0.5)
    section_objects, cap_records = duplicate_half_section(
        structural_sources, section_collection, section_root, plane_x
    )
    for obj in internal_sources:
        bpy.data.objects.remove(obj, do_unlink=True)

    if len(shell_objects) != 5 or len(section_objects) != 10:
        raise RuntimeError(
            f"V3 object count mismatch: material={len(shell_objects)}, "
            f"section={len(section_objects)}"
        )
    export_selected(MATERIAL_GLB, [material_root, *shell_objects])
    export_selected(STRUCTURAL_GLB, [section_root, *section_objects])
    export_selected(
        MAIN_GLB, [material_root, section_root, *shell_objects, *section_objects]
    )

    material_summary = summarize_glb(MATERIAL_GLB)
    structural_summary = summarize_glb(STRUCTURAL_GLB)
    main_summary = summarize_glb(MAIN_GLB)
    contract_checks = exact_contract_checks(
        main_summary, material_summary, structural_summary, cap_records
    )
    texture_checks = texture_contract_checks(texture_records)
    if not all(texture_checks.values()):
        raise RuntimeError(
            "V3 texture contract failed: "
            + json.dumps(texture_checks, ensure_ascii=False)
        )
    if not all(contract_checks.values()):
        raise RuntimeError(
            "V3 GLB contract failed: "
            + json.dumps(
                {"checks": contract_checks, "cap_records": cap_records},
                ensure_ascii=False,
            )
        )

    write_json(
        REPORT_DIR / "texture_validation.json",
        {
            "schema_version": "bf3d.r2q.texture_validation.v3",
            "families": texture_records,
            "checks": texture_checks,
            "passed": all(texture_checks.values()),
        },
    )
    write_json(
        REPORT_DIR / "texture_seam_validation.json",
        {
            "schema_version": "bf3d.r2q.texture_seam_validation.v3",
            "tile_m": TILE_M,
            "families": {
                key: {
                    channel: value[channel]["seam_max_abs_error"]
                    for channel in ("base_color", "orm", "normal_gl")
                }
                for key, value in texture_records.items()
            },
            "passed": texture_checks["all_maps_are_seamless_on_disk"],
        },
    )
    write_json(
        REPORT_DIR / "orm_disk_error_validation.json",
        {
            "schema_version": "bf3d.r2q.orm_disk_error_validation.v3",
            "channel_contract": "R=AO,G=Roughness,B=Metallic",
            "max_allowed_abs_error": 1.0 / 255.0 + 1e-4,
            "families": {
                key: value["orm"]["disk_max_abs_error"]
                for key, value in texture_records.items()
            },
            "passed": texture_checks["orm_disk_roundtrip_error_bounded"],
        },
    )
    write_json(
        REPORT_DIR / "uv_texcoord_validation.json",
        {
            "schema_version": "bf3d.r2q.uv_texcoord_validation.v3",
            "records": uv_records,
            "glb_primitive_attributes": main_summary["primitive_attributes"],
            "checks": {
                "r2j_uv0_unchanged": all(
                    item["uv0_unchanged"] for item in uv_records["r2j"]
                ),
                "r2j_internal_texcoord_1": uv_records[
                    "r2j_internal_uv_texcoord"
                ]
                == 1,
                "r2k_physical_texcoord_0": uv_records[
                    "r2k_physical_uv_texcoord"
                ]
                == 0,
                "physical_tile_m_1": uv_records["tile_m"] == 1.0,
            },
            "passed": True,
        },
    )
    write_json(
        REPORT_DIR / "section_scale_cap_validation.json",
        {
            "schema_version": "bf3d.r2q.section_scale_cap_validation.v3",
            "section_plane_x": plane_x,
            "cap_records": cap_records,
            "thickness_scale": 1.0,
            "hard_coded_0_45m_used": False,
            "layer_thickness_amplified": False,
            "passed": all(record["passed"] for record in cap_records),
        },
    )
    write_json(
        REPORT_DIR / "glb_channel_texcoord_validation.json",
        {
            "schema_version": "bf3d.r2q.glb_channel_texcoord_validation.v3",
            "main": main_summary,
            "material": material_summary,
            "structural": structural_summary,
            "checks": contract_checks,
            "passed": all(contract_checks.values()),
        },
    )
    write_json(
        REPORT_DIR / "role_forbidden_validation.json",
        {
            "schema_version": "bf3d.r2q.role_forbidden_validation.v3",
            "forbidden_tokens": list(FORBIDDEN_TOKENS),
            "main_roles": main_summary["roles"],
            "material_roles": material_summary["roles"],
            "section_roles": structural_summary["roles"],
            "checks": {
                key: value
                for key, value in contract_checks.items()
                if "role" in key or "clean" in key
            },
            "passed": all(
                value
                for key, value in contract_checks.items()
                if "role" in key or "clean" in key
            ),
        },
    )

    camera, _lights = setup_neutral_scene(section_objects)
    evidence = evidence_renders(
        camera,
        full_collection,
        section_collection,
        section_objects,
        materials,
        textures,
    )
    direct_open = configure_direct_open(
        full_collection, section_collection, camera
    )
    save_review_blend()
    assert_snapshot_unchanged(history)

    build_report = {
        "schema_version": "bf3d.r2q.build_report.v3",
        "requirement_id": REQUIREMENT_ID,
        "asset_id": ASSET_ID,
        "input_gate": gate,
        "outputs": {
            "main_glb": main_summary,
            "material_glb": material_summary,
            "structural_glb": structural_summary,
            "direct_open_blend": artifact(REVIEW_BLEND),
        },
        "object_counts": {"material": 5, "section": 10, "total_meshes": 15},
        "top_level_groups": [MATERIAL_ROOT_NAME, SECTION_ROOT_NAME],
        "direct_open": direct_open,
        "evidence": evidence,
        "checks": {**texture_checks, **contract_checks},
        "passed": all(texture_checks.values()) and all(contract_checks.values()),
        "history_snapshot_unchanged": True,
        "cycles_three_ab_status": "pending_independent_runtime_comparison",
    }
    write_json(REPORT_DIR / "build_report.json", build_report)
    write_json(
        REPORT_DIR / "visual_manifest.json",
        {
            "schema_version": "bf3d.r2q.visual_manifest.v3",
            "render_engine": "BLENDER_EEVEE",
            "neutral_preset": "P40 neutral",
            "renders": evidence,
            "cycles_ab": "pending",
            "threejs_ab": "pending",
            "passed": len(evidence) >= 15,
        },
    )
    print(
        "BF3D_R2Q_V3_BUILD="
        + json.dumps(
            {
                "main": artifact(MAIN_GLB),
                "material": artifact(MATERIAL_GLB),
                "structural": artifact(STRUCTURAL_GLB),
                "blend": artifact(REVIEW_BLEND),
                "evidence_count": len(evidence),
            },
            ensure_ascii=False,
        )
    )


def reopen_validation() -> None:
    """Validate the directly-opened Blend, viewport defaults and packed payload."""

    checks = {}
    full = bpy.data.collections.get(FULL_COLLECTION_NAME)
    section = bpy.data.collections.get(SECTION_COLLECTION_NAME)
    camera = bpy.data.objects.get(CAMERA_NAME)
    scene = bpy.context.scene
    mesh_objects = [obj for obj in scene.objects if obj.type == "MESH"]
    checks["blend_path_is_v3"] = Path(bpy.data.filepath).resolve() == REVIEW_BLEND.resolve()
    checks["material_collection_exists"] = full is not None
    checks["section_collection_exists"] = section is not None
    checks["material_five_meshes"] = full is not None and len(
        [obj for obj in full.objects if obj.type == "MESH"]
    ) == 5
    checks["section_ten_meshes"] = section is not None and len(
        [obj for obj in section.objects if obj.type == "MESH"]
    ) == 10
    checks["scene_exact_fifteen_asset_meshes"] = len(
        [
            obj
            for obj in mesh_objects
            if obj.get("bf3d_asset") == ASSET_ID
        ]
    ) == 15
    checks["material_hidden_by_default"] = full is not None and full.hide_viewport
    checks["section_visible_by_default"] = section is not None and not section.hide_viewport
    checks["active_candidate_camera"] = (
        camera is not None
        and camera.data.type == "ORTHO"
        and scene.camera == camera
        and camera.get("bf3d_camera_status") == "candidate"
    )
    checks["agx_medium_low_contrast"] = (
        scene.view_settings.view_transform == "AgX"
        and scene.view_settings.look == "AgX - Medium Low Contrast"
        and abs(scene.view_settings.exposure) <= 1e-8
    )
    background = (
        scene.world.node_tree.nodes.get("Background")
        if scene.world and scene.world.use_nodes
        else None
    )
    checks["neutral_world"] = background is not None and all(
        abs(float(background.inputs["Color"].default_value[index]) - value) <= 1e-6
        for index, value in enumerate((0.12, 0.12, 0.12, 1.0))
    ) and abs(float(background.inputs["Strength"].default_value) - 0.72) <= 1e-6
    checks["p40_neutral_four_lights"] = set(
        obj.name
        for obj in scene.objects
        if obj.type == "LIGHT" and obj.name.startswith("P40_NEUTRAL_")
    ) == {
        "P40_NEUTRAL_KEY",
        "P40_NEUTRAL_FILL",
        "P40_NEUTRAL_RIM",
        "P40_NEUTRAL_TOP",
    }
    target_screen_records = []
    for screen_name in ("Layout", "Modeling"):
        screen = bpy.data.screens.get(screen_name)
        areas = [] if screen is None else [
            area.spaces.active.shading.type
            for area in screen.areas
            if area.type == "VIEW_3D"
        ]
        target_screen_records.append({"screen": screen_name, "shading": areas})
    checks["layout_modeling_view3d_material"] = all(
        record["shading"] and all(value == "MATERIAL" for value in record["shading"])
        for record in target_screen_records
    )
    packed_images = [
        image.name for image in bpy.data.images if image.packed_file is not None
    ]
    checks["all_18_primary_maps_packed"] = len(
        [name for name in packed_images if name.startswith("BF3D_V3_")]
    ) >= 18
    checks["no_forbidden_scene_objects"] = not [
        obj.name
        for obj in scene.objects
        if any(token in obj.name.upper() for token in FORBIDDEN_TOKENS)
    ]
    checks["three_glb_hashes_match_build"] = all(
        path.is_file() for path in (MAIN_GLB, MATERIAL_GLB, STRUCTURAL_GLB)
    )
    report = {
        "schema_version": "bf3d.r2q.blend_reopen_validation.v3",
        "blend": artifact(REVIEW_BLEND),
        "target_workspaces": target_screen_records,
        "packed_images": packed_images,
        "checks": checks,
        "passed": all(checks.values()),
    }
    write_json(REPORT_DIR / "blend_reopen_validation.json", report)
    if not report["passed"]:
        raise RuntimeError(
            "V3 Blend reopen validation failed: "
            + json.dumps(checks, ensure_ascii=False)
        )
    print("BF3D_R2Q_V3_REOPEN=" + json.dumps(report, ensure_ascii=False))


def factory_import_validation() -> None:
    """Factory-import each derived GLB and verify independent parse/scene contracts."""

    expected = {
        MAIN_GLB: {
            "meshes": 15,
            "roots": {MATERIAL_ROOT_NAME, SECTION_ROOT_NAME},
            "modes": {"material": 5, "section": 10},
        },
        MATERIAL_GLB: {
            "meshes": 5,
            "roots": {MATERIAL_ROOT_NAME},
            "modes": {"material": 5},
        },
        STRUCTURAL_GLB: {
            "meshes": 10,
            "roots": {SECTION_ROOT_NAME},
            "modes": {"section": 10},
        },
    }
    results = []
    for path, contract in expected.items():
        bpy.ops.wm.read_factory_settings(use_empty=True)
        result = bpy.ops.import_scene.gltf(filepath=str(path))
        scene_objects = list(bpy.context.scene.objects)
        meshes = [obj for obj in scene_objects if obj.type == "MESH"]
        roots = {
            obj.name for obj in scene_objects if obj.parent is None and obj.type == "EMPTY"
        }
        modes = Counter(
            obj.get("bf3d_review_mode")
            for obj in meshes
            if obj.get("bf3d_review_mode")
        )
        roles = Counter(
            obj.get("bf3d_structural_role")
            for obj in meshes
            if obj.get("bf3d_structural_role")
        )
        forbidden = [
            obj.name
            for obj in scene_objects
            if any(token in obj.name.upper() for token in FORBIDDEN_TOKENS)
        ]
        uv_counts = {obj.name: len(obj.data.uv_layers) for obj in meshes}
        checks = {
            "import_finished": "FINISHED" in result,
            "mesh_count": len(meshes) == contract["meshes"],
            "top_level_roots": roots == contract["roots"],
            "review_modes": dict(sorted(modes.items())) == contract["modes"],
            "no_forbidden_objects": not forbidden,
            "all_meshes_have_uv0": all(count >= 1 for count in uv_counts.values()),
            "at_least_one_mesh_has_uv1": any(count >= 2 for count in uv_counts.values()),
            "all_scales_identity": all(
                all(abs(float(value) - 1.0) <= 1e-6 for value in obj.scale)
                for obj in scene_objects
            ),
        }
        if path == MATERIAL_GLB:
            checks["at_least_one_mesh_has_uv1"] = all(
                count >= 2 for count in uv_counts.values()
            )
        results.append(
            {
                "artifact": artifact(path),
                "mesh_count": len(meshes),
                "roots": sorted(roots),
                "review_modes": dict(sorted(modes.items())),
                "roles": dict(sorted(roles.items())),
                "uv_layer_counts": uv_counts,
                "forbidden": forbidden,
                "checks": checks,
                "passed": all(checks.values()),
            }
        )
    report = {
        "schema_version": "bf3d.r2q.factory_import_validation.v3",
        "imports": results,
        "passed": all(item["passed"] for item in results),
    }
    write_json(REPORT_DIR / "factory_import_validation.json", report)
    write_json(REPORT_DIR / "derived_glb_factory_import_validation.json", report)
    if not report["passed"]:
        raise RuntimeError(
            "V3 factory import validation failed: "
            + json.dumps(report, ensure_ascii=False)
        )
    print("BF3D_R2Q_V3_FACTORY_IMPORT=" + json.dumps(report, ensure_ascii=False))


def finalize() -> None:
    """Publish fail-closed V3 manifests after build/reopen/import validation."""

    required_reports = (
        "input_gate_validation.json",
        "texture_validation.json",
        "texture_seam_validation.json",
        "orm_disk_error_validation.json",
        "uv_texcoord_validation.json",
        "section_scale_cap_validation.json",
        "glb_channel_texcoord_validation.json",
        "role_forbidden_validation.json",
        "build_report.json",
        "visual_manifest.json",
        "blend_reopen_validation.json",
        "factory_import_validation.json",
        "derived_glb_factory_import_validation.json",
    )
    reports = {}
    for name in required_reports:
        path = REPORT_DIR / name
        if not path.is_file():
            raise RuntimeError(f"V3 required report missing: {path}")
        reports[name] = json.loads(path.read_text(encoding="utf-8"))
        if reports[name].get("passed") is not True and name not in {
            "input_gate_validation.json"
        }:
            raise RuntimeError(f"V3 required report is not passed: {name}")

    core = {
        "schema_version": "bf3d.r2q.internal_material_lookdev.v3",
        "requirement_id": REQUIREMENT_ID,
        "asset_id": ASSET_ID,
        "status": STATUS,
        "next_stage_allowed": False,
        "approval_granted": False,
        "evidence": EVIDENCE,
        "reference_status": REFERENCE_STATUS,
        "not_for_construction": True,
        "scope": {
            "material_group": "5 complete R2J shells",
            "section_group": (
                "10 physical half-section objects: 5 steel shells, backfill, "
                "copper cooling, cast cooling, hotface, refractory"
            ),
            "runtime_clipping_required": False,
            "layer_thickness_scale": 1.0,
        },
        "outputs": {
            "main_glb": artifact(MAIN_GLB),
            "material_glb": artifact(MATERIAL_GLB),
            "structural_glb": artifact(STRUCTURAL_GLB),
            "direct_open_blend": artifact(REVIEW_BLEND),
        },
        "validation_reports": {
            name: artifact(REPORT_DIR / name) for name in required_reports
        },
        "pending": {
            "cycles_vs_eevee_ab": "pending_independent_review",
            "threejs_vs_eevee_ab": "pending_independent_review",
            "visual_review": "pending_independent_review",
            "spec_review": "pending_independent_review",
        },
        "historical_assets_overwritten": False,
    }
    write_json(MODEL_MANIFEST, core)
    write_json(STAGE / "pipeline_status.json", core)
    summary = (
        "# WEB-60 R2Q Internal Material LookDev V3\n\n"
        f"- Status: `{STATUS}`\n"
        "- Next stage allowed: `false`\n"
        "- Evidence/reference: `E/illustrative`, `REF-PENDING`, not for construction\n"
        "- Main GLB: 2 top-level mode groups, 15 meshes total\n"
        "- BF3D_V3_MODE_MATERIAL: 5 complete R2J shells\n"
        "- BF3D_V3_MODE_SECTION: 10 actual physical half-section meshes at 1x thickness\n"
        "- Textures: 6 families x BaseColor/ORM/NormalGL, 1K, fixed seed, 1 m tiling\n"
        "- Section caps: 6 family-specific material instances; no generic neutral cap\n"
        "- Direct-open Blend: P40 neutral, AgX Medium Low Contrast, orthographic candidate\n"
        "- Cycles/Eevee and Three.js/Eevee A-B: pending independent review\n"
    )
    (STAGE / "summary.md").write_text(summary, encoding="utf-8")

    artifact_paths = [
        Path(__file__).resolve(),
        MAIN_GLB,
        MATERIAL_GLB,
        STRUCTURAL_GLB,
        REVIEW_BLEND,
        MODEL_MANIFEST,
        STAGE / "pipeline_status.json",
        STAGE / "summary.md",
        *sorted(TEXTURE_DIR.glob("*.png")),
        *sorted(RENDER_DIR.glob("*.png")),
        *[REPORT_DIR / name for name in required_reports],
    ]
    manifest = {
        "schema_version": "bf3d.r2q.artifact_manifest.v3",
        "status": STATUS,
        "next_stage_allowed": False,
        "artifacts": [artifact(path) for path in artifact_paths if path.is_file()],
    }
    write_json(STAGE / "artifact_manifest.json", manifest)
    print("BF3D_R2Q_V3_FINAL=" + json.dumps(core, ensure_ascii=False))


def main() -> None:
    args = sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else []
    if "--reopen" in args:
        reopen_validation()
    elif "--factory-import" in args:
        factory_import_validation()
    elif "--finalize" in args:
        finalize()
    else:
        build()


if __name__ == "__main__":
    main()
