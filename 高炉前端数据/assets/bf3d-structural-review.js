import * as THREE from "../libs/three/three.module.js";
import { installR2HDetailNormal } from "./r2h-detail-normal.js";

const REQUIREMENT_ID = "REQ-BF3D-STRUCTURAL-REVIEW-20260719";
const ASSET_ID = "GL02_STRUCTURAL_REVIEW_V3";
const OPERATIONAL_ASSET_URL =
  "models/gl02_blast_furnace_structural_review.v1.glb";
const REVIEW_ASSET_URL = "models/gl02_blast_furnace_review.v3.glb";
const LOOKDEV_PRESET_URL = "web/presets/lookdev_camera_v1.json";
const MATERIAL_GROUP_NAME = "BF3D_V3_MODE_MATERIAL";
const SECTION_GROUP_NAME = "BF3D_V3_MODE_SECTION";
const DETAIL_NORMAL_URL =
  "models/textures/INT30_R2H_DetailNormal_1K_OpenGL_plusY_low_strength_0_25.png";
const DETAIL_NORMAL_SHA256 =
  "86e14c20ccdd008d078acda4b9226b48ca83eeab31a5511db432771ed914f638";

const MODES = {
  operational: {
    label: "运行视图",
    description: "V1 运行资产与 115 个测点保持在线。",
  },
  material: {
    label: "纯材质审查",
    description: "V3 墙体材质剖面审查；隐藏测点、引线、轮廓和工艺粒子。",
  },
  structural: {
    label: "结构剖面",
    description: "V3 物理半剖实体；不使用运行时裁剪或双面材质。",
  },
};

const AUXILIARY_ROOT_PATTERNS = [
  /^GL02_LAYER_HIGHLIGHT_/,
  /^GL02_CUTAWAY_PROFILE_EDGES$/,
  /^BF3D_INTERNAL_SIMULATION_RUNTIME$/,
];

const FORBIDDEN_REVIEW_NAME_PATTERNS = [
  /^SENSOR_/,
  /^HIT_/,
  /CUTAWAY_PROFILE_EDGES/i,
  /PRESSURE_(?:LEADER|LINE)/i,
  /(?:BURDEN|TEMP).*RING/i,
  /STREAMLINE/i,
  /PROCESS_PARTICLE/i,
  /YELLOW_(?:PROFILE|OUTLINE)/i,
];

/* R2S_AUDIT_CONTRACT_BEGIN
 *
 * This block is intentionally numeric and read-only.  It does not construct a
 * renderer, replace the production PerspectiveCamera/OrbitControls, enter the
 * production RAF, or emit beauty/mask pixels.  Image capture remains
 * fail-closed until the AgX Medium Low equivalent and the photometric mapping
 * have separate pre-approval.
 */
const R2S_REQUIREMENT_ID =
  "REQ-BF3D-R2S-RENDERER-CONTRACT-ALIGNMENT-20260720";
const R2S_STAGE_ID = "WEB-60_R2S";
const R2S_GATE_VALUE = "WEB-60_R2S";
const R2S_QUERY_GATE_NAME = "bf3d_test_capture";
const R2S_WINDOW_TOKEN_NAME = "__BF3D_TEST_CAPTURE_TOKEN__";
const R2S_COLOR_STATE = "pending_preapproval";
const R2S_PHOTOMETRY_STATE = "pending_preapproval";
const R2S_COORDINATE_BASIS = "(x,y,z)->(x,z,-y)";

function deepFreezeAuditValue(value) {
  if (!value || typeof value !== "object" || Object.isFrozen(value)) {
    return value;
  }
  for (const nested of Object.values(value)) {
    deepFreezeAuditValue(nested);
  }
  return Object.freeze(value);
}

function resolveR2SAuditGateAtModuleLoad() {
  let queryValueMatches = false;
  let queryValueCount = 0;
  try {
    const values = new URLSearchParams(window.location.search).getAll(
      R2S_QUERY_GATE_NAME,
    );
    queryValueCount = values.length;
    queryValueMatches =
      values.length === 1 && values[0] === R2S_GATE_VALUE;
  } catch {
    queryValueMatches = false;
  }
  const windowTokenPreInjected = Object.prototype.hasOwnProperty.call(
    window,
    R2S_WINDOW_TOKEN_NAME,
  );
  const windowTokenMatches =
    windowTokenPreInjected &&
    window[R2S_WINDOW_TOKEN_NAME] === R2S_GATE_VALUE;
  return deepFreezeAuditValue({
    evaluatedAtModuleLoad: true,
    query: {
      name: R2S_QUERY_GATE_NAME,
      expectedValue: R2S_GATE_VALUE,
      valueCount: queryValueCount,
      matches: queryValueMatches,
    },
    preInjectedWindowToken: {
      name: R2S_WINDOW_TOKEN_NAME,
      expectedValue: R2S_GATE_VALUE,
      wasPresent: windowTokenPreInjected,
      matches: windowTokenMatches,
    },
    enabled: queryValueMatches && windowTokenMatches,
  });
}

const R2S_AUDIT_GATE = resolveR2SAuditGateAtModuleLoad();

const R2R_FROZEN_SECTION_BOUNDS_BLENDER = deepFreezeAuditValue({
  minimum: [
    -4.460000038146973,
    -4.450119495391846,
    -20.0,
  ],
  maximum: [
    -0.28433388471603394,
    4.450119495391846,
    20.0,
  ],
});

const R2R_SHOT_FORMULAS = deepFreezeAuditValue({
  standard_ortho_section_1x:
    "location=(max.x+1.8*max(height,width),center.y,center.z); target=center; ortho=max(1.05*height,1.22*width)",
  local_layer_closeup_1x:
    "target=(max.x,max.y-max(0.035*width,0.35),min.z+0.58*height); location=(max.x+1.8*max(height,width),center.y,target.z); ortho=max(3.6,0.24*width)",
  six_family_material_board_with_midgray:
    "orthographic camera on +X looking at origin; scale=9.6; six 1.25 m icospheres use the locked R2Q material datablocks and a neutral midgray block is centered below them",
});

const R2R_COMPARISON_THRESHOLDS = deepFreezeAuditValue({
  silhouette_iou_min: 0.995,
  symmetric_edge_distance_p95_px_max: 3.0,
  camera_matrix_and_projection_abs_max: 1e-6,
  light_position_direction_color_abs_max: 1e-4,
  projection_control_point_error_px_max: 4.0,
  midgray_median_delta_e_00_max: 3.0,
  material_family_roi_median_delta_e_00_max: 5.0,
  material_family_roi_p95_delta_e_00_max: 10.0,
  material_family_roi_median_relative_luminance_diff_max: 0.08,
  material_board_luminance_ssim_min: 0.9,
  structural_internal_roi_luminance_ssim_min: 0.85,
  repeatability_changed_pixel_threshold: 0.00784313725490196,
  repeatability_changed_pixel_ratio_max: 0.01,
});

const R2R_P40_LIGHTS_BLENDER = deepFreezeAuditValue([
  {
    name: "P40_NEUTRAL_KEY",
    blenderType: "SUN",
    threeType: "DirectionalLight",
    position: [
      46.1323356628418,
      -46.1323356628418,
      49.166168212890625,
    ],
    direction: [
      -0.577350378036499,
      0.5773506164550781,
      -0.5773500204086304,
    ],
    colorLinearRgb: [1.0, 1.0, 1.0],
    sourceEnergy: 2.25,
    sunAngleRad: 0.13962633907794952,
  },
  {
    name: "P40_NEUTRAL_FILL",
    blenderType: "SUN",
    threeType: "DirectionalLight",
    position: [
      -46.1323356628418,
      -11.53308391571045,
      19.18014907836914,
    ],
    direction: [
      0.9186304807662964,
      0.22965724766254425,
      -0.32152092456817627,
    ],
    colorLinearRgb: [
      0.9599999785423279,
      0.9800000190734863,
      1.0,
    ],
    sourceEnergy: 1.0499999523162842,
    sunAngleRad: 0.13962633907794952,
  },
  {
    name: "P40_NEUTRAL_RIM",
    blenderType: "SUN",
    threeType: "DirectionalLight",
    position: [
      11.53308391571045,
      46.1323356628418,
      49.166168212890625,
    ],
    direction: [
      -0.1740776151418686,
      -0.6963106989860535,
      -0.6963106393814087,
    ],
    colorLinearRgb: [
      0.8999999761581421,
      0.949999988079071,
      1.0,
    ],
    sourceEnergy: 1.350000023841858,
    sunAngleRad: 0.13962633907794952,
  },
  {
    name: "P40_NEUTRAL_TOP",
    blenderType: "AREA",
    blenderShape: "DISK",
    threeType: "RectAreaLight",
    position: [0.0, 0.0, 60.69925308227539],
    direction: [0.0, 0.0, -1.0],
    colorLinearRgb: [1.0, 1.0, 1.0],
    sourceEnergy: 3921.24853515625,
    diskDiameterM: 34.59925079345703,
  },
]);

