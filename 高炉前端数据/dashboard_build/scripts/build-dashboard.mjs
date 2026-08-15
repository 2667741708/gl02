import { createHash } from "node:crypto";
import { brotliCompressSync, gzipSync } from "node:zlib";
import { mkdir, readFile, rm, writeFile } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { build } from "vite";

const REQUIREMENT = "REQ-8093-FRONTEND-PERF-R1";
const scriptDir = path.dirname(fileURLToPath(import.meta.url));
const buildRoot = path.resolve(scriptDir, "..");
const frontendRoot = path.resolve(buildRoot, "..");

function pathOption(name, fallback) {
  const index = process.argv.indexOf(name);
  if (index < 0) return fallback;
  const value = process.argv[index + 1];
  if (!value || value.startsWith("--")) {
    throw new Error(name + " requires a path value");
  }
  return path.resolve(value);
}

const sourceHtml = pathOption(
  "--source",
  path.join(frontendRoot, "frontend_dashboard_v3.server.html"),
);
const generatedDir = path.join(buildRoot, ".generated");
const generatedMain = path.join(generatedDir, "dashboard-main.jsx");
const outputDir = pathOption("--output-dir", path.join(frontendRoot, "assets", "build"));
const productionHtml = pathOption(
  "--production-html",
  path.join(frontendRoot, "frontend_dashboard_v3.production.html"),
);
const reportPath = path.join(outputDir, "dashboard-build-report.json");
const checkOnly = process.argv.includes("--check");

function sha256(data) {
  return createHash("sha256").update(data).digest("hex");
}

function exactlyOne(text, pattern, label) {
  const matches = [...text.matchAll(pattern)];
  if (matches.length !== 1) {
    throw new Error(`${label}: expected exactly one match, got ${matches.length}`);
  }
  return matches[0];
}

function productionMainSource(source) {
  const rewritten = source
    .replaceAll("import('./libs/three/", "import(/* @vite-ignore */ '/libs/three/")
    .replaceAll('import("./libs/three/', 'import(/* @vite-ignore */ "/libs/three/');
  return [
    `/* ${REQUIREMENT}: generated from the current dashboard HTML. */`,
    'import * as React from "react";',
    'import * as ReactDOMClient from "react-dom/client";',
    'import { createPortal } from "react-dom";',
    'const ReactDOM = Object.freeze({ ...ReactDOMClient, createPortal });',
    rewritten,
  ].join("\n");
}

function replaceOverviewModules(html, loaderAsset) {
  const modulePattern = /\s*<script type="module" src="assets\/(?:bf3d-furnace-body-billboard-adapter|bf3d-physical-point-filter-8093|bf3d-surface-camera-guard-8093|bf3d-tooltip-stable-hover-8093|bf-core-metrics-pspace-live-8093)\.js\?v=[^"]+"><\/script>/g;
  const matches = html.match(modulePattern) || [];
  if (matches.length !== 5) {
    throw new Error(`overview runtime tags: expected 5, got ${matches.length}`);
  }
  const withoutModules = html.replace(modulePattern, "");
  const marker = "<!-- 8093 measured-point display policy; 133-point catalog remains available to the runtime -->";
  if (!withoutModules.includes(marker)) throw new Error("overview runtime insertion marker missing");
  return withoutModules.replace(
    marker,
    `${marker}\n  <!-- ${REQUIREMENT}: Three.js and GLB runtime load only on #overview. -->\n  <script type="module" src="/${loaderAsset}"></script>`,
  );
}

function buildProductionHtml(html, mainAsset, loaderAsset) {
  let output = html;
  for (const tag of [
    '  <script src="libs/react.development.js"></script>\n',
    '  <script src="libs/react-dom.development.js"></script>\n',
    '  <script src="libs/babel.min.js"></script>\n',
  ]) {
    if (!output.includes(tag)) throw new Error(`runtime tag missing: ${tag.trim()}`);
    output = output.replace(tag, "");
  }
  const babelBlock = exactlyOne(
    output,
    /  <script type="text\/babel" data-presets="typescript,react">[\s\S]*?  <\/script>/g,
    "browser Babel block",
  );
  output = output.replace(
    babelBlock[0],
    `  <!-- ${REQUIREMENT}: React 18 production bundle, precompiled by Vite/esbuild. -->\n  <script type="module" src="/${mainAsset}"></script>`,
  );
  output = replaceOverviewModules(output, loaderAsset);
  output = output.replace(
    "<head>",
    `<head>\n  <meta name="bf-build-contract" content="${REQUIREMENT};vite;react-production;route-split">`,
  );
  return output;
}

