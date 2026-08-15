#!/usr/bin/env node
"use strict";

/*
 * REQ-ABC33-CONTEXTUAL-ASSISTANT-20260811
 * Full five-route x 17 engine/viewport acceptance. This is a read-only
 * browser verifier: all model/SSE endpoints are fulfilled inside Playwright.
 */

const fs = require("fs");
const path = require("path");

let playwright;
try {
  playwright = require("playwright");
} catch (_) {
  playwright = require("C:/Users/hmw20/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright");
}

const ROOT = path.resolve(__dirname, "..");
const DEFAULT_BASE_URL = "http://127.0.0.1:18093/frontend_dashboard_v3.server.html";
const ROUTES = ["overview", "diagnosis", "optimization", "trend", "qa"];
const MATRIX = {
  chromium: [[1280, 720], [1366, 768], [1440, 900], [1546, 864], [1920, 1080], [1024, 768], [768, 1024], [390, 844], [375, 667]],
  firefox: [[1920, 1080], [1366, 768], [768, 1024], [390, 844]],
  webkit: [[1920, 1080], [1366, 768], [768, 1024], [390, 844]],
};
const ROUTE_SELECTORS = {
  overview: [".overview-grid", ".overview-right", ".overview-furnace-panel-v12"],
  diagnosis: [".diagnosis-grid", ".diagnosis-hero"],
  optimization: [".optimization-screen", ".optimization-workbench-v10"],
  trend: [".trend-grid", ".trend-screen", ".core-grouped-metrics"],
  qa: [".qa-grid", ".qa-server-shell", ".qa-conv-grid"],
};

function parseArgs(argv) {
  const options = {
    baseUrl: process.env.ABC_VIEWPORT_BASE_URL || DEFAULT_BASE_URL,
    outputDir: process.env.ABC_VIEWPORT_OUTPUT_DIR || path.join(ROOT, "logs", "abc_contextual_assistant_viewports"),
    engine: "all",
    route: "all",
    viewport: "all",
    timeoutMs: 60000,
    headed: false,
    listMatrix: false,
    storageState: process.env.ABC_VIEWPORT_STORAGE_STATE || "",
    retryFailed: "",
    baseUrlExplicit: false,
  };
  for (let index = 2; index < argv.length; index += 1) {
    const arg = argv[index];
    const next = () => {
      if (index + 1 >= argv.length) throw new Error(`${arg} requires a value`);
      index += 1;
      return argv[index];
    };
    if (arg === "--base-url") { options.baseUrl = next(); options.baseUrlExplicit = true; }
    else if (arg === "--output-dir") options.outputDir = path.resolve(next());
    else if (arg === "--engine") options.engine = next();
    else if (arg === "--route") options.route = next();
    else if (arg === "--viewport") options.viewport = next();
    else if (arg === "--timeout-ms") options.timeoutMs = Number(next());
    else if (arg === "--storage-state") options.storageState = path.resolve(next());
    else if (arg === "--retry-failed") options.retryFailed = path.resolve(next());
    else if (arg === "--headed") options.headed = true;
    else if (arg === "--list-matrix") options.listMatrix = true;
    else if (arg === "--help") options.help = true;
    else throw new Error(`unknown argument: ${arg}`);
  }
  if (options.engine !== "all" && !Object.hasOwn(MATRIX, options.engine)) throw new Error(`unsupported engine: ${options.engine}`);
  if (options.route !== "all" && !ROUTES.includes(options.route)) throw new Error(`unsupported route: ${options.route}`);
  if (options.viewport !== "all" && !/^\d+x\d+$/.test(options.viewport)) throw new Error("--viewport must be WIDTHxHEIGHT");
  if (!Number.isFinite(options.timeoutMs) || options.timeoutMs <= 0) throw new Error("--timeout-ms must be positive");
  return options;
}

function usage() {
  return [
    "Usage: node tools/verify_abc_contextual_assistant_viewports.cjs [options]",
    "  --base-url URL       dashboard URL (default local 127.0.0.1:18093)",
    "  --output-dir PATH    report and screenshot directory",
    "  --engine NAME        all|chromium|firefox|webkit",
    "  --route NAME         all|overview|diagnosis|optimization|trend|qa",
    "  --viewport WxH       run one viewport present in the selected engine matrix",
    "  --storage-state PATH Playwright auth storage-state JSON",
    "  --retry-failed PATH rerun only failed rows from a prior 85-row report and merge",
    "  --timeout-ms N       navigation/readiness timeout",
    "  --headed             show browsers",
    "  --list-matrix        print selected combinations without launching",
    "Environment auth: ABC_VIEWPORT_AUTHORIZATION, or ABC_VIEWPORT_BASIC_USER and ABC_VIEWPORT_BASIC_PASSWORD.",
  ].join("\n");
}

