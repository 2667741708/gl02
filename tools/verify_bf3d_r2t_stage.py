#!/usr/bin/env python3
"""Fail-closed verifier for the WEB-60 R2T OCIO/photometry pre-capture stage."""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
STAGE = (
    ROOT
    / "PT"
    / "高炉3D模型"
    / "work"
    / "WEB_60_20260720_R2T_OCIO_PHOTOMETRIC_EQUIVALENCE"
)


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def load_json(path: Path) -> dict[str, Any]:
    require(path.is_file(), f"missing JSON: {path}")
    value = json.loads(path.read_text(encoding="utf-8"))
    require(isinstance(value, dict), f"JSON root must be an object: {path}")
    return value


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def resolve_locked_path(value: str) -> Path:
    path = Path(value)
    return path if path.is_absolute() else ROOT / path


def verify_identity(
    path: Path, expected_bytes: int, expected_sha256: str, label: str
) -> dict[str, Any]:
    require(path.is_file(), f"{label} is missing: {path}")
    actual_bytes = path.stat().st_size
    actual_sha256 = sha256(path)
    require(
        actual_bytes == expected_bytes,
        f"{label} bytes mismatch: {actual_bytes} != {expected_bytes}",
    )
    require(
        actual_sha256 == expected_sha256,
        f"{label} SHA-256 mismatch: {actual_sha256} != {expected_sha256}",
    )
    return {
        "path": str(path),
        "bytes": actual_bytes,
        "sha256": actual_sha256,
    }


def verify_input_lock() -> dict[str, Any]:
    lock = load_json(STAGE / "input_lock.json")
    require(lock["schema_version"] == "bf3d.r2t.input_lock.v1", "input lock schema")
    require(lock["stage_id"] == "WEB-60_R2T", "input lock stage")
    entries = lock.get("entries")
    require(isinstance(entries, list), "input lock entries must be a list")
    require(lock.get("entry_count") == 19, "input lock declared count")
    require(len(entries) == 19, "input lock actual count")
    ids = [entry.get("id") for entry in entries]
    require(len(ids) == len(set(ids)), "input lock IDs must be unique")

    verified = []
    for entry in entries:
        require(
            set(entry) >= {"id", "path", "bytes", "sha256"},
            f"incomplete input lock entry: {entry}",
        )
        require(
            isinstance(entry["bytes"], int) and entry["bytes"] >= 0,
            f"invalid bytes for {entry['id']}",
        )
        require(
            isinstance(entry["sha256"], str) and len(entry["sha256"]) == 64,
            f"invalid SHA-256 for {entry['id']}",
        )
        identity = verify_identity(
            resolve_locked_path(entry["path"]),
            entry["bytes"],
            entry["sha256"],
            f"input lock {entry['id']}",
        )
        identity["id"] = entry["id"]
        verified.append(identity)

    return {
        "entry_count": len(verified),
        "all_match": True,
        "ids": ids,
    }


def verify_color_candidate() -> dict[str, Any]:
    color = load_json(STAGE / "color_management_candidate.json")
    require(
        color["schema_version"] == "bf3d.r2t.color_management_candidate.v1",
        "color candidate schema",
    )
    require(
        color["status"]
        == "exact_webgl_failed_uniform_portability_candidate_verified_not_approved",
        "color candidate WebGL status",
    )
    require(color["approved_for_webgl_capture"] is False, "WebGL approval false")
    require(color["approved_for_production_runtime"] is False, "production false")
    require(color["capture_eligible"] is False, "color capture eligibility false")
    require(
        color["processor_contract"]["cache_id"]
        == "cb6dc6defbf01d33b84718a55c277f0a",
        "OCIO cache ID",
    )
    require(
        color["processor_contract"]["output"]
        == "display-encoded sRGB including the final OCIO moncurve OETF",
        "OCIO encoded output contract",
    )
    require(
        color["processor_contract"]["double_srgb_oetf_forbidden"] is True,
        "double OETF guard",
    )
    require(
        color["final_pass_contract"]["renderer_tone_mapping"]
        == "THREE.NoToneMapping",
        "NoToneMapping contract",
    )
    require(
        color["final_pass_contract"]["material"] == "THREE.RawShaderMaterial",
        "RawShaderMaterial contract",
    )
    require(color["license"]["license_pending"] is True, "license must be pending")
    require(
        color["license"]["web_distribution_allowed"] is False,
        "distribution must be blocked",
    )
    webgl = color["webgl_acceptance"]
    require(
        webgl["status"]
        == "evaluated_exact_hard_gate_failed_uniform_candidate_passed_not_approved",
        "WebGL oracle evaluated status",
    )
    require(webgl["expected_exit_code"] == 1, "WebGL expected blocked exit code")
    require(
        webgl["exact_generated_shader"]["status"] == "failed_hard_gate",
        "exact WebGL hard gate",
    )
    require(
        webgl["exact_generated_shader"]["passed_engines"] == 2
        and webgl["exact_generated_shader"]["failed_engines"] == 1,
        "exact WebGL engine count",
    )
    require(
        webgl["exact_generated_shader"]["firefox_failed_point_ids"] == ["black"],
        "exact Firefox failed point",
    )
    require(
        webgl["literal_nextafter_candidate"]["status"]
        == "failed_candidate_not_approved"
        and webgl["literal_nextafter_candidate"]["approval_status"]
        == "candidate_not_approved",
        "literal portability candidate status",
    )
    require(
        webgl["uniform_nextafter_candidate"]["status"]
        == "passed_candidate_not_approved"
        and webgl["uniform_nextafter_candidate"]["approval_status"]
        == "candidate_not_approved",
        "uniform portability candidate status",
    )
    require(
        webgl["uniform_nextafter_candidate"]["passed_engines"] == 3
        and webgl["uniform_nextafter_candidate"]["may_override_exact_hard_gate"]
        is False,
        "uniform candidate engine result and hard-gate boundary",
    )
    require(
        all(value is False for value in webgl["isolation"].values() if isinstance(value, bool)),
        "WebGL production isolation booleans",
    )
    require(
        webgl["not_evaluated_blocks_capture"] is True
        and webgl["exact_failure_blocks_capture"] is True
        and webgl["candidate_not_approved_blocks_runtime_selection"] is True,
        "WebGL not-evaluated policy",
    )
    require(
        color["cpu_verification"]["oracle_count"] == 8,
        "CPU oracle count",
    )
    require(
        color["cpu_verification"]["all_checks_pass"] is True,
        "CPU oracle status",
    )

    generated = color["generated_assets"]
    expected_assets = [
        generated["manifest"],
        generated["shader"],
        generated["lut_37_rgb32f"],
        generated["lut_37_rgba32f"],
        generated["lut_57_rgb32f"],
        generated["lut_57_rgba32f"],
    ]
    verified = []
    for entry in expected_assets:
        path_value = entry["path"]
        if path_value.startswith("generated/"):
            path = STAGE / path_value
        else:
            path = STAGE / "generated" / Path(path_value).name
        verified.append(
            verify_identity(
                path,
                entry["bytes"],
                entry["sha256"],
                f"generated color asset {path.name}",
            )
        )
    return {
        "asset_count": len(verified),
        "cpu_oracles": color["cpu_verification"]["oracle_count"],
        "webgl_status": webgl["status"],
        "exact_engines_passed": webgl["exact_generated_shader"]["passed_engines"],
        "exact_engines_failed": webgl["exact_generated_shader"]["failed_engines"],
        "uniform_candidate_engines_passed": webgl[
            "uniform_nextafter_candidate"
        ]["passed_engines"],
        "uniform_candidate_approval": webgl[
            "uniform_nextafter_candidate"
        ]["approval_status"],
        "license_pending": color["license"]["license_pending"],
    }


