#!/usr/bin/env python3
"""Patch the 8093 page for pSpace live core values and safe history merging."""

from __future__ import annotations

import argparse
import re
from pathlib import Path


SCHEMA = "bf.core-metrics.pspace-live.8093.v1"
MARKER = "REQ-8093-CORE-PSPACE-REALTIME-20260804"
ASSET_NAME = "bf-core-metrics-pspace-live-8093.js"
ASSET_VERSION = "20260804-r1"
SYSTEM_CLOCK_MARKER = "REQ-8093-HEADER-SYSTEM-CLOCK-20260805"


SYSTEM_CLOCK_HEADER = r'''    function Header({ wsStatus, currentTime, diagnosis, dataQuality }) { const [systemTime, setSystemTime] = useState(() => new Date()); useEffect(() => { const tick = () => setSystemTime(new Date()); tick(); const id = window.setInterval(tick, 1000); return () => window.clearInterval(id) }, []); const d = getDiag(diagnosis), missing = (dataQuality?.missing_files?.length || 0) + Object.values(dataQuality?.missing_points_before_fill || {}).reduce((a, b) => a + Number(b || 0), 0); return <header className="topbar branded-topbar"><div className="brand"><div className="brand-title">高炉工艺大模型智能决策系统</div></div><div className="brand-pack"><div className="brand-subtitle">炽穹・高炉炼铁大模型</div><div className="brand-sep"></div><img className="brand-logo steel-logo" src="logo/冀南钢铁集团logo.png" alt="冀南钢铁集团" /><img className="brand-logo ysu-logo" src="logo/燕山大学logo.png" alt="燕山大学" /></div><div className="status-strip"><div className="top-item">当前班次：<span className="top-value">白班</span></div><div className="top-item" title="浏览器所在终端的系统时间">时间：<span className="top-value mono">{fmtTime(systemTime)}</span></div><div className="top-item">总体状态：<span className={`top-value ${sev(d.label)}`}>{d.label === 'normal' ? '正常' : '轻度异常'}</span></div><div className="top-item">数据状态：<span className={`top-value ${wsStatus === 'connected' && !missing ? 'good' : wsStatus === 'connected' ? 'warn' : 'bad'}`}>{wsStatus === 'connected' ? (missing ? '有缺点' : '正常') : '未连接'}</span></div><div className="top-item">当前告警：<span className="top-value bad">{d.label === 'normal' ? 0 : 2}</span></div><div className="top-item" title="PostgreSQL分钟镜像的最新数据时间">分钟数据：<span className="top-value mono">{fmtTime(currentTime, 'hm')}</span></div></div><div className="refresh">↻</div></header> }'''


