#!/usr/bin/env python3
"""Browser acceptance checks for the local diagnosis-review prototype."""

from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path
from urllib.parse import quote


ROOT = Path(__file__).resolve().parents[1]
ROUTES = ("overview", "diagnosis", "optimization", "trend", "qa")
CHROMIUM_VIEWPORTS = (
    (1280, 720), (1366, 768), (1440, 900), (1546, 864), (1920, 1080),
    (1024, 768), (768, 1024), (390, 844), (375, 667),
)
REPRESENTATIVE_VIEWPORTS = ((1920, 1080), (1366, 768), (768, 1024), (390, 844))


def main() -> int:
    parser = argparse.ArgumentParser(description="验证本机异常炉况复核弹窗")
    parser.add_argument("--base-url", default="http://127.0.0.1:8096")
    parser.add_argument("--engines", default="chromium,firefox,webkit")
    parser.add_argument("--ws-port", default="8769")
    args = parser.parse_args()
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        raise SystemExit("缺少 Playwright；请先安装浏览器测试依赖。") from exc

    engines = [name.strip() for name in args.engines.split(",") if name.strip()]
    output = ROOT / "logs" / f"diagnosis_review_browser_{datetime.now():%Y%m%d_%H%M%S}"
    output.mkdir(parents=True, exist_ok=True)
    results = []
    with sync_playwright() as playwright:
        for engine_name in engines:
            browser_type = getattr(playwright, engine_name)
            browser = browser_type.launch(headless=True)
            viewports = CHROMIUM_VIEWPORTS if engine_name == "chromium" else REPRESENTATIVE_VIEWPORTS
            try:
                for route in ROUTES:
                    for width, height in viewports:
                        context = browser.new_context(viewport={"width": width, "height": height})
                        page = context.new_page()
                        console_errors = []
                        page.on("console", lambda message, target=console_errors: target.append(message.text) if message.type == "error" else None)
                        case_id = quote(f"matrix-{engine_name}-{route}-{width}x{height}")
                        url = f"{args.base_url}/frontend_dashboard_v3.server.html?ws_port={args.ws_port}&fixture=cold&case_id={case_id}#{route}"
                        record = {"engine": engine_name, "viewport": f"{width}x{height}", "route": route, "url": url, "failures": []}
                        try:
                            page.goto(url, wait_until="domcontentloaded", timeout=30000)
                            page.locator(".bfdr-dialog").wait_for(state="visible", timeout=15000)
                            if page.locator(".bfdr-score-row").count() != 7:
                                record["failures"].append("候选分数不是七类")
                            overflow = page.evaluate("document.documentElement.scrollWidth > document.documentElement.clientWidth")
                            if overflow:
                                record["failures"].append("页面存在横向溢出")
                            if not page.locator(".bfdr-close").is_enabled():
                                record["failures"].append("关闭按钮不可操作")
                            page.locator(".bfdr-close").click()
                            if console_errors:
                                record["failures"].append("控制台错误：" + " | ".join(console_errors[:5]))
                        except Exception as exc:  # noqa: BLE001
                            record["failures"].append(str(exc))
                        if record["failures"]:
                            shot = output / f"FAIL_{engine_name}_{route}_{width}x{height}.png"
                            page.screenshot(path=str(shot), full_page=True)
                            record["screenshot"] = str(shot)
                        results.append(record)
                        context.close()
            finally:
                browser.close()

    report = {
        "generated_at": datetime.now().isoformat(),
        "base_url": args.base_url,
        "checks": len(results),
        "failed": sum(bool(item["failures"]) for item in results),
        "results": results,
    }
    report_path = output / "report.json"
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"ok": report["failed"] == 0, "checks": report["checks"], "failed": report["failed"], "report": str(report_path)}, ensure_ascii=False))
    return 0 if report["failed"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