function selectedMatrix(options) {
  const engines = options.engine === "all" ? Object.keys(MATRIX) : [options.engine];
  const routes = options.route === "all" ? ROUTES : [options.route];
  return engines.flatMap(engine => MATRIX[engine]
    .filter(([width, height]) => options.viewport === "all" || `${width}x${height}` === options.viewport)
    .flatMap(([width, height]) => routes.map(route => ({ engine, width, height, route }))));
}

function routeUrl(baseUrl, route) {
  const url = new URL(baseUrl);
  url.hash = route;
  return url.toString();
}

function responseJson(route, value, status = 200) {
  return route.fulfill({ status, contentType: "application/json; charset=utf-8", body: JSON.stringify(value) });
}

async function installSafeModelMocks(context, intercepted) {
  await context.route("**/*", async route => {
    const request = route.request();
    const url = new URL(request.url());
    const pathname = url.pathname;
    const method = request.method().toUpperCase();
    const acceptsEventStream = String(request.headers()["accept"] || "").toLowerCase().includes("text/event-stream");
    const knownModelPath = /(?:\/v1\/chat\/completions|\/api\/(?:qa|short-window)\/chat|\/api\/diagnosis\/model-review|\/api\/diagnosis-ai-analysis(?:\/|$)|\/(?:generate|inference)(?:\/|$))/i.test(pathname);
    const record = type => intercepted.push({ type, method, url: `${url.origin}${pathname}`, mocked: true });

    if (pathname === "/v1/chat/completions" || pathname === "/api/qa/chat" || pathname === "/api/short-window/chat" || (acceptsEventStream && knownModelPath)) {
      record("model_or_sse");
      return responseJson(route, {
        ok: true,
        choices: [{ message: { content: "视口验收模拟回答：只读解释，任何工艺调整须经值班工长确认。" } }],
        messages: [{ id: "mock_assistant", role: "assistant", content: "视口验收模拟回答：只读解释。", created_at: "2026-08-12T00:00:00Z" }],
        conversation: { id: "viewport_mock_conversation", title: "ABC规则解释", source_type: "abc_rule", rule_id: "A1", evaluation_id: "viewport_mock" },
        conversations: [],
      });
    }
    if (pathname === "/api/diagnosis/model-review") {
      record("model_review");
      return responseJson(route, { ok: true, model_review: { state: "completed", read_only: true, message: "视口验收模拟复核" } });
    }
    if (pathname === "/api/qa/contextual-conversations" && method === "POST") {
      record("contextual_conversation");
      return responseJson(route, { ok: true, conversation: { id: "viewport_mock_conversation", title: "ABC规则解释", source_type: "abc_rule", rule_id: "A1", evaluation_id: "viewport_mock" } });
    }
    if (/^\/api\/furnace-rules\/[^/]+\/explanation-context$/.test(pathname) && method === "GET") {
      record("deterministic_context_fixture");
      return responseJson(route, {
        ok: true,
        operator_explanation: {
          rule_id: pathname.split("/")[3],
          display_name: "视口验收规则",
          status: "eligible",
          score: 88,
          confidence: 1,
          evaluation_ts: "2026-08-12T00:00:00Z",
          calculation: { terms: [{ term_id: "viewport_fixture", display_name: "模拟确定性因子", semantic: "仅用于上下文助手视口验收", unit: null, raw_value: 0.5, normalized_score_0_100: 50, weight: 100, weighted_points: 50 }] },
          process_guidance: { intervention_order: ["确认数据", "核对趋势", "现场复核", "工长审批", "记录结果"] },
        },
        ai_analysis: "视口验收固定解释；未调用真实模型。",
      });
    }
    if (pathname === "/api/furnace-rules/latest" && method === "GET") {
      record("furnace_rules_latest_fixture");
      return responseJson(route, { ok: true, batch: null, evaluations: [], items: [] });
    }
    if (pathname === "/api/automation/status" && method === "GET") {
      record("automation_status_fixture");
      return responseJson(route, { ok: true, services: [], tasks: [], read_only: true });
    }
    if ((pathname === "/api/short-window/summaries" || pathname === "/api/short-window/conversations") && method === "GET") {
      record("short_window_readonly_fixture");
      return responseJson(route, { ok: true, items: [], conversations: [] });
    }
    if (pathname === "/api/qa/bootstrap" && method === "GET") {
      record("protected_qa_bootstrap_fixture");
      const conversation = { id: "viewport_mock_conversation", title: "ABC规则解释", source_type: "abc_rule", rule_id: "A1", evaluation_id: "viewport_mock", message_count: 2, updated_at: "2026-08-12T00:00:00Z" };
      return responseJson(route, { ok: true, conversation, conversations: [conversation], messages: [{ id: "viewport_question", role: "user", content: "查询最近一小时炉体温度。", created_at: "2026-08-12T00:00:00Z" }, { id: "viewport_context", role: "assistant", content: "规则确定性上下文已载入。\n\n![MCP数据图](/data/mcp_charts/viewport_matrix.png)", created_at: "2026-08-12T00:00:01Z" }], projects: [], report_assets: [] });
    }
    if (pathname === "/data/mcp_charts/viewport_matrix.png" && method === "GET") {
      record("mcp_chart_png_fixture");
      return route.fulfill({ status: 200, contentType: "image/png", body: Buffer.from("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII=", "base64") });
    }
    if (pathname === "/api/qa/projects" && method === "GET") {
      record("protected_qa_projects_fixture");
      return responseJson(route, { ok: true, projects: [], allowed_folders: [], report_assets: [], project_assets: [], folder_assets: [], conversations: [] });
    }
    if (pathname === "/api/ollama/status") {
      record("model_health");
      return responseJson(route, { ok: true, mocked: true });
    }
    if (method !== "GET" && knownModelPath) {
      record("model_safety_catch_all");
      return responseJson(route, { ok: true, mocked: true, content: "视口验收固定模拟响应" });
    }
    if (knownModelPath) {
      record("model_read_safety_catch_all");
      return responseJson(route, { ok: true, mocked: true, status: "completed", state: "completed", analysis: "视口验收固定模拟分析" });
    }
    return route.continue();
  });
}

