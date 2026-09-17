"""Exercise actual preparation through its sensor section; native full path is separate."""
import ast
from contextlib import nullcontext
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import sys
import time

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / '高炉前端数据/智能助手/backend'))
import qa_evidence_policy
import qa_task_plan
from qa_frozen_candidate import latest_frozen_candidate


class ReachedHistory(Exception):
    pass


def exercise(question, *, prior=False, browser_snapshot=True, mode='', owned=True,
        archive_failure=False, access_mode='authenticated'):
    candidate, _ = latest_frozen_candidate(ROOT)
    if prior:
        candidate = ROOT / '.codex_runtime/qa-routing-v45/candidate-r2'
    tree = ast.parse((candidate / 'ollama_proxy_server.py').read_bytes())
    nodes = [node for node in ast.walk(tree) if isinstance(node, ast.FunctionDef)
        and node.name in {'prepare_qa_chat', 'latest_snapshot', 'recent_snapshots'}]
    state = {'sensor_reads': [], 'snapshot_writes': [], 'browser_snapshot_reads': [], 'captured': {}}

    class Cursor:
        def __init__(self, rows): self.rows = rows
        def fetchone(self): return self.rows[0] if self.rows else None
        def fetchall(self): return self.rows

    class Connection:
        def execute(self, sql, params=()):
            text = ' '.join(sql.lower().split())
            if 'from furnace_snapshots' in text:
                state['sensor_reads'].append('assistant_snapshot_read')
                return Cursor([])
            if text.startswith('select * from qa_conversations'):
                return Cursor([{'id': 'synthetic-room'}] if owned else [])
            if 'from qa_conversation_origins' in text:
                return Cursor([])
            raise AssertionError('Unexpected preparation query')

    def reach_history(conn, room):
        frame = sys._getframe(1)
        state['captured'] = {key: frame.f_locals.get(key) for key in ('context_meta', 'snapshot_id', 'snapshots')}
        raise ReachedHistory()

    def insert(conn, snapshot):
        state['snapshot_writes'].append('browser_snapshot')
        if archive_failure:
            raise RuntimeError('Synthetic snapshot archive failure')
        return 1

    def by_id(conn, identity):
        state['browser_snapshot_reads'].append(identity)
        return {'id': identity, 'source_time': '2026-01-01T00:00:00+00:00'}

    namespace = {'Any': object, 'time': time, 'db_connect': lambda: nullcontext(Connection()),
        'qa_task_plan': qa_task_plan, 'qa_evidence_policy': qa_evidence_policy,
        'insert_snapshot': insert, 'snapshot_by_id': by_id,
        'sanitize_model_exposure': lambda exc: type(exc).__name__,
        'last_qa_context_anchor': lambda *args: {'message_id': 3, 'snapshot_id': 4},
        'last_qa_tool_context': lambda *args: {'objects': ['synthetic-private-object']},
        'choose_latest_state_snapshot': lambda rows: next((row for row in rows if row), None),
        'load_messages': reach_history, 'QA_TREND_WINDOW_MINUTES': 30,
        'QA_TREND_HOURS': 8, 'QA_TREND_DIAGNOSIS_LIMIT': 120,
        'now_utc': lambda: datetime(2026, 1, 1, tzinfo=timezone.utc), 'timedelta': timedelta}
    exec(compile(ast.Module(body=nodes, type_ignores=[]), '<full-prepare-sensor-section>', 'exec'), namespace)

    class Handler:
        def latest_pg_snapshot_for_qa(self, conn):
            state['sensor_reads'].append('latest_sensor_provider')
            return None
        def recent_pg_diagnosis_snapshots_for_qa(self, **kwargs):
            state['sensor_reads'].append('trend_sensor_provider')
            return [], {}

    payload = {'conversation_id': 'synthetic-room', '_qa_owner_subject': 'synthetic-owner',
        'analysis_mode': mode, '_qa_access_mode': access_mode}
    if browser_snapshot:
        payload['current_snapshot'] = {'source_time': '2026-01-01T00:00:00+00:00'}
    expected = (RuntimeError if archive_failure else ReachedHistory) if owned else PermissionError
    with pytest.raises(expected):
        namespace['prepare_qa_chat'](Handler(), payload, question)
    return state


@pytest.mark.parametrize('question', [
    '仅基于我提供的数据：风压=[220,224,226]，计算平均值，不查数据库。',
    '假设炉顶压力为180千帕，请计算增加10%的压力。',
    '风温数据分别为1000、1010、1020，请计算平均值。',
    '只分析这些数值10、20、30，不调用工具。',
    '不要读取实时数据库，解释炉顶压力控制原理。',
    '无需访问生产数据，说明温度波动可能的原因。',
    '写一个Python示例读取数据库。',
    '给出SQL查询当前温度的代码。',
    '提供一段Bash脚本。',
])
def test_restriction_prevents_sensor_reads_but_preserves_page_archival_without_evidence(question):
    result = exercise(question)
    assert result['sensor_reads'] == result['browser_snapshot_reads'] == []
    assert result['snapshot_writes'] == ['browser_snapshot']
    assert result['captured']['snapshots'] == [] and result['captured']['snapshot_id'] is None
    assert result['captured']['context_meta']['context_mode'] == 'source_plan_without_live_context'
    assert result['captured']['context_meta']['sensor_context_skipped'] is True


