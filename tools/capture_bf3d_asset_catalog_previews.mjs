import { mkdir, writeFile } from "node:fs/promises";
import path from "node:path";

const playwrightModule = await import(
  process.env.BF_PLAYWRIGHT_CORE_URL || "playwright-core"
);
const { chromium } = playwrightModule;

const workspace = process.cwd();
const catalogRoot = path.join(workspace, "PT", "高炉3D模型", "模型资产库");
const baseUrl =
  "http://127.0.0.1:8096/PT/%E9%AB%98%E7%82%893D%E6%A8%A1%E5%9E%8B/" +
  "%E6%A8%A1%E5%9E%8B%E8%B5%84%E4%BA%A7%E5%BA%93/";
const executablePath =
  "C:/Users/hmw20/AppData/Local/ms-playwright/chromium-1228/chrome-win64/chrome.exe";
const assets = [
  {
    folder: "01_程序化高炉_R3冻结版",
    file: "GL02_IMG2THREEJS_PROGRAMMATIC_R3_FROZEN.glb",
    title: "程序化高炉 R3 冻结版",
  },
  {
    folder: "02_正式GLB语义底座",
    file: "gl02_blast_furnace.glb",
    title: "正式 GLB 语义底座",
  },
  {
    folder: "03_V5高质PBR炉壳",
    file: "gl02_blast_furnace_material_review.v5.glb",
    title: "V5 高质 PBR 炉壳",
  },
  {
    folder: "04_IMG2THREEJS结构表面_R3",
    file: "GL02_FORMAL_IMG2THREEJS_STRUCTURAL_SURFACE_R3.glb",
    title: "img2threejs 结构表面 R3",
  },
  {
    folder: "05_IMG2THREEJS环语义_R4",
    file: "GL02_FORMAL_IMG2THREEJS_RING_SEMANTICS_R4.glb",
    title: "img2threejs 环语义 R4",
  },
  {
    folder: "06_IMG2THREEJS检修通道_R5",
    file: "GL02_FORMAL_IMG2THREEJS_MAINTENANCE_ACCESS_R5.glb",
    title: "img2threejs 检修通道 R5",
  },
  {
    folder: "07_IMG2THREEJS炉顶除尘_R6",
    file: "GL02_FORMAL_IMG2THREEJS_TOP_FEED_GAS_CLEANING_R6.glb",
    title: "img2threejs 炉顶与除尘 R6",
  },
  {
    folder: "08_静压力18点覆盖层",
    file: "VIS30_STATIC_PRESSURE_18_ONLY_OVERLAY.glb",
    title: "炉体静压力 18 点覆盖层",
    direction: [1.2, 0.4, 1.5],
  },
  {
    folder: "09_高炉本体133点Billboard",
    file: "GL02_FURNACE_BODY_R1.glb",
    title: "高炉本体与 133 点 Billboard",
    previewRoute: "preview/",
  },
  {
    folder: "09_高炉本体133点Billboard_cn",
    file: "GL02_FURNACE_BODY_R1.glb",
    title: "高炉本体与 133 点中文语义 Billboard",
    previewRoute: "preview/",
  },
];

function encodePath(parts) {
  return parts.map((part) => encodeURIComponent(part)).join("/");
}

await mkdir(catalogRoot, { recursive: true });
const browser = await chromium.launch({ headless: true, executablePath });
const results = [];

