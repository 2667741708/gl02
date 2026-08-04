#!/usr/bin/env node
"use strict";

const childProcess = require("child_process");
const crypto = require("crypto");
const fs = require("fs");
const path = require("path");
const readline = require("readline");

const PLAYWRIGHT_FALLBACK =
  "C:/Users/hmw20/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/.pnpm/playwright@1.61.1/node_modules/playwright";
let playwright;
try {
  playwright = require("playwright");
} catch {
  playwright = require(PLAYWRIGHT_FALLBACK);
}

const ROOT = path.resolve(__dirname, "..");
const FRONTEND_ROOT = path.join(ROOT, "高炉前端数据");
const STAGE_ROOT = path.join(
  ROOT,
  "PT",
  "高炉3D模型",
  "work",
  "WEB_60_20260720_R2U_SECTION_CAP_CONTROLLED_V4",
);
const PREVIEW_ROOT = path.join(STAGE_ROOT, "preview");
const SCREENSHOT_ROOT = path.join(PREVIEW_ROOT, "screenshots");
const REPORT_PATH = path.join(
  STAGE_ROOT,
  "reports",
  "bf3d_review_v4_preview_report.json",
);
const HTML_PATH = path.join(FRONTEND_ROOT, "bf3d_review_v4.server.html");
const JS_PATH = path.join(
  FRONTEND_ROOT,
  "assets",
  "bf3d-review-renderer-v4.js",
);
const CSS_PATH = path.join(
  FRONTEND_ROOT,
  "assets",
  "bf3d-review-renderer.css",
);
const SERVER_PATH = path.join(ROOT, "tools", "serve_bf3d_review_v4.py");
const REVIEW_GLB_PATH = path.join(
  FRONTEND_ROOT,
  "models",
  "gl02_blast_furnace_review.v4.glb",
);
const FORMAL_GLB_PATH = path.join(
  FRONTEND_ROOT,
  "models",
  "gl02_blast_furnace.glb",
);
const PRODUCTION_HTML_PATH = path.join(
  FRONTEND_ROOT,
  "frontend_dashboard_v3.server.html",
);
const PRODUCTION_CONTROLLER_PATH = path.join(
  FRONTEND_ROOT,
  "assets",
  "bf3d-structural-review.js",
);
const THREE_MODULE_PATH = path.join(
  FRONTEND_ROOT,
  "libs",
  "three",
  "three.module.js",
);
const RECT_AREA_ADDON_PATH = path.join(
  FRONTEND_ROOT,
  "libs",
  "three",
  "lights",
  "RectAreaLightUniformsLib.js",
);

const REQUIREMENT_ID =
  "REQ-BF3D-R2U-ISOLATED-WEB-REVIEW-20260720";
const EXPECTED_REVIEW_SHA256 =
  "e46508bcecc8fef76510a0b889e0598ad3cb2289cc00f6b99566c78e3ed3afd2";
const EXPECTED_REVIEW_BYTES = 4_275_268;
const EXPECTED_FORMAL_SHA256 =
  "808960f1b2703e7fb27df35f1b1b1a17063b9b10d2267acba593fc3872b62af6";
const EXPECTED_THREE_SHA256 =
  "76dea8151bc9352aef3528b4262e249b2604f62543828328db978d060d61a495";
const EXPECTED_RECT_AREA_SHA256 =
  "08085bc942253cd54948bf936fecb66b54514a135872656e475a1cab09b55214";

const CHROMIUM_VIEWPORTS = Object.freeze([
  Object.freeze([1280, 720]),
  Object.freeze([1366, 768]),
  Object.freeze([1440, 900]),
  Object.freeze([1546, 864]),
  Object.freeze([1920, 1080]),
  Object.freeze([1024, 768]),
  Object.freeze([768, 1024]),
  Object.freeze([390, 844]),
  Object.freeze([375, 667]),
]);
const REPRESENTATIVE_VIEWPORTS = Object.freeze([
  Object.freeze([1920, 1080]),
  Object.freeze([1366, 768]),
  Object.freeze([768, 1024]),
  Object.freeze([390, 844]),
]);
const REPRESENTATIVE_ONLY = process.argv.includes("--representative");
const STABILITY_ITERATIONS_REQUIRED = REPRESENTATIVE_ONLY ? 1 : 2;
const PAGE_TIMEOUT_MS = 90_000;

function sha256Buffer(buffer) {
  return crypto.createHash("sha256").update(buffer).digest("hex");
}

function sha256File(filePath) {
  return sha256Buffer(fs.readFileSync(filePath));
}

function relativePath(filePath) {
  return path.relative(ROOT, filePath).replaceAll(path.sep, "/");
}

function serializeError(error, phase = undefined) {
  return {
    ...(phase ? { phase } : {}),
    name: error?.name || "Error",
    message: String(error?.message || error),
    stack: String(error?.stack || ""),
  };
}

function makeCheck(id, passed, detail = undefined) {
  return {
    id,
    passed: Boolean(passed),
    ...(detail === undefined ? {} : { detail }),
  };
}

function assert(condition, message, detail = undefined) {
  if (!condition) {
    const error = new Error(message);
    error.detail = detail;
    throw error;
  }
}

function inspectFile(filePath, expected = {}) {
  const payload = fs.readFileSync(filePath);
  const actual = {
    path: relativePath(filePath),
    bytes: payload.byteLength,
    sha256: sha256Buffer(payload),
  };
  return {
    ...actual,
    expected_bytes: expected.bytes ?? null,
    expected_sha256: expected.sha256 ?? null,
    bytes_match:
      expected.bytes === undefined || expected.bytes === actual.bytes,
    sha256_match:
      expected.sha256 === undefined || expected.sha256 === actual.sha256,
  };
}

function parseGlbJson(filePath) {
  const payload = fs.readFileSync(filePath);
  assert(payload.toString("ascii", 0, 4) === "glTF", "review GLB magic 无效");
  assert(payload.readUInt32LE(4) === 2, "review GLB 版本不是 2");
  let offset = 12;
  let document = null;
  while (offset < payload.length) {
    const length = payload.readUInt32LE(offset);
    const type = payload.toString("ascii", offset + 4, offset + 8);
    if (type === "JSON") {
      document = JSON.parse(
        payload
          .toString("utf8", offset + 8, offset + 8 + length)
          .replace(/\u0000+$/u, ""),
      );
    }
    offset += 8 + length;
  }
  assert(document, "review GLB 缺少 JSON chunk");
  return document;
}

