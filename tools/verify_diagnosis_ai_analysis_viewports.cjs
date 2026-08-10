#!/usr/bin/env node
"use strict";

const { chromium, firefox, webkit } = require("playwright");

const baseUrl = process.argv[2] || "http://127.0.0.1:18093/frontend_dashboard_v3.server.html?t=ai-cross-engine#diagnosis";
const engineFilter = process.argv[3] || "all";
const validationMode = process.argv[4] || "completed";
const representativeViewports = [
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

async function gotoWithRetry(page, url) {
  let lastError;
  for (let attempt = 1; attempt <= 5; attempt += 1) {
    try {
      return await page.goto(url, { waitUntil: "domcontentloaded", timeout: 60000 });
    } catch (error) {
      lastError = error;
      if (attempt < 5) await new Promise(resolve => setTimeout(resolve, 2000));
    }
  }
  throw lastError;
}

async function waitForTargetCard(page, url) {
  let lastError;
  for (let attempt = 1; attempt <= 5; attempt += 1) {
    const card = page.getByRole("button", {
      name: "查看热制度下行智能分析并可提交高炉长评分",
      exact: true,
    });
    try {
      await card.waitFor({ state: "visible", timeout: 20000 });
      return card;
    } catch (error) {
      lastError = error;
      if (attempt < 5) {
        await new Promise(resolve => setTimeout(resolve, 2000));
        await gotoWithRetry(page, url);
      }
    }
  }
  throw lastError;
}

async function verifyEngine(name, browserType, viewports, launchOptions = {}) {
  const browser = await browserType.launch({ headless: true, ...launchOptions });
  const results = [];
  try {
    for (const viewport of viewports) {
      const page = await browser.newPage({ viewport });
      const consoleErrors = [];
      const httpErrors = [];
      page.on("console", message => {
        if (message.type() === "error") consoleErrors.push(message.text());
      });
      page.on("response", response => {
        if (response.status() >= 400) httpErrors.push(`${response.status()} ${response.url()}`);
      });
      await gotoWithRetry(page, baseUrl);
      const card = await waitForTargetCard(page, baseUrl);
      await card.click();
      const coreSummary = page.locator(".bfdms-core-evidence > summary");
      if (validationMode === "completed") {
        await page.locator(".bfdms-ai-state.state-completed").waitFor({
          state: "visible",
          timeout: 240000,
        });
      } else {
        await coreSummary.waitFor({ state: "visible", timeout: 30000 });
      }
      if (await coreSummary.count() !== 1) throw new Error("19项核心变量展开入口缺失或重复");
      await coreSummary.click();
      const combinedTop = page.getByRole("button", {
        name: "查看综合顶温60分钟曲线",
        exact: true,
      });
      if (await combinedTop.count() !== 1) throw new Error("综合顶温曲线入口缺失或重复");
      await combinedTop.click();
      await page.locator(".bfdms-core-chart svg").waitFor({
        state: "visible",
        timeout: 5000,
      });
      const layout = await page.evaluate(() => {
        const dialog = document.querySelector(".bfdms-dialog");
        const scroll = document.querySelector(".bfdms-scroll");
        const form = document.querySelector(".bfdms-form");
        const auth = document.querySelector(".bfdms-auth");
        const analysis = document.querySelector(".bfdms-ai-body");
        const rect = dialog && dialog.getBoundingClientRect();
        return {
          pageOverflow: document.documentElement.scrollWidth > document.documentElement.clientWidth + 1,
          dialogFits: Boolean(rect && rect.left >= -1 && rect.right <= innerWidth + 1 && rect.top >= -1 && rect.bottom <= innerHeight + 1),
          scrollOverflowY: scroll ? getComputedStyle(scroll).overflowY : "missing",
          formVisible: Boolean(form && getComputedStyle(form).display !== "none"),
          authHidden: Boolean(auth && getComputedStyle(auth).display === "none"),
          hasAnalysis: Boolean(
            analysis &&
            analysis.textContent.includes("智能助手判断") &&
            analysis.textContent.includes("不是概率") &&
            analysis.textContent.includes("为什么得到这个分数") &&
            analysis.textContent.includes("调剂引擎1建议依据") &&
            analysis.textContent.includes("知识库依据与指导")
          ),
          hasVariableCards: Boolean(document.querySelector(".bfdms-ai-driver")),
          hasActionCards: Boolean(document.querySelector(".bfdms-ai-action")),
          hasKnowledgeCards: Boolean(document.querySelector(".bfdms-ai-knowledge-list article")),
          coreDetailsOpen: Boolean(document.querySelector(".bfdms-core-evidence[open]")),
          coreVariableCount: document.querySelectorAll(".bfdms-core-card").length,
          coreSelectedCount: document.querySelectorAll(".bfdms-core-card.is-selected").length,
          coreChartVisible: Boolean(document.querySelector(".bfdms-core-chart svg")),
          coreChartText: document.querySelector(".bfdms-core-chart")?.textContent || "",
          submitUsable: Boolean(document.querySelector(".bfdms-submit:not([disabled])")),
        };
      });
      const featureErrors = consoleErrors.filter(text =>
        !text.includes("code generator has deoptimised the styling")
      );
      const completedContentPassed = validationMode !== "completed" ||
        (layout.hasAnalysis && layout.hasVariableCards &&
        layout.hasActionCards && layout.hasKnowledgeCards);
      const passed = !layout.pageOverflow && layout.dialogFits &&
        layout.scrollOverflowY === "auto" && layout.formVisible &&
        layout.authHidden && completedContentPassed && layout.coreDetailsOpen &&
        layout.coreVariableCount === 19 && layout.coreSelectedCount > 0 &&
        layout.coreChartVisible && layout.coreChartText.includes("综合顶温") &&
        layout.coreChartText.includes("近5分钟") && layout.submitUsable &&
        featureErrors.length === 0;
      results.push({ engine: name, viewport, passed, ...layout, featureErrors, consoleErrors, httpErrors });
      await page.close();
    }
  } finally {
    await browser.close();
  }
  return results;
}

(async () => {
  const rows = [];
  if (engineFilter === "all" || engineFilter === "chromium") {
    rows.push(...(await verifyEngine("chromium", chromium, chromiumViewports, {
      executablePath: "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe",
    })));
  }
  if (engineFilter === "all" || engineFilter === "firefox") {
    rows.push(...(await verifyEngine("firefox", firefox, representativeViewports)));
  }
  if (engineFilter === "all" || engineFilter === "webkit") {
    rows.push(...(await verifyEngine("webkit", webkit, representativeViewports)));
  }
  const report = {
    schema: "diagnosis-ai-analysis.cross-engine.v1",
    validationMode,
    passed: rows.every(row => row.passed),
    total: rows.length,
    rows,
  };
  process.stdout.write(`${JSON.stringify(report, null, 2)}\n`);
  process.exitCode = report.passed ? 0 : 1;
})().catch(error => {
  process.stderr.write(`${error.stack || error}\n`);
  process.exitCode = 2;
});
