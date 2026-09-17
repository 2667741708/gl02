"""Ordinary preparation must require a positive source grant, retain scoped ABC evidence."""
import ast
import copy
import hashlib
import json
from pathlib import Path
import subprocess
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'tools'), str(ROOT / 'tests')]
from build_qa_ordinary_context_candidate import PRIOR, HELPERS, build_proxy, validate_planner
from qa_frozen_candidate import latest_frozen_candidate
from test_qa_sensor_context_source_gate import exercise, qa_task_plan


@pytest.mark.parametrize('question', [
    '你好', '解释炉顶压力控制原理。', '说明工艺规则的通常含义。',
    '请解释本对话绑定的规则。', '换个话题，解释MCP协议的含义。',
])
def test_ordinary_prepare_archives_page_without_sensor_evidence(question):
    state = exercise(question)
    assert state['sensor_reads'] == state['browser_snapshot_reads'] == []
    assert state['snapshot_writes'] == ['browser_snapshot']
    assert state['captured']['snapshots'] == []
    assert state['captured']['snapshot_id'] is None


@pytest.mark.parametrize('question', ['查询当前炉顶压力。', '查询最近一小时风温的趋势。'])
def test_actual_task_plan_authorizes_explicit_live_sources(question):
    plan = qa_task_plan.build_task_plan(question)
    policy = qa_task_plan.sensor_context_policy(plan)
    assert policy['enabled'] is True and policy['skipped'] is False
    assert policy['reason'] == 'task_plan_live_source_granted'


@pytest.mark.parametrize('mutation', [
    lambda p: p.pop('intents'), lambda p: p.update(intents='live_data'),
    lambda p: p.update(intents=['ordinary_qa']), lambda p: p.pop('allowed_sources'),
    lambda p: p.update(allowed_sources='live_readonly_data'),
    lambda p: p.update(allowed_sources=['knowledge_base']),
    lambda p: p.pop('allow_prefetch'), lambda p: p.update(allow_prefetch=1),
    lambda p: p.update(allow_prefetch=False), lambda p: p.update(no_live_lookup=True),
    lambda p: p.update(all_tools_disabled=True),
])
def test_missing_malformed_or_restricted_grant_fails_closed(mutation):
    plan = qa_task_plan.build_task_plan('查询当前炉顶压力。')
    mutation(plan)
    assert qa_task_plan.sensor_context_policy(plan)['enabled'] is False


@pytest.mark.parametrize('plan', [None, {}, 'live_readonly_data', []])
def test_non_plan_input_never_grants_live_sources(plan):
    assert qa_task_plan.sensor_context_policy(plan)['enabled'] is False


def test_code_only_overrides_an_otherwise_valid_grant():
    plan = qa_task_plan.build_task_plan('查询当前炉顶压力。')
    assert qa_task_plan.sensor_context_policy(plan, code_only=True)['reason'] == 'disabled_code_only'


@pytest.mark.parametrize('question', [
    '请解释本对话绑定的规则。', '说明本会话规则的公式和权重。',
    '这个规则为什么触发？', '解释A1规则的评分。', 'C11规则的权重是多少？',
])
def test_explicit_bound_rule_reference_can_use_server_loaded_authority(question):
    assert qa_task_plan.bound_rule_context_requested(question) is True


@pytest.mark.parametrize('question', [
    '你好', '解释压力控制原理。', '换个话题，解释这个规则。',
    '不要使用本会话上下文，解释规则。', '忘掉上文，解释A1规则。',
    '请翻译“解释本对话绑定的规则”。', '请翻译“C11规则的权重是多少”。',
    '解释C12规则。', '解释XA1规则。', '解释B14规则。',
    '仅根据我给的数据10、20、30，解释A1规则并计算平均值。',
    '逐字引用《制度》原文，再解释本对话绑定的规则。',
])
def test_unrelated_quoted_negative_or_exclusive_source_request_does_not_inherit_authority(question):
    assert qa_task_plan.bound_rule_context_requested(question) is False


def test_frozen_candidate_has_exact_two_changed_modules_and_preserves_whole_other_ast():
    candidate, manifest = latest_frozen_candidate(ROOT)
    assert manifest['sensor_context_gate'] == 'qa-sensor-context-source-gate-v2'
    assert len(manifest['inherited_v47_files_byte_identical']) == 14
    for name in manifest['inherited_v47_files_byte_identical']:
        assert (candidate / name).read_bytes() == (PRIOR / name).read_bytes()
    before = (PRIOR / 'ollama_proxy_server.py').read_text(encoding='utf-8')
    assert build_proxy(before) == (candidate / 'ollama_proxy_server.py').read_text(encoding='utf-8')
    validate_planner((PRIOR / 'qa_task_plan.py').read_bytes(), (candidate / 'qa_task_plan.py').read_bytes())
    assert manifest['model_digest'] == 'e4ad74c41d68de1c8004419d8141a2b2df2275fa08f0dcf326ca0e63fb6d8124'
    assert all(manifest[key] is False for key in ('model_switch_allowed',
        'fallback_model_allowed', 'same_name_weight_replacement_allowed'))


def test_planner_proof_rejects_other_top_level_semantic_changes():
    candidate, _ = latest_frozen_candidate(ROOT)
    current = (candidate / 'qa_task_plan.py').read_text(encoding='utf-8')
    with pytest.raises(AssertionError, match='Existing task planning'):
        validate_planner((PRIOR / 'qa_task_plan.py').read_bytes(), current + '\nUNREVIEWED = True\n')


def test_optimized_python_cannot_disable_builder_guards():
    result = subprocess.run([sys.executable, '-O', '-X', 'utf8',
        str(ROOT / 'tools/build_qa_ordinary_context_candidate.py'), '--help'],
        capture_output=True, text=True, encoding='utf-8', timeout=15)
    assert result.returncode != 0 and 'assertions enabled' in result.stderr