function buildGlbContract() {
  const document = parseGlbJson(REVIEW_GLB_PATH);
  const nodes = document.nodes || [];
  const materials = document.materials || [];
  const meshes = document.meshes || [];
  const materialGroup = nodes.find(
    (node) => node.name === "BF3D_V4_MODE_MATERIAL",
  );
  const sectionGroup = nodes.find(
    (node) => node.name === "BF3D_V4_MODE_SECTION",
  );
  const materialNodes = nodes.filter(
    (node) => node.extras?.bf3d_review_mode === "material",
  );
  const sectionNodes = nodes.filter(
    (node) =>
      node.extras?.bf3d_review_mode === "section" &&
      node.extras?.bf3d_section_physical_cut === true,
  );
  const sectionCapPlanes = sectionNodes.map((node) => {
    const mesh = meshes[node.mesh];
    const capPrimitive = (mesh?.primitives || []).find((primitive) =>
      String(materials[primitive.material]?.name || "").includes("_CAP_"),
    );
    const positionAccessor =
      document.accessors?.[capPrimitive?.attributes?.POSITION];
    return {
      node: node.name || "",
      material: materials[capPrimitive?.material]?.name || null,
      x_min: positionAccessor?.min?.[0] ?? null,
      x_max: positionAccessor?.max?.[0] ?? null,
      z_min: positionAccessor?.min?.[2] ?? null,
      z_max: positionAccessor?.max?.[2] ?? null,
    };
  });
  const capPlaneXs = sectionCapPlanes
    .flatMap((entry) => [entry.x_min, entry.x_max])
    .filter(Number.isFinite);
  const sectionCapsShareCutPlane =
    sectionCapPlanes.length === 10 &&
    sectionCapPlanes.every(
      (entry) =>
        Number.isFinite(entry.x_min) &&
        Number.isFinite(entry.x_max) &&
        Math.abs(entry.x_min - entry.x_max) < 1e-6,
    ) &&
    Math.max(...capPlaneXs) - Math.min(...capPlaneXs) < 1e-5;
  const forbiddenNames = nodes
    .map((node) => String(node.name || ""))
    .filter((name) =>
      /(^|[_\-\s])(SENSOR|HIT|LINE|LINES|LINESEGMENTS|POINT|POINTS|SPRITE|OUTLINE|HIGHLIGHT|PARTICLE|PARTICLES|LEADER|CALLOUT|RING)([_\-\s]|$)/i.test(
        name,
      ),
    );
  const forbiddenPrimitiveModes = meshes.flatMap((mesh) =>
    (mesh.primitives || [])
      .filter((primitive) => ![undefined, 4].includes(primitive.mode))
      .map((primitive) => ({
        mesh: mesh.name || "",
        mode: primitive.mode,
      })),
  );
  const externalImages = (document.images || []).filter((image) => image.uri);
  const pbrFailures = materials
    .map((material, index) => ({
      index,
      name: material.name || "",
      baseColorTexture:
        material.pbrMetallicRoughness?.baseColorTexture?.index ?? null,
      metallicRoughnessTexture:
        material.pbrMetallicRoughness?.metallicRoughnessTexture?.index ?? null,
      normalTexture: material.normalTexture?.index ?? null,
      doubleSided: material.doubleSided === true,
    }))
    .filter(
      (material) =>
        material.baseColorTexture === null ||
        material.metallicRoughnessTexture === null ||
        material.normalTexture === null ||
        material.doubleSided,
    );
  const checks = [
    makeCheck(
      "glb_top_level_groups",
      Boolean(materialGroup) && Boolean(sectionGroup),
      {
        material_group: Boolean(materialGroup),
        section_group: Boolean(sectionGroup),
      },
    ),
    makeCheck("glb_material_logical_count", materialNodes.length === 5, {
      actual: materialNodes.length,
      expected: 5,
    }),
    makeCheck("glb_physical_section_count", sectionNodes.length === 10, {
      actual: sectionNodes.length,
      expected: 10,
      nodes: sectionNodes.map((node) => node.name),
    }),
    makeCheck("glb_forbidden_names_zero", forbiddenNames.length === 0, {
      forbidden: forbiddenNames,
    }),
    makeCheck(
      "glb_triangle_primitives_only",
      forbiddenPrimitiveModes.length === 0,
      { forbidden: forbiddenPrimitiveModes },
    ),
    makeCheck("glb_pbr_channels_complete", pbrFailures.length === 0, {
      failures: pbrFailures,
    }),
    makeCheck(
      "glb_section_cap_registered_plane",
      sectionCapsShareCutPlane,
      {
        interpretation:
          "V4 十个物理 Section 封口均位于同一受控切平面；跨对象正面积重叠已由 R2U 几何验证器独立证明为 0。",
        cap_planes: sectionCapPlanes,
      },
    ),
    makeCheck("glb_external_images_zero", externalImages.length === 0, {
      external_images: externalImages,
    }),
  ];
  return {
    asset_generator: document.asset?.generator || null,
    node_count: nodes.length,
    mesh_count: meshes.length,
    material_count: materials.length,
    image_count: (document.images || []).length,
    material_nodes: materialNodes.map((node) => node.name),
    physical_section_nodes: sectionNodes.map((node) => node.name),
    checks,
    passed: checks.every((check) => check.passed),
  };
}

