# 程序索引

## 本机异常炉况诊断复核原型

- `高炉前端数据/智能助手/backend/diagnosis_review.py`：回环库配置边界、签名会话、异常段、服务端快照校验、追加事件存储。
- `高炉前端数据/assets/bf-diagnosis-review-local.js/.css`：按开关注入的居中异常弹窗、七类候选分数和三态复核。
- `高炉前端数据/diagnosis_review_local_test.html`：仅回环可用的五类测试场景。
- `tools/start_diagnosis_review_preview.py`：8096/8769本机启动器；不操作220.12服务。
- `tools/verify_diagnosis_review_local.py`：五页面、三浏览器引擎、规定视口矩阵。

## 高炉前端数据/assets/bf3d-furnace-summary-readability-8093.css

- 需求：`REQ-BF3D-8093-FURNACE-SUMMARY-READABILITY-20260802`。
- 职责：只扩大 8093 总览的 7 张 `.follow-model` 工艺汇总浮层，完整显示字段名、数值和单位。
- 边界：不得选择 `.furnace-billboard` 或 `.core-group-row`；121 个物理点 Billboard、左侧 28 变量和 8094 不受影响。
- 页面入口：[frontend_dashboard_v3.server.html](../高炉前端数据/frontend_dashboard_v3.server.html)中的缓存破坏版本 `20260802-expanded7-r2`；`.layered-cad-stage` 前缀保证专用覆盖权重高于运行时追加的旧样式。
- 测试：[test_8093_furnace_summary_readability.py](../tests/test_8093_furnace_summary_readability.py)。

## tools/remote_deploy_8093_furnace_summary_readability.py

- 职责：备份并原子写入 8093 页面和专用 CSS，幂等维护 link，验证 CSS 合同，同时保护 8094 页面、共享 adapter 与 8094 相机哈希。
- 运行：由 [remote_guarded_deploy_8093_furnace_summary_readability.ps1](../tools/remote_guarded_deploy_8093_furnace_summary_readability.ps1)在 8093 守卫停—改—启窗口内调用。

## 高炉前端数据/assets/bf3d-tooltip-stable-hover-8093.js（Billboard 醒目度）

- 需求：`REQ-BF3D-8093-BILLBOARD-EMPHASIS-20260802`。
- 入口：`installBillboardEmphasis(viewer, host)`。
- 配置：`BILLBOARD_SCALE_MULTIPLIER=1.22`；只作用于 8093 可见 Sprite，并包装 `scale.set()` 保持实时刷新后的比例。
- 测试：[test_8093_stable_tooltip_hover.py](../tests/test_8093_stable_tooltip_hover.py)。
- 风险：比例继续增大会加剧密集层标签重叠；如需调整，优先在 `1.15–1.30` 范围内做真实视口复验，不得改共享 adapter。

## 高炉前端数据/assets/bf3d-tooltip-stable-hover-8093.js

8093 专用的 Billboard 单写入者悬停控制器。统一 tooltip 坐标空间，使用屏幕空间迟滞和驻留切换，随相机投影更新位置，并在相机拖拽时隐藏；不实现点位聚焦。

## tools/remote_deploy_8093_stable_tooltip_hover.py

8093 悬停修复的原子部署器。备份 8093 页面和既有专用资源，注入旧写入器退出标志与 viewer buffer getter，部署新资源，同时保护 8094 页面、共享 adapter 和 8094 相机哈希。

## tests/test_8093_stable_tooltip_hover.py

覆盖单写入者、统一坐标、迟滞参数、无位置定时器、幂等页面补丁以及 8094/共享资源隔离保护。

## 高炉前端数据/assets/bf3d-physical-point-filter-8093.js

### 文件职责

8093 独立的三维点位后置筛选器。它在共享 133 点 adapter 建好场景后，原地保留 121 个实际炉体/设备测点，移除 12 个抽象或汇总 Billboard，不影响左侧 28 变量面板。

### 被以下需求使用

- [REQ-BF3D-8093-MEASURED-121-OVERVIEW-20260801](./requirements_traceability.md#req-bf3d-8093-measured-121-overview-20260801)

## 高炉前端数据/assets/bf3d-surface-camera-guard-8093.js

### 文件职责

8093 全景相机与防穿透运行时。始终围绕炉心旋转，以模型整体包围半径限制最小距离，关闭 Billboard 点位聚焦。

### 被以下需求使用

- [REQ-BF3D-8093-MEASURED-121-OVERVIEW-20260801](./requirements_traceability.md#req-bf3d-8093-measured-121-overview-20260801)

## tools/remote_deploy_8093_physical_points_overview.py

### 文件职责

在 220.12 上发现 8093 V4 前端目录，备份并原子替换 8093 页面和两个独立运行时，同时验证 8094 页面、共享 adapter 与 8094 相机文件哈希未变化。

### 修改风险

脚本目标是远端 8093 正式页面。任何版本标记、相对路径或受保护文件清单变化，都必须先执行隔离根目录回归测试，再做远端部署。

## tools/remote_deploy_8093_initial_camera_framing.py

### 文件职责

只更新 8093 相机运行时和页面相机缓存版本；备份变更前文件，并以 SHA-256 保护 8093 模型、其他 8093 专用运行时、8094 页面和共享资源。

## tools/remote_guarded_deploy_8093_initial_camera_framing.ps1

### 文件职责

在远端暂停 `BFV4PreviewProxy8093` 守卫、调用相机原子部署器并恢复守卫；整个窗口要求 8768 持续运行，恢复后核查 8093 HTTP、相机 schema、适配系数和文件哈希。

## tools/audit_8093_remote_local_parity.py

### 文件职责

并行读取 8093 HTTP 页面、5 个运行时资产和 GLB，分别与本机源码、Web 同名 alias 和资产库受控 master 做 SHA-256 对账，避免把整页注入差异或历史同名模型误判为守卫覆盖。
