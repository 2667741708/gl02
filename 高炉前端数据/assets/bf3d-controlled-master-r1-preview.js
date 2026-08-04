import * as THREE from "three";
import { OrbitControls } from "three/addons/controls/OrbitControls.js";
import { GLTFLoader } from "three/addons/loaders/GLTFLoader.js";

const ROOT = "../PT/高炉3D模型/work/ASSET_10_20260721_R1_CONTROLLED_MASTER/glb/";
const ASSETS = {
  whole:{file:"bf3d_full_assembly.r1.glb",meshes:48,sourceObjects:33,sensors:18,label:"整体高炉",visibility:"whole_exterior"},
  cutaway:{file:"bf3d_full_assembly.r1.glb",meshes:48,sourceObjects:33,sensors:18,label:"整体剖切",visibility:"whole_cutaway"},
  combined:{file:"bf3d_combined_review.r1.glb",meshes:23,sensors:18,label:"外壳+传感器"},
  base:{file:"bf3d_base.r1.glb",meshes:5,sensors:0,label:"基础炉体"},
  sensors:{file:"bf3d_sensors.r1.glb",meshes:18,sensors:18,label:"18点传感器"},
  structural:{file:"bf3d_structural_section.r1.glb",meshes:25,sourceObjects:10,sensors:0,label:"结构剖面"},
};
const viewport=document.querySelector("#viewport"),loading=document.querySelector("#loading");
const fields={state:document.querySelector("#state"),meshes:document.querySelector("#meshes"),materials:document.querySelector("#materials"),sensors:document.querySelector("#sensors"),bounds:document.querySelector("#bounds")};
const renderer=new THREE.WebGLRenderer({antialias:true,alpha:true});renderer.setPixelRatio(Math.min(devicePixelRatio,2));renderer.outputColorSpace=THREE.SRGBColorSpace;renderer.toneMapping=THREE.ACESFilmicToneMapping;renderer.toneMappingExposure=1.05;viewport.prepend(renderer.domElement);
const scene=new THREE.Scene();const camera=new THREE.PerspectiveCamera(38,1,.05,300);camera.position.set(18,-22,13);
const controls=new OrbitControls(camera,renderer.domElement);controls.enableDamping=true;controls.target.set(0,0,4);
scene.add(new THREE.HemisphereLight(0xdde7e4,0x15191a,1.65));const key=new THREE.DirectionalLight(0xfff3dc,3.0);key.position.set(8,-10,16);scene.add(key);const rim=new THREE.DirectionalLight(0x88b9c0,1.8);rim.position.set(-10,7,10);scene.add(rim);
const loader=new GLTFLoader();let current=null,requestId=0;
function resize(){const w=viewport.clientWidth,h=viewport.clientHeight;renderer.setSize(w,h,false);camera.aspect=w/h;camera.updateProjectionMatrix()}
new ResizeObserver(resize).observe(viewport);resize();
function dispose(root){root.traverse(o=>{if(o.geometry)o.geometry.dispose();const list=Array.isArray(o.material)?o.material:[o.material];list.filter(Boolean).forEach(m=>m.dispose())});scene.remove(root)}
function fit(root){const box=new THREE.Box3().setFromObject(root),size=box.getSize(new THREE.Vector3()),center=box.getCenter(new THREE.Vector3()),span=Math.max(size.x,size.y,size.z)||1;controls.target.copy(center);camera.position.set(center.x+span*1.15,center.y-span*1.55,center.z+span*.7);camera.near=Math.max(span/1000,.01);camera.far=span*20;camera.updateProjectionMatrix();controls.update();return {size,center}}
function setState(kind,text){document.body.dataset.loadState=kind;fields.state.textContent=text;fields.state.className=kind==="ready"?"ok":kind==="error"?"bad":"warn"}
async function loadAsset(id){const token=++requestId,contract=ASSETS[id];document.body.dataset.activeAsset=id;loading.hidden=false;loading.textContent=`正在加载${contract.label}…`;setState("loading","加载中");
  try{const gltf=await loader.loadAsync(ROOT+contract.file);if(token!==requestId){dispose(gltf.scene);return}if(current)dispose(current);current=gltf.scene;scene.add(current);let meshes=0,sensors=0,visibleMeshes=0;const mats=new Set();current.traverse(o=>{if(o.isMesh){meshes++;if(o.name.startsWith("GL02_INT30_PRESSURE_"))sensors++;if(contract.visibility==="whole_exterior"&&o.name.startsWith("SECTION_"))o.visible=false;if(contract.visibility==="whole_cutaway"&&!o.name.startsWith("SECTION_")&&!o.name.startsWith("GL02_INT30_PRESSURE_"))o.visible=false;if(o.visible)visibleMeshes++;(Array.isArray(o.material)?o.material:[o.material]).filter(Boolean).forEach(m=>mats.add(m.uuid))}});const b=fit(current),pass=meshes===contract.meshes&&sensors===contract.sensors;fields.meshes.textContent=`${meshes} / ${contract.meshes}（可见${visibleMeshes}）`;fields.materials.textContent=String(mats.size);fields.sensors.textContent=`${sensors} / ${contract.sensors}`;fields.bounds.textContent=`${b.size.x.toFixed(1)}×${b.size.y.toFixed(1)}×${b.size.z.toFixed(1)} m`;setState(pass?"ready":"error",pass?"可用":"合同不匹配");loading.hidden=true;window.__BF3D_MASTER_R1__={asset:id,file:contract.file,meshCount:meshes,visibleMeshCount:visibleMeshes,materialCount:mats.size,sensorCount:sensors,expectedMeshes:contract.meshes,expectedSensors:contract.sensors,bounds:[b.size.x,b.size.y,b.size.z],passed:pass};
  }catch(error){console.error(error);loading.textContent=`加载失败：${error.message}`;setState("error","加载失败");window.__BF3D_MASTER_R1__={asset:id,passed:false,error:String(error)}}}
document.querySelectorAll("[data-asset]").forEach(button=>button.addEventListener("click",()=>{document.querySelectorAll("[data-asset]").forEach(b=>b.classList.toggle("active",b===button));loadAsset(button.dataset.asset)}));
renderer.setAnimationLoop(()=>{controls.update();renderer.render(scene,camera)});loadAsset("whole");
