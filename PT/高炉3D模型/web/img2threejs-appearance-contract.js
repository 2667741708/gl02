import * as THREE from "three";

export const IMG2THREEJS_APPEARANCE_CONTRACT=Object.freeze({
  schema:"bf3d.img2threejs.appearance.v2",
  source:"WEB_60_IMG2THREEJS_20260725_R4_RING_SEMANTICS",
  renderer:Object.freeze({
    outputColorSpace:"srgb",
    toneMapping:"aces-filmic",
    toneMappingExposure:1.22,
    maxPixelRatio:2,
    shadowMapType:"pcf-soft",
  }),
  scene:Object.freeze({
    fogColor:0x111719,
    fogDensity:.0075,
    groundColor:0x141a1b,
    groundRoughness:.94,
    groundMetalness:.05,
  }),
  camera:Object.freeze({
    fov:34,
    near:.1,
    far:400,
  }),
  lights:Object.freeze({
    hemisphere:Object.freeze({sky:0xc3d8d6,ground:0x1b1e1d,intensity:1.25}),
    key:Object.freeze({color:0xffd3ab,intensity:3.85,position:Object.freeze([-24,42,34])}),
    rim:Object.freeze({color:0x6fcdf0,intensity:2.15,position:Object.freeze([26,36,-28])}),
    fill:Object.freeze({color:0x9fb5b2,intensity:1.15,position:Object.freeze([8,18,32])}),
  }),
  textures:Object.freeze({
    roughness:"base_roughness.png",
    normal:"base_normal.png",
    repeat:Object.freeze([3,8]),
    anisotropy:8,
    normalScale:Object.freeze([.24,.24]),
  }),
  materials:Object.freeze({
    shell:Object.freeze({type:"MeshPhysicalMaterial",name:"R2 aged shell",color:0x66706a,roughness:.78,metalness:.58,clearcoat:.04,clearcoatRoughness:.84}),
    dark:Object.freeze({type:"MeshStandardMaterial",name:"dark solid structural steel",color:0x202625,roughness:.76,metalness:.8}),
    access:Object.freeze({type:"MeshStandardMaterial",name:"bright galvanized access steel",color:0xa7b0ab,roughness:.54,metalness:.74}),
    heat:Object.freeze({type:"MeshStandardMaterial",name:"heat-darkened metal",color:0x6e4a35,roughness:.34,metalness:.86}),
    orange:Object.freeze({type:"MeshStandardMaterial",name:"muted tuyere collar",color:0xa94f23,roughness:.54,metalness:.62}),
    bodySensor:Object.freeze({type:"MeshStandardMaterial",name:"measured body temperature point identity",color:0x78d6c2,emissive:0x245d54,emissiveIntensity:1.15,roughness:.38,metalness:.28}),
    formalSensor:Object.freeze({type:"MeshStandardMaterial",name:"formal process point identity",color:0x9eb8c0,emissive:0x263d43,emissiveIntensity:.85,roughness:.42,metalness:.34}),
    pressureSensor:Object.freeze({type:"MeshStandardMaterial",name:"measured static pressure overlay identity",color:0xe0b653,emissive:0x614913,emissiveIntensity:1.05,roughness:.44,metalness:.22}),
    thermalIdentityBand:Object.freeze({type:"MeshBasicMaterial",name:"non-physical segmented thermal layer identity",color:0x50e0cf,transparent:true,opacity:.78,depthWrite:false,side:2,toneMapped:false,polygonOffset:true,polygonOffsetFactor:-1,polygonOffsetUnits:-1}),
    pressureIdentityBand:Object.freeze({type:"MeshBasicMaterial",name:"non-physical segmented static pressure layer identity",color:0xf2c65b,transparent:true,opacity:.9,depthWrite:false,side:2,toneMapped:false,polygonOffset:true,polygonOffsetFactor:-1,polygonOffsetUnits:-1}),
    tapholeGlow:Object.freeze({type:"MeshStandardMaterial",name:"taphole warm state illustration",color:0x93451f,emissive:0x5c1d08,emissiveIntensity:.65,roughness:.52,metalness:.5}),
    clay:Object.freeze({type:"MeshStandardMaterial",name:"review clay",color:0x8a918d,roughness:.82,metalness:.12}),
  }),
});

