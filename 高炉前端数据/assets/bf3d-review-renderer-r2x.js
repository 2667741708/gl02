import * as THREE from "three";
import { OrbitControls } from "three/addons/controls/OrbitControls.js";
import { GLTFLoader } from "three/addons/loaders/GLTFLoader.js";
import { RectAreaLightUniformsLib } from "three/addons/lights/RectAreaLightUniformsLib.js";

const REQUIREMENT_ID =
  "REQ-BF3D-R2X-R2J-AO-REBAKE-CONSUMPTION-20260720";
const MODEL_URL =
  "r2x/gl02_blast_furnace_material_review.r2x-ao-smoke1k.v5payload.glb";
const EXPECTED_MODEL_SHA256 =
  "bd074c23c237fe7ff3abac0f823bd9aef978021e4e829963b3f979e9b58f1c00";
const EXPECTED_MODEL_BYTES = 1_115_216;
const EXPECTED_SHELL_COUNT = 5;
const EXPECTED_MATERIAL_NAMES = Object.freeze([
  "INT30_R2G_R1_LOCK_BAKED_PBR_STEEL",
  "INT30_R2G_R1_LOCK_BAKED_PBR_STEEL.001",
]);
const EXPECTED_MATERIAL_COUNT = EXPECTED_MATERIAL_NAMES.length;
const FIXED_EXPOSURE = 1.0;
const ENVIRONMENT_LINEAR_RADIANCE = Object.freeze([0.0864, 0.0864, 0.0864]);
const TARGET_NAMES = Object.freeze([
  "R2J_ASM_GL02_FURNACE_BELLY_SHELL_55MM_E",
  "R2J_ASM_GL02_FURNACE_BOSH_SHELL_55MM_E",
  "R2J_ASM_GL02_FURNACE_HEARTH_SHELL_65MM_E",
  "R2J_ASM_GL02_FURNACE_SHAFT_SHELL_45MM_E",
  "R2J_ASM_GL02_FURNACE_THROAT_SHELL_45MM_E",
]);
const CAMERA_COMPOSITION = Object.freeze({
  materialExteriorDirection: Object.freeze([0.78, 0.18, 0.62]),
  materialExteriorDetailDirection: Object.freeze([0.78, 0.18, 0.62]),
  exteriorGlobalHeightTarget: 0.86,
  exteriorGlobalHeightMinimum: 0.8,
  exteriorGlobalHeightMaximum: 0.93,
  exteriorDetailZone: "BELLY",
  exteriorDetailWidthTarget: 0.74,
  exteriorDetailWidthMinimum: 0.6,
  exteriorDetailHeightMinimum: 0.25,
  exteriorDetailCenterOffsetMaximum: 0.15,
  projectionFitIterations: 10,
});
const FORBIDDEN_OBJECT_NAME =
  /(^|[_\-\s])(SENSOR|HIT|LINE|LINES|LINESEGMENTS|POINT|POINTS|SPRITE|OUTLINE|HIGHLIGHT|PARTICLE|PARTICLES|LEADER|CALLOUT|RING)([_\-\s]|$)/i;
const P40_DIRECTIONAL_LIGHTS = Object.freeze([
  Object.freeze({
    name: "P40_NEUTRAL_KEY",
    position: Object.freeze([
      46.1323356628418,
      49.166168212890625,
      46.1323356628418,
    ]),
    direction: Object.freeze([
      -0.577350378036499,
      -0.5773500204086304,
      -0.5773506164550781,
    ]),
    color: Object.freeze([1.0, 1.0, 1.0]),
    intensity: 2.25,
  }),
  Object.freeze({
    name: "P40_NEUTRAL_FILL",
    position: Object.freeze([
      -46.1323356628418,
      19.18014907836914,
      11.53308391571045,
    ]),
    direction: Object.freeze([
      0.9186304807662964,
      -0.32152092456817627,
      -0.22965724766254425,
    ]),
    color: Object.freeze([0.9599999785423279, 0.9800000190734863, 1.0]),
    intensity: 1.0499999523162842,
  }),
  Object.freeze({
    name: "P40_NEUTRAL_RIM",
    position: Object.freeze([
      11.53308391571045,
      49.166168212890625,
      -46.1323356628418,
    ]),
    direction: Object.freeze([
      -0.1740776151418686,
      -0.6963106393814087,
      0.6963106989860535,
    ]),
    color: Object.freeze([0.8999999761581421, 0.949999988079071, 1.0]),
    intensity: 1.350000023841858,
  }),
]);
const P40_TOP_AREA = Object.freeze({
  name: "P40_NEUTRAL_TOP",
  position: Object.freeze([0.0, 60.69925308227539, 0.0]),
  emissionDirection: Object.freeze([0.0, -1.0, 0.0]),
  color: Object.freeze([1.0, 1.0, 1.0]),
  sourceDiskDiameterMeters: 34.59925079345703,
  squareWidthMeters: 30.6627876536543,
  squareHeightMeters: 30.6627876536543,
  sourcePowerWatts: 3921.24853515625,
  intensityAtK1: 1.3275510357953,
});

let rectAreaUniformsInitialized = false;
let rectAreaUniformsEffectiveInitCalls = 0;

class R2XContractError extends Error {
  constructor(message) {
    super(message);
    this.name = "R2XContractError";
    this.code = "BF3D_R2X_CONTRACT";
  }
}

function initRectAreaLightUniformsOnce() {
  if (rectAreaUniformsInitialized) return;
  RectAreaLightUniformsLib.init();
  rectAreaUniformsInitialized = true;
  rectAreaUniformsEffectiveInitCalls += 1;
}

function normalizeName(value) {
  return String(value || "").trim().toUpperCase();
}

function colorFromLinear(values) {
  return new THREE.Color().setRGB(
    Number(values[0]),
    Number(values[1]),
    Number(values[2]),
    THREE.LinearSRGBColorSpace,
  );
}

function materialList(object) {
  if (!object?.material) return [];
  return Array.isArray(object.material) ? object.material : [object.material];
}

