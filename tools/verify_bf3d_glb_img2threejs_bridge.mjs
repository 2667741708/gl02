import {mkdir, writeFile} from "node:fs/promises";
import path from "node:path";

const playwrightModule=await import(
  (typeof process!=="undefined"&&process.env?.BF_PLAYWRIGHT_CORE_URL)||"playwright-core"
);
const {chromium,firefox,webkit}=playwrightModule;

const URL="http://127.0.0.1:8096/PT/%E9%AB%98%E7%82%893D%E6%A8%A1%E5%9E%8B/work/WEB_60_GLB_IMG2THREEJS_BRIDGE_20260724_R1/preview/";
const OUT_DIR="D:/文件/冀南钢铁运行中第二版本/PT/高炉3D模型/work/WEB_60_GLB_IMG2THREEJS_BRIDGE_20260724_R1";
const CHROMIUM_VIEWPORTS=[[1280,720],[1366,768],[1440,900],[1546,864],[1920,1080],[1024,768],[768,1024],[390,844],[375,667]];
const REPRESENTATIVE_VIEWPORTS=[[1920,1080],[1366,768],[768,1024],[390,844]];
const ENGINES=[
  {name:"chromium",launcher:chromium,executablePath:"C:/Users/hmw20/AppData/Local/ms-playwright/chromium-1228/chrome-win64/chrome.exe",viewports:CHROMIUM_VIEWPORTS},
  {name:"firefox",launcher:firefox,executablePath:"C:/Users/hmw20/AppData/Local/ms-playwright/firefox-1532/firefox/firefox.exe",viewports:REPRESENTATIVE_VIEWPORTS},
  {name:"webkit",launcher:webkit,executablePath:"C:/Users/hmw20/AppData/Local/ms-playwright/webkit-2311/Playwright.exe",viewports:REPRESENTATIVE_VIEWPORTS},
];

function slug(engine,width,height){
  return `${engine}_${width}x${height}`;
}

