"""Execute only the real MCP read function against local non-sensitive files."""
import ast
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize("source_path", [ROOT / "高炉前端数据/智能助手/mcp/bf_data_mcp_server.py", ROOT / ".codex_runtime/qa-routing-v4/candidate/bf_data_mcp_server.py"])
def test_unicode_and_real_truncation_use_character_counts(tmp_path, source_path):
    tree = ast.parse(source_path.read_text(encoding="utf-8"))
    fn = next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == "read_report_excerpt")
    fn.decorator_list = []
    env = {"Any": object, "REPORTS_DIR": tmp_path, "MAX_REPORT_CHARS": 10000, "normalize_text": lambda value: value}
    exec(compile(ast.fix_missing_locations(ast.Module(body=[fn], type_ignores=[])), "actual_report_reader", "exec"), env)
    body = "# 日报\n## 摘要\n" + "中文记录。" * 100
    path = tmp_path / "日报.md"
    path.write_text(body, encoding="utf-8")
    full = env["read_report_excerpt"]("日报.md", mode="full", max_chars=4000)
    assert full["content"] == body and full["truncated"] is False
    assert full["total_chars"] == full["chars_returned"] == len(body)
    truncated = env["read_report_excerpt"]("日报.md", max_chars=200)
    assert truncated["truncated"] is True and truncated["chars_returned"] == 200
    assert truncated["total_chars"] == len(body)
    outside = tmp_path.parent / "outside.md"
    with pytest.raises(ValueError, match="禁止读取"):
        env["read_report_excerpt"]("../outside.md")
