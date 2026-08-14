#!/usr/bin/env node
"use strict";

const fs = require("fs");
const path = require("path");

let playwright;
try {
  playwright = require("playwright");
} catch (_) {
  playwright = require("C:/Users/hmw20/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright");
}

const baseUrl = process.argv[2] || "http://10.30.220.12:8093/高炉前端数据/frontend_dashboard_v3.server.html#qa";
const artifactPath = process.argv[3];
const outputPath = process.argv[4] || path.resolve(".tmp/8093-guest-frontend-matrix.json");
if (!artifactPath) throw new Error("artifact path is required");
const html = fs.readFileSync(artifactPath, "utf8");

const matrix = {
  chromium: [[1280,720],[1366,768],[1440,900],[1546,864],[1920,1080],[1024,768],[768,1024],[390,844],[375,667]],
  firefox: [[1920,1080],[1366,768],[768,1024],[390,844]],
  webkit: [[1920,1080],[1366,768],[768,1024],[390,844]],
};

async function verify(engineName, browser, viewport) {
  const context = await browser.newContext({ viewport: { width: viewport[0], height: viewport[1] } });
  const page = await context.newPage();
  const pageErrors = [];
  const consoleErrors = [];
  let chatPosts = 0;
  page.on("pageerror", error => pageErrors.push(String(error)));
  page.on("console", message => {
    if (message.type() === "error" && !/favicon|websocket|\[BABEL\] Note: The code generator has deoptimised the styling/i.test(message.text())) consoleErrors.push(message.text());
  });
  await context.route("**/*", async route => {
    const request = route.request();
    if (request.method().toUpperCase() === "POST" && request.url().includes("/api/qa/chat")) chatPosts += 1;
    if (request.resourceType() === "document" && request.url().includes("frontend_dashboard_v3.server.html")) {
      return route.fulfill({ status: 200, contentType: "text/html; charset=utf-8", body: html });
    }
    return route.continue();
  });
  try {
    await page.goto(baseUrl, { waitUntil: "domcontentloaded", timeout: 30000 });
    await page.getByText("登录私有模式（可选）", { exact: true }).waitFor({ state: "visible", timeout: 30000 });
    const initialGuest = await page.locator(".qa-context-source-badge", { hasText: "匿名访客" }).isVisible();
    const forcedLogin = await page.locator(".qa-session-login-card").isVisible().catch(() => false);
    const overflowBefore = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
    await page.getByText("登录私有模式（可选）", { exact: true }).click();
    await page.getByText("登录私有会话（可选）", { exact: true }).waitFor({ state: "visible", timeout: 10000 });
    await Promise.all([
      page.waitForNavigation({ waitUntil: "domcontentloaded", timeout: 30000 }),
      page.getByText("继续匿名使用", { exact: true }).click(),
    ]);
    await page.getByText("登录私有模式（可选）", { exact: true }).waitFor({ state: "visible", timeout: 30000 });
    const returnedGuest = await page.locator(".qa-context-source-badge", { hasText: "匿名访客" }).isVisible();
    const dialogClosed = !await page.locator(".qa-session-login-card").isVisible().catch(() => false);
    const overflowAfter = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
    return {
      engine: engineName,
      viewport: `${viewport[0]}x${viewport[1]}`,
      ok: initialGuest && !forcedLogin && returnedGuest && dialogClosed && chatPosts === 0
        && overflowBefore <= 1 && overflowAfter <= 1 && pageErrors.length === 0 && consoleErrors.length === 0,
      initial_guest: initialGuest,
      forced_login: forcedLogin,
      returned_guest: returnedGuest,
      dialog_closed: dialogClosed,
      chat_posts: chatPosts,
      overflow_before: overflowBefore,
      overflow_after: overflowAfter,
      page_errors: pageErrors,
      console_errors: consoleErrors,
    };
  } catch (error) {
    return {
      engine: engineName,
      viewport: `${viewport[0]}x${viewport[1]}`,
      ok: false,
      error: String(error && error.stack || error),
      chat_posts: chatPosts,
      page_errors: pageErrors,
      console_errors: consoleErrors,
    };
  } finally {
    await context.close();
  }
}

async function verifyWithRetry(engineName, browser, viewport) {
  const first = await verify(engineName, browser, viewport);
  if (first.ok) return { ...first, attempts: 1 };
  await new Promise(resolve => setTimeout(resolve, 1000));
  const second = await verify(engineName, browser, viewport);
  return {
    ...second,
    attempts: 2,
    first_attempt: {
      error: first.error || "",
      page_errors: first.page_errors || [],
      console_errors: first.console_errors || [],
    },
  };
}

async function main() {
  const results = [];
  for (const [engineName, viewports] of Object.entries(matrix)) {
    const launchOptions = engineName === "chromium"
      ? { headless: true, args: ["--disable-web-security", "--disable-features=BlockInsecurePrivateNetworkRequests,PrivateNetworkAccessSendPreflights"] }
      : { headless: true };
    const browser = await playwright[engineName].launch(launchOptions);
    try {
      for (const viewport of viewports) results.push(await verifyWithRetry(engineName, browser, viewport));
    } finally {
      await browser.close();
    }
  }
  const report = {
    ok: results.length === 17 && results.every(item => item.ok),
    requirement_id: "BUG-8093-GUEST-UI-RECOVERY-20260814",
    artifact: path.resolve(artifactPath),
    combinations: results.length,
    results,
  };
  fs.mkdirSync(path.dirname(outputPath), { recursive: true });
  fs.writeFileSync(outputPath, JSON.stringify(report, null, 2), "utf8");
  process.stdout.write(JSON.stringify({ ok: report.ok, combinations: report.combinations, failed: results.filter(item => !item.ok) }) + "\n");
  if (!report.ok) process.exitCode = 1;
}

main().catch(error => {
  process.stderr.write(String(error && error.stack || error) + "\n");
  process.exitCode = 1;
});