function buildStaticContract() {
  const html = fs.readFileSync(HTML_PATH, "utf8");
  const renderer = fs.readFileSync(JS_PATH, "utf8");
  const server = fs.readFileSync(SERVER_PATH, "utf8");
  const verifier = fs.readFileSync(__filename, "utf8");
  const importmapMatch = html.match(
    /<script type="importmap">([\s\S]*?)<\/script>/u,
  );
  const importmapHash = importmapMatch
    ? crypto
        .createHash("sha256")
        .update(importmapMatch[1], "utf8")
        .digest("base64")
    : null;
  const importmapHashSource = importmapHash
    ? `'sha256-${importmapHash}'`
    : null;
  const productionController = fs.readFileSync(
    PRODUCTION_CONTROLLER_PATH,
    "utf8",
  );
  const checks = [
    makeCheck(
      "explicit_illustrative_boundary",
      [
        "E/illustrative",
        "REF-PENDING",
        "未完成 Blender 等价校准",
      ].every((token) => html.includes(token)),
    ),
    makeCheck(
      "single_review_model_url",
      renderer.includes(
        'const MODEL_URL = "models/gl02_blast_furnace_review.v4.glb"',
      ) &&
        !renderer.includes("gl02_blast_furnace.glb") &&
        !renderer.includes("material_review.v4.glb") &&
        !renderer.includes("structural_review.v4.glb"),
    ),
    makeCheck(
      "production_page_not_loaded",
      !html.includes("frontend_dashboard_v3.server.html") &&
        !renderer.includes("frontend_dashboard_v3.server.html"),
    ),
    makeCheck(
      "production_controller_not_loaded",
      !html.includes("bf3d-structural-review.js") &&
        !renderer.includes("bf3d-structural-review.js"),
    ),
    makeCheck(
      "production_default_v1_route_unchanged",
      productionController.includes(
        '"models/gl02_blast_furnace_structural_review.v1.glb"',
      ),
      {
        expected_operational_asset:
          "models/gl02_blast_furnace_structural_review.v1.glb",
      },
    ),
    makeCheck(
      "three_r160_and_rect_area_vendored",
      renderer.includes('from "three"') &&
        renderer.includes(
          'from "three/addons/lights/RectAreaLightUniformsLib.js"',
        ) &&
        html.includes('"three": "./libs/three/three.module.js"'),
    ),
    makeCheck(
      "two_main_modes_and_material_subviews",
      [
        'data-mode-button="material"',
        'data-mode-button="structural"',
        'data-material-view-button="exterior"',
        'data-material-view-button="interior"',
      ].every((token) => html.includes(token)),
    ),
    makeCheck(
      "composition_disclosure_contract",
      [
        "R2J 五区实体交界与原始表面纹理",
        "不是数据圆环、轮廓或引线",
      ].every((token) => html.includes(token)) &&
        renderer.includes("STRUCTURAL_WEDGE_DIAGNOSIS") &&
        renderer.includes("跨对象共面重叠 0") &&
        renderer.includes("不是固定圆环、竖线") &&
        renderer.includes("保留半炉的对侧内壁") &&
        renderer.includes("mobileInteriorDistanceScale: 1.16") &&
        renderer.includes("mobileInteriorLayerBoundaryTarget: 3"),
    ),
    makeCheck(
      "loading_empty_error_retry_state_model",
      renderer.includes('"empty"') &&
        renderer.includes('"error"') &&
        renderer.includes('"loading"') &&
        html.includes('id="retry-button"'),
    ),
    makeCheck(
      "complete_asset_response_consumption",
      renderer.includes("await response.arrayBuffer()") &&
        renderer.includes("审查资产响应未完整消费") &&
        !renderer.includes("response.body.getReader") &&
        !renderer.includes("reader.releaseLock"),
    ),
    makeCheck(
      "two_iteration_stability_gate",
      verifier.includes(
        "const STABILITY_ITERATIONS_REQUIRED = REPRESENTATIVE_ONLY ? 1 : 2",
      ) &&
        verifier.includes("连续稳定性矩阵硬门失败") &&
        verifier.includes("bf3d_review_stability_run_") &&
        verifier.includes('page.on("requestfinished"') &&
        verifier.includes("review_request_finished_count"),
    ),
    makeCheck(
      "no_exposure_control",
      !html.includes('type="range"') &&
        renderer.includes("const FIXED_EXPOSURE = 1.0"),
    ),
    makeCheck(
      "p40_candidate_light_contract",
      [
        "P40_NEUTRAL_KEY",
        "P40_NEUTRAL_FILL",
        "P40_NEUTRAL_RIM",
        "P40_NEUTRAL_TOP",
        "RectAreaLight",
        "PMREMGenerator",
      ].every((token) => renderer.includes(token)),
    ),
    makeCheck(
      "exclusive_lifecycle_contract",
      [
        "new THREE.Scene",
        "new THREE.WebGLRenderer",
        "new THREE.PerspectiveCamera",
        "requestAnimationFrame",
        "new ResizeObserver",
        "dispose()",
      ].every((token) => renderer.includes(token)),
    ),
    makeCheck(
      "server_allowlist_excludes_production",
      server.includes('"formal_glb_exposed": False') &&
        server.includes('"production_page_exposed": False') &&
        server.includes('"production_controller_exposed": False'),
    ),
    makeCheck(
      "script_csp_fail_closed_importmap_hash",
      Boolean(importmapHashSource) &&
        server.includes(
          `"script-src 'self' ${importmapHashSource}; "`,
        ) &&
        !server.includes("script-src 'self' 'unsafe-inline'"),
      {
        importmap_hash_source: importmapHashSource,
        script_unsafe_inline_present: server.includes(
          "script-src 'self' 'unsafe-inline'",
        ),
      },
    ),
    makeCheck(
      "style_csp_three_runtime_compatibility",
      server.includes(`"style-src 'self' 'unsafe-inline'; "`),
      {
        reason:
          "Three r160 canvas.style 与 OrbitControls touchAction 运行时写入；隔离页无用户输入样式。",
      },
    ),
    makeCheck(
      "simsun_font_contract",
      fs
        .readFileSync(CSS_PATH, "utf8")
        .includes('font-family: SimSun, "宋体", serif'),
    ),
  ];
  return { checks, passed: checks.every((check) => check.passed) };
}

function snapshotProtectedFiles() {
  return {
    formal_glb: inspectFile(FORMAL_GLB_PATH, {
      sha256: EXPECTED_FORMAL_SHA256,
    }),
    review_glb: inspectFile(REVIEW_GLB_PATH, {
      bytes: EXPECTED_REVIEW_BYTES,
      sha256: EXPECTED_REVIEW_SHA256,
    }),
    production_html: inspectFile(PRODUCTION_HTML_PATH),
    production_controller: inspectFile(PRODUCTION_CONTROLLER_PATH),
    three_module: inspectFile(THREE_MODULE_PATH, {
      sha256: EXPECTED_THREE_SHA256,
    }),
    rect_area_addon: inspectFile(RECT_AREA_ADDON_PATH, {
      sha256: EXPECTED_RECT_AREA_SHA256,
    }),
  };
}

