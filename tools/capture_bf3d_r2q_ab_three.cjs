#!/usr/bin/env node
"use strict";

/**
 * REQ-BF3D-R2R-BLENDER-RENDERER-NUMERIC-AB-20260719
 *
 * Fail-closed Three.js contract preflight for the locked R2Q renderer A/B
 * stage. This program deliberately stops before any beauty or alpha-mask
 * capture when the live production Web renderer does not match the
 * pre-registered Blender camera, light, and color-management contract.
 *
 * Inputs:
 * - PT/高炉3D模型/work/WEB_60_20260719_R2R_RENDERER_NUMERIC_AB_GATE/
 *   capture_contract.json
 * - the immutable assets listed by capture_contract.json
 * - the production bf3d-structural-review.js controller
 *
 * Outputs:
 * - reports/three_contract_preflight.json
 * - reports/three_capture_manifest.json
 *
 * Exit codes:
 * - 0: contract-compatible and eligible to capture (not expected currently)
 * - 2: blocked_contract_mismatch; no capture was made
 * - 1: preflight execution/input error; no capture was made
 */

const crypto = require("crypto");
const fs = require("fs");
const http = require("http");
const path = require("path");

const PLAYWRIGHT_PATH =
  "C:/Users/hmw20/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/.pnpm/playwright@1.61.1/node_modules/playwright";

let playwright;
try {
  playwright = require("playwright");
} catch {
  playwright = require(PLAYWRIGHT_PATH);
}

const ROOT = path.resolve(__dirname, "..");
const FRONTEND_ROOT = path.join(ROOT, "高炉前端数据");
const STAGE_ROOT = path.join(
  ROOT,
  "PT",
  "高炉3D模型",
  "work",
  "WEB_60_20260719_R2R_RENDERER_NUMERIC_AB_GATE",
);
const REPORT_ROOT = path.join(STAGE_ROOT, "reports");
const CONTRACT_PATH = path.join(STAGE_ROOT, "capture_contract.json");
const PREFLIGHT_PATH = path.join(
  REPORT_ROOT,
  "three_contract_preflight.json",
);
const MANIFEST_PATH = path.join(
  REPORT_ROOT,
  "three_capture_manifest.json",
);
const PRODUCTION_HTML_PATH = path.join(
  FRONTEND_ROOT,
  "frontend_dashboard_v3.server.html",
);
const REVIEW_FILE = "gl02_blast_furnace_review.v3.glb";
const OPERATIONAL_FILE =
  "gl02_blast_furnace_structural_review.v1.glb";
const REVIEW_ASSET_URL = `models/${REVIEW_FILE}`;
const VIEWPORT = Object.freeze({ width: 1920, height: 1080 });
const DEVICE_SCALE_FACTOR = 1;
const CONTRACT_MISMATCH_EXIT_CODE = 2;

const MIME = {
  ".html": "text/html; charset=utf-8",
  ".js": "text/javascript; charset=utf-8",
  ".css": "text/css; charset=utf-8",
  ".json": "application/json; charset=utf-8",
  ".glb": "model/gltf-binary",
  ".bin": "application/octet-stream",
  ".hdr": "application/octet-stream",
  ".png": "image/png",
  ".jpg": "image/jpeg",
  ".jpeg": "image/jpeg",
  ".webp": "image/webp",
  ".svg": "image/svg+xml",
  ".woff": "font/woff",
  ".woff2": "font/woff2",
};

function timestamp() {
  return new Date().toISOString();
}

function relativeToRoot(filePath) {
  return path.relative(ROOT, filePath).split(path.sep).join("/");
}

function sha256(filePath) {
  return crypto
    .createHash("sha256")
    .update(fs.readFileSync(filePath))
    .digest("hex");
}

function readJson(filePath) {
  return JSON.parse(fs.readFileSync(filePath, "utf8"));
}

function writeJson(filePath, value) {
  fs.mkdirSync(path.dirname(filePath), { recursive: true });
  fs.writeFileSync(
    filePath,
    `${JSON.stringify(value, null, 2)}\n`,
    "utf8",
  );
}

function maxAbsDifference(left, right) {
  if (
    !Array.isArray(left) ||
    !Array.isArray(right) ||
    left.length !== right.length
  ) {
    return null;
  }
  let maximum = 0;
  for (let index = 0; index < left.length; index += 1) {
    const a = Number(left[index]);
    const b = Number(right[index]);
    if (!Number.isFinite(a) || !Number.isFinite(b)) return null;
    maximum = Math.max(maximum, Math.abs(a - b));
  }
  return maximum;
}

function inspectInputLocks(contract) {
  return (contract.input_locks || []).map((lock) => {
    const absolutePath = path.resolve(ROOT, lock.path);
    const exists = fs.existsSync(absolutePath);
    const stat = exists ? fs.statSync(absolutePath) : null;
    const actualBytes = stat?.isFile() ? stat.size : null;
    const actualSha256 = stat?.isFile() ? sha256(absolutePath) : null;
    const bytesMatch = actualBytes === Number(lock.bytes);
    const sha256Match =
      actualSha256 === String(lock.sha256 || "").toLowerCase();
    return {
      id: lock.id,
      path: lock.path,
      required: lock.required === true,
      expected: {
        bytes: Number(lock.bytes),
        sha256: String(lock.sha256 || "").toLowerCase(),
      },
      actual: {
        exists,
        is_file: Boolean(stat?.isFile()),
        bytes: actualBytes,
        sha256: actualSha256,
      },
      bytes_match: bytesMatch,
      sha256_match: sha256Match,
      passed:
        exists &&
        Boolean(stat?.isFile()) &&
        bytesMatch &&
        sha256Match,
    };
  });
}

function requiredLocksPassed(lockChecks) {
  return lockChecks
    .filter((item) => item.required)
    .every((item) => item.passed);
}

function startStaticServer() {
  return new Promise((resolve, reject) => {
    const server = http.createServer((request, response) => {
      let pathname;
      try {
        pathname = decodeURIComponent(
          new URL(request.url, "http://127.0.0.1").pathname,
        );
      } catch {
        response.writeHead(400).end("bad request");
        return;
      }
      if (pathname === "/") {
        pathname = "/frontend_dashboard_v3.server.html";
      }
      const target = path.resolve(
        FRONTEND_ROOT,
        pathname.replace(/^\/+/, ""),
      );
      if (
        target !== FRONTEND_ROOT &&
        !target.startsWith(`${FRONTEND_ROOT}${path.sep}`)
      ) {
        response.writeHead(403).end("forbidden");
        return;
      }
      fs.stat(target, (error, stat) => {
        if (error || !stat.isFile()) {
          response.writeHead(404).end("not found");
          return;
        }
        response.writeHead(200, {
          "Content-Type":
            MIME[path.extname(target).toLowerCase()] ||
            "application/octet-stream",
          "Cache-Control": "no-store",
        });
        fs.createReadStream(target).pipe(response);
      });
    });
    server.once("error", reject);
    server.listen(0, "127.0.0.1", () => resolve(server));
  });
}

