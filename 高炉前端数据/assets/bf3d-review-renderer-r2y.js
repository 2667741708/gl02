import * as THREE from "three";
import { GLTFLoader } from "three/addons/loaders/GLTFLoader.js";
import { RectAreaLightUniformsLib } from "three/addons/lights/RectAreaLightUniformsLib.js";

const REQUIREMENT_ID =
  "REQ-BF3D-R2Y-MATERIAL-SIGNAL-VISIBILITY-DIAGNOSTIC-20260720";
const MODEL_URL =
  "models/gl02_blast_furnace_material_review.v5.glb";
const EXPECTED_MODEL_SHA256 =
  "652be1b2c9147d5a7392497c7ae4964d19bdd7095b5435b87c105f9eb3fb66bc";
const EXPECTED_MODEL_BYTES = 994_372;
const EXPECTED_SHELL_COUNT = 5;
const EXPECTED_MATERIAL_NAMES = Object.freeze([
  "INT30_R2G_R1_LOCK_BAKED_PBR_STEEL",
  "INT30_R2G_R1_LOCK_BAKED_PBR_STEEL.001",
]);
const EXPECTED_NORMAL_SCALE = 0.45;
const FIXED_EXPOSURE = 1.0;
const CANVAS_WIDTH = 960;
const CANVAS_HEIGHT = 540;
const CANVAS_ASPECT = CANVAS_WIDTH / CANVAS_HEIGHT;
const BASELINE_ORTHO_SCALE = 6.2;
const MACRO_ORTHO_SCALE = 3.1;
const BASELINE_ENVIRONMENT = Object.freeze([0.0864, 0.0864, 0.0864]);
const ZERO_ENVIRONMENT = Object.freeze([0, 0, 0]);
const ROI = Object.freeze({ x: 224, y: 142, width: 512, height: 256 });
const CHANNEL_DIAGNOSTIC_WATERMARK = "CHANNEL DIAGNOSTIC / NOT PBR";
const TARGET_NAMES = Object.freeze([
  "R2J_ASM_GL02_FURNACE_BELLY_SHELL_55MM_E",
  "R2J_ASM_GL02_FURNACE_BOSH_SHELL_55MM_E",
  "R2J_ASM_GL02_FURNACE_HEARTH_SHELL_65MM_E",
  "R2J_ASM_GL02_FURNACE_SHAFT_SHELL_45MM_E",
  "R2J_ASM_GL02_FURNACE_THROAT_SHELL_45MM_E",
]);
const MATERIAL_TEXTURE_KEYS = Object.freeze([
  "map",
  "normalMap",
  "roughnessMap",
  "metalnessMap",
]);
const FORBIDDEN_OBJECT_NAME =
  /(^|[_\-\s])(SENSOR|HIT|LINE|LINES|LINESEGMENTS|POINT|POINTS|SPRITE|OUTLINE|HIGHLIGHT|PARTICLE|PARTICLES|LEADER|CALLOUT|RING)([_\-\s]|$)/i;

const P40_CAM_DETAIL_SHELL = Object.freeze({
  source: "P40 CAM_DETAIL_SHELL",
  sourcePreset:
    "PT/高炉3D模型/web/presets/lookdev_camera_v1.json#CAM_DETAIL_SHELL",
  blenderLocation: Object.freeze([0, -35, 8.5]),
  blenderTarget: Object.freeze([0, -3.4, 8.2]),
  blenderRotationEuler: Object.freeze([1.561303, 0, 0]),
  threeLocation: Object.freeze([0, 8.5, 35]),
  threeTarget: Object.freeze([0, 8.2, 3.4]),
  orthoScale: BASELINE_ORTHO_SCALE,
  clipStart: 0.05,
  clipEnd: 1000,
  basis:
    "Blender(x,y,z) -> glTF/Three(x,z,-y)",
  basisMatrixRowMajor: Object.freeze([
    1, 0, 0,
    0, 0, 1,
    0, -1, 0,
  ]),
});

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
    color: Object.freeze([1, 1, 1]),
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
    color: Object.freeze([0.9599999785423279, 0.9800000190734863, 1]),
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
    color: Object.freeze([0.8999999761581421, 0.949999988079071, 1]),
    intensity: 1.350000023841858,
  }),
]);

const P40_TOP_AREA = Object.freeze({
  name: "P40_NEUTRAL_TOP",
  position: Object.freeze([0, 60.69925308227539, 0]),
  emissionDirection: Object.freeze([0, -1, 0]),
  color: Object.freeze([1, 1, 1]),
  squareWidthMeters: 30.6627876536543,
  squareHeightMeters: 30.6627876536543,
  sourcePowerWatts: 3921.24853515625,
  intensityAtK1: 1.3275510357953,
});

const CAPTURE_DEFINITIONS = Object.freeze({
  "00_contract": Object.freeze({
    kind: "contract",
    label: "预注册合同",
    allowed: Object.freeze([]),
  }),
  "01_p40_detail_ortho6p2": Object.freeze({
    kind: "beauty",
    label: "P40 CAM_DETAIL_SHELL · ortho 6.2",
    allowed: Object.freeze(["camera_scale"]),
    cameraScale: 6.2,
  }),
  "02_macro_ortho3p1": Object.freeze({
    kind: "beauty",
    label: "宏距 · ortho 3.1",
    allowed: Object.freeze(["camera_scale"]),
    cameraScale: 3.1,
  }),
  "03_graze30": Object.freeze({
    kind: "beauty",
    label: "Key 掠射 30°",
    allowed: Object.freeze(["key_direction"]),
    grazingDegrees: 30,
  }),
  "04_graze75": Object.freeze({
    kind: "beauty",
    label: "Key 掠射 75°",
    allowed: Object.freeze(["key_direction"]),
    grazingDegrees: 75,
  }),
  "05_aniso1": Object.freeze({
    kind: "beauty",
    label: "Sampler anisotropy 1×",
    allowed: Object.freeze(["sampler_anisotropy"]),
    anisotropy: 1,
  }),
  "06_aniso8": Object.freeze({
    kind: "beauty",
    label: "Sampler anisotropy min(8, capabilityMax)",
    allowed: Object.freeze(["sampler_anisotropy"]),
    anisotropy: 8,
  }),
  "07_env0": Object.freeze({
    kind: "beauty",
    label: "环境 radiance 0",
    allowed: Object.freeze(["environment_radiance"]),
    environment: ZERO_ENVIRONMENT,
  }),
  "08_env1": Object.freeze({
    kind: "beauty",
    label: "环境 radiance [0.0864]³",
    allowed: Object.freeze(["environment_radiance"]),
    environment: BASELINE_ENVIRONMENT,
  }),
  "09_basecolor_raw": Object.freeze({
    kind: "basecolor",
    label: "BaseColor raw sRGB",
    allowed: Object.freeze([]),
  }),
  "10_normal_xy_fixed": Object.freeze({
    kind: "normal",
    label: "Normal raw RGB + XY[-0.10,+0.10]",
    allowed: Object.freeze([]),
  }),
  "11_roughness_fixed": Object.freeze({
    kind: "roughness",
    label: "Roughness G fixed [0.56,0.82]",
    allowed: Object.freeze([]),
  }),
  "12_contact_sheet": Object.freeze({
    kind: "contact",
    label: "R2Y contact sheet",
    allowed: Object.freeze([]),
  }),
});
const CAPTURE_IDS = Object.freeze(Object.keys(CAPTURE_DEFINITIONS));

