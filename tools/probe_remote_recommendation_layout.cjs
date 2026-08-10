#!/usr/bin/env node
"use strict";

const { chromium } = require("playwright");

const selectors = [
  ".screen",
  ".bf-multi-condition-page",
  ".bf-multi-condition-page > .panel",
  ".bf-condition-matrix",
  ".bf-selected-condition-title",
  ".bf-engine-cockpit",
  ".bf-engine-cockpit .opt-cockpit-top",
  ".bf-engine-cockpit .opt-cockpit-bottom",
  ".bf-recommendation-detail-grid",
];

(async () => {
  const url = process.argv[2] || "http://10.30.220.12:8093/?layout_probe=20260806#optimization";
  const width = Number(process.argv[3] || 1920);
  const height = Number(process.argv[4] || 1080);
  const browser = await chromium.launch({ headless: true });
  const page = await browser.newPage({ viewport: { width, height } });
  await page.route("**/api/diagnosis/model-review", route => route.fulfill({
    status: 503,
    contentType: "application/json",
    body: JSON.stringify({ ok: false, error: "layout probe" }),
  }));
  await page.goto(url, { waitUntil: "domcontentloaded", timeout: 90000 });
  await page.waitForSelector(".bf-multi-condition-page", { state: "attached", timeout: 120000 });
  await page.waitForTimeout(3000);
  const result = await page.evaluate(list => {
    const row = selector => {
      const node = document.querySelector(selector);
      if (!node) return { selector, present: false };
      const rect = node.getBoundingClientRect();
      const style = getComputedStyle(node);
      return {
        selector,
        present: true,
        top: Math.round(rect.top),
        bottom: Math.round(rect.bottom),
        width: Math.round(rect.width),
        height: Math.round(rect.height),
        clientHeight: node.clientHeight,
        scrollHeight: node.scrollHeight,
        overflow: style.overflow,
        display: style.display,
      };
    };
    return {
      viewport: { width: innerWidth, height: innerHeight },
      body: { clientHeight: document.body.clientHeight, scrollHeight: document.body.scrollHeight, overflow: getComputedStyle(document.body).overflow },
      rows: list.map(row),
    };
  }, selectors);
  process.stdout.write(JSON.stringify(result, null, 2));
  await browser.close();
})().catch(error => {
  console.error(error);
  process.exitCode = 1;
});