HISTORY_MERGE_BLOCK = r'''      /* BF_HISTORY_MERGE_TIMESTAMP_PRIMARY_WINS_8093 */
      function historyTimestampKey8093(value) {
        const ms = new Date(value).getTime();
        return Number.isFinite(ms) ? new Date(ms).toISOString() : null;
      }
      function alignedHistorySeries8093(history, key) {
        const timestamps = Array.isArray(history?.timestamps) ? history.timestamps : [];
        const values = history?.[key];
        if (!Array.isArray(values) || values.length !== timestamps.length) return null;
        const series = new Map();
        timestamps.forEach((timestamp, index) => {
          const normalized = historyTimestampKey8093(timestamp);
          if (normalized) series.set(normalized, values[index] ?? null);
        });
        return series;
      }
      function mergeHistoryByTimestamp8093(primary = {}, secondary = {}) {
        const primaryTimes = Array.isArray(primary.timestamps) ? primary.timestamps : [];
        const secondaryTimes = Array.isArray(secondary.timestamps) ? secondary.timestamps : [];
        const timeline = [...new Set([...secondaryTimes, ...primaryTimes].map(historyTimestampKey8093).filter(Boolean))]
          .sort((a, b) => new Date(a) - new Date(b));
        const keys = [...new Set([...Object.keys(secondary), ...Object.keys(primary)])]
          .filter(key => key !== 'timestamps');
        const history = { timestamps: timeline };
        const ignoredIncompleteTrendSeries = [];
        keys.forEach(key => {
          if (key === 'diagnosisHistory') {
            history[key] = Array.isArray(primary[key]) ? primary[key] : (secondary[key] || []);
            return;
          }
          const secondarySeries = alignedHistorySeries8093(secondary, key);
          const primarySeries = alignedHistorySeries8093(primary, key);
          if (!secondarySeries && Array.isArray(secondary[key]) && secondary[key].length) {
            ignoredIncompleteTrendSeries.push(key);
          }
          if (secondarySeries || primarySeries) {
            const merged = new Map(secondarySeries || []);
            (primarySeries || []).forEach((value, timestamp) => merged.set(timestamp, value));
            history[key] = timeline.map(timestamp => merged.has(timestamp) ? merged.get(timestamp) : null);
          } else if (!Array.isArray(primary[key]) && primary[key] !== undefined) {
            history[key] = primary[key];
          } else if (!Array.isArray(secondary[key]) && secondary[key] !== undefined) {
            history[key] = secondary[key];
          }
        });
        return { history, ignoredIncompleteTrendSeries };
      }
      function mergedInitMessage(msg, trend) {
        const merged = mergeHistoryByTimestamp8093(msg.history || {}, trend.history || {});
        const history = merged.history;
        const next = Object.assign({}, msg, {
          history,
          data_quality: Object.assign({}, msg.data_quality || {}, {
            trend_history: trend.data_quality || {},
            trend_source: trend.source,
            trend_server: trend.server,
            trend_interval_seconds: trend.interval_seconds,
            trend_aggregate: trend.aggregate,
            history_merge: {
              schema: 'bf.history.timestamp-merge.8093.v1',
              strategy: 'timestamp_union_8768_primary_wins',
              ignored_incomplete_trend_series: merged.ignoredIncompleteTrendSeries
            }
          })
        });
        if (history.timestamps && history.timestamps.length) {
          next.timestamp = history.timestamps[history.timestamps.length - 1];
        }
        return next;
      }
'''


