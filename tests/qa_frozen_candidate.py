"""Bind current proxy tests to the newest frozen closure, never a stale fallback."""
import hashlib
import json
from pathlib import Path
import re


def latest_frozen_candidate(root: Path):
    options = []
    for manifest_path in (root / '.codex_runtime').glob('qa-routing-v*/candidate-r*/package_manifest.private.json'):
        match = re.fullmatch(r'qa-routing-v(\d+)', manifest_path.parent.parent.name)
        revision = re.fullmatch(r'candidate-r(\d+)', manifest_path.parent.name)
        if match and revision:
            options.append((int(match.group(1)), int(revision.group(1)), manifest_path))
    assert options, 'No frozen current candidate; freeze before execution-chain tests'
    path = max(options, key=lambda option: option[:2])[2]
    manifest = json.loads(path.read_bytes())
    base_files = {'bf_data_mcp_server.py', 'ollama_proxy_server.py', 'qa_completion.py',
        'qa_document_compound.py', 'qa_document_knowledge.py', 'qa_evidence_policy.py',
        'qa_fixed_model_identity.py', 'qa_history_compound.py', 'qa_history_projection.py',
        'qa_knowledge_reader_source_gate.py', 'qa_knowledge_source_binding.py',
        'qa_statistical_evidence.py', 'qa_task_plan.py', 'qa_verified_facts.py', 'qa_window_quality.py'}
    if manifest['schema'] == 'bf.qa.private-prompt-binding-candidate.v1':
        assert set(manifest['files']) == base_files | {'qa_prompt_binding.py'}
        assert manifest['added_modules'] == ['qa_prompt_binding.py']
        assert (path.parent / 'qa_prompt_binding.py').read_bytes() == (root / '高炉前端数据/智能助手/backend/qa_prompt_binding.py').read_bytes()
    else:
        assert set(manifest['files']) == base_files
    assert manifest['model_name'] == 'chiqiongblastfuenace:latest'
    assert manifest['model_digest'] == 'e4ad74c41d68de1c8004419d8141a2b2df2275fa08f0dcf326ca0e63fb6d8124'
    assert not any(manifest[key] for key in ('model_switch_allowed', 'same_name_weight_replacement_allowed', 'fallback_model_allowed'))
    for name, item in manifest['files'].items():
        assert Path(name).name == name and name not in ('.', '..')
        assert hashlib.sha256((path.parent / name).read_bytes()).hexdigest() == item['sha256']
    assert (path.parent / 'qa_task_plan.py').read_bytes() == (root / '高炉前端数据/智能助手/backend/qa_task_plan.py').read_bytes(), 'Newest frozen planner differs; do not fall back to an older package'
    return path.parent, manifest
