"""Cross-browser fixture verification for REQ-TREND-19-LANE-MERGE-20260807."""

from __future__ import annotations

import argparse
import asyncio
import contextlib
import http.server
import json
import math
import threading
import urllib.parse
from datetime import datetime, timedelta, timezone
from pathlib import Path

import websockets


ROOT = Path(__file__).resolve().parents[1]
PAGE = ROOT / "高炉前端数据" / "front2" / "frontend_dashboard_front2.server.html"
SITE_ROOT = ROOT / "高炉前端数据"
EXPECTED = [
    "P_top", "P_top_gas_A", "P_top_gas_B", "P_top_gas_C", "P_top_gas_D",
    "T_top", "T_top_A", "T_top_B", "T_top_C", "T_top_D", "Q_blast",
    "P_blast_cold", "P_blast", "T_blast", "PI", "DP_total", "DP_upper",
    "DP_lower", "GasUtil",
]
CHROMIUM_VIEWPORTS = [(1280, 720), (1366, 768), (1440, 900), (1546, 864), (1920, 1080), (1024, 768), (768, 1024), (390, 844), (375, 667)]
REPRESENTATIVE_VIEWPORTS = [(1920, 1080), (1366, 768), (768, 1024), (390, 844)]


def fixture_script() -> str:
    targets = json.dumps(EXPECTED, ensure_ascii=False)
    return f"""
(() => {{
  const targets = {targets};
  const now = Date.now();
  const timestamps = Array.from({{length: 480}}, (_, i) => new Date(now - (479 - i) * 60000).toISOString());
  const history = {{timestamps}};
  targets.forEach((id, index) => {{
    const base = 20 + index * 9;
    history[id] = timestamps.map((_, i) => base + Math.sin(i / (12 + index % 5)) * (1 + index * .08) + i * .002);
  }});
  history.GasUtil = timestamps.map((_, i) => .46 + Math.sin(i / 33) * .012);
  window.__sentWsMessages = [];
  window.__fixtureSockets = [];
  window.__fixtureInitMessage = {{type:'init', history, timestamp:timestamps.at(-1), diagnosis:{{label:'normal',score:82}}}};
  window.__deliverFixtureInit = socket => {{
    if (!socket || socket.__fixtureInitialized || typeof socket.onmessage !== 'function') return false;
    socket.__fixtureInitialized = true;
    socket.onopen?.();
    socket.onmessage({{data: JSON.stringify(window.__fixtureInitMessage)}});
    return true;
  }};
  class FixtureWebSocket {{
    static OPEN = 1;
    static CONNECTING = 0;
    constructor() {{
      this.readyState = 1;
      window.__fixtureSockets.push(this);
      const deliverInit = () => {{
        if (!window.__deliverFixtureInit(this)) {{
          setTimeout(deliverInit, 20);
        }}
      }};
      setTimeout(deliverInit, 50);
    }}
    send(raw) {{
      const request = JSON.parse(raw);
      window.__sentWsMessages.push(request);
      if (request.type !== 'chronos_predict_recommended_batch') return;
      const future = Array.from({{length: 121}}, (_, i) => new Date(now + i * 60000).toISOString());
      const predictions = request.target_ids.map((id, index) => ({{
        target_id: id,
        future_timestamps: future,
        p50: future.map((_, i) => (id === 'GasUtil' ? .46 : 20 + index * 9) + Math.sin(i / 14) * (1 + index * .08))
      }}));
      setTimeout(() => this.onmessage?.({{data: JSON.stringify({{type:'chronos_prediction_batch', status:'success', forecast:{{predictions}}}})}}), 20);
    }}
    close() {{ this.readyState = 3; this.onclose?.(); }}
  }}
  window.WebSocket = FixtureWebSocket;
}})();
"""


