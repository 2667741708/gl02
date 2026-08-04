const R2H_SCHEMA_VERSION = 'bf3d.r2h.detail_normal.v1';
const R2H_PATCH_KEY = 'R2H_DETAIL_NORMAL_RNM_V1';
const DEFAULT_SHELL_NAMES = [
  'APPROX_GL02_FURNACE_HEARTH',
  'APPROX_GL02_FURNACE_BOSH',
  'APPROX_GL02_FURNACE_BELLY',
  'APPROX_GL02_FURNACE_SHAFT',
  'APPROX_GL02_FURNACE_THROAT'
];

const NORMAL_PARS_TOKEN = '#include <normalmap_pars_fragment>';
const NORMAL_MAPS_TOKEN = '#include <normal_fragment_maps>';

const R2H_NORMAL_PARS = `${NORMAL_PARS_TOKEN}
uniform sampler2D r2hDetailNormalMap;
uniform vec2 r2hDetailUvMin;
uniform vec2 r2hDetailUvSpan;
uniform vec2 r2hDetailRepeat;
uniform float r2hDetailStrengthNear;
uniform float r2hDetailFadeStartM;
uniform float r2hDetailFadeEndM;

vec3 r2hBlendRNM( vec3 baseNormal, vec3 detailNormal ) {
  vec3 n1 = normalize( baseNormal );
  vec3 n2 = normalize( detailNormal );
  vec3 t = n1 + vec3( 0.0, 0.0, 1.0 );
  vec3 u = n2 * vec3( -1.0, -1.0, 1.0 );
  return normalize( t * dot( t, u ) - u * t.z );
}`;

const R2H_NORMAL_MAPS = `
#ifdef USE_NORMALMAP_OBJECTSPACE
  normal = texture2D( normalMap, vNormalMapUv ).xyz * 2.0 - 1.0;
  #ifdef FLIP_SIDED
    normal = - normal;
  #endif
  #ifdef DOUBLE_SIDED
    normal = normal * faceDirection;
  #endif
  normal = normalize( normalMatrix * normal );
#elif defined( USE_NORMALMAP_TANGENTSPACE )
  vec3 mapN = texture2D( normalMap, vNormalMapUv ).xyz * 2.0 - 1.0;
  mapN.xy *= normalScale;

  vec2 r2hNormalizedUv = ( vNormalMapUv - r2hDetailUvMin ) / max( r2hDetailUvSpan, vec2( 0.0001 ) );
  vec3 r2hDetailN = texture2D( r2hDetailNormalMap, r2hNormalizedUv * r2hDetailRepeat ).xyz * 2.0 - 1.0;
  r2hDetailN.y *= normalScale.y < 0.0 ? -1.0 : 1.0;

  float r2hFragmentDistanceM = length( vViewPosition );
  float r2hDistanceWeight = 1.0 - smoothstep( r2hDetailFadeStartM, r2hDetailFadeEndM, r2hFragmentDistanceM );
  float r2hWeight = clamp( r2hDetailStrengthNear * r2hDistanceWeight, 0.0, 1.0 );
  r2hDetailN.xy *= r2hWeight;
  r2hDetailN = normalize( r2hDetailN );

  mapN = r2hBlendRNM( mapN, r2hDetailN );
  normal = normalize( tbn * mapN );
#elif defined( USE_BUMPMAP )
  normal = perturbNormalArb( - vViewPosition, normal, dHdxy_fwd(), faceDirection );
#endif`;

function smoothstep(edge0, edge1, value) {
  const x = Math.min(1, Math.max(0, (value - edge0) / Math.max(edge1 - edge0, 1e-9)));
  return x * x * (3 - 2 * x);
}

function detailDistanceWeight(distanceM, fadeStartM, fadeEndM) {
  return 1 - smoothstep(fadeStartM, fadeEndM, distanceM);
}

async function sha256Hex(buffer) {
  if (!globalThis.crypto?.subtle) throw new Error('Web Crypto SHA-256 is unavailable');
  const digest = await globalThis.crypto.subtle.digest('SHA-256', buffer);
  return Array.from(new Uint8Array(digest), (byte) => byte.toString(16).padStart(2, '0')).join('');
}

