import { readFile, writeFile } from "node:fs/promises";
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
const assetRelativePath =
  "PT/高炉3D模型/work/WEB_60_GLB_IMG2THREEJS_BRIDGE_20260724_R1/assets/" +
  "GL02_FORMAL_IMG2THREEJS_TOP_FEED_GAS_CLEANING_R6.glb";
const assetPath = path.resolve(argument("--asset", path.join(workspace, assetRelativePath)));
const assetUrl = argument(
  "--url",
  `http://127.0.0.1:8096/${assetRelativePath
    .split("/")
    .map((part) => encodeURIComponent(part))
    .join("/")}`,
);
const output = path.resolve(
  argument(
    "--output",
    path.join(path.dirname(assetPath), "top_feed_gas_cleaning_glb_reopen_check.json"),
  ),
);
const executablePath = argument(
  "--chromium",
  "C:/Users/hmw20/AppData/Local/ms-playwright/chromium-1228/chrome-win64/chrome.exe",
);

await readFile(assetPath);
const browser = await chromium.launch({ headless: true, executablePath });
const page = await browser.newPage({ viewport: { width: 1440, height: 900 } });
const consoleErrors = [];
const pageErrors = [];
page.on("console", (message) => {
  if (message.type() === "error") consoleErrors.push(message.text());
});
page.on("pageerror", (error) => pageErrors.push(error.message));

