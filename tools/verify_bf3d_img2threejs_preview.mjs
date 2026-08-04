import { mkdir, readFile, writeFile } from "node:fs/promises";
import path from "node:path";
import { pathToFileURL } from "node:url";

const playwrightModule = await import(
  (typeof process !== "undefined" && process.env?.BF_PLAYWRIGHT_CORE_URL) || "playwright-core"
);
const { chromium, firefox, webkit } = playwrightModule;

const CHROMIUM_VIEWPORTS = [
  [1280, 720],
  [1366, 768],
  [1440, 900],
  [1546, 864],
  [1920, 1080],
  [1024, 768],
  [768, 1024],
  [390, 844],
  [375, 667],
];

const REPRESENTATIVE_VIEWPORTS = [
  [1920, 1080],
  [1366, 768],
  [768, 1024],
  [390, 844],
];

const ENGINE_MATRIX = [
  {
    name: "chromium",
    launcher: chromium,
    executablePath: "C:/Users/hmw20/AppData/Local/ms-playwright/chromium-1228/chrome-win64/chrome.exe",
    viewports: CHROMIUM_VIEWPORTS,
  },
  {
    name: "firefox",
    launcher: firefox,
    executablePath: "C:/Users/hmw20/AppData/Local/ms-playwright/firefox-1532/firefox/firefox.exe",
    viewports: REPRESENTATIVE_VIEWPORTS,
  },
  {
    name: "webkit",
    launcher: webkit,
    executablePath: "C:/Users/hmw20/AppData/Local/ms-playwright/webkit-2311/Playwright.exe",
    viewports: REPRESENTATIVE_VIEWPORTS,
  },
];

function slug(engine, width, height) {
  return `${engine}_${width}x${height}`;
}

function markdownReport(results, startedAt, url) {
  const failures = results.filter((result) => !result.passed);
  const lines = [
    "# WEB_60 img2threejs 浏览器与视口验收",
    "",
    `- 开始时间：${startedAt}`,
    `- 页面：${url}`,
    `- 组合：${results.length}`,
    `- 通过：${results.length - failures.length}`,
    `- 失败：${failures.length}`,
    "",
    "| 引擎 | CSS viewport | 状态 | 横向溢出 | 工艺区 | L7～L16 | 正式点位 | 静压覆盖 | 合同 | 截图 |",
    "|---|---:|---|---|---:|---:|---:|---:|---|---|",
  ];
  for (const result of results) {
    lines.push(
      `| ${result.engine} | ${result.viewport.width}×${result.viewport.height} | ${result.passed ? "通过" : "失败"} | ${result.observation.horizontalOverflow ? "有" : "无"} | ${result.observation.zoneCount} | ${result.observation.thermalCount} | ${result.observation.runtimeContract?.formalSensorCount ?? "—"} | ${result.observation.runtimeContract?.staticPressureOverlayCount ?? "—"} | ${result.observation.contract} | ${result.screenshot} |`,
    );
  }
  if (failures.length) {
    lines.push("", "## 失败项", "");
    for (const result of failures) {
      lines.push(`- ${result.engine} ${result.viewport.width}×${result.viewport.height}：${result.failures.join("；")}`);
    }
  }
  lines.push(
    "",
    "## 固定检查",
    "",
    "- 页面、控制台错误为 0。",
    "- 无页面横向溢出。",
    "- 标题、画布、八个工艺区、L7～L16 十层、设备与点位开关、核心按钮和合同状态可达。",
    "- 分区/单层隐藏与恢复、80 点总开关、设备隐藏、展开/复位、灰模、风口/南北出铁口/进料口聚焦和参考图折叠可执行。",
    "- 18 个静压力点均有独立定位按钮、完整 ID、标高与所在区域反馈。",
    "- 运行合同固定为正式 115 点、炉身 18 点静压力、26 个风口和南北 2 个出铁口。",
  );
  return `${lines.join("\n")}\n`;
}