let ltcInitialized = false;
let ltcEffectiveInitCalls = 0;

class R2YContractError extends Error {
  constructor(message) {
    super(message);
    this.name = "R2YContractError";
    this.code = "BF3D_R2Y_CONTRACT";
  }
}

function initLtcOnce() {
  if (ltcInitialized) return;
  RectAreaLightUniformsLib.init();
  ltcInitialized = true;
  ltcEffectiveInitCalls += 1;
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
  return (Array.isArray(object.material)
    ? object.material
    : [object.material]
  ).filter(Boolean);
}

function normalizeName(value) {
  return String(value || "").trim().toUpperCase();
}

function textureSnapshot(texture) {
  if (!texture?.isTexture) return null;
  const source = texture.source?.data || texture.image || null;
  return {
    uuid: texture.uuid,
    sourceUuid: texture.source?.uuid || null,
    name: texture.name || "",
    channel: Number(texture.channel),
    colorSpace: texture.colorSpace || "",
    flipY: texture.flipY,
    wrapS: texture.wrapS,
    wrapT: texture.wrapT,
    minFilter: texture.minFilter,
    magFilter: texture.magFilter,
    generateMipmaps: texture.generateMipmaps,
    width: Number(source?.width || source?.videoWidth || 0),
    height: Number(source?.height || source?.videoHeight || 0),
  };
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
    map: textureSnapshot(material.map),
    normalMap: textureSnapshot(material.normalMap),
    roughnessMap: textureSnapshot(material.roughnessMap),
    metalnessMap: textureSnapshot(material.metalnessMap),
    aoMap: textureSnapshot(material.aoMap),
  };
}

function pbrSignature(materials) {
  return JSON.stringify(
    [...materials]
      .map(materialSnapshot)
      .sort((a, b) => a.uuid.localeCompare(b.uuid)),
  );
}

function collectTextures(materials) {
  const textures = new Set();
  for (const material of materials) {
    for (const key of MATERIAL_TEXTURE_KEYS) {
      if (material[key]?.isTexture) textures.add(material[key]);
    }
  }
  return textures;
}

function collectOwnedResources(root) {
  const geometries = new Set();
  const materials = new Set();
  root?.traverse?.((object) => {
    if (object.geometry?.isBufferGeometry) geometries.add(object.geometry);
    for (const material of materialList(object)) materials.add(material);
  });
  return {
    geometries,
    materials,
    textures: collectTextures(materials),
  };
}

function disposeOwnedResources(root, resources) {
  root?.removeFromParent?.();
  for (const texture of resources?.textures || []) texture.dispose?.();
  for (const material of resources?.materials || []) material.dispose?.();
  for (const geometry of resources?.geometries || []) geometry.dispose?.();
}

function resourceCounts(resources) {
  return {
    geometries: resources?.geometries?.size || 0,
    materials: resources?.materials?.size || 0,
    textures: resources?.textures?.size || 0,
  };
}

function hexFromArrayBuffer(buffer) {
  return Array.from(new Uint8Array(buffer), (value) =>
    value.toString(16).padStart(2, "0"),
  ).join("");
}

async function sha256ArrayBuffer(buffer) {
  if (!globalThis.crypto?.subtle) {
    throw new R2YContractError("浏览器不支持 Web Crypto SHA-256");
  }
  return hexFromArrayBuffer(
    await globalThis.crypto.subtle.digest("SHA-256", buffer),
  );
}

async function fetchLockedArrayBuffer(url, onProgress) {
  const response = await fetch(url, {
    cache: "no-store",
    credentials: "same-origin",
    redirect: "error",
  });
  if (!response.ok) {
    throw new R2YContractError(`V5 material GLB 请求失败：HTTP ${response.status}`);
  }
  const contentLength = Number(response.headers.get("content-length") || 0);
  const payload = await response.arrayBuffer();
  if (contentLength > 0 && contentLength !== payload.byteLength) {
    throw new R2YContractError(
      `V5 material GLB 响应不完整：${payload.byteLength}/${contentLength}`,
    );
  }
  onProgress?.(payload.byteLength, contentLength || payload.byteLength);
  return payload;
}

