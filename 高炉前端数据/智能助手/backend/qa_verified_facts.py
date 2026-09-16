"""Typed, finite, scoped sensor facts and deterministic comparisons (QAOPT-E02/E04/E05/E06)."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import math
import re
from typing import Any

VERSION = 'qa-verified-facts-v1'


def finite(value: Any) -> bool:
    return not isinstance(value, bool) and isinstance(value, (int, float)) and math.isfinite(value)


def timestamp(value: Any) -> datetime | None:
    try:
        return datetime.fromisoformat(str(value).replace('Z', '+00:00'))
    except (TypeError, ValueError):
        return None


@dataclass(frozen=True)
class EvidenceItem:
    object_id: str
    kind: str
    value: float
    unit: str
    data_time: str
    source: str
    sample_count: int | None = None
    start_time: str | None = None
    end_time: str | None = None
    unit_source: str = 'tool_metadata'


def latest_item(object_id: str, result: dict) -> EvidenceItem | None:
    if not isinstance(result, dict) or result.get('ok') is not True:
        return None
    variable, latest, source = result.get('variable'), result.get('latest'), result.get('source')
    if not all(isinstance(item, dict) for item in (variable, latest, source)):
        return None
    if variable.get('variable_name') != object_id or not finite(latest.get('value')) or timestamp(latest.get('ts')) is None:
        return None
    source_name = source.get('profile') or source.get('engine') or source.get('service')
    if not source_name or source.get('read_policy') not in (None, 'readonly'):
        return None
    unit = str(variable.get('unit') or '').strip()
    unit_source = 'tool_metadata'
    if not unit:
        # Reuse the existing production public-unit contract. Never infer a
        # unit from a value, a display label, or a similar variable name.
        from mcp_host.cross_source_executor import _CANONICAL_UNIT_FALLBACKS
        unit = _CANONICAL_UNIT_FALLBACKS.get(object_id, '')
        unit_source = 'canonical_gl02_contract' if unit else 'missing'
    return EvidenceItem(object_id, 'sensor_latest', float(latest['value']), unit, str(latest['ts']), str(source_name), unit_source=unit_source)


def prefetch_outcome(prefetch: dict, plan: dict) -> dict | None:
    if plan.get('intents') != ['live_data'] or prefetch.get('used') is not True or prefetch.get('kind') not in ('latest', 'multi_latest'):
        return None
    if prefetch['kind'] == 'latest':
        values = {str(prefetch.get('variable')): prefetch.get('latest')}
    else:
        values = prefetch.get('latest_by_variable') or {}
    expected = list(plan.get('entities') or []) or list(values)
    facts = [item for name in expected if (item := latest_item(name, values.get(name))) is not None]
    missing = [name for name in expected if name not in {item.object_id for item in facts}]
    missing_units = [item.object_id for item in facts if not item.unit]
    complete = not missing and not missing_units
    lines = [f'{item.object_id}：最近一次已保存值 {item.value:.6g}{item.unit or "（单位未登记）"}；数据时间 {item.data_time}；来源 {item.source} / readonly。' for item in facts]
    inherited_units = [item.object_id for item in facts if item.unit_source == 'canonical_gl02_contract']
    if inherited_units:
        lines.append('单位来源：' + '、'.join(inherited_units) + '沿用已登记的GL02规范变量单位合同，原始工具未提供单位字段；未换算原始数值。')
    if missing_units:
        lines.append('单位尚未核实的对象：' + '、'.join(missing_units) + '；本次读取未完整完成，未推测单位或用于正式跨量比较。')
    if missing:
        lines.append('未取得有效证据的对象：' + '、'.join(missing) + '。')
    lines.append('这些是上述采集时刻的单点读数，不能据此确认当前无异常、历史趋势、参数匹配或因果关系；未核实生产正常范围。')
    return {'ok': True, 'answer': '\n'.join(lines), 'answer_route': 'verified_prefetch_facts', 'model_request_count': 0,
            'grounding_status': 'verified_facts' if facts else 'no_verified_evidence',
            'completion': {'schema': 'qa-completion-v1', 'terminal_state': 'completed' if complete else 'partial', 'complete': complete, 'requested_objects': expected, 'covered_objects': [item.object_id for item in facts], 'missing_objects': missing, 'missing_unit_objects': missing_units,
                           'unit_sources': {item.object_id: item.unit_source for item in facts}}}


def temperature_comparison(payload: dict, question: str, arguments: dict) -> dict | None:
    if not re.search(r'温差|温度差|分布', question) or not re.search(r'A\s*[-—~到至]\s*D|[Aa][、,， ]+[Bb]', question):
        return None
    expected = ['T_throat_A', 'T_throat_B', 'T_throat_C', 'T_throat_D']
    if set(arguments.get('variables') or []) != set(expected) or arguments.get('query_type') != 'statistics':
        return None
    begin, end = timestamp(arguments.get('start_time')), timestamp(arguments.get('end_time'))
    if begin is None or end is None or end <= begin:
        return {'answer': '温差分析缺少有效的查询时间窗，未计算点间差值。', 'complete': False, 'missing': expected}
    rows = payload.get('items') if isinstance(payload, dict) and payload.get('ok') is True else []
    rows = rows if isinstance(rows, list) else []
    by_name: dict[str, list] = {}
    for row in rows:
        if isinstance(row, dict):
            by_name.setdefault(str(row.get('requested_variable')), []).append(row)
    lines, means, units, missing, warnings = [], {}, set(), [], []
    for name in expected:
        items = by_name.get(name, [])
        result = items[0].get('result', items[0]) if len(items) == 1 else {}
        result = result if isinstance(result, dict) else {}
        stats = result.get('statistics') or {}
        variable, source = result.get('variable') or {}, result.get('source') or {}
        stats = stats if isinstance(stats, dict) else {}
        variable = variable if isinstance(variable, dict) else {}
        source = source if isinstance(source, dict) else {}
        start, finish = timestamp(result.get('start_time')), timestamp(result.get('end_time'))
        count, avg = stats.get('count'), stats.get('avg')
        source_name = source.get('profile') or source.get('engine') or source.get('service')
        valid = result.get('ok') is True and variable.get('variable_name') == name and start == begin and finish == end and bool(source_name) and source.get('read_policy') in (None, 'readonly') and finite(avg) and finite(count) and count > 0 and int(count) == count
        if not valid:
            missing.append(name)
            lines.append(f'{name}：对象、时间窗或统计证据不完整，未纳入比较。')
            continue
        unit = str(variable.get('unit') or '')
        units.add(unit)
        means[name] = float(avg)
        lines.append(f'{name}：窗口均值 {avg:.6g}{unit or "（单位未登记）"}；有效样本 {count}；来源 {source.get("profile") or source.get("engine") or source.get("service") or "已登记只读来源"}。')
        if not unit:
            warnings.append(f'{name}单位未登记')
        if count < max(1, (end - begin).total_seconds() / 60):
            warnings.append(f'{name}样本未覆盖每个预期分钟，未插值')
        if avg == 0 and stats.get('min') == 0 and stats.get('max') == 0:
            warnings.append(f'{name}全零值需要核对测点有效性，未按有效温度或缺失零填充解释')
    comparable = len(means) >= 2 and len(units) == 1 and '' not in units
    if comparable:
        high, low = max(means, key=means.get), min(means, key=means.get)
        lines.insert(0, f'本窗口各点均值的最大差 = {high}均值 − {low}均值 = {means[high] - means[low]:.6g}{next(iter(units))}。')
    else:
        warnings.append('缺点或单位不完整/不一致，未计算正式点间温差')
    lines.insert(0, f'统计时间窗：{arguments["start_time"]} 至 {arguments["end_time"]}。')
    lines.append('；'.join(warnings) + '。' if warnings else '各点统计证据齐全。')
    lines.append('各点窗口均值不是同一时刻对齐后的空间温差；没有经核实的该炉阈值和同时刻有效测点序列，无法判定温差“大/正常/异常”或气流偏行。')
    return {'answer': '\n'.join(lines), 'complete': not missing and comparable and not warnings, 'missing': missing,
            'covered': list(means), 'quality_warnings': warnings, 'formula': 'max(window_point_mean)-min(window_point_mean)' if comparable else None}
