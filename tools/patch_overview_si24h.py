"""Inject the read-only 24-hour strict-hourly Si card into a dashboard source page."""

from __future__ import annotations

import argparse
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "高炉前端数据" / "frontend_dashboard_v3.server.html"
MARKER = "REQ-8093-OVERVIEW-SI24H-20260811"


def extract_between(text: str, start: str, end: str) -> str:
    left = text.index(start)
    right = text.index(end, left)
    return text[left:right]


def patch(target: Path) -> None:
    source = SOURCE.read_text(encoding="utf-8")
    text = target.read_text(encoding="utf-8")
    component = extract_between(
        source,
        f"    /* {MARKER}",
        "    OverviewRight = function BFOverviewRightThreeColumnV12",
    )
    anchor = "    OverviewRight = function BFOverviewRightThreeColumnV12"
    if text.count(anchor) != 1:
        raise ValueError(f"expected one final OverviewRight anchor, found {text.count(anchor)}")
    if MARKER in text:
        start = text.index(f"    /* {MARKER}")
        end = text.index(anchor, start)
        text = text[:start] + component + text[end:]
    else:
        text = text.replace(anchor, component + anchor, 1)

    old_tail = "</div><OverviewLargeTrendV8 buf={buf} items={items} trendNote={trendNote} /></aside> }"
    if text.count(old_tail) == 1:
        text = text.replace(old_tail, "</div><OverviewSiHourly24hV15 /></aside> }", 1)
    elif "</div><OverviewSiHourly24hV15 /></aside> }" not in text:
        raise ValueError(f"expected one final trend tail, found {text.count(old_tail)}")

    css = extract_between(
        source,
        ".overview-si24-panel .panel-body",
        "\n`; document.head.appendChild(el)",
    )
    style_anchor = "    /* REQ-8093-FAST-IN-APP-NAV-20260715 */"
    if text.count(style_anchor) != 1:
        raise ValueError(f"expected one style insertion anchor, found {text.count(style_anchor)}")
    style_block = (
        "    ; (function () { const apply = () => { const old = document.getElementById('req-overview-si24h-20260811'); "
        "if (old) old.remove(); const el = document.createElement('style'); el.id = 'req-overview-si24h-20260811'; el.textContent = `\n"
        + css
        + "\n`; document.head.appendChild(el) }; apply(); setTimeout(apply, 0); setTimeout(apply, 500) })();\n"
    )
    if "req-overview-si24h-20260811" not in text:
        text = text.replace(style_anchor, style_block + style_anchor, 1)
    if text.count(MARKER) != 1 or "<OverviewSiHourly24hV15 />" not in text:
        raise ValueError("patched page failed the Si24h marker contract")
    target.write_text(text, encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--target", type=Path, required=True)
    args = parser.parse_args()
    patch(args.target.resolve())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
