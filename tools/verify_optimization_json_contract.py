"""Read-only compatibility check for the optimization workbench data contract.

REQ-OPT-20260710-WORKBENCH.  The script opens a browser context, reads one
``init`` payload from the configured WebSocket bridge, and validates only the
fields consumed by ``BFOptimizationWorkbenchV10``.  It does not write to the
bridge, database, model service, or production page.
"""

from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path

from playwright.async_api import async_playwright


DEFAULT_PAGE_URL = "http://10.30.220.12:8093/?ws_port=8768#optimization"
DEFAULT_WS_URL = "ws://10.30.220.12:8768"
REQUIRED_SERIES = ("DP_total", "P_top", "PI", "T_top", "GasUtil", "Q_blast")


async def read_init_payload(page_url: str, ws_url: str, timeout_ms: int) -> dict:
    """Read and summarize one real-time init payload without persisting values."""
    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch(headless=True)
        page = await browser.new_page()
        await page.goto(page_url, wait_until="domcontentloaded", timeout=timeout_ms)
        result = await page.evaluate(
            """
            async ({wsUrl, timeoutMs, requiredSeries}) => new Promise(resolve => {
              let settled = false;
              const finish = value => {
                if (settled) return;
                settled = true;
                clearTimeout(timer);
                try { socket.close(); } catch (_) {}
                resolve(value);
              };
              const socket = new WebSocket(wsUrl);
              const timer = setTimeout(() => finish({ok:false, error:'WebSocket init timeout'}), timeoutMs);
              socket.addEventListener('error', () => finish({ok:false, error:'WebSocket connection error'}));
              socket.addEventListener('message', event => {
                let payload;
                try { payload = JSON.parse(event.data); } catch (_) { return; }
                if (payload.type !== 'init') return;
                const history = payload.history || {};
                const timestamps = Array.isArray(history.timestamps) ? history.timestamps : [];
                const series = Object.fromEntries(requiredSeries.map(id => {
                  const values = Array.isArray(history[id]) ? history[id] : [];
                  const tailWindow = Math.min(60, timestamps.length);
                  return [id, {
                    present: Array.isArray(history[id]),
                    length: values.length,
                    finite_values: values.filter(value => Number.isFinite(Number(value))).length,
                    leading_samples: Math.max(0, values.length - timestamps.length),
                    has_shared_history: values.length >= timestamps.length,
                    tail_window_ready: values.length >= tailWindow,
                  }];
                }));
                const diagnosis = payload.diagnosis || {};
                const recommendation = diagnosis.recommendation || null;
                const recommendationStatus = diagnosis.recommendation_status || {};
                finish({
                  ok: true,
                  type: payload.type,
                  timestamp_count: timestamps.length,
                  latest_data_ts: payload.data_quality?.latest_data_ts || timestamps.at(-1) || null,
                  diagnosis_present: !!payload.diagnosis,
                  diagnosis_label: diagnosis.main_label || diagnosis.label || diagnosis.diagnosis?.main_label || null,
                  recommendation_present: !!recommendation,
                  recommendation_status: recommendationStatus.state || null,
                  recommendation_engine: recommendation?.engine_meta?.name || null,
                  recommendation_version: recommendation?.engine_meta?.version || null,
                  recommendation_goal: recommendation?.goal || null,
                  recommendation_actions: [
                    ...(recommendation?.immediate_actions || []),
                    ...(recommendation?.followup_actions || []),
                    ...(recommendation?.forbidden_actions || []),
                  ].length,
                  data_quality_status: payload.data_quality?.status || null,
                  series,
                });
              });
            })
            """,
            {"wsUrl": ws_url, "timeoutMs": timeout_ms, "requiredSeries": list(REQUIRED_SERIES)},
        )
        await browser.close()
        return result


def validate(summary: dict) -> list[str]:
    """Return contract failures for fields required by the optimization page."""
    failures: list[str] = []
    if not summary.get("ok"):
        return [summary.get("error", "unknown WebSocket error")]
    if summary.get("type") != "init":
        failures.append("missing_init_payload")
    if not summary.get("diagnosis_present") or not summary.get("diagnosis_label"):
        failures.append("diagnosis_missing")
    if not summary.get("recommendation_present"):
        failures.append("recommendation_missing")
    if summary.get("recommendation_status") != "ready":
        failures.append("recommendation_not_ready")
    if summary.get("recommendation_engine") != "blast_furnace_recommendation_engine":
        failures.append("recommendation_engine_mismatch")
    if not summary.get("recommendation_actions"):
        failures.append("recommendation_actions_missing")
    if not summary.get("timestamp_count"):
        failures.append("history_timestamps_missing")
    for series_id, info in (summary.get("series") or {}).items():
        if not info.get("present"):
            failures.append(f"{series_id}_missing")
        elif not info.get("tail_window_ready"):
            failures.append(f"{series_id}_tail_window_missing")
    return failures


def main() -> int:
    parser = argparse.ArgumentParser(description="Read-only optimization JSON contract verification.")
    parser.add_argument("--page-url", default=DEFAULT_PAGE_URL)
    parser.add_argument("--ws-url", default=DEFAULT_WS_URL)
    parser.add_argument("--timeout-ms", type=int, default=20_000)
    parser.add_argument("--out", default="logs/optimization_json_contract_remote_8768.json")
    args = parser.parse_args()

    summary = asyncio.run(read_init_payload(args.page_url, args.ws_url, args.timeout_ms))
    failures = validate(summary)
    result = {"ok": not failures, "failures": failures, "summary": summary}
    target = Path(args.out)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
