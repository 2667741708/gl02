#!/usr/bin/env python3
"""Patch only the multi-condition feature block into the guarded 8094 HTML."""

from __future__ import annotations

import argparse
import json
import os
import re
import tempfile
from pathlib import Path


REQ_MARKER = "REQ-OPT-MULTI-CONDITION-LLM-REVIEW-20260805"
VISUAL_REQ_MARKER = "REQ-OPT-VISUAL-COCKPIT-RESTORE-20260806"
DEPLOY_MARKER = "OPS-8094-MULTI-CONDITION-REVIEW-20260805"
FEATURE_START = f"    /* {REQ_MARKER} */"
FEATURE_END = "    OptimizationTab = OptimizationVisualWorkbenchLayout;"
PREVIOUS_FEATURE_END = "    OptimizationTab = OptimizationMultiConditionCockpitLayout;"
LEGACY_ASSIGNMENT = "    OptimizationTab = OptimizationEngineCockpitLayout;"
WS_8768 = "get('ws_port') || '8768'"
WS_8769 = "get('ws_port') || '8769'"
REQUIRED_BASELINE_MARKERS = (
    "BUG-BF3D-CAD-PANEL-BODY-GAP-20260804-R2",
    "20260726-viewport-wheel-r8",
    "function OptimizationEngineCockpitLayout",
    "function bfRecommendationConfidence",
    "function getDiag",
)


def extract_feature_block(source: str) -> str:
    start = source.find(FEATURE_START)
    if start < 0:
        raise ValueError(f"feature source missing {REQ_MARKER}")
    end = source.find(FEATURE_END, start)
    if end < 0:
        raise ValueError("feature source missing multi-condition assignment")
    end += len(FEATURE_END)
    block = source[start:end]
    if block.count(REQ_MARKER) != 1:
        raise ValueError("feature source contains an ambiguous requirement marker")
    if block.count(VISUAL_REQ_MARKER) != 2:
        raise ValueError(f"feature source missing visual workbench contract: {VISUAL_REQ_MARKER}")
    return block.replace(
        FEATURE_START,
        f"{FEATURE_START}\n    /* {DEPLOY_MARKER} */",
        1,
    )


def patch_text(
    target: str, feature_source: str, ws_port: int = 8769
) -> tuple[str, dict[str, object]]:
    for marker in REQUIRED_BASELINE_MARKERS:
        if marker not in target:
            raise ValueError(f"8094 baseline marker missing: {marker}")

    feature_block = extract_feature_block(feature_source)
    if REQ_MARKER in target:
        start = target.find(FEATURE_START)
        end = target.find(FEATURE_END, start)
        matched_end = FEATURE_END
        if end < 0:
            end = target.find(PREVIOUS_FEATURE_END, start)
            matched_end = PREVIOUS_FEATURE_END
        if start < 0 or end < 0:
            raise ValueError("existing feature block is incomplete")
        end += len(matched_end)
        patched = target[:start] + feature_block + target[end:]
        mode = "replace"
    else:
        if target.count(LEGACY_ASSIGNMENT) != 1:
            raise ValueError("8094 legacy optimization assignment is not unique")
        patched = target.replace(LEGACY_ASSIGNMENT, feature_block, 1)
        mode = "insert"

    desired_ws = WS_8769 if ws_port == 8769 else WS_8768
    alternate_ws = WS_8768 if ws_port == 8769 else WS_8769
    if patched.count(desired_ws) == 1:
        pass
    elif patched.count(alternate_ws) == 1:
        patched = patched.replace(alternate_ws, desired_ws, 1)
    else:
        raise ValueError("8094 default WebSocket port contract is ambiguous")

    checks = {
        "requirement_marker_count": patched.count(REQ_MARKER),
        "deployment_marker_count": patched.count(DEPLOY_MARKER),
        "multi_assignment_count": patched.count(FEATURE_END),
        "previous_assignment_count": patched.count(PREVIOUS_FEATURE_END),
        "legacy_assignment_count": patched.count(LEGACY_ASSIGNMENT),
        "visual_requirement_marker_count": patched.count(VISUAL_REQ_MARKER),
        "default_ws_8769_count": patched.count(WS_8769),
        "default_ws_8768_count": patched.count(WS_8768),
    }
    expected = {
        "requirement_marker_count": 1,
        "deployment_marker_count": 1,
        "multi_assignment_count": 1,
        "previous_assignment_count": 0,
        "legacy_assignment_count": 0,
        "visual_requirement_marker_count": 2,
        "default_ws_8769_count": 1 if ws_port == 8769 else 0,
        "default_ws_8768_count": 1 if ws_port == 8768 else 0,
    }
    if checks != expected:
        raise ValueError(f"patched 8094 contract mismatch: {checks}")
    return patched, {"mode": mode, **checks}


def write_atomic(path: Path, text: str) -> None:
    handle, temporary = tempfile.mkstemp(prefix=path.name + ".", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(handle, "w", encoding="utf-8", newline="") as stream:
            stream.write(text)
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--target", type=Path, required=True)
    parser.add_argument("--feature-source", type=Path, required=True)
    parser.add_argument("--ws-port", type=int, choices=(8768, 8769), default=8769)
    args = parser.parse_args()
    target = args.target.resolve()
    source = args.feature_source.resolve()
    original = target.read_text(encoding="utf-8")
    patched, report = patch_text(
        original, source.read_text(encoding="utf-8"), ws_port=args.ws_port
    )
    if patched != original:
        write_atomic(target, patched)
    report.update(
        {
            "ok": True,
            "target": str(target),
            "changed": patched != original,
            "length_before": len(original),
            "length_after": len(patched),
        }
    )
    print(json.dumps(report, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