function collectOwnedResources(root) {
  const resources = {
    geometries: new Set(),
    materials: new Set(),
    textures: new Set(),
  };
  root?.traverse?.((object) => {
    if (object.geometry) resources.geometries.add(object.geometry);
    for (const material of materialList(object)) {
      resources.materials.add(material);
      for (const key of [
        "map",
        "aoMap",
        "roughnessMap",
        "metalnessMap",
        "normalMap",
        "emissiveMap",
        "alphaMap",
        "bumpMap",
        "displacementMap",
        "lightMap",
        "envMap",
      ]) {
        if (material?.[key]?.isTexture) resources.textures.add(material[key]);
      }
    }
  });
  return resources;
}

function resourceCounts(resources) {
  return {
    geometries: resources?.geometries?.size || 0,
    materials: resources?.materials?.size || 0,
    textures: resources?.textures?.size || 0,
  };
}

function disposeOwnedResources(root, resources) {
  root?.removeFromParent?.();
  for (const texture of resources?.textures || []) texture.dispose?.();
  for (const material of resources?.materials || []) material.dispose?.();
  for (const geometry of resources?.geometries || []) geometry.dispose?.();
}

function hexFromArrayBuffer(buffer) {
  return Array.from(new Uint8Array(buffer), (value) =>
    value.toString(16).padStart(2, "0"),
  ).join("");
}

async function sha256ArrayBuffer(buffer) {
  if (!globalThis.crypto?.subtle) {
    throw new R2XContractError("浏览器不支持 Web Crypto SHA-256");
  }
  const digest = await globalThis.crypto.subtle.digest("SHA-256", buffer);
  return hexFromArrayBuffer(digest);
}

async function fetchArrayBufferWithProgress(url, onProgress) {
  const response = await fetch(url, {
    cache: "no-store",
    credentials: "same-origin",
    redirect: "error",
  });
  if (!response.ok) {
    throw new R2XContractError(`候选资产请求失败：HTTP ${response.status}`);
  }
  const expectedLength = Number(response.headers.get("content-length") || 0);
  const payload = await response.arrayBuffer();
  if (expectedLength > 0 && payload.byteLength !== expectedLength) {
    throw new R2XContractError(
      `候选资产响应不完整：${payload.byteLength}/${expectedLength}`,
    );
  }
  onProgress?.(payload.byteLength, expectedLength || payload.byteLength);
  return payload;
}

function bufferAttributeFinite(attribute) {
  if (!attribute?.array || attribute.count <= 0) return false;
  for (const value of attribute.array) {
    if (!Number.isFinite(value)) return false;
  }
  return true;
}

function textureContract(texture) {
  return texture
    ? {
        uuid: texture.uuid,
        name: texture.name || "",
        channel: Number(texture.channel),
        colorSpace: texture.colorSpace || "",
      }
    : null;
}

function materialSnapshot(material) {
  return {
    uuid: material.uuid,
    name: material.name,
    type: material.type,
    color: material.color?.toArray?.() || null,
    emissive: material.emissive?.toArray?.() || null,
    roughness: material.roughness,
    metalness: material.metalness,
    normalScale: material.normalScale?.toArray?.() || null,
    opacity: material.opacity,
    transparent: material.transparent,
    alphaTest: material.alphaTest,
    side: material.side,
    map: textureContract(material.map),
    normalMap: textureContract(material.normalMap),
    roughnessMap: textureContract(material.roughnessMap),
    metalnessMap: textureContract(material.metalnessMap),
    aoMap: textureContract(material.aoMap),
    aoMapIntensity: material.aoMapIntensity,
  };
}

function nonAoSignature(snapshot) {
  const copy = structuredClone(snapshot);
  delete copy.aoMapIntensity;
  return JSON.stringify(copy);
}