function protectedSnapshotsMatch(before, after) {
  return Object.keys(before).every(
    (key) =>
      before[key].bytes === after[key].bytes &&
      before[key].sha256 === after[key].sha256,
  );
}

function startReviewServer() {
  return new Promise((resolve, reject) => {
    const executable = process.env.PYTHON || "python";
    const child = childProcess.spawn(
      executable,
      [SERVER_PATH, "--host", "127.0.0.1", "--port", "0", "--quiet"],
      {
        cwd: ROOT,
        windowsHide: true,
        stdio: ["ignore", "pipe", "pipe"],
      },
    );
    const stderr = [];
    child.stderr.setEncoding("utf8");
    child.stderr.on("data", (chunk) => stderr.push(chunk));
    const lines = readline.createInterface({ input: child.stdout });
    const timer = setTimeout(() => {
      lines.close();
      child.kill();
      reject(
        new Error(
          `审查服务器启动超时：${stderr.join("").trim() || "no stderr"}`,
        ),
      );
    }, 15_000);
    child.once("error", (error) => {
      clearTimeout(timer);
      lines.close();
      reject(error);
    });
    child.once("exit", (code) => {
      if (!timer) return;
      if (code !== null && code !== 0) {
        clearTimeout(timer);
        lines.close();
        reject(
          new Error(
            `审查服务器提前退出 ${code}：${stderr.join("").trim()}`,
          ),
        );
      }
    });
    lines.on("line", (line) => {
      let payload;
      try {
        payload = JSON.parse(line);
      } catch {
        return;
      }
      if (payload.event !== "bf3d_review_server_ready") return;
      clearTimeout(timer);
      lines.close();
      resolve({ child, ready: payload, stderr });
    });
  });
}

async function stopReviewServer(server) {
  if (!server?.child || server.child.exitCode !== null) return;
  const exited = new Promise((resolve) =>
    server.child.once("exit", (code, signal) => resolve({ code, signal })),
  );
  server.child.kill();
  await Promise.race([
    exited,
    new Promise((resolve) => setTimeout(resolve, 3_000)),
  ]);
}

function attachDiagnostics(page, origin) {
  const diagnostics = {
    console_errors: [],
    page_errors: [],
    http_errors: [],
    external_requests: [],
    request_failures: [],
    request_finished: [],
    requests: [],
  };
  page.on("console", (message) => {
    if (message.type() === "error") {
      diagnostics.console_errors.push({
        text: message.text(),
        location: message.location()?.url || "",
      });
    }
  });
  page.on("pageerror", (error) =>
    diagnostics.page_errors.push(String(error?.stack || error)),
  );
  page.on("request", (request) => {
    const url = request.url();
    diagnostics.requests.push(url);
    try {
      const parsed = new URL(url);
      if (
        ["http:", "https:"].includes(parsed.protocol) &&
        parsed.origin !== origin
      ) {
        diagnostics.external_requests.push(url);
      }
    } catch {
      diagnostics.external_requests.push(url);
    }
  });
  page.on("response", (response) => {
    if (response.status() >= 400) {
      diagnostics.http_errors.push({
        url: response.url(),
        status: response.status(),
      });
    }
  });
  page.on("requestfailed", (request) => {
    diagnostics.request_failures.push({
      url: request.url(),
      failure: request.failure()?.errorText || "unknown",
    });
  });
  page.on("requestfinished", (request) => {
    diagnostics.request_finished.push(request.url());
  });
  return diagnostics;
}

async function pageLayoutAudit(page) {
  return page.evaluate(() => {
    const root = document.documentElement;
    const body = document.body;
    const controls = [
      ...document.querySelectorAll(
        "[data-mode-button], [data-material-view-button], #reset-view-button, #retry-button",
      ),
    ].map((element) => {
      const rect = element.getBoundingClientRect();
      return {
        label: element.textContent.trim(),
        left: rect.left,
        right: rect.right,
        width: rect.width,
        visible:
          getComputedStyle(element).display !== "none" &&
          getComputedStyle(element).visibility !== "hidden",
      };
    });
    return {
      viewport: [innerWidth, innerHeight],
      document_client_width: root.clientWidth,
      document_scroll_width: root.scrollWidth,
      body_client_width: body.clientWidth,
      body_scroll_width: body.scrollWidth,
      horizontal_overflow:
        root.scrollWidth > root.clientWidth + 1 ||
        body.scrollWidth > body.clientWidth + 1,
      font_family: getComputedStyle(body).fontFamily,
      controls,
      clipped_visible_controls: controls.filter(
        (control) =>
          control.visible &&
          (control.left < -1 || control.right > innerWidth + 1),
      ),
      section_rows: document.querySelectorAll(
        "#section-register-body tr[data-section-id]",
      ).length,
      boundary_visible: document.body.innerText.includes(
        "未完成 Blender 等价校准",
      ),
      footer_visible: document.body.innerText.includes("不请求正式 GLB"),
    };
  });
}

function modeScreenshotPath(engine, width, height, state) {
  return path.join(
    SCREENSHOT_ROOT,
    `${engine}_${width}x${height}_${state}.png`,
  );
}

async function captureMode(page, engine, width, height, state) {
  const screenshotPath = modeScreenshotPath(engine, width, height, state);
  await page.screenshot({
    path: screenshotPath,
    fullPage: false,
    animations: "disabled",
  });
  return {
    state,
    path: relativePath(screenshotPath),
    bytes: fs.statSync(screenshotPath).size,
    sha256: sha256File(screenshotPath),
  };
}

