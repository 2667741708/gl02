# 需求追踪

## REQ-8093-DIAGNOSIS-REVIEW-LOCAL-PROTOTYPE-20260803

- 需求：在隔离的本机8096/8769原型中，对非“正常顺行”的主诊断居中告警，并允许高组长查看规则符合度、其余七类分数并进行三态人工复核。
- 实现：[后端边界](../高炉前端数据/智能助手/backend/diagnosis_review.py)、[独立交互模块](../高炉前端数据/assets/bf-diagnosis-review-local.js)、[样式](../高炉前端数据/assets/bf-diagnosis-review-local.css)、[测试场景](../高炉前端数据/diagnosis_review_local_test.html)、[启动器](../tools/start_diagnosis_review_preview.py)。
- 数据边界：220.12只读；复核事件只写显式指定的回环PostgreSQL；现有主HTML不硬编码原型资源。
- 验证：[专项测试](../tests/test_diagnosis_review_api.py)、[契约测试](../tests/test_diagnosis_review_contract.py)、[浏览器矩阵](../tools/verify_diagnosis_review_local.py)。
- 状态：本地代码及14项模块/契约测试通过，Chromium本机交互冒烟通过；真实本机库与完整跨浏览器矩阵待配置本机凭据/浏览器依赖后执行。详见[专项说明](8093_异常炉况诊断人工复核本地原型_20260804.md)。

## REQ-BF3D-8093-FURNACE-SUMMARY-READABILITY-20260802

- 需求：将 8093 总览围绕高炉的 7 张外围工艺汇总浮层进一步放大，完整显示字段名、实时值和单位；121 个炉体物理点 Billboard、左侧 28 变量面板、相机和 8094 不得改变。
- 实现：[8093 七类汇总浮层样式](../高炉前端数据/assets/bf3d-furnace-summary-readability-8093.css)只作用于 `.furnace-layer-callouts.follow-model`：桌面宽度 `208–242px`，紧凑桌面 `198px`，低高度边界 `190px`；字段列使用 `max-content`，取消 `ellipsis`，所有断点均保留单位。
- 部署：[原子部署器](../tools/remote_deploy_8093_furnace_summary_readability.py)与[守卫停—改—启脚本](../tools/remote_guarded_deploy_8093_furnace_summary_readability.ps1)只允许修改 8093 HTML 和新增的 8093 专用 CSS，部署前后保护 8094 页面、共享 Billboard adapter 和 8094 相机资源哈希。
- 验证：[专项合同测试](../tests/test_8093_furnace_summary_readability.py)与既有稳定悬停测试联跑 `11 passed`；远端页面和 CSS 均返回 HTTP 200，页面版本为 `20260802-expanded7-r2`，8093/8768 TCP 均监听。
- 状态：已部署到 `http://10.30.220.12:8093/#overview`；守卫暂停/恢复、8768 不变、8093/8768 监听、HTTP 200 全部通过。最终页面 SHA-256 `F308993A...24FC1`，CSS SHA-256 `BDA77396...EE48`，回滚备份 `backups/8093_furnace_summary_readability_20260802/20260802_210417`。Chrome 现有重载因 8093 重资源页面等待超时，最终 DOM 尺寸/截图验收仍需在页面刷新稳定后补录，不据此宣称完整跨浏览器矩阵通过。

## REQ-BF3D-8093-BILLBOARD-EMPHASIS-20260802

- 需求：适度扩大 8093 炉体点位 Billboard，使中文语义、实时值、状态圆点和边框更醒目；不得改变 121 点数量、左侧 28 变量、相机和无点位聚焦口径。
- 实现：[8093 稳定悬停/醒目度运行时](../高炉前端数据/assets/bf3d-tooltip-stable-hover-8093.js)使用 `BILLBOARD_SCALE_MULTIPLIER=1.22` 包装每个可见 Sprite 的 `scale.set()`，所以实时刷新后仍维持比例。
- 隔离：不修改共享 [Billboard adapter](../高炉前端数据/assets/bf3d-furnace-body-billboard-adapter.js)，8094 尺寸不变。
- 验证：6 项合同测试通过；220.12 8093 页面实测 `billboardCount=121`、`emphasisScale=1.22`、`emphasisMode=moderate-8093`、资源版本 `r2-emphasis122`。
- 状态：已通过 `BFV4PreviewProxy8093` 守卫停—改—启流程部署，8093/8768 均运行并监听。

## BUG-BF3D-8093-TOOLTIP-JITTER-SINGLE-OWNER-20260802

