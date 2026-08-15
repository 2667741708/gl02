from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SKILL = ROOT / ".codex" / "skills" / "agent-tool-capability-evaluation"


def test_four_core_evaluations_are_declared() -> None:
    skill = (SKILL / "SKILL.md").read_text(encoding="utf-8")
    reference = (SKILL / "references" / "four-core-evaluations.md").read_text(encoding="utf-8")
    rubric = (SKILL / "references" / "evaluation-rubric.md").read_text(encoding="utf-8")
    for term in (
        "传感器证据落地推断",
        "确定性工具增强计算",
        "多工具跨 MCP 编排",
        "最终答案证据忠实度",
    ):
        assert term in reference
        assert term in rubric
    assert "传感器证据落地判推断" in reference
    assert "scripts/evaluate_mcp_template_lines.py" in skill


def test_template_evaluator_is_bundled_and_has_safe_live_gate() -> None:
    script = (SKILL / "scripts" / "evaluate_mcp_template_lines.py").read_text(encoding="utf-8")
    assert '--execute' in script
    assert '--list-only' in script
    assert '--resume' in script
    assert '--case-id' in script
    assert "no retry by contract" in script
    assert "checkpoint.jsonl" in script


def test_project_to_global_sync_uses_exact_file_list() -> None:
    script = (ROOT / "tools" / "sync_agent_tool_capability_evaluation_skill.ps1").read_text(encoding="utf-8")
    assert "PowerShell 7 Core" in script
    assert "PublishProjectToGlobal" in script
    assert "Verify" in script
    assert "four-core-evaluations.md" in script
    assert "evaluate_mcp_template_lines.py" in script
    assert "remote_write_performed = $false" in script
