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
const sourceRelativePath =
  "PT/高炉3D模型/work/WEB_60_GLB_IMG2THREEJS_BRIDGE_20260724_R1/assets/" +
  "GL02_FORMAL_IMG2THREEJS_MAINTENANCE_ACCESS_R5.glb";
const outputRelativeFolder = "PT/高炉3D模型/模型资产库/09_高炉本体133点Billboard";
const sourcePath = path.resolve(argument("--source", path.join(workspace, sourceRelativePath)));
const outputFolder = path.resolve(
  argument("--output-folder", path.join(workspace, outputRelativeFolder)),
);
const outputPath = path.join(outputFolder, "GL02_FURNACE_BODY_R1.glb");
const pointManifestPath = path.join(outputFolder, "sensor_billboards.v1.json");
const exportReportPath = path.join(outputFolder, "furnace_body_export_report.json");
const executablePath = argument(
  "--chromium",
  "C:/Users/hmw20/AppData/Local/ms-playwright/chromium-1228/chrome-win64/chrome.exe",
);
const shellUrl = argument(
  "--shell-url",
  "http://127.0.0.1:8096/PT/%E9%AB%98%E7%82%893D%E6%A8%A1%E5%9E%8B/work/" +
    "WEB_60_GLB_IMG2THREEJS_BRIDGE_20260724_R1/preview/",
);
const sourceUrl = argument(
  "--source-url",
  `http://127.0.0.1:8096/${sourceRelativePath
    .split("/")
    .map((part) => encodeURIComponent(part))
    .join("/")}`,
);

await readFile(sourcePath);
await mkdir(outputFolder, { recursive: true });

const browser = await chromium.launch({ headless: true, executablePath });
const page = await browser.newPage({ viewport: { width: 1440, height: 900 } });
const consoleErrors = [];
const pageErrors = [];
page.on("console", (message) => {
  if (message.type() === "error") consoleErrors.push(message.text());
});
page.on("pageerror", (error) => pageErrors.push(error.message));

