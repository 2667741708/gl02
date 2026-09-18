"""REQ-QA-WINDOW-QUALITY-20260917: explicit sample-quality scope, no risk grades."""
from __future__ import annotations

from datetime import datetime
from typing import Any

VERSION = 'qa-window-quality-v1'
LABELS = ('Good', 'Held', 'Bad', 'Uncertain', 'DERIVED_AVERAGE', 'Unknown')
FIELDS = dict(zip(LABELS, ('quality_good_count', 'quality_held_count', 'quality_bad_count',
    'quality_uncertain_count', 'quality_derived_count', 'quality_unknown_count')))


def count(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value >= 0


def label(value: Any) -> str:
    normalized = value.strip().lower() if isinstance(value, str) else ''
    return next((name for name in LABELS[:-1] if name.lower() == normalized), 'Unknown')


def sql_projection(column: str) -> str:
    if column not in ('value', 'one_minute_average_value'):
        raise ValueError('Only reviewed statistics value columns are allowed')
    normalized = "LOWER(BTRIM(COALESCE(quality::text, '')))"
    terms = ['COUNT(*) AS observed_rows']
    for name in LABELS[:-1]:
        terms.append(f"COUNT(*) FILTER (WHERE {column} IS NOT NULL AND {normalized} = '{name.lower()}') AS {FIELDS[name]}")
    known = ', '.join("'" + name.lower() + "'" for name in LABELS[:-1])
    terms.append(f"COUNT(*) FILTER (WHERE {column} IS NOT NULL AND {normalized} NOT IN ({known})) AS {FIELDS['Unknown']}")
    return ',\n                   ' + ',\n                   '.join(terms)


def from_counts(statistics: dict, start: str, end: str) -> dict | None:
    total, observed = statistics.get('count'), statistics.get('observed_rows')
    counts = {name: statistics.get(field) for name, field in FIELDS.items()}
    if not count(total) or not count(observed) or observed < total:
        return None
    if not all(count(value) for value in counts.values()) or sum(counts.values()) != total:
        return None
    return {'schema': VERSION, 'scope': 'queried_window', 'whole_window_verified': True,
        'basis': 'non_null_values', 'sample_count': total, 'observed_rows': observed,
        'excluded_rows': observed - total, 'counts': counts, 'start_time': start, 'end_time': end}


def from_rows(rows: list[dict]) -> dict:
    """Caller supplies exactly the numeric rows used by its existing statistics."""
    counts = {name: 0 for name in LABELS}
    for row in rows:
        counts[label(row.get('quality'))] += 1
    return {'schema': VERSION, 'scope': 'returned_samples', 'whole_window_verified': False,
        'basis': 'returned_numeric_rows', 'sample_count': len(rows), 'counts': counts}


def _time(value: Any) -> datetime | None:
    try:
        return datetime.fromisoformat(str(value).replace('Z', '+00:00'))
    except (ValueError, TypeError):
        return None


def render(statistics: dict, expected_start: Any, expected_end: Any) -> str:
    summary = statistics.get('quality_summary')
    if not isinstance(summary, dict) or summary.get('schema') != VERSION:
        return ''
    counts, total = summary.get('counts'), summary.get('sample_count')
    if not isinstance(counts, dict) or set(counts) != set(LABELS) or not count(total) or not count(statistics.get('count')) or total != statistics.get('count'):
        return ''
    if not all(count(value) for value in counts.values()) or sum(counts.values()) != total:
        return ''
    scope = summary.get('scope')
    if scope == 'queried_window':
        if summary.get('whole_window_verified') is not True or summary.get('basis') != 'non_null_values':
            return ''
        observed, excluded = summary.get('observed_rows'), summary.get('excluded_rows')
        if not count(observed) or not count(excluded) or observed != total + excluded:
            return ''
        start, end = _time(expected_start), _time(expected_end)
        if start is None or end is None or _time(summary.get('start_time')) != start or _time(summary.get('end_time')) != end:
            return ''
        try:
            if end <= start:
                return ''
        except TypeError:
            return ''
        prefix = '同一查询窗口的非空数值样本质量'
        limit = f'空值行 {excluded} 条未进入质量比例；采样覆盖率和新增实测数量未核实。'
    elif scope == 'returned_samples':
        if summary.get('whole_window_verified') is not False or summary.get('basis') != 'returned_numeric_rows':
            return ''
        prefix = '实际返回数值样本质量'
        limit = '返回序列可能受条数上限或派生处理影响；整窗完整性、采样覆盖率和新增实测数量未核实。'
    else:
        return ''
    if not total:
        return prefix + '：无样本，未计算比例。' + limit
    distribution = '；'.join(f'{name} {counts[name]}/{total}（{100 * counts[name] / total:.2f}%）' for name in LABELS)
    cautions = []
    if counts['Held']:
        cautions.append('含Held保持值，不能据此确认新增实测或真实炉况稳定。')
    if counts['Bad'] or counts['Uncertain'] or counts['Unknown']:
        cautions.append('含Bad、Uncertain或未知质量，未据此判定正式风险或稳定等级。')
    if counts['DERIVED_AVERAGE']:
        cautions.append('派生平均标记不证明原始传感器质量。')
    return prefix + '：' + distribution + '。' + ''.join(cautions) + limit
