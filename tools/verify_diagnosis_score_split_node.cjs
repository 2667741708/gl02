const http = require("http");
const fs = require("fs");
const path = require("path");
const url = require("url");
const { chromium } = require("C:/Users/hmw20/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/.pnpm/playwright@1.61.1/node_modules/playwright");

const root = path.resolve(__dirname, "..");
const frontendDir = path.join(root, "高炉前端数据");

function contentType(filePath) {
  const ext = path.extname(filePath).toLowerCase();
  if (ext === ".html") return "text/html; charset=utf-8";
  if (ext === ".js") return "application/javascript; charset=utf-8";
  if (ext === ".css") return "text/css; charset=utf-8";
  if (ext === ".png") return "image/png";
  if (ext === ".svg") return "image/svg+xml";
  return "application/octet-stream";
}

function startServer() {
  const server = http.createServer((req, res) => {
    const parsed = url.parse(req.url || "/");
    const decodedPath = decodeURIComponent(parsed.pathname || "/");
    const relativePath = decodedPath === "/" ? "/frontend_dashboard_v3.server.html" : decodedPath;
    const filePath = path.normalize(path.join(frontendDir, relativePath));
    if (!filePath.startsWith(frontendDir)) {
      res.writeHead(403);
      res.end("forbidden");
      return;
    }
    fs.readFile(filePath, (err, data) => {
      if (err) {
        res.writeHead(404);
        res.end("not found");
        return;
      }
      res.writeHead(200, { "Content-Type": contentType(filePath) });
      res.end(data);
    });
  });
  return new Promise((resolve) => {
    server.listen(0, "127.0.0.1", () => {
      const address = server.address();
      resolve({ server, baseUrl: `http://127.0.0.1:${address.port}/frontend_dashboard_v3.server.html?ws_port=8767#diagnosis` });
    });
  });
}

async function checkViewport(browser, baseUrl, outputDir, width, height) {
  const page = await browser.newPage({ viewport: { width, height } });
  const pageErrors = [];
  const consoleErrors = [];
  page.on("pageerror", (err) => pageErrors.push(String(err)));
  page.on("console", (msg) => {
    if (msg.type() === "error") consoleErrors.push(msg.text());
  });
  await page.goto(baseUrl, { waitUntil: "domcontentloaded", timeout: 60000 });
  await page.waitForSelector(".bf-diag-split-list", { timeout: 45000 });
  await page.waitForTimeout(1000);
  const screenshot = path.join(outputDir, `diagnosis_score_split_${width}x${height}.png`);
  await page.screenshot({ path: screenshot, fullPage: false });
  const metrics = await page.evaluate(() => {
    const root = document.querySelector(".bf-diag-split-list");
    const groupTitles = [...document.querySelectorAll(".bf-diag-group-title")].map((x) => x.textContent.trim());
    const cards = [...document.querySelectorAll(".bf-diag-split-card")];
    const whiteText = cards.every((card) => {
      const nodes = [
        card.querySelector(".diag-rank-name"),
        card.querySelector(".diag-rank-value"),
        card.querySelector(".diag-rank-den"),
        card.querySelector(".bf-diag-risk-chip"),
      ].filter(Boolean);
      return nodes.every((node) => getComputedStyle(node).color === "rgb(255, 255, 255)");
    });
    return {
      hash: location.hash,
      viewportWidth: innerWidth,
      documentWidth: document.documentElement.scrollWidth,
      groupTitles,
      cardCount: cards.length,
      normalGroupCards: document.querySelectorAll(".bf-diag-normal-group .bf-diag-split-card").length,
      abnormalGroupCards: document.querySelectorAll(".bf-diag-abnormal-grid .bf-diag-split-card").length,
      whiteText,
      hasRawScoresText: (root?.innerText || "").includes("raw_scores"),
    };
  });
  await page.close();
  const failures = [];
  if (metrics.hash !== "#diagnosis") failures.push("route_not_diagnosis");
  if (metrics.documentWidth > width + 1) failures.push("horizontal_overflow");
  if (!metrics.groupTitles.includes("正常顺行炉况")) failures.push("missing_normal_group_title");
  if (!metrics.groupTitles.includes("异常炉况")) failures.push("missing_abnormal_group_title");
  if (metrics.cardCount !== 8) failures.push("card_count_not_8");
  if (metrics.normalGroupCards !== 1) failures.push("normal_group_not_1");
  if (metrics.abnormalGroupCards !== 7) failures.push("abnormal_group_not_7");
  if (!metrics.whiteText) failures.push("text_not_all_white");
  if (metrics.hasRawScoresText) failures.push("raw_scores_visible");
  return {
    viewport: `${width}x${height}`,
    ok: failures.length === 0,
    failures,
    screenshot,
    metrics,
    page_errors: pageErrors,
    console_errors: consoleErrors.filter((x) => !x.includes("WebSocket connection") && !x.includes("Failed to fetch")),
  };
}

async function main() {
  const args = process.argv.slice(2);
  const viewports = [];
  let outputDir = path.join(root, "logs", "diagnosis_score_split_20260714");
  for (let i = 0; i < args.length; i += 1) {
    if (args[i] === "--viewport") viewports.push(args[++i]);
    else if (args[i] === "--output-dir") outputDir = path.resolve(args[++i]);
  }
  if (!viewports.length) viewports.push("1366x768", "390x844");
  fs.mkdirSync(outputDir, { recursive: true });
  const { server, baseUrl } = await startServer();
  const browser = await chromium.launch({ headless: true });
  try {
    const results = [];
    for (const item of viewports) {
      const [width, height] = item.toLowerCase().split("x").map((x) => Number(x));
      results.push(await checkViewport(browser, baseUrl, outputDir, width, height));
    }
    const manifest = path.join(outputDir, "diagnosis_score_split_manifest.json");
    fs.writeFileSync(manifest, JSON.stringify(results, null, 2), "utf8");
    const failed = results.filter((x) => !x.ok || x.page_errors.length || x.console_errors.length);
    console.log(JSON.stringify({ count: results.length, failed: failed.length, manifest }, null, 2));
    process.exitCode = failed.length ? 1 : 0;
  } finally {
    await browser.close();
    server.close();
  }
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
