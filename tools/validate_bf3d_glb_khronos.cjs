#!/usr/bin/env node
"use strict";

/**
 * Validate one or more controlled BF3D GLBs with the official Khronos
 * glTF-Validator npm package.
 *
 * Requirement:
 *   REQ-BF3D-R2U-SECTION-CAP-CONTROLLED-V4-20260720
 *
 * The command fails closed when the package, an asset, or the output report is
 * unavailable, and exits non-zero whenever the validator reports an error.
 */

const crypto = require("node:crypto");
const fs = require("node:fs");
const path = require("node:path");

function usage() {
  return [
    "Usage:",
    "  node tools/validate_bf3d_glb_khronos.cjs \\",
    "    --module-dir <npm-runtime-dir> \\",
    "    --asset <file.glb> [--asset <file.glb> ...] \\",
    "    --output <report.json> \\",
    "    [--requirement-id <traceability-id>] \\",
    "    [--schema-version <report-schema>]",
  ].join("\n");
}

function parseArgs(argv) {
  const result = { assets: [] };
  for (let index = 0; index < argv.length; index += 1) {
    const token = argv[index];
    if (token === "--help" || token === "-h") {
      process.stdout.write(`${usage()}\n`);
      process.exit(0);
    }
    const value = argv[index + 1];
    if (!value || value.startsWith("--")) {
      throw new Error(`Missing value for ${token}`);
    }
    if (token === "--module-dir") result.moduleDir = value;
    else if (token === "--asset") result.assets.push(value);
    else if (token === "--output") result.output = value;
    else if (token === "--requirement-id") result.requirementId = value;
    else if (token === "--schema-version") result.schemaVersion = value;
    else throw new Error(`Unknown argument: ${token}`);
    index += 1;
  }
  if (!result.moduleDir || !result.output || result.assets.length === 0) {
    throw new Error(usage());
  }
  return result;
}

function sha256(buffer) {
  return crypto.createHash("sha256").update(buffer).digest("hex");
}

function readJson(file) {
  return JSON.parse(fs.readFileSync(file, "utf8"));
}

function normalizedIssueCounts(report) {
  const issues = report?.issues || {};
  return {
    errors: Number(issues.numErrors || 0),
    warnings: Number(issues.numWarnings || 0),
    infos: Number(issues.numInfos || 0),
    hints: Number(issues.numHints || 0),
  };
}

async function main() {
  const args = parseArgs(process.argv.slice(2));
  const moduleDir = path.resolve(args.moduleDir);
  const packageJsonPath = path.join(
    moduleDir,
    "node_modules",
    "gltf-validator",
    "package.json",
  );
  const packageLockPath = path.join(moduleDir, "package-lock.json");
  if (!fs.existsSync(packageJsonPath) || !fs.existsSync(packageLockPath)) {
    throw new Error(
      `Pinned Khronos validator runtime is incomplete: ${moduleDir}`,
    );
  }

  const packageJson = readJson(packageJsonPath);
  const packageLock = readJson(packageLockPath);
  const expectedVersion =
    packageLock?.packages?.["node_modules/gltf-validator"]?.version;
  const expectedIntegrity =
    packageLock?.packages?.["node_modules/gltf-validator"]?.integrity;
  if (
    packageJson.name !== "gltf-validator" ||
    !expectedVersion ||
    packageJson.version !== expectedVersion ||
    !expectedIntegrity
  ) {
    throw new Error("Khronos validator package identity/lock mismatch");
  }

  const validator = require(path.dirname(packageJsonPath));
  const assets = [];
  let allPassed = true;
  for (const assetArgument of args.assets) {
    const assetPath = path.resolve(assetArgument);
    if (!fs.existsSync(assetPath) || !fs.statSync(assetPath).isFile()) {
      throw new Error(`GLB asset does not exist: ${assetPath}`);
    }
    const bytes = fs.readFileSync(assetPath);
    const validation = await validator.validateBytes(
      new Uint8Array(bytes.buffer, bytes.byteOffset, bytes.byteLength),
      {
        uri: path.basename(assetPath),
        format: "glb",
        maxIssues: 0,
        writeTimestamp: false,
      },
    );
    const counts = normalizedIssueCounts(validation);
    const passed = counts.errors === 0;
    if (!passed) allPassed = false;
    assets.push({
      path: assetPath.replaceAll("\\", "/"),
      bytes: bytes.byteLength,
      sha256: sha256(bytes),
      issue_counts: counts,
      passed,
      report: validation,
    });
  }

  const output = path.resolve(args.output);
  fs.mkdirSync(path.dirname(output), { recursive: true });
  const result = {
    schema_version:
      args.schemaVersion || "bf3d.r2u.khronos_gltf_validator.v1",
    requirement_id:
      args.requirementId ||
      "REQ-BF3D-R2U-SECTION-CAP-CONTROLLED-V4-20260720",
    validator: {
      implementation: "KhronosGroup/glTF-Validator npm package",
      package: packageJson.name,
      package_version: packageJson.version,
      validator_version: String(validator.version?.() || "unknown"),
      license: packageJson.license,
      package_lock_integrity: expectedIntegrity,
      supported_extensions: validator.supportedExtensions?.() || [],
    },
    assets,
    gate: {
      requirement: "glTF Validator errors must equal zero for every asset",
      asset_count: assets.length,
      all_assets_zero_errors: allPassed,
    },
    passed: allPassed,
  };
  fs.writeFileSync(output, `${JSON.stringify(result, null, 2)}\n`, "utf8");
  process.stdout.write(`${JSON.stringify(result, null, 2)}\n`);
  process.exitCode = allPassed ? 0 : 2;
}

main().catch((error) => {
  process.stderr.write(
    `${JSON.stringify(
      {
        schema_version: "bf3d.r2u.khronos_gltf_validator.error.v1",
        passed: false,
        error: String(error?.stack || error),
      },
      null,
      2,
    )}\n`,
  );
  process.exitCode = 3;
});
