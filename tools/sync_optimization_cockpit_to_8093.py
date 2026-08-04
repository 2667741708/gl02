"""Merge the reviewed front2 optimization cockpit into an existing 8093 HTML page.

REQ-8093-OPT-COCKPIT-DEPLOY-20260714.  This tool deliberately extracts only
the cockpit component and its scoped CSS from front2, keeping all unrelated
8093 fixes in the target page intact.  It is idempotent and can stage a
downloaded remote page before controlled deployment.
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "高炉前端数据" / "front2" / "frontend_dashboard_front2.server.html"
SOURCE_CSS = ROOT / "高炉前端数据" / "front2" / "front2-industrial.css"
DEFAULT_TARGET = ROOT / "高炉前端数据" / "frontend_dashboard_v3.server.html"
FUNCTION_START = "function OptimizationCockpitLayout({buf,diagnosis}){"
FUNCTION_END = "\n(function(){if(document.getElementById('v3-optimization-no-scroll-style')"
CSS_START = "/* Decision cockpit: parameter optimization route. Keeps real-time content compact and scanable. */"
STYLE_ID = "ops-8093-optimization-cockpit-20260714"
ASSIGNMENT = "OptimizationTab=OptimizationCockpitLayout;"
RENDER_MARKER = "window.__BF_RENDER_APP__&&window.__BF_RENDER_APP__();"


def extract_component() -> str:
    text = SOURCE.read_text(encoding="utf-8")
    start = text.find(FUNCTION_START)
    end = text.find(FUNCTION_END, start)
    if start < 0 or end < 0:
        raise RuntimeError("front2 cockpit component markers were not found")
    return text[start:end].rstrip() + "\n"


def extract_css() -> str:
    text = SOURCE_CSS.read_text(encoding="utf-8")
    start = text.find(CSS_START)
    if start < 0:
        raise RuntimeError("front2 cockpit CSS marker was not found")
    css = text[start:].strip()
    # front2 uses a body class; 8093 intentionally remains on its own body shell.
    return css.replace("body.front2-app:has", "body:has").replace("body.front2-app ", "").replace("body.front2-app", "body")


def sync_html(target_text: str) -> str:
    component = extract_component()
    if FUNCTION_START not in target_text:
        marker = "OptimizationTab=function BFOptimizationWorkbenchV10({buf,diagnosis}){"
        if marker not in target_text:
            raise RuntimeError("8093 V10 optimization entry marker was not found")
        target_text = target_text.replace(marker, component + marker, 1)
    style_tag = f'<style id="{STYLE_ID}">{extract_css()}</style>'
    old_style_start = f'<style id="{STYLE_ID}">'
    if old_style_start in target_text:
        old_start = target_text.find(old_style_start)
        old_end = target_text.find("</style>", old_start)
        if old_end < 0:
            raise RuntimeError("existing cockpit style is not closed")
        target_text = target_text[:old_start] + style_tag + target_text[old_end + len("</style>"):]
    else:
        if "</head>" not in target_text:
            raise RuntimeError("8093 HTML head end marker was not found")
        target_text = target_text.replace("</head>", style_tag + "</head>", 1)
    if ASSIGNMENT not in target_text:
        if RENDER_MARKER not in target_text:
            raise RuntimeError("8093 final render marker was not found")
        target_text = target_text.replace(RENDER_MARKER, ASSIGNMENT + "\n" + RENDER_MARKER, 1)
    return target_text


def verify(text: str) -> dict[str, bool]:
    return {
        "component": FUNCTION_START in text,
        "style": STYLE_ID in text and ".optimization-cockpit" in text,
        "render_binding": ASSIGNMENT in text,
        "legacy_v10_preserved": "BFOptimizationWorkbenchV10" in text,
        "formal_header_preserved": "topbar branded-topbar" in text,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Merge the front2 optimization cockpit into an 8093 HTML file.")
    parser.add_argument("--target", type=Path, default=DEFAULT_TARGET)
    parser.add_argument("--check", action="store_true", help="Check required cockpit markers without writing.")
    parser.add_argument("--no-backup", action="store_true", help="Do not create a timestamped sibling backup before writing.")
    args = parser.parse_args()
    target = args.target.resolve()
    text = target.read_text(encoding="utf-8")
    if args.check:
        checks = verify(text)
        print(json.dumps({"target": str(target), "ok": all(checks.values()), "checks": checks}, ensure_ascii=False))
        return 0 if all(checks.values()) else 1
    updated = sync_html(text)
    checks = verify(updated)
    if not all(checks.values()):
        raise RuntimeError(f"post-sync verification failed: {checks}")
    backup = None
    if not args.no_backup:
        backup = target.with_name(f"{target.name}.bak_optimization_cockpit_{datetime.now():%Y%m%d_%H%M%S}")
        backup.write_text(text, encoding="utf-8")
    target.write_text(updated, encoding="utf-8")
    print(json.dumps({"target": str(target), "backup": str(backup) if backup else None, "checks": checks}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
