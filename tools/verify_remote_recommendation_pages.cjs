#!/usr/bin/env node
"use strict";

const fs = require("fs");
const path = require("path");
const { chromium, firefox, webkit } = require("playwright");

const defaultUrls = [
  "http://10.30.220.12:8093/?recommendation_acceptance=20260806#optimization",
  "http://10.30.220.12:8094/?recommendation_acceptance=20260806#optimization",
];
const urls = process.argv.slice(2).length ? process.argv.slice(2) : defaultUrls;
const representative = [
  { width: 1920, height: 1080 },
  { width: 1366, height: 768 },
  { width: 768, height: 1024 },
  { width: 390, height: 844 },
];
const chromiumViewports = [
  { width: 1280, height: 720 },
  { width: 1366, height: 768 },
  { width: 1440, height: 900 },
  { width: 1546, height: 864 },
  { width: 1920, height: 1080 },
  { width: 1024, height: 768 },
  { width: 768, height: 1024 },
  { width: 390, height: 844 },
  { width: 375, height: 667 },
];

async function gotoWithRetry(page, url, attempts = 3) {
  let lastError;
  for (let attempt = 1; attempt <= attempts; attempt += 1) {
    try {
      await page.goto(url, { waitUntil: "domcontentloaded", timeout: 90000 });
      return;
    } catch (error) {
      lastError = error;
      if (attempt === attempts) break;
      await page.waitForTimeout(1200 * attempt);
    }
  }
  throw lastError;
}

async function verify(browserName, browserType, viewports) {
  const browser = await browserType.launch({ headless: true });
  const results = [];
  try {
    for (const url of urls) {
      for (const viewport of viewports) {
        const page = await browser.newPage({ viewport });
        const consoleErrors = [];
        page.on("console", message => {
          if (message.type() === "error") consoleErrors.push(message.text());
        });
        const pageErrors = [];
        page.on("pageerror", error => pageErrors.push(String(error)));
        await page.route("**/api/diagnosis/model-review", route => route.fulfill({
          status: 200,
          contentType: "application/json",
          body: JSON.stringify({ ok: true, model_review: { schema_version: "diagnosis_model_review.v1", state: "completed", reviewed_label: "cold", verdict: "agree", rule_score: 80, model_support_score: 88, summary: "浏览器布局验收使用只读固定复核结果。", supporting_evidence: [], contradicting_evidence: [], missing_data: [], attention_items: [], manual_review_recommended: false, read_only: true, model_meta: { cache_hit: true, read_only: true } } }),
        }));
        await page.route(/\.(glb|gltf)(\?.*)?$/i, route => route.abort());
        await gotoWithRetry(page, url);
        await page.waitForSelector(".bf-visual-recommendation-page", { state: "attached", timeout: 120000 });
        await page.waitForFunction(() => document.querySelectorAll(".bf-condition-switch-v2").length === 8, null, { timeout: 120000 });
        await page.locator('[data-condition-label="edge"]').click();
        await page.waitForFunction(() => document.querySelector(".bf-visual-recommendation-page")?.getAttribute("data-selected-condition") === "edge", null, { timeout: 30000 });
        await page.getByRole("button", { name: "展开19项证据与曲线", exact: true }).click();
        await page.waitForFunction(() => document.querySelectorAll(".bf-core-evidence-card-v2").length === 19, null, { timeout: 30000 });
        await page.getByRole("button", { name: "查看完整动作依据", exact: true }).click();
        await page.waitForSelector(".bf-workbench-drawer", { state: "visible", timeout: 30000 });
        const state = await page.evaluate(() => {
          const root = document.querySelector(".bf-visual-recommendation-page");
          const drawer = document.querySelector(".bf-workbench-drawer");
          const statuses = [...drawer.querySelectorAll(".bf-action-audit")]
            .map(node => [...node.classList].find(name => name.startsWith("status-")))
            .filter(Boolean);
          const fields = ["原文章节", "触发证据", "前置条件", "阻断原因", "调剂幅度", "执行顺序", "缺失数据", "观察窗口", "审批要求"];
          const drawerText = drawer.textContent || "";
          const primaryCharts = [...document.querySelectorAll(".bf-primary-evidence-spark")].map(node => node.getBoundingClientRect());
          const coreCards = [...document.querySelectorAll(".bf-core-evidence-card-v2")];
          const coreIds = coreCards.map(node => node.getAttribute("data-core-evidence-id"));
          const top = document.querySelector(".opt-cockpit-top")?.getBoundingClientRect();
          const bottom = document.querySelector(".opt-cockpit-bottom")?.getBoundingClientRect();
          return {
            selected: root?.getAttribute("data-selected-condition"),
            selectionMode: root?.getAttribute("data-selection-mode"),
            conditionCount: document.querySelectorAll(".bf-condition-switch-v2").length,
            primaryCount: primaryCharts.length,
            primaryChartsPositive: primaryCharts.every(rect => rect.width > 0 && rect.height >= 30),
            coreCount: coreCards.length,
            uniqueCoreCount: new Set(coreIds).size,
            actionCount: drawer.querySelectorAll(".bf-action-audit").length,
            statuses,
            allAuditFields: fields.every(field => drawerText.includes(field)),
            modelSummary: !!document.querySelector(".bf-model-compact-v2"),
            auditDrawer: !!drawer,
            topHeight: top?.height || 0,
            bottomHeight: bottom?.height || 0,
            horizontalOverflow: document.documentElement.scrollWidth > window.innerWidth + 1,
            multiVisible: !!root?.getClientRects().length,
          };
        });
        const allowedStatuses = new Set(["status-eligible", "status-blocked", "status-needs_data", "status-manual_confirm"]);
        const relevantConsoleErrors = consoleErrors.filter(message => !message.includes("deoptimised the styling") && !message.includes("ERR_FAILED"));
        const passed = state.multiVisible && state.selected === "edge" && state.selectionMode === "manual" && state.conditionCount === 8 && state.primaryCount === 4 && state.primaryChartsPositive && state.coreCount === 19 && state.uniqueCoreCount === 19 && state.actionCount > 0 && state.modelSummary && state.auditDrawer && state.allAuditFields && state.topHeight >= 280 && state.bottomHeight >= 250 && !state.horizontalOverflow && pageErrors.length === 0 && relevantConsoleErrors.length === 0 && state.statuses.every(item => allowedStatuses.has(item));
        results.push({ browserName, url, viewport, passed, consoleErrors: relevantConsoleErrors, pageErrors, ...state });
        await page.close();
      }
    }
  } finally {
    await browser.close();
  }
  return results;
}

(async () => {
  const results = [];
  results.push(...await verify("chromium", chromium, chromiumViewports));
  results.push(...await verify("firefox", firefox, representative));
  results.push(...await verify("webkit", webkit, representative));
  const report = { ok: results.every(item => item.passed), checked: results.length, results };
  const output = path.resolve(process.env.BF_RECOMMENDATION_VISUAL_REPORT || path.join("logs", "acceptance", "8093_8094_recommendation_visual_20260806.json"));
  fs.mkdirSync(path.dirname(output), { recursive: true });
  fs.writeFileSync(output, JSON.stringify(report, null, 2), "utf8");
  process.stdout.write(JSON.stringify({ ok: report.ok, checked: report.checked, output }, null, 2));
  if (!report.ok) process.exitCode = 1;
})().catch(error => {
  console.error(error);
  process.exitCode = 1;
});
