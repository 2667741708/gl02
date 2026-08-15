"""Repository entrypoint for the canonical MCP agent golden-task evaluator."""
from __future__ import annotations

import runpy
from pathlib import Path


SCRIPT = (
    Path(__file__).resolve().parents[1]
    / ".codex" / "skills" / "agent-tool-capability-evaluation"
    / "scripts" / "evaluate_mcp_gold_tasks.py"
)

if __name__ == "__main__":
    runpy.run_path(str(SCRIPT), run_name="__main__")