try {
  for (const asset of assets) {
    const context = await browser.newContext({
      viewport: { width: 1440, height: 900 },
      deviceScaleFactor: 1,
    });
    const page = await context.newPage();
    const consoleErrors = [];
    const pageErrors = [];
    page.on("console", (message) => {
      if (message.type() === "error") consoleErrors.push(message.text());
    });
    page.on("pageerror", (error) => pageErrors.push(error.message));
    const output = path.join(catalogRoot, asset.folder, "网页预览.png");
    const assetUrl = `${baseUrl}${encodePath([asset.folder, asset.file])}`;
    try {
      if (asset.previewRoute) {
        const previewUrl = `${baseUrl}${encodePath([asset.folder, "preview"])}/`;
        await page.goto(previewUrl, { waitUntil: "networkidle", timeout: 120_000 });
        await page.waitForFunction(
          () =>
            document.body.dataset.loadState === "ready" &&
            window.__BF3D_FURNACE_BODY_BILLBOARD__?.passed === true,
          null,
          { timeout: 120_000 },
        );
        const info = await page.evaluate(() => {
          const contract = window.__BF3D_FURNACE_BODY_BILLBOARD__;
          return {
            nodes: contract.modelNodeCount,
            meshes: contract.modelMeshCount,
            totalBillboardCount: contract.totalBillboardCount,
            allBillboardsUseThreeSprite: contract.allBillboardsUseThreeSprite,
            contractPassed: contract.passed,
          };
        });
        await page.screenshot({ path: output, fullPage: false });
        results.push({
          ...asset,
          assetUrl,
          previewUrl,
          output,
          captureMode: "asset_runtime_preview",
          ...info,
          consoleErrors,
          pageErrors,
          passed:
            info.contractPassed === true &&
            info.totalBillboardCount === 133 &&
            info.allBillboardsUseThreeSprite === true &&
            consoleErrors.length === 0 &&
            pageErrors.length === 0,
        });
        continue;
      }
      await page.goto(baseUrl, { waitUntil: "domcontentloaded", timeout: 60_000 });
      await page.setContent(
        `<!doctype html>
        <html lang="zh-CN">
        <head>
          <meta charset="utf-8">
          <meta name="viewport" content="width=device-width,initial-scale=1">
          <script type="importmap">
            {
              "imports": {
                "three": "/高炉前端数据/libs/three/three.module.js",
                "three/addons/": "/高炉前端数据/libs/three/"
              }
            }
          </script>
          <style>
            *{box-sizing:border-box}
            html,body{margin:0;width:100%;height:100%;overflow:hidden;background:#101718;color:#f0eee6;font-family:SimSun,"宋体",serif}
            canvas{display:block;width:100%;height:100%}
            .title{position:fixed;left:28px;top:24px;z-index:2;padding:12px 16px;border:1px solid rgba(83,222,207,.5);background:rgba(9,18,20,.86);box-shadow:0 14px 36px rgba(0,0,0,.24)}
            .title small{display:block;color:#58ddd1;letter-spacing:.12em;margin-bottom:5px}
            .title strong{display:block;font-size:24px}
            .title span{display:block;margin-top:6px;color:#aab9b8;font:12px Consolas,monospace}
            .boundary{position:fixed;right:26px;bottom:22px;z-index:2;color:#9caaa9;font-size:13px}
          </style>
        </head>
        <body>
          <canvas id="asset-canvas"></canvas>
          <div class="title"><small>BF3D 模型资产库 · 网页预览</small><strong></strong><span></span></div>
          <div class="boundary">资产快照 · 固定相机与灯光 · 非生产路由</div>
        </body>
        </html>`,
        { waitUntil: "domcontentloaded" },
      );
      // Ignore the static directory shell's one-time favicon 404; validation starts
      // after the isolated asset viewer document is installed.
      consoleErrors.length = 0;
      pageErrors.length = 0;
      const info = await page.evaluate(
        async ({ url, title, file, direction }) => {
          const THREE = await import("three");
          const { GLTFLoader } = await import("three/addons/loaders/GLTFLoader.js");
          document.querySelector(".title strong").textContent = title;
          document.querySelector(".title span").textContent = file;
          const canvas = document.querySelector("#asset-canvas");
          const renderer = new THREE.WebGLRenderer({
            canvas,
            antialias: true,
            alpha: false,
            powerPreference: "high-performance",
          });
          renderer.setPixelRatio(1);
          renderer.setSize(innerWidth, innerHeight, false);
          renderer.outputColorSpace = THREE.SRGBColorSpace;
          renderer.toneMapping = THREE.ACESFilmicToneMapping;
          renderer.toneMappingExposure = 1.34;
          renderer.shadowMap.enabled = true;
          renderer.shadowMap.type = THREE.PCFSoftShadowMap;

          const scene = new THREE.Scene();
          scene.background = new THREE.Color(0x101718);
          scene.fog = new THREE.FogExp2(0x101718, 0.0045);
          const camera = new THREE.PerspectiveCamera(36, innerWidth / innerHeight, 0.02, 2500);
          scene.add(new THREE.HemisphereLight(0xcbe5df, 0x241d17, 1.35));
          const key = new THREE.DirectionalLight(0xffe0b0, 4.2);
          key.position.set(38, 64, 42);
          key.castShadow = true;
          scene.add(key);
          const rim = new THREE.DirectionalLight(0x63bdd4, 3.0);
          rim.position.set(-44, 32, -35);
          scene.add(rim);
          const fill = new THREE.DirectionalLight(0x9fc9c0, 1.2);
          fill.position.set(12, 20, -42);
          scene.add(fill);

          const gltf = await new GLTFLoader().loadAsync(url);
          const model = gltf.scene;
          model.traverse((object) => {
            if (!object.isMesh) return;
            object.castShadow = true;
            object.receiveShadow = true;
          });
          scene.add(model);
          model.updateWorldMatrix(true, true);
          const box = new THREE.Box3().setFromObject(model);
          if (box.isEmpty()) throw new Error(`模型边界为空：${file}`);
          const center = box.getCenter(new THREE.Vector3());
          const size = box.getSize(new THREE.Vector3());
          const radius = Math.max(size.length() * 0.5, 1);
          const dir = new THREE.Vector3(...(direction || [1, 0.48, 1.25])).normalize();
          const distance = radius / Math.tan(THREE.MathUtils.degToRad(camera.fov * 0.5)) * 1.08;
          camera.position.copy(center).addScaledVector(dir, distance);
          camera.near = Math.max(distance / 1200, 0.02);
          camera.far = Math.max(distance * 12, 500);
          camera.lookAt(center);
          camera.updateProjectionMatrix();

          const groundSize = Math.max(size.x, size.z, radius) * 2.8;
          const ground = new THREE.Mesh(
            new THREE.CircleGeometry(groundSize, 96),
            new THREE.MeshStandardMaterial({
              color: 0x263130,
              roughness: 0.96,
              metalness: 0.02,
            }),
          );
          ground.rotation.x = -Math.PI / 2;
          ground.position.set(center.x, box.min.y - Math.max(size.y * 0.006, 0.015), center.z);
          ground.receiveShadow = true;
          scene.add(ground);
          renderer.render(scene, camera);
          await new Promise((resolve) => requestAnimationFrame(() => {
            renderer.render(scene, camera);
            resolve();
          }));
          return {
            nodes: (() => {
              let count = 0;
              model.traverse((object) => { if (object !== model) count += 1; });
              return count;
            })(),
            meshes: (() => {
              let count = 0;
              model.traverse((object) => { if (object.isMesh) count += 1; });
              return count;
            })(),
            size: size.toArray(),
          };
        },
        {
          url: assetUrl,
          title: asset.title,
          file: asset.file,
          direction: asset.direction,
        },
      );
      await page.screenshot({ path: output, fullPage: true });
      results.push({
        ...asset,
        assetUrl,
        output,
        ...info,
        consoleErrors,
        pageErrors,
        passed: consoleErrors.length === 0 && pageErrors.length === 0,
      });
    } catch (error) {
      results.push({
        ...asset,
        assetUrl,
        output,
        consoleErrors,
        pageErrors,
        passed: false,
        error: error instanceof Error ? error.message : String(error),
      });
    } finally {
      await context.close();
    }
  }
} finally {
  await browser.close();
}

const report = {
  schema: "bf3d.asset_catalog_preview_capture.v1",
  generatedAt: new Date().toISOString(),
  catalogRoot,
  assetCount: results.length,
  passedCount: results.filter((item) => item.passed).length,
  failedCount: results.filter((item) => !item.passed).length,
  results,
  passed: results.every((item) => item.passed),
};
await writeFile(
  path.join(catalogRoot, "preview_capture_report.json"),
  `${JSON.stringify(report, null, 2)}\n`,
  "utf8",
);
process.stdout.write(`${JSON.stringify({
  assetCount: report.assetCount,
  passedCount: report.passedCount,
  failedCount: report.failedCount,
  passed: report.passed,
})}\n`);
if (!report.passed) process.exitCode = 1;