CORE_HELPERS = r'''    /* REQ-8093-CORE-PSPACE-REALTIME-20260804 */
    const CORE_PSPACE_SCHEMA_8093 = 'bf.core-metrics.pspace-live.8093.v1';
    const CORE_PSPACE_EVENT_8093 = 'bf:core-pspace-live';
    const CORE_PSPACE_STALE_MS_8093 = 12000;
    const CORE_PSPACE_IDS_8093 = CORE_METRIC_ITEMS.map(item => metricItemIds(item)[0]);
    function coreTimestampMs8093(value) { if (!value) return null; const ms = new Date(value).getTime(); return Number.isFinite(ms) ? ms : null }
    function coreAgeMs8093(timestamp, receivedAt, now) { const sourceMs = coreTimestampMs8093(timestamp), basis = sourceMs ?? Number(receivedAt || 0); return basis > 0 ? Math.max(0, now - basis) : Number.POSITIVE_INFINITY }
    function coreAgeText8093(ageMs) { if (!Number.isFinite(ageMs)) return '未知'; const seconds = Math.max(0, Math.round(ageMs / 1000)); if (seconds < 60) return `${seconds}秒`; const minutes = Math.floor(seconds / 60), rest = seconds % 60; return rest ? `${minutes}分${rest}秒` : `${minutes}分` }
    function coreQualityText8093(quality, valid) { const text = String(quality ?? '').trim(); if (!valid) return '异常'; if (!text) return '未传'; if (/good|ok|normal|正常|良好/i.test(text)) return '良好'; return text.length > 6 ? text.slice(0, 6) : text }
    function coreClockText8093(timestamp, mode = 'hms') { return timestamp ? fmtTime(timestamp, mode) : '--' }
    function coreLiveRecord8093(live, id, now) { const record = live?.values?.[id]; if (live?.schema !== CORE_PSPACE_SCHEMA_8093 || !record) return null; const ageMs = Number.isFinite(Number(record.sourceAgeMs ?? record.ageMs)) ? Number(record.sourceAgeMs ?? record.ageMs) : coreAgeMs8093(record.timestamp, record.receivedAt, now), transportAgeMs = Number.isFinite(Number(record.transportAgeMs)) ? Number(record.transportAgeMs) : coreAgeMs8093('', record.receivedAt, now), valid = live?.status === 'connected' && record.valid === true && Number.isFinite(Number(record.value)) && transportAgeMs <= Number(live?.staleAfterMs || CORE_PSPACE_STALE_MS_8093); return { ...record, ageMs, transportAgeMs, valid } }
    function coreMetricCurrent8093(buf, item, live, now = Date.now()) { const ids = metricItemIds(item), records = ids.map(id => coreLiveRecord8093(live, id, now)), digits = ids[0] === 'PI' || ids[0] === 'L' || ids.includes('L_south') ? 2 : 1, useLive = records.length > 0 && records.every(record => record?.valid); if (useLive) { const rawValues = records.map(record => Number(record.value)), timestamp = records.map(record => record.timestamp).filter(Boolean).sort((a, b) => new Date(b) - new Date(a))[0] || live?.lastFrameAt || '', ageMs = Math.max(...records.map(record => record.ageMs)), quality = records.map(record => coreQualityText8093(record.quality, record.valid)).join('/'), value = ids.map((id, index) => displayNum(id, rawValues[index], digits)).join('/'); return { source: 'pspace_realtime', degraded: false, rawValues, value, timestamp, ageMs, ageSeconds: Math.round(ageMs / 1000), quality, metaText: `${coreClockText8093(timestamp, 'hms')}｜${coreAgeText8093(ageMs)}｜${quality}`, title: `pSpace秒级实时；数据时间 ${coreClockText8093(timestamp, 'full')}；年龄 ${coreAgeText8093(ageMs)}；质量 ${quality}` } } const rawValues = ids.map(id => latest(buf, id)), timestamp = buf.timestamps?.[buf.timestamps.length - 1] || '', ageMs = coreAgeMs8093(timestamp, 0, now), badLive = records.some(record => record && !record.valid), quality = badLive ? '实时质量异常' : '质量未传', value = ids.map((id, index) => displayNum(id, rawValues[index], digits)).join('/'); return { source: 'postgres_minute', degraded: true, rawValues, value, timestamp, ageMs, ageSeconds: Number.isFinite(ageMs) ? Math.round(ageMs / 1000) : null, quality, metaText: `镜像 ${coreClockText8093(timestamp, 'hm')}｜${coreAgeText8093(ageMs)}｜${badLive ? '异常' : '未传'}`, title: `已降级为分钟镜像；数据时间 ${coreClockText8093(timestamp, 'full')}；年龄 ${coreAgeText8093(ageMs)}；${quality}` } }
    function coreMetricBaselineEvidence8093(buf, item, current) { return metricItemIds(item).map((id, index) => { const raw = current?.rawValues?.[index], baseline = rollingIqrBaseline(buf, id), deviation = rollingIqrDeviation(buf, id, raw), status = iqrStatus(deviation); return { id, raw, baselineSource: baseline?.source || '', median: baseline?.median ?? null, iqr: baseline?.iqr ?? null, deviation, status: status.level, statusLabel: status.label, statusTone: status.tone } }) }
    function coreMetricPrimaryEvidence8093(evidence) { const valid = (evidence || []).filter(row => Number.isFinite(row?.deviation)); return valid.length ? valid.reduce((a, b) => Math.abs(b.deviation) > Math.abs(a.deviation) ? b : a) : ((evidence || [])[0] || { deviation: null, status: 'unknown', statusLabel: '--', statusTone: '' }) }
    function coreRealtimeSummary8093(live, now) { const valid = CORE_PSPACE_IDS_8093.filter(id => coreLiveRecord8093(live, id, now)?.valid).length, total = CORE_PSPACE_IDS_8093.length, degraded = total - valid, frame = live?.lastFrameAt || ''; if (live?.status === 'connected' && valid === total) return { tone: 'is-live', text: `pSpace秒级实时 ${valid}/${total}｜最新 ${coreClockText8093(frame, 'hms')}` }; if (live?.status === 'connected' && valid > 0) return { tone: 'is-degraded', text: `pSpace实时 ${valid}/${total}；${degraded}项已降级为分钟镜像` }; if (live?.status === 'connecting' || !live) return { tone: 'is-connecting', text: '正在连接pSpace秒级实时流；当前使用分钟镜像' }; return { tone: 'is-degraded', text: '实时流异常，已降级为分钟镜像' } }
    function useCoreMetricRealtime8093() { const initial = window.__BF_CORE_PSPACE_LIVE__?.snapshot?.() || window.__BF_CORE_PSPACE_LIVE__ || null, [live, setLive] = useState(initial), [now, setNow] = useState(Date.now()); useEffect(() => { const update = event => setLive(event?.detail || window.__BF_CORE_PSPACE_LIVE__?.snapshot?.() || window.__BF_CORE_PSPACE_LIVE__ || null); window.addEventListener(CORE_PSPACE_EVENT_8093, update); update(); const timer = window.setInterval(() => setNow(Date.now()), 1000); return () => { window.removeEventListener(CORE_PSPACE_EVENT_8093, update); window.clearInterval(timer) } }, []); return { live, now } }
'''