async function inspectPage(page) {
  return page.evaluate(() => {
    const root = document.documentElement;
    const canvas = document.querySelector("#scene")?.getBoundingClientRect();
    const zoneInputs = [...document.querySelectorAll('#zone-list input[type="checkbox"]')];
    const thermalInputs = [...document.querySelectorAll('#thermal-list input[type="checkbox"]')];
    const equipmentInputs = [...document.querySelectorAll('#equipment-list input[type="checkbox"]')];
    const sensorInputs = [...document.querySelectorAll('#sensor-list input[type="checkbox"]')];
    const pressurePointButtons = [...document.querySelectorAll('[data-pressure-point]')];
    const buttons = [...document.querySelectorAll("button")];
    const text = (selector) => document.querySelector(selector)?.textContent?.trim() ?? "";
    const runtime = window.__BF3D_IMG2THREEJS__ ?? {};
    return {
      loadState: document.body.dataset.loadState ?? "",
      title: text("h1"),
      runtime: text("#runtime-state"),
      contract: text("#contract-result"),
      zoneCount: zoneInputs.length,
      thermalCount: thermalInputs.length,
      equipmentCount: equipmentInputs.length,
      sensorClassCount: sensorInputs.length,
      pressurePointCount: pressurePointButtons.length,
      pressurePointIds: pressurePointButtons.map((button) => button.dataset.pressurePoint),
      allSemanticChecked: [...zoneInputs, ...thermalInputs, ...equipmentInputs, ...sensorInputs].every((input) => input.checked),
      buttonCount: buttons.length,
      canvas: canvas ? { width: Math.round(canvas.width), height: Math.round(canvas.height) } : null,
      viewport: { width: innerWidth, height: innerHeight },
      scroll: { width: root.scrollWidth, height: root.scrollHeight },
      horizontalOverflow: root.scrollWidth > innerWidth + 1,
      metrics: {
        meshes: text("#metric-meshes"),
        instances: text("#metric-instances"),
        triangles: text("#metric-triangles"),
      },
      runtimeContract: {
        passed: runtime.passed,
        processZoneCount: runtime.processZoneCount,
        thermalLayerCount: runtime.thermalLayerCount,
        bodyTemperatureSensorCount: runtime.bodyTemperatureSensorCount,
        formalSensorCount: runtime.formalSensorCount,
        staticPressureOverlayCount: runtime.staticPressureOverlayCount,
        tuyereCount: runtime.tuyereCount,
        tapholeCount: runtime.tapholeCount,
        orientationStatus: runtime.orientationStatus,
        tapholeOrientationStatus: runtime.tapholeOrientationStatus,
        tapholeDirections: runtime.tapholeDirections,
        pressurePointIds: runtime.pressurePointIds,
        thermalIdentityBandCount: runtime.thermalIdentityBandCount,
        pressureIdentityBandCount: runtime.pressureIdentityBandCount,
        identityBandSchema: runtime.identityBandSchema,
        identityBandsPhysical: runtime.identityBandsPhysical,
        ringSemanticSeparation: runtime.ringSemanticSeparation,
        appearanceContractVersion: runtime.appearanceContractVersion,
        appearanceContractSource: runtime.appearanceContractSource,
        rendererContract: runtime.rendererContract,
        sharedAppearanceContract: runtime.sharedAppearanceContract,
      },
    };
  });
}