def verify_generated_manifest() -> dict[str, Any]:
    manifest = load_json(STAGE / "generated" / "ocio_assets_manifest.json")
    require(manifest["schema_version"] == "bf3d.r2t.ocio_assets.v1", "manifest schema")
    require(
        manifest["transform"]["processor_cache_id"]
        == "cb6dc6defbf01d33b84718a55c277f0a",
        "manifest processor cache ID",
    )
    require(manifest["license_pending"] is True, "manifest license")
    integration = manifest["threejs_integration_contract"]
    require(
        integration["renderer_tone_mapping"] == "THREE.NoToneMapping",
        "manifest NoToneMapping",
    )
    require(
        integration["material"] == "THREE.RawShaderMaterial",
        "manifest RawShaderMaterial",
    )
    require(
        integration["post_shader_oetf"] == "FORBIDDEN"
        and integration["double_oetf_allowed"] is False
        and integration["second_srgb_oetf_allowed"] is False,
        "manifest double OETF guard",
    )
    textures = manifest["textures"]
    require([item["edge_length"] for item in textures] == [37, 57], "LUT edges")
    require(
        [item["sampler_name"] for item in textures]
        == ["ocio_lut3d_0Sampler", "ocio_lut3d_1Sampler"],
        "LUT samplers",
    )
    require(
        all(item["interpolation"] == "NEAREST" for item in textures),
        "LUT interpolation",
    )
    require(
        all(
            item["wrap_s"] == "CLAMP_TO_EDGE"
            and item["wrap_t"] == "CLAMP_TO_EDGE"
            and item["wrap_r"] == "CLAMP_TO_EDGE"
            for item in textures
        ),
        "LUT wrap",
    )
    require(
        len(manifest["cpu_oracle"]["points"]) == 8,
        "manifest CPU oracle count",
    )
    return {
        "edge_lengths": [item["edge_length"] for item in textures],
        "samplers": [item["sampler_name"] for item in textures],
        "cpu_oracle_count": len(manifest["cpu_oracle"]["points"]),
    }


