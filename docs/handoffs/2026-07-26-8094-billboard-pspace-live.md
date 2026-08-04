# 8094 Billboard 接入 pSpace 实时 133 点

需求：`REQ-BF3D-BILLBOARD-PSPACE-LIVE-20260726`

## 已上线架构

- 页面：`http://10.30.220.12:8094/#overview`，以及中文 Billboard 独立预览。
- 原 `BFV4PreviewWs8768` 保持 PostgreSQL 30 秒诊断/页面流，不替换、不重启。
- 新增独立计划任务 `\BlastFurnaceServices\V4BillboardPspace8770`，以 SYSTEM
  身份在 220.12 启动 `tools/run_billboard_pspace_8770.py`。
- `8770` 使用 pSpace PythonSDK `RealReadList` 直接读取
  `10.22.181.243:8889`，默认 1 秒轮询；不是 PostgreSQL 分钟值。
- 8094 页面主数据仍使用 `8768`，Billboard 适配器单独订阅 `8770`。
- 防火墙规则 `BF V4 Billboard pSpace 8770` 只允许 `10.0.0.0/8` 访问 TCP
  8770。
- 运行器从 220.12 V3 目录已有的站点只读样例中读取 pSpace 凭据，仅注入子进程
  环境；仓库、前端、报告和日志均不记录密码。

## 点位与协议合同

- 原 115 字段诊断合同与 Billboard 合同直接重合 108 点。
- 8770 发布 140 个兼容键，其中物理 Billboard `canonical_id` 精确为 133。
- 新增 4 个炉喉温度 `T_throat_A-D` 和 18 个 A～F 静压力
  `P_static_lower/middle/upper_A-F`。
- 三个高度静压力均值同时发布旧键 `P_static_*_mean` 与 Billboard 键
  `P_static_20m35/23m49/28m98`。
- 135 个唯一 pSpace 长名按 `100 + 35` 分批读取，再合并为同一 tick。
- `point_meta` 为 133 项，只向浏览器下发时间、质量和错误，不下发 pSpace 长名。
- 15 秒无新帧即显示“中断”；8094 只读回退页面已有缓冲，独立预览保留最后真实
  值，均不补 0、不插值、不生成模拟值。

## 背景可调

- 三维场景默认背景为护眼浅灰 `#eef2f1`。
- 可在页面右下角“背景”控件切换护眼浅灰、纯白、钢灰、深色或自定义颜色。
- 选择保存在浏览器本地存储；也可用 `background` 和 `background_color` 查询参数
  覆盖。
- 背景控制只修改 Three.js 场景清屏色，不改 pSpace、8768、数据库、诊断或模型。

## 程序入口

- [pSpace 桥](../../tools/pspace_8092_realtime_bridge.py)
- [8770 常驻运行器](../../tools/run_billboard_pspace_8770.py)
- [8094 Billboard 与背景适配器](../../高炉前端数据/assets/bf3d-furnace-body-billboard-adapter.js)
- [独立中文预览](../../PT/高炉3D模型/模型资产库/09_高炉本体133点Billboard_cn/preview/app.js)
- [8770 受控发布](../../tools/remote_deploy_8094_billboard_pspace_live.ps1)
- [背景前端热发布](../../tools/remote_deploy_8094_billboard_background.ps1)
- [外部 8770 验证](../../tools/verify_billboard_pspace_8770.py)

## 生产验收

2026-07-26 12:05:57 从本机经 VPN 直连 `ws://10.30.220.12:8770`：

- `replay_mode=pspace_realtime`
- `stream_value_count=140`
- `billboard_meta_count=133`
- `billboard_expected=133`
- `billboard_mapped=133`
- `billboard_missing_count=0`
- `numeric_billboard_values=133`
- `quality_metadata_count=133`
- 五个代表点均存在且为数值

Chrome 实际 8094 页面 DOM 已确认：

- “背景”控件存在，默认选中“护眼浅灰”；
- 纯白、钢灰、深色、自定义选项可达；
- 133 点 Billboard 页面合同存在；
- 正式品牌头部和生产数据页面正常。

自动测试：

- `python -m pytest tests\test_pspace_billboard_realtime_bridge.py -q`：`1 passed`；
- 两个浏览器模块 `node --check` 通过；
- 中文独立预览 Chromium `1440×900`、`390×844` 的模拟 pSpace 合同验证通过。

## 发布与回滚

- 8770 成功发布备份：
  `F:\高炉炼铁项目-real-sensor-v2_V4_8093_PREVIEW\backups\8094_billboard_pspace_live_20260726_083914`
- 背景前端发布备份：
  `F:\高炉炼铁项目-real-sensor-v2_V4_8093_PREVIEW\backups\8094_billboard_background_20260726_120242`
- 最新适配器 SHA-256：
  `7ABBDA1074D71A06316E42AA392251CF4C0D96C91FB523D4DEC1BB182327622E`
- 最新 8094 HTML SHA-256：
  `04E93D22E9B2650721265DDBB376FE81A9E39B3851BB5FC672BF72DB5A9B6CBB`
- 发布中曾因误把 8768 识别为 pSpace、以及重启 8770 后首帧握手超时触发自动
  回滚；最终架构已将 8768 与 8770 分离，背景更新采用前端热发布，不再重启实时
  桥。

## 2026-07-26 3D 视口与滚轮缩放修复

- 追踪项：`BUG-BF3D-8094-VIEWPORT-WHEEL-20260726`。
- 根因一：页面旧的 `ops-cad-ghost-bands-fix` 会在加载后再次插入左右各 `24%`
  的 `!important` 缩进；它与适配器规则同优先级但插入更晚，导致 3D 画布重新
  变窄。