function validateCandidate(gltf) {
  const root = gltf?.scene;
  if (!root?.isObject3D) {
    throw new R2XContractError("R2X 候选没有可用 glTF scene");
  }

  const meshes = [];
  const forbiddenObjects = [];
  const yellowOutlines = [];
  root.traverse((object) => {
    const name = normalizeName(object.name);
    const typeForbidden =
      object.isLine || object.isLineSegments || object.isPoints || object.isSprite;
    if (typeForbidden || FORBIDDEN_OBJECT_NAME.test(name)) {
      forbiddenObjects.push({ name: object.name || "", type: object.type });
    }
    if (object.isLine || object.isLineSegments) {
      for (const material of materialList(object)) {
        const color = material?.color;
        if (color && color.r > 0.65 && color.g > 0.5 && color.b < 0.25) {
          yellowOutlines.push({
            object: object.name || "",
            material: material.name || "",
          });
        }
      }
    }
    if (object.isMesh) meshes.push(object);
  });

  if (forbiddenObjects.length || yellowOutlines.length) {
    throw new R2XContractError(
      `候选含禁止对象：forbidden=${forbiddenObjects.length}, yellow=${yellowOutlines.length}`,
    );
  }
  if (meshes.length !== EXPECTED_SHELL_COUNT) {
    throw new R2XContractError(
      `五壳数量不匹配：${meshes.length}/${EXPECTED_SHELL_COUNT}`,
    );
  }

  const names = meshes.map((mesh) => normalizeName(mesh.name)).sort();
  const expectedNames = TARGET_NAMES.map(normalizeName).sort();
  if (JSON.stringify(names) !== JSON.stringify(expectedNames)) {
    throw new R2XContractError(
      `五壳对象身份不匹配：${JSON.stringify(names)}`,
    );
  }

  const entries = [];
  const materialSet = new Set();
  for (const mesh of meshes) {
    const materials = materialList(mesh);
    if (materials.length !== 1) {
      throw new R2XContractError(
        `${mesh.name} material 数量=${materials.length}，期望 1`,
      );
    }
    const material = materials[0];
    if (!material?.isMeshStandardMaterial) {
      throw new R2XContractError(
        `${mesh.name} 不是 MeshStandardMaterial：${material?.type}`,
      );
    }
    const uv2 = mesh.geometry?.getAttribute?.("uv2");
    const channels = {
      map: Number(material.map?.channel),
      normalMap: Number(material.normalMap?.channel),
      roughnessMap: Number(material.roughnessMap?.channel),
      metalnessMap: Number(material.metalnessMap?.channel),
      aoMap: Number(material.aoMap?.channel),
    };
    const checks = {
      aoMapPresent: Boolean(material.aoMap?.isTexture),
      aoMapChannel2: channels.aoMap === 2,
      uv2Present: Boolean(uv2),
      uv2Finite: bufferAttributeFinite(uv2),
      mapPresentChannel0: Boolean(material.map?.isTexture) && channels.map === 0,
      normalMapPresentChannel0:
        Boolean(material.normalMap?.isTexture) && channels.normalMap === 0,
      roughnessMapPresentChannel0:
        Boolean(material.roughnessMap?.isTexture) &&
        channels.roughnessMap === 0,
      metalnessMapPresentChannel0:
        Boolean(material.metalnessMap?.isTexture) &&
        channels.metalnessMap === 0,
      importedAoIntensityIsOne: material.aoMapIntensity === 1,
    };
    if (!Object.values(checks).every(Boolean)) {
      throw new R2XContractError(
        `${mesh.name} AO/PBR 运行合同失败：${JSON.stringify(checks)}`,
      );
    }
    const snapshot = materialSnapshot(material);
    entries.push({
      mesh,
      material,
      uv2,
      importedAoIntensity: material.aoMapIntensity,
      importedSnapshot: snapshot,
      importedNonAoSignature: nonAoSignature(snapshot),
      checks,
      channels,
    });
    materialSet.add(material);
  }
  const importedMaterialNames = [...materialSet]
    .map((material) => material.name)
    .sort();
  const expectedMaterialNames = [...EXPECTED_MATERIAL_NAMES].sort();
  if (
    materialSet.size !== EXPECTED_MATERIAL_COUNT ||
    JSON.stringify(importedMaterialNames) !==
      JSON.stringify(expectedMaterialNames)
  ) {
    throw new R2XContractError(
      `候选共享材质基线不匹配：count=${materialSet.size}/${EXPECTED_MATERIAL_COUNT}, names=${JSON.stringify(importedMaterialNames)}`,
    );
  }

  return {
    root,
    meshes,
    entries,
    materials: [...materialSet],
    forbiddenObjects,
    yellowOutlines,
  };
}

/**
 * R2X 1K AO v5payload 隔离审查渲染器。
 *
 * 对应需求：REQ-BF3D-R2X-R2J-AO-REBAKE-CONSUMPTION-20260720
 * 输入：唯一 SHA 锁定的五壳 v5payload GLB。
 * 输出：同机位 global/detail 的 AO off/on 只读审查。
 * 异常：SHA、五壳、uv2、texture channel 或 AO-only 变更失败即关闭。
 */
class BF3DR2XReviewRenderer {
  constructor(viewport) {
    if (!viewport) throw new R2XContractError("缺少 R2X 审查视口");
    this.viewport = viewport;
    this.disposed = false;
    this.loadPromise = null;
    this.loadState = "loading";
    this.view = "global";
    this.aoEnabled = false;
    this.asset = null;
    this.assetResources = null;
    this.assetSha256 = null;
    this.assetShaVerified = false;
    this.assetRequestCount = 0;
    this.loadAttemptCount = 0;
    this.frameCount = 0;
    this.resizeCount = 0;
    this.lastError = null;
    this.projectionAudit = null;
    this.cameraDirection = [0, 0, 1];
    this.cameraDistanceScale = 1;
    this.rafId = 0;
    this.resizeObserverDisconnected = false;
    this.controlsDisposed = false;
    this.rendererDisposed = false;
    this.rafCancelled = false;
    this.environmentSourceDisposed = false;
    this.environmentTargetDisposed = false;
    this.disposedResourceCounts = {
      geometries: 0,
      materials: 0,
      textures: 0,
    };

    this.canvas = document.createElement("canvas");
    this.canvas.id = "bf3d-review-canvas";
    this.canvas.setAttribute("role", "img");
    this.canvas.setAttribute(
      "aria-label",
      "GL02 高炉 R2X 1K AO 同机位只读视图",
    );
    this.viewport.prepend(this.canvas);

    this.scene = new THREE.Scene();
    this.scene.name = "BF3D_R2X_ISOLATED_REVIEW_SCENE";
    this.scene.background = colorFromLinear([0.033, 0.039, 0.041]);

    this.camera = new THREE.PerspectiveCamera(38, 1, 0.05, 1000);
    this.camera.name = "BF3D_R2X_ISOLATED_REVIEW_CAMERA";
    this.camera.up.set(0, 1, 0);

    this.renderer = new THREE.WebGLRenderer({
      canvas: this.canvas,
      antialias: true,
      alpha: false,
      powerPreference: "high-performance",
      preserveDrawingBuffer: false,
    });
    this.renderer.setPixelRatio(Math.min(globalThis.devicePixelRatio || 1, 2));
    this.renderer.outputColorSpace = THREE.SRGBColorSpace;
    this.renderer.toneMapping = THREE.ACESFilmicToneMapping;
    this.renderer.toneMappingExposure = FIXED_EXPOSURE;
    this.renderer.shadowMap.enabled = false;
    this.renderer.localClippingEnabled = false;
    if ("useLegacyLights" in this.renderer) this.renderer.useLegacyLights = false;

    this.controls = new OrbitControls(this.camera, this.canvas);
    this.controls.enableDamping = true;
    this.controls.dampingFactor = 0.075;
    this.controls.screenSpacePanning = true;
    this.controls.minPolarAngle = 0.08;
    this.controls.maxPolarAngle = Math.PI - 0.08;

    initRectAreaLightUniformsOnce();
    this.lightRig = this.createP40CandidateLights();
    this.scene.add(this.lightRig);
    this.createFixedLinearEnvironment();

    this.resizeObserver = new ResizeObserver(() => this.resize());
    this.resizeObserver.observe(this.viewport);
    this.resize();
    this.raf = () => {
      if (this.disposed) return;
      try {
        this.controls.update();
        this.renderer.render(this.scene, this.camera);
        this.frameCount += 1;
        this.rafId = requestAnimationFrame(this.raf);
      } catch (error) {
        this.lastError = String(error?.message || error);
        this.setLoadState("error", `渲染失败：${this.lastError}`);
      }
    };
    this.rafId = requestAnimationFrame(this.raf);
  }

