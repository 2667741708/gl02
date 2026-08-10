#!/usr/bin/env python3
"""Browser verification for 8093 pSpace live core values and DB fallback."""

from __future__ import annotations

import argparse
import asyncio
import json
import time
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from playwright.async_api import TimeoutError as PlaywrightTimeoutError
from playwright.async_api import async_playwright


ROOT = Path(__file__).resolve().parents[1]
ALL_VIEWPORTS = (
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


def with_cache_bust(url: str) -> str:
    parts = urlsplit(url)
    query = dict(parse_qsl(parts.query, keep_blank_values=True))
    query["core_live_qa"] = str(int(time.time() * 1000))
    return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(query), parts.fragment))


async def goto_overview(page, url: str) -> None:
    target = with_cache_bust(url)
    try:
        await page.goto(target, wait_until="domcontentloaded", timeout=45_000)
    except PlaywrightTimeoutError:
        await page.goto(target, wait_until="commit", timeout=20_000)
    await page.wait_for_selector(".core-pspace-live-8093", state="visible", timeout=45_000)


async def collect_page_rows(page) -> list[dict]:
    return await page.evaluate(
        """
        () => [...document.querySelectorAll('.core-page-v7-content .core-live-row')].map(row => {
          const rect = row.getBoundingClientRect();
          const meta = row.querySelector('.core-live-meta');
          const value = row.querySelector('.core-live-number');
          return {
            id: row.dataset.coreMetricId || '',
            source: row.dataset.valueSource || '',
            timestamp: row.dataset.valueTimestamp || '',
            ageSeconds: Number(row.dataset.valueAgeSeconds),
            transportAgeSeconds: Number(row.dataset.transportAgeSeconds),
            quality: row.dataset.valueQuality || '',
            value: value?.textContent?.trim() || '',
            meta: meta?.textContent?.trim() || '',
            title: row.querySelector('.core-live-value')?.getAttribute('title') || '',
            width: Number(rect.width.toFixed(2)),
            height: Number(rect.height.toFixed(2)),
            visible: getComputedStyle(row).display !== 'none' && rect.width > 0 && rect.height > 0,
          };
        })
        """
    )


async def inspect_viewport(page, url: str, expected_source: str, screenshot: Path) -> dict:
    page_errors: list[str] = []
    console_errors: list[dict[str, str]] = []
    page.on("pageerror", lambda error: page_errors.append(str(error)))
    page.on(
        "console",
        lambda message: console_errors.append(
            {"text": message.text, "url": str(message.location.get("url", ""))}
        )
        if message.type == "error"
        else None,
    )
    await goto_overview(page, url)

    if expected_source == "pspace_realtime":
        await page.wait_for_function(
            """
            () => document.querySelectorAll(
              '.core-live-row[data-value-source="pspace_realtime"]'
            ).length > 0
            """,
            timeout=30_000,
        )
    elif expected_source == "postgres_minute":
        await page.wait_for_function(
            """
            () => {
              const rows = [...document.querySelectorAll(
                '.core-live-row[data-value-source="postgres_minute"]'
              )];
              return rows.length > 0 && rows.every((row) => {
                const value = row.querySelector('.core-live-number')?.textContent?.trim() || '';
                return Boolean(row.dataset.valueTimestamp) && Boolean(value) && value !== '--';
              });
            }
            """,
            timeout=30_000,
        )

    tabs = page.locator(".core-metric-tabs-v7 button")
    tab_count = await tabs.count()
    all_rows: dict[str, dict] = {}
    tab_results: list[dict] = []
    for index in range(tab_count):
        await tabs.nth(index).click()
        await page.wait_for_timeout(350)
        rows = await collect_page_rows(page)
        for row in rows:
            all_rows[row["id"]] = row
        tab_results.append(
            {
                "index": index,
                "label": (await tabs.nth(index).inner_text()).strip(),
                "row_count": len(rows),
                "ids": [row["id"] for row in rows],
            }
        )

    shell = await page.evaluate(
        """
        () => {
          const content = document.querySelector('.core-page-v7-content');
          const banner = document.querySelector('.core-live-banner');
          const state = window.__BF_CORE_PSPACE_LIVE__ || {};
          return {
            viewportWidth: innerWidth,
            documentWidth: document.documentElement.scrollWidth,
            formalHeader: !!document.querySelector('.topbar.branded-topbar'),
            banner: banner?.textContent?.trim() || '',
            bannerVisible: !!banner && banner.getBoundingClientRect().height > 0,
            contentOverflowY: content ? getComputedStyle(content).overflowY : '',
            contentClientHeight: content?.clientHeight || 0,
            contentScrollHeight: content?.scrollHeight || 0,
            schema: state.schema || '',
            status: state.status || '',
            validCount: Number(state.validCount || 0),
            lastFrameAt: state.lastFrameAt || '',
          };
        }
        """
    )

    failures: list[str] = []
    if tab_count != 2:
        failures.append(f"tab_count:{tab_count}")
    if len(all_rows) != 28:
        failures.append(f"unique_core_ids:{len(all_rows)}")
    if not shell["formalHeader"]:
        failures.append("formal_header_missing")
    if not shell["bannerVisible"]:
        failures.append("live_banner_hidden")
    if shell["documentWidth"] > shell["viewportWidth"] + 1:
        failures.append("horizontal_overflow")
    if shell["schema"] != "bf.core-metrics.pspace-live.8093.v1":
        failures.append(f"schema:{shell['schema']}")

    for sensor_id, row in all_rows.items():
        if not row["visible"]:
            failures.append(f"{sensor_id}:hidden")
        if expected_source != "auto" and row["source"] != expected_source:
            failures.append(f"{sensor_id}:source:{row['source']}")
        if not row["meta"] or not row["quality"]:
            failures.append(f"{sensor_id}:freshness_or_quality_missing")
        if expected_source == "pspace_realtime":
            if not row["timestamp"]:
                failures.append(f"{sensor_id}:timestamp_missing")
            if row["ageSeconds"] < 0:
                failures.append(f"{sensor_id}:source_age:{row['ageSeconds']}")
            if not 0 <= row["transportAgeSeconds"] <= 12:
                failures.append(
                    f"{sensor_id}:transport_age:{row['transportAgeSeconds']}"
                )
            if row["value"] in {"", "--"}:
                failures.append(f"{sensor_id}:value_missing")
        if expected_source == "postgres_minute" and "已降级为分钟镜像" not in row["title"]:
            failures.append(f"{sensor_id}:fallback_not_explicit")
        if expected_source == "postgres_minute":
            if not row["timestamp"]:
                failures.append(f"{sensor_id}:fallback_timestamp_missing")
            if row["value"] in {"", "--"}:
                failures.append(f"{sensor_id}:fallback_value_missing")

    if expected_source == "pspace_realtime" and "pSpace秒级实时" not in shell["banner"]:
        failures.append("live_banner_contract")
    if expected_source == "postgres_minute" and "已降级为分钟镜像" not in shell["banner"]:
        failures.append("fallback_banner_contract")

    filtered_console_errors = [
        item
        for item in console_errors
        if "favicon.ico" not in item["url"]
        and "WebSocket connection" not in item["text"]
        and "Failed to fetch" not in item["text"]
    ]
    if page_errors or filtered_console_errors:
        failures.append("page_or_console_errors")

    await page.screenshot(path=str(screenshot), full_page=False)
    return {
        "passed": not failures,
        "failures": failures,
        "shell": shell,
        "tabs": tab_results,
        "rows": list(all_rows.values()),
        "page_errors": page_errors,
        "console_errors": filtered_console_errors,
        "screenshot": str(screenshot),
    }


