#!/usr/bin/env python3
r"""Independently verify the frozen WEB-60 R2T OCIO asset set.

Requirement:
    REQ-BF3D-R2T-OCIO-PHOTOMETRIC-EQUIVALENCE-20260720

This verifier deliberately does not import the generator. It independently
rebuilds the PyOpenColorIO 2.5 processor and GPU shader, checks every source
and artifact byte/SHA, bit-compares every RGB component in both RGBA payloads,
checks every alpha bit, validates the manifest/runtime contract, and evaluates
all frozen CPU float32 oracle points.

Run with:
    "D:\Program Files\Blender Foundation\Blender 5.2\5.2\python\bin\python.exe" ^
      tools\verify_bf3d_r2t_ocio_assets.py
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys
from typing import Any


REQUIREMENT_ID = "REQ-BF3D-R2T-OCIO-PHOTOMETRIC-EQUIVALENCE-20260720"
SCHEMA_VERSION = "bf3d.r2t.ocio_assets.v1"

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_ASSET_DIR = (
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

SHADER_FILE = "Blender52_AgX_MediumLow_sRGB.glsl"
SHADER_FUNCTION = "Blender52_AgX_MediumLow_sRGB"
SHADER_PIXEL_NAME = "outColor"
SHADER_RESOURCE_PREFIX = "ocio_"
SHADER_BYTES = 14_155
SHADER_SHA256 = "8e90dd5173fd5ef78735b584f7b4d40e464e88f71b12a94c08a062522f3494ac"
MANIFEST_FILE = "ocio_assets_manifest.json"

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
    ("black", [0.0, 0.0, 0.0], [0.000238591, 0.000238585, 0.000238734]),
    (
        "gray_18_percent",
        [0.18, 0.18, 0.18],
        [0.461316407, 0.461314797, 0.461351335],
    ),
    (
        "white_1",
        [1.0, 1.0, 1.0],
        [0.746896923, 0.746895909, 0.746919751],
    ),
    (
        "gray_4",
        [4.0, 4.0, 4.0],
        [0.887917399, 0.887916625, 0.887931526],
    ),
    (
        "red_18_percent",
        [0.18, 0.0, 0.0],
        [0.457238734, 0.024740530, 0.0],
    ),
    (
        "green_18_percent",
        [0.0, 0.18, 0.0],
        [0.106957830, 0.440579742, 0.001707785],
    ),
    (
        "blue_18_percent",
        [0.0, 0.0, 0.18],
        [0.0, 0.148732483, 0.466190100],
    ),
    (
        "hdr_8_2_point5",
        [8.0, 2.0, 0.5],
        [0.973748267, 0.820390582, 0.750006497],
    ),
)

EXPECTED_FILENAMES = {
    SHADER_FILE,
    MANIFEST_FILE,
    *(spec["rgb_file"] for spec in TEXTURE_SPECS),
    *(spec["rgba_file"] for spec in TEXTURE_SPECS),
}


class VerificationError(RuntimeError):
    """Raised when an independently recomputed invariant does not hold."""


def require(condition: bool, message: str) -> None:
    """Raise a verification error unless *condition* is true."""

    if not condition:
        raise VerificationError(message)


def sha256_bytes(payload: bytes) -> str:
    """Return the lowercase SHA-256 digest for a payload."""

    return hashlib.sha256(payload).hexdigest()


def read_exact_file(path: Path, expected_bytes: int, expected_sha: str) -> bytes:
    """Read a file and independently verify its byte count and SHA-256."""

    try:
        payload = path.read_bytes()
    except OSError as exc:
        raise VerificationError(f"Cannot read {path}: {exc}") from exc
    actual_sha = sha256_bytes(payload)
    require(
        len(payload) == expected_bytes,
        f"{path} byte count {len(payload)} != {expected_bytes}",
    )
    require(
        actual_sha == expected_sha,
        f"{path} SHA-256 {actual_sha} != {expected_sha}",
    )
    return payload


def import_runtime_modules() -> tuple[Any, Any]:
    """Import the independent verification runtime."""

    try:
        import PyOpenColorIO as ocio  # type: ignore[import-not-found]
    except ImportError as exc:
        raise VerificationError(
            "PyOpenColorIO is unavailable; use Blender 5.2's python.exe."
        ) from exc
    try:
        import numpy as np
    except ImportError as exc:
        raise VerificationError("NumPy is required for bitwise LUT checks.") from exc
    require(
        ocio.__version__ == PYOCIO_VERSION,
        f"PyOpenColorIO {ocio.__version__} != {PYOCIO_VERSION}",
    )
    require(
        sys.byteorder == "little",
        "The frozen payload contract requires little-endian float32.",
    )
    return ocio, np


def verify_sources() -> dict[str, bytes]:
    """Verify all four frozen source identities."""

    payloads: dict[str, bytes] = {}
    for spec in SOURCE_SPECS:
        payloads[spec["id"]] = read_exact_file(
            Path(spec["path"]),
            spec["bytes"],
            spec["sha256"],
        )
    return payloads


def rebuild_processor_and_shader(ocio: Any) -> tuple[Any, Any, bytes, str, list[Any]]:
    """Independently rebuild the exact processor and GLSL descriptor."""

    config = ocio.Config.CreateFromFile(str(SOURCE_SPECS[0]["path"]))
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
    require(
        processor.getCacheID() == PROCESSOR_CACHE_ID,
        "Independent processor cache ID mismatch: "
        f"{processor.getCacheID()} != {PROCESSOR_CACHE_ID}",
    )

    shader_desc = ocio.GpuShaderDesc.CreateShaderDesc()
    shader_desc.setLanguage(ocio.GPU_LANGUAGE_GLSL_ES_3_0)
    shader_desc.setFunctionName(SHADER_FUNCTION)
    shader_desc.setResourcePrefix(SHADER_RESOURCE_PREFIX)
    processor.getDefaultGPUProcessor().extractGpuShaderInfo(shader_desc)
    shader = shader_desc.getShaderText().encode("utf-8")
    require(len(shader) == SHADER_BYTES, "Rebuilt GLSL byte count mismatch.")
    require(
        sha256_bytes(shader) == SHADER_SHA256,
        "Rebuilt GLSL SHA-256 mismatch.",
    )
    require(
        shader_desc.getPixelName() == SHADER_PIXEL_NAME,
        "Rebuilt shader pixel identifier mismatch.",
    )
    require(
        not list(shader_desc.getTextures()),
        "Rebuilt processor unexpectedly has a 1D/2D texture.",
    )
    textures = list(shader_desc.get3DTextures())
    require(
        len(textures) == len(TEXTURE_SPECS),
        "Rebuilt processor does not have exactly two 3D textures.",
    )
    return (
        processor,
        processor.getDefaultCPUProcessor(),
        shader,
        shader_desc.getCacheID(),
        textures,
    )


def verify_shader_file(asset_dir: Path, rebuilt_shader: bytes) -> dict[str, Any]:
    """Verify the stored GLSL byte identity and required declarations."""

    stored = read_exact_file(
        asset_dir / SHADER_FILE,
        SHADER_BYTES,
        SHADER_SHA256,
    )
    require(stored == rebuilt_shader, "Stored GLSL differs from rebuilt OCIO GLSL.")
    text = stored.decode("utf-8")
    require(
        f"vec4 {SHADER_FUNCTION}(vec4 inPixel)" in text,
        "GLSL function signature is missing.",
    )
    require(
        "texture3D(" not in text and "texture(" in text,
        "GLSL does not use the expected ES 3 texture() form.",
    )
    for spec in TEXTURE_SPECS:
        declaration = f"uniform sampler3D {spec['sampler_name']};"
        require(declaration in text, f"Missing GLSL sampler: {declaration}")
        require(
            f"texture({spec['sampler_name']}," in text,
            f"GLSL does not sample {spec['sampler_name']}.",
        )
    return {
        "bytes": len(stored),
        "sha256": sha256_bytes(stored),
        "function": SHADER_FUNCTION,
        "samplers": [spec["sampler_name"] for spec in TEXTURE_SPECS],
    }


def ocio_rgb_bytes(texture: Any) -> bytes:
    """Read the independent OCIO texture buffer exactly as exposed."""

    view = memoryview(texture.getValues())
    require(
        view.itemsize == 4 and view.format in {"f", "<f", "=f", "@f"},
        f"Unexpected OCIO buffer format {view.format!r}/{view.itemsize}.",
    )
    require(view.c_contiguous, "OCIO texture buffer is not C-contiguous.")
    return view.cast("B").tobytes()


def expected_rgba_bytes(np: Any, rgb_payload: bytes) -> bytes:
    """Independently derive exact RGBA bits from an OCIO RGB payload."""

    rgb_bits = np.frombuffer(rgb_payload, dtype="<u4")
    require(rgb_bits.size % 3 == 0, "RGB float count is not divisible by three.")
    rgb_bits = rgb_bits.reshape((-1, 3))
    rgba_bits = np.empty((rgb_bits.shape[0], 4), dtype="<u4")
    rgba_bits[:, :3] = rgb_bits
    rgba_bits[:, 3] = np.uint32(0x3F800000)
    return rgba_bits.tobytes(order="C")


def verify_texture_files(
    ocio: Any,
    np: Any,
    asset_dir: Path,
    textures: list[Any],
) -> list[dict[str, Any]]:
    """Bit-verify both RGB and RGBA payloads in full OCIO order."""

    reports: list[dict[str, Any]] = []
    for spec, texture in zip(TEXTURE_SPECS, textures, strict=True):
        require(
            texture.textureName == spec["texture_name"],
            f"Texture {spec['index']} OCIO name mismatch.",
        )
        require(
            texture.samplerName == spec["sampler_name"],
            f"Texture {spec['index']} OCIO sampler mismatch.",
        )
        require(
            texture.edgeLen == spec["edge_length"],
            f"Texture {spec['index']} OCIO edge length mismatch.",
        )
        require(
            texture.interpolation == ocio.INTERP_NEAREST,
            f"Texture {spec['index']} OCIO interpolation is not NEAREST.",
        )

        rebuilt_rgb = ocio_rgb_bytes(texture)
        require(
            len(rebuilt_rgb) == spec["rgb_bytes"],
            f"Texture {spec['index']} rebuilt RGB byte count mismatch.",
        )
        require(
            len(rebuilt_rgb) // 4 == spec["rgb_float_count"],
            f"Texture {spec['index']} rebuilt RGB float count mismatch.",
        )
        require(
            sha256_bytes(rebuilt_rgb) == spec["rgb_sha256"],
            f"Texture {spec['index']} rebuilt RGB SHA-256 mismatch.",
        )
        stored_rgb = read_exact_file(
            asset_dir / spec["rgb_file"],
            spec["rgb_bytes"],
            spec["rgb_sha256"],
        )
        require(
            stored_rgb == rebuilt_rgb,
            f"Texture {spec['index']} stored RGB differs from OCIO.",
        )

        rebuilt_rgba = expected_rgba_bytes(np, rebuilt_rgb)
        rgba_path = asset_dir / spec["rgba_file"]
        try:
            stored_rgba = rgba_path.read_bytes()
        except OSError as exc:
            raise VerificationError(f"Cannot read {rgba_path}: {exc}") from exc
        require(
            stored_rgba == rebuilt_rgba,
            f"Texture {spec['index']} RGBA payload differs from exact expansion.",
        )

        rgb_bits = np.frombuffer(stored_rgb, dtype="<u4").reshape((-1, 3))
        rgba_bits = np.frombuffer(stored_rgba, dtype="<u4").reshape((-1, 4))
        require(
            np.array_equal(rgba_bits[:, :3], rgb_bits),
            f"Texture {spec['index']} has reordered or changed RGB float bits.",
        )
        require(
            bool(np.all(rgba_bits[:, 3] == np.uint32(0x3F800000))),
            f"Texture {spec['index']} does not have alpha=1 for every texel.",
        )
        reports.append(
            {
                "index": spec["index"],
                "texture_name": spec["texture_name"],
                "sampler_name": spec["sampler_name"],
                "edge_length": spec["edge_length"],
                "texels_bit_checked": int(rgba_bits.shape[0]),
                "rgb": {
                    "floats": len(stored_rgb) // 4,
                    "bytes": len(stored_rgb),
                    "sha256": sha256_bytes(stored_rgb),
                },
                "rgba": {
                    "floats": len(stored_rgba) // 4,
                    "bytes": len(stored_rgba),
                    "sha256": sha256_bytes(stored_rgba),
                    "all_alpha_float32_bits": "0x3f800000",
                },
            }
        )
    return reports


def verify_cpu_oracles(cpu_processor: Any) -> list[dict[str, Any]]:
    """Recompute all float32 CPU oracle points at the frozen tolerance."""

    reports: list[dict[str, Any]] = []
    for identifier, input_rgb, expected in CPU_ORACLES:
        actual = [float(value) for value in cpu_processor.applyRGB(input_rgb)]
        max_abs_error = max(
            abs(actual[channel] - expected[channel]) for channel in range(3)
        )
        require(
            max_abs_error <= CPU_ORACLE_ATOL,
            f"CPU oracle {identifier} max error {max_abs_error} "
            f"> {CPU_ORACLE_ATOL}; actual={actual}, expected={expected}",
        )
        reports.append(
            {
                "id": identifier,
                "actual_float32": actual,
                "expected": expected,
                "max_abs_error": max_abs_error,
                "pass": True,
            }
        )
    return reports


def verify_three_static_negative_fact(three_source: bytes) -> dict[str, Any]:
    """Check source tokens only; do not claim a numeric Three/Blender result."""

    text = three_source.decode("utf-8")
    tokens = (
        "const AgXToneMapping = 6;",
        "vec3 agxDefaultContrastApprox( vec3 x )",
        "color = agxDefaultContrastApprox( color );",
    )
    for token in tokens:
        require(token in text, f"Three r160 static token is missing: {token!r}")
    require(
        LOOK not in text,
        "Three r160 unexpectedly names Blender's Medium Low look.",
    )
    return {
        "method": "static_source_tokens_only",
        "native_curve": "agxDefaultContrastApprox",
        "blender_medium_low_present": False,
        "numeric_comparison_performed": False,
        "equivalence_claimed": False,
        "pass": True,
    }


def expected_manifest_sources() -> list[dict[str, Any]]:
    """Return the exact manifest-facing frozen source records."""

    return [
        {
            "id": spec["id"],
            "path": spec["manifest_path"],
            "bytes": spec["bytes"],
            "sha256": spec["sha256"],
        }
        for spec in SOURCE_SPECS
    ]


def verify_manifest(
    np: Any,
    manifest: dict[str, Any],
    shader_cache_id: str,
    texture_reports: list[dict[str, Any]],
    cpu_reports: list[dict[str, Any]],
) -> dict[str, Any]:
    """Verify the machine-readable semantic and artifact contract."""

    require(manifest.get("schema_version") == SCHEMA_VERSION, "Manifest schema mismatch.")
    require(
        manifest.get("requirement_id") == REQUIREMENT_ID,
        "Manifest requirement ID mismatch.",
    )
    require(manifest.get("stage_id") == "WEB-60_R2T", "Manifest stage mismatch.")
    require(
        manifest.get("asset_status")
        == "generated_exact_unapproved_license_pending",
        "Manifest asset status mismatch.",
    )
    require(manifest.get("license_pending") is True, "license_pending must be true.")
    require(
        manifest.get("redistribution_approved") is False,
        "redistribution_approved must be false while licensing is pending.",
    )
    require(
        manifest.get("capture_eligible") is False,
        "This generated asset set must not independently unlock capture.",
    )
    require(
        manifest.get("sources") == expected_manifest_sources(),
        "Manifest locked sources differ from the independent contract.",
    )

    runtime = manifest.get("runtime", {})
    require(
        runtime.get("pyopencolorio_version") == PYOCIO_VERSION,
        "Manifest PyOpenColorIO version mismatch.",
    )
    require(
        runtime.get("python_implementation") == sys.implementation.name
        and runtime.get("python_version")
        == ".".join(str(part) for part in sys.version_info[:3]),
        "Manifest Python runtime mismatch.",
    )
    require(
        runtime.get("numpy_version") == np.__version__,
        "Manifest NumPy runtime mismatch.",
    )
    require(runtime.get("byte_order") == "little", "Manifest byte order mismatch.")

    transform = manifest.get("transform", {})
    expected_transform = {
        "input_color_space": INPUT_COLOR_SPACE,
        "input_encoding": "scene-linear",
        "input_is_scene_linear": True,
        "display": DISPLAY,
        "view": VIEW,
        "look": LOOK,
        "exposure_ev": 0.0,
        "direction": "FORWARD",
        "output_color_space": "sRGB",
        "output_encoding": "display-encoded sRGB",
        "output_is_display_encoded": True,
        "processor_cache_id": PROCESSOR_CACHE_ID,
    }
    require(transform == expected_transform, "Manifest transform contract mismatch.")

    shader = manifest.get("shader", {})
    shader_expectations = {
        "file": SHADER_FILE,
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
    }
    for key, expected in shader_expectations.items():
        require(
            shader.get(key) == expected,
            f"Manifest shader field {key!r} mismatch.",
        )

    textures = manifest.get("textures")
    require(
        isinstance(textures, list) and len(textures) == len(TEXTURE_SPECS),
        "Manifest must contain exactly two texture records.",
    )
    for spec, report, entry in zip(
        TEXTURE_SPECS,
        texture_reports,
        textures,
        strict=True,
    ):
        exact_fields = {
            "ocio_order_index": spec["index"],
            "texture_name": spec["texture_name"],
            "sampler_name": spec["sampler_name"],
            "edge_length": spec["edge_length"],
            "texel_count": spec["edge_length"] ** 3,
            "interpolation": "NEAREST",
            "wrap_s": "CLAMP_TO_EDGE",
            "wrap_t": "CLAMP_TO_EDGE",
            "wrap_r": "CLAMP_TO_EDGE",
            "mipmaps": False,
        }
        for key, expected in exact_fields.items():
            require(
                entry.get(key) == expected,
                f"Manifest texture {spec['index']} field {key!r} mismatch.",
            )
        require(
            entry.get("ordering")
            == (
                "Exact PyOpenColorIO Texture3D.getValues() flat RGB order; "
                "no axis, texel, or channel reordering."
            ),
            f"Manifest texture {spec['index']} ordering statement mismatch.",
        )
        rgb = entry.get("rgb32f", {})
        require(rgb.get("file") == spec["rgb_file"], "Manifest RGB filename mismatch.")
        require(
            rgb.get("component_type") == "IEEE-754 float32"
            and rgb.get("byte_order") == "little"
            and rgb.get("channels") == "RGB",
            f"Manifest texture {spec['index']} RGB format mismatch.",
        )
        require(
            rgb.get("float_count") == spec["rgb_float_count"]
            and rgb.get("bytes") == spec["rgb_bytes"]
            and rgb.get("sha256") == spec["rgb_sha256"],
            f"Manifest texture {spec['index']} RGB identity mismatch.",
        )
        rgba = entry.get("rgba32f", {})
        require(
            rgba.get("file") == spec["rgba_file"],
            f"Manifest texture {spec['index']} RGBA filename mismatch.",
        )
        require(
            rgba.get("component_type") == "IEEE-754 float32"
            and rgba.get("byte_order") == "little"
            and rgba.get("channels") == "RGBA"
            and rgba.get("alpha") == 1.0,
            f"Manifest texture {spec['index']} RGBA format mismatch.",
        )
        require(
            rgba.get("float_count") == report["rgba"]["floats"]
            and rgba.get("bytes") == report["rgba"]["bytes"]
            and rgba.get("sha256") == report["rgba"]["sha256"],
            f"Manifest texture {spec['index']} RGBA identity mismatch.",
        )
        require(
            rgba.get("conversion")
            == (
                "For every OCIO RGB texel, copy R/G/B float32 bits in "
                "place and append float32 alpha 1.0."
            ),
            f"Manifest texture {spec['index']} RGBA conversion mismatch.",
        )

    integration = manifest.get("threejs_integration_contract", {})
    required_integration = {
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
    }
    for key, expected in required_integration.items():
        require(
            integration.get(key) == expected,
            f"Manifest Three.js integration field {key!r} mismatch.",
        )

    oracle = manifest.get("cpu_oracle", {})
    require(
        oracle.get("numeric_type") == "float32"
        and oracle.get("absolute_tolerance") == CPU_ORACLE_ATOL,
        "Manifest CPU oracle contract mismatch.",
    )
    points = oracle.get("points")
    require(
        isinstance(points, list) and len(points) == len(CPU_ORACLES),
        "Manifest CPU oracle point count mismatch.",
    )
    for (identifier, input_rgb, expected), point, recomputed in zip(
        CPU_ORACLES,
        points,
        cpu_reports,
        strict=True,
    ):
        require(point.get("id") == identifier, "Manifest CPU oracle ID mismatch.")
        require(
            point.get("input_scene_linear_rgb") == input_rgb,
            f"Manifest CPU oracle {identifier} input mismatch.",
        )
        require(
            point.get("expected_display_encoded_srgb") == expected,
            f"Manifest CPU oracle {identifier} expected output mismatch.",
        )
        require(point.get("pass") is True, f"Manifest CPU oracle {identifier} not PASS.")
        require(
            point.get("actual_float32") == recomputed["actual_float32"],
            f"Manifest CPU oracle {identifier} actual output mismatch.",
        )
        require(
            point.get("max_abs_error") == recomputed["max_abs_error"],
            f"Manifest CPU oracle {identifier} max error mismatch.",
        )
        require(
            float(point.get("max_abs_error", 1.0)) <= CPU_ORACLE_ATOL,
            f"Manifest CPU oracle {identifier} error exceeds tolerance.",
        )

    static_fact = manifest.get("three_builtin_agx_non_equivalence", {})
    require(
        static_fact.get("kind") == "static_negative_fact_only"
        and static_fact.get("native_curve") == "agxDefaultContrastApprox"
        and static_fact.get("blender_look") == LOOK
        and static_fact.get("blender_medium_low_implemented_by_native_three_agx")
        is False
        and static_fact.get("numeric_equivalence_claimed") is False,
        "Manifest Three built-in AgX static negative fact mismatch.",
    )
    guardrails = manifest.get("guardrails", {})
    require(
        guardrails.get("three_builtin_agx_substitution_allowed") is False
        and guardrails.get("cross_renderer_equivalence_claimed") is False
        and guardrails.get("production_runtime_mutation_authorized") is False
        and guardrails.get("license_review_required_before_redistribution") is True,
        "Manifest guardrails mismatch.",
    )

    return {
        "schema_version": manifest["schema_version"],
        "license_pending": manifest["license_pending"],
        "scene_linear_input": transform["input_is_scene_linear"],
        "display_encoded_output": transform["output_is_display_encoded"],
        "nearest_and_clamp": True,
        "no_tone_mapping_raw_shader": True,
        "double_oetf_forbidden": True,
        "numpy_version": np.__version__,
    }


def verify_asset_directory_shape(asset_dir: Path) -> None:
    """Reject missing or unexpected files in the generated asset directory."""

    require(asset_dir.is_dir(), f"Generated asset directory is missing: {asset_dir}")
    actual = {path.name for path in asset_dir.iterdir() if path.is_file()}
    require(
        actual == EXPECTED_FILENAMES,
        f"Generated filenames differ: actual={sorted(actual)}, "
        f"expected={sorted(EXPECTED_FILENAMES)}",
    )
    require(
        all(path.is_file() for path in asset_dir.iterdir()),
        "Generated directory must contain files only.",
    )


def parse_args() -> argparse.Namespace:
    """Parse the generated asset directory option."""

    parser = argparse.ArgumentParser(
        description=(
            "Independently verify the exact WEB-60 R2T Blender 5.2 OCIO "
            "GLSL ES3 and RGB/RGBA LUT assets."
        ),
    )
    parser.add_argument(
        "--asset-dir",
        type=Path,
        default=DEFAULT_ASSET_DIR,
        help=f"Generated asset directory (default: {DEFAULT_ASSET_DIR})",
    )
    return parser.parse_args()


def main() -> int:
    """Run every independent byte, semantic, and numeric check."""

    args = parse_args()
    asset_dir = args.asset_dir.resolve()
    try:
        verify_asset_directory_shape(asset_dir)
        source_payloads = verify_sources()
        ocio, np = import_runtime_modules()
        (
            _processor,
            cpu_processor,
            rebuilt_shader,
            shader_cache_id,
            textures,
        ) = rebuild_processor_and_shader(ocio)
        shader_report = verify_shader_file(asset_dir, rebuilt_shader)
        texture_reports = verify_texture_files(
            ocio,
            np,
            asset_dir,
            textures,
        )
        cpu_reports = verify_cpu_oracles(cpu_processor)
        three_report = verify_three_static_negative_fact(
            source_payloads["three_r160_module"]
        )

        manifest_path = asset_dir / MANIFEST_FILE
        try:
            manifest_payload = manifest_path.read_bytes()
            manifest = json.loads(manifest_payload.decode("utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            raise VerificationError(f"Cannot parse {manifest_path}: {exc}") from exc
        require(isinstance(manifest, dict), "Manifest root must be an object.")
        manifest_report = verify_manifest(
            np,
            manifest,
            shader_cache_id,
            texture_reports,
            cpu_reports,
        )

        report = {
            "ok": True,
            "requirement_id": REQUIREMENT_ID,
            "asset_dir": str(asset_dir),
            "source_files_verified": len(SOURCE_SPECS),
            "pyopencolorio_version": ocio.__version__,
            "processor_cache_id": PROCESSOR_CACHE_ID,
            "shader": shader_report,
            "textures": texture_reports,
            "total_texels_bit_checked": sum(
                item["texels_bit_checked"] for item in texture_reports
            ),
            "total_rgba_alpha_values_checked": sum(
                item["texels_bit_checked"] for item in texture_reports
            ),
            "cpu_oracles": {
                "count": len(cpu_reports),
                "atol": CPU_ORACLE_ATOL,
                "max_abs_error": max(
                    item["max_abs_error"] for item in cpu_reports
                ),
                "all_pass": True,
                "points": cpu_reports,
            },
            "manifest": {
                "bytes": len(manifest_payload),
                "sha256": sha256_bytes(manifest_payload),
                **manifest_report,
            },
            "three_builtin_agx_non_equivalence": three_report,
            "all_checks_pass": True,
        }
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0
    except (VerificationError, OSError, ValueError) as exc:
        print(
            json.dumps(
                {
                    "ok": False,
                    "requirement_id": REQUIREMENT_ID,
                    "asset_dir": str(asset_dir),
                    "error": str(exc),
                    "all_checks_pass": False,
                },
                ensure_ascii=False,
                indent=2,
            ),
            file=sys.stderr,
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
