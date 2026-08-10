#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Idempotently patch current 8093/8094 server/page surfaces for V20 Si UI."""

from __future__ import annotations

import argparse
from pathlib import Path


MARKER = "REQ-SI-V20-8093-8094-SHADOW-WORKBENCH-20260808"
ASSET_TAG = '<script src="assets/bf-si-v20-shadow-workbench.js?v=20260808-v1"></script>'


GET_ROUTES = '''        if parsed.path == "/api/si-v20/status":
            self.handle_si_v20_status(parsed.query)
            return
        if parsed.path == "/api/si-v20/history":
            self.handle_si_v20_history(parsed.query)
            return
'''

POST_ROUTES = '''        if parsed.path == "/api/si-v20/predict":
            self.handle_si_v20_predict()
            return
        if parsed.path == "/api/si-v20/replay":
            self.handle_si_v20_replay()
            return
'''

HANDLERS = '''    # REQ-SI-V20-8093-8094-SHADOW-WORKBENCH-20260808
    def _si_v20_operator_session(self) -> dict[str, Any] | None:
        session = self.current_review_session()
        if si_v20_shadow.require_login() and not session:
            self.send_json(
                {
                    "ok": False,
                    "error_code": "SI_V20_LOGIN_REQUIRED",
                    "error": "请先使用生产账号登录，再发起V20影子预测或历史回放。",
                },
                status=401,
            )
            return None
        return session or {"sub": "local_operator", "role": "operator"}

    def handle_si_v20_status(self, query: str) -> None:
        params = parse_qs(query)
        try:
            target_limit = max(1, min(int(params.get("limit", ["120"])[0]), 300))
            payload = si_v20_shadow.SiV20ShadowService().status(target_limit=target_limit)
        except ValueError as exc:
            self.send_json({"ok": False, "error": str(exc)}, status=400)
            return
        except Exception as exc:  # noqa: BLE001
            self.send_json({"ok": False, "error_code": "SI_V20_STATUS_UNAVAILABLE", "error": sanitize_model_exposure(exc)}, status=503)
            return
        self.send_json(payload)

    def handle_si_v20_history(self, query: str) -> None:
        params = parse_qs(query)
        parsed_dates: dict[str, date | None] = {"date_from": None, "date_to": None}
        for name in parsed_dates:
            value = str(params.get(name, [""])[0]).strip()
            if not value:
                continue
            try:
                parsed_dates[name] = datetime.strptime(value, "%Y-%m-%d").date()
            except ValueError:
                self.send_json({"ok": False, "error": f"{name} must be YYYY-MM-DD"}, status=400)
                return
        try:
            limit = max(1, min(int(params.get("limit", ["1000"])[0]), 2000))
        except ValueError:
            self.send_json({"ok": False, "error": "limit must be an integer"}, status=400)
            return
        meltno = str(params.get("meltno", [""])[0]).strip() or None
        latest_per_heat = str(params.get("latest_per_heat", ["1"])[0]).lower() in {"1", "true", "yes"}
        try:
            payload = si_v20_shadow.SiV20ShadowService().history(
                date_from=parsed_dates["date_from"], date_to=parsed_dates["date_to"],
                meltno=meltno, limit=limit, latest_per_heat=latest_per_heat,
            )
        except Exception as exc:  # noqa: BLE001
            self.send_json({"ok": False, "error_code": "SI_V20_HISTORY_UNAVAILABLE", "error": sanitize_model_exposure(exc), "items": []}, status=503)
            return
        self.send_json(payload)

    def _handle_si_v20_write(self, action: str) -> None:
        session = self._si_v20_operator_session()
        if session is None:
            return
        try:
            payload = self.read_json_body()
        except Exception:
            self.send_json({"ok": False, "error": "请求JSON格式不正确"}, status=400)
            return
        service = si_v20_shadow.SiV20ShadowService()
        try:
            kwargs = {"username": str(session.get("sub") or "operator"), "role": str(session.get("role") or "operator")}
            result = service.predict(payload, **kwargs) if action == "predict" else service.replay(payload, **kwargs)
        except ValueError as exc:
            self.send_json({"ok": False, "error": str(exc)}, status=400)
            return
        except Exception as exc:  # noqa: BLE001
            self.send_json({"ok": False, "error_code": "SI_V20_PREDICTION_FAILED", "error": sanitize_model_exposure(exc)}, status=503)
            return
        self.send_json(result)

    def handle_si_v20_predict(self) -> None:
        self._handle_si_v20_write("predict")

    def handle_si_v20_replay(self) -> None:
        self._handle_si_v20_write("replay")

'''


def insert_after(text: str, anchor: str, addition: str, name: str) -> str:
    if addition.strip() in text:
        return text
    if anchor not in text:
        raise RuntimeError(f"{name} anchor missing")
    return text.replace(anchor, anchor + addition, 1)


def patch_server(path: Path) -> None:
    text = path.read_text(encoding="utf-8")
    if "from datetime import datetime, timedelta, timezone" in text:
        text = text.replace(
            "from datetime import datetime, timedelta, timezone",
            "from datetime import date, datetime, timedelta, timezone",
            1,
        )
    elif "from datetime import date, datetime, timedelta, timezone" not in text:
        raise RuntimeError("datetime import anchor missing")
    text = insert_after(
        text,
        "from heat_performance_quality import HeatPerformanceQualityStore\n",
        "import si_v20_shadow\n",
        "si_v20 import",
    )
    text = insert_after(
        text,
        '        if parsed.path == "/api/heat-performance-quality":\n            self.handle_heat_performance_quality(parsed.query)\n            return\n',
        GET_ROUTES,
        "GET routes",
    )
    text = insert_after(
        text,
        '        if parsed.path == "/api/diagnosis-ai-analysis/retry":\n            self.handle_diagnosis_ai_analysis_retry()\n            return\n',
        POST_ROUTES,
        "POST routes",
    )
    if MARKER not in text:
        anchor = "    def forward_response(self, resp, content_type: str) -> None:\n"
        if anchor not in text:
            raise RuntimeError("handler insertion anchor missing")
        text = text.replace(anchor, HANDLERS + anchor, 1)
    path.write_text(text, encoding="utf-8", newline="\n")


def patch_page(path: Path) -> None:
    text = path.read_text(encoding="utf-8")
    if "bf-si-v20-shadow-workbench.js" in text:
        return
    if "</body>" not in text:
        raise RuntimeError(f"page body anchor missing: {path}")
    text = text.replace("</body>", f"  {ASSET_TAG}\n</body>", 1)
    path.write_text(text, encoding="utf-8", newline="\n")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--server", type=Path, required=True)
    parser.add_argument("--page8093", type=Path, required=True)
    parser.add_argument("--page8094", type=Path, required=True)
    args = parser.parse_args()
    patch_server(args.server)
    patch_page(args.page8093)
    patch_page(args.page8094)
    for path in (args.server, args.page8093, args.page8094):
        print(path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
