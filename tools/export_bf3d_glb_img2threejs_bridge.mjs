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
const candidateId = "WEB_60_GLB_IMG2THREEJS_BRIDGE_20260724_R1";
const defaultUrl =
  "http://127.0.0.1:8096/PT/%E9%AB%98%E7%82%893D%E6%A8%A1%E5%9E%8B/work/" +
  `${candidateId}/preview/`;
const defaultOutput = path.join(
  workspace,
  "PT",
  "高炉3D模型",
  "work",
  candidateId,
  "assets",
  "GL02_FORMAL_IMG2THREEJS_TOP_FEED_GAS_CLEANING_R6.glb",
);

const url = argument("--url", defaultUrl);
const output = path.resolve(argument("--output", defaultOutput));
const reportPath = path.resolve(
  argument("--report", path.join(path.dirname(output), "top_feed_gas_cleaning_glb_export_report.json")),
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
      window.__BF3D_GLB_IMG2THREEJS_BRIDGE__?.passed === true &&
      Array.isArray(window.__BF3D_GLB_EXPORT_ROOTS__),
    null,
    { timeout: 120_000 },
  );
  await page.locator("#mode-hybrid").click();
  await page.locator("#toggle-equipment").check();
  await page.locator("#toggle-shell-detail").check();
  await page.locator("#toggle-sensors").check();
  await page.locator("#toggle-pressure").check();
  await page.locator("#toggle-internal").uncheck();

  const sanitizedPortableExtraPathCount = await page.evaluate(() => {
    const absolutePathPattern = /^(?:[A-Za-z]:[\\/]|\\\\)/;
    const visited = new WeakSet();
    let removed = 0;
    const sanitize = (value) => {
      if (!value || typeof value !== "object" || visited.has(value)) return;
      visited.add(value);
      for (const key of Object.keys(value)) {
        const child = value[key];
        if (typeof child === "string" && absolutePathPattern.test(child)) {
          delete value[key];
          removed += 1;
        } else {
          sanitize(child);
        }
      }
    };
    for (const root of window.__BF3D_GLB_EXPORT_ROOTS__) {
      root.traverse((object) => sanitize(object.userData));
    }
    return removed;
  });

  const runtime = await page.evaluate((sanitizedCount) => {
    const contract = window.__BF3D_GLB_IMG2THREEJS_BRIDGE__;
    return {
      passed: contract.passed,
      schema: contract.schema,
      formalNodeCount: contract.formalNodeCount,
      formalSensorCount: contract.formalSensorCount,
      staticPressureOverlayCount: contract.staticPressureOverlayCount,
      tapholeCount: contract.tapholeCount,
      fittedProgrammaticShellCount: contract.fittedProgrammaticShellCount,
      fittedShellProfilePointCount: contract.fittedShellProfilePointCount,
      fittedSteelRingCount: contract.fittedSteelRingCount,
      fittedVerticalSeamCount: contract.fittedVerticalSeamCount,
      thermalIdentityBandCount: contract.thermalIdentityBandCount,
      pressureIdentityBandCount: contract.pressureIdentityBandCount,
      identityBandSchema: contract.identityBandSchema,
      identityBandsPhysical: contract.identityBandsPhysical,
      ringSemanticSeparation: contract.ringSemanticSeparation,
      maintenanceAccessSchema: contract.maintenanceAccessSchema,
      fittedMaintenancePlatformCount: contract.fittedMaintenancePlatformCount,
      fittedWalkwayDeckCount: contract.fittedWalkwayDeckCount,
      fittedGuardrailRingCount: contract.fittedGuardrailRingCount,
      fittedGuardrailPostCount: contract.fittedGuardrailPostCount,
      fittedSupportBracketCount: contract.fittedSupportBracketCount,
      fittedAccessLadderCount: contract.fittedAccessLadderCount,
      fittedAccessLadderRungCount: contract.fittedAccessLadderRungCount,
      platformLevelIds: contract.platformLevelIds,
      platformSourceDisplayYs: contract.platformSourceDisplayYs,
      topFeedGasCleaningSchema: contract.topFeedGasCleaningSchema,
      fittedConveyorSystemCount: contract.fittedConveyorSystemCount,
      fittedConveyorBeltCount: contract.fittedConveyorBeltCount,
      fittedConveyorRollerCount: contract.fittedConveyorRollerCount,
      fittedConveyorTrestleCount: contract.fittedConveyorTrestleCount,
      fittedConveyorDischargeChuteCount: contract.fittedConveyorDischargeChuteCount,
      fittedTopGasUptakeCount: contract.fittedTopGasUptakeCount,
      fittedGasDuctCount: contract.fittedGasDuctCount,
      fittedGravityDustCatcherCount: contract.fittedGravityDustCatcherCount,
      fittedFineDustCollectorCount: contract.fittedFineDustCollectorCount,
      fittedDustHopperCount: contract.fittedDustHopperCount,
      fittedExternalProcessSupportCount: contract.fittedExternalProcessSupportCount,
      fineDustCollectorEquipmentTypeStatus: contract.fineDustCollectorEquipmentTypeStatus,
      appearanceContractVersion: contract.appearanceContractVersion,
      appearanceContractSource: contract.appearanceContractSource,
      fittedSurfaceTangentSpace: contract.fittedSurfaceTangentSpace,
      hybridSuppressedEquipmentCount: contract.hybridSuppressedEquipmentCount,
      sanitizedPortableExtraPathCount: sanitizedCount,
      exportRootNames: window.__BF3D_GLB_EXPORT_ROOTS__.map((root) => root.name),
      truthBoundary: contract.truthBoundary,
      productionRouteChanged: contract.productionRouteChanged,
    };
  }, sanitizedPortableExtraPathCount);

  const fileName = path.basename(output);
  const downloadPromise = page.waitForEvent("download", { timeout: 180_000 });
  const exportResult = await page.evaluate(async (downloadName) => {
    const { GLTFExporter } = await import("three/addons/exporters/GLTFExporter.js");
    const roots = window.__BF3D_GLB_EXPORT_ROOTS__;
    for (const root of roots) root.updateMatrixWorld(true);
    const exporter = new GLTFExporter();
    const arrayBuffer = await new Promise((resolve, reject) => {
      exporter.parse(
        roots,
        resolve,
        reject,
        {
          binary: true,
          onlyVisible: true,
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
    schema: "bf3d.glb_img2threejs_top_feed_gas_cleaning_export.v1",
    generatedAt: new Date().toISOString(),
    sourceUrl: url,
    candidateId,
    output,
    bytes: fileStat.size,
    browserReportedBytes: exportResult.bytes,
    sha256: createHash("sha256").update(payload).digest("hex"),
    runtime,
    exporter: {
      threeRevision: "160",
      binary: true,
      onlyVisible: true,
      maxTextureSize: 1024,
    },
    consoleErrors,
    pageErrors,
    passed:
      fileStat.size > 0 &&
      fileStat.size === exportResult.bytes &&
      consoleErrors.length === 0 &&
      pageErrors.length === 0 &&
      runtime.passed === true &&
      runtime.fittedProgrammaticShellCount === 1 &&
      runtime.fittedSteelRingCount === 13 &&
      runtime.fittedVerticalSeamCount === 12 &&
      runtime.thermalIdentityBandCount === 10 &&
      runtime.pressureIdentityBandCount === 3 &&
      runtime.identityBandSchema === "bf3d.non_physical_segmented_identity_band.v1" &&
      runtime.identityBandsPhysical === false &&
      runtime.ringSemanticSeparation === true &&
      runtime.maintenanceAccessSchema === "bf3d.physical_maintenance_access.v1" &&
      runtime.fittedMaintenancePlatformCount === 7 &&
      runtime.fittedWalkwayDeckCount === 7 &&
      runtime.fittedGuardrailRingCount === 14 &&
      runtime.fittedGuardrailPostCount === 194 &&
      runtime.fittedSupportBracketCount === 100 &&
      runtime.fittedAccessLadderCount === 6 &&
      runtime.fittedAccessLadderRungCount > 60 &&
      runtime.platformLevelIds?.join(",") === "P01,P02,P03,P04,P05,P06,P07" &&
      runtime.topFeedGasCleaningSchema === "bf3d.external_top_feed_gas_cleaning.v1" &&
      runtime.fittedConveyorSystemCount === 1 &&
      runtime.fittedConveyorBeltCount === 1 &&
      runtime.fittedConveyorRollerCount === 18 &&
      runtime.fittedConveyorTrestleCount === 4 &&
      runtime.fittedConveyorDischargeChuteCount === 1 &&
      runtime.fittedTopGasUptakeCount === 4 &&
      runtime.fittedGasDuctCount === 3 &&
      runtime.fittedGravityDustCatcherCount === 1 &&
      runtime.fittedFineDustCollectorCount === 1 &&
      runtime.fittedDustHopperCount === 5 &&
      runtime.fittedExternalProcessSupportCount === 16 &&
      runtime.fineDustCollectorEquipmentTypeStatus === "candidate_pending_engineering_confirmation" &&
      runtime.appearanceContractVersion === "bf3d.img2threejs.appearance.v2" &&
      runtime.appearanceContractSource === "WEB_60_IMG2THREEJS_20260725_R4_RING_SEMANTICS" &&
      runtime.fittedSurfaceTangentSpace === true &&
      runtime.hybridSuppressedEquipmentCount === 3 &&
      runtime.sanitizedPortableExtraPathCount >= 0 &&
      runtime.productionRouteChanged === false,
  };
  await writeFile(reportPath, `${JSON.stringify(report, null, 2)}\n`, "utf8");
  process.stdout.write(`${JSON.stringify(report, null, 2)}\n`);
  if (!report.passed) process.exitCode = 1;
} finally {
  await browser.close();
}
