#!/usr/bin/env python3
"""Browser acceptance checks for the local diagnosis-review prototype."""

from __future__ import annotations

import argparse
import json
import re
import time
from datetime import datetime
from pathlib import Path
from urllib.parse import quote


ROOT = Path(__file__).resolve().parents[1]
ROUTES = ("overview", "diagnosis", "optimization", "trend", "qa")
CHROMIUM_VIEWPORTS = (
    (1280, 720),
    (1366, 768),
    (1440, 900),
    (1546, 864),
    (1920, 1080),
    (1024, 768),
    (768, 1024),
    (390, 844),
    (375, 667),
)
REPRESENTATIVE_VIEWPORTS = ((1920, 1080), (1366, 768), (768, 1024), (390, 844))
QUICK_VIEWPORTS = {
    "chromium": ((1366, 768), (390, 844)),
    "firefox": ((1366, 768),),
    "webkit": ((1366, 768),),
}
IGNORED_CONSOLE_ERROR_SNIPPETS = ("code generator has deoptimised the styling",)


def is_actionable_console_error(text: str) -> bool:
    return not any(snippet in text for snippet in IGNORED_CONSOLE_ERROR_SNIPPETS)


def validation_matrix(
    profile: str, engine_name: str
) -> tuple[tuple[str, tuple[int, int]], ...]:
    """Return a risk-tiered route/viewport matrix for one browser engine."""

    if engine_name not in {"chromium", "firefox", "webkit"}:
        raise ValueError(f"unsupported browser engine: {engine_name}")
    full_viewports = (
        CHROMIUM_VIEWPORTS if engine_name == "chromium" else REPRESENTATIVE_VIEWPORTS
    )
    if profile == "quick":
        routes = ("diagnosis",)
        viewports = QUICK_VIEWPORTS[engine_name]
    elif profile == "standard":
        routes = ("diagnosis",)
        viewports = full_viewports
    elif profile == "full":
        routes = ROUTES
        viewports = full_viewports
    else:
        raise ValueError(f"unsupported validation profile: {profile}")
    return tuple((route, viewport) for route in routes for viewport in viewports)


