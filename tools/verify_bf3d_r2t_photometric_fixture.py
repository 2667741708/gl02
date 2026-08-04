#!/usr/bin/env python3
"""Independently verify the WEB-60 R2T linear photometric fixture.

Requirement:
    REQ-BF3D-R2T-P40-PHOTOMETRIC-CALIBRATION-20260720

The verifier recomputes sample-set membership, the non-negative WLS scalar for
each family, scaled residual rows, disk-square reporting, browser isolation,
and the no-beauty boundary. A successful verification means only that the
candidate evidence is complete and internally reproducible. It cannot approve
photometric equivalence, capture, or production integration.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import statistics
import sys
import traceback
from typing import Any, Iterable


REQUIREMENT_ID = "REQ-BF3D-R2T-P40-PHOTOMETRIC-CALIBRATION-20260720"
STAGE_ID = "WEB-60_R2T"
SCHEMA_VERSION = "bf3d.r2t.photometric_verification_report.v1"
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
DEFINITION_PATH = FIXTURE_ROOT / "fixture_definition.json"
BLENDER_OUTPUT_PATH = FIXTURE_ROOT / "blender_linear_reference.json"
THREE_OUTPUT_PATH = FIXTURE_ROOT / "three_linear_readback.json"
FIT_REPORT_PATH = REPORT_ROOT / "photometric_fit_held_out_report.json"
BUILD_REPORT_PATH = REPORT_ROOT / "photometric_fixture_build_report.json"
LTC_REPORT_PATH = REPORT_ROOT / "ltc_runtime_oracle_report.json"
VERIFICATION_REPORT_PATH = REPORT_ROOT / "photometric_verification_report.json"
EXPECTED_FAMILIES = ("sun", "top_area", "world")
EXPECTED_ENGINES = ("chromium", "firefox", "webkit")
DENOMINATOR_EPSILON = 1e-20
ABS_TOL = 1e-12
REL_TOL = 1e-9
IMAGE_SUFFIXES = {
    ".png",
    ".jpg",
    ".jpeg",
    ".webp",
    ".exr",
    ".hdr",
    ".tif",
    ".tiff",
    ".bmp",
}


class VerificationError(RuntimeError):
    """Raised when any independent evidence invariant fails."""


def utc_now() -> str:
    """Return an ISO-8601 UTC timestamp."""

    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def read_json(path: Path) -> dict[str, Any]:
    """Read one UTF-8 JSON object."""

    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, value: dict[str, Any]) -> None:
    """Write the verification report as UTF-8 JSON."""

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def sha256_bytes(payload: bytes) -> str:
    """Return a lowercase SHA-256 digest."""

    return hashlib.sha256(payload).hexdigest()


def inspect_file(path: Path) -> dict[str, Any]:
    """Return one artifact identity."""

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


def close(left: float, right: float) -> bool:
    """Compare two finite scalars with strict absolute/relative tolerances."""

    return math.isclose(
        float(left),
        float(right),
        rel_tol=REL_TOL,
        abs_tol=ABS_TOL,
    )


def require(condition: bool, message: str) -> None:
    """Raise a verification error on a failed invariant."""

    if not condition:
        raise VerificationError(message)


def mapping(vector: Iterable[float]) -> list[float]:
    """Apply the frozen coordinate transform."""

    x, y, z = (float(value) for value in vector)
    return [x, z, -y]


def check_definition(
    definition: dict[str, Any],
    contract: dict[str, Any],
) -> dict[str, Any]:
    """Verify the complete pre-render freeze and its sample partitions."""

    require(
        definition.get("schema_version")
        == "bf3d.r2t.photometric_fixture_definition.v1",
        "definition schema mismatch",
    )
    require(
        definition.get("requirement_id") == REQUIREMENT_ID,
        "definition requirement mismatch",
    )
    require(
        definition.get("status") == "frozen_before_render",
        "definition is not frozen_before_render",
    )
    coordinate = definition["coordinate_mapping"]
    require(
        coordinate["formula"] == "Blender (x,y,z) -> Three.js (x,z,-y)",
        "coordinate formula mismatch",
    )
    require(
        coordinate["matrix_row_major"]
        == [1.0, 0.0, 0.0, 0.0, 0.0, 1.0, 0.0, -1.0, 0.0],
        "coordinate matrix mismatch",
    )
    require(coordinate["determinant"] == 1.0, "coordinate determinant mismatch")
    three = definition["renderer_contract"]["three"]
    expected_three = {
        "revision": "160",
        "tone_mapping": "THREE.NoToneMapping",
        "exposure": 1.0,
        "render_target": "RGBA32F",
        "msaa": False,
        "samples": 0,
        "dithering": False,
        "post_processing": False,
        "shadows": False,
        "ao": False,
        "extra_gi": False,
    }
    for key, expected in expected_three.items():
        require(three.get(key) == expected, f"Three contract mismatch: {key}")
    require(
        three["engines"] == list(EXPECTED_ENGINES),
        "browser engine list mismatch",
    )
    require(three["fresh_runs_per_engine"] == 2, "fresh-run count mismatch")
    common = definition["renderer_contract"]["common"]
    for key in (
        "scene_linear",
        "one_light_family_at_a_time",
    ):
        require(common[key] is True, f"common contract missing: {key}")
    for key in (
        "shadows",
        "post_processing",
        "ao",
        "extra_gi",
        "beauty_capture",
        "mask_capture",
    ):
        require(common[key] is False, f"common contract must disable: {key}")
    freeze = definition["freeze_protocol"]
    require(
        freeze["definition_written_and_sha256_computed_before_any_renderer"]
        is True,
        "pre-render freeze sequence missing",
    )
    require(
        freeze["fit_three_engine"] == "chromium"
        and freeze["fit_three_run_index"] == 0,
        "canonical fit source changed",
    )
    require(
        freeze["held_out_refit_allowed"] is False,
        "held-out refit must be disabled",
    )
    fit_contract = definition["fit_contract"]
    require(
        fit_contract["method"]
        == "one non-negative weighted least-squares scalar per family",
        "fit method mismatch",
    )
    require(
        fit_contract["zero_denominator_policy"] == "fail_closed",
        "zero-denominator policy mismatch",
    )
    require(
        fit_contract["sun_three_lights_share_one_k"] is True,
        "SUN shared-k rule missing",
    )
    for key in (
        "per_light_refit",
        "per_material_refit",
        "per_shot_refit",
        "per_engine_refit",
        "per_browser_refit",
    ):
        require(fit_contract[key] is False, f"forbidden refit enabled: {key}")

    families = definition["families"]
    require(tuple(families) == EXPECTED_FAMILIES, "family order/set mismatch")
    expected_counts = {
        "sun": {"fit": 12, "held_out": 12},
        "top_area": {"fit": 18, "held_out": 10},
        "world": {"fit": 7, "held_out": 8},
    }
    all_ids: list[str] = []
    partition_counts: dict[str, dict[str, int]] = {}
    mapping_errors = []
    for family in EXPECTED_FAMILIES:
        rows = families[family]["samples"]
        partition_counts[family] = {
            partition: sum(
                row["partition"] == partition for row in rows
            )
            for partition in ("fit", "held_out")
        }
        require(
            partition_counts[family] == expected_counts[family],
            f"{family} sample partition counts changed",
        )
        for row in rows:
            all_ids.append(row["id"])
            for blender_key, three_key in (
                ("blender_surface_normal", "three_surface_normal"),
                ("blender_view_normal", "three_view_normal"),
            ):
                expected_vector = mapping(row[blender_key])
                if any(
                    not close(expected, actual)
                    for expected, actual in zip(
                        expected_vector,
                        row[three_key],
                        strict=True,
                    )
                ):
                    mapping_errors.append(
                        {
                            "sample_id": row["id"],
                            "blender_key": blender_key,
                            "three_key": three_key,
                            "expected": expected_vector,
                            "actual": row[three_key],
                        }
                    )
            if family == "sun":
                expected_direction = mapping(
                    row["blender_propagation_direction"]
                )
                require(
                    all(
                        close(expected, actual)
                        for expected, actual in zip(
                            expected_direction,
                            row["three_propagation_direction"],
                            strict=True,
                        )
                    ),
                    f"SUN direction mapping mismatch: {row['id']}",
                )
            if family == "top_area":
                expected_position = mapping(
                    row["blender_relative_light_position"]
                )
                require(
                    all(
                        close(expected, actual)
                        for expected, actual in zip(
                            expected_position,
                            row["three_relative_light_position"],
                            strict=True,
                        )
                    ),
                    f"TOP position mapping mismatch: {row['id']}",
                )
    require(len(all_ids) == len(set(all_ids)), "duplicate fixture sample IDs")
    require(not mapping_errors, f"coordinate mapping errors: {mapping_errors}")

    sun_fit_dots = sorted(
        {
            row["normal_dot_light"]
            for row in families["sun"]["samples"]
            if row["partition"] == "fit"
        }
    )
    require(
        sun_fit_dots
        == sorted(contract["fit_contract"]["sun_fit"]["normal_dot_light"]),
        "SUN fit n·l values changed",
    )
    sun_light_names = {
        row["light_name"]
        for row in families["sun"]["samples"]
        if row["partition"] == "fit"
    }
    require(
        sun_light_names
        == {
            "P40_NEUTRAL_KEY",
            "P40_NEUTRAL_FILL",
            "P40_NEUTRAL_RIM",
        },
        "SUN fit light set changed",
    )
    area_fit_positions = {
        tuple(row["normalized_patch_xz"])
        for row in families["top_area"]["samples"]
        if row["partition"] == "fit"
    }
    require(
        area_fit_positions
        == {
            tuple(float(value) for value in row)
            for row in contract["fit_contract"]["area_fit"][
                "normalized_patch_xz"
            ]
        },
        "TOP fit normalized patch positions changed",
    )
    area_fit_heights = {
        row["height_over_side"]
        for row in families["top_area"]["samples"]
        if row["partition"] == "fit"
    }
    require(
        area_fit_heights
        == {
            float(value)
            for value in contract["fit_contract"]["area_fit"][
                "height_over_side"
            ]
        },
        "TOP fit height ratios changed",
    )
    board_pairs = {
        (row["material"]["roughness"], row["material"]["metalness"])
        for row in families["world"]["samples"]
        if row["partition"] == "held_out"
    }
    require(
        board_pairs
        == {
            (float(roughness), float(metalness))
            for roughness in contract["fit_contract"]["environment_fit"][
                "held_out_board"
            ]["roughness"]
            for metalness in contract["fit_contract"]["environment_fit"][
                "held_out_board"
            ]["metalness"]
        },
        "WORLD held-out material board changed",
    )
    require(
        definition["acceptance"]["linear_fit_thresholds_pre_registered"]
        is False
        and definition["acceptance"][
            "linear_held_out_thresholds_pre_registered"
        ]
        is False,
        "unregistered linear thresholds were introduced",
    )
    require(
        definition["acceptance"]["numeric_equivalence_auto_approval_allowed"]
        is False,
        "auto approval must remain disabled",
    )
    return {
        "passed": True,
        "sample_count": len(all_ids),
        "partition_counts": partition_counts,
        "sample_ids_sha256": sha256_bytes(
            "\n".join(all_ids).encode("utf-8")
        ),
        "coordinate_mapping_errors": mapping_errors,
    }


def sample_map(rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """Build a unique sample map."""

    result = {row["id"]: row for row in rows}
    require(len(result) == len(rows), "duplicate renderer sample IDs")
    return result


def scalar(row: dict[str, Any]) -> float:
    """Return one finite linear luminance sample."""

    value = float(row["statistics"]["linear_rec709_luminance"])
    require(math.isfinite(value), f"non-finite sample scalar: {row.get('id')}")
    return value


def check_blender(
    definition: dict[str, Any],
    output: dict[str, Any],
    definition_sha: str,
) -> dict[str, Any]:
    """Verify Cycles reference and Eevee held-out completeness."""

    require(
        output.get("schema_version")
        == "bf3d.r2t.blender_linear_reference.v1",
        "Blender reference schema mismatch",
    )
    require(
        output.get("status") == "reference_evaluated"
        and output.get("evaluated") is True
        and output.get("passed") is True,
        "Blender reference is incomplete",
    )
    require(
        output["definition"]["sha256"] == definition_sha,
        "Blender definition SHA mismatch",
    )
    require(
        output["runtime"]["blender_version"].startswith("5.2."),
        "Blender runtime is not 5.2",
    )
    require(output["runtime"]["background"] is True, "Blender was not background")
    require(
        output["contract"]["cycles_is_only_fit_reference"] is True
        and output["contract"]["eevee_board_is_held_out"] is True,
        "Blender fit/held-out engine contract changed",
    )
    require(
        output["contract"]["beauty_capture"] is False
        and output["contract"]["mask_capture"] is False,
        "Blender claims an image capture",
    )
    require(not output["not_evaluated"], "Blender has not-evaluated samples")
    require(not output["errors"], "Blender reference contains errors")
    expected_ids = {
        row["id"]
        for family in definition["families"].values()
        for row in family["samples"]
    }
    cycles = sample_map(output["cycles_samples"])
    require(set(cycles) == expected_ids, "Cycles sample set mismatch")
    expected_board = {
        row["id"]
        for row in definition["families"]["world"]["samples"]
        if row["partition"] == "held_out"
        and row["material_kind"] == "principled_board"
    }
    eevee = sample_map(output["eevee_held_out_samples"])
    require(set(eevee) == expected_board, "Eevee board sample set mismatch")
    for row in cycles.values():
        require(row["engine"] == "CYCLES", "non-Cycles fit reference found")
        require(
            row["active_light_family"] == row["family"],
            f"Blender family mismatch: {row['id']}",
        )
        require(
            len(row["active_lights"]) <= 1
            and row["other_light_family_count"] == 0,
            f"Blender mixed light families: {row['id']}",
        )
        require(row["shadows"] is False, "Blender shadow enabled")
        require(row["post_processing"] is False, "Blender post enabled")
        scalar(row)
    for row in eevee.values():
        require(
            row["engine"] == "BLENDER_EEVEE",
            "unexpected Eevee held-out engine",
        )
        scalar(row)
    return {
        "passed": True,
        "cycles_sample_count": len(cycles),
        "eevee_held_out_sample_count": len(eevee),
        "cycles_samples": cycles,
        "eevee_samples": eevee,
    }


def check_three(
    definition: dict[str, Any],
    output: dict[str, Any],
    definition_sha: str,
) -> dict[str, Any]:
    """Verify all Three r160 fresh browser runs and isolation."""

    require(
        output.get("schema_version")
        == "bf3d.r2t.three_linear_readback.v1",
        "Three readback schema mismatch",
    )
    require(
        output.get("status") == "linear_readback_evaluated"
        and output.get("evaluated") is True
        and output.get("passed") is True,
        "Three readback is incomplete",
    )
    require(
        output["definition"]["sha256"] == definition_sha,
        "Three definition SHA mismatch",
    )
    require(output["source_integrity"]["passed"] is True, "Three source mismatch")
    require(
        output["contract"]["fit_engine"] == "chromium"
        and output["contract"]["fit_run_index"] == 0
        and output["contract"]["per_browser_refit"] is False,
        "Three fit-source contract changed",
    )
    require(not output["not_evaluated"], "Three has not-evaluated runs")
    require(not output["errors"], "Three output contains errors")
    runs = output["runs"]
    require(len(runs) == 6, "Three must contain six fresh browser runs")
    expected_ids = {
        row["id"]
        for family in definition["families"].values()
        for row in family["samples"]
    }
    run_maps: dict[tuple[str, int], dict[str, dict[str, Any]]] = {}
    run_pmrem: dict[tuple[str, int], dict[str, Any]] = {}
    run_family_signals: dict[
        tuple[str, int], dict[str, dict[str, Any]]
    ] = {}
    for engine in EXPECTED_ENGINES:
        engine_runs = [row for row in runs if row["engine"] == engine]
        require(len(engine_runs) == 2, f"{engine} fresh-run count mismatch")
        require(
            {row["run_index"] for row in engine_runs} == {0, 1},
            f"{engine} run indices mismatch",
        )
    for run in runs:
        key = (run["engine"], int(run["run_index"]))
        require(
            run["evaluated"] is True
            and run["passed"] is True
            and run["status"] == "evaluated",
            f"Three run failed: {key}",
        )
        require(
            not run["console_errors"]
            and not run["page_errors"]
            and not run["http_errors"]
            and not run["external_requests"]
            and not run["cleanup_errors"]
            and not run["errors"],
            f"Three run contains runtime errors: {key}",
        )
        require(
            run["isolation"]["production_assets_not_loaded"] is True
            and run["isolation"]["production_mutation_performed"] is False,
            f"Three production isolation failed: {key}",
        )
        page = run["page_result"]
        require(
            page["runtime"]["three_revision"] == "160"
            and page["runtime"]["webgl2"] is True
            and page["runtime"]["ext_color_buffer_float"] is True
            and page["runtime"]["ltc_float_texture_ready"] is True,
            f"Three runtime prerequisite failed: {key}",
        )
        sample_rows = sample_map(page["samples"])
        require(set(sample_rows) == expected_ids, f"Three sample set mismatch: {key}")
        for row in sample_rows.values():
            renderer = row["renderer"]
            require(
                renderer["tone_mapping"] == renderer["expected_tone_mapping"],
                f"Three tone mapping mismatch: {row['id']}",
            )
            require(
                renderer["tone_mapping_exposure"] == 1.0
                and renderer["output_color_space"] == "srgb-linear"
                and renderer["render_target_type"] == "FloatType"
                and renderer["render_target_samples"] == 0,
                f"Three linear target mismatch: {row['id']}",
            )
            for flag in (
                "shadows",
                "antialias",
                "dithering",
                "post_processing",
                "ao",
                "extra_gi",
            ):
                require(
                    renderer[flag] is False,
                    f"Three forbidden renderer flag {flag}: {row['id']}",
                )
            require(
                len(row["active_lights"]) <= 1
                and row["other_light_family_count"] == 0
                and row["active_light_family"] == row["family"],
                f"Three mixed family: {row['id']}",
            )
            scalar(row)
        independent = run["independent_evaluation"]
        require(
            independent["passed"] is True
            and independent["family_signal_contracts_pass"] is True
            and independent["world_pmrem_contract_pass"] is True,
            f"Three independent family/PMREM audit failed: {key}",
        )
        recomputed_signals: dict[str, dict[str, Any]] = {}
        for family in EXPECTED_FAMILIES:
            fit_rows = [
                row
                for row in definition["families"][family]["samples"]
                if row["partition"] == "fit"
            ]
            values = [scalar(sample_rows[row["id"]]) for row in fit_rows]
            denominator = sum(
                float(row["weight"]) * value * value
                for row, value in zip(fit_rows, values, strict=True)
            )
            stored_signal = independent["family_signal_summary"][family]
            require(
                stored_signal["passed"] is True
                and stored_signal["sample_count"] == len(values)
                and stored_signal["finite_sample_count"] == len(values)
                and stored_signal["positive_sample_count"]
                == sum(value > 0.0 for value in values)
                and close(stored_signal["min_three_k1"], min(values))
                and close(stored_signal["max_three_k1"], max(values))
                and close(
                    stored_signal["mean_three_k1"],
                    statistics.fmean(values),
                )
                and close(
                    stored_signal["weighted_wls_denominator"],
                    denominator,
                )
                and denominator > DENOMINATOR_EPSILON,
                f"Three {family} signal summary mismatch: {key}",
            )
            recomputed_signals[family] = {
                "sample_count": len(values),
                "positive_sample_count": sum(
                    value > 0.0 for value in values
                ),
                "min_three_k1": min(values),
                "max_three_k1": max(values),
                "mean_three_k1": statistics.fmean(values),
                "weighted_wls_denominator": denominator,
            }
        pmrem = independent["world_pmrem"]
        require(
            pmrem["implementation"]
            == (
                "constant Linear-sRGB Float32 equirectangular texture "
                "through PMREM"
            )
            and pmrem["radiance_linear_rgb"]
            == definition["families"]["world"]["radiance_linear_rgb"]
            and pmrem["source_resolution"] == [64, 32]
            and pmrem["source_type"] == "FloatType"
            and pmrem["source_color_space"] == "srgb-linear"
            and pmrem["cube_size"] == 16
            and pmrem["three_r160_lod_min"] == 4
            and pmrem["minimum_cube_size"] == 16
            and pmrem["minimum_equirectangular_width"] == 64
            and pmrem["ambient_light_substitution"] is False
            and pmrem["used_for_fit_and_held_out"] is True,
            f"Three WORLD PMREM prerequisite mismatch: {key}",
        )
        run_maps[key] = sample_rows
        run_pmrem[key] = pmrem
        run_family_signals[key] = recomputed_signals
    return {
        "passed": True,
        "run_count": len(runs),
        "sample_count_per_run": len(expected_ids),
        "run_samples": run_maps,
        "run_pmrem": run_pmrem,
        "family_signal_summary_by_run": {
            f"{engine}#{run_index}": summaries
            for (engine, run_index), summaries in run_family_signals.items()
        },
    }


def recompute_wls(
    definition: dict[str, Any],
    family: str,
    blender: dict[str, dict[str, Any]],
    three: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    """Recompute one non-negative family scalar from fit rows only."""

    rows = [
        row
        for row in definition["families"][family]["samples"]
        if row["partition"] == "fit"
    ]
    numerator = 0.0
    denominator = 0.0
    for row in rows:
        weight = float(row["weight"])
        target = scalar(three[row["id"]])
        reference = scalar(blender[row["id"]])
        numerator += weight * target * reference
        denominator += weight * target * target
    require(
        math.isfinite(denominator) and denominator > DENOMINATOR_EPSILON,
        f"{family} WLS denominator fails closed",
    )
    unconstrained = numerator / denominator
    return {
        "fit_sample_ids": [row["id"] for row in rows],
        "numerator": numerator,
        "denominator": denominator,
        "unconstrained_scalar": unconstrained,
        "non_negative_scalar": max(0.0, unconstrained),
    }


def check_fit_report(
    definition: dict[str, Any],
    contract: dict[str, Any],
    fit_report: dict[str, Any],
    blender_samples: dict[str, dict[str, Any]],
    three_runs: dict[tuple[str, int], dict[str, dict[str, Any]]],
    three_pmrem_runs: dict[tuple[str, int], dict[str, Any]],
) -> dict[str, Any]:
    """Recompute WLS and every stored browser residual."""

    require(
        fit_report.get("schema_version")
        == "bf3d.r2t.photometric_fit_held_out_report.v1",
        "fit report schema mismatch",
    )
    require(
        fit_report.get("status")
        == "evaluated_candidate_not_approved_no_acceptance_thresholds"
        and fit_report.get("evaluation_complete") is True
        and fit_report.get("passed") is False,
        "fit report classification mismatch",
    )
    classification = fit_report["classification"]
    require(
        classification["fit_executed"] is True
        and classification["held_out_executed"] is True
        and classification["linear_thresholds_pre_registered"] is False
        and classification["photometric_equivalence_approved"] is False
        and classification["capture_eligible"] is False
        and classification["production_integration_allowed"] is False
        and classification["beauty_capture_performed"] is False
        and classification["mask_capture_performed"] is False,
        "fit report approval boundary changed",
    )
    require(not fit_report["not_evaluated"], "fit report has not-evaluated blocks")
    canonical_three = three_runs[("chromium", 0)]
    recomputed: dict[str, dict[str, Any]] = {}
    for family in EXPECTED_FAMILIES:
        actual = recompute_wls(
            definition,
            family,
            blender_samples,
            canonical_three,
        )
        stored = fit_report["fit_results"][family]
        require(
            stored["fit_source_three_engine"] == "chromium"
            and stored["fit_source_three_run_index"] == 0,
            f"{family} fit source changed",
        )
        require(
            stored["held_out_sample_ids_used"] == [],
            f"{family} held-out data entered fit",
        )
        require(
            stored["fit_sample_ids"] == actual["fit_sample_ids"],
            f"{family} fit sample IDs changed",
        )
        for key in (
            "numerator",
            "denominator",
            "unconstrained_scalar",
            "non_negative_scalar",
        ):
            require(
                close(stored[key], actual[key]),
                f"{family} stored WLS {key} mismatch",
            )
        require(
            stored["denominator"] > stored["denominator_epsilon"],
            f"{family} stored denominator fails closed",
        )
        fit_values = [
            scalar(canonical_three[sample_id])
            for sample_id in actual["fit_sample_ids"]
        ]
        stored_signal = stored["canonical_three_signal_summary"]
        top_level_signal = fit_report[
            "canonical_three_family_signal_summary"
        ][family]
        require(
            stored_signal == top_level_signal
            and stored_signal["engine"] == "chromium"
            and stored_signal["run_index"] == 0
            and stored_signal["partition"] == "fit"
            and stored_signal["sample_count"] == len(fit_values)
            and stored_signal["positive_sample_count"]
            == sum(value > 0.0 for value in fit_values)
            and close(stored_signal["min_three_k1"], min(fit_values))
            and close(stored_signal["max_three_k1"], max(fit_values))
            and close(
                stored_signal["mean_three_k1"],
                statistics.fmean(fit_values),
            )
            and close(
                stored_signal["weighted_wls_denominator"],
                actual["denominator"],
            )
            and stored_signal["passed"] is True,
            f"{family} canonical Three signal summary mismatch",
        )
        recomputed[family] = actual

    evaluations = fit_report["browser_evaluations"]
    require(len(evaluations) == 36, "browser evaluation group count mismatch")
    expected_groups = {
        (family, partition, engine, run_index)
        for family in EXPECTED_FAMILIES
        for partition in ("fit", "held_out")
        for engine in EXPECTED_ENGINES
        for run_index in (0, 1)
    }
    actual_groups = {
        (
            item["family"],
            item["partition"],
            item["three_engine"],
            int(item["three_run_index"]),
        )
        for item in evaluations
    }
    require(actual_groups == expected_groups, "browser evaluation groups changed")
    for item in evaluations:
        family = item["family"]
        partition = item["partition"]
        engine = item["three_engine"]
        run_index = int(item["three_run_index"])
        require(item["refit_performed"] is False, "browser refit was performed")
        k = recomputed[family]["non_negative_scalar"]
        source_rows = three_runs[(engine, run_index)]
        expected_ids = [
            row["id"]
            for row in definition["families"][family]["samples"]
            if row["partition"] == partition
        ]
        stored_ids = [row["sample_id"] for row in item["rows"]]
        require(stored_ids == expected_ids, "evaluation row IDs changed")
        for row in item["rows"]:
            sample_id = row["sample_id"]
            reference = scalar(blender_samples[sample_id])
            target = scalar(source_rows[sample_id])
            scaled = k * target
            residual = scaled - reference
            relative = abs(residual) / max(abs(reference), 1e-12)
            require(
                close(row["k_from_chromium_run_0"], k)
                and close(row["blender_cycles"], reference)
                and close(row["three_k1"], target)
                and close(row["three_scaled"], scaled)
                and close(row["residual"], residual)
                and close(row["absolute_relative_residual"], relative),
                f"stored evaluation row mismatch: {sample_id}",
            )
        require(
            item["metrics"]["status"]
            == "evaluated_no_pre_registered_acceptance_threshold"
            and item["metrics"]["threshold"] is None
            and item["metrics"]["equivalence_pass_claimed"] is False,
            "evaluation metric classification changed",
        )

    eevee = fit_report["eevee_world_board_held_out"]
    require(
        eevee["partition"] == "held_out"
        and eevee["refit_performed"] is False
        and len(eevee["rows"]) == 8,
        "Eevee held-out board contract mismatch",
    )
    world_audit = fit_report["world_pmrem_runtime_audit"]
    require(
        world_audit["status"] == "evaluated"
        and world_audit["passed"] is True
        and world_audit["frozen_radiance_linear_rgb"]
        == definition["families"]["world"]["radiance_linear_rgb"]
        and world_audit["sampling_implementation_fix_only"] is True
        and world_audit["radiance_changed"] is False
        and world_audit["sample_definition_changed"] is False
        and world_audit["partition_or_weight_changed"] is False
        and world_audit["threshold_changed"] is False
        and world_audit["fit_rule_changed"] is False,
        "WORLD PMREM sampling-fix boundary changed",
    )
    failure = world_audit["failure_evidence_before_fix"]
    implementation = world_audit["implemented_sampling_prerequisite"]
    require(
        failure["source_resolution"] == [16, 8]
        and failure["derived_cube_size"] == 4
        and failure["three_r160_lod_min"] == 4
        and failure["minimum_cube_size"] == 16
        and failure["world_wls_denominator"] == 0.0
        and implementation["source_resolution"] == [64, 32]
        and implementation["derived_cube_size"] == 16
        and implementation["three_r160_lod_min"] == 4
        and implementation["minimum_cube_size"] == 16
        and implementation["constant_float32_equirectangular"] is True
        and implementation["pmrem_to_scene_environment"] is True
        and implementation["ambient_light_substitution"] is False,
        "WORLD PMREM minimum-LOD evidence mismatch",
    )
    require(
        len(world_audit["runs"]) == 6,
        "WORLD PMREM browser audit run count mismatch",
    )
    observed_world_keys = set()
    for run in world_audit["runs"]:
        key = (run["engine"], int(run["run_index"]))
        observed_world_keys.add(key)
        raw_pmrem = three_pmrem_runs[key]
        world_rows = [
            row
            for row in three_runs[key].values()
            if row["family"] == "world"
        ]
        world_values = [scalar(row) for row in world_rows]
        world_held_out_values = [
            scalar(row)
            for row in world_rows
            if row["partition"] == "held_out"
        ]
        all_signal = run["all_world_signal"]
        held_out_signal = run["held_out_world_signal"]
        require(
            run["passed"] is True
            and run["radiance_linear_rgb"]
            == raw_pmrem["radiance_linear_rgb"]
            and run["source_resolution"]
            == raw_pmrem["source_resolution"]
            and run["cube_size"] == raw_pmrem["cube_size"]
            and run["three_r160_lod_min"]
            == raw_pmrem["three_r160_lod_min"]
            and run["ambient_light_substitution"] is False
            and run["fit_signal"]["passed"] is True
            and run["fit_signal"]["weighted_wls_denominator"]
            > DENOMINATOR_EPSILON,
            f"WORLD PMREM stored browser audit mismatch: {key}",
        )
        require(
            all_signal["sample_count"] == len(world_values)
            and all_signal["positive_sample_count"]
            == sum(value > 0.0 for value in world_values)
            and close(all_signal["min_three_k1"], min(world_values))
            and close(all_signal["max_three_k1"], max(world_values))
            and close(
                all_signal["mean_three_k1"],
                statistics.fmean(world_values),
            )
            and held_out_signal["sample_count"]
            == len(world_held_out_values)
            and held_out_signal["positive_sample_count"]
            == sum(value > 0.0 for value in world_held_out_values)
            and close(
                held_out_signal["min_three_k1"],
                min(world_held_out_values),
            )
            and close(
                held_out_signal["max_three_k1"],
                max(world_held_out_values),
            )
            and close(
                held_out_signal["mean_three_k1"],
                statistics.fmean(world_held_out_values),
            ),
            f"WORLD PMREM all/held-out range mismatch: {key}",
        )
    require(
        observed_world_keys == set(three_pmrem_runs),
        "WORLD PMREM browser audit key set mismatch",
    )
    top_basis = fit_report["top_rect_area_basis_audit"]
    expected_basis = {
        "x": [1.0, 0.0, 0.0],
        "y": [0.0, 0.0, -1.0],
        "z": [0.0, 1.0, 0.0],
        "emission_direction": [0.0, -1.0, 0.0],
    }
    require(
        top_basis["status"] == "evaluated"
        and top_basis["expected"] == expected_basis
        and top_basis["all_runs_passed"] is True
        and len(top_basis["runs"]) == 6,
        "TOP basis audit is incomplete",
    )
    for run in top_basis["runs"]:
        require(
            run["diagnostic_used_for_fit_or_held_out"] is False
            and run["passed"] is True
            and run["max_abs_error"] <= 1e-12,
            "TOP basis diagnostic failed or entered fit",
        )
        for key, expected_vector in expected_basis.items():
            require(
                all(
                    close(actual, expected)
                    for actual, expected in zip(
                        run["observed"][key],
                        expected_vector,
                        strict=True,
                    )
                ),
                f"TOP observed basis mismatch: {run['engine']}#{run['run_index']}",
            )
    disk_square = fit_report["disk_square_spatial_residual"]
    require(
        disk_square["status"] == "evaluated_known_non_equivalence"
        and disk_square["shape_mapping"]
        == "Blender DISK -> equal-area Three square"
        and disk_square["analytic_equivalence_claimed"] is False,
        "disk-square residual classification mismatch",
    )
    require(
        disk_square["fit_partition"]["metrics"]["sample_count"] == 18
        and disk_square["held_out_partition"]["metrics"]["sample_count"] == 10,
        "disk-square residual sample counts changed",
    )
    expected_non_equivalence = contract["known_non_equivalence"]
    require(
        fit_report["known_non_equivalence"] == expected_non_equivalence,
        "known non-equivalence list changed",
    )
    guardrails = fit_report["guardrails"]
    require(
        guardrails["one_k_per_family"] is True
        and guardrails["all_three_suns_share_one_k"] is True,
        "family-level scalar guardrail changed",
    )
    for key in (
        "per_light_refit",
        "per_material_refit",
        "per_shot_refit",
        "per_engine_refit",
        "per_browser_refit",
        "held_out_refit",
        "threshold_relaxation",
        "production_scene_mutation",
        "production_renderer_mutation",
        "production_material_mutation",
        "beauty_capture",
    ):
        require(guardrails[key] is False, f"forbidden action enabled: {key}")
    return {
        "passed": True,
        "recomputed_fit_results": recomputed,
        "browser_evaluation_groups": len(evaluations),
        "eevee_held_out_samples": len(eevee["rows"]),
        "canonical_three_family_signal_summary": fit_report[
            "canonical_three_family_signal_summary"
        ],
        "world_pmrem_runtime_audit": {
            key: value
            for key, value in world_audit.items()
            if key != "runs"
        },
        "disk_square_fit_metrics": disk_square["fit_partition"]["metrics"],
        "disk_square_held_out_metrics": disk_square["held_out_partition"][
            "metrics"
        ],
    }


def check_build_report(build: dict[str, Any]) -> dict[str, Any]:
    """Verify the build recorded every block and actual subprocess command."""

    require(
        build.get("schema_version")
        == "bf3d.r2t.photometric_fixture_build_report.v1",
        "build report schema mismatch",
    )
    require(
        build.get("status") == "fixture_evaluated_candidate_not_approved"
        and build.get("fixture_execution_complete") is True
        and build.get("passed") is True,
        "build execution is incomplete",
    )
    require(not build["not_evaluated"], "build report has not-evaluated blocks")
    require(not build["errors"], "build report contains errors")
    require(
        len(build["commands"]) == 2
        and {item["id"] for item in build["commands"]}
        == {"blender_reference", "three_linear_readback"},
        "build command evidence missing",
    )
    for command in build["commands"]:
        require(
            command["exit_code"] == 0
            and command["timed_out"] is False
            and command["passed"] is True,
            f"build command failed: {command['id']}",
        )
    for block_name, block in build["blocks"].items():
        require(
            block["evaluated"] is True and block["passed"] is True,
            f"build block incomplete: {block_name}",
        )
    classification = build["classification"]
    require(
        classification["photometric_equivalence_approved"] is False
        and classification["capture_eligible"] is False
        and classification["approval_granted"] is False
        and classification["production_integration_allowed"] is False
        and classification["beauty_capture_performed"] is False
        and classification["mask_capture_performed"] is False,
        "build approval boundary changed",
    )
    return {
        "passed": True,
        "block_count": len(build["blocks"]),
        "command_results": [
            {
                "id": command["id"],
                "argv": command["argv"],
                "exit_code": command["exit_code"],
                "timed_out": command["timed_out"],
            }
            for command in build["commands"]
        ],
    }


def check_ltc(report: dict[str, Any]) -> dict[str, Any]:
    """Verify the TOP runtime prerequisite remains candidate-only."""

    require(
        report.get("schema_version")
        == "bf3d.r2t.ltc_runtime_oracle_report.v1",
        "LTC report schema mismatch",
    )
    require(
        report.get("status")
        == "runtime_prerequisite_verified_candidate_not_approved"
        and report.get("passed") is True,
        "LTC runtime prerequisite is not verified",
    )
    classification = report["classification"]
    require(
        classification["runtime_prerequisite_verified"] is True
        and classification["capture_eligible"] is False
        and classification["approval_granted"] is False
        and classification["blender_photometric_equivalence_claimed"] is False
        and classification["rect_area_light_shadow_claimed"] is False,
        "LTC candidate-only boundary changed",
    )
    return {
        "passed": True,
        "status": report["status"],
        "evaluated_runs": report["summary"]["evaluated_runs"],
        "passed_runs": report["summary"]["passed_runs"],
        "candidate_only": True,
    }


def check_no_beauty_outputs() -> dict[str, Any]:
    """Fail if the isolated fixture contains any image/beauty artifact."""

    images = [
        path.relative_to(REPO_ROOT).as_posix()
        for path in FIXTURE_ROOT.rglob("*")
        if path.is_file() and path.suffix.lower() in IMAGE_SUFFIXES
    ]
    require(not images, f"beauty/image outputs are forbidden: {images}")
    return {
        "passed": True,
        "image_output_count": 0,
        "beauty_capture_performed": False,
        "mask_capture_performed": False,
    }


def parse_args() -> argparse.Namespace:
    """Parse verifier CLI options."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--json",
        action="store_true",
        help="Print the complete verification report to stdout.",
    )
    return parser.parse_args()


