#!/usr/bin/env python3
r"""Generate the frozen WEB-60 R2T Blender 5.2 OCIO GPU assets.

Requirement:
    REQ-BF3D-R2T-OCIO-PHOTOMETRIC-EQUIVALENCE-20260720

Inputs:
    The byte-locked Blender 5.2 OCIO config and its two referenced cube files,
    plus the byte-locked Three.js r160 source used for the static negative fact.

Outputs:
    An exact GLSL ES 3.0 OCIO shader function, RGB32F and RGBA32F payloads for
    both OCIO 3D textures, and a deterministic machine-readable manifest.

Errors:
    The command fails closed if any source identity, PyOpenColorIO version,
    processor cache ID, CPU oracle, shader identity, or LUT identity differs
    from the frozen contract.

Run with:
    "D:\Program Files\Blender Foundation\Blender 5.2\5.2\python\bin\python.exe" ^
      tools\generate_bf3d_r2t_ocio_assets.py
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import sys
from typing import Any, Iterable


REQUIREMENT_ID = "REQ-BF3D-R2T-OCIO-PHOTOMETRIC-EQUIVALENCE-20260720"
SCHEMA_VERSION = "bf3d.r2t.ocio_assets.v1"

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT_DIR = (
    REPO_ROOT
    / "PT"
    / "高炉3D模型"
    / "work"
    / "WEB_60_20260720_R2T_OCIO_PHOTOMETRIC_EQUIVALENCE"
    / "generated"
)
BLENDER_COLOR_ROOT = Path(
    r"D:\Program Files\Blender Foundation\Blender 5.2\5.2\datafiles\colormanagement"
)

SOURCE_SPECS = (
    {
        "id": "blender52_ocio_config",
        "path": BLENDER_COLOR_ROOT / "config.ocio",
        "manifest_path": (
            "D:/Program Files/Blender Foundation/Blender 5.2/5.2/"
            "datafiles/colormanagement/config.ocio"
        ),
        "bytes": 68_593,
        "sha256": "df5714c85d5afb5e9762281503a0c48a9f65dadb22d32a3aee50c454a0821f62",
    },
    {
        "id": "blender52_luminance_compensation_bt2020_cube",
        "path": BLENDER_COLOR_ROOT
        / "luts"
        / "luminance_compensation_bt2020.cube",
        "manifest_path": (
            "D:/Program Files/Blender Foundation/Blender 5.2/5.2/"
            "datafiles/colormanagement/luts/luminance_compensation_bt2020.cube"
        ),
        "bytes": 1_570_615,
        "sha256": "3ec0a2dbae1e48aa6889e2b17df4009b6aca430051dae1721c64fdc6699de884",
    },
    {
        "id": "blender52_agx_base_srgb_cube",
        "path": BLENDER_COLOR_ROOT / "luts" / "AgX_Base_sRGB.cube",
        "manifest_path": (
            "D:/Program Files/Blender Foundation/Blender 5.2/5.2/"
            "datafiles/colormanagement/luts/AgX_Base_sRGB.cube"
        ),
        "bytes": 2_901_408,
        "sha256": "02f4d185608daa67fda01a1a48529bbc1533c8afdc826cde5c78f2eb5bb1b839",
    },
    {
        "id": "three_r160_module",
        "path": REPO_ROOT / "高炉前端数据" / "libs" / "three" / "three.module.js",
        "manifest_path": "高炉前端数据/libs/three/three.module.js",
        "bytes": 1_272_972,
        "sha256": "76dea8151bc9352aef3528b4262e249b2604f62543828328db978d060d61a495",
    },
)

PYOCIO_VERSION = "2.5.0"
PROCESSOR_CACHE_ID = "cb6dc6defbf01d33b84718a55c277f0a"

INPUT_COLOR_SPACE = "Linear Rec.709"
DISPLAY = "sRGB"
VIEW = "AgX"
LOOK = "AgX - Medium Low Contrast"
EXPOSURE_EV = 0.0

SHADER_FILE = "Blender52_AgX_MediumLow_sRGB.glsl"
SHADER_FUNCTION = "Blender52_AgX_MediumLow_sRGB"
SHADER_PIXEL_NAME = "outColor"
SHADER_RESOURCE_PREFIX = "ocio_"
SHADER_BYTES = 14_155
SHADER_SHA256 = "8e90dd5173fd5ef78735b584f7b4d40e464e88f71b12a94c08a062522f3494ac"

TEXTURE_SPECS = (
    {
        "index": 0,
        "texture_name": "ocio_lut3d_0",
        "sampler_name": "ocio_lut3d_0Sampler",
        "edge_length": 37,
        "rgb_file": "ocio_lut3d_0_37_rgb32f_le.bin",
        "rgba_file": "ocio_lut3d_0_37_rgba32f_le.bin",
        "rgb_float_count": 151_959,
        "rgb_bytes": 607_836,
        "rgb_sha256": "9174984646340cb89db8af731b1fb17e1d04ab05ad38d9a10b2ebbfba1fce8ed",
    },
    {
        "index": 1,
        "texture_name": "ocio_lut3d_1",
        "sampler_name": "ocio_lut3d_1Sampler",
        "edge_length": 57,
        "rgb_file": "ocio_lut3d_1_57_rgb32f_le.bin",
        "rgba_file": "ocio_lut3d_1_57_rgba32f_le.bin",
        "rgb_float_count": 555_579,
        "rgb_bytes": 2_222_316,
        "rgb_sha256": "cb92475f7c9feb46b589847f26c9ce068c89f1d0a2f7a88aecd0857b42c7fe5f",
    },
)

CPU_ORACLE_ATOL = 5e-7
CPU_ORACLES = (
    {
        "id": "black",
        "input": [0.0, 0.0, 0.0],
        "expected": [0.000238591, 0.000238585, 0.000238734],
    },
    {
        "id": "gray_18_percent",
        "input": [0.18, 0.18, 0.18],
        "expected": [0.461316407, 0.461314797, 0.461351335],
    },
    {
        "id": "white_1",
        "input": [1.0, 1.0, 1.0],
        "expected": [0.746896923, 0.746895909, 0.746919751],
    },
    {
        "id": "gray_4",
        "input": [4.0, 4.0, 4.0],
        "expected": [0.887917399, 0.887916625, 0.887931526],
    },
    {
        "id": "red_18_percent",
        "input": [0.18, 0.0, 0.0],
        "expected": [0.457238734, 0.024740530, 0.0],
    },
    {
        "id": "green_18_percent",
        "input": [0.0, 0.18, 0.0],
        "expected": [0.106957830, 0.440579742, 0.001707785],
    },
    {
        "id": "blue_18_percent",
        "input": [0.0, 0.0, 0.18],
        "expected": [0.0, 0.148732483, 0.466190100],
    },
    {
        "id": "hdr_8_2_point5",
        "input": [8.0, 2.0, 0.5],
        "expected": [0.973748267, 0.820390582, 0.750006497],
    },
)


class GenerationError(RuntimeError):
    """Raised when a frozen R2T generation invariant does not hold."""


def sha256_bytes(payload: bytes) -> str:
    """Return the lowercase SHA-256 digest for an in-memory payload."""

    return hashlib.sha256(payload).hexdigest()


def read_locked_source(spec: dict[str, Any]) -> bytes:
    """Read one source and enforce its frozen byte count and SHA-256."""

    path = Path(spec["path"])
    try:
        payload = path.read_bytes()
    except OSError as exc:
        raise GenerationError(f"Cannot read locked source {path}: {exc}") from exc
    actual_size = len(payload)
    actual_sha = sha256_bytes(payload)
    if actual_size != spec["bytes"] or actual_sha != spec["sha256"]:
        raise GenerationError(
            "Locked source identity mismatch for "
            f"{path}: bytes={actual_size} sha256={actual_sha}; "
            f"expected bytes={spec['bytes']} sha256={spec['sha256']}"
        )
    return payload


def import_runtime_modules() -> tuple[Any, Any]:
    """Import and validate the Blender-bundled OCIO and NumPy runtimes."""

    try:
        import PyOpenColorIO as ocio  # type: ignore[import-not-found]
    except ImportError as exc:
        raise GenerationError(
            "PyOpenColorIO is unavailable. Run this script with Blender 5.2's "
            r"python: D:\Program Files\Blender Foundation\Blender 5.2\5.2"
            r"\python\bin\python.exe"
        ) from exc
    try:
        import numpy as np
    except ImportError as exc:
        raise GenerationError(
            "NumPy is required to construct the bit-preserving RGBA32F payloads."
        ) from exc
    if ocio.__version__ != PYOCIO_VERSION:
        raise GenerationError(
            f"PyOpenColorIO version mismatch: {ocio.__version__}; "
            f"expected {PYOCIO_VERSION}"
        )
    if sys.byteorder != "little":
        raise GenerationError(
            "The frozen payload contract is IEEE-754 float32 little-endian."
        )
    return ocio, np


def build_processor(ocio: Any, config_path: Path) -> tuple[Any, Any]:
    """Build the exact Blender display/view/look processor and CPU processor."""

    config = ocio.Config.CreateFromFile(str(config_path))
    display_view = ocio.DisplayViewTransform(
        src=INPUT_COLOR_SPACE,
        display=DISPLAY,
        view=VIEW,
    )
    pipeline = ocio.LegacyViewingPipeline()
    pipeline.setDisplayViewTransform(display_view)
    pipeline.setLooksOverride(LOOK)
    pipeline.setLooksOverrideEnabled(True)
    processor = pipeline.getProcessor(config)
    actual_cache = processor.getCacheID()
    if actual_cache != PROCESSOR_CACHE_ID:
        raise GenerationError(
            f"Processor cache mismatch: {actual_cache}; "
            f"expected {PROCESSOR_CACHE_ID}"
        )
    return processor, processor.getDefaultCPUProcessor()


def evaluate_cpu_oracles(cpu_processor: Any) -> list[dict[str, Any]]:
    """Evaluate all frozen float32 CPU oracle points."""

    results: list[dict[str, Any]] = []
    for oracle in CPU_ORACLES:
        actual = [float(value) for value in cpu_processor.applyRGB(oracle["input"])]
        errors = [
            abs(actual[channel] - oracle["expected"][channel])
            for channel in range(3)
        ]
        max_abs_error = max(errors)
        if max_abs_error > CPU_ORACLE_ATOL:
            raise GenerationError(
                f"CPU oracle {oracle['id']} failed: actual={actual}, "
                f"expected={oracle['expected']}, max_abs_error={max_abs_error}"
            )
        results.append(
            {
                "id": oracle["id"],
                "input_scene_linear_rgb": oracle["input"],
                "expected_display_encoded_srgb": oracle["expected"],
                "actual_float32": actual,
                "max_abs_error": max_abs_error,
                "pass": True,
            }
        )
    return results


def extract_shader_and_textures(
    ocio: Any,
    processor: Any,
) -> tuple[bytes, str, list[Any]]:
    """Extract the exact GLSL ES 3.0 code and ordered OCIO 3D textures."""

    shader_desc = ocio.GpuShaderDesc.CreateShaderDesc()
    shader_desc.setLanguage(ocio.GPU_LANGUAGE_GLSL_ES_3_0)
    shader_desc.setFunctionName(SHADER_FUNCTION)
    shader_desc.setResourcePrefix(SHADER_RESOURCE_PREFIX)
    processor.getDefaultGPUProcessor().extractGpuShaderInfo(shader_desc)

    if shader_desc.getPixelName() != SHADER_PIXEL_NAME:
        raise GenerationError(
            f"Unexpected OCIO pixel name: {shader_desc.getPixelName()}"
        )
    shader = shader_desc.getShaderText().encode("utf-8")
    shader_sha = sha256_bytes(shader)
    if len(shader) != SHADER_BYTES or shader_sha != SHADER_SHA256:
        raise GenerationError(
            f"GLSL identity mismatch: bytes={len(shader)} sha256={shader_sha}; "
            f"expected bytes={SHADER_BYTES} sha256={SHADER_SHA256}"
        )

    textures_2d = list(shader_desc.getTextures())
    textures_3d = list(shader_desc.get3DTextures())
    if textures_2d:
        raise GenerationError(
            f"Unexpected OCIO 1D/2D textures: {len(textures_2d)}"
        )
    if len(textures_3d) != len(TEXTURE_SPECS):
        raise GenerationError(
            f"Unexpected OCIO 3D texture count: {len(textures_3d)}"
        )
    return shader, shader_desc.getCacheID(), textures_3d


def validate_static_three_fact(three_source: bytes) -> dict[str, Any]:
    """Validate only the frozen static reason Three r160 AgX is not equivalent."""

    text = three_source.decode("utf-8")
    required_tokens = (
        "const AgXToneMapping = 6;",
        "vec3 agxDefaultContrastApprox( vec3 x )",
        "color = agxDefaultContrastApprox( color );",
    )
    missing = [token for token in required_tokens if token not in text]
    if missing:
        raise GenerationError(
            "Three.js r160 static AgX evidence is missing: " + repr(missing)
        )
    if LOOK in text:
        raise GenerationError(
            "The frozen Three.js source unexpectedly contains the Blender "
            "Medium Low look name; review the static negative fact."
        )
    return {
        "kind": "static_negative_fact_only",
        "source_id": "three_r160_module",
        "native_agx_enum_available": True,
        "native_curve": "agxDefaultContrastApprox",
        "blender_look": LOOK,
        "blender_medium_low_implemented_by_native_three_agx": False,
        "numeric_equivalence_claimed": False,
        "fact": (
            "Three.js r160 built-in AgXToneMapping calls "
            "agxDefaultContrastApprox and does not implement Blender's "
            "AgX - Medium Low Contrast look; it is not an equivalent substitute."
        ),
    }


def _rgb_buffer_bytes(texture: Any) -> bytes:
    """Return the OCIO float32 texture buffer without reordering."""

    values = texture.getValues()
    view = memoryview(values)
    if view.itemsize != 4 or view.format not in {"f", "<f", "=f", "@f"}:
        raise GenerationError(
            "OCIO returned an unexpected texture buffer format: "
            f"format={view.format!r} itemsize={view.itemsize}"
        )
    if not view.c_contiguous:
        raise GenerationError("OCIO returned a non-contiguous texture buffer.")
    return view.cast("B").tobytes()


def _rgba_from_rgb(np: Any, rgb_payload: bytes) -> bytes:
    """Expand RGB32F to RGBA32F while preserving every RGB float bit."""

    rgb_u32 = np.frombuffer(rgb_payload, dtype="<u4")
    if rgb_u32.size % 3:
        raise GenerationError("RGB payload float count is not divisible by three.")
    rgb_u32 = rgb_u32.reshape((-1, 3))
    rgba_u32 = np.empty((rgb_u32.shape[0], 4), dtype="<u4")
    rgba_u32[:, :3] = rgb_u32
    rgba_u32[:, 3] = np.uint32(0x3F800000)
    return rgba_u32.tobytes(order="C")


def build_texture_artifacts(
    ocio: Any,
    np: Any,
    textures: Iterable[Any],
) -> tuple[list[dict[str, Any]], dict[str, bytes]]:
    """Validate and package both ordered OCIO textures."""

    manifest_entries: list[dict[str, Any]] = []
    files: dict[str, bytes] = {}
    for spec, texture in zip(TEXTURE_SPECS, textures, strict=True):
        if texture.textureName != spec["texture_name"]:
            raise GenerationError(
                f"Texture {spec['index']} name mismatch: {texture.textureName}"
            )
        if texture.samplerName != spec["sampler_name"]:
            raise GenerationError(
                f"Texture {spec['index']} sampler mismatch: {texture.samplerName}"
            )
        if texture.edgeLen != spec["edge_length"]:
            raise GenerationError(
                f"Texture {spec['index']} edge mismatch: {texture.edgeLen}"
            )
        if texture.interpolation != ocio.INTERP_NEAREST:
            raise GenerationError(
                f"Texture {spec['index']} interpolation is not NEAREST: "
                f"{texture.interpolation}"
            )

        rgb_payload = _rgb_buffer_bytes(texture)
        rgb_sha = sha256_bytes(rgb_payload)
        if (
            len(rgb_payload) != spec["rgb_bytes"]
            or len(rgb_payload) // 4 != spec["rgb_float_count"]
            or rgb_sha != spec["rgb_sha256"]
        ):
            raise GenerationError(
                f"Texture {spec['index']} RGB payload mismatch: "
                f"floats={len(rgb_payload) // 4} bytes={len(rgb_payload)} "
                f"sha256={rgb_sha}"
            )
        rgba_payload = _rgba_from_rgb(np, rgb_payload)
        texel_count = spec["edge_length"] ** 3
        if len(rgba_payload) != texel_count * 4 * 4:
            raise GenerationError(
                f"Texture {spec['index']} RGBA byte count is invalid."
            )

        files[spec["rgb_file"]] = rgb_payload
        files[spec["rgba_file"]] = rgba_payload
        manifest_entries.append(
            {
                "ocio_order_index": spec["index"],
                "texture_name": spec["texture_name"],
                "sampler_name": spec["sampler_name"],
                "edge_length": spec["edge_length"],
                "texel_count": texel_count,
                "interpolation": "NEAREST",
                "wrap_s": "CLAMP_TO_EDGE",
                "wrap_t": "CLAMP_TO_EDGE",
                "wrap_r": "CLAMP_TO_EDGE",
                "mipmaps": False,
                "ordering": (
                    "Exact PyOpenColorIO Texture3D.getValues() flat RGB order; "
                    "no axis, texel, or channel reordering."
                ),
                "rgb32f": {
                    "file": spec["rgb_file"],
                    "component_type": "IEEE-754 float32",
                    "byte_order": "little",
                    "channels": "RGB",
                    "float_count": spec["rgb_float_count"],
                    "bytes": len(rgb_payload),
                    "sha256": rgb_sha,
                },
                "rgba32f": {
                    "file": spec["rgba_file"],
                    "component_type": "IEEE-754 float32",
                    "byte_order": "little",
                    "channels": "RGBA",
                    "alpha": 1.0,
                    "float_count": len(rgba_payload) // 4,
                    "bytes": len(rgba_payload),
                    "sha256": sha256_bytes(rgba_payload),
                    "conversion": (
                        "For every OCIO RGB texel, copy R/G/B float32 bits in "
                        "place and append float32 alpha 1.0."
                    ),
                },
            }
        )
    return manifest_entries, files


def build_manifest(
    ocio: Any,
    np: Any,
    shader_cache_id: str,
    texture_entries: list[dict[str, Any]],
    oracle_results: list[dict[str, Any]],
    three_fact: dict[str, Any],
) -> dict[str, Any]:
    """Construct the deterministic machine-readable asset contract."""

    source_entries = [
        {
            "id": spec["id"],
            "path": spec["manifest_path"],
            "bytes": spec["bytes"],
            "sha256": spec["sha256"],
        }
        for spec in SOURCE_SPECS
    ]
    return {
        "schema_version": SCHEMA_VERSION,
        "requirement_id": REQUIREMENT_ID,
        "stage_id": "WEB-60_R2T",
        "asset_status": "generated_exact_unapproved_license_pending",
        "capture_eligible": False,
        "license_pending": True,
        "redistribution_approved": False,
        "sources": source_entries,
        "runtime": {
            "python_implementation": sys.implementation.name,
            "python_version": ".".join(str(part) for part in sys.version_info[:3]),
            "pyopencolorio_version": ocio.__version__,
            "numpy_version": np.__version__,
            "byte_order": sys.byteorder,
        },
        "transform": {
            "input_color_space": INPUT_COLOR_SPACE,
            "input_encoding": "scene-linear",
            "input_is_scene_linear": True,
            "display": DISPLAY,
            "view": VIEW,
            "look": LOOK,
            "exposure_ev": EXPOSURE_EV,
            "direction": "FORWARD",
            "output_color_space": "sRGB",
            "output_encoding": "display-encoded sRGB",
            "output_is_display_encoded": True,
            "processor_cache_id": PROCESSOR_CACHE_ID,
        },
        "shader": {
            "file": SHADER_FILE,
            "artifact_kind": (
                "PyOpenColorIO GLSL ES 3.0 shader declarations and function; "
                "the host supplies the complete RawShaderMaterial program."
            ),
            "language": "GPU_LANGUAGE_GLSL_ES_3_0",
            "function_name": SHADER_FUNCTION,
            "pixel_name": SHADER_PIXEL_NAME,
            "resource_prefix": SHADER_RESOURCE_PREFIX,
            "shader_desc_cache_id": shader_cache_id,
            "bytes": SHADER_BYTES,
            "sha256": SHADER_SHA256,
            "samplers_in_ocio_order": [
                spec["sampler_name"] for spec in TEXTURE_SPECS
            ],
        },
        "textures": texture_entries,
        "threejs_integration_contract": {
            "material": "THREE.RawShaderMaterial",
            "renderer_tone_mapping": "THREE.NoToneMapping",
            "input_to_shader": "scene-linear Linear Rec.709 RGB",
            "shader_output": "display-encoded sRGB RGB",
            "post_shader_oetf": "FORBIDDEN",
            "second_srgb_oetf_allowed": False,
            "double_oetf_allowed": False,
            "texture_type": "THREE.FloatType",
            "texture_format": "THREE.RGBAFormat",
            "texture_internal_format": "RGBA32F",
            "texture_color_space": "THREE.NoColorSpace",
            "texture_min_filter": "THREE.NearestFilter",
            "texture_mag_filter": "THREE.NearestFilter",
            "texture_wrap_s": "THREE.ClampToEdgeWrapping",
            "texture_wrap_t": "THREE.ClampToEdgeWrapping",
            "texture_wrap_r": "THREE.ClampToEdgeWrapping",
            "texture_generate_mipmaps": False,
        },
        "cpu_oracle": {
            "numeric_type": "float32",
            "absolute_tolerance": CPU_ORACLE_ATOL,
            "points": oracle_results,
        },
        "three_builtin_agx_non_equivalence": three_fact,
        "guardrails": {
            "production_runtime_mutation_authorized": False,
            "cross_renderer_equivalence_claimed": False,
            "three_builtin_agx_substitution_allowed": False,
            "license_review_required_before_redistribution": True,
        },
        "verification": {
            "script": "tools/verify_bf3d_r2t_ocio_assets.py",
            "required_checks": [
                "source bytes and SHA-256",
                "PyOpenColorIO version and processor cache ID",
                "exact GLSL bytes, SHA-256, function, and samplers",
                "exact ordered RGB32F OCIO payloads",
                "full bitwise RGB32F to RGBA32F expansion and alpha 1.0",
                "manifest semantic contract",
                "all float32 CPU oracle points",
                "Three.js r160 static built-in AgX negative fact",
            ],
        },
    }


def atomic_write(path: Path, payload: bytes) -> None:
    """Atomically replace one generated artifact."""

    temporary = path.with_name(path.name + ".tmp")
    try:
        temporary.write_bytes(payload)
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()


def parse_args() -> argparse.Namespace:
    """Parse the output directory option."""

    parser = argparse.ArgumentParser(
        description=(
            "Generate the byte-locked Blender 5.2 AgX Medium Low OCIO "
            "GLSL ES3 and RGB/RGBA LUT payloads for WEB-60 R2T."
        ),
        epilog=(
            "The source identities are fixed in the script and cannot be "
            "overridden. The command fails if they do not match."
        ),
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=DEFAULT_OUTPUT_DIR,
        help=f"Generated asset directory (default: {DEFAULT_OUTPUT_DIR})",
    )
    return parser.parse_args()


def main() -> int:
    """Generate all artifacts after validating every frozen invariant."""

    args = parse_args()
    try:
        source_payloads = {
            spec["id"]: read_locked_source(spec) for spec in SOURCE_SPECS
        }
        ocio, np = import_runtime_modules()
        processor, cpu_processor = build_processor(
            ocio,
            Path(SOURCE_SPECS[0]["path"]),
        )
        oracle_results = evaluate_cpu_oracles(cpu_processor)
        shader, shader_cache_id, textures = extract_shader_and_textures(
            ocio,
            processor,
        )
        texture_entries, artifact_payloads = build_texture_artifacts(
            ocio,
            np,
            textures,
        )
        three_fact = validate_static_three_fact(
            source_payloads["three_r160_module"]
        )
        manifest = build_manifest(
            ocio,
            np,
            shader_cache_id,
            texture_entries,
            oracle_results,
            three_fact,
        )
        manifest_payload = (
            json.dumps(
                manifest,
                ensure_ascii=False,
                indent=2,
                sort_keys=True,
            )
            + "\n"
        ).encode("utf-8")

        output_dir = args.output_dir.resolve()
        output_dir.mkdir(parents=True, exist_ok=True)
        artifact_payloads[SHADER_FILE] = shader
        for filename, payload in artifact_payloads.items():
            atomic_write(output_dir / filename, payload)
        manifest_file = output_dir / "ocio_assets_manifest.json"
        atomic_write(manifest_file, manifest_payload)

        summary = {
            "ok": True,
            "requirement_id": REQUIREMENT_ID,
            "output_dir": str(output_dir),
            "processor_cache_id": PROCESSOR_CACHE_ID,
            "shader": {
                "file": SHADER_FILE,
                "bytes": len(shader),
                "sha256": sha256_bytes(shader),
            },
            "textures": texture_entries,
            "manifest": {
                "file": manifest_file.name,
                "bytes": len(manifest_payload),
                "sha256": sha256_bytes(manifest_payload),
            },
        }
        print(json.dumps(summary, ensure_ascii=False, indent=2))
        return 0
    except (GenerationError, OSError, ValueError) as exc:
        print(
            json.dumps(
                {
                    "ok": False,
                    "requirement_id": REQUIREMENT_ID,
                    "error": str(exc),
                },
                ensure_ascii=False,
                indent=2,
            ),
            file=sys.stderr,
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
