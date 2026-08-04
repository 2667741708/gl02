import { createHash } from "node:crypto";
import { readFile, readdir, stat, writeFile } from "node:fs/promises";
import path from "node:path";

const workspace = process.cwd();
const catalogRoot = path.join(workspace, "PT", "高炉3D模型", "模型资产库");
const catalogPath = path.join(catalogRoot, "asset_catalog.v1.json");
const captureReportPath = path.join(catalogRoot, "preview_capture_report.json");
const outputPath = path.join(catalogRoot, "asset_catalog_validation.json");

function sha256(payload) {
  return createHash("sha256").update(payload).digest("hex");
}

function pngDimensions(payload) {
  const signature = "89504e470d0a1a0a";
  if (payload.subarray(0, 8).toString("hex") !== signature) return null;
  return {
    width: payload.readUInt32BE(16),
    height: payload.readUInt32BE(20),
  };
}

const catalog = JSON.parse(await readFile(catalogPath, "utf8"));
const captureReport = JSON.parse(await readFile(captureReportPath, "utf8"));
const captureByFolder = new Map(
  captureReport.results.map((item) => [item.folder, item]),
);
const folderNames = new Set();
const results = [];

for (const asset of catalog.assets) {
  const failures = [];
  if (folderNames.has(asset.folder)) failures.push("duplicate_folder");
  folderNames.add(asset.folder);
  const folder = path.join(catalogRoot, asset.folder);
  const folderStat = await stat(folder).catch(() => null);
  if (!folderStat?.isDirectory()) failures.push("missing_asset_folder");
  const entries = folderStat?.isDirectory()
    ? await readdir(folder, { withFileTypes: true })
    : [];
  const glbFiles = entries.filter(
    (entry) => entry.isFile() && entry.name.toLowerCase().endsWith(".glb"),
  );
  const pngFiles = entries.filter(
    (entry) => entry.isFile() && entry.name.toLowerCase().endsWith(".png"),
  );
  if (glbFiles.length !== 1) failures.push(`glb_count_${glbFiles.length}`);
  if (pngFiles.length !== 1) failures.push(`png_count_${pngFiles.length}`);
  if (!entries.some((entry) => entry.isFile() && entry.name === "资产说明.md")) {
    failures.push("missing_asset_readme");
  }

  const modelPath = path.join(folder, asset.model_file);
  const previewPath = path.join(folder, asset.preview_file);
  const sourcePath = path.resolve(workspace, asset.source_path);
  const modelPayload = await readFile(modelPath).catch(() => null);
  const previewPayload = await readFile(previewPath).catch(() => null);
  const sourcePayload = await readFile(sourcePath).catch(() => null);
  if (!modelPayload) failures.push("missing_model_file");
  if (!previewPayload) failures.push("missing_preview_file");
  if (!sourcePayload) failures.push("missing_source_file");
  const modelSha256 = modelPayload ? sha256(modelPayload) : null;
  const sourceSha256 = sourcePayload ? sha256(sourcePayload) : null;
  const isDerived = asset.derivation_policy === "generated_derivative";
  if (modelSha256 !== asset.sha256) failures.push("catalog_model_hash_mismatch");
  if (isDerived) {
    if (!asset.source_sha256) failures.push("derived_asset_missing_source_hash");
    if (sourceSha256 !== asset.source_sha256) {
      failures.push("derived_asset_source_hash_mismatch");
    }
  } else {
    if (sourceSha256 !== asset.sha256) failures.push("catalog_source_hash_mismatch");
    if (modelSha256 !== sourceSha256) failures.push("copy_differs_from_source");
  }
  if (modelPayload?.byteLength !== asset.bytes) failures.push("catalog_bytes_mismatch");
  const dimensions = previewPayload ? pngDimensions(previewPayload) : null;
  if (!dimensions) failures.push("invalid_preview_png");
  if (dimensions && (dimensions.width !== 1440 || dimensions.height !== 900)) {
    failures.push(`preview_dimensions_${dimensions.width}x${dimensions.height}`);
  }
  const capture = captureByFolder.get(asset.folder);
  if (!capture?.passed) failures.push("browser_preview_not_passed");
  if (capture?.nodes !== asset.nodes) failures.push("catalog_node_count_mismatch");
  if (capture?.meshes !== asset.meshes) failures.push("catalog_mesh_count_mismatch");

  results.push({
    assetId: asset.asset_id,
    folder: asset.folder,
    modelPath,
    previewPath,
    sourcePath,
    bytes: modelPayload?.byteLength ?? null,
    sha256: modelSha256,
    derivationPolicy: asset.derivation_policy || "copy",
    copyMatchesSource: modelSha256 !== null && modelSha256 === sourceSha256,
    sourceIntegrityVerified:
      sourceSha256 !== null &&
      sourceSha256 === (isDerived ? asset.source_sha256 : asset.sha256),
    previewDimensions: dimensions,
    browserPreviewPassed: capture?.passed === true,
    failures,
    passed: failures.length === 0,
  });
}

const report = {
  schema: "bf3d.distributed_asset_catalog_validation.v1",
  generatedAt: new Date().toISOString(),
  catalogPath,
  assetCount: results.length,
  expectedAssetCount: 10,
  passedCount: results.filter((item) => item.passed).length,
  failedCount: results.filter((item) => !item.passed).length,
  copyHashMatchCount: results.filter((item) => item.copyMatchesSource).length,
  derivedSourceIntegrityCount: results.filter(
    (item) =>
      item.derivationPolicy === "generated_derivative" &&
      item.sourceIntegrityVerified,
  ).length,
  preview1440x900Count: results.filter(
    (item) =>
      item.previewDimensions?.width === 1440 &&
      item.previewDimensions?.height === 900,
  ).length,
  results,
  passed:
    catalog.schema_version === "bf3d.distributed_asset_catalog.v1" &&
    results.length === 10 &&
    results.every((item) => item.passed),
};
await writeFile(outputPath, `${JSON.stringify(report, null, 2)}\n`, "utf8");
process.stdout.write(`${JSON.stringify({
  assetCount: report.assetCount,
  passedCount: report.passedCount,
  failedCount: report.failedCount,
  copyHashMatchCount: report.copyHashMatchCount,
  derivedSourceIntegrityCount: report.derivedSourceIntegrityCount,
  preview1440x900Count: report.preview1440x900Count,
  passed: report.passed,
})}\n`);
if (!report.passed) process.exitCode = 1;
