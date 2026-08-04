# 总览页响应式布局口径

## OPS-8093-RESPONSIVE-OVERVIEW

目标页面：`http://10.30.220.12:8093/?t=<cache-bust>#overview`

实现文件：

- 本地：`高炉前端数据/frontend_dashboard_v3.server.html`
- 8093：`F:\高炉炼铁项目-real-sensor-v2_V4_8093_PREVIEW\高炉前端数据\frontend_dashboard_v3.server.html`

## BUG-8093-OVERVIEW-ADAPTIVE-CLIP-20260716

用户在不同显示器尺寸下看到首页文字和核心变量被截断。根因是总览三栏的后置样式重新写入固定最小栏宽，覆盖了旧窄屏规则；同时核心变量行的固定列宽大于左栏实际宽度，`1280×720` 又未命中原有短屏压缩断点。

当前修复位于 [最终响应式覆盖](../高炉前端数据/frontend_dashboard_v3.server.html#L10656)：

- `>=1280px` 保持桌面三栏，改用 `27fr / 45fr / 28fr` 可收缩轨道；左、右栏保留 `320px` 安全下限，中栏允许真实收缩。
- `<1280px` 切换为单列纵向工作流，核心变量、炉体、诊断建议和趋势都可通过主内容区滚动到达，不再把三栏藏在横向裁切区中。
- 核心变量行使用弹性名称、数值与曲线列；面板宽度不足 `430px` 时隐藏次要状态列，保留序号、完整变量名、数值和可点击迷你趋势。
- `1280×720` 等低高度桌面统一压缩正式头部和底部导航；手机端两张历史基线图改为单列，避免图题和图表被裁切。
- 修复只涉及前端布局与只读交互，不改变 8767/8768 WebSocket、数据库、诊断、建议或 Chronos 数据契约。

专项验证入口为 [verify_overview_adaptive_layout.py](../tools/verify_overview_adaptive_layout.py)。2026-07-16 本地静态边界验收结果：Chromium 9 个固定视口 × 5 路由 `45/45` 通过；Firefox 与 WebKit 各 4 个代表视口 × 5 路由，加 Edge `1366×768` × 5 路由，合计 `45/45` 通过。报告与截图见 [Chromium manifest](../logs/overview_adaptive_qa_20260716/manifest.json) 和 [跨引擎 manifest](../logs/overview_adaptive_qa_20260716_cross_engine/manifest.json)。本次未部署 220.12，远端发布后仍须用真实 8768 数据再做现场 Edge 冒烟。

## 固定屏幕尺寸

现场和办公电脑常见尺寸按以下几档优先验收：

- 桌面：`1280×720`、`1366×768`、`1440×900`、`1546×864`、`1920×1080`。
- 平板：`1024×768`、`768×1024`。
- 手机：`390×844`、`375×667`。
- 以上均为浏览器内容区 CSS viewport，不以浏览器缩放代替真实视口。

## 布局规则

- 总览页左侧核心指标允许按 7 类分组、2 页切换展示；若旧 28 行紧凑列表因缓存或旧服务出现，也必须保证名称、数值、状态和迷你曲线不重叠。
- 核心指标迷你曲线是详情入口：点击后必须在可关闭的弹层中提供趋势缩放、时间点精确值和分析窗口选择；变量相关性必须使用同一分钟有效样本计算并标明“相关不等于因果”，不能以视觉相似替代计算结果。
- 总览页中间炉体允许叠加七个工艺分层实时标注卡片，分层必须与核心 28 变量分类一致：煤气顶压、热制度、送风供氧、压差透气、料线、喷煤、出铁口温度。
- 左侧核心指标在 1366 宽度下优先保证名称、数值、状态、小趋势线四类信息；单位和偏离列可隐藏，小趋势线宽度不得小于约 `70px`。
- `max-width:1366px` 或 `max-height:760px` 时，左侧指标隐藏单位和偏离列，保留序号、名称、数值、状态和迷你曲线。
- `<1280px` 时总览切为单列并在主内容区纵向滚动；不得用横向裁切或隐藏后两栏来维持桌面三栏。
- `max-height:680px` 时进一步压缩行高、字体和迷你曲线高度，优先保证不遮挡。

## 验收

建议验证：

```powershell
curl.exe --max-time 45 -s -H 'Cache-Control: no-cache' "http://10.30.220.12:8093/?t=20260709-responsive#overview" | Select-String "OPS-8093-RESPONSIVE-OVERVIEW|core-grouped-metrics|compact-core-metrics"
powershell -NoProfile -ExecutionPolicy Bypass -File "F:\高炉炼铁项目-real-sensor-v2_V4_8093_PREVIEW\tools\verify_8093_v4_file_enabled.ps1"
```

`Select-String` 只能确认关键字存在；最终验收必须以 `verify_8093_v4_file_enabled.ps1` 的 `EffectiveCoreGroups=true` 为准。若 `LastCompactMetricRowsIndex` 大于 `LastGroupedMetricRowsIndex`，说明旧 28 行紧凑核心指标在后续脚本中覆盖了 7 类分组版。

浏览器验收：

- `1920x1080`：三栏总览完整显示。
- `1366x768`：左侧核心指标名称、数值、状态、迷你曲线不互相覆盖。
- 窄窗口：页面单列纵向滚动，无页面横向溢出，三块业务区域均可到达。

## 2026-07-09 远端 Playwright 验收

目标 URL：

- `http://10.30.220.12:8093/?t=playwright-coregroups-safe-20260709-1212#overview`
- `http://10.30.220.12:8093/?t=playwright-coregroups-1366-20260709-1213#overview`

验收结果：

- `1920x1080`：`.core-grouped-metrics=1`，`.compact-core-metrics=0`，第一页 21 行，控制台错误 0，页面错误 0，横向溢出 0。
- `1366x768`：第一页显示“煤气顶压 / 热制度 / 送风供氧 / 压差透气”，21 行，横向溢出 0。
- `1366x768`：点击第二个页签后显示“料线 / 喷煤 / 出铁口温度”，7 行，横向溢出 0。
- 截图保存于 `logs/8093_coregroups_playwright/overview_1920x1080_coregroups_safe.png`、`logs/8093_coregroups_playwright/overview_1366x768_coregroups_page1.png`、`logs/8093_coregroups_playwright/overview_1366x768_coregroups_page2.png`。

## 2026-07-09 小趋势线调优验收

目标 URL：

- `http://10.30.220.12:8093/?t=playwright-spark-30min-v2-20260709-1231#overview`

验收结果：

- 小趋势窗口：`CORE_SPARK_MINUTES=30`
- 小趋势线宽：`CORE_SPARK_LINE_WIDTH=1.45`
- 第一条小趋势实际 ECharts 数据点：`30`
- 第一条小趋势实际 ECharts 线宽：`1.45`
- `1366x768` 下第一条小趋势 DOM 宽度：`52px`
- `.core-grouped-metrics=1`，`.compact-core-metrics=0`
- 控制台错误 0，页面错误 0，横向溢出 0
- 截图保存于 `logs/8093_coregroups_playwright/overview_1366x768_spark_30min_thin_v2.png`

## 2026-07-09 炉体七工艺分层验收

目标 URL：

- `http://10.30.220.12:8093/?t=playwright-layer-callouts-final-20260709-1244#overview`

实现文件：

- 本地页面：[高炉前端数据/frontend_dashboard_v3.server.html](../高炉前端数据/frontend_dashboard_v3.server.html)
- 远端补丁：[tools/patch_22012_8093_core_metric_groups.py](../tools/patch_22012_8093_core_metric_groups.py)

验收结果：

- `1920x1080`：`.furnace-layer-card=7`，行数为 `5 / 4 / 2 / 3 / 7 / 5 / 2`，CAD 模型 `loaded`，传感器节点 `115`，映射节点 `115`，控制台错误 0，页面错误 0，标注溢出 0，面板溢出 0。
- `1366x768`：`.furnace-layer-card=7`，行数为 `5 / 4 / 2 / 3 / 7 / 5 / 2`，CAD 模型 `loaded`，传感器节点 `115`，映射节点 `115`，控制台错误 0，页面错误 0，标注溢出 0，面板溢出 0。
- 炉体画布收在中轴区域：`1920x1080` 下画布宽度约为炉体面板宽度 `44%`，`1366x768` 下约为 `46%`。
- `.core-grouped-metrics=1`，`.compact-core-metrics=0`，左侧核心指标仍保持七类分组。
- 截图保存于 `logs/8093_coregroups_playwright/overview_1920x1080_furnace_layer_callouts_final.png`、`logs/8093_coregroups_playwright/overview_1366x768_furnace_layer_callouts_final.png`。

## 2026-07-09 密度与小趋势 V3 验收

目标 URL：

- `http://10.30.220.12:8093/?t=playwright-density-spark-v3-20260709-1253#overview`

实现文件：

- 本地页面：[高炉前端数据/frontend_dashboard_v3.server.html](../高炉前端数据/frontend_dashboard_v3.server.html)
- 远端补丁：[tools/patch_22012_8093_core_metric_groups.py](../tools/patch_22012_8093_core_metric_groups.py)

验收结果：

- `OPS-8093-CORE-DENSITY-SPARK-V3` 已进入文件和 HTTP 响应。
- `1366x768`：左侧面板宽度约 `364.5px`，第一条核心指标行高 `18px`，小趋势槽位 `72x14px`，小趋势数据点 `30`，线宽 `1.55`，`smooth=false`，控制台错误 0，页面错误 0，面板溢出 0，横向溢出 0。
- `1920x1080`：第一条核心指标行高 `19px`，小趋势槽位 `86x15px`，小趋势数据点 `30`，线宽 `1.55`，控制台错误 0，页面错误 0，面板溢出 0，横向溢出 0。
- 炉体画布收在中轴区域：`1920x1080` 和 `1366x768` 下画布宽度均约为炉体面板宽度 `50%`。
- 截图保存于 `logs/8093_coregroups_playwright/overview_1366x768_density_spark_v3.png`、`logs/8093_coregroups_playwright/overview_1920x1080_density_spark_v3.png`。

## 2026-07-09 CAD 炉体灰色竖块修复

用户指出 8093 总览页 CAD 高炉本体被两侧灰色区域遮住。本次定位到原因是后续炉体点位跟随样式把 `.cad-furnace-viewer` 再次压缩到约 `30%~32%` 宽，并叠加旧半透明背景。修复标记为 `OPS-8093-CAD-GHOST-BANDS-FIX`。

实现与验证：

- 本地页面：[高炉前端数据/frontend_dashboard_v3.server.html:L1715-L1722](../高炉前端数据/frontend_dashboard_v3.server.html#L1715-L1722)
- 远端补丁：[tools/patch_22012_8093_core_metric_groups.py:L356-L363](../tools/patch_22012_8093_core_metric_groups.py#L356-L363)
- 样式结果：`viewerBackgroundColor=rgba(0, 0, 0, 0)`，`viewerBackgroundImage=none`，`rendererClearAlpha=0`，`viewerWidthRatio=0.518`，`horizontalOverflow=false`。
- 本地截图：[overview_1366x768_cad_ghost_bands_fix_local_static_8093.png](../logs/8093_coregroups_playwright/overview_1366x768_cad_ghost_bands_fix_local_static_8093.png)
- 远端状态：2026-07-09 16:10 已部署到 `10.30.220.12:8093`，`BFV4PreviewProxy8093=Running`，8768 保持监听。
- 远端 Playwright：`viewerBackgroundColor=rgba(0, 0, 0, 0)`，`viewerBackgroundImage=none`，`canvasBackgroundColor=rgba(0, 0, 0, 0)`，`rendererClearAlpha=0`，`viewerWidthRatio=0.518`，`sensorCount=115`，`cardCount=7`，`lineCount=8`，`pinCount=8`，`horizontalOverflow=false`。
- 远端截图：[overview_1366x768_cad_ghost_bands_fix_remote_8093.png](../logs/8093_coregroups_playwright/overview_1366x768_cad_ghost_bands_fix_remote_8093.png)