def verify_webgl_oracle() -> dict[str, Any]:
    report = load_json(STAGE / "reports" / "ocio_webgl_oracle_report.json")
    require(
        report["schema_version"] == "bf3d.r2t.ocio_webgl_oracle_report.v1",
        "WebGL report schema",
    )
    require(
        report["status"]
        == "failed_exact_hard_gate_uniform_portability_candidate_passed_not_approved",
        "WebGL report status",
    )
    require(report["passed"] is False, "exact WebGL report must remain failed")
    contract = report["contract"]
    require(
        contract["exact_generated_shader_is_release_hard_gate"] is True
        and contract["portability_candidate_cannot_satisfy_exact_hard_gate"]
        is True,
        "WebGL exact/candidate boundary",
    )
    require(
        contract["production_page_loaded"] is False
        and contract["production_controller_loaded"] is False
        and contract["formal_glb_loaded"] is False
        and contract["production_mutation_performed"] is False,
        "WebGL production isolation contract",
    )
    require(
        contract["thresholds"]["rgba32f_max_abs_error"] == 0.00002
        and contract["thresholds"][
            "default_framebuffer_max_error_code_values_per_rgb_channel"
        ]
        == 1
        and contract["repeat_count"] == 2,
        "WebGL frozen thresholds",
    )
    exact = report["exact_variant"]
    require(
        exact["id"] == "exact_generated_shader"
        and exact["approval_status"] == "authoritative_exact_generated_asset"
        and exact["status"] == "failed_hard_gate"
        and exact["passed"] is False,
        "exact variant identity and failure",
    )
    summary = report["summary"]
    require(
        summary["expected_engines"] == 3
        and summary["evaluated_engines"] == 3
        and summary["passed_engines"] == 2
        and summary["failed_engines"] == 1
        and summary["not_evaluated_engines"] == [],
        "exact three-engine summary",
    )
    firefox_summary = summary["per_engine"]["firefox"]
    require(
        firefox_summary["passed"] is False
        and firefox_summary["float_max_abs_error"] == 0.000238734
        and firefox_summary["eight_bit_max_code_error"] == 0
        and firefox_summary["float_repeat_max_abs_delta"] == 0,
        "exact Firefox black-float failure summary",
    )
    require(
        summary["per_engine"]["chromium"]["passed"] is True
        and summary["per_engine"]["webkit"]["passed"] is True,
        "exact Chromium/WebKit pass",
    )
    exact_firefox = next(
        item for item in report["engines"] if item["engine"] == "firefox"
    )
    require(
        len(exact_firefox["page_result"]["repeats"]) == 2,
        "exact Firefox repeat count",
    )
    for repeat in exact_firefox["page_result"]["repeats"]:
        black = next(
            point for point in repeat["points"] if point["id"] == "black"
        )
        require(
            black["actual_rgba32f"][:3] == [0, 0, 0]
            and black["float_pass"] is False
            and black["eight_bit_pass"] is True,
            "exact Firefox black observation",
        )
        require(
            all(
                point["float_pass"] is True and point["eight_bit_pass"] is True
                for point in repeat["points"]
                if point["id"] != "black"
            ),
            "exact Firefox non-black observations",
        )
    literal = report["portability_candidate"]
    require(
        literal["id"] == "portability_nextafter_min_normal_candidate"
        and literal["approval_status"] == "candidate_not_approved"
        and literal["passed"] is False
        and literal["summary"]["passed_engines"] == 2
        and literal["summary"]["failed_engines"] == 1,
        "literal portability result",
    )
    uniform = report["uniform_portability_candidate"]
    require(
        uniform["id"]
        == "portability_uniform_nextafter_min_normal_candidate"
        and uniform["approval_status"] == "candidate_not_approved"
        and uniform["status"] == "passed_candidate_not_approved"
        and uniform["passed"] is True
        and uniform["summary"]["passed_engines"] == 3
        and uniform["summary"]["failed_engines"] == 0,
        "uniform portability result",
    )
    require(
        uniform["side_effect_comparison_to_exact"]["passed"] is True
        and uniform["side_effect_comparison_to_exact"][
            "all_engines_non_black_passed"
        ]
        is True
        and uniform["side_effect_comparison_to_exact"][
            "all_engines_portability_black_passed"
        ]
        is True,
        "uniform candidate side-effect comparison",
    )
    require(
        report["resource_integrity"]["passed"] is True,
        "WebGL report resource integrity",
    )
    literal_resource = report["resource_integrity"]["portability_candidate"]
    require(
        literal_resource["diff_token_count"] == 9
        and literal_resource["replacement_token_float32"]["bits_hex"]
        == "0x00800001"
        and literal_resource["in_memory_compiled_ocio_function"]["sha256"]
        == "669de12ed704754c6eb7ff4d28ab3cd8e7acbf5a892c150193276e585d69a63d"
        and literal_resource["generated_asset_mutated_on_disk"] is False,
        "literal portability resource identity",
    )
    uniform_resource = report["resource_integrity"][
        "uniform_portability_candidate"
    ]
    require(
        uniform_resource["diff_token_count"] == 9
        and uniform_resource["uniform_value_float32"]["bits_hex"]
        == "0x00800001"
        and uniform_resource["in_memory_compiled_ocio_function"]["sha256"]
        == "9e3bcd185e776401b2dcd04bada5fafca514587655a81558d926663b9fd499cf"
        and uniform_resource["generated_asset_mutated_on_disk"] is False,
        "uniform portability resource identity",
    )
    for label, entries in [
        ("exact", report["engines"]),
        ("literal", literal["engines"]),
        ("uniform", uniform["engines"]),
    ]:
        require(len(entries) == 3, f"{label} WebGL engine count")
        for entry in entries:
            require(entry["evaluated"] is True, f"{label} engine evaluated")
            require(entry["console_errors"] == [], f"{label} console errors")
            require(entry["page_errors"] == [], f"{label} page errors")
            require(entry["http_errors"] == [], f"{label} HTTP errors")
            require(
                entry["external_requests"] == [],
                f"{label} external requests",
            )
    require(report["errors"] == [], "WebGL top-level errors")
    verify_identity(
        STAGE / "webgl_oracle" / "index.html",
        825,
        "33850ef85d676b5f35e9a8406e6a4b34b97efa5cbfd8b0fc050f17251d7a0fce",
        "WebGL oracle index",
    )
    verify_identity(
        STAGE / "webgl_oracle" / "oracle.js",
        35918,
        "377a3b71e7df8be289299f6b4365c54fc6ec7d32f2a1f0cac41ac48c9094881d",
        "WebGL oracle implementation",
    )
    verify_identity(
        STAGE / "webgl_oracle" / "README.md",
        2245,
        "5c189e1f53a1de208dc63c3887c467f3b1c2f6d1c1987764be83e46b18568f45",
        "WebGL oracle README",
    )
    verify_identity(
        ROOT / "tools" / "verify_bf3d_r2t_ocio_webgl.cjs",
        65363,
        "b2d4b4787ecb668561743ef7e636f826b794b60ebda4e9f8c3b1c1f9ae44ee2f",
        "WebGL oracle verifier",
    )
    review = (STAGE / "reports" / "ocio_webgl_oracle_spec_review.md").read_text(
        encoding="utf-8"
    )
    require(
        "candidate_not_approved" in review
        and "next_stage_allowed=false" in review
        and "exact equivalence：未批准" in review,
        "WebGL independent review boundary",
    )
    return {
        "exact_status": exact["status"],
        "exact_engines_passed": summary["passed_engines"],
        "exact_engines_failed": summary["failed_engines"],
        "exact_firefox_failed_point": "black",
        "literal_candidate_passed": literal["passed"],
        "uniform_candidate_passed": uniform["passed"],
        "uniform_candidate_approval": uniform["approval_status"],
        "production_side_effects": 0,
    }


def verify_photometry() -> dict[str, Any]:
    photo = load_json(STAGE / "photometric_calibration_contract.json")
    require(
        photo["schema_version"] == "bf3d.r2t.photometric_calibration_contract.v1",
        "photometric schema",
    )
    require(photo["status"] == "pre_registered_capture_blocked", "photo status")
    require(photo["approved"] is False, "photo approval false")
    require(photo["capture_eligible"] is False, "photo capture false")
    mapping = photo["coordinate_mapping"]
    require(mapping["determinant"] == 1.0, "coordinate determinant")
    require(mapping["orthogonal"] is True, "coordinate orthogonal")
    candidate = photo["candidate_family"]
    require(candidate["sun"]["shared_scale_only"] is True, "shared SUN scale")
    require(candidate["sun"]["pre_registered_k"] == 1.0, "SUN k")
    require(candidate["top_area"]["pre_registered_k"] == 1.0, "AREA k")
    require(candidate["world"]["pre_registered_k"] == 1.0, "ENV k")
    require(
        abs(candidate["top_area"]["intensity_at_k1"] - 1.3275510357953) < 1e-13,
        "AREA analytic intensity",
    )
    ltc = photo["runtime_prerequisites"]["rect_area_light_ltc"]
    require(
        ltc["status"] == "runtime_verified_candidate_not_approved",
        "LTC source/runtime status",
    )
    verify_identity(
        ROOT / ltc["source"]["path"],
        ltc["source"]["bytes"],
        ltc["source"]["sha256"],
        "vendored RectAreaLightUniformsLib",
    )
    require(
        ltc["source"]["vendor_lock"]
        == "高炉前端数据/libs/three/vendor.lock.json",
        "LTC vendor lock path",
    )
    runtime = ltc["runtime_verification"]
    require(
        runtime["status"]
        == "runtime_prerequisite_verified_candidate_not_approved"
        and runtime["evaluated_runs"] == 6
        and runtime["passed_runs"] == 6
        and runtime["failed_runs"] == 0,
        "LTC runtime result",
    )
    require(
        runtime["same_three_esm_instance_verified"] is True
        and runtime["effective_addon_init_calls"] == 1
        and runtime["duplicate_attempt_rejected_before_addon_invocation"]
        is True
        and runtime["required_float_branch_selected_in_all_runs"] is True,
        "LTC runtime identity/init/branch",
    )
    require(
        runtime["blender_photometric_equivalence_claimed"] is False
        and runtime["rect_area_light_shadow_claimed"] is False
        and runtime["capture_eligible"] is False
        and runtime["production_integration_allowed"] is False,
        "LTC runtime approval boundary",
    )
    require(
        all(
            item["status"] != "equivalent"
            for item in photo["known_non_equivalence"]
        ),
        "known non-equivalence must remain explicit",
    )
    require(
        photo["guardrails"]["not_evaluated_blocks_pass"] is True,
        "photo not-evaluated policy",
    )
    return {
        "candidate_id": candidate["id"],
        "sun_count": len(candidate["sun"]["lights"]),
        "area_intensity_at_k1": candidate["top_area"]["intensity_at_k1"],
        "ltc_status": ltc["status"],
        "ltc_runtime_runs_passed": runtime["passed_runs"],
    }