async function observe(page){
  return page.evaluate(()=>{
    const root=document.documentElement;
    const canvas=document.querySelector("#scene")?.getBoundingClientRect();
    const bridge=window.__BF3D_GLB_IMG2THREEJS_BRIDGE__||{};
    const text=selector=>document.querySelector(selector)?.textContent?.trim()||"";
    return {
      loadState:document.body.dataset.loadState||"",
      appearanceMode:document.body.dataset.appearanceMode||"",
      title:text("h1"),
      runtime:text("#runtime-state"),
      appearance:text("#appearance-result"),
      contract:text("#contract-result"),
      canvas:canvas?{width:Math.round(canvas.width),height:Math.round(canvas.height)}:null,
      viewport:{width:innerWidth,height:innerHeight},
      scroll:{width:root.scrollWidth,height:root.scrollHeight},
      horizontalOverflow:root.scrollWidth>innerWidth+1,
      controls:{
        appearanceButtons:document.querySelectorAll(".segmented button").length,
        toggles:document.querySelectorAll('.switch-list input[type="checkbox"]').length,
        focusButtons:document.querySelectorAll(".button-grid button").length,
        presets:document.querySelectorAll("#furnace-preset option").length,
      },
      bridge:{
        passed:bridge.passed,
        formalNodeCount:bridge.formalNodeCount,
        formalSensorCount:bridge.formalSensorCount,
        bodyTemperatureSensorCount:bridge.bodyTemperatureSensorCount,
        thermalLayerCount:bridge.thermalLayerCount,
        thermalLayerCounts:bridge.thermalLayerCounts,
        staticPressureOverlayCount:bridge.staticPressureOverlayCount,
        tapholeCount:bridge.tapholeCount,
        tapholeMap:bridge.tapholeMap,
        formalShellSectionCount:bridge.formalShellSectionCount,
        cylindricalUvShellCount:bridge.cylindricalUvShellCount,
        diagnosticBandCount:bridge.diagnosticBandCount,
        pressureRingCount:bridge.pressureRingCount,
        thermalIdentityBandCount:bridge.thermalIdentityBandCount,
        pressureIdentityBandCount:bridge.pressureIdentityBandCount,
        identityBandSchema:bridge.identityBandSchema,
        identityBandsPhysical:bridge.identityBandsPhysical,
        ringSemanticSeparation:bridge.ringSemanticSeparation,
        maintenanceAccessSchema:bridge.maintenanceAccessSchema,
        fittedMaintenancePlatformCount:bridge.fittedMaintenancePlatformCount,
        fittedWalkwayDeckCount:bridge.fittedWalkwayDeckCount,
        fittedGuardrailRingCount:bridge.fittedGuardrailRingCount,
        fittedGuardrailPostCount:bridge.fittedGuardrailPostCount,
        fittedSupportBracketCount:bridge.fittedSupportBracketCount,
        fittedAccessLadderCount:bridge.fittedAccessLadderCount,
        fittedAccessLadderRungCount:bridge.fittedAccessLadderRungCount,
        platformLevelIds:bridge.platformLevelIds,
        platformSourceDisplayYs:bridge.platformSourceDisplayYs,
        topFeedGasCleaningSchema:bridge.topFeedGasCleaningSchema,
        fittedConveyorSystemCount:bridge.fittedConveyorSystemCount,
        fittedConveyorBeltCount:bridge.fittedConveyorBeltCount,
        fittedConveyorRollerCount:bridge.fittedConveyorRollerCount,
        fittedConveyorTrestleCount:bridge.fittedConveyorTrestleCount,
        fittedConveyorDischargeChuteCount:bridge.fittedConveyorDischargeChuteCount,
        fittedTopGasUptakeCount:bridge.fittedTopGasUptakeCount,
        fittedGasDuctCount:bridge.fittedGasDuctCount,
        fittedGravityDustCatcherCount:bridge.fittedGravityDustCatcherCount,
        fittedFineDustCollectorCount:bridge.fittedFineDustCollectorCount,
        fittedDustHopperCount:bridge.fittedDustHopperCount,
        fittedExternalProcessSupportCount:bridge.fittedExternalProcessSupportCount,
        fineDustCollectorEquipmentTypeStatus:bridge.fineDustCollectorEquipmentTypeStatus,
        fittedProgrammaticShellCount:bridge.fittedProgrammaticShellCount,
        fittedShellProfilePointCount:bridge.fittedShellProfilePointCount,
        fittedSteelRingCount:bridge.fittedSteelRingCount,
        fittedVerticalSeamCount:bridge.fittedVerticalSeamCount,
        fittedSurfacePatina:bridge.fittedSurfacePatina,
        fittedSurfaceTangentSpace:bridge.fittedSurfaceTangentSpace,
        hybridSuppressedEquipmentCount:bridge.hybridSuppressedEquipmentCount,
        appearanceContractVersion:bridge.appearanceContractVersion,
        appearanceContractSource:bridge.appearanceContractSource,
        rendererContract:bridge.rendererContract,
        sharedAppearanceContract:bridge.sharedAppearanceContract,
        appearanceParity:bridge.appearanceParity,
        v5Loaded:bridge.v5Loaded,
        v5ShellMeshCount:bridge.v5ShellMeshCount,
        productionRouteChanged:bridge.productionRouteChanged,
        truthBoundary:bridge.truthBoundary,
        textureBudget:bridge.textureBudget,
      },
    };
  });
}

async function exerciseControls(page,{loadV5=false}={}){
  await page.locator("#mode-original").click();
  if((await page.locator("#mode-original").getAttribute("aria-pressed"))!=="true")throw new Error("原始材质模式未启用");
  await page.locator("#mode-hybrid").click();
  if((await page.locator("#mode-hybrid").getAttribute("aria-pressed"))!=="true")throw new Error("程序化钢灰模式未恢复");

  for(const value of ["thermal-down","thermal-up","pressure","normal"]){
    await page.locator("#furnace-preset").selectOption(value);
    if((await page.locator("#furnace-preset").inputValue())!==value)throw new Error(`炉况视觉预设未切换：${value}`);
  }

  for(const selector of ["#toggle-equipment","#toggle-shell-detail","#toggle-sensors","#toggle-pressure","#toggle-labels"]){
    const input=page.locator(selector);
    await input.uncheck();
    if(await input.isChecked())throw new Error(`覆盖层未关闭：${selector}`);
  }
  await page.locator("#show-all").click();
  for(const selector of ["#toggle-equipment","#toggle-shell-detail","#toggle-sensors","#toggle-pressure","#toggle-internal","#toggle-labels"]){
    if(!(await page.locator(selector).isChecked()))throw new Error(`全部显示未恢复：${selector}`);
  }
  await page.locator("#toggle-internal").uncheck();

  await page.locator("#focus-north").click();
  if((await page.locator("#selection-title").textContent())?.trim()!=="北出铁口")throw new Error("北出铁口定位未反馈");
  await page.locator("#focus-south").click();
  if((await page.locator("#selection-title").textContent())?.trim()!=="南出铁口")throw new Error("南出铁口定位未反馈");
  await page.locator("#focus-pressure").click();
  await page.locator("#focus-layers").click();
  await page.locator("#focus-top-system").click();
  await page.locator("#reset-view").click();

  const rotate=page.locator("#auto-rotate");
  await rotate.click();
  if((await rotate.getAttribute("aria-pressed"))!=="true")throw new Error("自动旋转未启用");
  await rotate.click();
  if((await rotate.getAttribute("aria-pressed"))!=="false")throw new Error("自动旋转未关闭");

  if(loadV5){
    await page.locator("#mode-v5").click();
    await page.waitForFunction(()=>window.__BF3D_GLB_IMG2THREEJS_BRIDGE__?.v5Loaded===true,{timeout:120000});
    const v5=await page.evaluate(()=>window.__BF3D_GLB_IMG2THREEJS_BRIDGE__);
    if(v5.v5ShellMeshCount!==5)throw new Error(`V5 壳体网格数错误：${v5.v5ShellMeshCount}`);
    await page.locator("#mode-hybrid").click();
  }
}

