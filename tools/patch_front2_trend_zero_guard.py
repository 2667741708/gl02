# -*- coding: utf-8 -*-
"""Add the trend forecast zero-collapse guard to the front2 source page."""

from __future__ import annotations

import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
TARGET = ROOT / "高炉前端数据" / "front2" / "frontend_dashboard_front2.server.html"
MARKER = "REQ-TREND-19-ZERO-COLLAPSE-GUARD-20260807"
HELPER = (
    f"/* {MARKER}: reject impossible all-zero forecasts for nonzero histories. */\n"
    "function sanitizeTrendForecast(id,values,history){if(!Array.isArray(values))return [];"
    "const forecast=values.map(Number).filter(Number.isFinite),recent=(history||[]).slice(-30).map(Number).filter(Number.isFinite);"
    "if(forecast.length&&recent.some(value=>Math.abs(value)>1e-6)&&forecast.every(value=>Math.abs(value)<=1e-9))return [];"
    "return values;}\n"
)


def main() -> int:
    text = TARGET.read_text(encoding="utf-8")
    changed = False
    if MARKER not in text:
        text, count = re.subn(
            r"(const TREND_PREDICT_IDS=\[[^\n]+?\];\r?\n)",
            r"\1" + HELPER,
            text,
            count=1,
        )
        if count != 1:
            raise RuntimeError("TREND_PREDICT_IDS declaration anchor was not found")
        changed = True
    guarded = "bufRef.current[`${id}__forecast`]=sanitizeTrendForecast(id,arr,bufRef.current[id])"
    if guarded not in text:
        text, count = re.subn(
            r"bufRef\.current\[`\$\{id\}__forecast`\]=arr",
            guarded,
            text,
            count=1,
        )
        if count != 1:
            raise RuntimeError("forecast assignment anchor was not found")
        changed = True
    if changed:
        TARGET.write_text(text, encoding="utf-8", newline="\n")
    print({"changed": changed, "target": str(TARGET)})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
