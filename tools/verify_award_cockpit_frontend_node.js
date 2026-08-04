const fs = require("fs");
const path = require("path");

function configureNodePath() {
  if (process.env.NODE_PATH) {
    require("module").Module._initPaths();
    return;
  }
  const home = process.env.USERPROFILE || process.env.HOME || "";
  const base = path.join(home, ".cache", "codex-runtimes", "codex-primary-runtime", "dependencies", "node", "node_modules");
  const pnpmPlaywright = path.join(base, ".pnpm", "playwright@1.60.0", "node_modules");
  process.env.NODE_PATH = [pnpmPlaywright, base].join(path.delimiter);
  require("module").Module._initPaths();
}

configureNodePath();

const { chromium } = require("playwright");

const root = path.resolve(__dirname, "..");
const defaultPage = path.join(root, "高炉前端数据", "frontend_award_cockpit.html");
const defaultScreenshotDir = path.join(root, "logs", "award_cockpit");
const viewports = [
  ["desktop", { width: 1440, height: 900 }],
  ["wide", { width: 1680, height: 980 }],
  ["mobile", { width: 390, height: 844 }],
];

function parseArgs(argv) {
  const args = {
    url: `file:///${defaultPage.replace(/\\/g, "/")}`,
    screenshotDir: defaultScreenshotDir,
  };
  for (let index = 0; index < argv.length; index += 1) {
    const item = argv[index];
    if (item === "--url") args.url = argv[++index];
    if (item === "--screenshot-dir") args.screenshotDir = argv[++index];
  }
  return args;
}

async function inspectViewport(browser, args, name, viewport) {
  const page = await browser.newPage({ viewport });
  const pageErrors = [];
  page.on("pageerror", (error) => pageErrors.push(String(error)));
  page.on("console", (message) => {
    if (message.type() === "error") pageErrors.push(message.text());
  });

  await page.goto(args.url, { waitUntil: "domcontentloaded", timeout: 60000 });
  await page.waitForTimeout(1200);

  fs.mkdirSync(args.screenshotDir, { recursive: true });
  const screenshot = path.join(args.screenshotDir, `${name}.png`);
  await page.screenshot({ path: screenshot, fullPage: false });

  const result = await page.evaluate(() => {
    const viewportW = window.innerWidth;
    const viewportH = window.innerHeight;
    const body = document.body;
    const rootEl = document.querySelector(".cockpit");
    const panels = [...document.querySelectorAll(".panel")];
    const texts = body.innerText || "";
    const overflow = [...document.querySelectorAll("body *")]
      .filter((el) => {
        const style = getComputedStyle(el);
        if (style.position === "fixed") return false;
        const rect = el.getBoundingClientRect();
        return rect.left < -4 || rect.right > viewportW + 4;
      })
      .slice(0, 12)
      .map((el) => ({
        tag: el.tagName,
        cls: String(el.className || ""),
        text: (el.textContent || "").trim().slice(0, 40),
      }));
    const clippedText = [...document.querySelectorAll("h1,.metric-name,.advice-title,.nav-button span")]
      .filter((el) => el.scrollWidth > el.clientWidth + 2 && getComputedStyle(el).overflow !== "hidden")
      .map((el) => ({ cls: String(el.className || ""), text: (el.textContent || "").trim() }));

    return {
      viewport: { width: viewportW, height: viewportH },
      title: document.title,
      rootVisible: !!rootEl && rootEl.getBoundingClientRect().width > 0 && rootEl.getBoundingClientRect().height > 0,
      panelCount: panels.length,
      metricRows: document.querySelectorAll(".metric-row").length,
      navButtons: document.querySelectorAll(".nav-button").length,
      hasRequiredText: [
        "高炉工艺大模型智能决策系统",
        "实时炉况",
        "高炉数字孪生",
        "趋势预测",
        "调控建议",
        "智能问答",
      ].every((item) => texts.includes(item)),
      horizontalOverflow: overflow,
      clippedText,
      bodyFits: body.scrollWidth <= viewportW + 4 || viewportW <= 420,
    };
  });

  await page.close();
  result.name = name;
  result.screenshot = screenshot;
  result.page_errors = pageErrors;
  result.ok = Boolean(
    result.rootVisible &&
      result.panelCount >= 4 &&
      result.metricRows >= 10 &&
      result.navButtons >= 6 &&
      result.hasRequiredText &&
      result.page_errors.length === 0 &&
      result.horizontalOverflow.length === 0 &&
      result.clippedText.length === 0,
  );
  return result;
}

async function main() {
  const args = parseArgs(process.argv.slice(2));
  const browser = await chromium.launch({ headless: true });
  try {
    const results = [];
    for (const [name, viewport] of viewports) {
      results.push(await inspectViewport(browser, args, name, viewport));
    }
    console.log(JSON.stringify(results, null, 2));
    process.exitCode = results.every((item) => item.ok) ? 0 : 1;
  } finally {
    await browser.close();
  }
}

main().catch((error) => {
  console.error(error);
  process.exit(1);
});