function validate(observation,consoleErrors,pageErrors,requestFailures){
  const failures=[];
  const bridge=observation.bridge;
  if(observation.loadState!=="ready")failures.push(`loadState=${observation.loadState}`);
  if(observation.horizontalOverflow)failures.push(`页面横向溢出 ${observation.scroll.width}>${observation.viewport.width}`);
  if(!observation.canvas||observation.canvas.width<280||observation.canvas.height<300)failures.push("三维画布尺寸不足");
  if(observation.controls.appearanceButtons!==3)failures.push("外观模式按钮不是 3 个");
  if(observation.controls.toggles!==6)failures.push("语义开关不是 6 个");
  if(observation.controls.focusButtons!==7)failures.push("视角按钮不是 7 个");
  if(observation.controls.presets!==4)failures.push("炉况视觉预设不是 4 个");
  if(observation.contract!=="合同通过"||!bridge.passed)failures.push("运行合同未通过");
  if(bridge.formalNodeCount!==190)failures.push(`正式节点 ${bridge.formalNodeCount} != 190`);
  if(bridge.formalSensorCount!==115)failures.push(`正式点位 ${bridge.formalSensorCount} != 115`);
  if(bridge.bodyTemperatureSensorCount!==80)failures.push(`炉体测温 ${bridge.bodyTemperatureSensorCount} != 80`);
  if(bridge.thermalLayerCount!==10||Object.values(bridge.thermalLayerCounts||{}).some(count=>count!==8))failures.push("L7～L16 不是 10×8");
  if(bridge.staticPressureOverlayCount!==18)failures.push(`静压力覆盖 ${bridge.staticPressureOverlayCount} != 18`);
  if(bridge.tapholeCount!==2||bridge.tapholeMap?.north!=="T_taphole_2"||bridge.tapholeMap?.south!=="T_taphole_1")failures.push("南北出铁口映射不符合原始 GLB 坐标");
  if(bridge.formalShellSectionCount!==5)failures.push(`五区炉壳 ${bridge.formalShellSectionCount} != 5`);
  if(bridge.cylindricalUvShellCount!==5)failures.push(`圆柱 UV 炉壳 ${bridge.cylindricalUvShellCount} != 5`);
  if(bridge.diagnosticBandCount!==10)failures.push(`诊断层环 ${bridge.diagnosticBandCount} != 10`);
  if(bridge.pressureRingCount!==3)failures.push(`静压力环 ${bridge.pressureRingCount} != 3`);
  if(
    bridge.thermalIdentityBandCount!==10||
    bridge.pressureIdentityBandCount!==3||
    bridge.identityBandSchema!=="bf3d.non_physical_segmented_identity_band.v1"||
    bridge.identityBandsPhysical!==false||
    bridge.ringSemanticSeparation!==true
  )failures.push("实体钢构与非实体分段数据带的语义边界缺失");
  if(
    bridge.maintenanceAccessSchema!=="bf3d.physical_maintenance_access.v1"||
    bridge.fittedMaintenancePlatformCount!==7||
    bridge.fittedWalkwayDeckCount!==7||
    bridge.fittedGuardrailRingCount!==14||
    bridge.fittedGuardrailPostCount!==194||
    bridge.fittedSupportBracketCount!==100||
    bridge.fittedAccessLadderCount!==6||
    bridge.fittedAccessLadderRungCount<=60||
    bridge.platformLevelIds?.join(",")!=="P01,P02,P03,P04,P05,P06,P07"||
    bridge.platformSourceDisplayYs?.join(",")!=="8.1,13.25,18.15,29.2,40.9,51.1,55.7"
  )failures.push("R5 检修平台、护栏、牛腿或连接梯道合同缺失");
  if(
    bridge.topFeedGasCleaningSchema!=="bf3d.external_top_feed_gas_cleaning.v1"||
    bridge.fittedConveyorSystemCount!==1||
    bridge.fittedConveyorBeltCount!==1||
    bridge.fittedConveyorRollerCount!==18||
    bridge.fittedConveyorTrestleCount!==4||
    bridge.fittedConveyorDischargeChuteCount!==1||
    bridge.fittedTopGasUptakeCount!==4||
    bridge.fittedGasDuctCount!==3||
    bridge.fittedGravityDustCatcherCount!==1||
    bridge.fittedFineDustCollectorCount!==1||
    bridge.fittedDustHopperCount!==5||
    bridge.fittedExternalProcessSupportCount!==16||
    bridge.fineDustCollectorEquipmentTypeStatus!=="candidate_pending_engineering_confirmation"
  )failures.push("R6 上料传送带、煤气管路、重力除尘或静压/精除尘候选合同缺失");
  if(bridge.fittedProgrammaticShellCount!==1)failures.push(`程序化拟合炉壳 ${bridge.fittedProgrammaticShellCount} != 1`);
  if(bridge.fittedShellProfilePointCount!==72)failures.push(`炉壳轮廓采样 ${bridge.fittedShellProfilePointCount} != 72`);
  if(bridge.fittedSteelRingCount!==13)failures.push(`程序化钢圈 ${bridge.fittedSteelRingCount} != 13`);
  if(bridge.fittedVerticalSeamCount!==12)failures.push(`程序化板缝 ${bridge.fittedVerticalSeamCount} != 12`);
  if(bridge.fittedSurfacePatina!=="deterministic_vertex_color_macro_streaks"||bridge.fittedSurfaceTangentSpace!==true)failures.push("炉壳污迹或切线空间合同缺失");
  if(bridge.hybridSuppressedEquipmentCount!==3)failures.push(`R6 应替换的旧简化平台/塔架/煤气管数量 ${bridge.hybridSuppressedEquipmentCount} != 3`);
  if(bridge.appearanceContractVersion!=="bf3d.img2threejs.appearance.v2"||bridge.appearanceContractSource!=="WEB_60_IMG2THREEJS_20260725_R4_RING_SEMANTICS"||bridge.sharedAppearanceContract!==true)failures.push("未与程序化模型共用外观合同");
  if(bridge.rendererContract?.toneMappingExposure!==1.22||bridge.rendererContract?.toneMapping!=="aces-filmic")failures.push("ACES/曝光合同不一致");
  if(bridge.appearanceParity!=="shared_renderer_material_pbr_plus_fitted_structural_steel_maintenance_access_and_external_top_feed_gas_cleaning_r6")failures.push("R6 结构表面、检修通道和外部系统一致性边界缺失");
  if(bridge.productionRouteChanged!==false)failures.push("候选错误声明已切换生产路由");
  if(bridge.textureBudget?.v5LoadPolicy!=="desktop_on_demand")failures.push("V5 未保持桌面按需加载策略");
  for(const item of consoleErrors)failures.push(`console: ${item}`);
  for(const item of pageErrors)failures.push(`pageerror: ${item}`);
  for(const item of requestFailures)failures.push(`requestfailed: ${item}`);
  return failures;
}

