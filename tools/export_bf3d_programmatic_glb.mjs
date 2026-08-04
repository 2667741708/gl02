import { createHash } from "node:crypto";
import { mkdir, readFile, stat, writeFile } from "node:fs/promises";
import path from "node:path";

const playwrightModule = await import(
  process.env.BF_PLAYWRIGHT_CORE_URL || "playwright-core"
);
const { chromium } = playwrightModule;

function argument(name, fallback) {
  const index = process.argv.indexOf(name);
  return index >= 0 && process.argv[index + 1] ? process.argv[index + 1] : fallback;
}

const workspace = process.cwd();
const frozenId = "WEB_60_IMG2THREEJS_20260724_R3_FROZEN";
const defaultUrl =
  "http://127.0.0.1:8096/PT/%E9%AB%98%E7%82%893D%E6%A8%A1%E5%9E%8B/work/" +
  `${frozenId}/preview/`;
const defaultOutput = path.join(
  workspace,
  "PT",
  "高炉3D模型",
  "work",
  frozenId,
  "assets",
  "GL02_IMG2THREEJS_PROGRAMMATIC_R3_FROZEN.glb",
);

const url = argument("--url", defaultUrl);
const output = path.resolve(argument("--output", defaultOutput));
const reportPath = path.resolve(
  argument("--report", path.join(path.dirname(output), "programmatic_glb_export_report.json")),
);
const executablePath = argument(
  "--chromium",
  "C:/Users/hmw20/AppData/Local/ms-playwright/chromium-1228/chrome-win64/chrome.exe",
);

await mkdir(path.dirname(output), { recursive: true });
await mkdir(path.dirname(reportPath), { recursive: true });

const browser = await chromium.launch({ headless: true, executablePath });
const page = await browser.newPage({ viewport: { width: 1440, height: 900 } });
const consoleErrors = [];
const pageErrors = [];
page.on("console", (message) => {
  if (message.type() === "error") consoleErrors.push(message.text());
});
page.on("pageerror", (error) => pageErrors.push(error.message));

try {
  await page.goto(url, { waitUntil: "networkidle", timeout: 120_000 });
  await page.waitForFunction(
    () =>
      document.body.dataset.loadState === "ready" &&
      window.__BF3D_IMG2THREEJS__?.passed === true &&
      Boolean(window.__BF3D_PROGRAMMATIC_MODEL_ROOT__),
    null,
    { timeout: 120_000 },
  );

  const runtime = await page.evaluate(() => {
    const contract = window.__BF3D_IMG2THREEJS__;
    return {
      passed: contract.passed,
      frozenBaseline: contract.frozenBaseline,
      processZoneCount: contract.processZoneCount,
      thermalLayerCount: contract.thermalLayerCount,
      formalSensorCount: contract.formalSensorCount,
      staticPressureOverlayCount: contract.staticPressureOverlayCount,
      tuyereCount: contract.tuyereCount,
      tapholeCount: contract.tapholeCount,
      meshes: contract.meshes,
      instances: contract.instances,
      triangles: contract.triangles,
      evidenceBoundary: contract.evidenceBoundary,
    };
  });

  const fileName = path.basename(output);
  const downloadPromise = page.waitForEvent("download", { timeout: 120_000 });
  const exportResult = await page.evaluate(async (downloadName) => {
    const { GLTFExporter } = await import("three/addons/exporters/GLTFExporter.js");
    const root = window.__BF3D_PROGRAMMATIC_MODEL_ROOT__;
    root.updateMatrixWorld(true);
    const exporter = new GLTFExporter();
    const arrayBuffer = await new Promise((resolve, reject) => {
      exporter.parse(
        root,
        resolve,
        reject,
        {
          binary: true,
          onlyVisible: false,
          trs: false,
          includeCustomExtensions: true,
          maxTextureSize: 1024,
        },
      );
    });
    if (!(arrayBuffer instanceof ArrayBuffer)) {
      throw new Error("GLTFExporter 未返回二进制 ArrayBuffer");
    }
    const blob = new Blob([arrayBuffer], { type: "model/gltf-binary" });
    const anchor = document.createElement("a");
    anchor.href = URL.createObjectURL(blob);
    anchor.download = downloadName;
    document.body.append(anchor);
    anchor.click();
    anchor.remove();
    setTimeout(() => URL.revokeObjectURL(anchor.href), 2_000);
    return { bytes: arrayBuffer.byteLength };
  }, fileName);
  const download = await downloadPromise;
  await download.saveAs(output);

  const payload = await readFile(output);
  const fileStat = await stat(output);
  const report = {
    schema: "bf3d.programmatic_glb_export.v1",
    generatedAt: new Date().toISOString(),
    sourceUrl: url,
    frozenBaseline: frozenId,
    output,
    bytes: fileStat.size,
    browserReportedBytes: exportResult.bytes,
    sha256: createHash("sha256").update(payload).digest("hex"),
    runtime,
    exporter: {
      threeRevision: "160",
      binary: true,
      onlyVisible: false,
      maxTextureSize: 1024,
    },
    consoleErrors,
    pageErrors,
    passed:
      fileStat.size > 0 &&
      fileStat.size === exportResult.bytes &&
      consoleErrors.length === 0 &&
      pageErrors.length === 0 &&
      runtime.passed === true,
  };
  await writeFile(reportPath, `${JSON.stringify(report, null, 2)}\n`, "utf8");
  process.stdout.write(`${JSON.stringify(report, null, 2)}\n`);
  if (!report.passed) process.exitCode = 1;
} finally {
  await browser.close();
}
