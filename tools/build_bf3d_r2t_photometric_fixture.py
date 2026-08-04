#!/usr/bin/env python3
r"""Build the frozen WEB-60 R2T scene-linear photometric fixture.

Requirement:
    REQ-BF3D-R2T-P40-PHOTOMETRIC-CALIBRATION-20260720

The command first writes and hashes the complete fit/held-out definition, then
starts Blender 5.2 background and the isolated Three.js r160 browser runner.
One non-negative WLS scalar is computed per light family. No held-out sample
may enter a fit, and no browser-, light-, material-, or shot-specific scalar is
created.

Outputs:
    photometric_fixture/fixture_definition.json
    photometric_fixture/blender_linear_reference.json
    photometric_fixture/three_linear_readback.json
    reports/photometric_fit_held_out_report.json
    reports/photometric_fixture_build_report.json

The completed report remains candidate-only because the pre-registered contract
does not define independent linear held-out acceptance thresholds and records
several known non-equivalences.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import shutil
import statistics
import subprocess
import sys
import traceback
from typing import Any, Iterable


REQUIREMENT_ID = "REQ-BF3D-R2T-P40-PHOTOMETRIC-CALIBRATION-20260720"
STAGE_ID = "WEB-60_R2T"
DEFINITION_SCHEMA = "bf3d.r2t.photometric_fixture_definition.v1"
FIT_REPORT_SCHEMA = "bf3d.r2t.photometric_fit_held_out_report.v1"
BUILD_REPORT_SCHEMA = "bf3d.r2t.photometric_fixture_build_report.v1"

REPO_ROOT = Path(__file__).resolve().parents[1]
STAGE_ROOT = (
    REPO_ROOT
    / "PT"
    / "高炉3D模型"
    / "work"
    / "WEB_60_20260720_R2T_OCIO_PHOTOMETRIC_EQUIVALENCE"
)
FIXTURE_ROOT = STAGE_ROOT / "photometric_fixture"
REPORT_ROOT = STAGE_ROOT / "reports"
CONTRACT_PATH = STAGE_ROOT / "photometric_calibration_contract.json"
LTC_REPORT_PATH = REPORT_ROOT / "ltc_runtime_oracle_report.json"
DEFINITION_PATH = FIXTURE_ROOT / "fixture_definition.json"
BLENDER_SCRIPT_PATH = FIXTURE_ROOT / "blender_reference.py"
BLENDER_OUTPUT_PATH = FIXTURE_ROOT / "blender_linear_reference.json"
THREE_RUNNER_PATH = REPO_ROOT / "tools" / "build_bf3d_r2t_photometric_fixture.cjs"
THREE_OUTPUT_PATH = FIXTURE_ROOT / "three_linear_readback.json"
FIT_REPORT_PATH = REPORT_ROOT / "photometric_fit_held_out_report.json"
BUILD_REPORT_PATH = REPORT_ROOT / "photometric_fixture_build_report.json"

BLENDER_EXE = Path(
    r"D:\Program Files\Blender Foundation\Blender 5.2\blender.exe"
)
THREE_MODULE_PATH = REPO_ROOT / "高炉前端数据" / "libs" / "three" / "three.module.js"
LTC_ADDON_PATH = (
    REPO_ROOT
    / "高炉前端数据"
    / "libs"
    / "three"
    / "lights"
    / "RectAreaLightUniformsLib.js"
)
EXPECTED_SOURCES = {
    "blender_5_2_executable": {
        "path": BLENDER_EXE,
        "bytes": 112_975_320,
        "sha256": "e27fbfea8564aa645d4463cb0949695fd85562b9de6df9561b06859a1074adf7",
    },
    "three_r160_module": {
        "path": THREE_MODULE_PATH,
        "bytes": 1_272_972,
        "sha256": "76dea8151bc9352aef3528b4262e249b2604f62543828328db978d060d61a495",
    },
    "rect_area_ltc_addon": {
        "path": LTC_ADDON_PATH,
        "bytes": 313_854,
        "sha256": "08085bc942253cd54948bf936fecb66b54514a135872656e475a1cab09b55214",
    },
}

LUMA = (0.2126, 0.7152, 0.0722)
DENOMINATOR_EPSILON = 1e-20


class BuildError(RuntimeError):
    """Raised when a frozen photometric build invariant does not hold."""


def utc_now() -> str:
    """Return an ISO-8601 UTC timestamp."""

    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def sha256_bytes(payload: bytes) -> str:
    """Return a lowercase SHA-256 digest."""

    return hashlib.sha256(payload).hexdigest()


def inspect_file(path: Path) -> dict[str, Any]:
    """Return a repository-relative identity for one file."""

    payload = path.read_bytes()
    try:
        manifest_path = path.relative_to(REPO_ROOT).as_posix()
    except ValueError:
        manifest_path = path.as_posix()
    return {
        "path": manifest_path,
        "bytes": len(payload),
        "sha256": sha256_bytes(payload),
    }


def read_json(path: Path) -> dict[str, Any]:
    """Read one UTF-8 JSON object."""

    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, value: dict[str, Any]) -> None:
    """Write deterministic human-readable UTF-8 JSON."""

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def canonical_json_bytes(value: dict[str, Any]) -> bytes:
    """Return the exact bytes used to freeze the fixture definition."""

    return (
        json.dumps(value, ensure_ascii=False, indent=2) + "\n"
    ).encode("utf-8")


def map_blender_to_three(vector: Iterable[float]) -> list[float]:
    """Apply B(x,y,z) -> T(x,z,-y)."""

    x, y, z = (float(value) for value in vector)
    return [x, z, -y]


def base_lambert() -> dict[str, Any]:
    """Return the frozen 18-percent gray Lambert material payload."""

    return {"base_color_linear_rgb": [0.18, 0.18, 0.18]}


def _slug(value: float) -> str:
    """Create a stable decimal sample-id component."""

    return f"{value:.3f}".replace(".", "p")


def build_sun_samples(contract: dict[str, Any]) -> list[dict[str, Any]]:
    """Create the frozen SUN fit and held-out sample rows."""

    family = contract["candidate_family"]["sun"]
    fit_dots = list(contract["fit_contract"]["sun_fit"]["normal_dot_light"])
    held_out_dots = [0.875, 0.625, 0.375, 0.125]
    samples: list[dict[str, Any]] = []
    for partition, dots in (("fit", fit_dots), ("held_out", held_out_dots)):
        for light in family["lights"]:
            for dot in dots:
                tangent = math.sqrt(max(0.0, 1.0 - float(dot) ** 2))
                propagation_b = [tangent, 0.0, -float(dot)]
                propagation_t = map_blender_to_three(propagation_b)
                samples.append(
                    {
                        "id": (
                            f"sun_{partition}_{light['name'].lower()}_"
                            f"ndotl_{_slug(float(dot))}"
                        ),
                        "family": "sun",
                        "partition": partition,
                        "weight": 1.0,
                        "geometry": "plane_patch",
                        "material_kind": "lambert",
                        "material": base_lambert(),
                        "light_name": light["name"],
                        "normal_dot_light": float(dot),
                        "blender_energy": float(light["intensity_at_k1"]),
                        "three_intensity_at_k1": float(light["intensity_at_k1"]),
                        "blender_angular_diameter_rad": 0.13962633907794952,
                        "blender_surface_normal": [0.0, 0.0, 1.0],
                        "three_surface_normal": [0.0, 1.0, 0.0],
                        "blender_view_normal": [0.0, 0.0, 1.0],
                        "three_view_normal": [0.0, 1.0, 0.0],
                        "blender_propagation_direction": propagation_b,
                        "three_propagation_direction": propagation_t,
                        "coordinate_mapping_applied": True,
                    }
                )
    return samples


def build_area_samples(contract: dict[str, Any]) -> list[dict[str, Any]]:
    """Create TOP DISK/equal-area-square fit and held-out rows."""

    top = contract["candidate_family"]["top_area"]
    area_fit = contract["fit_contract"]["area_fit"]
    fit_positions = [
        [float(item[0]), float(item[1])]
        for item in area_fit["normalized_patch_xz"]
    ]
    fit_heights = [float(item) for item in area_fit["height_over_side"]]
    held_out_positions = [
        [0.125, 0.125],
        [0.375, 0.125],
        [0.75, 0.25],
        [0.5, 0.5],
        [0.75, 0.75],
    ]
    held_out_heights = [0.75, 1.5]
    side = float(top["square_width_m"])
    samples: list[dict[str, Any]] = []
    for partition, positions, heights in (
        ("fit", fit_positions, fit_heights),
        ("held_out", held_out_positions, held_out_heights),
    ):
        for height_ratio in heights:
            height = side * height_ratio
            for normalized_x, normalized_z in positions:
                patch_three = [side * normalized_x, 0.0, side * normalized_z]
                patch_blender = [
                    patch_three[0],
                    -patch_three[2],
                    patch_three[1],
                ]
                relative_blender = [
                    -patch_blender[0],
                    -patch_blender[1],
                    height,
                ]
                relative_three = map_blender_to_three(relative_blender)
                samples.append(
                    {
                        "id": (
                            f"top_area_{partition}_x{_slug(normalized_x)}_"
                            f"z{_slug(normalized_z)}_h{_slug(height_ratio)}"
                        ),
                        "family": "top_area",
                        "partition": partition,
                        "weight": 1.0,
                        "geometry": "plane_patch",
                        "material_kind": "lambert",
                        "material": base_lambert(),
                        "normalized_patch_xz": [normalized_x, normalized_z],
                        "height_over_side": height_ratio,
                        "height_m": height,
                        "source_power_w": float(top["source_power_w"]),
                        "source_disk_diameter_m": float(
                            top["source_disk_diameter_m"]
                        ),
                        "source_disk_area_m2": float(top["source_disk_area_m2"]),
                        "equal_area_square_side_m": side,
                        "three_intensity_at_k1": float(top["intensity_at_k1"]),
                        "blender_patch_position": patch_blender,
                        "three_patch_position": patch_three,
                        "blender_relative_light_position": relative_blender,
                        "three_relative_light_position": relative_three,
                        "blender_surface_normal": [0.0, 0.0, 1.0],
                        "three_surface_normal": [0.0, 1.0, 0.0],
                        "blender_view_normal": [0.0, 0.0, 1.0],
                        "three_view_normal": [0.0, 1.0, 0.0],
                        "coordinate_mapping_applied": True,
                    }
                )
    return samples


def build_world_samples(contract: dict[str, Any]) -> list[dict[str, Any]]:
    """Create WORLD diffuse fit objects and the frozen material board."""

    radiance = list(
        contract["candidate_family"]["world"]["constant_radiance_linear_rgb"]
    )
    axes = [
        ("pos_x", [1.0, 0.0, 0.0]),
        ("neg_x", [-1.0, 0.0, 0.0]),
        ("pos_y", [0.0, 1.0, 0.0]),
        ("neg_y", [0.0, -1.0, 0.0]),
        ("pos_z", [0.0, 0.0, 1.0]),
        ("neg_z", [0.0, 0.0, -1.0]),
    ]
    samples: list[dict[str, Any]] = [
        {
            "id": "world_fit_diffuse_sphere",
            "family": "world",
            "partition": "fit",
            "weight": 1.0,
            "geometry": "sphere_patch_center",
            "material_kind": "lambert",
            "material": base_lambert(),
            "blender_surface_normal": [0.0, 0.0, 1.0],
            "three_surface_normal": [0.0, 1.0, 0.0],
            "blender_view_normal": [0.0, 0.0, 1.0],
            "three_view_normal": [0.0, 1.0, 0.0],
            "radiance_linear_rgb": radiance,
            "coordinate_mapping_applied": True,
        }
    ]
    for axis_name, normal_b in axes:
        normal_t = map_blender_to_three(normal_b)
        samples.append(
            {
                "id": f"world_fit_plane_{axis_name}",
                "family": "world",
                "partition": "fit",
                "weight": 1.0,
                "geometry": "plane_patch",
                "material_kind": "lambert",
                "material": base_lambert(),
                "blender_surface_normal": normal_b,
                "three_surface_normal": normal_t,
                "blender_view_normal": normal_b,
                "three_view_normal": normal_t,
                "radiance_linear_rgb": radiance,
                "coordinate_mapping_applied": True,
            }
        )
    board = contract["fit_contract"]["environment_fit"]["held_out_board"]
    for metalness in board["metalness"]:
        for roughness in board["roughness"]:
            samples.append(
                {
                    "id": (
                        f"world_held_out_board_m{_slug(float(metalness))}_"
                        f"r{_slug(float(roughness))}"
                    ),
                    "family": "world",
                    "partition": "held_out",
                    "weight": 1.0,
                    "geometry": "sphere_patch_center",
                    "material_kind": "principled_board",
                    "material": {
                        "base_color_linear_rgb": [0.18, 0.18, 0.18],
                        "roughness": float(roughness),
                        "metalness": float(metalness),
                        "ior": 1.5,
                        "dielectric_f0": 0.04,
                    },
                    "blender_surface_normal": [0.0, 0.0, 1.0],
                    "three_surface_normal": [0.0, 1.0, 0.0],
                    "blender_view_normal": [0.0, 0.0, 1.0],
                    "three_view_normal": [0.0, 1.0, 0.0],
                    "radiance_linear_rgb": radiance,
                    "coordinate_mapping_applied": True,
                }
            )
    return samples


def validate_contract(contract: dict[str, Any]) -> None:
    """Enforce the pre-registered contract before deriving any input."""

    checks = [
        (
            contract.get("schema_version")
            == "bf3d.r2t.photometric_calibration_contract.v1",
            "photometric contract schema mismatch",
        ),
        (
            contract.get("requirement_id") == REQUIREMENT_ID,
            "photometric contract requirement mismatch",
        ),
        (
            contract["coordinate_mapping"]["formula"]
            == "Blender (x,y,z) -> Three.js (x,z,-y)",
            "coordinate mapping formula mismatch",
        ),
        (
            contract["runtime_prerequisites"]["linear_fixture"]["tone_mapping"]
            == "THREE.NoToneMapping",
            "NoToneMapping contract missing",
        ),
        (
            contract["runtime_prerequisites"]["linear_fixture"]["msaa"] is False,
            "MSAA must be disabled",
        ),
        (
            contract["runtime_prerequisites"]["linear_fixture"][
                "one_light_family_at_a_time"
            ]
            is True,
            "one-family-at-a-time contract missing",
        ),
        (
            contract["fit_contract"]["method"]
            == "one non-negative weighted least-squares scalar per family",
            "WLS method mismatch",
        ),
        (
            contract["fit_contract"]["zero_denominator_policy"] == "fail_closed",
            "zero-denominator policy mismatch",
        ),
        (
            contract["fit_contract"]["fit_and_held_out_sets_frozen_before_render"]
            is True,
            "fit/held-out freeze requirement missing",
        ),
        (
            contract["fit_contract"]["sun_fit"]["all_three_suns_share_one_k"]
            is True,
            "SUN shared-k contract missing",
        ),
        (
            contract["fit_contract"]["area_fit"][
                "disk_square_spatial_residual_must_be_reported"
            ]
            is True,
            "DISK-square residual reporting requirement missing",
        ),
        (
            contract["fit_contract"]["environment_fit"]["held_out_refit_allowed"]
            is False,
            "environment held-out refit must be forbidden",
        ),
    ]
    failed = [message for passed, message in checks if not passed]
    if failed:
        raise BuildError("; ".join(failed))
    for key in (
        "per_light_tuning_allowed",
        "per_material_tuning_allowed",
        "per_shot_tuning_allowed",
        "threshold_relaxation_allowed",
        "post_hoc_image_tuning_allowed",
    ):
        if contract["guardrails"][key] is not False:
            raise BuildError(f"guardrail mismatch: {key}")


def inspect_locked_sources() -> dict[str, Any]:
    """Enforce the frozen Blender, Three, and LTC addon identities."""

    resources = []
    for source_id, spec in EXPECTED_SOURCES.items():
        actual = inspect_file(Path(spec["path"]))
        passed = (
            actual["bytes"] == spec["bytes"]
            and actual["sha256"] == spec["sha256"]
        )
        resources.append(
            {
                "id": source_id,
                **actual,
                "expected_bytes": spec["bytes"],
                "expected_sha256": spec["sha256"],
                "passed": passed,
            }
        )
    if not all(item["passed"] for item in resources):
        raise BuildError("one or more frozen runtime sources changed")
    return {"resources": resources, "passed": True}


def validate_ltc_prerequisite() -> dict[str, Any]:
    """Read, but never modify, the existing TOP LTC runtime report."""

    report = read_json(LTC_REPORT_PATH)
    identity = inspect_file(LTC_REPORT_PATH)
    passed = (
        report.get("schema_version")
        == "bf3d.r2t.ltc_runtime_oracle_report.v1"
        and report.get("status")
        == "runtime_prerequisite_verified_candidate_not_approved"
        and report.get("passed") is True
        and report.get("classification", {}).get(
            "runtime_prerequisite_verified"
        )
        is True
        and report.get("classification", {}).get("capture_eligible") is False
        and report.get("summary", {}).get("evaluated_runs") == 6
        and report.get("summary", {}).get("passed_runs") == 6
        and not report.get("summary", {}).get("not_evaluated_runs")
    )
    if not passed:
        raise BuildError("TOP LTC runtime prerequisite is not verified")
    return {
        **identity,
        "status": report["status"],
        "evaluated_runs": report["summary"]["evaluated_runs"],
        "passed_runs": report["summary"]["passed_runs"],
        "candidate_only": True,
        "blender_photometric_equivalence_claimed": False,
        "rect_area_light_shadow_claimed": False,
        "passed": True,
    }


def build_definition(
    contract: dict[str, Any],
    contract_identity: dict[str, Any],
    ltc_prerequisite: dict[str, Any],
) -> dict[str, Any]:
    """Derive the complete deterministic fixture definition."""

    sun_samples = build_sun_samples(contract)
    area_samples = build_area_samples(contract)
    world_samples = build_world_samples(contract)
    all_ids = [item["id"] for item in sun_samples + area_samples + world_samples]
    if len(all_ids) != len(set(all_ids)):
        raise BuildError("fixture sample IDs are not unique")
    return {
        "schema_version": DEFINITION_SCHEMA,
        "requirement_id": REQUIREMENT_ID,
        "stage_id": STAGE_ID,
        "status": "frozen_before_render",
        "objective": (
            "Evaluate the pre-registered Blender P40 SUN, TOP and WORLD "
            "candidates in an isolated scene-linear fixture."
        ),
        "source_contract": contract_identity,
        "freeze_protocol": {
            "definition_written_and_sha256_computed_before_any_renderer": True,
            "existing_definition_mismatch_policy": "fail_closed_no_overwrite",
            "fit_and_held_out_ids_immutable_after_first_write": True,
            "fit_measurement": (
                "center-ROI median RGB converted to linear Rec.709 luminance"
            ),
            "fit_three_engine": "chromium",
            "fit_three_run_index": 0,
            "held_out_refit_allowed": False,
        },
        "coordinate_mapping": contract["coordinate_mapping"],
        "renderer_contract": {
            "common": {
                "scene_linear": True,
                "one_light_family_at_a_time": True,
                "shadows": False,
                "post_processing": False,
                "ao": False,
                "extra_gi": False,
                "beauty_capture": False,
                "mask_capture": False,
            },
            "blender": {
                "version": "5.2.x",
                "background": True,
                "factory_startup": True,
                "fit_reference_engine": "CYCLES",
                "held_out_engine": "BLENDER_EEVEE_NEXT",
                "cycles_device": "CPU",
                "cycles_samples": 128,
                "cycles_seed": 3407,
                "width": 24,
                "height": 24,
                "center_roi_size": 8,
                "readback": "Render Result scene-linear float32",
                "file_image_output": False,
            },
            "three": {
                "revision": "160",
                "tone_mapping": "THREE.NoToneMapping",
                "exposure": 1.0,
                "output_color_space": "THREE.LinearSRGBColorSpace",
                "render_target": "RGBA32F",
                "msaa": False,
                "samples": 0,
                "dithering": False,
                "post_processing": False,
                "shadows": False,
                "ao": False,
                "extra_gi": False,
                "width": 32,
                "height": 32,
                "center_roi_size": 8,
                "engines": ["chromium", "firefox", "webkit"],
                "fresh_runs_per_engine": 2,
            },
        },
        "fit_contract": {
            "method": contract["fit_contract"]["method"],
            "formula": contract["fit_contract"]["formula"],
            "measurement_scalar": "linear_rec709_luminance",
            "denominator_epsilon": DENOMINATOR_EPSILON,
            "zero_denominator_policy": "fail_closed",
            "one_scalar_per_family": True,
            "sun_three_lights_share_one_k": True,
            "per_light_refit": False,
            "per_material_refit": False,
            "per_shot_refit": False,
            "per_engine_refit": False,
            "per_browser_refit": False,
        },
        "runtime_prerequisites": {
            "top_ltc": ltc_prerequisite,
            "top_ltc_effect": (
                "runtime prerequisite only; not TOP/Blender equivalence "
                "or RectAreaLight shadow approval"
            ),
        },
        "families": {
            "sun": {
                "formula": contract["candidate_family"]["sun"]["formula"],
                "three_use_legacy_lights": False,
                "shared_k_name": "k_sun",
                "known_non_equivalence": ["sun_angular_diameter", "sun_and_area_shadows"],
                "samples": sun_samples,
            },
            "top_area": {
                "formula": contract["candidate_family"]["top_area"]["formula"],
                "blender_shape": "DISK",
                "three_shape": "equal-area square RectAreaLight",
                "shared_k_name": "k_area",
                "disk_square_spatial_residual_required": True,
                "known_non_equivalence": [
                    "sun_and_area_shadows",
                    "disk_to_square_spatial_distribution",
                ],
                "samples": area_samples,
            },
            "world": {
                "formula": contract["candidate_family"]["world"]["formula"],
                "radiance_linear_rgb": contract["candidate_family"]["world"][
                    "constant_radiance_linear_rgb"
                ],
                "three_implementation": (
                    "constant Linear-sRGB Float32 equirectangular texture "
                    "through PMREM to scene.environment"
                ),
                "env_map_intensity": 1.0,
                "shared_k_name": "k_env",
                "ambient_light_substitution": False,
                "known_non_equivalence": [
                    "radiometric_to_photometric_units",
                    "blender_path_traced_ibl_vs_three_pmrem_split_sum",
                ],
                "samples": world_samples,
            },
        },
        "known_non_equivalence": contract["known_non_equivalence"],
        "acceptance": {
            "linear_fit_thresholds_pre_registered": False,
            "linear_held_out_thresholds_pre_registered": False,
            "metrics_must_be_reported": True,
            "numeric_equivalence_auto_approval_allowed": False,
            "complete_execution_classification": (
                "evaluated_candidate_not_approved_no_acceptance_thresholds"
            ),
            "not_evaluated_blocks_pass": True,
        },
        "guardrails": {
            **contract["guardrails"],
            "production_scene_loaded": False,
            "production_renderer_loaded": False,
            "production_glb_loaded": False,
            "beauty_capture_allowed": False,
        },
    }


def freeze_definition(definition: dict[str, Any]) -> dict[str, Any]:
    """Write once or prove byte-for-byte equality with the existing freeze."""

    expected_payload = canonical_json_bytes(definition)
    if DEFINITION_PATH.exists():
        existing_payload = DEFINITION_PATH.read_bytes()
        if existing_payload != expected_payload:
            raise BuildError(
                "existing fixture_definition.json differs from the derived "
                "pre-render definition; refusing post-freeze overwrite"
            )
        created = False
    else:
        DEFINITION_PATH.parent.mkdir(parents=True, exist_ok=True)
        DEFINITION_PATH.write_bytes(expected_payload)
        existing_payload = expected_payload
        created = True
    return {
        "path": DEFINITION_PATH.relative_to(REPO_ROOT).as_posix(),
        "bytes": len(existing_payload),
        "sha256": sha256_bytes(existing_payload),
        "created_this_run": created,
        "frozen_before_renderer_start": True,
        "passed": True,
    }


def run_command(
    argv: list[str],
    timeout_seconds: int,
) -> dict[str, Any]:
    """Run one child process and preserve its exact argv and result."""

    started_at = utc_now()
    try:
        completed = subprocess.run(
            argv,
            cwd=REPO_ROOT,
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout_seconds,
        )
        return {
            "argv": argv,
            "cwd": REPO_ROOT.as_posix(),
            "started_at": started_at,
            "completed_at": utc_now(),
            "exit_code": completed.returncode,
            "stdout": completed.stdout,
            "stderr": completed.stderr,
            "timed_out": False,
            "passed": completed.returncode == 0,
        }
    except subprocess.TimeoutExpired as exc:
        return {
            "argv": argv,
            "cwd": REPO_ROOT.as_posix(),
            "started_at": started_at,
            "completed_at": utc_now(),
            "exit_code": None,
            "stdout": str(exc.stdout or ""),
            "stderr": str(exc.stderr or ""),
            "timed_out": True,
            "passed": False,
        }


def output_is_complete(
    path: Path,
    expected_schema: str,
    definition_sha: str,
) -> tuple[bool, dict[str, Any] | None]:
    """Check one renderer output without mutating it."""

    if not path.is_file():
        return False, None
    try:
        data = read_json(path)
    except (OSError, json.JSONDecodeError):
        return False, None
    output_definition_sha = data.get("definition", {}).get("sha256")
    return (
        data.get("schema_version") == expected_schema
        and data.get("passed") is True
        and data.get("evaluated") is True
        and output_definition_sha == definition_sha,
        data,
    )


def sample_scalar(sample: dict[str, Any]) -> float:
    """Read the frozen linear Rec.709 luminance measurement."""

    value = float(sample["statistics"]["linear_rec709_luminance"])
    if not math.isfinite(value):
        raise BuildError(f"non-finite sample scalar for {sample.get('id')}")
    return value


def compute_wls(
    family: str,
    definition: dict[str, Any],
    blender_samples: dict[str, dict[str, Any]],
    three_samples: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    """Compute one non-negative WLS scalar from fit IDs only."""

    fit_rows = [
        sample
        for sample in definition["families"][family]["samples"]
        if sample["partition"] == "fit"
    ]
    numerator = 0.0
    denominator = 0.0
    terms = []
    for row in fit_rows:
        sample_id = row["id"]
        if sample_id not in blender_samples or sample_id not in three_samples:
            raise BuildError(f"missing fit sample {sample_id}")
        blender_value = sample_scalar(blender_samples[sample_id])
        three_value = sample_scalar(three_samples[sample_id])
        weight = float(row["weight"])
        numerator_term = weight * three_value * blender_value
        denominator_term = weight * three_value * three_value
        numerator += numerator_term
        denominator += denominator_term
        terms.append(
            {
                "sample_id": sample_id,
                "partition": "fit",
                "weight": weight,
                "blender_cycles": blender_value,
                "three_k1": three_value,
                "numerator_term": numerator_term,
                "denominator_term": denominator_term,
            }
        )
    if not math.isfinite(denominator) or denominator <= DENOMINATOR_EPSILON:
        raise BuildError(
            f"{family} WLS denominator failed closed: {denominator}"
        )
    unconstrained = numerator / denominator
    k = max(0.0, unconstrained)
    three_fit_values = [
        float(term["three_k1"])
        for term in terms
    ]
    return {
        "family": family,
        "k_name": definition["families"][family]["shared_k_name"],
        "fit_source_three_engine": "chromium",
        "fit_source_three_run_index": 0,
        "fit_sample_count": len(fit_rows),
        "fit_sample_ids": [row["id"] for row in fit_rows],
        "held_out_sample_ids_used": [],
        "numerator": numerator,
        "denominator": denominator,
        "denominator_epsilon": DENOMINATOR_EPSILON,
        "zero_denominator_policy": "fail_closed",
        "canonical_three_signal_summary": {
            "engine": "chromium",
            "run_index": 0,
            "partition": "fit",
            "sample_count": len(three_fit_values),
            "positive_sample_count": sum(
                value > 0.0 for value in three_fit_values
            ),
            "min_three_k1": min(three_fit_values),
            "max_three_k1": max(three_fit_values),
            "mean_three_k1": statistics.fmean(three_fit_values),
            "weighted_wls_denominator": denominator,
            "denominator_epsilon": DENOMINATOR_EPSILON,
            "zero_denominator_policy": "fail_closed",
            "passed": denominator > DENOMINATOR_EPSILON,
        },
        "unconstrained_scalar": unconstrained,
        "non_negative_scalar": k,
        "constraint_active": unconstrained < 0.0,
        "terms": terms,
        "status": "evaluated",
    }


def percentile(values: list[float], probability: float) -> float:
    """Compute a deterministic linear-interpolation percentile."""

    if not values:
        raise BuildError("cannot compute percentile of an empty list")
    ordered = sorted(values)
    position = (len(ordered) - 1) * probability
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return ordered[lower]
    fraction = position - lower
    return ordered[lower] * (1.0 - fraction) + ordered[upper] * fraction


def metric_summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Summarize signed, absolute and relative residuals."""

    if not rows:
        return {"status": "not_evaluated", "sample_count": 0}
    residuals = [float(row["residual"]) for row in rows]
    absolute = [abs(value) for value in residuals]
    relative = [float(row["absolute_relative_residual"]) for row in rows]
    return {
        "status": "evaluated_no_pre_registered_acceptance_threshold",
        "sample_count": len(rows),
        "mean_signed_residual": statistics.fmean(residuals),
        "mae": statistics.fmean(absolute),
        "rmse": math.sqrt(statistics.fmean(value * value for value in residuals)),
        "median_absolute_residual": statistics.median(absolute),
        "max_absolute_residual": max(absolute),
        "median_absolute_relative_residual": statistics.median(relative),
        "p95_absolute_relative_residual": percentile(relative, 0.95),
        "max_absolute_relative_residual": max(relative),
        "threshold": None,
        "equivalence_pass_claimed": False,
    }


