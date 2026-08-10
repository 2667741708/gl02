# -*- coding: utf-8 -*-
from __future__ import annotations

import asyncio

from playwright.async_api import async_playwright


async def main() -> None:
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page(viewport={"width": 1366, "height": 768})
        console_errors: list[str] = []
        page_errors: list[str] = []
        failed_requests: list[str] = []
        page.on("console", lambda msg: console_errors.append(msg.text) if msg.type == "error" else None)
        page.on("pageerror", lambda exc: page_errors.append(str(exc)))
        page.on("requestfailed", lambda request: failed_requests.append(f"{request.url}: {request.failure}"))
        response = await page.goto("http://10.30.220.12:8094/?trend19_diag=20260807#trend", wait_until="domcontentloaded", timeout=90000)
        await page.wait_for_timeout(15000)
        result = await page.evaluate("""() => ({
          url: location.href,
          ready: document.readyState,
          text: document.body?.innerText?.slice(0, 2000) || '',
          hasTitle: document.body?.innerText?.includes('19个核心变量趋势与预测') || false,
          appChildren: document.querySelector('.app')?.children.length || 0,
          scripts: [...document.scripts].map(s => ({type: s.type, src: s.src, length: s.textContent.length}))
        })""")
        print({"status": response.status if response else None, "result": result, "console_errors": console_errors, "page_errors": page_errors, "failed_requests": failed_requests})
        await browser.close()


if __name__ == "__main__":
    asyncio.run(main())
