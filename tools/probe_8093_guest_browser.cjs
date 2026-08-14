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

const baseUrl = process.argv[2] || "http://10.30.220.12:8093/#qa";
const outputPath = process.argv[3] || path.resolve(".tmp/8093-guest-browser-probe.json");
const sourceOverride = process.argv[4] || "";

async function main() {
  const browser = await playwright.chromium.launch({
    headless: true,
    args: sourceOverride ? ["--disable-web-security", "--disable-features=BlockInsecurePrivateNetworkRequests,PrivateNetworkAccessSendPreflights"] : [],
  });
  const context = await browser.newContext({ viewport: { width: 1366, height: 768 } });
  const page = await context.newPage();
  const bootstrap = [];
  const pageErrors = [];
  const consoleErrors = [];

  page.on("response", async response => {
    if (!response.url().includes("/api/qa/bootstrap")) return;
    let body = null;
    try { body = await response.json(); } catch (_) { }
    bootstrap.push({ status: response.status(), access_mode: body?.access_mode || "", error: body?.error || "" });
  });
  page.on("pageerror", error => pageErrors.push(String(error)));
  page.on("console", message => {
    if (message.type() === "error" && !/favicon|websocket|\[BABEL\] Note: The code generator has deoptimised the styling/i.test(message.text())) consoleErrors.push(message.text());
  });
  if (sourceOverride) {
    const html = fs.readFileSync(sourceOverride, "utf8");
    await context.route("**/frontend_dashboard_v3.server.html*", route => {
      if (route.request().resourceType() !== "document") return route.continue();
      return route.fulfill({ status: 200, contentType: "text/html; charset=utf-8", body: html });
    });
  }

  try {
    await page.goto(baseUrl, { waitUntil: "domcontentloaded", timeout: 30000 });
    await page.waitForTimeout(10000);
    const guestBadge = page.locator(".qa-context-source-badge", { hasText: "匿名访客" });
    const privateLogin = page.getByText("登录私有模式（可选）", { exact: true });
    const initialGuestVisible = await guestBadge.isVisible().catch(() => false);
    const initialLoginVisible = await page.locator(".qa-session-login-card").isVisible().catch(() => false);
    let optionalLoginOpened = false;
    let continuedAsGuest = false;
    if (await privateLogin.isVisible().catch(() => false)) {
      await privateLogin.click();
      optionalLoginOpened = await page.getByText("登录私有会话（可选）", { exact: true }).isVisible().catch(() => false)
        && await page.getByText("继续匿名使用", { exact: true }).isVisible().catch(() => false);
      if (optionalLoginOpened) {
        await Promise.all([
          page.waitForNavigation({ waitUntil: "domcontentloaded", timeout: 30000 }),
          page.getByText("继续匿名使用", { exact: true }).click(),
        ]);
        await page.waitForTimeout(3000);
        continuedAsGuest = await guestBadge.isVisible().catch(() => false)
          && !await page.locator(".qa-session-login-card").isVisible().catch(() => false);
      }
    }
    const result = {
      ok: sourceOverride ? initialGuestVisible && !initialLoginVisible && optionalLoginOpened && continuedAsGuest : true,
      url: page.url(),
      bootstrap,
      source_override: sourceOverride,
      guest_badge_visible: initialGuestVisible,
      login_dialog_visible: initialLoginVisible,
      private_login_button_visible: await privateLogin.isVisible().catch(() => false),
      continue_guest_button_visible: await page.getByText("继续匿名使用", { exact: true }).isVisible().catch(() => false),
      optional_login_opened: optionalLoginOpened,
      continued_as_guest: continuedAsGuest,
      title: await page.title(),
      body_text: String(await page.locator("body").innerText().catch(() => "")).slice(0, 500),
      page_errors: pageErrors,
      console_errors: consoleErrors,
    };
    fs.mkdirSync(path.dirname(outputPath), { recursive: true });
    fs.writeFileSync(outputPath, JSON.stringify(result, null, 2), "utf8");
    process.stdout.write(JSON.stringify(result) + "\n");
  } finally {
    await context.close();
    await browser.close();
  }
}

main().catch(error => {
  process.stderr.write(String(error && error.stack || error) + "\n");
  process.exitCode = 1;
});
