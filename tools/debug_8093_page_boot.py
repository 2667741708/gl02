import asyncio
from playwright.async_api import async_playwright

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page(viewport={"width": 1366, "height": 768})
        errors = []
        page.on("pageerror", lambda exc: errors.append(f"pageerror: {exc}"))
        page.on("console", lambda msg: errors.append(f"console-{msg.type}: {msg.text}") if msg.type in {"error", "warning"} else None)
        response = await page.goto("http://10.30.220.12:8093/?ws_port=8768&optimization_polish_case=1#optimization", wait_until="domcontentloaded", timeout=60000)
        await page.wait_for_timeout(8000)
        print({"status": response.status if response else None, "hash": await page.evaluate("location.hash"), "root": await page.locator("#root").inner_html(), "errors": errors})
        await browser.close()

asyncio.run(main())