def main() -> int:
    parser = argparse.ArgumentParser(description="验证本机异常炉况复核弹窗")
    parser.add_argument("--base-url", default="http://127.0.0.1:8096")
    parser.add_argument("--engines", default="chromium,firefox,webkit")
    parser.add_argument("--ws-port", default="8769")
    parser.add_argument(
        "--profile",
        choices=("quick", "standard", "full"),
        default="quick",
        help="quick=4 targeted checks, standard=17 diagnosis checks, full=85 all-route checks",
    )
    parser.add_argument(
        "--check-manual-score",
        action="store_true",
        help="Open and validate the manual-score dialog; implied by standard/full profiles.",
    )
    parser.add_argument(
        "--live",
        action="store_true",
        help="Use the live server-owned diagnosis context instead of loopback-only fixtures.",
    )
    args = parser.parse_args()
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        raise SystemExit("缺少 Playwright；请先安装浏览器测试依赖。") from exc

    engines = [name.strip() for name in args.engines.split(",") if name.strip()]
    output = ROOT / "logs" / f"diagnosis_review_browser_{datetime.now():%Y%m%d_%H%M%S}"
    output.mkdir(parents=True, exist_ok=True)
    results = []
    started = time.perf_counter()
    with sync_playwright() as playwright:
        for engine_name in engines:
            browser_type = getattr(playwright, engine_name)
            browser = browser_type.launch(headless=True)
            matrix = validation_matrix(args.profile, engine_name)
            initial_width, initial_height = matrix[0][1]
            context = browser.new_context(
                viewport={"width": initial_width, "height": initial_height}
            )
            try:
                for route, (width, height) in matrix:
                    page = context.new_page()
                    if not args.live:
                        page.add_init_script("localStorage.clear(); sessionStorage.clear();")
                    page.set_viewport_size({"width": width, "height": height})
                    console_errors = []
                    failed_responses = []
                    page.on(
                        "console",
                        lambda message, target=console_errors: target.append(
                            message.text
                        )
                        if message.type == "error"
                        and is_actionable_console_error(message.text)
                        else None,
                    )
                    page.on(
                        "response",
                        lambda response, target=failed_responses: target.append(
                            f"HTTP {response.status} {response.url}"
                        )
                        if response.status >= 400
                        else None,
                    )
                    case_prefix = "evidence-cn" if args.profile == "quick" else "matrix"
                    case_id = quote(f"{case_prefix}-{engine_name}-{route}-{width}x{height}")
                    query = f"ws_port={args.ws_port}&cb={case_id}"
                    if not args.live:
                        query += f"&fixture=cold&case_id={case_id}"
                    url = f"{args.base_url}/frontend_dashboard_v3.server.html?{query}#{route}"
                    record = {
                        "engine": engine_name,
                        "viewport": f"{width}x{height}",
                        "route": route,
                        "url": url,
                        "failures": [],
                    }
                    try:
                        navigation_started = time.perf_counter()
                        page.goto(url, wait_until="domcontentloaded", timeout=30000)
                        record["navigation_ms"] = round(
                            (time.perf_counter() - navigation_started) * 1000, 1
                        )
                        page.locator(".bfdr-dialog").wait_for(
                            state="visible", timeout=15000
                        )
                        if page.locator(".bfdr-score-row").count() != 7:
                            record["failures"].append("候选分数不是七类")
                        evidence_wrap = page.locator(".bfdr-evidence-wrap")
                        evidence_text = evidence_wrap.inner_text()
                        score_names = page.locator(".bfdr-score-name").all_inner_texts()
                        forbidden_codes = (
                            "low_body_temperature",
                            "low_blast_pressure",
                            "operation_heat_reduction",
                        )
                        if any(code in evidence_text for code in forbidden_codes):
                            record["failures"].append("主要诊断证据仍显示英文内部码")
                        if args.profile == "quick":
                            for expected in ("炉体温度偏低", "风压偏低", "操作减热", "诊断证据"):
                                if expected not in evidence_text:
                                    record["failures"].append(f"主要诊断证据缺少中文名：{expected}")
                            if evidence_wrap.locator("img").count() != 0:
                                record["failures"].append("证据标题未保持文本转义")
                            if "<img src=x onerror=alert(1)>" not in evidence_text:
                                record["failures"].append("证据特殊字符未按纯文本显示")
                        if any(
                            re.search(r"[A-Za-z][A-Za-z0-9_]*", name)
                            for name in score_names
                        ):
                            record["failures"].append("候选炉况名称仍包含英文内部码")
                        overflow = page.evaluate(
                            "document.documentElement.scrollWidth > document.documentElement.clientWidth"
                        )
                        if overflow:
                            record["failures"].append("页面存在横向溢出")
                        if not page.locator(".bfdr-close").is_enabled():
                            record["failures"].append("关闭按钮不可操作")
                        page.locator(".bfdr-close").click()
                        if route == "diagnosis":
                            core = page.locator(
                                '.diag-vars-wrap[data-core-variable-contract="no-throat-temperature-20260811"]'
                            )
                            core.wait_for(state="visible", timeout=5000)
                            cards = core.locator(".diag-var-card[data-core-variable-id]")
                            if cards.count() != 32:
                                record["failures"].append("核心诊断变量不是32项")
                            core_ids = set(
                                cards.evaluate_all(
                                    "nodes => nodes.map(node => node.dataset.coreVariableId)"
                                )
                            )
                            throat_ids = {
                                "T_throat_A",
                                "T_throat_B",
                                "T_throat_C",
                                "T_throat_D",
                            }
                            if core_ids & throat_ids:
                                record["failures"].append("核心诊断变量仍包含炉喉温度")
                            if not {
                                "T_top_A",
                                "T_top_B",
                                "T_top_C",
                                "T_top_D",
                            }.issubset(core_ids):
                                record["failures"].append("四点炉顶温度被误删")
                        if route == "diagnosis" and (
                            args.check_manual_score or args.profile != "quick"
                        ):
                            cards = page.locator(".diag-rank-card[data-bfdms-label]")
                            if cards.count() != 8:
                                record["failures"].append("手动评分入口不是八类")
                            else:
                                page.locator(
                                    '.diag-rank-card[data-bfdms-label="cold"]'
                                ).click()
                                page.locator(".bfdms-dialog").wait_for(
                                    state="visible", timeout=5000
                                )
                                if (
                                    page.locator(".bfdms-score").count() != 1
                                    or page.locator(".bfdms-suggestion").count() != 1
                                ):
                                    record["failures"].append("手动评分字段不完整")
                                page.locator(".bfdms-close").click()
                        if console_errors:
                            record["failures"].append(
                                "控制台错误：" + " | ".join(console_errors[:5])
                            )
                        if failed_responses:
                            record["failures"].append(
                                "资源请求失败：" + " | ".join(failed_responses[:5])
                            )
                    except Exception as exc:  # noqa: BLE001
                        record["failures"].append(str(exc))
                    if record["failures"]:
                        shot = (
                            output / f"FAIL_{engine_name}_{route}_{width}x{height}.png"
                        )
                        page.screenshot(path=str(shot), full_page=True)
                        record["screenshot"] = str(shot)
                    results.append(record)
                    page.close()
            finally:
                context.close()
                browser.close()

    report = {
        "generated_at": datetime.now().isoformat(),
        "base_url": args.base_url,
        "profile": args.profile,
        "browser_context_reused_per_engine": True,
        "checks": len(results),
        "failed": sum(bool(item["failures"]) for item in results),
        "elapsed_seconds": round(time.perf_counter() - started, 3),
        "results": results,
    }
    report_path = output / "report.json"
    report_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(
        json.dumps(
            {
                "ok": report["failed"] == 0,
                "profile": args.profile,
                "checks": report["checks"],
                "failed": report["failed"],
                "elapsed_seconds": report["elapsed_seconds"],
                "report": str(report_path),
            },
            ensure_ascii=False,
        )
    )
    return 0 if report["failed"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