function isExpectedOfflineNoise(value) {
  const text = String(value || "");
  return (
    text.includes("127.0.0.1:8767") ||
    text.includes("ws://127.0.0.1:8767") ||
    text.includes("/api/") ||
    text.includes("/favicon.ico") ||
    text.includes("[BABEL] Note:")
  );
}

function attachDiagnostics(page) {
  const diagnostics = {
    page_errors: [],
    console_errors: [],
    http_errors: [],
    request_failures: [],
    ignored_expected_request_failures: [],
    review_asset_responses: [],
  };
  page.on("pageerror", (error) => {
    diagnostics.page_errors.push(String(error));
  });
  page.on("console", (message) => {
    if (message.type() !== "error") return;
    const location = message.location()?.url || "";
    if (
      !isExpectedOfflineNoise(message.text()) &&
      !isExpectedOfflineNoise(location)
    ) {
      diagnostics.console_errors.push({
        text: message.text(),
        location,
      });
    }
  });
  page.on("response", (response) => {
    let responsePath = "";
    try {
      responsePath = new URL(response.url()).pathname;
    } catch {
      responsePath = response.url();
    }
    if (responsePath.endsWith(`/${REVIEW_FILE}`)) {
      diagnostics.review_asset_responses.push({
        status: response.status(),
        url: response.url(),
      });
      return;
    }
    if (
      response.status() >= 400 &&
      !isExpectedOfflineNoise(response.url())
    ) {
      diagnostics.http_errors.push({
        status: response.status(),
        url: response.url(),
      });
    }
  });
  page.on("requestfailed", (request) => {
    const failure = {
      url: request.url(),
      error: request.failure()?.errorText || "unknown",
    };
    if (
      failure.url.includes(`/${OPERATIONAL_FILE}`) &&
      failure.error.includes("ERR_ABORTED")
    ) {
      /*
       * The production React page can dispose an initial duplicate
       * operational viewer while mounting the surviving overview viewer.
       * The surviving controller has already proven 115 sensors ready; this
       * cancelled duplicate is therefore recorded, but is not a review-asset
       * or render-contract failure. This matches the existing structural
       * verifier's narrower request-failure policy.
       */
      diagnostics.ignored_expected_request_failures.push(failure);
      return;
    }
    if (!isExpectedOfflineNoise(failure.url)) {
      diagnostics.request_failures.push(failure);
    }
  });
  return diagnostics;
}

async function waitForProductionController(page) {
  await page.waitForFunction(
    () => {
      const controller = window.__BF3D_STRUCTURAL_REVIEW__;
      const state = controller?.getState?.();
      const viewer = window.__BF_CAD_FURNACE_VIEWER;
      return (
        state?.status === "ready" &&
        state?.mode === "operational" &&
        state?.sensor_count === 115 &&
        viewer?.renderer?.isWebGLRenderer === true &&
        viewer?.camera?.isCamera === true &&
        viewer?.THREE?.REVISION
      );
    },
    null,
    { timeout: 90_000 },
  );
}

async function enterStructuralReview(page) {
  await page.evaluate(async () => {
    await window.__BF3D_STRUCTURAL_REVIEW__.setMode("structural");
  });
  await page.waitForFunction(
    () => {
      const state = window.__BF3D_STRUCTURAL_REVIEW__?.getState?.();
      return (
        state?.mode === "structural" &&
        state?.asset_status === "ready" &&
        state?.section_visible_count === 10 &&
        state?.material_visible_count === 0
      );
    },
    null,
    { timeout: 90_000 },
  );
  await page.evaluate(() => {
    document
      .querySelector('[data-review-camera="global"]')
      ?.click();
  });
  await page.waitForFunction(
    () =>
      window.__BF3D_STRUCTURAL_REVIEW__?.getState?.()
        .structural_camera === "global",
    null,
    { timeout: 30_000 },
  );
}

async function fixCaptureCanvas(page) {
  return page.evaluate(({ width, height, dpr }) => {
    const viewer = window.__BF_CAD_FURNACE_VIEWER;
    const renderer = viewer?.renderer;
    const camera = viewer?.camera;
    const canvas = renderer?.domElement;
    const host = canvas?.parentElement;
    if (!viewer || !renderer || !camera || !canvas || !host) {
      throw new Error("production Three.js viewer is incomplete");
    }

    /*
     * Capture-harness-only normalization. It changes no checked-in source,
     * camera type/FOV/framing, light, material, tone map, or exposure.
     */
    host.style.position = "fixed";
    host.style.left = "0";
    host.style.top = "0";
    host.style.right = "auto";
    host.style.bottom = "auto";
    host.style.width = `${width}px`;
    host.style.height = `${height}px`;
    host.style.maxWidth = "none";
    host.style.maxHeight = "none";
    host.style.margin = "0";
    host.style.padding = "0";
    canvas.style.display = "block";
    renderer.setPixelRatio(dpr);
    renderer.setSize(width, height, true);
    if (camera.isPerspectiveCamera) {
      camera.aspect = width / height;
    }
    camera.updateProjectionMatrix();
    viewer.controls?.update?.();
    renderer.render(viewer.scene, camera);

    return {
      scope: "capture_harness_runtime_only",
      source_files_mutated: false,
      permitted_adjustments: [
        "CSS canvas width/height",
        "WebGLRenderer pixel ratio",
        "WebGLRenderer drawing-buffer size",
        "camera aspect ratio for the fixed canvas",
      ],
      forbidden_adjustments_applied: [],
    };
  }, {
    width: VIEWPORT.width,
    height: VIEWPORT.height,
    dpr: DEVICE_SCALE_FACTOR,
  });
}

async function waitForTwoAnimationFrames(page) {
  await page.evaluate(
    () =>
      new Promise((resolve) => {
        requestAnimationFrame(() => requestAnimationFrame(resolve));
      }),
  );
}