  createP40CandidateLights() {
    const group = new THREE.Group();
    group.name = "BF3D_P40_CANDIDATE_LIGHT_RIG";
    for (const entry of P40_DIRECTIONAL_LIGHTS) {
      const light = new THREE.DirectionalLight(
        colorFromLinear(entry.color),
        entry.intensity,
      );
      light.name = entry.name;
      light.position.fromArray(entry.position);
      light.castShadow = false;
      const target = new THREE.Object3D();
      target.name = `${entry.name}_FIXED_TARGET`;
      target.position
        .fromArray(entry.position)
        .add(new THREE.Vector3().fromArray(entry.direction));
      light.target = target;
      group.add(target, light);
    }
    const top = new THREE.RectAreaLight(
      colorFromLinear(P40_TOP_AREA.color),
      P40_TOP_AREA.intensityAtK1,
      P40_TOP_AREA.squareWidthMeters,
      P40_TOP_AREA.squareHeightMeters,
    );
    top.name = P40_TOP_AREA.name;
    top.position.fromArray(P40_TOP_AREA.position);
    top.lookAt(
      new THREE.Vector3()
        .fromArray(P40_TOP_AREA.position)
        .add(new THREE.Vector3().fromArray(P40_TOP_AREA.emissionDirection)),
    );
    top.power = P40_TOP_AREA.sourcePowerWatts;
    group.add(top);
    return group;
  }

  createFixedLinearEnvironment() {
    const width = 16;
    const height = 8;
    const data = new Float32Array(width * height * 4);
    for (let index = 0; index < width * height; index += 1) {
      const offset = index * 4;
      data[offset] = ENVIRONMENT_LINEAR_RADIANCE[0];
      data[offset + 1] = ENVIRONMENT_LINEAR_RADIANCE[1];
      data[offset + 2] = ENVIRONMENT_LINEAR_RADIANCE[2];
      data[offset + 3] = 1;
    }
    const source = new THREE.DataTexture(
      data,
      width,
      height,
      THREE.RGBAFormat,
      THREE.FloatType,
    );
    source.name = "BF3D_FIXED_LINEAR_ENV_SOURCE";
    source.colorSpace = THREE.LinearSRGBColorSpace;
    source.mapping = THREE.EquirectangularReflectionMapping;
    source.minFilter = THREE.LinearFilter;
    source.magFilter = THREE.LinearFilter;
    source.generateMipmaps = false;
    source.needsUpdate = true;
    const pmrem = new THREE.PMREMGenerator(this.renderer);
    pmrem.compileEquirectangularShader();
    this.environmentTarget = pmrem.fromEquirectangular(source);
    this.environmentTarget.texture.name = "BF3D_FIXED_LINEAR_ENV_PMREM";
    this.scene.environment = this.environmentTarget.texture;
    source.dispose();
    pmrem.dispose();
    this.environmentSourceDisposed = true;
  }

  resize() {
    if (this.disposed) return;
    const rect = this.viewport.getBoundingClientRect();
    const width = Math.max(1, Math.floor(rect.width));
    const height = Math.max(1, Math.floor(rect.height));
    const pixelRatio = this.renderer.getPixelRatio();
    if (
      this.renderer.domElement.width === Math.floor(width * pixelRatio) &&
      this.renderer.domElement.height === Math.floor(height * pixelRatio)
    ) {
      return;
    }
    this.renderer.setSize(width, height, false);
    this.camera.aspect = width / height;
    this.camera.updateProjectionMatrix();
    this.resizeCount += 1;
  }

  updateProgress(received, total) {
    const progress = document.querySelector("#load-progress");
    if (!progress) return;
    const ratio = total > 0 ? Math.min(1, received / total) : 0;
    progress.value = Math.round(ratio * 100);
    progress.textContent = `${progress.value}%`;
  }

  setLoadState(kind, message) {
    this.loadState = kind;
    document.body.dataset.loadState = kind;
    const layer = document.querySelector("#review-state-layer");
    const title = document.querySelector("#state-title");
    const body = document.querySelector("#state-message");
    const retry = document.querySelector("#retry-button");
    const badge = document.querySelector("#load-state-badge");
    if (layer) {
      layer.dataset.kind = kind;
      layer.setAttribute("aria-busy", String(kind === "loading"));
      layer.hidden = kind === "ready";
    }
    if (title) {
      title.textContent =
        kind === "loading"
          ? "正在读取 R2X v5payload 候选"
          : kind === "empty"
            ? "候选资产为空"
            : kind === "error"
              ? "R2X 合同失败"
              : "R2X 候选已就绪";
    }
    if (body) body.textContent = message || "";
    if (retry) retry.hidden = !["error", "empty"].includes(kind);
    if (badge) {
      badge.className = `state-badge is-${kind}`;
      badge.textContent =
        kind === "ready" ? "就绪" : kind === "loading" ? "加载中" : "失败";
    }
  }

  parseGltf(buffer) {
    const loader = new GLTFLoader();
    return new Promise((resolve, reject) => {
      loader.parse(buffer, "", resolve, reject);
    });
  }

  async load() {
    if (this.disposed) throw new R2XContractError("渲染器已释放");
    if (this.loadPromise) return this.loadPromise;
    this.loadPromise = this.loadInternal().finally(() => {
      this.loadPromise = null;
    });
    return this.loadPromise;
  }