function finiteAuditNumber(value, label) {
  const number = Number(value);
  if (!Number.isFinite(number)) {
    throw new TypeError(`R2S audit numeric contract is invalid: ${label}`);
  }
  return number;
}

function mapBlenderVectorToThree(vector) {
  const x = finiteAuditNumber(vector?.[0], "basis.x");
  const y = finiteAuditNumber(vector?.[1], "basis.y");
  const z = finiteAuditNumber(vector?.[2], "basis.z");
  const mappedZ = -y;
  return [x, z, Object.is(mappedZ, -0) ? 0 : mappedZ];
}

function addAuditVectors(a, b) {
  return [
    finiteAuditNumber(a?.[0], "vector_a.x") +
      finiteAuditNumber(b?.[0], "vector_b.x"),
    finiteAuditNumber(a?.[1], "vector_a.y") +
      finiteAuditNumber(b?.[1], "vector_b.y"),
    finiteAuditNumber(a?.[2], "vector_a.z") +
      finiteAuditNumber(b?.[2], "vector_b.z"),
  ];
}

function buildR2SP40LightMapping() {
  return R2R_P40_LIGHTS_BLENDER.map((source) => {
    const threePosition = mapBlenderVectorToThree(source.position);
    const threeDirection = mapBlenderVectorToThree(source.direction);
    const result = {
      name: source.name,
      blender: {
        type: source.blenderType,
        shape: source.blenderShape || null,
        position: source.position.slice(),
        direction: source.direction.slice(),
        colorLinearRgb: source.colorLinearRgb.slice(),
        energy: source.sourceEnergy,
        sunAngleRad: source.sunAngleRad ?? null,
        diskDiameterM: source.diskDiameterM ?? null,
      },
      three: {
        type: source.threeType,
        position: threePosition,
        direction: threeDirection,
        target: addAuditVectors(threePosition, threeDirection),
        colorLinearRgb: source.colorLinearRgb.slice(),
        intensity: null,
        intensityMappingState: R2S_PHOTOMETRY_STATE,
        sunAngleMappingState:
          source.blenderType === "SUN"
            ? R2S_PHOTOMETRY_STATE
            : "not_applicable",
      },
      coordinateMapping: {
        formula: R2S_COORDINATE_BASIS,
        sourcePosition: source.position.slice(),
        mappedPosition: threePosition.slice(),
        sourceDirection: source.direction.slice(),
        mappedDirection: threeDirection.slice(),
      },
    };
    if (source.name === "P40_NEUTRAL_TOP") {
      const sourceRadius = source.diskDiameterM * 0.5;
      const equalAreaM2 = Math.PI * sourceRadius * sourceRadius;
      const equalAreaSquareSideM = Math.sqrt(equalAreaM2);
      result.three.equalAreaSquareProxy = {
        implementation: "THREE.RectAreaLight",
        sourceShape: "DISK",
        sourceDiskDiameterM: source.diskDiameterM,
        sourceDiskAreaM2: equalAreaM2,
        widthM: equalAreaSquareSideM,
        heightM: equalAreaSquareSideM,
        equalArea: true,
        limitations: [
          "equal emitting area only; disk and square edge silhouettes differ",
          "angular emission and edge falloff equivalence is not approved",
          "Blender AREA power does not map directly to Three intensity",
        ],
      };
    }
    return result;
  });
}

function orthographicFrustum(horizontalScale) {
  const scale = finiteAuditNumber(horizontalScale, "ortho_scale");
  const aspect = 1920 / 1080;
  return {
    left: -scale / 2,
    right: scale / 2,
    top: scale / (2 * aspect),
    bottom: -scale / (2 * aspect),
    near: 0.05,
    far: 1000.0,
  };
}

function buildR2SShot(
  id,
  formula,
  blenderLocation,
  blenderTarget,
  orthoScale,
  options = {},
) {
  return {
    id,
    formula,
    fixedSeed: 20260719,
    actualAssetGeometry: options.actualAssetGeometry !== false,
    diagnosticOnly: options.diagnosticOnly === true,
    thicknessScale:
      options.actualAssetGeometry === false ? null : 1.0,
    camera: {
      objectName: "CAM_R2Q_SECTION_ORTHO_CANDIDATE",
      blenderType: "ORTHO",
      threeImplementation: "THREE.OrthographicCamera",
      independentFromProductionCamera: true,
      blender: {
        location: blenderLocation.slice(),
        target: blenderTarget.slice(),
        horizontalOrthoScale: orthoScale,
      },
      three: {
        location: mapBlenderVectorToThree(blenderLocation),
        target: mapBlenderVectorToThree(blenderTarget),
        up: [0.0, 1.0, 0.0],
        horizontalOrthoScale: orthoScale,
        frustum: orthographicFrustum(orthoScale),
      },
    },
  };
}

function buildEnabledR2SAuditShotManifest() {
  const minimum = R2R_FROZEN_SECTION_BOUNDS_BLENDER.minimum;
  const maximum = R2R_FROZEN_SECTION_BOUNDS_BLENDER.maximum;
  const center = [
    Math.fround((minimum[0] + maximum[0]) / 2),
    Math.fround((minimum[1] + maximum[1]) / 2),
    Math.fround((minimum[2] + maximum[2]) / 2),
  ];
  const height = maximum[2] - minimum[2];
  const width = maximum[1] - minimum[1];
  const maximumSpan = Math.max(height, width);
  const standardLocation = [
    Math.fround(maximum[0] + 1.8 * maximumSpan),
    center[1],
    center[2],
  ];
  const standardOrthoScale = Math.max(
    1.05 * height,
    1.22 * width,
  );
  const localTarget = [
    maximum[0],
    Math.fround(
      maximum[1] - Math.max(0.035 * width, 0.35),
    ),
    Math.fround(minimum[2] + 0.58 * height),
  ];
  const localLocation = [
    standardLocation[0],
    center[1],
    localTarget[2],
  ];
  const localOrthoScale = Math.max(3.6, 0.24 * width);

  return deepFreezeAuditValue({
    schemaVersion: "bf3d.web.r2s.audit_shot_manifest.v1",
    requirementId: R2S_REQUIREMENT_ID,
    stageId: R2S_STAGE_ID,
    auditMode: true,
    readOnly: true,
    deterministic: true,
    captureEligible: false,
    colorState: R2S_COLOR_STATE,
    resolutionCssPixels: [1920, 1080],
    devicePixelRatio: 1,
    coordinateMapping: R2S_COORDINATE_BASIS,
    boundsSource:
      "locked R2R capture_manifest section geometry; never runtime Box3",
    frozenSectionBoundsBlender: {
      minimum: minimum.slice(),
      maximum: maximum.slice(),
      center,
      height,
      width,
    },
    shots: [
      buildR2SShot(
        "standard_ortho_section_1x",
        R2R_SHOT_FORMULAS.standard_ortho_section_1x,
        standardLocation,
        center,
        standardOrthoScale,
      ),
      buildR2SShot(
        "local_layer_closeup_1x",
        R2R_SHOT_FORMULAS.local_layer_closeup_1x,
        localLocation,
        localTarget,
        localOrthoScale,
      ),
      buildR2SShot(
        "six_family_material_board_with_midgray",
        R2R_SHOT_FORMULAS.six_family_material_board_with_midgray,
        [12.0, 0.0, 0.0],
        [0.0, 0.0, 0.0],
        9.6,
        {
          actualAssetGeometry: false,
          diagnosticOnly: true,
        },
      ),
    ],
    imageCapture: {
      apiExposed: false,
      captureAttempted: false,
      beautyFiles: [],
      maskFiles: [],
      blocker: "color_management_preapproval_required",
    },
  });
}

