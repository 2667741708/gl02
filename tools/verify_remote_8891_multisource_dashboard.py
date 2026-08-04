#!/usr/bin/env python3
"""Chromium/CDP acceptance for the standalone 8891 multi-source dashboard.

This verifier is intentionally read-only. It checks the catalog and source
controls, submits one real pSpace query through the page, then exercises the
required CSS viewports and records screenshots plus a JSON report.
"""

from __future__ import annotations

import argparse
import base64
import json
import time
import urllib.parse
from pathlib import Path
from typing import Any

import requests
import websocket


VIEWPORTS = (
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


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--cdp", default="http://127.0.0.1:9225")
    parser.add_argument(
        "--url",
        default="http://127.0.0.1:8891/heat?multisource_acceptance=1",
    )
    parser.add_argument("--out-dir", required=True)
    parser.add_argument("--ready-timeout", type=float, default=25.0)
    return parser.parse_args()


class CDP:
    def __init__(self, websocket_url: str) -> None:
        self.ws = websocket.create_connection(
            websocket_url,
            timeout=2,
            origin="http://127.0.0.1",
        )
        self.seq = 0
        self.events: list[dict[str, Any]] = []

    def close(self) -> None:
        self.ws.close()

    def send(
        self, method: str, params: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        self.seq += 1
        message_id = self.seq
        self.ws.send(
            json.dumps(
                {"id": message_id, "method": method, "params": params or {}},
                separators=(",", ":"),
            )
        )
        deadline = time.time() + 3
        while time.time() < deadline:
            payload = json.loads(self.ws.recv())
            if payload.get("id") == message_id:
                if "error" in payload:
                    raise RuntimeError(f"{method}: {payload['error']}")
                return payload.get("result", {})
            self.events.append(payload)
        raise TimeoutError(method)

    def evaluate(self, expression: str) -> Any:
        result = self.send(
            "Runtime.evaluate",
            {
                "expression": expression,
                "returnByValue": True,
                "awaitPromise": True,
            },
        )
        remote = result.get("result", {})
        if remote.get("subtype") == "error":
            raise RuntimeError(remote.get("description", expression))
        return remote.get("value")

    def screenshot(self, target: Path) -> None:
        result = self.send("Page.captureScreenshot", {"format": "png"})
        target.write_bytes(base64.b64decode(result["data"]))


def wait_value(cdp: CDP, expression: str, timeout: float) -> Any:
    deadline = time.time() + timeout
    last: Any = None
    while time.time() < deadline:
        try:
            last = cdp.evaluate(expression)
            if last:
                return last
        except (TimeoutError, RuntimeError, websocket.WebSocketTimeoutException):
            pass
        time.sleep(0.2)
    raise TimeoutError(f"Timed out waiting for {expression}; last={last!r}")


def main() -> int:
    args = parse_args()
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    target = requests.put(
        f"{args.cdp}/json/new?{urllib.parse.quote(args.url, safe='')}",
        timeout=2,
    ).json()
    cdp = CDP(target["webSocketDebuggerUrl"])
    report: dict[str, Any] = {
        "schema": "heat.multisource.8891.chromium-viewport-acceptance.v1",
        "url": args.url,
        "started_at_epoch": time.time(),
        "viewports": [],
    }
    try:
        cdp.send("Runtime.enable")
        cdp.send("Log.enable")
        cdp.send("Page.enable")
        wait_value(
            cdp,
            "document.querySelector('#dataCatalogTag')?.textContent.includes('31')",
            args.ready_timeout,
        )
        report["catalog"] = cdp.evaluate(
            """
            (() => ({
              tag: document.querySelector('#dataCatalogTag')?.textContent || '',
              sourceCards: document.querySelectorAll('.source-card').length,
              datasetOptions: document.querySelectorAll('#dataDataset option').length,
              controls: [
                'dataDataset','dataStart','dataEnd','dataMeltno','dataSearch',
                'dataVariables','dataLimit','dataQueryBtn','dataCsv','dataXlsx'
              ].every(id => Boolean(document.getElementById(id))),
              sources: [...document.querySelectorAll('.source-card')]
                .map(card => card.dataset.source)
            }))()
            """
        )

        cdp.evaluate(
            """
            (() => {
              const select = document.querySelector('#dataDataset');
              select.value = 'pspace.realtime';
              select.dispatchEvent(new Event('change', {bubbles:true}));
              document.querySelector('#dataVariables').value = 'P_top,DP_total';
              document.querySelector('#dataLimit').value = '50';
              document.querySelector('#dataQueryForm')
                .dispatchEvent(new Event('submit', {bubbles:true,cancelable:true}));
              return true;
            })()
            """
        )
        wait_value(
            cdp,
            "document.querySelectorAll('#dataResultWrap tbody tr').length > 0",
            15,
        )
        report["real_ui_query"] = cdp.evaluate(
            """
            (() => ({
              rows: document.querySelectorAll('#dataResultWrap tbody tr').length,
              columns: document.querySelectorAll('#dataResultWrap thead th').length,
              meta: document.querySelector('#dataResultMeta')?.innerText || '',
              csvReady: document.querySelector('#dataCsv')?.getAttribute('href')
                ?.includes('format=csv') || false,
              xlsxReady: document.querySelector('#dataXlsx')?.getAttribute('href')
                ?.includes('format=xlsx') || false
            }))()
            """
        )

        for width, height in VIEWPORTS:
            cdp.send(
                "Emulation.setDeviceMetricsOverride",
                {
                    "width": width,
                    "height": height,
                    "deviceScaleFactor": 1,
                    "mobile": False,
                },
            )
            time.sleep(0.15)
            check = cdp.evaluate(
                """
                (() => {
                  const root = document.documentElement;
                  const form = document.querySelector('#dataQueryForm');
                  const button = document.querySelector('#dataQueryBtn');
                  const result = document.querySelector('#dataResultWrap');
                  const rect = button?.getBoundingClientRect();
                  return {
                    width: window.innerWidth,
                    height: window.innerHeight,
                    scrollWidth: root.scrollWidth,
                    noPageHorizontalOverflow:
                      root.scrollWidth <= root.clientWidth + 1,
                    formVisible: Boolean(form && form.offsetWidth && form.offsetHeight),
                    queryButtonReachable: Boolean(
                      rect && rect.width > 0 && rect.height > 0
                    ),
                    resultScrollable:
                      ['auto','scroll'].includes(getComputedStyle(result).overflowY),
                    sourceCards: document.querySelectorAll('.source-card').length,
                    rows: document.querySelectorAll(
                      '#dataResultWrap tbody tr'
                    ).length,
                    fontFamily: getComputedStyle(
                      document.querySelector('.multi-source')
                    ).fontFamily
                  };
                })()
                """
            )
            check["passed"] = bool(
                check["noPageHorizontalOverflow"]
                and check["formVisible"]
                and check["queryButtonReachable"]
                and check["resultScrollable"]
                and check["sourceCards"] == 4
                and check["rows"] > 0
            )
            report["viewports"].append(check)
            cdp.screenshot(out_dir / f"8891_multisource_{width}x{height}.png")

        error_events = []
        for event in cdp.events:
            method = event.get("method")
            params = event.get("params", {})
            if method == "Runtime.exceptionThrown":
                error_events.append(
                    {
                        "method": method,
                        "text": params.get("exceptionDetails", {}).get("text", ""),
                    }
                )
            if (
                method == "Log.entryAdded"
                and params.get("entry", {}).get("level") == "error"
            ):
                error_events.append(
                    {
                        "method": method,
                        "text": params.get("entry", {}).get("text", ""),
                    }
                )
        report["browser_errors"] = error_events
        report["checks"] = {
            "catalog_31": report["catalog"]["datasetOptions"] == 31,
            "four_source_cards": report["catalog"]["sourceCards"] == 4,
            "all_query_controls": report["catalog"]["controls"] is True,
            "real_pspace_ui_query": report["real_ui_query"]["rows"] > 0,
            "csv_and_xlsx_links": (
                report["real_ui_query"]["csvReady"]
                and report["real_ui_query"]["xlsxReady"]
            ),
            "all_required_viewports": len(report["viewports"]) == len(VIEWPORTS),
            "all_viewports_passed": all(
                item["passed"] for item in report["viewports"]
            ),
            "no_browser_errors": not error_events,
        }
        report["passed"] = all(report["checks"].values())
    finally:
        report["finished_at_epoch"] = time.time()
        (out_dir / "8891_multisource_acceptance.json").write_text(
            json.dumps(report, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        cdp.close()
    print(
        json.dumps(
            {"passed": report.get("passed"), "checks": report.get("checks")},
            ensure_ascii=False,
        )
    )
    return 0 if report.get("passed") else 1


if __name__ == "__main__":
    raise SystemExit(main())
