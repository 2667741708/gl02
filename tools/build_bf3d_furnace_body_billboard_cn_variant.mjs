import { createHash } from "node:crypto";
import {
  copyFile,
  mkdir,
  readFile,
  stat,
  writeFile,
} from "node:fs/promises";
import path from "node:path";

function argument(name, fallback) {
  const index = process.argv.indexOf(name);
  return index >= 0 && process.argv[index + 1] ? process.argv[index + 1] : fallback;
}

const workspace = process.cwd();
const sourceFolder = path.resolve(
  argument(
    "--source-folder",
    path.join(
      workspace,
      "PT",
      "高炉3D模型",
      "模型资产库",
      "09_高炉本体133点Billboard",
    ),
  ),
);
const outputFolder = path.resolve(
  argument(
    "--output-folder",
    path.join(
      workspace,
      "PT",
      "高炉3D模型",
      "模型资产库",
      "09_高炉本体133点Billboard_cn",
    ),
  ),
);
const sourceManifestPath = path.join(sourceFolder, "sensor_billboards.v1.json");
const outputManifestPath = path.join(outputFolder, "sensor_billboards.v1.json");
const mappingPath = path.join(outputFolder, "cn_label_mapping.v1.json");
const reportPath = path.join(outputFolder, "cn_variant_build_report.json");
const modelFile = "GL02_FURNACE_BODY_R1.glb";
const docsFolder = path.join(workspace, "PT", "高炉3D模型", "docs");
const semanticContractPath = path.join(
  docsFolder,
  "GL02传感器语义映射.v1.json",
);
const unitContractPath = path.join(
  docsFolder,
  "GL02传感器单位映射.v1.json",
);
const pointCatalogPath = path.join(
  docsFolder,
  "GL02传感器点位清单.v1.json",
);

function canonicalId(runtimeId) {
  const staticPressure = runtimeId.match(
    /^GL02_INT30_PRESSURE_(LOWER|MIDDLE|UPPER)_([A-F])$/,
  );
  if (staticPressure) {
    return `P_static_${staticPressure[1].toLowerCase()}_${staticPressure[2]}`;
  }
  if (runtimeId.startsWith("SENSOR_")) return runtimeId.slice("SENSOR_".length);
  throw new Error(`无法映射数据库 canonical ID：${runtimeId}`);
}

await mkdir(outputFolder, { recursive: true });
await mkdir(path.join(outputFolder, "preview"), { recursive: true });
await mkdir(path.join(outputFolder, "reports"), { recursive: true });

const [sourceManifest, semanticContract, unitContract, pointCatalog] =
  await Promise.all([
    readFile(sourceManifestPath, "utf8").then(JSON.parse),
    readFile(semanticContractPath, "utf8").then(JSON.parse),
    readFile(unitContractPath, "utf8").then(JSON.parse),
    readFile(pointCatalogPath, "utf8").then(JSON.parse),
  ]);
const semanticsById = new Map(
  semanticContract.points.map((entry) => [entry.canonical_id, entry]),
);
const unitsById = new Map(
  unitContract.points.map((entry) => [entry.canonical_id, entry]),
);
const catalogByRuntimeId = new Map(
  pointCatalog.points.map((entry) => [entry.runtime_id, entry]),
);
const localizedPoints = sourceManifest.points.map((point) => {
  const canonical = canonicalId(point.id);
  const semantic = semanticsById.get(canonical);
  const unit = unitsById.get(canonical);
  const catalog = catalogByRuntimeId.get(point.id);
  if (!semantic) throw new Error(`独立语义映射缺少：${canonical}`);
  if (!unit) throw new Error(`独立单位映射缺少：${canonical}`);
  if (!catalog) throw new Error(`独立点位清单缺少 Billboard：${point.id}`);
  return {
    ...point,
    canonical_id: canonical,
    data_binding_key: canonical,
    original_short_label: point.short_label,
    original_display_name: point.display_name,
    short_label: semantic.semantic_abbreviation_cn,
    display_name: semantic.semantic_name_cn,
    semantic_abbreviation_cn: semantic.semantic_abbreviation_cn,
    semantic_name_cn: semantic.semantic_name_cn,
    semantic_mapping_rule: semantic.semantic_rule,
    process_zone: semantic.process_zone,
    zone_segment: semantic.zone_segment,
    layer_id: semantic.layer_id,
    elevation_m: semantic.elevation_m,
    orientation: semantic.orientation,
    unit_key: unit.unit_key,
    normalized_unit: unit.normalized_unit,
    display_unit: unit.display_unit,
    unit_conversion: unit.conversion,
    unit_status: unit.unit_status,
    unit: unit.display_unit,
    database_chinese_name_raw: catalog.database.chinese_name,
    database_description_raw: catalog.database.description,
  };
});
const chineseLabelCount = localizedPoints.filter((point) =>
  /[\u3400-\u9fff]/u.test(point.short_label),
).length;
const idSet = new Set(localizedPoints.map((point) => point.id));
const sourceIdSet = new Set(sourceManifest.points.map((point) => point.id));
const idsPreserved =
  idSet.size === sourceIdSet.size &&
  [...sourceIdSet].every((id) => idSet.has(id));