async function loadVerifiedTexture(THREE, renderer, textureUrl, expectedSha256) {
  const response = await fetch(textureUrl, { cache: 'no-store' });
  if (!response.ok) throw new Error(`Detail Normal HTTP ${response.status}: ${textureUrl}`);
  const buffer = await response.arrayBuffer();
  const actualSha256 = await sha256Hex(buffer);
  if (actualSha256 !== expectedSha256) {
    throw new Error(`Detail Normal SHA-256 mismatch: expected ${expectedSha256}, got ${actualSha256}`);
  }

  const objectUrl = URL.createObjectURL(new Blob([buffer], { type: 'image/png' }));
  try {
    const texture = await new THREE.TextureLoader().loadAsync(objectUrl);
    texture.name = 'INT30_R2H_DetailNormal_LOW_1K_OpenGL_plusY';
    texture.colorSpace = THREE.NoColorSpace;
    texture.wrapS = THREE.RepeatWrapping;
    texture.wrapT = THREE.RepeatWrapping;
    texture.minFilter = THREE.LinearMipmapLinearFilter;
    texture.magFilter = THREE.LinearFilter;
    texture.generateMipmaps = true;
    texture.anisotropy = Math.min(renderer.capabilities.getMaxAnisotropy?.() || 1, 16);
    texture.needsUpdate = true;
    return { texture, actualSha256, byteLength: buffer.byteLength };
  } finally {
    URL.revokeObjectURL(objectUrl);
  }
}

function geometryUvContract(THREE, object, physicalTileM) {
  const uv = object.geometry?.getAttribute?.('uv');
  if (!uv || uv.count === 0) throw new Error(`${object.name} has no TEXCOORD_0/uv attribute`);

  let minU = Infinity;
  let minV = Infinity;
  let maxU = -Infinity;
  let maxV = -Infinity;
  for (let index = 0; index < uv.count; index += 1) {
    const u = uv.getX(index);
    const v = uv.getY(index);
    minU = Math.min(minU, u);
    minV = Math.min(minV, v);
    maxU = Math.max(maxU, u);
    maxV = Math.max(maxV, v);
  }

  object.geometry.computeBoundingBox();
  const size = new THREE.Vector3();
  object.geometry.boundingBox.getSize(size);
  const radiusM = Math.max((Math.abs(size.x) + Math.abs(size.z)) * 0.25, 0.25);
  const circumferenceM = 2 * Math.PI * radiusM;
  const verticalM = Math.max(Math.abs(size.y), 0.25);
  const repeatU = THREE.MathUtils.clamp(circumferenceM / physicalTileM, 8, 128);
  const repeatV = THREE.MathUtils.clamp(verticalM / physicalTileM, 8, 128);

  return {
    uvMin: new THREE.Vector2(minU, minV),
    uvSpan: new THREE.Vector2(Math.max(maxU - minU, 1e-4), Math.max(maxV - minV, 1e-4)),
    repeat: new THREE.Vector2(repeatU, repeatV),
    metrics: {
      uv_min: [minU, minV],
      uv_max: [maxU, maxV],
      uv_span: [Math.max(maxU - minU, 1e-4), Math.max(maxV - minV, 1e-4)],
      physical_tile_m: physicalTileM,
      radius_m: radiusM,
      circumference_m: circumferenceM,
      vertical_m: verticalM,
      repeat: [repeatU, repeatV]
    }
  };
}

function shellBounds(THREE, root, shellNames) {
  const box = new THREE.Box3();
  let found = 0;
  for (const name of shellNames) {
    const object = root.getObjectByName(name);
    if (!object) continue;
    object.updateWorldMatrix(true, false);
    box.expandByObject(object);
    found += 1;
  }
  const center = new THREE.Vector3();
  const size = new THREE.Vector3();
  box.getCenter(center);
  box.getSize(size);
  const sphere = new THREE.Sphere();
  box.getBoundingSphere(sphere);
  return { box, center, size, sphere, found };
}