CORE_ROW = r'''    CoreMetricRow = function BFCoreMetricRowPspaceLive8093({ buf, item, index, onOpen, coreLive, coreNow }) { const ids = metricItemIds(item), key = ids.join('|'), current = coreMetricCurrent8093(buf, item, coreLive, coreNow), evidence = coreMetricBaselineEvidence8093(buf, item, current), primary = coreMetricPrimaryEvidence8093(evidence), z = primary.deviation, st = { level: primary.status, label: primary.statusLabel, tone: primary.statusTone }, transportAgeSeconds = current.source === 'pspace_realtime' ? Math.round(Math.max(...ids.map(id => coreLiveRecord8093(coreLive, id, coreNow)?.transportAgeMs || 0)) / 1000) : '', statusTitle = evidence.every(row => row.median !== null && row.iqr !== null && row.deviation !== null) ? evidence.map(row => `${ROW_BY_ID[row.id]?.name || row.id}独立30日基线：中位数 ${fmtNum(displayValue(row.id, row.median), 2)}，IQR ${fmtNum(displayValue(row.id, row.iqr), 2)}，当前偏离 ${row.deviation >= 0 ? '+' : ''}${fmtNum(row.deviation, 2)} IQR，状态 ${row.statusLabel}`).join('；') : `${metricItemName(item)}：独立30日基线暂不可用`; return <div className={`metric-row core-group-row core-live-row ${current.degraded ? 'is-degraded' : 'is-live'}`} key={key} data-core-metric-id={ids[0]} data-value-source={current.source} data-value-raw={primary.raw ?? ''} data-value-timestamp={current.timestamp} data-value-age-seconds={current.ageSeconds ?? ''} data-transport-age-seconds={transportAgeSeconds} data-value-quality={current.quality} data-baseline-source={primary.baselineSource} data-baseline-median={primary.median ?? ''} data-baseline-iqr={primary.iqr ?? ''} data-baseline-deviation={z ?? ''} data-baseline-status={st.level} data-baseline-evidence={JSON.stringify(evidence)}><div className="metric-no mono">{String(index + 1).padStart(2, '0')}</div><div className="metric-name" title={metricItemName(item)}>{metricItemName(item)}</div><div className="metric-value core-live-value" title={current.title} aria-label={current.title}><span className="core-live-number">{current.value}</span><span className="core-live-meta">{current.metaText}</span></div><div className="metric-status" title={statusTitle} aria-label={statusTitle}><span className={`metric-dot ${st.tone}`}></span>{st.label}</div><CoreMetricSparkButtonV1 buf={buf} item={item} onOpen={onOpen} /></div> }
'''