  async loadInternal() {
    this.loadAttemptCount += 1;
    this.lastError = null;
    this.setLoadState(
      "loading",
      `只加载 ${MODEL_URL}；完成后核验 SHA 与 AO 运行合同。`,
    );
    this.updateProgress(0, EXPECTED_MODEL_BYTES);
    let candidateGltf = null;
    let candidateResources = null;
    try {
      this.assetRequestCount += 1;
      const buffer = await fetchArrayBufferWithProgress(
        MODEL_URL,
        (received, total) => this.updateProgress(received, total),
      );
      if (buffer.byteLength !== EXPECTED_MODEL_BYTES) {
        throw new R2XContractError(
          `候选字节数不匹配：${buffer.byteLength}/${EXPECTED_MODEL_BYTES}`,
        );
      }
      this.assetSha256 = await sha256ArrayBuffer(buffer);
      this.assetShaVerified = this.assetSha256 === EXPECTED_MODEL_SHA256;
      if (!this.assetShaVerified) {
        throw new R2XContractError(
          `候选 SHA 不匹配：${this.assetSha256}`,
        );
      }
      candidateGltf = await this.parseGltf(buffer);
      candidateResources = collectOwnedResources(candidateGltf.scene);
      const contract = validateCandidate(candidateGltf);
      this.clearAsset();
      this.asset = contract;
      this.assetResources = candidateResources;
      this.scene.add(contract.root);
      contract.root.visible = true;
      this.setView("global");
      this.setAoEnabled(false);
      this.setLoadState(
        "ready",
        "R2X v5payload SHA、五壳、uv2 与 texture channel 已核验。",
      );
      this.renderContractStatus();
      return this.getState();
    } catch (error) {
      if (candidateGltf?.scene && candidateGltf.scene !== this.asset?.root) {
        disposeOwnedResources(candidateGltf.scene, candidateResources);
      }
      this.lastError = String(error?.message || error);
      this.setLoadState("error", this.lastError);
      this.renderContractStatus();
      throw error;
    }
  }

  clearAsset() {
    if (!this.asset?.root) return;
    disposeOwnedResources(this.asset.root, this.assetResources);
    this.asset = null;
    this.assetResources = null;
  }

  setView(view) {
    if (!["global", "detail"].includes(view)) {
      throw new R2XContractError(`未知 R2X 视角：${view}`);
    }
    this.view = view;
    document.body.dataset.reviewView = view;
    for (const button of document.querySelectorAll("[data-view-button]")) {
      const active = button.dataset.viewButton === view;
      button.classList.toggle("is-active", active);
      button.setAttribute("aria-pressed", String(active));
    }
    if (this.asset) this.resetCamera();
    this.renderViewDescription();
    return this.getState();
  }

  setAoEnabled(enabled) {
    const value = enabled === true || enabled === "on";
    if (!this.asset) {
      this.aoEnabled = value;
      return this.getState();
    }
    for (const entry of this.asset.entries) {
      entry.material.aoMapIntensity = value ? entry.importedAoIntensity : 0;
    }
    this.aoEnabled = value;
    document.body.dataset.aoState = value ? "on" : "off";
    for (const button of document.querySelectorAll("[data-ao-button]")) {
      const active = button.dataset.aoButton === (value ? "on" : "off");
      button.classList.toggle("is-active", active);
      button.setAttribute("aria-pressed", String(active));
    }
    this.renderViewDescription();
    this.renderContractStatus();
    this.renderOnce();
    return this.getState();
  }

  renderViewDescription() {
    const description = document.querySelector("#active-view-description");
    if (!description) return;
    const viewLabel =
      this.view === "detail" ? "炉腰材质近景" : "外表面全景";
    const aoLabel = this.aoEnabled
      ? "AO On；恢复候选导入值 1"
      : "AO Off；只把五壳 aoMapIntensity 设为 0";
    description.textContent = `${viewLabel} · ${aoLabel}；相机、PBR 与 P40 色彩路径保持。`;
  }

  findBelly() {
    const target = this.asset?.meshes.find((mesh) =>
      normalizeName(mesh.name).includes("_BELLY_"),
    );
    if (!target) throw new R2XContractError("未找到 BELLY 外壳");
    return target;
  }

  resetCamera() {
    if (!this.asset) return this.getState();
    if (this.view === "detail") this.frameExteriorDetail();
    else this.frameGlobal();
    this.renderOnce();
    return this.getState();
  }

  frameGlobal() {
    const box = new THREE.Box3().setFromObject(this.asset.root);
    if (box.isEmpty()) throw new R2XContractError("五壳全景包围盒为空");
    const center = box.getCenter(new THREE.Vector3());
    const sphere = box.getBoundingSphere(new THREE.Sphere());
    const direction = new THREE.Vector3(
      ...CAMERA_COMPOSITION.materialExteriorDirection,
    ).normalize();
    const halfFov = THREE.MathUtils.degToRad(this.camera.fov * 0.5);
    const distance = Math.max(
      sphere.radius * 1.5,
      (sphere.radius / Math.max(Math.sin(halfFov), 0.2)) * 1.08,
    );
    this.positionCamera(center, direction, distance, sphere.radius);
    const fitted = this.fitProjectionFraction({
      object: this.asset.root,
      center,
      direction,
      initialDistance: distance,
      metric: "heightFraction",
      targetFraction: CAMERA_COMPOSITION.exteriorGlobalHeightTarget,
    });
    this.cameraDirection = direction.toArray();
    this.cameraDistanceScale = fitted.distance / distance;
    this.projectionAudit = {
      view: "global",
      target: "ALL_FIVE_R2J_SHELLS",
      metricMethod: "projected_mesh_vertices_ndc",
      cameraOnly: true,
      thresholds: {
        heightMinimum: CAMERA_COMPOSITION.exteriorGlobalHeightMinimum,
        heightMaximum: CAMERA_COMPOSITION.exteriorGlobalHeightMaximum,
      },
      metrics: fitted.metrics,
      passed:
        fitted.metrics.heightFraction >=
          CAMERA_COMPOSITION.exteriorGlobalHeightMinimum &&
        fitted.metrics.heightFraction <=
          CAMERA_COMPOSITION.exteriorGlobalHeightMaximum,
    };
  }