function createFallbackController({
  viewerEl,
  reason,
  threeRevision,
  webgl2,
  expectedSha256,
  fadeStartM,
  fadeEndM,
  strengthNear
}) {
  const state = {
    schema_version: R2H_SCHEMA_VERSION,
    mode: 'base_normal_only',
    status: 'fallback',
    fallback: reason,
    three_revision: threeRevision,
    webgl2,
    base_normal: {
      texture_name: 'INT30_R2G_R1_LOCK_NormalGL_4K',
      normal_scale: [0.45, 0.45],
      convention: 'OpenGL +Y'
    },
    detail_normal: {
      expected_sha256: expectedSha256,
      blend: 'RNM',
      strength_near: strengthNear,
      fade_start_m: fadeStartM,
      fade_end_m: fadeEndM,
      active: false
    },
    applied: { shell_mesh_count: 0, material_clone_count: 0, detail_texture_instance_count: 0 },
    resources: { texture_count_delta: 0, shader_patch_count: 0, compiled_shader_count: 0 }
  };
  const syncDataset = () => {
    viewerEl.dataset.detailNormalMode = state.mode;
    viewerEl.dataset.detailNormalStatus = state.status;
    viewerEl.dataset.detailNormalAppliedShellCount = '0';
    viewerEl.dataset.detailNormalFallback = state.fallback;
  };
  syncDataset();
  return {
    getState: () => structuredClone(state),
    setEnabled: () => false,
    setNearStrength: () => false,
    weightForDistance: (distanceM) => strengthNear * detailDistanceWeight(distanceM, fadeStartM, fadeEndM),
    getShellCameraPose: () => null,
    dispose: () => {},
    syncDataset
  };
}