const textureCache=new Map();

function resolveTextureUrl(baseUrl,fileName){
  return new URL(fileName,new URL(baseUrl,document.baseURI)).href;
}

function loadTexture(url){
  if(textureCache.has(url))return textureCache.get(url);
  const promise=new Promise((resolve,reject)=>{
    new THREE.TextureLoader().load(url,texture=>{
      texture.wrapS=texture.wrapT=THREE.RepeatWrapping;
      texture.repeat.set(...IMG2THREEJS_APPEARANCE_CONTRACT.textures.repeat);
      texture.anisotropy=IMG2THREEJS_APPEARANCE_CONTRACT.textures.anisotropy;
      resolve(texture);
    },undefined,reject);
  }).catch(error=>{
    textureCache.delete(url);
    throw error;
  });
  textureCache.set(url,promise);
  return promise;
}

function standard(spec){
  const {type:ignoredType,...parameters}=spec;
  return new THREE.MeshStandardMaterial(parameters);
}

export async function createImg2ThreejsMaterialSet({textureBaseUrl}){
  const contract=IMG2THREEJS_APPEARANCE_CONTRACT;
  const [roughness,normal]=await Promise.all([
    loadTexture(resolveTextureUrl(textureBaseUrl,contract.textures.roughness)),
    loadTexture(resolveTextureUrl(textureBaseUrl,contract.textures.normal)),
  ]);
  const {type:ignoredShellType,...shellParameters}=contract.materials.shell;
  const shell=new THREE.MeshPhysicalMaterial({
    ...shellParameters,
    normalMap:normal,
    normalScale:new THREE.Vector2(...contract.textures.normalScale),
    roughnessMap:roughness,
  });
  const {type:ignoredThermalBandType,...thermalBandParameters}=contract.materials.thermalIdentityBand;
  const {type:ignoredPressureBandType,...pressureBandParameters}=contract.materials.pressureIdentityBand;
  const thermalIdentityBand=new THREE.MeshBasicMaterial(thermalBandParameters);
  const pressureIdentityBand=new THREE.MeshBasicMaterial(pressureBandParameters);
  return {
    shell,
    dark:standard(contract.materials.dark),
    access:standard(contract.materials.access),
    heat:standard(contract.materials.heat),
    orange:standard(contract.materials.orange),
    bodySensor:standard(contract.materials.bodySensor),
    formalSensor:standard(contract.materials.formalSensor),
    pressureSensor:standard(contract.materials.pressureSensor),
    thermalIdentityBand,
    pressureIdentityBand,
    tapholeGlow:standard(contract.materials.tapholeGlow),
    clay:standard(contract.materials.clay),
    textures:{roughness,normal},
  };
}

