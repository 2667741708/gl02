from __future__ import annotations

import hashlib
import json
from pathlib import Path


FRONT2_DIR = Path(__file__).resolve().parent
FRONTEND_DIR = FRONT2_DIR.parent
ORIGINAL = FRONTEND_DIR / "frontend_dashboard_v3.server.html"
FRONT2 = FRONT2_DIR / "frontend_dashboard_front2.server.html"
THEME = FRONT2_DIR / "front2-industrial.css"
INDUSTRIAL_FURNACE_ASSET = FRONT2_DIR / "assets" / "blast-furnace-cutaway-industrial-v1.png"
CONDITION_ASSET_DIR = FRONT2_DIR / "assets" / "furnace-conditions"
CONDITION_ASSET_NAMES = ("normal.png", "lowline.png", "edge.png", "center.png", "channel.png", "cold.png", "hot.png", "column.png")
EXPECTED_ORIGINAL_SHA256 = "470CAA57EAFBC72A03C7B9C5F0CA5C4A22B81DECDE83DBC8B866D196A83DD03A"
OPTIMIZATION_COCKPIT_STYLE_START = '<style id="ops-8093-optimization-cockpit-20260714">'
OPTIMIZATION_COCKPIT_STYLE_END = '</style>'


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest().upper()


def remove_cockpit_style(html: str) -> str:
    start = html.find(OPTIMIZATION_COCKPIT_STYLE_START)
    if start < 0:
        return html
    end = html.find(OPTIMIZATION_COCKPIT_STYLE_END, start)
    if end < 0:
        return html
    return html[:start] + html[end + len(OPTIMIZATION_COCKPIT_STYLE_END):]


def main() -> int:
    original = ORIGINAL.read_text(encoding="utf-8")
    front2 = FRONT2.read_text(encoding="utf-8")
    theme = THEME.read_text(encoding="utf-8")
    normalized_front2 = front2.replace('<body class="front2-app">', '<body>', 1).replace(
        '<link id="front2-industrial-theme" rel="stylesheet" href="/front2/front2-industrial.css">',
        "",
        1,
    )
    checks = {
        "original_sha256_unchanged": sha256(ORIGINAL) == EXPECTED_ORIGINAL_SHA256,
        "original_optimization_cockpit": all(
            token in original
            for token in (
                "OptimizationCockpitLayout",
                "ops-8093-optimization-cockpit-20260714",
                "OptimizationTab=OptimizationCockpitLayout;",
            )
        ),
        "front2_cockpit_consistent": all(
            token in normalized_front2 and token in original
            for token in (
                "function OptimizationCockpitLayout({buf,diagnosis}){",
                "OptimizationTab=OptimizationCockpitLayout;",
                "buildDynamicOptimization",
                "ACTION_KNOWLEDGE",
            )
        ),
        "front2_scope": 'body class="front2-app"' in front2,
        "front2_theme_link": '/front2/front2-industrial.css' in front2,
        "industrial_furnace_asset": INDUSTRIAL_FURNACE_ASSET.is_file()
        and INDUSTRIAL_FURNACE_ASSET.stat().st_size > 100_000,
        "condition_furnace_assets": all(
            (CONDITION_ASSET_DIR / name).is_file()
            and (CONDITION_ASSET_DIR / name).stat().st_size > 100_000
            and f"'{name}'" in front2
            for name in CONDITION_ASSET_NAMES
        )
        and "BFConditionFurnaceImage" in front2
        and "<MiniFurnaceIcon label={d.label}/>" in front2,
        "five_routes": all(f"['{route}'" in front2 for route in ("overview", "diagnosis", "optimization", "trend", "qa")),
        "websocket_contract": "chronos_predict_recommended_batch" in front2 and "diagnosis_history" in front2,
        "qa_sse_contract": all(token in front2 for token in ("/api/qa/chat", "start", "delta", "final", "error")),
        "trend_history_marker": "__BF_TREND_HISTORY_PATCHED__" in front2,
        "automation_marker": "__BF_AUTOMATION_MONITOR__" in front2,
        "formal_brand_header": all(
            token in front2
            for token in (
                "高炉工艺大模型智能决策系统",
                "炽穹・高炉炼铁大模型",
                "logo/冀南钢铁集团logo.png",
                "logo/燕山大学logo.png",
            )
        ),
        "industrial_tokens": all(
            token in theme
            for token in ("--f2-surface", "--f2-accent", "#4eb6aa", "SimSun", "max-width: 1279px")
        ),
    }
    failed = [name for name, passed in checks.items() if not passed]
    payload = {
        "ok": not failed,
        "failed": failed,
        "checks": checks,
        "original_sha256": sha256(ORIGINAL),
        "front2_sha256": sha256(FRONT2),
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
