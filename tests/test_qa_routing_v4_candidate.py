from __future__ import annotations

import ast
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CANDIDATE = ROOT / ".codex_runtime" / "qa-routing-v4" / "candidate"


def test_v4_candidate_uses_shared_entity_resolver() -> None:
    source = (CANDIDATE / "ollama_proxy_server.py").read_text(encoding="utf-8")
    ast.parse(source)
    assert "import qa_entity_resolution" in source
    assert "entity_resolution = qa_entity_resolution.resolve_requested_entities(question)" in source
    assert 'variables = list(entity_resolution.get("variables") or [])' in source


def test_v4_build_is_hash_bound_to_accepted_v3() -> None:
    report = json.loads((CANDIDATE / "build.json").read_text(encoding="utf-8"))
    assert report["proxy_baseline_sha256"] == "abd7cc463c42a7e1c707e1b840b33c9040b33cb850ac7719b164732329af6e67"
    assert report["task_plan_baseline_sha256"] == "bc34986d7a8cb7ff5af11d073809fce623b4cd924865484d5bf98cd9255510e8"
    assert report["issues"] == ["QAOPT-R03"]
    assert report["syntax"] == "passed"
    assert report["production_changed"] is False