try {
  await page.goto(shellUrl, { waitUntil: "networkidle", timeout: 120_000 });
  const fileName = path.basename(outputPath);
  const downloadPromise = page.waitForEvent("download", { timeout: 180_000 });
  const runtime = await page.evaluate(async ({ url, downloadName }) => {
    const THREE = await import("three");
    const { GLTFLoader } = await import("three/addons/loaders/GLTFLoader.js");
    const { GLTFExporter } = await import("three/addons/exporters/GLTFExporter.js");
    const gltf = await new GLTFLoader().loadAsync(url);
    const root = gltf.scene;
    root.name = "GL02_FURNACE_BODY_R1";
    root.updateMatrixWorld(true);

    const formalPattern = /^SENSOR_/;
    const pressurePattern = /^GL02_INT30_PRESSURE_(LOWER|MIDDLE|UPPER)_([A-F])$/;
    const bodyTemperaturePattern =
      /^SENSOR_T_body_L(7|8|9|10|11|12|13|14|15|16)_([A-H])$/;
    const externalKinds = new Set([
      "physical_external_top_feed_and_gas_cleaning_system",
      "physical_top_feed_conveyor_system",
      "physical_top_gas_cleaning_system",
      "physical_top_feed_conveyor_belt",
      "physical_conveyor_longitudinal_trusses",
      "physical_conveyor_diagonal_trusses",
      "physical_conveyor_rollers",
      "physical_conveyor_drive_drum",
      "physical_conveyor_support_trestle",
      "physical_conveyor_support_leg",
      "physical_conveyor_support_crossbeam",
      "physical_conveyor_service_catwalk",
      "physical_conveyor_catwalk_guardrail",
      "physical_charging_discharge_chute",
      "physical_top_gas_uptake",
      "physical_raw_gas_downcomer",
      "physical_interstage_gas_duct",
      "physical_clean_gas_outlet_duct",
      "physical_gravity_dust_catcher",
      "physical_static_pressure_fine_dust_collector_candidate",
      "physical_dust_hopper",
      "physical_dust_catcher_support_legs",
      "physical_fine_dust_collector_supports",
    ]);
    const pointRecords = [];
    const removeSet = new Set();
    const vector = new THREE.Vector3();

    const shortFormalLabel = (name) => {
      const bodyMatch = name.match(bodyTemperaturePattern);
      if (bodyMatch) return `L${bodyMatch[1]}·${bodyMatch[2]}`;
      return name.replace(/^SENSOR_/, "").replaceAll("_", "·");
    };
    const formalCategory = (name) => {
      if (bodyTemperaturePattern.test(name)) return "body_temperature";
      if (/^SENSOR_T_taphole/i.test(name)) return "taphole_temperature";
      if (/^SENSOR_T_/i.test(name)) return "temperature";
      if (/^SENSOR_P_/i.test(name)) return "pressure";
      if (/^SENSOR_(?:F|Q)_/i.test(name)) return "flow";
      return "process_sensor";
    };

    root.traverse((object) => {
      if (object === root) return;
      const name = object.name || "";
      const pressureMatch = name.match(pressurePattern);
      if (formalPattern.test(name) || pressureMatch) {
        object.getWorldPosition(vector);
        const isPressure = Boolean(pressureMatch);
        pointRecords.push({
          id: name,
          source_kind: isPressure ? "static_pressure_18" : "formal_sensor_115",
          category: isPressure ? "static_pressure" : formalCategory(name),
          short_label: isPressure
            ? `静压·${({ LOWER: "低", MIDDLE: "中", UPPER: "高" })[pressureMatch[1]]}·${pressureMatch[2]}`
            : shortFormalLabel(name),
          display_name: isPressure
            ? `${({ LOWER: "低位", MIDDLE: "中位", UPPER: "高位" })[pressureMatch[1]]}静压力 ${pressureMatch[2]}`
            : name.replace(/^SENSOR_/, "").replaceAll("_", " "),
          position: [
            Number(vector.x.toFixed(6)),
            Number(vector.y.toFixed(6)),
            Number(vector.z.toFixed(6)),
          ],
          coordinate_authority: isPressure
            ? "VIS30 static-pressure overlay coordinate"
            : "formal GL02 sensor-node coordinate",
          realtime_value: null,
          unit: null,
        });
        removeSet.add(object);
        return;
      }
      const semanticKind = object.userData?.semanticKind || "";
      const schema = object.userData?.schema || "";
      if (
        externalKinds.has(semanticKind) ||
        schema === "bf3d.external_top_feed_gas_cleaning.v1" ||
        /^IMG2THREEJS_(?:EXTERNAL_TOP_FEED_GAS_CLEANING|TOP_FEED_CONVEYOR|TOP_GAS_CLEANING)_R6/.test(
          name,
        )
      ) {
        removeSet.add(object);
        return;
      }
      if (
        object.userData?.physical === false ||
        /^diagnostic-band-L/.test(name) ||
        /^static-pressure-ring-/.test(name)
      ) {
        removeSet.add(object);
      }
    });

    // Remove highest selected ancestors first; children below a selected ancestor need no
    // separate operation. Sensor anchors are leaves in the source asset.
    const rootsToRemove = [...removeSet].filter((object) => {
      let cursor = object.parent;
      while (cursor) {
        if (removeSet.has(cursor)) return false;
        cursor = cursor.parent;
      }
      return true;
    });
    for (const object of rootsToRemove) object.removeFromParent();
    root.updateMatrixWorld(true);
    root.userData = {
      ...(root.userData || {}),
      schema: "bf3d.furnace_body_without_external_systems.v1",
      sourceAsset: "GL02_FORMAL_IMG2THREEJS_MAINTENANCE_ACCESS_R5.glb",
      removedExternalTopFeedAndGasCleaning: true,
      removedEmbeddedSensorMarkers: true,
      removedNonPhysicalIdentityBands: true,
      billboardManifest: "sensor_billboards.v1.json",
      productionRouteChanged: false,
    };

    const counts = {
      modelNodeCount: 0,
      modelMeshCount: 0,
      formalSensorNodeCount: 0,
      staticPressureNodeCount: 0,
      nonPhysicalBandCount: 0,
      externalSystemNodeCount: 0,
      fittedProgrammaticShellCount: 0,
      fittedSteelRingCount: 0,
      fittedVerticalSeamCount: 0,
      maintenancePlatformCount: 0,
      guardrailRingCount: 0,
      accessLadderCount: 0,
      tapholeCount: 0,
    };
    root.traverse((object) => {
      if (object !== root) counts.modelNodeCount += 1;
      if (object.isMesh) counts.modelMeshCount += 1;
      const name = object.name || "";
      const kind = object.userData?.semanticKind || "";
      if (formalPattern.test(name)) counts.formalSensorNodeCount += 1;
      if (pressurePattern.test(name)) counts.staticPressureNodeCount += 1;
      if (object.userData?.physical === false) counts.nonPhysicalBandCount += 1;
      if (
        externalKinds.has(kind) ||
        object.userData?.schema === "bf3d.external_top_feed_gas_cleaning.v1"
      ) {
        counts.externalSystemNodeCount += 1;
      }
      if (name === "IMG2THREEJS_FITTED_GL02_SHELL") counts.fittedProgrammaticShellCount += 1;
      if (name.startsWith("IMG2THREEJS_FITTED_STEEL_RING_")) counts.fittedSteelRingCount += 1;
      if (name.startsWith("IMG2THREEJS_FITTED_VERTICAL_SEAM_")) counts.fittedVerticalSeamCount += 1;
      if (kind === "physical_maintenance_platform") counts.maintenancePlatformCount += 1;
      if (kind === "physical_double_guardrail_ring") counts.guardrailRingCount += 1;
      if (kind === "physical_connecting_access_ladder") counts.accessLadderCount += 1;
      if (/TAPHOLE/i.test(name) && object.isMesh) counts.tapholeCount += 1;
    });

    pointRecords.sort((a, b) => a.id.localeCompare(b.id, "zh-CN"));
    const formalPoints = pointRecords.filter(
      (point) => point.source_kind === "formal_sensor_115",
    );
    const pressurePoints = pointRecords.filter(
      (point) => point.source_kind === "static_pressure_18",
    );
    const bodyBox = new THREE.Box3().setFromObject(root);
    const bodyCenter = bodyBox.getCenter(new THREE.Vector3());
    const bodySize = bodyBox.getSize(new THREE.Vector3());
    const manifest = {
      schema: "bf3d.sensor_billboards.v1",
      generated_at: new Date().toISOString(),
      coordinate_space: "GL02_FURNACE_BODY_R1 model world",
      body_model: "GL02_FURNACE_BODY_R1.glb",
      source_model: "GL02_FORMAL_IMG2THREEJS_MAINTENANCE_ACCESS_R5.glb",
      billboard_implementation: "THREE.Sprite + CanvasTexture",
      billboard_behavior: "camera_facing_in_renderer",
      live_data_boundary:
        "realtime_value and unit are null placeholders; bind by point id through an adapter",
      counts: {
        formal_sensor_115: formalPoints.length,
        static_pressure_18: pressurePoints.length,
        total: pointRecords.length,
      },
      body_bounds: {
        min: bodyBox.min.toArray().map((value) => Number(value.toFixed(6))),
        max: bodyBox.max.toArray().map((value) => Number(value.toFixed(6))),
        center: bodyCenter.toArray().map((value) => Number(value.toFixed(6))),
        size: bodySize.toArray().map((value) => Number(value.toFixed(6))),
      },
      points: pointRecords,
    };

    const exporter = new GLTFExporter();
    const arrayBuffer = await new Promise((resolve, reject) => {
      exporter.parse(
        root,
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
    return {
      bytes: arrayBuffer.byteLength,
      counts,
      pointManifest: manifest,
      removedRootCount: rootsToRemove.length,
    };
  }, { url: sourceUrl, downloadName: fileName });
  const download = await downloadPromise;
  await download.saveAs(outputPath);

  const outputPayload = await readFile(outputPath);
  const sourcePayload = await readFile(sourcePath);
  const outputStat = await stat(outputPath);
  const report = {
    schema: "bf3d.furnace_body_billboard_asset_export.v1",
    generatedAt: new Date().toISOString(),
    sourcePath,
    sourceUrl,
    outputPath,
    pointManifestPath,
    sourceBytes: sourcePayload.byteLength,
    sourceSha256: createHash("sha256").update(sourcePayload).digest("hex"),
    bytes: outputStat.size,
    browserReportedBytes: runtime.bytes,
    sha256: createHash("sha256").update(outputPayload).digest("hex"),
    counts: runtime.counts,
    pointCounts: runtime.pointManifest.counts,
    removedRootCount: runtime.removedRootCount,
    consoleErrors,
    pageErrors,
    truthBoundary:
      "The furnace body is a visual/integration asset; dimensions and E/illustrative geometry are not construction authority.",
    productionRouteChanged: false,
    passed:
      outputStat.size > 0 &&
      outputStat.size === runtime.bytes &&
      runtime.pointManifest.counts.formal_sensor_115 === 115 &&
      runtime.pointManifest.counts.static_pressure_18 === 18 &&
      runtime.pointManifest.counts.total === 133 &&
      runtime.counts.formalSensorNodeCount === 0 &&
      runtime.counts.staticPressureNodeCount === 0 &&
      runtime.counts.nonPhysicalBandCount === 0 &&
      runtime.counts.externalSystemNodeCount === 0 &&
      runtime.counts.fittedProgrammaticShellCount === 1 &&
      runtime.counts.fittedSteelRingCount === 13 &&
      runtime.counts.fittedVerticalSeamCount === 12 &&
      runtime.counts.maintenancePlatformCount === 7 &&
      runtime.counts.guardrailRingCount === 14 &&
      runtime.counts.accessLadderCount === 6 &&
      consoleErrors.length === 0 &&
      pageErrors.length === 0,
  };
  await writeFile(
    pointManifestPath,
    `${JSON.stringify(runtime.pointManifest, null, 2)}\n`,
    "utf8",
  );
  await writeFile(exportReportPath, `${JSON.stringify(report, null, 2)}\n`, "utf8");
  process.stdout.write(`${JSON.stringify(report, null, 2)}\n`);
  if (!report.passed) process.exitCode = 1;
} finally {
  await browser.close();
}
