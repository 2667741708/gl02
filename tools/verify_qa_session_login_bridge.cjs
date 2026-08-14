#!/usr/bin/env node
"use strict";

/* REQ-QA-SESSION-LOGIN-BRIDGE-20260812: browser contract, no real model call. */
const fs = require("fs");
const path = require("path");

let playwright;
try {
  playwright = require("playwright");
} catch (_) {
  playwright = require("C:/Users/hmw20/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright");
}

const baseUrl = process.argv[2] || "http://127.0.0.1:18093/高炉前端数据/frontend_dashboard_v3.server.html#qa";
const outputPath = process.argv[3] || path.resolve("logs/qa_session_login_bridge/report.json");
const viewportText = process.argv[4] || "1366x768";
const viewportMatch = viewportText.match(/^(\d+)x(\d+)$/);
if (!viewportMatch) throw new Error("viewport must use WIDTHxHEIGHT");
const viewport = { width: Number(viewportMatch[1]), height: Number(viewportMatch[2]) };

async function main() {
  const browser = await playwright.chromium.launch({ headless: true });
  const context = await browser.newContext({ viewport });
  const page = await context.newPage();
  let authenticated = false;
  let loginPosts = 0;
  let chatPosts = 0;
  const consoleErrors = [];
  const pageErrors = [];
  page.on("console", message => { if (message.type() === "error") consoleErrors.push(message.text()); });
  page.on("pageerror", error => pageErrors.push(String(error)));

  await context.route("**/*", async route => {
    const request = route.request();
    const url = new URL(request.url());
    const method = request.method().toUpperCase();
    const json = (status, body) => route.fulfill({ status, contentType: "application/json; charset=utf-8", body: JSON.stringify(body) });
    if (url.pathname === "/api/qa/bootstrap") {
      if (!authenticated) return json(403, { ok: false, error: "qa_session_required" });
      return json(200, { ok: true, conversation: { id: "qa-login-fixture", title: "登录后会话" }, conversations: [], messages: [], projects: [], report_assets: [] });
    }
    if (url.pathname === "/api/auth/login" && method === "POST") {
      loginPosts += 1;
      const body = JSON.parse(request.postData() || "{}");
      if (body.username !== "fixture_operator" || body.password !== "fixture_password") return json(401, { ok: false, message: "账号或密码不匹配。" });
      authenticated = true;
      return json(200, { ok: true, username: body.username, role: "operator" });
    }
    if (url.pathname === "/api/qa/chat") {
      chatPosts += 1;
      return json(500, { ok: false, error: "unexpected_model_call" });
    }
    if (url.pathname === "/api/qa/projects") return json(200, { ok: true, projects: [], allowed_folders: [], report_assets: [], project_assets: [], folder_assets: [], conversations: [] });
    if (url.pathname === "/api/short-window/conversations") return json(200, { ok: true, items: [] });
    if (url.pathname === "/api/ollama/status") return json(200, { ok: true });
    if (url.pathname.startsWith("/api/")) return json(200, { ok: true, items: [] });
    return route.continue();
  });

  try {
    await page.goto(baseUrl, { waitUntil: "domcontentloaded", timeout: 30000 });
    await page.waitForSelector(".qa-session-login-card", { state: "visible", timeout: 30000 });
    const before = await page.locator(".qa-session-login-card").innerText();
    await page.locator(".qa-session-login-card input[autocomplete='username']").fill("fixture_operator");
    await page.locator(".qa-session-login-card input[type='password']").fill("fixture_password");
    await page.locator(".qa-session-login-card button[type='submit']").click();
    await page.waitForSelector(".qa-session-login-card", { state: "detached", timeout: 10000 });
    await page.waitForFunction(() => document.querySelector(".qa-server-title")?.textContent?.includes("登录后会话"), null, { timeout: 10000 });
    const passwordInputs = await page.locator(".qa-session-login-card input[type='password']").count();
    const result = {
      ok: before.includes("登录私有会话（可选）") && before.includes("继续匿名使用") && authenticated && loginPosts === 1 && chatPosts === 0 && passwordInputs === 0 && pageErrors.length === 0,
      requirement_id: "REQ-QA-SESSION-LOGIN-BRIDGE-20260812",
      viewport,
      login_posts: loginPosts,
      model_or_chat_posts: chatPosts,
      password_inputs_after_login: passwordInputs,
      console_errors: consoleErrors.filter(text => !/favicon|websocket/i.test(text)),
      page_errors: pageErrors,
    };
    fs.mkdirSync(path.dirname(outputPath), { recursive: true });
    fs.writeFileSync(outputPath, JSON.stringify(result, null, 2), "utf8");
    process.stdout.write(JSON.stringify(result) + "\n");
    if (!result.ok) process.exitCode = 1;
  } finally {
    await context.close();
    await browser.close();
  }
}

main().catch(error => {
  process.stderr.write(String(error && error.stack || error) + "\n");
  process.exitCode = 1;
});
