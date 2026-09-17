"""REQ-QA-STATISTICS-EVIDENCE-20260917: preserve values, units and quality scope."""
from __future__ import annotations

from copy import deepcopy
from datetime import datetime
import math
import re
from typing import Any, Mapping
import qa_window_quality

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


def request_matches_variable(metadata: Any, requested: Any) -> bool:
    """Only explicit identifiers bind aliases to an authoritative canonical object."""
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
    return requested in names


def request_unit_contract(variable: Any, requested: Any, fallbacks: Mapping[str, str]) -> dict:
    object_id = variable['variable_name'] if request_matches_variable(variable, requested) else str(requested)
    return unit_contract(variable, object_id, fallbacks)


def sensor_variables(value: Any) -> list[str] | None:
    """Match the sensor tool's list parsing, without accepting non-string schema items."""
    if not isinstance(value, list) or not value or not all(isinstance(item, str) for item in value):
        return None
    result = list(dict.fromkeys(part.strip() for item in value
        for part in re.split(r'[,，、;；\n]+', item) if part.strip()))
    return result if 0 < len(result) <= 80 else None


def renderer_item_shape_ready(item: Any) -> bool:
    if not isinstance(item, dict):
        return False
    for key in ('variable', 'source', 'latest', 'statistics'):
        value = item.get(key)
        if value is not None and not isinstance(value, dict):
            return False
    statistics = item.get('statistics')
    if isinstance(statistics, dict):
        for key in ('first', 'last'):
            value = statistics.get(key)
            if value is not None and not isinstance(value, dict):
                return False
    return True


def quality_context(statistics: dict, expected_start: Any = None, expected_end: Any = None) -> str:
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
    window_quality = qa_window_quality.render(statistics, expected_start, expected_end)
    return (f'首样本质量 {values[0]}；末样本质量 {values[1]}；'
            + ('端点含Held标记，不能据此确认新增实测或真实炉况稳定；' if held else '')
            + (window_quality if window_quality else '窗口内各类质量数量和比例未核实，端点标记不代表整窗质量。'))


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


def renderer_request_ready(item: Any, payload: Any, arguments: Any = None) -> bool:
    """Bind a direct result to explicit request identifiers, without inferring descriptions."""
    if not isinstance(item, dict) or not isinstance(payload, dict) or payload.get('ok') is not True:
        return False
    metadata = item.get('variable')
    requested = item.get('requested_variable')
    if not renderer_item_shape_ready(item) or not request_matches_variable(metadata, requested):
        return False
    arguments = arguments if isinstance(arguments, Mapping) else {}
    variables = sensor_variables(payload.get('variables'))
    if variables is None:
        return False
    if 'variables' in arguments and sensor_variables(arguments['variables']) != variables:
        return False
    if requested not in variables:
        return False
    return True


def renderer_statistics_ready(item: Any, payload: Any, arguments: Any = None) -> bool:
    """Bind a direct tool result to explicit requested names and the requested window."""
    if not renderer_request_ready(item, payload, arguments):
        return False
    canonical = item['variable']['variable_name']
    arguments = arguments if isinstance(arguments, Mapping) else {}
    begin = arguments.get('start_time', payload.get('start_time'))
    end = arguments.get('end_time', payload.get('end_time'))
    return summary_has_data(prefetch_summary(canonical, begin, end, item))


def sample_time(value: Any) -> datetime | None:
    # A date alone is not the timestamp of a sensor observation or collection.
    if not isinstance(value, (str, datetime)) or not re.match(r'^\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}', str(value)):
        return None
    return _time(value)


def latest_result_ready(result: Any, canonical: Any) -> bool:
    if not renderer_item_shape_ready(result) or result.get('ok') is not True:
        return False
    metadata, latest, source = result.get('variable'), result.get('latest'), result.get('source')
    if not all(isinstance(value, dict) for value in (metadata, latest, source)):
        return False
    if not isinstance(canonical, str) or not canonical.strip() or metadata.get('variable_name') != canonical:
        return False
    source_name = source.get('profile') or source.get('engine') or source.get('service')
    return (finite(latest.get('value')) and sample_time(latest.get('ts')) is not None
        and isinstance(source_name, str) and bool(source_name.strip())
        and source.get('read_policy') in (None, 'readonly'))


def renderer_latest_ready(item: Any, payload: Any, arguments: Any = None) -> bool:
    if not renderer_request_ready(item, payload, arguments):
        return False
    if payload.get('query_type') not in ('latest', 'current', 'realtime'):
        return False
    if isinstance(arguments, Mapping) and 'query_type' in arguments and arguments['query_type'] not in ('latest', 'current', 'realtime'):
        return False
    return latest_result_ready(item, item['variable']['variable_name'])


