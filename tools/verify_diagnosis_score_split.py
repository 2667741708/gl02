from __future__ import annotations

import argparse
import asyncio
import contextlib
import functools
import http.server
import json
import socketserver
import threading
from pathlib import Path

from playwright.async_api import async_playwright


ROOT = Path(__file__).resolve().parents[1]
FRONTEND_DIR = ROOT / "高炉前端数据"


class QuietHandler(http.server.SimpleHTTPRequestHandler):
    def log_message(self, format: str, *args: object) -> None:
        return


@contextlib.contextmanager
def static_server() -> str:
    handler = functools.partial(QuietHandler, directory=str(FRONTEND_DIR))
    with socketserver.TCPServer(("127.0.0.1", 0), handler) as server:
        port = server.server_address[1]
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            yield f"http://127.0.0.1:{port}/frontend_dashboard_v3.server.html?ws_port=8767#diagnosis"
        finally:
            server.shutdown()
            thread.join(timeout=5)


async def check_viewport(url: str, width: int, height: int, output_dir: Path) -> dict[str, object]:
    output_dir.mkdir(parents=True, exist_ok=True)
    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch(headless=True)
        page = await browser.new_page(viewport={"width": width, "height": height})
        page_errors: list[str] = []
        console_errors: list[str] = []
        page.on("pageerror", lambda exc: page_errors.append(str(exc)))
        page.on("console", lambda msg: console_errors.append(msg.text) if msg.type == "error" else None)
        await page.goto(url, wait_until="domcontentloaded", timeout=60_000)
        await page.wait_for_selector(".bf-diag-split-list", timeout=45_000)
        await page.wait_for_timeout(1000)
        screenshot = output_dir / f"diagnosis_score_split_{width}x{height}.png"
        await page.screenshot(path=str(screenshot), full_page=False)
        metrics = await page.evaluate(
            """
            () => {
              const root = document.querySelector('.bf-diag-split-list');
              const groupTitles = [...document.querySelectorAll('.bf-diag-group-title')].map(x => x.textContent.trim());
              const cards = [...document.querySelectorAll('.bf-diag-split-card')];
              const furnaceImage = document.querySelector('.diag-conclusion img.diag-condition-furnace');
              const diagnosisScreen = document.querySelector('.screen.diagnosis-grid')?.getBoundingClientRect();
              const rankPanel = document.querySelector('.diagnosis-grid > .panel:first-child')?.getBoundingClientRect();
              const lastCard = cards.length ? cards[cards.length - 1].getBoundingClientRect() : null;
              const scoreRowsInline = cards.every(card => {
                const score = card.querySelector('.bf-diag-rank-score')?.getBoundingClientRect();
                const value = card.querySelector('.bf-diag-score-number')?.getBoundingClientRect();
                return score && value && Math.abs(score.top - value.top) < 1 && Math.abs(score.height - value.height) < 1;
              });
              const whiteText = cards.every(card => {
                const nodes = [
                  card.querySelector('.diag-rank-name'),
                  card.querySelector('.diag-rank-value'),
                  card.querySelector('.diag-rank-den'),
                  card.querySelector('.bf-diag-risk-chip')
                ].filter(Boolean);
                return nodes.every(node => getComputedStyle(node).color === 'rgb(255, 255, 255)');
              });
              return {
                hash: location.hash,
                viewportWidth: innerWidth,
                documentWidth: document.documentElement.scrollWidth,
                groupTitles,
                cardCount: cards.length,
                normalGroupCards: document.querySelectorAll('.bf-diag-normal-group .bf-diag-split-card').length,
                abnormalGroupCards: document.querySelectorAll('.bf-diag-abnormal-grid .bf-diag-split-card').length,
                whiteText,
                furnaceImage: furnaceImage ? {src: furnaceImage.getAttribute('src'), condition: furnaceImage.dataset.condition, width: furnaceImage.naturalWidth, height: furnaceImage.naturalHeight} : null,
                legacyFurnaceSvgCount: document.querySelectorAll('.diag-conclusion svg').length,
                scoreRowsInline,
                diagnosisHeight: diagnosisScreen?.height || 0,
                rankPanelContainsScores: !!(rankPanel && lastCard && lastCard.bottom <= rankPanel.bottom + 1),
                rankNotePresent: (root?.innerText || '').includes('正常顺行分数越高越好'),
                hasRawScoresText: (root?.innerText || '').includes('raw_scores')
              };
            }
            """
        )
        await browser.close()
    failures: list[str] = []
    if metrics["hash"] != "#diagnosis":
        failures.append("route_not_diagnosis")
    if metrics["documentWidth"] > width + 1:
        failures.append("horizontal_overflow")
    if "正常顺行炉况" not in metrics["groupTitles"]:
        failures.append("missing_normal_group_title")
    if "异常炉况" not in metrics["groupTitles"]:
        failures.append("missing_abnormal_group_title")
    if metrics["cardCount"] != 8:
        failures.append("card_count_not_8")
    if metrics["normalGroupCards"] != 1:
        failures.append("normal_group_not_1")
    if metrics["abnormalGroupCards"] != 7:
        failures.append("abnormal_group_not_7")
    if not metrics["whiteText"]:
        failures.append("text_not_all_white")
    if not metrics["furnaceImage"] or metrics["furnaceImage"]["width"] < 100:
        failures.append("condition_furnace_image_missing")
    if metrics["legacyFurnaceSvgCount"]:
        failures.append("legacy_furnace_svg_active")
    if not metrics["scoreRowsInline"]:
        failures.append("score_rows_not_inline")
    if not metrics["rankPanelContainsScores"]:
        failures.append("rank_scores_escape_panel")
    if width >= 1280 and metrics["diagnosisHeight"] > 1200:
        failures.append("desktop_diagnosis_height_expanded")
    if metrics["rankNotePresent"]:
        failures.append("rank_note_still_visible")
    if metrics["hasRawScoresText"]:
        failures.append("raw_scores_visible")
    return {
        "viewport": f"{width}x{height}",
        "ok": not failures,
        "failures": failures,
        "screenshot": str(screenshot),
        "metrics": metrics,
        "page_errors": page_errors,
        "console_errors": [x for x in console_errors if "WebSocket connection" not in x and "Failed to fetch" not in x],
    }


async def main_async(args: argparse.Namespace) -> int:
    output_dir = Path(args.output_dir)
    server_context = contextlib.nullcontext(args.url) if args.url else static_server()
    with server_context as url:
        results = []
        for size in args.viewport:
            width, height = map(int, size.lower().split("x", 1))
            results.append(await check_viewport(url, width, height, output_dir))
    manifest = output_dir / "diagnosis_score_split_manifest.json"
    manifest.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    failed = [item for item in results if not item["ok"] or item["page_errors"] or item["console_errors"]]
    print(json.dumps({"count": len(results), "failed": len(failed), "manifest": str(manifest)}, ensure_ascii=False, indent=2))
    return 1 if failed else 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify the diagnosis score split panel.")
    parser.add_argument("--url", default="", help="Optional running diagnosis URL; otherwise use a temporary static server.")
    parser.add_argument("--viewport", action="append", default=["1366x768", "390x844"])
    parser.add_argument("--output-dir", default="logs/diagnosis_score_split_20260714")
    return asyncio.run(main_async(parser.parse_args()))


if __name__ == "__main__":
    raise SystemExit(main())
