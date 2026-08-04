# 2026-08-04：8093 底部空白排查与 8094 修复

## 用户问题

现场截图显示三维高炉面板底部出现一条空白带。排查范围为 8093 页面只读检查，并将修复更新到 8094；不修改 8093 守卫服务或 8768 实时服务。

## 结论

直接原因是页面末尾的 `ops-cad-ghost-bands-fix` 覆盖样式把 `.cad-furnace-viewer` 的底部 inset 固定为 `5%`，紧凑视口进一步为 `6%`。这会让 3D 画布和承载它的 `.furnace-stage-3d` 底部不重合，形成截图中的空白带；不是 GLB 炉底缺面。8093 只做了只读对照，未写入。

另有历史相机 fit margin 会影响模型整体显得偏小，但不改变本轮“画布底部留空”的直接 CSS 根因。

## 实现

- 故障 ID：`BUG-BF3D-CAD-BOTTOM-BAND-20260804`。
- 补丁器：[patch_8094_cad_bottom_band.py](../../tools/patch_8094_cad_bottom_band.py)。
- 远端部署器：[remote_deploy_8094_cad_bottom_band.ps1](../../tools/remote_deploy_8094_cad_bottom_band.ps1)。
- 合同测试：[test_8094_cad_bottom_band_fix.py](../../tests/test_8094_cad_bottom_band_fix.py)。
- 补丁只向独立 8094 HTML 追加高优先级、幂等、可重复应用的最终样式：`bottom: 0`；左右 24% 和原有顶部留白保持不变。

## 线上结果

2026-08-04 已在 `10.30.220.12:8094` 完成备份后更新：

- 备份目录：`F:\高炉炼铁项目-real-sensor-v2_V4_8093_PREVIEW\backups\8094_cad_bottom_band_20260804_124719`。
- 8094 HTTP `200`，页面包含 `BUG-BF3D-CAD-BOTTOM-BAND-20260804`。
- 8094 页面 SHA-256：`25714139F80ECCF8E5ED5C112986A305BB979AB56F73CE4A4981EDE1E9A54467`。
- `V3AutoPreviewProxy8094=Running`；8093、8094、8768、8770 监听进程均保持不变。
- 8093 更新前后返回内容一致，未触碰 `BFV4PreviewProxy8093` 守卫。

## 浏览器复核

Chrome 现场页读取到补丁标记和运行时样式；在 `1552×816` 视口，`.furnace-stage-3d` 底部为 `700px`，`.cad-furnace-viewer` 底部为 `699px`，底部差值约 `1px`（边框/取整误差），页面横向滚动宽度等于内容宽度。页面当时处于实时数据等待态，因此不把本次记录表述为完整跨浏览器矩阵完成；完整矩阵仍按项目验收基线补跑。