  frameExteriorDetail() {
    const targetObject = this.findBelly();
    const box = new THREE.Box3().setFromObject(targetObject);
    if (box.isEmpty()) throw new R2XContractError("BELLY 近景包围盒为空");
    const center = box.getCenter(new THREE.Vector3());
    const sphere = box.getBoundingSphere(new THREE.Sphere());
    const direction = new THREE.Vector3(
      ...CAMERA_COMPOSITION.materialExteriorDetailDirection,
    ).normalize();
    const halfFov = THREE.MathUtils.degToRad(this.camera.fov * 0.5);
    const initialDistance = Math.max(
      sphere.radius * 1.35,
      sphere.radius / Math.max(Math.sin(halfFov), 0.2),
    );
    const fitted = this.fitProjectionFraction({
      object: targetObject,
      center,
      direction,
      initialDistance,
      metric: "widthFraction",
      targetFraction: CAMERA_COMPOSITION.exteriorDetailWidthTarget,
    });
    this.cameraDirection = direction.toArray();
    this.cameraDistanceScale = fitted.distance / initialDistance;
    this.projectionAudit = {
      view: "detail",
      target: targetObject.name,
      metricMethod: "projected_mesh_vertices_ndc",
      cameraOnly: true,
      thresholds: {
        widthMinimum: CAMERA_COMPOSITION.exteriorDetailWidthMinimum,
        heightMinimum: CAMERA_COMPOSITION.exteriorDetailHeightMinimum,
        centerOffsetMaximum:
          CAMERA_COMPOSITION.exteriorDetailCenterOffsetMaximum,
      },
      metrics: fitted.metrics,
      passed:
        fitted.metrics.widthFraction >=
          CAMERA_COMPOSITION.exteriorDetailWidthMinimum &&
        fitted.metrics.heightFraction >=
          CAMERA_COMPOSITION.exteriorDetailHeightMinimum &&
        fitted.metrics.centerOffsetFraction <=
          CAMERA_COMPOSITION.exteriorDetailCenterOffsetMaximum,
    };
  }

  projectObjectToCanvas(object) {
    object.updateWorldMatrix(true, true);
    this.camera.updateMatrixWorld(true);
    const point = new THREE.Vector3();
    let minX = Number.POSITIVE_INFINITY;
    let maxX = Number.NEGATIVE_INFINITY;
    let minY = Number.POSITIVE_INFINITY;
    let maxY = Number.NEGATIVE_INFINITY;
    let projectedVertexCount = 0;
    object.traverse((candidate) => {
      if (!candidate.isMesh) return;
      const position = candidate.geometry?.getAttribute?.("position");
      if (!position) return;
      candidate.updateWorldMatrix(true, false);
      for (let index = 0; index < position.count; index += 1) {
        point
          .fromBufferAttribute(position, index)
          .applyMatrix4(candidate.matrixWorld)
          .project(this.camera);
        if (![point.x, point.y, point.z].every(Number.isFinite)) continue;
        minX = Math.min(minX, point.x);
        maxX = Math.max(maxX, point.x);
        minY = Math.min(minY, point.y);
        maxY = Math.max(maxY, point.y);
        projectedVertexCount += 1;
      }
    });
    if (!projectedVertexCount) {
      throw new R2XContractError("投影目标没有可用顶点");
    }
    const centerNdcX = (minX + maxX) * 0.5;
    const centerNdcY = (minY + maxY) * 0.5;
    return {
      widthFraction: (maxX - minX) * 0.5,
      heightFraction: (maxY - minY) * 0.5,
      centerOffsetXFraction: Math.abs(centerNdcX) * 0.5,
      centerOffsetYFraction: Math.abs(centerNdcY) * 0.5,
      centerOffsetFraction:
        Math.max(Math.abs(centerNdcX), Math.abs(centerNdcY)) * 0.5,
      ndcBounds: [minX, minY, maxX, maxY],
      projectedVertexCount,
    };
  }

  positionCamera(center, direction, distance, radius) {
    this.camera.position.copy(center).addScaledVector(direction, distance);
    this.camera.near = Math.max(0.05, distance - radius * 2.4);
    this.camera.far = Math.max(300, distance + radius * 4.8);
    this.camera.lookAt(center);
    this.camera.updateProjectionMatrix();
    this.camera.updateMatrixWorld(true);
    this.controls.target.copy(center);
    this.controls.minDistance = Math.max(0.2, radius * 0.12);
    this.controls.maxDistance = Math.max(120, distance * 5);
    this.controls.update();
  }

  fitProjectionFraction({
    object,
    center,
    direction,
    initialDistance,
    metric,
    targetFraction,
  }) {
    const sphere = new THREE.Box3()
      .setFromObject(object)
      .getBoundingSphere(new THREE.Sphere());
    let distance = Math.max(0.5, initialDistance);
    let metrics = null;
    for (
      let iteration = 0;
      iteration < CAMERA_COMPOSITION.projectionFitIterations;
      iteration += 1
    ) {
      this.positionCamera(center, direction, distance, sphere.radius);
      metrics = this.projectObjectToCanvas(object);
      const actual = Math.max(0.0001, metrics[metric]);
      const correction = THREE.MathUtils.clamp(
        actual / targetFraction,
        0.55,
        1.8,
      );
      distance *= correction;
    }
    this.positionCamera(center, direction, distance, sphere.radius);
    metrics = this.projectObjectToCanvas(object);
    return { distance, metrics };
  }

  nonAoMutationAudit() {
    if (!this.asset) {
      return { checked: false, mutationCount: 0, mutatedMaterials: [] };
    }
    const mutatedMaterials = [];
    for (const entry of this.asset.entries) {
      const current = materialSnapshot(entry.material);
      if (nonAoSignature(current) !== entry.importedNonAoSignature) {
        mutatedMaterials.push(entry.material.name);
      }
    }
    return {
      checked: true,
      mutationCount: mutatedMaterials.length,
      mutatedMaterials,
    };
  }