async function inspectRuntime(page, browserIdentity) {
  const runtime = await page.evaluate(({ width, height }) => {
    const viewer = window.__BF_CAD_FURNACE_VIEWER;
    const controller = window.__BF3D_STRUCTURAL_REVIEW__;
    const state = controller.getState();
    const THREE = viewer.THREE;
    const renderer = viewer.renderer;
    const camera = viewer.camera;
    const scene = viewer.scene;
    const canvas = renderer.domElement;
    const gl = renderer.getContext();
    const contextAttributes = gl.getContextAttributes();
    const debugInfo = gl.getExtension("WEBGL_debug_renderer_info");
    const drawingBufferSize = renderer.getDrawingBufferSize(
      new THREE.Vector2(),
    );
    const logicalRendererSize = renderer.getSize(new THREE.Vector2());
    const canvasRect = canvas.getBoundingClientRect();
    const sectionGroup = scene.getObjectByName("BF3D_V3_MODE_SECTION");
    const materialGroup = scene.getObjectByName("BF3D_V3_MODE_MATERIAL");
    const reviewRoot = scene.getObjectByName(
      "BF3D_V3_CONTROLLED_REVIEW_ROOT",
    );
    const reviewLights = scene.getObjectByName(
      "BF3D_REVIEW_NEUTRAL_LIGHTS",
    );

    const vector = (value) =>
      value
        ? [Number(value.x), Number(value.y), Number(value.z)]
        : null;
    const matrix = (value) =>
      value?.elements?.map((item) => Number(item)) || null;
    const color = (value) =>
      value
        ? {
            linear_rgb: value.toArray().map((item) => Number(item)),
            hex: `#${value.getHexString()}`,
          }
        : null;

    let bounds = null;
    let productionDynamicFrame = null;
    if (sectionGroup) {
      sectionGroup.updateWorldMatrix(true, true);
      const box = new THREE.Box3().setFromObject(sectionGroup);
      const center = box.getCenter(new THREE.Vector3());
      const size = box.getSize(new THREE.Vector3());
      const sphere = box.getBoundingSphere(new THREE.Sphere());
      const direction = new THREE.Vector3(1, 0.1, 0.08).normalize();
      const halfFov = THREE.MathUtils.degToRad(
        Math.max(10, camera.fov || 42) * 0.5,
      );
      const distance = Math.max(
        sphere.radius * 1.35,
        sphere.radius / Math.max(Math.sin(halfFov), 0.2),
      );
      const expectedPosition = center
        .clone()
        .addScaledVector(direction, distance);
      const positionDelta = camera.position
        .clone()
        .sub(expectedPosition)
        .toArray()
        .map((item) => Number(item));
      const browserHeight = size.y;
      const browserWidth = size.z;
      const orthographicScale = Math.max(
        1.05 * browserHeight,
        1.22 * browserWidth,
      );
      bounds = {
        min: vector(box.min),
        max: vector(box.max),
        center: vector(center),
        size: vector(size),
        sphere_radius: Number(sphere.radius),
      };
      productionDynamicFrame = {
        implementation:
          "runtime Box3/BoundingSphere + PerspectiveCamera FOV",
        direction: vector(direction),
        half_fov_rad: Number(halfFov),
        distance: Number(distance),
        expected_position_from_current_controller_formula:
          vector(expectedPosition),
        actual_position: vector(camera.position),
        position_abs_max: Math.max(
          ...positionDelta.map((item) => Math.abs(item)),
        ),
        matches_current_controller_formula:
          positionDelta.every((item) => Math.abs(item) <= 1e-5),
        required_orthographic_formula_browser_axis_audit: {
          note:
            "Diagnostic Y-up interpretation only; no matrix comparison is authorized after projection-type mismatch.",
          location: [
            Number(box.max.x + 1.8 * Math.max(browserHeight, browserWidth)),
            Number(center.y),
            Number(center.z),
          ],
          target: vector(center),
          ortho_scale: Number(orthographicScale),
          browser_height_from_size_y: Number(browserHeight),
          browser_width_from_size_z: Number(browserWidth),
        },
      };
    }

    const lightInventory = [];
    reviewLights?.traverse((object) => {
      if (!object.isLight) return;
      const target = object.target || null;
      const direction = target
        ? target
            .getWorldPosition(new THREE.Vector3())
            .sub(object.getWorldPosition(new THREE.Vector3()))
            .normalize()
        : null;
      lightInventory.push({
        name: object.name || null,
        three_type: object.type,
        intensity: Number(object.intensity),
        color: color(object.color),
        position: vector(object.position),
        world_position: vector(
          object.getWorldPosition(new THREE.Vector3()),
        ),
        target_name: target?.name || null,
        target_position: target ? vector(target.position) : null,
        direction_to_runtime_target: vector(direction),
        distance: Number.isFinite(Number(object.distance))
          ? Number(object.distance)
          : null,
        decay: Number.isFinite(Number(object.decay))
          ? Number(object.decay)
          : null,
        width: Number.isFinite(Number(object.width))
          ? Number(object.width)
          : null,
        height: Number.isFinite(Number(object.height))
          ? Number(object.height)
          : null,
      });
    });

    const toneMappingName = (() => {
      const values = [
        ["THREE.NoToneMapping", THREE.NoToneMapping],
        ["THREE.LinearToneMapping", THREE.LinearToneMapping],
        ["THREE.ReinhardToneMapping", THREE.ReinhardToneMapping],
        ["THREE.CineonToneMapping", THREE.CineonToneMapping],
        ["THREE.ACESFilmicToneMapping", THREE.ACESFilmicToneMapping],
        ["THREE.AgXToneMapping", THREE.AgXToneMapping],
        ["THREE.NeutralToneMapping", THREE.NeutralToneMapping],
      ];
      return (
        values.find(([, value]) => value === renderer.toneMapping)?.[0] ||
        `unknown(${renderer.toneMapping})`
      );
    })();

    const outputColorSpaceName =
      renderer.outputColorSpace === THREE.SRGBColorSpace
        ? "THREE.SRGBColorSpace"
        : renderer.outputColorSpace === THREE.LinearSRGBColorSpace
          ? "THREE.LinearSRGBColorSpace"
          : String(renderer.outputColorSpace);

    const moduleResources = performance
      .getEntriesByType("resource")
      .map((entry) => entry.name)
      .filter((name) => /\/libs\/three\/three\.module\.js(?:\?|$)/.test(name));

    return {
      page: {
        url: location.href,
        title: document.title,
        viewport: {
          inner_width: window.innerWidth,
          inner_height: window.innerHeight,
          visual_viewport_width: window.visualViewport?.width || null,
          visual_viewport_height: window.visualViewport?.height || null,
          requested_width: width,
          requested_height: height,
        },
        device_pixel_ratio: window.devicePixelRatio,
      },
      browser: {
        user_agent: navigator.userAgent,
        platform: navigator.platform,
        language: navigator.language,
        user_agent_data: navigator.userAgentData
          ? {
              brands: navigator.userAgentData.brands,
              mobile: navigator.userAgentData.mobile,
              platform: navigator.userAgentData.platform,
            }
          : null,
      },
      three: {
        revision: String(THREE.REVISION),
        module_resources: moduleResources,
      },
      webgl: {
        context_constructor: gl.constructor?.name || null,
        version: String(gl.getParameter(gl.VERSION)),
        shading_language_version: String(
          gl.getParameter(gl.SHADING_LANGUAGE_VERSION),
        ),
        vendor: String(gl.getParameter(gl.VENDOR)),
        renderer: String(gl.getParameter(gl.RENDERER)),
        unmasked_vendor: debugInfo
          ? String(gl.getParameter(debugInfo.UNMASKED_VENDOR_WEBGL))
          : null,
        unmasked_renderer: debugInfo
          ? String(gl.getParameter(debugInfo.UNMASKED_RENDERER_WEBGL))
          : null,
        context_attributes: contextAttributes
          ? {
              alpha: contextAttributes.alpha,
              antialias: contextAttributes.antialias,
              depth: contextAttributes.depth,
              stencil: contextAttributes.stencil,
              premultiplied_alpha:
                contextAttributes.premultipliedAlpha,
              preserve_drawing_buffer:
                contextAttributes.preserveDrawingBuffer,
              power_preference: contextAttributes.powerPreference,
              fail_if_major_performance_caveat:
                contextAttributes.failIfMajorPerformanceCaveat,
              desynchronized: contextAttributes.desynchronized,
            }
          : null,
        max_texture_size: Number(
          gl.getParameter(gl.MAX_TEXTURE_SIZE),
        ),
        max_renderbuffer_size: Number(
          gl.getParameter(gl.MAX_RENDERBUFFER_SIZE),
        ),
      },
      canvas: {
        element_width: canvas.width,
        element_height: canvas.height,
        client_width: canvas.clientWidth,
        client_height: canvas.clientHeight,
        bounding_rect: {
          x: Number(canvasRect.x),
          y: Number(canvasRect.y),
          width: Number(canvasRect.width),
          height: Number(canvasRect.height),
        },
        renderer_logical_size: vector({
          x: logicalRendererSize.x,
          y: logicalRendererSize.y,
          z: 0,
        }).slice(0, 2),
        renderer_pixel_ratio: Number(renderer.getPixelRatio()),
        renderer_drawing_buffer_size: vector({
          x: drawingBufferSize.x,
          y: drawingBufferSize.y,
          z: 0,
        }).slice(0, 2),
        gl_drawing_buffer_size: [
          Number(gl.drawingBufferWidth),
          Number(gl.drawingBufferHeight),
        ],
      },
      controller_state: state,
      asset_scene: {
        review_root_present: Boolean(reviewRoot),
        review_root_name: reviewRoot?.name || null,
        section_group_present: Boolean(sectionGroup),
        section_group_name: sectionGroup?.name || null,
        section_group_visible: sectionGroup?.visible ?? null,
        material_group_present: Boolean(materialGroup),
        material_group_name: materialGroup?.name || null,
        material_group_visible: materialGroup?.visible ?? null,
        section_bounds: bounds,
      },
      camera: {
        name: camera.name || null,
        type: camera.type,
        is_camera: camera.isCamera === true,
        is_perspective_camera: camera.isPerspectiveCamera === true,
        is_orthographic_camera: camera.isOrthographicCamera === true,
        fov_degrees: Number.isFinite(Number(camera.fov))
          ? Number(camera.fov)
          : null,
        aspect: Number.isFinite(Number(camera.aspect))
          ? Number(camera.aspect)
          : null,
        zoom: Number(camera.zoom),
        near: Number(camera.near),
        far: Number(camera.far),
        position: vector(camera.position),
        quaternion: [
          Number(camera.quaternion.x),
          Number(camera.quaternion.y),
          Number(camera.quaternion.z),
          Number(camera.quaternion.w),
        ],
        up: vector(camera.up),
        controls_target: vector(viewer.controls?.target),
        matrix_world: matrix(camera.matrixWorld),
        matrix_world_inverse: matrix(camera.matrixWorldInverse),
        projection_matrix: matrix(camera.projectionMatrix),
        projection_matrix_inverse: matrix(
          camera.projectionMatrixInverse,
        ),
        production_dynamic_frame: productionDynamicFrame,
      },
      lights: {
        collection_name: reviewLights?.name || null,
        collection_present: Boolean(reviewLights),
        collection_visible: reviewLights?.visible ?? null,
        inventory: lightInventory,
      },
      color_management: {
        output_color_space: outputColorSpaceName,
        output_color_space_raw: String(renderer.outputColorSpace),
        tone_mapping: toneMappingName,
        tone_mapping_raw: Number(renderer.toneMapping),
        tone_mapping_exposure_multiplier: Number(
          renderer.toneMappingExposure,
        ),
        tone_mapping_exposure_equivalent_ev:
          renderer.toneMappingExposure > 0
            ? Number(Math.log2(renderer.toneMappingExposure))
            : null,
        clear_alpha: Number(renderer.getClearAlpha()),
        scene_background: scene.background
          ? color(scene.background)
          : null,
        scene_environment_present: Boolean(scene.environment),
        scene_fog_present: Boolean(scene.fog),
        direct_render_without_composer:
          state.lookdev_mode === "neutral_direct",
      },
    };
  }, VIEWPORT);

  runtime.browser.playwright_engine = browserIdentity.engine;
  runtime.browser.playwright_browser_version =
    browserIdentity.browserVersion;
  return runtime;
}