async function runViewport(browser, engine, viewport, baseUrl, stress) {
  const [width, height] = viewport;
  const context = await browser.newContext({
    viewport: { width, height },
    deviceScaleFactor: 1,
    locale: "zh-CN",
    colorScheme: "dark",
  });
  const page = await context.newPage();
  page.setDefaultTimeout(PAGE_TIMEOUT_MS);
  const origin = new URL(baseUrl).origin;
  const diagnostics = attachDiagnostics(page, origin);
  const checks = [];
  const screenshots = [];
  let stateBeforeDispose = null;
  let disposedState = null;
  let layout = null;
  let stressAudit = null;
  try {
    await page.goto(baseUrl, {
      waitUntil: "domcontentloaded",
      timeout: PAGE_TIMEOUT_MS,
    });
    await page.waitForFunction(
      () =>
        globalThis.BF3D_REVIEW_PREVIEW?.getState?.().loadState === "ready",
      null,
      { timeout: PAGE_TIMEOUT_MS },
    );
    await page.waitForFunction(
      () =>
        globalThis.BF3D_REVIEW_PREVIEW?.getState?.().lifecycle.frameCount >= 2,
    );

    const exterior = await page.evaluate(() =>
      globalThis.BF3D_REVIEW_PREVIEW.getAuditSnapshot(),
    );
    const exteriorUi = await page.evaluate(() => ({
      note: document.querySelector("#visible-set-note")?.textContent || "",
      description:
        document.querySelector("#active-view-description")?.textContent || "",
    }));
    checks.push(
      makeCheck(
        "material_exterior_state",
        exterior.mode === "material" &&
          exterior.materialView === "exterior" &&
          exterior.objects.visibleMaterialLogical === 5 &&
          exterior.objects.visibleSectionLogical === 0,
        exterior,
      ),
    );
    checks.push(
      makeCheck(
        "material_exterior_composition_disclosure",
        exterior.composition.exteriorDataRingOrLeader === false &&
          exterior.composition.exteriorBoundaryMeaning.includes(
            "R2J 五区实体交界",
          ) &&
          exterior.composition.cameraDirection[2] > 0.55 &&
          exteriorUi.note.includes("不是数据圆环、轮廓或引线") &&
          exteriorUi.description.includes("R2J 五区实体交界"),
        {
          composition: exterior.composition,
          ui: exteriorUi,
        },
      ),
    );
    checks.push(
      makeCheck(
        "asset_sha_verified",
        exterior.model.shaVerified === true &&
          exterior.model.actualSha256 === EXPECTED_REVIEW_SHA256,
        exterior.model,
      ),
    );
    checks.push(
      makeCheck(
        "runtime_contract",
        exterior.renderer.revision === "160" &&
          exterior.lighting.directionalCount === 3 &&
          exterior.lighting.topType === "RectAreaLight" &&
          exterior.lighting.effectiveLtcInitCalls === 1 &&
          exterior.lighting.ambientLightCount === 0 &&
          exterior.blenderEquivalent === false &&
          exterior.fixedExposure === 1,
        {
          renderer: exterior.renderer,
          lighting: exterior.lighting,
          blenderEquivalent: exterior.blenderEquivalent,
        },
      ),
    );
    screenshots.push(
      await captureMode(page, engine, width, height, "material-exterior"),
    );

    await page.click('[data-material-view-button="interior"]');
    await page.waitForFunction(
      () => document.body.dataset.materialView === "interior",
    );
    const interior = await page.evaluate(() =>
      globalThis.BF3D_REVIEW_PREVIEW.getAuditSnapshot(),
    );
    const interiorUi = await page.evaluate(() => ({
      note: document.querySelector("#visible-set-note")?.textContent || "",
      description:
        document.querySelector("#active-view-description")?.textContent || "",
    }));
    const mobileInteriorExpected = width <= 520;
    const expectedInteriorDistanceScale = mobileInteriorExpected ? 1.16 : 1;
    checks.push(
      makeCheck(
        "material_interior_closeup_state",
        interior.mode === "material" &&
          interior.materialView === "interior" &&
          interior.cameraPreset === "material-interior-closeup" &&
          interior.objects.visibleSectionLogical === 10 &&
          interior.objects.visibleMaterialLogical === 0 &&
          interior.composition.mobileInteriorPullbackApplied ===
            mobileInteriorExpected &&
          Math.abs(
            interior.composition.cameraDistanceScale -
              expectedInteriorDistanceScale,
          ) < 1e-6 &&
          interior.composition.mobileInteriorLayerBoundaryTarget >= 3 &&
          interiorUi.note.includes("至少三处材料层边界"),
        {
          state: interior,
          ui: interiorUi,
          mobile_interior_expected: mobileInteriorExpected,
          expected_distance_scale: expectedInteriorDistanceScale,
        },
      ),
    );
    screenshots.push(
      await captureMode(page, engine, width, height, "material-interior"),
    );

    await page.click('[data-mode-button="structural"]');
    await page.waitForFunction(
      () => document.body.dataset.reviewMode === "structural",
    );
    await page.click("#reset-view-button");
    const structural = await page.evaluate(() =>
      globalThis.BF3D_REVIEW_PREVIEW.getAuditSnapshot(),
    );
    const structuralUi = await page.evaluate(() => ({
      note: document.querySelector("#visible-set-note")?.textContent || "",
      description:
        document.querySelector("#active-view-description")?.textContent || "",
    }));
    checks.push(
      makeCheck(
        "structural_global_state",
        structural.mode === "structural" &&
          structural.cameraPreset === "structural-global" &&
          structural.objects.physicalSectionCount === 10 &&
          structural.objects.visibleSectionLogical === 10 &&
          structural.objects.forbiddenObjectCount === 0 &&
          structural.objects.yellowOutlineCount === 0 &&
          structural.composition.structuralBottomWedgeDiagnosis ===
            "controlled_section_caps_zero_overlap" &&
          structural.composition.structuralBottomWedgeIsCavityOrOpening ===
            false &&
          structural.composition.structuralGeometryModified === false &&
          structural.composition.cameraDirection[2] > 0.2 &&
          structuralUi.note.includes("跨对象共面重叠 0") &&
          structuralUi.note.includes("不是固定圆环、竖线") &&
          structuralUi.note.includes("不是"),
        {
          state: structural,
          ui: structuralUi,
        },
      ),
    );
    checks.push(
      makeCheck(
        "pbr_unchanged_after_modes",
        structural.pbr.checked === true &&
          structural.pbr.mutationCount === 0,
        structural.pbr,
      ),
    );
    screenshots.push(
      await captureMode(page, engine, width, height, "structural-section"),
    );

    if (stress) {
      const memoryBefore = structural.renderer.memory;
      for (let index = 0; index < 12; index += 1) {
        await page.click('[data-mode-button="material"]');
        await page.click(
          `[data-material-view-button="${
            index % 2 === 0 ? "exterior" : "interior"
          }"]`,
        );
        await page.click('[data-mode-button="structural"]');
      }
      await page.waitForTimeout(120);
      const afterStress = await page.evaluate(() =>
        globalThis.BF3D_REVIEW_PREVIEW.getAuditSnapshot(),
      );
      stressAudit = {
        cycles: 12,
        memory_before: memoryBefore,
        memory_after: afterStress.renderer.memory,
        pbr: afterStress.pbr,
      };
      checks.push(
        makeCheck(
          "mode_switch_resource_stability",
          afterStress.renderer.memory.geometries === memoryBefore.geometries &&
            afterStress.renderer.memory.textures === memoryBefore.textures &&
            afterStress.pbr.mutationCount === 0,
          stressAudit,
        ),
      );
    }

    layout = await pageLayoutAudit(page);
    checks.push(
      makeCheck(
        "responsive_layout",
        layout.horizontal_overflow === false &&
          layout.clipped_visible_controls.length === 0 &&
          layout.section_rows === 10 &&
          layout.boundary_visible &&
          layout.footer_visible &&
          /SimSun|宋体/i.test(layout.font_family),
        layout,
      ),
    );

    const requestPaths = diagnostics.requests
      .map((url) => {
        try {
          return new URL(url).pathname;
        } catch {
          return url;
        }
      })
      .filter((value) => !String(value).startsWith("blob:"));
    const finishedRequestPaths = diagnostics.request_finished
      .map((url) => {
        try {
          return new URL(url).pathname;
        } catch {
          return url;
        }
      })
      .filter((value) => !String(value).startsWith("blob:"));
    const reviewRequests = requestPaths.filter(
      (pathname) =>
        pathname === "/models/gl02_blast_furnace_review.v4.glb",
    );
    const finishedReviewRequests = finishedRequestPaths.filter(
      (pathname) =>
        pathname === "/models/gl02_blast_furnace_review.v4.glb",
    );
    const productionRequests = requestPaths.filter(
      (pathname) =>
        pathname.endsWith("/frontend_dashboard_v3.server.html") ||
        pathname.endsWith("/assets/bf3d-structural-review.js") ||
        pathname.endsWith("/models/gl02_blast_furnace.glb"),
    );
    checks.push(
      makeCheck(
        "network_isolation",
        reviewRequests.length === 1 &&
          finishedReviewRequests.length === 1 &&
          productionRequests.length === 0 &&
          diagnostics.external_requests.length === 0,
        {
          review_request_count: reviewRequests.length,
          review_request_finished_count: finishedReviewRequests.length,
          production_requests: productionRequests,
          external_requests: diagnostics.external_requests,
          requests: requestPaths,
          finished_requests: finishedRequestPaths,
        },
      ),
    );

    stateBeforeDispose = await page.evaluate(() =>
      globalThis.BF3D_REVIEW_PREVIEW.getAuditSnapshot(),
    );
    disposedState = await page.evaluate(() =>
      globalThis.BF3D_REVIEW_PREVIEW.dispose(),
    );
    checks.push(
      makeCheck(
        "exclusive_resource_disposal",
        disposedState.lifecycle.disposed === true &&
          disposedState.lifecycle.rafActive === false &&
          disposedState.lifecycle.resizeObserverActive === false &&
          disposedState.lifecycle.rendererDisposed === true &&
          disposedState.lifecycle.controlsDisposed === true &&
          disposedState.lifecycle.resizeObserverDisconnected === true &&
          disposedState.lifecycle.rafCancelled === true &&
          disposedState.lifecycle.environmentSourceDisposed === true &&
          disposedState.lifecycle.environmentTargetDisposed === true &&
          disposedState.lifecycle.disposedResourceCounts.geometries > 0 &&
          disposedState.lifecycle.disposedResourceCounts.materials > 0 &&
          stateBeforeDispose.lifecycle.contextLossCount === 0,
        disposedState.lifecycle,
      ),
    );
    checks.push(
      makeCheck(
        "four_error_classes_zero",
        diagnostics.console_errors.length === 0 &&
          diagnostics.page_errors.length === 0 &&
          diagnostics.http_errors.length === 0 &&
          diagnostics.external_requests.length === 0 &&
          diagnostics.request_failures.length === 0,
        diagnostics,
      ),
    );
  } catch (error) {
    checks.push(
      makeCheck("viewport_execution", false, {
        error: serializeError(error),
        diagnostics,
      }),
    );
  } finally {
    await context.close();
  }

  const passed = checks.every((check) => check.passed);
  return {
    engine,
    viewport: { width, height },
    url: baseUrl,
    data_state: stateBeforeDispose?.loadState || "not_ready",
    passed,
    checks,
    layout,
    stress_audit: stressAudit,
    lifecycle_before_dispose: stateBeforeDispose?.lifecycle || null,
    lifecycle_after_dispose: disposedState?.lifecycle || null,
    diagnostics,
    screenshots,
  };
}