export function createImg2ThreejsSegmentedIdentityRing({
  radius,
  width=.05,
  y=0,
  material,
  name="non-physical-segmented-identity-band",
  segments=120,
  dashSegments=3,
  gapSegments=2,
}){
  const safeRadius=Math.max(Number(radius)||0,.1);
  const safeWidth=Math.max(Number(width)||0,.012);
  const safeSegments=Math.max(24,Math.floor(Number(segments)||120));
  const safeDash=Math.max(1,Math.floor(Number(dashSegments)||3));
  const safeGap=Math.max(1,Math.floor(Number(gapSegments)||2));
  const innerRadius=Math.max(safeRadius-safeWidth*.5,.05);
  const outerRadius=safeRadius+safeWidth*.5;
  const positions=[];
  const normals=[];
  const uvs=[];
  const indices=[];
  let vertexOffset=0;
  for(let index=0;index<safeSegments;index++){
    if(index%(safeDash+safeGap)>=safeDash)continue;
    const angle0=index/safeSegments*Math.PI*2;
    const angle1=(index+1)/safeSegments*Math.PI*2;
    positions.push(
      Math.cos(angle0)*innerRadius,0,Math.sin(angle0)*innerRadius,
      Math.cos(angle0)*outerRadius,0,Math.sin(angle0)*outerRadius,
      Math.cos(angle1)*outerRadius,0,Math.sin(angle1)*outerRadius,
      Math.cos(angle1)*innerRadius,0,Math.sin(angle1)*innerRadius,
    );
    normals.push(0,1,0,0,1,0,0,1,0,0,1,0);
    uvs.push(0,0,1,0,1,1,0,1);
    indices.push(
      vertexOffset,vertexOffset+1,vertexOffset+2,
      vertexOffset,vertexOffset+2,vertexOffset+3,
    );
    vertexOffset+=4;
  }
  const geometry=new THREE.BufferGeometry();
  geometry.setAttribute("position",new THREE.Float32BufferAttribute(positions,3));
  geometry.setAttribute("normal",new THREE.Float32BufferAttribute(normals,3));
  geometry.setAttribute("uv",new THREE.Float32BufferAttribute(uvs,2));
  geometry.setIndex(indices);
  geometry.computeBoundingSphere();
  const ring=new THREE.Mesh(geometry,material);
  ring.name=name;
  ring.position.y=y;
  ring.renderOrder=6;
  ring.userData={
    semanticKind:"non_physical_segmented_identity_band",
    physical:false,
    segmented:true,
    dashSegments:safeDash,
    gapSegments:safeGap,
  };
  return ring;
}

export function applyImg2ThreejsRendererContract(renderer){
  const contract=IMG2THREEJS_APPEARANCE_CONTRACT.renderer;
  renderer.setPixelRatio(Math.min(window.devicePixelRatio||1,contract.maxPixelRatio));
  renderer.outputColorSpace=THREE.SRGBColorSpace;
  renderer.toneMapping=THREE.ACESFilmicToneMapping;
  renderer.toneMappingExposure=contract.toneMappingExposure;
  renderer.shadowMap.enabled=true;
  renderer.shadowMap.type=THREE.PCFSoftShadowMap;
}

export function applyImg2ThreejsSceneContract(scene){
  const contract=IMG2THREEJS_APPEARANCE_CONTRACT.scene;
  scene.fog=new THREE.FogExp2(contract.fogColor,contract.fogDensity);
}

export function createImg2ThreejsLightRig(){
  const contract=IMG2THREEJS_APPEARANCE_CONTRACT.lights;
  const rig=new THREE.Group();
  rig.name="IMG2THREEJS_APPEARANCE_LIGHT_RIG_V1";
  const hemisphere=new THREE.HemisphereLight(contract.hemisphere.sky,contract.hemisphere.ground,contract.hemisphere.intensity);
  hemisphere.name="IMG2THREEJS_HEMISPHERE";
  const key=new THREE.DirectionalLight(contract.key.color,contract.key.intensity);
  key.name="IMG2THREEJS_KEY";
  key.position.set(...contract.key.position);
  key.castShadow=true;
  key.shadow.mapSize.set(2048,2048);
  key.shadow.camera.left=key.shadow.camera.bottom=-42;
  key.shadow.camera.right=key.shadow.camera.top=42;
  const rim=new THREE.DirectionalLight(contract.rim.color,contract.rim.intensity);
  rim.name="IMG2THREEJS_RIM";
  rim.position.set(...contract.rim.position);
  const fill=new THREE.DirectionalLight(contract.fill.color,contract.fill.intensity);
  fill.name="IMG2THREEJS_FILL";
  fill.position.set(...contract.fill.position);
  rig.add(hemisphere,key,rim,fill);
  rig.userData={hemisphere,key,rim,fill,contractVersion:contract.schema};
  return rig;
}

export function createImg2ThreejsGroundMaterial(){
  const contract=IMG2THREEJS_APPEARANCE_CONTRACT.scene;
  return new THREE.MeshStandardMaterial({
    name:"IMG2THREEJS_GROUND",
    color:contract.groundColor,
    roughness:contract.groundRoughness,
    metalness:contract.groundMetalness,
  });
}