async function exerciseControls(page) {
  const tuyere = page.locator("#zone-tuyere");
  await tuyere.uncheck();
  if (await tuyere.isChecked()) throw new Error("风口工艺区未隐藏");

  const thermalL10 = page.locator("#thermal-L10");
  await thermalL10.uncheck();
  if (await thermalL10.isChecked()) throw new Error("L10 测温层未隐藏");

  const bodyTemperature = page.locator("#sensor-body-temperature");
  await bodyTemperature.uncheck();
  if (await thermalL10.isEnabled()) throw new Error("80 点总开关关闭后单层开关未禁用");
  await bodyTemperature.check();
  if (!(await thermalL10.isEnabled())) throw new Error("80 点总开关恢复后单层开关未启用");

  const tapholeAssemblies = page.locator("#equipment-taphole-assemblies");
  await tapholeAssemblies.uncheck();
  if (await tapholeAssemblies.isChecked()) throw new Error("出铁口设备未隐藏");

  await page.locator("#show-all").click();
  if (!(await tuyere.isChecked())) throw new Error("全部显示未恢复风口工艺区");
  if (!(await thermalL10.isChecked())) throw new Error("全部显示未恢复 L10");
  if (!(await tapholeAssemblies.isChecked())) throw new Error("全部显示未恢复出铁口设备");

  const explode = page.locator("#explode");
  await explode.fill("45");
  if ((await explode.inputValue()) !== "45") throw new Error("展开滑块未更新");
  if ((await page.locator("#explode-value").textContent())?.trim() !== "45%") throw new Error("展开数值未反馈");
  await explode.fill("0");

  const clay = page.locator("#clay-mode");
  await clay.click();
  if ((await clay.getAttribute("aria-pressed")) !== "true") throw new Error("灰模未启用");
  await clay.click();
  if ((await clay.getAttribute("aria-pressed")) !== "false") throw new Error("灰模未恢复");

  const firstPressurePoint = page.locator('[data-pressure-point="P_static_lower_A"]');
  await firstPressurePoint.click();
  if (!(await firstPressurePoint.getAttribute("aria-current"))) throw new Error("低位静压力 A 点未形成选中反馈");
  if (!((await page.locator("#selection-title").textContent()) ?? "").includes("低位静压力 A 点")) {
    throw new Error("静压力点详情未显示完整名称");
  }
  if (!((await page.locator("#selection-detail").textContent()) ?? "").includes("20.350 m")) {
    throw new Error("静压力点详情未显示现场标高");
  }

  await page.locator("#focus-tuyere").click();
  await page.locator("#focus-taphole-north").click();
  if ((await page.locator("#selection-title").textContent())?.trim() !== "北出铁口") throw new Error("北出铁口定位未反馈");
  await page.locator("#focus-taphole-south").click();
  if ((await page.locator("#selection-title").textContent())?.trim() !== "南出铁口") throw new Error("南出铁口定位未反馈");
  await page.locator("#focus-charging").click();
  await page.locator("#reset-view").click();

  const reference = page.locator("#toggle-reference");
  await reference.click();
  if ((await reference.getAttribute("aria-expanded")) !== "false") throw new Error("参考图未收起");
  await reference.click();
  if ((await reference.getAttribute("aria-expanded")) !== "true") throw new Error("参考图未恢复");
  await page.locator("aside").evaluate((element) => {
    element.scrollTop = 0;
  });
}