def verify_vendor_ltc() -> dict[str, Any]:
    lock_path = ROOT / "高炉前端数据" / "libs" / "three" / "vendor.lock.json"
    lock = load_json(lock_path)
    require(
        lock["schema_version"]
        == "bf3d.three_r160.rect_area_ltc_vendor_lock.v1",
        "LTC vendor lock schema",
    )
    require(lock["status"] == "vendor_sources_locked", "LTC vendor lock status")
    require(lock["three"]["revision"] == "160", "LTC Three revision")
    core = lock["three"]["core"]
    verify_identity(
        ROOT / core["path"],
        core["bytes"],
        core["sha256"],
        "LTC vendor Three core",
    )
    require(
        lock["runtime_contract"]["same_three_esm_instance_required"] is True,
        "LTC same Three ESM instance guard",
    )
    require(
        lock["runtime_contract"]["init_exactly_once_per_three_module_instance"]
        is True,
        "LTC init-once guard",
    )
    require(
        lock["runtime_contract"]["expected_texture_size"] == [64, 64],
        "LTC texture size",
    )
    require(
        lock["runtime_contract"]["rect_area_shadow_supported"] is False,
        "RectArea shadow capability",
    )
    files = lock["vendored_files"]
    require(len(files) == 3, "LTC vendored file count")
    for entry in files:
        verify_identity(
            ROOT / entry["path"],
            entry["bytes"],
            entry["sha256"],
            f"LTC vendor file {entry['id']}",
        )
    return {
        "file_count": len(files),
        "addon_sha256": files[0]["sha256"],
        "three_commit": lock["three"]["peeled_commit"],
        "ltc_commit": lock["selfshadow_ltc"]["commit"],
        "runtime_init_verified": True,
        "rect_area_shadow_supported": False,
    }


def verify_ltc_runtime() -> dict[str, Any]:
    report = load_json(STAGE / "reports" / "ltc_runtime_oracle_report.json")
    require(
        report["schema_version"] == "bf3d.r2t.ltc_runtime_oracle_report.v1",
        "LTC runtime report schema",
    )
    require(
        report["status"]
        == "runtime_prerequisite_verified_candidate_not_approved",
        "LTC runtime report status",
    )
    require(report["passed"] is True, "LTC runtime report pass")
    classification = report["classification"]
    require(
        classification["artifact_role"] == "candidate_runtime_prerequisite"
        and classification["runtime_prerequisite_verified"] is True,
        "LTC runtime classification",
    )
    require(
        classification["capture_eligible"] is False
        and classification["approval_granted"] is False
        and classification["production_integration_allowed"] is False
        and classification["next_stage_automatically_allowed"] is False
        and classification["blender_photometric_equivalence_claimed"] is False
        and classification["rect_area_light_shadow_claimed"] is False,
        "LTC runtime approval boundary",
    )
    contract = report["contract"]
    require(
        contract["same_three_esm_instance_required"] is True
        and contract["effective_addon_init_calls_required"] == 1
        and contract["webgl2_required"] is True
        and contract["float_texture_extension_required"]
        == "OES_texture_float_linear"
        and contract["half_float_fallback_satisfies_this_gate"] is False,
        "LTC runtime fixed contract",
    )
    require(
        contract["production_page_loaded"] is False
        and contract["production_controller_loaded"] is False
        and contract["formal_glb_loaded"] is False
        and contract["production_mutation_performed"] is False,
        "LTC runtime production isolation",
    )
    expected_texture_sha = {
        "LTC_FLOAT_1": (
            65536,
            "cf5cf21e5c112d2095c7e2418cb0a1ac54636e275d73e42f3453646c67f26814",
        ),
        "LTC_FLOAT_2": (
            65536,
            "3b1b09080b26104498db277c14fc1733786465c6958e7a8403d688b1e24c2ff5",
        ),
        "LTC_HALF_1": (
            32768,
            "a391de32f868fd4aa8774917b793174b7be804c08e2fb8924c30f31d7aa8dcd7",
        ),
        "LTC_HALF_2": (
            32768,
            "fa1ecbc6deb3c85ddf603cdf1e98e30279444f905eb1cebb849d761b570dd696",
        ),
    }
    textures = contract["required_textures"]
    require(len(textures) == 4, "LTC runtime texture count")
    for texture in textures:
        require(
            texture["id"] in expected_texture_sha,
            "LTC runtime texture ID",
        )
        expected_bytes, expected_sha = expected_texture_sha[texture["id"]]
        require(
            texture["data_bytes"] == expected_bytes
            and texture["data_sha256"] == expected_sha,
            f"LTC runtime texture identity {texture['id']}",
        )
    summary = report["summary"]
    require(
        summary["expected_engines"] == 3
        and summary["expected_runs"] == 6
        and summary["evaluated_runs"] == 6
        and summary["passed_runs"] == 6
        and summary["failed_runs"] == 0
        and summary["not_evaluated_runs"] == []
        and summary["engines_passed"] == 3,
        "LTC runtime summary",
    )
    require(
        all(value == 0 for value in summary["error_counts"].values()),
        "LTC runtime summary errors",
    )
    groups = report["engine_groups"]
    require(
        [group["engine"] for group in groups]
        == ["chromium", "firefox", "webkit"],
        "LTC runtime engine order",
    )
    for group in groups:
        require(
            group["evaluated_runs"] == 2
            and group["passed_runs"] == 2
            and group["required_float_branch_supported"] is True
            and group["selected_branches"] == ["float", "float"]
            and group["extension_branch_consistent"] is True
            and group["independent_run_outputs_byte_identical"] is True
            and group["shader_sources_identical"] is True
            and group["passed"] is True,
            f"LTC runtime engine group {group['engine']}",
        )
        require(
            all(value == 0 for value in group["error_counts"].values()),
            f"LTC runtime engine errors {group['engine']}",
        )
    runs = report["runs"]
    require(len(runs) == 6, "LTC runtime run count")
    for run in runs:
        require(
            run["evaluated"] is True and run["passed"] is True,
            f"LTC runtime evaluated run {run['engine']}/{run['run_index']}",
        )
        require(
            run["console_errors"] == []
            and run["page_errors"] == []
            and run["http_errors"] == []
            and run["external_requests"] == [],
            f"LTC runtime run errors {run['engine']}/{run['run_index']}",
        )
        page = run["page_result"]
        require(
            page["status"] == "completed"
            and page["passed"] is True
            and page["import_contract"]["passed"] is True
            and page["init_once"]["addon_init_effective_calls"] == 1
            and page["init_once"]["duplicate_attempts_rejected_before_addon"]
            == 1
            and page["init_once"]["exactly_once_passed"] is True,
            f"LTC runtime page init {run['engine']}/{run['run_index']}",
        )
        runtime = page["runtime"]
        fixture = runtime["fixture"]
        readback = runtime["readback"]
        require(
            runtime["extension_branch"]["expected_branch"] == "float"
            and runtime["extension_branch"]["actual_selected_textures"]
            == ["LTC_FLOAT_1", "LTC_FLOAT_2"]
            and runtime["extension_branch"]["passed"] is True,
            f"LTC runtime extension branch {run['engine']}/{run['run_index']}",
        )
        require(
            fixture["ambient_light_count"] == 0
            and fixture["environment_present"] is False
            and fixture["mesh_standard_material"]["emissive_linear_rgb"]
            == [0, 0, 0]
            and fixture["mesh_standard_material"]["metalness"] == 1
            and fixture["claims"]["lit_output_requires_rect_area_ltc_specular_path"]
            is True
            and fixture["claims"]["proves_blender_photometric_equivalence"]
            is False
            and fixture["claims"]["proves_rect_area_light_shadows"] is False,
            f"LTC runtime fixture {run['engine']}/{run['run_index']}",
        )
        require(
            readback["lit_non_black"] is True
            and readback["zero_intensity_control_black"] is True
            and readback["repeat_byte_identical"] is True
            and readback["passed"] is True,
            f"LTC runtime readback {run['engine']}/{run['run_index']}",
        )
    require(report["source_integrity"]["passed"] is True, "LTC source integrity")
    require(report["errors"] == [], "LTC top-level errors")
    verify_identity(
        STAGE / "ltc_runtime_oracle" / "index.html",
        1096,
        "28aa98a64912d18e0d1bd0f3370464380f8bf0d84343f303602b0fcd26da12dc",
        "LTC runtime oracle index",
    )
    verify_identity(
        STAGE / "ltc_runtime_oracle" / "oracle.js",
        29944,
        "6e115a09fdf19598cfe0ce91607812ccd8efe21fcfbecafe888b78e00be1fb78",
        "LTC runtime oracle implementation",
    )
    verify_identity(
        STAGE / "ltc_runtime_oracle" / "README.md",
        2284,
        "57976d16124298cf1c28b366a2ac0bc0b8175addfc76915381dbefd8349c86e5",
        "LTC runtime oracle README",
    )
    verify_identity(
        ROOT / "tools" / "verify_bf3d_r2t_ltc_runtime.cjs",
        44771,
        "b10ff04545d76e65e8435188c0f0f05c6724405f6a7b4878c6f2c7f7d064a58d",
        "LTC runtime verifier",
    )
    return {
        "status": report["status"],
        "engines_passed": summary["engines_passed"],
        "runs_passed": summary["passed_runs"],
        "texture_count": len(textures),
        "effective_addon_init_calls": 1,
        "production_side_effects": 0,
        "blender_photometric_equivalence_claimed": False,
        "rect_area_light_shadow_claimed": False,
    }


