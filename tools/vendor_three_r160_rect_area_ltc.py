#!/usr/bin/env python3
"""Install or verify the exact Three.js r160 RectAreaLight LTC dependency."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import tempfile
import urllib.request
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
THREE_ROOT = ROOT / "高炉前端数据" / "libs" / "three"
LOCK_PATH = THREE_ROOT / "vendor.lock.json"
USER_AGENT = "bf3d-r2t-vendor-lock/1.0"

THREE_COMMIT = "d04539a76736ff500cae883d6a38b3dd8643c548"
THREE_TAG_OBJECT = "643680ed5fc73ba27e32a6529d59cae8c8b3825c"
LTC_COMMIT = "5c0770b74114b5dd38e9dae1b93f8486af7eac1b"

CORE = {
    "path": "高炉前端数据/libs/three/three.module.js",
    "bytes": 1272972,
    "sha256": "76dea8151bc9352aef3528b4262e249b2604f62543828328db978d060d61a495",
    "revision": "160",
}

SOURCES = [
    {
        "id": "three_r160_rect_area_light_uniforms_lib",
        "url": (
            "https://raw.githubusercontent.com/mrdoob/three.js/"
            f"{THREE_COMMIT}/examples/jsm/lights/RectAreaLightUniformsLib.js"
        ),
        "destination": "高炉前端数据/libs/three/lights/RectAreaLightUniformsLib.js",
        "bytes": 313854,
        "sha256": "08085bc942253cd54948bf936fecb66b54514a135872656e475a1cab09b55214",
        "license_id": "three_r160_mit",
    },
    {
        "id": "three_r160_license",
        "url": (
            "https://raw.githubusercontent.com/mrdoob/three.js/"
            f"{THREE_COMMIT}/LICENSE"
        ),
        "destination": "高炉前端数据/libs/three/LICENSE-three-r160.txt",
        "bytes": 1081,
        "sha256": "852e0e8699169bf9f6fdc6bda3e682d078dcbc738b5d33e74df594721bff271d",
        "license_id": "three_r160_mit",
    },
    {
        "id": "selfshadow_ltc_code_license",
        "url": (
            "https://raw.githubusercontent.com/selfshadow/ltc_code/"
            f"{LTC_COMMIT}/LICENSE"
        ),
        "destination": "高炉前端数据/libs/three/LICENSE-ltc_code-5c0770b.txt",
        "bytes": 1718,
        "sha256": "692a54e97fcadd0f04b14027386e53809c1dcf96de3e15b15af15731b15c1e94",
        "license_id": "selfshadow_ltc_bsd_style_with_citation",
    },
]


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def resolve_repo_path(value: str) -> Path:
    return ROOT / Path(value)


def require_identity(data: bytes, source: dict[str, Any]) -> None:
    actual_bytes = len(data)
    actual_sha256 = sha256_bytes(data)
    if actual_bytes != source["bytes"]:
        raise RuntimeError(
            f"{source['id']} bytes mismatch: {actual_bytes} != {source['bytes']}"
        )
    if actual_sha256 != source["sha256"]:
        raise RuntimeError(
            f"{source['id']} SHA-256 mismatch: "
            f"{actual_sha256} != {source['sha256']}"
        )


def fetch_exact(source: dict[str, Any]) -> bytes:
    request = urllib.request.Request(
        source["url"],
        headers={"User-Agent": USER_AGENT, "Accept": "application/octet-stream"},
    )
    with urllib.request.urlopen(request, timeout=60) as response:
        data = response.read()
        final_url = response.geturl()
    if final_url != source["url"]:
        raise RuntimeError(
            f"{source['id']} redirected unexpectedly: {final_url}"
        )
    require_identity(data, source)
    return data


def atomic_write(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    file_descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=path.parent
    )
    try:
        with os.fdopen(file_descriptor, "wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary_name, path)
    except BaseException:
        try:
            os.unlink(temporary_name)
        except FileNotFoundError:
            pass
        raise


def verify_core() -> dict[str, Any]:
    path = resolve_repo_path(CORE["path"])
    if not path.is_file():
        raise RuntimeError(f"Three core is missing: {path}")
    actual_bytes = path.stat().st_size
    actual_sha256 = sha256_file(path)
    if actual_bytes != CORE["bytes"] or actual_sha256 != CORE["sha256"]:
        raise RuntimeError(
            "Three core identity mismatch: "
            f"bytes={actual_bytes}, sha256={actual_sha256}"
        )
    prefix = path.read_text(encoding="utf-8", errors="strict")[:256]
    if "REVISION = '160'" not in prefix:
        raise RuntimeError("Three core REVISION is not exactly 160")
    return {
        **CORE,
        "verified": True,
    }


def build_lock() -> dict[str, Any]:
    return {
        "schema_version": "bf3d.three_r160.rect_area_ltc_vendor_lock.v1",
        "requirement_id": "REQ-BF3D-R2T-P40-PHOTOMETRIC-CALIBRATION-20260720",
        "status": "vendor_sources_locked",
        "three": {
            "version": "0.160.0",
            "revision": "160",
            "tag": "r160",
            "annotated_tag_object": THREE_TAG_OBJECT,
            "peeled_commit": THREE_COMMIT,
            "npm_git_head": THREE_COMMIT,
            "npm_tarball": "https://registry.npmjs.org/three/-/three-0.160.0.tgz",
            "npm_shasum_sha1": "cd1e4dbd01aee0719280a9086d75545db52b7a8f",
            "npm_integrity": (
                "sha512-DLU8lc0zNIPkM7rH5/e1Ks1Z8tWCGRq6g8mPowdDJpw1CFBJMU7Uo"
                "JjC6PefXW7z//SSl0b2+GCw14LB+uDhng=="
            ),
            "core": CORE,
        },
        "selfshadow_ltc": {
            "commit": LTC_COMMIT,
            "reference_data_url": (
                "https://raw.githubusercontent.com/selfshadow/ltc_code/"
                f"{LTC_COMMIT}/fit/results/ltc.js"
            ),
            "reference_data_bytes": 315547,
            "reference_data_sha256": (
                "21071160163defd419b8f754ab604a8e60c44fcf539bfff9916e0e8e82316c1d"
            ),
            "paper_citation_required": True,
        },
        "vendored_files": [
            {
                "id": source["id"],
                "path": source["destination"],
                "source_url": source["url"],
                "bytes": source["bytes"],
                "sha256": source["sha256"],
                "license_id": source["license_id"],
            }
            for source in SOURCES
        ],
        "runtime_contract": {
            "import_specifier": (
                "three/addons/lights/RectAreaLightUniformsLib.js"
            ),
            "resolved_path": (
                "高炉前端数据/libs/three/lights/"
                "RectAreaLightUniformsLib.js"
            ),
            "same_three_esm_instance_required": True,
            "init_call": "RectAreaLightUniformsLib.init()",
            "init_exactly_once_per_three_module_instance": True,
            "expected_ltc_textures": [
                "LTC_FLOAT_1",
                "LTC_FLOAT_2",
                "LTC_HALF_1",
                "LTC_HALF_2",
            ],
            "expected_texture_size": [
                64,
                64,
            ],
            "webgl_extension_failure_policy": "fail_closed",
            "rect_area_shadow_supported": False,
            "supported_materials": [
                "THREE.MeshStandardMaterial",
                "THREE.MeshPhysicalMaterial",
            ],
        },
        "licenses": {
            "three_r160_mit": {
                "path": "高炉前端数据/libs/three/LICENSE-three-r160.txt",
                "redistribution_notice_required": True,
            },
            "selfshadow_ltc_bsd_style_with_citation": {
                "path": (
                    "高炉前端数据/libs/three/"
                    "LICENSE-ltc_code-5c0770b.txt"
                ),
                "redistribution_notice_required": True,
                "paper_citation_required": True,
            },
        },
        "guardrails": {
            "latest_or_master_allowed": False,
            "unverified_cdn_allowed": False,
            "automatic_hash_update_allowed": False,
            "source_byte_rewrite_allowed": False,
            "production_capture_allowed_on_mismatch": False,
        },
    }


def write_lock() -> None:
    payload = (
        json.dumps(
            build_lock(),
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
        + "\n"
    ).encode("utf-8")
    atomic_write(LOCK_PATH, payload)


def install() -> dict[str, Any]:
    core = verify_core()
    fetched: list[tuple[dict[str, Any], bytes]] = []
    for source in SOURCES:
        fetched.append((source, fetch_exact(source)))
    for source, data in fetched:
        atomic_write(resolve_repo_path(source["destination"]), data)
    write_lock()
    return verify()


def verify() -> dict[str, Any]:
    core = verify_core()
    files = []
    for source in SOURCES:
        path = resolve_repo_path(source["destination"])
        if not path.is_file():
            raise RuntimeError(f"vendored file is missing: {path}")
        data = path.read_bytes()
        require_identity(data, source)
        files.append(
            {
                "id": source["id"],
                "path": str(path),
                "bytes": len(data),
                "sha256": sha256_bytes(data),
            }
        )
    expected_lock = (
        json.dumps(
            build_lock(),
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
        + "\n"
    ).encode("utf-8")
    if not LOCK_PATH.is_file():
        raise RuntimeError(f"vendor lock is missing: {LOCK_PATH}")
    actual_lock = LOCK_PATH.read_bytes()
    if actual_lock != expected_lock:
        raise RuntimeError(
            "vendor.lock.json differs from the deterministic expected lock"
        )
    return {
        "ok": True,
        "requirement_id": (
            "REQ-BF3D-R2T-P40-PHOTOMETRIC-CALIBRATION-20260720"
        ),
        "core": core,
        "vendored_files": files,
        "vendor_lock": {
            "path": str(LOCK_PATH),
            "bytes": len(actual_lock),
            "sha256": sha256_bytes(actual_lock),
        },
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    action = parser.add_mutually_exclusive_group(required=True)
    action.add_argument("--install", action="store_true")
    action.add_argument("--verify-only", action="store_true")
    return parser.parse_args()


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    args = parse_args()
    report = install() if args.install else verify()
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, RuntimeError, ValueError, KeyError) as error:
        print(
            json.dumps(
                {
                    "ok": False,
                    "requirement_id": (
                        "REQ-BF3D-R2T-P40-PHOTOMETRIC-CALIBRATION-20260720"
                    ),
                    "error": str(error),
                },
                ensure_ascii=False,
                indent=2,
            ),
            file=sys.stderr,
        )
        raise SystemExit(1)