class FixtureWebSocketService:
    def __init__(self) -> None:
        self.requests: list[dict] = []

    async def handler(self, websocket) -> None:
        try:
            await self._handler(websocket)
        except websockets.exceptions.ConnectionClosed:
            return

    @staticmethod
    def history_payload() -> tuple[dict, datetime]:
        now = datetime.now(timezone.utc).replace(second=0, microsecond=0)
        timestamps = [(now - timedelta(minutes=479 - index)).isoformat() for index in range(480)]
        history: dict[str, list | str] = {"timestamps": timestamps}
        for index, target in enumerate(EXPECTED):
            base = 20 + index * 9
            history[target] = [
                base + math.sin(point / (12 + index % 5)) * (1 + index * .08) + point * .002
                for point in range(480)
            ]
        history["GasUtil"] = [.46 + math.sin(point / 33) * .012 for point in range(480)]
        return history, now

    async def _handler(self, websocket) -> None:
        history, now = self.history_payload()
        await websocket.send(
            json.dumps(
                {
                    "type": "init",
                    "history": history,
                    "timestamp": now.isoformat(),
                    "diagnosis": {"label": "normal", "score": 82},
                },
                ensure_ascii=False,
            )
        )
        async for raw in websocket:
            request = json.loads(raw)
            if request.get("type") != "chronos_predict_recommended_batch":
                continue
            self.requests.append(request)
            future = [(now + timedelta(minutes=index)).isoformat() for index in range(121)]
            predictions = []
            for index, target in enumerate(request.get("target_ids") or []):
                base = .46 if target == "GasUtil" else 20 + index * 9
                predictions.append(
                    {
                        "target_id": target,
                        "future_timestamps": future,
                        "p50": [base + math.sin(point / 14) * (1 + index * .08) for point in range(121)],
                    }
                )
            await websocket.send(
                json.dumps(
                    {
                        "type": "chronos_prediction_batch",
                        "status": "success",
                        "forecast": {"predictions": predictions},
                    },
                    ensure_ascii=False,
                )
            )


class FixtureRequestHandler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(SITE_ROOT), **kwargs)

    def log_message(self, format: str, *args) -> None:
        return

    def do_GET(self) -> None:
        path = urllib.parse.urlsplit(self.path).path
        if path == "/frontend_dashboard_front2.server.html":
            payload = PAGE.read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)
            return
        if path.startswith("/api/"):
            payload = json.dumps(
                {"ok": True, "items": [], "conversations": [], "summaries": [], "state": "idle"},
                ensure_ascii=False,
            ).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)
            return
        super().do_GET()


@contextlib.contextmanager
def fixture_server():
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), FixtureRequestHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}/frontend_dashboard_front2.server.html"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


