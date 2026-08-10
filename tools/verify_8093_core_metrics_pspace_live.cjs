#!/usr/bin/env node
"use strict";

const fs = require("fs");
const path = require("path");
const { chromium, firefox, webkit } = require("playwright");

const ALL_VIEWPORTS = [
  [1280, 720],
  [1366, 768],
  [1440, 900],
  [1546, 864],
  [1920, 1080],
  [1024, 768],
  [768, 1024],
  [390, 844],
  [375, 667],
];
const REPRESENTATIVE_VIEWPORTS = [
  [1920, 1080],
  [1366, 768],
  [768, 1024],
  [390, 844],
];

function argument(name, fallback) {
  const index = process.argv.indexOf(`--${name}`);
  return index >= 0 && process.argv[index + 1] ? process.argv[index + 1] : fallback;
}

function cacheBust(url) {
  const target = new URL(url);
  target.searchParams.set("core_live_qa", String(Date.now()));
  return target.toString();
}

async function collectRows(page) {
  return page.evaluate(() =>
    [...document.querySelectorAll(".core-page-v7-content .core-live-row")].map((row) => {
      const rect = row.getBoundingClientRect();
      return {
        id: row.dataset.coreMetricId || "",
        source: row.dataset.valueSource || "",
        timestamp: row.dataset.valueTimestamp || "",
        ageSeconds: Number(row.dataset.valueAgeSeconds),
        transportAgeSeconds: Number(row.dataset.transportAgeSeconds),
        quality: row.dataset.valueQuality || "",
        value: row.querySelector(".core-live-number")?.textContent?.trim() || "",
        meta: row.querySelector(".core-live-meta")?.textContent?.trim() || "",
        title: row.querySelector(".core-live-value")?.getAttribute("title") || "",
        visible: getComputedStyle(row).display !== "none" && rect.width > 0 && rect.height > 0,
      };
    }),
  );
}

