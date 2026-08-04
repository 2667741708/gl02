#!/usr/bin/env python3
"""Deploy the isolated 8093 stable Billboard-hover runtime.

BUG-BF3D-8093-TOOLTIP-JITTER-SINGLE-OWNER-20260802

Run on 10.30.220.12 after uploading this script and the JavaScript payload.
Only the 8093 HTML and its dedicated hover asset may change.  The 8094 page,
shared Billboard adapter and 8094 camera runtime are protected by SHA-256.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
from datetime import datetime
from pathlib import Path


REQ_ID = "BUG-BF3D-8093-TOOLTIP-JITTER-SINGLE-OWNER-20260802"
HOVER_ASSET = "assets/bf3d-tooltip-stable-hover-8093.js"
HOVER_VERSION = "20260802-stable-hover-r2-emphasis122"
HOVER_MARKER = "<!-- 8093-only single-owner stable Billboard hover -->"
HOVER_TAG = (
    f"{HOVER_MARKER}\n"
    f'<script type="module" src="{HOVER_ASSET}?v={HOVER_VERSION}"></script>'
)
PREAMBLE_MARKER = "// BUG-BF3D-8093-TOOLTIP-JITTER-SINGLE-OWNER-20260802"
PREAMBLE = f"""{PREAMBLE_MARKER}
    window.__BF3D_HOVER_SINGLE_OWNER_8093__ = true;
    window.__BF_CAD_TOOLTIP_SMOOTH_COORD_FIX__ = true;
    window.__BF_CAD_TOOLTIP_LOCAL_COORD_FIX__ = true;
    window.__BF3D_CAD_SENSOR_TOOLTIP_8093__ = typeof cadSensorTooltip === 'function' ? cadSensorTooltip : window.cadSensorTooltip;
    """


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest().upper()


def atomic_write(path: Path, content: bytes) -> None:
    temporary = path.with_name(f"{path.name}.stable-hover.tmp")
    temporary.write_bytes(content)
    os.replace(temporary, path)


def locate_frontend(root: Path) -> Path:
    candidates = [
        path.parent
        for path in root.rglob("frontend_dashboard_v3.server.html")
        if (path.parent / "assets").is_dir()
    ]
    if len(candidates) != 1:
        raise RuntimeError(f"expected one 8093 frontend directory, found {candidates}")
    return candidates[0]


def patch_page(text: str) -> str:
    render_call = "window.__BF_RENDER_APP__ && window.__BF_RENDER_APP__();"
    if text.count(render_call) != 1:
        raise RuntimeError("8093 render call is missing or duplicated")

    preamble_pattern = re.compile(
        rf"\s*{re.escape(PREAMBLE_MARKER)}.*?window\.__BF3D_CAD_SENSOR_TOOLTIP_8093__\s*=.*?;\s*",
        re.DOTALL,
    )
    text = preamble_pattern.sub("\n    ", text, count=1)
    text = text.replace(render_call, PREAMBLE + render_call, 1)

    buffer_getter = "getBuffer: () => bufRef.current"
    getter_token = "const viewerApi = { getBuffer: () => bufRef.current, THREE,"
    legacy_viewer_token = "const viewerApi = { THREE,"
    direct_viewer_token = "window.__BF_CAD_FURNACE_VIEWER = { sensorObjects,"
    if buffer_getter not in text:
        if text.count(legacy_viewer_token) == 1:
            text = text.replace(legacy_viewer_token, getter_token, 1)
        elif direct_viewer_token in text:
            text = text.replace(
                direct_viewer_token,
                "window.__BF_CAD_FURNACE_VIEWER = { getBuffer: () => bufRef.current, sensorObjects,",
            )
        else:
            raise RuntimeError("8093 viewer buffer marker is missing")

    tag_pattern = re.compile(
        rf"(?:{re.escape(HOVER_MARKER)}\s*)?"
        rf'<script\s+type="module"\s+src="{re.escape(HOVER_ASSET)}[^\"]*"\s*></script>'
    )
    text = tag_pattern.sub("", text)
    if "</body>" not in text:
        raise RuntimeError("8093 page has no closing body tag")
    text = text.replace("</body>", f"  {HOVER_TAG}\n</body>", 1)

    if text.count(PREAMBLE_MARKER) != 1:
        raise RuntimeError("single-owner preamble is missing or duplicated")
    if text.index(PREAMBLE_MARKER) > text.index(render_call):
        raise RuntimeError("single-owner flags must be set before React render")
    if text.count(HOVER_ASSET) != 1:
        raise RuntimeError("8093 hover runtime tag is duplicated")
    if buffer_getter not in text:
        raise RuntimeError("viewer buffer getter was not exposed")
    return text


def deploy(root: Path, hover_payload: Path) -> dict[str, object]:
    frontend = locate_frontend(root)
    page_8093 = frontend / "frontend_dashboard_v3.server.html"
    page_8094 = frontend / "frontend_dashboard_v3.8094_preview.server.html"
    assets = frontend / "assets"
    target_hover = assets / "bf3d-tooltip-stable-hover-8093.js"
    shared_adapter = assets / "bf3d-furnace-body-billboard-adapter.js"
    camera_8094 = assets / "bf3d-surface-camera-guard-8094.js"
    required = (page_8093, page_8094, shared_adapter, camera_8094, hover_payload)
    missing = [str(path) for path in required if not path.is_file()]
    if missing:
        raise FileNotFoundError(f"required file missing: {missing}")

    payload_text = hover_payload.read_text(encoding="utf-8")
    for marker in (
        'SCHEMA = "bf3d.tooltip.stable-hover.8093.v1"',
        "enterRadiusPx: 30",
        "exitRadiusPx: 46",
        "switchMarginPx: 12",
        "switchDwellMs: 140",
        'coordinateSpace: "viewport-fixed"',
        "event.stopImmediatePropagation()",
        "pointFocusEnabled: false",
        'EMPHASIS_REQ_ID = "REQ-BF3D-8093-BILLBOARD-EMPHASIS-20260802"',
        "BILLBOARD_SCALE_MULTIPLIER = 1.22",
    ):
        if marker not in payload_text:
            raise RuntimeError(f"stable-hover payload marker missing: {marker}")

    hashes_before = {
        "page_8093": sha256(page_8093),
        "page_8094": sha256(page_8094),
        "shared_adapter": sha256(shared_adapter),
        "camera_8094": sha256(camera_8094),
    }
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup = root / "backups" / "8093_stable_tooltip_hover_20260802" / stamp
    backup.mkdir(parents=True, exist_ok=False)
    shutil.copy2(page_8093, backup / f"{page_8093.name}.bak")
    if target_hover.is_file():
        shutil.copy2(target_hover, backup / f"{target_hover.name}.bak")

    patched_page = patch_page(page_8093.read_text(encoding="utf-8"))
    atomic_write(target_hover, hover_payload.read_bytes())
    atomic_write(page_8093, patched_page.encode("utf-8"))

    deployed_page = page_8093.read_text(encoding="utf-8")
    deployed_hover = target_hover.read_text(encoding="utf-8")
    if HOVER_TAG not in deployed_page or PREAMBLE not in deployed_page:
        raise RuntimeError("deployed 8093 page failed the exact marker contract")
    if 'SCHEMA = "bf3d.tooltip.stable-hover.8093.v1"' not in deployed_hover:
        raise RuntimeError("deployed stable-hover asset failed its schema contract")

    hashes_after = {
        "page_8093": sha256(page_8093),
        "hover_8093": sha256(target_hover),
        "page_8094": sha256(page_8094),
        "shared_adapter": sha256(shared_adapter),
        "camera_8094": sha256(camera_8094),
    }
    for protected in ("page_8094", "shared_adapter", "camera_8094"):
        if hashes_before[protected] != hashes_after[protected]:
            raise RuntimeError(f"protected file changed: {protected}")

    return {
        "req_id": REQ_ID,
        "deployed": True,
        "root": str(root),
        "frontend": str(frontend),
        "backup": str(backup),
        "hashes_before": hashes_before,
        "hashes_after": hashes_after,
        "single_writer": True,
        "coordinate_space": "viewport-fixed",
        "selection_policy": "screen-space-hysteresis",
        "point_focus_enabled": False,
        "billboard_scale_multiplier": 1.22,
        "8094_unchanged": True,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--root",
        type=Path,
        default=Path(r"F:\高炉炼铁项目-real-sensor-v2_V4_8093_PREVIEW"),
    )
    parser.add_argument("--hover-payload", type=Path, required=True)
    args = parser.parse_args()
    result = deploy(args.root.resolve(), args.hover_payload.resolve())
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
