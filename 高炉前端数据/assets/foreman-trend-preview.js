/*
 * 独立工长趋势复刻预览。
 *
 * 对应需求：REQ-FOREMAN-TREND-STANDALONE-PREVIEW-20260805
 * 数据边界：默认只读取现有 WebSocket init/tick；fixture=1 仅用于布局验收并显式标注非生产。
 */
(() => {
  'use strict';

  const REQUIREMENT_ID = 'REQ-FOREMAN-TREND-STANDALONE-PREVIEW-20260805';
  const TREND_GROUP = 'foreman-trend-preview-sync';
  const MAX_POINTS = 720;
  const palette = ['#ff2f9c', '#f3f4ff', '#ff4b3e', '#ffad32', '#ffe22f', '#65d58a', '#ad8cff', '#e64cff', '#69d8ff', '#48f27a', '#f9fbff', '#d49366'];
  const extraPalette = ['#f6a6ff', '#50e3c2', '#f58b4e', '#9bd8ff', '#c5f56d', '#ff7b9b', '#b8a2ff', '#79f0dc', '#ffd36e', '#a5b5c7', '#ff6dce', '#8ef09a'];

  const m = (label, ids, digits, unit, fixture, extra = {}) => ({ label, ids: Array.isArray(ids) ? ids : [ids], digits, unit, fixture, ...extra });

  const FOREMAN_METRIC_COLUMNS = [
    [
      m('东北顶压', ['P_top_gas_B', 'P_top_NE'], 1, 'kPa', 254.5),
      m('东南顶压', ['P_top_gas_A', 'P_top_SE'], 1, 'kPa', 254.1),
      m('西北顶压', ['P_top_gas_C', 'P_top_NW'], 1, 'kPa', 254.9),
      m('西南顶压', ['P_top_gas_D', 'P_top_SW'], 1, 'kPa', 253.9),
      m('雷达探尺', 'L', 2, 'm', 1.43),
      m('北尺', 'L_north', 2, 'm', -0.47),
      m('南尺', 'L_south', 2, 'm', -0.46)
    ],
    [
      m('东北顶温', 'T_top_A', 1, '℃', 106.0),
      m('东南顶温', 'T_top_B', 1, '℃', 104.4),
      m('西北顶温', 'T_top_C', 1, '℃', 106.9),
      m('西南顶温', 'T_top_D', 1, '℃', 107.1),
      m('上小时喷煤量', ['PCI_previous_hour', 'PCI_hour_previous'], 1, 't', 43.4, { derive: 'previous-hour-coal' }),
      m('本小时喷煤量', ['PCI_current_hour', 'PCI_hour_current'], 1, 't', 20.2, { derive: 'current-hour-coal' }),
      m('喷煤实际速率', 'PCI_rate', 2, 't/h', 43.80)
    ],
    [
      m('冷风流量', 'Q_blast', 1, 'Nm³/min', 3031.5),
      m('冷风压力', 'P_blast_cold', 1, 'kPa', 452.8),
      m('热风压力', 'P_blast', 1, 'kPa', 441.7),
      m('热风温度', 'T_blast', 1, '℃', 1248.1),
      m('透气性指数', 'PI', 2, '-', 19.26),
      m('炉腹煤气指数', ['BellyGasIndex', 'belly_gas_index'], 1, '-', 68),
      m('炉腹煤气量', ['Q_belly_gas', 'belly_gas_flow'], 0, 'Nm³/min', 5012)
    ],
    [
      m('全炉压差', 'DP_total', 1, 'kPa', 187.4),
      m('上部压差', 'DP_upper', 1, 'kPa', -0.8),
      m('下部压差', 'DP_lower', 1, 'kPa', 188.1),
      m('下部压差占比', ['DP_lower_ratio'], 1, '%', 100.4, { derive: 'lower-pressure-ratio' }),
      m('综合顶压', 'P_top', 1, 'kPa', 251.9),
      m('荒煤气温度', 'T_top', 1, '℃', 99.3),
      m('外网煤气压力', ['P_gas_network', 'external_gas_pressure'], 1, 'kPa', 15.6)
    ],
    [
      m('煤气利用率', 'GasUtil', 2, '%', 46.80),
      m('一氧化碳', ['CO_top', 'CO'], 1, '%', 25.6),
      m('二氧化碳', ['CO2_top', 'CO2'], 1, '%', 22.5),
      m('氢气', ['H2_top', 'H2'], 1, '%', 4.4),
      m('鼓风动能', ['BlastEnergy', 'blast_energy'], 0, 'kg·m/s', 11362),
      m('标准风速', ['BlastSpeedStd', 'standard_blast_speed'], 0, 'm/s', 253),
      m('实际风速', ['BlastSpeedActual', 'actual_blast_speed'], 0, 'm/s', 263)
    ],
    [
      m('软水流量', ['Q_soft_water', 'soft_water_flow'], 0, 'm³/h', 4503),
      m('软水压力', ['P_soft_water', 'soft_water_pressure'], 2, 'MPa', 0.80),
      m('高压水流量', ['Q_high_pressure_water', 'high_pressure_water_flow'], 0, 'm³/h', 881),
      m('高压水压力', ['P_high_pressure_water', 'high_pressure_water_pressure'], 2, 'MPa', 1.58),
      m('中压水压力', ['P_medium_pressure_water', 'medium_pressure_water_pressure'], 2, 'MPa', 0.82),
      m('膨胀罐液位', ['ExpansionTankLevel', 'expansion_tank_level'], 1, 'm', 3.8),
      m('罐重', 'Hopper_weight', 1, 't', 52.7)
    ],
    [
      m('氮气流量', ['Q_N2', 'nitrogen_flow'], 0, 'Nm³/h', 1311),
      m('氮气压力', ['P_N2', 'nitrogen_pressure'], 1, 'kPa', 609.1),
      m('阀前富氧压力', ['P_O2_valve_in', 'oxygen_valve_in_pressure'], 2, 'MPa', 0.67),
      m('阀后富氧压力', ['P_O2_valve_out', 'oxygen_valve_out_pressure'], 2, 'MPa', 0.49),
      m('富氧流量', 'Q_O2', 0, 'Nm³/h', 19984),
      m('富氧率', 'O2_rate', 3, '%', 7.198),
      m('理论燃烧温度', 'TFT', 0, '℃', 2074)
    ]
  ];

  const MAIN_SERIES = [
    { id: 'P_top', name: '综合顶压', unit: 'kPa', center: 94 },
    { id: 'DP_total', name: '全炉压差', unit: 'kPa', center: 84 },
    { id: 'P_blast', name: '热风压力', unit: 'kPa', center: 77 },
    { id: 'T_blast', name: '热风温度', unit: '℃', center: 69 },
    { id: 'Q_blast', name: '冷风流量', unit: 'Nm³/min', center: 62 },
    { id: 'PCI_rate', name: '喷煤实际速率', unit: 't/h', center: 54 },
    { id: 'GasUtil', name: '煤气利用率', unit: '%', center: 46 },
    { id: 'PI', name: '透气性指数', unit: '-', center: 38 },
    { id: 'T_top', name: '荒煤气温度', unit: '℃', center: 29 },
    { id: 'L', name: '雷达探尺', unit: 'm', center: 21 },
    { id: 'Q_O2', name: '富氧流量', unit: 'Nm³/h', center: 13 },
    { id: 'O2_rate', name: '富氧率', unit: '%', center: 6 }
  ].map((item, index) => ({ ...item, color: palette[index] }));

  const LOWER_SERIES = [
    { id: 'Hopper_weight_set', name: '罐重设定', unit: 't', color: '#df3cff', step: 'end' },
    { id: 'Hopper_weight', name: '罐重', unit: 't', color: '#62eaff' },
    { id: 'L', name: '雷达探尺', unit: 'm', color: '#ffe442' },
    { id: 'L_south', name: '南尺', unit: 'm', color: '#d58b62' },
    { id: 'L_north', name: '北尺', unit: 'm', color: '#f4f7ff' }
  ];

  const PSPACE_EXTRA_SERIES = [
    ...['A', 'B', 'C', 'D', 'E', 'F'].map(sector => ({ id: `P_static_lower_${sector}`, name: `炉身下部静压${sector}`, unit: 'kPa' })),
    ...['A', 'B', 'C', 'D', 'E', 'F'].map(sector => ({ id: `P_static_middle_${sector}`, name: `炉身中部静压${sector}`, unit: 'kPa' })),
    ...['A', 'B', 'C', 'D', 'E', 'F'].map(sector => ({ id: `P_static_upper_${sector}`, name: `炉身上部静压${sector}`, unit: 'kPa' })),
    ...['A', 'B', 'C', 'D'].map(sector => ({ id: `T_throat_${sector}`, name: `炉喉温度${sector}`, unit: '℃' }))
  ];

  const curveCatalog = [];
  const curveById = new Map();
  function registerCurve(item, defaultSelected = false) {
    if (!item?.id || curveById.has(item.id)) return;
    const curve = { ...item, color: item.color || extraPalette[curveCatalog.length % extraPalette.length], defaultSelected };
    curveCatalog.push(curve);
    curveById.set(curve.id, curve);
  }
  MAIN_SERIES.forEach(item => registerCurve(item, true));
  LOWER_SERIES.forEach(item => registerCurve(item, false));
  FOREMAN_METRIC_COLUMNS.flat().forEach(metric => registerCurve({ id: metric.ids[0], name: metric.label, unit: metric.unit }, false));
  registerCurve({ id: 'DP_lower_ratio', name: '下部压差占比', unit: '%' }, false);
  PSPACE_EXTRA_SERIES.forEach(item => registerCurve(item, false));
  const COLOR_BY_ID = Object.fromEntries(curveCatalog.map(item => [item.id, item.color]));
  LOWER_SERIES.forEach(item => { item.color = COLOR_BY_ID[item.id] || item.color; });

  const params = new URLSearchParams(location.search);
  const fixtureMode = params.get('fixture') === '1';
  const displayState = {
    displayMinutes: Number(params.get('minutes') || 120),
    rangeStart: params.get('range_start') || '',
    rangeEnd: params.get('range_end') || '',
    zoom: { start: 0, end: 100 },
    hiddenSeries: new Set(),
    selectedSeries: new Set(MAIN_SERIES.map(item => item.id)),
    cursorEnabled: true
  };
  const buffer = { timestamps: [], series: {} };
  const pspaceState = { status: 'idle', values: {}, lastFrame: '', lastReceivedAt: 0, timer: 0 };
  const historyState = { status: 'idle', lastTimestamp: '' };
  const coalIntegrationState = { current: null, previous: null };
  let mainChart;
  let lowerChart;
  let reconnectTimer;
  let pspaceReconnectTimer;

  const byId = id => document.getElementById(id);
  const sourceState = byId('source-state');
  const systemClock = byId('system-clock');
  const dataClock = byId('data-clock');
  const mainEmpty = byId('main-chart-empty');
  const lowerEmpty = byId('lower-chart-empty');
  const mainStatus = byId('main-toolbar-status');
  const lowerStatus = byId('lower-toolbar-status');
  const seriesKey = byId('series-key');
  const seriesPicker = byId('series-picker');
  const seriesPickerList = byId('series-picker-list');

  function pad(value) {
    return String(value).padStart(2, '0');
  }

  function formatClock(value, withDate = true) {
    const date = value instanceof Date ? value : new Date(value);
    if (!Number.isFinite(date.getTime())) return '--';
    const time = `${pad(date.getHours())}:${pad(date.getMinutes())}:${pad(date.getSeconds())}`;
    return withDate ? `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())} ${time}` : time;
  }

  function setSourceState(text, tone) {
    sourceState.textContent = text;
    sourceState.className = `source-state ${tone}`;
  }

  function finite(value) {
    // Missing values must stay missing. Number(null) and Number('') are zero,
    // which previously made unavailable pSpace points look like real zeros.
    if (value === null || value === undefined || value === '') return null;
    const number = Number(value);
    return Number.isFinite(number) ? number : null;
  }

  const DISPLAY_FRACTION_DIGITS = 2;

  function displayValue(id, value) {
    const numeric = finite(value);
    if (numeric === null) return null;
    return id === 'GasUtil' && Math.abs(numeric) <= 1.5 ? numeric * 100 : numeric;
  }

  function seriesColor(id) {
    return COLOR_BY_ID[id] || extraPalette[Math.abs(String(id).split('').reduce((sum, char) => sum + char.charCodeAt(0), 0)) % extraPalette.length];
  }

  function pspaceValueFor(id) {
    const record = pspaceState.values[id];
    return record && record.value !== null ? finite(record.value) : null;
  }

  function latestMetricValue(id) {
    const live = pspaceValueFor(id);
    return live !== null ? live : latestFor(id);
  }

  function latestMetricTimestamp(id) {
    const record = pspaceState.values[id];
    return record?.timestamp || buffer.timestamps[buffer.timestamps.length - 1] || '';
  }

  function latestFor(id) {
    const values = buffer.series[id] || [];
    for (let index = values.length - 1; index >= 0; index -= 1) {
      const value = finite(values[index]);
      if (value !== null) return value;
    }
    return null;
  }

  function latestForAliases(ids) {
    for (const id of ids) {
      const value = latestMetricValue(id);
      if (value !== null) return value;
    }
    return null;
  }

  function integrateCoalWindow(startMs, endMs) {
    const values = buffer.series.PCI_rate || [];
    const result = globalThis.BF_FOREMAN_COAL_MATH?.integrateRateSeries(
      buffer.timestamps,
      values,
      startMs,
      endMs
    );
    return result || { amount: null, coveredMs: 0, coverageRatio: 0, sampleCount: 0 };
  }

  function derivedMetric(metric) {
    if (metric.derive === 'lower-pressure-ratio') {
      const lower = latestMetricValue('DP_lower');
      const total = latestMetricValue('DP_total');
      return lower !== null && total !== null && Math.abs(total) > 1e-9 ? lower / total * 100 : null;
    }
    const latestTimestamp = buffer.timestamps[buffer.timestamps.length - 1];
    const latestDate = latestTimestamp ? new Date(latestTimestamp) : null;
    if (!latestDate || !Number.isFinite(latestDate.getTime())) return null;
    const hourStart = new Date(latestDate);
    hourStart.setMinutes(0, 0, 0);
    if (metric.derive === 'current-hour-coal') {
      coalIntegrationState.current = integrateCoalWindow(hourStart.getTime(), latestDate.getTime() + 1);
      return coalIntegrationState.current.amount;
    }
    if (metric.derive === 'previous-hour-coal') {
      coalIntegrationState.previous = integrateCoalWindow(hourStart.getTime() - 3600000, hourStart.getTime());
      return coalIntegrationState.previous.amount;
    }
    return null;
  }

  function metricValue(metric) {
    const direct = latestForAliases(metric.ids);
    return direct !== null ? direct : derivedMetric(metric);
  }

  function metricSource(metric) {
    if (metric.ids.some(id => pspaceValueFor(id) !== null)) return 'pspace';
    if (metric.derive === 'lower-pressure-ratio' && pspaceValueFor('DP_lower') !== null && pspaceValueFor('DP_total') !== null) return 'pspace-derived';
    if (metric.ids.some(id => latestFor(id) !== null)) return 'minute';
    if (['current-hour-coal', 'previous-hour-coal'].includes(metric.derive) && derivedMetric(metric) !== null) return 'minute-derived';
    return '';
  }

  function formatMetric(metric, value) {
    if (value === null) return '--';
    const normalized = displayValue(metric.ids.includes('GasUtil') ? 'GasUtil' : metric.ids[0], value);
    return normalized.toLocaleString('zh-CN', {
      minimumFractionDigits: DISPLAY_FRACTION_DIGITS,
      maximumFractionDigits: DISPLAY_FRACTION_DIGITS
    });
  }

  function buildMetricMatrix() {
    const root = byId('metric-matrix');
    const fragment = document.createDocumentFragment();
    FOREMAN_METRIC_COLUMNS.forEach(column => {
      const columnElement = document.createElement('div');
      columnElement.className = 'metric-column';
      column.forEach(metric => {
        const cell = document.createElement('div');
        cell.className = 'metric-cell is-missing';
        cell.dataset.metric = metric.ids[0];
        cell.title = `${metric.label}${metric.unit ? `（${metric.unit}）` : ''}`;
        const label = document.createElement('span');
        label.className = 'metric-label';
        label.textContent = metric.label;
        const value = document.createElement('span');
        value.className = 'metric-value';
        value.textContent = '--';
        cell.append(label, value);
        columnElement.appendChild(cell);
        metric.element = cell;
        metric.valueElement = value;
      });
      fragment.appendChild(columnElement);
    });
    root.appendChild(fragment);
  }

  function renderMetrics() {
    FOREMAN_METRIC_COLUMNS.flat().forEach(metric => {
      const value = metricValue(metric);
      const source = metricSource(metric);
      const color = seriesColor(metric.ids[0]);
      metric.valueElement.textContent = formatMetric(metric, value);
      metric.element.classList.toggle('is-missing', value === null);
      metric.element.dataset.state = value === null ? 'missing' : 'value';
      metric.element.dataset.source = source || 'unavailable';
      metric.element.style.setProperty('--metric-series-color', color);
      metric.valueElement.style.color = value === null ? '#ffd265' : color;
      metric.valueElement.title = source === 'pspace' || source === 'pspace-derived'
        ? `pSpace 秒级实时${pspaceState.values[metric.ids[0]]?.quality ? `，质量：${pspaceState.values[metric.ids[0]].quality}` : ''}`
        : source === 'minute-derived' ? '喷煤实际速率按真实时间间隔积分' : source === 'minute' ? 'PostgreSQL 1分钟镜像' : '当前实时合同未返回该点位';
      metric.element.title = value === null
        ? `${metric.label}：当前 pSpace/分钟实时合同均未返回该点位`
        : `${metric.label}：${formatMetric(metric, value)}${metric.unit ? ` ${metric.unit}` : ''}｜数据源：${source === 'pspace-derived' ? 'pSpace派生' : source === 'pspace' ? 'pSpace秒级' : source === 'minute-derived' ? '喷煤速率时间积分' : 'PostgreSQL分钟镜像'}`;
    });
    const ratio = FOREMAN_METRIC_COLUMNS.flat().find(metric => metric.derive === 'lower-pressure-ratio');
    const formula = byId('ratio-formula');
    if (formula && ratio) {
      const lower = latestMetricValue('DP_lower');
      const total = latestMetricValue('DP_total');
      formula.textContent = lower !== null && total !== null
        ? `下部压差占比 = ${formatMetric({ ids: ['DP_lower'], digits: 1 }, lower)} ÷ ${formatMetric({ ids: ['DP_total'], digits: 1 }, total)} × 100% = ${formatMetric(ratio, metricValue(ratio))}%`
        : '下部压差占比 = 下部压差 ÷ 全炉压差 × 100%';
    }
  }

  function median(values) {
    if (!values.length) return 0;
    const ordered = [...values].sort((a, b) => a - b);
    const middle = Math.floor(ordered.length / 2);
    return ordered.length % 2 ? ordered[middle] : (ordered[middle - 1] + ordered[middle]) / 2;
  }

  function quantile(values, probability) {
    if (!values.length) return 0;
    const ordered = [...values].sort((a, b) => a - b);
    const position = (ordered.length - 1) * probability;
    const lower = Math.floor(position);
    const upper = Math.ceil(position);
    if (lower === upper) return ordered[lower];
    return ordered[lower] * (upper - position) + ordered[upper] * (position - lower);
  }

  function seriesValues(id) {
    if (id === 'DP_lower_ratio') {
      const lower = buffer.series.DP_lower || [];
      const total = buffer.series.DP_total || [];
      return buffer.timestamps.map((_, index) => {
        const lowerValue = finite(lower[index]);
        const totalValue = finite(total[index]);
        return lowerValue !== null && totalValue !== null && Math.abs(totalValue) > 1e-9 ? lowerValue / totalValue * 100 : null;
      });
    }
    const direct = buffer.series[id];
    if (Array.isArray(direct)) return direct.map(value => displayValue(id, value));
    const metric = FOREMAN_METRIC_COLUMNS.flat().find(item => item.ids.includes(id));
    if (metric) {
      for (const alias of metric.ids) {
        if (Array.isArray(buffer.series[alias])) return buffer.series[alias].map(value => displayValue(id, value));
      }
    }
    return [];
  }

  function windowSlice(id) {
    const allTimes = buffer.timestamps;
    const allValues = seriesValues(id);
    if (displayState.rangeStart && displayState.rangeEnd) {
      const startMs = new Date(displayState.rangeStart).getTime();
      const endMs = new Date(displayState.rangeEnd).getTime();
      if (Number.isFinite(startMs) && Number.isFinite(endMs) && endMs > startMs) {
        const indexes = allTimes.map((timestamp, index) => ({ index, time: new Date(timestamp).getTime() }))
          .filter(item => Number.isFinite(item.time) && item.time >= startMs && item.time <= endMs);
        return { times: indexes.map(item => allTimes[item.index]), values: indexes.map(item => allValues[item.index]) };
      }
    }
    const end = allTimes.length;
    const start = Math.max(0, end - displayState.displayMinutes);
    return { times: allTimes.slice(start), values: allValues.slice(start, end) };
  }

  function laneData(item, center = item.center, amplitude = 3.6) {
    const { times, values } = windowSlice(item.id);
    const valid = values.map(finite).filter(value => value !== null);
    const centerValue = median(valid);
    const q10 = quantile(valid, .1);
    const q90 = quantile(valid, .9);
    const scale = Math.max(Math.abs(q90 - q10), Math.abs(centerValue) * .008, .0001);
    return times.map((timestamp, index) => {
      const raw = finite(values[index]);
      if (raw === null) return [timestamp, null, null];
      const deviation = Math.max(-1.7, Math.min(1.7, (raw - centerValue) / scale));
      return [timestamp, center + deviation * amplitude, raw];
    });
  }

  function normalizedData(item) {
    const { times, values } = windowSlice(item.id);
    const valid = values.map(finite).filter(value => value !== null);
    const minimum = valid.length ? Math.min(...valid) : 0;
    const maximum = valid.length ? Math.max(...valid) : 1;
    const span = Math.max(maximum - minimum, Math.abs(maximum || minimum || 1) * .02, .0001);
    return times.map((timestamp, index) => {
      const raw = finite(values[index]);
      return [timestamp, raw === null ? null : 7 + (raw - minimum) / span * 86, raw];
    });
  }

  function tooltipFormatter(parameters) {
    const rows = (parameters || []).filter(parameter => parameter.value && finite(parameter.value[2]) !== null);
    if (!rows.length) return '';
    const time = formatClock(rows[0].value[0]);
    const content = rows.map(row => {
      const item = curveCatalog.find(series => series.name === row.seriesName);
      const raw = finite(row.value[2]);
      return `${row.marker}${row.seriesName}：<b>${raw.toLocaleString('zh-CN', {
        minimumFractionDigits: DISPLAY_FRACTION_DIGITS,
        maximumFractionDigits: DISPLAY_FRACTION_DIGITS
      })}</b>${item?.unit ? ` ${item.unit}` : ''}`;
    });
    return `${time}<br>${content.join('<br>')}`;
  }

  function commonChartOption(bottom = 46) {
    return {
      backgroundColor: '#24252f',
      animation: false,
      grid: { left: 44, right: 10, top: 8, bottom },
      legend: { show: false },
      tooltip: {
        trigger: 'axis',
        confine: true,
        backgroundColor: 'rgba(15,16,23,.96)',
        borderColor: '#717887',
        textStyle: { color: '#f6f7fb', fontFamily: 'SimSun, 宋体, serif', fontSize: 12 },
        axisPointer: { type: displayState.cursorEnabled ? 'cross' : 'line', lineStyle: { color: '#dde5ee', width: 1 } },
        formatter: tooltipFormatter
      },
      xAxis: {
        type: 'time',
        boundaryGap: false,
        axisLine: { show: true, lineStyle: { color: '#e4e4e7', width: 1 } },
        axisTick: { show: true, lineStyle: { color: '#c8c9cf' } },
        axisLabel: {
          color: '#f3f4f8',
          fontFamily: 'Bahnschrift, Arial Narrow, monospace',
          fontSize: 9,
          lineHeight: 11,
          hideOverlap: true,
          formatter(value) {
            const date = new Date(value);
            return `${formatClock(date, false)}\n${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}`;
          }
        },
        splitLine: { show: false }
      },
      yAxis: {
        type: 'value',
        min: 0,
        max: 100,
        interval: 10,
        axisLine: { show: true, lineStyle: { color: '#d7d8dd' } },
        axisTick: { show: true, lineStyle: { color: '#d7d8dd' } },
        axisLabel: { color: '#f0f1f5', fontSize: 9 },
        splitLine: { show: false }
      },
      dataZoom: [{ type: 'inside', start: displayState.zoom.start, end: displayState.zoom.end, filterMode: 'none', zoomOnMouseWheel: true, moveOnMouseMove: true }]
    };
  }

  function mainOption() {
    const option = commonChartOption(46);
    const selected = curveCatalog.filter(item => displayState.selectedSeries.has(item.id));
    const centers = selected.length > 1 ? selected.map((_, index) => 94 - (index * 88 / (selected.length - 1))) : [50];
    option.series = selected.map((item, index) => ({
      id: item.id,
      name: item.name,
      unit: item.unit,
      type: 'line',
      showSymbol: false,
      connectNulls: true,
      smooth: .16,
      sampling: 'lttb',
      silent: displayState.hiddenSeries.has(item.id),
      lineStyle: { color: seriesColor(item.id), width: displayState.hiddenSeries.has(item.id) ? 0 : 2.25, opacity: displayState.hiddenSeries.has(item.id) ? 0 : 1 },
      emphasis: { disabled: displayState.hiddenSeries.has(item.id), lineStyle: { width: 3.2 } },
      data: displayState.hiddenSeries.has(item.id) ? [] : laneData(item, item.defaultSelected && selected.length === MAIN_SERIES.length ? item.center : centers[index])
    }));
    return option;
  }

  function lowerOption() {
    const option = commonChartOption(42);
    option.yAxis.axisLabel.color = '#62eaff';
    option.xAxis.axisLabel.color = '#62eaff';
    option.series = LOWER_SERIES.map(item => ({
      id: item.id,
      name: item.name,
      unit: item.unit,
      type: 'line',
      step: item.step,
      showSymbol: false,
      connectNulls: true,
      smooth: false,
      sampling: 'lttb',
      lineStyle: { color: item.color, width: 2.15 },
      data: normalizedData(item)
    }));
    return option;
  }

  function hasMainData() {
    return buffer.timestamps.length > 1 && curveCatalog.some(item => displayState.selectedSeries.has(item.id) && seriesValues(item.id).some(value => finite(value) !== null));
  }

  function hasLowerData() {
    return buffer.timestamps.length > 1 && LOWER_SERIES.some(item => (buffer.series[item.id] || []).some(value => finite(value) !== null));
  }

  function updateCharts() {
    const mainReady = hasMainData();
    const lowerReady = hasLowerData();
    mainEmpty.hidden = mainReady;
    lowerEmpty.hidden = lowerReady;
    mainStatus.textContent = mainReady ? `${displayState.displayMinutes}分钟 · ${Math.min(displayState.displayMinutes, buffer.timestamps.length)}点 · 已选${displayState.selectedSeries.size}条 · pSpace当前值优先` : '等待趋势数据';
    lowerStatus.textContent = lowerReady ? `${displayState.displayMinutes}分钟 · 上下图时间轴联动` : '等待周期数据';
    mainChart.setOption(mainOption(), true);
    lowerChart.setOption(lowerOption(), true);
  }

  function renderAll() {
    renderMetrics();
    const latestTimestamp = buffer.timestamps[buffer.timestamps.length - 1];
    initializeRangeInputs();
    dataClock.textContent = latestTimestamp ? `数据时间 ${formatClock(latestTimestamp)}` : '数据时间 --';
    updateCharts();
  }

  function alignSeries(history) {
    const timestamps = Array.isArray(history?.timestamps) ? history.timestamps : [];
    buffer.timestamps = timestamps.slice(-MAX_POINTS);
    buffer.series = {};
    Object.entries(history || {}).forEach(([key, values]) => {
      if (key !== 'timestamps' && Array.isArray(values)) {
        buffer.series[key] = values.slice(-buffer.timestamps.length);
      }
    });
    historyState.lastTimestamp = buffer.timestamps[buffer.timestamps.length - 1] || '';
  }

  function appendTick(message, source = 'minute') {
    if (!message.timestamp) return;
    const timestamp = message.timestamp;
    const lastIndex = buffer.timestamps.length - 1;
    const isNewTimestamp = !buffer.timestamps.length || new Date(timestamp).getTime() > new Date(buffer.timestamps[lastIndex]).getTime();
    if (isNewTimestamp) buffer.timestamps.push(timestamp);
    const ids = new Set([...Object.keys(buffer.series), ...FOREMAN_METRIC_COLUMNS.flat().flatMap(metric => metric.ids), ...MAIN_SERIES.map(item => item.id), ...LOWER_SERIES.map(item => item.id)]);
    ids.forEach(id => {
      const series = buffer.series[id] || (buffer.series[id] = Array(Math.max(0, buffer.timestamps.length - (isNewTimestamp ? 1 : 0))).fill(null));
      if (isNewTimestamp) series.push(message.values?.[id] ?? null);
      else if (Object.prototype.hasOwnProperty.call(message.values || {}, id)) series[lastIndex] = message.values[id];
      if (series.length > MAX_POINTS) series.shift();
    });
    if (buffer.timestamps.length > MAX_POINTS) buffer.timestamps.shift();
    if (source === 'minute') historyState.lastTimestamp = timestamp;
  }

  function applyPspaceFrame(message) {
    if (!message || !['init', 'tick'].includes(message.type)) return;
    const values = message.type === 'init' ? message.history : message.values;
    if (!values || typeof values !== 'object') return;
    const pointMeta = message.point_meta || {};
    const timestamp = message.timestamp || Object.values(pointMeta).map(meta => meta?.timestamp).filter(Boolean).sort().pop() || '';
    let touched = 0;
    Object.entries(values).forEach(([id, raw]) => {
      const value = message.type === 'init' && Array.isArray(raw) ? raw.filter(item => finite(item) !== null).pop() : finite(raw);
      if (value === null) return;
      const meta = pointMeta[id] || {};
      pspaceState.values[id] = {
        value,
        timestamp: meta.timestamp || timestamp,
        quality: meta.quality || '',
        error: meta.error || '',
        receivedAt: Date.now()
      };
      touched += 1;
    });
    if (!touched) return;
    pspaceState.status = 'live';
    pspaceState.lastFrame = timestamp || new Date().toISOString();
    pspaceState.lastReceivedAt = Date.now();
    updateSourceState();
    renderAll();
  }

  function fixtureWave(base, amplitude, index, phase = 0, stepAt = 115, stepValue = 0) {
    const slow = Math.sin((index + phase) / 18) * amplitude;
    const fast = Math.sin((index + phase) / 3.7) * amplitude * .22;
    const noise = Math.sin((index * 17 + phase * 11) / 5.3) * amplitude * .13;
    return base + slow + fast + noise + (index >= stepAt ? stepValue : 0);
  }

  function buildFixture() {
    const now = new Date();
    now.setSeconds(0, 0);
    const count = 241;
    buffer.timestamps = Array.from({ length: count }, (_, index) => new Date(now.getTime() - (count - index - 1) * 60000).toISOString());
    buffer.series = {};
    FOREMAN_METRIC_COLUMNS.flat().forEach((metric, metricIndex) => {
      const id = metric.ids[0];
      if (metric.derive) return;
      const amplitude = Math.max(Math.abs(metric.fixture) * .004, metric.digits >= 2 ? .025 : .5);
      buffer.series[id] = buffer.timestamps.map((_, index) => fixtureWave(metric.fixture, amplitude, index, metricIndex * 2.3, 154 - metricIndex % 5, amplitude * (metricIndex % 2 ? -.8 : 1.2)));
    });
    const cycleValue = (index, plateau) => {
      const cycle = index % 31;
      if (cycle < 4) return cycle / 4 * plateau;
      if (cycle < 15) return plateau;
      if (cycle < 23) return plateau * (1 - (cycle - 15) / 8);
      return 0;
    };
    buffer.series.Hopper_weight_set = buffer.timestamps.map((_, index) => cycleValue(index, 56 + Math.sin(index / 35) * 8));
    buffer.series.Hopper_weight = buffer.timestamps.map((_, index) => Math.max(0, cycleValue(index - 2, 48 + Math.sin(index / 28) * 6) + Math.sin(index / 2) * .7));
    buffer.series.L = buffer.timestamps.map((_, index) => 1.32 + Math.sin(index / 50) * .26 - cycleValue(index - 5, .34));
    buffer.series.L_south = buffer.timestamps.map((_, index) => -.42 + Math.sin(index / 17) * .09 - cycleValue(index - 3, .12));
    buffer.series.L_north = buffer.timestamps.map((_, index) => -.46 + Math.cos(index / 19) * .08 - cycleValue(index - 1, .1));
    const aliases = {
      P_top: [251.9, 2.2, 1.8], DP_total: [187.4, 3.4, -2.4], P_blast: [441.7, 5.2, 4.6], T_blast: [1248.1, 14, 9],
      Q_blast: [3031.5, 55, 95], PCI_rate: [43.8, 5.8, -2.4], GasUtil: [46.8, 1.1, 1.2], PI: [19.26, .75, -.5],
      T_top: [99.3, 7.8, 5.4], Q_O2: [19984, 660, 320], O2_rate: [7.198, .38, .22]
    };
    Object.entries(aliases).forEach(([id, [base, amplitude, step]]) => {
      buffer.series[id] = buffer.timestamps.map((_, index) => fixtureWave(base, amplitude, index, id.length * 4, 156, step));
    });
  }

  function updateSourceState() {
    const historyLive = historyState.status === 'live';
    const pspaceLive = pspaceState.status === 'live';
    document.documentElement.dataset.foremanHistoryStatus = historyState.status;
    document.documentElement.dataset.foremanPspaceStatus = pspaceState.status;
    document.documentElement.dataset.foremanPspaceLastFrame = pspaceState.lastFrame || '';
    if (fixtureMode) return;
    if (historyLive && pspaceLive) setSourceState('pSpace秒级已连接 · 分钟历史已连接', 'is-live');
    else if (historyLive) setSourceState('分钟历史已连接 · pSpace等待', 'is-degraded');
    else if (pspaceLive) setSourceState('pSpace秒级已连接 · 分钟历史等待', 'is-live');
    else if (historyState.status === 'connecting' || pspaceState.status === 'connecting') setSourceState('实时数据连接中', 'is-connecting');
    else setSourceState('实时数据暂不可用', 'is-offline');
  }

  function connectWebSocket() {
    const host = params.get('ws_host') || location.hostname || '127.0.0.1';
    const port = params.get('ws_port') || '8767';
    const scheme = location.protocol === 'https:' ? 'wss' : 'ws';
    const url = params.get('ws_url') || `${scheme}://${host}:${port}`;
    historyState.status = 'connecting';
    updateSourceState();
    let socket;
    try {
      socket = new WebSocket(url);
    } catch (error) {
      historyState.status = 'offline';
      updateSourceState();
      reconnectTimer = window.setTimeout(connectWebSocket, 3000);
      return;
    }
    socket.addEventListener('open', () => {
      historyState.status = 'live';
      updateSourceState();
    });
    socket.addEventListener('message', event => {
      try {
        const message = JSON.parse(event.data);
        if (message.type === 'init') alignSeries(message.history || {});
        if (message.type === 'tick') appendTick(message, 'minute');
        if (message.type === 'init' || message.type === 'tick') renderAll();
      } catch (error) {
        console.error(`${REQUIREMENT_ID}: invalid websocket payload`, error);
      }
    });
    socket.addEventListener('close', () => {
      historyState.status = 'offline';
      updateSourceState();
      reconnectTimer = window.setTimeout(connectWebSocket, 3000);
    });
    socket.addEventListener('error', () => {
      historyState.status = 'offline';
      updateSourceState();
    });
  }

  function connectPspaceWebSocket() {
    if (params.get('pspace_ws_disabled') === '1') return;
    const host = params.get('pspace_ws_host') || location.hostname || '127.0.0.1';
    const port = params.get('pspace_ws_port') || '8770';
    const scheme = location.protocol === 'https:' ? 'wss' : 'ws';
    const url = params.get('pspace_ws_url') || `${scheme}://${host}:${port}`;
    pspaceState.status = 'connecting';
    updateSourceState();
    let socket;
    try {
      socket = new WebSocket(url);
    } catch (error) {
      pspaceState.status = 'offline';
      updateSourceState();
      pspaceReconnectTimer = window.setTimeout(connectPspaceWebSocket, 5000);
      return;
    }
    socket.addEventListener('open', () => {
      pspaceState.status = 'live';
      updateSourceState();
    });
    socket.addEventListener('message', event => {
      try { applyPspaceFrame(JSON.parse(event.data)); }
      catch (error) { console.error(`${REQUIREMENT_ID}: invalid pSpace websocket payload`, error); }
    });
    socket.addEventListener('close', () => {
      pspaceState.status = 'offline';
      updateSourceState();
      pspaceReconnectTimer = window.setTimeout(connectPspaceWebSocket, 5000);
    });
    socket.addEventListener('error', () => {
      pspaceState.status = 'offline';
      updateSourceState();
    });
  }

  function dispatchZoom() {
    [mainChart, lowerChart].forEach(chart => chart.dispatchAction({ type: 'dataZoom', start: displayState.zoom.start, end: displayState.zoom.end }));
  }

  function zoom(factor) {
    const center = (displayState.zoom.start + displayState.zoom.end) / 2;
    const width = Math.max(8, Math.min(100, (displayState.zoom.end - displayState.zoom.start) * factor));
    displayState.zoom.start = Math.max(0, center - width / 2);
    displayState.zoom.end = Math.min(100, center + width / 2);
    if (displayState.zoom.start === 0) displayState.zoom.end = width;
    if (displayState.zoom.end === 100) displayState.zoom.start = 100 - width;
    dispatchZoom();
  }

  function pan(direction) {
    const width = displayState.zoom.end - displayState.zoom.start;
    const delta = width * .2 * direction;
    let start = displayState.zoom.start + delta;
    let end = displayState.zoom.end + delta;
    if (start < 0) { end -= start; start = 0; }
    if (end > 100) { start -= end - 100; end = 100; }
    displayState.zoom = { start: Math.max(0, start), end: Math.min(100, end) };
    dispatchZoom();
  }

  function resetZoom(latest = false) {
    displayState.zoom = latest ? { start: 55, end: 100 } : { start: 0, end: 100 };
    dispatchZoom();
  }

  function exportChart(chart, filename) {
    const anchor = document.createElement('a');
    anchor.href = chart.getDataURL({ type: 'png', pixelRatio: 2, backgroundColor: '#24252f' });
    anchor.download = `${filename}_${new Date().toISOString().replace(/[:.]/g, '-')}.png`;
    anchor.click();
  }

  function handleToolbarAction(action, button, chartName) {
    if (action === 'zoom-in') zoom(.62);
    if (action === 'zoom-out') zoom(1.62);
    if (action === 'pan-left') pan(-1);
    if (action === 'pan-right') pan(1);
    if (action === 'reset') resetZoom(false);
    if (action === 'latest') resetZoom(true);
    if (action === 'cursor') {
      displayState.cursorEnabled = !displayState.cursorEnabled;
      document.querySelectorAll('[data-action="cursor"]').forEach(item => item.classList.toggle('is-active', displayState.cursorEnabled));
      updateCharts();
    }
    if (action === 'legend') {
      seriesKey.hidden = !seriesKey.hidden;
      button.classList.toggle('is-active', !seriesKey.hidden);
    }
    if (action === 'series-picker') {
      seriesPicker.hidden = !seriesPicker.hidden;
      button.classList.toggle('is-active', !seriesPicker.hidden);
    }
    if (action === 'series-picker-close') {
      seriesPicker.hidden = true;
      document.querySelectorAll('[data-action="series-picker"]').forEach(item => item.classList.remove('is-active'));
    }
    if (action === 'export') exportChart(chartName === 'main' ? mainChart : lowerChart, chartName === 'main' ? '工长主趋势' : '工艺周期趋势');
    if (action === 'range-prev' || action === 'range-next') {
      const shift = action === 'range-prev' ? -1 : 1;
      const start = new Date(displayState.rangeStart || buffer.timestamps[Math.max(0, buffer.timestamps.length - displayState.displayMinutes)] || Date.now());
      const end = new Date(displayState.rangeEnd || buffer.timestamps[buffer.timestamps.length - 1] || Date.now());
      start.setHours(start.getHours() + shift);
      end.setHours(end.getHours() + shift);
      displayState.rangeStart = toDateTimeLocal(start);
      displayState.rangeEnd = toDateTimeLocal(end);
      syncRangeInputs();
      updateCharts();
    }
    if (action === 'range-apply') applyManualRange();
  }

  function toDateTimeLocal(value) {
    const date = value instanceof Date ? value : new Date(value);
    if (!Number.isFinite(date.getTime())) return '';
    const pad = item => String(item).padStart(2, '0');
    return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}T${pad(date.getHours())}:00`;
  }

  function syncRangeInputs() {
    const start = byId('trend-range-start');
    const end = byId('trend-range-end');
    if (start) start.value = displayState.rangeStart ? toDateTimeLocal(displayState.rangeStart) : '';
    if (end) end.value = displayState.rangeEnd ? toDateTimeLocal(displayState.rangeEnd) : '';
  }

  function initializeRangeInputs() {
    if (!displayState.rangeStart || !displayState.rangeEnd) {
      const latest = buffer.timestamps[buffer.timestamps.length - 1];
      const end = latest ? new Date(latest) : new Date();
      const start = new Date(end.getTime() - displayState.displayMinutes * 60000);
      displayState.rangeStart = toDateTimeLocal(start);
      displayState.rangeEnd = toDateTimeLocal(end);
    }
    syncRangeInputs();
  }

  function applyManualRange() {
    const start = byId('trend-range-start')?.value || '';
    const end = byId('trend-range-end')?.value || '';
    const startMs = new Date(start).getTime();
    const endMs = new Date(end).getTime();
    if (!Number.isFinite(startMs) || !Number.isFinite(endMs) || endMs <= startMs) return;
    const hours = Math.max(1, Math.round((endMs - startMs) / 3600000));
    displayState.displayMinutes = hours * 60;
    displayState.rangeStart = toDateTimeLocal(new Date(startMs));
    displayState.rangeEnd = toDateTimeLocal(new Date(endMs));
    const select = byId('window-minutes');
    if (select && [...select.options].some(option => option.value === String(displayState.displayMinutes))) select.value = String(displayState.displayMinutes);
    resetZoom(false);
    updateCharts();
  }

  function bindControls() {
    document.querySelectorAll('[data-chart-toolbar]').forEach(toolbar => {
      const chartName = toolbar.dataset.chartToolbar;
      toolbar.addEventListener('click', event => {
        const button = event.target.closest('button[data-action]');
        if (button) handleToolbarAction(button.dataset.action, button, chartName);
      });
    });
    byId('window-minutes').value = String(displayState.displayMinutes);
    byId('window-minutes').addEventListener('change', event => {
      displayState.displayMinutes = Number(event.target.value) || 90;
      const latest = buffer.timestamps[buffer.timestamps.length - 1];
      if (latest) {
        const end = new Date(latest);
        displayState.rangeEnd = toDateTimeLocal(end);
        displayState.rangeStart = toDateTimeLocal(new Date(end.getTime() - displayState.displayMinutes * 60000));
        syncRangeInputs();
      }
      resetZoom(false);
      updateCharts();
    });
    ['trend-range-start', 'trend-range-end'].forEach(id => byId(id)?.addEventListener('change', applyManualRange));
    MAIN_SERIES.forEach(item => {
      const button = document.createElement('button');
      button.type = 'button';
      button.dataset.seriesId = item.id;
      button.innerHTML = `<span class="series-swatch" style="--series-color:${item.color}"></span><span>${item.name}</span>`;
      button.addEventListener('click', () => {
        if (displayState.hiddenSeries.has(item.id)) displayState.hiddenSeries.delete(item.id);
        else displayState.hiddenSeries.add(item.id);
        button.classList.toggle('is-hidden', displayState.hiddenSeries.has(item.id));
        updateCharts();
      });
      seriesKey.appendChild(button);
    });
    buildSeriesPicker();
    const suffix = `?ws_port=${encodeURIComponent(params.get('ws_port') || '8767')}&pspace_ws_port=${encodeURIComponent(params.get('pspace_ws_port') || '8770')}`;
    document.querySelectorAll('.legacy-tabs [data-target]').forEach(link => {
      link.href = `frontend_dashboard_v3.server.html${suffix}#${link.dataset.target}`;
    });
    const activeLink = document.querySelector('.legacy-tabs a.active');
    activeLink.href = fixtureMode ? 'foreman_trend_preview.html?fixture=1' : `foreman_trend_preview.html${suffix}`;
    syncRangeInputs();
  }

  function buildSeriesPicker() {
    if (!seriesPickerList) return;
    const fragment = document.createDocumentFragment();
    curveCatalog.forEach(item => {
      const label = document.createElement('label');
      label.className = 'series-picker-item';
      label.style.setProperty('--series-color', seriesColor(item.id));
      const input = document.createElement('input');
      input.type = 'checkbox';
      input.checked = displayState.selectedSeries.has(item.id);
      input.dataset.seriesSelect = item.id;
      input.addEventListener('change', () => {
        if (input.checked) displayState.selectedSeries.add(item.id);
        else displayState.selectedSeries.delete(item.id);
        updateCharts();
      });
      const swatch = document.createElement('span');
      swatch.className = 'series-picker-swatch';
      const name = document.createElement('span');
      name.className = 'series-picker-name';
      name.textContent = `${item.name}${item.unit ? `（${item.unit}）` : ''}`;
      label.append(input, swatch, name);
      fragment.appendChild(label);
    });
    seriesPickerList.replaceChildren(fragment);
  }

  function initialize() {
    if (!window.echarts) {
      setSourceState('图表依赖加载失败', 'is-offline');
      return;
    }
    buildMetricMatrix();
    mainChart = window.echarts.init(byId('main-trend-chart'), null, { renderer: 'canvas' });
    lowerChart = window.echarts.init(byId('lower-trend-chart'), null, { renderer: 'canvas' });
    mainChart.group = TREND_GROUP;
    lowerChart.group = TREND_GROUP;
    window.echarts.connect(TREND_GROUP);
    window.BFCurveInspector?.installEcharts(mainChart);
    window.BFCurveInspector?.installEcharts(lowerChart);
    bindControls();
    const observer = new ResizeObserver(() => {
      mainChart.resize();
      lowerChart.resize();
    });
    observer.observe(document.querySelector('.foreman-stage'));
    window.setInterval(() => { systemClock.textContent = formatClock(new Date()); }, 1000);
    systemClock.textContent = formatClock(new Date());
    document.documentElement.dataset.requirement = REQUIREMENT_ID;
    if (fixtureMode) {
      buildFixture();
      setSourceState('布局校验数据 · 非生产', 'is-fixture');
      renderAll();
    } else {
      renderAll();
      connectWebSocket();
      connectPspaceWebSocket();
    }
  }

  window.addEventListener('beforeunload', () => {
    window.clearTimeout(reconnectTimer);
    window.clearTimeout(pspaceReconnectTimer);
  });
  window.addEventListener('DOMContentLoaded', initialize, { once: true });
})();