async def check_page(
    browser_type,
    engine: str,
    viewport: tuple[int, int],
    screenshot_dir: Path | None,
    url: str,
    ws_port: int,
    ws_fixture: FixtureWebSocketService,
) -> dict:
    browser = await browser_type.launch(headless=True)
    page = await browser.new_page(viewport={"width": viewport[0], "height": viewport[1]})
    page_errors: list[str] = []
    console_errors: list[str] = []
    page.on("pageerror", lambda exc: page_errors.append(str(exc)))
    page.on("console", lambda message: console_errors.append(message.text) if message.type == "error" else None)
    separator = "&" if "?" in url else "?"
    await page.goto(f"{url}{separator}ws_port={ws_port}#trend", wait_until="domcontentloaded", timeout=60_000)
    await page.wait_for_selector(".trend-chart-stack.trend-lane-single .trend-lane-chart", timeout=60_000)
    request_start = len(ws_fixture.requests)
    await page.get_by_role("button", name="生成全部未来曲线").click()
    for _ in range(100):
        if len(ws_fixture.requests) > request_start:
            break
        await asyncio.sleep(.05)
    if len(ws_fixture.requests) <= request_start:
        raise AssertionError(f"no Chronos request received for {engine} {viewport}")
    request = ws_fixture.requests[-1]
    await page.wait_for_function(
        """() => {
          const element = document.querySelector('.trend-lane-single .trend-lane-chart');
          const chart = element && window.echarts.getInstanceByDom(element);
          return !!chart && chart.getOption().series.filter(item => String(item.id || '').endsWith('-forecast')).length === 19;
        }""",
        timeout=30_000,
    )
    result = await page.evaluate("""() => {
      const chartElement = document.querySelector('.trend-lane-single .trend-lane-chart');
      const chart = window.echarts.getInstanceByDom(chartElement);
      const option = chart.getOption();
      const panels = document.querySelectorAll('.trend-chart-stack.trend-lane-single > .panel');
      const names = option.legend?.[0]?.data || [];
      const historical = (option.series || []).filter(item => String(item.id || '').endsWith('-history'));
      const predicted = (option.series || []).filter(item => String(item.id || '').endsWith('-forecast'));
      const overflow = document.documentElement.scrollWidth - document.documentElement.clientWidth;
      const firstName = names[0];
      chart.dispatchAction({type:'legendToggleSelect', name:firstName});
      const selected = chart.getOption().legend?.[0]?.selected || {};
      return {
        panelCount: panels.length,
        legendCount: names.length,
        historicalCount: historical.length,
        forecastCount: predicted.length,
        rawCoordinatePresent: historical.some(item => (item.data || []).some(point => Number.isFinite(Number(point?.[2])))),
        forecastDashed: predicted.every(item => item.lineStyle?.type === 'dashed'),
        legendToggleWorks: selected[firstName] === false,
        overflow,
        rightPanelCount: document.querySelectorAll('.trend-analysis-stack > .panel').length
      };
    }""")
    if screenshot_dir and engine == "chromium" and viewport == (1366, 768):
        screenshot_dir.mkdir(parents=True, exist_ok=True)
        await page.screenshot(path=str(screenshot_dir / "front2_trend_19_lane_1366x768.png"), full_page=False)
    await browser.close()
    result["targetIds"] = request.get("target_ids") or []
    result.update(engine=engine, viewport=f"{viewport[0]}x{viewport[1]}", page_errors=page_errors, console_errors=console_errors)
    assert not page_errors and not console_errors, result
    assert result["panelCount"] == 1 and result["rightPanelCount"] == 3, result
    assert result["targetIds"] == EXPECTED, result
    assert result["legendCount"] == 19 and result["historicalCount"] == 19 and result["forecastCount"] == 19, result
    assert result["rawCoordinatePresent"] and result["forecastDashed"] and result["legendToggleWorks"], result
    assert result["overflow"] <= 1, result
    return result


async def run(output: Path, screenshot_dir: Path | None, url: str) -> list[dict]:
    try:
        from playwright.async_api import async_playwright
    except ImportError as exc:
        raise AssertionError("playwright is required") from exc
    results: list[dict] = []
    ws_fixture = FixtureWebSocketService()
    async with websockets.serve(ws_fixture.handler, "127.0.0.1", 0) as ws_server:
        ws_port = ws_server.sockets[0].getsockname()[1]
        async with async_playwright() as playwright:
            for viewport in CHROMIUM_VIEWPORTS:
                results.append(await check_page(playwright.chromium, "chromium", viewport, screenshot_dir, url, ws_port, ws_fixture))
            for engine, browser_type in (("firefox", playwright.firefox), ("webkit", playwright.webkit)):
                for viewport in REPRESENTATIVE_VIEWPORTS:
                    results.append(await check_page(browser_type, engine, viewport, screenshot_dir, url, ws_port, ws_fixture))
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps({"checks": len(results), "results": results}, ensure_ascii=False, indent=2), encoding="utf-8")
    return results


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", default=str(ROOT / "logs" / "acceptance" / "front2_trend_19_lane_20260807.json"))
    parser.add_argument("--screenshots", default=str(ROOT / "logs" / "acceptance" / "front2_trend_19_lane_20260807"))
    parser.add_argument("--url", help="Optional deployed page URL; defaults to an isolated local fixture server.")
    args = parser.parse_args()
    if args.url:
        results = asyncio.run(run(Path(args.output), Path(args.screenshots), args.url))
    else:
        with fixture_server() as url:
            results = asyncio.run(run(Path(args.output), Path(args.screenshots), url))
    print(json.dumps({"checks": len(results), "status": "PASS"}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
