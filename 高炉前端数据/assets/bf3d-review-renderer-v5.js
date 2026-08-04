import * as THREE from "three";
import { OrbitControls } from "three/addons/controls/OrbitControls.js";
import { GLTFLoader } from "three/addons/loaders/GLTFLoader.js";
import { RectAreaLightUniformsLib } from "three/addons/lights/RectAreaLightUniformsLib.js";

const REQUIREMENT_ID = "REQ-BF3D-R2V-ISOLATED-WEB-REVIEW-20260720";
const MODEL_URL = "models/gl02_blast_furnace_review.v5.glb";
const EXPECTED_MODEL_SHA256 =
  "0ac031e626c9eaa0b0cdd8192cf9fda712324af174a4285f563a97309451ed3c";
const EXPECTED_MODEL_BYTES = 4_663_220;
const MATERIAL_GROUP_NAME = "BF3D_V5_MODE_MATERIAL";
const SECTION_GROUP_NAME = "BF3D_V5_MODE_SECTION";
const FIXED_EXPOSURE = 1.0;
const ENVIRONMENT_LINEAR_RADIANCE = Object.freeze([0.0864, 0.0864, 0.0864]);
const SECTION_EXPECTED_COUNT = 10;
const MATERIAL_EXPECTED_COUNT = 5;
const CAMERA_COMPOSITION = Object.freeze({
  materialExteriorDirection: Object.freeze([0.78, 0.18, 0.62]),
  structuralDirection: Object.freeze([1.0, 0.09, 0.24]),
  interiorDirection: Object.freeze([1.0, 0.035, 0.015]),
  mobileInteriorMaxWidth: 520,
  mobileInteriorDistanceScale: 1.16,
  mobileInteriorLayerBoundaryTarget: 3,
});
const EXTERIOR_BOUNDARY_MEANING =
  "R2J 五区实体交界与原始表面纹理，不是数据圆环、轮廓或引线。";
const STRUCTURAL_WEDGE_DIAGNOSIS =
  "V5 物理 Section 已通过 10/10 闭合与跨对象共面重叠 0；中央深色面为保留半炉的对侧内壁，不是固定圆环、竖线、数据引线或内腔封堵。";
const FORBIDDEN_OBJECT_NAME =
  /(^|[_\-\s])(SENSOR|HIT|LINE|LINES|LINESEGMENTS|POINT|POINTS|SPRITE|OUTLINE|HIGHLIGHT|PARTICLE|PARTICLES|LEADER|CALLOUT|RING)([_\-\s]|$)/i;
const MATERIAL_TEXTURE_KEYS = Object.freeze([
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
]);