function makeCheck(
  id,
  status,
  expected,
  actual,
  reason,
  options = {},
) {
  return {
    id,
    status,
    blocking: options.blocking !== false,
    expected,
    actual,
    reason,
  };
}

function buildChecks(contract, lockChecks, runtime, diagnostics) {
  const checks = [];
  const sceneContract = contract.scene_contract || {};
  const requiredLights = sceneContract.required_lights || [];
  const requiredLightTypes = sceneContract.required_light_types || {};
  const lightInventory = runtime.lights.inventory || [];
  const lightsByName = new Map(
    lightInventory
      .filter((light) => light.name)
      .map((light) => [light.name, light]),
  );
  const requiredWebTypes = {
    SUN: "DirectionalLight",
    AREA: "RectAreaLight",
    AREA_DISK: "RectAreaLight",
  };

  checks.push(
    makeCheck(
      "immutable_input_locks",
      requiredLocksPassed(lockChecks) ? "pass" : "fail",
      {
        required_locks:
          lockChecks.filter((item) => item.required).length,
        bytes_and_sha256_match: true,
      },
      {
        passed:
          lockChecks.filter(
            (item) => item.required && item.passed,
          ).length,
        failed:
          lockChecks.filter(
            (item) => item.required && !item.passed,
          ).length,
      },
      requiredLocksPassed(lockChecks)
        ? "All required locked inputs match the pre-registered byte size and SHA-256."
        : "One or more required inputs drifted; the contract is fail-closed.",
    ),
  );

  const expectedResolution = sceneContract.resolution || [
    VIEWPORT.width,
    VIEWPORT.height,
  ];
  const canvas = runtime.canvas;
  const viewport = runtime.page.viewport;
  const canvasFixed =
    viewport.inner_width === expectedResolution[0] &&
    viewport.inner_height === expectedResolution[1] &&
    runtime.page.device_pixel_ratio === DEVICE_SCALE_FACTOR &&
    canvas.element_width === expectedResolution[0] &&
    canvas.element_height === expectedResolution[1] &&
    canvas.client_width === expectedResolution[0] &&
    canvas.client_height === expectedResolution[1] &&
    canvas.renderer_pixel_ratio === DEVICE_SCALE_FACTOR &&
    canvas.renderer_drawing_buffer_size[0] === expectedResolution[0] &&
    canvas.renderer_drawing_buffer_size[1] === expectedResolution[1] &&
    canvas.gl_drawing_buffer_size[0] === expectedResolution[0] &&
    canvas.gl_drawing_buffer_size[1] === expectedResolution[1];
  checks.push(
    makeCheck(
      "fixed_capture_canvas",
      canvasFixed ? "pass" : "fail",
      {
        css_viewport: expectedResolution,
        canvas_css_pixels: expectedResolution,
        drawing_buffer_pixels: expectedResolution,
        device_pixel_ratio: DEVICE_SCALE_FACTOR,
        resolution_percentage:
          sceneContract.resolution_percentage,
      },
      {
        css_viewport: [
          viewport.inner_width,
          viewport.inner_height,
        ],
        canvas_element: [
          canvas.element_width,
          canvas.element_height,
        ],
        canvas_client: [
          canvas.client_width,
          canvas.client_height,
        ],
        renderer_pixel_ratio: canvas.renderer_pixel_ratio,
        renderer_drawing_buffer:
          canvas.renderer_drawing_buffer_size,
        gl_drawing_buffer: canvas.gl_drawing_buffer_size,
      },
      canvasFixed
        ? "The capture harness established an actual 1920x1080 DPR1 production WebGL canvas."
        : "The production WebGL canvas did not reach the fixed capture dimensions.",
    ),
  );

  const identityComplete =
    Boolean(runtime.browser.user_agent) &&
    Boolean(runtime.browser.playwright_browser_version) &&
    Boolean(runtime.three.revision) &&
    Boolean(runtime.webgl.version) &&
    Boolean(runtime.webgl.renderer);
  checks.push(
    makeCheck(
      "runtime_identity",
      identityComplete ? "pass" : "fail",
      {
        actual_browser_identity_required: true,
        actual_three_identity_required: true,
        actual_webgl_identity_required: true,
      },
      {
        browser: runtime.browser,
        three: runtime.three,
        webgl: runtime.webgl,
      },
      identityComplete
        ? "Browser, Three.js, and WebGL identities were read from the live production viewer."
        : "At least one required runtime identity is unavailable.",
    ),
  );

  const state = runtime.controller_state;
  const reviewAssetReady =
    state.mode === "structural" &&
    state.asset_status === "ready" &&
    state.review_asset_url === REVIEW_ASSET_URL &&
    diagnostics.review_asset_responses.some(
      (response) => response.status === 200,
    );
  checks.push(
    makeCheck(
      "locked_review_glb_loaded",
      reviewAssetReady ? "pass" : "fail",
      {
        review_asset_url: REVIEW_ASSET_URL,
        mode: "structural",
        asset_status: "ready",
      },
      {
        review_asset_url: state.review_asset_url,
        mode: state.mode,
        asset_status: state.asset_status,
        responses: diagnostics.review_asset_responses,
      },
      reviewAssetReady
        ? "The live production controller loaded the locked R2Q V3 review GLB."
        : "The locked review GLB was not proven ready in the production controller.",
    ),
  );

  const meshCountsMatch =
    state.section_visible_count ===
      sceneContract.expected_visible_meshes &&
    state.material_renderable_count ===
      sceneContract.expected_hidden_meshes &&
    state.material_visible_count === 0;
  checks.push(
    makeCheck(
      "review_mesh_visibility",
      meshCountsMatch ? "pass" : "fail",
      {
        visible_collection: sceneContract.visible_collection,
        hidden_collection: sceneContract.hidden_collection,
        expected_visible_meshes:
          sceneContract.expected_visible_meshes,
        expected_hidden_meshes:
          sceneContract.expected_hidden_meshes,
      },
      {
        web_section_group:
          runtime.asset_scene.section_group_name,
        web_material_group:
          runtime.asset_scene.material_group_name,
        section_visible_count: state.section_visible_count,
        material_renderable_count:
          state.material_renderable_count,
        material_visible_count: state.material_visible_count,
      },
      meshCountsMatch
        ? "The R2Q section mesh counts and material-group isolation match the registered counts."
        : "The section/material visibility counts do not match the registered contract.",
    ),
  );

  const requiredCameraType = sceneContract.camera_type;
  const actualCameraType = runtime.camera.is_orthographic_camera
    ? "ORTHO"
    : runtime.camera.is_perspective_camera
      ? "PERSPECTIVE"
      : runtime.camera.type;
  checks.push(
    makeCheck(
      "camera_projection_type",
      actualCameraType === requiredCameraType ? "pass" : "fail",
      {
        camera_object: sceneContract.camera_object,
        camera_type: requiredCameraType,
      },
      {
        camera_name: runtime.camera.name,
        camera_type: actualCameraType,
        three_type: runtime.camera.type,
        fov_degrees: runtime.camera.fov_degrees,
      },
      actualCameraType === requiredCameraType
        ? "The production projection type matches the registered Blender camera."
        : "Production uses PerspectiveCamera(42); the registered Blender capture requires a named orthographic camera.",
    ),
  );

  const fixedCameraObject =
    runtime.camera.name === sceneContract.camera_object &&
    runtime.camera.production_dynamic_frame
      ?.matches_current_controller_formula !== true;
  checks.push(
    makeCheck(
      "camera_object_and_framing_source",
      fixedCameraObject ? "pass" : "fail",
      {
        camera_object: sceneContract.camera_object,
        framing:
          "locked Blender camera and pre-registered per-shot orthographic formula",
      },
      {
        camera_name: runtime.camera.name,
        framing:
          runtime.camera.production_dynamic_frame?.implementation ||
          null,
        matches_production_dynamic_bounds_formula:
          runtime.camera.production_dynamic_frame
            ?.matches_current_controller_formula ?? null,
        dynamic_bounds:
          runtime.asset_scene.section_bounds,
        dynamic_frame:
          runtime.camera.production_dynamic_frame,
      },
      fixedCameraObject
        ? "The named fixed camera and framing source match."
        : "The Web camera is unnamed and is re-framed from live Box3/BoundingSphere bounds, so it is not the locked Blender orthographic camera.",
    ),
  );

  checks.push(
    makeCheck(
      "camera_matrix_and_projection_abs_max",
      actualCameraType === requiredCameraType &&
        fixedCameraObject
        ? "not_evaluated"
        : "blocked",
      {
        threshold:
          contract.comparison_contract?.thresholds
            ?.camera_matrix_and_projection_abs_max,
      },
      {
        current_web_matrix_world:
          runtime.camera.matrix_world,
        current_web_projection_matrix:
          runtime.camera.projection_matrix,
        blender_camera_matrix:
          "not read because categorical camera preflight failed",
      },
      "Numeric camera-matrix A/B is forbidden until camera type, named object, coordinate convention, and framing source match.",
    ),
  );

  checks.push(
    makeCheck(
      "light_collection",
      runtime.lights.collection_name ===
        sceneContract.light_collection
        ? "pass"
        : "fail",
      {
        collection_name: sceneContract.light_collection,
      },
      {
        collection_name: runtime.lights.collection_name,
        collection_present: runtime.lights.collection_present,
        collection_visible: runtime.lights.collection_visible,
      },
      runtime.lights.collection_name ===
        sceneContract.light_collection
        ? "The light collection name matches."
        : "The Web controller creates a runtime approximation group instead of the registered Blender light collection.",
    ),
  );

  for (const lightName of requiredLights) {
    const expectedType = requiredLightTypes[lightName] || null;
    const expectedWebType =
      requiredWebTypes[expectedType] || expectedType;
    const actualLight = lightsByName.get(lightName) || null;
    const typeMatches =
      actualLight && actualLight.three_type === expectedWebType;
    checks.push(
      makeCheck(
        `required_light:${lightName}`,
        typeMatches ? "pass" : "fail",
        {
          blender_type: expectedType,
          required_web_analogue: expectedWebType,
        },
        actualLight,
        typeMatches
          ? `${lightName} is present with the expected Web analogue.`
          : actualLight
            ? `${lightName} has the wrong Web light type.`
            : `${lightName} is absent from the live Web light rig.`,
      ),
    );
  }

  const extraLights = lightInventory
    .filter((light) => !requiredLights.includes(light.name))
    .map((light) => ({
      name: light.name,
      three_type: light.three_type,
      intensity: light.intensity,
    }));
  const topArea = lightsByName.get("P40_NEUTRAL_TOP");
  checks.push(
    makeCheck(
      "top_area_and_world_separation",
      Boolean(topArea?.three_type === "RectAreaLight")
        ? "pass"
        : "fail",
      {
        required_top_light: {
          name: "P40_NEUTRAL_TOP",
          blender_type: "AREA",
          required_web_analogue: "RectAreaLight",
        },
        world_light_is_not_a_substitute: true,
      },
      {
        top_light: topArea || null,
        extra_runtime_lights: extraLights,
      },
      topArea?.three_type === "RectAreaLight"
        ? "The required top AREA light has a Web area-light analogue."
        : "The controller filters the preset to SUN lights and adds AmbientLight as a world approximation; that does not replace P40_NEUTRAL_TOP AREA.",
    ),
  );

  const dynamicDirections = lightInventory
    .filter((light) => requiredLights.includes(light.name))
    .filter((light) => light.target_name?.endsWith("_TARGET"));
  checks.push(
    makeCheck(
      "light_direction_source",
      dynamicDirections.length === 0 ? "pass" : "fail",
      {
        direction_source:
          "locked Blender rotation_euler_rad for every required light",
      },
      {
        direction_source:
          dynamicDirections.length > 0
            ? "runtime target at current section bounds focus"
            : null,
        dynamically_targeted_lights: dynamicDirections.map(
          (light) => ({
            name: light.name,
            target_name: light.target_name,
            target_position: light.target_position,
            direction_to_runtime_target:
              light.direction_to_runtime_target,
          }),
        ),
      },
      dynamicDirections.length === 0
        ? "Required light directions are not dynamically retargeted."
        : "The Web SUN analogues aim at the current bounds focus and do not preserve the locked Blender Euler rotations.",
    ),
  );

  const allRequiredLightsMatch = requiredLights.every((name) => {
    const expectedType = requiredWebTypes[
      requiredLightTypes[name]
    ];
    return lightsByName.get(name)?.three_type === expectedType;
  });
  checks.push(
    makeCheck(
      "light_position_direction_color_abs_max",
      allRequiredLightsMatch && dynamicDirections.length === 0
        ? "not_evaluated"
        : "blocked",
      {
        threshold:
          contract.comparison_contract?.thresholds
            ?.light_position_direction_color_abs_max,
      },
      {
        inventory: lightInventory,
        blender_numeric_comparison:
          "not executed because the required rig is incomplete or dynamically retargeted",
      },
      "Numeric light parity cannot be evaluated after a missing required light or direction-source mismatch.",
    ),
  );

  const expectedViewTransform = sceneContract.view_transform;
  const actualToneMapping = runtime.color_management.tone_mapping;
  const viewTransformMatches =
    expectedViewTransform === "AgX" &&
    actualToneMapping === "THREE.AgXToneMapping";
  checks.push(
    makeCheck(
      "view_transform",
      viewTransformMatches ? "pass" : "fail",
      {
        blender_view_transform: expectedViewTransform,
        blender_look: sceneContract.look,
      },
      {
        web_tone_mapping: actualToneMapping,
        web_look: "not implemented",
      },
      viewTransformMatches
        ? "The Web tone mapper implements the registered AgX view transform."
        : "The registered Blender pipeline is AgX with a named look; production Web uses ACES filmic and has no matching AgX look.",
    ),
  );

  const outputSrgb =
    runtime.color_management.output_color_space ===
    "THREE.SRGBColorSpace";
  checks.push(
    makeCheck(
      "display_output_color_space",
      outputSrgb ? "pass" : "fail",
      {
        blender_display: "sRGB",
      },
      {
        web_output_color_space:
          runtime.color_management.output_color_space,
      },
      outputSrgb
        ? "Both pipelines target an sRGB display/output encoding."
        : "The Web output encoding is not sRGB.",
    ),
  );

  const expectedExposureEv = Number(sceneContract.exposure);
  const actualExposureEv =
    runtime.color_management
      .tone_mapping_exposure_equivalent_ev;
  const exposureMatches =
    Number.isFinite(expectedExposureEv) &&
    Number.isFinite(actualExposureEv) &&
    Math.abs(expectedExposureEv - actualExposureEv) <= 1e-12;
  checks.push(
    makeCheck(
      "exposure",
      exposureMatches ? "pass" : "fail",
      {
        blender_exposure_ev: expectedExposureEv,
        equivalent_linear_multiplier: 2 ** expectedExposureEv,
      },
      {
        three_tone_mapping_exposure_multiplier:
          runtime.color_management
            .tone_mapping_exposure_multiplier,
        approximate_equivalent_ev: actualExposureEv,
      },
      exposureMatches
        ? "The Web exposure multiplier is equivalent to the registered Blender exposure."
        : "Blender is locked to 0 EV (1.0 multiplier), while production Web uses toneMappingExposure 1.05.",
    ),
  );

  const alphaMatches =
    sceneContract.transparent_film === true &&
    runtime.webgl.context_attributes?.alpha === true &&
    runtime.color_management.clear_alpha === 0 &&
    runtime.color_management.scene_background === null;
  checks.push(
    makeCheck(
      "transparent_background",
      alphaMatches ? "pass" : "fail",
      {
        transparent_film: sceneContract.transparent_film,
        color_mode: sceneContract.color_mode,
      },
      {
        webgl_alpha:
          runtime.webgl.context_attributes?.alpha ?? null,
        clear_alpha:
          runtime.color_management.clear_alpha,
        scene_background:
          runtime.color_management.scene_background,
      },
      alphaMatches
        ? "The live Web renderer has an alpha-capable transparent background."
        : "The live Web renderer does not match the transparent-background requirement.",
    ),
  );

  const compositorMatches =
    sceneContract.compositor_effects === false &&
    runtime.color_management.direct_render_without_composer === true;
  checks.push(
    makeCheck(
      "compositor_effects",
      compositorMatches ? "pass" : "fail",
      {
        compositor_effects: sceneContract.compositor_effects,
      },
      {
        direct_render_without_composer:
          runtime.color_management
            .direct_render_without_composer,
      },
      compositorMatches
        ? "The review path is a direct render with no registered compositor effects."
        : "A direct, compositor-free Web render was not proven.",
    ),
  );

  const diagnosticsClean =
    diagnostics.page_errors.length === 0 &&
    diagnostics.console_errors.length === 0 &&
    diagnostics.http_errors.length === 0 &&
    diagnostics.request_failures.length === 0;
  checks.push(
    makeCheck(
      "browser_diagnostics",
      diagnosticsClean ? "pass" : "fail",
      {
        page_errors: 0,
        console_errors: 0,
        http_errors: 0,
        request_failures: 0,
      },
      {
        page_errors: diagnostics.page_errors.length,
        console_errors: diagnostics.console_errors.length,
        http_errors: diagnostics.http_errors.length,
        request_failures: diagnostics.request_failures.length,
      },
      diagnosticsClean
        ? "No unexpected browser, console, HTTP, or request failure was observed."
        : "Unexpected browser diagnostics make the preflight fail closed.",
    ),
  );

  return checks;
}

