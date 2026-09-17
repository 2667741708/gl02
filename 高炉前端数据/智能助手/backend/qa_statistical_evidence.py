"""REQ-QA-STATISTICS-EVIDENCE-20260917: preserve values, units and quality scope."""
from __future__ import annotations

from copy import deepcopy
from datetime import datetime
import math
from typing import Any, Mapping

VERSION = 'qa-statistical-evidence-v1'


def finite(value: Any) -> bool:
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        return False
    try:
        return math.isfinite(value)
    except OverflowError:
        return False


def number(value: Any) -> str:
    """Keep familiar 3 decimals, but never turn a nonzero change into displayed zero."""
    if value is None:
        return '无'
    if not finite(value):
        return '无法判断'
    rounded = f'{float(value):.3f}'.rstrip('0').rstrip('.')
    if value != 0 and float(rounded) == 0:
        return format(value, '.12g')
    return '0' if float(rounded) == 0 else rounded


def valid_count(value: Any) -> bool:
    return bool(finite(value) and value > 0 and int(value) == value)


def unit_contract(variable: Any, object_id: str, fallbacks: Mapping[str, str]) -> dict:
    raw = variable.get('unit') if isinstance(variable, dict) else None
    unit = raw.strip() if isinstance(raw, str) else ''
    if unit:
        return {'unit': unit, 'source': 'tool_metadata', 'disclosure': ''}
    raw = fallbacks.get(object_id)
    unit = raw.strip() if isinstance(raw, str) else ''
    if unit:
        return {'unit': unit, 'source': 'canonical_gl02_contract',
                'disclosure': '单位来源：已登记的GL02规范变量单位合同；原始工具未提供单位字段，未换算原始数值。'}
    return {'unit': '', 'source': 'missing',
            'disclosure': '单位未核实，保留原数值，不用于正式跨量比较。'}


def quality_context(statistics: dict) -> str:
    """Endpoint flags do not establish quality for every sample in the window."""
    labels = {'good': 'Good', 'held': 'Held', 'bad': 'Bad', 'uncertain': 'Uncertain',
              'derived_average': 'DERIVED_AVERAGE'}
    values = []
    for key in ('first', 'last'):
        row = statistics.get(key)
        raw = row.get('quality') if isinstance(row, dict) else None
        if isinstance(raw, str):
            text = labels.get(raw.strip().lower(), '未核实')
        elif finite(raw) and int(raw) == raw:
            text = f'原始标记 {int(raw)}（释义未核实）'
        else:
            text = '未核实'
        values.append(text)
    held = 'Held' in values
    return (f'首样本质量 {values[0]}；末样本质量 {values[1]}；'
            + ('端点含Held标记，不能据此确认新增实测或真实炉况稳定；' if held else '')
            + '窗口内各类质量数量和比例未核实，端点标记不代表整窗质量。')


def prefetch_summary(object_id: str, requested_start: str, requested_end: str, result: Any) -> dict:
    result = result if isinstance(result, dict) else {}
    stats = result.get('statistics')
    stats = deepcopy(stats) if isinstance(stats, dict) else {}
    metadata = result.get('variable')
    metadata = deepcopy(metadata) if isinstance(metadata, dict) else {}
    source = result.get('source')
    source = deepcopy(source) if isinstance(source, dict) else {}
    # Flat keys retain old consumers; the complete typed statistics are separate.
    summary = {**stats, 'ok': result.get('ok') is True, 'tool': 'query_gl02_statistics',
        'variable': object_id, 'variable_metadata': metadata,
        'unit': metadata.get('unit'), 'statistics': stats, 'source': source,
        'start_time': result.get('start_time'), 'end_time': result.get('end_time'),
        'requested_start_time': requested_start, 'requested_end_time': requested_end}
    summary['evidence_valid'] = summary_has_data(summary)
    return summary


def _time(value: Any) -> datetime | None:
    try:
        return datetime.fromisoformat(str(value).replace('Z', '+00:00'))
    except (ValueError, TypeError):
        return None


def summary_has_data(summary: Any) -> bool:
    if not isinstance(summary, dict) or summary.get('ok') is not True:
        return False
    metadata, source = summary.get('variable_metadata'), summary.get('source')
    object_id = summary.get('variable')
    if not isinstance(object_id, str) or not object_id.strip() or not isinstance(metadata, dict) or metadata.get('variable_name') != object_id:
        return False
    if not isinstance(source, dict) or source.get('read_policy') not in (None, 'readonly'):
        return False
    source_name = source.get('profile') or source.get('engine') or source.get('service')
    if not isinstance(source_name, str) or not source_name.strip():
        return False
    begin, end = _time(summary.get('start_time')), _time(summary.get('end_time'))
    expected_begin, expected_end = _time(summary.get('requested_start_time')), _time(summary.get('requested_end_time'))
    if begin is None or end is None or expected_begin is None or expected_end is None:
        return False
    try:
        if end <= begin or begin != expected_begin or end != expected_end:
            return False
    except TypeError:
        return False
    count = summary.get('count')
    return bool(valid_count(count) and
                any(finite(summary.get(key)) for key in ('avg', 'min', 'max')))


def renderer_statistics_ready(item: Any, payload: Any, arguments: Any = None) -> bool:
    """Bind a direct tool result to explicit requested names and the requested window."""
    if not isinstance(item, dict) or not isinstance(payload, dict) or payload.get('ok') is not True:
        return False
    metadata = item.get('variable')
    requested = item.get('requested_variable')
    if not isinstance(metadata, dict) or not isinstance(requested, str) or not requested.strip():
        return False
    canonical = metadata.get('variable_name')
    if not isinstance(canonical, str) or not canonical.strip():
        return False
    names = {canonical}
    for key in ('aliases', 'legacy_variable_names'):
        values = metadata.get(key)
        if isinstance(values, list):
            names.update(value for value in values if isinstance(value, str) and value.strip())
    for key in ('short_name', 'point_id', 'tag_long_name', 'tag'):
        value = metadata.get(key)
        if isinstance(value, str) and value.strip():
            names.add(value)
    if requested not in names:
        return False
    arguments = arguments if isinstance(arguments, Mapping) else {}
    variables = arguments.get('variables', payload.get('variables'))
    if not isinstance(variables, list) or not variables or not all(isinstance(v, str) and v.strip() for v in variables):
        return False
    if requested not in variables:
        return False
    begin = arguments.get('start_time', payload.get('start_time'))
    end = arguments.get('end_time', payload.get('end_time'))
    return summary_has_data(prefetch_summary(canonical, begin, end, item))