const P40_DIRECTIONAL_LIGHTS = Object.freeze([
  Object.freeze({
    name: "P40_NEUTRAL_KEY",
    position: Object.freeze([46.1323356628418, 49.166168212890625, 46.1323356628418]),
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
  sourceDiskAreaSquareMeters: 940.206546693096,
  squareWidthMeters: 30.6627876536543,
  squareHeightMeters: 30.6627876536543,
  sourcePowerWatts: 3921.24853515625,
  intensityAtK1: 1.3275510357953,
});

const ROLE_LABELS = Object.freeze({
  steel_shell: "钢壳",
  backfill: "背衬浇注层",
  hotface_embed: "热面嵌入层",
  refractory: "残余耐火层",
  cooling_stave: "冷却壁",
});

const ZONE_LABELS = Object.freeze({
  HEARTH: "炉缸钢壳",
  BOSH: "炉腹钢壳",
  BELLY: "炉腰钢壳",
  SHAFT: "炉身钢壳",
  THROAT: "炉喉钢壳",
});

let rectAreaUniformsInitialized = false;
let rectAreaUniformsEffectiveInitCalls = 0;

class EmptyReviewAssetError extends Error {
  constructor(message) {
    super(message);
    this.name = "EmptyReviewAssetError";
    this.code = "BF3D_REVIEW_EMPTY";
  }
}

function initRectAreaLightUniformsOnce() {
  if (rectAreaUniformsInitialized) return;
  RectAreaLightUniformsLib.init();
  rectAreaUniformsInitialized = true;
  rectAreaUniformsEffectiveInitCalls += 1;
}

function normalizeName(value) {
  return String(value || "").trim();
}

function materialList(object) {
  if (!object?.material) return [];
  return (Array.isArray(object.material)
    ? object.material
    : [object.material]
  ).filter(Boolean);
}

function uniqueMaterials(root) {
  const materials = new Set();
  root?.traverse?.((object) => {
    for (const material of materialList(object)) materials.add(material);
  });
  return materials;
}

function renderableDescendants(root) {
  const renderables = [];
  root?.traverse?.((object) => {
    if (object !== root && object.isMesh) renderables.push(object);
  });
  return renderables;
}

function logicalReviewDescendants(root, mode) {
  const logical = [];
  root?.traverse?.((object) => {
    if (object === root) return;
    if (normalizeName(object.userData?.bf3d_review_mode) !== mode) return;
    let parent = object.parent;
    while (parent && parent !== root) {
      if (normalizeName(parent.userData?.bf3d_review_mode) === mode) return;
      parent = parent.parent;
    }
    logical.push(object);
  });
  return logical;
}

function collectOwnedResources(root) {
  const geometries = new Set();
  const materials = new Set();
  const textures = new Set();
  root?.traverse?.((object) => {
    if (object.geometry?.isBufferGeometry) geometries.add(object.geometry);
    for (const material of materialList(object)) {
      materials.add(material);
      for (const key of MATERIAL_TEXTURE_KEYS) {
        if (material[key]?.isTexture) textures.add(material[key]);
      }
    }
  });
  return { geometries, materials, textures };
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

function colorFromLinear(values) {
  return new THREE.Color().setRGB(
    Number(values[0]),
    Number(values[1]),
    Number(values[2]),
    THREE.LinearSRGBColorSpace,
  );
}

function materialContractSignature(material) {
  return JSON.stringify({
    uuid: material?.uuid || null,
    type: material?.type || null,
    color: material?.color?.toArray?.() || null,
    emissive: material?.emissive?.toArray?.() || null,
    roughness: material?.roughness ?? null,
    metalness: material?.metalness ?? null,
    normalScale: material?.normalScale?.toArray?.() || null,
    opacity: material?.opacity ?? null,
    transparent: material?.transparent ?? null,
    alphaTest: material?.alphaTest ?? null,
    side: material?.side ?? null,
    clippingPlaneCount: material?.clippingPlanes?.length || 0,
    textures: Object.fromEntries(
      MATERIAL_TEXTURE_KEYS.map((key) => [key, material?.[key]?.uuid || null]),
    ),
  });
}

function hexFromArrayBuffer(buffer) {
  return Array.from(new Uint8Array(buffer), (value) =>
    value.toString(16).padStart(2, "0"),
  ).join("");
}

async function sha256ArrayBuffer(buffer) {
  if (!globalThis.crypto?.subtle) {
    throw new Error("当前浏览器不支持 Web Crypto SHA-256，审查资产拒绝加载");
  }
  return hexFromArrayBuffer(await globalThis.crypto.subtle.digest("SHA-256", buffer));
}

async function fetchArrayBufferWithProgress(url, onProgress) {
  const response = await fetch(url, {
    cache: "no-store",
    credentials: "same-origin",
    redirect: "error",
  });
  if (!response.ok) {
    throw new Error(`审查资产请求失败：HTTP ${response.status}`);
  }
  const expectedLength = Number(response.headers.get("content-length") || 0);
  const payload = await response.arrayBuffer();
  if (expectedLength > 0 && payload.byteLength !== expectedLength) {
    throw new Error(
      `审查资产响应未完整消费：${payload.byteLength}/${expectedLength} bytes`,
    );
  }
  onProgress?.(payload.byteLength, expectedLength || payload.byteLength);
  return payload;
}

function describeSection(object) {
  const role = normalizeName(object.userData?.bf3d_structural_role);
  const zone = normalizeName(object.userData?.bf3d_zone);
  const name = normalizeName(object.name);
  let label = ZONE_LABELS[zone] || ROLE_LABELS[role] || "物理剖面";
  if (role === "cooling_stave") {
    label = name.includes("COPPER") ? "铜冷却壁" : "铸铁冷却壁";
  }
  return {
    id: name,
    label,
    role: ROLE_LABELS[role] || role || "未标注",
    evidence: normalizeName(object.userData?.bf3d_evidence) || "E/illustrative",
    referenceStatus:
      normalizeName(object.userData?.bf3d_reference_status) || "REF-PENDING",
  };
}

function validateReviewAsset(gltf) {
  const root = gltf?.scene;
  if (!root?.isObject3D) {
    throw new EmptyReviewAssetError("V5 审查资产没有可用的 glTF scene");
  }

  const materialGroup = root.children.find(
    (object) => normalizeName(object.name) === MATERIAL_GROUP_NAME,
  );
  const sectionGroup = root.children.find(
    (object) => normalizeName(object.name) === SECTION_GROUP_NAME,
  );
  const unexpectedTopLevel = root.children.filter(
    (object) =>
      ![MATERIAL_GROUP_NAME, SECTION_GROUP_NAME].includes(
        normalizeName(object.name),
      ),
  );
  if (!materialGroup || !sectionGroup || root.children.length !== 2) {
    throw new Error(
      `V5 顶层组合同不匹配：material=${materialGroup ? 1 : 0}/1，section=${
        sectionGroup ? 1 : 0
      }/1，unexpected=${unexpectedTopLevel.length}`,
    );
  }

  const materialLogical = logicalReviewDescendants(materialGroup, "material");
  const sectionTagged = logicalReviewDescendants(sectionGroup, "section");
  const sectionLogical = sectionTagged.filter(
    (object) =>
      object.userData?.bf3d_section_physical_cut === true ||
      object.userData?.bf3d_section_physical_cut === "true",
  );
  const materialPrimitives = renderableDescendants(materialGroup);
  const sectionPrimitives = renderableDescendants(sectionGroup);
  if (!materialLogical.length && !sectionLogical.length) {
    throw new EmptyReviewAssetError("V5 审查资产没有逻辑材质或结构对象");
  }
  if (
    materialLogical.length !== MATERIAL_EXPECTED_COUNT ||
    sectionLogical.length !== SECTION_EXPECTED_COUNT
  ) {
    throw new Error(
      `逻辑对象合同不匹配：material=${materialLogical.length}/${MATERIAL_EXPECTED_COUNT}，section=${sectionLogical.length}/${SECTION_EXPECTED_COUNT}`,
    );
  }

  const forbiddenObjects = [];
  root.traverse((object) => {
    const typeForbidden =
      object.isLine ||
      object.isLineSegments ||
      object.isPoints ||
      object.isSprite;
    if (typeForbidden || FORBIDDEN_OBJECT_NAME.test(normalizeName(object.name))) {
      forbiddenObjects.push({
        name: normalizeName(object.name),
        type: object.type,
      });
    }
  });
  if (forbiddenObjects.length) {
    throw new Error(
      `V5 含禁止审查对象：${forbiddenObjects
        .map((entry) => `${entry.name || "(unnamed)"}:${entry.type}`)
        .join(", ")}`,
    );
  }

  const materials = new Set([
    ...uniqueMaterials(materialGroup),
    ...uniqueMaterials(sectionGroup),
  ]);
  const nonPbrMaterials = [...materials].filter(
    (material) => !material.isMeshStandardMaterial && !material.isMeshPhysicalMaterial,
  );
  const doubleSidedMaterials = [...materials].filter(
    (material) => material.side === THREE.DoubleSide,
  );
  const clippingMaterials = [...materials].filter(
    (material) => (material.clippingPlanes?.length || 0) > 0,
  );
  if (
    nonPbrMaterials.length ||
    doubleSidedMaterials.length ||
    clippingMaterials.length
  ) {
    throw new Error(
      `PBR 合同不匹配：nonPbr=${nonPbrMaterials.length}，doubleSide=${doubleSidedMaterials.length}，clipping=${clippingMaterials.length}`,
    );
  }

  const materialSignatures = new Map(
    [...materials].map((material) => [
      material,
      materialContractSignature(material),
    ]),
  );
  root.visible = false;
  materialGroup.visible = false;
  sectionGroup.visible = false;

  return {
    root,
    materialGroup,
    sectionGroup,
    materialLogical,
    sectionLogical,
    materialPrimitives,
    sectionPrimitives,
    materials,
    materialSignatures,
    forbiddenObjects,
    unexpectedTopLevel,
    sectionRegister: sectionLogical.map(describeSection),
  };
}

/**
 * 独立、只读的 GL02 V5 材质/结构审查渲染器。
 *
 * 对应需求：REQ-BF3D-R2V-ISOLATED-WEB-REVIEW-20260720
 * 输入：唯一 review.v5 GLB（浏览器内 SHA-256 硬核验）。
 * 输出：纯材质外表面、内部层近景和十 Section 全局剖面。
 * 异常：SHA、结构、PBR、禁止对象或 WebGL 任一合同失败即 fail closed。
 * 生命周期：本类独占 Scene、Renderer、Camera、RAF、ResizeObserver 与 Dispose。
 */
class BF3DReviewRenderer {
  constructor(viewport) {
    if (!viewport) throw new Error("缺少独立审查视口容器");
    this.viewport = viewport;
    this.disposed = false;
    this.loadPromise = null;
    this.loadState = "loading";
    this.mode = "material";
    this.materialView = "exterior";
    this.cameraPreset = "material-exterior-global";
    this.cameraDirection = [0, 0, 1];
    this.cameraDistanceScale = 1;
    this.mobileInteriorPullbackApplied = false;
    this.assetRequestCount = 0;
    this.loadAttemptCount = 0;
    this.assetSha256 = null;
    this.assetShaVerified = false;
    this.frameCount = 0;
    this.resizeCount = 0;
    this.contextLossCount = 0;
    this.contextRestoreCount = 0;
    this.rafId = 0;
    this.lastError = null;
    this.asset = null;
    this.assetResources = null;
    this.disposedResourceCounts = {
      geometries: 0,
      materials: 0,
      textures: 0,
    };
    this.environmentSourceDisposed = false;
    this.environmentTargetDisposed = false;
    this.rendererDisposed = false;
    this.controlsDisposed = false;
    this.resizeObserverDisconnected = false;
    this.rafCancelled = false;

    this.canvas = document.createElement("canvas");
    this.canvas.id = "bf3d-review-canvas";
    this.canvas.setAttribute("role", "img");
    this.canvas.setAttribute(
      "aria-label",
      "GL02 高炉 V5 材质与结构只读三维视图",
    );
    this.viewport.prepend(this.canvas);

    this.scene = new THREE.Scene();
    this.scene.name = "BF3D_ISOLATED_REVIEW_SCENE";
    this.scene.background = colorFromLinear([0.033, 0.039, 0.041]);

    this.camera = new THREE.PerspectiveCamera(38, 1, 0.05, 1000);
    this.camera.name = "BF3D_ISOLATED_REVIEW_CAMERA";
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

    this.handleContextLost = (event) => {
      event.preventDefault();
      this.contextLossCount += 1;
      if (!this.disposed) {
        this.setLoadState("error", "WebGL 上下文已丢失，请刷新页面重试");
      }
    };
    this.handleContextRestored = () => {
      this.contextRestoreCount += 1;
    };
    this.canvas.addEventListener("webglcontextlost", this.handleContextLost);
    this.canvas.addEventListener(
      "webglcontextrestored",
      this.handleContextRestored,
    );

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
    group.userData.bf3dEvidence = "E/illustrative";
    group.userData.bf3dReferenceStatus = "REF-PENDING";
    group.userData.blenderEquivalent = false;

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
    if (
      this.renderer.domElement.width === Math.floor(width * this.renderer.getPixelRatio()) &&
      this.renderer.domElement.height === Math.floor(height * this.renderer.getPixelRatio())
    ) {
      return;
    }
    this.renderer.setSize(width, height, false);
    this.camera.aspect = width / height;
    this.camera.updateProjectionMatrix();
    this.resizeCount += 1;
  }

  updateProgress(received, total) {
    const percent =
      total > 0 ? Math.min(100, Math.round((received / total) * 100)) : 0;
    const progress = document.querySelector("#load-progress");
    if (progress) {
      progress.value = percent;
      progress.textContent = `${percent}%`;
    }
    const message = document.querySelector("#state-message");
    if (message) {
      const receivedMb = (received / 1_048_576).toFixed(1);
      const totalMb = total > 0 ? ` / ${(total / 1_048_576).toFixed(1)} MB` : " MB";
      message.textContent = `正在读取 ${receivedMb}${totalMb}；完成后核验 SHA-256。`;
    }
  }

  setLoadState(kind, message = "") {
    this.loadState = kind;
    document.body.dataset.loadState = kind;
    const layer = document.querySelector("#review-state-layer");
    const title = document.querySelector("#state-title");
    const stateMessage = document.querySelector("#state-message");
    const retry = document.querySelector("#retry-button");
    const badge = document.querySelector("#load-state-badge");
    const progress = document.querySelector(".load-progress");
    const ready = kind === "ready";
    const labels = {
      loading: ["正在读取受控审查资产", "加载中"],
      ready: ["资产已通过合同核验", "已就绪"],
      empty: ["审查资产为空", "空状态"],
      error: ["审查资产加载失败", "错误"],
      disposed: ["审查渲染器已释放", "已释放"],
    };
    if (layer) {
      layer.dataset.kind = kind;
      layer.setAttribute("aria-busy", kind === "loading" ? "true" : "false");
    }
    if (title) title.textContent = labels[kind]?.[0] || "审查状态";
    if (stateMessage && message) stateMessage.textContent = message;
    if (retry) retry.hidden = !["empty", "error"].includes(kind);
    if (progress) progress.hidden = kind !== "loading";
    if (badge) {
      badge.className = `state-badge is-${kind}`;
      badge.textContent = labels[kind]?.[1] || kind;
    }
    for (const button of document.querySelectorAll(
      "[data-mode-button], [data-material-view-button], #reset-view-button",
    )) {
      button.disabled = !ready;
    }
  }

  async parseGltf(buffer) {
    const loader = new GLTFLoader();
    return new Promise((resolve, reject) => {
      loader.parse(
        buffer,
        new URL("./", globalThis.location.href).href,
        resolve,
        reject,
      );
    });
  }

  async load() {
    if (this.disposed) throw new Error("审查渲染器已释放");
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
      `加载唯一受控资产 ${MODEL_URL}；完成后核验 SHA-256。`,
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
        throw new Error(
          `资产字节数不匹配：${buffer.byteLength}/${EXPECTED_MODEL_BYTES}`,
        );
      }
      const sha256 = await sha256ArrayBuffer(buffer);
      this.assetSha256 = sha256;
      this.assetShaVerified = sha256 === EXPECTED_MODEL_SHA256;
      if (!this.assetShaVerified) {
        throw new Error(
          `资产 SHA-256 不匹配：${sha256}（期望 ${EXPECTED_MODEL_SHA256}）`,
        );
      }

      candidateGltf = await this.parseGltf(buffer);
      candidateResources = collectOwnedResources(candidateGltf.scene);
      const contract = validateReviewAsset(candidateGltf);
      this.clearAsset();
      this.asset = contract;
      this.assetResources = candidateResources;
      this.scene.add(contract.root);
      this.renderSectionRegister();
      this.applyView({ resetCamera: true });
      this.setLoadState(
        "ready",
        "V5 审查资产、SHA、PBR 与物理 Section 合同均已通过。",
      );
      this.renderContractStatus();
      return this.getState();
    } catch (error) {
      if (candidateGltf?.scene && candidateGltf.scene !== this.asset?.root) {
        disposeOwnedResources(candidateGltf.scene, candidateResources);
      }
      this.lastError = String(error?.message || error);
      const kind =
        error?.code === "BF3D_REVIEW_EMPTY" || error instanceof EmptyReviewAssetError
          ? "empty"
          : "error";
      this.setLoadState(kind, this.lastError);
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

  setMode(mode) {
    if (this.loadState !== "ready" || !this.asset) return;
    if (!["material", "structural"].includes(mode)) {
      throw new Error(`未知审查模式：${mode}`);
    }
    this.mode = mode;
    this.applyView({ resetCamera: true });
  }

  setMaterialView(view) {
    if (this.loadState !== "ready" || !this.asset) return;
    if (!["exterior", "interior"].includes(view)) {
      throw new Error(`未知材质视角：${view}`);
    }
    this.mode = "material";
    this.materialView = view;
    this.applyView({ resetCamera: true });
  }

  applyView({ resetCamera = false } = {}) {
    if (!this.asset) return;
    const showMaterial =
      this.mode === "material" && this.materialView === "exterior";
    const showSection = !showMaterial;
    this.asset.root.visible = true;
    this.asset.materialGroup.visible = showMaterial;
    this.asset.sectionGroup.visible = showSection;
    document.body.dataset.reviewMode = this.mode;
    document.body.dataset.materialView = this.materialView;

    for (const button of document.querySelectorAll("[data-mode-button]")) {
      const active = button.dataset.modeButton === this.mode;
      button.classList.toggle("is-active", active);
      button.setAttribute("aria-pressed", String(active));
    }
    const materialViewControl = document.querySelector(".material-view-control");
    materialViewControl?.toggleAttribute("data-inactive", this.mode !== "material");
    for (const button of document.querySelectorAll(
      "[data-material-view-button]",
    )) {
      const active =
        this.mode === "material" &&
        button.dataset.materialViewButton === this.materialView;
      button.classList.toggle("is-active", active);
      button.setAttribute("aria-pressed", String(active));
      button.disabled = this.mode !== "material";
    }

    const visibleLogical = showMaterial
      ? this.asset.materialLogical.length
      : this.asset.sectionLogical.length;
    document.body.dataset.visibleLogicalCount = String(visibleLogical);
    document.body.dataset.visibleSectionCount = String(
      showSection ? this.asset.sectionLogical.length : 0,
    );
    document.querySelector("#visible-object-count").textContent =
      String(visibleLogical);

    const title = document.querySelector("#visible-set-title");
    const note = document.querySelector("#visible-set-note");
    const description = document.querySelector("#active-view-description");
    if (this.mode === "structural") {
      title.textContent = "十 Section 全炉剖面";
      note.textContent = STRUCTURAL_WEDGE_DIAGNOSIS;
      description.textContent =
        "结构剖面：十个物理 Section 全局可见；底部深色楔形为现有 GLB 封口面共面叠合与遮挡，非内腔且未修复。";
      this.cameraPreset = "structural-global";
    } else if (this.materialView === "interior") {
      title.textContent = "内部层材质近景";
      note.textContent =
        "查看钢内表面、背衬、热面、耐火层及两类冷却壁；窄屏同时保留至少三处材料层边界。";
      description.textContent =
        "内部层近景：使用物理 Section 暴露六类内部材质；移动端稍外拉，不修改 GLB PBR。";
      this.cameraPreset = "material-interior-closeup";
    } else {
      title.textContent = "外表面材质";
      note.textContent = EXTERIOR_BOUNDARY_MEANING;
      description.textContent = `外表面：${EXTERIOR_BOUNDARY_MEANING}保留 GLB 原始 PBR。`;
      this.cameraPreset = "material-exterior-global";
    }
    if (resetCamera) this.resetCamera();
    this.updateSectionVisibility();
    this.renderContractStatus();
  }

  resetCamera() {
    if (!this.asset) return;
    if (this.mode === "material" && this.materialView === "interior") {
      this.frameDetail(this.asset.sectionGroup);
    } else {
      const group =
        this.mode === "structural"
          ? this.asset.sectionGroup
          : this.asset.materialGroup;
      this.frameGlobal(group, this.mode);
    }
  }

  frameGlobal(group, mode) {
    const box = new THREE.Box3().setFromObject(group);
    if (box.isEmpty()) throw new EmptyReviewAssetError("当前可见集包围盒为空");
    const center = box.getCenter(new THREE.Vector3());
    const sphere = box.getBoundingSphere(new THREE.Sphere());
    const direction = new THREE.Vector3(
      ...(mode === "structural"
        ? CAMERA_COMPOSITION.structuralDirection
        : CAMERA_COMPOSITION.materialExteriorDirection),
    ).normalize();
    const halfFov = THREE.MathUtils.degToRad(this.camera.fov * 0.5);
    const distance = Math.max(
      sphere.radius * 1.5,
      (sphere.radius / Math.max(Math.sin(halfFov), 0.2)) * 1.08,
    );
    this.camera.position.copy(center).addScaledVector(direction, distance);
    this.cameraDirection = direction.toArray();
    this.cameraDistanceScale = 1;
    this.mobileInteriorPullbackApplied = false;
    this.camera.near = Math.max(0.05, distance - sphere.radius * 2.35);
    this.camera.far = Math.max(300, distance + sphere.radius * 4.5);
    this.camera.lookAt(center);
    this.camera.updateProjectionMatrix();
    this.controls.target.copy(center);
    this.controls.minDistance = Math.max(0.35, sphere.radius * 0.16);
    this.controls.maxDistance = Math.max(120, distance * 2.6);
    this.controls.update();
  }

  frameDetail(group) {
    const box = new THREE.Box3().setFromObject(group);
    if (box.isEmpty()) throw new EmptyReviewAssetError("内部层近景包围盒为空");
    const center = box.getCenter(new THREE.Vector3());
    const size = box.getSize(new THREE.Vector3());
    const target = center.clone();
    target.y -= size.y * 0.03;
    target.z += size.z * 0.43;
    const direction = new THREE.Vector3(
      ...CAMERA_COMPOSITION.interiorDirection,
    ).normalize();
    const halfFov = THREE.MathUtils.degToRad(this.camera.fov * 0.5);
    const detailSpan = Math.max(size.z * 0.72, size.y * 0.15, 3.6);
    const baseDistance = Math.max(
      4,
      detailSpan / Math.max(2 * Math.tan(halfFov), 0.3),
    );
    const isMobile =
      this.viewport.getBoundingClientRect().width <=
      CAMERA_COMPOSITION.mobileInteriorMaxWidth;
    const distanceScale = isMobile
      ? CAMERA_COMPOSITION.mobileInteriorDistanceScale
      : 1;
    const distance = baseDistance * distanceScale;
    this.camera.position.copy(target).addScaledVector(direction, distance);
    this.cameraDirection = direction.toArray();
    this.cameraDistanceScale = distanceScale;
    this.mobileInteriorPullbackApplied = isMobile;
    this.camera.near = 0.05;
    this.camera.far = Math.max(300, distance + size.y * 2);
    this.camera.lookAt(target);
    this.camera.updateProjectionMatrix();
    this.controls.target.copy(target);
    this.controls.minDistance = Math.max(0.35, distance * 0.18);
    this.controls.maxDistance = Math.max(120, distance * 8);
    this.controls.update();
  }

  renderSectionRegister() {
    const body = document.querySelector("#section-register-body");
    const empty = document.querySelector("#section-list-empty");
    if (!body) return;
    body.replaceChildren();
    const sections = this.asset?.sectionRegister || [];
    empty.hidden = sections.length > 0;
    if (!sections.length) return;
    for (const section of sections) {
      const row = document.createElement("tr");
      row.dataset.sectionId = section.id;
      const objectCell = document.createElement("td");
      objectCell.textContent = section.label;
      objectCell.title = section.id;
      const roleCell = document.createElement("td");
      roleCell.textContent = section.role;
      const stateCell = document.createElement("td");
      stateCell.dataset.sectionStatus = "hidden";
      stateCell.textContent = "隐藏";
      row.append(objectCell, roleCell, stateCell);
      body.append(row);
    }
  }

  updateSectionVisibility() {
    const visible =
      this.mode === "structural" ||
      (this.mode === "material" && this.materialView === "interior");
    for (const cell of document.querySelectorAll("[data-section-status]")) {
      cell.dataset.sectionStatus = visible ? "visible" : "hidden";
      cell.textContent = visible ? "可见" : "隐藏";
    }
  }

  pbrMutationAudit() {
    if (!this.asset?.materialSignatures) {
      return { checked: false, mutationCount: 0, mutatedMaterialNames: [] };
    }
    const mutatedMaterialNames = [];
    for (const [material, signature] of this.asset.materialSignatures) {
      if (materialContractSignature(material) !== signature) {
        mutatedMaterialNames.push(material.name || material.uuid);
      }
    }
    return {
      checked: true,
      mutationCount: mutatedMaterialNames.length,
      mutatedMaterialNames,
    };
  }

  renderContractStatus() {
    const sha = document.querySelector("#asset-sha");
    const assetContract = document.querySelector("#asset-contract");
    const logical = document.querySelector("#logical-counts");
    const section = document.querySelector("#section-count");
    const pbr = document.querySelector("#pbr-status");
    const pbrAudit = this.pbrMutationAudit();
    if (sha) {
      sha.textContent = this.assetShaVerified
        ? `${this.assetSha256.slice(0, 12)}…${this.assetSha256.slice(-8)}`
        : this.assetSha256 || "待核验";
      sha.title = this.assetSha256 || "";
    }
    if (assetContract) {
      assetContract.textContent = this.assetShaVerified
        ? "review.v5 · SHA 已核验"
        : "review.v5 · 正在核验 SHA";
    }
    if (logical) {
      logical.textContent = this.asset
        ? `材质 ${this.asset.materialLogical.length} / 结构 ${this.asset.sectionLogical.length}`
        : "待读取";
    }
    if (section) {
      section.textContent = this.asset
        ? `${this.asset.sectionLogical.length} / ${SECTION_EXPECTED_COUNT}`
        : "待读取";
    }
    if (pbr) {
      pbr.textContent = pbrAudit.checked
        ? pbrAudit.mutationCount === 0
          ? "GLB 原值未覆盖"
          : `检测到 ${pbrAudit.mutationCount} 项变化`
        : "未检查";
    }
    document.body.dataset.modelShaVerified = String(this.assetShaVerified);
    document.body.dataset.pbrMutationCount = String(pbrAudit.mutationCount);
    document.body.dataset.ltcInitCount = String(
      rectAreaUniformsEffectiveInitCalls,
    );
  }

  getState() {
    const visibleSection =
      this.asset?.sectionGroup?.visible === true
        ? this.asset.sectionLogical.length
        : 0;
    const visibleMaterial =
      this.asset?.materialGroup?.visible === true
        ? this.asset.materialLogical.length
        : 0;
    const pbrAudit = this.pbrMutationAudit();
    return {
      schemaVersion: "bf3d.isolated_review_state.v1",
      requirementId: REQUIREMENT_ID,
      loadState: this.loadState,
      mode: this.mode,
      materialView: this.materialView,
      cameraPreset: this.cameraPreset,
      evidence: "E/illustrative",
      referenceStatus: "REF-PENDING",
      notForConstruction: true,
      blenderEquivalent: false,
      colorPath: "Three r160 sRGB + ACES approximate path",
      fixedExposure: FIXED_EXPOSURE,
      composition: {
        cameraDirection: this.cameraDirection.slice(),
        cameraDistanceScale: this.cameraDistanceScale,
        exteriorBoundaryMeaning: EXTERIOR_BOUNDARY_MEANING,
        exteriorDataRingOrLeader: false,
        structuralBottomWedgeDiagnosis:
          "controlled_section_caps_zero_overlap",
        structuralBottomWedgeIsCavityOrOpening: false,
        structuralGeometryModified: false,
        mobileInteriorPullbackApplied:
          this.mobileInteriorPullbackApplied,
        mobileInteriorMaxWidth:
          CAMERA_COMPOSITION.mobileInteriorMaxWidth,
        mobileInteriorDistanceScale:
          CAMERA_COMPOSITION.mobileInteriorDistanceScale,
        mobileInteriorLayerBoundaryTarget:
          CAMERA_COMPOSITION.mobileInteriorLayerBoundaryTarget,
      },
      model: {
        url: MODEL_URL,
        expectedBytes: EXPECTED_MODEL_BYTES,
        expectedSha256: EXPECTED_MODEL_SHA256,
        actualSha256: this.assetSha256,
        shaVerified: this.assetShaVerified,
        requestCount: this.assetRequestCount,
        loadAttemptCount: this.loadAttemptCount,
      },
      objects: {
        materialLogical: this.asset?.materialLogical.length || 0,
        sectionLogical: this.asset?.sectionLogical.length || 0,
        materialPrimitives: this.asset?.materialPrimitives.length || 0,
        sectionPrimitives: this.asset?.sectionPrimitives.length || 0,
        physicalSectionCount: this.asset?.sectionLogical.length || 0,
        visibleMaterialLogical: visibleMaterial,
        visibleSectionLogical: visibleSection,
        forbiddenObjectCount: this.asset?.forbiddenObjects.length || 0,
        yellowOutlineCount: 0,
      },
      pbr: pbrAudit,
      lighting: {
        directionalCount: P40_DIRECTIONAL_LIGHTS.length,
        directionalNames: P40_DIRECTIONAL_LIGHTS.map((entry) => entry.name),
        topType: "RectAreaLight",
        topName: P40_TOP_AREA.name,
        topEqualAreaSquareMeters: [
          P40_TOP_AREA.squareWidthMeters,
          P40_TOP_AREA.squareHeightMeters,
        ],
        topSourceDiskDiameterMeters: P40_TOP_AREA.sourceDiskDiameterMeters,
        topShadowsClaimed: false,
        fixedLinearEnvironment: ENVIRONMENT_LINEAR_RADIANCE.slice(),
        environmentImplementation: "Float DataTexture -> PMREM",
        ambientLightCount: 0,
        effectiveLtcInitCalls: rectAreaUniformsEffectiveInitCalls,
        photometricEquivalentClaimed: false,
      },
      lifecycle: {
        sceneOwned: this.scene?.name === "BF3D_ISOLATED_REVIEW_SCENE",
        rendererOwned: Boolean(this.renderer),
        cameraOwned: this.camera?.name === "BF3D_ISOLATED_REVIEW_CAMERA",
        rafActive: !this.disposed && this.rafId !== 0,
        resizeObserverActive:
          !this.disposed && !this.resizeObserverDisconnected,
        disposed: this.disposed,
        rendererDisposed: this.rendererDisposed,
        controlsDisposed: this.controlsDisposed,
        resizeObserverDisconnected: this.resizeObserverDisconnected,
        rafCancelled: this.rafCancelled,
        frameCount: this.frameCount,
        resizeCount: this.resizeCount,
        contextLossCount: this.contextLossCount,
        contextRestoreCount: this.contextRestoreCount,
        environmentSourceDisposed: this.environmentSourceDisposed,
        environmentTargetDisposed: this.environmentTargetDisposed,
        ownedResourceCounts: resourceCounts(this.assetResources),
        disposedResourceCounts: { ...this.disposedResourceCounts },
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
    this.canvas?.removeEventListener("webglcontextlost", this.handleContextLost);
    this.canvas?.removeEventListener(
      "webglcontextrestored",
      this.handleContextRestored,
    );
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
    this.setLoadState("disposed", "Scene、Renderer、Camera、RAF 与 Resize 资源已释放。");
    return this.getState();
  }
}

function bindControls(controller) {
  for (const button of document.querySelectorAll("[data-mode-button]")) {
    button.addEventListener("click", () => {
      controller.setMode(button.dataset.modeButton);
    });
  }
  for (const button of document.querySelectorAll(
    "[data-material-view-button]",
  )) {
    button.addEventListener("click", () => {
      controller.setMaterialView(button.dataset.materialViewButton);
    });
  }
  document.querySelector("#reset-view-button")?.addEventListener("click", () => {
    controller.resetCamera();
  });
  document.querySelector("#retry-button")?.addEventListener("click", () => {
    controller.load().catch(() => {
      // The fail-closed state is already rendered by loadInternal().
    });
  });
}

function exposeReadOnlyAuditApi(controller) {
  const api = Object.freeze({
    schemaVersion: "bf3d.isolated_review_api.v1",
    requirementId: REQUIREMENT_ID,
    getState: () => controller.getState(),
    getAuditSnapshot: () => controller.getAuditSnapshot(),
    retry: () => controller.load(),
    dispose: () => controller.dispose(),
  });
  Object.defineProperty(globalThis, "BF3D_REVIEW_PREVIEW", {
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
  if (title) title.textContent = "独立审查渲染器初始化失败";
  if (message) message.textContent = String(error?.message || error);
  if (retry) retry.hidden = false;
  if (badge) {
    badge.className = "state-badge is-error";
    badge.textContent = "错误";
  }
}

async function bootstrap() {
  const controller = new BF3DReviewRenderer(
    document.querySelector("#bf3d-review-viewport"),
  );
  bindControls(controller);
  exposeReadOnlyAuditApi(controller);
  const disposeOnPageHide = () => controller.dispose();
  globalThis.addEventListener("pagehide", disposeOnPageHide, { once: true });
  try {
    await controller.load();
  } catch {
    // loadInternal() already supplies the explicit empty/error/retry state.
  }
}

bootstrap().catch(renderFatalBootstrapError);