METRIC_ROWS = r'''    MetricRows = function BFCoreMetricRowsPspaceLive8093({ buf }) { const [page, setPage] = useState(0), [detailItem, setDetailItem] = useState(null), { live: coreLive, now: coreNow } = useCoreMetricRealtime8093(), current = CORE_METRIC_PAGES_V7[page] || CORE_METRIC_PAGES_V7[0], liveSummary = coreRealtimeSummary8093(coreLive, coreNow); let offset = current.startIndex; return <div className="metric-list core-grouped-metrics core-page-v7 core-pspace-live-8093"><div className="core-metric-tabs-v7" role="tablist" aria-label="核心变量分页">{CORE_METRIC_PAGES_V7.map((entry, i) => <button key={entry.title} className={page === i ? 'active' : ''} aria-selected={page === i} onClick={() => setPage(i)}><span>{entry.title}</span></button>)}</div><div className={`core-live-banner ${liveSummary.tone}`} role="status" aria-live="polite">{liveSummary.text}</div><div className="core-page-v7-content">{current.groups.map(group => { const start = offset; offset += group.items.length; return <div className="core-metric-group" key={group.title} style={{ '--rows': String(group.items.length) }}><div className="core-group-title"><span>{group.title}</span></div><div className="core-group-rows">{group.items.map((entry, i) => <CoreMetricRow buf={buf} item={entry} index={start + i} onOpen={setDetailItem} coreLive={coreLive} coreNow={coreNow} key={entry.id || entry.name} />)}</div></div> })}</div>{detailItem && <CoreMetricDetailModalV1 key={metricItemIds(detailItem)[0]} buf={buf} item={detailItem} coreLive={coreLive} coreNow={coreNow} onClose={() => setDetailItem(null)} />}</div> }
'''