function executionMatrix() {
  if (REPRESENTATIVE_ONLY) {
    return [{ engine: "chromium", viewports: [[1440, 900]] }];
  }
  return [
    { engine: "chromium", viewports: CHROMIUM_VIEWPORTS },
    { engine: "firefox", viewports: REPRESENTATIVE_VIEWPORTS },
    { engine: "webkit", viewports: REPRESENTATIVE_VIEWPORTS },
  ];
}

async function runBrowserMatrix(baseUrl) {
  const results = [];
  for (const entry of executionMatrix()) {
    const browser = await playwright[entry.engine].launch({ headless: true });
    try {
      for (const viewport of entry.viewports) {
        const stress =
          entry.engine === "chromium" &&
          viewport[0] === 1440 &&
          viewport[1] === 900;
        results.push(
          await runViewport(
            browser,
            entry.engine,
            viewport,
            baseUrl,
            stress,
          ),
        );
      }
    } finally {
      await browser.close();
    }
  }
  return results;
}

function errorTotals(results) {
  return results.reduce(
    (totals, result) => {
      totals.console += result.diagnostics.console_errors.length;
      totals.page += result.diagnostics.page_errors.length;
      totals.http += result.diagnostics.http_errors.length;
      totals.external += result.diagnostics.external_requests.length;
      totals.request_failed += result.diagnostics.request_failures.length;
      return totals;
    },
    { console: 0, page: 0, http: 0, external: 0, request_failed: 0 },
  );
}