def evaluate_partition(
    definition: dict[str, Any],
    family: str,
    partition: str,
    k: float,
    blender_samples: dict[str, dict[str, Any]],
    three_samples: dict[str, dict[str, Any]],
    engine: str,
    run_index: int,
) -> dict[str, Any]:
    """Evaluate one partition using the already-fitted family scalar."""

    rows = []
    for fixture_row in definition["families"][family]["samples"]:
        if fixture_row["partition"] != partition:
            continue
        sample_id = fixture_row["id"]
        if sample_id not in blender_samples or sample_id not in three_samples:
            raise BuildError(f"missing {partition} sample {sample_id}")
        blender_value = sample_scalar(blender_samples[sample_id])
        three_k1 = sample_scalar(three_samples[sample_id])
        three_scaled = k * three_k1
        residual = three_scaled - blender_value
        rows.append(
            {
                "sample_id": sample_id,
                "family": family,
                "partition": partition,
                "three_engine": engine,
                "three_run_index": run_index,
                "k_from_chromium_run_0": k,
                "blender_cycles": blender_value,
                "three_k1": three_k1,
                "three_scaled": three_scaled,
                "residual": residual,
                "absolute_relative_residual": abs(residual)
                / max(abs(blender_value), 1e-12),
            }
        )
    return {
        "family": family,
        "partition": partition,
        "three_engine": engine,
        "three_run_index": run_index,
        "refit_performed": False,
        "rows": rows,
        "metrics": metric_summary(rows),
    }