async function inspect(page, url, expectedSource, screenshot, allowStaticApiErrors = false) {
  const pageErrors = [];
  const consoleErrors = [];
  page.on("pageerror", (error) => pageErrors.push(String(error)));
  page.on("console", (message) => {
    if (message.type() === "error") {
      consoleErrors.push({ text: message.text(), url: message.location()?.url || "" });
    }
  });
  const target = cacheBust(url);
  let lastNavigationError = null;
  for (let attempt = 1; attempt <= 3; attempt += 1) {
    try {
      await page.goto(target, { waitUntil: "domcontentloaded", timeout: 45000 });
      lastNavigationError = null;
      break;
    } catch (error) {
      lastNavigationError = error;
      if (attempt < 3) await page.waitForTimeout(2000 * attempt);
    }
  }
  if (lastNavigationError) throw lastNavigationError;
  await page.waitForSelector(".core-pspace-live-8093", { state: "visible", timeout: 45000 });
  let sourceWaitError = "";
  if (expectedSource !== "auto") {
    try {
      await page.waitForFunction(
        (source) => {
          const rows = [...document.querySelectorAll(`.core-live-row[data-value-source="${source}"]`)];
          if (rows.length !== 14) return false;
          if (source !== "postgres_minute") return true;
          return rows.every((row) => {
            const value = row.querySelector(".core-live-number")?.textContent?.trim() || "";
            return Boolean(row.dataset.valueTimestamp) && Boolean(value) && value !== "--";
          });
        },
        expectedSource,
        { timeout: 30000 },
      );
    } catch (error) {
      sourceWaitError = String(error?.message || error);
    }
  }

  const tabs = page.locator(".core-metric-tabs-v7 button");
  const tabCount = await tabs.count();
  const allRows = new Map();
  const tabResults = [];
  for (let index = 0; index < tabCount; index += 1) {
    await tabs.nth(index).click();
    await page.waitForTimeout(350);
    const rows = await collectRows(page);
    rows.forEach((row) => allRows.set(row.id, row));
    tabResults.push({
      index,
      label: (await tabs.nth(index).innerText()).trim(),
      rowCount: rows.length,
      ids: rows.map((row) => row.id),
    });
  }

  let minuteDataWaitError = "";
  try {
    await page.waitForFunction(
      () => [...document.querySelectorAll(".status-strip .top-item")].some((item) => {
        const text = item.textContent?.trim() || "";
        return text.startsWith("分钟数据：") && !text.endsWith("--");
      }),
      { timeout: 15000 },
    );
  } catch (error) {
    minuteDataWaitError = String(error?.message || error);
  }

  const shell = await page.evaluate(() => {
    const content = document.querySelector(".core-page-v7-content");
    const banner = document.querySelector(".core-live-banner");
    const state = window.__BF_CORE_PSPACE_LIVE__ || {};
    const topItems = [...document.querySelectorAll(".status-strip .top-item")]
      .map((item) => item.textContent?.trim() || "");
    const systemClockText = topItems.find((text) => text.startsWith("时间："))?.slice(3) || "";
    const minuteDataText = topItems.find((text) => text.startsWith("分钟数据："))?.slice(5) || "";
    const clockParts = systemClockText.match(
      /^(\d{4})\/(\d{1,2})\/(\d{1,2})\s+(\d{1,2}):(\d{2}):(\d{2})$/,
    );
    const systemClockMs = clockParts
      ? new Date(
          Number(clockParts[1]),
          Number(clockParts[2]) - 1,
          Number(clockParts[3]),
          Number(clockParts[4]),
          Number(clockParts[5]),
          Number(clockParts[6]),
        ).getTime()
      : NaN;
    return {
      viewportWidth: innerWidth,
      documentWidth: document.documentElement.scrollWidth,
      formalHeader: !!document.querySelector(".topbar.branded-topbar"),
      banner: banner?.textContent?.trim() || "",
      bannerVisible: !!banner && banner.getBoundingClientRect().height > 0,
      contentOverflowY: content ? getComputedStyle(content).overflowY : "",
      contentClientHeight: content?.clientHeight || 0,
      contentScrollHeight: content?.scrollHeight || 0,
      schema: state.schema || "",
      status: state.status || "",
      validCount: Number(state.validCount || 0),
      lastFrameAt: state.lastFrameAt || "",
      browserNow: new Date().toISOString(),
      systemClockText,
      minuteDataText,
      systemClockDeltaSeconds: Number.isFinite(systemClockMs)
        ? Math.abs(Date.now() - systemClockMs) / 1000
        : null,
      samplePTop: state.values?.P_top || null,
    };
  });

  const failures = [];
  if (sourceWaitError) failures.push(`source_wait:${expectedSource}`);
  if (minuteDataWaitError) failures.push("minute_data_wait");
  if (tabCount !== 2) failures.push(`tab_count:${tabCount}`);
  if (allRows.size !== 28) failures.push(`unique_core_ids:${allRows.size}`);
  if (!shell.formalHeader) failures.push("formal_header_missing");
  if (!shell.systemClockText) failures.push("system_clock_missing");
  if (!Number.isFinite(shell.systemClockDeltaSeconds) || shell.systemClockDeltaSeconds > 3) {
    failures.push(`system_clock_delta:${shell.systemClockDeltaSeconds}`);
  }
  if (!shell.minuteDataText) failures.push("minute_data_time_missing");
  if (!shell.bannerVisible) failures.push("live_banner_hidden");
  if (shell.documentWidth > shell.viewportWidth + 1) failures.push("horizontal_overflow");
  if (shell.schema !== "bf.core-metrics.pspace-live.8093.v1") failures.push(`schema:${shell.schema}`);

  for (const [id, row] of allRows.entries()) {
    if (!row.visible) failures.push(`${id}:hidden`);
    if (expectedSource !== "auto" && row.source !== expectedSource) {
      failures.push(`${id}:source:${row.source}`);
    }
    if (!row.meta || !row.quality) failures.push(`${id}:freshness_or_quality_missing`);
    if (expectedSource === "pspace_realtime") {
      if (!row.timestamp) failures.push(`${id}:timestamp_missing`);
      if (!(row.ageSeconds >= 0)) failures.push(`${id}:source_age:${row.ageSeconds}`);
      if (!(row.transportAgeSeconds >= 0 && row.transportAgeSeconds <= 12)) {
        failures.push(`${id}:transport_age:${row.transportAgeSeconds}`);
      }
      if (!row.value || row.value === "--") failures.push(`${id}:value_missing`);
    }
    if (expectedSource === "postgres_minute" && !row.title.includes("已降级为分钟镜像")) {
      failures.push(`${id}:fallback_not_explicit`);
    }
    if (expectedSource === "postgres_minute") {
      if (!row.timestamp) failures.push(`${id}:fallback_timestamp_missing`);
      if (!row.value || row.value === "--") failures.push(`${id}:fallback_value_missing`);
    }
  }
  if (expectedSource === "pspace_realtime" && !shell.banner.includes("pSpace秒级实时")) {
    failures.push("live_banner_contract");
  }
  if (expectedSource === "postgres_minute" && !shell.banner.includes("已降级为分钟镜像")) {
    failures.push("fallback_banner_contract");
  }

  const filteredConsoleErrors = consoleErrors.filter(
    (item) =>
      !item.url.includes("favicon.ico") &&
      !(allowStaticApiErrors && item.url.includes("/api/")) &&
      !item.text.includes("[BABEL] Note") &&
      !item.text.includes("WebSocket connection") &&
      !item.text.includes("Failed to fetch"),
  );
  if (pageErrors.length || filteredConsoleErrors.length) failures.push("page_or_console_errors");
  await page.screenshot({ path: screenshot, fullPage: false });
  return {
    passed: failures.length === 0,
    failures,
    shell,
    tabs: tabResults,
    rows: [...allRows.values()],
    pageErrors,
    consoleErrors: filteredConsoleErrors,
    screenshot,
  };
}