function contextOptions(options) {
  const result = { viewport: null, deviceScaleFactor: 1, ignoreHTTPSErrors: true };
  if (options.storageState) result.storageState = options.storageState;
  if (process.env.ABC_VIEWPORT_AUTHORIZATION) result.extraHTTPHeaders = { Authorization: process.env.ABC_VIEWPORT_AUTHORIZATION };
  if (process.env.ABC_VIEWPORT_BASIC_USER) {
    result.httpCredentials = {
      username: process.env.ABC_VIEWPORT_BASIC_USER,
      password: process.env.ABC_VIEWPORT_BASIC_PASSWORD || "",
    };
  }
  return result;
}

async function launchBrowser(engine, headed) {
  const launch = { headless: !headed };
  if (engine !== "chromium") return playwright[engine].launch(launch);
  try {
    return await playwright.chromium.launch({ ...launch, channel: "msedge" });
  } catch (_) {
    return playwright.chromium.launch(launch);
  }
}

async function waitForRoute(page, route, timeoutMs) {
  await page.waitForFunction(({ expectedRoute, selectors }) => {
    const hash = location.hash.replace(/^#/, "").split("?")[0];
    const activeNav = document.querySelector(".bottom-nav .nav-btn.active,.bottom-nav [aria-current='page']");
    const main = document.querySelector("main.main,main");
    const specificRoot = selectors.some(selector => document.querySelector(selector));
    return hash === expectedRoute && Boolean(activeNav) && Boolean(specificRoot || (main && (main.innerText || "").trim().length >= 20));
  }, { expectedRoute: route, selectors: ROUTE_SELECTORS[route] }, { timeout: timeoutMs });
}

async function gotoWithRetry(page, url, timeoutMs) {
  let lastError = null;
  for (let attempt = 1; attempt <= 3; attempt += 1) {
    try {
      return await page.goto(url, { waitUntil: "domcontentloaded", timeout: timeoutMs });
    } catch (error) {
      lastError = error;
      if (!/ERR_CONNECTION_RESET|ECONNRESET|Navigation failed because page crashed/i.test(String(error)) || attempt === 3) throw error;
      await page.waitForTimeout(250 * attempt);
    }
  }
  throw lastError;
}

async function dismissAutomaticDiagnosisReview(page) {
  const candidates = page.locator('[role="dialog"],.bfdms-dialog,[class*="modal"]')
    .filter({ hasText: /(?:异常炉况|高炉长人工复核)/ });
  const count = await candidates.count();
  for (let index = 0; index < count; index += 1) {
    const dialog = candidates.nth(index);
    const isTargetAssistant = await dialog.evaluate(element => Boolean(element.closest("#bf-abc33-assistant-dialog"))).catch(() => false);
    if (isTargetAssistant || !await dialog.isVisible().catch(() => false)) continue;
    const title = (await dialog.innerText().catch(() => "")).slice(0, 160);
    const close = dialog.getByRole("button", { name: /(?:关闭|取消|稍后)/ }).first();
    if (await close.count() && await close.isVisible().catch(() => false)) {
      await close.click({ timeout: 3000 });
      await dialog.waitFor({ state: "hidden", timeout: 3000 }).catch(() => {});
      return [{ action: "closed_automatic_diagnosis_review", title }];
    }
  }
  return [];
}

async function activateTargetRoute(page, route, timeoutMs) {
  await page.locator(".bottom-nav").waitFor({ state: "attached", timeout: timeoutMs });
  await page.waitForTimeout(200);
  const dismissed = await dismissAutomaticDiagnosisReview(page);
  await page.evaluate(({ expectedRoute, routeOrder }) => {
    const current = location.hash.replace(/^#/, "").split("?")[0];
    const index = routeOrder.indexOf(expectedRoute);
    const button = document.querySelectorAll(".bottom-nav .nav-btn,.bottom-nav button")[index];
    if (current !== expectedRoute || !button?.classList.contains("active")) button?.click();
    if (location.hash.replace(/^#/, "").split("?")[0] !== expectedRoute) location.hash = expectedRoute;
  }, { expectedRoute: route, routeOrder: ROUTES });
  await page.waitForTimeout(200);
  dismissed.push(...await dismissAutomaticDiagnosisReview(page));
  return dismissed;
}

async function inspectPage(page, route) {
  return page.evaluate(({ expectedRoute, selectors }) => {
    const root = document.documentElement;
    const main = document.querySelector("main.main, main");
    const nav = document.querySelector(".bottom-nav");
    const activeNav = document.querySelector(".bottom-nav .nav-btn.active, .bottom-nav [aria-current='page']");
    const specificRouteRoot = selectors.map(selector => document.querySelector(selector)).find(Boolean) || null;
    const hashRoute = location.hash.replace(/^#/, "").split("?")[0];
    const routeRoot = specificRouteRoot || (hashRoute === expectedRoute && activeNav ? main : null);
    const text = (routeRoot?.innerText || main?.innerText || "").trim();
    const visible = element => Boolean(element && getComputedStyle(element).visibility !== "hidden" && getComputedStyle(element).display !== "none" && element.getBoundingClientRect().width > 0 && element.getBoundingClientRect().height > 0);
    const loading = [...document.querySelectorAll("[aria-busy='true'],.loading,.is-loading")].filter(visible).length;
    const empty = [...document.querySelectorAll(".empty,.qa-server-empty,.empty-state")].filter(visible).length;
    const error = [...document.querySelectorAll(".error,.text-bad,.qa-server-error,.error-state")].filter(visible).length;
    const navRect = nav?.getBoundingClientRect();
    const mainRect = main?.getBoundingClientRect();
    const routeRect = routeRoot?.getBoundingClientRect();
    const mainStyle = main ? getComputedStyle(main) : null;
    const mainBottomPadding = mainStyle ? parseFloat(mainStyle.paddingBottom) || 0 : 0;
    const navHeight = navRect?.height || 0;
    const navPosition = nav ? getComputedStyle(nav).position : "missing";
    const navOverlays = navPosition === "fixed" || navPosition === "sticky";
    const mainEndsAboveNav = Boolean(mainRect && navRect && mainRect.bottom <= navRect.top + 2);
    const routeEndsAboveNav = Boolean(routeRect && navRect && routeRect.bottom <= navRect.top + 2);
    const paddingProtectsContent = mainBottomPadding + 2 >= navHeight;
    const routeButtons = [...document.querySelectorAll(".bottom-nav button")];
    return {
      routeMounted: Boolean(routeRoot),
      hashRoute,
      specificRouteSelectorMatched: Boolean(specificRouteRoot),
      activeNavText: activeNav?.textContent?.trim() || "",
      keyRouteReachable: routeButtons.length >= 5 && Boolean(activeNav),
      horizontalOverflow: root.scrollWidth > root.clientWidth + 1,
      scrollWidth: root.scrollWidth,
      clientWidth: root.clientWidth,
      bottomNavVisible: visible(nav),
      bottomNavNotCovering: !nav || !navOverlays || mainEndsAboveNav || routeEndsAboveNav || paddingProtectsContent,
      bottomNavGeometry: { navPosition, navHeight, mainBottomPadding, mainBottom: mainRect?.bottom ?? null, routeBottom: routeRect?.bottom ?? null, navTop: navRect?.top ?? null, mainEndsAboveNav, routeEndsAboveNav, paddingProtectsContent },
      chineseReadable: /[\u3400-\u9fff]/.test(text),
      textLength: text.length,
      dataState: error ? "error" : loading ? "loading" : empty ? "empty" : text ? "ready" : "missing",
      stateCounts: { loading, empty, error },
      viewport: { width: innerWidth, height: innerHeight },
      expectedRoute,
    };
  }, { expectedRoute: route, selectors: ROUTE_SELECTORS[route] });
}

async function inspectContextualAssistant(page, route) {
  if (route === "optimization") {
    const entry = page.locator(".abc33-entry-overview").first();
    if (await entry.count() && await entry.isVisible().catch(() => false)) {
      await entry.click().catch(() => {});
      await page.waitForTimeout(100);
    }
    const trigger = page.locator(".abc33-assistant-open").first();
    const triggerCount = await page.locator(".abc33-assistant-open").count();
    let dialogState = "not_opened";
    let deterministicContextVisible = false;
    if (triggerCount && await trigger.isVisible().catch(() => false)) {
      await trigger.click();
      await page.locator("#bf-abc33-assistant-dialog").waitFor({ state: "visible", timeout: 10000 });
      await page.waitForFunction(() => !["opening", "analysis_preparing", "analysis_streaming"].includes(document.querySelector("#bf-abc33-assistant-dialog")?.dataset.state), null, { timeout: 10000 }).catch(() => {});
      const details = await page.locator("#bf-abc33-assistant-dialog").evaluate(element => ({
        state: element.dataset.state || "unknown",
        text: element.textContent || "",
      }));
      dialogState = details.state;
      deterministicContextVisible = details.text.includes("本次规则上下文") && details.text.includes("计算项与物理语义");
    }
    return { checked: true, triggerCount, dialogState, deterministicContextVisible };
  }
  if (route === "qa") {
    const details = await page.evaluate(() => ({
      shellVisible: Boolean(document.querySelector(".qa-grid,.qa-server-shell,.qa-conv-grid")),
      composerVisible: Boolean(document.querySelector(".qa-server-compose textarea,.qa-conv-composer textarea,.chat-input")),
      contextUiVisible: Boolean(document.querySelector(".qa-context-basket,.qa-summary-panel,.qa-context-source-badge,.qa-mini-title")),
      abcSourceFilter: [...document.querySelectorAll("button")].some(button => /参数优化炉框|规则解释/.test(button.textContent || "")),
      mcpTemplateVisible: [...document.querySelectorAll(".qa-prompt-use")].some(button => /矩阵热度图/.test(button.textContent || "")),
      promptScrollerVisible: Boolean(document.querySelector(".qa-prompt-scroll")),
      promptScrollerKeyboardAccessible: document.querySelector(".qa-prompt-scroll")?.getAttribute("tabindex") === "0",
      originalCommonVisible: Boolean(document.querySelector('[data-prompt-section="original-common"] .qa-prompt-use')),
      mcpCommonVisible: Boolean(document.querySelector('[data-prompt-section="mcp-common"] .qa-prompt-use')),
      customPromptVisible: Boolean(document.querySelector(".qa-prompt-custom input")),
      mcpChartVisible: Boolean(document.querySelector('.qa-mcp-chart img[src="/data/mcp_charts/viewport_matrix.png"],.qa-md-images img[src="/data/mcp_charts/viewport_matrix.png"]')),
      copyQuestionVisible: Boolean(document.querySelector('.qa-message-copy[data-copy-role="question"][aria-label="复制问题"]')),
      copyAnswerVisible: Boolean(document.querySelector('.qa-message-copy[data-copy-role="answer"][aria-label="复制回复"]')),
    }));
    let customPromptPersisted = false;
    let relatedQuestionsVisible = false;
    let promptScrollerManuallyScrollable = false;
    let copiedQuestionBody = false;
    let copiedAnswerBodyAndChart = false;
    await page.evaluate(() => {
      window.__BF_VIEWPORT_CLIPBOARD__ = [];
      try { Object.defineProperty(navigator, "clipboard", { configurable: true, value: { writeText: async text => window.__BF_VIEWPORT_CLIPBOARD__.push(String(text)) } }) } catch (error) { }
      const originalExecCommand = document.execCommand?.bind(document);
      document.execCommand = command => {
        if (String(command).toLowerCase() === "copy") {
          const textarea = document.activeElement?.tagName === "TEXTAREA" ? document.activeElement : document.querySelector("textarea[readonly]");
          if (textarea) window.__BF_VIEWPORT_CLIPBOARD__.push(String(textarea.value || ""));
          return true;
        }
        return originalExecCommand ? originalExecCommand(command) : false;
      };
    });
    const copyQuestion = page.locator('.qa-message-copy[data-copy-role="question"]').first();
    if (await copyQuestion.isVisible().catch(() => false)) {
      await copyQuestion.click();
      copiedQuestionBody = await page.evaluate(() => (window.__BF_VIEWPORT_CLIPBOARD__ || []).some(text => text === "查询最近一小时炉体温度。"));
    }
    const copyAnswer = page.locator('.qa-message-copy[data-copy-role="answer"]').first();
    if (await copyAnswer.isVisible().catch(() => false)) {
      await copyAnswer.click();
      copiedAnswerBodyAndChart = await page.evaluate(() => (window.__BF_VIEWPORT_CLIPBOARD__ || []).some(text => text.includes("规则确定性上下文已载入。") && text.includes("/data/mcp_charts/viewport_matrix.png") && !text.includes("2026/")));
    }
    promptScrollerManuallyScrollable = await page.evaluate(() => {
      const scroller = document.querySelector(".qa-prompt-scroll");
      if (!scroller) return false;
      const overflowY = getComputedStyle(scroller).overflowY;
      if (!/auto|scroll/.test(overflowY)) return false;
      if (scroller.scrollHeight <= scroller.clientHeight) return true;
      scroller.scrollTop = scroller.scrollHeight;
      const changed = scroller.scrollTop > 0;
      scroller.scrollTop = 0;
      return changed;
    });
    const customInput = page.locator(".qa-prompt-custom input").first();
    if (await customInput.isVisible().catch(() => false)) {
      const customText = "自定义视口验收问题：查询最近十分钟顶压。";
      await customInput.fill(customText);
      await page.locator(".qa-prompt-custom button").first().click();
      customPromptPersisted = await page.evaluate(text => {
        const value = JSON.parse(localStorage.getItem("bf_qa_prompt_preferences_v1") || "{}");
        return (value.custom || []).includes(text) && (value.pinned || []).includes(text);
      }, customText);
      await page.evaluate(() => document.dispatchEvent(new CustomEvent("bf:qa-related-mcp-questions", { detail: { questions: ["相关视口验收问题"] } })));
      await page.waitForTimeout(120);
      relatedQuestionsVisible = await page.getByText("相关视口验收问题", { exact: true }).isVisible().catch(() => false);
    }
    return { checked: true, ...details, customPromptPersisted, relatedQuestionsVisible, promptScrollerManuallyScrollable, copiedQuestionBody, copiedAnswerBodyAndChart };
  }
  return { checked: false };
}

function rowFailures(layout, assistant, consoleErrors, pageErrors) {
  const failures = [];
  if (!layout.routeMounted || layout.hashRoute !== layout.expectedRoute) failures.push("key route did not mount");
  if (!layout.keyRouteReachable) failures.push("formal navigation is not reachable");
  if (layout.horizontalOverflow) failures.push("horizontal overflow detected");
  if (!layout.bottomNavVisible || !layout.bottomNavNotCovering) failures.push("bottom navigation is hidden or covers main content");
  if (!layout.chineseReadable || layout.textLength < 20) failures.push("Chinese route content is missing or unreadable");
  if (consoleErrors.length) failures.push("console errors detected");
  if (pageErrors.length) failures.push("page errors detected");
  if (layout.expectedRoute === "optimization" && (!assistant.triggerCount || !assistant.deterministicContextVisible)) failures.push("optimization contextual assistant entry/dialog incomplete");
  if (layout.expectedRoute === "qa" && (!assistant.shellVisible || !assistant.composerVisible || !assistant.contextUiVisible || !assistant.abcSourceFilter)) failures.push("qa contextual assistant workspace incomplete");
  if (layout.expectedRoute === "qa" && (!assistant.mcpTemplateVisible || !assistant.promptScrollerVisible || !assistant.customPromptVisible || !assistant.customPromptPersisted || !assistant.relatedQuestionsVisible || !assistant.mcpChartVisible)) failures.push("qa MCP visual recommendations are incomplete");
  if (layout.expectedRoute === "qa" && (!assistant.originalCommonVisible || !assistant.mcpCommonVisible || !assistant.promptScrollerKeyboardAccessible || !assistant.promptScrollerManuallyScrollable)) failures.push("qa original/MCP recommendation sections or manual scrolling are incomplete");
  if (layout.expectedRoute === "qa" && (!assistant.copyQuestionVisible || !assistant.copyAnswerVisible || !assistant.copiedQuestionBody || !assistant.copiedAnswerBodyAndChart)) failures.push("qa question/answer copy controls are incomplete");
  return failures;
}

async function verifyOneAttempt(browser, item, options) {
  const context = await browser.newContext({ ...contextOptions(options), viewport: { width: item.width, height: item.height } });
  const intercepted = [];
  const consoleErrors = [];
  const consoleNotes = [];
  const pageErrors = [];
  const httpErrors = [];
  await installSafeModelMocks(context, intercepted);
  const page = await context.newPage();
  page.on("console", message => {
    if (message.type() !== "error") return;
    const text = message.text();
    if (/code generator has deoptimised the styling|Babel.*deoptimised/i.test(text)) consoleNotes.push(text);
    else if (["127.0.0.1", "localhost"].includes(new URL(options.baseUrl).hostname) && /ws:\/\/(?:127\.0\.0\.1|localhost):(?:8768|8770)\//i.test(text) && /refused|can.?t establish|network error|error code 7/i.test(text)) consoleNotes.push(`local fixture has no live data WebSocket: ${text}`);
    else consoleErrors.push(text);
  });
  page.on("pageerror", error => pageErrors.push(String(error?.stack || error)));
  page.on("response", response => { if (response.status() >= 400) httpErrors.push({ status: response.status(), url: response.url() }); });
  const url = routeUrl(options.baseUrl, item.route);
  let layout = { expectedRoute: item.route, dataState: "navigation_failed" };
  let assistant = { checked: ["optimization", "qa"].includes(item.route), error: null };
  let dismissedOverlays = [];
  const runtimeErrors = [];
  try {
    await gotoWithRetry(page, url, options.timeoutMs);
    dismissedOverlays = await activateTargetRoute(page, item.route, options.timeoutMs);
    await waitForRoute(page, item.route, options.timeoutMs);
    await page.waitForTimeout(250);
    layout = await inspectPage(page, item.route);
    assistant = await inspectContextualAssistant(page, item.route);
  } catch (error) {
    runtimeErrors.push(String(error?.stack || error));
  }
  const screenshot = path.join(options.outputDir, `${item.engine}_${item.route}_${item.width}x${item.height}.png`);
  await page.screenshot({ path: screenshot, fullPage: false }).catch(error => runtimeErrors.push(`screenshot: ${error}`));
  const failures = [...rowFailures(layout, assistant, consoleErrors, pageErrors), ...runtimeErrors];
  await context.close();
  return {
    engine: item.engine,
    viewport: { width: item.width, height: item.height },
    route: item.route,
    url,
    data_state: layout.dataState,
    screenshot,
    passed: failures.length === 0,
    layout,
    contextual_assistant: assistant,
    dismissed_overlays: dismissedOverlays,
    model_requests: { real_sent: 0, intercepted },
    errors: { failures, console: consoleErrors, console_notes: consoleNotes, pageerror: pageErrors, http: httpErrors },
  };
}

function transientCombinationFailure(row) {
  const failureText = (row?.errors?.failures || []).join("\n");
  return /ERR_CONNECTION_RESET|ERR_NO_BUFFER_SPACE|page\.goto: Timeout \d+ms exceeded|page\.goto:.*(?:navigation|timeout)/i.test(failureText);
}

function firstFailureSummary(row) {
  return {
    data_state: row.data_state,
    failures: row.errors?.failures || [],
    console: row.errors?.console || [],
    pageerror: row.errors?.pageerror || [],
    http: row.errors?.http || [],
  };
}

async function verifyOne(browser, item, options) {
  const first = await verifyOneAttempt(browser, item, options);
  if (options.disableAttemptRetry || !transientCombinationFailure(first)) return { ...first, retry_count: 0, first_failure: null };
  const retried = await verifyOneAttempt(browser, item, options);
  return { ...retried, retry_count: 1, first_failure: firstFailureSummary(first) };
}

async function main() {
  const options = parseArgs(process.argv);
  if (options.help) {
    process.stdout.write(`${usage()}\n`);
    return;
  }
  let resumeReport = null;
  if (options.retryFailed) {
    resumeReport = JSON.parse(fs.readFileSync(options.retryFailed, "utf8"));
    if (!Array.isArray(resumeReport.rows) || resumeReport.rows.length !== 85) throw new Error("--retry-failed requires a trusted 85-row report");
    if (!options.baseUrlExplicit && resumeReport.base_url) options.baseUrl = resumeReport.base_url;
    options.disableAttemptRetry = true;
  }
  let matrix = selectedMatrix(options);
  if (resumeReport) {
    const failedKeys = new Set(resumeReport.rows.filter(row => !row.passed).map(row => `${row.engine}|${row.viewport.width}x${row.viewport.height}|${row.route}`));
    matrix = matrix.filter(row => failedKeys.has(`${row.engine}|${row.width}x${row.height}|${row.route}`));
    if (!matrix.length && failedKeys.size) throw new Error("failed rows do not match the selected matrix filters");
  }
  if (options.listMatrix) {
    process.stdout.write(`${JSON.stringify({ schema_version: "abc_contextual_assistant_viewports.matrix.v1", total: matrix.length, matrix }, null, 2)}\n`);
    return;
  }
  fs.mkdirSync(options.outputDir, { recursive: true });
  const rows = [];
  const engines = [...new Set(matrix.map(item => item.engine))];
  for (const engine of engines) {
    const browser = await launchBrowser(engine, options.headed);
    try {
      for (const item of matrix.filter(row => row.engine === engine)) rows.push(await verifyOne(browser, item, options));
    } finally {
      await browser.close();
    }
  }
  let finalRows = rows;
  if (resumeReport) {
    const replacements = new Map(rows.map(row => [`${row.engine}|${row.viewport.width}x${row.viewport.height}|${row.route}`, row]));
    finalRows = resumeReport.rows.map(previous => {
      const key = `${previous.engine}|${previous.viewport.width}x${previous.viewport.height}|${previous.route}`;
      const replacement = replacements.get(key);
      return replacement ? { ...replacement, retry_count: 1, first_failure: firstFailureSummary(previous) } : previous;
    });
  }
  const report = {
    schema_version: "abc_contextual_assistant_viewports.full.v1",
    requirement_id: "REQ-ABC33-CONTEXTUAL-ASSISTANT-20260811",
    generated_at: new Date().toISOString(),
    base_url: options.baseUrl,
    expected_full_matrix: 85,
    selected_checks: finalRows.length,
    passed: finalRows.every(row => row.passed),
    summary: { passed: finalRows.filter(row => row.passed).length, failed: finalRows.filter(row => !row.passed).length },
    resumed_from: options.retryFailed || null,
    rerun_checks: rows.length,
    rows: finalRows,
  };
  const reportPath = path.join(options.outputDir, "report.json");
  fs.writeFileSync(reportPath, JSON.stringify(report, null, 2), "utf8");
  process.stdout.write(`${JSON.stringify({ passed: report.passed, checks: rows.length, summary: report.summary, report: reportPath }, null, 2)}\n`);
  process.exitCode = report.passed ? 0 : 1;
}

main().catch(error => {
  process.stderr.write(`${error?.stack || error}\n`);
  process.exitCode = 2;
});
