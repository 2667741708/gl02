(() => {
  "use strict";

  const BLIND_LABEL_MODE = new URLSearchParams(window.location.search).get("labeling_blind") === "1";

  const LAYERS = [
    { layer: 7, height: 16.860, region: "belly" },
    { layer: 8, height: 18.335, region: "belly" },
    { layer: 9, height: 20.125, region: "waist" },
    { layer: 10, height: 21.860, region: "stack_lower" },
    { layer: 11, height: 23.711, region: "stack_lower" },
    { layer: 12, height: 25.441, region: "stack_lower" },
    { layer: 13, height: 27.171, region: "stack_lower" },
    { layer: 14, height: 28.901, region: "stack_middle" },
    { layer: 15, height: 30.631, region: "stack_upper" },
    { layer: 16, height: 32.361, region: "stack_upper" },
  ];
  const SECTORS = "ABCDEFGH".split("");
  const INFRARED_STOPS = [
    [0.00, [5, 6, 17]],
    [0.15, [51, 0, 78]],
    [0.34, [143, 0, 61]],
    [0.54, [220, 37, 24]],
    [0.73, [255, 140, 0]],
    [0.89, [255, 227, 80]],
    [1.00, [255, 253, 240]],
  ];
  const PROFILE = [
    [16.860, 4.36], [18.335, 4.46], [20.125, 4.38], [21.860, 4.24],
    [23.711, 4.10], [25.441, 3.91], [27.171, 3.69], [28.901, 3.52],
    [30.631, 3.36], [32.361, 3.16],
  ];
  const MAX_RADIUS = 4.46;
  const TREND_COLORS = ["#57b8ff", "#64d4a9", "#f1c75b", "#f28b57", "#d879d8", "#9f9cff", "#ef6c78", "#c4d36b"];

  const ids = [
    "sourceBadge", "latestText", "startInput", "endInput", "stepSelect",
    "rangePrevButton", "rangeNextButton",
    "fpsSelect", "regionSelect", "cohesiveToggle", "loadButton", "thermalCanvas",
    "canvasStage", "loadingState", "errorState", "errorMessage", "retryButton",
    "emptyState", "legendLow", "legendHigh", "frameTime", "frameCounter",
    "previousButton", "playButton", "nextButton", "timelineInput", "loopToggle",
    "recordButton", "recordStatus", "maxTemp", "minTemp", "avgTemp",
    "coverageText", "hotspotText", "deltaText", "layerTableBody", "estimateEmpty",
    "estimateMetrics", "estimateHeight", "estimateDirection", "estimateVelocity",
    "estimateConfidence", "temperatureLayerSelect", "pressureBandSelect",
    "temperatureTrendCanvas", "pressureTrendCanvas", "temperatureTrendLegend",
    "pressureTrendLegend",
  ];
  const el = Object.fromEntries(ids.map((id) => [id, document.getElementById(id)]));
  const ctx = el.thermalCanvas.getContext("2d", { alpha: false });
  const raster = document.createElement("canvas");
  const rasterCtx = raster.getContext("2d", { alpha: true });

  const state = {
    payload: null,
    temperaturePoints: [],
    pressurePoints: [],
    pointsByKey: new Map(),
    index: 0,
    playing: false,
    recording: false,
    recorder: null,
    recordChunks: [],
    lastTick: 0,
    loadController: null,
    latestTime: null,
    cohesiveAvailable: true,
  };

  function finite(value) {
    const number = Number(value);
    return Number.isFinite(number) ? number : null;
  }

  function clamp(value, low, high) {
    return Math.max(low, Math.min(high, value));
  }

  function mean(values) {
    const valid = values.filter((value) => Number.isFinite(value));
    return valid.length ? valid.reduce((sum, value) => sum + value, 0) / valid.length : null;
  }

  function interpolate(a, b, ratio) {
    return a + (b - a) * ratio;
  }

  function infraredColor(value, low, high, alpha = 255) {
    if (!Number.isFinite(value)) return [36, 43, 47, Math.min(alpha, 100)];
    const t = clamp((value - low) / Math.max(high - low, 1e-9), 0, 1);
    for (let index = 1; index < INFRARED_STOPS.length; index += 1) {
      const [rightT, rightColor] = INFRARED_STOPS[index];
      const [leftT, leftColor] = INFRARED_STOPS[index - 1];
      if (t <= rightT) {
        const ratio = (t - leftT) / Math.max(rightT - leftT, 1e-9);
        return [
          Math.round(interpolate(leftColor[0], rightColor[0], ratio)),
          Math.round(interpolate(leftColor[1], rightColor[1], ratio)),
          Math.round(interpolate(leftColor[2], rightColor[2], ratio)),
          alpha,
        ];
      }
    }
    return [...INFRARED_STOPS[INFRARED_STOPS.length - 1][1], alpha];
  }

  function radiusAtHeight(height) {
    if (height <= PROFILE[0][0]) return PROFILE[0][1];
    for (let index = 1; index < PROFILE.length; index += 1) {
      const [h1, r1] = PROFILE[index];
      const [h0, r0] = PROFILE[index - 1];
      if (height <= h1) return interpolate(r0, r1, (height - h0) / (h1 - h0));
    }
    return PROFILE[PROFILE.length - 1][1];
  }

  function formatDateTime(value) {
    if (!value) return "--";
    const date = new Date(value);
    if (Number.isNaN(date.getTime())) return String(value);
    return new Intl.DateTimeFormat("zh-CN", {
      year: "numeric", month: "2-digit", day: "2-digit",
      hour: "2-digit", minute: "2-digit", second: "2-digit", hour12: false,
    }).format(date);
  }

  function toInputValue(date) {
    const pad = (value) => String(value).padStart(2, "0");
    return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}`
      + `T${pad(date.getHours())}:${pad(date.getMinutes())}`;
  }

  function toQueryValue(inputValue) {
    return String(inputValue || "").replace("T", " ") + ":00";
  }

  function setAppState(name, message = "") {
    document.querySelector(".app-shell").dataset.appState = name;
    el.loadingState.classList.toggle("hidden", name !== "loading" && name !== "preparing");
    el.errorState.classList.toggle("hidden", name !== "error");
    el.emptyState.classList.toggle("hidden", name !== "empty");
    if (message) el.errorMessage.textContent = message;
  }

  function setBusy(busy) {
    el.loadButton.disabled = busy || state.recording;
    el.loadButton.textContent = busy ? "正在加载" : "加载历史";
    [el.startInput, el.endInput, el.stepSelect, el.cohesiveToggle, el.temperatureLayerSelect, el.pressureBandSelect].forEach((node) => {
      node.disabled = busy || state.recording || (node === el.cohesiveToggle && !state.cohesiveAvailable);
    });
  }

  function setRecordingControls(recording) {
    [
      el.startInput, el.endInput, el.stepSelect, el.fpsSelect, el.regionSelect,
      el.cohesiveToggle, el.temperatureLayerSelect, el.pressureBandSelect,
      el.loadButton, el.previousButton, el.playButton,
      el.nextButton, el.timelineInput, el.loopToggle,
    ].forEach((node) => {
      node.disabled = recording || (node === el.cohesiveToggle && !state.cohesiveAvailable);
    });
  }

  async function fetchJson(url, timeoutMs = 60000) {
    const controller = new AbortController();
    const timer = window.setTimeout(() => controller.abort(), timeoutMs);
    state.loadController = controller;
    try {
      const response = await fetch(url, { cache: "no-store", signal: controller.signal });
      let payload = null;
      try { payload = await response.json(); } catch (_error) { payload = null; }
      if (!response.ok) {
        throw new Error(payload?.message || `请求失败（HTTP ${response.status}）`);
      }
      return payload;
    } catch (error) {
      if (error.name === "AbortError") throw new Error("读取超时，请缩短时间窗或增大取帧步长。");
      throw error;
    } finally {
      window.clearTimeout(timer);
      if (state.loadController === controller) state.loadController = null;
    }
  }

  function regionMatches(region, selected) {
    if (!selected || selected === "all") return true;
    return region === selected;
  }

  function pointValue(layer, sector, frameIndex) {
    const point = state.pointsByKey.get(`${layer}:${sector}`);
    return point ? finite(point.values?.[frameIndex]) : null;
  }

  function layerBounds(height) {
    if (height <= LAYERS[0].height) return [0, 0, 0];
    for (let index = 1; index < LAYERS.length; index += 1) {
      if (height <= LAYERS[index].height) {
        const low = LAYERS[index - 1];
        const high = LAYERS[index];
        return [index - 1, index, (height - low.height) / (high.height - low.height)];
      }
    }
    const last = LAYERS.length - 1;
    return [last, last, 0];
  }

  function mixedValue(layer0, layer1, layerRatio, sectorPosition, frameIndex) {
    const sector0 = clamp(Math.floor(sectorPosition), 0, SECTORS.length - 1);
    const sector1 = clamp(sector0 + 1, 0, SECTORS.length - 1);
    const sectorRatio = sectorPosition - sector0;
    const values = [
      [pointValue(LAYERS[layer0].layer, SECTORS[sector0], frameIndex), (1 - layerRatio) * (1 - sectorRatio)],
      [pointValue(LAYERS[layer0].layer, SECTORS[sector1], frameIndex), (1 - layerRatio) * sectorRatio],
      [pointValue(LAYERS[layer1].layer, SECTORS[sector0], frameIndex), layerRatio * (1 - sectorRatio)],
      [pointValue(LAYERS[layer1].layer, SECTORS[sector1], frameIndex), layerRatio * sectorRatio],
    ];
    let sum = 0;
    let weight = 0;
    values.forEach(([value, itemWeight]) => {
      if (Number.isFinite(value) && itemWeight > 0) {
        sum += value * itemWeight;
        weight += itemWeight;
      }
    });
    return weight > 0 ? sum / weight : null;
  }

  function drawRaster(plot, frameIndex) {
    const width = Math.max(240, Math.min(560, Math.round(plot.width * 0.62)));
    const height = Math.max(280, Math.min(620, Math.round(plot.height * 0.88)));
    if (raster.width !== width || raster.height !== height) {
      raster.width = width;
      raster.height = height;
    }
    const image = rasterCtx.createImageData(width, height);
    const pixels = image.data;
    const low = finite(state.payload?.scales?.temperature?.low) ?? 0;
    const high = finite(state.payload?.scales?.temperature?.high) ?? 1;
    const minHeight = LAYERS[0].height;
    const maxHeight = LAYERS[LAYERS.length - 1].height;
    const selectedRegion = el.regionSelect.value;

    for (let y = 0; y < height; y += 1) {
      const heightRatio = 1 - y / Math.max(height - 1, 1);
      const physicalHeight = interpolate(minHeight, maxHeight, heightRatio);
      const halfWidth = (radiusAtHeight(physicalHeight) / MAX_RADIUS) * width * 0.47;
      const [layer0, layer1, layerRatio] = layerBounds(physicalHeight);
      const region = layerRatio < 0.5 ? LAYERS[layer0].region : LAYERS[layer1].region;
      const alpha = regionMatches(region, selectedRegion) ? 255 : 56;
      for (let x = 0; x < width; x += 1) {
        const pixel = (y * width + x) * 4;
        const relativeX = x - width / 2;
        if (Math.abs(relativeX) > halfWidth) {
          pixels[pixel] = 4; pixels[pixel + 1] = 6; pixels[pixel + 2] = 8; pixels[pixel + 3] = 255;
          continue;
        }
        const u = clamp((relativeX / Math.max(halfWidth, 1) + 1) / 2, 0, 1);
        const value = mixedValue(layer0, layer1, layerRatio, u * (SECTORS.length - 1), frameIndex);
        const color = infraredColor(value, low, high, alpha);
        pixels[pixel] = color[0]; pixels[pixel + 1] = color[1]; pixels[pixel + 2] = color[2]; pixels[pixel + 3] = color[3];
      }
    }
    rasterCtx.putImageData(image, 0, 0);
    ctx.drawImage(raster, plot.x, plot.y, plot.width, plot.height);
  }

  function heightToY(height, plot) {
    const low = LAYERS[0].height;
    const high = LAYERS[LAYERS.length - 1].height;
    return plot.y + (1 - (height - low) / (high - low)) * plot.height;
  }

  function xAtSector(sectorIndex, layerHeight, plot) {
    const half = (radiusAtHeight(layerHeight) / MAX_RADIUS) * plot.width * 0.47;
    return plot.x + plot.width / 2 + ((sectorIndex / 7) * 2 - 1) * half;
  }

  function drawOverlay(plot, frameIndex) {
    ctx.save();
    ctx.lineWidth = 1;
    ctx.font = "13px SimSun, serif";
    ctx.textBaseline = "middle";
    LAYERS.forEach((item) => {
      const y = heightToY(item.height, plot);
      const half = (radiusAtHeight(item.height) / MAX_RADIUS) * plot.width * 0.47;
      const highlighted = regionMatches(item.region, el.regionSelect.value);
      ctx.strokeStyle = highlighted ? "rgba(235,240,240,.36)" : "rgba(150,160,165,.12)";
      ctx.beginPath(); ctx.moveTo(plot.x + plot.width / 2 - half, y); ctx.lineTo(plot.x + plot.width / 2 + half, y); ctx.stroke();
      ctx.fillStyle = highlighted ? "#d7e0e2" : "#657177";
      ctx.textAlign = "right";
      ctx.fillText(`L${item.layer}  ${item.height.toFixed(3)}m`, plot.x - 9, y);
    });

    const baseHeight = LAYERS[0].height;
    SECTORS.forEach((sector, index) => {
      const x = xAtSector(index, baseHeight, plot);
      ctx.fillStyle = "#dce4e5";
      ctx.textAlign = "center";
      ctx.fillText(sector, x, plot.y + plot.height + 20);
    });

    ctx.strokeStyle = "rgba(230,236,236,.75)";
    ctx.lineWidth = 1.3;
    ctx.beginPath();
    PROFILE.slice().reverse().forEach(([height, radius], index) => {
      const x = plot.x + plot.width / 2 - (radius / MAX_RADIUS) * plot.width * 0.47;
      const y = heightToY(height, plot);
      if (index === 0) ctx.moveTo(x, y); else ctx.lineTo(x, y);
    });
    PROFILE.forEach(([height, radius]) => {
      const x = plot.x + plot.width / 2 + (radius / MAX_RADIUS) * plot.width * 0.47;
      ctx.lineTo(x, heightToY(height, plot));
    });
    ctx.closePath(); ctx.stroke();

    const estimate = state.payload?.cohesive_zone?.[frameIndex];
    if (estimate?.status === "available") {
      const center = finite(estimate.center_height_m);
      const thickness = finite(estimate.thickness_m);
      if (center !== null && center >= LAYERS[0].height && center <= LAYERS[LAYERS.length - 1].height) {
        const y = heightToY(center, plot);
        const half = (radiusAtHeight(center) / MAX_RADIUS) * plot.width * 0.47;
        if (thickness !== null) {
          const yTop = heightToY(center + thickness / 2, plot);
          const yBottom = heightToY(center - thickness / 2, plot);
          ctx.fillStyle = "rgba(255,177,49,.10)";
          ctx.fillRect(plot.x + plot.width / 2 - half, Math.min(yTop, yBottom), half * 2, Math.abs(yBottom - yTop));
        }
        ctx.setLineDash([8, 6]);
        ctx.strokeStyle = "#ffb53f";
        ctx.lineWidth = 2;
        ctx.beginPath(); ctx.moveTo(plot.x + plot.width / 2 - half, y); ctx.lineTo(plot.x + plot.width / 2 + half, y); ctx.stroke();
        ctx.setLineDash([]);
        ctx.fillStyle = "#ffe0a2";
        ctx.textAlign = "left";
        ctx.fillText(`根部代理 ${center.toFixed(2)}m`, plot.x + plot.width / 2 + half + 7, y);
      }
    }

    const timestamp = state.payload?.timeline?.[frameIndex];
    ctx.fillStyle = "rgba(0,0,0,.66)";
    ctx.fillRect(plot.x + 10, plot.y + 10, 260, 48);
    ctx.fillStyle = "#fff";
    ctx.font = "16px SimSun, serif";
    ctx.textAlign = "left";
    ctx.fillText(formatDateTime(timestamp), plot.x + 20, plot.y + 29);
    ctx.font = "12px SimSun, serif";
    ctx.fillStyle = "#b9c4c7";
    ctx.fillText("数据库炉体测温 · 红外插值回放", plot.x + 20, plot.y + 48);
    ctx.restore();
  }

  function resizeCanvas() {
    const rect = el.canvasStage.getBoundingClientRect();
    const ratio = Math.min(window.devicePixelRatio || 1, 2);
    const width = Math.max(320, Math.round(rect.width * ratio));
    const height = Math.max(360, Math.round(rect.height * ratio));
    if (el.thermalCanvas.width !== width || el.thermalCanvas.height !== height) {
      el.thermalCanvas.width = width;
      el.thermalCanvas.height = height;
    }
    ctx.setTransform(ratio, 0, 0, ratio, 0, 0);
    renderFrame();
  }

  function trendTimeLabel(value, includeDate = false) {
    const date = new Date(value);
    if (Number.isNaN(date.getTime())) return "--";
    const pad = (number) => String(number).padStart(2, "0");
    const time = `${pad(date.getHours())}:${pad(date.getMinutes())}`;
    return includeDate ? `${pad(date.getMonth() + 1)}/${pad(date.getDate())} ${time}` : time;
  }

  function drawTrendChart(canvas, legend, points, unit) {
    const parent = canvas.parentElement;
    const rect = parent.getBoundingClientRect();
    const ratio = Math.min(window.devicePixelRatio || 1, 2);
    const width = Math.max(280, Math.round(rect.width));
    const height = Math.max(220, Math.round(rect.height));
    const pixelWidth = Math.round(width * ratio);
    const pixelHeight = Math.round(height * ratio);
    if (canvas.width !== pixelWidth || canvas.height !== pixelHeight) {
      canvas.width = pixelWidth;
      canvas.height = pixelHeight;
    }
    const chart = canvas.getContext("2d", { alpha: false });
    chart.setTransform(ratio, 0, 0, ratio, 0, 0);
    chart.fillStyle = "#080c0f";
    chart.fillRect(0, 0, width, height);

    const timeline = state.payload?.timeline || [];
    const series = points.map((point) => ({
      point,
      values: (point.values || []).map(finite),
    }));
    const valid = series.flatMap((item) => item.values.filter((value) => value !== null));
    canvas.dataset.renderedSeries = String(series.length);
    if (!timeline.length || !series.length || !valid.length) {
      chart.fillStyle = "#9aa8ae";
      chart.font = "14px SimSun, serif";
      chart.textAlign = "center";
      chart.fillText(series.length ? "所选时间段没有有效曲线数据" : "所选层位没有注册点位", width / 2, height / 2);
      legend.textContent = "暂无有效数据";
      return;
    }

    let low = Math.min(...valid);
    let high = Math.max(...valid);
    const padding = Math.max((high - low) * 0.08, unit === "℃" ? 1 : 0.02);
    low -= padding;
    high += padding;
    if (Math.abs(high - low) < 1e-9) high = low + 1;

    const left = width < 480 ? 48 : 58;
    const right = 16;
    const top = 18;
    const bottom = 42;
    const plotWidth = Math.max(140, width - left - right);
    const plotHeight = Math.max(120, height - top - bottom);
    const xFor = (index) => left + (timeline.length <= 1 ? 0 : index / (timeline.length - 1) * plotWidth);
    const yFor = (value) => top + (high - value) / (high - low) * plotHeight;
    canvas.__trendHit = { timeline, series, xFor, yFor, left, right, top, plotWidth, plotHeight, width, height, unit };

    chart.lineWidth = 1;
    chart.font = "12px SimSun, serif";
    chart.textAlign = "right";
    chart.textBaseline = "middle";
    for (let tick = 0; tick <= 4; tick += 1) {
      const y = top + tick / 4 * plotHeight;
      const value = high - tick / 4 * (high - low);
      chart.strokeStyle = "#263138";
      chart.beginPath();
      chart.moveTo(left, y);
      chart.lineTo(left + plotWidth, y);
      chart.stroke();
      chart.fillStyle = "#aeb9bd";
      chart.fillText(`${value.toFixed(unit === "℃" ? 0 : 2)}`, left - 7, y);
    }
    chart.save();
    chart.translate(13, top + plotHeight / 2);
    chart.rotate(-Math.PI / 2);
    chart.fillStyle = "#9aa8ae";
    chart.textAlign = "center";
    chart.fillText(unit, 0, 0);
    chart.restore();

    series.forEach((item, seriesIndex) => {
      chart.strokeStyle = TREND_COLORS[seriesIndex % TREND_COLORS.length];
      chart.lineWidth = 1.7;
      chart.beginPath();
      let drawing = false;
      item.values.forEach((value, index) => {
        if (value === null) {
          drawing = false;
          return;
        }
        const x = xFor(index);
        const y = yFor(value);
        if (!drawing) chart.moveTo(x, y);
        else chart.lineTo(x, y);
        drawing = true;
      });
      chart.stroke();
    });

    const tickIndices = Array.from(new Set([0, Math.floor((timeline.length - 1) / 2), timeline.length - 1]));
    chart.textBaseline = "top";
    tickIndices.forEach((index, order) => {
      chart.fillStyle = "#9aa8ae";
      chart.textAlign = order === 0 ? "left" : order === tickIndices.length - 1 ? "right" : "center";
      chart.fillText(trendTimeLabel(timeline[index], order === 0), xFor(index), top + plotHeight + 9);
    });

    const cursorIndex = clamp(state.index, 0, timeline.length - 1);
    const cursorX = xFor(cursorIndex);
    chart.strokeStyle = "#f5f0d0";
    chart.lineWidth = 1;
    chart.setLineDash([4, 4]);
    chart.beginPath();
    chart.moveTo(cursorX, top);
    chart.lineTo(cursorX, top + plotHeight);
    chart.stroke();
    chart.setLineDash([]);

    legend.innerHTML = series.map((item, index) => {
      const value = item.values[cursorIndex];
      const label = item.point.azimuth || item.point.id;
      const shown = value === null ? "--" : `${value.toFixed(unit === "℃" ? 1 : 3)}${unit}`;
      return `<span><i style="background:${TREND_COLORS[index % TREND_COLORS.length]}"></i>${label} ${shown}</span>`;
    }).join("");
  }

  function showCanvasInspector(event, canvas) {
    const hit = canvas.__trendHit;
    if (!hit || !hit.timeline.length) return;
    const rect = canvas.getBoundingClientRect();
    const x = event.clientX - rect.left;
    const y = event.clientY - rect.top;
    let best = null;
    hit.series.forEach((item) => item.values.forEach((value, index) => {
      if (value === null) return;
      const dx = hit.xFor(index) - x;
      const dy = hit.yFor(value) - y;
      const distance = Math.sqrt(dx * dx + dy * dy);
      if (!best || distance < best.distance) best = { distance, item, value, index };
    }));
    if (!best || best.distance > 52) return;
    document.querySelectorAll('.bf-canvas-inspector').forEach((node) => node.remove());
    const popup = document.createElement('div');
    popup.className = 'bf-canvas-inspector';
    popup.innerHTML = `<div><span>点位ID</span><b>${String(best.item.point.id || '--')}</b></div><div><span>曲线</span>${String(best.item.point.azimuth || best.item.point.id || '--')}</div><div><span>数据</span><b>${best.value.toFixed(hit.unit === '℃' ? 1 : 3)}${hit.unit}</b></div><div><span>时间戳</span>${formatDateTime(hit.timeline[best.index])}</div>`;
    document.body.appendChild(popup);
    const popupRect = popup.getBoundingClientRect();
    popup.style.left = `${Math.min(Math.max(8, event.clientX + 12), window.innerWidth - popupRect.width - 8)}px`;
    popup.style.top = `${Math.min(Math.max(8, event.clientY + 12), window.innerHeight - popupRect.height - 8)}px`;
  }

  function bindTrendContextMenu(canvas) {
    if (!canvas || canvas.dataset.contextInspectorBound === '1') return;
    canvas.dataset.contextInspectorBound = '1';
    canvas.addEventListener('contextmenu', (event) => { event.preventDefault(); showCanvasInspector(event, canvas); });
    canvas.addEventListener('mouseleave', () => document.querySelectorAll('.bf-canvas-inspector').forEach((node) => node.remove()));
  }

  function shiftReplayRange(hours) {
    const start = new Date(el.startInput.value); const end = new Date(el.endInput.value);
    if (!Number.isFinite(start.getTime()) || !Number.isFinite(end.getTime())) return;
    start.setHours(start.getHours() + hours); end.setHours(end.getHours() + hours);
    el.startInput.value = toInputValue(start); el.endInput.value = toInputValue(end);
  }

  function renderTrendCharts() {
    const selectedLayer = Number(el.temperatureLayerSelect.value);
    const selectedBand = el.pressureBandSelect.value;
    const temperatureSeries = state.temperaturePoints
      .filter((point) => Number(point.layer) === selectedLayer)
      .sort((left, right) => String(left.azimuth).localeCompare(String(right.azimuth)));
    const pressureSeries = state.pressurePoints
      .filter((point) => point.pressure_band === selectedBand)
      .sort((left, right) => String(left.azimuth).localeCompare(String(right.azimuth)));
    drawTrendChart(el.temperatureTrendCanvas, el.temperatureTrendLegend, temperatureSeries, "℃");
    drawTrendChart(el.pressureTrendCanvas, el.pressureTrendLegend, pressureSeries, "kPa");
    bindTrendContextMenu(el.temperatureTrendCanvas);
    bindTrendContextMenu(el.pressureTrendCanvas);
  }

  function currentVisibleValues(frameIndex) {
    return state.temperaturePoints
      .filter((point) => regionMatches(point.region, el.regionSelect.value))
      .map((point) => ({ point, value: finite(point.values?.[frameIndex]) }))
      .filter((item) => item.value !== null);
  }

  function updateSummary(frameIndex) {
    const values = currentVisibleValues(frameIndex);
    const numbers = values.map((item) => item.value);
    if (!numbers.length) {
      [el.maxTemp, el.minTemp, el.avgTemp, el.hotspotText, el.deltaText].forEach((node) => { node.textContent = "--"; });
      el.coverageText.textContent = "0%";
    } else {
      const maximum = Math.max(...numbers);
      const minimum = Math.min(...numbers);
      const average = mean(numbers);
      const hotspot = values.find((item) => item.value === maximum);
      el.maxTemp.textContent = `${maximum.toFixed(1)}℃`;
      el.minTemp.textContent = `${minimum.toFixed(1)}℃`;
      el.avgTemp.textContent = `${average.toFixed(1)}℃`;
      el.hotspotText.textContent = hotspot ? `L${hotspot.point.layer}-${hotspot.point.azimuth}` : "--";
      const expected = state.temperaturePoints.filter((point) => regionMatches(point.region, el.regionSelect.value)).length;
      el.coverageText.textContent = `${(numbers.length / Math.max(expected, 1) * 100).toFixed(1)}%`;

      let largest = null;
      if (frameIndex > 0) {
        values.forEach(({ point, value }) => {
          const previous = finite(point.values?.[frameIndex - 1]);
          if (previous === null) return;
          const delta = value - previous;
          if (!largest || Math.abs(delta) > Math.abs(largest.delta)) largest = { point, delta };
        });
      }
      el.deltaText.textContent = largest
        ? `L${largest.point.layer}-${largest.point.azimuth} ${largest.delta >= 0 ? "+" : ""}${largest.delta.toFixed(1)}℃`
        : "首帧";
    }

    el.layerTableBody.innerHTML = "";
    LAYERS.slice().reverse().filter((item) => regionMatches(item.region, el.regionSelect.value)).forEach((item) => {
      const layerValues = SECTORS.map((sector) => pointValue(item.layer, sector, frameIndex));
      const current = mean(layerValues);
      const previous = frameIndex > 0 ? mean(SECTORS.map((sector) => pointValue(item.layer, sector, frameIndex - 1))) : null;
      const delta = current !== null && previous !== null ? current - previous : null;
      const row = document.createElement("tr");
      row.innerHTML = `<td>L${item.layer}</td><td>${item.height.toFixed(3)}m</td>`
        + `<td>${current === null ? "--" : `${current.toFixed(1)}℃`}</td>`
        + `<td class="${delta === null ? "" : delta >= 0 ? "delta-up" : "delta-down"}">`
        + `${delta === null ? "--" : `${delta >= 0 ? "+" : ""}${delta.toFixed(1)}℃`}</td>`;
      el.layerTableBody.appendChild(row);
    });

    const estimate = state.payload?.cohesive_zone?.[frameIndex];
    const available = estimate?.status === "available";
    el.estimateEmpty.classList.toggle("hidden", available);
    el.estimateMetrics.classList.toggle("hidden", !available);
    if (available) {
      const labels = { up: "上移", down: "下移", stable: "稳定" };
      el.estimateHeight.textContent = finite(estimate.center_height_m) === null ? "--" : `${Number(estimate.center_height_m).toFixed(2)}m`;
      el.estimateDirection.textContent = labels[estimate.direction] || "--";
      el.estimateVelocity.textContent = finite(estimate.velocity_m_per_h) === null ? "--" : `${Number(estimate.velocity_m_per_h).toFixed(2)}m/h`;
      el.estimateConfidence.textContent = finite(estimate.confidence) === null ? "--" : `${(Number(estimate.confidence) * 100).toFixed(0)}%`;
    } else if (el.cohesiveToggle.checked) {
      el.estimateEmpty.textContent = estimate?.reason_codes?.length
        ? `当前帧不可用：${estimate.reason_codes.join("、")}`
        : "当前帧没有满足门禁的根部代理。";
    } else {
      el.estimateEmpty.textContent = "未启用；勾选后重新加载。";
    }
  }

  function renderFrame() {
    const rect = el.canvasStage.getBoundingClientRect();
    const width = rect.width;
    const height = rect.height;
    ctx.fillStyle = "#050708";
    ctx.fillRect(0, 0, width, height);
    if (!state.payload?.timeline?.length) return;

    state.index = clamp(state.index, 0, state.payload.timeline.length - 1);
    const leftMargin = width < 620 ? 58 : 88;
    const rightMargin = width < 620 ? 30 : 110;
    const plot = { x: leftMargin, y: 18, width: Math.max(160, width - leftMargin - rightMargin), height: Math.max(260, height - 68) };
    drawRaster(plot, state.index);
    drawOverlay(plot, state.index);

    el.frameTime.textContent = formatDateTime(state.payload.timeline[state.index]);
    el.frameCounter.textContent = `${state.index + 1} / ${state.payload.timeline.length}`;
    el.timelineInput.value = String(state.index);
    updateSummary(state.index);
    renderTrendCharts();
    if (BLIND_LABEL_MODE && window.parent !== window) {
      window.parent.postMessage({
        type: "hcz-replay-frame",
        schema: "gl02.hcz-label-frame.v1",
        observed_at: state.payload.timeline[state.index],
        source_window_start: state.payload.start_time,
        source_window_end: state.payload.end_time,
        blind_to_model: true,
        model_outputs_included: false,
        coverage: state.payload.coverage || null,
      }, window.location.origin);
    }
  }

  function setPlayback(playing) {
    state.playing = Boolean(playing && state.payload?.timeline?.length > 1);
    state.lastTick = 0;
    el.playButton.textContent = state.playing ? "暂停" : "播放";
  }

  function finishRecording() {
    setPlayback(false);
    if (state.recorder && state.recorder.state !== "inactive") state.recorder.stop();
  }

  function advanceFrame(direction = 1) {
    if (!state.payload?.timeline?.length) return;
    const last = state.payload.timeline.length - 1;
    if (direction > 0 && state.index >= last) {
      if (state.recording) {
        setPlayback(false);
        window.setTimeout(finishRecording, 300);
        return;
      }
      if (el.loopToggle.checked) state.index = 0;
      else { setPlayback(false); return; }
    } else {
      state.index = clamp(state.index + direction, 0, last);
    }
    renderFrame();
  }

  function playbackLoop(timestamp) {
    if (state.playing) {
      const fps = clamp(Number(el.fpsSelect.value) || 4, 1, 30);
      const interval = 1000 / fps;
      if (!state.lastTick || timestamp - state.lastTick >= interval) {
        state.lastTick = timestamp;
        advanceFrame(1);
      }
    }
    window.requestAnimationFrame(playbackLoop);
  }

  function preparePoints(payload) {
    state.temperaturePoints = (payload.points || []).filter((point) => point.metric === "temperature");
    state.pressurePoints = (payload.points || []).filter((point) => point.metric === "pressure");
    state.pointsByKey = new Map(
      state.temperaturePoints.map((point) => [`${point.layer}:${point.azimuth}`, point]),
    );
  }

  async function loadReplay() {
    setPlayback(false);
    if (state.loadController) state.loadController.abort();
    const start = el.startInput.value;
    const end = el.endInput.value;
    if (!start || !end) {
      setAppState("error", "请选择完整的开始和结束时间。");
      return;
    }
    if (new Date(start).getTime() >= new Date(end).getTime()) {
      setAppState("error", "开始时间必须早于结束时间。");
      return;
    }
    setBusy(true);
    setAppState("loading");
    el.sourceBadge.className = "status-badge waiting";
    el.sourceBadge.textContent = "读取中";
    const query = new URLSearchParams({
      start: toQueryValue(start),
      end: toQueryValue(end),
      step_minutes: el.stepSelect.value,
      include_cohesive: BLIND_LABEL_MODE ? "0" : (el.cohesiveToggle.checked ? "1" : "0"),
    });
    try {
      const payload = await fetchJson(`/api/replay?${query.toString()}`, 90000);
      if (!payload?.ok || !payload.timeline?.length) {
        state.payload = null;
        setAppState("empty");
        return;
      }
      state.payload = payload;
      state.index = 0;
      preparePoints(payload);
      el.timelineInput.max = String(payload.timeline.length - 1);
      el.timelineInput.value = "0";
      const low = finite(payload.scales?.temperature?.low);
      const high = finite(payload.scales?.temperature?.high);
      el.legendLow.textContent = low === null ? "低 --" : `低 ${low.toFixed(1)}℃`;
      el.legendHigh.textContent = high === null ? "高 --" : `高 ${high.toFixed(1)}℃`;
      el.sourceBadge.className = "status-badge ready";
      el.sourceBadge.textContent = "数据库就绪";
      setAppState("ready");
      renderFrame();
    } catch (error) {
      state.payload = null;
      el.sourceBadge.className = "status-badge error";
      el.sourceBadge.textContent = "数据异常";
      setAppState("error", error.message || "数据链暂不可用，请稍后重试。");
    } finally {
      setBusy(false);
    }
  }

  function downloadRecording(blob) {
    const link = document.createElement("a");
    const start = el.startInput.value.replace(/[:T]/g, "").replace("-", "").replace("-", "");
    const end = el.endInput.value.replace(/[:T]/g, "").replace("-", "").replace("-", "");
    const url = URL.createObjectURL(blob);
    link.href = url;
    link.download = `GL02炉体温度红外回放_${start}_${end}.webm`;
    document.body.appendChild(link);
    link.click();
    link.remove();
    window.setTimeout(() => URL.revokeObjectURL(url), 2000);
  }

  function startRecording() {
    if (!state.payload?.timeline?.length) {
      el.recordStatus.textContent = "请先加载历史数据。";
      return;
    }
    if (state.payload.timeline.length < 2) {
      el.recordStatus.textContent = "当前时间窗只有一帧，无法生成移动视频。";
      return;
    }
    if (!el.thermalCanvas.captureStream || typeof MediaRecorder === "undefined") {
      el.recordStatus.textContent = "当前浏览器不支持画布视频导出，请使用现场Edge。";
      return;
    }
    if (state.recording) {
      finishRecording();
      return;
    }
    const fps = clamp(Number(el.fpsSelect.value) || 4, 1, 30);
    const mimeCandidates = ["video/webm;codecs=vp9", "video/webm;codecs=vp8", "video/webm"];
    const mimeType = mimeCandidates.find((value) => MediaRecorder.isTypeSupported(value)) || "";
    try {
      const stream = el.thermalCanvas.captureStream(fps);
      state.recorder = new MediaRecorder(stream, mimeType ? { mimeType } : undefined);
    } catch (error) {
      el.recordStatus.textContent = `无法开始录制：${error.message}`;
      return;
    }
    state.recordChunks = [];
    state.recording = true;
    state.index = 0;
    el.recordButton.textContent = "停止并保存";
    setRecordingControls(true);
    el.recordStatus.textContent = `正在按${fps}帧/秒生成视频，请保持页面打开。`;
    state.recorder.ondataavailable = (event) => {
      if (event.data?.size) state.recordChunks.push(event.data);
    };
    state.recorder.onerror = () => {
      state.recordStatus.textContent = "视频编码失败，请降低播放帧率后重试。";
    };
    state.recorder.onstop = () => {
      const blob = new Blob(state.recordChunks, { type: state.recorder.mimeType || "video/webm" });
      state.recording = false;
      el.recordButton.textContent = "导出WebM视频";
      setRecordingControls(false);
      if (blob.size > 0) {
        downloadRecording(blob);
        el.recordStatus.textContent = `视频已生成，大小${(blob.size / 1024 / 1024).toFixed(1)}MB。`;
      } else {
        el.recordStatus.textContent = "没有生成有效视频数据。";
      }
      state.recorder = null;
      state.recordChunks = [];
    };
    renderFrame();
    state.recorder.start(500);
    setPlayback(true);
  }

  async function initialise() {
    setBusy(true);
    setAppState("preparing");
    try {
      const health = await fetchJson("/api/health", 20000);
      if (!health?.ok || !health.latest_sample_time) throw new Error("数据库暂时没有可用炉体温度。 ");
      if (BLIND_LABEL_MODE) {
        document.body.dataset.hczLabelBlind = "true";
        el.cohesiveToggle.checked = false;
        el.cohesiveToggle.disabled = true;
        const label = el.cohesiveToggle.closest("label");
        if (label) { label.hidden = true; label.style.display = "none"; }
        const estimateCard = document.querySelector(".estimate-card");
        if (estimateCard) { estimateCard.hidden = true; estimateCard.style.display = "none"; }
        document.title = "GL02 HCZ盲标注实测回放";
      } else if (health.cohesive_available === false) {
        state.cohesiveAvailable = false;
        el.cohesiveToggle.checked = false;
        el.cohesiveToggle.disabled = true;
        const label = el.cohesiveToggle.closest("label");
        const text = label?.querySelector("span");
        if (text) text.textContent = "根部代理未安装（温度回放可用）";
        if (label) label.title = "不影响炉体实测温度的红外回放。";
      }
      state.latestTime = new Date(health.latest_sample_time);
      const end = new Date(state.latestTime);
      end.setSeconds(0, 0);
      const start = new Date(end.getTime() - 6 * 60 * 60 * 1000);
      el.endInput.value = toInputValue(end);
      el.startInput.value = toInputValue(start);
      el.latestText.textContent = `最新数据：${formatDateTime(health.latest_sample_time)}`;
      await loadReplay();
    } catch (error) {
      el.sourceBadge.className = "status-badge error";
      el.sourceBadge.textContent = "连接失败";
      setAppState("error", error.message || "无法读取数据库健康状态。 ");
    } finally {
      setBusy(false);
    }
  }

  el.loadButton.addEventListener("click", loadReplay);
  el.retryButton.addEventListener("click", loadReplay);
  el.playButton.addEventListener("click", () => setPlayback(!state.playing));
  el.previousButton.addEventListener("click", () => { setPlayback(false); advanceFrame(-1); });
  el.nextButton.addEventListener("click", () => { setPlayback(false); advanceFrame(1); });
  el.timelineInput.addEventListener("input", () => { setPlayback(false); state.index = Number(el.timelineInput.value); renderFrame(); });
  el.regionSelect.addEventListener("change", renderFrame);
  el.temperatureLayerSelect.addEventListener("change", renderTrendCharts);
  el.pressureBandSelect.addEventListener("change", renderTrendCharts);
  el.rangePrevButton.addEventListener("click", () => shiftReplayRange(-1));
  el.rangeNextButton.addEventListener("click", () => shiftReplayRange(1));
  document.addEventListener("click", (event) => { if (!event.target.closest(".bf-canvas-inspector")) document.querySelectorAll(".bf-canvas-inspector").forEach((node) => node.remove()); });
  el.recordButton.addEventListener("click", startRecording);
  window.addEventListener("resize", resizeCanvas, { passive: true });
  document.addEventListener("visibilitychange", () => { if (document.hidden && !state.recording) setPlayback(false); });

  window.requestAnimationFrame(playbackLoop);
  resizeCanvas();
  initialise();
})();