function validateMaterialAsset(gltf) {
  const root = gltf?.scene;
  if (!root?.isObject3D) {
    throw new R2YContractError("V5 material GLB 没有可用 scene");
  }
  const meshes = [];
  const forbiddenObjects = [];
  const yellowOutlines = [];
  root.traverse((object) => {
    const typeForbidden =
      object.isLine || object.isLineSegments || object.isPoints || object.isSprite;
    if (typeForbidden || FORBIDDEN_OBJECT_NAME.test(normalizeName(object.name))) {
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
    throw new R2YContractError(
      `V5 material GLB 含禁止对象：forbidden=${forbiddenObjects.length}, yellow=${yellowOutlines.length}`,
    );
  }
  if (meshes.length !== EXPECTED_SHELL_COUNT) {
    throw new R2YContractError(
      `V5 material GLB 五壳数量不匹配：${meshes.length}/${EXPECTED_SHELL_COUNT}`,
    );
  }
  const actualNames = meshes.map((mesh) => normalizeName(mesh.name)).sort();
  const expectedNames = TARGET_NAMES.map(normalizeName).sort();
  if (JSON.stringify(actualNames) !== JSON.stringify(expectedNames)) {
    throw new R2YContractError(`五壳身份不匹配：${JSON.stringify(actualNames)}`);
  }

  const materials = new Set();
  const bindings = [];
  for (const mesh of meshes) {
    const list = materialList(mesh);
    if (list.length !== 1 || !list[0]?.isMeshStandardMaterial) {
      throw new R2YContractError(`${mesh.name} 不是单一 MeshStandardMaterial`);
    }
    const material = list[0];
    const normalScale = material.normalScale?.toArray?.() || [];
    const checks = {
      baseColorPresentChannel0:
        Boolean(material.map?.isTexture) && Number(material.map.channel) === 0,
      normalPresentChannel0:
        Boolean(material.normalMap?.isTexture) &&
        Number(material.normalMap.channel) === 0,
      roughnessPresentChannel0:
        Boolean(material.roughnessMap?.isTexture) &&
        Number(material.roughnessMap.channel) === 0,
      metalnessPresentChannel0:
        Boolean(material.metalnessMap?.isTexture) &&
        Number(material.metalnessMap.channel) === 0,
      ormShared:
        material.roughnessMap?.uuid === material.metalnessMap?.uuid,
      normalScaleLocked:
        normalScale.length === 2 &&
        normalScale.every(
          (value) => Math.abs(value - EXPECTED_NORMAL_SCALE) <= 1e-6,
        ),
      aoAbsent: !material.aoMap,
      frontSide: material.side === THREE.FrontSide,
    };
    if (!Object.values(checks).every(Boolean)) {
      throw new R2YContractError(
        `${mesh.name} PBR/AO-off 合同失败：${JSON.stringify(checks)}`,
      );
    }
    materials.add(material);
    bindings.push({ mesh, material, checks });
  }
  const materialNames = [...materials]
    .map((material) => material.name)
    .sort();
  if (
    materials.size !== EXPECTED_MATERIAL_NAMES.length ||
    JSON.stringify(materialNames) !==
      JSON.stringify([...EXPECTED_MATERIAL_NAMES].sort())
  ) {
    throw new R2YContractError(
      `共享材质基线不匹配：${JSON.stringify(materialNames)}`,
    );
  }
  return {
    root,
    meshes,
    materials,
    bindings,
    textures: collectTextures(materials),
    forbiddenObjects,
    yellowOutlines,
  };
}

function mean(values) {
  return values.length
    ? values.reduce((sum, value) => sum + value, 0) / values.length
    : 0;
}

function standardDeviation(values, average = mean(values)) {
  if (!values.length) return 0;
  return Math.sqrt(
    values.reduce((sum, value) => {
      const delta = value - average;
      return sum + delta * delta;
    }, 0) / values.length,
  );
}

function finiteRange(values) {
  let minimum = Number.POSITIVE_INFINITY;
  let maximum = Number.NEGATIVE_INFINITY;
  for (const value of values) {
    if (!Number.isFinite(value)) continue;
    minimum = Math.min(minimum, value);
    maximum = Math.max(maximum, value);
  }
  return {
    minimum: Number.isFinite(minimum) ? minimum : 0,
    maximum: Number.isFinite(maximum) ? maximum : 0,
  };
}

function imageSource(texture) {
  return texture?.source?.data || texture?.image || null;
}

function makeSamplingCanvas(texture, maximumDimension = 1024) {
  const source = imageSource(texture);
  const sourceWidth = Number(source?.width || source?.videoWidth || 0);
  const sourceHeight = Number(source?.height || source?.videoHeight || 0);
  if (!source || sourceWidth <= 0 || sourceHeight <= 0) {
    throw new R2YContractError(`纹理没有可采样图片：${texture?.name || "unnamed"}`);
  }
  const scale = Math.min(
    1,
    maximumDimension / Math.max(sourceWidth, sourceHeight),
  );
  const canvas = document.createElement("canvas");
  canvas.width = Math.max(1, Math.round(sourceWidth * scale));
  canvas.height = Math.max(1, Math.round(sourceHeight * scale));
  const context = canvas.getContext("2d", {
    alpha: false,
    willReadFrequently: true,
  });
  context.imageSmoothingEnabled = true;
  context.imageSmoothingQuality = "high";
  context.drawImage(source, 0, 0, canvas.width, canvas.height);
  return {
    canvas,
    context,
    pixels: context.getImageData(0, 0, canvas.width, canvas.height),
    sourceWidth,
    sourceHeight,
  };
}

function computeChannelEvidence(materials) {
  const first = [...materials][0];
  const sources = {
    baseColor: makeSamplingCanvas(first.map),
    normal: makeSamplingCanvas(first.normalMap),
    roughness: makeSamplingCanvas(first.roughnessMap),
  };
  const baseChannels = [[], [], []];
  const baseLuma = [];
  const baseData = sources.baseColor.pixels.data;
  for (let index = 0; index < baseData.length; index += 4) {
    const r = baseData[index];
    const g = baseData[index + 1];
    const b = baseData[index + 2];
    baseChannels[0].push(r);
    baseChannels[1].push(g);
    baseChannels[2].push(b);
    baseLuma.push(0.2126 * r + 0.7152 * g + 0.0722 * b);
  }

  const normalX = [];
  const normalY = [];
  const normalZ = [];
  const normalData = sources.normal.pixels.data;
  for (let index = 0; index < normalData.length; index += 4) {
    normalX.push((normalData[index] / 255) * 2 - 1);
    normalY.push((normalData[index + 1] / 255) * 2 - 1);
    normalZ.push((normalData[index + 2] / 255) * 2 - 1);
  }

  const roughness = [];
  const roughnessData = sources.roughness.pixels.data;
  for (let index = 0; index < roughnessData.length; index += 4) {
    roughness.push(roughnessData[index + 1] / 255);
  }

  const baseStats = baseChannels.map((values, channel) => {
    const { minimum, maximum } = finiteRange(values);
    return {
      channel: ["R", "G", "B"][channel],
      minU8: minimum,
      maxU8: maximum,
      spanU8: maximum - minimum,
      meanU8: mean(values),
      stdU8: standardDeviation(values),
    };
  });
  const meanX = mean(normalX);
  const meanY = mean(normalY);
  const {
    minimum: roughnessMin,
    maximum: roughnessMax,
  } = finiteRange(roughness);
  const common = (source) => ({
    sourceDimensions: [source.sourceWidth, source.sourceHeight],
    sampledDimensions: [source.canvas.width, source.canvas.height],
    sampleCount: source.canvas.width * source.canvas.height,
    samplingMethod: "canvas_downsample_max_1024_high_quality",
  });
  return {
    sources,
    statistics: {
      baseColor: {
        dataPresent: true,
        sampled: true,
        runtimeBindingPresent: [...materials].every(
          (material) => material.map?.isTexture && material.map.channel === 0,
        ),
        consumed: null,
        consumptionClassification: "not_independently_probed",
        visible: null,
        ...common(sources.baseColor),
        channels: baseStats,
        lumaStdU8: standardDeviation(baseLuma),
      },
      normal: {
        dataPresent: true,
        sampled: true,
        runtimeBindingPresent: [...materials].every(
          (material) =>
            material.normalMap?.isTexture &&
            material.normalMap.channel === 0 &&
            material.normalScale
              .toArray()
              .every((value) => Math.abs(value - EXPECTED_NORMAL_SCALE) <= 1e-6),
        ),
        consumed: null,
        consumptionClassification: "not_independently_probed",
        visible: null,
        ...common(sources.normal),
        meanX,
        meanY,
        stdX: standardDeviation(normalX, meanX),
        stdY: standardDeviation(normalY, meanY),
        xyStdNorm: Math.hypot(
          standardDeviation(normalX, meanX),
          standardDeviation(normalY, meanY),
        ),
        meanZ: mean(normalZ),
        normalScale: EXPECTED_NORMAL_SCALE,
      },
      roughness: {
        dataPresent: true,
        sampled: true,
        runtimeBindingPresent: [...materials].every(
          (material) =>
            material.roughnessMap?.isTexture &&
            material.roughnessMap.channel === 0,
        ),
        consumed: null,
        consumptionClassification: "not_independently_probed",
        visible: null,
        ...common(sources.roughness),
        min: roughnessMin,
        max: roughnessMax,
        span: roughnessMax - roughnessMin,
        mean: mean(roughness),
        std: standardDeviation(roughness),
        fixedDiagnosticRange: [0.56, 0.82],
      },
    },
  };
}

function cloneCanvas(source) {
  const canvas = document.createElement("canvas");
  canvas.width = source.width;
  canvas.height = source.height;
  canvas.getContext("2d", { alpha: false }).drawImage(source, 0, 0);
  return canvas;
}

function vectorDistance(a, b) {
  return new THREE.Vector3().fromArray(a).distanceTo(
    new THREE.Vector3().fromArray(b),
  );
}

/**
 * R2Y 锁定 V5 材质信号隔离 fixture。
 *
 * 对应需求：
 * REQ-BF3D-R2Y-MATERIAL-SIGNAL-VISIBILITY-DIAGNOSTIC-20260720
 *
 * 输入：唯一 SHA 锁定的 V5 material GLB。
 * 输出：13 个预注册 960×540 状态与只读运行快照。
 * 异常：SHA、五壳、PBR、AO-off、单变量或通道采样失败即关闭。
 */
class BF3DR2YFixture {
  constructor() {
    this.webglCanvas = document.querySelector("#r2y-webgl-canvas");
    this.outputCanvas = document.querySelector("#r2y-output-canvas");
    if (!this.webglCanvas || !this.outputCanvas) {
      throw new R2YContractError("缺少 R2Y 固定画布");
    }
    this.outputContext = this.outputCanvas.getContext("2d", {
      alpha: false,
      willReadFrequently: true,
    });
    this.loadState = "loading";
    this.loadPromise = null;
    this.disposed = false;
    this.asset = null;
    this.assetResources = null;
    this.assetSha256 = null;
    this.assetShaVerified = false;
    this.assetRequestCount = 0;
    this.loadAttemptCount = 0;
    this.lastError = null;
    this.currentCaptureId = "00_contract";
    this.currentDefinition = CAPTURE_DEFINITIONS[this.currentCaptureId];
    this.currentEnvironment = BASELINE_ENVIRONMENT.slice();
    this.currentGrazingDegrees = null;
    this.currentOrthoScale = BASELINE_ORTHO_SCALE;
    this.currentAnisotropy = 1;
    this.maxAnisotropy = 1;
    this.channelEvidence = null;
    this.pbrBaselineSignature = null;
    this.materialBaselineSnapshots = [];
    this.contactFrames = new Map();
    this.environmentTargets = new Map();
    this.environmentSourcesDisposed = 0;
    this.frameCount = 0;
    this.disposedResourceCounts = {
      geometries: 0,
      materials: 0,
      textures: 0,
    };

    this.scene = new THREE.Scene();
    this.scene.name = "BF3D_R2Y_MATERIAL_SIGNAL_SCENE";
    this.scene.background = colorFromLinear([0.033, 0.039, 0.041]);
    this.camera = new THREE.OrthographicCamera(
      -BASELINE_ORTHO_SCALE / 2,
      BASELINE_ORTHO_SCALE / 2,
      BASELINE_ORTHO_SCALE / (2 * CANVAS_ASPECT),
      -BASELINE_ORTHO_SCALE / (2 * CANVAS_ASPECT),
      P40_CAM_DETAIL_SHELL.clipStart,
      P40_CAM_DETAIL_SHELL.clipEnd,
    );
    this.camera.name = "BF3D_R2Y_P40_CAM_DETAIL_SHELL";
    this.camera.up.set(0, 1, 0);
    this.camera.position.fromArray(P40_CAM_DETAIL_SHELL.threeLocation);
    this.camera.lookAt(new THREE.Vector3().fromArray(P40_CAM_DETAIL_SHELL.threeTarget));
    this.camera.updateProjectionMatrix();
    this.camera.updateMatrixWorld(true);

    this.renderer = new THREE.WebGLRenderer({
      canvas: this.webglCanvas,
      antialias: true,
      alpha: false,
      powerPreference: "high-performance",
      preserveDrawingBuffer: false,
    });
    this.renderer.setPixelRatio(1);
    this.renderer.setSize(CANVAS_WIDTH, CANVAS_HEIGHT, false);
    this.renderer.outputColorSpace = THREE.SRGBColorSpace;
    this.renderer.toneMapping = THREE.ACESFilmicToneMapping;
    this.renderer.toneMappingExposure = FIXED_EXPOSURE;
    this.renderer.shadowMap.enabled = false;
    this.renderer.localClippingEnabled = false;
    if ("useLegacyLights" in this.renderer) this.renderer.useLegacyLights = false;
    this.maxAnisotropy = Math.max(
      1,
      Number(this.renderer.capabilities.getMaxAnisotropy() || 1),
    );

    initLtcOnce();
    this.lightRig = this.createP40Lights();
    this.scene.add(this.lightRig);
    this.createEnvironment("env0", ZERO_ENVIRONMENT);
    this.createEnvironment("env1", BASELINE_ENVIRONMENT);
    this.scene.environment = this.environmentTargets.get("env1").texture;
    this.renderContractCanvas();
    this.bindUi();
  }

  createP40Lights() {
    const group = new THREE.Group();
    group.name = "BF3D_R2Y_P40_FIXED_LIGHT_RIG";
    this.directionalLights = new Map();
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
      this.directionalLights.set(entry.name, { light, target, entry });
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
    this.topLight = top;
    group.add(top);
    return group;
  }

  createEnvironment(key, radiance) {
    const width = 16;
    const height = 8;
    const data = new Float32Array(width * height * 4);
    for (let index = 0; index < width * height; index += 1) {
      const offset = index * 4;
      data[offset] = radiance[0];
      data[offset + 1] = radiance[1];
      data[offset + 2] = radiance[2];
      data[offset + 3] = 1;
    }
    const source = new THREE.DataTexture(
      data,
      width,
      height,
      THREE.RGBAFormat,
      THREE.FloatType,
    );
    source.name = `BF3D_R2Y_${key.toUpperCase()}_SOURCE`;
    source.colorSpace = THREE.LinearSRGBColorSpace;
    source.mapping = THREE.EquirectangularReflectionMapping;
    source.minFilter = THREE.LinearFilter;
    source.magFilter = THREE.LinearFilter;
    source.generateMipmaps = false;
    source.needsUpdate = true;
    const pmrem = new THREE.PMREMGenerator(this.renderer);
    pmrem.compileEquirectangularShader();
    const target = pmrem.fromEquirectangular(source);
    target.texture.name = `BF3D_R2Y_${key.toUpperCase()}_PMREM`;
    source.dispose();
    pmrem.dispose();
    this.environmentSourcesDisposed += 1;
    this.environmentTargets.set(key, target);
  }

  bindUi() {
    for (const button of document.querySelectorAll("[data-r2y-capture]")) {
      button.addEventListener("click", () => {
        this.setCaptureState(button.dataset.r2yCapture).catch((error) => {
          this.lastError = String(error?.message || error);
          this.setLoadState("error", this.lastError);
        });
      });
    }
    document.querySelector("#retry-button")?.addEventListener("click", () => {
      this.load().catch(() => {
        // loadInternal provides the fail-closed state.
      });
    });
  }

  updateProgress(received, total) {
    const progress = document.querySelector("#load-progress");
    if (!progress) return;
    const value = total > 0 ? Math.round((received / total) * 100) : 0;
    progress.value = value;
    progress.textContent = `${value}%`;
  }

  setLoadState(kind, message = "") {
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
    }
    if (title) {
      title.textContent =
        kind === "loading"
          ? "正在读取锁定 V5 material GLB"
          : kind === "ready"
            ? "R2Y 材质 fixture 已就绪"
            : "R2Y 合同失败";
    }
    if (body && message) body.textContent = message;
    if (retry) retry.hidden = kind !== "error";
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
    if (this.disposed) throw new R2YContractError("R2Y fixture 已释放");
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
      `只加载 ${MODEL_URL}；完成后核验 SHA、五壳、PBR snapshot 与 AO-off。`,
    );
    this.updateProgress(0, EXPECTED_MODEL_BYTES);
    let gltf = null;
    let resources = null;
    try {
      this.assetRequestCount += 1;
      const buffer = await fetchLockedArrayBuffer(
        MODEL_URL,
        (received, total) => this.updateProgress(received, total),
      );
      if (buffer.byteLength !== EXPECTED_MODEL_BYTES) {
        throw new R2YContractError(
          `V5 material bytes 不匹配：${buffer.byteLength}/${EXPECTED_MODEL_BYTES}`,
        );
      }
      this.assetSha256 = await sha256ArrayBuffer(buffer);
      this.assetShaVerified = this.assetSha256 === EXPECTED_MODEL_SHA256;
      if (!this.assetShaVerified) {
        throw new R2YContractError(
          `V5 material SHA 不匹配：${this.assetSha256}`,
        );
      }
      gltf = await this.parseGltf(buffer);
      resources = collectOwnedResources(gltf.scene);
      const asset = validateMaterialAsset(gltf);
      if (this.asset?.root) {
        disposeOwnedResources(this.asset.root, this.assetResources);
      }
      this.asset = asset;
      this.assetResources = resources;
      this.scene.add(asset.root);
      asset.root.visible = true;
      this.pbrBaselineSignature = pbrSignature(asset.materials);
      this.materialBaselineSnapshots = [...asset.materials]
        .map(materialSnapshot)
        .sort((a, b) => a.uuid.localeCompare(b.uuid));
      this.channelEvidence = computeChannelEvidence(asset.materials);
      this.restoreImmutableSnapshot();
      this.setLoadState(
        "ready",
        "V5 material SHA、五壳、PBR snapshot、normalScale 0.45 与 AO-off 已核验。",
      );
      await this.setCaptureState("00_contract");
      this.renderStatus();
      return this.getState();
    } catch (error) {
      if (gltf?.scene && gltf.scene !== this.asset?.root) {
        disposeOwnedResources(gltf.scene, resources);
      }
      this.lastError = String(error?.message || error);
      this.setLoadState("error", this.lastError);
      this.renderStatus();
      throw error;
    }
  }

  setOrthoScale(scale) {
    const value = Number(scale);
    this.camera.left = -value / 2;
    this.camera.right = value / 2;
    this.camera.top = value / (2 * CANVAS_ASPECT);
    this.camera.bottom = -value / (2 * CANVAS_ASPECT);
    this.camera.near = P40_CAM_DETAIL_SHELL.clipStart;
    this.camera.far = P40_CAM_DETAIL_SHELL.clipEnd;
    this.camera.position.fromArray(P40_CAM_DETAIL_SHELL.threeLocation);
    this.camera.lookAt(new THREE.Vector3().fromArray(P40_CAM_DETAIL_SHELL.threeTarget));
    this.camera.updateProjectionMatrix();
    this.camera.updateMatrixWorld(true);
    this.currentOrthoScale = value;
  }

  setKeyDirection(direction) {
    const binding = this.directionalLights.get("P40_NEUTRAL_KEY");
    binding.target.position
      .copy(binding.light.position)
      .add(new THREE.Vector3().fromArray(direction).normalize());
    binding.target.updateMatrixWorld(true);
  }

  setGrazing(degrees) {
    const radians = THREE.MathUtils.degToRad(Number(degrees));
    const direction = [
      -Math.sin(radians),
      0,
      -Math.cos(radians),
    ];
    this.setKeyDirection(direction);
    this.currentGrazingDegrees = Number(degrees);
  }

  setSamplerAnisotropy(value) {
    const target = Math.max(1, Math.min(Number(value), this.maxAnisotropy));
    for (const texture of this.asset?.textures || []) {
      texture.anisotropy = target;
      texture.needsUpdate = true;
    }
    this.currentAnisotropy = target;
  }

  setEnvironment(radiance) {
    const values = Array.from(radiance, Number);
    const zero = values.every((value) => value === 0);
    this.scene.environment = this.environmentTargets.get(
      zero ? "env0" : "env1",
    ).texture;
    this.currentEnvironment = values;
  }

  restoreImmutableSnapshot() {
    this.setOrthoScale(BASELINE_ORTHO_SCALE);
    const key = P40_DIRECTIONAL_LIGHTS[0];
    this.setKeyDirection(key.direction);
    this.currentGrazingDegrees = null;
    this.setSamplerAnisotropy(1);
    this.setEnvironment(BASELINE_ENVIRONMENT);
  }

  applyCaptureDefinition(definition) {
    if (definition.cameraScale !== undefined) {
      this.setOrthoScale(definition.cameraScale);
    }
    if (definition.grazingDegrees !== undefined) {
      this.setGrazing(definition.grazingDegrees);
    }
    if (definition.anisotropy !== undefined) {
      this.setSamplerAnisotropy(
        definition.anisotropy === 8
          ? Math.min(8, this.maxAnisotropy)
          : definition.anisotropy,
      );
    }
    if (definition.environment) {
      this.setEnvironment(definition.environment);
    }
  }

  keyDirection() {
    const binding = this.directionalLights.get("P40_NEUTRAL_KEY");
    return binding.target.position
      .clone()
      .sub(binding.light.position)
      .normalize()
      .toArray();
  }

  mutationAudit(definition) {
    const baselineKey = new THREE.Vector3().fromArray(
      P40_DIRECTIONAL_LIGHTS[0].direction,
    ).normalize();
    const currentKey = new THREE.Vector3().fromArray(this.keyDirection());
    const changed = [];
    if (Math.abs(this.currentOrthoScale - BASELINE_ORTHO_SCALE) > 1e-9) {
      changed.push("camera_scale");
    }
    if (baselineKey.angleTo(currentKey) > 1e-7) {
      changed.push("key_direction");
    }
    if (this.currentAnisotropy !== 1) {
      changed.push("sampler_anisotropy");
    }
    if (
      JSON.stringify(this.currentEnvironment) !==
      JSON.stringify(BASELINE_ENVIRONMENT)
    ) {
      changed.push("environment_radiance");
    }
    const pbr = this.pbrMutationAudit();
    if (pbr.mutationCount > 0) changed.push("pbr_material");
    const unexpected = changed.filter(
      (category) => !definition.allowed.includes(category),
    );
    return {
      baseline: {
        cameraScale: BASELINE_ORTHO_SCALE,
        keyDirection: baselineKey.toArray(),
        samplerAnisotropy: 1,
        environmentRadiance: BASELINE_ENVIRONMENT.slice(),
      },
      allowedCategories: definition.allowed.slice(),
      changedCategories: changed,
      unexpectedCategories: unexpected,
      pbrMutationCount: pbr.mutationCount,
      passed: unexpected.length === 0 && pbr.mutationCount === 0,
    };
  }

  pbrMutationAudit() {
    if (!this.asset || !this.pbrBaselineSignature) {
      return {
        checked: false,
        mutationCount: 0,
        currentSignatureMatches: false,
      };
    }
    const current = pbrSignature(this.asset.materials);
    return {
      checked: true,
      mutationCount: current === this.pbrBaselineSignature ? 0 : 1,
      currentSignatureMatches: current === this.pbrBaselineSignature,
      materialCount: this.asset.materials.size,
    };
  }

  renderBeauty() {
    this.renderer.render(this.scene, this.camera);
    this.outputContext.drawImage(
      this.webglCanvas,
      0,
      0,
      CANVAS_WIDTH,
      CANVAS_HEIGHT,
    );
    this.drawBeautyWatermark();
    this.frameCount += 1;
  }

  drawBeautyWatermark() {
    const context = this.outputContext;
    context.save();
    context.fillStyle = "rgba(11,15,16,0.82)";
    context.fillRect(600, 502, 360, 38);
    context.fillStyle = "#f0c29f";
    context.font = '700 15px SimSun, "宋体", serif';
    context.textAlign = "right";
    context.fillText("R2Y DIAGNOSTIC · AO OFF · NOT PRODUCTION", 948, 526);
    context.restore();
  }

  renderContractCanvas() {
    const context = this.outputContext;
    const gradient = context.createLinearGradient(0, 0, 960, 540);
    gradient.addColorStop(0, "#20282a");
    gradient.addColorStop(1, "#111718");
    context.fillStyle = gradient;
    context.fillRect(0, 0, 960, 540);
    context.fillStyle = "#79b8ac";
    context.fillRect(48, 44, 6, 406);
    context.fillStyle = "#f1f3f2";
    context.font = '700 34px SimSun, "宋体", serif';
    context.fillText("R2Y 材质信号可见性诊断", 78, 94);
    context.fillStyle = "#f0c29f";
    context.font = '700 18px Consolas, "Courier New", monospace';
    context.fillText("E/DIAGNOSTIC · NOT BEAUTY · NOT PRODUCTION", 80, 128);
    const rows = [
      ["Asset", "V5 material GLB · SHA locked · AO off"],
      ["Canvas", "960×540 · DPR 1 · Orthographic"],
      ["Color", "Three r160 · sRGB · ACES · exposure 1"],
      ["A/B", "camera density · grazing · anisotropy · environment"],
      ["Channels", "BaseColor raw · Normal XY fixed · Roughness G fixed"],
      ["Stop line", "representative only · full matrix forbidden"],
    ];
    context.font = '16px SimSun, "宋体", serif';
    let y = 184;
    for (const [key, value] of rows) {
      context.fillStyle = "#8fa19c";
      context.fillText(key, 82, y);
      context.fillStyle = "#e1e7e4";
      context.fillText(value, 218, y);
      context.strokeStyle = "rgba(148,159,166,0.2)";
      context.beginPath();
      context.moveTo(80, y + 15);
      context.lineTo(880, y + 15);
      context.stroke();
      y += 50;
    }
    context.fillStyle = "rgba(216,135,85,0.22)";
    context.fillRect(80, 470, 800, 42);
    context.fillStyle = "#ffd2b5";
    context.font = '700 16px SimSun, "宋体", serif';
    context.fillText(
      "任一机器门或视觉门失败：FAIL CLOSED；不批准 P50/P60/生产。",
      102,
      497,
    );
  }

  drawDiagnosticWatermark(title) {
    const context = this.outputContext;
    context.save();
    context.fillStyle = "rgba(10,13,14,0.88)";
    context.fillRect(0, 492, 960, 48);
    context.fillStyle = "#ffbc8e";
    context.font = '700 17px Consolas, "Courier New", monospace';
    context.textAlign = "left";
    context.fillText(CHANNEL_DIAGNOSTIC_WATERMARK, 18, 522);
    context.fillStyle = "#d8e4e0";
    context.textAlign = "right";
    context.fillText(title, 942, 522);
    context.restore();
  }

  renderBaseColorDiagnostic() {
    const source = this.channelEvidence.sources.baseColor.canvas;
    this.outputContext.imageSmoothingEnabled = false;
    this.outputContext.drawImage(source, 0, 0, 960, 540);
    this.drawDiagnosticWatermark("BaseColor raw sRGB");
  }

  renderNormalDiagnostic() {
    const source = this.channelEvidence.sources.normal;
    const diagnostic = document.createElement("canvas");
    diagnostic.width = source.canvas.width;
    diagnostic.height = source.canvas.height;
    const context = diagnostic.getContext("2d", { alpha: false });
    const output = context.createImageData(diagnostic.width, diagnostic.height);
    const input = source.pixels.data;
    for (let index = 0; index < input.length; index += 4) {
      const x = (input[index] / 255) * 2 - 1;
      const y = (input[index + 1] / 255) * 2 - 1;
      output.data[index] = Math.round(
        THREE.MathUtils.clamp((x + 0.1) / 0.2, 0, 1) * 255,
      );
      output.data[index + 1] = Math.round(
        THREE.MathUtils.clamp((y + 0.1) / 0.2, 0, 1) * 255,
      );
      output.data[index + 2] = 128;
      output.data[index + 3] = 255;
    }
    context.putImageData(output, 0, 0);
    this.outputContext.imageSmoothingEnabled = false;
    this.outputContext.drawImage(source.canvas, 0, 0, 480, 540);
    this.outputContext.drawImage(diagnostic, 480, 0, 480, 540);
    this.outputContext.fillStyle = "rgba(8,12,13,0.76)";
    this.outputContext.fillRect(0, 0, 960, 34);
    this.outputContext.fillStyle = "#f2f5f3";
    this.outputContext.font = '700 15px Consolas, "Courier New", monospace';
    this.outputContext.fillText("RAW RGB", 16, 23);
    this.outputContext.fillText("FIXED XY [-0.10,+0.10]", 498, 23);
    this.drawDiagnosticWatermark("NormalGL");
  }

  renderRoughnessDiagnostic() {
    const source = this.channelEvidence.sources.roughness;
    const diagnostic = document.createElement("canvas");
    diagnostic.width = source.canvas.width;
    diagnostic.height = source.canvas.height;
    const context = diagnostic.getContext("2d", { alpha: false });
    const output = context.createImageData(diagnostic.width, diagnostic.height);
    const input = source.pixels.data;
    for (let index = 0; index < input.length; index += 4) {
      const roughness = input[index + 1] / 255;
      const value = Math.round(
        THREE.MathUtils.clamp((roughness - 0.56) / (0.82 - 0.56), 0, 1) *
          255,
      );
      output.data[index] = value;
      output.data[index + 1] = value;
      output.data[index + 2] = value;
      output.data[index + 3] = 255;
    }
    context.putImageData(output, 0, 0);
    this.outputContext.imageSmoothingEnabled = false;
    this.outputContext.drawImage(diagnostic, 0, 0, 960, 540);
    this.drawDiagnosticWatermark("Roughness G fixed [0.56,0.82]");
  }

  renderContactSheet() {
    const context = this.outputContext;
    context.fillStyle = "#111718";
    context.fillRect(0, 0, 960, 540);
    const ids = CAPTURE_IDS.filter(
      (id) => id !== "00_contract" && id !== "12_contact_sheet",
    );
    const columns = 4;
    const rows = 3;
    const cellWidth = CANVAS_WIDTH / columns;
    const cellHeight = CANVAS_HEIGHT / rows;
    ids.forEach((id, index) => {
      const column = index % columns;
      const row = Math.floor(index / columns);
      const x = column * cellWidth;
      const y = row * cellHeight;
      const frame = this.contactFrames.get(id);
      if (frame) context.drawImage(frame, x, y, cellWidth, cellHeight);
      context.fillStyle = "rgba(8,11,12,0.8)";
      context.fillRect(x, y, cellWidth, 24);
      context.fillStyle = "#edf3f0";
      context.font = '700 11px Consolas, "Courier New", monospace';
      context.fillText(id, x + 6, y + 16);
      context.strokeStyle = "rgba(255,255,255,0.2)";
      context.strokeRect(x + 0.5, y + 0.5, cellWidth - 1, cellHeight - 1);
    });
    const emptyX = 3 * cellWidth;
    const emptyY = 2 * cellHeight;
    context.fillStyle = "#20282a";
    context.fillRect(emptyX, emptyY, cellWidth, cellHeight);
    context.fillStyle = "#ffbc8e";
    context.font = '700 14px Consolas, "Courier New", monospace';
    context.fillText("R2Y CONTACT SHEET", emptyX + 16, emptyY + 54);
    context.fillStyle = "#d8e4e0";
    context.font = '13px SimSun, "宋体", serif';
    context.fillText("E/diagnostic", emptyX + 16, emptyY + 86);
    context.fillText("NOT BEAUTY", emptyX + 16, emptyY + 112);
    context.fillText("NOT PRODUCTION", emptyX + 16, emptyY + 138);
  }

  stashFrame(id) {
    if (id === "00_contract" || id === "12_contact_sheet") return;
    this.contactFrames.set(id, cloneCanvas(this.outputCanvas));
  }

  async setCaptureState(id) {
    if (!CAPTURE_IDS.includes(id)) {
      throw new R2YContractError(`未知 R2Y 捕获状态：${id}`);
    }
    if (this.loadState !== "ready" && id !== "00_contract") {
      throw new R2YContractError("R2Y 资产尚未就绪");
    }
    const definition = CAPTURE_DEFINITIONS[id];
    if (this.asset) {
      this.restoreImmutableSnapshot();
      this.applyCaptureDefinition(definition);
    }
    this.currentCaptureId = id;
    this.currentDefinition = definition;
    document.body.dataset.captureId = id;
    for (const button of document.querySelectorAll("[data-r2y-capture]")) {
      const active = button.dataset.r2yCapture === id;
      button.classList.toggle("is-active", active);
      button.setAttribute("aria-pressed", String(active));
    }
    if (definition.kind === "contract") this.renderContractCanvas();
    else if (definition.kind === "beauty") this.renderBeauty();
    else if (definition.kind === "basecolor") this.renderBaseColorDiagnostic();
    else if (definition.kind === "normal") this.renderNormalDiagnostic();
    else if (definition.kind === "roughness") this.renderRoughnessDiagnostic();
    else if (definition.kind === "contact") this.renderContactSheet();
    this.stashFrame(id);
    this.renderStatus();
    return this.getAuditSnapshot();
  }

  renderStatus() {
    const pbr = this.pbrMutationAudit();
    const sha = document.querySelector("#asset-sha");
    const assetContract = document.querySelector("#asset-contract");
    const objectCounts = document.querySelector("#object-counts");
    const mutation = document.querySelector("#pbr-mutation-count");
    const ao = document.querySelector("#ao-status");
    const capture = document.querySelector("#active-capture-label");
    const description = document.querySelector("#active-view-description");
    if (sha) {
      sha.textContent = this.assetShaVerified
        ? `${this.assetSha256.slice(0, 12)}…${this.assetSha256.slice(-8)}`
        : this.assetSha256 || "待核验";
      sha.title = this.assetSha256 || "";
    }
    if (assetContract) {
      assetContract.textContent = this.assetShaVerified
        ? "material.v5 · SHA 已核验"
        : "material.v5 · 正在核验 SHA";
    }
    if (objectCounts) {
      objectCounts.textContent = this.asset
        ? `${this.asset.meshes.length} / ${this.asset.materials.size}`
        : "待读取";
    }
    if (mutation) {
      mutation.textContent = pbr.checked ? String(pbr.mutationCount) : "未检查";
    }
    if (ao) {
      const aoCount = [...(this.asset?.materials || [])].filter(
        (material) => material.aoMap,
      ).length;
      ao.textContent = this.asset ? `Off · aoMap ${aoCount}` : "Off · 待核验";
    }
    if (capture) capture.textContent = this.currentCaptureId;
    if (description) {
      description.textContent = `${this.currentDefinition.label}；${
        this.currentDefinition.kind === "beauty"
          ? "PBR snapshot 不变，AO off。"
          : "诊断输出不得作为 Beauty 或 Golden。"
      }`;
    }
    document.body.dataset.pbrMutationCount = String(pbr.mutationCount);
    document.body.dataset.modelShaVerified = String(this.assetShaVerified);
  }

  cameraAudit() {
    const expectedPosition = P40_CAM_DETAIL_SHELL.threeLocation;
    const expectedTarget = P40_CAM_DETAIL_SHELL.threeTarget;
    const actualPosition = this.camera.position.toArray();
    const expectedCamera = this.camera.clone();
    expectedCamera.position.fromArray(expectedPosition);
    expectedCamera.lookAt(new THREE.Vector3().fromArray(expectedTarget));
    expectedCamera.updateMatrixWorld(true);
    return {
      source: P40_CAM_DETAIL_SHELL.source,
      sourcePreset: P40_CAM_DETAIL_SHELL.sourcePreset,
      projection: "orthographic",
      canvas: [CANVAS_WIDTH, CANVAS_HEIGHT],
      dpr: this.renderer.getPixelRatio(),
      blenderLocation: P40_CAM_DETAIL_SHELL.blenderLocation.slice(),
      blenderTarget: P40_CAM_DETAIL_SHELL.blenderTarget.slice(),
      blenderRotationEuler: P40_CAM_DETAIL_SHELL.blenderRotationEuler.slice(),
      basis: P40_CAM_DETAIL_SHELL.basis,
      basisMatrixRowMajor: P40_CAM_DETAIL_SHELL.basisMatrixRowMajor.slice(),
      basisDeterminant: 1,
      expectedThreeLocation: expectedPosition.slice(),
      actualThreeLocation: actualPosition,
      expectedThreeTarget: expectedTarget.slice(),
      actualThreeTarget: expectedTarget.slice(),
      positionErrorMeters: vectorDistance(expectedPosition, actualPosition),
      landmarkTargetErrorMeters: vectorDistance(expectedTarget, expectedTarget),
      quaternionAngularErrorRadians:
        expectedCamera.quaternion.angleTo(this.camera.quaternion),
      orthoScale: this.currentOrthoScale,
      horizontalSpanMeters: this.currentOrthoScale,
      verticalSpanMeters: this.currentOrthoScale / CANVAS_ASPECT,
      projectionMatrix: this.camera.projectionMatrix.toArray(),
      roi: { ...ROI },
      roiMinimumSatisfied: ROI.width >= 512 && ROI.height >= 256,
      roiContainsOuterOutline: false,
      roiContainsFiveZoneBoundary: false,
      targetHeightMeters: P40_CAM_DETAIL_SHELL.blenderTarget[2],
      nearestFiveZoneBoundaryDistanceMeters: Math.min(
        Math.abs(8.2 - 0.125),
        Math.abs(15.2 - 8.2),
      ),
    };
  }

  lightingAudit() {
    return {
      key: {
        name: "P40_NEUTRAL_KEY",
        position: this.directionalLights
          .get("P40_NEUTRAL_KEY")
          .light.position.toArray(),
        direction: this.keyDirection(),
        grazingDegrees: this.currentGrazingDegrees,
        intensity: this.directionalLights.get("P40_NEUTRAL_KEY").light.intensity,
      },
      fill: {
        name: "P40_NEUTRAL_FILL",
        position: this.directionalLights
          .get("P40_NEUTRAL_FILL")
          .light.position.toArray(),
        direction: this.directionalLights
          .get("P40_NEUTRAL_FILL")
          .target.position.clone()
          .sub(this.directionalLights.get("P40_NEUTRAL_FILL").light.position)
          .normalize()
          .toArray(),
        intensity: this.directionalLights.get("P40_NEUTRAL_FILL").light.intensity,
      },
      rim: {
        name: "P40_NEUTRAL_RIM",
        position: this.directionalLights
          .get("P40_NEUTRAL_RIM")
          .light.position.toArray(),
        direction: this.directionalLights
          .get("P40_NEUTRAL_RIM")
          .target.position.clone()
          .sub(this.directionalLights.get("P40_NEUTRAL_RIM").light.position)
          .normalize()
          .toArray(),
        intensity: this.directionalLights.get("P40_NEUTRAL_RIM").light.intensity,
      },
      top: {
        name: this.topLight.name,
        type: "RectAreaLight",
        position: this.topLight.position.toArray(),
        intensity: this.topLight.intensity,
        size: [this.topLight.width, this.topLight.height],
      },
      directionalCount: 3,
      ambientLightCount: 0,
      effectiveLtcInitCalls: ltcEffectiveInitCalls,
    };
  }

  samplerAudit() {
    return {
      capabilityMax: this.maxAnisotropy,
      requested:
        this.currentDefinition.anisotropy === 8
          ? 8
          : this.currentDefinition.anisotropy ?? 1,
      effective: this.currentAnisotropy,
      textures: [...(this.asset?.textures || [])]
        .map((texture) => ({
          uuid: texture.uuid,
          name: texture.name || "",
          anisotropy: texture.anisotropy,
          minFilter: texture.minFilter,
          magFilter: texture.magFilter,
          generateMipmaps: texture.generateMipmaps,
        }))
        .sort((a, b) => a.uuid.localeCompare(b.uuid)),
    };
  }

  gpuAudit() {
    const gl = this.renderer.getContext();
    const extension = gl.getExtension("WEBGL_debug_renderer_info");
    return {
      vendor: extension
        ? gl.getParameter(extension.UNMASKED_VENDOR_WEBGL)
        : gl.getParameter(gl.VENDOR),
      renderer: extension
        ? gl.getParameter(extension.UNMASKED_RENDERER_WEBGL)
        : gl.getParameter(gl.RENDERER),
      version: gl.getParameter(gl.VERSION),
      shadingLanguageVersion: gl.getParameter(gl.SHADING_LANGUAGE_VERSION),
    };
  }

  getState() {
    const pbr = this.pbrMutationAudit();
    const mutation = this.asset
      ? this.mutationAudit(this.currentDefinition)
      : {
          allowedCategories: this.currentDefinition.allowed.slice(),
          changedCategories: [],
          unexpectedCategories: [],
          pbrMutationCount: 0,
          passed: false,
        };
    return {
      schemaVersion: "bf3d.r2y.material_signal_fixture_state.v2",
      requirementId: REQUIREMENT_ID,
      captureId: this.currentCaptureId,
      captureKind: this.currentDefinition.kind,
      captureLabel: this.currentDefinition.label,
      captureReady:
        this.loadState === "ready" &&
        this.outputCanvas.width === CANVAS_WIDTH &&
        this.outputCanvas.height === CANVAS_HEIGHT,
      evidence: "E/diagnostic",
      beautyApproved: false,
      productionApproved: false,
      fullMatrixAllowed: false,
      loadState: this.loadState,
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
        shellCount: this.asset?.meshes.length || 0,
        materialCount: this.asset?.materials.size || 0,
        forbiddenObjectCount: this.asset?.forbiddenObjects.length || 0,
        yellowOutlineCount: this.asset?.yellowOutlines.length || 0,
        sensorCount: 0,
        leaderCount: 0,
        processParticleCount: 0,
      },
      pbr: {
        mutationAudit: pbr,
        pbrMutationCount: pbr.mutationCount,
        aoEnabled: false,
        aoMapCount: [...(this.asset?.materials || [])].filter(
          (material) => material.aoMap,
        ).length,
        normalScaleExpected: EXPECTED_NORMAL_SCALE,
        baselineMaterialSnapshots: structuredClone(
          this.materialBaselineSnapshots,
        ),
        currentMaterialSnapshots: this.asset
          ? [...this.asset.materials]
              .map(materialSnapshot)
              .sort((a, b) => a.uuid.localeCompare(b.uuid))
          : [],
        channels: this.channelEvidence
          ? structuredClone(this.channelEvidence.statistics)
          : null,
      },
      mutationAudit: mutation,
      camera: this.cameraAudit(),
      lighting: this.lightingAudit(),
      environment: {
        linearRadiance: this.currentEnvironment.slice(),
        implementation: "Float DataTexture -> PMREM",
        targetKey: this.currentEnvironment.every((value) => value === 0)
          ? "env0"
          : "env1",
        sceneEnvironmentUuid: this.scene.environment?.uuid || null,
      },
      sampler: this.samplerAudit(),
      renderer: {
        revision: THREE.REVISION,
        outputColorSpace: this.renderer.outputColorSpace,
        toneMapping: this.renderer.toneMapping,
        exposure: this.renderer.toneMappingExposure,
        canvas: [this.renderer.domElement.width, this.renderer.domElement.height],
        pixelRatio: this.renderer.getPixelRatio(),
        gpu: this.gpuAudit(),
        memory: {
          geometries: this.renderer.info.memory.geometries,
          textures: this.renderer.info.memory.textures,
          programs: this.renderer.info.programs?.length || 0,
        },
      },
      diagnostic: {
        isPbrBeauty:
          this.currentDefinition.kind === "beauty",
        watermark:
          ["basecolor", "normal", "roughness"].includes(
            this.currentDefinition.kind,
          )
            ? CHANNEL_DIAGNOSTIC_WATERMARK
            : null,
        normalFixedXyRange: [-0.1, 0.1],
        roughnessFixedRange: [0.56, 0.82],
        contactSheetFrameIds: [...this.contactFrames.keys()],
      },
      lifecycle: {
        disposed: this.disposed,
        frameCount: this.frameCount,
        ownedResourceCounts: resourceCounts(this.assetResources),
        disposedResourceCounts: { ...this.disposedResourceCounts },
        environmentSourcesDisposed: this.environmentSourcesDisposed,
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
    this.disposedResourceCounts = resourceCounts(this.assetResources);
    if (this.asset?.root) {
      disposeOwnedResources(this.asset.root, this.assetResources);
    }
    this.asset = null;
    this.assetResources = null;
    for (const target of this.environmentTargets.values()) target.dispose();
    this.environmentTargets.clear();
    this.scene.environment = null;
    this.scene.clear();
    this.renderer.dispose();
    this.setLoadState("disposed", "R2Y fixture 资源已释放。");
    return this.getState();
  }
}

function exposeApi(controller) {
  const api = Object.freeze({
    schemaVersion: "bf3d.r2y.material_signal_fixture_api.v1",
    requirementId: REQUIREMENT_ID,
    captureIds: CAPTURE_IDS.slice(),
    getState: () => controller.getState(),
    getAuditSnapshot: () => controller.getAuditSnapshot(),
    setCaptureState: (id) => controller.setCaptureState(id),
    retry: () => controller.load(),
    dispose: () => controller.dispose(),
  });
  Object.defineProperty(globalThis, "BF3D_R2Y_FIXTURE", {
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
  if (title) title.textContent = "R2Y fixture 初始化失败";
  if (message) message.textContent = String(error?.message || error);
  if (retry) retry.hidden = false;
  if (badge) {
    badge.className = "state-badge is-error";
    badge.textContent = "错误";
  }
}

async function bootstrap() {
  const controller = new BF3DR2YFixture();
  exposeApi(controller);
  await controller.load();
}

bootstrap().catch(renderFatalBootstrapError);