def verify_photometric_fixture() -> dict[str, Any]:
    verification = load_json(
        STAGE / "reports" / "photometric_verification_report.json"
    )
    require(
        verification["schema_version"]
        == "bf3d.r2t.photometric_verification_report.v1",
        "photometric verification schema",
    )
    require(
        verification["status"] == "candidate_evidence_verified_not_approved"
        and verification["verification_passed"] is True
        and verification["passed"] is True,
        "photometric verification status",
    )
    classification = verification["classification"]
    require(
        classification["verified_subject"]
        == "candidate_evidence_integrity_only"
        and classification["photometric_equivalence_approved"] is False
        and classification["capture_eligible"] is False
        and classification["approval_granted"] is False
        and classification["production_integration_allowed"] is False
        and classification["beauty_capture_performed"] is False
        and classification["mask_capture_performed"] is False,
        "photometric candidate-only classification",
    )
    checks = verification["checks"]
    require(
        set(checks)
        == {
            "definition",
            "ltc_prerequisite",
            "blender_reference",
            "three_linear_readback",
            "fit_and_held_out",
            "build_report",
            "no_beauty_outputs",
        }
        and all(item["passed"] is True for item in checks.values()),
        "photometric verification checks",
    )
    require(
        checks["definition"]["sample_count"] == 67
        and checks["blender_reference"]["cycles_sample_count"] == 67
        and checks["blender_reference"]["eevee_held_out_sample_count"] == 8
        and checks["three_linear_readback"]["run_count"] == 6
        and checks["three_linear_readback"]["sample_count_per_run"] == 67
        and checks["no_beauty_outputs"]["image_output_count"] == 0,
        "photometric renderer sample counts",
    )

    for artifact in verification["artifacts"].values():
        verify_identity(
            ROOT / artifact["path"],
            artifact["bytes"],
            artifact["sha256"],
            f"photometric artifact {artifact['path']}",
        )

    definition = verification["artifacts"]["fixture_definition"]
    require(
        definition["bytes"] == 103102
        and definition["sha256"]
        == "8d43067c8875c4e677330e830eda079b841d5d8a6fad05f13b26200f349bbcfd",
        "frozen photometric fixture definition identity",
    )

    fit = load_json(STAGE / "reports" / "photometric_fit_held_out_report.json")
    require(
        fit["schema_version"]
        == "bf3d.r2t.photometric_fit_held_out_report.v1"
        and fit["status"]
        == "evaluated_candidate_not_approved_no_acceptance_thresholds"
        and fit["evaluation_complete"] is True
        and fit["passed"] is False,
        "photometric fit report status",
    )
    fit_classification = fit["classification"]
    require(
        fit_classification["fit_executed"] is True
        and fit_classification["held_out_executed"] is True
        and fit_classification["linear_thresholds_pre_registered"] is False
        and fit_classification["photometric_equivalence_approved"] is False
        and fit_classification["capture_eligible"] is False
        and fit_classification["approval_granted"] is False
        and fit_classification["production_integration_allowed"] is False,
        "photometric fit candidate boundary",
    )
    expected_scalars = {
        "sun": (
            "k_sun",
            0.9414175269608743,
            0.055471528149193094,
        ),
        "top_area": (
            "k_area",
            0.9450029255130412,
            0.0910057735916505,
        ),
        "world": (
            "k_env",
            0.9299202953495894,
            0.0019578534604496323,
        ),
    }
    for family, (name, scalar, denominator) in expected_scalars.items():
        result = fit["fit_results"][family]
        require(
            result["k_name"] == name
            and abs(result["non_negative_scalar"] - scalar) < 1e-15
            and abs(result["denominator"] - denominator) < 1e-15
            and result["denominator"] > result["denominator_epsilon"]
            and result["zero_denominator_policy"] == "fail_closed"
            and result["status"] == "evaluated",
            f"photometric WLS result {family}",
        )
        signal = fit["canonical_three_family_signal_summary"][family]
        require(
            signal["positive_sample_count"] == signal["sample_count"]
            and signal["weighted_wls_denominator"] > signal["denominator_epsilon"]
            and signal["zero_denominator_policy"] == "fail_closed"
            and signal["passed"] is True,
            f"photometric family signal {family}",
        )
    require(
        len(fit["browser_evaluations"]) == 36
        and all(
            item["refit_performed"] is False
            and item["metrics"]["threshold"] is None
            and item["metrics"]["equivalence_pass_claimed"] is False
            for item in fit["browser_evaluations"]
        ),
        "photometric browser held-out candidate boundary",
    )
    eevee = fit["eevee_world_board_held_out"]
    require(
        eevee["evaluated_engine"] == "BLENDER_EEVEE"
        and eevee["runtime_identifier_alias_recorded"] is True
        and len(eevee["rows"]) == 8
        and eevee["metrics"]["threshold"] is None
        and eevee["metrics"]["equivalence_pass_claimed"] is False,
        "Eevee WORLD held-out result",
    )
    world = fit["world_pmrem_runtime_audit"]
    require(
        world["passed"] is True
        and world["failure_evidence_before_fix"]["source_resolution"] == [16, 8]
        and world["failure_evidence_before_fix"]["derived_cube_size"] == 4
        and world["failure_evidence_before_fix"]["world_wls_denominator"]
        == 0.0
        and world["implemented_sampling_prerequisite"]["source_resolution"]
        == [64, 32]
        and world["implemented_sampling_prerequisite"]["derived_cube_size"]
        == 16
        and world["implemented_sampling_prerequisite"][
            "ambient_light_substitution"
        ]
        is False
        and world["frozen_radiance_linear_rgb"] == [0.0864, 0.0864, 0.0864]
        and world["sampling_implementation_fix_only"] is True
        and world["radiance_changed"] is False
        and world["sample_definition_changed"] is False
        and world["threshold_changed"] is False,
        "WORLD PMREM minimum valid sampling audit",
    )
    top_basis = fit["top_rect_area_basis_audit"]
    require(
        top_basis["all_runs_passed"] is True
        and len(top_basis["runs"]) == 6
        and all(item["passed"] is True for item in top_basis["runs"]),
        "TOP RectArea basis audit",
    )
    disk_square = fit["disk_square_spatial_residual"]
    require(
        disk_square["status"] == "evaluated_known_non_equivalence"
        and disk_square["residual_is_zero_required"] is False
        and disk_square["analytic_equivalence_claimed"] is False
        and disk_square["fit_partition"]["metrics"]["threshold"] is None
        and disk_square["held_out_partition"]["metrics"]["threshold"] is None,
        "disk-square known non-equivalence",
    )
    require(
        fit["not_evaluated"] == []
        and all(
            item["status"] != "equivalent"
            for item in fit["known_non_equivalence"]
        ),
        "photometric known non-equivalence list",
    )

    build = load_json(STAGE / "reports" / "photometric_fixture_build_report.json")
    require(
        build["schema_version"] == "bf3d.r2t.photometric_fixture_build_report.v1"
        and build["status"] == "fixture_evaluated_candidate_not_approved"
        and build["fixture_execution_complete"] is True
        and build["passed"] is True
        and build["not_evaluated"] == []
        and build["errors"] == [],
        "photometric build status",
    )
    return {
        "status": verification["status"],
        "definition_sha256": definition["sha256"],
        "cycles_samples": checks["blender_reference"]["cycles_sample_count"],
        "eevee_world_held_out_samples": checks["blender_reference"][
            "eevee_held_out_sample_count"
        ],
        "three_runs_passed": checks["three_linear_readback"]["run_count"],
        "fit_executed": True,
        "held_out_executed": True,
        "photometric_equivalence_approved": False,
        "capture_eligible": False,
    }