def main() -> int:
    """Run all independent checks and write their hashes and commands."""

    args = parse_args()
    report: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "requirement_id": REQUIREMENT_ID,
        "stage_id": STAGE_ID,
        "generated_at": utc_now(),
        "status": "running",
        "verification_passed": False,
        "passed": False,
        "classification": {
            "verified_subject": "candidate_evidence_integrity_only",
            "photometric_equivalence_approved": False,
            "capture_eligible": False,
            "approval_granted": False,
            "production_integration_allowed": False,
            "beauty_capture_performed": False,
            "mask_capture_performed": False,
        },
        "checks": {},
        "commands": {
            "build": "python tools\\build_bf3d_r2t_photometric_fixture.py",
            "verify": "python tools\\verify_bf3d_r2t_photometric_fixture.py",
            "syntax": (
                "python -m py_compile "
                "tools\\build_bf3d_r2t_photometric_fixture.py "
                "tools\\verify_bf3d_r2t_photometric_fixture.py "
                "PT\\高炉3D模型\\work\\WEB_60_20260720_R2T_"
                "OCIO_PHOTOMETRIC_EQUIVALENCE\\photometric_fixture\\"
                "blender_reference.py"
            ),
            "node_syntax": (
                "node --check "
                "tools\\build_bf3d_r2t_photometric_fixture.cjs"
            ),
        },
        "artifacts": {},
        "errors": [],
    }
    exit_code = 1
    try:
        required_paths = [
            CONTRACT_PATH,
            DEFINITION_PATH,
            BLENDER_OUTPUT_PATH,
            THREE_OUTPUT_PATH,
            FIT_REPORT_PATH,
            BUILD_REPORT_PATH,
            LTC_REPORT_PATH,
        ]
        missing = [path.as_posix() for path in required_paths if not path.is_file()]
        require(not missing, f"required artifacts missing: {missing}")
        contract = read_json(CONTRACT_PATH)
        definition = read_json(DEFINITION_PATH)
        blender = read_json(BLENDER_OUTPUT_PATH)
        three = read_json(THREE_OUTPUT_PATH)
        fit_report = read_json(FIT_REPORT_PATH)
        build_report = read_json(BUILD_REPORT_PATH)
        ltc_report = read_json(LTC_REPORT_PATH)
        definition_sha = inspect_file(DEFINITION_PATH)["sha256"]
        require(
            definition["source_contract"]["sha256"]
            == inspect_file(CONTRACT_PATH)["sha256"],
            "definition source contract SHA mismatch",
        )
        report["checks"]["definition"] = check_definition(
            definition,
            contract,
        )
        report["checks"]["ltc_prerequisite"] = check_ltc(ltc_report)
        blender_check = check_blender(
            definition,
            blender,
            definition_sha,
        )
        report["checks"]["blender_reference"] = {
            key: value
            for key, value in blender_check.items()
            if key not in {"cycles_samples", "eevee_samples"}
        }
        three_check = check_three(
            definition,
            three,
            definition_sha,
        )
        report["checks"]["three_linear_readback"] = {
            key: value
            for key, value in three_check.items()
            if key not in {"run_samples", "run_pmrem"}
        }
        report["checks"]["fit_and_held_out"] = check_fit_report(
            definition,
            contract,
            fit_report,
            blender_check["cycles_samples"],
            three_check["run_samples"],
            three_check["run_pmrem"],
        )
        report["checks"]["build_report"] = check_build_report(build_report)
        report["checks"]["no_beauty_outputs"] = check_no_beauty_outputs()
        artifact_paths = {
            "photometric_contract": CONTRACT_PATH,
            "fixture_definition": DEFINITION_PATH,
            "blender_linear_reference": BLENDER_OUTPUT_PATH,
            "three_linear_readback": THREE_OUTPUT_PATH,
            "photometric_fit_held_out_report": FIT_REPORT_PATH,
            "photometric_fixture_build_report": BUILD_REPORT_PATH,
            "ltc_runtime_oracle_report_read_only_prerequisite": LTC_REPORT_PATH,
            "build_tool": REPO_ROOT
            / "tools"
            / "build_bf3d_r2t_photometric_fixture.py",
            "browser_runner": REPO_ROOT
            / "tools"
            / "build_bf3d_r2t_photometric_fixture.cjs",
            "verify_tool": Path(__file__).resolve(),
            "blender_fixture_script": FIXTURE_ROOT / "blender_reference.py",
            "three_fixture_oracle": FIXTURE_ROOT / "web" / "oracle.js",
        }
        report["artifacts"] = {
            key: inspect_file(path) for key, path in artifact_paths.items()
        }
        report["verification_passed"] = all(
            check.get("passed") is True
            for check in report["checks"].values()
        )
        report["passed"] = report["verification_passed"]
        report["status"] = (
            "candidate_evidence_verified_not_approved"
            if report["passed"]
            else "candidate_evidence_verification_failed_closed"
        )
        exit_code = 0 if report["passed"] else 1
    except Exception as exc:  # noqa: BLE001 - fail-closed report is required
        report["status"] = "candidate_evidence_verification_failed_closed"
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
        write_json(VERIFICATION_REPORT_PATH, report)
        summary = report if args.json else {
            "status": report["status"],
            "verification_passed": report["verification_passed"],
            "photometric_equivalence_approved": report["classification"][
                "photometric_equivalence_approved"
            ],
            "capture_eligible": report["classification"]["capture_eligible"],
            "checks": {
                key: value.get("passed")
                for key, value in report["checks"].items()
            },
            "report": VERIFICATION_REPORT_PATH.relative_to(REPO_ROOT).as_posix(),
            "errors": report["errors"],
        }
        print(json.dumps(summary, ensure_ascii=False, indent=2))
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
