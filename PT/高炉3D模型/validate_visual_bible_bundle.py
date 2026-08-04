"""Validate the controlled Visual Bible bundle.

Requirement:
    REQ-BF3D-VISUAL-BIBLE-001

The validator checks that the normative document, controlled annexes and
machine-readable presets stay present, parseable and mutually traceable.
It does not approve Blender, GLB or browser assets.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from collections import Counter
from pathlib import Path
from urllib.parse import unquote


ROOT = Path(__file__).resolve().parent
VISUAL_BIBLE = ROOT / "工业级高炉数字孪生视觉规范（Visual Bible）.md"

REQUIRED_FILES = (
    VISUAL_BIBLE,
    ROOT / "docs" / "视觉参考图板.md",
    ROOT / "docs" / "材质卡册.md",
    ROOT / "docs" / "LookDev与相机固定参数.md",
    ROOT / "docs" / "GL02数据映射附件.md",
    ROOT / "source" / "references" / "README.md",
    ROOT / "THIRD_PARTY_NOTICES.md",
    ROOT / "web" / "presets" / "lookdev_camera_v1.json",
    ROOT / "validation" / "golden-images" / "golden_views_v1.json",
    ROOT / "validation" / "Visual_Bible当前实现合规矩阵.md",
    ROOT / "validation" / "visual_bible_conformance_v1.json",
)

REQUIRED_RULE_IDS = (
    "VB-REF-001",
    "VB-MAT-001",
    "VB-LOOK-001",
    "VB-LOOK-002",
    "VB-DATA-001",
    "VB-QA-001",
    "VB-QA-002",
)

REQUIRED_DATA_TERMS = (
    "115",
    "L7",
    "L16",
    "80",
    "18",
    "静压力",
    "料线",
    "上料",
    "炉次",
    "铁水",
    "炉渣",
    "evidence",
    "derivation",
    "quality",
    "published_at",
    "knowledge_time",
)

REQUIRED_CONFORMANCE_STATUSES = (
    "compliant",
    "partial",
    "noncompliant",
    "blocked",
    "not_applicable",
)

MARKDOWN_LINK_RE = re.compile(r"!?\[[^\]]*\]\(([^)]+)\)")
MARKDOWN_IMAGE_RE = re.compile(r"!\[[^\]]*\]\(([^)]+)\)")


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def add_check(
    checks: list[dict[str, object]],
    check_id: str,
    ok: bool,
    detail: object,
) -> None:
    checks.append({"id": check_id, "ok": bool(ok), "detail": detail})


def resolve_markdown_target(document: Path, raw_target: str) -> Path | None:
    target = raw_target.strip()
    if target.startswith("<") and target.endswith(">"):
        target = target[1:-1].strip()
    if not target or target.startswith(("#", "http://", "https://", "mailto:")):
        return None
    target = target.split("#", 1)[0]
    target = unquote(target)
    if not target:
        return None
    candidate = Path(target)
    if candidate.is_absolute():
        return candidate
    return (document.parent / candidate).resolve()


def validate_markdown_links(path: Path) -> list[str]:
    missing: list[str] = []
    for match in MARKDOWN_LINK_RE.finditer(read_text(path)):
        raw_target = match.group(1)
        target = resolve_markdown_target(path, raw_target)
        if target is not None and not target.exists():
            missing.append(raw_target)
    return sorted(set(missing))


def load_json(path: Path) -> object:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def resolve_json_path(document: Path, raw_target: str) -> Path:
    return (document.parent / raw_target).resolve()


def run_validation() -> dict[str, object]:
    checks: list[dict[str, object]] = []

    missing_files = [str(path.relative_to(ROOT)) for path in REQUIRED_FILES if not path.exists()]
    add_check(checks, "required_files_exist", not missing_files, missing_files)

    if not VISUAL_BIBLE.exists():
        return {
            "requirement": "REQ-BF3D-VISUAL-BIBLE-001",
            "ok": False,
            "checks": checks,
        }

    bible_text = read_text(VISUAL_BIBLE)
    add_check(checks, "visual_bible_version_v1_1", "当前版本：v1.1" in bible_text, "v1.1")
    add_check(
        checks,
        "visual_bible_requirement_id",
        "REQ-BF3D-VISUAL-BIBLE-001" in bible_text,
        "REQ-BF3D-VISUAL-BIBLE-001",
    )

    missing_rule_ids = [rule_id for rule_id in REQUIRED_RULE_IDS if rule_id not in bible_text]
    add_check(checks, "controlled_rule_ids_present", not missing_rule_ids, missing_rule_ids)

    fov_ok = (
        "小于 30°属于窄视角/长焦感" in bible_text
        and "大于 70°属于广角" in bible_text
        and "广角低于 30°" not in bible_text
        and "长焦高于 70°" not in bible_text
    )
    add_check(checks, "camera_fov_semantics_correct", fov_ok, "small=narrow, large=wide")

    json_paths = (
        ROOT / "web" / "presets" / "lookdev_camera_v1.json",
        ROOT / "validation" / "golden-images" / "golden_views_v1.json",
        ROOT / "validation" / "visual_bible_conformance_v1.json",
    )
    parsed_json: dict[Path, object] = {}
    for path in json_paths:
        if not path.exists():
            continue
        try:
            payload = load_json(path)
            parsed_json[path] = payload
            add_check(
                checks,
                f"json_valid:{path.name}",
                isinstance(payload, (dict, list)) and bool(payload),
                type(payload).__name__,
            )
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            add_check(checks, f"json_valid:{path.name}", False, str(exc))

    preset_path = ROOT / "web" / "presets" / "lookdev_camera_v1.json"
    preset = parsed_json.get(preset_path)
    if isinstance(preset, dict):
        camera_ids = sorted((preset.get("cameras") or {}).keys())
        expected_cameras = sorted(
            (
                "CAM_GLOBAL_FRONT",
                "CAM_GLOBAL_BACK",
                "CAM_GLOBAL_LEFT",
                "CAM_GLOBAL_RIGHT",
                "CAM_DETAIL_SHELL",
                "CAM_DETAIL_TUYERE",
                "CAM_DETAIL_TAPHOLE",
            )
        )
        add_check(
            checks,
            "lookdev_seven_fixed_cameras",
            camera_ids == expected_cameras,
            camera_ids,
        )
        preset_paths: list[str] = []
        for item in preset.get("source_evidence") or []:
            if isinstance(item, dict) and isinstance(item.get("path"), str):
                preset_paths.append(item["path"])
        web_source = (preset.get("web_runtime_audit") or {}).get("source")
        if isinstance(web_source, str):
            preset_paths.append(web_source)
        hdri = (preset.get("environment_assets") or {}).get(
            "industrial_sunset_candidate"
        ) or {}
        if isinstance(hdri.get("path"), str):
            preset_paths.append(hdri["path"])
        missing_preset_paths = [
            raw for raw in preset_paths if not resolve_json_path(preset_path, raw).exists()
        ]
        add_check(
            checks,
            "lookdev_referenced_files_exist",
            not missing_preset_paths,
            missing_preset_paths,
        )
        hdri_path = (
            resolve_json_path(preset_path, hdri["path"])
            if isinstance(hdri.get("path"), str)
            else None
        )
        hdri_expected_hash = str(hdri.get("sha256") or "").lower()
        hdri_actual_hash = (
            sha256_file(hdri_path) if hdri_path is not None and hdri_path.exists() else ""
        )
        add_check(
            checks,
            "lookdev_hdri_hash_matches",
            bool(hdri_expected_hash) and hdri_actual_hash == hdri_expected_hash,
            {
                "expected": hdri_expected_hash,
                "actual": hdri_actual_hash,
            },
        )

    golden_path = ROOT / "validation" / "golden-images" / "golden_views_v1.json"
    golden = parsed_json.get(golden_path)
    if isinstance(golden, dict):
        view_ids = [
            item.get("id")
            for item in golden.get("views") or []
            if isinstance(item, dict)
        ]
        add_check(
            checks,
            "golden_view_ids_unique",
            len(view_ids) >= 16 and len(view_ids) == len(set(view_ids)),
            {"count": len(view_ids), "unique": len(set(view_ids))},
        )
        golden_link = golden.get("lookdev_preset")
        golden_paths = [golden_link] if isinstance(golden_link, str) else []
        for lock in (golden.get("asset_locks") or {}).values():
            if isinstance(lock, dict) and isinstance(lock.get("path"), str):
                golden_paths.append(lock["path"])
        missing_golden_paths = [
            raw for raw in golden_paths if not resolve_json_path(golden_path, raw).exists()
        ]
        add_check(
            checks,
            "golden_referenced_files_exist",
            not missing_golden_paths,
            missing_golden_paths,
        )
        evidence_failures: list[dict[str, str]] = []
        for item in golden.get("views") or []:
            if not isinstance(item, dict) or not item.get("evidence_image"):
                continue
            image_path = resolve_json_path(golden_path, str(item["evidence_image"]))
            expected_hash = str(item.get("evidence_sha256") or "").lower()
            if not image_path.exists():
                evidence_failures.append(
                    {"id": str(item.get("id")), "reason": "missing_image"}
                )
                continue
            actual_hash = sha256_file(image_path)
            if not expected_hash or actual_hash != expected_hash:
                evidence_failures.append(
                    {
                        "id": str(item.get("id")),
                        "reason": "sha256_mismatch",
                    }
                )
        add_check(
            checks,
            "golden_evidence_hashes_match",
            not evidence_failures,
            evidence_failures,
        )
        suite_status = str(golden.get("suite_status") or "")
        promoted = [
            item.get("id")
            for item in golden.get("views") or []
            if isinstance(item, dict)
            and item.get("golden_baseline_state") in {"approved", "promoted"}
        ]
        add_check(
            checks,
            "golden_approval_boundary_preserved",
            "not_approved" in suite_status and not promoted,
            {"suite_status": suite_status, "promoted": promoted},
        )

    material_path = ROOT / "docs" / "材质卡册.md"
    if material_path.exists():
        material_text = read_text(material_path)
        material_matches = list(
            re.finditer(
            r"^##\s+\d+\.\s+(MAT-[A-Z0-9-]+)\b",
                material_text,
                flags=re.MULTILINE,
            )
        )
        material_ids = [match.group(1) for match in material_matches]
        required_card_fields = (
            "Material ID",
            "材质族 / 对象",
            "来源级别",
            "物理尺度",
            "BaseColor",
            "Metalness",
            "Roughness",
            "Normal / Height",
            "污渍/覆盖层",
            "纹素密度",
            "贴图组合",
            "距离策略",
            "性能档",
            "禁止事项",
            "当前资产/状态",
        )
        incomplete_cards: dict[str, list[str]] = {}
        for index, match in enumerate(material_matches):
            end = (
                material_matches[index + 1].start()
                if index + 1 < len(material_matches)
                else material_text.find("\n## 20.", match.start())
            )
            if end < 0:
                end = len(material_text)
            section = material_text[match.start() : end]
            missing_fields = [
                field for field in required_card_fields if field not in section
            ]
            if missing_fields:
                incomplete_cards[match.group(1)] = missing_fields
        add_check(
            checks,
            "material_cards_filled_and_unique",
            len(material_ids) == 18
            and len(set(material_ids)) == 18
            and not incomplete_cards,
            {
                "count": len(material_ids),
                "unique": len(set(material_ids)),
                "incomplete": incomplete_cards,
            },
        )

    reference_board_path = ROOT / "docs" / "视觉参考图板.md"
    if reference_board_path.exists():
        local_reference_images: list[Path] = []
        missing_reference_images: list[str] = []
        for match in MARKDOWN_IMAGE_RE.finditer(read_text(reference_board_path)):
            raw_target = match.group(1)
            target = resolve_markdown_target(reference_board_path, raw_target)
            if target is None:
                continue
            local_reference_images.append(target)
            if not target.exists():
                missing_reference_images.append(raw_target)
        add_check(
            checks,
            "visual_reference_board_local_images",
            len(local_reference_images) >= 12 and not missing_reference_images,
            {
                "count": len(local_reference_images),
                "missing": missing_reference_images,
            },
        )
        add_check(
            checks,
            "r1_surface_visual_lock_reference_present",
            any(
                path.name == "SURF20_R5_10_R1_R4_R5_GRAZING_COMPARISON.png"
                for path in local_reference_images
            ),
            [path.name for path in local_reference_images],
        )

    data_path = ROOT / "docs" / "GL02数据映射附件.md"
    if data_path.exists():
        data_text = read_text(data_path)
        missing_terms = [term for term in REQUIRED_DATA_TERMS if term not in data_text]
        add_check(checks, "data_annex_required_terms", not missing_terms, missing_terms)

    conformance_path = ROOT / "validation" / "Visual_Bible当前实现合规矩阵.md"
    if conformance_path.exists():
        conformance_text = read_text(conformance_path)
        missing_statuses = [
            status for status in REQUIRED_CONFORMANCE_STATUSES if status not in conformance_text
        ]
        add_check(
            checks,
            "conformance_status_vocabulary",
            not missing_statuses,
            missing_statuses,
        )
        approval_boundaries = (
            "KEEP_P50_PENDING_NOT_APPROVED" in conformance_text
            and "not_granted_preflight_only" in conformance_text
        )
        add_check(
            checks,
            "p50_p60_approval_boundaries_preserved",
            approval_boundaries,
            "P50 pending; P60 preflight only",
        )
        conformance_json_path = ROOT / "validation" / "visual_bible_conformance_v1.json"
        conformance_json = parsed_json.get(conformance_json_path)
        if isinstance(conformance_json, dict):
            items = [
                item
                for item in conformance_json.get("items") or []
                if isinstance(item, dict)
            ]
            item_ids = [item.get("id") for item in items]
            counts = Counter(str(item.get("status")) for item in items)
            summary = conformance_json.get("summary") or {}
            allowed_statuses = set(REQUIRED_CONFORMANCE_STATUSES)
            summary_matches = (
                summary.get("total") == len(items)
                and all(
                    counts.get(status, 0) == int(summary.get(status, 0))
                    for status in allowed_statuses
                )
            )
            boundaries = conformance_json.get("approval_boundaries") or {}
            mirror_ok = (
                len(items) == 45
                and len(item_ids) == len(set(item_ids))
                and set(counts).issubset(allowed_statuses)
                and summary_matches
                and boundaries.get("p50") == "KEEP_P50_PENDING_NOT_APPROVED"
                and boundaries.get("p60") == "not_granted_preflight_only"
                and boundaries.get("formal_glb_replaced") is False
            )
            add_check(
                checks,
                "conformance_machine_mirror_consistent",
                mirror_ok,
                {
                    "items": len(items),
                    "unique_ids": len(set(item_ids)),
                    "counts": dict(counts),
                    "summary": summary,
                },
            )

    markdown_paths = [path for path in REQUIRED_FILES if path.suffix.lower() == ".md" and path.exists()]
    link_failures: dict[str, list[str]] = {}
    for path in markdown_paths:
        missing = validate_markdown_links(path)
        if missing:
            link_failures[str(path.relative_to(ROOT))] = missing
    add_check(checks, "markdown_relative_links_exist", not link_failures, link_failures)

    return {
        "requirement": "REQ-BF3D-VISUAL-BIBLE-001",
        "root": str(ROOT),
        "ok": all(bool(check["ok"]) for check in checks),
        "checks": checks,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--json",
        action="store_true",
        help="Print the full machine-readable validation report.",
    )
    args = parser.parse_args()

    report = run_validation()
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        for check in report["checks"]:
            marker = "PASS" if check["ok"] else "FAIL"
            print(f"[{marker}] {check['id']}: {check['detail']}")
        print(f"RESULT: {'PASS' if report['ok'] else 'FAIL'}")
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