def verify_review_preview() -> dict[str, Any]:
    report = load_json(STAGE / "reports" / "bf3d_review_preview_report.json")
    require(
        report["schema_version"] == "bf3d.review_preview_report.v1"
        and report["requirement_id"]
        == "REQ-BF3D-R2T-ISOLATED-REVIEW-PREVIEW-20260720"
        and report["execution_scope"]
        == "full_cross_engine_viewport_matrix_stability_x2"
        and report["overall_status"] == "full_matrix_passed_illustrative_only",
        "isolated review report status",
    )
    require(
        report["evidence"] == "E/illustrative"
        and report["reference_status"] == "REF-PENDING"
        and report["not_for_construction"] is True
        and report["blender_equivalence_calibration_complete"] is False
        and report["capture_eligible_for_numeric_ab"] is False
        and report["approval_granted"] is False,
        "isolated review approval boundary",
    )
    require(
        report["required_runs"] == 17
        and report["passed_runs"] == 17
        and report["failed_runs"] == 0
        and report["required_screenshots_per_run"] == 3
        and report["screenshot_count"] == 51
        and len(report["matrix"]) == 17
        and report["stability_iterations_required"] == 2
        and report["stability_iterations_completed"] == 2
        and report["stability_gate_passed"] is True
        and report["total_viewport_runs"] == 34
        and report["total_passed_runs"] == 34
        and report["total_failed_runs"] == 0
        and report["total_screenshot_captures"] == 102
        and len(report["stability_iterations"]) == 2
        and report["hard_failures"] == [],
        "isolated review matrix totals",
    )
    require(
        all(value == 0 for value in report["error_totals"].values()),
        "isolated review error totals",
    )
    for iteration in report["stability_iterations"]:
        require(
            iteration["schema_version"]
            == "bf3d.review_stability_iteration.v1"
            and iteration["iterations_required"] == 2
            and iteration["required_runs"] == 17
            and iteration["actual_runs"] == 17
            and iteration["passed_runs"] == 17
            and iteration["failed_runs"] == 0
            and iteration["screenshot_count"] == 51
            and iteration["passed"] is True
            and all(value == 0 for value in iteration["error_totals"].values())
            and all(
                run["passed"] is True
                and run["review_glb_request_finished_count"] == 1
                and run["diagnostic_counts"]["request_failed"] == 0
                for run in iteration["runs"]
            ),
            f"isolated review stability iteration {iteration['iteration']}",
        )
        iteration_log = load_json(ROOT / iteration["log_path"])
        require(
            iteration_log["iteration"] == iteration["iteration"]
            and iteration_log["passed"] is True,
            f"isolated review stability log {iteration['iteration']}",
        )
    for run in report["matrix"]:
        run_checks = {item["id"]: item for item in run["checks"]}
        require(
            run["passed"] is True
            and len(run["screenshots"]) == 3
            and all(
                len(run["diagnostics"][key]) == 0
                for key in (
                    "console_errors",
                    "page_errors",
                    "http_errors",
                    "external_requests",
                    "request_failures",
                )
            ),
            f"isolated review run {run['engine']} {run['viewport']}",
        )
        require(
            run_checks["network_isolation"]["passed"] is True
            and run_checks["network_isolation"]["detail"][
                "review_request_count"
            ]
            == 1
            and run_checks["network_isolation"]["detail"][
                "review_request_finished_count"
            ]
            == 1,
            f"isolated review request completion {run['engine']} {run['viewport']}",
        )
    require(
        report["protected_files_unchanged"] is True,
        "isolated review protected files unchanged",
    )
    protected = report["protected_files_after"]
    require(
        protected["formal_glb"]["sha256"]
        == "808960f1b2703e7fb27df35f1b1b1a17063b9b10d2267acba593fc3872b62af6"
        and protected["review_glb"]["sha256"]
        == "7e4b3b95343103784500aba354a124262ecf593fe89a3f0aa98348692152574b"
        and protected["production_html"]["sha256"]
        == "51118fc70d34cd28f32deac6039fbe81245b8cf196f46653696837a404dcdfbc"
        and protected["production_controller"]["sha256"]
        == "d99b6d8fc419d2c0d61f713af2343fe15b212f2c89f6f905ca27555dcb90b206",
        "isolated review protected identities",
    )
    glb = report["glb_contract"]
    require(
        glb["material_count"] == 13
        and glb["image_count"] == 21
        and len(glb["material_nodes"]) == 5
        and len(glb["physical_section_nodes"]) == 10
        and glb["passed"] is True,
        "isolated review GLB contract",
    )
    glb_checks = {item["id"]: item for item in glb["checks"]}
    require(
        glb_checks["glb_forbidden_names_zero"]["detail"]["forbidden"] == []
        and glb_checks["glb_pbr_channels_complete"]["detail"]["failures"] == []
        and glb_checks["glb_section_cap_coplanar_overlap_basis"]["passed"]
        is True
        and len(
            glb_checks["glb_section_cap_coplanar_overlap_basis"]["detail"][
                "cap_planes"
            ]
        )
        == 10,
        "isolated review GLB forbidden/PBR/cap gates",
    )
    source_checks = {
        item["id"]: item for item in report["source_contract"]["checks"]
    }
    require(
        source_checks["production_default_v1_route_unchanged"]["passed"] is True
        and source_checks["production_default_v1_route_unchanged"]["detail"][
            "expected_operational_asset"
        ]
        == "models/gl02_blast_furnace_structural_review.v1.glb"
        and source_checks["composition_disclosure_contract"]["passed"] is True
        and source_checks["complete_asset_response_consumption"]["passed"]
        is True
        and source_checks["two_iteration_stability_gate"]["passed"] is True
        and source_checks["script_csp_fail_closed_importmap_hash"]["passed"]
        is True
        and source_checks["script_csp_fail_closed_importmap_hash"]["detail"][
            "script_unsafe_inline_present"
        ]
        is False,
        "isolated review route/disclosure/CSP gates",
    )
    verify_identity(
        ROOT / "高炉前端数据" / "bf3d_review.server.html",
        8600,
        "d816cb90a46398c1b5c8fec45d3c7a192c83b4b103aa43e64dc62eddf228fd53",
        "isolated review HTML",
    )
    verify_identity(
        ROOT / "高炉前端数据" / "assets" / "bf3d-review-renderer.js",
        44431,
        "1a44438276bdf92c66cb2f2813fed67f4aff6470e84527479530b3d7ac0ba224",
        "isolated review renderer",
    )
    verify_identity(
        ROOT / "高炉前端数据" / "assets" / "bf3d-review-renderer.css",
        13878,
        "00742c243a34b028efe47efe2c24796ba8b476b30339549bc6c024bf898018e8",
        "isolated review CSS",
    )
    verify_identity(
        ROOT / "tools" / "serve_bf3d_review.py",
        11732,
        "ff1182d01fddcaa1bf05d492785ca09330d2eff185f2112fe198f1c6c7ec8c5d",
        "isolated review server",
    )
    verify_identity(
        ROOT / "tools" / "verify_bf3d_review_preview.cjs",
        48844,
        "99be4134ec953e5e9b6d658d924fd0316f800fc0bed9845efa2ed1df5c8d95de",
        "isolated review verifier",
    )
    return {
        "status": report["overall_status"],
        "runs_passed": report["total_passed_runs"],
        "screenshots": report["total_screenshot_captures"],
        "stability_iterations": report["stability_iterations_completed"],
        "error_totals": report["error_totals"],
        "production_requests": 0,
        "production_integration_allowed": False,
    }


