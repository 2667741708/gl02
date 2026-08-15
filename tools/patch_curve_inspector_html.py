"""Inject the shared sensor-curve inspector into a generated dashboard HTML page."""

from __future__ import annotations

import argparse
import re
from pathlib import Path


HELPER_TAG = '<script src="assets/curve-inspector.js?v=20260811-hourly-range-r1"></script>'
INSTALL_MARKER = 'window.BFCurveInspector?.installEcharts(c);'


def patch(path: Path) -> bool:
    text = path.read_text(encoding="utf-8")
    changed = False
    if "curve-inspector.js" not in text:
        match = re.search(r'(?m)([ \t]*<script src=["\']libs/echarts\.min\.js["\']></script>)', text)
        if not match:
            raise RuntimeError(f"missing ECharts anchor in {path}")
        text = text[:match.end()] + "\n  " + HELPER_TAG + text[match.end():]
        changed = True
    if INSTALL_MARKER not in text:
        match = re.search(r"c\.setOption\(opt,\s*true\);\s*c\.on\('legendselectchanged'", text)
        if not match:
            raise RuntimeError(f"missing ChartBox anchor in {path}")
        original = match.group(0)
        replacement = re.sub(r"c\.setOption\(opt,\s*true\);", "c.setOption(opt,true); " + INSTALL_MARKER, original, count=1)
        text = text[:match.start()] + replacement + text[match.end():]
        changed = True
    if changed:
        path.write_text(text, encoding="utf-8", newline="")
    return changed


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("html", type=Path)
    args = parser.parse_args()
    changed = patch(args.html)
    text = args.html.read_text(encoding="utf-8")
    if "curve-inspector.js" not in text or INSTALL_MARKER not in text:
        raise RuntimeError("curve inspector contract is incomplete")
    print({"changed": changed, "path": str(args.html), "helper": True, "chart_install": True})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