function buildThresholdStatus(contract, checks) {
  const thresholds =
    contract.comparison_contract?.thresholds || {};
  const blockedBy = checks
    .filter(
      (check) =>
        check.blocking &&
        (check.status === "fail" ||
          check.status === "blocked" ||
          check.status === "not_evaluated"),
    )
    .map((check) => check.id);
  return Object.entries(thresholds).map(([id, threshold]) => ({
    id,
    threshold,
    status: "not_evaluated",
    reason:
      "No Three.js beauty or alpha mask was captured because contract preflight failed.",
    blocked_by: blockedBy,
  }));
}

function summarizeChecks(checks) {
  const summary = {
    total: checks.length,
    pass: 0,
    fail: 0,
    blocked: 0,
    not_evaluated: 0,
  };
  for (const check of checks) {
    if (Object.hasOwn(summary, check.status)) {
      summary[check.status] += 1;
    }
  }
  return summary;
}

function blockingCheckIds(checks) {
  return checks
    .filter(
      (check) =>
        check.blocking &&
        check.status !== "pass",
    )
    .map((check) => check.id);
}

function buildBlockedManifest({
  contract,
  generatedAt,
  inputLocks,
  postflightInputLocks,
  preflight,
  runtime,
  command,
  executionError = null,
}) {
  return {
    schema_version: "bf3d.r2r.three_capture_manifest.v1",
    requirement_id: contract?.requirement_id || null,
    stage_id: contract?.stage_id || "WEB-60_R2R",
    renderer: "Three.js production structural review",
    generated_at: generatedAt,
    status:
      preflight?.status ||
      (executionError
        ? "blocked_preflight_error"
        : "blocked_contract_mismatch"),
    exit_code: executionError ? 1 : CONTRACT_MISMATCH_EXIT_CODE,
    command,
    evidence_class: contract?.evidence_class || "E/illustrative",
    reference_status: contract?.reference_status || "REF-PENDING",
    not_for_construction: contract?.not_for_construction !== false,
    approval_granted: contract?.approval_granted === true,
    source_mutation_forbidden:
      contract?.source_mutation_forbidden !== false,
    source_files_mutated: false,
    capture_eligible: false,
    capture_attempted: false,
    beauty_capture_count: 0,
    alpha_mask_capture_count: 0,
    beauty_and_alpha_mask_required:
      contract?.capture_contract
        ?.beauty_and_alpha_mask_required === true,
    beauty_and_alpha_mask_emitted: false,
    ab_pass_claimed: false,
    comparison_status: "not_evaluated",
    prohibited_claims: [
      "No Blender/Three renderer numeric A/B PASS.",
      "No beauty image exists for this Three.js run.",
      "No alpha mask exists for this Three.js run.",
      "No pixel threshold was evaluated.",
    ],
    artifacts: {
      preflight_report:
        "reports/three_contract_preflight.json",
      capture_manifest:
        "reports/three_capture_manifest.json",
      renders_directory: null,
      beauty_images: [],
      alpha_masks: [],
      numeric_comparisons: [],
    },
    controlled_input_locks: inputLocks,
    postflight_input_locks: postflightInputLocks,
    runtime_identity: runtime
      ? {
          browser: runtime.browser,
          three: runtime.three,
          webgl: runtime.webgl,
          canvas: runtime.canvas,
        }
      : null,
    blocking_checks:
      preflight?.blocking_checks || [],
    execution_error: executionError,
  };
}