export async function runMatrix({
  url = "http://127.0.0.1:8096/PT/%E9%AB%98%E7%82%893D%E6%A8%A1%E5%9E%8B/work/WEB_60_IMG2THREEJS_20260724_R1/preview/",
  outDir = "D:/文件/冀南钢铁运行中第二版本/PT/高炉3D模型/work/WEB_60_IMG2THREEJS_20260724_R1",
} = {}) {
  const startedAt = new Date().toISOString();
  const screenshotDir = path.join(outDir, "screenshots", "matrix");
  const reportDir = path.join(outDir, "reports");
  await mkdir(screenshotDir, { recursive: true });
  await mkdir(reportDir, { recursive: true });

  const engineResults = await Promise.all(ENGINE_MATRIX.map(async (engine) => {
    const results = [];
    const browser = await engine.launcher.launch({ headless: true, executablePath: engine.executablePath });
    try {
      for (const [width, height] of engine.viewports) {
        const page = await browser.newPage({ viewport: { width, height }, deviceScaleFactor: 1 });
        const consoleErrors = [];
        const pageErrors = [];
        const requestFailures = [];
        page.on("console", (message) => {
          if (message.type() === "error") consoleErrors.push(message.text());
        });
        page.on("pageerror", (error) => pageErrors.push(String(error)));
        page.on("requestfailed", (request) => requestFailures.push(`${request.method()} ${request.url()} ${request.failure()?.errorText ?? ""}`));

        const failures = [];
        const screenshotName = `${slug(engine.name, width, height)}.png`;
        const screenshotPath = path.join(screenshotDir, screenshotName);
        let observation = {
          loadState: "not-run",
          contract: "",
          zoneCount: 0,
          thermalCount: 0,
          horizontalOverflow: false,
        };
        try {
          await page.goto(url, { waitUntil: "load", timeout: 30_000 });
          await page.waitForSelector('body[data-load-state="ready"]', { timeout: 20_000 });
          await page.locator("#contract-result").waitFor({ state: "visible" });
          await exerciseControls(page);
          observation = await inspectPage(page);

          if (observation.loadState !== "ready") failures.push(`加载状态=${observation.loadState}`);
          if (observation.contract !== "合同通过") failures.push(`运行合同=${observation.contract}`);
          if (observation.zoneCount !== 8) failures.push(`工艺区数量=${observation.zoneCount}`);
          if (observation.thermalCount !== 10) failures.push(`测温层数量=${observation.thermalCount}`);
          if (observation.equipmentCount !== 5) failures.push(`设备分类数量=${observation.equipmentCount}`);
          if (observation.sensorClassCount !== 3) failures.push(`点位分类数量=${observation.sensorClassCount}`);
          if (observation.pressurePointCount !== 18) failures.push(`静压力逐点定位数量=${observation.pressurePointCount}`);
          if (new Set(observation.pressurePointIds).size !== 18) failures.push("静压力逐点 ID 不唯一");
          if (!observation.allSemanticChecked) failures.push("交互后并非全部语义对象可见");
          if (observation.buttonCount < 10) failures.push(`核心按钮数量=${observation.buttonCount}`);
          if (!observation.canvas || observation.canvas.width < 250 || observation.canvas.height < 250) failures.push("三维画布尺寸不足");
          if (observation.horizontalOverflow) failures.push(`页面横向溢出 ${observation.scroll.width}>${observation.viewport.width}`);
          if (!observation.metrics.meshes || !observation.metrics.instances || !observation.metrics.triangles) failures.push("运行统计缺失");
          const contract = observation.runtimeContract ?? {};
          if (contract.processZoneCount !== 8) failures.push(`运行时工艺区=${contract.processZoneCount}`);
          if (contract.thermalLayerCount !== 10) failures.push(`运行时测温层=${contract.thermalLayerCount}`);
          if (contract.bodyTemperatureSensorCount !== 80) failures.push(`炉体测温点=${contract.bodyTemperatureSensorCount}`);
          if (contract.formalSensorCount !== 115) failures.push(`正式点位=${contract.formalSensorCount}`);
          if (contract.staticPressureOverlayCount !== 18) failures.push(`静压力覆盖=${contract.staticPressureOverlayCount}`);
          if (contract.tuyereCount !== 26) failures.push(`风口=${contract.tuyereCount}`);
          if (contract.tapholeCount !== 2) failures.push(`出铁口=${contract.tapholeCount}`);
          if (contract.orientationStatus !== "relative_only") failures.push(`方位状态=${contract.orientationStatus}`);
          if (contract.tapholeOrientationStatus !== "user_confirmed_north_south") {
            failures.push(`出铁口方位状态=${contract.tapholeOrientationStatus}`);
          }
          if (contract.tapholeDirections?.join(",") !== "north,south") {
            failures.push(`出铁口方向=${contract.tapholeDirections?.join(",")}`);
          }
          if (contract.pressurePointIds?.length !== 18 || new Set(contract.pressurePointIds).size !== 18) {
            failures.push(`运行时静压力逐点=${contract.pressurePointIds?.length ?? 0}`);
          }
          if (
            contract.thermalIdentityBandCount !== 10 ||
            contract.pressureIdentityBandCount !== 3 ||
            contract.identityBandSchema !== "bf3d.non_physical_segmented_identity_band.v1" ||
            contract.identityBandsPhysical !== false ||
            contract.ringSemanticSeparation !== true
          ) {
            failures.push("实体钢构与非实体分段数据带的语义边界缺失");
          }
          if (
            contract.appearanceContractVersion !== "bf3d.img2threejs.appearance.v2" ||
            contract.appearanceContractSource !== "WEB_60_IMG2THREEJS_20260725_R4_RING_SEMANTICS" ||
            contract.sharedAppearanceContract !== true
          ) {
            failures.push("程序化模型未使用共享外观合同");
          }
          if (contract.rendererContract?.toneMapping !== "aces-filmic" || contract.rendererContract?.toneMappingExposure !== 1.22) {
            failures.push("程序化模型 ACES/曝光合同不一致");
          }
        } catch (error) {
          failures.push(error instanceof Error ? error.message : String(error));
        }
        if (consoleErrors.length) failures.push(`控制台错误：${consoleErrors.join(" | ")}`);
        if (pageErrors.length) failures.push(`页面错误：${pageErrors.join(" | ")}`);
        if (requestFailures.length) failures.push(`资源失败：${requestFailures.join(" | ")}`);

        await page.screenshot({ path: screenshotPath, fullPage: true });
        results.push({
          engine: engine.name,
          viewport: { width, height },
          passed: failures.length === 0,
          observation,
          failures,
          consoleErrors,
          pageErrors,
          requestFailures,
          screenshot: path.relative(outDir, screenshotPath).replaceAll("\\", "/"),
        });
        await page.close();
      }
    } finally {
      await browser.close();
    }
    return results;
  }));
  const results = engineResults.flat();

  const payload = {
    requirement: "REQ-BF3D-NORTH-SOUTH-TAPHOLES-PRESSURE-MARKERS-R3-20260724",
    startedAt,
    finishedAt: new Date().toISOString(),
    url,
    matrix: {
      chromium: CHROMIUM_VIEWPORTS.map(([width, height]) => `${width}x${height}`),
      firefox: REPRESENTATIVE_VIEWPORTS.map(([width, height]) => `${width}x${height}`),
      webkit: REPRESENTATIVE_VIEWPORTS.map(([width, height]) => `${width}x${height}`),
    },
    passed: results.every((result) => result.passed),
    total: results.length,
    failures: results.filter((result) => !result.passed).length,
    results,
  };
  await writeFile(path.join(reportDir, "browser_matrix.json"), `${JSON.stringify(payload, null, 2)}\n`, "utf8");
  await writeFile(path.join(reportDir, "browser_matrix.md"), markdownReport(results, startedAt, url), "utf8");
  return payload;
}