async function run() {
  const html = await readFile(sourceHtml, "utf8");
  const babelBlock = exactlyOne(
    html,
    /  <script type="text\/babel" data-presets="typescript,react">\r?\n([\s\S]*?)  <\/script>/g,
    "source browser Babel block",
  );
  const mainSource = productionMainSource(babelBlock[1]);

  if (checkOnly) {
    if (!html.includes('react.development.js') || !html.includes('babel.min.js')) {
      throw new Error("source dashboard no longer matches the migration baseline");
    }
    console.log(JSON.stringify({ ok: true, requirement: REQUIREMENT, sourceBytes: Buffer.byteLength(html), extractedBytes: Buffer.byteLength(mainSource) }));
    return;
  }

  await mkdir(generatedDir, { recursive: true });
  await writeFile(generatedMain, mainSource, "utf8");
  await rm(outputDir, { recursive: true, force: true });

  const result = await build({
    root: buildRoot,
    mode: "production",
    publicDir: false,
    logLevel: "info",
    build: {
      outDir: outputDir,
      emptyOutDir: true,
      manifest: true,
      minify: "esbuild",
      sourcemap: false,
      target: ["chrome100", "firefox100", "safari15"],
      rollupOptions: {
        external: (id) => id.startsWith("/libs/three/"),
        input: {
          "dashboard-main": generatedMain,
          "overview-route-loader": path.join(buildRoot, "src", "overview-route-loader.js"),
        },
        output: {
          entryFileNames: "[name]-[hash].js",
          chunkFileNames: "chunks/[name]-[hash].js",
          assetFileNames: "[name]-[hash][extname]",
        },
      },
    },
    define: {
      "process.env.NODE_ENV": JSON.stringify("production"),
    },
  });
  void result;

  const manifest = JSON.parse(await readFile(path.join(outputDir, ".vite", "manifest.json"), "utf8"));
  const entries = Object.values(manifest).filter((item) => item.isEntry);
  const mainEntry = entries.find((item) => item.name === "dashboard-main");
  const loaderEntry = entries.find((item) => item.name === "overview-route-loader");
  if (!mainEntry?.file || !loaderEntry?.file) throw new Error("Vite entry manifest is incomplete");
  const mainAsset = `assets/build/${mainEntry.file}`;
  const loaderAsset = `assets/build/${loaderEntry.file}`;
  const builtHtml = buildProductionHtml(html, mainAsset, loaderAsset);
  await mkdir(path.dirname(productionHtml), { recursive: true });
  await writeFile(productionHtml, builtHtml, "utf8");

  const mainBytes = await readFile(path.join(outputDir, mainEntry.file));
  const loaderBytes = await readFile(path.join(outputDir, loaderEntry.file));
  const billboardSource = await readFile(
    path.join(frontendRoot, "assets", "bf3d-furnace-body-billboard-adapter.js"),
    "utf8",
  );
  const report = {
    ok: true,
    requirement: REQUIREMENT,
    source: {
      file: path.relative(frontendRoot, sourceHtml).replaceAll("\\", "/"),
      bytes: Buffer.byteLength(html),
      sha256: sha256(html),
    },
    output: {
      html: path.relative(frontendRoot, productionHtml).replaceAll("\\", "/"),
      htmlBytes: Buffer.byteLength(builtHtml),
      htmlGzipBytes: gzipSync(builtHtml).byteLength,
      htmlBrotliBytes: brotliCompressSync(builtHtml).byteLength,
      main: mainAsset,
      mainBytes: mainBytes.byteLength,
      mainGzipBytes: gzipSync(mainBytes).byteLength,
      mainBrotliBytes: brotliCompressSync(mainBytes).byteLength,
      loader: loaderAsset,
      loaderBytes: loaderBytes.byteLength,
    },
    invariants: {
      browserBabelRemoved: !builtHtml.includes("babel.min.js"),
      developmentReactRemoved: !builtHtml.includes("react.development.js"),
      glbUrlUnchanged: mainBytes.includes(
        Buffer.from("models/GL02_FURNACE_BODY_R1.glb?v=20260806-static-stability-r1"),
      ),
      billboardDrawingContractPreserved: [
        'const font = \'26px SimSun, "宋体", serif\';',
        "new THREE.CanvasTexture(canvas)",
        "new THREE.SpriteMaterial",
        'schema: "bf3d.sensor_billboard.runtime.v1"',
      ].every((marker) => billboardSource.includes(marker)),
      overviewRuntimeRouteGated: builtHtml.includes("bf-build-contract") && !builtHtml.includes('<script type="module" src="assets/bf3d-furnace-body-billboard-adapter.js'),
    },
  };
  await writeFile(reportPath, `${JSON.stringify(report, null, 2)}\n`, "utf8");
  console.log(JSON.stringify(report));
}

await run();