function stabilityLogPath(iteration) {
  const name = REPRESENTATIVE_ONLY
    ? "bf3d_review_representative_run.json"
    : `bf3d_review_stability_run_${iteration}.json`;
  return path.join(PREVIEW_ROOT, name);
}

function buildStabilityIteration(iteration, results, startedAt, completedAt) {
  const requiredRuns = REPRESENTATIVE_ONLY ? 1 : 17;
  const errors = errorTotals(results);
  const passedRuns = results.filter((entry) => entry.passed).length;
  const screenshotCount = results.reduce(
    (count, entry) => count + entry.screenshots.length,
    0,
  );
  const passed =
    results.length === requiredRuns &&
    passedRuns === requiredRuns &&
    Object.values(errors).every((value) => value === 0) &&
    screenshotCount === requiredRuns * 3;
  const record = {
    schema_version: "bf3d.review_stability_iteration.v1",
    requirement_id: REQUIREMENT_ID,
    iteration,
    iterations_required: STABILITY_ITERATIONS_REQUIRED,
    started_at: startedAt,
    completed_at: completedAt,
    required_runs: requiredRuns,
    actual_runs: results.length,
    passed_runs: passedRuns,
    failed_runs: results.length - passedRuns,
    screenshot_count: screenshotCount,
    error_totals: errors,
    passed,
    source_sha256: {
      html: sha256File(HTML_PATH),
      renderer: sha256File(JS_PATH),
      css: sha256File(CSS_PATH),
      server: sha256File(SERVER_PATH),
      verifier: sha256File(__filename),
    },
    protected_sha256: {
      review_glb: sha256File(REVIEW_GLB_PATH),
      formal_glb: sha256File(FORMAL_GLB_PATH),
      production_html: sha256File(PRODUCTION_HTML_PATH),
      production_controller: sha256File(PRODUCTION_CONTROLLER_PATH),
    },
    runs: results.map((entry) => ({
      engine: entry.engine,
      viewport: entry.viewport,
      passed: entry.passed,
      failed_checks: entry.checks
        .filter((check) => !check.passed)
        .map((check) => check.id),
      check_results: Object.fromEntries(
        entry.checks.map((check) => [check.id, check.passed]),
      ),
      diagnostic_counts: {
        console: entry.diagnostics.console_errors.length,
        page: entry.diagnostics.page_errors.length,
        http: entry.diagnostics.http_errors.length,
        external: entry.diagnostics.external_requests.length,
        request_failed: entry.diagnostics.request_failures.length,
        request_finished: entry.diagnostics.request_finished.length,
      },
      review_glb_request_finished_count:
        entry.diagnostics.request_finished.filter((url) => {
          try {
            return (
              new URL(url).pathname ===
              "/models/gl02_blast_furnace_review.v4.glb"
            );
          } catch {
            return false;
          }
        }).length,
      screenshots: entry.screenshots,
    })),
  };
  const logPath = stabilityLogPath(iteration);
  record.log_path = relativePath(logPath);
  fs.writeFileSync(logPath, `${JSON.stringify(record, null, 2)}\n`, "utf8");
  return record;
}

function aggregateStabilityErrors(iterations) {
  return iterations.reduce(
    (totals, iteration) => {
      for (const key of Object.keys(totals)) {
        totals[key] += iteration.error_totals[key];
      }
      return totals;
    },
    { console: 0, page: 0, http: 0, external: 0, request_failed: 0 },
  );
}