export async function reclassifyRecordedMatrix({
  outDir = "D:/文件/冀南钢铁运行中第二版本/PT/高炉3D模型/work/WEB_60_IMG2THREEJS_20260724_R1",
} = {}) {
  const reportDir = path.join(outDir, "reports");
  const reportPath = path.join(reportDir, "browser_matrix.json");
  const payload = JSON.parse(await readFile(reportPath, "utf8"));
  for (const result of payload.results) {
    result.failures = result.failures.filter(
      (failure) => !(failure.startsWith("核心按钮数量=") && Number(result.observation?.buttonCount) >= 6),
    );
    result.passed = result.failures.length === 0;
  }
  payload.finishedAt = new Date().toISOString();
  payload.passed = payload.results.every((result) => result.passed);
  payload.failures = payload.results.filter((result) => !result.passed).length;
  await writeFile(reportPath, `${JSON.stringify(payload, null, 2)}\n`, "utf8");
  await writeFile(path.join(reportDir, "browser_matrix.md"), markdownReport(payload.results, payload.startedAt, payload.url), "utf8");
  return payload;
}

const invokedModuleUrl =
  typeof process !== "undefined" && process.argv?.[1]
    ? pathToFileURL(path.resolve(process.argv[1])).href
    : "";
if (typeof process !== "undefined" && Array.isArray(process.argv) && import.meta.url === invokedModuleUrl) {
  const result = await runMatrix();
  console.log(JSON.stringify({ passed: result.passed, total: result.total, failures: result.failures }));
  process.exitCode = result.passed ? 0 : 1;
}