def latest_details(result: dict, unit: str) -> dict:
    """Disclose quality and time provenance; never invent a collection time or aligned mean."""
    latest, source = result['latest'], result['source']
    labels = {'good': 'Good', 'held': 'Held', 'bad': 'Bad', 'uncertain': 'Uncertain',
        'derived_average': 'DERIVED_AVERAGE'}
    raw = latest.get('quality')
    quality = labels.get(raw.strip().lower()) if isinstance(raw, str) else None
    quality_text = quality or (f'原始标记 {int(raw)}（释义未核实）' if finite(raw) and int(raw) == raw else '未核实')
    missing = []
    if not quality: missing.append('quality_meaning')
    if not unit: missing.append('unit')
    collected = latest.get('collected_at')
    collection_text = str(collected) if sample_time(collected) is not None else '未核实'
    if collection_text == '未核实': missing.append('collection_time')
    pspace = source.get('engine') == 'pspace_python_api' or source.get('profile') == 'pspace_243'
    time_label = '接口读取标记时间' if pspace else '工具采集标记时间'
    text = f'质量 {quality_text}；{time_label} {collection_text}；'
    text += '标记时间不等于原传感器物理采样时刻；'
    if source.get('read_policy') is None:
        missing.append('readonly_policy')
        text += '只读策略字段未提供；'
    if quality == 'Held': text += 'Held表示保持值，不能证明新增实测或真实炉况稳定；'
    if quality in ('Bad', 'Uncertain') or not quality:
        text += '质量不足或释义未核实，不用于正式正常或风险等级判断；'
    if quality == 'DERIVED_AVERAGE' or source.get('derived') is True:
        text += '派生均值不是单个物理测点，不证明原组件质量为Good；'
        metadata = result['variable']
        components = latest.get('components')
        expected = {'T_top_A', 'T_top_B', 'T_top_C', 'T_top_D'}
        valid = metadata.get('variable_name') == 'T_top' and isinstance(components, list) and len(components) == 4
        if valid:
            valid = all(isinstance(row, dict) and isinstance(row.get('component'), str)
                and row['component'] in expected and finite(row.get('value')) and sample_time(row.get('ts')) is not None for row in components)
        if valid:
            valid = {row['component'] for row in components} == expected
        if valid:
            times = [sample_time(row['ts']) for row in components]
            valid = all(value == times[0] for value in times) and sample_time(latest.get('ts')) == times[0]
        if valid:
            calculated = sum(row['value'] / 4 for row in components)
            valid = finite(calculated) and math.isclose(calculated, latest['value'], rel_tol=1e-10, abs_tol=1e-12)
        if not valid:
            missing.append('derived_component_alignment')
            text += '四个组件、同一数据时刻和均值复算未共同核实，返回值不能当作同一时刻A-D完整均值；'
        else:
            text += 'A-D四组件同一时刻且均值复算一致；原组件质量与物理采样覆盖仍未核实；'
    text += '以上是已保存的单点或派生值，不能确认此刻无异常、历史趋势或因果关系。'
    return {'text': text, 'missing': missing, 'quality': quality, 'collection_time': collection_text}


def sensor_latest_completion(payload: Any, arguments: Any, fallbacks: Mapping[str, str]) -> dict | None:
    if isinstance(payload, dict) and isinstance(payload.get('result'), dict):
        payload = payload['result']
    if not isinstance(payload, dict) or payload.get('query_type') not in ('latest', 'current', 'realtime'):
        return None
    arguments = arguments if isinstance(arguments, Mapping) else {}
    expected = sensor_variables(arguments.get('variables', payload.get('variables'))) or []
    items = payload.get('items')
    items = items if isinstance(items, list) else []
    covered, missing, fields = [], [], {}
    for name in expected:
        matches = [item for item in items if isinstance(item, dict) and item.get('requested_variable') == name]
        if len(matches) != 1 or not renderer_latest_ready(matches[0], payload, arguments):
            missing.append(name)
            continue
        item = matches[0]
        unit = request_unit_contract(item['variable'], name, fallbacks)['unit']
        detail = latest_details(item, unit)
        covered.append(name)
        if detail['missing']: fields[name] = detail['missing']
    complete = bool(expected) and not missing and not fields
    return {'schema': 'qa-completion-v2', 'terminal_state': 'completed' if complete else 'partial',
        'complete': complete, 'requested_objects': expected, 'covered_objects': covered,
        'missing_objects': missing, 'missing_evidence_fields': fields, 'semantic_review_required': True}