function buildEnabledR2SAuditContract() {
  return deepFreezeAuditValue({
    schemaVersion: "bf3d.web.r2s.audit_capture_contract.v1",
    requirementId: R2S_REQUIREMENT_ID,
    stageId: R2S_STAGE_ID,
    auditMode: true,
    testOnly: true,
    readOnly: true,
    captureEligible: false,
    colorState: R2S_COLOR_STATE,
    resolutionCssPixels: [1920, 1080],
    devicePixelRatio: 1,
    fileFormat: "PNG",
    colorMode: "RGBA",
    transparentFilm: true,
    fixedSeed: 20260719,
    repeatCount: 2,
    camera: {
      objectName: "CAM_R2Q_SECTION_ORTHO_CANDIDATE",
      blenderType: "ORTHO",
      threeImplementation: "THREE.OrthographicCamera",
      independentFromProductionCamera: true,
      productionCameraReferenceUsed: false,
      runtimeBoundsUsed: false,
      coordinateMapping: R2S_COORDINATE_BASIS,
      shotFormulas: {
        ...R2R_SHOT_FORMULAS,
      },
    },
    lights: {
      requiredCount: 4,
      requiredNames: R2R_P40_LIGHTS_BLENDER.map(
        (light) => light.name,
      ),
      coordinateMapping: R2S_COORDINATE_BASIS,
      dynamicBoundsFocusUsed: false,
      productionLightsReplaced: false,
      photometryState: R2S_PHOTOMETRY_STATE,
      items: buildR2SP40LightMapping(),
      worldReference: {
        colorLinearRgba: [0.12, 0.12, 0.12, 1.0],
        strength: 0.72,
        threeMappingState: R2S_PHOTOMETRY_STATE,
        ambientLightSubstitutionApproved: false,
      },
    },
    colorManagement: {
      colorState: R2S_COLOR_STATE,
      captureEligible: false,
      blenderReference: {
        viewTransform: "AgX",
        look: "AgX - Medium Low Contrast",
        exposureEv: 0.0,
      },
      productionRendererUnchanged: {
        toneMapping: "THREE.ACESFilmicToneMapping",
        toneMappingExposure: 1.05,
        outputColorSpace: "THREE.SRGBColorSpace",
      },
      approvedEquivalentCurveOrLut: null,
      threeBuiltInAgxDefaultContrastIsApprovedEquivalent: false,
      blocker:
        "AgX Medium Low equivalent curve/LUT is not pre-approved",
    },
    comparisonThresholds: {
      ...R2R_COMPARISON_THRESHOLDS,
    },
    comparisonContract: {
      maskThreshold: 0.5,
      interiorErosionPixels: 2,
      comparisonColorSpace:
        "sRGB PNG decoded to float; luminance uses IEC sRGB linearization; DeltaE00 uses CIE Lab D65",
      thresholds: {
        ...R2R_COMPARISON_THRESHOLDS,
      },
      aggregation:
        "every applicable shot, every material-family ROI and every repeatability check must pass; no averaging may hide a failed shot or family",
      notEvaluatedPolicy:
        "any required threshold marked not_evaluated prevents a complete A/B PASS",
      missingOrInvalidInputPolicy: "fail_closed",
      thresholdChangeAfterCaptureForbidden: true,
    },
    thresholdChangeAllowed: false,
    aggregation:
      "every applicable shot, material-family ROI and repeatability check must pass independently",
    notEvaluatedPolicy:
      "any required threshold marked not_evaluated prevents a complete A/B PASS",
    productionIsolation: {
      productionCameraType: "THREE.PerspectiveCamera",
      productionControlsType: "OrbitControls",
      productionRendererOwnership: "main viewer",
      productionRafOwnership: "main viewer requestAnimationFrame",
      productionToneMapping: "THREE.ACESFilmicToneMapping",
      productionToneMappingExposure: 1.05,
      formalGlb: {
        path: "models/gl02_blast_furnace.glb",
        bytes: 4314736,
        sha256:
          "808960f1b2703e7fb27df35f1b1b1a17063b9b10d2267acba593fc3872b62af6",
      },
      mutableReferencesShared: false,
      mutationsPerformed: false,
    },
  });
}

export function buildR2SAuditShotManifest() {
  if (!R2S_AUDIT_GATE.enabled) {
    return deepFreezeAuditValue({
      schemaVersion: "bf3d.web.r2s.audit_shot_manifest.v1",
      requirementId: R2S_REQUIREMENT_ID,
      stageId: R2S_STAGE_ID,
      auditMode: false,
      readOnly: true,
      deterministic: true,
      captureEligible: false,
      colorState: R2S_COLOR_STATE,
      shots: [],
      imageCapture: {
        apiExposed: false,
        captureAttempted: false,
        beautyFiles: [],
        maskFiles: [],
        blocker: "dual_test_gate_not_satisfied",
      },
    });
  }
  return buildEnabledR2SAuditShotManifest();
}

export function getR2SAuditCaptureCapability() {
  const auditMode = R2S_AUDIT_GATE.enabled;
  return deepFreezeAuditValue({
    schemaVersion: "bf3d.web.r2s.audit_capture_capability.v1",
    requirementId: R2S_REQUIREMENT_ID,
    stageId: R2S_STAGE_ID,
    auditMode,
    testOnly: true,
    readOnly: true,
    captureEligible: false,
    colorState: R2S_COLOR_STATE,
    numericManifestAvailable: auditMode,
    imageCaptureAvailable: false,
    beautyCaptureAvailable: false,
    maskCaptureAvailable: false,
    gates: R2S_AUDIT_GATE,
    blockers: [
      ...(auditMode ? [] : ["dual_test_gate_not_satisfied"]),
      "color_management_preapproval_required",
      "light_photometry_preapproval_required",
    ],
    auditContract: auditMode ? buildEnabledR2SAuditContract() : null,
    shotManifest: auditMode
      ? buildEnabledR2SAuditShotManifest()
      : null,
  });
}
/* R2S_AUDIT_CONTRACT_END */

function normalizeName(name) {
  return String(name || "").replace(/\.\d{3}$/, "");
}

function isRenderable(object) {
  return Boolean(
    object?.isMesh ||
      object?.isLine ||
      object?.isLineSegments ||
      object?.isPoints ||
      object?.isSprite,
  );
}

function materialList(object) {
  if (!object?.material) return [];
  return (Array.isArray(object.material)
    ? object.material
    : [object.material]
  ).filter(Boolean);
}

function uniqueMaterials(root) {
  const result = new Set();
  root?.traverse?.((object) => {
    materialList(object).forEach((material) => result.add(material));
  });
  return result;
}

function renderableDescendants(root) {
  const result = [];
  root?.traverse?.((object) => {
    if (isRenderable(object)) result.push(object);
  });
  return result;
}

function logicalReviewDescendants(root, mode) {
  const result = [];
  root?.traverse?.((object) => {
    if (String(object?.userData?.bf3d_review_mode || "") !== mode) return;
    if (
      String(object?.parent?.userData?.bf3d_review_mode || "") === mode
    ) {
      return;
    }
    if (mode === "section" && object.parent && object.parent !== root) {
      // Section exports carry the same review tag on the wrapper and the
      // inner mesh. Count only the top-most tagged object so one physical
      // unit is not double-counted as two logical review objects.
      const parentTagged = String(
        object.parent?.userData?.bf3d_review_mode || "",
      );
      if (parentTagged === mode) return;
    }
    if (String(object?.userData?.bf3d_review_mode || "") === mode) {
      result.push(object);
    }
  });
  return result;
}

function copyVector(value) {
  return value?.clone?.() || null;
}

function createPanel(stage) {
  const panel = document.createElement("section");
  panel.className = "bf3d-review-panel";
  panel.dataset.reviewLoadState = "idle";
  panel.setAttribute("aria-label", "高炉三维审查模式");
  panel.setAttribute("aria-busy", "false");
  panel.innerHTML = `
    <div class="bf3d-review-head">
      <strong>三维审查</strong>
      <span data-review-asset>V3 尚未加载</span>
    </div>
    <div class="bf3d-review-actions" role="group" aria-label="选择三维显示模式">
      <button type="button" data-review-mode="operational">运行视图</button>
      <button type="button" data-review-mode="material">纯材质审查</button>
      <button type="button" data-review-mode="structural">结构剖面</button>
    </div>
    <div class="bf3d-review-status" aria-live="polite">
      <b data-review-label>运行视图</b>
      <span data-review-description>V1 运行资产与 115 个测点保持在线。</span>
    </div>
    <div class="bf3d-review-recovery" data-review-recovery hidden>
      <button type="button" data-review-retry>重试加载</button>
      <button type="button" data-review-dismiss>返回运行视图</button>
    </div>
    <div class="bf3d-review-legend" data-review-legend hidden>
      <span><i class="steel"></i>R2J 五区实体钢壳</span>
      <span><i class="backfill"></i>40 mm 背衬填料</span>
      <span><i class="copper"></i>铜冷却壁</span>
      <span><i class="castiron"></i>铸铁冷却壁</span>
      <span><i class="hotface"></i>热面嵌入层</span>
      <span><i class="refractory"></i>残余耐火层</span>
      <small>全部材质和厚度为 E / REF-PENDING / illustrative，非施工数据。</small>
      <div class="bf3d-review-camera-actions" role="group" aria-label="结构剖面相机">
        <button type="button" data-review-camera="global">全炉剖面</button>
        <button type="button" data-review-camera="layer-detail">层材质近景</button>
      </div>
    </div>
  `;
  stage.appendChild(panel);
  return panel;
}