def evaluate_eevee_board(
    definition: dict[str, Any],
    blender_cycles: dict[str, dict[str, Any]],
    blender_eevee: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    """Compare the frozen Eevee held-out board to Cycles without fitting."""

    rows = []
    for fixture_row in definition["families"]["world"]["samples"]:
        if (
            fixture_row["partition"] != "held_out"
            or fixture_row["material_kind"] != "principled_board"
        ):
            continue
        sample_id = fixture_row["id"]
        if sample_id not in blender_cycles or sample_id not in blender_eevee:
            raise BuildError(f"missing Eevee held-out board sample {sample_id}")
        reference = sample_scalar(blender_cycles[sample_id])
        eevee = sample_scalar(blender_eevee[sample_id])
        residual = eevee - reference
        rows.append(
            {
                "sample_id": sample_id,
                "blender_cycles": reference,
                "blender_eevee": eevee,
                "residual": residual,
                "absolute_relative_residual": abs(residual)
                / max(abs(reference), 1e-12),
            }
        )
    evaluated_engine = (
        next(iter(blender_eevee.values()))["engine"]
        if blender_eevee
        else "not_evaluated"
    )
    return {
        "partition": "held_out",
        "reference_engine": "CYCLES",
        "evaluated_engine": evaluated_engine,
        "definition_engine_label": "BLENDER_EEVEE_NEXT",
        "runtime_identifier_alias_recorded": True,
        "refit_performed": False,
        "rows": rows,
        "metrics": metric_summary(rows),
    }


def build_fit_report(
    definition: dict[str, Any],
    definition_identity: dict[str, Any],
    contract: dict[str, Any],
    blender_output: dict[str, Any],
    three_output: dict[str, Any],
) -> dict[str, Any]:
    """Fit the three family scalars and evaluate every frozen held-out row."""

    blender_cycles = {
        item["id"]: item for item in blender_output["cycles_samples"]
    }
    blender_eevee = {
        item["id"]: item for item in blender_output["eevee_held_out_samples"]
    }
    canonical_run = next(
        (
            run
            for run in three_output["runs"]
            if run["engine"] == "chromium"
            and run["run_index"] == 0
            and run["passed"] is True
        ),
        None,
    )
    if canonical_run is None:
        raise BuildError("pre-registered chromium run 0 fit input is unavailable")
    canonical_three = {
        item["id"]: item for item in canonical_run["page_result"]["samples"]
    }

    fit_results: dict[str, dict[str, Any]] = {}
    evaluations = []
    for family in ("sun", "top_area", "world"):
        fit = compute_wls(
            family,
            definition,
            blender_cycles,
            canonical_three,
        )
        fit_results[family] = fit

    for run in three_output["runs"]:
        if run.get("passed") is not True:
            raise BuildError(
                f"Three run not evaluated: {run.get('engine')}#{run.get('run_index')}"
            )
        three_samples = {
            item["id"]: item for item in run["page_result"]["samples"]
        }
        for family in ("sun", "top_area", "world"):
            k = float(fit_results[family]["non_negative_scalar"])
            for partition in ("fit", "held_out"):
                evaluations.append(
                    evaluate_partition(
                        definition,
                        family,
                        partition,
                        k,
                        blender_cycles,
                        three_samples,
                        run["engine"],
                        int(run["run_index"]),
                    )
                )

    canonical_area_fit = next(
        item
        for item in evaluations
        if item["family"] == "top_area"
        and item["partition"] == "fit"
        and item["three_engine"] == "chromium"
        and item["three_run_index"] == 0
    )
    canonical_area_held_out = next(
        item
        for item in evaluations
        if item["family"] == "top_area"
        and item["partition"] == "held_out"
        and item["three_engine"] == "chromium"
        and item["three_run_index"] == 0
    )
    eevee_board = evaluate_eevee_board(
        definition,
        blender_cycles,
        blender_eevee,
    )
    expected_top_basis = {
        "x": [1.0, 0.0, 0.0],
        "y": [0.0, 0.0, -1.0],
        "z": [0.0, 1.0, 0.0],
        "emission_direction": [0.0, -1.0, 0.0],
    }
    top_basis_runs = []
    for run in three_output["runs"]:
        diagnostics = run["page_result"].get("diagnostics", {}).get(
            "rect_area_controls_not_used_for_fit_or_held_out",
            [],
        )
        control = next(
            (
                item
                for item in diagnostics
                if item.get("mode") == "y_up_small_control_metal"
            ),
            None,
        )
        if control is None:
            raise BuildError(
                f"TOP basis diagnostic missing for "
                f"{run['engine']}#{run['run_index']}"
            )
        light = control["light"]
        observed = {
            "x": light["basis_x"],
            "y": light["basis_y"],
            "z": light["basis_z"],
            "emission_direction": light["emission_direction"],
        }
        errors = [
            abs(float(actual) - float(expected))
            for key in expected_top_basis
            for actual, expected in zip(
                observed[key],
                expected_top_basis[key],
                strict=True,
            )
        ]
        max_abs_error = max(errors)
        top_basis_runs.append(
            {
                "engine": run["engine"],
                "run_index": run["run_index"],
                "diagnostic_used_for_fit_or_held_out": False,
                "observed": observed,
                "max_abs_error": max_abs_error,
                "passed": max_abs_error <= 1e-12,
            }
        )
    if not all(item["passed"] for item in top_basis_runs):
        raise BuildError("TOP RectArea basis audit failed")
    world_pmrem_runs = []
    expected_world_radiance = definition["families"]["world"][
        "radiance_linear_rgb"
    ]
    for run in three_output["runs"]:
        independent = run.get("independent_evaluation", {})
        diagnostics = independent.get("world_pmrem")
        family_signal = independent.get("family_signal_summary", {}).get(
            "world"
        )
        world_samples = [
            sample
            for sample in run["page_result"]["samples"]
            if sample["family"] == "world"
        ]
        world_values = [sample_scalar(sample) for sample in world_samples]
        world_held_out_values = [
            sample_scalar(sample)
            for sample in world_samples
            if sample["partition"] == "held_out"
        ]
        if (
            independent.get("world_pmrem_contract_pass") is not True
            or diagnostics is None
            or family_signal is None
            or family_signal.get("passed") is not True
        ):
            raise BuildError(
                f"WORLD PMREM audit failed for "
                f"{run['engine']}#{run['run_index']}"
            )
        world_pmrem_runs.append(
            {
                "engine": run["engine"],
                "run_index": run["run_index"],
                "radiance_linear_rgb": diagnostics[
                    "radiance_linear_rgb"
                ],
                "source_resolution": diagnostics["source_resolution"],
                "cube_size": diagnostics["cube_size"],
                "three_r160_lod_min": diagnostics[
                    "three_r160_lod_min"
                ],
                "ambient_light_substitution": diagnostics[
                    "ambient_light_substitution"
                ],
                "fit_signal": family_signal,
                "all_world_signal": {
                    "sample_count": len(world_values),
                    "positive_sample_count": sum(
                        value > 0.0 for value in world_values
                    ),
                    "min_three_k1": min(world_values),
                    "max_three_k1": max(world_values),
                    "mean_three_k1": statistics.fmean(world_values),
                },
                "held_out_world_signal": {
                    "sample_count": len(world_held_out_values),
                    "positive_sample_count": sum(
                        value > 0.0 for value in world_held_out_values
                    ),
                    "min_three_k1": min(world_held_out_values),
                    "max_three_k1": max(world_held_out_values),
                    "mean_three_k1": statistics.fmean(
                        world_held_out_values
                    ),
                },
                "passed": True,
            }
        )
    source_artifacts = {
        "fixture_definition": definition_identity,
        "photometric_contract": inspect_file(CONTRACT_PATH),
        "ltc_runtime_report": inspect_file(LTC_REPORT_PATH),
        "blender_linear_reference": inspect_file(BLENDER_OUTPUT_PATH),
        "three_linear_readback": inspect_file(THREE_OUTPUT_PATH),
    }
    return {
        "schema_version": FIT_REPORT_SCHEMA,
        "requirement_id": REQUIREMENT_ID,
        "stage_id": STAGE_ID,
        "generated_at": utc_now(),
        "status": "evaluated_candidate_not_approved_no_acceptance_thresholds",
        "evaluation_complete": True,
        "passed": False,
        "classification": {
            "artifact_role": "isolated_photometric_candidate_evidence",
            "fit_executed": True,
            "held_out_executed": True,
            "linear_thresholds_pre_registered": False,
            "photometric_equivalence_approved": False,
            "capture_eligible": False,
            "approval_granted": False,
            "production_integration_allowed": False,
            "beauty_capture_performed": False,
            "mask_capture_performed": False,
        },
        "source_artifacts": source_artifacts,
        "fit_contract": definition["fit_contract"],
        "fit_results": fit_results,
        "browser_evaluations": evaluations,
        "eevee_world_board_held_out": eevee_board,
        "canonical_three_family_signal_summary": {
            family: payload["canonical_three_signal_summary"]
            for family, payload in fit_results.items()
        },
        "world_pmrem_runtime_audit": {
            "status": "evaluated",
            "passed": True,
            "failure_evidence_before_fix": {
                "source_resolution": [16, 8],
                "derived_cube_size": 4,
                "three_r160_lod_min": 4,
                "minimum_cube_size": 16,
                "failure_mode": (
                    "cubeSize 4 is below 2^LOD_MIN=16; the r160 "
                    "PMREM blur chain entered invalid negative LOD indexing "
                    "and all WORLD fit readbacks/denominator were zero"
                ),
                "world_wls_denominator": 0.0,
            },
            "implemented_sampling_prerequisite": {
                "source_resolution": [64, 32],
                "derived_cube_size": 16,
                "three_r160_lod_min": 4,
                "minimum_cube_size": 16,
                "constant_float32_equirectangular": True,
                "pmrem_to_scene_environment": True,
                "ambient_light_substitution": False,
            },
            "frozen_radiance_linear_rgb": expected_world_radiance,
            "sampling_implementation_fix_only": True,
            "radiance_changed": False,
            "sample_definition_changed": False,
            "partition_or_weight_changed": False,
            "threshold_changed": False,
            "fit_rule_changed": False,
            "runs": world_pmrem_runs,
        },
        "top_rect_area_basis_audit": {
            "status": "evaluated",
            "expected": expected_top_basis,
            "source_contract_basis": contract["candidate_family"]["top_area"][
                "three_basis"
            ],
            "runs": top_basis_runs,
            "all_runs_passed": True,
            "basis_use": (
                "local X -> world +X; local Y -> world -Z; "
                "local Z -> world +Y; emission local -Z -> world -Y"
            ),
        },
        "disk_square_spatial_residual": {
            "status": "evaluated_known_non_equivalence",
            "shape_mapping": "Blender DISK -> equal-area Three square",
            "fit_partition": canonical_area_fit,
            "held_out_partition": canonical_area_held_out,
            "residual_is_zero_required": False,
            "analytic_equivalence_claimed": False,
        },
        "known_non_equivalence": contract["known_non_equivalence"],
        "not_evaluated": [],
        "guardrails": {
            "fit_source": "Three Chromium run 0 against Blender Cycles",
            "one_k_per_family": True,
            "all_three_suns_share_one_k": True,
            "per_light_refit": False,
            "per_material_refit": False,
            "per_shot_refit": False,
            "per_engine_refit": False,
            "per_browser_refit": False,
            "held_out_refit": False,
            "threshold_relaxation": False,
            "production_scene_mutation": False,
            "production_renderer_mutation": False,
            "production_material_mutation": False,
            "beauty_capture": False,
        },
    }


def initial_build_report() -> dict[str, Any]:
    """Create a fail-closed report before any work starts."""

    block_names = [
        "contract_and_source_integrity",
        "fixture_definition_frozen",
        "top_ltc_prerequisite",
        "blender_cycles_reference",
        "blender_eevee_world_board_held_out",
        "three_r160_linear_readback",
        "family_wls_fit",
        "held_out_evaluation",
        "disk_square_spatial_residual",
    ]
    return {
        "schema_version": BUILD_REPORT_SCHEMA,
        "requirement_id": REQUIREMENT_ID,
        "stage_id": STAGE_ID,
        "generated_at": utc_now(),
        "status": "running",
        "fixture_execution_complete": False,
        "passed": False,
        "classification": {
            "photometric_equivalence_approved": False,
            "capture_eligible": False,
            "approval_granted": False,
            "production_integration_allowed": False,
            "beauty_capture_performed": False,
            "mask_capture_performed": False,
        },
        "blocks": {
            name: {
                "status": "not_evaluated",
                "evaluated": False,
                "passed": False,
            }
            for name in block_names
        },
        "commands": [],
        "artifacts": {},
        "not_evaluated": list(block_names),
        "errors": [],
    }


def mark_block(
    report: dict[str, Any],
    name: str,
    *,
    status: str,
    passed: bool,
    detail: Any = None,
) -> None:
    """Update one build block without implying final approval."""

    report["blocks"][name] = {
        "status": status,
        "evaluated": True,
        "passed": passed,
        **({} if detail is None else {"detail": detail}),
    }
    if name in report["not_evaluated"]:
        report["not_evaluated"].remove(name)


def parse_args() -> argparse.Namespace:
    """Parse command-line options."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--freeze-only",
        action="store_true",
        help=(
            "Freeze the complete definition, mark render/fit blocks "
            "not_evaluated, and exit non-zero."
        ),
    )
    parser.add_argument(
        "--blender-timeout-seconds",
        type=int,
        default=1800,
    )
    parser.add_argument(
        "--browser-timeout-seconds",
        type=int,
        default=900,
    )
    return parser.parse_args()


def main() -> int:
    """Build the fixture and write a complete fail-closed evidence chain."""

    args = parse_args()
    report = initial_build_report()
    exit_code = 1
    try:
        contract = read_json(CONTRACT_PATH)
        validate_contract(contract)
        sources = inspect_locked_sources()
        contract_identity = inspect_file(CONTRACT_PATH)
        ltc = validate_ltc_prerequisite()
        mark_block(
            report,
            "contract_and_source_integrity",
            status="evaluated",
            passed=True,
            detail={
                "contract": contract_identity,
                "locked_sources": sources,
            },
        )
        mark_block(
            report,
            "top_ltc_prerequisite",
            status="runtime_prerequisite_verified_candidate_not_approved",
            passed=True,
            detail=ltc,
        )
        definition = build_definition(
            contract,
            contract_identity,
            ltc,
        )
        definition_identity = freeze_definition(definition)
        mark_block(
            report,
            "fixture_definition_frozen",
            status="frozen_before_render",
            passed=True,
            detail=definition_identity,
        )
        report["artifacts"]["fixture_definition"] = definition_identity

        if args.freeze_only:
            report["status"] = "frozen_only_render_and_fit_not_evaluated"
            report["errors"].append(
                {
                    "type": "IntentionalNotEvaluated",
                    "message": (
                        "--freeze-only requested; renderer, fit, held-out and "
                        "disk-square blocks remain not_evaluated and block."
                    ),
                }
            )
            return 1

        blender_argv = [
            str(BLENDER_EXE),
            "--factory-startup",
            "--background",
            "--python",
            str(BLENDER_SCRIPT_PATH),
            "--",
            "--definition",
            str(DEFINITION_PATH),
            "--definition-sha256",
            definition_identity["sha256"],
            "--output",
            str(BLENDER_OUTPUT_PATH),
        ]
        blender_command = run_command(
            blender_argv,
            args.blender_timeout_seconds,
        )
        report["commands"].append(
            {"id": "blender_reference", **blender_command}
        )
        blender_complete, blender_output = output_is_complete(
            BLENDER_OUTPUT_PATH,
            "bf3d.r2t.blender_linear_reference.v1",
            definition_identity["sha256"],
        )
        mark_block(
            report,
            "blender_cycles_reference",
            status=(
                "evaluated"
                if blender_complete
                else "failed_or_not_evaluated"
            ),
            passed=blender_complete,
            detail=(
                inspect_file(BLENDER_OUTPUT_PATH)
                if BLENDER_OUTPUT_PATH.is_file()
                else None
            ),
        )
        eevee_complete = bool(
            blender_complete
            and blender_output
            and len(blender_output.get("eevee_held_out_samples", [])) == 8
        )
        mark_block(
            report,
            "blender_eevee_world_board_held_out",
            status=(
                "evaluated_held_out"
                if eevee_complete
                else "failed_or_not_evaluated"
            ),
            passed=eevee_complete,
            detail={
                "expected_samples": 8,
                "actual_samples": (
                    len(blender_output.get("eevee_held_out_samples", []))
                    if blender_output
                    else 0
                ),
            },
        )

        node = shutil.which("node")
        if node is None:
            raise BuildError("node executable is unavailable")
        three_argv = [
            node,
            str(THREE_RUNNER_PATH),
            "--definition-sha256",
            definition_identity["sha256"],
        ]
        three_command = run_command(
            three_argv,
            args.browser_timeout_seconds,
        )
        report["commands"].append(
            {"id": "three_linear_readback", **three_command}
        )
        three_complete, three_output = output_is_complete(
            THREE_OUTPUT_PATH,
            "bf3d.r2t.three_linear_readback.v1",
            definition_identity["sha256"],
        )
        mark_block(
            report,
            "three_r160_linear_readback",
            status=(
                "evaluated"
                if three_complete
                else "failed_or_not_evaluated"
            ),
            passed=three_complete,
            detail=(
                inspect_file(THREE_OUTPUT_PATH)
                if THREE_OUTPUT_PATH.is_file()
                else None
            ),
        )

        if not blender_complete or not eevee_complete or not three_complete:
            raise BuildError(
                "one or more renderer blocks failed; fit/held-out remains blocked"
            )
        assert blender_output is not None
        assert three_output is not None
        fit_report = build_fit_report(
            definition,
            definition_identity,
            contract,
            blender_output,
            three_output,
        )
        write_json(FIT_REPORT_PATH, fit_report)
        fit_identity = inspect_file(FIT_REPORT_PATH)
        report["artifacts"]["blender_linear_reference"] = inspect_file(
            BLENDER_OUTPUT_PATH
        )
        report["artifacts"]["three_linear_readback"] = inspect_file(
            THREE_OUTPUT_PATH
        )
        report["artifacts"]["photometric_fit_held_out_report"] = fit_identity
        mark_block(
            report,
            "family_wls_fit",
            status="evaluated",
            passed=True,
            detail={
                family: {
                    "k_name": payload["k_name"],
                    "non_negative_scalar": payload["non_negative_scalar"],
                    "denominator": payload["denominator"],
                    "fit_sample_count": payload["fit_sample_count"],
                    "canonical_three_signal_summary": payload[
                        "canonical_three_signal_summary"
                    ],
                }
                for family, payload in fit_report["fit_results"].items()
            },
        )
        mark_block(
            report,
            "held_out_evaluation",
            status="evaluated_no_pre_registered_acceptance_threshold",
            passed=True,
            detail={
                "browser_evaluation_groups": len(
                    fit_report["browser_evaluations"]
                ),
                "eevee_board_samples": len(
                    fit_report["eevee_world_board_held_out"]["rows"]
                ),
                "refit_performed": False,
                "equivalence_pass_claimed": False,
            },
        )
        mark_block(
            report,
            "disk_square_spatial_residual",
            status="evaluated_known_non_equivalence",
            passed=True,
            detail={
                "fit_metrics": fit_report["disk_square_spatial_residual"][
                    "fit_partition"
                ]["metrics"],
                "held_out_metrics": fit_report["disk_square_spatial_residual"][
                    "held_out_partition"
                ]["metrics"],
                "analytic_equivalence_claimed": False,
            },
        )
        report["fixture_execution_complete"] = not report["not_evaluated"]
        report["passed"] = report["fixture_execution_complete"]
        report["status"] = (
            "fixture_evaluated_candidate_not_approved"
            if report["fixture_execution_complete"]
            else "fixture_incomplete_fail_closed"
        )
        exit_code = 0 if report["fixture_execution_complete"] else 1
    except Exception as exc:  # noqa: BLE001 - fail-closed report is required
        report["status"] = "fixture_failed_closed"
        report["errors"].append(
            {
                "type": type(exc).__name__,
                "message": str(exc),
                "traceback": traceback.format_exc(),
            }
        )
        exit_code = 1
    finally:
        report["generated_at"] = utc_now()
        write_json(BUILD_REPORT_PATH, report)
        print(
            json.dumps(
                {
                    "status": report["status"],
                    "fixture_execution_complete": report[
                        "fixture_execution_complete"
                    ],
                    "passed": report["passed"],
                    "not_evaluated": report["not_evaluated"],
                    "report": BUILD_REPORT_PATH.relative_to(REPO_ROOT).as_posix(),
                },
                ensure_ascii=False,
                indent=2,
            )
        )
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
