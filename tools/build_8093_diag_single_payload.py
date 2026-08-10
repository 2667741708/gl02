"""Build a single-condition diagnosis payload on top of the stable 8093 proxy.

The local development proxy may contain unrelated, not-yet-deployed MCP changes.
This builder copies only the diagnosis-analysis function block into a downloaded
stable 8093 source so the guarded deployment cannot pull in those dependencies.
"""

from __future__ import annotations

import argparse
from pathlib import Path


BLOCK_START = "def load_five_minute_diagnosis_context("
BLOCK_END = "class Handler(BaseHTTPRequestHandler):"
ASSET_VERSION = "20260806-core19-r10-foreman-knowledge"


def replace_block(source: str, replacement_source: str) -> str:
    source_start = source.index(BLOCK_START)
    source_end = source.index(BLOCK_END, source_start)
    replacement_start = replacement_source.index(BLOCK_START)
    replacement_end = replacement_source.index(BLOCK_END, replacement_start)
    replacement = replacement_source[replacement_start:replacement_end]
    return source[:source_start] + replacement + source[source_end:]


def build(base_path: Path, local_path: Path, output_path: Path) -> None:
    base = base_path.read_text(encoding="utf-8-sig")
    local = local_path.read_text(encoding="utf-8-sig")
    for text, name in ((base, "base"), (local, "local")):
        if text.count(BLOCK_START) != 1 or text.count(BLOCK_END) != 1:
            raise RuntimeError(f"{name} proxy diagnosis block markers changed")
    if "import diagnosis_review\n" not in base:
        raise RuntimeError("stable proxy import anchor changed")
    if "import diag_ai_evidence\n" not in base:
        base = base.replace(
            "import diagnosis_review\n",
            "import diagnosis_review\nimport diag_ai_evidence\n",
            1,
        )
    result = replace_block(base, local)
    core_route = (
        '        if parsed.path == "/api/diagnosis-core-evidence":\n'
        "            self.handle_diagnosis_core_evidence_get(parsed.query)\n"
        "            return\n"
    )
    if core_route not in result:
        route_anchor = (
            '        if parsed.path == "/api/diagnosis-ai-analysis":\n'
            "            self.handle_diagnosis_ai_analysis_get(parsed.query)\n"
            "            return\n"
        )
        if route_anchor not in result:
            raise RuntimeError("diagnosis analysis route anchor changed")
        result = result.replace(route_anchor, route_anchor + core_route, 1)
    for previous_asset_version in (
        "20260805-ai5m-r1",
        "20260805-ai-evidence-r2",
        "20260805-ai-single-r3",
        "20260806-core19-r4",
        "20260806-core19-r5",
        "20260806-core19-r6",
        "20260806-core19-r8",
        "20260806-core19-r7",
    ):
        result = result.replace(previous_asset_version, ASSET_VERSION)
    for asset_name in (
        "bf-diagnosis-review-local.js",
        "bf-diagnosis-manual-score-local.js",
    ):
        result = result.replace(
            f'<script defer src="/assets/{asset_name}?v={ASSET_VERSION}"></script>',
            f'<script src="/assets/{asset_name}?v={ASSET_VERSION}"></script>',
        )
    required = (
        "build_single_condition_analysis_messages",
        "parse_single_condition_analysis_payload",
        "max_tokens=1200",
        "current_five_minute_analysis_context(target_label)",
        'parsed.path == "/api/diagnosis-core-evidence"',
        f"v={ASSET_VERSION}",
        f'<script src="/assets/bf-diagnosis-manual-score-local.js?v={ASSET_VERSION}"></script>',
    )
    missing = [marker for marker in required if marker not in result]
    if missing:
        raise RuntimeError("single-condition payload markers missing: " + ", ".join(missing))
    forbidden = (
        "from mcp_host.cross_source_plan import",
        "context_with_cross_source_snapshot",
    )
    # The downloaded stable proxy may already contain the completed MCP upgrade.
    # Preserve those markers, but never introduce an MCP dependency that was not
    # present in the remote deployment baseline.
    present = [marker for marker in forbidden if marker not in base and marker in result]
    if present:
        raise RuntimeError("unrelated MCP dependency leaked into payload: " + ", ".join(present))
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(result, encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", required=True, type=Path)
    parser.add_argument("--local", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    build(args.base, args.local, args.output)
    print(args.output.resolve())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