async def verify(args: argparse.Namespace) -> dict:
    viewports = ALL_VIEWPORTS if args.matrix == "all" else REPRESENTATIVE_VIEWPORTS
    output = Path(args.out_dir).resolve()
    output.mkdir(parents=True, exist_ok=True)
    results: list[dict] = []
    async with async_playwright() as playwright:
        if args.browser == "msedge":
            browser = await playwright.chromium.launch(headless=True, channel="msedge")
        else:
            browser = await getattr(playwright, args.browser).launch(headless=True)
        for width, height in viewports:
            page = await browser.new_page(viewport={"width": width, "height": height})
            screenshot = output / (
                f"core_pspace_{args.expected_source}_{args.browser}_{width}x{height}.png"
            )
            try:
                result = await inspect_viewport(
                    page,
                    args.url,
                    args.expected_source,
                    screenshot,
                )
            except Exception as error:  # pragma: no cover - runtime evidence path
                result = {
                    "passed": False,
                    "failures": ["unhandled_error"],
                    "error": str(error),
                    "screenshot": str(screenshot),
                }
            results.append(
                {
                    "browser": args.browser,
                    "viewport": f"{width}x{height}",
                    "url": args.url,
                    "expected_source": args.expected_source,
                    **result,
                }
            )
            await page.close()
        await browser.close()
    return {
        "schema": "qa.8093.core-metrics-pspace-live.v1",
        "browser": args.browser,
        "matrix": args.matrix,
        "expected_source": args.expected_source,
        "passed": all(result["passed"] for result in results),
        "results": results,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--url",
        default="http://10.30.220.12:8093/?ws_port=8768#overview",
    )
    parser.add_argument(
        "--browser",
        choices=("chromium", "firefox", "webkit", "msedge"),
        default="chromium",
    )
    parser.add_argument("--matrix", choices=("all", "representative"), default="all")
    parser.add_argument(
        "--expected-source",
        choices=("pspace_realtime", "postgres_minute", "auto"),
        default="pspace_realtime",
    )
    parser.add_argument(
        "--out-dir",
        default=str(ROOT / "logs" / "8093_core_metrics_pspace_live_qa"),
    )
    args = parser.parse_args()

    payload = asyncio.run(verify(args))
    output = Path(args.out_dir).resolve()
    output.mkdir(parents=True, exist_ok=True)
    manifest = output / f"manifest_{args.expected_source}_{args.browser}_{args.matrix}.json"
    manifest.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"passed": payload["passed"], "manifest": str(manifest)}, ensure_ascii=False))
    return 0 if payload["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
