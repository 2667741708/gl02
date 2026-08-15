"""Repository entrypoint for the agent-tool-capability-evaluation skill script."""
from __future__ import annotations

import runpy
from pathlib import Path


SCRIPT = (
    Path(__file__).resolve().parents[1]
    / ".codex"
    / "skills"
    / "agent-tool-capability-evaluation"
    / "scripts"
    / "evaluate_mcp_template_lines.py"
)

if __name__ == "__main__":
    runpy.run_path(str(SCRIPT), run_name="__main__")