def verify_pipeline() -> dict[str, Any]:
    pipeline = load_json(STAGE / "pipeline_status.json")
    require(
        pipeline["schema_version"] == "bf3d.r2t.ocio_photometric_equivalence.v1",
        "pipeline schema",
    )
    require(
        pipeline["status"]
        == "ocio_exact_webgl_failed_uniform_candidate_ltc_and_photometric_candidate_verified_isolated_review_passed_capture_blocked",
        "pipeline status",
    )
    require(pipeline["approval_granted"] is False, "pipeline approval false")
    require(pipeline["next_stage_allowed"] is False, "next stage false")
    require(pipeline["capture_eligible"] is False, "pipeline capture false")
    root_cause = pipeline["root_cause"]
    require(
        root_cause["asset_materials_missing"] is False
        and root_cause["historical_v1_selected_in_user_screenshot"] is True
        and root_cause["screenshot_import_completed"] is False,
        "pipeline Blender screenshot diagnosis",
    )
    require(
        root_cause["production_overview_default_asset_is_v1"] is True
        and root_cause["production_overview_default_asset"]
        == "models/gl02_blast_furnace_structural_review.v1.glb"
        and root_cause[
            "v3_review_asset_is_lazy_loaded_only_after_review_mode_selection"
        ]
        is True
        and root_cause["v3_review_asset"]
        == "models/gl02_blast_furnace_review.v3.glb",
        "pipeline production V1 versus V3 review routing diagnosis",
    )
    require(
        root_cause["isolated_v3_review_available"] is True
        and root_cause["isolated_v3_review_page"]
        == "高炉前端数据/bf3d_review.server.html"
        and root_cause["isolated_v3_review_loads_only_review_v3"] is True
        and root_cause["isolated_v3_review_production_integrated"] is False
        and root_cause["current_web_review_renderer_equivalent_to_blender"]
        is False,
        "pipeline isolated review boundary",
    )
    require(
        pipeline["release_gates"]["ocio_source_and_cpu_assets"] == "passed",
        "CPU release gate",
    )
    require(
        pipeline["release_gates"]["ocio_webgl_gpu_oracle"]
        == "failed_exact_2_pass_1_fail_uniform_candidate_3_pass_not_approved",
        "GPU oracle gate",
    )
    color = pipeline["color_management"]
    require(
        color["webgl_oracle_executed"] is True
        and color["webgl_oracle_verified"] is False
        and color["exact_webgl_hard_gate_passed"] is False
        and color["exact_webgl_engines_passed"] == 2
        and color["exact_webgl_engines_failed"] == 1,
        "pipeline exact WebGL result",
    )
    require(
        color["uniform_nextafter_candidate_passed"] is True
        and color["uniform_nextafter_candidate_engines_passed"] == 3
        and color["uniform_nextafter_candidate_approval"]
        == "candidate_not_approved",
        "pipeline uniform candidate result",
    )
    require(
        pipeline["release_gates"]["rect_area_light_ltc"]
        == "runtime_verified_3_engines_6_runs_candidate_not_approved",
        "LTC release gate",
    )
    require(
        pipeline["photometry"]["rect_area_light_ltc_runtime_verified"] is True
        and pipeline["photometry"]["rect_area_light_ltc_engines_passed"] == 3
        and pipeline["photometry"]["rect_area_light_ltc_fresh_runs_passed"]
        == 6
        and pipeline["photometry"][
            "rect_area_light_ltc_production_integration_allowed"
        ]
        is False,
        "pipeline LTC runtime result",
    )
    photometry = pipeline["photometry"]
    require(
        photometry["linear_fixture_implemented"] is True
        and photometry["fixture_definition_bytes"] == 103102
        and photometry["fixture_definition_sha256"]
        == "8d43067c8875c4e677330e830eda079b841d5d8a6fad05f13b26200f349bbcfd"
        and photometry["fixture_status"]
        == "candidate_evidence_verified_not_approved"
        and photometry["blender_cycles_samples_passed"] == 67
        and photometry["blender_eevee_world_held_out_samples_passed"] == 8
        and photometry["three_engines_passed"] == 3
        and photometry["three_fresh_runs_passed"] == 6
        and photometry["three_runtime_error_count"] == 0
        and photometry["fit_executed"] is True
        and photometry["held_out_executed"] is True
        and photometry["linear_acceptance_thresholds_preregistered"] is False
        and photometry["wls_denominators_nonzero"] is True
        and photometry["disk_square_spatial_residual_status"]
        == "evaluated_known_non_equivalence"
        and photometry["photometric_equivalence_approved"] is False
        and photometry["capture_eligible"] is False
        and photometry["production_integration_allowed"] is False,
        "pipeline photometric fixture candidate result",
    )
    require(
        pipeline["release_gates"]["linear_photometric_fixture"]
        == "evaluated_candidate_verified_not_approved"
        and pipeline["release_gates"]["photometric_fit_and_held_out"]
        == "evaluated_no_pre_registered_acceptance_thresholds"
        and pipeline["release_gates"]["isolated_review_preview"]
        == "stability_x2_full_matrix_34_of_34_illustrative_only",
        "pipeline photometric/preview release gates",
    )
    preview = pipeline["isolated_review_preview"]
    require(
        preview["status"] == "full_matrix_passed_illustrative_only"
        and preview["review_asset_sha256"]
        == "7e4b3b95343103784500aba354a124262ecf593fe89a3f0aa98348692152574b"
        and preview["independent_scene_renderer_camera_raf"] is True
        and preview["forbidden_runtime_object_count"] == 0
        and preview["production_request_count"] == 0
        and preview["required_runs"] == 17
        and preview["passed_runs"] == 17
        and preview["screenshot_count"] == 51
        and preview["stability_iterations_required"] == 2
        and preview["stability_iterations_passed"] == 2
        and preview["total_viewport_runs_passed"] == 34
        and preview["total_screenshot_captures"] == 102
        and preview["review_glb_request_finished_per_run"] == 1
        and preview["complete_asset_response_consumption"] is True
        and preview["console_page_http_external_requestfailed_errors"] == 0
        and preview["composition_disclosure_verified"] is True
        and preview["section_cap_overlap_disclosed_not_fixed"] is True
        and preview["evidence"] == "E/illustrative"
        and preview["reference_status"] == "REF-PENDING"
        and preview["blender_equivalence_calibration_complete"] is False
        and preview["capture_eligible_for_numeric_ab"] is False
        and preview["production_integration_allowed"] is False,
        "pipeline isolated preview result",
    )
    require(
        pipeline["guardrails"]["production_page_mutated"] is False,
        "production page guard",
    )
    require(
        pipeline["guardrails"]["formal_glb_replaced"] is False,
        "formal GLB guard",
    )
    require(
        pipeline["guardrails"][
            "photometric_acceptance_threshold_invented_after_results"
        ]
        is False
        and pipeline["guardrails"]["isolated_preview_mutated_production"]
        is False
        and pipeline["guardrails"][
            "isolated_preview_reclassified_section_cap_overlap_as_cavity"
        ]
        is False,
        "photometric/preview guardrails",
    )
    formal = pipeline["formal_glb"]
    verify_identity(
        ROOT / formal["path"],
        formal["bytes"],
        formal["sha256"],
        "formal production GLB",
    )
    return {
        "status": pipeline["status"],
        "capture_eligible": pipeline["capture_eligible"],
        "approval_granted": pipeline["approval_granted"],
        "next_stage_allowed": pipeline["next_stage_allowed"],
    }


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    report = {
        "requirement_id": "REQ-BF3D-R2T-OCIO-PHOTOMETRIC-EQUIVALENCE-20260720",
        "stage_id": "WEB-60_R2T",
        "passed": True,
        "input_lock": verify_input_lock(),
        "color": verify_color_candidate(),
        "generated_manifest": verify_generated_manifest(),
        "webgl_oracle": verify_webgl_oracle(),
        "photometry": verify_photometry(),
        "vendor_ltc": verify_vendor_ltc(),
        "ltc_runtime": verify_ltc_runtime(),
        "photometric_fixture": verify_photometric_fixture(),
        "isolated_review_preview": verify_review_preview(),
        "pipeline": verify_pipeline(),
    }
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (AssertionError, KeyError, TypeError, ValueError, OSError) as error:
        failure = {
            "requirement_id": "REQ-BF3D-R2T-OCIO-PHOTOMETRIC-EQUIVALENCE-20260720",
            "stage_id": "WEB-60_R2T",
            "passed": False,
            "error": str(error),
        }
        print(json.dumps(failure, ensure_ascii=False, indent=2), file=sys.stderr)
        raise SystemExit(1)