function markdown(results,startedAt){
  const failures=results.filter(item=>!item.passed);
  const lines=[
    "# GLB × img2threejs 混合预览跨引擎/视口报告",
    "",
    `- 开始时间：${startedAt}`,
    `- 页面：${URL}`,
    `- 组合：${results.length}`,
    `- 通过：${results.length-failures.length}`,
    `- 失败：${failures.length}`,
    "",
    "| 引擎 | CSS viewport | 状态 | 横向溢出 | 正式节点 | 正式点位 | L7～L16 | 静压力 | 南北铁口 | 截图 |",
    "|---|---:|---|---|---:|---:|---:|---:|---:|---|",
  ];
  for(const result of results){
    const b=result.observation.bridge;
    lines.push(`| ${result.engine} | ${result.viewport.width}×${result.viewport.height} | ${result.passed?"通过":"失败"} | ${result.observation.horizontalOverflow?"有":"无"} | ${b.formalNodeCount??"—"} | ${b.formalSensorCount??"—"} | ${b.thermalLayerCount??"—"} | ${b.staticPressureOverlayCount??"—"} | ${b.tapholeCount??"—"} | ${result.screenshot} |`);
  }
  lines.push(
    "",
    "## 额外桌面门",
    "",
    "- Chromium 1440×900 执行 V5 PBR 壳体按需加载，要求五个壳体网格加载成功，再恢复程序化同款。",
    "- 默认 GLB 外观必须使用 `bf3d.img2threejs.appearance.v2` 同源合同，并包含 R5 炉壳/检修通道，以及 R6 上料传送带、18 个托辊、4 座支架、4 根煤气上升管、3 段煤气管路、1 台重力除尘器和 1 台静压/精除尘候选。",
    "- 所有组合执行原始/程序化外观切换、四个视觉预设、六个语义开关、南北出铁口定位、静压力/L7～L16/炉顶与除尘聚焦和自动旋转启停。",
    "- 页面、控制台和资源错误必须为 0；正式 8092 路由保持未切换。",
  );
  if(failures.length){
    lines.push("","## 失败项","");
    for(const result of failures)lines.push(`- ${result.engine} ${result.viewport.width}×${result.viewport.height}：${result.failures.join("；")}`);
  }
  return `${lines.join("\n")}\n`;
}