@pytest.mark.parametrize('question', [
    '仅基于我提供的数据：风压=[220,224,226]，计算平均值，不查数据库。',
    '写一个Python示例读取数据库。',
])
def test_shared_guest_page_archival_does_not_enable_sensor_evidence(question):
    result = exercise(question, access_mode='guest_shared')
    assert result['snapshot_writes'] == ['browser_snapshot']
    assert result['sensor_reads'] == result['browser_snapshot_reads'] == []
    assert result['captured']['snapshots'] == [] and result['captured']['snapshot_id'] is None


@pytest.mark.parametrize('question', [
    '仅基于我提供的数据：风压=[220,224,226]，计算平均值，不查数据库。',
    '写一个Python示例读取数据库。',
])
def test_page_archival_failure_never_enables_live_fallback_or_facts(question):
    result = exercise(question, archive_failure=True)
    assert result['snapshot_writes'] == ['browser_snapshot']
    assert result['sensor_reads'] == result['browser_snapshot_reads'] == []
    assert result['captured'] == {}


def test_restriction_without_page_snapshot_performs_no_snapshot_operations():
    result = exercise('假设炉顶压力为180千帕，计算增加10%的压力。', browser_snapshot=False)
    assert result['snapshot_writes'] == result['sensor_reads'] == result['browser_snapshot_reads'] == []


@pytest.mark.parametrize('question', [
    '查询当前炉顶压力。',
    '我给的数据风压=[220,224,226]，分析平均值；同时查询当前炉顶压力。',
    '查询最近一小时炉顶压力；再写一个Python代码示例。',
    '这个最近30分钟的趋势如何？',
    '请解释本对话绑定的规则。',
])
def test_nonrestricted_live_compound_and_followup_paths_keep_snapshot_behavior(question):
    result = exercise(question)
    assert len(result['sensor_reads']) == 5
    assert result['snapshot_writes'] == ['browser_snapshot']
    assert result['browser_snapshot_reads'] == [1]
    assert result['captured']['snapshot_id'] == 1
    assert result['captured']['context_meta']['context_mode'] == 'latest_snapshot_plus_pg_8h_trend'


def test_nonrestricted_initial_context_prepare_keeps_authoritative_path_compatibility():
    assert len(exercise('请解释规则形成过程。', mode='initial_context_explanation')['sensor_reads']) == 5


def test_owner_denial_precedes_any_sensor_access():
    result = exercise('查询当前炉顶压力。', owned=False)
    assert result['sensor_reads'] == result['snapshot_writes'] == []


@pytest.mark.parametrize('question', [
    '仅基于我提供的数据：风压=[220,224,226]，计算平均值，不查数据库。',
    '写一个Python示例读取数据库。',
])
def test_prior_full_prepare_demonstrates_the_five_unwanted_reads(question):
    result = exercise(question, prior=True, browser_snapshot=False)
    assert len(result['sensor_reads']) == 5


def test_frozen_candidate_inherits_other_modules_and_does_not_change_base():
    candidate, manifest = latest_frozen_candidate(ROOT)
    source_gate = ROOT / '.codex_runtime/qa-routing-v46/candidate-r2'
    source_manifest = json.loads((source_gate / 'package_manifest.private.json').read_bytes())
    prior = ROOT / '.codex_runtime/qa-routing-v45/candidate-r2'
    assert len(source_manifest['inherited_v45_files_byte_identical']) == 15
    for name in source_manifest['inherited_v45_files_byte_identical']:
        assert (source_gate / name).read_bytes() == (prior / name).read_bytes()
    before = ast.parse((prior / 'ollama_proxy_server.py').read_bytes())
    after = ast.parse((source_gate / 'ollama_proxy_server.py').read_bytes())
    funcs = lambda tree: {n.name: ast.dump(n, include_attributes=False) for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)}
    a, b = funcs(before), funcs(after)
    assert a.keys() == b.keys()
    assert {name for name in a if a[name] != b[name]} == {'prepare_qa_chat'}
    current = funcs(ast.parse((candidate / 'ollama_proxy_server.py').read_bytes()))
    assert current['prepare_qa_chat'] == b['prepare_qa_chat'], 'New candidate changed the frozen source gate'
    assert manifest['model_digest'] == source_manifest['model_digest']