async function main() {
  const url = argument("url", "http://10.30.220.12:8093/?ws_port=8768#overview");
  const browserName = argument("browser", "chromium");
  const matrix = argument("matrix", "all");
  const explicitViewports = argument("viewports", "")
    .split(",")
    .map((item) => item.trim().match(/^(\d+)x(\d+)$/))
    .filter(Boolean)
    .map((match) => [Number(match[1]), Number(match[2])]);
  const expectedSource = argument("expected-source", "pspace_realtime");
  const allowStaticApiErrors = process.argv.includes("--allow-static-api-errors");
  const outDir = path.resolve(argument("out-dir", "logs/8093_core_metrics_pspace_live_qa"));
  const viewports = explicitViewports.length
    ? explicitViewports
    : matrix === "all"
      ? ALL_VIEWPORTS
      : matrix === "single"
        ? [[1366, 768]]
        : REPRESENTATIVE_VIEWPORTS;
  const launcher = { chromium, firefox, webkit }[browserName];
  if (!launcher) throw new Error(`Unsupported browser: ${browserName}`);
  fs.mkdirSync(outDir, { recursive: true });

  const launchOptions = { headless: true };
  if (browserName === "chromium") {
    const executablePath = argument(
      "executable-path",
      "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe",
    );
    if (fs.existsSync(executablePath)) launchOptions.executablePath = executablePath;
  }
  const browser = await launcher.launch(launchOptions);
  const results = [];
  for (const [width, height] of viewports) {
    const page = await browser.newPage({ viewport: { width, height } });
    const screenshot = path.join(
      outDir,
      `core_pspace_${expectedSource}_${browserName}_${width}x${height}.png`,
    );
    try {
      results.push({
        browser: browserName,
        viewport: `${width}x${height}`,
        url,
        expectedSource,
        ...(await inspect(page, url, expectedSource, screenshot, allowStaticApiErrors)),
      });
    } catch (error) {
      results.push({
        browser: browserName,
        viewport: `${width}x${height}`,
        url,
        expectedSource,
        passed: false,
        failures: ["unhandled_error"],
        error: String(error?.stack || error),
        screenshot,
      });
    }
    await page.close();
    await new Promise((resolve) => setTimeout(resolve, 1500));
  }
  await browser.close();

  const payload = {
    schema: "qa.8093.core-metrics-pspace-live.v1",
    browser: browserName,
    matrix,
    expectedSource,
    passed: results.every((result) => result.passed),
    results,
  };
  const manifest = path.join(outDir, `manifest_${expectedSource}_${browserName}_${matrix}.json`);
  fs.writeFileSync(manifest, JSON.stringify(payload, null, 2), "utf8");
  process.stdout.write(`${JSON.stringify({ passed: payload.passed, manifest })}\n`);
  process.exitCode = payload.passed ? 0 : 1;
}

main().catch((error) => {
  process.stderr.write(`${error?.stack || error}\n`);
  process.exitCode = 1;
});