try {
  await page.goto(
    "http://127.0.0.1:8096/PT/%E9%AB%98%E7%82%893D%E6%A8%A1%E5%9E%8B/work/" +
      "WEB_60_GLB_IMG2THREEJS_BRIDGE_20260724_R1/preview/",
    { waitUntil: "networkidle", timeout: 120_000 },
  );
  await page.waitForFunction(
    () => window.__BF3D_GLB_IMG2THREEJS_BRIDGE__?.passed === true,
    null,
    { timeout: 120_000 },
  );
  const counts = await page.evaluate(async (url) => {
    const { GLTFLoader } = await import("three/addons/loaders/GLTFLoader.js");
    const gltf = await new GLTFLoader().loadAsync(url);
    const result = {
      nodeCount: 0,
      meshCount: 0,
      formalSensorCount: 0,
      bodyTemperatureSensorCount: 0,
      staticPressureOverlayCount: 0,
      fittedProgrammaticShellCount: 0,
      fittedSteelRingCount: 0,
      fittedVerticalSeamCount: 0,
      thermalIdentityBandCount: 0,
      pressureIdentityBandCount: 0,
      nonPhysicalBandCount: 0,
      maintenanceAccessSystemCount: 0,
      maintenancePlatformCount: 0,
      walkwayDeckCount: 0,
      guardrailRingCount: 0,
      guardrailPostInstanceCount: 0,
      radialBracketInstanceCount: 0,
      diagonalBraceInstanceCount: 0,
      accessLadderCount: 0,
      accessLadderSideRailCount: 0,
      accessLadderRungInstanceCount: 0,
      externalTopFeedGasCleaningSystemCount: 0,
      conveyorSystemCount: 0,
      conveyorBeltCount: 0,
      conveyorRollerInstanceCount: 0,
      conveyorTrestleCount: 0,
      conveyorDischargeChuteCount: 0,
      topGasCleaningSystemCount: 0,
      topGasUptakeCount: 0,
      gasDuctCount: 0,
      gravityDustCatcherCount: 0,
      fineDustCollectorCount: 0,
      dustHopperCount: 0,
      externalProcessSupportCount: 0,
      pendingEquipmentTypeCount: 0,
      originalMaintenancePlatformCount: 0,
      originalAccessTowerBridgeCount: 0,
      originalGasUptakeDowncomerCount: 0,
      originalShellSectionCount: 0,
      platformIds: [],
    };
    gltf.scene.traverse((object) => {
      if (object !== gltf.scene) result.nodeCount += 1;
      const name = object.name || "";
      const kind = object.userData?.semanticKind || "";
      const instanceCount = Number(object.userData?.instanceCount || object.count || 0);
      if (object.isMesh) result.meshCount += 1;
      if (name.startsWith("SENSOR_")) result.formalSensorCount += 1;
      if (/^SENSOR_T_body_L(?:7|8|9|10|11|12|13|14|15|16)_[A-H]$/.test(name)) {
        result.bodyTemperatureSensorCount += 1;
      }
      if (/^GL02_INT30_PRESSURE_(?:LOWER|MIDDLE|UPPER)_[A-F]$/.test(name)) {
        result.staticPressureOverlayCount += 1;
      }
      if (name === "IMG2THREEJS_FITTED_GL02_SHELL") result.fittedProgrammaticShellCount += 1;
      if (name.startsWith("IMG2THREEJS_FITTED_STEEL_RING_")) result.fittedSteelRingCount += 1;
      if (name.startsWith("IMG2THREEJS_FITTED_VERTICAL_SEAM_")) result.fittedVerticalSeamCount += 1;
      if (name.startsWith("diagnostic-band-L")) result.thermalIdentityBandCount += 1;
      if (name.startsWith("static-pressure-ring-")) result.pressureIdentityBandCount += 1;
      if (object.userData?.physical === false) result.nonPhysicalBandCount += 1;
      if (kind === "physical_maintenance_access_system") result.maintenanceAccessSystemCount += 1;
      if (kind === "physical_maintenance_platform") {
        result.maintenancePlatformCount += 1;
        result.platformIds.push(object.userData.platformId);
      }
      if (kind === "physical_annular_walkway_deck") result.walkwayDeckCount += 1;
      if (kind === "physical_double_guardrail_ring") result.guardrailRingCount += 1;
      if (kind === "physical_guardrail_posts") result.guardrailPostInstanceCount += instanceCount;
      if (kind === "physical_radial_support_brackets") result.radialBracketInstanceCount += instanceCount;
      if (kind === "physical_diagonal_support_braces") result.diagonalBraceInstanceCount += instanceCount;
      if (kind === "physical_connecting_access_ladder") result.accessLadderCount += 1;
      if (kind === "physical_access_ladder_side_rail") result.accessLadderSideRailCount += 1;
      if (kind === "physical_access_ladder_rungs") result.accessLadderRungInstanceCount += instanceCount;
      if (kind === "physical_external_top_feed_and_gas_cleaning_system") {
        result.externalTopFeedGasCleaningSystemCount += 1;
      }
      if (kind === "physical_top_feed_conveyor_system") result.conveyorSystemCount += 1;
      if (kind === "physical_top_feed_conveyor_belt") result.conveyorBeltCount += 1;
      if (kind === "physical_conveyor_rollers") result.conveyorRollerInstanceCount += instanceCount;
      if (kind === "physical_conveyor_support_trestle") {
        result.conveyorTrestleCount += 1;
        result.externalProcessSupportCount += 1;
      }
      if (kind === "physical_charging_discharge_chute") result.conveyorDischargeChuteCount += 1;
      if (kind === "physical_top_gas_cleaning_system") result.topGasCleaningSystemCount += 1;
      if (kind === "physical_top_gas_uptake") result.topGasUptakeCount += 1;
      if (
        kind === "physical_raw_gas_downcomer" ||
        kind === "physical_interstage_gas_duct" ||
        kind === "physical_clean_gas_outlet_duct"
      ) {
        result.gasDuctCount += 1;
      }
      if (kind === "physical_gravity_dust_catcher") result.gravityDustCatcherCount += 1;
      if (kind === "physical_static_pressure_fine_dust_collector_candidate") {
        result.fineDustCollectorCount += 1;
      }
      if (kind === "physical_dust_hopper") result.dustHopperCount += 1;
      if (kind === "physical_dust_catcher_support_legs") {
        result.externalProcessSupportCount += instanceCount;
      }
      if (kind === "physical_fine_dust_collector_supports") {
        result.externalProcessSupportCount += instanceCount;
      }
      if (object.userData?.equipmentTypeStatus === "candidate_pending_engineering_confirmation") {
        result.pendingEquipmentTypeCount += 1;
      }
      if (/^APPROX_GL02_maintenance_platforms/i.test(name)) {
        result.originalMaintenancePlatformCount += 1;
      }
      if (/^APPROX_GL02_access_tower_and_bridges/i.test(name)) {
        result.originalAccessTowerBridgeCount += 1;
      }
      if (/^APPROX_GL02_gas_uptakes_and_downcomer/i.test(name)) {
        result.originalGasUptakeDowncomerCount += 1;
      }
      if (/^APPROX_GL02_FURNACE_(?:HEARTH|BOSH|BELLY|SHAFT|THROAT)$/i.test(name)) {
        result.originalShellSectionCount += 1;
      }
    });
    result.platformIds.sort();
    return result;
  }, assetUrl);

  const passed =
    counts.formalSensorCount === 115 &&
    counts.bodyTemperatureSensorCount === 80 &&
    counts.staticPressureOverlayCount === 18 &&
    counts.fittedProgrammaticShellCount === 1 &&
    counts.fittedSteelRingCount === 13 &&
    counts.fittedVerticalSeamCount === 12 &&
    counts.thermalIdentityBandCount === 10 &&
    counts.pressureIdentityBandCount === 3 &&
    counts.nonPhysicalBandCount === 13 &&
    counts.maintenanceAccessSystemCount === 1 &&
    counts.maintenancePlatformCount === 7 &&
    counts.walkwayDeckCount === 7 &&
    counts.guardrailRingCount === 14 &&
    counts.guardrailPostInstanceCount === 194 &&
    counts.radialBracketInstanceCount === 100 &&
    counts.diagonalBraceInstanceCount === 100 &&
    counts.accessLadderCount === 6 &&
    counts.accessLadderSideRailCount === 12 &&
    counts.accessLadderRungInstanceCount === 112 &&
    counts.externalTopFeedGasCleaningSystemCount === 1 &&
    counts.conveyorSystemCount === 1 &&
    counts.conveyorBeltCount === 1 &&
    counts.conveyorRollerInstanceCount === 18 &&
    counts.conveyorTrestleCount === 4 &&
    counts.conveyorDischargeChuteCount === 1 &&
    counts.topGasCleaningSystemCount === 1 &&
    counts.topGasUptakeCount === 4 &&
    counts.gasDuctCount === 3 &&
    counts.gravityDustCatcherCount === 1 &&
    counts.fineDustCollectorCount === 1 &&
    counts.dustHopperCount === 5 &&
    counts.externalProcessSupportCount === 16 &&
    counts.pendingEquipmentTypeCount >= 5 &&
    counts.originalMaintenancePlatformCount === 0 &&
    counts.originalAccessTowerBridgeCount === 0 &&
    counts.originalGasUptakeDowncomerCount === 0 &&
    counts.originalShellSectionCount === 0 &&
    counts.platformIds.join(",") === "P01,P02,P03,P04,P05,P06,P07" &&
    consoleErrors.length === 0 &&
    pageErrors.length === 0;
  const report = {
    schema: "bf3d.glb_img2threejs_top_feed_gas_cleaning_reopen_check.v1",
    generatedAt: new Date().toISOString(),
    assetPath,
    assetUrl,
    counts,
    consoleErrors,
    pageErrors,
    passed,
  };
  await writeFile(output, `${JSON.stringify(report, null, 2)}\n`, "utf8");
  process.stdout.write(`${JSON.stringify(report, null, 2)}\n`);
  if (!passed) process.exitCode = 1;
} finally {
  await browser.close();
}