  aoStateAudit() {
    if (!this.asset) {
      return {
        checked: false,
        expectedIntensity: this.aoEnabled ? 1 : 0,
        matchingMaterialCount: 0,
        passed: false,
        materials: [],
      };
    }
    const expectedIntensity = this.aoEnabled ? 1 : 0;
    const materials = this.asset.entries.map((entry) => ({
      mesh: entry.mesh.name,
      material: entry.material.name,
      importedIntensity: entry.importedAoIntensity,
      currentIntensity: entry.material.aoMapIntensity,
      aoMapUuid: entry.material.aoMap?.uuid || null,
      aoMapChannel: Number(entry.material.aoMap?.channel),
      uv2Count: entry.uv2.count,
      uv2Finite: bufferAttributeFinite(entry.uv2),
      matchesExpected:
        entry.material.aoMapIntensity === expectedIntensity &&
        entry.importedAoIntensity === 1,
    }));
    const matchingMaterialCount = materials.filter(
      (entry) => entry.matchesExpected,
    ).length;
    return {
      checked: true,
      state: this.aoEnabled ? "on" : "off",
      expectedIntensity,
      matchingMaterialCount,
      passed: matchingMaterialCount === EXPECTED_SHELL_COUNT,
      materials,
    };
  }

  currentMaterialSnapshots() {
    return (this.asset?.entries || []).map((entry) => ({
      mesh: entry.mesh.name,
      ...materialSnapshot(entry.material),
    }));
  }

  renderOnce() {
    if (this.disposed || !this.renderer) return;
    this.controls.update();
    this.renderer.render(this.scene, this.camera);
    this.frameCount += 1;
  }

  renderContractStatus() {
    const sha = document.querySelector("#asset-sha");
    const assetContract = document.querySelector("#asset-contract");
    const aoContract = document.querySelector("#ao-contract");
    const shellCount = document.querySelector("#shell-count");
    const uv2Status = document.querySelector("#uv2-status");
    const aoState = document.querySelector("#ao-state-status");
    if (sha) {
      sha.textContent = this.assetShaVerified
        ? `${this.assetSha256.slice(0, 12)}…${this.assetSha256.slice(-8)}`
        : this.assetSha256 || "待核验";
      sha.title = this.assetSha256 || "";
    }
    if (assetContract) {
      assetContract.textContent = this.assetShaVerified
        ? "r2x v5payload · SHA 已核验"
        : "v5payload · 正在核验 SHA";
    }
    if (shellCount) {
      shellCount.textContent = this.asset
        ? `${this.asset.meshes.length} / ${this.asset.materials.length}`
        : "待读取";
    }
    const aoAudit = this.aoStateAudit();
    if (aoContract) {
      aoContract.textContent =
        this.asset && aoAudit.passed
          ? "5/5 uv2 · aoMap channel 2"
          : "uv2 / channel 2 · 待检查";
    }
    if (uv2Status) {
      uv2Status.textContent =
        this.asset && aoAudit.passed ? "5/5 · finite" : "未检查";
    }
    if (aoState) {
      aoState.textContent = this.aoEnabled
        ? "On · imported intensity 1"
        : "Off · intensity 0";
    }
    const mutation = this.nonAoMutationAudit();
    document.body.dataset.modelShaVerified = String(this.assetShaVerified);
    document.body.dataset.nonAoMutationCount = String(mutation.mutationCount);
    document.body.dataset.aoContractPassed = String(aoAudit.passed);
    document.body.dataset.forbiddenObjectCount = String(
      this.asset?.forbiddenObjects.length || 0,
    );
    document.body.dataset.yellowOutlineCount = String(
      this.asset?.yellowOutlines.length || 0,
    );
  }

