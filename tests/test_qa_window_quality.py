"""Quality denominators and window binding, using the actual accepted MCP seams."""
import ast
from copy import deepcopy
from datetime import datetime, timedelta
import importlib.util
import math
from pathlib import Path
import sys
from types import SimpleNamespace
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / '高炉前端数据/智能助手/backend'))
import qa_window_quality as quality
import qa_statistical_evidence as evidence

spec = importlib.util.spec_from_file_location('window_quality_builder', ROOT / 'tools/build_qa_v30_window_quality_candidate.py')
builder = importlib.util.module_from_spec(spec)
spec.loader.exec_module(builder)
MCP_BASE = ROOT / '.codex_runtime/qa-routing-v26/candidate/bf_data_mcp_server.py'
BEGIN, END = '2026-01-01T00:00:00', '2026-01-01T00:30:00'


def sql_stats():
    return {'count': 5, 'observed_rows': 7, 'avg': 4, 'min': 3, 'max': 5,
        **dict(zip(quality.FIELDS.values(), (1, 2, 1, 0, 0, 1)))}


@pytest.mark.parametrize('raw,expected', [(' good ', 'Good'), ('HELD', 'Held'), ('Bad', 'Bad'),
    ('uncertain', 'Uncertain'), ('derived_average', 'DERIVED_AVERAGE'), (0, 'Unknown'),
    (None, 'Unknown'), ('private-secret-label', 'Unknown')])
def test_quality_labels_are_explicit_and_unknown_flags_are_not_guessed_or_echoed(raw, expected):
    assert quality.label(raw) == expected


def test_same_window_quality_denominator_excludes_null_rows_and_preserves_statistics():
    stats = sql_stats()
    original = deepcopy(stats)
    summary = quality.from_counts(stats, BEGIN, END)
    assert stats == original and summary['sample_count'] == 5 and summary['excluded_rows'] == 2
    stats['quality_summary'] = summary
    text = quality.render(stats, BEGIN, END)
    assert 'Held 2/5（40.00%）' in text and '空值行 2 条' in text
    assert '不能据此确认新增实测或真实炉况稳定' in text
    assert '正式风险或稳定等级' in text and '采样覆盖率和新增实测数量未核实' in text
    assert '7（' not in text and 'private-secret' not in text


@pytest.mark.parametrize('bad', ['count_mismatch', 'negative', 'boolean', 'float', 'missing',
    'observed_less_than_count', 'malformed_scope', 'wrong_window', 'missing_expected_window', 'basis',
    'whole_window_false', 'observed_inconsistent', 'extra_label'])
def test_inconsistent_or_mismatched_window_quality_never_becomes_a_whole_window_claim(bad):
    stats = sql_stats()
    summary = quality.from_counts(stats, BEGIN, END)
    if bad == 'count_mismatch': summary['sample_count'] = 6
    if bad == 'negative': summary['counts']['Held'] = -1
    if bad == 'boolean': summary['counts']['Held'] = True
    if bad == 'float': summary['counts']['Held'] = 2.0
    if bad == 'missing': summary['counts'].pop('Unknown')
    if bad == 'malformed_scope': summary['scope'] = 'all_production'
    if bad == 'wrong_window': summary['end_time'] = '2026-01-01T01:00:00'
    if bad == 'basis': summary['basis'] = 'all_samples'
    if bad == 'whole_window_false': summary['whole_window_verified'] = False
    if bad == 'observed_inconsistent': summary['observed_rows'] = 100
    if bad == 'extra_label': summary['counts']['secret-label'] = 0
    if bad == 'observed_less_than_count':
        malformed = sql_stats()
        malformed['observed_rows'] = 1
        assert quality.from_counts(malformed, BEGIN, END) is None
        return
    stats['quality_summary'] = summary
    assert quality.render(stats, None if bad == 'missing_expected_window' else BEGIN, END) == ''


def test_missing_quality_projection_is_not_filled_with_zero_or_good():
    assert quality.from_counts({'count': 4, 'observed_rows': 4}, BEGIN, END) is None
    assert evidence.quality_context({'count': 4, 'quality_summary': None}, BEGIN, END).endswith('端点标记不代表整窗质量。')


def test_returned_sample_distribution_does_not_claim_query_window_complete():
    summary = quality.from_rows([{'quality': 'Held'}, {'quality': 'Good'}, {'quality': 'private-label'}])
    stats = {'count': 3, 'quality_summary': summary}
    text = quality.render(stats, BEGIN, END)
    assert '实际返回数值样本质量' in text and 'Held 1/3（33.33%）' in text
    assert '整窗完整性' in text and '条数上限或派生处理' in text
    assert 'private-label' not in text and not summary['whole_window_verified']


def test_derived_average_does_not_establish_raw_sensor_good_quality():
    summary = quality.from_rows([{'quality': 'DERIVED_AVERAGE'}])
    text = quality.render({'count': 1, 'quality_summary': summary}, BEGIN, END)
    assert 'DERIVED_AVERAGE 1/1（100.00%）' in text
    assert '派生平均标记不证明原始传感器质量' in text


