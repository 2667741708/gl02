# 工长趋势独立预览页交接记录（2026-08-05）

## 目标

在不删除、不替换当前正式趋势页的前提下，新增一张可直接对比现场照片布局的“工长趋势1”独立页面。

## 入口

- 固定布局对比：`http://127.0.0.1:8092/foreman_trend_preview.html?fixture=1`
- 现有实时流：`http://127.0.0.1:8092/foreman_trend_preview.html?ws_port=8767`
- 原正式趋势页：`http://127.0.0.1:8092/frontend_dashboard_v3.server.html?ws_port=8767#trend`

## 复刻内容

- 黑色顶部标题栏与系统时间；
- 7×7 蓝色指标矩阵，共 49 个现场变量；
- 灰色 HMI 趋势工具栏；
- 上方 12 通道长时间趋势；
- 下方 5 通道阶梯/脉冲周期趋势；
- 图例、缩放、平移、复位、最新窗口和导出动作；
- 底部旧式导航，并保留到正式 `#trend` 页的真实入口。

## 数据和安全边界

`fixture=1` 的数据只用于布局校验，页面明确显示“布局校验数据 · 非生产”；去掉 fixture 后才连接 WebSocket。实时数据缺失显示 `--`，不使用伪造的生产值。本次未新增数据库表、API、服务，也未修改正式趋势页。

## 验收证据

- `python -m unittest tests.test_foreman_trend_preview -v`：`4 tests / OK`；
- `node tools/verify_foreman_trend_preview.cjs`：Edge/Chromium `1280×1024` 通过，页面/控制台错误 0；
- `node tools/verify_foreman_trend_viewports.cjs`：Edge/Chromium 9 项、Firefox 4 项、WebKit 4 项，共 `17 checks / PASS`；
- 截图：[foreman_trend_1280x1024.png](../../logs/foreman_trend_preview_20260805/foreman_trend_1280x1024.png)；
- 报告：[report.json](../../logs/foreman_trend_preview_20260805/report.json) 和 [viewport_matrix/report.json](../../logs/foreman_trend_preview_20260805/viewport_matrix/report.json)。

## 后续边界

页面仅用于当前对比。若要接入生产导航或替换正式趋势页，必须另行完成真实变量逐项核对、权限/数据状态验收、现场签字和受控部署；不能由 fixture 截图直接推断生产可用。

## 220.12 受控发布（2026-08-05 14:30）

- 发布入口：`http://10.30.220.12:8093/foreman_trend_preview.html?ws_port=8768`；页面经 8093 静态服务连接既有 8768 PostgreSQL 分钟流，不接入 8770 pSpace 秒级流。
- 操作：使用 [remote_deploy_8093_foreman_trend_preview.ps1](../../tools/remote_deploy_8093_foreman_trend_preview.ps1) 原子替换独立 HTML、CSS、JS；备份为 `F:\高炉炼铁项目-real-sensor-v2_V4_8093_PREVIEW\backups\8093_foreman_trend_preview_20260805\20260805_142959`。
- 隔离：8093 PID 仍为 `6892`，8768 PID 仍为 `15824`；两个服务均为 Running。未重启服务、未写数据库、未改正式趋势页。
- 远端浏览器验收：`1280×1024` 下数据时间 `2026-08-05 14:30:00`，29 项真实值、20 项真实缺失、主趋势 `12/12`、下方趋势 `5/5`、横向溢出为 0、页面/控制台错误为 0。证据：[报告](../../logs/foreman_trend_preview_20260805/remote_8093_live_report.json)、[截图](../../logs/foreman_trend_preview_20260805/foreman_trend_remote_8093_1280x1024.png)。
