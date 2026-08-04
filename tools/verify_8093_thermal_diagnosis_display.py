from __future__ import annotations

import argparse
import asyncio
import json
import time
from pathlib import Path

from playwright.async_api import async_playwright


ROOT = Path(__file__).resolve().parents[1]
V3_SOURCE = ROOT / "高炉前端数据" / "frontend_dashboard_v3.server.html"
FRONT2_SOURCE = ROOT / "高炉前端数据" / "front2" / "frontend_dashboard_front2.server.html"
AGENTS = ROOT / "AGENTS.md"


def static_check() -> dict:
    expected = "REQ-8093-THERMAL-DIAGNOSIS-DISPLAY-20260716"
    checks = {}
    for source in (V3_SOURCE, FRONT2_SOURCE):
        text = source.read_text(encoding="utf-8")
        checks[str(source.relative_to(ROOT))] = {
            "marker": expected in text,
            "cold_display": "cold: '热制度下行'" in text or "cold:'热制度下行'" in text,
            "hot_display": "hot: '热制度上行'" in text or "hot:'热制度上行'" in text,
            "server_text_normalizer": "normalizeThermalDiagnosisText" in text,
            "key_contract_preserved": "keep cold/hot keys and scores unchanged" in text,
        }
    agent_text = AGENTS.read_text(encoding="utf-8")
    checks["AGENTS.md"] = {
        "constraint": "炉况展示名称规范" in agent_text
        and "cold` 展示为“热制度下行”" in agent_text
        and "hot` 展示为“热制度上行”" in agent_text,
    }
    return {"passed": all(all(entry.values()) for entry in checks.values()), "checks": checks}


async def browser_check(url: str, width: int, height: int, browser_name: str, routes: tuple[str, ...]) -> dict:
    payload = {
        "type": "init",
        "timestamp": "2026-07-16T08:00:00.000Z",
        "history": {
            "timestamps": [
                "2026-07-16T07:55:00.000Z",
                "2026-07-16T07:56:00.000Z",
                "2026-07-16T07:57:00.000Z",
                "2026-07-16T07:58:00.000Z",
                "2026-07-16T07:59:00.000Z",
                "2026-07-16T08:00:00.000Z",
            ],
            "P_top": [250, 251, 251, 252, 253, 252],
            "T_top": [185, 188, 190, 193, 196, 199],
            "T_blast": [1180, 1181, 1182, 1182, 1183, 1184],
            "DP_total": [195, 197, 199, 201, 202, 204],
            "PI": [1.02, 1.01, 1.0, 0.99, 0.98, 0.97],
        },
        "diagnosis": {
            "main_label": "hot",
            "secondary_label": "cold",
            "main_score": 76,
            "raw_scores": {"normal": 20, "lowline": 12, "edge": 28, "center": 18, "channel": 16, "cold": 51, "hot": 76, "column": 14},
            "evidence": ["炉热迹象需要复查", "炉凉风险尚未消除"],
            "recommendation": {"goal": "控制炉热并避免炉凉反复", "immediate_actions": [{"text": "炉热时先减喷煤"}]},
        },
        "data_quality": {},
    }
    init_script = f"""
    (() => {{
      const payload = {json.dumps(payload, ensure_ascii=False)};
      class MockWebSocket {{
        constructor() {{
          this.readyState = 0;
          setTimeout(() => {{ this.readyState = 1; this.onopen && this.onopen(); }}, 100);
          setTimeout(() => {{ this.onmessage && this.onmessage({{data: JSON.stringify(payload)}}); }}, 1_000);
        }}
        send() {{}}
        close() {{ this.readyState = 3; this.onclose && this.onclose(); }}
      }}
      MockWebSocket.CONNECTING = 0; MockWebSocket.OPEN = 1; MockWebSocket.CLOSING = 2; MockWebSocket.CLOSED = 3;
      window.WebSocket = MockWebSocket;
    }})();
    """
    cache_bust = int(time.time() * 1000)
    results: list[dict] = []
    async with async_playwright() as playwright:
        browser = await (
            playwright.chromium.launch(headless=True, channel="msedge")
            if browser_name == "msedge"
            else getattr(playwright, browser_name).launch(headless=True)
        )
        page = await browser.new_page(viewport={"width": width, "height": height})
        for route in routes:
            await page.goto(f"{url.rstrip('/')}?thermal_display_test={cache_bust}-{route}#{route}", wait_until="domcontentloaded", timeout=60_000)
            await page.wait_for_timeout(8_500)
            visible_text = await page.locator("main").inner_text()
            results.append(
                {
                    "route": route,
                    "has_up": "热制度上行" in visible_text,
                    "has_down": "热制度下行" in visible_text,
                    "has_legacy": "炉热" in visible_text or "炉凉" in visible_text,
                    "horizontal_overflow": await page.evaluate("document.documentElement.scrollWidth > innerWidth + 1"),
                }
            )
        await browser.close()
    failures = [item["route"] for item in results if item["has_legacy"] or item["horizontal_overflow"]]
    diagnosis = next((item for item in results if item["route"] == "diagnosis"), None)
    if diagnosis is not None and not (diagnosis["has_up"] and diagnosis["has_down"]):
        failures.append("diagnosis_mapping")
    return {"passed": not failures, "failures": failures, "routes": results}


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify cold/hot use thermal-discipline display names without changing diagnostic keys.")
    parser.add_argument("--url", default="http://127.0.0.1:8093/")
    parser.add_argument("--browser", choices=("chromium", "firefox", "webkit", "msedge"), default="chromium")
    parser.add_argument("--routes", default="overview,diagnosis,optimization,trend,qa")
    parser.add_argument("--width", type=int, default=1366)
    parser.add_argument("--height", type=int, default=768)
    parser.add_argument("--static-only", action="store_true")
    parser.add_argument("--out-dir", default=str(ROOT / "logs" / "8093_thermal_diagnosis_display_qa"))
    args = parser.parse_args()
    output = Path(args.out_dir).resolve()
    output.mkdir(parents=True, exist_ok=True)
    report = {"static": static_check()}
    if not args.static_only:
        routes = tuple(route.strip() for route in args.routes.split(",") if route.strip())
        valid_routes = {"overview", "diagnosis", "optimization", "trend", "qa"}
        if not routes or any(route not in valid_routes for route in routes):
            parser.error("--routes must be a comma-separated subset of overview,diagnosis,optimization,trend,qa")
        report["browser"] = asyncio.run(browser_check(args.url, args.width, args.height, args.browser, routes))
    report["passed"] = report["static"]["passed"] and report.get("browser", {}).get("passed", True)
    path = output / f"manifest_{args.browser}_{args.width}x{args.height}.json"
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"passed": report["passed"], "manifest": str(path)}, ensure_ascii=False))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