- 根因二：OrbitControls 未通过查看器合同暴露，前景标注层又会影响滚轮事件命中，
  无法稳定保证滚轮到达 Three.js canvas。
- 修复：`bf3d-furnace-body-billboard-adapter.js` 使用更高特异性的最终视口规则，
  让画布覆盖完整舞台；标注线层固定 `pointer-events:none`；查看器容器增加捕获式
  非被动滚轮缩放，背景控件区域除外；“全景”按钮继续用于恢复完整模型视图。
- 热发布未重启 8768/8770，发布结果确认两个进程均保持不变。
- Chromium `1366×768` 实测：画布/舞台宽度比 `0.9966`；模拟向上滚轮后相机距离
  从 `74.04` 降至 `49.83`，`zoomPassed=true`。截图和 JSON 位于
  `logs/8094_billboard_zoom_20260726/`。
- 验收时远端页面实际缓存标签为 `20260726-viewport-fit-r7`；功能合同和滚轮事件
  均已生效，验证器按 `20260726-viewport-*` 合同判断，避免仅因缓存尾号变化误报。
- 同次验收发现 manifest 偶发空响应时原适配器会每 `120ms` 立即重试，可能形成
  静态资源请求风暴并拖慢 8094；r8 改为 `1s → 2s → 4s` 指数退避，最高 `15s`，
  成功挂载后恢复初始退避并停止重试。

## 2026-07-26 8094 炉次分析入口移除

- 追踪项：`REQ-8094-HEAT-DASHBOARD-LINK-20260726-DISABLED`。
- 用户要求从 8094 页面移除“炉次分析”入口；执行
  [remote_surgical_disable_8094_heat_dashboard_link.ps1](../../tools/remote_surgical_disable_8094_heat_dashboard_link.ps1)
  对远端 8094 预览 HTML 做单文件定点移除，不删除保留的入口资源文件，不重启服务。
- 验证结果：8094 HTTP 200；页面导航仅剩总览、炉况诊断、参数优化建议、趋势分析、智能问答；
  8093、8094、8768 监听和 8094 计划任务均保持运行。
- 回滚备份：
  `F:\高炉炼铁项目-real-sensor-v2_V4_8093_PREVIEW\backups\8094_heat_dashboard_link_surgical_disable_20260726_140354\before_disable.html`。

## 2026-07-26 220.12 独立炉次仪表盘端口评估

- 用户问题：炉次分析仪表盘是否可以在 220.12 上使用独立端口访问，并暂不与 8094 联动。
- 结论：架构上可以，建议预留 `8891`；但当前不直接启动，因为 220.12 的 V4/V3 目录没有
  `db_dashboard` 服务代码，且 220.12 PostgreSQL 5432 的 `bf_sensor` 传感器表存在，
  `public.t_ipes_cond` / `public.t_ipes_out_put` 炉次表不存在。当前 8890、8891 空闲，
  8094 不依赖它。
- 完整独立服务还需要：独立目录中的 `server.py`、`heat_service.py`、`heat.html`、
  `index.html` 与 ECharts 静态资源；220.12 的 `bf_sensor` 只读连接；以及 IMES 炉次/产出
  数据的受控只读连接或镜像。数据库口令不写入代码、文档或页面。
- 只读证据：
  [远端端口/文件探针](../../tools/remote_probe_22012_heat_dashboard.ps1)、
  [PostgreSQL 关系探针](../../tools/probe_22012_heat_dashboard_db.py)。

## 2026-07-26 220.12 独立炉次仪表盘部署启动

- 追踪项：`OPS-22012-STANDALONE-HEAT-DASHBOARD-8891-DEPLOY-20260726`。
- 部署目录：
  `F:\高炉炼铁项目-real-sensor-v2_V4_8093_PREVIEW\standalone_heat_dashboard_8891`；
  同步本地 `db_dashboard/server.py`、`heat_service.py`、`heat.html`、`index.html`、
  ECharts 静态资源和独立运行脚本。IMES 凭据文件位于远端 `PT` 子目录，不在 Web 静态目录，
  ACL 限制为 Administrators/SYSTEM；密码未写入文档、页面或部署命令输出。
- 运行方式：计划任务
  `\BlastFurnaceServices\StandaloneHeatDashboard8891`，监听 `0.0.0.0:8891`；
  防火墙规则为 `BlastFurnaceStandaloneHeatDashboard8891`。服务进程只读访问 220.12
  PostgreSQL `bf_sensor` 和 IMES 只读数据，不修改生产库。
- 访问地址：`http://10.30.220.12:8891/heat`；API 为 `/api/overview`、`/api/heats`、
  `/api/heat-detail`。当前远端验收返回 133 个传感器点、约 1,960.98 万分钟值，最近 3 炉可读，
  最新炉次为 `2#20260726-332`；详情接口对最新炉次 HTTP 200。
- 验证脚本：
  [deploy_22012_heat_dashboard_8891.ps1](../../tools/deploy_22012_heat_dashboard_8891.ps1)、
  [run_22012_heat_dashboard_8891.ps1](../../tools/run_22012_heat_dashboard_8891.ps1)、
  [remote_verify_22012_heat_dashboard_8891.ps1](../../tools/remote_verify_22012_heat_dashboard_8891.ps1)。
  本地后端测试 `8 passed`；外部页面和 API HTTP 200；8094 保持 HTTP 200 且炉次入口不存在，
  8093、8094、8768、8770 监听保持。
- 回滚备份：部署脚本在远端创建
  `F:\高炉炼铁项目-real-sensor-v2_V4_8093_PREVIEW\standalone_heat_dashboard_8891\backups\heat_dashboard_8891_20260726_172722`。