- 需求：消除 8093 密集 Billboard 附近的 tooltip 颤动，不改变 121 点、左侧 28 变量、全炉旋转和无点位聚焦口径。
- 实现：[稳定悬停控制器](../高炉前端数据/assets/bf3d-tooltip-stable-hover-8093.js)、[隔离部署器](../tools/remote_deploy_8093_stable_tooltip_hover.py)。
- 算法：单写入者、视口固定坐标、30/46px 进入退出迟滞、12px 切换优势量、140ms 候选驻留、点位锚定、相机拖拽隐藏。
- 验证：[5 项合同测试](../tests/test_8093_stable_tooltip_hover.py)、[独立 Chrome 悬停验收器](../tools/verify_8093_stable_tooltip_hover.py)及[专项说明](./8093_Billboard悬停抖动修复_20260802.md)。
- 状态：2026-08-02 已通过 `BFV4PreviewProxy8093` 守卫停—改—启闭环部署；8093/8768 监听与 HTTP 200 通过，8094/共享文件哈希保持不变。

## REQ-BF3D-8093-MEASURED-121-OVERVIEW-20260801

### 需求

- 8093 左侧 28 核心变量面板不得移动或删改。
- 高炉三维场景显示 121 个实际炉体或设备测点。
- 12 个计算、设定、汇总或兼容点只留在变量面板，不显示在炉壳。
- 去除 Billboard 点位聚焦，保留炉心全景 360° 旋转和整体包围半径防穿透。
- 修改只部署到 8093，8094 必须保持不变。

### 实现与验收

| 对象 | 位置 | 合同 |
|---|---|---|
| 121 点筛选 | [bf3d-physical-point-filter-8093.js](../高炉前端数据/assets/bf3d-physical-point-filter-8093.js) | `80 + 18 + 2 + 21 = 121`，排除 12 点 |
| 全景相机 | [bf3d-surface-camera-guard-8093.js](../高炉前端数据/assets/bf3d-surface-camera-guard-8093.js) | `pointFocusEnabled=false`、炉心 target、无限方位角 |
| 远端部署 | [remote_deploy_8093_physical_points_overview.py](../tools/remote_deploy_8093_physical_points_overview.py) | 原子写入、备份、保护 8094/共享资源哈希 |
| 回归测试 | [test_8093_physical_points_overview.py](../tests/test_8093_physical_points_overview.py) | 121/12 精确数量、脚本顺序、无聚焦、8094 隔离 |

### 状态

已于 2026-08-01 部署到 `10.30.220.12:8093`。静态资源与隔离契约通过；完整跨浏览器视觉矩阵待在允许单次页面加载超过 5 秒时补跑。

## REQ-BF3D-8093-INITIAL-FRAME-CLOSER-20260802

- 需求：修正 8093 初始全景中炉体偏小、底部留白看似“没有到底”的构图，同时确认远端代码和受控 GLB 没有被守卫覆盖。
- 实现：[8093 相机运行时](../高炉前端数据/assets/bf3d-surface-camera-guard-8093.js)升级为 `bf3d.camera.overview-only.8093.v4`；去掉旧 8% 包围球额外适配余量，初始和“全景”复位约放大 8%。
- 安全边界：`controls.minDistance=fullOrbitRadius`、`camera.near=0.05m`、炉心 target 和无限方位角不变；没有修改 GLB。
- 部署：[守卫停—改—启入口](../tools/remote_guarded_deploy_8093_initial_camera_framing.ps1)和[相机原子部署器](../tools/remote_deploy_8093_initial_camera_framing.py)只更新 8093 页面缓存标记与 8093 相机资产，并保护模型、8094 及其他 8093 运行时哈希。
- 验证：本地 7 项合同测试通过；远端守卫暂停/恢复、8768 不变、HTTP 200；恢复守卫后相机 SHA-256 与本机一致。完整审计见[专项记录](8093_初始构图与远端本机一致性审计_20260802.md)。

## BUG-BF3D-CAD-BOTTOM-BAND-20260804

- 需求：排除 8093 页面底部空白带的直接原因，并把最小修复更新到 8094；8093 守卫、8768 实时服务和 8094 运行时不得被重启或越界修改。
- 根因：`ops-cad-ghost-bands-fix` 的 `bottom:5%/6%` 覆盖规则使 3D 画布底部低于承载 stage，形成可见空白；不是 GLB 缺面。
- 实现：[8094 补丁器](../tools/patch_8094_cad_bottom_band.py)、[8094-only 部署器](../tools/remote_deploy_8094_cad_bottom_band.ps1)、[合同测试](../tests/test_8094_cad_bottom_band_fix.py)。
- 验证：本地 `3 tests / OK`；远端 8094 HTTP 200、页面标记存在、8094 任务 Running，8093/8094/8768/8770 PID 均未变化；Chrome 现场页 stage/viewer 底部差值约 1px。
- 记录：[专项交接说明](handoffs/2026-08-04-8094-cad-bottom-band-fix.md)。
