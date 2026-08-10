#!/usr/bin/env python3
"""Remove the visible judgment-confidence score from V3 frontend pages.

The diagnostic score remains available to rules, charts, APIs, and audit records.
This patch only removes the user-facing ``判断把握 ...`` presentation.  It is
idempotent so it can be applied to both the 8093 source page and the separately
maintained 8094 preview page during an atomic frontend deployment.
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path


LABEL = "判断把握"
MARKER = "REQ-UI-REMOVE-JUDGMENT-CONFIDENCE-20260806"


def _matching_tag_end(text: str, start: int, tag: str) -> int | None:
    token_re = re.compile(rf"</?{tag}\b[^>]*>", re.IGNORECASE)
    depth = 0
    for match in token_re.finditer(text, start):
        token = match.group(0)
        if token.startswith("</"):
            depth -= 1
            if depth == 0:
                return match.end()
        elif not token.endswith("/>"):
            depth += 1
    return None


def _remove_enclosing_blocks(
    text: str,
    *,
    tag: str,
    opening_marker: str,
) -> tuple[str, int]:
    removed = 0
    cursor = 0
    while True:
        label_at = text.find(LABEL, cursor)
        if label_at < 0:
            break
        search_at = label_at
        matched = False
        while search_at >= 0:
            start = text.rfind(f"<{tag}", 0, search_at + 1)
            if start < 0:
                break
            opening_end = text.find(">", start)
            if opening_end < 0 or opening_end >= label_at:
                search_at = start - 1
                continue
            opening = text[start : opening_end + 1]
            if opening_marker not in opening:
                search_at = start - 1
                continue
            end = _matching_tag_end(text, start, tag)
            if end is not None and start <= label_at < end:
                text = text[:start] + text[end:]
                removed += 1
                matched = True
                cursor = 0
                break
            search_at = start - 1
        if not matched:
            cursor = label_at + len(LABEL)
    return text, removed


def patch_text(
    original: str, *, add_marker: bool = True
) -> tuple[str, dict[str, int | bool]]:
    text = original
    counts = {"confidence_blocks": 0, "conclusion_rows": 0, "meta_items": 0, "copy": 0}

    text, counts["confidence_blocks"] = _remove_enclosing_blocks(
        text, tag="div", opening_marker='className="confidence"'
    )
    text, counts["conclusion_rows"] = _remove_enclosing_blocks(
        text, tag="div", opening_marker='className="diag-line'
    )
    text, counts["meta_items"] = _remove_enclosing_blocks(
        text, tag="span", opening_marker="<span"
    )

    replacements = (
        (
            "判断把握 ${fmtNum(d.score, 0)}/100，顶温变化",
            "顶温变化",
        ),
        (
            "判断把握 ${fmtNum(d.score,0)}/100，顶温变化",
            "顶温变化",
        ),
        (
            "，判断把握 ${fmtNum(d.score, 0)}/100。",
            "。",
        ),
        (
            "，判断把握 ${fmtNum(d.score,0)}/100。",
            "。",
        ),
        (
            "；判断把握：${fmtNum(diag.score, 2)}/100。",
            "。",
        ),
        (
            ".replace(/判断把握/g, '判断把握')",
            "",
        ),
        (
            " const confidence = Math.round(Number(d.confidence || d.score || 0));",
            "",
        ),
        (
            "    function bfRecommendationConfidence(d) { const raw = Number(d?.confidence), score = Number(d?.score || 0); if (Number.isFinite(raw) && raw > 0 && raw <= 1) return Math.round(raw * 100); if (Number.isFinite(raw) && raw > 1) return Math.round(Math.min(100, raw)); return Math.round(Math.min(100, Math.max(0, score))) }\n",
            "",
        ),
        (
            "const confidence = bfRecommendationConfidence(d), decision =",
            "const decision =",
        ),
    )
    for before, after in replacements:
        occurrences = text.count(before)
        if occurrences:
            text = text.replace(before, after)
            counts["copy"] += occurrences

    if LABEL in text:
        lines = [
            str(index)
            for index, line in enumerate(text.splitlines(), start=1)
            if LABEL in line
        ]
        raise ValueError(f"unhandled visible label remains on lines: {','.join(lines)}")

    if add_marker and MARKER not in text:
        closing = text.lower().rfind("</body>")
        marker = f"  <!-- {MARKER} -->\n"
        text = text[:closing] + marker + text[closing:] if closing >= 0 else text + "\n" + marker

    counts["changed"] = text != original
    return text, counts


def patch_file(path: Path, *, add_marker: bool = True) -> dict[str, object]:
    resolved = path.resolve()
    original = resolved.read_text(encoding="utf-8")
    patched, counts = patch_text(original, add_marker=add_marker)
    if patched != original:
        temporary = resolved.with_suffix(resolved.suffix + ".judgment-confidence.tmp")
        temporary.write_text(patched, encoding="utf-8")
        temporary.replace(resolved)
    return {
        "ok": True,
        "path": str(resolved),
        "label_absent": LABEL not in patched,
        "marker_present": MARKER in patched,
        **counts,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--target", type=Path, required=True)
    parser.add_argument("--no-marker", action="store_true")
    args = parser.parse_args()
    print(
        json.dumps(
            patch_file(args.target, add_marker=not args.no_marker),
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
