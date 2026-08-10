#!/usr/bin/env node
"use strict";

const fs = require("fs");
const path = require("path");
const { chromium } = require("playwright");

(async () => {
  const url = process.argv[2] || "http://10.30.220.12:8093/?recommendation_probe=20260806#optimization";
  const browser = await chromium.launch({ headless: true });
  const page = await browser.newPage({ viewport: { width: 1366, height: 768 } });
  const consoleMessages = [];
  const pageErrors = [];
  page.on("console", message => consoleMessages.push({ type: message.type(), text: message.text() }));
  page.on("pageerror", error => pageErrors.push(String(error)));
  await page.goto(url, { waitUntil: "domcontentloaded", timeout: 90000 });
  await page.waitForTimeout(30000);
  const state = await page.evaluate(() => ({
    href: location.href,
    title: document.title,
    readyState: document.readyState,
    bodyText: document.body?.innerText?.slice(0, 2000),
    multiAttached: !!document.querySelector(".bf-multi-condition-page"),
    multiVisible: !!document.querySelector(".bf-multi-condition-page")?.getClientRects().length,
    conditionCount: document.querySelectorAll(".bf-condition-choice").length,
    loginVisible: [...document.querySelectorAll("button,h1,h2,h3")].some(node => /登录/.test(node.textContent || "") && node.getClientRects().length),
    rootHtmlLength: document.getElementById("root")?.innerHTML?.length || 0,
  }));
  const outputDir = path.resolve("logs", "acceptance", "8093_8094_recommendation_probe_20260806");
  fs.mkdirSync(outputDir, { recursive: true });
  const port = new URL(url).port;
  await page.screenshot({ path: path.join(outputDir, `${port}.png`), fullPage: true });
  const report = { url, state, consoleMessages, pageErrors };
  fs.writeFileSync(path.join(outputDir, `${port}.json`), JSON.stringify(report, null, 2), "utf8");
  process.stdout.write(JSON.stringify(report, null, 2));
  await browser.close();
})().catch(error => {
  console.error(error);
  process.exitCode = 1;
});
