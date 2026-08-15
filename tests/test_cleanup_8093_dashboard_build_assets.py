from __future__ import annotations

import importlib.util
import json
import os
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
TOOL = ROOT / "tools" / "cleanup_8093_dashboard_build_assets.py"


def load_tool():
    spec = importlib.util.spec_from_file_location("cleanup_8093_dashboard_build_assets_test", TOOL)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def make_fixture(tmp_path: Path, active: str = "dashboard-main-current1.js"):
    frontend = tmp_path / "frontend"
    build = frontend / "assets" / "build"
    build.mkdir(parents=True)
    html = frontend / "frontend_dashboard_v3.production.html"
    html.write_text(
        f'<script type="module" src="assets/build/{active}?v=1"></script>',
        encoding="utf-8",
    )
    return html, build


def write_bundle(build: Path, name: str, content: str, mtime_ns: int) -> Path:
    path = build / name
    path.write_text(content, encoding="utf-8")
    os.utime(path, ns=(mtime_ns, mtime_ns))
    return path


def test_dry_run_keeps_active_and_newest_rollback_without_deleting(tmp_path: Path) -> None:
    tool = load_tool()
    html, build = make_fixture(tmp_path)
    write_bundle(build, "dashboard-main-current1.js", "current", 10)
    write_bundle(build, "dashboard-main-rollback2.js", "rollback", 30)
    old = write_bundle(build, "dashboard-main-old00001.js", "old", 20)
    unrelated = write_bundle(build, "overview-route-loader-Abcd1234.js", "loader", 40)

    plan = tool.build_cleanup_plan(html, build)

    assert plan["active_bundle"] == "dashboard-main-current1.js"
    assert plan["rollback_bundle"] == "dashboard-main-rollback2.js"
    assert [item["name"] for item in plan["delete_candidates"]] == [
        "dashboard-main-old00001.js"
    ]
    assert old.exists()
    assert unrelated.exists()
    assert "overview-route-loader-Abcd1234.js" in plan["ignored_nonmatching_files"]


def test_apply_deletes_only_sealed_old_bundle_and_emits_manifest(tmp_path: Path) -> None:
    tool = load_tool()
    html, build = make_fixture(tmp_path)
    current = write_bundle(build, "dashboard-main-current1.js", "current", 10)
    rollback = write_bundle(build, "dashboard-main-rollback2.js", "rollback", 30)
    old = write_bundle(build, "dashboard-main-old00001.js", "old", 20)
    unrelated = write_bundle(build, "vendor-main-unused000.js", "vendor", 40)
    manifest_path = tmp_path / "manifest.json"

    assert tool.main(
        [
            "--html",
            str(html),
            "--build-dir",
            str(build),
            "--manifest-out",
            str(manifest_path),
            "--apply",
        ]
    ) == 0

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest["mode"] == "apply"
    assert manifest["removed"] == [old.name]
    assert current.exists()
    assert rollback.exists()
    assert unrelated.exists()
    assert not old.exists()


def test_refuses_missing_active_bundle(tmp_path: Path) -> None:
    tool = load_tool()
    html, build = make_fixture(tmp_path)
    write_bundle(build, "dashboard-main-other001.js", "other", 10)

    with pytest.raises(tool.CleanupSafetyError, match="active bundle.*does not exist"):
        tool.build_cleanup_plan(html, build)


def test_refuses_ambiguous_active_bundle_references(tmp_path: Path) -> None:
    tool = load_tool()
    html, build = make_fixture(tmp_path)
    html.write_text(
        '<script src="/assets/build/dashboard-main-first001.js"></script>'
        '<script src="/assets/build/dashboard-main-second02.js"></script>',
        encoding="utf-8",
    )

    with pytest.raises(tool.CleanupSafetyError, match="exactly one distinct"):
        tool.build_cleanup_plan(html, build)


def test_refuses_directory_outside_exact_assets_build_shape(tmp_path: Path) -> None:
    tool = load_tool()
    unsafe = tmp_path / "build"
    unsafe.mkdir()

    with pytest.raises(tool.CleanupSafetyError, match="outside an exact assets/build"):
        tool.validate_build_dir(unsafe)


def test_apply_refuses_candidate_changed_after_plan(tmp_path: Path) -> None:
    tool = load_tool()
    html, build = make_fixture(tmp_path)
    write_bundle(build, "dashboard-main-current1.js", "current", 10)
    write_bundle(build, "dashboard-main-rollback2.js", "rollback", 30)
    first_old = write_bundle(build, "dashboard-main-old00001.js", "old-1", 20)
    changed_old = write_bundle(build, "dashboard-main-old00002.js", "old-2", 15)
    plan = tool.build_cleanup_plan(html, build)
    changed_old.write_text("changed", encoding="utf-8")

    with pytest.raises(tool.CleanupSafetyError, match="changed after planning"):
        tool.apply_cleanup_plan(plan)
    assert first_old.exists(), "all candidates must validate before the first deletion"


def test_heat_query_reference_resolves_to_unique_feature_asset() -> None:
    html = (ROOT / "高炉前端数据" / "frontend_dashboard_v3.server.html").read_text(
        encoding="utf-8"
    )
    asset = ROOT / "高炉前端数据" / "assets" / "bf-heat-performance-quality-8093-query-v2.js"
    source = asset.read_text(encoding="utf-8")

    assert "assets/bf-heat-performance-quality-8093-query-v2.js?v=20260807-query-v2" in html
    assert "REQ-8093-HEAT-PERFORMANCE-QUALITY-QUERY-20260807" in source
    assert "bfHeatPerformanceQueryDrawer" in source
    assert "/api/heat-performance-quality" in source
    assert "date_from" in source and "date_to" in source and "has_samples" in source