  getState() {
    const nonAoMutation = this.nonAoMutationAudit();
    const aoState = this.aoStateAudit();
    return {
      schemaVersion: "bf3d.r2x.isolated_review_state.v1",
      requirementId: REQUIREMENT_ID,
      loadState: this.loadState,
      view: this.view,
      aoEnabled: this.aoEnabled,
      aoState: this.aoEnabled ? "on" : "off",
      evidence: "E/illustrative",
      smokeResolution: "1K",
      p50Approved: false,
      productionApproved: false,
      notForConstruction: true,
      colorPath: "Three r160 sRGB + ACES approximate path",
      fixedExposure: FIXED_EXPOSURE,
      model: {
        url: MODEL_URL,
        expectedBytes: EXPECTED_MODEL_BYTES,
        expectedSha256: EXPECTED_MODEL_SHA256,
        actualSha256: this.assetSha256,
        shaVerified: this.assetShaVerified,
        requestCount: this.assetRequestCount,
        loadAttemptCount: this.loadAttemptCount,
      },
      composition: {
        view: this.view,
        cameraDirection: this.cameraDirection.slice(),
        cameraDistanceScale: this.cameraDistanceScale,
        cameraPosition: this.camera.position.toArray(),
        cameraQuaternion: this.camera.quaternion.toArray(),
        projectionMatrix: this.camera.projectionMatrix.toArray(),
        projectionAudit: this.projectionAudit
          ? structuredClone(this.projectionAudit)
          : null,
        cameraOnly: true,
        cameraContractSource: "R2W locked CAMERA_COMPOSITION",
      },
      objects: {
        shellCount: this.asset?.meshes.length || 0,
        materialCount: this.asset?.materials.length || 0,
        forbiddenObjectCount: this.asset?.forbiddenObjects.length || 0,
        yellowOutlineCount: this.asset?.yellowOutlines.length || 0,
      },
      aoContract: {
        aoMapCount:
          this.asset?.entries.filter((entry) => entry.material.aoMap).length || 0,
        aoMapChannel2Count:
          this.asset?.entries.filter(
            (entry) => Number(entry.material.aoMap?.channel) === 2,
          ).length || 0,
        uv2Count:
          this.asset?.entries.filter((entry) => Boolean(entry.uv2)).length || 0,
        uv2FiniteCount:
          this.asset?.entries.filter((entry) =>
            bufferAttributeFinite(entry.uv2),
          ).length || 0,
        nonAoTextureChannel0Count:
          this.asset?.entries.filter(
            (entry) =>
              Number(entry.material.map?.channel) === 0 &&
              Number(entry.material.normalMap?.channel) === 0 &&
              Number(entry.material.roughnessMap?.channel) === 0 &&
              Number(entry.material.metalnessMap?.channel) === 0,
          ).length || 0,
        state: aoState,
        onlyIntensityChangesAtRuntime: nonAoMutation.mutationCount === 0,
      },
      pbr: {
        nonAoMutation,
        materialSnapshots: this.currentMaterialSnapshots(),
      },
      lighting: {
        directionalCount: P40_DIRECTIONAL_LIGHTS.length,
        directionalNames: P40_DIRECTIONAL_LIGHTS.map((entry) => entry.name),
        topType: "RectAreaLight",
        topName: P40_TOP_AREA.name,
        topEqualAreaSquareMeters: [
          P40_TOP_AREA.squareWidthMeters,
          P40_TOP_AREA.squareHeightMeters,
        ],
        fixedLinearEnvironment: ENVIRONMENT_LINEAR_RADIANCE.slice(),
        environmentImplementation: "Float DataTexture -> PMREM",
        ambientLightCount: 0,
        effectiveLtcInitCalls: rectAreaUniformsEffectiveInitCalls,
        photometricEquivalentClaimed: false,
      },
      renderer: {
        revision: THREE.REVISION,
        outputColorSpace: this.renderer?.outputColorSpace || null,
        toneMapping: this.renderer?.toneMapping ?? null,
        exposure: this.renderer?.toneMappingExposure ?? null,
        memory: this.renderer
          ? {
              geometries: this.renderer.info.memory.geometries,
              textures: this.renderer.info.memory.textures,
              programs: this.renderer.info.programs?.length || 0,
            }
          : null,
      },
      lifecycle: {
        disposed: this.disposed,
        rafActive: !this.disposed && this.rafId !== 0,
        frameCount: this.frameCount,
        resizeCount: this.resizeCount,
        ownedResourceCounts: resourceCounts(this.assetResources),
        disposedResourceCounts: { ...this.disposedResourceCounts },
        environmentSourceDisposed: this.environmentSourceDisposed,
        environmentTargetDisposed: this.environmentTargetDisposed,
        rendererDisposed: this.rendererDisposed,
        controlsDisposed: this.controlsDisposed,
        resizeObserverDisconnected: this.resizeObserverDisconnected,
        rafCancelled: this.rafCancelled,
      },
      lastError: this.lastError,
    };
  }

  getAuditSnapshot() {
    return structuredClone(this.getState());
  }

  dispose() {
    if (this.disposed) return this.getState();
    this.disposed = true;
    if (this.rafId) {
      cancelAnimationFrame(this.rafId);
      this.rafId = 0;
      this.rafCancelled = true;
    }
    this.resizeObserver?.disconnect();
    this.resizeObserverDisconnected = true;
    this.controls?.dispose();
    this.controlsDisposed = true;
    this.disposedResourceCounts = resourceCounts(this.assetResources);
    this.clearAsset();
    if (this.environmentTarget) {
      this.environmentTarget.dispose();
      this.environmentTargetDisposed = true;
    }
    if (this.scene) {
      this.scene.environment = null;
      this.scene.clear();
    }
    this.renderer?.dispose();
    this.rendererDisposed = true;
    this.canvas?.remove();
    this.setLoadState("disposed", "R2X 独占资源已释放。");
    return this.getState();
  }
}

function bindControls(controller) {
  for (const button of document.querySelectorAll("[data-view-button]")) {
    button.addEventListener("click", () => {
      controller.setView(button.dataset.viewButton);
    });
  }
  for (const button of document.querySelectorAll("[data-ao-button]")) {
    button.addEventListener("click", () => {
      controller.setAoEnabled(button.dataset.aoButton === "on");
    });
  }
  document.querySelector("#retry-button")?.addEventListener("click", () => {
    controller.load().catch(() => {
      // loadInternal renders the fail-closed state.
    });
  });
}

function exposeAuditApi(controller) {
  const api = Object.freeze({
    schemaVersion: "bf3d.r2x.isolated_review_api.v1",
    requirementId: REQUIREMENT_ID,
    getState: () => controller.getState(),
    getAuditSnapshot: () => controller.getAuditSnapshot(),
    setView: (view) => controller.setView(view),
    setAoEnabled: (enabled) => controller.setAoEnabled(enabled),
    resetCamera: () => controller.resetCamera(),
    renderOnce: () => controller.renderOnce(),
    retry: () => controller.load(),
    dispose: () => controller.dispose(),
  });
  Object.defineProperty(globalThis, "BF3D_R2X_REVIEW", {
    value: api,
    writable: false,
    configurable: false,
    enumerable: true,
  });
}

function renderFatalBootstrapError(error) {
  document.body.dataset.loadState = "error";
  const layer = document.querySelector("#review-state-layer");
  const title = document.querySelector("#state-title");
  const message = document.querySelector("#state-message");
  const retry = document.querySelector("#retry-button");
  const badge = document.querySelector("#load-state-badge");
  if (layer) {
    layer.dataset.kind = "error";
    layer.setAttribute("aria-busy", "false");
  }
  if (title) title.textContent = "R2X 渲染器初始化失败";
  if (message) message.textContent = String(error?.message || error);
  if (retry) retry.hidden = false;
  if (badge) {
    badge.className = "state-badge is-error";
    badge.textContent = "错误";
  }
}

async function bootstrap() {
  const controller = new BF3DR2XReviewRenderer(
    document.querySelector("#bf3d-review-viewport"),
  );
  bindControls(controller);
  exposeAuditApi(controller);
  await controller.load();
}

bootstrap().catch(renderFatalBootstrapError);
