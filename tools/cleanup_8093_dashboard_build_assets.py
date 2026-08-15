#!/usr/bin/env python3
"""Plan or apply a narrowly scoped cleanup of hashed 8093 dashboard bundles.

The command is intentionally conservative:

* dry-run is the default;
* only direct ``assets/build/dashboard-main-*.js`` children are candidates;
* the active bundle is parsed from the supplied HTML and must exist;
* the active bundle and newest non-active bundle are always retained;
* every candidate is revalidated immediately before deletion;
* a JSON manifest is emitted for review/audit.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable


SCHEMA = "bf.8093.dashboard-build-cleanup.v1"
BUNDLE_NAME_RE = re.compile(r"^dashboard-main-[A-Za-z0-9_-]+\.js$")
ASSET_ATTR_RE = re.compile(r"(?:src|href)\s*=\s*['\"]([^'\"]+)['\"]", re.IGNORECASE)
BUNDLE_URL_RE = re.compile(
    r"(?:^|/)assets/build/(dashboard-main-[A-Za-z0-9_-]+\.js)$",
    re.IGNORECASE,
)


class CleanupSafetyError(RuntimeError):
    """Raised when cleanup cannot prove its target and active asset are safe."""


@dataclass(frozen=True)
class BundleRecord:
    path: Path
    size: int
    mtime_ns: int
    sha256: str

    def as_dict(self) -> dict[str, object]:
        return {
            "name": self.path.name,
            "path": str(self.path),
            "size": self.size,
            "mtime_ns": self.mtime_ns,
            "sha256": self.sha256,
        }


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _is_relative_to(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
        return True
    except ValueError:
        return False


def validate_build_dir(build_dir: Path) -> Path:
    resolved = build_dir.resolve(strict=True)
    if not resolved.is_dir():
        raise CleanupSafetyError(f"build directory is not a directory: {resolved}")
    if resolved.name != "build" or resolved.parent.name != "assets":
        raise CleanupSafetyError(
            "refusing cleanup outside an exact assets/build directory: " f"{resolved}"
        )
    return resolved


def parse_active_bundle(html_path: Path) -> str:
    resolved = html_path.resolve(strict=True)
    if not resolved.is_file():
        raise CleanupSafetyError(f"HTML target is not a file: {resolved}")
    html = resolved.read_text(encoding="utf-8")
    matches = set()
    for raw_url in ASSET_ATTR_RE.findall(html):
        url_path = raw_url.split("#", 1)[0].split("?", 1)[0]
        match = BUNDLE_URL_RE.search(url_path)
        if match:
            matches.add(match.group(1))
    matches = sorted(matches)
    if len(matches) != 1:
        raise CleanupSafetyError(
            "expected exactly one distinct assets/build/dashboard-main reference "
            f"in {resolved}; found {matches}"
        )
    return matches[0]


def inspect_bundle(path: Path, build_dir: Path) -> BundleRecord:
    resolved = path.resolve(strict=True)
    if path.is_symlink() or resolved.parent != build_dir:
        raise CleanupSafetyError(f"bundle escapes or aliases build directory: {path}")
    if not BUNDLE_NAME_RE.fullmatch(resolved.name):
        raise CleanupSafetyError(f"bundle name is outside allowlist: {resolved.name}")
    if not resolved.is_file():
        raise CleanupSafetyError(f"bundle is not a regular file: {resolved}")
    stat = resolved.stat()
    return BundleRecord(
        path=resolved,
        size=stat.st_size,
        mtime_ns=stat.st_mtime_ns,
        sha256=sha256_file(resolved),
    )


def collect_bundles(build_dir: Path) -> list[BundleRecord]:
    records = []
    for path in build_dir.iterdir():
        if BUNDLE_NAME_RE.fullmatch(path.name):
            records.append(inspect_bundle(path, build_dir))
    return sorted(records, key=lambda item: (item.mtime_ns, item.path.name), reverse=True)


def build_cleanup_plan(html_path: Path, build_dir: Path) -> dict[str, object]:
    resolved_build = validate_build_dir(build_dir)
    resolved_html = html_path.resolve(strict=True)
    active_name = parse_active_bundle(resolved_html)
    records = collect_bundles(resolved_build)
    by_name = {record.path.name: record for record in records}
    if active_name not in by_name:
        raise CleanupSafetyError(
            f"active bundle referenced by HTML does not exist in build directory: {active_name}"
        )

    non_active = [record for record in records if record.path.name != active_name]
    rollback = non_active[0] if non_active else None
    keep_names = {active_name}
    if rollback:
        keep_names.add(rollback.path.name)
    delete = [record for record in records if record.path.name not in keep_names]
    keep = [record for record in records if record.path.name in keep_names]

    return {
        "schema": SCHEMA,
        "ok": True,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "html": str(resolved_html),
        "build_dir": str(resolved_build),
        "active_bundle": active_name,
        "rollback_bundle": rollback.path.name if rollback else None,
        "keep": [record.as_dict() for record in keep],
        "delete_candidates": [record.as_dict() for record in delete],
        "delete_candidate_count": len(delete),
        "delete_candidate_bytes": sum(record.size for record in delete),
        "ignored_nonmatching_files": sorted(
            path.name
            for path in resolved_build.iterdir()
            if path.is_file() and not BUNDLE_NAME_RE.fullmatch(path.name)
        ),
    }


def _record_map(records: Iterable[dict[str, object]]) -> dict[str, dict[str, object]]:
    return {str(record["name"]): record for record in records}


def apply_cleanup_plan(plan: dict[str, object]) -> list[str]:
    build_dir = validate_build_dir(Path(str(plan["build_dir"])))
    html_path = Path(str(plan["html"])).resolve(strict=True)
    active_name = parse_active_bundle(html_path)
    if active_name != plan["active_bundle"]:
        raise CleanupSafetyError(
            "active HTML bundle changed after planning; refusing deletion: "
            f"planned={plan['active_bundle']} current={active_name}"
        )

    expected = _record_map(plan.get("delete_candidates", []))
    validated: list[BundleRecord] = []
    for name, record in expected.items():
        if name == active_name:
            raise CleanupSafetyError(f"refusing to delete active bundle: {name}")
        if not BUNDLE_NAME_RE.fullmatch(name):
            raise CleanupSafetyError(f"delete candidate name is outside allowlist: {name}")
        target = build_dir / name
        current = inspect_bundle(target, build_dir)
        if current.sha256 != record["sha256"] or current.size != record["size"]:
            raise CleanupSafetyError(f"delete candidate changed after planning: {name}")
        if not _is_relative_to(current.path, build_dir):
            raise CleanupSafetyError(f"delete candidate escaped build directory: {name}")
        validated.append(current)

    removed: list[str] = []
    for current in validated:
        current.path.unlink()
        removed.append(current.path.name)
    return removed


def default_paths() -> tuple[Path, Path]:
    root = Path(__file__).resolve().parents[1]
    frontend = root / "高炉前端数据"
    return frontend / "frontend_dashboard_v3.production.html", frontend / "assets" / "build"


def write_manifest(path: Path, manifest: dict[str, object]) -> None:
    destination = path.resolve()
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
        newline="\n",
    )


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    default_html, default_build = default_paths()
    parser = argparse.ArgumentParser(
        description=(
            "Keep the active 8093 dashboard-main bundle plus the newest rollback bundle. "
            "Defaults to dry-run."
        )
    )
    parser.add_argument("--html", type=Path, default=default_html)
    parser.add_argument("--build-dir", type=Path, default=default_build)
    parser.add_argument("--manifest-out", type=Path)
    parser.add_argument(
        "--apply",
        action="store_true",
        help="delete only the reviewed delete_candidates; omitted means dry-run",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        manifest = build_cleanup_plan(args.html, args.build_dir)
        manifest["mode"] = "apply" if args.apply else "dry-run"
        manifest["removed"] = []
        if args.apply:
            manifest["removed"] = apply_cleanup_plan(manifest)
        if args.manifest_out:
            write_manifest(args.manifest_out, manifest)
        print(json.dumps(manifest, ensure_ascii=False, indent=2))
        return 0
    except (CleanupSafetyError, FileNotFoundError, UnicodeDecodeError, OSError) as error:
        print(
            json.dumps(
                {"schema": SCHEMA, "ok": False, "error": str(error)},
                ensure_ascii=False,
                indent=2,
            ),
            file=sys.stderr,
        )
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
