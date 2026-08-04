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
  "GL02_FORMAL_IMG2THREEJS_RING_SEMANTICS_R4.glb";
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
    path.join(path.dirname(assetPath), "ring_semantics_glb_reopen_check.json"),
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
      physicalShellMetadataCount: 0,
      physicalReinforcementMetadataCount: 0,
      physicalSeamMetadataCount: 0,
      physicalAccessMetadataCount: 0,
      thermalIdentityBandCount: 0,
      pressureIdentityBandCount: 0,
      nonPhysicalBandCount: 0,
      segmentedBandCount: 0,
      brightAccessMaterialCount: 0,
      darkStructuralMaterialCount: 0,
      thermalIdentityMaterialCount: 0,
      pressureIdentityMaterialCount: 0,
    };
    const materials = new Set();
    gltf.scene.traverse((object) => {
      if (object !== gltf.scene) result.nodeCount += 1;
      const name = object.name || "";
      if (object.isMesh) {
        result.meshCount += 1;
        const objectMaterials = Array.isArray(object.material)
          ? object.material
          : [object.material];
        for (const material of objectMaterials) if (material) materials.add(material);
      }
      if (name.startsWith("SENSOR_")) result.formalSensorCount += 1;
      if (/^SENSOR_T_body_L(?:7|8|9|10|11|12|13|14|15|16)_[A-H]$/.test(name)) {
        result.bodyTemperatureSensorCount += 1;
      }
      if (/^GL02_INT30_PRESSURE_(?:LOWER|MIDDLE|UPPER)_[A-F]$/.test(name)) {
        result.staticPressureOverlayCount += 1;
      }
      if (name === "IMG2THREEJS_FITTED_GL02_SHELL") {
        result.fittedProgrammaticShellCount += 1;
      }
      if (name.startsWith("IMG2THREEJS_FITTED_STEEL_RING_")) {
        result.fittedSteelRingCount += 1;
      }
      if (name.startsWith("IMG2THREEJS_FITTED_VERTICAL_SEAM_")) {
        result.fittedVerticalSeamCount += 1;
      }
      if (object.userData?.semanticKind === "physical_furnace_shell" && object.userData?.physical === true) {
        result.physicalShellMetadataCount += 1;
      }
      if (object.userData?.semanticKind === "physical_shell_reinforcement_ring" && object.userData?.physical === true) {
        result.physicalReinforcementMetadataCount += 1;
      }
      if (object.userData?.semanticKind === "physical_shell_vertical_seam" && object.userData?.physical === true) {
        result.physicalSeamMetadataCount += 1;
      }
      if (object.userData?.semanticKind === "physical_access_platform_guardrail" && object.userData?.physical === true) {
        result.physicalAccessMetadataCount += 1;
      }
      if (name.startsWith("diagnostic-band-L")) result.thermalIdentityBandCount += 1;
      if (name.startsWith("static-pressure-ring-")) result.pressureIdentityBandCount += 1;
      if (object.userData?.physical === false) result.nonPhysicalBandCount += 1;
      if (object.userData?.segmented === true) result.segmentedBandCount += 1;
    });
    for (const material of materials) {
      if (material.name === "bright galvanized access steel") {
        result.brightAccessMaterialCount += 1;
      }
      if (material.name === "dark solid structural steel") {
        result.darkStructuralMaterialCount += 1;
      }
      if (material.name === "non-physical segmented thermal layer identity") {
        result.thermalIdentityMaterialCount += 1;
      }
      if (material.name === "non-physical segmented static pressure layer identity") {
        result.pressureIdentityMaterialCount += 1;
      }
    }
    return result;
  }, assetUrl);

  const passed =
    counts.formalSensorCount === 115 &&
    counts.bodyTemperatureSensorCount === 80 &&
    counts.staticPressureOverlayCount === 18 &&
    counts.fittedProgrammaticShellCount === 1 &&
    counts.fittedSteelRingCount === 13 &&
    counts.fittedVerticalSeamCount === 12 &&
    counts.physicalShellMetadataCount === 1 &&
    counts.physicalReinforcementMetadataCount === 13 &&
    counts.physicalSeamMetadataCount === 12 &&
    counts.physicalAccessMetadataCount >= 1 &&
    counts.thermalIdentityBandCount === 10 &&
    counts.pressureIdentityBandCount === 3 &&
    counts.nonPhysicalBandCount === 13 &&
    counts.segmentedBandCount === 13 &&
    counts.brightAccessMaterialCount === 1 &&
    counts.darkStructuralMaterialCount === 1 &&
    counts.thermalIdentityMaterialCount === 1 &&
    counts.pressureIdentityMaterialCount === 1 &&
    consoleErrors.length === 0 &&
    pageErrors.length === 0;
  const report = {
    schema: "bf3d.glb_img2threejs_ring_semantics_reopen_check.v1",
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