async function collectLivePreflight(contract) {
  const server = await startStaticServer();
  const port = server.address().port;
  const baseUrl =
    `http://127.0.0.1:${port}/frontend_dashboard_v3.server.html`;
  let browser = null;
  let context = null;
  let page = null;
  try {
    browser = await playwright.chromium.launch({ headless: true });
    context = await browser.newContext({
      viewport: VIEWPORT,
      deviceScaleFactor: DEVICE_SCALE_FACTOR,
    });
    page = await context.newPage();
    const diagnostics = attachDiagnostics(page);
    await page.goto(`${baseUrl}?ws_port=8767#overview`, {
      waitUntil: "domcontentloaded",
      timeout: 90_000,
    });
    await waitForProductionController(page);
    await enterStructuralReview(page);
    const captureHarness = await fixCaptureCanvas(page);
    await waitForTwoAnimationFrames(page);
    const runtime = await inspectRuntime(page, {
      engine: browser.browserType().name(),
      browserVersion: browser.version(),
    });
    const checks = buildChecks(
      contract,
      inspectInputLocks(contract),
      runtime,
      diagnostics,
    );
    return {
      baseUrl,
      diagnostics,
      captureHarness,
      runtime,
      checks,
    };
  } finally {
    await page?.close().catch(() => {});
    await context?.close().catch(() => {});
    await browser?.close().catch(() => {});
    await new Promise((resolve) => server.close(resolve));
  }
}