STYLE_AND_ASSET = f'''  <!-- {MARKER}: pSpace current values + PostgreSQL minute history -->
  <style id="bf-core-metrics-pspace-live-8093-style">
    .overview-cad-grid .core-grouped-metrics.core-page-v7.core-pspace-live-8093 {{
      grid-template-rows:38px 20px minmax(0,1fr)!important;
      gap:4px!important
    }}
    .core-pspace-live-8093 .core-live-banner {{
      min-height:20px;display:flex;align-items:center;padding:0 8px;border:1px solid rgba(70,142,204,.58);
      border-radius:4px;background:rgba(5,35,66,.78);font:900 10px/1 SimSun,"宋体",serif;white-space:normal
    }}
    .core-pspace-live-8093 .core-live-banner.is-live {{color:#8be6be;border-color:rgba(61,183,130,.7)}}
    .core-pspace-live-8093 .core-live-banner.is-degraded {{color:#ffd27d;border-color:rgba(224,158,48,.78)}}
    .core-pspace-live-8093 .core-live-banner.is-connecting {{color:#a9ccec}}
    .core-pspace-live-8093 .core-page-v7-content {{overflow:auto!important;scrollbar-width:thin}}
    .overview-cad-grid .core-page-v7.core-pspace-live-8093 .core-group-rows {{
      overflow:visible!important;grid-template-rows:repeat(var(--rows),minmax(36px,1fr))!important
    }}
    .overview-cad-grid .core-page-v7.core-pspace-live-8093 .core-group-row {{
      grid-template-columns:24px minmax(82px,1fr) minmax(132px,148px) minmax(64px,84px)!important;
      min-height:36px!important
    }}
    .overview-cad-grid .core-page-v7.core-pspace-live-8093 .core-group-row .metric-status {{display:none!important}}
    .overview-cad-grid .core-page-v7 .core-group-row .metric-value.core-live-value {{
      width:auto!important;min-width:0!important;max-width:none!important;display:flex!important;flex-direction:column;
      align-items:flex-start;justify-content:center;gap:2px;overflow:visible!important;text-overflow:clip!important;line-height:1!important
    }}
    .core-pspace-live-8093 .core-live-number {{display:block;font:900 18px/1 "D-DIN","Bahnschrift",Arial,sans-serif;color:#f7fbff;white-space:nowrap}}
    .core-pspace-live-8093 .core-live-meta {{display:block;font:900 8.5px/1 SimSun,"宋体",serif;color:#7be0b2;white-space:nowrap;letter-spacing:0}}
    .core-pspace-live-8093 .core-live-row.is-degraded .core-live-number {{color:#ffe1a3;text-shadow:0 0 8px rgba(237,166,51,.36)}}
    .core-pspace-live-8093 .core-live-row.is-degraded .core-live-meta {{color:#f0bd64}}
    @container overview-core-panel (min-width:430px) {{
      .overview-cad-grid .core-page-v7.core-pspace-live-8093 .core-group-row {{
        grid-template-columns:28px minmax(96px,1fr) minmax(138px,154px) 56px minmax(76px,110px)!important
      }}
      .overview-cad-grid .core-page-v7.core-pspace-live-8093 .core-group-row .metric-status {{display:flex!important}}
    }}
    @media(max-width:1366px),(max-height:760px) {{
      .overview-cad-grid .core-grouped-metrics.core-page-v7.core-pspace-live-8093 {{grid-template-rows:32px 18px minmax(0,1fr)!important;gap:3px!important}}
      .core-pspace-live-8093 .core-live-banner {{min-height:18px;font-size:8.8px;padding-inline:5px}}
      .overview-cad-grid .core-page-v7.core-pspace-live-8093 .core-group-rows {{grid-template-rows:repeat(var(--rows),minmax(28px,1fr))!important}}
      .overview-cad-grid .core-page-v7.core-pspace-live-8093 .core-group-row {{grid-template-columns:21px minmax(78px,1fr) minmax(112px,126px) minmax(60px,82px)!important;min-height:28px!important}}
      .core-pspace-live-8093 .core-live-number {{font-size:15px}}
      .core-pspace-live-8093 .core-live-meta {{font-size:7.8px}}
    }}
    @media(max-height:680px) {{
      .overview-cad-grid .core-grouped-metrics.core-page-v7.core-pspace-live-8093 {{grid-template-rows:27px 16px minmax(0,1fr)!important}}
      .core-pspace-live-8093 .core-live-banner {{min-height:16px;font-size:8px}}
      .overview-cad-grid .core-page-v7.core-pspace-live-8093 .core-group-rows {{grid-template-rows:repeat(var(--rows),minmax(26px,1fr))!important}}
      .overview-cad-grid .core-page-v7.core-pspace-live-8093 .core-group-row {{grid-template-columns:20px minmax(72px,1fr) minmax(106px,120px) minmax(54px,76px)!important;min-height:26px!important;padding-inline:3px!important}}
      .core-pspace-live-8093 .core-live-number {{font-size:14px}}
      .core-pspace-live-8093 .core-live-meta {{font-size:7.4px}}
    }}
    @media(max-width:760px) {{
      .overview-cad-grid .core-page-v7.core-pspace-live-8093 .core-group-row {{grid-template-columns:20px minmax(78px,1fr) minmax(112px,128px) minmax(60px,1fr)!important}}
    }}
    @media(min-width:761px) and (max-width:1279px) {{
      .overview-cad-grid .core-page-v7.core-pspace-live-8093 .core-group-row {{grid-template-columns:21px minmax(100px,1fr) minmax(112px,126px) 56px minmax(120px,1fr)!important}}
    }}
  </style>
  <script type="module" src="assets/{ASSET_NAME}?v={ASSET_VERSION}"></script>
'''


def replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise ValueError(f"{label}: expected one anchor, found {count}")
    return text.replace(old, new, 1)


def patch_history_merge(text: str) -> str:
    if "BF_HISTORY_MERGE_TIMESTAMP_PRIMARY_WINS_8093" in text:
        return text
    old_signal = "const history = Object.assign({}, msg.history || {}, trend.history || {});"
    if old_signal not in text:
        raise ValueError("history merge: unsafe Object.assign anchor was not found")
    pattern = re.compile(
        r"      function mergedInitMessage\(msg, trend\) \{.*?\n      \}\n(?=      function deliver)",
        re.DOTALL,
    )
    text, count = pattern.subn(HISTORY_MERGE_BLOCK, text, count=1)
    if count != 1:
        raise ValueError(f"history merge: expected one function block, found {count}")
    return text


def patch_core_components(text: str) -> str:
    if "BFCoreMetricRowsPspaceLive8093" in text:
        live_record_line = next(
            line for line in CORE_HELPERS.splitlines() if "function coreLiveRecord8093" in line
        )
        current_line = next(
            line for line in CORE_HELPERS.splitlines() if "function coreMetricCurrent8093" in line
        )
        evidence_line = next(
            line
            for line in CORE_HELPERS.splitlines()
            if "function coreMetricBaselineEvidence8093" in line
        )
        primary_line = next(
            line
            for line in CORE_HELPERS.splitlines()
            if "function coreMetricPrimaryEvidence8093" in line
        )
        text, live_record_count = re.subn(
            r"^    function coreLiveRecord8093\(.*$",
            live_record_line,
            text,
            count=1,
            flags=re.MULTILINE,
        )
        text, current_count = re.subn(
            r"^    function coreMetricCurrent8093\(.*$",
            current_line,
            text,
            count=1,
            flags=re.MULTILINE,
        )
        text, evidence_count = re.subn(
            r"^    function (?:coreMetricDeviationForCurrent8093|coreMetricBaselineEvidence8093)\(.*$",
            evidence_line,
            text,
            count=1,
            flags=re.MULTILINE,
        )
        if evidence_count == 0:
            text = text.replace(current_line, current_line + "\n" + evidence_line, 1)
            evidence_count = 1
        text, primary_count = re.subn(
            r"^    function coreMetricPrimaryEvidence8093\(.*$",
            primary_line,
            text,
            count=1,
            flags=re.MULTILINE,
        )
        if primary_count == 0:
            text = text.replace(evidence_line, evidence_line + "\n" + primary_line, 1)
            primary_count = 1
        text, live_row_count = re.subn(
            r"^    CoreMetricRow = function BFCoreMetricRowPspaceLive8093\(.*$",
            CORE_ROW.rstrip("\n"),
            text,
            count=1,
            flags=re.MULTILINE,
        )
        if (
            live_record_count != 1
            or current_count != 1
            or evidence_count != 1
            or primary_count != 1
            or live_row_count != 1
        ):
            raise ValueError(
                "existing realtime component could not be upgraded "
                f"(record={live_record_count}, current={current_count}, "
                f"evidence={evidence_count}, primary={primary_count}, row={live_row_count})"
            )
        return text

    row_pattern = re.compile(
        r"^    CoreMetricRow = function BFCoreMetricRowDetailV1\(.*$",
        re.MULTILINE,
    )
    text, row_count = row_pattern.subn(CORE_HELPERS + CORE_ROW.rstrip("\n"), text, count=1)
    if row_count != 1:
        raise ValueError(f"core row: expected final detail row once, found {row_count}")

    rows_pattern = re.compile(
        r"^    MetricRows = function BFCoreMetricRowsDetailV1\(.*$",
        re.MULTILINE,
    )
    text, rows_count = rows_pattern.subn(METRIC_ROWS.rstrip("\n"), text, count=1)
    if rows_count != 1:
        raise ValueError(f"metric rows: expected final detail component once, found {rows_count}")

    text = replace_once(
        text,
        "function CoreMetricDetailModalV1({ buf, item, onClose }) {",
        "function CoreMetricDetailModalV1({ buf, item, onClose, coreLive, coreNow }) {",
        "detail modal signature",
    )
    text = replace_once(
        text,
        "hasDelta = Number.isFinite(Number(stats.delta)); const dialog",
        "hasDelta = Number.isFinite(Number(stats.delta)), current = coreMetricCurrent8093(buf, item, coreLive, coreNow); const dialog",
        "detail current-value binding",
    )
    text = replace_once(
        text,
        "<div><span>当前值</span><b>{fmtNum(stats.latest, digits)}{unit}</b></div>",
        "<div className={`core-detail-current ${current.degraded ? 'is-degraded' : 'is-live'}`} title={current.title}><span>当前值 · {current.degraded ? '分钟镜像' : 'pSpace实时'}</span><b>{current.value}{unit}</b><small>{current.metaText}</small></div>",
        "detail current-value display",
    )
    return text


