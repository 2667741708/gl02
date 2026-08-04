from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

try:
    from playwright.async_api import async_playwright
except ModuleNotFoundError:
    async_playwright = None


ROOT = Path(__file__).resolve().parents[1]


def default_file_url() -> str:
    return (ROOT / "高炉前端数据" / "frontend_dashboard_v3.server.html").resolve().as_uri()


def with_hash(url: str, tab: str) -> str:
    parts = urlsplit(url)
    query = parts.query
    extra = "worker_wording_case=1"
    query = f"{query}&{extra}" if query else extra
    return urlunsplit((parts.scheme, parts.netloc, parts.path, query, tab))


async def read_tab_text(page, url: str, tab: str) -> str:
    await page.goto(with_hash(url, tab), wait_until="domcontentloaded")
    await page.wait_for_selector(".app", timeout=30_000)
    await page.wait_for_timeout(1200)
    if tab == "diagnosis":
        button = page.locator("button", has_text="工长关注项")
        if await button.count():
            await button.first.click()
            await page.wait_for_timeout(300)
    return await page.evaluate("() => document.body.innerText")


async def inspect(url: str) -> dict:
    if async_playwright is None:
        html = (ROOT / "高炉前端数据" / "frontend_dashboard_v3.server.html").read_text(encoding="utf-8")
        override = html.split("function workerText", 1)[-1]
        optimization = html.split("function OptimizationTab({", 1)[-1].split("(function(){if(document.getElementById('v3-optimization-no-scroll-style')", 1)[0]
        trend = html.split("function TrendTab({", 1)[-1].split("function qaNow", 1)[0]
        diagnosis = html.split("function diagScoreTone", 1)[-1].split("function BaselineCompareLegacy", 1)[0] + override
        return {
            "texts": {
                "source_override": override,
                "overview": override,
                "diagnosis": diagnosis,
                "optimization": optimization,
                "trend": trend,
            },
            "page_errors": [],
            "console_errors": [],
            "fallback": "playwright_not_installed_source_override_check",
        }
    page_errors: list[str] = []
    console_errors: list[str] = []
    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch(headless=True)
        page = await browser.new_page(viewport={"width": 1366, "height": 768})
        page.on("pageerror", lambda exc: page_errors.append(str(exc)))
        page.on("console", lambda msg: console_errors.append(msg.text) if msg.type == "error" else None)
        texts = {tab: await read_tab_text(page, url, tab) for tab in ["overview", "diagnosis", "optimization", "trend"]}
        await browser.close()
    return {
        "texts": texts,
        "page_errors": page_errors,
        "console_errors": [
            e for e in console_errors if "Failed to fetch" not in e and 'URL scheme "file"' not in e
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify worker-facing wording in the V3/V4 frontend.")
    parser.add_argument("--url", default=default_file_url(), help="Base frontend URL or file URL.")
    args = parser.parse_args()

    result = asyncio.run(inspect(args.url))
    failures: list[str] = []
    if result["page_errors"] or result["console_errors"]:
        failures.append("page_or_console_errors")

    visible_all = "\n".join(result["texts"].values())
    forbidden_visible = [
        "触发或接近阈值",
        "铁口温度代理",
        "置信度：",
        "规则命中",
        "建议性质",
        "触发依据",
        "预期作用",
        "注意事项",
        "关键指标对比",
        "窗口前",
    ]
    if not result.get("fallback"):
        hits = [word for word in forbidden_visible if word in visible_all]
        if hits:
            failures.append("forbidden_visible_words:" + ",".join(hits))

    required = {
        "overview": ["判断把握"],
        "diagnosis": ["红=严重", "工长关注项", "判断把握"],
        "optimization": ["强度", "依据", "作用", "现场确认", "参考范围/口径", "15分钟变化"],
        "trend": ["关键指标变化", "窗口起点", "预测终点"],
    }
    missing = [
        f"{tab}:{word}"
        for tab, words in required.items()
        for word in words
        if word not in result["texts"].get(tab, "")
    ]
    if missing:
        failures.append("missing_required_words:" + ",".join(missing))

    payload = {
        "failed": len(failures),
        "failures": failures,
        "visible_lengths": {tab: len(text) for tab, text in result["texts"].items()},
        "page_errors": result["page_errors"],
        "console_errors": result["console_errors"],
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