function snapshotCamera(viewer) {
  const camera = viewer.camera;
  const controls = viewer.controls;
  return {
    position: camera.position.clone(),
    quaternion: camera.quaternion.clone(),
    up: camera.up.clone(),
    near: camera.near,
    far: camera.far,
    fov: camera.fov,
    zoom: camera.zoom,
    target: controls?.target?.clone?.() || new THREE.Vector3(),
    controls: controls
      ? {
          enabled: controls.enabled,
          enableDamping: controls.enableDamping,
          enablePan: controls.enablePan,
          enableRotate: controls.enableRotate,
          enableZoom: controls.enableZoom,
          minDistance: controls.minDistance,
          maxDistance: controls.maxDistance,
        }
      : null,
  };
}

function restoreCamera(viewer, snapshot) {
  if (!snapshot) return;
  const camera = viewer.camera;
  camera.position.copy(snapshot.position);
  camera.quaternion.copy(snapshot.quaternion);
  camera.up.copy(snapshot.up);
  camera.near = snapshot.near;
  camera.far = snapshot.far;
  if (Number.isFinite(snapshot.fov)) camera.fov = snapshot.fov;
  if (Number.isFinite(snapshot.zoom)) camera.zoom = snapshot.zoom;
  camera.updateProjectionMatrix();
  if (viewer.controls && snapshot.controls) {
    viewer.controls.target.copy(snapshot.target);
    Object.assign(viewer.controls, snapshot.controls);
    viewer.controls.update();
  }
}

function rendererSnapshot(renderer) {
  const clearColor = new THREE.Color();
  renderer.getClearColor(clearColor);
  return {
    outputColorSpace: renderer.outputColorSpace,
    toneMapping: renderer.toneMapping,
    toneMappingExposure: renderer.toneMappingExposure,
    localClippingEnabled: renderer.localClippingEnabled,
    clearColor,
    clearAlpha: renderer.getClearAlpha(),
  };
}

function restoreRenderer(renderer, snapshot) {
  if (!snapshot) return;
  renderer.outputColorSpace = snapshot.outputColorSpace;
  renderer.toneMapping = snapshot.toneMapping;
  renderer.toneMappingExposure = snapshot.toneMappingExposure;
  renderer.localClippingEnabled = snapshot.localClippingEnabled;
  renderer.setClearColor(snapshot.clearColor, snapshot.clearAlpha);
}

function auxiliaryRoots(scene) {
  return scene.children.filter(
    (object) =>
      object.isGridHelper ||
      AUXILIARY_ROOT_PATTERNS.some((pattern) => pattern.test(object.name || "")),
  );
}

