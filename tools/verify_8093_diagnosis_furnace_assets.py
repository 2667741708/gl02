"""Verify the eight-condition furnace image mapping and diagnosis score layout.

Requirement: REQ-8093-DIAG-FURNACE-ASSETS-20260714.
The check is intentionally static plus HTTP asset reachability so it can run
before a live diagnosis happens to select every one of the eight conditions.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import struct
import urllib.request
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
HTML = ROOT / "高炉前端数据" / "frontend_dashboard_v3.server.html"
FRONT2_HTML = ROOT / "高炉前端数据" / "front2" / "frontend_dashboard_front2.server.html"
ASSET_DIR = ROOT / "高炉前端数据" / "assets" / "furnace-conditions"
EXPECTED = {
    "normal": "normal.png",
    "lowline": "lowline.png",
    "edge": "edge.png",
    "center": "center.png",
    "channel": "channel.png",
    "cold": "cold.png",
    "hot": "hot.png",
    "column": "column.png",
}


def png_size(path: Path) -> tuple[int, int]:
    header = path.read_bytes()[:24]
    if len(header) != 24 or header[:8] != b"\x89PNG\r\n\x1a\n":
        raise ValueError(f"not a PNG: {path}")
    return struct.unpack(">II", header[16:24])


def fetch_ok(url: str) -> bool:
    request = urllib.request.Request(url, headers={"User-Agent": "diagnosis-furnace-verifier/1.0"})
    with urllib.request.urlopen(request, timeout=15) as response:
        return response.status == 200 and int(response.headers.get("Content-Length", "0") or 0) > 100_000


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify eight diagnosis furnace image assets and mappings.")
    parser.add_argument("--base-url", default="", help="Optional running page base URL, for example http://127.0.0.1:8093")
    args = parser.parse_args()

    html = HTML.read_text(encoding="utf-8")
    front2 = FRONT2_HTML.read_text(encoding="utf-8")
    mapping_tokens = [f"{key}:'{name}'" for key, name in EXPECTED.items()]
    assets = {key: ASSET_DIR / name for key, name in EXPECTED.items()}
    dimensions = {key: png_size(path) for key, path in assets.items() if path.is_file()}
    hashes = {
        key: hashlib.sha256(path.read_bytes()).hexdigest()
        for key, path in assets.items()
        if path.is_file()
    }

    checks = {
        "requirement_marker": "REQ-8093-DIAG-FURNACE-ASSETS-20260714" in html,
        "eight_mapping_entries": all(token in html for token in mapping_tokens),
        "front2_mapping_consistent": all(token in front2 for token in mapping_tokens),
        "diagnosis_passes_main_label": "<MiniFurnaceIcon label={d.label}/>" in html,
        "active_image_component_after_svg": html.rfind("BFConditionFurnaceImage") > html.find("function MiniFurnaceIcon(){return <svg"),
        "score_value_inline": all(token in html for token in ("bf-diag-score-number", "bf-diag-rank-main", "font-variant-numeric:tabular-nums")),
        "assets_exist": len(dimensions) == 8,
        "assets_same_canvas": len(set(dimensions.values())) == 1 and next(iter(dimensions.values()), None) == (1086, 1448),
        "assets_are_distinct": len(set(hashes.values())) == 8,
    }

    http_assets: dict[str, bool] = {}
    if args.base_url:
        base = args.base_url.rstrip("/")
        for key, name in EXPECTED.items():
            try:
                http_assets[key] = fetch_ok(f"{base}/assets/furnace-conditions/{name}")
            except Exception:
                http_assets[key] = False
        checks["http_assets"] = all(http_assets.values())

    failed = [name for name, ok in checks.items() if not ok]
    result = {
        "ok": not failed,
        "failed": failed,
        "checks": checks,
        "dimensions": {key: list(value) for key, value in dimensions.items()},
        "http_assets": http_assets,
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