function writeExecutionErrorReports({
  contract,
  generatedAt,
  command,
  inputLocks,
  error,
}) {
  const errorDetail = {
    name: error?.name || "Error",
    message: String(error?.message || error),
    stack: String(error?.stack || error),
  };
  const postflightInputLocks = contract
    ? inspectInputLocks(contract)
    : [];
  const preflight = {
    schema_version: "bf3d.r2r.three_contract_preflight.v1",
    requirement_id: contract?.requirement_id || null,
    stage_id: contract?.stage_id || "WEB-60_R2R",
    generated_at: generatedAt,
    status: "blocked_preflight_error",
    exit_code: 1,
    command,
    capture_eligible: false,
    capture_attempted: false,
    beauty_and_alpha_mask_emitted: false,
    ab_pass_claimed: false,
    input_contract: relativeToRoot(CONTRACT_PATH),
    input_contract_sha256: fs.existsSync(CONTRACT_PATH)
      ? sha256(CONTRACT_PATH)
      : null,
    input_locks: inputLocks,
    postflight_input_locks: postflightInputLocks,
    checks: [],
    check_summary: {
      total: 0,
      pass: 0,
      fail: 0,
      blocked: 0,
      not_evaluated: 0,
    },
    blocking_checks: ["preflight_execution_error"],
    thresholds: [],
    runtime: null,
    diagnostics: null,
    execution_error: errorDetail,
  };
  const manifest = buildBlockedManifest({
    contract,
    generatedAt,
    inputLocks,
    postflightInputLocks,
    preflight,
    runtime: null,
    command,
    executionError: errorDetail,
  });
  writeJson(PREFLIGHT_PATH, preflight);
  writeJson(MANIFEST_PATH, manifest);
}