function collectOwnedResources(root) {
  const geometries = new Set();
  const materials = new Set();
  const textures = new Set();
  const seenValues = new Set();

  const inspectValue = (value) => {
    if (!value || seenValues.has(value)) return;
    if (value.isTexture) {
      textures.add(value);
      return;
    }
    if (typeof value !== "object") return;
    seenValues.add(value);
    if (Array.isArray(value)) {
      value.forEach(inspectValue);
      return;
    }
    for (const nested of Object.values(value)) inspectValue(nested);
  };

  root?.traverse?.((object) => {
    if (object.geometry) geometries.add(object.geometry);
    materialList(object).forEach((material) => {
      materials.add(material);
      for (const value of Object.values(material)) inspectValue(value);
      if (material.uniforms) inspectValue(material.uniforms);
    });
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

function materialContractSignature(material) {
  const textureKeys = [
    "map",
    "aoMap",
    "roughnessMap",
    "metalnessMap",
    "normalMap",
    "emissiveMap",
    "alphaMap",
  ];
  return JSON.stringify({
    type: material?.type || "",
    textures: Object.fromEntries(
      textureKeys.map((key) => [key, material?.[key]?.uuid || null]),
    ),
    color: material?.color?.getHexString?.() || null,
    emissive: material?.emissive?.getHexString?.() || null,
    roughness: material?.roughness ?? null,
    metalness: material?.metalness ?? null,
    normalScale: material?.normalScale?.toArray?.() || null,
    opacity: material?.opacity ?? null,
    transparent: material?.transparent ?? null,
    alphaTest: material?.alphaTest ?? null,
    side: material?.side ?? null,
    clippingPlaneCount: material?.clippingPlanes?.length || 0,
  });
}

function validateReviewAsset(gltf) {
  const root = gltf?.scene;
  if (!root?.isObject3D) throw new Error("V3 审查资产缺少 glTF scene");

  const materialGroups = root.children.filter(
    (object) => normalizeName(object.name) === MATERIAL_GROUP_NAME,
  );
  const sectionGroups = root.children.filter(
    (object) => normalizeName(object.name) === SECTION_GROUP_NAME,
  );
  const unexpectedTopLevel = root.children.filter((object) => {
    const name = normalizeName(object.name);
    return name !== MATERIAL_GROUP_NAME && name !== SECTION_GROUP_NAME;
  });
  if (
    materialGroups.length !== 1 ||
    sectionGroups.length !== 1 ||
    root.children.length !== 2 ||
    unexpectedTopLevel.length !== 0
  ) {
    throw new Error(
      `V3 顶层组合同不匹配：material=${materialGroups.length}/1，section=${sectionGroups.length}/1，unexpected=${unexpectedTopLevel.length}`,
    );
  }

  const materialGroup = materialGroups[0];
  const sectionGroup = sectionGroups[0];
  /*
   * GLTFLoader represents a Blender mesh with multiple material slots as one
   * logical Object3D plus one child Mesh per glTF primitive.  The physical
   * half-section objects each have body and cut-cap materials, so counting
   * primitive Mesh children reports 20 instead of the controlled 10 objects.
   * Use the exported review-mode metadata as the stable object contract while
   * retaining primitive counts as a separate runtime audit signal.
   */
  const materialRenderables = logicalReviewDescendants(
    materialGroup,
    "material",
  );
  const sectionTaggedRenderables = logicalReviewDescendants(
    sectionGroup,
    "section",
  );
  const sectionRenderables = sectionTaggedRenderables.filter(
    (object) =>
      object.userData?.bf3d_section_physical_cut === true ||
      object.userData?.bf3d_section_physical_cut === "true",
  );
  const materialPrimitiveRenderables = renderableDescendants(materialGroup);
  const sectionPrimitiveRenderables = renderableDescendants(sectionGroup);
  const allRenderables = [
    ...materialPrimitiveRenderables,
    ...sectionPrimitiveRenderables,
  ];
  if (materialRenderables.length !== 5 || sectionRenderables.length !== 10) {
    throw new Error(
      `V3 逻辑审查对象合同不匹配：material=${materialRenderables.length}/5，section=${sectionRenderables.length}/10`,
    );
  }
  const emptyLogicalObjects = [
    ...materialRenderables,
    ...sectionTaggedRenderables,
  ]
    .filter((object) => renderableDescendants(object).length === 0)
    .map((object) => normalizeName(object.name));
  if (
    materialPrimitiveRenderables.length < materialRenderables.length ||
    sectionPrimitiveRenderables.length < sectionTaggedRenderables.length ||
    emptyLogicalObjects.length
  ) {
    throw new Error(
      `V3 图元合同不匹配：material=${materialPrimitiveRenderables.length}，section=${sectionPrimitiveRenderables.length}，empty=${emptyLogicalObjects.join(",")}`,
    );
  }

  const forbidden = [];
  root.traverse((object) => {
    const name = normalizeName(object.name);
    if (
      object.isLine ||
      object.isLineSegments ||
      object.isPoints ||
      object.isSprite ||
      FORBIDDEN_REVIEW_NAME_PATTERNS.some((pattern) => pattern.test(name))
    ) {
      forbidden.push(name || object.type);
    }
  });
  if (forbidden.length) {
    throw new Error(`V3 含禁止审查对象：${forbidden.join(", ")}`);
  }

  const sectionMaterials = uniqueMaterials(sectionGroup);
  const clippingMaterials = [...sectionMaterials].filter(
    (material) => (material.clippingPlanes?.length || 0) > 0,
  );
  const doubleSideMaterials = [...sectionMaterials].filter(
    (material) => material.side === THREE.DoubleSide,
  );
  if (clippingMaterials.length || doubleSideMaterials.length) {
    throw new Error(
      `物理 SECTION 材质合同不匹配：clipping=${clippingMaterials.length}，doubleSide=${doubleSideMaterials.length}`,
    );
  }

  const physicalSectionCount = sectionRenderables.filter(
    (object) =>
      object.userData?.bf3d_section_physical_cut === true ||
      object.userData?.bf3d_section_physical_cut === "true",
  ).length;
  if (physicalSectionCount !== 10) {
    throw new Error(
      `物理 SECTION 元数据不完整：${physicalSectionCount}/10`,
    );
  }

  const reviewMaterials = new Set([
    ...uniqueMaterials(materialGroup),
    ...sectionMaterials,
  ]);
  const materialSnapshots = new Map(
    [...reviewMaterials].map((material) => [
      material,
      materialContractSignature(material),
    ]),
  );

  materialGroup.visible = false;
  sectionGroup.visible = false;
  root.visible = false;
  return {
    root,
    materialGroup,
    sectionGroup,
    materialRenderables,
    sectionRenderables,
    materialPrimitiveRenderables,
    sectionPrimitiveRenderables,
    allRenderables,
    sectionMaterials,
    materialSnapshots,
    forbidden,
    unexpectedTopLevel,
    physicalSectionCount,
  };
}

function frameGroup(viewer, group, mode) {
  const box = new THREE.Box3().setFromObject(group);
  if (box.isEmpty()) return;
  const center = box.getCenter(new THREE.Vector3());
  const sphere = box.getBoundingSphere(new THREE.Sphere());
  const direction =
    mode === "structural"
      ? new THREE.Vector3(1, 0.1, 0.08).normalize()
      : new THREE.Vector3(0.88, 0.2, 0.43).normalize();
  const halfFov = THREE.MathUtils.degToRad(
    Math.max(10, viewer.camera.fov || 42) * 0.5,
  );
  const distance = Math.max(
    sphere.radius * 1.35,
    sphere.radius / Math.max(Math.sin(halfFov), 0.2),
  );
  viewer.camera.position.copy(
    center.clone().addScaledVector(direction, distance),
  );
  viewer.camera.near = Math.max(0.05, distance - sphere.radius * 2.2);
  viewer.camera.far = Math.max(260, distance + sphere.radius * 4);
  viewer.camera.lookAt(center);
  viewer.camera.updateProjectionMatrix();
  if (viewer.controls) {
    viewer.controls.target.copy(center);
    viewer.controls.minDistance = Math.max(0.35, sphere.radius * 0.15);
    viewer.controls.maxDistance = Math.max(100, distance * 2.5);
    viewer.controls.update();
  }
}

function frameStructuralLayerDetail(viewer, group) {
  const box = new THREE.Box3().setFromObject(group);
  if (box.isEmpty()) return;
  const center = box.getCenter(new THREE.Vector3());
  const size = box.getSize(new THREE.Vector3());
  const target = center.clone();
  target.y -= size.y * 0.03;
  target.z += size.z * 0.43;
  const direction = new THREE.Vector3(1, 0.035, 0.015).normalize();
  const halfFov = THREE.MathUtils.degToRad(
    Math.max(10, viewer.camera.fov || 42) * 0.5,
  );
  const detailSpan = Math.max(size.z * 0.72, size.y * 0.15);
  const distance = Math.max(
    4,
    detailSpan / Math.max(2 * Math.tan(halfFov), 0.3),
  );
  viewer.camera.position.copy(
    target.clone().addScaledVector(direction, distance),
  );
  viewer.camera.near = 0.05;
  viewer.camera.far = Math.max(260, distance + size.y * 2);
  viewer.camera.lookAt(target);
  viewer.camera.updateProjectionMatrix();
  if (viewer.controls) {
    viewer.controls.target.copy(target);
    viewer.controls.minDistance = Math.max(0.35, distance * 0.18);
    viewer.controls.maxDistance = Math.max(100, distance * 8);
    viewer.controls.update();
  }
}

function linearColor(values, fallback = [1, 1, 1]) {
  const source = Array.isArray(values) && values.length >= 3 ? values : fallback;
  return new THREE.Color().setRGB(
    Number(source[0]),
    Number(source[1]),
    Number(source[2]),
  );
}

function createNeutralLights(preset, focus) {
  const group = new THREE.Group();
  group.name = "BF3D_REVIEW_NEUTRAL_LIGHTS";
  group.userData.bf3d_lookdev_source = LOOKDEV_PRESET_URL;
  group.userData.bf3d_lookdev_mode = "neutral_direct";

  const neutral =
    preset?.blender?.light_rigs?.neutral?.lights?.filter(
      (entry) => entry.type === "SUN",
    ) || [];
  for (const entry of neutral) {
    const light = new THREE.DirectionalLight(
      linearColor(entry.color_linear_rgb),
      Number(entry.energy || 0),
    );
    light.name = entry.name;
    const position = entry.location_m || [0, 1, 0];
    light.position.set(
      Number(position[0]),
      Number(position[2]),
      -Number(position[1]),
    );
    const target = new THREE.Object3D();
    target.name = `${entry.name}_TARGET`;
    target.position.copy(focus);
    light.target = target;
    group.add(target, light);
  }

  const worldStrength = Number(
    preset?.blender?.color_management?.neutral?.world_strength ?? 0.72,
  );
  const worldColor =
    preset?.blender?.color_management?.neutral?.world_color_linear_rgba ||
    [0.12, 0.12, 0.12, 1];
  const ambient = new THREE.AmbientLight(
    linearColor(worldColor),
    worldStrength * 0.35,
  );
  ambient.name = "BF3D_REVIEW_NEUTRAL_WORLD_APPROX";
  group.add(ambient);
  group.visible = false;
  return group;
}

async function createController(viewer, host, stage) {
  const baseModel = viewer.baseModel || viewer.model;
  const scene = viewer.scene;
  if (
    !baseModel?.isObject3D ||
    !scene?.isScene ||
    !viewer.renderer ||
    !viewer.camera ||
    !viewer.controls ||
    !viewer.GLTFLoader
  ) {
    throw new Error(
      "生效 Viewer API 不完整：需要 baseModel/scene/renderer/camera/controls/GLTFLoader",
    );
  }

  const panel = createPanel(stage);
  const reviewScope = stage.parentElement || stage;
  const assetLabel = panel.querySelector("[data-review-asset]");
  const statusLabel = panel.querySelector("[data-review-label]");
  const statusDescription = panel.querySelector(
    "[data-review-description]",
  );
  const legend = panel.querySelector("[data-review-legend]");
  const recovery = panel.querySelector("[data-review-recovery]");
  const retryButton = panel.querySelector("[data-review-retry]");
  const dismissButton = panel.querySelector("[data-review-dismiss]");
  const buttons = Array.from(panel.querySelectorAll("[data-review-mode]"));
  const cameraButtons = Array.from(
    panel.querySelectorAll("[data-review-camera]"),
  );
  const uiAbort = new AbortController();

  const state = {
    controllerStatus: "ready",
    mode: "operational",
    requestedMode: "operational",
    assetStatus: "idle",
    transitionId: 0,
    loadAttempt: 0,
    assetRequestCount: 0,
    abortCount: 0,
    disposeCount: 0,
    error: null,
    lookdev: "operational",
    lastFailedMode: "material",
    structuralCamera: "global",
  };

  let disposed = false;
  let reviewContract = null;
  let reviewResources = null;
  let reviewLights = null;
  let lookdevPreset = null;
  let loadPromise = null;
  let loadAbortController = null;
  let loadGeneration = 0;
  let operationalSnapshot = null;
  let materialReviewBasePositions = null;
  let materialReviewLayout = "stacked";
  let detailController = null;
  let integratedRow = null;
  let integratedTimer = 0;

  function updateUi() {
    const reviewVisible =
      state.mode !== "operational" || state.assetStatus === "loading";
    const statusVisible = state.assetStatus === "error";
    stage.dataset.bf3dReviewMode = state.mode;
    stage.dataset.bf3dReviewLoadState = state.assetStatus;
    host.dataset.bf3dReviewMode = state.mode;
    host.dataset.bf3dReviewLoadState = state.assetStatus;
    panel.dataset.reviewLoadState = state.assetStatus;
    panel.setAttribute(
      "aria-busy",
      String(state.assetStatus === "loading"),
    );
    stage.classList.toggle("bf3d-review-active", reviewVisible);
    stage.classList.toggle("bf3d-review-status-visible", statusVisible);
    stage.classList.toggle(
      "bf3d-review-material",
      state.mode === "material" ||
        (state.assetStatus === "loading" &&
          state.requestedMode === "material"),
    );
    stage.classList.toggle(
      "bf3d-review-structural",
      state.mode === "structural" ||
        (state.assetStatus === "loading" &&
          state.requestedMode === "structural"),
    );
    reviewScope.classList.toggle("bf3d-review-scope-active", reviewVisible);

    for (const button of buttons) {
      const buttonMode =
        button.dataset.reviewMode ||
        button.dataset.integratedReviewMode;
      const activeMode =
        state.assetStatus === "loading" ? state.requestedMode : state.mode;
      const active = buttonMode === activeMode;
      button.classList.toggle("active", active);
      button.setAttribute("aria-pressed", String(active));
      button.disabled = disposed;
    }
    for (const button of cameraButtons) {
      const cameraModeAvailable =
        state.mode === "structural" || state.mode === "material";
      const active =
        cameraModeAvailable &&
        button.dataset.reviewCamera === state.structuralCamera;
      button.classList.toggle("active", active);
      button.setAttribute("aria-pressed", String(active));
      button.disabled = disposed || !cameraModeAvailable;
    }

    if (state.assetStatus === "loading") {
      assetLabel.textContent = `V3 加载中 · 第 ${state.loadAttempt} 次`;
      statusLabel.textContent = "审查资产加载中";
      statusDescription.textContent =
        state.requestedMode === "structural"
          ? "正在读取物理结构剖面，可切换模式或返回运行视图。"
          : "正在读取纯材质审查资产，可切换模式或返回运行视图。";
    } else if (state.assetStatus === "error") {
      assetLabel.textContent = "V3 加载失败";
      statusLabel.textContent = "审查资产不可用";
      statusDescription.textContent =
        state.error || "请重试；V1 运行视图已经恢复。";
    } else if (reviewContract) {
      assetLabel.textContent = "V3 · 5 个材质实体 + 10 个物理剖面";
      statusLabel.textContent = MODES[state.mode].label;
      statusDescription.textContent = MODES[state.mode].description;
    } else {
      assetLabel.textContent = "V3 尚未加载";
      statusLabel.textContent = MODES.operational.label;
      statusDescription.textContent = MODES.operational.description;
    }
    recovery.hidden = state.assetStatus !== "error";
    legend.hidden = state.mode !== "structural" && state.mode !== "material";
  }

  function bindModeButton(button) {
    button.addEventListener(
      "click",
      () => {
        const mode =
          button.dataset.reviewMode ||
          button.dataset.integratedReviewMode;
        void setMode(mode);
      },
      { signal: uiAbort.signal },
    );
  }

  function setStructuralCamera(nextCamera) {
    if (
      disposed ||
      (state.mode !== "structural" && state.mode !== "material") ||
      !reviewContract?.sectionGroup
    ) {
      return false;
    }
    if (nextCamera === "layer-detail") {
      frameStructuralLayerDetail(viewer, reviewContract.sectionGroup);
      state.structuralCamera = "layer-detail";
    } else {
      frameGroup(viewer, reviewContract.sectionGroup, "structural");
      state.structuralCamera = "global";
    }
    updateUi();
    return true;
  }

  function mountIntegratedControls() {
    const controls = reviewScope.querySelector(".cad-layer-controls");
    if (!controls) return false;
    integratedRow = controls.querySelector(
      '.cad-review-controls-row[data-bf3d-owner="structural-review-v3"]',
    );
    if (!integratedRow) {
      integratedRow = document.createElement("div");
      integratedRow.className =
        "cad-layer-controls-row cad-review-controls-row";
      integratedRow.dataset.bf3dOwner = "structural-review-v3";
      integratedRow.innerHTML = `
        <span class="cad-layer-controls-label">审查</span>
        <button type="button" data-integrated-review-mode="operational">运行视图</button>
        <button type="button" data-integrated-review-mode="material">纯材质</button>
        <button type="button" data-integrated-review-mode="structural">结构剖面</button>
      `;
      const status = controls.querySelector(".cad-layer-selection-status");
      controls.insertBefore(integratedRow, status);
      const integratedButtons = Array.from(
        integratedRow.querySelectorAll("[data-integrated-review-mode]"),
      );
      integratedButtons.forEach(bindModeButton);
      buttons.push(...integratedButtons);
    }
    updateUi();
    return true;
  }

  function captureOperationalState() {
    if (operationalSnapshot) return;
    const objectVisibility = new Map();
    baseModel.traverse((object) => objectVisibility.set(object, object.visible));
    const hitVisibility = new Map(
      (viewer.hitObjects || []).map((object) => [object, object.visible]),
    );
    const auxiliaryVisibility = new Map(
      auxiliaryRoots(scene).map((object) => [object, object.visible]),
    );
    const lightState = new Map();
    scene.traverse((object) => {
      if (object.isLight && !reviewLights?.getObjectById(object.id)) {
        lightState.set(object, {
          visible: object.visible,
          intensity: object.intensity,
        });
      }
    });
    const internalSimulation = window.__BF3D_INTERNAL_SIMULATION__;
    operationalSnapshot = {
      objectVisibility,
      hitVisibility,
      auxiliaryVisibility,
      lightState,
      baseModelVisible: baseModel.visible,
      camera: snapshotCamera(viewer),
      renderer: rendererSnapshot(viewer.renderer),
      background: scene.background,
      environment: scene.environment,
      fog: scene.fog,
      layer: viewer.getLayerHighlightState?.() || null,
      cutaway: viewer.getCutawayState?.() || null,
      simulation:
        internalSimulation?.viewer === viewer
          ? internalSimulation.getState?.() || null
          : null,
      detail: detailController?.getState?.() || null,
    };
  }

  function suspendOperationalState() {
    captureOperationalState();
    const internalSimulation = window.__BF3D_INTERNAL_SIMULATION__;
    if (internalSimulation?.viewer === viewer) internalSimulation.pause?.();
    viewer.clearLayerHighlight?.();
    viewer.setCutawayMode?.("exterior");
    baseModel.visible = false;
    for (const object of viewer.hitObjects || []) object.visible = false;
    for (const object of auxiliaryRoots(scene)) object.visible = false;
    for (const [light] of operationalSnapshot?.lightState || []) {
      light.visible = false;
    }
    detailController?.setEnabled?.(false);
    const tooltip = stage.querySelector(".cad-furnace-tooltip");
    if (tooltip) tooltip.style.display = "none";
  }

  function hideReviewAsset() {
    if (!reviewContract) return;
    applyMaterialReviewLayout(false);
    reviewContract.materialGroup.visible = false;
    reviewContract.sectionGroup.visible = false;
    reviewContract.root.visible = false;
    if (reviewLights) reviewLights.visible = false;
  }

  function restoreOperationalState() {
    hideReviewAsset();
    const snapshot = operationalSnapshot;
    if (!snapshot) {
      baseModel.visible = true;
      state.mode = "operational";
      state.lookdev = "operational";
      return;
    }

    scene.background = snapshot.background;
    scene.environment = snapshot.environment;
    scene.fog = snapshot.fog;
    restoreRenderer(viewer.renderer, snapshot.renderer);
    for (const [light, saved] of snapshot.lightState) {
      light.visible = saved.visible;
      light.intensity = saved.intensity;
    }
    for (const [object, visible] of snapshot.objectVisibility) {
      if (object) object.visible = visible;
    }
    baseModel.visible = snapshot.baseModelVisible;
    for (const [object, visible] of snapshot.hitVisibility) {
      if (object) object.visible = visible;
    }
    for (const [object, visible] of snapshot.auxiliaryVisibility) {
      if (object) object.visible = visible;
    }

    const cutaway = snapshot.cutaway;
    if (cutaway?.mode === "cutaway") {
      viewer.setCutawayMode?.("cutaway");
      if (cutaway.playing) viewer.playCutaway?.();
      else viewer.pauseCutaway?.();
    } else {
      viewer.setCutawayMode?.("exterior");
    }
    if (snapshot.layer?.layerId) {
      viewer.highlightLayer?.(snapshot.layer.layerId);
    } else {
      viewer.clearLayerHighlight?.();
    }
    const internalSimulation = window.__BF3D_INTERNAL_SIMULATION__;
    if (internalSimulation?.viewer === viewer && snapshot.simulation) {
      internalSimulation.setMode?.(snapshot.simulation.mode);
      if (snapshot.simulation.playing) internalSimulation.play?.();
      else internalSimulation.pause?.();
    }
    if (snapshot.detail) {
      detailController?.setEnabled?.(
        snapshot.detail.detail_normal?.active !== false &&
          snapshot.detail.status !== "disabled",
      );
      const detailStrength =
        snapshot.detail.detail_normal?.strength_near;
      if (Number.isFinite(detailStrength)) {
        detailController?.setNearStrength?.(detailStrength);
      }
    } else {
      detailController?.setEnabled?.(true);
    }
    restoreCamera(viewer, snapshot.camera);
    operationalSnapshot = null;
    state.mode = "operational";
    state.lookdev = "operational";
  }

  async function ensureLookdevPreset(signal) {
    if (lookdevPreset) return lookdevPreset;
    const response = await fetch(LOOKDEV_PRESET_URL, {
      signal,
      cache: "force-cache",
    });
    if (!response.ok) {
      throw new Error(`LookDev 预设 HTTP ${response.status}`);
    }
    const preset = await response.json();
    if (
      preset?.schema_version !== "bf3d.lookdev_camera.v1" ||
      !preset?.blender?.light_rigs?.neutral
    ) {
      throw new Error("LookDev 预设合同不匹配");
    }
    if (signal?.aborted) {
      throw new DOMException("LookDev 预设加载已取消", "AbortError");
    }
    lookdevPreset = preset;
    return preset;
  }

  function applyNeutralLookdev(group) {
    if (!lookdevPreset) throw new Error("中性 LookDev 预设尚未加载");
    const box = new THREE.Box3().setFromObject(group);
    const focus = box.isEmpty()
      ? new THREE.Vector3()
      : box.getCenter(new THREE.Vector3());
    if (!reviewLights) {
      reviewLights = createNeutralLights(lookdevPreset, focus);
      scene.add(reviewLights);
    } else {
      reviewLights.traverse((object) => {
        if (object.name.endsWith("_TARGET")) object.position.copy(focus);
      });
    }
    for (const [light] of operationalSnapshot?.lightState || []) {
      light.visible = false;
    }
    reviewLights.visible = true;
    scene.background = null;
    scene.environment = null;
    scene.fog = null;
    viewer.renderer.outputColorSpace = THREE.SRGBColorSpace;
    viewer.renderer.toneMapping = THREE.ACESFilmicToneMapping;
    viewer.renderer.toneMappingExposure = Number(
      lookdevPreset?.web_runtime_audit?.tone_mapping_exposure ?? 1.05,
    );
    viewer.renderer.localClippingEnabled = false;
    state.lookdev = "neutral_direct";
  }

  function reviewMaterialContractState() {
    if (!reviewContract) {
      return {
        clippingCount: 0,
        doubleSideCount: 0,
        pbrMutationCount: 0,
      };
    }
    const materials = reviewContract.sectionMaterials;
    return {
      clippingCount: [...materials].filter(
        (material) => (material.clippingPlanes?.length || 0) > 0,
      ).length,
      doubleSideCount: [...materials].filter(
        (material) => material.side === THREE.DoubleSide,
      ).length,
      pbrMutationCount: [...reviewContract.materialSnapshots].filter(
        ([material, signature]) =>
          materialContractSignature(material) !== signature,
      ).length,
    };
  }

  function applyMaterialReviewLayout(expanded) {
    if (!reviewContract?.materialRenderables?.length) return;
    const objects = [...reviewContract.materialRenderables].sort((a, b) =>
      normalizeName(a.name).localeCompare(normalizeName(b.name), "zh-Hans"),
    );
    if (!materialReviewBasePositions) {
      materialReviewBasePositions = new Map(
        objects.map((object) => [object, object.position.clone()]),
      );
    }
    for (const object of objects) {
      const basePosition = materialReviewBasePositions.get(object);
      if (basePosition) object.position.copy(basePosition);
    }
    materialReviewLayout = "stacked";
    if (!expanded) return;

    const box = new THREE.Box3().setFromObject(reviewContract.materialGroup);
    const size = box.getSize(new THREE.Vector3());
    const step = Math.max(size.x * 0.72, 1.8);
    const middle = (objects.length - 1) / 2;
    objects.forEach((object, index) => {
      const basePosition = materialReviewBasePositions.get(object);
      if (!basePosition) return;
      const offset = index - middle;
      object.position.set(
        basePosition.x + offset * step,
        basePosition.y,
        basePosition.z + Math.abs(offset) * step * 0.06,
      );
    });
    materialReviewLayout = "exploded";
  }

  async function ensureReviewAsset() {
    if (reviewContract) return reviewContract;
    if (loadPromise) return loadPromise;

    const generation = ++loadGeneration;
    const controller = new AbortController();
    loadAbortController = controller;
    state.assetStatus = "loading";
    state.loadAttempt += 1;
    state.assetRequestCount += 1;
    state.error = null;
    updateUi();
    let parsedRoot = null;
    let parsedResources = null;
    let committedContract = null;

    loadPromise = (async () => {
      const [response, preset] = await Promise.all([
        fetch(REVIEW_ASSET_URL, {
          signal: controller.signal,
          cache: "force-cache",
        }),
        ensureLookdevPreset(controller.signal),
      ]);
      if (!response.ok) {
        throw new Error(`V3 审查模型 HTTP ${response.status}`);
      }
      const buffer = await response.arrayBuffer();
      const loader = new viewer.GLTFLoader();
      const basePath = new URL(".", response.url).href;
      const gltf = await loader.parseAsync(buffer, basePath);
      parsedRoot = gltf.scene;
      parsedResources = collectOwnedResources(parsedRoot);
      if (
        disposed ||
        controller.signal.aborted ||
        generation !== loadGeneration
      ) {
        disposeOwnedResources(parsedRoot, parsedResources);
        parsedRoot = null;
        parsedResources = null;
        throw new DOMException("V3 审查加载已取消", "AbortError");
      }

      const contract = validateReviewAsset(gltf);
      reviewResources = parsedResources;
      reviewContract = contract;
      committedContract = contract;
      parsedRoot = null;
      parsedResources = null;
      lookdevPreset = preset;
      contract.root.name = "BF3D_V3_CONTROLLED_REVIEW_ROOT";
      contract.root.visible = false;
      scene.add(contract.root);
      viewer.reviewRoot = contract.root;
      state.assetStatus = "ready";
      state.error = null;
      return contract;
    })()
      .catch((error) => {
        if (parsedRoot) {
          disposeOwnedResources(parsedRoot, parsedResources);
          parsedRoot = null;
          parsedResources = null;
        }
        if (
          committedContract &&
          reviewContract === committedContract &&
          reviewContract.root
        ) {
          disposeOwnedResources(reviewContract.root, reviewResources);
          reviewContract = null;
          reviewResources = null;
          if (viewer.reviewRoot === committedContract.root) {
            delete viewer.reviewRoot;
          }
        }
        throw error;
      })
      .finally(() => {
        if (generation === loadGeneration) {
          loadPromise = null;
          loadAbortController = null;
        }
      });

    return loadPromise;
  }

  function abortPendingLoad() {
    if (!loadAbortController) return;
    state.abortCount += 1;
    loadGeneration += 1;
    loadAbortController.abort();
    loadAbortController = null;
    loadPromise = null;
    if (!reviewContract) state.assetStatus = "idle";
  }

  function applyReviewMode(nextMode) {
    if (!reviewContract) throw new Error("V3 审查资产尚未就绪");
    suspendOperationalState();
    applyMaterialReviewLayout(nextMode === "material");
    const materialAuditMode = nextMode === "material";
    reviewContract.root.visible = true;
    reviewContract.materialGroup.visible = false;
    reviewContract.sectionGroup.visible =
      materialAuditMode || nextMode === "structural";
    if (materialAuditMode) materialReviewLayout = "section_material_audit";
    const visibleGroup = reviewContract.sectionGroup;
    applyNeutralLookdev(visibleGroup);
    if (materialAuditMode) {
      frameStructuralLayerDetail(viewer, visibleGroup);
      state.structuralCamera = "layer-detail";
    } else {
      frameGroup(viewer, visibleGroup, nextMode);
      state.structuralCamera = "global";
    }
    if (nextMode === "structural") state.structuralCamera = "global";
    state.mode = nextMode;
    state.assetStatus = "ready";
    state.error = null;
    updateUi();
  }

  async function setMode(nextMode) {
    if (!MODES[nextMode] || disposed) return false;
    const token = ++state.transitionId;
    state.requestedMode = nextMode;

    if (nextMode === "operational") {
      abortPendingLoad();
      restoreOperationalState();
      state.assetStatus = reviewContract ? "ready" : "idle";
      state.error = null;
      updateUi();
      return true;
    }

    captureOperationalState();
    suspendOperationalState();
    state.assetStatus = reviewContract ? "ready" : "loading";
    updateUi();
    try {
      const contract = await ensureReviewAsset();
      if (
        disposed ||
        token !== state.transitionId ||
        state.requestedMode === "operational"
      ) {
        return false;
      }
      applyReviewMode(state.requestedMode, contract);
      return true;
    } catch (error) {
      if (
        disposed ||
        token !== state.transitionId ||
        error?.name === "AbortError"
      ) {
        return false;
      }
      state.lastFailedMode = nextMode;
      state.assetStatus = "error";
      state.error = String(error?.message || error);
      restoreOperationalState();
      state.requestedMode = nextMode;
      updateUi();
      return false;
    }
  }

  async function retry() {
    if (disposed || state.assetStatus !== "error") return false;
    state.error = null;
    state.assetStatus = "idle";
    updateUi();
    return setMode(state.lastFailedMode || "material");
  }

  function getState() {
    const materialState = reviewMaterialContractState();
    const runtimeRoot = scene.getObjectByName(
      "BF3D_INTERNAL_SIMULATION_RUNTIME",
    );
    const yellowProfile = scene.getObjectByName(
      "GL02_CUTAWAY_PROFILE_EDGES",
    );
    const calloutElements = Array.from(
      reviewScope.querySelectorAll(
        ".furnace-layer-callouts, .furnace-follow-lines",
      ),
    );
    const visibleCalloutCount = calloutElements.filter((element) => {
      const style = window.getComputedStyle(element);
      return (
        style.display !== "none" &&
        style.visibility !== "hidden" &&
        Number(style.opacity || 1) > 0
      );
    }).length;
    return {
      schema_version: "bf3d.web.structural_review_runtime.v3",
      requirement_id: REQUIREMENT_ID,
      asset_id: ASSET_ID,
      status: disposed ? "disposed" : state.controllerStatus,
      mode: state.mode,
      requested_mode: state.requestedMode,
      asset_status: state.assetStatus,
      operational_asset_url: OPERATIONAL_ASSET_URL,
      review_asset_url: REVIEW_ASSET_URL,
      evidence: "E/illustrative",
      reference_status: "REF-PENDING",
      not_for_construction: true,
      lookdev_mode: state.lookdev,
      structural_camera: state.structuralCamera,
      lookdev_preset_url: LOOKDEV_PRESET_URL,
      lookdev_preset_schema: lookdevPreset?.schema_version || null,
      pmrem_enabled: false,
      pmrem_reason: "no_approved_neutral_environment",
      sensor_count: (viewer.sensorObjects || []).length,
      hit_count: (viewer.hitObjects || []).length,
      sensor_visible_count: (viewer.sensorObjects || []).filter(
        (object) => object.visible && baseModel.visible,
      ).length,
      hit_visible_count: (viewer.hitObjects || []).filter(
        (object) => object.visible,
      ).length,
      base_model_visible: baseModel.visible,
      material_group_count: reviewContract ? 1 : 0,
      section_group_count: reviewContract ? 1 : 0,
      material_renderable_count:
        reviewContract?.materialRenderables.length || 0,
      section_renderable_count:
        reviewContract?.sectionRenderables.length || 0,
      material_primitive_renderable_count:
        reviewContract?.materialPrimitiveRenderables.length || 0,
      section_primitive_renderable_count:
        reviewContract?.sectionPrimitiveRenderables.length || 0,
      material_visible_count: reviewContract
        ? reviewContract.materialRenderables.filter(
            (object) =>
              object.visible &&
              reviewContract.materialGroup.visible &&
              reviewContract.root.visible,
          ).length
        : 0,
      section_visible_count: reviewContract
        ? reviewContract.sectionRenderables.filter(
            (object) =>
              object.visible &&
              reviewContract.sectionGroup.visible &&
              reviewContract.root.visible,
          ).length
        : 0,
      physical_section_count: reviewContract?.physicalSectionCount || 0,
      unexpected_top_level_count:
        reviewContract?.unexpectedTopLevel.length || 0,
      forbidden_review_object_count: reviewContract?.forbidden.length || 0,
      review_material_clipping_count: materialState.clippingCount,
      review_double_side_count: materialState.doubleSideCount,
      review_pbr_mutation_count: materialState.pbrMutationCount,
      material_review_layout: materialReviewLayout,
      r2h_detail_normal: detailController?.getState?.() || null,
      owned_resources: resourceCounts(reviewResources),
      load_attempt: state.loadAttempt,
      asset_request_count: state.assetRequestCount,
      abort_count: state.abortCount,
      dispose_count: state.disposeCount,
      transition_id: state.transitionId,
      error: state.error,
      callouts_hidden: stage.classList.contains("bf3d-review-active"),
      callout_present_count: calloutElements.length,
      callout_visible_count: visibleCalloutCount,
      yellow_profile_present_count: yellowProfile ? 1 : 0,
      yellow_profile_visible_count: yellowProfile?.visible ? 1 : 0,
      yellow_profile_hidden: Boolean(yellowProfile && !yellowProfile.visible),
      process_runtime_present_count: runtimeRoot ? 1 : 0,
      process_runtime_visible_count: runtimeRoot?.visible ? 1 : 0,
      process_runtime_hidden: Boolean(runtimeRoot && !runtimeRoot.visible),
      modes: Object.keys(MODES),
    };
  }

  function dispose() {
    if (disposed) return;
    abortPendingLoad();
    restoreOperationalState();
    disposed = true;
    state.controllerStatus = "disposed";
    state.disposeCount += 1;
    detailController?.dispose?.();
    window.clearInterval(integratedTimer);
    uiAbort.abort();
    integratedRow?.remove();
    panel.remove();
    if (reviewLights) {
      scene.remove(reviewLights);
      reviewLights.clear();
      reviewLights = null;
    }
    if (reviewContract?.root) {
      disposeOwnedResources(reviewContract.root, reviewResources);
    }
    reviewContract = null;
    reviewResources = null;
    stage.classList.remove(
      "bf3d-review-active",
      "bf3d-review-status-visible",
      "bf3d-review-material",
      "bf3d-review-structural",
    );
    reviewScope.classList.remove("bf3d-review-scope-active");
    delete stage.dataset.bf3dReviewMode;
    delete stage.dataset.bf3dReviewLoadState;
    delete host.dataset.bf3dReviewMode;
    delete host.dataset.bf3dReviewLoadState;
    if (viewer.reviewRoot) delete viewer.reviewRoot;
    if (viewer.structuralReview === api) delete viewer.structuralReview;
    if (window.__BF3D_STRUCTURAL_REVIEW__ === api) {
      delete window.__BF3D_STRUCTURAL_REVIEW__;
    }
  }

  function isConnected() {
    return !disposed && host.isConnected && viewer.renderer?.domElement?.isConnected;
  }

  function getAuditCaptureCapability() {
    return getR2SAuditCaptureCapability();
  }

  function getAuditShotManifest() {
    return buildR2SAuditShotManifest();
  }

  const api = {
    setMode,
    retry,
    getState,
    getAuditCaptureCapability,
    getAuditShotManifest,
    dispose,
    isConnected,
  };

  buttons.forEach(bindModeButton);
  cameraButtons.forEach((button) => {
    button.addEventListener(
      "click",
      () => setStructuralCamera(button.dataset.reviewCamera),
      { signal: uiAbort.signal },
    );
  });
  retryButton.addEventListener("click", () => void retry(), {
    signal: uiAbort.signal,
  });
  dismissButton.addEventListener(
    "click",
    () => void setMode("operational"),
    { signal: uiAbort.signal },
  );

  updateUi();
  if (!mountIntegratedControls()) {
    integratedTimer = window.setInterval(() => {
      if (mountIntegratedControls()) window.clearInterval(integratedTimer);
    }, 120);
  }

  Promise.resolve(
    installR2HDetailNormal({
      THREE,
      renderer: viewer.renderer,
      camera: viewer.camera,
      root: baseModel,
      viewerEl: host,
      textureUrl: DETAIL_NORMAL_URL,
      expectedSha256: DETAIL_NORMAL_SHA256,
      strengthNear: 0.85,
      fadeStartM: 3,
      fadeEndM: 20,
      physicalTileM: 0.3,
    }),
  )
    .then((controller) => {
      if (disposed) {
        controller?.dispose?.();
        return;
      }
      detailController = controller;
      if (state.mode !== "operational" || state.assetStatus === "loading") {
        detailController?.setEnabled?.(false);
      }
    })
    .catch((error) => {
      console.warn("BF3D R5 detail normal unavailable", error);
    });

  return api;
}

let activeViewer = null;
let activeController = null;
let initializingViewer = null;

async function tryMount() {
  const viewer = window.__BF_CAD_FURNACE_VIEWER;
  if (
    activeController &&
    (viewer !== activeViewer || !activeController.isConnected?.())
  ) {
    activeController.dispose?.();
    activeController = null;
    activeViewer = null;
  }
  if (!viewer || viewer === activeViewer || viewer === initializingViewer) return;

  const host = document.querySelector(".cad-furnace-viewer");
  const stage = host?.closest(".layered-cad-stage");
  if (
    !host ||
    !stage ||
    !viewer.baseModel ||
    !viewer.scene ||
    !viewer.renderer ||
    !viewer.camera ||
    !viewer.controls ||
    !viewer.GLTFLoader
  ) {
    return;
  }

  initializingViewer = viewer;
  try {
    const controller = await createController(viewer, host, stage);
    if (window.__BF_CAD_FURNACE_VIEWER !== viewer || !host.isConnected) {
      controller.dispose();
      return;
    }
    activeController?.dispose?.();
    activeController = controller;
    activeViewer = viewer;
    viewer.structuralReview = controller;
    window.__BF3D_STRUCTURAL_REVIEW__ = controller;
    host.dataset.bf3dStructuralReviewStatus = "ready";
  } catch (error) {
    host.dataset.bf3dStructuralReviewStatus = "error";
    console.error("BF3D structural review init failed", error);
  } finally {
    if (initializingViewer === viewer) initializingViewer = null;
  }
}

const mountTimer = window.setInterval(() => void tryMount(), 120);
window.addEventListener(
  "beforeunload",
  () => {
    window.clearInterval(mountTimer);
    activeController?.dispose?.();
  },
  { once: true },
);
