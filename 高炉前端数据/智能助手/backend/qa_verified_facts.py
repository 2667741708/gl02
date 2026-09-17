"""Typed, finite, scoped sensor facts and deterministic comparisons (QAOPT-E02/E04/E05/E06)."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import math
import re
from typing import Any

VERSION = 'qa-verified-facts-v3-latest-reuse'


def finite(value: Any) -> bool:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return False
    try:
        return math.isfinite(value)
    except OverflowError:
        return False


def cv_contract(statistics: dict, unit: str) -> dict:
    """Guard a descriptive population ratio, without assuming a physical zero."""
    mean = statistics.get('avg')
    stddev = statistics.get('stddev', statistics.get('stddev_pop'))
    if not finite(mean) or not finite(stddev) or stddev < 0:
        return {'value': None, 'reason': '统计输入缺失或无效'}
    if not str(unit or '').strip():
        return {'value': None, 'reason': '单位和零点口径未登记'}
    if str(unit).strip().lower() in {'℃', '°c', '°f', '℉', '摄氏度', '华氏度', 'celsius', 'fahrenheit'}:
        return {'value': None, 'reason': '该温标不是比例尺度，CV不适用；请用标准差与极差描述波动'}
    minimum = statistics.get('min')
    if mean <= 0 or (finite(minimum) and minimum < 0):
        return {'value': None, 'reason': '均值非正或存在负值，CV相对波动口径不适用'}
    scale = max([abs(float(stddev))] + [abs(float(statistics[key]))
                for key in ('min', 'max') if finite(statistics.get(key))])
    if mean <= max(scale, abs(float(mean))) * 1e-12:
        return {'value': None, 'reason': '均值接近数值零，CV对微小变化敏感，不作相对波动比较'}
    value = float(stddev) / float(mean) * 100.0
    if not math.isfinite(value):
        return {'value': None, 'reason': '计算结果不是有限数值'}
    return {'value': value, 'reason': '描述性比值；比例尺度与有效零点未另行核实，不用于正式跨尺度优劣比较'}


def render_cv(statistics: dict, unit: str, number) -> str:
    contract = cv_contract(statistics, unit)
    if contract['value'] is None:
        return 'CV未提供：' + contract['reason'] + '；保留标准差与极差。'
    return ('CV = STDDEV_POP ÷ 均值 × 100% = ' + number(contract['value']) + '%；'
            + contract['reason'] + '。')


def trend_context(statistics: dict, unit_text: str, number) -> str:
    """Name the scope of an upstream two-signal check and compare all scales."""
    if not any(key in statistics for key in ('endpoint_direction', 'regression_direction', 'recent_direction')):
        return ''
    known = {'上升', '下降', '基本持平'}
    directions = [statistics.get(key) for key in
                  ('endpoint_direction', 'regression_direction', 'recent_direction')]
    endpoint, regression, recent = [value if isinstance(value, str) and value in known else '无法判断' for value in directions]
    pair = ('consistent' if endpoint == regression else 'conflicting') if endpoint in known and regression in known else 'insufficient'
    all_scales = ('方向一致' if endpoint == regression == recent else '存在时间尺度差异') if all(value in known for value in (endpoint, regression, recent)) else '部分时间尺度证据不足'
    delta = statistics.get('recent_delta')
    return (f'首末方向 {endpoint}；回归方向 {regression}；最近15分钟方向 {recent}；'
            f'最近15分钟变化量 {number(delta) + unit_text if finite(delta) else "无法判断"}；'
            f'首末与回归一致性 {pair}；全部时间尺度：{all_scales}。')


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
    import qa_statistical_evidence
    if not qa_statistical_evidence.latest_result_ready(result, object_id):
        return None
    from mcp_host.cross_source_executor import _CANONICAL_UNIT_FALLBACKS
    variable, latest, source = result['variable'], result['latest'], result['source']
    source_name = source.get('profile') or source.get('engine') or source.get('service')
    contract = qa_statistical_evidence.unit_contract(variable, object_id, _CANONICAL_UNIT_FALLBACKS)
    return EvidenceItem(object_id, 'sensor_latest', float(latest['value']), contract['unit'], str(latest['ts']), str(source_name), unit_source=contract['source'])


def prefetch_outcome(prefetch: dict, plan: dict) -> dict | None:
    import qa_statistical_evidence
    if plan.get('intents') != ['live_data'] or prefetch.get('used') is not True or prefetch.get('kind') not in ('latest', 'multi_latest'):
        return None
    if prefetch['kind'] == 'latest':
        values = {str(prefetch.get('variable')): prefetch.get('latest')}
    else:
        values = prefetch.get('latest_by_variable') or {}
    values = values if isinstance(values, dict) else {}
    expected = list(plan.get('entities') or []) or list(values)
    facts = [item for name in expected if (item := latest_item(name, values.get(name))) is not None]
    missing = [name for name in expected if name not in {item.object_id for item in facts}]
    missing_units = [item.object_id for item in facts if not item.unit]
    details = {item.object_id: qa_statistical_evidence.latest_details(values[item.object_id], item.unit) for item in facts}
    missing_details = {name: detail['missing'] for name, detail in details.items() if detail['missing']}
    complete = not missing and not missing_units and not missing_details
    lines = [f'{item.object_id}：最近一次已保存值 {qa_statistical_evidence.number(item.value)}{item.unit or "（单位未登记）"}；数据时间 {item.data_time}；来源 {item.source} / {values[item.object_id]["source"].get("read_policy") or "只读策略字段未提供"}。' + details[item.object_id]['text'] for item in facts]
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
                           'unit_sources': {item.object_id: item.unit_source for item in facts},
                           'missing_evidence_fields': missing_details, 'semantic_review_required': True}}


def reusable_latest_read(question: str, prefetch: dict, plan: dict) -> bool:
    """Reuse all requested latest facts; never complete an analysis from points.

    Missing units remain an explicit partial result. A model cannot repair a
    missing physical unit, and the UI enable-tools flag is not a forced tool.
    """
    if (plan.get('intents') != ['live_data'] or plan.get('no_live_lookup')
            or plan.get('unresolved_entities') or plan.get('unresolved_entity_count')):
        return False
    text = str(question or '').split('\n[服务端对话状态：', 1)[0]
    if re.search(r'分析|判断|是否|正常|异常|风险|趋势|走势|变化|波动|稳不稳|高不高|低不低|大不大|温差|差值|分布|梯度|匹配|对比|比较|原理|原因|为什么|解释|含义|作用|功能|是什么|如何|怎么|说明|介绍|建议|历史|最近|过去|今天|今日|昨天|昨日|昨晚|前天|上午|下午|夜里|凌晨|小时|分钟|统计|平均|均值|最高|最低|标准差|极差|画|图|导出|报告|报表|预测|设定|调节|(?:\d{1,2}|[零一二两三四五六七八九十]{1,3})\s*(?:点|时|:)', text):
        return False
    outcome = prefetch_outcome(prefetch, plan)
    if outcome is None:
        return False
    contract = outcome['completion']
    return bool(contract['covered_objects'] and not contract['missing_objects'])


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