export async function installR2HDetailNormal({
  THREE,
  renderer,
  camera,
  root,
  viewerEl,
  textureUrl,
  expectedSha256,
  shellNames = DEFAULT_SHELL_NAMES,
  strengthNear = 0.55,
  fadeStartM = 3,
  fadeEndM = 20,
  physicalTileM = 0.30
}) {
  const threeRevision = String(THREE.REVISION);
  const webgl2 = Boolean(renderer.capabilities.isWebGL2);
  const derivatives = webgl2 || Boolean(renderer.extensions?.has?.('OES_standard_derivatives'));
  const maxTextures = Number(renderer.capabilities.maxTextures || 0);
  const shaderChunkCompatible =
    THREE.ShaderChunk?.normal_fragment_maps?.includes('USE_NORMALMAP_TANGENTSPACE') &&
    THREE.ShaderChunk?.normal_fragment_maps?.includes('vec3 mapN');

  if (threeRevision !== '160') {
    return createFallbackController({
      viewerEl, reason: `unsupported_three_revision_${threeRevision}`, threeRevision, webgl2,
      expectedSha256, fadeStartM, fadeEndM, strengthNear
    });
  }
  if (!derivatives || maxTextures < 4 || !shaderChunkCompatible) {
    const reason = !derivatives ? 'derivatives_unavailable' : maxTextures < 4 ? 'insufficient_texture_units' : 'shader_chunk_mismatch';
    return createFallbackController({
      viewerEl, reason, threeRevision, webgl2, expectedSha256, fadeStartM, fadeEndM, strengthNear
    });
  }

  let loaded;
  try {
    loaded = await loadVerifiedTexture(THREE, renderer, textureUrl, expectedSha256);
  } catch (error) {
    return createFallbackController({
      viewerEl, reason: `detail_texture_error:${error.message}`, threeRevision, webgl2,
      expectedSha256, fadeStartM, fadeEndM, strengthNear
    });
  }

  const detailTexture = loaded.texture;
  const bounds = shellBounds(THREE, root, shellNames);
  const records = [];
  const uniformSets = [];
  const uvContracts = [];
  let shaderPatchCount = 0;
  let compiledShaderCount = 0;
  let shaderFallbackCount = 0;
  let enabled = true;
  let currentStrengthNear = strengthNear;
  let status = 'active';
  let fallback = 'none';

  for (const shellName of shellNames) {
    const object = root.getObjectByName(shellName);
    if (!object?.isMesh) {
      status = 'fallback';
      fallback = `missing_shell:${shellName}`;
      continue;
    }

    let uvContract;
    try {
      uvContract = geometryUvContract(THREE, object, physicalTileM);
    } catch (error) {
      status = 'fallback';
      fallback = `uv_contract_error:${error.message}`;
      continue;
    }
    uvContracts.push({ shell: shellName, ...uvContract.metrics });

    const originals = Array.isArray(object.material) ? object.material.slice() : [object.material];
    const clones = originals.map((original, materialIndex) => {
      const clone = original.clone();
      clone.name = `${original.name || shellName}_R2H_RNM_${materialIndex}`;
      clone.userData = {
        ...clone.userData,
        r2h_detail_normal: R2H_PATCH_KEY,
        r2h_shell_name: shellName,
        r2h_base_normal_preserved: Boolean(clone.normalMap),
        r2h_base_normal_scale: clone.normalScale?.toArray?.() || null
      };
      const originalCompile = clone.onBeforeCompile.bind(clone);
      const uniforms = {
        map: { value: detailTexture },
        uvMin: { value: uvContract.uvMin },
        uvSpan: { value: uvContract.uvSpan },
        repeat: { value: uvContract.repeat },
        strength: { value: currentStrengthNear },
        fadeStart: { value: fadeStartM },
        fadeEnd: { value: fadeEndM }
      };
      uniformSets.push(uniforms);

      clone.onBeforeCompile = (shader, renderContext) => {
        originalCompile(shader, renderContext);
        if (
          !clone.normalMap ||
          !shader.fragmentShader.includes(NORMAL_PARS_TOKEN) ||
          !shader.fragmentShader.includes(NORMAL_MAPS_TOKEN)
        ) {
          shaderFallbackCount += 1;
          status = 'fallback';
          fallback = `shader_patch_token_or_base_normal_missing:${shellName}`;
          return;
        }
        shader.uniforms.r2hDetailNormalMap = uniforms.map;
        shader.uniforms.r2hDetailUvMin = uniforms.uvMin;
        shader.uniforms.r2hDetailUvSpan = uniforms.uvSpan;
        shader.uniforms.r2hDetailRepeat = uniforms.repeat;
        shader.uniforms.r2hDetailStrengthNear = uniforms.strength;
        shader.uniforms.r2hDetailFadeStartM = uniforms.fadeStart;
        shader.uniforms.r2hDetailFadeEndM = uniforms.fadeEnd;
        shader.fragmentShader = shader.fragmentShader
          .replace(NORMAL_PARS_TOKEN, R2H_NORMAL_PARS)
          .replace(NORMAL_MAPS_TOKEN, R2H_NORMAL_MAPS);
        compiledShaderCount += 1;
        clone.userData.r2h_compiled = true;
      };
      clone.customProgramCacheKey = () => `${R2H_PATCH_KEY}:${shellName}:${materialIndex}`;
      clone.needsUpdate = true;
      shaderPatchCount += 1;
      return clone;
    });

    object.material = Array.isArray(object.material) ? clones : clones[0];
    records.push({ object, originals, clones, shellName });
  }

  if (records.length !== shellNames.length || shaderPatchCount !== shellNames.length) {
    status = 'fallback';
    fallback = fallback === 'none' ? 'shell_or_material_count_mismatch' : fallback;
  }

  function cameraProbe() {
    const centerDistanceM = camera.position.distanceTo(bounds.sphere.center);
    const approximateSurfaceDistanceM = Math.max(0, centerDistanceM - bounds.sphere.radius);
    return {
      center_distance_m: centerDistanceM,
      approximate_surface_distance_m: approximateSurfaceDistanceM,
      approximate_detail_weight: enabled
        ? currentStrengthNear * detailDistanceWeight(approximateSurfaceDistanceM, fadeStartM, fadeEndM)
        : 0
    };
  }

  function getState() {
    return {
      schema_version: R2H_SCHEMA_VERSION,
      mode: 'onBeforeCompile_RNM',
      status: enabled ? status : 'disabled',
      fallback,
      three_revision: threeRevision,
      webgl2,
      capabilities: { derivatives, max_textures: maxTextures },
      base_normal: {
        texture_name: records[0]?.clones[0]?.normalMap?.name || 'unknown',
        normal_scale: records[0]?.clones[0]?.normalScale?.toArray?.() || null,
        convention: 'OpenGL +Y',
        preserved: records.every((record) => record.clones.every((material) => Boolean(material.normalMap)))
      },
      detail_normal: {
        texture_url: textureUrl,
        expected_sha256: expectedSha256,
        verified_sha256: loaded.actualSha256,
        bytes: loaded.byteLength,
        color_space: 'NoColorSpace',
        wrap: 'RepeatWrapping',
        blend: 'RNM',
        asset_candidate: 'low_strength_0.25',
        strength_near: currentStrengthNear,
        fade_start_m: fadeStartM,
        fade_end_m: fadeEndM,
        distance_metric: 'fragment_view_space_length_vViewPosition',
        uv_policy: 'per_shell_atlas_uv_normalized_physical_repeat',
        physical_tile_m: physicalTileM,
        active: enabled
      },
      applied: {
        shell_mesh_count: records.length,
        material_clone_count: records.reduce((sum, record) => sum + record.clones.length, 0),
        detail_texture_instance_count: 1
      },
      resources: {
        texture_count_delta: 1,
        shader_patch_count: shaderPatchCount,
        compiled_shader_count: compiledShaderCount,
        shader_fallback_count: shaderFallbackCount,
        layer_switch_material_growth: 0
      },
      sample_weights: {
        '1m': currentStrengthNear * detailDistanceWeight(1, fadeStartM, fadeEndM),
        '3m': currentStrengthNear * detailDistanceWeight(3, fadeStartM, fadeEndM),
        '8m': currentStrengthNear * detailDistanceWeight(8, fadeStartM, fadeEndM),
        '20m': currentStrengthNear * detailDistanceWeight(20, fadeStartM, fadeEndM)
      },
      camera_probe: cameraProbe(),
      shell_bounds: {
        center: bounds.center.toArray(),
        size: bounds.size.toArray(),
        sphere_radius_m: bounds.sphere.radius
      },
      uv_contracts: uvContracts
    };
  }

  function syncDataset() {
    const current = getState();
    viewerEl.dataset.detailNormalMode = current.mode;
    viewerEl.dataset.detailNormalStatus = current.status;
    viewerEl.dataset.detailNormalAppliedShellCount = String(current.applied.shell_mesh_count);
    viewerEl.dataset.detailNormalFallback = current.fallback;
    viewerEl.dataset.detailNormalWeight = current.camera_probe.approximate_detail_weight.toFixed(6);
  }

  function setEnabled(nextEnabled) {
    enabled = Boolean(nextEnabled);
    for (const uniforms of uniformSets) uniforms.strength.value = enabled ? currentStrengthNear : 0;
    syncDataset();
    return enabled;
  }

  function setNearStrength(value) {
    currentStrengthNear = THREE.MathUtils.clamp(Number(value) || 0, 0, 1);
    for (const uniforms of uniformSets) uniforms.strength.value = enabled ? currentStrengthNear : 0;
    syncDataset();
    return currentStrengthNear;
  }

  function getShellCameraPose(distanceFromSurfaceM, direction = new THREE.Vector3(0.92, 0, 0.38)) {
    const dir = direction.clone().normalize();
    const half = bounds.size.clone().multiplyScalar(0.5);
    const support = Math.abs(dir.x) * half.x + Math.abs(dir.y) * half.y + Math.abs(dir.z) * half.z;
    return {
      position: bounds.center.clone().addScaledVector(dir, support + Math.max(0.1, distanceFromSurfaceM)),
      target: bounds.center.clone(),
      requested_surface_distance_m: distanceFromSurfaceM
    };
  }

  function dispose() {
    for (const record of records) {
      record.object.material = Array.isArray(record.object.material) ? record.originals : record.originals[0];
      for (const clone of record.clones) clone.dispose();
    }
    detailTexture.dispose();
    status = 'disposed';
    enabled = false;
    syncDataset();
  }

  syncDataset();
  return {
    getState,
    setEnabled,
    setNearStrength,
    weightForDistance: (distanceM) =>
      (enabled ? currentStrengthNear : 0) * detailDistanceWeight(distanceM, fadeStartM, fadeEndM),
    getShellCameraPose,
    dispose,
    syncDataset
  };
}

export const R2H_DETAIL_NORMAL_CONTRACT = {
  schema_version: R2H_SCHEMA_VERSION,
  patch_key: R2H_PATCH_KEY,
  shell_names: DEFAULT_SHELL_NAMES.slice(),
  blend: 'RNM',
  detail_asset: 'low_strength_0.25',
  fade_start_m: 3,
  fade_end_m: 20,
  physical_tile_m: 0.30
};