async function main() {
  const command = "node tools/capture_bf3d_r2q_ab_three.cjs";
  const generatedAt = timestamp();
  let contract = null;
  let inputLocks = [];
  try {
    if (!fs.existsSync(CONTRACT_PATH)) {
      throw new Error(
        `capture contract is missing: ${CONTRACT_PATH}`,
      );
    }
    contract = readJson(CONTRACT_PATH);
    if (
      contract.schema_version !==
      "bf3d.r2r.capture_contract.v1"
    ) {
      throw new Error(
        `unsupported capture contract schema: ${contract.schema_version}`,
      );
    }
    inputLocks = inspectInputLocks(contract);
    if (!requiredLocksPassed(inputLocks)) {
      const failed = inputLocks
        .filter((item) => item.required && !item.passed)
        .map((item) => item.id);
      throw new Error(
        `required input lock mismatch: ${failed.join(", ")}`,
      );
    }
    if (!fs.existsSync(PRODUCTION_HTML_PATH)) {
      throw new Error(
        `production HTML is missing: ${PRODUCTION_HTML_PATH}`,
      );
    }

    const live = await collectLivePreflight(contract);
    const postflightInputLocks = inspectInputLocks(contract);
    const postflightLocksPassed = requiredLocksPassed(
      postflightInputLocks,
    );
    if (!postflightLocksPassed) {
      live.checks.unshift(
        makeCheck(
          "postflight_source_integrity",
          "fail",
          {
            required_locks_unchanged: true,
          },
          {
            failed: postflightInputLocks
              .filter((item) => item.required && !item.passed)
              .map((item) => item.id),
          },
          "A locked source changed while the preflight was running.",
        ),
      );
    } else {
      live.checks.unshift(
        makeCheck(
          "postflight_source_integrity",
          "pass",
          {
            required_locks_unchanged: true,
          },
          {
            required_locks:
              postflightInputLocks.filter(
                (item) => item.required,
              ).length,
            passed:
              postflightInputLocks.filter(
                (item) => item.required && item.passed,
              ).length,
          },
          "All locked sources still match after the browser preflight.",
        ),
      );
    }

    const blockingChecks = blockingCheckIds(live.checks);
    const status =
      blockingChecks.length > 0
        ? "blocked_contract_mismatch"
        : "eligible_for_capture";
    const exitCode =
      status === "blocked_contract_mismatch"
        ? CONTRACT_MISMATCH_EXIT_CODE
        : 0;
    const thresholds = buildThresholdStatus(
      contract,
      live.checks,
    );
    const preflight = {
      schema_version:
        "bf3d.r2r.three_contract_preflight.v1",
      requirement_id: contract.requirement_id,
      stage_id: contract.stage_id,
      generated_at: generatedAt,
      status,
      exit_code: exitCode,
      command,
      evidence_class: contract.evidence_class,
      reference_status: contract.reference_status,
      not_for_construction: contract.not_for_construction,
      approval_granted: contract.approval_granted,
      source_mutation_forbidden:
        contract.source_mutation_forbidden,
      source_files_mutated: false,
      capture_eligible: status === "eligible_for_capture",
      capture_attempted: false,
      beauty_and_alpha_mask_emitted: false,
      ab_pass_claimed: false,
      fail_closed_policy:
        contract.comparison_contract
          ?.missing_or_invalid_input_policy,
      not_evaluated_policy:
        contract.comparison_contract
          ?.not_evaluated_policy,
      input_contract: relativeToRoot(CONTRACT_PATH),
      input_contract_sha256: sha256(CONTRACT_PATH),
      script: {
        path: relativeToRoot(__filename),
        sha256: sha256(__filename),
      },
      production_runtime_page: {
        path: relativeToRoot(PRODUCTION_HTML_PATH),
        bytes: fs.statSync(PRODUCTION_HTML_PATH).size,
        sha256: sha256(PRODUCTION_HTML_PATH),
        served_url: live.runtime.page.url,
      },
      input_locks: inputLocks,
      postflight_input_locks: postflightInputLocks,
      capture_harness: live.captureHarness,
      runtime: live.runtime,
      diagnostics: live.diagnostics,
      checks: live.checks,
      check_summary: summarizeChecks(live.checks),
      blocking_checks: blockingChecks,
      thresholds,
      decision:
        status === "blocked_contract_mismatch"
          ? {
              action: "stop_before_capture",
              reason:
                "The live production Three.js camera, light rig, and color pipeline do not match the pre-registered Blender renderer contract.",
              beauty_capture_forbidden: true,
              alpha_mask_capture_forbidden: true,
              numeric_ab_pass_forbidden: true,
              production_mutation_forbidden: true,
            }
          : {
              action:
                "preflight_only_complete_capture_in_a_separate_authorized_step",
              reason:
                "This program is a preflight and does not emit capture evidence.",
              beauty_capture_forbidden: false,
              alpha_mask_capture_forbidden: false,
              numeric_ab_pass_forbidden: true,
              production_mutation_forbidden: true,
            },
    };
    const manifest = buildBlockedManifest({
      contract,
      generatedAt,
      inputLocks,
      postflightInputLocks,
      preflight,
      runtime: live.runtime,
      command,
    });
    if (status === "eligible_for_capture") {
      manifest.status = "eligible_for_capture";
      manifest.exit_code = 0;
    }
    writeJson(PREFLIGHT_PATH, preflight);
    writeJson(MANIFEST_PATH, manifest);

    const summary = {
      status,
      exit_code: exitCode,
      capture_attempted: false,
      beauty_and_alpha_mask_emitted: false,
      ab_pass_claimed: false,
      blocking_checks: blockingChecks,
      reports: [
        relativeToRoot(PREFLIGHT_PATH),
        relativeToRoot(MANIFEST_PATH),
      ],
    };
    process.stdout.write(`${JSON.stringify(summary, null, 2)}\n`);
    process.exitCode = exitCode;
  } catch (error) {
    writeExecutionErrorReports({
      contract,
      generatedAt,
      command,
      inputLocks,
      error,
    });
    process.stderr.write(`${error?.stack || error}\n`);
    process.exitCode = 1;
  }
}

main();