def patch_asset_entry(text: str) -> str:
    if f'id="bf-core-metrics-pspace-live-8093-style"' in text:
        return text
    preferred = "  <!-- REQ-BF3D-8093-FURNACE-BODY-NO-SIM-20260801:"
    if preferred in text:
        return text.replace(preferred, STYLE_AND_ASSET + preferred, 1)
    if "</body>" not in text:
        raise ValueError("asset entry: </body> anchor was not found")
    return text.replace("</body>", STYLE_AND_ASSET + "</body>", 1)


def patch_system_clock(text: str) -> str:
    header_pattern = re.compile(
        r"^    function Header\(\{ wsStatus, currentTime, diagnosis, dataQuality \}\) \{.*$",
        re.MULTILINE,
    )
    text, count = header_pattern.subn(SYSTEM_CLOCK_HEADER, text, count=1)
    if count != 1:
        raise ValueError(f"system clock header: expected one Header function, found {count}")
    if SYSTEM_CLOCK_MARKER not in text:
        text = text.replace(
            SYSTEM_CLOCK_HEADER,
            f"    /* {SYSTEM_CLOCK_MARKER} */\n{SYSTEM_CLOCK_HEADER}",
            1,
        )
    if text.count(SYSTEM_CLOCK_MARKER) != 1:
        raise ValueError("system clock header marker must occur exactly once")
    return text


def patch_page(text: str) -> str:
    patched = patch_history_merge(text)
    patched = patch_core_components(patched)
    patched = patch_asset_entry(patched)
    patched = patch_system_clock(patched)
    if patched.count(MARKER) != 2:
        raise ValueError("final page must contain one JSX marker and one asset marker")
    if patched.count(ASSET_NAME) != 1:
        raise ValueError("final page must load the realtime asset exactly once")
    if "BFCoreMetricRowsPspaceLive8093" not in patched or SCHEMA not in patched:
        raise ValueError("final realtime contract markers are incomplete")
    if (
        "const [systemTime, setSystemTime] = useState(() => new Date())" not in patched
        or "分钟数据：" not in patched
        or "const [displayTime, setDisplayTime] = useState(currentTime)" in patched
    ):
        raise ValueError("final system clock contract is incomplete")
    return patched


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, help="UTF-8 HTML input path")
    parser.add_argument("--output", help="Output path; defaults to in-place")
    args = parser.parse_args()

    source = Path(args.input)
    target = Path(args.output) if args.output else source
    original = source.read_text(encoding="utf-8")
    patched = patch_page(original)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(patched, encoding="utf-8", newline="\n")
    print(
        f"patched={target} changed={patched != original} schema={SCHEMA} "
        f"asset={ASSET_NAME}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
