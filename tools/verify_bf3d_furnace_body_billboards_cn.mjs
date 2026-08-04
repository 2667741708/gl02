import { spawnSync } from "node:child_process";
import { readFile, writeFile } from "node:fs/promises";
import path from "node:path";

const workspace = process.cwd();
const sourceFolder = path.join(
  workspace,
  "PT",
  "高炉3D模型",
  "模型资产库",
  "09_高炉本体133点Billboard",
);
const cnFolder = path.join(
  workspace,
  "PT",
  "高炉3D模型",
  "模型资产库",
  "09_高炉本体133点Billboard_cn",
);
const url =
  "http://127.0.0.1:8096/PT/%E9%AB%98%E7%82%893D%E6%A8%A1%E5%9E%8B/" +
  "%E6%A8%A1%E5%9E%8B%E8%B5%84%E4%BA%A7%E5%BA%93/" +
  "09_%E9%AB%98%E7%82%89%E6%9C%AC%E4%BD%93133%E7%82%B9Billboard_cn/preview/";
const runtimeReportPath = path.join(cnFolder, "billboard_validation_report.json");
const screenshotPath = path.join(cnFolder, "网页预览.png");
const mobileScreenshotPath = path.join(cnFolder, "reports", "chromium_390x844.png");
const outputPath = path.join(cnFolder, "cn_variant_validation_report.json");

const verifier = path.join(
  workspace,
  "tools",
  "verify_bf3d_furnace_body_billboards.mjs",
);
const child = spawnSync(
  process.execPath,
  [
    verifier,
    "--url",
    url,
    "--output",
    runtimeReportPath,
    "--screenshot",
    screenshotPath,
    "--mobile-screenshot",
    mobileScreenshotPath,
    "--mock-pspace",
  ],
  {
    cwd: workspace,
    env: process.env,
    encoding: "utf8",
    maxBuffer: 10 * 1024 * 1024,
  },
);
if (child.status !== 0) {
  process.stderr.write(child.stderr || child.stdout || "中文 Billboard 浏览器验证失败\n");
  process.exit(child.status || 1);
}

const [sourceManifest, cnManifest, mapping, runtimeReport] = await Promise.all([
  readFile(path.join(sourceFolder, "sensor_billboards.v1.json"), "utf8").then(JSON.parse),
  readFile(path.join(cnFolder, "sensor_billboards.v1.json"), "utf8").then(JSON.parse),
  readFile(path.join(cnFolder, "cn_label_mapping.v1.json"), "utf8").then(JSON.parse),
  readFile(runtimeReportPath, "utf8").then(JSON.parse),
]);
const sourceIds = sourceManifest.points.map((point) => point.id).sort();
const cnIds = cnManifest.points.map((point) => point.id).sort();
const allLabelsChinese = cnManifest.points.every((point) =>
  /[\u3400-\u9fff]/u.test(point.short_label),
);
const idsPreserved =
  sourceIds.length === cnIds.length &&
  sourceIds.every((id, index) => id === cnIds[index]);
const pointById = new Map(cnManifest.points.map((point) => [point.id, point]));
const semanticSpotChecks = {
  totalPressureDrop:
    pointById.get("SENSOR_DP_total")?.short_label === "全炉压差",
  gasUtilization:
    pointById.get("SENSOR_GasUtil")?.short_label === "煤气利用",
  southTaphole:
    pointById.get("SENSOR_T_taphole_1")?.short_label === "南铁口温",
  northTaphole:
    pointById.get("SENSOR_T_taphole_2")?.short_label === "北铁口温",
  bodyTemperature:
    pointById.get("SENSOR_T_body_L10_A")?.short_label === "身下温·L10A",
  furnaceBelly:
    pointById.get("SENSOR_T_body_L7_A")?.short_label === "腹下温·L7A",
  furnaceWaist:
    pointById.get("SENSOR_T_body_L9_A")?.short_label === "炉腰温·L9A",
  furnaceBodyMiddle:
    pointById.get("SENSOR_T_body_L14_A")?.short_label === "身中温·L14A",
  furnaceBodyUpper:
    pointById.get("SENSOR_T_body_L16_A")?.short_label === "身上温·L16A",
  furnaceThroat:
    pointById.get("SENSOR_T_throat_A")?.short_label === "喉温·A",
  staticPressure:
    pointById.get("GL02_INT30_PRESSURE_MIDDLE_B")?.short_label ===
    "身中静压·B",
  canonicalBinding:
    pointById.get("GL02_INT30_PRESSURE_MIDDLE_B")?.canonical_id ===
    "P_static_middle_B",
  unitMapping:
    pointById.get("SENSOR_T_body_L10_A")?.display_unit === "℃" &&
    pointById.get("GL02_INT30_PRESSURE_MIDDLE_B")?.display_unit === "kPa",
};
const desktopContract = runtimeReport.desktop.contract;
const report = {
  schema: "bf3d.furnace_body_billboard_cn_variant_validation.v1",
  generatedAt: new Date().toISOString(),
  url,
  runtimeReportPath,
  screenshotPath,
  sourcePointCount: sourceManifest.points.length,
  chinesePointCount: cnManifest.points.length,
  chineseLabelCount: cnManifest.points.filter((point) =>
    /[\u3400-\u9fff]/u.test(point.short_label),
  ).length,
  uniqueIdCount: new Set(cnIds).size,
  idsPreserved,
  allLabelsChinese,
  mappingCounts: mapping.counts,
  semanticSpotChecks,
  runtime: {
    desktopPassed: runtimeReport.desktop.passed,
    mobilePassed: runtimeReport.mobile.passed,
    locale: desktopContract.locale,
    labelVariant: desktopContract.labelVariant,
    chineseLabelCount: desktopContract.chineseLabelCount,
    spriteCount: desktopContract.spriteCount,
    totalBillboardCount: desktopContract.totalBillboardCount,
    allBillboardsUseThreeSprite: desktopContract.allBillboardsUseThreeSprite,
  },
  passed:
    runtimeReport.passed === true &&
    cnManifest.locale === "zh-CN" &&
    cnManifest.label_variant === "chinese_semantic_abbreviation" &&
    cnManifest.points.length === 133 &&
    allLabelsChinese &&
    idsPreserved &&
    new Set(cnIds).size === 133 &&
    Object.values(semanticSpotChecks).every(Boolean) &&
    desktopContract.locale === "zh-CN" &&
    desktopContract.labelVariant === "chinese_semantic_abbreviation" &&
    desktopContract.chineseLabelCount === 133 &&
    desktopContract.spriteCount === 133 &&
    desktopContract.allBillboardsUseThreeSprite === true,
};
await writeFile(outputPath, `${JSON.stringify(report, null, 2)}\n`, "utf8");
process.stdout.write(`${JSON.stringify({
  output: outputPath,
  pointCount: report.chinesePointCount,
  chineseLabelCount: report.chineseLabelCount,
  idsPreserved: report.idsPreserved,
  desktopPassed: report.runtime.desktopPassed,
  mobilePassed: report.runtime.mobilePassed,
  passed: report.passed,
})}\n`);
if (!report.passed) process.exitCode = 1;
