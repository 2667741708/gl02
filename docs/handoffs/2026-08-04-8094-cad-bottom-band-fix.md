# 2026-08-04：8093/8094 三维画布底部空白 R2 修复

## 用户问题

现场截图显示三维高炉白色画布下方仍有一大块深蓝空带。用户后续授权重启 8094，并将同一修复通过守卫闭环更新到 8093，要求截图直到真实画布底边视觉验收成功。

## 结论

根因有两层：页面末尾 `ops-cad-ghost-bands-fix` 把 `.cad-furnace-viewer` 的底部 inset 固定为 `5%/6%`；旧规则 `.overview-grid>.panel:last-of-type .panel-body` 又在当前三列布局中误命中炉况总览面板，给正文增加 `46px` 底部 padding（`max-width:1500px` 时为 `66px`）。用户截图中的大块深蓝空带主要来自第二层，不是 GLB 炉底缺面。

另有历史相机 fit margin 会影响模型整体显得偏小，但不改变本轮“画布底部留空”的直接 CSS 根因。

## 实现

- 故障 ID：`BUG-BF3D-CAD-BOTTOM-BAND-20260804`；最终修订标记：`BUG-BF3D-CAD-PANEL-BODY-GAP-20260804-R2`。
- 共用补丁器：[patch_8094_cad_bottom_band.py](../../tools/patch_8094_cad_bottom_band.py)，通过 `--scope 8093|8094` 选择目标页。
- 8094 初次热部署器：[remote_deploy_8094_cad_bottom_band.ps1](../../tools/remote_deploy_8094_cad_bottom_band.ps1)；8094 进程重启入口：[restart_22012_8094_preview.ps1](../../tools/restart_22012_8094_preview.ps1)。
- 8093 守卫部署器：[remote_guarded_deploy_8093_cad_bottom_band.ps1](../../tools/remote_guarded_deploy_8093_cad_bottom_band.ps1)。
- 合同测试：[test_8094_cad_bottom_band_fix.py](../../tests/test_8094_cad_bottom_band_fix.py)和[test_8093_cad_bottom_band_fix.py](../../tests/test_8093_cad_bottom_band_fix.py)。
- 补丁以高优先级、幂等方式同时设置 viewer `bottom:0` 与当前炉况总览面板直属 `.panel-body { padding-bottom:0 }`；左右 24% 和原有顶部构图保持不变。补丁器会把旧的仅 stage/viewer 修复自动升级为 R2。

## 线上结果

2026-08-04 已在 `10.30.220.12` 完成 8094 重启和 8093 守卫部署：

- 8094 初次备份为 `backups\8094_cad_bottom_band_20260804_124719`，R2 备份为 `backups\8094_cad_bottom_band_20260804_153734`。
- 8094 HTTP `200`，页面同时包含基础标记和 `BUG-BF3D-CAD-PANEL-BODY-GAP-20260804-R2`；R2 页面 SHA-256：`A13AB868BA7D71FC04450D05BD88D23506DB6BB7103C1165D5CCFD2021D193C7`。
- 8094 于 `13:57:16` 完成真实进程替换，监听 PID `2688 -> 9976`；清理的孤儿 PID 为 `13924`。8093/8768/8770 PID 分别保持 `13788/10868/12956`，8094 HTTP `200`，计划任务保持 `Running`。
- 8093 使用守卫停—改—启闭环部署，R2 备份目录为 `F:\高炉炼铁项目-real-sensor-v2_V4_8093_PREVIEW\backups\8093_cad_bottom_band_20260804\20260804_160815`；`guard_paused=true`、`guard_restored=true`、8093 HTTP `200`。
- 8093 R2 页面 SHA-256 为 `0AB75FF725FC889062C051ED1A6775C25E796F474151DACD95E791044896A3F4`。闭环确认 8094/8768/8770 PID 未变化，8094 页面、共享 adapter 和 8094 相机 SHA-256 均未变化。

## 浏览器复核

首次验收错误地只量了 `.furnace-stage-3d` 与 `.cad-furnace-viewer`，两者相差 `0.606px`，却没有量实际 canvas 到 panel-body 的边界，因此漏掉 `46px` padding 并产生了误判；旧报告已明确作废。

R2 使用 cache-bust 参数分别加载 8093、8094。在两页 `1552×816` CSS viewport 中，Three.js canvas 到炉况总览直属 panel-body 的底差均为 `0.606px`，canvas 到外层 panel 的差值为 `1.212px`（边框），`padding-bottom=0px`，横向溢出为 0；8093 控制台错误列表为 0。白色画布在截图中直达面板底部，专项视觉验收通过。

- 8093 R2 截图：[8093_overview_panel_flush_r2_1552x816_20260804.png](../../logs/acceptance/8093_8094_cad_bottom_band_20260804_r2/8093_overview_panel_flush_r2_1552x816_20260804.png)。
- 8094 R2 截图：[8094_overview_panel_flush_r2_1552x816_20260804.png](../../logs/acceptance/8093_8094_cad_bottom_band_20260804_r2/8094_overview_panel_flush_r2_1552x816_20260804.png)。
- 完整边界数据见 [R2 验收记录](../../logs/acceptance/8093_8094_cad_bottom_band_20260804_r2/acceptance.md)。本结论只覆盖三维画布底部空白专项和该桌面视口，不替代 Firefox、WebKit、现场 Edge 或全路由矩阵。
- 重启过程中发现的计划任务孤儿进程、冷启动 HTTP 重试和服务状态枚举问题见[错误追踪](../error_traceability.md)。
