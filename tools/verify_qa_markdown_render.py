from __future__ import annotations

import asyncio
import json
from pathlib import Path

from playwright.async_api import async_playwright


async def main() -> None:
    errors: list[dict[str, str]] = []
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page(viewport={"width": 1600, "height": 1000})
        page.on(
            "console",
            lambda msg: errors.append({"type": msg.type, "text": msg.text})
            if msg.type in {"error", "warning"}
            else None,
        )
        page.on("pageerror", lambda exc: errors.append({"type": "pageerror", "text": str(exc)}))
        await page.goto(
            "http://127.0.0.1:8092/frontend_dashboard_v3.server.html?ws_port=8767#qa",
            wait_until="domcontentloaded",
            timeout=60_000,
        )
        await page.wait_for_selector(".qa-server-shell", timeout=60_000)
        item = page.locator(".qa-nav-item", has_text="请调用MCP工具画出最近1小时炉顶温度和顶压").first
        await item.click(timeout=30_000)
        await page.wait_for_timeout(2500)
        result = await page.evaluate(
            """() => ({
                mdCount: document.querySelectorAll('.qa-md').length,
                imgCount: document.querySelectorAll('.qa-md img[src*="/data/mcp_charts/"]').length,
                strongCount: document.querySelectorAll('.qa-md strong').length,
                codeCount: document.querySelectorAll('.qa-md code').length,
                imageSrc: document.querySelector('.qa-md img[src*="/data/mcp_charts/"]')?.getAttribute('src') || '',
                rawMarkdownVisible: Array.from(document.querySelectorAll('.qa-server-bubble')).some(x => /!\\[[^\\]]*\\]\\(|\\*\\*图片路径\\*\\*/.test(x.innerText || '')),
                activeTitle: document.querySelector('.qa-server-title')?.innerText || ''
            })"""
        )
        screenshot = Path("logs/qa_markdown_mcp_image_verify.png").resolve()
        screenshot.parent.mkdir(parents=True, exist_ok=True)
        await page.screenshot(path=str(screenshot), full_page=False)
        await browser.close()
    print(json.dumps({"result": result, "errors": errors[-10:], "screenshot": str(screenshot)}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