async function main(){
  const startedAt=new Date().toISOString();
  const screenshotDir=path.join(OUT_DIR,"screenshots","matrix");
  const reportDir=path.join(OUT_DIR,"reports");
  await mkdir(screenshotDir,{recursive:true});
  await mkdir(reportDir,{recursive:true});
  const allResults=[];
  for(const engine of ENGINES){
    const browser=await engine.launcher.launch({headless:true,executablePath:engine.executablePath});
    try{
      for(const [width,height] of engine.viewports){
        const page=await browser.newPage({viewport:{width,height},deviceScaleFactor:1});
        const consoleErrors=[];
        const pageErrors=[];
        const requestFailures=[];
        page.on("console",message=>{if(message.type()==="error")consoleErrors.push(message.text())});
        page.on("pageerror",error=>pageErrors.push(String(error)));
        page.on("requestfailed",request=>requestFailures.push(`${request.method()} ${request.url()} ${request.failure()?.errorText||""}`));
        const failures=[];
        let observation={bridge:{},controls:{},horizontalOverflow:false,viewport:{width,height},scroll:{}};
        const screenshotName=`${slug(engine.name,width,height)}.png`;
        const screenshotPath=path.join(screenshotDir,screenshotName);
        try{
          await page.goto(URL,{waitUntil:"networkidle",timeout:90000});
          await page.waitForFunction(()=>document.body.dataset.loadState==="ready",{timeout:90000});
          await exerciseControls(page,{loadV5:engine.name==="chromium"&&width===1440&&height===900});
          observation=await observe(page);
          failures.push(...validate(observation,consoleErrors,pageErrors,requestFailures));
          await page.screenshot({path:screenshotPath,fullPage:true});
        }catch(error){
          failures.push(error?.stack||String(error));
          try{await page.screenshot({path:screenshotPath,fullPage:true})}catch{}
        }finally{
          await page.close();
        }
        allResults.push({
          engine:engine.name,
          viewport:{width,height},
          passed:failures.length===0,
          failures,
          observation,
          consoleErrors,
          pageErrors,
          requestFailures,
          screenshot:path.relative(OUT_DIR,screenshotPath).replaceAll("\\","/"),
        });
      }
    }finally{
      await browser.close();
    }
  }
  const report={
    schema:"bf3d.glb_img2threejs_bridge.browser_matrix.v1",
    startedAt,
    completedAt:new Date().toISOString(),
    url:URL,
    combinations:allResults.length,
    passed:allResults.every(item=>item.passed),
    passedCount:allResults.filter(item=>item.passed).length,
    failedCount:allResults.filter(item=>!item.passed).length,
    results:allResults,
  };
  await writeFile(path.join(reportDir,"browser_matrix.json"),`${JSON.stringify(report,null,2)}\n`,"utf8");
  await writeFile(path.join(reportDir,"browser_matrix.md"),markdown(allResults,startedAt),"utf8");
  console.log(`BF3D_GLB_IMG2THREEJS_MATRIX=${JSON.stringify({passed:report.passed,combinations:report.combinations,passedCount:report.passedCount,failedCount:report.failedCount,report:path.join(reportDir,"browser_matrix.json")})}`);
  if(!report.passed)process.exitCode=1;
}

await main();
