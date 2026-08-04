from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

from playwright.async_api import async_playwright


ROOT = Path(__file__).resolve().parents[1]
EXPECTED_LABELS = ["正常\n顺行", "低料线", "边缘\n发展", "中心\n过吹", "管道\n行程", "炉凉", "炉热", "崩滑\n悬料"]
EXPECTED_COLORS = {"#58dc7a", "#ffd54a", "#ef515d"}
EXPECTED_HISTORY_POINTS = 12


def default_file_url() -> str:
    return (ROOT / "高炉前端数据" / "frontend_dashboard_v3.server.html").resolve().as_uri()


def with_diagnosis_hash(url: str) -> str:
    parts = urlsplit(url)
    query = parts.query
    extra = "score_histogram_case=1"
    query = f"{query}&{extra}" if query else extra
    return urlunsplit((parts.scheme, parts.netloc, parts.path, query, "diagnosis"))


async def inspect_chart(url: str, screenshot_path: Path) -> dict:
    page_errors: list[str] = []
    console_errors: list[str] = []
    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch(headless=True)
        page = await browser.new_page(viewport={"width": 1440, "height": 900})
        page.on("pageerror", lambda exc: page_errors.append(str(exc)))
        page.on("console", lambda msg: console_errors.append(msg.text) if msg.type == "error" else None)
        await page.goto(with_diagnosis_hash(url), wait_until="domcontentloaded")
        await page.wait_for_selector(".foreman-diagnosis .diag-analysis-band .panel .chart", timeout=30_000)
        await page.wait_for_timeout(2_000)
        result = await page.evaluate(
            """
            () => {
              const panel = Array.from(document.querySelectorAll('.foreman-diagnosis .diag-analysis-band > .panel'))
                .find(p => (p.textContent || '').includes('8种炉况实时直方图'));
              const chart = panel?.querySelector('.chart');
              const instance = chart && window.echarts ? echarts.getInstanceByDom(chart) : null;
              const option = instance ? instance.getOption() : {};
              const series = option.series || [];
              const first = series[0] || {};
              const xData = option.xAxis && option.xAxis[0] ? option.xAxis[0].data || [] : [];
              const barData = first.data || [];
              const bodyText = document.body.innerText || '';
              return {
                body_text: bodyText,
                panel_text: panel?.innerText || '',
                chart_exists: !!chart,
                echarts_instance: !!instance,
                title_text: option.title && option.title[0] ? option.title[0].text : '',
                subtitle_text: option.title && option.title[0] ? option.title[0].subtext : '',
                series_count: series.length,
                series_type: first.type || null,
                x_axis_data: xData,
                bar_data_count: barData.length,
                bar_values: barData.map(x => typeof x === 'object' ? x.value : x),
                bar_colors: barData.map(x => x && x.itemStyle ? x.itemStyle.color : null),
                canvas_count: panel ? panel.querySelectorAll('canvas').length : 0,
                body_overflow_x: document.documentElement.scrollWidth - document.documentElement.clientWidth,
                history_header_count: document.querySelectorAll('.diag-history-12 thead th').length,
                history_scroll_width: document.querySelector('.diag-history-scroll')?.scrollWidth || 0,
                history_client_width: document.querySelector('.diag-history-scroll')?.clientWidth || 0,
                history_has_horizontal_scroll: (() => {
                  const wrap = document.querySelector('.diag-history-scroll');
                  return wrap ? wrap.scrollWidth > wrap.clientWidth + 1 : false;
                })(),
              };
            }
            """
        )
        screenshot_path.parent.mkdir(parents=True, exist_ok=True)
        await page.screenshot(path=str(screenshot_path), full_page=False)
        await browser.close()
    result["page_errors"] = page_errors
    result["console_errors"] = [
        e
        for e in console_errors
        if "Failed to fetch" not in e and 'URL scheme "file"' not in e and "Babel transformer" not in e
    ]
    result["screenshot"] = str(screenshot_path)
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify the diagnosis page renders the 8-condition score histogram.")
    parser.add_argument("--url", default=default_file_url(), help="Base frontend URL or file URL.")
    parser.add_argument("--screenshot", default=str(ROOT / "logs" / "diagnosis_score_histogram.png"))
    args = parser.parse_args()

    result = asyncio.run(inspect_chart(args.url, Path(args.screenshot)))
    failures = []
    if result["page_errors"] or result["console_errors"]:
        failures.append("page_or_console_errors")
    if not result["chart_exists"] or not result["echarts_instance"]:
        failures.append("chart_not_ready")
    if result["series_count"] != 1 or result["series_type"] != "bar":
        failures.append("chart_not_single_bar_series")
    if result["x_axis_data"] != EXPECTED_LABELS:
        failures.append("x_axis_labels_not_8_conditions")
    if result["bar_data_count"] != 8:
        failures.append("bar_count_not_8")
    if any(color not in EXPECTED_COLORS for color in result["bar_colors"]):
        failures.append("bar_color_outside_safety_warning_danger_palette")
    if "绿色=安全" not in result["subtitle_text"] or "正常顺行≥40为安全" not in result["subtitle_text"]:
        failures.append("color_polarity_copy_missing")
    if result["bar_colors"] and result["bar_colors"][0] != "#58dc7a":
        failures.append("normal_bar_not_green_above_40")
    if "8种炉况实时直方图" not in result["panel_text"]:
        failures.append("histogram_panel_title_missing")
    if result["canvas_count"] < 1:
        failures.append("histogram_canvas_missing")
    if result["body_overflow_x"] > 1:
        failures.append("body_horizontal_overflow")
    if "诊断演化趋势" in result["panel_text"] or "近1小时12次" in result["panel_text"]:
        failures.append("old_trend_copy_still_visible")
    if result.get("history_header_count") != EXPECTED_HISTORY_POINTS + 2:
        failures.append("history_table_not_12_points")
    if result.get("history_has_horizontal_scroll"):
        failures.append("history_table_horizontal_scroll")

    payload = {"failed": len(failures), "failures": failures, "result": result}
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