def test_zero_samples_do_not_divide_by_zero_or_claim_stability():
    empty = {'count': 0, 'quality_summary': quality.from_rows([])}
    assert '无样本，未计算比例' in quality.render(empty, BEGIN, END)


def test_boolean_statistics_count_cannot_equal_one_valid_quality_sample():
    stats = {'count': True, 'quality_summary': quality.from_rows([{'quality': 'Held'}])}
    assert quality.render(stats, BEGIN, END) == ''


@pytest.mark.parametrize('column', ['value', 'one_minute_average_value'])
def test_parameterized_sql_projection_keeps_exact_nonnull_denominator(column):
    sql = quality.sql_projection(column)
    assert sql.count(column + ' IS NOT NULL') == 6
    assert "quality::text" in sql and 'quality_unknown_count' in sql
    assert 'LIMIT' not in sql and 'UPDATE' not in sql and 'DELETE' not in sql
    assert sql.startswith(',')


def test_sql_projection_rejects_unknown_or_injected_column():
    with pytest.raises(ValueError): quality.sql_projection('value); DROP TABLE x; --')


def mcp_scope(after=True):
    raw = MCP_BASE.read_bytes()
    text = builder.transform_mcp(raw).decode() if after else raw.decode()
    names = {'statistics_from_rows', 'numeric_row_value', 'population_std', 'query_postgres_statistics'}
    nodes = [n for n in ast.parse(text).body if isinstance(n, ast.FunctionDef) and n.name in names]
    scope = {'Any': Any, 'math': math, 'qa_window_quality': quality,
        'linear_slope_per_min': lambda _: None, 'recent_delta_from_rows': lambda _:None,
        'trend_fields': lambda **kw:{}, 'FURNACE_ID': 'synthetic_fixture'}
    exec(compile(ast.Module(body=nodes, type_ignores=[]), '<actual-MCP-quality>', 'exec'), scope)
    return scope


def test_actual_row_statistics_preserve_numbers_and_limit_quality_to_returned_samples():
    rows = [{'value': 0, 'quality': 'Held'}, {'value': 2, 'quality': 'Good'},
        {'value': None, 'quality': 'Bad'}, {'value': float('nan'), 'quality': 'Bad'}]
    before = mcp_scope(False)['statistics_from_rows'](rows)
    after = mcp_scope(True)['statistics_from_rows'](rows)
    assert before['count'] == after['count'] == 2 and after['avg'] == 1
    assert before['stddev'] == after['stddev'] == 1
    assert {k:v for k,v in after.items() if k != 'quality_summary'} == before
    assert after['quality_summary']['counts']['Held'] == 1
    assert not after['quality_summary']['whole_window_verified']


@pytest.mark.parametrize('engine', ['bf_sensor_postgresql', 'postgresql_compatible'])
def test_actual_postgres_function_keeps_same_window_arguments_and_query_count(engine):
    def run(after):
        calls, scope = [], mcp_scope(after)
        results = iter([sql_stats(), None, None, None, None])
        class Cursor:
            def __enter__(self): return self
            def __exit__(self, *args): pass
            def execute(self, query, args): calls.append((query, args))
            def fetchone(self): return next(results)
        class Connection:
            def __enter__(self): return self
            def __exit__(self, *args): pass
            def cursor(self): return Cursor()
        scope.update(import_psycopg=lambda:(SimpleNamespace(connect=lambda *a,**kw:Connection()), None),
            pg_conninfo=lambda _: 'synthetic_fixture', local_time_text=str,
            recent_window_start=lambda *a:BEGIN, pg_table=lambda *a:'synthetic_fixture.one_minute_average',
            enrich_statistics_trend=lambda stats,*a:stats)
        stats = scope['query_postgres_statistics']({'engine':engine}, 'synthetic_tag', BEGIN, END)
        return stats, calls
    old, before = run(False)
    new, after = run(True)
    assert len(before) == len(after) == 5 and [args for _,args in before] == [args for _,args in after]
    assert 'quality_summary' not in old and new['quality_summary']['whole_window_verified']
    assert new['quality_summary']['counts']['Held'] == 2
    assert 'quality_good_count' in after[0][0] and 'LIMIT' not in after[0][0]
    assert all(query.lstrip().startswith('SELECT') for query,_ in after)


def test_proxy_quality_rendering_passes_actual_window_without_changing_base_guard():
    raw = (ROOT / '.codex_runtime/qa-routing-v29/candidate-r2/ollama_proxy_server.py').read_bytes()
    transformed = builder.transform_proxy(raw)
    tree = ast.parse(transformed)
    functions = {n.name: n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)}
    assert 'quality_context(statistics, item.get("start_time"), item.get("end_time"))' in transformed.decode()
    assert ast.dump(functions['build_ollama_request']) == ast.dump({n.name:n for n in ast.walk(ast.parse(raw)) if isinstance(n,ast.FunctionDef)}['build_ollama_request'])