async function main() {
  fs.mkdirSync(SCREENSHOT_ROOT, { recursive: true });
  const startedAt = new Date().toISOString();
  const report = {
    schema_version: "bf3d.review_preview_report.v1",
    requirement_id: REQUIREMENT_ID,
    stage_id: "WEB-60_R2U",
    started_at: startedAt,
    execution_scope: REPRESENTATIVE_ONLY
      ? "representative_chromium_1440x900"
      : "full_cross_engine_viewport_matrix_stability_x2",
    evidence: "E/illustrative",
    reference_status: "REF-PENDING",
    not_for_construction: true,
    blender_equivalence_calibration_complete: false,
    capture_eligible_for_numeric_ab: false,
    approval_granted: false,
    protected_files_before: null,
    source_contract: null,
    glb_contract: null,
    server_contract: null,
    matrix: [],
    stability_iterations_required: STABILITY_ITERATIONS_REQUIRED,
    stability_iterations_completed: 0,
    stability_iterations: [],
    stability_gate_passed: false,
    total_viewport_runs: 0,
    total_passed_runs: 0,
    total_failed_runs: 0,
    total_screenshot_captures: 0,
    protected_files_after: null,
    protected_files_unchanged: false,
    error_totals: null,
    passed_runs: 0,
    failed_runs: 0,
    required_runs: REPRESENTATIVE_ONLY ? 1 : 17,
    required_screenshots_per_run: 3,
    screenshot_count: 0,
    overall_status: "running",
    hard_failures: [],
    limitations: [
      "This page is illustrative and REF-PENDING.",
      "Three r160 sRGB + ACES is an explicit approximate color path.",
      "The equal-area RectAreaLight does not prove Blender Disk Area equivalence or shadows.",
      "The result does not approve P50, P60, P70, QA-70, numeric A/B, or production integration.",
    ],
  };
  let server = null;
  try {
    report.protected_files_before = snapshotProtectedFiles();
    const integrityChecks = Object.entries(report.protected_files_before).map(
      ([id, value]) =>
        makeCheck(
          `source_integrity_${id}`,
          value.bytes_match && value.sha256_match,
          value,
        ),
    );
    report.source_contract = buildStaticContract();
    report.source_contract.checks.unshift(...integrityChecks);
    report.source_contract.passed = report.source_contract.checks.every(
      (check) => check.passed,
    );
    report.glb_contract = buildGlbContract();
    assert(report.source_contract.passed, "静态源合同失败", report.source_contract);
    assert(report.glb_contract.passed, "GLB 结构合同失败", report.glb_contract);

    server = await startReviewServer();
    report.server_contract = server.ready;
    for (
      let iteration = 1;
      iteration <= STABILITY_ITERATIONS_REQUIRED;
      iteration += 1
    ) {
      const iterationStartedAt = new Date().toISOString();
      const matrix = await runBrowserMatrix(server.ready.url);
      const iterationCompletedAt = new Date().toISOString();
      const stabilityIteration = buildStabilityIteration(
        iteration,
        matrix,
        iterationStartedAt,
        iterationCompletedAt,
      );
      report.stability_iterations.push(stabilityIteration);
      report.stability_iterations_completed =
        report.stability_iterations.length;
      report.matrix = matrix;
    }
    report.error_totals = aggregateStabilityErrors(
      report.stability_iterations,
    );
    report.passed_runs = report.matrix.filter((entry) => entry.passed).length;
    report.failed_runs = report.matrix.length - report.passed_runs;
    report.screenshot_count = report.matrix.reduce(
      (count, entry) => count + entry.screenshots.length,
      0,
    );
    report.total_viewport_runs = report.stability_iterations.reduce(
      (count, iteration) => count + iteration.actual_runs,
      0,
    );
    report.total_passed_runs = report.stability_iterations.reduce(
      (count, iteration) => count + iteration.passed_runs,
      0,
    );
    report.total_failed_runs = report.stability_iterations.reduce(
      (count, iteration) => count + iteration.failed_runs,
      0,
    );
    report.total_screenshot_captures =
      report.stability_iterations.reduce(
        (count, iteration) => count + iteration.screenshot_count,
        0,
      );
    report.stability_gate_passed =
      report.stability_iterations_completed ===
        report.stability_iterations_required &&
      report.stability_iterations.every((iteration) => iteration.passed);
    assert(
      report.stability_gate_passed,
      "连续稳定性矩阵硬门失败",
      report.stability_iterations.map((iteration) => ({
        iteration: iteration.iteration,
        passed: iteration.passed,
        passed_runs: iteration.passed_runs,
        failed_runs: iteration.failed_runs,
        screenshot_count: iteration.screenshot_count,
        error_totals: iteration.error_totals,
        log_path: iteration.log_path,
      })),
    );
    assert(
      report.matrix.length === report.required_runs,
      "浏览器矩阵运行数不完整",
      {
        actual: report.matrix.length,
        expected: report.required_runs,
      },
    );
    assert(
      report.failed_runs === 0,
      "浏览器矩阵存在失败",
      report.matrix
        .filter((entry) => !entry.passed)
        .map((entry) => ({
          engine: entry.engine,
          viewport: entry.viewport,
          failed_checks: entry.checks.filter((check) => !check.passed),
        })),
    );
    assert(
      Object.values(report.error_totals).every((value) => value === 0),
      "连续矩阵四类错误或请求失败不为 0",
      report.error_totals,
    );
    assert(
      report.total_viewport_runs ===
        report.required_runs * report.stability_iterations_required &&
        report.total_passed_runs === report.total_viewport_runs &&
        report.total_failed_runs === 0,
      "连续矩阵运行总数或通过数不完整",
      {
        total_viewport_runs: report.total_viewport_runs,
        total_passed_runs: report.total_passed_runs,
        total_failed_runs: report.total_failed_runs,
      },
    );
    assert(
      report.screenshot_count ===
        report.required_runs * report.required_screenshots_per_run,
      "每状态截图数量不完整",
      {
        actual: report.screenshot_count,
        expected:
          report.required_runs * report.required_screenshots_per_run,
      },
    );
    assert(
      report.total_screenshot_captures ===
        report.required_runs *
          report.required_screenshots_per_run *
          report.stability_iterations_required,
      "连续矩阵截图总数不完整",
      {
        actual: report.total_screenshot_captures,
        expected:
          report.required_runs *
          report.required_screenshots_per_run *
          report.stability_iterations_required,
      },
    );
    report.overall_status = REPRESENTATIVE_ONLY
      ? "representative_passed_full_matrix_pending"
      : "full_matrix_passed_illustrative_only";
  } catch (error) {
    report.hard_failures.push(serializeError(error, "verification"));
    report.overall_status = "hard_gate_failed";
  } finally {
    await stopReviewServer(server);
    try {
      report.protected_files_after = snapshotProtectedFiles();
      report.protected_files_unchanged = protectedSnapshotsMatch(
        report.protected_files_before,
        report.protected_files_after,
      );
      if (!report.protected_files_unchanged) {
        report.hard_failures.push({
          phase: "protected_files_after",
          message: "正式 GLB、review GLB、生产页、生产控制器或 vendored Three 前后不一致",
        });
        report.overall_status = "hard_gate_failed";
      }
    } catch (error) {
      report.hard_failures.push(serializeError(error, "protected_files_after"));
      report.overall_status = "hard_gate_failed";
    }
    report.completed_at = new Date().toISOString();
    fs.mkdirSync(path.dirname(REPORT_PATH), { recursive: true });
    fs.writeFileSync(REPORT_PATH, `${JSON.stringify(report, null, 2)}\n`, "utf8");
  }

  process.stdout.write(
    `${JSON.stringify(
      {
        ok:
          report.overall_status ===
            "representative_passed_full_matrix_pending" ||
          report.overall_status === "full_matrix_passed_illustrative_only",
        status: report.overall_status,
        scope: report.execution_scope,
        runs: report.matrix.length,
        passed_runs: report.passed_runs,
        failed_runs: report.failed_runs,
        screenshots: report.screenshot_count,
        stability_iterations_required:
          report.stability_iterations_required,
        stability_iterations_completed:
          report.stability_iterations_completed,
        stability_gate_passed: report.stability_gate_passed,
        total_viewport_runs: report.total_viewport_runs,
        total_passed_runs: report.total_passed_runs,
        total_failed_runs: report.total_failed_runs,
        total_screenshot_captures:
          report.total_screenshot_captures,
        stability_logs: report.stability_iterations.map(
          (iteration) => iteration.log_path,
        ),
        error_totals: report.error_totals,
        protected_files_unchanged: report.protected_files_unchanged,
        report: relativePath(REPORT_PATH),
      },
      null,
      2,
    )}\n`,
  );
  if (report.overall_status === "hard_gate_failed") {
    process.stderr.write(
      `${JSON.stringify(report.hard_failures, null, 2)}\n`,
    );
    process.exitCode = 1;
  }
}

main().catch((error) => {
  process.stderr.write(`${JSON.stringify(serializeError(error), null, 2)}\n`);
  process.exitCode = 1;
});