const localizedManifest = {
  ...sourceManifest,
  generated_at: new Date().toISOString(),
  locale: "zh-CN",
  label_variant: "chinese_semantic_abbreviation",
  localized_from: "../09_高炉本体133点Billboard/sensor_billboards.v1.json",
  point_catalog: "../../docs/GL02传感器点位清单.v1.json",
  semantic_contract: "../../docs/GL02传感器语义映射.v1.json",
  unit_contract: "../../docs/GL02传感器单位映射.v1.json",
  data_binding_key: "canonical_id",
  runtime_selection_key: "id",
  id_contract:
    "original runtime point ids are immutable; canonical_id binds bf_sensor.sensor_registry",
  chinese_label_count: chineseLabelCount,
  points: localizedPoints,
};
const mappings = localizedPoints.map((point) => ({
  id: point.id,
  canonical_id: point.canonical_id,
  source_kind: point.source_kind,
  original_short_label: point.original_short_label,
  semantic_abbreviation_cn: point.semantic_abbreviation_cn,
  semantic_name_cn: point.semantic_name_cn,
  rule: point.semantic_mapping_rule,
  process_zone: point.process_zone,
  zone_segment: point.zone_segment,
  layer_id: point.layer_id,
  elevation_m: point.elevation_m,
  unit_key: point.unit_key,
  display_unit: point.display_unit,
}));
const mappingDocument = {
  schema: "bf3d.sensor_billboard_cn_label_mapping.v1",
  generated_at: localizedManifest.generated_at,
  source_manifest: "../09_高炉本体133点Billboard/sensor_billboards.v1.json",
  target_manifest: "sensor_billboards.v1.json",
  authoritative_point_catalog: "../../docs/GL02传感器点位清单.v1.json",
  authoritative_semantic_contract: "../../docs/GL02传感器语义映射.v1.json",
  authoritative_unit_contract: "../../docs/GL02传感器单位映射.v1.json",
  counts: {
    source_points: sourceManifest.points.length,
    localized_points: localizedPoints.length,
    chinese_labels: chineseLabelCount,
    unique_ids: idSet.size,
  },
  ids_preserved: idsPreserved,
  mappings,
};

await copyFile(
  path.join(sourceFolder, modelFile),
  path.join(outputFolder, modelFile),
);
const sourceApp = await readFile(
  path.join(sourceFolder, "preview", "app.js"),
  "utf8",
);
const localizedApp = sourceApp
  .replace(
    "const entry = pointEntries.find((item) => item.point.id === record.id);",
    "const bindingId = record.canonical_id || record.id;\n" +
      "        const entry = pointEntries.find(\n" +
      "          (item) =>\n" +
      "            item.point.id === bindingId ||\n" +
      "            item.point.canonical_id === bindingId,\n" +
      "        );",
  )
  .replace(
    "entry.point.unit = null;\n        refreshEntryTexture(entry);",
    [
      'entry.point.unit = entry.point.display_unit || "";',
      "        refreshEntryTexture(entry);",
    ].join("\n"),
  );
if (localizedApp === sourceApp) {
  throw new Error("中文预览的数据绑定适配器补丁未生效");
}
await writeFile(
  path.join(outputFolder, "preview", "app.js"),
  localizedApp,
  "utf8",
);
await copyFile(
  path.join(sourceFolder, "preview", "styles.css"),
  path.join(outputFolder, "preview", "styles.css"),
);
const sourceIndex = await readFile(
  path.join(sourceFolder, "preview", "index.html"),
  "utf8",
);
const localizedIndex = sourceIndex
  .replace(
    "<title>GL02 高炉本体 · 133 点 Billboard</title>",
    "<title>GL02 高炉本体 · 133 点中文语义 Billboard</title>",
  )
  .replace(
    "GL02 · 炉体独立资产 / Billboard 数据层",
    "GL02 · 炉体独立资产 / 中文语义 Billboard 数据层",
  )
  .replace(
    "高炉本体与 133 个相机朝向点位",
    "高炉本体与 133 个中文语义点位",
  )
  .replace(
    "115 个正式传感器和 18 个静压力 Billboard",
    "115 个正式传感器和 18 个静压力中文 Billboard",
  );
await writeFile(
  path.join(outputFolder, "preview", "index.html"),
  localizedIndex,
  "utf8",
);
await writeFile(
  outputManifestPath,
  `${JSON.stringify(localizedManifest, null, 2)}\n`,
  "utf8",
);
await writeFile(mappingPath, `${JSON.stringify(mappingDocument, null, 2)}\n`, "utf8");

const sourceModelPayload = await readFile(path.join(sourceFolder, modelFile));
const outputModelPayload = await readFile(path.join(outputFolder, modelFile));
const outputModelStat = await stat(path.join(outputFolder, modelFile));
const report = {
  schema: "bf3d.furnace_body_billboard_cn_variant_build.v1",
  generatedAt: localizedManifest.generated_at,
  sourceFolder,
  outputFolder,
  modelFile,
  modelBytes: outputModelStat.size,
  modelSha256: createHash("sha256").update(outputModelPayload).digest("hex"),
  modelCopyMatchesSource:
    createHash("sha256").update(sourceModelPayload).digest("hex") ===
    createHash("sha256").update(outputModelPayload).digest("hex"),
  pointCounts: localizedManifest.counts,
  chineseLabelCount,
  idsPreserved,
  uniqueIdCount: idSet.size,
  mappingFile: mappingPath,
  manifestFile: outputManifestPath,
  pointCatalog: pointCatalogPath,
  semanticContract: semanticContractPath,
  unitContract: unitContractPath,
  passed:
    localizedManifest.counts.formal_sensor_115 === 115 &&
    localizedManifest.counts.static_pressure_18 === 18 &&
    localizedManifest.counts.total === 133 &&
    localizedPoints.length === 133 &&
    chineseLabelCount === 133 &&
    idSet.size === 133 &&
    idsPreserved,
};
await writeFile(reportPath, `${JSON.stringify(report, null, 2)}\n`, "utf8");
process.stdout.write(`${JSON.stringify(report, null, 2)}\n`);
if (!report.passed) process.exitCode = 1;
