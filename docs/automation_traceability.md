# 自动化与运行可追踪映射

## OPS-SENSOR-REGISTRY-HOPPER-WEIGHT-SET-20260814

- 流程：正式 TSV 固定 11 个物理分量与 1 个派生语义 → 远端清单哈希和备份 →
  `sensor_registry` 事务登记 → 复用既有 `sync_from_243_pg.py` 单次同步物理分量 →
  注册表与分钟历史复核。
- 运行边界：没有增加常驻读取程序，没有创建计划任务，没有重启 8093、8768 或 8770；
  现有持续同步任务的定义未修改。
- 生产结果：14/14 注册匹配，11/11 物理点采集成功，写入 59 条分钟值和 71 条 raw 值。
- 未完成边界：派生 `Hopper_weight_set` 尚未由现有同步链路物化；后续实现必须复用现有读取
  结果，不另开 pSpace 连接。详见[生产登记交接](handoffs/2026-08-14-hopper-weight-set-registry-production.md)。

## REQ-TS-LEADERBOARD-CORRECTION-20260811

- 需求：修复19项两小时预测排行榜，使用同切点、IQR归一化分段误差、归一化WIS、方向、覆盖和动态性共同排名，并保留分维度冠军。
- 程序：[排行榜生成器](../tools/timeseries_leaderboard.py)、[8778只读接口](../tools/timeseries_sidecar_service.py)、[健康检查](../tools/check_timeseries_sidecar_python.py)、[专项测试](../tests/test_timeseries_leaderboard.py)。
- 数据：[排行榜JSON](../PT/时间序列预测评测/results/timeseries_model_leaderboard_current.json)、[排行榜CSV](../PT/时间序列预测评测/results/timeseries_model_leaderboard_current.csv)、[排行榜报告](../PT/时间序列预测评测/results/timeseries_model_leaderboard_current.md)。
- API：新增`GET /api/timeseries/leaderboard`，schema为`bf.timeseries.leaderboard.v1`；文件缺失或schema错误时返回503，不影响预测默认模型。
- 验证：Python语法通过；pytest 3项通过；真实8切点/19项目标生成成功；本机18778状态、模型和排行榜接口通过，默认模型仍为LastValue。
- 边界：本轮只完成本机代码和产物，未更新220.12的8778，未修改或重启8093/8768/8777/8094/8770/数据库。

## REQ-TIMESERIES-ACTUAL-PREDICTION-CURVES-20260811

- 需求：以趋势页19项同屏形式展示真实预测曲线，必须能区分切点前历史实测、切点后未来实测真值、模型P50预测和P10-P90区间，不能用指标表或示意线代替。
- 程序：[实际曲线导出器](../tools/plot_ridge_actual_prediction_curves_19.py)读取既有评测CSV、38套Ridge模型和首轮公共切点；不连接生产服务。
- 输出：[19项实际预测曲线](../PT/时间序列预测评测/results/ridge_actual_prediction_curves_20260808_0948_expert_sparse.png)、[逐分钟实际与预测值](../PT/时间序列预测评测/results/ridge_actual_prediction_curves_20260808_0948_expert_sparse.csv)。
- 固定样本：`2026-08-08 09:48`，`Ridge-Delta expert_sparse`，历史60分钟、预测120分钟；每个变量保持真实量纲。
- 验证：Python语法检查通过；19项目标全部成功生成；PNG人工核查无裁切，CSV包含历史与未来两阶段、实际值和P10/P50/P90；8777/8778及生产趋势页未修改。

## OPS-DIAG-RULES-ONE-CLICK-DEPLOY-20260806

- 流程：本地白名单/语法/合同测试 → 生成单一ZIP与SHA-256清单 → `reliable_ssh`固定路由和身份校验 → 原子上传 → 远端以当前代理为基线合并诊断块 → 全量备份 → 暂停8093守卫并原子安装 → 恢复8093 → 精确重启8094 → HTTP/资产标记验证；失败执行文件回滚与服务恢复。
- 传输：[可靠SSH入口](../tools/reliable_ssh_22012_cli.mjs)读取本机受控密码文件，固定校验ed25519主机指纹并写既有审计日志；一个部署进程只进行一次身份探测、一次压缩包上传和一次远程PowerShell执行。
- 变更范围：9个白名单诊断文件；只允许操作 `BFV4PreviewProxy8093` 与 `V3AutoPreviewProxy8094`。8768、8770、11434必须在部署前后保持同一监听PID。
- 防回退：代理补丁在220.12上使用当前生产代理作为base，只替换诊断函数块、路由和四个诊断资产版本；已存在的跨库MCP代码由基线原样保留。
- 当前证据：47项合同和dry-run通过；可靠SSH身份探测成功。本轮未上传部署包、未重启服务。

## REQ-8093-8094-DIAGNOSIS-REVIEW-AI-20260806

- 链路：诊断快照/八类系统分 → 所选炉况公式驱动 → 5分钟变化/60分钟统计/30天基线 → 调剂引擎1与知识检索 → 单炉况模型调用 → v3派生结果；人工评分/建议走独立追加事件表。
- 程序：[证据编排](../高炉前端数据/智能助手/backend/diag_ai_evidence.py)、[单炉况合同](../高炉前端数据/智能助手/backend/diagnosis_model_review.py)、[分析API](../高炉前端数据/智能助手/backend/diagnosis_ai_analysis_api.py)、[共享代理](../高炉前端数据/智能助手/backend/ollama_proxy_server.py)、[8094受控启用](../tools/remote_guarded_enable_8094_diagnosis_ai.ps1)。
- 配置：8093/8094均启用复核、免登录现场身份、模型复核和AI后台分析；复核库为220.12回环PostgreSQL，密码只通过机器环境变量引用。
- 部署：8093备份 `diagnosis_ai_analysis_20260806_072403`；8094备份 `8094_diagnosis_ai_20260806_073217`。8094 PID `14416 -> 17348`，8093/8768/8770/11434 PID保持不变。
- 验证：Python `46 passed`；远端8094 `pageInjected/contextCanSubmit/analysisHasVariables/analysisHasRecommendation/analysisHasKnowledge=true`，schema v3，模型复核和评分空请求均为400。

## REQ-8093-DIAGNOSIS-AI-EVIDENCE-GUIDANCE-20260805

- 程序：[证据编排](../高炉前端数据/智能助手/backend/diag_ai_evidence.py)、[批量模型合同](../高炉前端数据/智能助手/backend/diagnosis_model_review.py)、[后台调度](../高炉前端数据/智能助手/backend/ollama_proxy_server.py)、[只读数据访问](../高炉前端数据/智能助手/backend/diagnosis_review.py)、[详细弹窗](../高炉前端数据/assets/bf-diagnosis-manual-score-local.js)。
- 数据源：只读最新诊断 `feature_snapshot`、最近60分钟核心变量、30天基线、调剂引擎1结果和知识库检索结果；不修改规则诊断、建议引擎、安全门禁或生产参数。
- 每桶流程：服务端构造所选炉况的变量统计和规则驱动ID → 只读调用调剂引擎1 → 只读检索知识库 → 一次模型只生成该炉况口语解释 → 校验所有引用ID → 可信证据随v3结果保存。
- 幻觉边界：模型输出中的 `key_driver_ids/recommendation_action_ids/knowledge_chunk_ids` 必须是服务端上下文子集；最终展示数值和建议正文均来自服务端对象，不从模型自由文本解析。
- 状态存储：沿用 `bf_assistant.diagnosis_ai_analysis_snapshots`，通过v2 `prompt_version`形成新派生批次；无DDL迁移，人工评分两张事件表不变。
- 测试：40项Python合同；Chromium九视口；应用内浏览器验证点击、详细证据、无横向溢出和关闭不保存。当前v2 Firefox/WebKit等待运行时可用后补测。
- 部署：该段的纯8093边界是2026-08-05历史口径；2026-08-06起按上方双端口需求分别受控部署。

## REQ-8093-DIAGNOSIS-AI-FIVE-MINUTE-ANALYSIS-20260805

- 程序：[批量模型合同](../高炉前端数据/智能助手/backend/diagnosis_model_review.py)、[后台调度](../高炉前端数据/智能助手/backend/ollama_proxy_server.py)、[HTTP处理器](../高炉前端数据/智能助手/backend/diagnosis_ai_analysis_api.py)、[组合弹窗](../高炉前端数据/assets/bf-diagnosis-manual-score-local.js)。
- 数据：只读 `bf_sensor.diagnosis_snapshots`，写派生表 `bf_assistant.diagnosis_ai_analysis_snapshots`；人工评分两表不变。
- 频率：30秒轮询是否出现新5分钟桶；现行v3按主诊断或用户所选炉况分别调用模型，一次只生成一个炉况结果；失败冷却120秒。
- 部署：该段记录2026-08-05的纯8093初次部署；2026-08-06后按上方双端口需求分别受控部署并保护无关服务。
- 验证：37项合同；Chromium九视口；Firefox/WebKit各四代表视口。运行说明见[专项文档](8093_每5分钟八炉况智能分析_20260805.md)。
- 运行结果：最终部署备份 `logs/deploy_backups/diagnosis_ai_analysis_20260805_212403`，守卫暂停/恢复成功且未回滚；8093 HTTP 200、8768 PID不变，21:20生产批次AI API完成。诊断上下文和5分钟分析使用独立复核库短连接，避免共享问答连接池耗尽导致503。

## REQ-8093-DIAGNOSIS-REVIEW-NO-LOGIN-PRODUCTION-20260804

- 程序：[复核事件后端](../高炉前端数据/智能助手/backend/diagnosis_review.py)、[8093 API与注入](../高炉前端数据/智能助手/backend/ollama_proxy_server.py)、[守卫部署](../tools/remote_guarded_deploy_8093_diagnosis_review.ps1)、[服务探针](../tools/remote_probe_8093_diagnosis_review.ps1)、[数据库探针](../tools/remote_probe_8093_review_pg.py)。
- 配置：8093显式启用功能、关闭测试场景并设置 `BF_DIAG_REVIEW_REQUIRE_LOGIN=0`；匿名身份由服务端固定；复核库只允许 `127.0.0.1:5432/bf_trend`，密码通过 `BF_DIAG_REVIEW_PGPASSWORD_ENV=GL02_PGPASSWORD`引用机器环境。
- 表/API：`bf_assistant.diagnosis_review_events`、`diagnosis_manual_score_events`；上下文GET和两类评分POST，历史GET仍登录保护。
- 运行保护：只停启 `BFV4PreviewProxy8093`；部署前备份，失败回滚；8768、8094 PID及8094页面哈希为阻断性检查。
- 当前状态：2026-08-04已上线；22项测试、远端API/数据库、9视口手动评分验收通过；事件表保持0行，未注入测试生产记录。运行手册见[专项说明](8093_异常炉况评分免登录部署_20260804.md)。

## REQ-8093-DIAGNOSIS-REVIEW-LOCAL-PROTOTYPE-20260803

- 程序：[诊断复核后端](../高炉前端数据/智能助手/backend/diagnosis_review.py)、[8096/8769启动器](../tools/start_diagnosis_review_preview.py)、[浏览器验证器](../tools/verify_diagnosis_review_local.py)。
- 配置：功能开关 `BF_DIAGNOSIS_REVIEW_ENABLED`；复核库必须独立使用 `BF_DIAG_REVIEW_PG*` 且为回环地址；登录与会话来自环境变量。
- 表/API：`bf_assistant.diagnosis_review_events`；`/api/auth/logout`、`/api/diagnosis-review-context`、`/api/diagnosis-reviews`。
- 安全边界：本阶段不部署、不停止、不修改220.12:8093/8768/数据库；测试场景固定标记 `local_fixture`。
- 运行手册：[专项说明](8093_异常炉况诊断人工复核本地原型_20260804.md)。

## REQ-BF3D-8093-FURNACE-SUMMARY-READABILITY-20260802

- 需求：[需求追踪](requirements_traceability.md#req-bf3d-8093-furnace-summary-readability-20260802)、[专项说明](8093_七类工艺汇总浮层可读性调整_20260802.md)。
- 程序：[CSS 资源](../高炉前端数据/assets/bf3d-furnace-summary-readability-8093.css)、[页面入口](../高炉前端数据/frontend_dashboard_v3.server.html)、[原子部署器](../tools/remote_deploy_8093_furnace_summary_readability.py)、[守卫部署](../tools/remote_guarded_deploy_8093_furnace_summary_readability.ps1)、[测试](../tests/test_8093_furnace_summary_readability.py)。
- 配置：资源版本 `20260802-expanded7-r2`；使用 `.layered-cad-stage` 提升选择器权重，确保压过运行后追加的旧 116px 动态规则；桌面宽度 `208–242px`，紧凑宽度 `198px`，低高度宽度 `190px`；标题 `13–17px`、行文字 `10.5–13.5px`；`text-overflow:clip`、单位始终 `display:inline`。
- 部署保护：只允许 8093 HTML 与专用 CSS 变化；8094 页面、共享 adapter、8094 相机资源受 SHA-256 保护；守卫只停启 `BFV4PreviewProxy8093`，`BFV4PreviewWs8768` 全程保持。
- 当前状态：11 项合同/回归测试通过；守卫结果 `guard_paused/guard_restored/ws8768_unchanged=true`；8093 HTML 和 CSS HTTP 200，版本标记、198px 紧凑宽度、取消省略和单位保留均可从线上资源读取，8093/8768 均监听。最终页面/CSS SHA-256 为 `F308993A...24FC1` / `BDA77396...EE48`，备份 `backups/8093_furnace_summary_readability_20260802/20260802_210417`。Chrome DOM/截图矩阵因重载等待超时待补，不能标记为跨浏览器完成。

## REQ-BF3D-8093-BILLBOARD-EMPHASIS-20260802

- 需求：[需求追踪](requirements_traceability.md#req-bf3d-8093-billboard-emphasis-20260802)。
- 程序：[8093 专用运行时](../高炉前端数据/assets/bf3d-tooltip-stable-hover-8093.js)、[隔离部署器](../tools/remote_deploy_8093_stable_tooltip_hover.py)、[守卫闭环](../tools/remote_guarded_redeploy_8093_tooltip.ps1)、[合同测试](../tests/test_8093_stable_tooltip_hover.py)。
- 配置：`BILLBOARD_SCALE_MULTIPLIER=1.22`，页面 DOM 信号 `data-billboard-emphasis-scale=1.22`、`data-billboard-emphasis=moderate-8093`。
- 部署保护：只改变 8093 页面模块版本与 8093 专用资源；8094 页面、共享 adapter、8094 相机资源继续受 SHA-256 保护。
- 当前状态：6 项合同测试通过；8093/8768 服务和监听正常；Chrome 现场页读取到 121 点和 1.22 比例。

## BUG-BF3D-8093-TOOLTIP-JITTER-SINGLE-OWNER-20260802

- 需求与故障：[需求追踪](requirements_traceability.md#bug-bf3d-8093-tooltip-jitter-single-owner-20260802)、[专项说明](8093_Billboard悬停抖动修复_20260802.md)。
- 程序：[运行时](../高炉前端数据/assets/bf3d-tooltip-stable-hover-8093.js)、[部署器](../tools/remote_deploy_8093_stable_tooltip_hover.py)、[测试](../tests/test_8093_stable_tooltip_hover.py)。
- 配置：进入/退出半径 30/46px、切换优势量 12px、驻留 140ms、坐标 `viewport-fixed`、点位聚焦关闭。
- 部署保护：仅允许 8093 页面与专用 hover 资源变化；8094 页面、共享 adapter、8094 相机运行时按 SHA-256 阻断越界写入。
- 当前状态：5 项合同测试通过；2026-08-02 已通过 [守卫停—改—启脚本](../tools/remote_guarded_redeploy_8093_tooltip.ps1)上线，`guard_paused/guard_restored/ws8768_unchanged=true`，8093/8768 监听、HTTP 200，8094/共享资源哈希未变。冷启动竞态与远端 viewer 不暴露 `THREE` 的兼容处理已纳入运行时。


## REQ-BF3D-ASSET-CONTROLLED-MASTER-R1-20260721

- 构建入口：[build_controlled_master_r1.py](../PT/高炉3D模型/work/ASSET_10_20260721_R1_CONTROLLED_MASTER/scripts/build_controlled_master_r1.py)。
- 资产登记：[bf3d_asset_registry.v1.json](../PT/高炉3D模型/asset_registry/bf3d_asset_registry.v1.json)。
- 验证入口：[verify_controlled_master_r1.py](../PT/高炉3D模型/work/ASSET_10_20260721_R1_CONTROLLED_MASTER/scripts/verify_controlled_master_r1.py)、[Khronos报告](../PT/高炉3D模型/work/ASSET_10_20260721_R1_CONTROLLED_MASTER/reports/khronos_gltf_validator_r1.json)。
- 自动化边界：构建脚本只读取锁定 V5、VIS30 与正式 GLB，输入 SHA 不匹配即失败；输出只写入 ASSET-10 阶段目录和资产登记目录，不覆盖正式或历史资产。
- 当前状态：`candidate_ready_for_controlled_review`，生产接入未授权。
本文档是当前工作区的最小追踪基线，用于把需求、程序、配置、接口、验证与运行文档串联起来。后续自动化、数据库、接口和计划任务变更应在此追加映射，而不是只保留在代码或临时对话中。

## 需求映射

## OPS-IMES-WEB-LOCAL-GUI-RELAY-20260805

- 目标：提供本机可点击的 IMES Web 访问入口，按需建立 220.12 跳板转发并打开本机登录页。
- 程序：[GUI 启动器](../tools/imes_web_launcher.py)、[既有回环转发器](../tools/imes_22012_relay.py)。
- 配置/安全边界：仅转发 `127.0.0.1:18080 -> 220.12 -> 10.10.181.209:8080`；不监听 `0.0.0.0`；SSH 密码只从当前进程环境变量或 GUI 临时输入获取，不写入 Markdown、脚本、命令行、日志或 HTTP 响应；IMES Web 密码和验证码仍由浏览器登录流程处理。
- 验证：`python -m py_compile tools/imes_web_launcher.py`；`pytest -q tests/test_imes_web_launcher.py`，2 项通过。
- 当前状态：本地 GUI 已实现；未启动远端服务、未写数据库、未把 IMES/Vastbase/pSpace 明文凭据写入普通文档。

| ID | 需求/运维目标 | 程序与配置 | API/数据契约 | 验证 | 文档与状态 |
|---|---|---|---|---|---|
| `OPS-IMES-REALTIME-1MIN-20260809` | 将220.12 IMES实时镜像任务由每5分钟改为每1分钟尝试执行，同时禁止长任务重叠 | [一体化部署器](../tools/set_22012_imes_realtime_1min.ps1)、计划任务`\GL02SensorSync\IMESRealtime` | 原Action/Principal不变；周期`PT1M`；`MultipleInstancesPolicy=IgnoreNew`；读取`bf_imes.raw_rows`只读验收；XML备份失败回滚；保护8093/8768/8094/8770 PID | PS语法与合同测试通过；远端脚本哈希`E21BCAEA...B13BF`；19:44独立复核仍为`PT1M+IgnoreNew`，`bf2_output_list_cond_data`镜像到19:44:39，炉次`2#20260809-126`；四个受保护PID未变 | [部署记录](handoffs/2026-08-09-imes-realtime-1min.md)；状态`production_deployed_verified`；单轮可超过2分钟，实际完成频率受`IgnoreNew`约束；下游质量汇总仍为5分钟 |
| `REQ-SI-V20-DUAL-TIMING-AND-HOURLY-MATCH-20260809` | 把历史开口前60分钟回看与生产服务器整点预测拆成两套统计；生产预测匹配发起后的下一次真实开口 | [服务](../高炉前端数据/智能助手/backend/si_v20_shadow.py)、[API](../高炉前端数据/智能助手/backend/ollama_proxy_server.py)、[小时运行器](../tools/run_si_v20_hourly_prediction.py)、[小时任务注册](../tools/register_22012_si_v20_hourly_task.ps1)、[汇总一分钟任务](../tools/set_22012_heat_quality_sync_1min.ps1)、[工作台](../高炉前端数据/si_v20_workbench.html) | 历史`cutoff=open_ts-60min`且同炉比较；旧生产口径为`hourly_schedule` | 定向pytest 22项通过 | 已由`REQ-SI-V20-STRICT-HOURLY-CLOSED-LOOP-20260810`取代；旧任务不再部署，生产基线使用`strict_hourly` |
| `REQ-SI-V20-CONFIGURABLE-SCHEDULE-20260809` | 页面可选1/10/30/60/1440分钟生产预测周期，并支持历史任意范围/粒度批量或指定时刻预测与曲线 | [服务](../高炉前端数据/智能助手/backend/si_v20_shadow.py)、[API](../高炉前端数据/智能助手/backend/ollama_proxy_server.py)、[分发器](../tools/run_si_v20_schedule_dispatcher.py)、[任务注册](../tools/register_22012_si_v20_schedule_task.ps1)、[工作台](../高炉前端数据/si_v20_workbench.html) | 固定一分钟后台轮询数据库配置；配置/批次/逐点审计三表；实时按requested_at后下一真实开口，历史按时间槽后下一真实开口；5000点上限；只写影子审计 | 定向pytest 28项通过；JS/PS/Python语法通过；生产三表、任务、8093/8094 API核验通过；23:00首点成功；8093浏览器无横向溢出 | 状态`production_deployed_verified`；默认60分钟，任务SYSTEM/IgnoreNew/最近结果0，页面资源r6 |
| `REQ-SI-V20-CURVE-EXPORT-20260809` | 按日期或炉次范围筛选并分别下载预测曲线与实际Si曲线 | [工作台](../高炉前端数据/si_v20_workbench.html)、[页面逻辑](../高炉前端数据/assets/bf-si-v20-workbench.js) | 导出服从当前日期、炉次和显示筛选；预测保留P10/P50/P90和匹配信息；实际按炉次去重；UTF-8 BOM及公式注入防护 | 8093真实页面124~127筛选为4行，实际Si导出4炉，页面无横向溢出；8094资源标记和API 200 | 已随r6部署8093/8094；Firefox/WebKit代表视口待补验 |
| `Q-COHESIVE-ZONE-TREND-CALCULATION-20260808` | 分析软熔带根部上升/下降的现有计算及可生产化升级路径 | [估计器](../炉况规则引擎/features/cohesive_zone_estimator.py)、[参数](../炉况规则引擎/config/cohesive_zone_estimator.yaml)、[8767适配](../自动诊断服务/local_pg_ws_bridge.py)、[历史回放](../tools/soft_zone_replay_server.py) | 当前输出仍为`bf3d_snapshot.v1.estimated.cohesive_zone`；建议后续持久化一分钟状态并增加15/30/60分钟`ΔH`与方向概率，不在本次新增API/schema | 静态核对现有双窗口、热力修正、压力厚度、偏心、置信度和安全合同；识别2026-08-05分钟聚合语义边界；本次未重新执行测试 | [问题追踪](question_traceability.md#q-cohesive-zone-trend-calculation-20260808)、[详细分析](软熔带趋势计算与升级分析_20260808.md)；仅分析和文档更新，未修改生产模型、数据库、服务或页面 |
| `REQ-SI-FUELRATIO-MES-REPORT-PERSISTENCE-20260808` | 检查并落库 MES Web 作业日志燃料比、料速/批数和全量报表字段 | [报表解析器](../数据库同步和存取/src/imes_report_client.py)、[同步入口](../数据库同步和存取/sync_bf2_operation_log_report.py)、[任务注册器](../tools/register_22012_bf2_operation_log_report_task.ps1)、[代理部署器](../tools/remote_deploy_22012_imes_report_proxy.ps1)、[MCP 工具](../高炉前端数据/智能助手/mcp/bf_data_mcp_server.py) | `bf_imes.imes_bf2_operation_log_report` / `v_bf2_operation_log_report` 保存 180天×24行和全部 `report_cells`；`report_fuel_ratio/report_coal_ratio` 为 Raqsoft 公式重算；`material_rate=semantic_unconfirmed`，不得把批数静默当料速；报表炉前 Si 尚未入库 | 220.12 18084 HTTP 200；历史回填 4320 行/180 天，重复键 0；计划任务 `IMESBF2OperationLogReport5m` `LastTaskResult=0`；活动 V4 MCP 工具列表/直接调用通过；`pytest -q tests/test_imes_report_client.py` 2 passed | [落库与页面方案](../PT/预测铁水Si含量/docs/fuel_ratio_report_persistence_page_plan_20260808.md)；状态`production_report_sync_deployed`，炉前 Si/料速语义仍待后续确认 |
| `REQ-SI-V20-OPEN-MINUS-HITRATE-20260807` | 将平均Si预测固定为“每炉开口前1小时”影子实验，目标验证±0.05命中率能否从昨日46.67%提升到≥60%且MAE不恶化 | [V20特征](../PT/预测铁水Si含量/src/si_semantic_engine/v20_open_minus_features.py)、[数据集构建器](../tools/build_open_minus_si_dataset_v20.py)、[训练评估器](../tools/train_open_minus_si_v20.py)、[一键预测兼容入口](../tools/predict_next_heat_si_v19.py) | `target__Si_mean=heat_performance_quality_summary.si_avg`；主cutoff为`open_ts-60min`并保留120/90/60/30/15/0min；前1~5炉Si独立字段且只用已发布更早炉次；PCI和传感器窗口为`[cutoff-window, cutoff)`；烧结化学仅低置信度时间背景 | V20纯单元测试7项通过；数据集/训练/一键预测CLI `--help`加载通过；完整220.12回放和训练待VPN可达时执行 | [V20实验说明](../PT/预测铁水Si含量/docs/v20_open_minus_hitrate_20260807.md)；状态`implemented_experimental_offline_not_promoted`，不替换生产模型、不写220.12业务表 |
| `REQ-FOREMAN-COAL-HOURLY-20260806` | 固化2号高炉工长趋势新增SIO点位，准确显示上小时/本小时喷煤量并按整点落库；不增加pSpace采集进程 | [页面时间积分](../高炉前端数据/assets/foreman-coal-math.js)、[工长趋势接入](../高炉前端数据/assets/foreman-trend-preview.js)、[本机点位补丁器](../tools/apply_foreman_points_and_coal_storage.py)、[整点落库模块](../tools/foreman_coal_hourly_store.py)、[Schema](../tools/sql/foreman_coal_hourly_20260806.sql)、[生产部署器](../tools/remote_deploy_foreman_points_coal_20260806.ps1) | `PCI_previous_hour=GL02/PC/T0004`；`PCI_rate=GL02/PC/T0007`；`PCI_current_hour=从整点按真实时间差积分`；表`bf_sensor.coal_injection_hourly`及两个视图；现有8770秒级流和现有30秒分钟同步任务复用 | 秒级5秒采样积分、11:00–11:19定值积分、长缺测限制3项Node测试通过；相关pytest 9项通过；点位150条、物理148、派生2；220.12注册16/16，物理实时值15/15，时间戳由14:35推进至14:53；四份清单SHA-256一致 | [完整口径](工长趋势2号炉点位与整点喷煤量_20260806.md)；状态`production_realtime_ready_history_backfill_pending`：`PCI_rate`有2月起历史，另外15个新增点仅从14:22开始入库，旧历史尚未回补 |
| `REQ-FOREMAN-CO-H2-WIND-REGISTRY-20260807` | 把 CO、H2、鼓风动能、标准风速、实际风速及已确认 CO2 纳入正式点位；部署时先写 `sensor_registry` 再恢复既有同步，不增加 pSpace 常驻读取程序 | [正式清单补丁器](../tools/apply_foreman_points_and_coal_storage.py)、[8770桥接](../tools/pspace_8092_realtime_bridge.py)、[注册器](../tools/init_foreman_points_pg_light.py)、[受控部署器](../tools/remote_deploy_foreman_points_coal_20260806.ps1)、[部署热更新器](../tools/remote_hot_deploy_foreman_points_coal_20260806.ps1) | CC/GF2：`CO_top=T0112`、`CO2_top=T0113`、`H2_top=T0111`；GL02/BT：`BlastEnergy=T0136`、`BlastSpeedStd=T0133`、`BlastSpeedActual=T0134`；部署注册确认数必须为19，随后启动 `BlastFurnaceV3PgContinuousSync30s` | 本机清单验证153行/151物理/2派生/19确认；桥接、清单和缺失语义相关pytest 8项通过；220.12 最近完整轮次 `tags_ok=151,tags_error=0`，六点均有 Good 分钟值 | [完整点位与部署顺序](工长趋势2号炉点位与整点喷煤量_20260806.md)；状态`production_deployed_verified` |
| `REQ-FOREMAN-SYNC-CONFIG-ENTRY-20260807` | 现有实时同步入口显式加载正式清单，避免部署后仍为148个点 | [实时入口](../数据库同步和存取/run_realtime_sync_pg_bg.ps1)、[同步配置](../数据库同步和存取/config/sync_config.json)、[受控部署器](../tools/remote_deploy_foreman_points_coal_20260806.ps1) | `--config <ScriptRoot>\\config\\sync_config.json`；入口与153行清单同包替换；随后核验 `sync_runs.tags_ok` 和 CO/H2/CO2/BT 新点 Good 分钟值 | 本机11项专项测试通过；PowerShell语法通过；220.12入口/配置哈希与本机一致，最近轮次 `tags_ok=151,tags_error=0`，六点均有 Good 分钟值 | [配置入口说明](config_reference.md#工长趋势同步配置入口2026-08-07)；状态`production_deployed_verified` |
| `REQ-BF3D-8093-FURNACE-BODY-NO-SIM-20260801` | 将 8094 已验收的高炉本体、133 点 Billboard 和炉壳表面相机同步到 8093，但 8093 不加载“炉内仿真与工艺对象”面板或内部仿真运行时 | [8093 受控补丁器](../tools/patch_8093_furnace_body_no_simulation.py)、[133点适配器](../高炉前端数据/assets/bf3d-furnace-body-billboard-adapter.js)、[8093相机入口](../高炉前端数据/assets/bf3d-surface-camera-guard-8093.js)、[共享表面相机算法](../高炉前端数据/assets/bf3d-surface-camera-guard-8094.js)、[浏览器验收器](../tools/verify_remote_8093_furnace_body_no_simulation.py)、[契约测试](../tests/test_8093_furnace_body_no_simulation_contract.py) | 8093 与 8094 共享远端 `models/gl02_blast_furnace.glb`，SHA-256 `150DF18B...4ED53`，对应 `GL02_FURNACE_BODY_R1.glb`；页面补齐 21 个静压兼容行和两处 `scene/model/controls/getBuffer` viewer 合同；加载 133 点适配器及端口作用域为 8093 的表面相机入口；明确不加载 `bf3d-internal-simulation.js/css`，`.bf3d-sim-panel` 防御性隐藏 | 远端真实 Chrome：模型资产标识 `GL02_FURNACE_BODY_R1.glb`、133 点、`bf3d.surface-camera-shell-guard.8093.v1`、连续滚轮碰撞及 `1.2m` 炉壳间距全部通过；仿真面板数量 0、仿真运行时不存在；5 页面×9 Chromium 视口共 45/45 可达、无横向溢出，正式头部可见且浏览器错误 0；本地 2 项契约测试通过 | 已部署 `http://10.30.220.12:8093/#overview`；最终 8093 HTML SHA-256 `5C536EF1...C6146`；首个完整回滚备份 `backups/8093_furnace_body_no_simulation_20260801/frontend_dashboard_v3.server.html.20260801_023920.bak`；证据 `logs/acceptance/8093_furnace_body_no_simulation_20260801_r1`；8094 页面 HTML 仍为 `ED0D9345...DF4C4`；Firefox/WebKit/现场 Edge 待补 |
| `BUG-BF3D-8093-NEAR-CLIP-20260801` | 修复 8093 放大到炉壳表面后“相机未越壳但炉壳消失、视觉上像穿入炉内”的近裁剪面缺陷 | [共享相机守卫](../高炉前端数据/assets/bf3d-surface-camera-guard-8094.js)、[8093缓存隔离入口](../高炉前端数据/assets/bf3d-surface-camera-guard-8093.js)、[远端部署器](../tools/deploy_8093_near_plane_fix.ps1)、[缓存版本部署器](../tools/deploy_8093_near_plane_cache_bust.ps1)、[部署探针](../tools/probe_8093_near_plane_deployment.ps1)、[浏览器回归](../tools/verify_remote_8093_furnace_body_no_simulation.py)、[服务器验收启动器](../tools/run_remote_8093_near_plane_acceptance.ps1)、[契约测试](../tests/test_8093_furnace_body_no_simulation_contract.py) | 根因是全模型适配器按包围球把 `camera.near` 重算到约 `26.67m`，防穿透守卫只约束相机坐标而未恢复投影矩阵；8093 现固定 `safeNearPlane=0.05m`，在表面 target、滚轮和 80ms 周期守卫三处纠偏并调用 `updateProjectionMatrix()`；条件限定 `PORT_SCOPE === "8093"`，8094 行为不变；主页面外层入口版本同步更新为 `near-plane-r4` 避免旧标签页命中 `sync-r1` 缓存 | 220.12 文件与 HTTP 返回哈希一致：入口 `01231424...D462F9`、共享守卫 `0C331DE1...AB929`、主页面 `8DF482B7...01B9D6`；真实 Chrome 标准 WheelEvent 10 次后 `collisionBlocked=true`，炉壳法向间距 `1.200m`、相机到 target `1.2353m`、`cameraNear=0.050m`，133 点、无仿真面板、浏览器错误 0，10 项核心断言全通过；本地 2 项契约测试通过 | 已部署 `http://10.30.220.12:8093/#overview`；资源回滚 `backups/8093_near_plane_fix_20260801/20260801_050810`（2 文件），页面回滚 `.../20260801_053530`；核心证据 `logs/acceptance/8093_near_plane_fix_20260801_r8`；布局沿用同日 `r1` 的 45/45 基线，本轮服务器无界面 Chrome 截屏与尺寸切换均超过用户规定的单次 5 秒上限，未生成新截图；Firefox/WebKit/现场 Edge 和用户端视觉复核待补 |
| `REQ-BF3D-8093-DUAL-CAMERA-MODES-20260801` | 将 8093 相机从固定表面法线守卫升级为“炉心 360° 全炉旋转＋Billboard 动态表面聚焦”双模式，同时保留近裁剪和炉壳防穿透 | [8093 独立双模式运行时](../高炉前端数据/assets/bf3d-surface-camera-guard-8093.js)、[本机验收页](../高炉前端数据/bf3d_8093_dual_camera_harness.html)、[页面补丁器](../tools/patch_8093_furnace_body_no_simulation.py)、[远端原子部署器](../tools/remote_deploy_8093_dual_camera_modes.py)、[SMB 限时回退部署器](../tools/deploy_8093_dual_camera_modes_smb.py)、[浏览器验收器](../tools/verify_remote_8093_furnace_body_no_simulation.py)、[契约测试](../tests/test_8093_furnace_body_no_simulation_contract.py)、[部署测试](../tests/test_8093_dual_camera_deploy.py) | schema `bf3d.camera.dual-mode.8093.v2`；overview target 为炉体中心、全模型包围半径限制最小距离、方位角无限；focus 由真实 Billboard 进入，按当前相机方位重新 Raycast 炉壳并更新点/法线，滚轮安全距离 `1.2m`、near `0.05m`；专项页固定直接加载 `GL02_FURNACE_BODY_R1.glb` 并校验 `8,229,120` bytes；按钮/Esc/全景恢复炉心模式；8094 文件不参与该运行时 | 本地语法与 4 项契约/隔离测试通过；模型纠错后真实浏览器确认 `modelAssetId=GL02_FURNACE_BODY_R1`、实际/预期均 `8229120` bytes、`assetVerified=true`、133 点、`overview/furnace-center`、near `0.050m`、包围半径 `25.769`、浏览器错误 0。旧 `4,314,736` bytes 模型上的 `650.8°`/动态聚焦/碰撞数据降级为算法原型历史，正确资产完整交互待重跑 | 本机正确资产加载冒烟已完成；220.12 SSH banner 在 3～4 秒限时内超时，SMB 管理共享返回访问拒绝，因此截至本记录尚未覆盖远端 8093，远端仍保持 `near-plane-r4/v1`；部署前必须在正确资产上重跑双模式交互，部署恢复后运行原子部署器并复验 8093，8094 必须保持哈希不变；Firefox/WebKit/现场 Edge 与 45 组合待补 |
| `REQ-BF3D-8094-SURFACE-CAMERA-GUARD-20260801` | 将 8094 总览 3D 相机的 OrbitControls target 从炉内包围球中心改到当前可见炉壳表面，并阻止滚轮穿过炉壳 | [8094 炉壳表面相机守卫](../高炉前端数据/assets/bf3d-surface-camera-guard-8094.js)、[幂等页面补丁器](../tools/patch_8094_surface_camera_guard.py)、[远端 Chromium 验收器](../tools/verify_remote_8094_surface_camera_guard.py)、[契约测试](../tests/test_8094_surface_camera_guard_contract.py) | 目标点由相机朝炉心射线与 `IMG2THREEJS_FITTED_GL02_SHELL` 的首个交点产生，并仅沿外法线偏移 `0.06m`；滚轮使用该表面 target，平移关闭；每次向内 Dolly 先做炉壳 Raycast，并在同一滚轮事件内将法向间距限制为 `1.2m`；“全景”仍重新求真实炉壳 target，不回到炉心 | 220.12 Chrome 真实页面保留 133 点；表面命中来源 `shell-raycast`、目标距真实壳面 `0.06m`；连续滚轮触发碰撞后法向间距精确为 `1.2m`、相机到 target 约 `1.235m`；全景后仍为表面 target；Chromium 规定 9 视口全部无横向溢出且守卫就绪；9 项断言通过 | 已部署 `http://10.30.220.12:8094/#overview`；8093 主 HTML SHA-256 部署前后均为 `4F0D80F4...C3CCEE`，未修改；回滚备份 `backups/8094_surface_camera_guard_20260801/frontend_dashboard_v3.8094_preview.server.html.20260801_021740.bak`；证据 `logs/acceptance/8094_surface_camera_guard_20260801_r1`；本次仅 Chromium，Firefox/WebKit/现场 Edge 待补 |
| `DOC-BF-LLM-DECISION-SYSTEM-20260727` | 编制《高炉工艺大模型智能决策系统技术报告》，融合真实高炉数据、已有炉况判断、专家知识库、MCP服务器、27B领域大模型、多目标博弈、帕累托优化及多智能体任务编排思想 | [DOCX 构建器](../tools/build_multiobjective_game_pareto_report.py)、[Visio风格流程图生成器](../tools/build_bf_report_flowcharts.py)、[报告图片资产](assets/bf_decision_report_v2_4/)、[冀南钢铁集团Logo](../高炉前端数据/logo/冀南钢铁集团logo.png)、[燕山大学Logo](../高炉前端数据/logo/燕山大学logo.png) | 报告使用“炽穹·高炉炼铁大模型”公开品牌口径；采用1.5TB高炉领域数据对27B基础模型进行参数高效微调，主体参数冻结，LoRA/QLoRA适配参数承载领域能力，通用任务混合与双轨回归评测作为能力保持门；业务数据流为用户问题、炉况上下文、MCP工具结果、专家知识证据进入27B工艺大模型并形成可解释回答；多智能体协同包括共享上下文、任务分解、角色协作、冲突协调、任务编排、安全门控、反馈与班次承接；不呈现炉况研判与操作建议的内部形成细节，不新增 API、schema、生产写入或部署 | 构建器检查 DOCX ZIP结构、正文、表格、页眉页脚、XML/关系和图片嵌入；版式固定为标题中文黑体，正文、项目符号、表格、图注和公式宋体小四号（12磅）；封面只保留报告标题及冀南钢铁集团、燕山大学两个Logo，不再显示副标题、项目说明、版本、日期或密级；内嵌5张系统界面图、2张Visio风格流程图及2个Logo | [高炉工艺大模型智能决策系统技术报告 V2.5](高炉工艺大模型智能决策系统技术报告_V2.5_20260727.docx)；对外技术方案稿，训练方法表述以能力保持验证为准 |
| `REQ-HEAT-MULTISOURCE-EXPLORER-20260727` | 将 220.12 的独立炉次炉况仪表盘扩展为可按任意左闭右开时间窗查询的多源只读数据工作台，并接入当前已授权的 Vastbase、PostgreSQL GL02、pSpace 与 IMES Web 数据面 | [多源适配器](../db_dashboard/external_sources.py)、[炉次服务](../db_dashboard/heat_service.py)、[HTTP/导出服务](../db_dashboard/server.py)、[生产页面](../db_dashboard/heat.html)、[交互控制器](../db_dashboard/heat_data_explorer.js)、[凭据迁移器](../tools/migrate_22012_dashboard_external_credentials.py)、[远端浏览器验收器](../tools/verify_remote_8891_multisource_dashboard.py) | 数据目录固定为 31 个白名单数据集：Vastbase 生产作业 6、Vastbase 实验室 5、PostgreSQL GL02 6、pSpace 2、IMES Web 12；查询支持 `start/end/meltno/search/variables/page/page_size`，时间窗为 `[start,end)`，最大 5000 行；CSV/XLSX 导出复用同一白名单查询；浏览器不得提交任意 SQL、任意 URL 或任意 pSpace tag | 220.12 实读：目录 31 项；Vastbase 双账号、PostgreSQL 与 pSpace 健康检查 ready；正式炉次 `2#20260726-345` 铁水化验按 `heatno+batchno` 精确返回；CSV/XLSX 均 HTTP 200 且文件头正确；真实页面 pSpace 查询 2 行；首次复验发现手机表单把页面撑至 572px，增加 `min-width:0` 与单列 `minmax(0,1fr)` 后，Chromium 9 个规定视口 9/9 无横向溢出、控制台错误 0；IMES Web 因服务器现有配置只有用户名而无可验证密码，状态明确为 `authorization_required` | [专项运行说明](22012_8891炉次多源数据仪表盘_20260727.md)；远端访问 `http://10.30.220.12:8891/heat`；证据 `F:\高炉炼铁项目-real-sensor-v2_V4_8093_PREVIEW\logs\acceptance\8891_multisource_20260727`；凭据只存 ACL 受限且被 Git 忽略的 `PT/external_sources.local.env`；8094 未修改；Firefox/WebKit/现场 Edge 新面板证据仍待补 |
| `REQ-BF3D-8095-BILLBOARD-FOCUS-GUARD-20260726` | 在当时不改变 8094 的前提下，为 8095 的 133 点 Billboard 增加“点位局部聚焦＋炉壳防穿透＋退出恢复炉心全景” | [8095 预览页](../高炉前端数据/frontend_dashboard_v3.8095_preview.server.html)、[聚焦防穿透运行时](../高炉前端数据/assets/bf3d-billboard-focus-guard-8095.js)、[远端验收器](../tools/verify_remote_8095_billboard_focus_guard.py) | 点击真实 Billboard 后把 OrbitControls target 切到点位，按表面法线放置相机；滚轮 Dolly 前用炉壳 Raycaster 约束安全距离 1.2m；退出后恢复原炉心 target、相机与全景旋转；该适配器仍只由 8095 页面加载 | 远端真实点击 `T_body_L9_H`，中文语义“炉腰温·L9H”；聚焦距离约 4.4069m；连续推进在距炉壳 1.2m 时触发 `collisionBlocked=true`；退出后相机/target 恢复；7 项机器断言全部通过，验收报告 `F:\高炉炼铁项目-real-sensor-v2_V4_8093_PREVIEW\logs\acceptance\8095_focus_guard_20260727_r3\8095_focus_guard_acceptance.json` | 访问 `http://10.30.220.12:8095/`；“8094 未修改”是截至 2026-07-27 的历史状态，2026-08-01 用户另行授权 8094 使用独立的表面相机守卫，见 `REQ-BF3D-8094-SURFACE-CAMERA-GUARD-20260801`；8095 适配器本身仍不得加载到 8094 |
| `REQ-IMES-MCP-FULL-VARIABLE-TEMPLATES-20260727` | 将两个IMES只读账号当前可读的每个实际变量补齐为逐字段业务解释、口语别名、直接问法和程序调用模板，并让MCP口语检索使用同一目录 | [模板生成器](../tools/update_imes_mcp_full_variable_templates.py)、[315字段语义目录](../高炉前端数据/智能助手/mcp/imes_full_variable_catalog.json)、[MCP加载与检索](../高炉前端数据/智能助手/mcp/imes_relay_mcp_server.py) | 目录由真实取样清单生成，覆盖`operations/laboratory`、11个对象、315个“对象×字段”；每项含账号、对象、字段、含义、别名、可信度、时间字段、主标识、口语示例与推荐工具；未知语义明确保留边界，不依据编号猜测 | 生成器`--check`确认11/315全覆盖且无遗漏；模板测试5项、MCP测试19项，共24项通过；料仓编号增加数字边界，避免“24号仓”误命中“4号仓” | [指令模板全集](../PT/IMES_Vastbase_MCP指令模板全集.md)、[覆盖清单](../logs/imes_mcp_full_variable_coverage_20260727.json)、[测试记录](test_reference.md#test-imes-mcp-full-variable-templates-20260727)；本机实现完成，220.12仍须在SSH恢复后同步 |
| `REQ-IMES-MULTI-ACCOUNT-ANY-READ-MCP-20260727` | 让 IMES MCP 通过现有生产作业与实验室两个只读账号访问其有权读取的任意数据，并支持具体变量/时间范围查询 | [多账号MCP](../高炉前端数据/智能助手/mcp/imes_relay_mcp_server.py)、[完整记录导出](../tools/export_imes_complete_row_samples.py)、[真实冒烟](../tools/smoke_test_imes_multi_account_mcp.py)、[stdio契约冒烟](../tools/smoke_test_imes_mcp_stdio.py) | `account_profile=operations/laboratory`；`list_imes_database_profiles`、`list_imes_business_objects`、`query_imes_variables`、`query_imes_readonly_sql`；时间窗为左闭右开；任意SQL仅允许单条只读语句；响应默认500、最大5000行 | 16项单元测试；stdio列出13工具且新增Schema完整；真实Vastbase冒烟为6/5个对象、变量查询10/7行、SQL查询5/1行，写SQL被拒绝 | [调用与边界](22012_IMES跳板转发与MCP.md#4-imes-relay-mcp)、[完整记录说明](IMES逐对象完整真实记录取样_20260727.md)；用户要求的明文凭据只在已忽略的本机报告中，MCP接口不回显密码；220.12同步因SSH超时待执行 |
| `REQ-SI-TEMPORAL-SEMANTIC-V5-20260727` | 持续扩展可解释Si神经元并严格评估从0.05向0.02收缩 | [V4派生](../PT/预测铁水Si含量/src/si_semantic_engine/v4_features.py)、[只读多窗口提取](../PT/预测铁水Si含量/src/si_semantic_engine/extract_v4_temporal_stats.py)、[V5特征](../PT/预测铁水Si含量/src/si_semantic_engine/v5_features.py)、[V5训练](../PT/预测铁水Si含量/src/si_semantic_engine/train_v5.py) | MES正式meltno；特征严格早于opentime；133点30/60/120/240分钟统计；历史Si仅使用截止前已发布更早炉次；只写本地Parquet/实验产物 | 30项单元测试；220.12只读事务；304,703行/115分片；V5测试MAE 0.047882、±0.02为31.10%；滚动月MAE 0.043577～0.075529；目标未达 | [V5方法](../PT/预测铁水Si含量/docs/experiment_method_v5.md)、[阶段报告](../PT/预测铁水Si含量/reports/2026-07-27_V4_V5持续迭代与0.02目标评估.md)；`experimental_offline_v5`，不接MCP、不改生产库/8093服务 |
| `REQ-8093-HEAT-PERFORMANCE-QUALITY-20260806` | 将正式炉次生产实绩和全部铁水试样聚合为220.12一炉一行事实，并在8093提供可展开原始试样的只读区域 | [表与存储合同](../高炉前端数据/智能助手/backend/heat_performance_quality.py)、[同步器](../tools/sync_22012_heat_performance_quality.py)、[8093接口](../高炉前端数据/智能助手/backend/ollama_proxy_server.py)、[前端区域](../高炉前端数据/assets/bf-heat-performance-quality-8093.js) | 正式`meltno`主键；原始试样不删除；C/Si/Mn/P/S均值、Si中位数/范围并存；缺失不补0；质量文本只描述完整性和Si 0.20%–0.40%目标带；首次全量、之后每5分钟回看3天幂等upsert；8093只读；连接类异常有限重试 | 本机`py_compile`、JS语法和专项+MES+跨源MCP共66项通过；2026-08-06生产全量9622炉、增量43炉、最新082炉均值复算、API和受保护PID通过；证据见[交接记录](handoffs/2026-08-06-8093-heat-performance-quality.md) | 生产仅重启8093并记录8768/8094/8770 PID；本次成功部署三者PID均未变化；本机源代码为发布源，不从远端反向覆盖；跨VPN浏览器复验受空响应影响仍需网络恢复后补测 |
| `REQ-HEAT-QUALITY-REPAIR-CLOSED-LOOP-20260807` | 修复时间回看状态覆盖、未来数据、缺口审计、原因谱系、指标命名和扫描截断 | [表/upsert/审计](../高炉前端数据/智能助手/backend/heat_performance_quality.py)、[分页回看同步器](../tools/sync_22012_heat_performance_quality.py)、[迁移](../tools/migrate_heat_quality_time_repair_columns_22012.py)、[API过滤](../高炉前端数据/智能助手/backend/ollama_proxy_server.py) | `time_anomaly_repaired` 谱系优先；未来/日期锚点冲突隔离；无证据不写；默认镜像链路复核已有汇总，镜像行过期时按正式炉号日期与 `work_date` 重建血缘；时间修复不覆盖罐次/试样明细 | [38项相关测试](test_reference.md#test-heat-quality-repair-production-20260809)与 `py_compile` 通过；089/090 精确 API、计划任务和哈希证据见[生产交接](handoffs/2026-08-09-heat-quality-closed-loop-production.md) | 2026-08-09 已部署220.12；任务结果0，089/090已修复；8093/8768运行，8094/8770未重启 |
| `REQ-SI-TEMPORAL-NEURONS-V2-20260726` | 将铁水Si主验收从±0.10收紧为±0.05个Si百分点，并把130点高延迟时序扩展为可解释微神经元、物理耦合神经元和语义神经元 | [单点多窗口派生](../PT/预测铁水Si含量/src/si_semantic_engine/temporal_features.py)、[跨点物理派生](../PT/预测铁水Si含量/src/si_semantic_engine/physics_neurons.py)、[21组映射](../PT/预测铁水Si含量/src/si_semantic_engine/expanded_neurons.py)、[V2训练](../PT/预测铁水Si含量/src/si_semantic_engine/train_v2.py)、[配置目录](../PT/预测铁水Si含量/configs/temporal_neuron_catalog.v2.json) | 长表输入`ts/sensor_id/value/quality`；窗口30/60/120/240分钟且禁止未来数据；当前148个规则特征唯一归入21组；±0.10仅作历史诊断；不新增API/schema/生产写入 | 16项单元测试通过；A/B两次`metrics/ablation/predictions/importance`哈希一致；21组模型测试MAE 0.0500、±0.05命中60.2%，260特征模型为0.0498/62.2% | [V2方法与限制](../PT/预测铁水Si含量/docs/experiment_method_v2.md)；本机PostgreSQL 16仍无`bf_sensor`，真实130点多窗口尚未物化；当前只允许代理离线实验，不接MCP或生产建议 |
| `Q-22012-STANDALONE-HEAT-DASHBOARD-PORT-20260726` | 在 220.12 上用独立端口运行炉次分析仪表盘、暂不与 8094 联动 | [炉次仪表盘服务](../db_dashboard/server.py)、[炉次聚合服务](../db_dashboard/heat_service.py)、[独立运行探针](../tools/remote_probe_22012_heat_dashboard.ps1)、[数据库探针](../tools/probe_22012_heat_dashboard_db.py) | 页面路由为 `/heat`；完整炉次数据依赖 220.12 本机 `bf_sensor.*` 与直连 IMES `public.t_ipes_cond` / `public.t_ipes_out_put`；8891 独立监听，8094 不依赖该服务 | 2026-07-26 远端部署后：任务 `\\BlastFurnaceServices\\StandaloneHeatDashboard8891` Running；`0.0.0.0:8891`；`/`、`/heat`、`/api/overview`、`/api/heats`、最新炉次 `/api/heat-detail` 均 HTTP 200；133 个传感器点、约 1,960.98 万分钟值、最近 3 炉返回 | 已完成独立部署；访问 `http://10.30.220.12:8891/heat`；只读、无 8094 联动；独立代码位于远端 `F:\高炉炼铁项目-real-sensor-v2_V4_8093_PREVIEW\\standalone_heat_dashboard_8891`，回滚备份由部署脚本生成 |
| `REQ-HEAT-HISTORY-MAPPING-EXPORT-20260726` | 解释炉次空值，支持按日期查炉次、查看逐炉传感器/炉况/建议，并导出可训练映射数据 | [炉次页面](../db_dashboard/heat.html)、[炉次服务](../db_dashboard/heat_service.py)、[HTTP与ZIP导出](../db_dashboard/server.py) | 默认排除开铁口晚于服务器当前时间5分钟的异常记录；日期结束值按次日零点做右开区间；传感器按窗口 `[start,end)`；炉渣按精确 `meltno`；正式铁水化验固定使用 `t_qpes_inner_batch.heatno -> t_ipes_cond.meltno` 且 `t_qpes_inner_batch.batchno -> inner_batch_insp_bb.batchno` 双键精确关联；试样号炉号/年月/炉次尾号推断仅保留为历史数据审计兼容口径，不得作为当前正式映射；烧结矿仅为开口前12小时背景，不能冒充精确入炉谱系；建议只读 | 远端实测 2026-07-25—26 返回23炉并排除1条未来异常；`2#20260726-342` 有17个核心点、24条炉况快照、建议状态 ready；2026-07-27 复核 `2#20260726-345` 双键精确铁水化验成功；完整ZIP含10个文件；既有9种 Chromium 视口无页面横向溢出，控制台错误0 | 已部署 `http://10.30.220.12:8891/heat`；ZIP包含主记录、铁水、炉渣、烧结背景、聚合特征、分钟值、诊断、建议和一炉一行建模宽表；炉料精确谱系和更长历史133点回填仍是后续数据治理项 |
| `REQ-PT-SIX-PRODUCTION-ANALYTICS-20260726` | 在PT下独立建设炉次数据集、铁水Si预测、炉况质量关联、矿焦批次、炉次传感器特征和原料背景六类分析 | [六模块索引](../PT/六类分析模块索引.md)、各模块 `analyze.py/config.json/README.md` | 统一CSV输入和审计输出；炉次主键固定 `meltno`；Si实验时间切分；传感器窗口 `[start,end)`；批次24通道不冒充成分；原料背景固定低置信度、非精确谱系 | `python -m py_compile` 六入口通过；`pytest tests/test_pt_six_analysis_modules.py --basetemp .tmp/pytest_pt_six` 为 `1 passed`，用同一组炉次、批次、传感器和烧结样本贯通六模块 | 六个文件夹已建立并可独立运行；当前为离线CSV分析边界，下一阶段可接8891炉次ZIP、Vastbase只读导出和PostgreSQL分钟值 |
| `OPS-22012-STANDALONE-HEAT-DASHBOARD-8891-DEPLOY-20260726` | 将本地炉次仪表盘代码部署到 220.12，并以 8891 独立计划任务启动 | [远端部署脚本](../tools/deploy_22012_heat_dashboard_8891.ps1)、[远端运行脚本](../tools/run_22012_heat_dashboard_8891.ps1)、[远端验收脚本](../tools/remote_verify_22012_heat_dashboard_8891.ps1)、[任务核验脚本](../tools/remote_verify_22012_heat_dashboard_task.ps1)、[本地后端测试](../tests/test_heat_service.py) | 远端任务 `\\BlastFurnaceServices\\StandaloneHeatDashboard8891`，触发器为系统启动；防火墙规则 `BlastFurnaceStandaloneHeatDashboard8891`；只读 API：`GET /api/overview`、`GET /api/heats`、`GET /api/heat-detail`；凭据文件位于 Web 根目录外并限制 ACL | 本地 `pytest tests\\test_heat_service.py tests\\test_heat_dashboard_si_distribution.py -q`：`8 passed`；远端页面/接口真实验收通过；外部请求 `http://10.30.220.12:8891/heat` HTTP 200；8094 HTTP 200 且“炉次分析”入口不存在，8093/8094/8768/8770 监听保持 | 2026-07-26 已完成；部署未改 8094 页面、8768/8770 实时桥或生产数据库；最新回滚备份为远端部署脚本输出的 `heat_dashboard_8891_20260726_172722` |
| `REQ-8094-HEAT-DASHBOARD-LINK-20260726-DISABLED` | 从 8094 页面移除“炉次分析”导航入口，保留 8094 的五个生产工作台页面以及炉次仪表盘资源的可回滚副本 | [远端定点移除脚本](../tools/remote_surgical_disable_8094_heat_dashboard_link.ps1)、[原入口资源](../高炉前端数据/assets/bf-heat-dashboard-link.js) | 8094 预览 HTML 不再加载 `bf-heat-dashboard-link.js`；不改 8890 炉次仪表盘自身、8094 问答、8768/8770 实时链路 | 2026-07-26 14:03 远端 HTML SHA-256 `B17D4CAD...16DACC4`；8094 页面 HTTP 200；页面导航只剩总览、炉况诊断、参数优化建议、趋势分析、智能问答；8093/8094/8768 监听和 8094 计划任务保持运行 | 备份目录 `F:\高炉炼铁项目-real-sensor-v2_V4_8093_PREVIEW\backups\8094_heat_dashboard_link_surgical_disable_20260726_140354`；脚本不重启服务，保留资源文件以便授权后恢复 |
| `OPS-22012-8094-ORPHAN-RECOVERY-20260726` | 恢复 220.12 上 HTTP 可连但问答无响应的 8094 独立预览代理，并保证不影响 8093、8768、8770 | [隔离重启](../tools/restart_22012_8094_preview.ps1)、[多孤儿定点恢复](../tools/recover_22012_8094_orphans.py)、计划任务 `\BlastFurnaceServices\V3AutoPreviewProxy8094` | 8094 继续使用 `BF_PROXY_PORT=8094`、`chiqiong-blast-furnace:latest` 与共享 `10.30.220.12:11434`；不改前端、数据库或 API 契约 | 清理仅属于 8094 的 PID `7828/13772/16952`，保护 8093 PID `14172`；最终 8094 PID `5560`，受管父进程 PID `15648`；最终仅保留一组 8093/8094 代理；状态接口 HTTP 200；真实 QA 30 秒无响应头，11434 直连首包/`api/ps` 仍超时 | [运维记录](22012_8093_v4_guard_ops.md#2026-07-26-8094-问答无响应与孤儿代理定点恢复)；8094 生命周期故障已修复，剩余问题定位到共享 Ollama/推理队列；未获授权前不重启 11434 |
| `REQ-HEAT-SI-DISTRIBUTION-20260726` | 将炉次 Si 从“最后一个样本”升级为全部样本点、每炉中位数和最小—最大范围，并在列表、趋势图、详情和导出中保持一致；同时防止快速切换炉次时旧详情响应覆盖新选择 | [Si统计](../db_dashboard/heat_service.py)、[炉次页面](../db_dashboard/heat.html)、[DOCX构建器](../tools/build_heat_centric_docx.py)、[后端测试](../tests/test_heat_service.py)、[前端契约测试](../tests/test_heat_dashboard_si_distribution.py) | `/api/heats`、`/api/heat-detail` 的每炉对象新增 `hot_metal_si_summary={sample_count,valid_count,min,median,max,spread}`；XLSX新增 `hot_metal_Si_latest/median/min/max/spread`，旧 `hot_metal_Si` 保留为最后样本兼容列；原始 `hot_metal_samples` 不删不平均 | 2026-07-26 pytest `8 passed`；真实 `2#20260725-329` 为 3 样、Si中位数 `0.21`、范围 `0.19—0.59`；图表加载 55 个全部样本点、24 个中位点和24组范围；Chromium 9视口、Firefox/WebKit各4代表视口、Edge `1366×768` 均无横向溢出、控制台/页面错误为0；快速点击竞态反例通过 | [问题与实现追踪](question_traceability.md#q-si-thermal-diagnosis-and-multisample-20260726)、[测试记录](test_reference.md#test-heat-si-distribution-20260726)、[运行手册](本机数据库转发与炉况汇总页面_20260725.md#5-炉次分析仪表盘与只读-api)；页面和API均只读，不新增生产写入；结果时间仍不是已确认取样时间 |
| `REQ-HEAT-CENTRIC-DASHBOARD-20260725` | 以 2# 高炉正式炉次为中心，形成五张逻辑数据表、133 点时间窗口特征、铁水/炉渣质量和烧结矿上游背景，并提供可直接访问的只读仪表盘与 DOCX 说明 | [炉次聚合服务](../db_dashboard/heat_service.py)、[8890 后端](../db_dashboard/server.py)、[炉次仪表盘](../db_dashboard/heat.html)、[DOCX 构建器](../tools/build_heat_centric_docx.py)、[纯函数测试](../tests/test_heat_service.py) | `GET /api/heats`、`GET /api/heat-detail`；逻辑表为 `heat_master`、`heat_hot_metal_chemistry`、`heat_slag_chemistry`、`heat_sensor_window_features`、`heat_alignment_audit`；窗口为 `pre_tap/tapping/inter_heat`；烧结矿只作开口前 12 小时时间背景，不冒充炉次精确谱系 | 2026-07-25 API 实读当前炉次、铁水/炉渣/烧结矿与 133 点；静压力/炉体温度/全部物理点分组为 18/80/133；Chromium 九视口无横向溢出，Edge `1366×768` 冒烟通过；DOCX ZIP、段落、表格和内嵌截图结构通过；Firefox/WebKit 未执行 | [DOCX 说明](以炉次为中心的五张核心数据表与133点时间窗口说明_20260725.docx)、[运行与对齐手册](本机数据库转发与炉况汇总页面_20260725.md)、[测试记录](test_reference.md#test-heat-centric-dashboard-20260725)；生产数据全程只读，烧结矿关联置信度固定为低，不得作为批次谱系或质量因果标签 |
| `OPS-DB-RELAY-DASHBOARD-20260725` | 启动本机到 IMES Vastbase、IMES Web、pSpace 的受控回环转发，并启动当前炉况数据库汇总页；同时固定炉次、铁水/炉渣化验与 133 点传感器的对齐口径 | [回环转发器](../tools/imes_22012_relay.py)、[炉况页启动器](../tools/start_db_dashboard_python.py)、[炉况页后端](../db_dashboard/server.py)、[铁水 Si 数据集构建器](../tools/build_hot_metal_si_dataset.py)、[出铁口/炉次审计](../tools/analyze_taphole_heat_alignment.py) | 本机只监听 `127.0.0.1:15433/18080/18889/8890`；8890 只读连接 `bf_trend`；炉次主锚点为 IMES `t_ipes_cond.meltno/opentime/closetime`，炉渣按 `meltno` 精确关联，铁水试样按已审计试样号映射，传感器窗口不得晚于出铁锚点 | 2026-07-25 三个 SSH direct-tcpip 目标探测成功，本机三端口监听；IMES Web HTTP 200；Vastbase 当前身份与两个目标化验视图 SELECT 权限通过；pSpace 243 经 18889 SDK 认证返回 0；8890 `/api/overview`、`/api/diagnosis`、`/api/summaries` 成功，Chromium `1440×900` 与 `390×844` 无横向溢出；后端语法编译通过 | [本机转发、炉况页与炉次对齐手册](本机数据库转发与炉况汇总页面_20260725.md)；本轮只读、未写生产库；炉况页数据行数改为 PostgreSQL 统计估算并以 `≈` 明示，避免对约两千万行分钟表做阻塞式精确计数 |
| `Q-IMES-SAMPLE-HEAT-RELATION-20260719` | 核实铁水试样号中 `234` 与 `002` 的层级，并确认是否关联正式炉次 | [试样号审计](../tools/audit_imes_sample_no.ps1)、[炉次对齐工具](../tools/analyze_taphole_heat_alignment.py) | 只读铁水化验 `si_sample_no/si_result_ts` 与 IMES `t_ipes_cond.meltno/opentime/closetime`；格式 `FYYMM-NNN-SSS` 中 `NNN` 对应炉次尾号，`SSS` 为炉次内试样记录序号 | 2026-07-12～18 正式炉次 89/89 找到相同试样组尾号；每炉 1/2/3/4 个匹配试样的炉次数为 9/39/32/9；当日 `22607-234-002 -> 2#20260719-234` | [问题追踪](question_traceability.md#q-imes-sample-heat-relation-20260719)、[专项报告](../reports/试样号234炉次关系_20260719.md)、[数据集口径](铁水硅炉况传感器数据集.md#31-试样号书写规则2026-07-19-实测)；结果时间不是取样时间，`002` 的现场类型仍待 `takesampletime`/取样位置/复验标志确认；只读，无生产写入 |
| `REQ-HOT-METAL-SI-DATASET-20260719` | 将当前 2# 高炉炉况、规则特征和传感器历史与 IMES 铁水 Si 标签组成可复现、无未来数据泄漏的本地数据集 | [构建器](../tools/build_hot_metal_si_dataset.py)、[离线验证器](../tools/validate_hot_metal_si_dataset.py)、[纯函数测试](../tests/test_build_hot_metal_si_dataset.py) | 只读 `bf_sensor.sensor_registry/one_minute_values/diagnosis_snapshots` 和 `public.v_qpes_inner_batch_insp_final_sample`；标签结果时间向前退让 120 分钟，炉况最大向前 15 分钟，传感器最大向前 10 分钟；无 schema/API/计划任务变化 | 单元测试 3/3；产物验证 `PASS`；5,699 样本主键唯一，4,103 条匹配炉况，严格训练版 4,090 条；未来时间、炉况间隔、传感器年龄和展示映射违规均为 0 | [数据口径与重建手册](铁水硅炉况传感器数据集.md)；[产物目录](../reports/铁水硅炉况传感器数据集_20260719)；当前 `si_result_ts` 是判定/审核时间代理，取得真实 `takesampletime/tappingtime` 后必须重建，不得标为生产金标准 |
| `Q-COHESIVE-ZONE-DATA-SOURCES-20260719` | 只读核查软熔带上升/下降趋势模型所需的 pSpace 实时量、IMES 批次/炉次/化验和冷却水/布料补充信号 | [pSpace 高度/质量核查](../tools/audit_22012_pspace_height_metadata.py)、[pSpace 文字检索](../tools/pspace_gl02_text_search.py)、[IMES 授权视图审计](../tools/audit_imes_granted_views.py)、[Vastbase 只读目录/受限导出](../tools/export_vastbase_local.py) | 不新增 API/schema；确认 L7～L13 56 点、18 个 A～F 静压力、28 个核心变量、冷却壁供回水/分区流量、溜槽角度/圈数/批重可读；IMES 命名化验视图和六个业务原表由不同只读身份分别可见 | 2026-07-19 经 220.12 实读 pSpace：80/80 炉体温度和目标点质量 `Good`，核心快照读取前缺点/错误为 0；IMES 五视图均可 `SELECT`，受限近期六表样本可读；2# `t_ipes_cond.tappingtemp` 全历史 9,373 条非空数为 0 | [逐项核查报告](软熔带数据源只读核查_20260719.md)；结论为“实时强信号可接入，冷却/布料源已存在但待对表，铁水温度与径向煤气成分仍不可用”；未改模型、数据库或生产服务 |
| `Q-IMES-WEB-ACCESS-AND-SAMPLE-NO-20260719` | 诊断 IMES Web 空响应，并核实铁水硅试样号书写规则 | [网络诊断](../tools/diagnose_imes_network.ps1)、[试样号审计](../tools/audit_imes_sample_no.ps1) | Web `10.10.181.209:8080`；Vastbase `10.10.181.195:5432`；试样号 `FYYMM-NNN-SSS` | Web TCP 成功但 Chrome `ERR_EMPTY_RESPONSE`/curl `Empty reply`；试样号 5,699/5,699 格式匹配、0 炉号错配、0 重复、14 条跨自然月边界；后续炉次对齐确认 `NNN` 为正式炉次尾号 | [问题追踪](question_traceability.md#q-imes-web-access-and-sample-no-20260719)、[炉次关系追踪](question_traceability.md#q-imes-sample-heat-relation-20260719)、[网络排障](IMES网络与Vastbase直连排障.md)、[数据集口径](铁水硅炉况传感器数据集.md#31-试样号书写规则2026-07-19-实测)；只读，无生产写入 |
| `Q-TAPHOLE-HEAT-INFERENCE-20260719` | 判断 pSpace 1/2 号出铁口温度能否推断正式炉次和开堵口时间 | [只读对齐工具](../tools/analyze_taphole_heat_alignment.py)、[专项测试](../tests/test_analyze_taphole_heat_alignment.py) | pSpace 镜像 `T_taphole_1/2`；IMES `t_ipes_cond.meltno/opentime/closetime/tappingtime` | 7 天两点各 10,080 分钟值、89 个 2# 炉次、207 个温度跳变；±15/±30/±60min 覆盖 26/49/82；53/89 温度占优信号歧义 | [问题追踪](question_traceability.md#q-taphole-heat-inference-20260719)、[7 天报告](../reports/出铁口温度炉次对齐_20260712_20260718/report.md)；结论为温度只作候选和校验，正式炉次/时间直接取 IMES；只读，无生产写入 |
| `REQ-BF3D-R2Q-INTERNAL-MATERIAL-WEB-20260719` | 将 R2P 的物理清洁审查资产升级为六材质族、物理封盖、1× 厚度和 WebP 交付的 R2Q V3 权威材质/结构审查路径 | [V3 导出器](../tools/export_bf3d_structural_review_v3.py)、[R2Q 阶段目录](../PT/高炉3D模型/work/WEB_60_20260719_R2Q_INTERNAL_MATERIAL_LOOKDEV/)、[Web 审查控制器](../高炉前端数据/assets/bf3d-structural-review.js) | 不新增生产 API/数据库；三 GLB 为主 `4,380,396`、纯材质 `993,260`、结构 `3,663,988` bytes；材质资产组 `5` 个逻辑对象、结构资产组 `10` 个逻辑对象/`20` 个主体+封盖 primitives；Web 纯材质审查用结构组近景露出内部材质；无运行时裁剪/DoubleSide/PBR 突变 | Three.js r160 `17/17`；五业务路由 `85/85`；C2 `12/12`；旧 cutaway 单浏览器 `PASS`、Firefox/WebKit `8/8 PASS`；规格、前端、Web 视觉独立复审均 `PASS` | `independent_reviews_passed_pending_ab_and_release_gates`；仅 `E/illustrative`、`REF-PENDING`、`not_for_construction`；严格 Cycles/Eevee、Three.js/Eevee 数值 A/B、现场 Edge、P50/P60/P70/QA-70 未完成；正式 GLB 与十阶段 `5/2/3` 统计不变 |
| `REQ-BF3D-CLEAN-STRUCTURAL-REVIEW-20260719` | 修正 V1 审查 GLB 依赖 Three.js 隐藏导致 Blender 直导仍显示圆环、竖向流线和传感器的问题，并把炉内层替换为可辨识 PBR 材质 | [V2 导出器](../tools/export_bf3d_structural_review_v2.py)、[复开/直导验证](../tools/verify_bf3d_structural_review_v2_blender.py)、[阶段总结](../PT/高炉3D模型/work/WEB_60_20260719_R2P_CLEAN_STRUCTURAL_REVIEW/WEB-60_R2P_阶段成果总结.md) | 不新增生产 API/数据库；输出 5 节点纯材质 GLB、10 节点物理剖面 GLB 和可直接打开 Blend；内部材质继续 `E/illustrative`、`not_for_construction=true` | Blender 5.2 复开检查 `ok=true`；两个 GLB factory-startup 直接导入 `ok=true`；清单 `all_checks_pass=true`；正式/V1 GLB SHA 均保持 | 已完成本地受控资产；V2 中传感器、圆环、流线、粒子和辅助几何均物理删除，页面运行资产和生产部署未改变 |
| `REQ-BF3D-SKILL-PACK-20260716` | 固定 Blender/MCP/渲染开源仓库版本，并把必要工作流适配为 GL02 高炉项目本地 Codex Skills | [总编排 Skill](../PT/高炉3D模型/skills/bf3d-orchestrate/SKILL.md)、[Skill 清单](../PT/高炉3D模型/skills/bundle-manifest.json)、[上游与本地源锁](../PT/高炉3D模型/skills/sources.lock.json)、[校验程序](../PT/高炉3D模型/validate_skill_pack.py) | 不新增生产 API/数据库；合同固定 115 个 `SENSOR_`、80 个炉体温度点、L7～L16、五个工艺段、坐标/extras、PBR 通道与 Three.js 交付门禁 | `python -B PT/高炉3D模型/validate_skill_pack.py`；逐 Skill `quick_validate.py`；可选用锁定仓库路径验证 HEAD/文件 SHA | [总设计详细规划](../PT/高炉3D模型/总设计详细规划.md)；2026-07-16 已完成 7 个 Skill、6 仓库 commit/tree、选定文件和 PythonCAD/GLB SHA 锁；尚未安装 MCP 或修改正式模型 |
| `REQ-BF3D-P35-P40-LAYERS-20260717` | 在不覆盖正式 GLB 的前提下提高炉体工业质感，并将 L7～L16 制作为可独立控制的十层 | [P35 批准文件](../PT/高炉3D模型/work/P35_DETAIL_GEOMETRY_20260717_135927/P35_DETAIL_GEOMETRY_APPROVED.blend)、[P36 批准文件](../PT/高炉3D模型/work/P36_LAYER_SEGMENTATION_20260717_P35_INTEGRATED/P36_LAYER_SEGMENTATION_APPROVED.blend)、[P40 批准文件](../PT/高炉3D模型/work/P40_FIXED_LOOKDEV_20260717_P36_FINAL/P40_LOOKDEV_APPROVED.blend) | P36 固定 L7～L16 共 10 个独立网格和 10 个独立材质；每层关联 A～H 8 点；115 个传感器、80 个炉体温度点不变 | 三阶段候选报告与独立视觉复核；检查点路径见 [3D 模型构建显示说明](../PT/3D模型构建显示.md#116-2026-07-17-十层运行时与-p50-法线修复追踪) | P35、P36、P40 已批准；P50/P60/P70 未批准；正式 `gl02_blast_furnace.glb` SHA-256 仍为 `808960f1...b62af6`，未覆盖 |
| `REQ-BF3D-THREE-RUNTIME-20260717` | 在 Three.js 查看器中为 L7～L16 提供单层八点筛选、动态高亮、状态色、哑光材质和资源复用 | [页面实现](../高炉前端数据/frontend_dashboard_v3.server.html)、[专项验证](../tools/verify_gl02_layered_model_ui.py) | 高亮状态包含层号、动画阶段、状态色、渲染质量和可见点数；支持进入膨胀、回弹、呼吸、切层淡出、同层幂等、清除高亮；状态色为正常/关注/严重/无数据 | `python -m py_compile tools/verify_gl02_layered_model_ui.py`；Edge `1366×768` 使用静态页面和 `--allow-offline-data-source` 通过 L7～L16、材质、动画及 100 次切层资源稳定断言 | 页面专项已通过，但该次为静态数据源；8767、数据库及生产实时状态色尚未验证，不能标记为生产实时链路完成 |
| `REQ-BF3D-CUTAWAY-20260717` | 默认去除旧圆环、竖线和装饰性流场对外观与剖面的干扰，同时提供可播放、暂停和复位的内切面工艺动画 | [页面实现](../高炉前端数据/frontend_dashboard_v3.server.html)、[权威炉内运行时](../高炉前端数据/assets/bf3d-internal-simulation.js)、[运行时验证](../tools/verify_gl02_cutaway_runtime.cjs) | 兼容 GLB 中旧 45 个内部工艺对象在外观和内切面均始终隐藏；内切面只负责炉壳裁剪、相机、遮挡与补光，料面、上料、软熔带、风口喷煤、静压力及炉缸状态由唯一 `BF3D_INTERNAL_SIMULATION_RUNTIME` 和统一证据门管理；API 为 `setCutawayMode/playCutaway/pauseCutaway/resetCutaway/getCutawayState`，DOM 状态为 `data-cutaway-*` 与 `data-internal-*`；路由卸载时停止旧 RAF 并释放资源，返回总览重新挂载 | 正式 GLB 与 P60 4K 隔离候选运行均 `ok=true`：旧 45 对象可识别但可见数恒为 0，内切面显示权威 simulation 根，L7～L16 每层八点、20 次切换资源稳定、OrbitControls 复位及“总览→诊断→总览”生命周期通过；意外错误为 0；Chromium 九视口 9/9，[Firefox/WebKit 代表视口](../logs/bf3d_cutaway_cross_engine_20260717/report.md) 8/8 | 功能已进入页面；外观炉壳保持不透明哑光并优先保留 GLB PBR 通道。现场 Edge、性能和实时数据链路仍按正式门禁补齐，不构成 P70 批准 |
| `REQ-BF3D-DATA-DRIVEN-INTERNAL-ANIMATION-20260717` | 将已认可的语义内切面与混合数字孪生 B/C 方向固化为可执行设计，并盘点料线、18 点静压力、上料、炉次、生产实绩、铁水和炉渣化验 | [主规格](../PT/高炉3D模型/高炉内部数据驱动3D动画总设计.md)、[总规划摘要](../PT/高炉3D模型/总设计详细规划.md#19-数据驱动炉内动画运行合同)、[数据审计记录](../PT/3D模型构建显示.md#1112-2026-07-17-新数据源盘点与炉内-bc-动画设计) | 规划 `bf3d_snapshot.v1`、`bf3d_event.v1`，区分 measured/interpolated/estimated/simulated/illustrative/stale/no-data；保留 event/sample/judged/published/ingested/render/knowledge 七类时间；固定 C1/C2/C3 边界 | 原始阶段为只读数据与现有实现审计；2026-07-19 已另按 `REQ-BF3D-C2-ROOT-MOTION-20260719` 实施第一版根部状态估计和快照链路 | 设计已固化；C2 根部低置信度基线已部分落地，MES 上料/开堵口、完整 C1 事件适配、经真值标定 C2、C3、`bf_twin` 表和生产资产仍未实施；`L_south/L_north`、上料时间、炉次—料批和炉次—化验关联仍须先核对 |
| `REQ-BF3D-C2-ROOT-MOTION-20260719` | 先实现软熔带炉墙侧根部上移/下移、厚度和偏心的实用低置信度预测，并接入 8767 与 Three.js | [实现记录](../PT/软熔带移动预测趋势.md)、[估计器](../炉况规则引擎/features/cohesive_zone_estimator.py)、[YAML 参数](../炉况规则引擎/config/cohesive_zone_estimator.yaml)、[8767 适配](../自动诊断服务/local_pg_ws_bridge.py)、[Three.js 运行时](../高炉前端数据/assets/bf3d-internal-simulation.js)、[页面快照发布](../高炉前端数据/frontend_dashboard_v3.server.html) | 输入为 L7～L13 炉体温度、压差/透气性、18 静压力及热状态辅助量；输出 `bf3d_snapshot.v1.estimated.cohesive_zone`，包含根部标高、`up/down/stable`、速度、15 分钟常速外推、厚度、相对 A 点偏心、八扇区根部、置信度和误差带；固定 `estimated/uncalibrated/control_use=prohibited/confidence<=0.45`，8767 和前端各自执行独立合同门 | 后端两份 pytest 联跑 `34 passed`；Three.js 专项 `ok=true`，含越权快照拒绝反例；C2 三引擎代表视口 12/12；全站跨引擎/视口矩阵 17 个运行、85 个页面组合全部通过，覆盖未来数据隔离、陈旧热力驱动忽略、缺失/陈旧降级、方向、厚度、偏心、外推、缓存、真实公共 API 桥接和前端生命周期 | 代码链路已实施；本机 PostgreSQL 16 实际监听 18000 但当前 `bf_trend` 缺少 `bf_sensor`，220.12 直连本轮超时，所以未宣称完成当前现场在线值验收。绝对方位、根部真值和 C2 标定仍是发布门禁 |
| `REQ-BF3D-INTERNAL-SIM-SURFACE-MODELING-20260718` | 将高炉内部真实结构/工艺仿真和外炉壳细颗粒质感固化为完整、分阶段、可回滚的建模方案 | [专项主规格](../PT/高炉3D模型/高炉内部仿真与外部细颗粒建模总方案.md)、[总规划入口](../PT/高炉3D模型/总设计详细规划.md#20-炉内仿真与外部细颗粒建模专项总方案)、[构建记录](../PT/3D模型构建显示.md#1113-2026-07-18-炉内仿真与外部细颗粒建模专项计划)、[动画规格入口](../PT/高炉3D模型/高炉内部数据驱动3D动画总设计.md#17-几何仿真资产与细颗粒材质专项入口) | 设计 `INT_STRUCTURE/INT_MEASURED/INT_ESTIMATED/INT_SIMULATED/EXTERIOR_SURFACE` 场景层；保护 115 点、L7～L16 与坐标；定义 C1/C2/C3 轻量场景 manifest、Structural/Detail Normal、RNM、距离衰减、PMREM、LOD 和 Three.js 可观察状态 | 文档级校验：标题/阶段/停止线、四份 PT 文档互链、自动化和问题追踪；本轮未执行 Blender、CFD/DEM、GLB、页面或浏览器测试 | 设计已固化；下一实际阶段为 `BASE-00 → SURF-10 + INT-10`。P50=`not_granted`、P60=`not_granted_preflight_only`、P70 未批准，正式 GLB、生产库和生产部署均未改变 |
| `REQ-BF3D-VISUAL-BIBLE-001` | 将高炉视觉规范从原则性框架补齐为可追踪的受控基线，包含视觉参考、已填材质卡、固定 LookDev/相机、GL02 数据映射和当前实现合规矩阵 | [Visual Bible v1.1](../PT/高炉3D模型/工业级高炉数字孪生视觉规范（Visual%20Bible）.md)、[视觉参考图板](../PT/高炉3D模型/docs/视觉参考图板.md)、[材质卡册](../PT/高炉3D模型/docs/材质卡册.md)、[LookDev/相机预设](../PT/高炉3D模型/web/presets/lookdev_camera_v1.json)、[Golden Views](../PT/高炉3D模型/validation/golden-images/golden_views_v1.json)、[合规矩阵](../PT/高炉3D模型/validation/Visual_Bible当前实现合规矩阵.md) | 稳定编号采用 `VB-GOV/REF/GEO/MAT/LOOK/INT/DATA/RUNTIME/QA-*`；数据附件固定 `evidence/derivation/quality`、七类时间和允许/禁止映射；合规状态仅允许 `compliant/partial/noncompliant/blocked/not_applicable` | `python -B PT/高炉3D模型/validate_visual_bible_bundle.py`；JSON 解析、相对链接、FOV 语义、受控附件、批准边界和必需编号全部通过 | 规范 v1.1 生效不等于资产批准；P40 维持既有批准，P50=`KEEP_P50_PENDING_NOT_APPROVED`，P60=`not_granted_preflight_only`；CC0 HDRI 已登记为候选但 PMREM/视觉批准未完成，GL02 现场材质参考和未接入运行时能力继续标为 blocked/partial |
| `REQ-BF3D-10STAGE-EXECUTION-20260718` | 按 BASE-00、SURF-10、INT-10、SURF-20、INT-20、INT-30、INT-40、INT-50、WEB-60、QA-70 十阶段，用多个制作与只读审查智能体实际执行高炉3D升级 | [多智能体执行台账](../PT/高炉3D模型/十阶段多智能体执行台账.md)、[实施总方案](../PT/高炉3D模型/高炉内部仿真与外部细颗粒建模总方案.md#17-分阶段实施与批准点)、[Visual Bible](../PT/高炉3D模型/工业级高炉数字孪生视觉规范（Visual%20Bible）.md)、[INT-30 R1B_R2 总结](../PT/高炉3D模型/work/INT_30_20260718_R1B_R2/INT-30_R1B_R2_阶段成果总结.md)、[R2A 料线门禁](../PT/高炉3D模型/work/INT_30_20260718_R2A_DATA_AUDIT/INT-30_R2A_料线数据门禁阶段成果总结.md)、[R2C中尺度恢复](../PT/高炉3D模型/work/INT_30_20260718_R2C_R1_MESO_DETAIL_MERGE/INT-30_R2C_R1_MESO_DETAIL_MERGE_阶段成果总结.md)、[R2D公平渲染等价](../PT/高炉3D模型/work/INT_30_20260718_R2D_R1_RENDER_PARITY/INT-30_R2D_R1_RENDER_PARITY_阶段成果总结.md) | 每阶段独立目录、单一质量变量、机器报告、固定机位证据、阶段成果总结和审批结论；制作智能体不得自批；115点、L7～L16、五段炉体和正式GLB不可破坏；剖切钢壳/冷却壁/炉衬必须为闭合实体、内外表面与可靠封口，禁止零厚度纸片；料线缺失不得补零或在语义未确认时驱动几何 | R2A 确认料线零点/正方向/范围/南北语义未闭环；R2C 只恢复既有焊缝和加强环可见性，几何/材质/18压力/12实体/115/80/L7-L16/正式GLB保护通过；只读审计定位旧A/B源/候选 World Background 环境辐射相差约8～17倍。R2D 以全新同一 World、AgX、曝光0.24、EEVEE96、同四灯/相机/可见性重做四层三视角，源与候选像素 `mean_diff=0/max_diff=0`，视觉/规格双审批准 R1 渲染等价 | INT-30 R1A=`approved_fixture_only`；R1B_R2=`approved_visual_correction_only`；R2A=`blocked_no_geometry_drive`；R2C=`approved_r1_surface_and_meso_visibility_blender_candidate_only`；R2D=`approved_r1_render_parity_evidence_only`；剖切厚度图仍偏暗，下一小阶段只修视觉证据，正式GLB仍未替换 |
| `REQ-BF3D-R1-SURFACE-LOCK-20260718` | 保留用户选择的 R1 细密粗糙读感，防止后续灯光、内部结构或 Web 交付将炉壳重新变平滑 | [Visual Bible 决策 `VB-DEC-MAT-001`](../PT/高炉3D模型/工业级高炉数字孪生视觉规范（Visual%20Bible）.md#461-gl02-当前-r1-粗糙读感锁vb-dec-mat-001)、[材质卡](../PT/高炉3D模型/docs/材质卡册.md#2-mat-steel-paint-001-老化喷漆钢壳)、[R1/R4/R5 对比](../PT/高炉3D模型/work/SURF_20_20260718_R5/renders/SURF20_R5_10_R1_R4_R5_GRAZING_COMPARISON.png)、[SURF-20 R5 总结](../PT/高炉3D模型/work/SURF_20_20260718_R5/SURF-20_R5_阶段成果总结.md)、[R2H Web 对照](../PT/高炉3D模型/work/INT_30_20260718_R2H_WEB_DETAIL_NORMAL/evidence/INT30_R2H_R1_WEB_ACCEPTANCE_CONTACT_SHEET.png) | 受控承载资产为 `SURF-20 R5`，固定 `B=0.16 / D=0.10m / N=0.45 / metallic=0.06 / roughness=0.56–0.82 / shared mapping=0.085`；“R1”只指微表面强度，不恢复早期 R1 的高金属身份 | SURF-20 R5 机器断言 31/31、复开 9/9、视觉/规格双审；INT-30 R2D 固定条件下源/候选像素 `mean_diff=0/max_diff=0`；R2H 保留 base `normalScale=0.45` 并以 RNM Detail Normal 完成 Chromium `64/64`、三引擎、100 次资源稳定及独立双审 | Blender 炉壳材质与 R2H 隔离网页候选已分别通过对应门禁；正式 8092 集成、生产 GLB 替换、现场 Edge、Khronos Validator 和整页性能仍未批准，未经用户重新选择不得改变 R1 |
| `TEST-BF3D-INT30-R2E-CUTAWAY-CONTRAST-20260718` | 在不改变模型和 R1 炉壳材质的前提下，解决钢壳/冷却结构/耐火层/工艺空间剖切证据过暗和层间难辨问题 | [阶段总结](../PT/高炉3D模型/work/INT_30_20260718_R2E_CUTAWAY_CONTRAST/INT-30_R2E_CUTAWAY_CONTRAST_阶段成果总结.md)、[机器报告](../PT/高炉3D模型/work/INT_30_20260718_R2E_CUTAWAY_CONTRAST/int30_r2e_machine_report.json)、[物理材质与假色并排](../PT/高炉3D模型/work/INT_30_20260718_R2E_CUTAWAY_CONTRAST/renders/INT30_R2E_05_PHYSICAL_VS_FALSE_COLOR.png)、[R2D/R2E 对照](../PT/高炉3D模型/work/INT_30_20260718_R2E_CUTAWAY_CONTRAST/renders/INT30_R2E_06_R2D_DARK_VS_R2E_LOOKDEV.png) | 仅在渲染进程中显示四个闭合 QUARTER、隐藏八个 FULL/HALF，使用暖灰 LookDev；假色临时覆盖并恢复，不保存 Blend；固定 `VB-DEC-MAT-001` R1 参数 | 四层闭合/正体积/非流形0；输入 R2C、R1、18压力、115/80、L7-L16 和正式 GLB 不变；元数据返工后 Artifact `14/14`、机器/视觉图片记录 `12/12`；六图逐图视觉 `approve`，规格复审 `approve` | `approved_cutaway_contrast_evidence_only`；只批准 E/illustrative 结构辨色证据，不代表实测厚度，不解除料线数据门，不批准 GLB/Three.js/生产替换 |
| `REQ-BF3D-INT30-R2F-LAYER-OVERLAY-RUNTIME-READY-20260718` | 在用户锁定 R1 粗糙表面的当前 INT-30 分支中恢复并固化 L7～L16 十层可点击诊断覆盖对象，避免重复建模或真实切割炉壳 | [阶段总结](../PT/高炉3D模型/work/INT_30_20260718_R2F_LAYER_OVERLAY_RUNTIME_READY/INT-30_R2F_LAYER_OVERLAY_RUNTIME_READY_阶段成果总结.md)、[机器报告](../PT/高炉3D模型/work/INT_30_20260718_R2F_LAYER_OVERLAY_RUNTIME_READY/int30_r2f_machine_report.json)、[单层选择矩阵](../PT/高炉3D模型/work/INT_30_20260718_R2F_LAYER_OVERLAY_RUNTIME_READY/renders/INT30_R2F_07_SELECTED_LAYER_MATRIX.png)、[十层/R1并排](../PT/高炉3D模型/work/INT_30_20260718_R2F_LAYER_OVERLAY_RUNTIME_READY/renders/INT30_R2F_08_STACKED_AND_R1_LOCK.png)、[总控批准](../PT/高炉3D模型/work/INT_30_20260718_R2F_LAYER_OVERLAY_RUNTIME_READY/R2F_CONTROLLER_APPROVAL.json) | 直接复用 R2C 中与 P36 候选逐层几何/矩阵/材质同 hash 的 `APPROX_GL02_TEMP_LAYER_BAND_L7..L16`；只加 `embedded` runtime metadata；默认隐藏、选中层单显；不复制网格、不切五段炉壳、不导出 GLB；保持 `VB-DEC-MAT-001` | 115/80、L7～L16每层8点、18压力、12 INT20、五段炉体、R1节点图 `6bf8bd...`、正式GLB `808960...` 全部保持；无重复 band；8 图独立视觉 `approve`，只读规范交叉审计 `approve` | `approved_embedded_layer_overlay_blender_candidate_only`；L16上部偏暗为不阻塞备注；仍不批准物理分层/实测厚度、GLB导出、Three.js embedded source、跨浏览器或生产替换；R2A料线门禁继续 blocked |
| `TEST-BF3D-INT30-R2G-ISOLATED-WEB-20260718` | 把 R2F 的十层对象和 R1/R5 外观导出为隔离 GLB，并验证 L7～L16 单层八点的浏览器运行合同 | [阶段总结](../PT/高炉3D模型/work/INT_30_20260718_R2G_ISOLATED_GLB_WEB_PREVIEW/INT-30_R2G_ISOLATED_GLB_WEB_PREVIEW_阶段成果总结.md)、[运行时报告](../PT/高炉3D模型/work/INT_30_20260718_R2G_ISOLATED_GLB_WEB_PREVIEW/web_preview/runtime_evidence/R2G_WEB_PREVIEW_RUNTIME_CHECK.json)、[材质近景](../PT/高炉3D模型/work/INT_30_20260718_R2G_ISOLATED_GLB_WEB_PREVIEW/web_preview/runtime_evidence/R2G_L10_detail_1440x900.png) | `normalTexture.scale=0.45`；runtime adapter gain=`1.55` 仅补偿 NormalGL 合成；十层 band 默认隐藏、单层单显，每层 A～H 八点；正式 GLB 只读保护 | 结构门禁通过；Chromium `1440×900` 运行时 `41/41`、错误 `0`；115/80/18/12/五段、十层均保持；候选 final/stable SHA=`9db82c83...f952`，正式 GLB SHA=`808960f1...b62af6` 未变 | `candidate_ready_for_review`；Web 近景仍比 Blender R1 源材质偏平，停止盲目增益；缺 Khronos Validator 与 Firefox/WebKit/Edge，禁止生产替换 |
| `TEST-BF3D-INT30-R2H-WEB-DETAIL-NORMAL-20260718` | 保留用户选择的 R1 粗糙读感，在隔离 Three.js 预览中补足 R2G 近景微颗粒，同时保持 L7～L16 单层八点合同和生产资产边界 | [阶段总结](../PT/高炉3D模型/work/INT_30_20260718_R2H_WEB_DETAIL_NORMAL/INT-30_R2H_WEB_DETAIL_NORMAL_阶段成果总结.md)、[控制器批准](../PT/高炉3D模型/work/INT_30_20260718_R2H_WEB_DETAIL_NORMAL/R2H_CONTROLLER_APPROVAL.json)、[静态报告](../PT/高炉3D模型/work/INT_30_20260718_R2H_WEB_DETAIL_NORMAL/reports/R2H_WEB_PREVIEW_STATIC_CHECK.json)、[运行时报告](../PT/高炉3D模型/work/INT_30_20260718_R2H_WEB_DETAIL_NORMAL/web_preview/runtime_evidence/R2H_WEB_DETAIL_NORMAL_RUNTIME_CHECK.json)、[三引擎报告](../PT/高炉3D模型/work/INT_30_20260718_R2H_WEB_DETAIL_NORMAL/web_preview/runtime_evidence/R2H_CROSS_ENGINE_SMOKE.json)、[R1/Web 对照](../PT/高炉3D模型/work/INT_30_20260718_R2H_WEB_DETAIL_NORMAL/evidence/INT30_R2H_R1_WEB_ACCEPTANCE_CONTACT_SHEET.png) | 保留基础 `NormalGL` 与 `normalScale=0.45`；仅五段精确炉壳克隆材质并共享一张 1K OpenGL +Y Detail Normal；`onBeforeCompile` RNM；近距权重 `0.85`，`3–20m` 平滑衰减，`20m` 关闭；材质检查相机只临时隐藏遮挡网格 | Chromium `64/64`；L7～L16 每层 `1 band + 8点`；100 次切换后材质/贴图/Shader 无增长；Chromium/Firefox/WebKit `1440×900` 全通过，控制台/页面/网络错误 `0`；视觉与规格独立双审均 `APPROVE`；正式 GLB SHA=`808960f1...b62af6` 未变 | `approved_isolated_web_detail_normal_candidate_only`；只批准隔离预览候选，不等于 8092 正式页面集成或生产 GLB 替换；料线数据门、实测厚度声明、Khronos Validator 和现场 Edge 仍按后续阶段门禁处理 |
| `TEST-BF3D-INT30-R2I-SHELL-ENTITY-THICKNESS-PROBE-20260719` | 在用户再次确认保留 R1 粗糙质感后，制作炉腰 BELLY 单段 55mm 实体厚度样件，验证内切面不能用零厚度纸片替代实体炉壳 | [阶段总结](../PT/高炉3D模型/work/INT_30_20260719_R2I_SHELL_ENTITY_THICKNESS_PROBE/INT-30_R2I_SHELL_ENTITY_THICKNESS_PROBE_阶段成果总结.md)、[总控批准](../PT/高炉3D模型/work/INT_30_20260719_R2I_SHELL_ENTITY_THICKNESS_PROBE/R2I_CONTROLLER_APPROVAL.json)、[机器报告](../PT/高炉3D模型/work/INT_30_20260719_R2I_SHELL_ENTITY_THICKNESS_PROBE/reports/int30_r2i_machine_report.json)、[复开验证](../PT/高炉3D模型/work/INT_30_20260719_R2I_SHELL_ENTITY_THICKNESS_PROBE/reports/reopen_validation.json)、[R3 总览图](../PT/高炉3D模型/work/INT_30_20260719_R2I_SHELL_ENTITY_THICKNESS_PROBE/renders/INT30_R2I_R3_05_CONTACT_SHEET_ANNOTATED.png) | 样件对象 `R2I_APPROX_GL02_FURNACE_BELLY_SOLID_55MM_ENTITY_PROBE`；外表面使用 `VB-DEC-MAT-001` R1 粗糙材质，内表面使用蓝灰钢，切口/封口使用琥珀证据材质；厚度 `55mm`、等级 `E/illustrative`；5倍图只作解释，真实保存几何仍为 55mm | 体积 `1.959154m³`、`boundary_edges=0`、`non_manifold_edges=0`、正体积；factory-startup 复开直接计数 18 压力对象；115/80、L7～L16 每层8点、12 个 INT20、五原壳和正式 GLB SHA=`808960f1...b62af6` 保持；30 项最终资产哈希与字节数匹配；R1/R2 视觉证据归档 rejected，R3 视觉与规格独立双审均 `APPROVE` | `approved_belly_single_segment_entity_probe_only`；只批准 BELLY 单段厚度方法样件，不等于五段炉壳全部实体化、不等于实测厚度、不批准 GLB/Three.js/8092/生产替换；2026-07-19 用户复确认 R1 粗糙读感为后续硬锁 |
| `TEST-BF3D-INT30-R2J-FIVE-ZONE-SHELL-ENTITY-20260719` | 在 R1 粗糙表面硬锁下，把 R2I 单段方法推广为炉缸、炉腹、炉腰、炉身、炉喉五区实体候选，并保留 L7～L16 诊断覆盖 | [阶段总结](../PT/高炉3D模型/work/INT_30_20260719_R2J_FIVE_ZONE_SHELL_ENTITY_ROLLOUT/INT-30_R2J_FIVE_ZONE_SHELL_ENTITY_ROLLOUT_阶段成果总结.md)、[总控批准](../PT/高炉3D模型/work/INT_30_20260719_R2J_FIVE_ZONE_SHELL_ENTITY_ROLLOUT/R2J_CONTROLLER_APPROVAL.json)、[机器报告](../PT/高炉3D模型/work/INT_30_20260719_R2J_FIVE_ZONE_SHELL_ENTITY_ROLLOUT/reports/int30_r2j_machine_report.json)、[复开验证](../PT/高炉3D模型/work/INT_30_20260719_R2J_FIVE_ZONE_SHELL_ENTITY_ROLLOUT/reports/reopen_validation.json)、[R6 总证据](../PT/高炉3D模型/work/INT_30_20260719_R2J_FIVE_ZONE_SHELL_ENTITY_ROLLOUT/renders/INT30_R2J_R6_07_CONTACT_SHEET_FINAL.png) | 五区厚度 `65/55/55/45/45mm`、均为 `E/illustrative`、同局部 Z 径向向内；保存互斥 `SOURCE_PARITY / ASSEMBLY / SOLO`；BOSH、SHAFT 分别独占 10mm 内肩；外表面继续使用 `VB-DEC-MAT-001` R1，透明测温 band 只作诊断解释 | machine/reopen joined volume 均 `35.802733065596335m³`、delta 0、`boundary=0/non-manifold=0/face_flip_count=0`；115/80/18、L7～L16 各8、10 bands、12 INT20、无5×对象和`.blend1`；当前报告坏厚度字段命中0；Artifact/Hash `20/20`、mismatch 0；视觉/规范独立复审 `PASS` | `approved_five_zone_shell_entity_blender_candidate_only`；只批准 Blender 候选及证据包，不批准实测厚度、GLB导出/替换、Three.js/8092、浏览器或生产集成；正式 GLB SHA 仍为 `808960f1...b62af6` |
| `TEST-BF3D-P50-4K-ROTATION-20260717` | 固定全炉 4K 哑光微粗糙 PBR 母版，并以整圈旋转证据排查背缝、盐粒、方向翻转和静态摩尔纹 | [4K 机器报告](../PT/高炉3D模型/work/P50_MASTER_4K_20260717_R1/p50_full_furnace_bake_candidate.json)、[24 帧联系表](../PT/高炉3D模型/work/P50_MASTER_4K_20260717_R1/review/P50_ROTATION_CONTACT_SHEET_24.png)、[旋转指标](../PT/高炉3D模型/work/P50_MASTER_4K_20260717_R1/review/p50_rotation_contact_sheet_metrics.json)、[人工观察](../PT/高炉3D模型/work/P50_MASTER_4K_20260717_R1/review/p50_master_4k_manual_observations.json) | BaseColor、Roughness、Metallic、NormalGL、AO、ORM 为 4K；运行时优先保留已烘焙 PBR 通道，炉壳外观 `OPAQUE/alpha=1` | 41/41 机器断言；24 帧旋转审查未发现明显背缝、盐粒噪点、UV 方向翻转或静态摩尔纹 | P50 仍为 `not_granted`；这些结果是完整候选证据，不得命名为 `P50_BAKE_APPROVED`，正式生产 GLB 未覆盖 |
| `TEST-BF3D-P60-PREFLIGHT-20260717` | 在不覆盖生产资产的前提下导出 4K 未压缩 GLB，验证 PBR 嵌入与模型合同 | [P60 隔离 GLB](../PT/高炉3D模型/work/P60_PREFLIGHT_4K_20260717_R1/P60_PREFLIGHT_4K_UNCOMPRESSED.glb)、[预检报告](../PT/高炉3D模型/work/P60_PREFLIGHT_4K_20260717_R1/p60_preflight_report.json)、[manifest](../PT/高炉3D模型/work/P60_PREFLIGHT_4K_20260717_R1/p60_preflight_manifest.json)、[Validator 状态](../PT/高炉3D模型/work/P60_PREFLIGHT_4K_20260717_R1/gltf_validator_status.json) | `OPAQUE`、BaseColor alpha=1；嵌入 BaseColor/Normal/ORM；保留 115 个传感器、80 个炉体温度点、L7～L16 十层和 45 个内部工艺示意对象 | 20/20 内部检查与 Blender 回读通过；无外部 URI、无 Draco/Meshopt 依赖 | 本机 Khronos glTF Validator 不可用，状态为 `not_granted_preflight_only`；不能写成 `GLTF_APPROVED`，正式生产 GLB 未覆盖 |
| `REQ-BF3D-PROCESS-DOCX-20260717` | 重载 P60 4K 隔离预览，并把本轮全部过程图片、制作步骤、批准边界和浏览器证据归档为可编辑 Word | [DOCX 生成器](../tools/build_bf3d_process_docx.py)、[Word 分页验证器](../tools/verify_bf3d_process_docx_render.py)、[8094 隔离预览启动器](../tools/serve_bf3d_preview.py)、[完整 Word](../PT/高炉3D模型/高炉3D模型制作过程与内切面验收记录_20260717.docx)、[图片清单](../PT/高炉3D模型/高炉3D模型制作过程图片清单_20260717.csv) | 递归范围固定为 P35/P36/P40/P50/P60 阶段目录和三组 `bf3d_*_20260717` QA 目录；共 308 图，正文保留 P50=`not_granted`、P60=`not_granted_preflight_only`、生产 GLB 未替换；8094 只在请求路由层映射 P60 候选 | 生成器检查 308/308、唯一 SHA 266、附录编号 308/308、DOCX ZIP 完整；Word 只读重分页并导出临时 PDF 为 70 页，抽查 1/2/12/30/50/70 页通过 | [生成报告](../PT/高炉3D模型/高炉3D模型制作过程文档生成报告_20260717.json)；正式 GLB SHA-256 仍为 `808960f1...b62af6`，未覆盖 |
| `BUG-BF3D-P50-FLAT-NORMAL-20260717` | 阻止平坦 8 位 NormalGL 通过 P50，并修复微凹凸量化丢失 | [P50 烘焙脚本](../PT/高炉3D模型/skills/bf3d-uv-bake/scripts/p50_full_furnace_bake_candidate.py)、[1K 独立复核](../PT/高炉3D模型/work/P50_FULL_FURNACE_BAKE_1024_20260717_153648_R2/p50_1k_visual_review.json)、[256px 修复冒烟复核](../PT/高炉3D模型/work/P50_FULL_FURNACE_BAKE_20260717_NORMAL_FIX_SMOKE256_R2/p50_normal_fix_smoke_review.json) | 旧 1K 候选为 `ITERATE`：NormalGL 平坦、图集有效占比 `21.743%`、缺背缝证据；修复采用 `4×` 烘焙编码和 `0.25` 运行时强度，并新增 `normal_contains_quantization_safe_microdetail` 门禁 | 256px R2 为 `26/26`，重复纹理哈希一致，115 点与 L7～L16 不变；复现入口为 `python PT/高炉3D模型/run_p50_full_furnace_bake_candidate.py --output-dir PT/高炉3D模型/work/P50_NORMAL_FIX_SMOKE256_REPRO --texture-size 256 --margin 4 --samples 8 --skip-render` | 仅批准法线修复 smoke；后续三列 1K 已补做图集占比、背缝和边界证据，但局部接触 AO、旋转 shimmer、P60/P70 与生产 GLB 替换均未批准 |
| `TEST-BF3D-LAYER-MATRIX-20260717` | 验证 L7～L16 十层交互在项目规定视口及三种浏览器引擎中的静态兼容性 | [专项脚本](../tools/verify_gl02_layered_model_ui.py)、[Chromium manifest](../logs/bf3d_layer_matrix_20260717/manifest.json)、[Firefox/WebKit manifest](../logs/bf3d_layer_cross_engine_20260717/manifest.json) | 静态模型仍为 115 点、80 个炉体温度点、L7～L16 十层且每层 A～H 八点；仅允许把 8767 与静态服务器 `/api/*` 失败记为 expected offline | Chromium 9/9；Firefox 4/4、WebKit 4/4，合计 8/8；另有 Edge `1366×768` 专项通过 | 三组结果均为静态数据源；8767 WebSocket、数据库和生产实时状态色未验证，不构成 P70 或实时链路批准 |
| `BUG-BF3D-P50-METALLIC-SHIMMER-20260717` | 降低三列 1K 候选的 Metallic 近二值盐粒和局部突刺，同时保留非平坦 Normal 与模型合同 | [三列 1K R1 报告](../PT/高炉3D模型/work/P50_FULL_FURNACE_BAKE_1024_3COL_20260717_R1/p50_full_furnace_bake_candidate.json)、[R1 独立复核](../PT/高炉3D模型/work/P50_FULL_FURNACE_BAKE_1024_3COL_20260717_R1/p50_3col_visual_review.json)、[Metallic R2 报告](../PT/高炉3D模型/work/P50_FULL_FURNACE_BAKE_1024_METALLIC_FIX_20260717_R2/p50_full_furnace_bake_candidate.json)、[八机位证据](../PT/高炉3D模型/work/P50_FULL_FURNACE_BAKE_1024_METALLIC_FIX_20260717_R2/review/p50_multiview_review_evidence.json) | R1 为 32/32、图集 `57.297%`、`25.580 texel/m`、Normal 非平坦且仅 `APPROVE_SMOKE`；R2 为 35/35，Metallic 近二值比例 `79.87%→0.043%`，相邻差 P95 `0.0667`、大跳变和局部脉冲均为 `0` | [R1/R2 同机位量化](../PT/高炉3D模型/work/P50_FULL_FURNACE_BAKE_1024_METALLIC_FIX_20260717_R2/review/p50_r1_r2_boundary_metrics.json)；后续 4K 24 帧旋转结果见 `TEST-BF3D-P50-4K-ROTATION-20260717` | R2 是历史中间证据；4K 旋转审查已未见明显接缝/噪点，但 P50 仍为 `not_granted`，P60 也仅完成内部预检，P70 未批准 |
| `TEST-BF3D-P50-LOCAL-AO-R3-20260717` | 只烘焙与炉壳紧邻构件的局部接触 AO，避免平台、塔架、内部结构和诊断覆盖层造成大面积脏黑 | [R3 候选报告](../PT/高炉3D模型/work/P50_LOCAL_CONTACT_AO_1K_20260717_1702_R3/p50_full_furnace_bake_candidate.json)、[八视角证据](../PT/高炉3D模型/work/P50_LOCAL_CONTACT_AO_1K_20260717_1702_R3/review/p50_multiview_review_evidence.json)、[人工观察](../PT/高炉3D模型/work/P50_LOCAL_CONTACT_AO_1K_20260717_1702_R3/review/p50_multiview_manual_observations.json)、[R2/R3 比较脚本](../PT/高炉3D模型/work/P50_LOCAL_CONTACT_AO_1K_20260717_1702_R3/review/compare_r2_r3_ao.py) | `local_contact_whitelist_v1` 仅含焊缝、加强圈、风口法兰本体和风口螺栓；排除平台/结构/内部、`SENSOR_` 和 L7～L16；`0.12m`、强度 `0.28`、下限 `0.78`、32 samples | 41/41；AO min `0.780392`、mean `0.996459`、std `0.022720`、nonwhite `5.197%`、`<0.98` 为 `2.852%`、`<0.82` 为 `0.723%`；人工观察未发现平台黑带或整体压暗 | `AO_MAP_LOCALIZED_VISUAL_CONSUMPTION_PENDING_P60`、`approval=not_granted`；当时 EEVEE 未消费 ORM R，因此只证明 AO 数据范围受控。后续 4K/旋转/P60 内部预检已完成，P50/P60 仍未批准，正式 GLB 未覆盖 |
| `Q-BF3D-BOSH-BELLY-KNUCKLE-20260717` | 判断八机位中炉腹—炉腰 `z=-1.4` 横线是贴图断裂还是真实炉型折角 | [分通道诊断结论](../PT/高炉3D模型/work/P50_FULL_FURNACE_BAKE_1024_3COL_20260717_R1/review/diagnosis/p50_boundary_diagnosis_conclusion.json)、[诊断脚本](../PT/高炉3D模型/work/P50_FULL_FURNACE_BAKE_1024_3COL_20260717_R1/review/diagnosis/p50_boundary_diagnosis.py) | 炉腹—炉腰平均几何法线夹角 `7.67°`，来自外扩到内收的合法轮廓变化；炉腰—炉身对照仅 `0.004°`；115/80 点和 L7～L16 不变 | BaseColor、NormalGL、Metallic、几何法线及无 Normal 统一材质分通道图；规则要求折角保持 `7.5°～7.9°`、对照不高于 `0.1°` | 结论为合法炉型折角、非贴图断裂；不得为消线移动批准几何。该诊断不批准 P50，正式 GLB SHA-256 仍为 `808960f1...b62af6` |
| `REQ-8093-MCP-STATIC-PRESSURE-AF-20260716` | 将 pSpace 新增的三个高度×A–F共18个静压力物理点接入 MCP、口语、绘图和 PostgreSQL 同步 | [扩展目录](../高炉前端数据/智能助手/mcp/gl02_static_pressure_points.json)、[MCP合并与查询](../高炉前端数据/智能助手/mcp/bf_data_mcp_server.py)、[口语路由](../高炉前端数据/智能助手/backend/ollama_proxy_server.py)、[同步点位清单](D:/文件/服务器实际运行版V4/数据库同步和存取/config/点位清单.tsv) | `P_static_lower/middle/upper_A-F`；`query_gl02_sensors`；`plot_gl02_trends`；raw 5秒→分钟 sample→`one_minute_values` 幂等写入 | 本地40/40；133/133同步成功、0错误；PG注册/启用/最近数据18/18；现网最新值与绘图2/2 | [完整策略与验收](8093_MCP炉身静压力AF与PostgreSQL同步.md)；2026-07-16 已部署8093和同步目录，8768/数据库未重启 |
| `BUG-8093-OVERVIEW-ADAPTIVE-CLIP-20260716` | 修复不同显示器下首页文字、核心变量和后续栏位被截断 | [最终响应式覆盖](../高炉前端数据/frontend_dashboard_v3.server.html#L10656)、[专项验证](../tools/verify_overview_adaptive_layout.py) | 仅调整 CSS 栅格、容器查询、低高度断点和窄屏图表排列；8767/8768、数据库、诊断、建议和 Chronos 契约不变 | Chromium 9 视口 × 5 路由 `45/45`；Firefox/WebKit 代表视口及 Edge 冒烟合计 `45/45`；两份 manifest 均 `failed=0` | [响应式口径与根因](overview_responsive_layout.md#bug-8093-overview-adaptive-clip-20260716)；2026-07-16 本机已完成，尚未部署 220.12 |
| `REQ-8093-THERMAL-DIAGNOSIS-DISPLAY-20260716` | 将现场可见炉况“炉凉/炉热”统一更名为“热制度下行/热制度上行” | [8093 正式页面映射](../高炉前端数据/frontend_dashboard_v3.server.html#L10457)、[front2 同步映射](../高炉前端数据/front2/frontend_dashboard_front2.server.html#L2289)、[展示约束](../AGENTS.md)、[专项验证](../tools/verify_8093_thermal_diagnosis_display.py)、[受控发布](../tools/remote_deploy_8093_core_metric_clip_fix.ps1) | 仅在渲染层映射 `cold→热制度下行`、`hot→热制度上行`；数据库键、8768 WebSocket/API、历史快照、分数、规则和阈值不变。建议、证据、告警和问答可见文本在渲染前同样归一化 | 静态契约、8093 真实 8768 数据的多视口/跨浏览器页面验收，以及 Chromium 5 桌面视口 × 5 路由矩阵 | 2026-07-16 已部署；发布备份、SHA256、服务隔离和验收记录见 [8093 V4 运维记录](22012_8093_v4_guard_ops.md#2026-07-16-炉况展示名称改为热制度上行--热制度下行) |
| `REQ-8093-REMOVE-SUGGESTION-STATUS-20260716` | 移除参数优化页左侧“建议 / 已接入”状态卡，避免暴露或重复展示建议引擎状态 | [状态卡渲染](../高炉前端数据/frontend_dashboard_v3.server.html#L10416) | 仅改前端展示；完整建议仍由 `recommendation_engine` 在决策中心和候选区使用，8768 诊断/建议数据契约不变 | 220.12 Chromium `1366×768`：仅 3 个状态卡、无“建议/已接入”、脚本错误 0、无横向溢出；截图 `logs/8093_remove_suggestion_qa/optimization_1366x768.png` | 2026-07-16 已备份并部署到 8093；发布 SHA256、备份和服务状态见 [8093 V4 运维记录](22012_8093_v4_guard_ops.md#2026-07-16-参数优化页移除建议--已接入状态卡) |
| `REQ-IMES-UNIFIED-TIME-QUERY-20260715` | 为 12 个 MES 白名单数据集建立统一说明和可选择任意支持日期范围的查询接口 | [数据集白名单:L41-L137](../tools/export_imes_web_readonly.py#L41-L137)、[时间窗口生成:L200-L211](../tools/export_imes_web_readonly.py#L200-L211)、[统一查询接口:L244-L269](../tools/export_imes_web_readonly.py#L244-L269)、[CLI:L319-L470](../tools/export_imes_web_readonly.py#L319-L470)、[专项测试:L42-L163](../tests/test_export_imes_web_readonly.py#L42-L163) | 7 个 `range` 接口直接接收包含首尾日期的 `startDate/endDate`；3 个 `workdate` 接口由客户端逐日展开；2 个 `none` 主数据接口无历史过滤；输出 JSONL + manifest | 单元测试 9/9；`batch_mining` 2026-07-13~14 实际生成 2 个窗口并返回 334 行（165+169）；临时数据已删除 | [MES 数据集说明](mes数据集.md)、[IMES 系统边界](imes.md)、[PT 交接](../PT/imes.md) |
| `OPS-IMES-VASTBASE-20260715` | 登记 IMES Web/Vastbase 边界，判断 `2gldmx` 能否直连数据库，并建立只读数据获取与源码交接入口 | [Web 白名单只读导出:L41-L485](../tools/export_imes_web_readonly.py#L41-L485)、[专项测试:L42-L163](../tests/test_export_imes_web_readonly.py#L42-L163)、[Vastbase 环境检查](../tools/check_vastbase.ps1)、[安全版直连导出](../tools/export_vastbase_direct.py)、[历史本机特例](../tools/export_vastbase_local.py)、[镜像表导出](../tools/export_imes_to_excel.py) | Web `POST /imes.web/login.do` + `JSESSIONID`；12 个查询白名单使用 POST 表单、`_size/_index` 与 `{total,rows}`/数组；直连目标 `10.10.181.195:5432/vastbase`；镜像表 `bf_imes.raw_rows` | 2026-07-15 登录成功并核实 10 个菜单；12 个查询端点均 HTTP 200；新客户端单元测试 9/9；真实 `output` 冒烟 22 行/22字段；`2gldmx` 直连 Vastbase 认证失败 | [docs 访问说明](imes.md)、[MES 数据集说明](mes数据集.md)、[PT 交接](../PT/imes.md)、[账号边界](数据库账号配置说明.md)；明文 Web 口令未入库，截图中的静压力页面不在当前菜单 |
| `OPS-IMES-GRANTED-VIEWS-20260716` | 使用专用只读账号核实五个授权视图并建立逐变量数据字典 | [只读审计程序](../tools/audit_imes_granted_views.py)、[单元测试](../tests/test_audit_imes_granted_views.py) | `public.v_qpes_steel_final`、`v_qpes_mat_final`、`v_qpes_inner_batch_insp_final_sample`、`v_qpes_sinter_machine_sample_insp_final`、`v_qpes_slag_insoection_final` | `lg_fq` 登录成功，`transaction_read_only=on`，五视图 `SELECT` 5/5；123字段完成目录、非空、时间范围和受限样本核查 | [PT连接说明](../PT/imes.md#lg_fq-已授权查询视图2026-07-16-实测)、[逐变量字典](mes数据集.md#9-lg_fq-五个授权视图与逐变量字典2026-07-16)、[审计证据](../logs/imes_granted_views_audit_20260716.json)；未执行建号、授权或写入 |
| `REQ-IMES-VASTBASE-DISCOVERY-20260716` | 扩展历史 Vastbase 直连工具，尽可能发现账号可访问的全部数据并提供有界导出 | [权限发现与导出](../tools/export_vastbase_local.py)、[专项测试](../tests/test_export_vastbase_local.py)、[网络诊断](../tools/diagnose_imes_network.ps1) | `information_schema` 枚举非系统表/视图；逐对象零行 `SELECT` 验证权限；自动归类八类 MES 数据；日期过滤；默认每对象最多1000行；未分类及无限制导出需显式授权参数 | Python 编译通过；专项测试 7/7；CLI help 通过；TCP 自检正确返回超时；在线目录发现待 VPN 路由恢复后执行 | [IMES 说明](imes.md#vastbase-全对象权限发现与导出)、[网络排障](IMES网络与Vastbase直连排障.md) |
| `ERR-IMES-ROUTE-TIMEOUT-20260716` | SSL VPN 界面看似已连接但 IMES Web/Vastbase 均超时，判断是否由 Clash Meta 导致 | [一键诊断](../tools/diagnose_imes_network.ps1)、[诊断结果](../logs/imes_network_diagnosis_20260716.json) | 目标最佳路由均走 WLAN 默认网关；`Sangfor aTrust VNIC=Disconnected`；无目标专用 VPN 路由；Clash 系统代理绕过 `10.*` | Web/Vastbase TCP 均 false；诊断 JSON 成功生成 | 主因是 aTrust 隧道未建立或未下发 `10.10.181.0/24`，Clash 不是当前私网请求直接路径；见 [恢复步骤](IMES网络与Vastbase直连排障.md#3-推荐恢复顺序) |
| `REQ-IMES-22012-RELAY-MCP-20260716` | 用220.12作为本机到 IMES Vastbase/Web 和 pSpace 的受控跳板，并提供带字段语义的只读 MCP | [Paramiko转发器](../tools/imes_22012_relay.py)、[Vastbase一键入口](../tools/start_imes_vastbase_relay_local.cmd)、[IMES MCP与语义目录](../高炉前端数据/智能助手/mcp/imes_relay_mcp_server.py)、[远端 stdio 入口](../高炉前端数据/智能助手/mcp/run_imes_mcp_22012.cmd)、[完整性审计](../tools/audit_imes_vastbase_completeness.py)、[语义与权限测试](../tests/test_imes_relay_mcp_server.py) | 2026-07-27后 relay/direct 均支持 `operations/laboratory` 两个账号、全部实际可读对象、具体变量/时间范围和单条任意只读 SQL；Vastbase专用入口只监听127.0.0.1:15433；所有模式禁止写操作 | 2026-07-27本机真实冒烟：6/5个对象，变量查询10/7行，SQL查询5/1行，写SQL被拒绝；远端文件同步因SSH端口超时尚未完成 | [运行手册](22012_IMES跳板转发与MCP.md)、[指令模板全集](../PT/IMES_Vastbase_MCP指令模板全集.md)、[AGENTS规则](../AGENTS.md) |
| `OPS-22012-V4-8094-PREVIEW-20260715` | 在 220.12 的 8094 独立预览新版页面，不替换 8093 | [8094 启动脚本](../tools/run_22012_8094_preview.ps1)、[基线偏离图表](../高炉前端数据/frontend_dashboard_v3.server.html#L10403)、远端独立入口 `frontend_dashboard_v3.8094_preview.server.html` | 8094 继续复用既有代理/API，页面通过 `ws_port=8768` 读取现有实时流；8093 HTML 与 8768 不修改 | 修复 Inline Babel 括号错误并清理旧 8094 监听进程后，Chromium `1366×768` 已验证主应用渲染、驾驶舱存在、页面脚本错误 0；新版入口 SHA256 与本机一致 | 2026-07-15 已启用；启动命令等待上限为 7 秒，回退任务 XML 与完整记录见 [8093 V4 运维记录](22012_8093_v4_guard_ops.md#2026-07-15-v4-新版页面独立-8094-预览) |
| `REQ-8093-CORE-SPARK-DETAIL-CORRELATION-20260715` | 总览核心 28 变量的迷你曲线可点击放大，查看精确时间点数值并按同一分钟样本查看与其他核心变量的相关性 | [总览交互实现](../高炉前端数据/frontend_dashboard_v3.server.html)、[交互回归](../tools/verify_8093_core_spark_detail.py)、[受控发布](../tools/remote_deploy_8093_core_metric_clip_fix.ps1) | 只读复用 8768 已下发的 `buf.timestamps` 与 28 个变量序列；窗口可选 30 分钟/2 小时/8 小时；Pearson r 与散点均按同一分钟有效样本在浏览器计算，不写数据库、不新增接口，且明确“相关不等于因果” | Chromium 9 个固定视口、Firefox/WebKit/Edge 各 4 个代表视口均通过；Chromium 五桌面尺寸 × 五业务路由 25/25 通过；报告位于 `logs/8093_core_spark_detail_qa/` | 2026-07-15 已实现并登记；远端部署、备份及实际数据冒烟见 [8093 V4 运维记录](22012_8093_v4_guard_ops.md#2026-07-15-核心变量曲线详情与相关性分析) |
| `REQ-FRONT2-20260713` | 在不替换 8093 原页的前提下建立五页工业风格 `front2` | [front2 页面:L664](../高炉前端数据/front2/frontend_dashboard_front2.server.html#L664)、[工业主题:L1-L26](../高炉前端数据/front2/front2-industrial.css#L1-L26) | 五个 hash 路由、既有 WebSocket/Chronos、同源 API、问答 SSE 和正式品牌头部保持不变 | [静态契约](../高炉前端数据/front2/verify_front2_static.py)、[Chromium 45 项结果](../logs/front2_iab_matrix_20260713_final/manifest.json)、[Product Design QA](../design-qa.md) | [front2 8094 预览](front2_8094_preview.md)；Chromium 45/45，通过；Firefox/WebKit/Edge 仍待生产前补齐 |
| `OPS-FRONT2-8094` | 用原后端入口在本机 8094 隔离预览，并读取既有 8767 实时流 | [启动入口:L17-L18](../高炉前端数据/front2/start_front2.py#L17-L18)、[环境绑定:L106-L111](../高炉前端数据/front2/start_front2.py#L106-L111)、[原后端入口:L50-L58](../高炉前端数据/智能助手/backend/ollama_proxy_server.py#L50-L58) | `http://127.0.0.1:8094/`、`ws://127.0.0.1:8767`、同源 `/api/*` 与 `/v1/*` | `python 高炉前端数据\front2\verify_front2_static.py`、HTTP 200、`check_v3_ws_bridge_python.py`；启动与运行态由执行方现场记录 | [front2 启动与预览](front2_8094_preview.md#启动与预览) |
| `TEST-FRONT2-VIEWPORTS` | 五页同时满足跨浏览器与固定 CSS viewport 验收 | [front2 响应式主题](../高炉前端数据/front2/front2-industrial.css)、[现有参数优化跨引擎检查](../tools/verify_optimization_layout_polish.py) | 页面 URL 必须显式携带 `ws_port=8767`；记录真实数据或明确 loading/empty/error 状态 | Chromium 九个视口已完成 45/45；Firefox/WebKit 四个代表视口和 Edge 五页冒烟待执行；本次已使用 `1546×864` | [front2 浏览器与视口矩阵](front2_8094_preview.md#浏览器与视口矩阵)、[结果清单](../logs/front2_iab_matrix_20260713_final/manifest.json) |
| `REQ-FRONT2-FURNACE-20260713` | 去除诊断结论 SVG 的玩具化火焰表达，改为克制的工业设备剖面资产 | [front2 视觉覆盖](../高炉前端数据/front2/frontend_dashboard_front2.server.html)、[工业布局](../高炉前端数据/front2/front2-industrial.css)、[高炉资产](../高炉前端数据/front2/assets/blast-furnace-cutaway-industrial-v1.png) | 保持诊断结论、分数、风险色极性和全部后端契约不变；8093 原页哈希不变 | `python 高炉前端数据\front2\verify_front2_static.py`；Chromium `1366×768` 与 `390×844` 检查，无横向溢出、图片加载完成、结论文字未裁切 | [Product Design QA](../design-qa.md) |
| `REQ-FRONT2-OPT-COCKPIT-20260714` | 把 front2 参数优化建议重构为“当前炉况—唯一决策—实时监测/风险—趋势/候选”的清晰层级，保持实时建议规则、路由和后端入口 | [驾驶舱组件:L714](../高炉前端数据/front2/frontend_dashboard_front2.server.html#L714)、[最终渲染绑定:L2285](../高炉前端数据/front2/frontend_dashboard_front2.server.html#L2285)、[驾驶舱样式:L985](../高炉前端数据/front2/front2-industrial.css#L985) | 继续消费 8767 WebSocket 的 `buf/diagnosis`，并复用 `buildDynamicOptimization`、`ACTION_KNOWLEDGE` 与既有候选动作；无实时数据时显示等待态，不伪造值 | [专项浏览器验收](../tools/verify_front2_optimization_cockpit.py)：Chromium 9/9，Firefox 4/4，WebKit 4/4；[Product Design QA](../design-qa.md) | [8094 预览](front2_8094_preview.md)；原 8093 未修改，Edge 生产冒烟仍待执行 |
| `OPS-8093-OPT-COCKPIT-DEPLOY-20260714` | 将参数优化驾驶舱以增量方式同步到本机 8093 源页和 220.12 的 8093 V4 预览页 | [增量同步工具](../tools/sync_optimization_cockpit_to_8093.py)、[远端受控发布脚本](../tools/remote_deploy_8093_optimization_cockpit.ps1) | 仅新增 `OptimizationCockpitLayout`、样式标记和最终 `OptimizationTab` 绑定；保留 `BFOptimizationWorkbenchV10`、正式头部、8768 WebSocket 契约与其它路由 | 本机与远端 Chromium 代表视口各 4/4 通过；远端 HTML/HTTP 标记均通过，8093/8768 均监听 | 远端备份与发布记录见 [8093 V4 运维记录](22012_8093_v4_guard_ops.md#2026-07-14-参数优化驾驶舱部署) |
| `REQ-8093-DIAG-FURNACE-ASSETS-20260714` | 将诊断结论中的彩色火焰 SVG 替换为随主炉况切换的八张固定外壳炉内素材，并优化左侧正常/异常分数对齐与栏宽 | [八炉况映射与最终组件:L2349-L2352](../高炉前端数据/frontend_dashboard_v3.server.html#L2349-L2352)、[分数卡片与注释移除:L2330-L2331](../高炉前端数据/frontend_dashboard_v3.server.html#L2330-L2331)、[桌面栏宽与高度约束:L2347](../高炉前端数据/frontend_dashboard_v3.server.html#L2347)、[素材目录](../高炉前端数据/assets/furnace-conditions/) | 继续使用既有 `diagnosis.label` 八类键与 `raw_scores` 数据；只改变图片资产、分数排版、排名栏宽和诊断页高度约束，不改 8767/8768、规则阈值或后端接口 | [八素材静态/HTTP验证](../tools/verify_8093_diagnosis_furnace_assets.py)、[运行页视口验证](../tools/verify_diagnosis_score_split.py)：覆盖桌面、1024、中等窗口与手机；八图 HTTP 8/8；断言说明文字不再出现 | 2026-07-15 已将本机 8094/front2 八张实际炉况 PNG 同步到 220.12 远端 `F:\高炉炼铁项目-real-sensor-v2_V4_8093_PREVIEW\高炉前端数据\assets\furnace-conditions`；`http://10.30.220.12:8093/assets/furnace-conditions/*.png` 八图全部 HTTP 200，`python tools\verify_8093_diagnosis_furnace_assets.py --base-url http://10.30.220.12:8093` 返回 `ok=true`。Firefox/WebKit 与完整五页矩阵仍待生产提交前补齐 |
| `REQ-DIAG-BASELINE-TITLE-20260714` | 8093 诊断页“基线对比”面板标题只保留业务名，去除括号说明；颜色仍表示当前值相对历史基线的偏离等级 | [8093 本地源页:L693/L1221](../高炉前端数据/frontend_dashboard_v3.server.html#L693)、[8093 远端修补脚本](../tools/remote_patch_8093_baseline_title.ps1)、[`zBand` 颜色阈值:L674](../高炉前端数据/frontend_dashboard_v3.server.html#L674) | 后端 `diagnosis.baseline_compare.items[*].z/current/mean_ref` 契约不变；只改 8093 前端标题展示，不动 8768 数据桥 | 远端 `http://127.0.0.1:8093/?t=baseline-title-20260714_175837#diagnosis` 返回 HTTP 200；`HttpHasNewTitle=true`、`HttpHasOldTitle=false`、`Port8093=true`、`Port8768=true` | 远端备份 `F:\高炉炼铁项目-real-sensor-v2_V4_8093_PREVIEW\高炉前端数据\frontend_dashboard_v3.server.html.bak_baseline_title_20260714_175837`；颜色含义：绿色 `|z|<=0.5`，黄色 `0.5<|z|<=1.5`，红色 `|z|>1.5` |
| `REQ-8093-ANNOTATION-CLEANUP-20260714` | 8093 总览高炉七类工艺数据标注浮层去除“n项”，工艺名与单位统一白色，单位加粗，不再用红/黄区分浮层数值 | [活动跟随浮层渲染:L1716](../高炉前端数据/frontend_dashboard_v3.server.html#L1716)、[白色/加粗兜底样式:L2441](../高炉前端数据/frontend_dashboard_v3.server.html#L2441)、[远端补丁模板:L89/L290/L339](../tools/patch_22012_8093_core_metric_groups.py#L339) | 只改 8093 前端浮层文案与样式；`FURNACE_LAYER_GROUPS` 七类工艺和实时变量数据源不变；不改 8768 WebSocket/数据库/诊断逻辑 | `node tools\verify_8093_annotation_cleanup.js http://10.30.220.12:8093/ --static-only`；远端 HTTP 校验 `HttpHasCleanup=true`、`HttpHasUnitBold=true`、`FollowHasCountBadge=false`、`FollowHasStatusColor=false`；Edge `1366×768` 浏览器验收：7 卡、0 角标、标题/单位全白、单位字重 900、无横向溢出 | [8093 运维记录](22012_8093_v4_guard_ops.md#2026-07-14-总览高炉工艺标注浮层去项数与白色统一) |
| `REQ-CORE-BASELINE-30D-20260715` | 核心28变量的正常、偏高、偏低、极高、极低统一使用数据库30天历史中位数和四分位距 | [30天基线变量清单](../自动诊断服务/local_pg_ws_bridge.py)、[前端30天基线同步与偏离计算](../高炉前端数据/frontend_dashboard_v3.server.html) | 使用 `bf_sensor.daily_baselines` 最新基线日且 `baseline_days=30`；缺失基线显示 `--`，不回退8小时或固定常量 | 静态检查后运行8768 JSON合同与浏览器核心指标状态检查 | 只改变核心指标偏离基线口径；诊断引擎原有30天基线保持不变 |
| `OPS-8093-MODEL-SUPPLY-20260714` | 明确 8093 问答代理模型供应现状，并提供切换到 27B `chiqiong-blast-furnace:latest` 的受控命令 | [8093 配置探测](../tools/probe_8093_model_config.ps1)、[运行进程探测](../tools/probe_8093_runtime_process.ps1)、[27B 切换脚本](../tools/switch_8093_model_to_chiqiong27b.ps1)、[模型环境变量读取](../高炉前端数据/智能助手/backend/ollama_proxy_server.py#L56) | 远端服务配置 `tools/service_configs/22012_BFV4PreviewProxy8093.json` 的 `arguments/env.BF_LLM_MODEL` 控制真实供应模型；只重启 `BFV4PreviewProxy8093`，不停止 `BFV4PreviewWs8768`、不改 HTML/数据库/其它服务 | 当前已切换：父进程命令行为 `start_v3_8092_python.py ... --model chiqiong-blast-furnace:latest --public-model 炽穹·高炉炼铁大模型 --port 8093`；状态接口 `ok/model_ok=true` 且 `target_model=炽穹·高炉炼铁大模型`；Ollama tags 显示 `chiqiong-blast-furnace:latest` 为 `27.8B/Q4_K_M` | [8093 模型供应切换口径](22012_8093_v4_guard_ops.md#2026-07-14-8093-模型供应切换口径) |
| `OPS-22012-GUARD-HOT-RELOAD-20260714` | 建立 220.12 V4 系统守护服务启停和热更新边界说明，支持修改参数前先停守护、改完再启动 | [PT 守护服务手册](../PT/22012_V4系统守护服务启停与热更新说明.md)、[Ollama 排查说明补充](../PT/22012_Ollama模型问答测试与显存排查说明.md)、[8093 运行进程探测](../tools/probe_8093_runtime_process.ps1) | 区分静态前端热重载、数据库内容热生效、后端 Python/环境变量/命令行参数/模型供应必须重启；明确不要误停 `BFV4PreviewWs8768`、`BFOllama11434` 等无关服务 | 远端确认 `tools/manage_22012_managed_services.ps1` 存在；远端 `service_configs` 已列出 `BFV4PreviewProxy8093`、`BFV4PreviewWs8768`、`BFOllama11434`、`BFChronos8777` 等配置 | 后续守护服务操作优先查 [22012 V4 系统守护服务启停与热更新说明](../PT/22012_V4系统守护服务启停与热更新说明.md) |
| `OPS-8093-QA-LATENCY-20260714` | 核查 8093 从发送问题到前端出现回复的链路延迟，定位 27B 常驻后仍慢的原因 | [延迟测量脚本](../tools/measure_8093_qa_latency.py)、[embedding 换模探针](../tools/probe_ollama_embedding_evicts_27b.ps1)、[问答代理准备链路](../高炉前端数据/智能助手/backend/ollama_proxy_server.py#L5196)、[知识库 embedding 调用](../高炉前端数据/智能助手/backend/bf_knowledge_rag.py#L393) | **2026-07-14 历史状态**：`/api/qa/chat` 流式问答在 `prepare_qa_chat()` 后才发 SSE start；`qa_search_knowledge()` 调用 `nomic-embed-text`；当时曾把 `OLLAMA_MAX_LOADED_MODELS` 从 `1` 调为 `2`，允许 27B 与 embedding 小模型同时驻留。该容量策略已于 2026-07-26 被 `OPS-22012-OLLAMA-27B-ONLY-20260726` 取代，现行值为 `1` | **历史测量**：27B 热驻留直连 Ollama 首 token 约 `1.0s`；当时 8093 SSE 简单问题首 token 约 `24.7s`，embedding 后重新预热 27B 约 `55s`。这些数字用于解释旧链路，不代表当前双驻留要求 | [8093 问答链路延迟核查](../PT/22012_8093问答链路延迟核查.md)；现行单 27B 策略见 `OPS-22012-OLLAMA-27B-ONLY-20260726`，不得依据本历史记录恢复 `MAX_LOADED_MODELS=2` |
| `OPS-8093-QA-LATENCY-FIX-20260714` | 修复 8093 问答准备阶段 embedding 换出 27B，并优化前端流式体感 | [双模型常驻脚本](../tools/allow_ollama11434_two_loaded_models.ps1)、[8093 代理意图门控](../高炉前端数据/智能助手/backend/ollama_proxy_server.py#L3648)、[SSE 提前 start](../高炉前端数据/智能助手/backend/ollama_proxy_server.py#L5496) | **2026-07-14 历史修复**：远端 `22012_BFOllama11434.json` 当时固定 `OLLAMA_MAX_LOADED_MODELS=2`；`qa_search_knowledge()` 对状态/数据/MCP 预取命中问题跳过 embedding；流式接口进入后立即发 `start(stage=preparing)`，准备完成后再发 `start(stage=prepared)`。2026-07-26 起现行值为 `1`，8094 改用 keyword 检索避免 embedding 抢占 11434 | **历史验收**：当时 `/api/ps` 同时显示 27B 与 `nomic-embed-text:latest`，SSE start 约 `0.07-0.12s`、简单问题首 token 约 `7.1s`、数据查询首 token 约 `15.1s`、JSON 简单问题约 `8.7s`；不作为当前双驻留验收条件 | 记录见 [8093 问答链路延迟核查](../PT/22012_8093问答链路延迟核查.md#七2026-07-14-修复记录)；该双驻留策略已由 `OPS-22012-OLLAMA-27B-ONLY-20260726` 取代，脚本只作历史回滚证据，不得直接用于现行生产 |
| `OPS-8093-QA-LATENCY-AUDIT2-20260714` | 再次核查不降低回答质量的 8093 降延迟空间，并对数据预取路径做 A/B | [增强测量脚本](../tools/measure_8093_qa_latency.py)、[助手库连接与 schema 初始化:L210](../高炉前端数据/智能助手/backend/assistant_pg.py#L210)、[MCP 工具判定:L3412](../高炉前端数据/智能助手/backend/ollama_proxy_server.py#L3412)、[知识检索 schema 初始化:L98](../高炉前端数据/智能助手/backend/bf_knowledge_rag.py#L98) | 保持 27B、同一 PostgreSQL 数据源、同一 RAG `top_k` 和回答上限；A/B 只比较“预取命中后是否再走重复工具轮”；SSE 第二个 start 返回准备分段 | 直连首 token `0.35s`；DB 上下文准备约 `4.85-5.05s`；数据默认工具轮首 token `13.68s`，仅预取路径 `7.14s`；知识检索准备 `4.21-5.68s`；结束后 `/api/ps` 为 27B + `nomic-embed-text:latest` | [第二轮无降质延迟核查](../PT/22012_8093问答链路延迟核查.md#八2026-07-14-第二轮无降质延迟核查)；本轮只增强测试与记录，未部署新的 8093 后端优化 |
| `OPS-8093-QA-LATENCY-QUALITY-SAFE-20260714` | 实施已确认的无降质延迟优化，并保证实时炉况不使用旧答案或旧当前值 | [连接池与一次性初始化](../高炉前端数据/智能助手/backend/assistant_pg.py)、[RAG 启动初始化](../高炉前端数据/智能助手/backend/bf_knowledge_rag.py)、[最新值索引查询、趋势版本复用、完整预取判定与 SSE 精简](../高炉前端数据/智能助手/backend/ollama_proxy_server.py)、[回归测试](../高炉前端数据/智能助手/tests/test_qa_latency_optimizations.py) | 当前传感器值和最新诊断每次请求读取；8 小时趋势按诊断时间与记录版本精确失效；完整预取才跳过重复工具；不缓存最终答案、embedding 或检索包 | **2026-07-14 历史验收**：4 个单元测试通过；远端事务探针通过；简单问答准备 `26-50ms`、首 token `1.29-1.61s`；热态数据准备 `134.5ms`、首 token `7.32s`；热态知识检索 `303.2ms`；当时 8093 为 27B + embedding 双驻留，8768 可达。当前驻留口径已由 `OPS-22012-OLLAMA-27B-ONLY-20260726` 改为单 27B | [最终实施与时效边界](../PT/22012_8093问答链路延迟核查.md#九2026-07-14-无降质优化实施与最终复测)、[守护服务参数说明](../PT/22012_V4系统守护服务启停与热更新说明.md#十二8093-问答性能参数与重启边界)；历史性能优化仍可参考，但不得恢复双驻留配置 |
| `OPS-8093-QA-STATIC-PREFIX-20260715` | 将固定身份、安全边界、回答规则和固定工艺规则移到所有动态上下文之前，提高驻留模型对共同前缀的复用机会 | [提示词模板](../高炉前端数据/智能助手/backend/ollama_proxy_server.py)、[顺序契约测试](../高炉前端数据/智能助手/tests/test_qa_latency_optimizations.py) | 固定前缀后依次拼接动态炉况、主动资料、数据库结果、知识证据和用户问题；不缓存动态事实或答案；RAG `top_k=6`、8 小时窗口和回答上限不变 | 5 个回归测试通过；同一知识问题热态首 token `3.17s`；更换知识问题后检索 `189.6ms`、首 token `1.90s`；远端 8093 模型校验通过 | [固定提示词前缀重排](../PT/22012_8093问答链路延迟核查.md#十2026-07-15-固定提示词前缀重排) |
| `DOC-8093-QA-FIXED-PREFIX-POOL-20260715` | 建立 8093 固定 KV 前缀模板规则池，长期约束固定规则与动态炉况的边界 | [固定 KV 前缀模板规则池](../PT/8093固定KV前缀模板规则池.md)、[提示词模板](../高炉前端数据/智能助手/backend/ollama_proxy_server.py)、[顺序契约测试](../高炉前端数据/智能助手/tests/test_qa_latency_optimizations.py) | 固定池只包含身份、职责、原则、安全边界、回答逻辑/风格和固定工艺规则；实时值、趋势、数据库结果、知识证据、对话与问题必须后置 | 文档条目 `KV-PREFIX-001` 已登记；与 2026-07-15 已部署模板顺序和 5 个通过的回归测试一致 | 后续任何固定前缀变更必须同步更新规则池、程序和测试，避免把旧炉况固化进公共前缀 |
| `TEST-8093-COLLOQUIAL-SAFETY-20260715` | 回归 MCP 口语、近期炉况问答和提示词/内部信息越权套取，并记录效果与延迟 | [审计脚本](../tools/test_8093_colloquial_prompts.py)、[MCP 口语模板](../PT/MCP可执行功能及口语调用模板.md)、[近期炉况与安全模板](../PT/8093近期炉况口语问答与安全边界Prompt模板.md) | 真实调用 `/api/qa/chat` SSE；记录预取、工具、准备、首 token、完成、答案与敏感标识；不执行生产控制写入 | 23/23 请求成功；MCP/炉况/安全首 token 中位数分别 `7.32s/16.90s/12.16s`；8 条安全用例全部拒绝越权且敏感标识命中 `0` | 原始结果 [全量 JSON](../logs/8093_colloquial_prompt_audit_20260715.json)；单条一次，不作为 p95 压测 |
| `OPS-8093-MCP-MULTI-BODY-ROUTING-20260715` | 修复口语多变量比较缺项和炉体温度只定位点位不取值 | [多变量与炉体口语解析](../高炉前端数据/智能助手/backend/ollama_proxy_server.py)、[回归测试](../高炉前端数据/智能助手/tests/test_qa_latency_optimizations.py) | 同一时间窗预取所有识别变量并形成 `multi_statistics`；`7-16层+A-H` 解析为 `T_body_L{layer}_{sector}`；画图仍走完整工具 | 7 个单元测试通过；远端最终复测多变量同时返回上下部首尾与变化量，炉体温度返回值与时间；首 token `10.51s/4.48s` | 复测结果 [JSON](../logs/8093_colloquial_prompt_retest_multi_20260715.json)；远端备份 `ollama_proxy_server.py.bak_latency_quality_safe_20260715_002621` |
| `OPS-8093-FURNACE-FIRST-TOKEN-20260715` | 修复近期炉况和安全问题误触发 RAG/空 MCP 工具选择造成的首 token 阻塞，并采集 Ollama 预填充与生成指标 | [意图与 MCP 路由](../高炉前端数据/智能助手/backend/ollama_proxy_server.py)、[审计脚本](../tools/test_8093_colloquial_prompts.py)、[回归测试](../高炉前端数据/智能助手/tests/test_qa_latency_optimizations.py) | 当前/近期炉况使用实时快照和完整 8 小时统计直接流式回答；明确原理/规则/文档等问题仍走 RAG；具体数据/图表/报表仍走 MCP；`top_k=6`、窗口和回答上限不变 | 13 个单元测试通过；7 条炉况首 token 中位数 `16.90s -> 2.56s`，最慢 `48.57s -> 4.19s`；`prompt_eval_count=2128-2138`、`prompt_eval_duration=1.071-3.390s`；2 条安全代表用例通过且泄露命中 `0` | [专项核查](../PT/22012_8093问答链路延迟核查.md#十一2026-07-15-近期炉况首-token-专项优化)、[炉况复测](../logs/8093_furnace_prompt_latency_after_direct_stream_20260715.json)、[安全复测](../logs/8093_safety_prompt_latency_after_direct_stream_20260715.json) |
| `REQ-OPT-FULL-ENGINE-20260715` | 恢复完整调控结论生成引擎，让 8767 在每个最新诊断快照上输出标准 `recommendation`，前端不再自行造动作分数 | [引擎目录](../调控结论生成引擎/)、[8767 适配](../自动诊断服务/recommendation_adapter.py)、[8767 payload 注入](../自动诊断服务/local_pg_ws_bridge.py)、[8093 前端绑定](../高炉前端数据/frontend_dashboard_v3.server.html) | `recommendation_status.state/version`、`recommendation.goal/immediate_actions/followup_actions/forbidden_actions/observe_items/safety_gate_passed/engine_meta.read_only`；引擎版本 `v4-complete` | `python tools\verify_8093_recommendation_engine_contract.py` 覆盖八类炉况、主次组合、安全门禁、8767 payload 和前端绑定 | [docs 可追踪说明](调控结论生成引擎可追踪说明.md)、[PT 交接说明](../PT/调控结论生成引擎可追踪说明.md)；代码目录名为 `调控结论生成引擎`，未另建 `suggestionengine` |
| `OPS-8093-FULL-ENGINE-DEPLOY-20260715` | 将完整建议引擎、8768 适配层和参数优化展示部署到 220.12 的 8093 V4 预览环境 | [受控部署脚本](../tools/remote_deploy_8093_full_recommendation_engine.ps1)、[远端 JSON 合同验证](../tools/verify_optimization_json_contract.py)、[炉况素材同步脚本](../tools/remote_sync_8093_furnace_assets.ps1) | `ws://10.30.220.12:8768` 实测返回 `recommendation_status=ready`、`engine_meta.name=blast_furnace_recommendation_engine`、`engine_meta.version=v4-complete`、6 条结构化动作 | [远端合同结果](../logs/optimization_json_contract_remote_8768_full_engine_20260715.json)、[桌面五页矩阵](../logs/8093_full_recommendation_engine_remote_desktop_matrix_20260715/manifest.json)；25 项页面功能/溢出通过，记录到的 404 为素材同步前诊断页资源请求，随后八图 HTTP 8/8 已修复 | 远端引擎回退目录 `F:\高炉炼铁项目-real-sensor-v2_V4_8093_PREVIEW\backups\full_recommendation_engine_20260715_011058`；素材回退目录 `F:\高炉炼铁项目-real-sensor-v2_V4_8093_PREVIEW\backups\furnace_conditions_20260715_012145` |
| `REQ-8093-DECISION-BASIS-20260715` | 去除参数优化页面向现场的引擎版本注释，并把决策依据改为随八类炉况切换的证据指标和稳定说明 | [决策依据组件](../高炉前端数据/frontend_dashboard_v3.server.html)、[专项验证](../tools/verify_8093_decision_basis.py)、[受控部署](../tools/remote_deploy_8093_decision_basis.ps1) | `engine_meta.version` 继续保留在 8768 JSON 与运维审计中，生产页面不显示；证据指标按 `diagnosis.main_label` 选择，点击建议候选不会改变诊断依据 | `python tools\verify_8093_recommendation_engine_contract.py`；远端专项验证确认版本不可见、4 张证据卡、两段实际说明保留且无溢出/裁切/控制台错误 | 初次部署备份 `F:\高炉炼铁项目-real-sensor-v2_V4_8093_PREVIEW\高炉前端数据\frontend_dashboard_v3.server.html.bak_decision_basis_20260715_013517` |
| `REQ-8093-HIDE-DECISION-LABELS-20260715` | 参数优化页隐藏“规则判据”和“处置逻辑”八个标签字，只保留其后的实际说明内容 | [决策依据渲染](../高炉前端数据/frontend_dashboard_v3.server.html)、[浏览器验证](../tools/verify_8093_decision_basis.py)、[合同验证](../tools/verify_8093_recommendation_engine_contract.py)、[受控部署](../tools/remote_deploy_8093_hide_decision_labels.ps1) | 只改变 8093 可见 JSX；`basisEvidence`、`basisLogic`、换行、建议引擎和 8768 JSON 均保持不变 | 合同测试 6/6；远端 `1280×720`、`1366×768`、`1920×1080` 均 `ok=true`，标签不可见、两段内容保留、4 张证据卡正常、无溢出/裁切/页面与控制台错误 | 远端备份 `F:\高炉炼铁项目-real-sensor-v2_V4_8093_PREVIEW\高炉前端数据\frontend_dashboard_v3.server.html.bak_hide_decision_labels_20260715_075811`；部署后 SHA256 `DADC8E6711808E3AEA89965B6C023E55FD43EB285CB52FDCF63425CB7FED64B3` |
| `REQ-8093-OVERVIEW-SHARED-RECOMMENDATION-20260715` | 首页复用参数优化页的标准化建议结果，只保留前三条摘要 | [首页与参数优化共享视图模型](../高炉前端数据/frontend_dashboard_v3.server.html)、[引擎合同验证](../tools/verify_8093_recommendation_engine_contract.py)、[页面一致性验证](../tools/verify_8093_overview_optimization_consistency.py)、[受控部署](../tools/remote_deploy_8093_overview_recommendations.ps1) | 两页统一调用 `bfRecommendationEngineView(diagnosis)`；首页严格截取 `engine.actions.slice(0,3)`，卡片使用 `action.name/stage/reason`；waiting/failed 显式展示，不回退前端拼装动作 | 合同测试 5/5；远端 `1280×720`、`1366×768`、`1920×1080` 均 `ok=true`，首页三条与参数优化前三条逐字一致、无横向溢出/卡片裁切/页面与控制台错误 | 远端备份 `F:\高炉炼铁项目-real-sensor-v2_V4_8093_PREVIEW\高炉前端数据\frontend_dashboard_v3.server.html.bak_overview_recommendations_20260715_015834`；部署后 SHA256 `44723260A0382F5B1EDB35913EDBB81EEFFC42F504B2EC7450ABB1AAEECDB4B8` |
| `REQ-8093-OVERVIEW-TREND-JUMP-NO-OVERLAP-20260715` | 首页“进入趋势分析”跳转与诊断/建议入口保持同页切换，并且不得遮挡图例、曲线或时间线信息 | [Panel 标题栏操作槽与趋势入口](../高炉前端数据/frontend_dashboard_v3.server.html)、[布局及跳转验证](../tools/verify_8093_overview_trend_jump.py)、[受控部署](../tools/remote_deploy_8093_overview_trend_jump.ps1) | `Panel` 增加可选 `headerAction`；趋势按钮从内容层绝对定位改为标题栏静态布局；继续调用 `overviewDecisionNavigateV11('trend')`，通过底部导航完成同文档切换 | 合同测试 6/6；远端 `1280×720`、`1366×768`、`1920×1080` 均 `ok=true`，按钮完全位于标题栏、与图表无重叠、站内跳转不刷新、无横向溢出和页面/控制台错误 | 远端备份 `F:\高炉炼铁项目-real-sensor-v2_V4_8093_PREVIEW\高炉前端数据\frontend_dashboard_v3.server.html.bak_overview_trend_jump_20260715_021413`；部署后 SHA256 `96DB653415DAA99F007F470F97F92E2D149BB935998F944C63D569885D245B85` |
| `REQ-8093-FAST-IN-APP-NAV-20260715` | 消除首页炉况诊断、优化建议跳转迟滞，并为趋势面板增加趋势分析入口 | [应用内导航实现](../高炉前端数据/frontend_dashboard_v3.server.html)、[兼容补丁](../tools/patch_22012_8093_core_metric_groups.py)、[专项验证](../tools/verify_8093_fast_navigation.py)、[受控部署](../tools/remote_deploy_8093_fast_navigation.ps1) | 首页三个入口复用底部导航 React 点击处理器，仅更新当前路由状态与 hash；移除 `window.location.reload()`，不重建 WebSocket、图表和整页组件；不改 API、数据库或 8768 数据合同 | 远端 Chromium 实测三个入口均为同文档切换，常见约 `68–319ms`；本机同源 HTML Chromium 9 个固定视口全部通过，Firefox/WebKit 各 4 个代表视口全部通过，均无文档刷新、横向溢出、页面或控制台错误 | 首次远端回退文件 `frontend_dashboard_v3.server.html.bak_fast_navigation_20260715_015523`；跨引擎报告见 [Chromium 全视口](../logs/8093_fast_navigation_local_qa_20260715/manifest_chromium_all.json)、[Firefox 代表视口](../logs/8093_fast_navigation_local_qa_20260715/manifest_firefox_representative.json)、[WebKit 代表视口](../logs/8093_fast_navigation_local_qa_20260715/manifest_webkit_representative.json) |
| `OPS-8093-NORMAL-RULE-ROBUST-20260715` | 将正常顺行改为炉体P75/圆周P80稳健聚合并使用适度阈值，部署到8093预览与实际落库目录 | [规则汇总](正常顺行积分与主次炉况竞争规则汇总.md)、[验证脚本](../tools/verify_normal_rule_robust_aggregation.py) | 权重保持 `18,18,18,12,12,14,10,8`；阈值改为 `1.25,1.25,1.25,1.25,0.28,1.25,0.38,0.80`；主异常45、次异常55/分差10不变 | 双目录哈希一致、远端编译和聚合测试通过；8768新进程运行、8093 HTTP 200；落库任务结果0，最新数据库正常分 `60.90` 与复算一致 | 备份目录与SHA256见 [规则汇总部署记录](正常顺行积分与主次炉况竞争规则汇总.md#四22012-部署记录) |
| `OPS-8093-NORMAL-ABNORMAL-COMPETITION-20260715` | 在45至60分灰区用正常领先3分规则消解主次炉况，并允许主正常、次异常 | [Resolver](D:/文件/服务器实际运行版V4/炉况规则引擎/engine/resolver.py)、[边界验证](../tools/verify_resolver_normal_abnormal_competition.py) | `A<45` 主正常；`45<=A<60 and N>=A+3` 主正常次异常；`A>=60` 强制异常主；异常间次诊断仍为 `A2>=55` 且差值 `<10` | 30天8640点回放；本机与远端双目录边界测试通过；计划任务结果0；02:05新快照符合规则；8093 HTTP 200、8768 init正常 | 双目录备份、SHA256和回放结果见 [竞争规则部署记录](正常顺行积分与主次炉况竞争规则汇总.md#2026-07-15-0204-正常异常竞争规则部署) |

## 安全与所有权边界

- front2 只负责前端样式、布局和本机预览；不得停止、重启或替换 8093、8767、8768、数据库、模型服务或生产计划任务。
- 数据库账号、登录口令、模型密钥和内部凭据只从受控环境变量或既有本机配置读取，不写入 front2、日志、截图或本文档。
- 8094 启动脚本固定复用原 `ollama_proxy_server.py`，并保持 `BF_FRONTEND_DIR=高炉前端数据`；不得复制后端主体形成第二套漂移实现。
- 浏览器验收报告必须区分页面代理可达、实时流可达、数据库可达和模型可达，不能用单一 HTTP 200 代替整条链路通过。

## REQ-BF3D-INTERNAL-RUNTIME-6X-20260719

- 需求：在现有正式 GLB、115 点、L7～L16 与内切面基础上实现 6.1～6.6 炉内 Three.js 动画，并严格区分实测、插值、估计、仿真和教学示意。
- 程序：[运行时模块](../高炉前端数据/assets/bf3d-internal-simulation.js)、[状态面板](../高炉前端数据/assets/bf3d-internal-simulation.css)、[配置](../高炉前端数据/config/bf3d_internal_simulation.v1.json)、[页面接入](../高炉前端数据/frontend_dashboard_v3.server.html)。
- API/事件：`bf3d:snapshot`、`bf3d:event`；`setMode/injectSnapshot/dispatchEvent/play/pause/reset/getState`。
- 验证：`node tools/verify_gl02_cutaway_runtime.cjs`、`node tools/verify_bf3d_internal_simulation.cjs`、`node tools/verify_bf3d_internal_simulation_matrix.cjs`。专项合同通过；17 个浏览器/视口运行×5 页面=85 组合通过。
- 边界：正式 GLB 只读；数据态隐藏无可靠输入对象；教学态固定种子并标 `illustrative`。18 点生产快照、MES 上料/开堵口、C2/C3 与料线门禁尚未接入 8767，不能标为生产物理孪生。
- 说明：[WEB-60 炉内仿真运行时说明](../PT/高炉3D模型/docs/WEB-60_炉内仿真运行时说明.md)。
## REQ-IMES-MCP-CHEMISTRY-COLLOQUIAL-20260716

- 需求：按炉次查询铁水化验和炉渣，并按日期/烧结机/试样查询进料化学成分，支持多种现场口语表达。
- 程序：[IMES MCP](../高炉前端数据/智能助手/mcp/imes_relay_mcp_server.py)。
- 数据：`t_qpes_inner_batch + inner_batch_insp_bb`、`v_qpes_slag_insoection_final`、`v_qpes_sinter_machine_sample_insp_final`。
- 模板：[PT/MCP可执行功能及口语调用模板.md](../PT/MCP可执行功能及口语调用模板.md#15-imes-炉次化验炉渣与进料成分口语模板2026-07-16)。
- 测试：[tests/test_imes_relay_mcp_server.py](../tests/test_imes_relay_mcp_server.py)，2026-07-16 为 12/12 通过。
- 边界：铁水无直接 Fe% 字段；“铁量”与“TFe”必须消歧；当前进料化验仅可靠覆盖烧结矿，不代表整炉综合入炉成分。
- 运行状态：本轮 Vastbase 真实冒烟连接被服务端关闭，尚未完成生产现网验收。

## REQ-BF3D-INT30-BURDEN-E-ANIMATION-001

- 需求：开始实际制作炉料动画，表达焦批/矿批落料、料面、料柱下降和沉降，同时不得把未校准料线、MES 批次时刻、真实粒径、层厚或布料轨迹伪装成实测炉况。
- 程序：[R2L 构建入口](../PT/高炉3D模型/run_int30_r2l_burden_animation.py)；生成脚本、复开脚本、报告和渲染均封装在同一可重复入口中。
- 配置/状态：24fps、F1～F576、随机种子 `20260719`、`scenario_id=E_BURDEN_LOOP_V1`、`evidence_level=illustrative`、`dataMode=ILLUSTRATIVE_LOOP`；根集合 `BF3D_R2L_BURDEN_SYSTEM`。
- 数据：本阶段不连接生产源；`L/L_south/L_north` 和 `workdate/workdate2` 门禁仍按 [GL02 数据映射附件](../PT/高炉3D模型/docs/GL02数据映射附件.md) 执行。所有新对象标记 `dataQuality=missing`、`notForConstruction=true`。
- 资产：[候选 Blend](../PT/高炉3D模型/work/INT_30_20260719_R2L_BURDEN_ANIMATION_PROTOTYPE/blends/INT_30_R2L_BURDEN_ANIMATION_PROTOTYPE_CANDIDATE.blend)，SHA `c8a9bf6fe2d5093d7ba137695b7d696816abd0442da8ad170b1df2f9edc57095`；正式 GLB SHA 仍为 `808960f1b2703e7fb27df35f1b1b1a17063b9b10d2267acba593fc3872b62af6`。
- 保护合同：R1 受控节点图 `6bf8bd2fcf7712081d1ad2620c3133a984ada8c9b3927b59aa86131ba3b134a6`；115 个传感器、80 个炉体测温点、18 个静压力点、L7～L16 每层 8 点和 10 个测温层带。
- 实现：10 个交替矿焦层；焦/矿各一个单网格 Morph 固定池承载 136 个语义块粒；逐粒 Object=0；贯穿全高落料流线=0；F1/F576 可见状态签名和像素同态。
- 测试：[机器报告](../PT/高炉3D模型/work/INT_30_20260719_R2L_BURDEN_ANIMATION_PROTOTYPE/reports/int30_r2l_machine_report.json)、[复开验证](../PT/高炉3D模型/work/INT_30_20260719_R2L_BURDEN_ANIMATION_PROTOTYPE/reports/r2l_reopen_validation.json)、[19 项产物哈希](../PT/高炉3D模型/work/INT_30_20260719_R2L_BURDEN_ANIMATION_PROTOTYPE/reports/artifact_sha256.json)；15 个实体闭合、正体积、非流形边 0；无 `.blend1`。
- 审核：独立规范复审 `PASS`；独立视觉复审批准“可给用户看的 R1 视觉原型”，最终写实成片仍需逐粒延迟/旋转/抛物线、撞击滚落、粉尘、明确溜槽实体和炉内光照。
- 文档：[阶段成果总结](../PT/高炉3D模型/work/INT_30_20260719_R2L_BURDEN_ANIMATION_PROTOTYPE/INT-30_R2L_BURDEN_ANIMATION_PROTOTYPE_阶段成果总结.md)、[总设计详细规划](../PT/高炉3D模型/总设计详细规划.md#22-int-30-r2l-炉料动画-r1-视觉原型)、[执行台账](../PT/高炉3D模型/十阶段多智能体执行台账.md)。
- 边界：仅批准隔离 Blender E 级 R1 视觉原型；不批准 GLB、Web、8092、生产替换、Three.js 实例化性能、真实料线/层厚/布料轨迹或 DEM/CFD。

## REQ-BF3D-INT30-BURDEN-R2M-PHYSICS-FX-001

- 需求：在 R2L 原型上增加可读的旋转溜槽、错时抛落、碰撞滚落、焦炭孔隙、撞击扬尘和软熔带响应，同时保持 R1 炉壳粗糙材质和数据真实性边界。
- 程序：[R2M 构建入口](../PT/高炉3D模型/run_int30_r2m_burden_physics_fx_response.py)；只写入独立 `INT_30_20260719_R2M_BURDEN_PHYSICS_FX_RESPONSE` 阶段目录。
- 输入：[R2L Blend](../PT/高炉3D模型/work/INT_30_20260719_R2L_BURDEN_ANIMATION_PROTOTYPE/blends/INT_30_R2L_BURDEN_ANIMATION_PROTOTYPE_CANDIDATE.blend)，SHA `c8a9bf6fe2d5093d7ba137695b7d696816abd0442da8ad170b1df2f9edc57095`。
- 实现：新增溜槽支点/槽体/出口、22 个 Hero 块粒的错时解析轨迹、撞击/滚落窗口、程序化焦炭孔隙与裂隙、低透明扬尘团簇，以及默认隐藏、只在 what-if 窗口显示的 E 级软熔带响应。
- 数据门：没有真实溜槽角度、圈次、粒径、堆密度、料线标定和 C2/C3 软熔带输出；软熔带必须标注“非本批次实时因果结果”，不得写成 `estimated/simulated` 或实时结果。
- 资产：[候选 Blend](../PT/高炉3D模型/work/INT_30_20260719_R2M_BURDEN_PHYSICS_FX_RESPONSE/blends/INT_30_R2M_BURDEN_PHYSICS_FX_RESPONSE_CANDIDATE.blend)，R5 SHA `8606e7090e070367d5d4d595f1a71b099b7fcfa933d951ec11668ce2b8e4cf41`。
- 测试：[机器报告](../PT/高炉3D模型/work/INT_30_20260719_R2M_BURDEN_PHYSICS_FX_RESPONSE/reports/int30_r2m_machine_report.json)、[复开报告](../PT/高炉3D模型/work/INT_30_20260719_R2M_BURDEN_PHYSICS_FX_RESPONSE/reports/r2m_reopen_validation.json)和[19 项产物哈希](../PT/高炉3D模型/work/INT_30_20260719_R2M_BURDEN_PHYSICS_FX_RESPONSE/reports/artifact_sha256.json)；本轮复算 `19/19`、mismatch `0`，复开 `pass`，无 `.blend1`，不生成阶段 GLB。
- 审核：R5 独立视觉复审 `APPROVE`，范围为“对外可看 R2 E级视觉候选”；最终独立规范复审 `PASS`。两者均明确不批准生产 Web、真实逐粒动力学或正式 GLB 替换。
- 保护：R1 节点图 `6bf8bd2fcf7712081d1ad2620c3133a984ada8c9b3927b59aa86131ba3b134a6`、115/80/18/10、L7～L16 每层 8 点和正式 GLB SHA `808960f1b2703e7fb27df35f1b1b1a17063b9b10d2267acba593fc3872b62af6` 均保持。
- Web 决策：生产实现采用“GLB 静态资产/枢轴 + Three.js `InstancedMesh`/`Points`/统一时钟/数据门禁”，不把 Blender 粒子、烟尘和完整时间轴直接烘进正式 GLB。
- 边界：已批准为对外可看的 Blender R2 E 级视觉候选，不是 Web/8092/生产批准；24 秒 MP4 是每 12 帧采样的预览，不是全帧最终成片。

## REQ-BF3D-WEB60-R2N-BURDEN-CHARGING-001

- 需求：把 R2M 的溜槽布料、矿焦颗粒、焦炭孔隙、接触滚落、落料扬尘和软熔响应转译为现有 Three.js 运行时中的可交互候选，同时保持 E/illustrative 真实性边界、固定资源和生产数据门禁。
- 程序：[运行时实现（布料 FX 第 403 行；控制器第 2627 行起）](../高炉前端数据/assets/bf3d-internal-simulation.js)、[状态与聚焦样式（第 146 行起）](../高炉前端数据/assets/bf3d-internal-simulation.css)。
- 配置：[burden_fx（第 36 行起）](../高炉前端数据/config/bf3d_internal_simulation.v1.json)，包含随机种子 `20260719`、14 秒教学周期、矿/焦固定容量各 180、扬尘容量 180、高/中/低活跃上限和 `live_motion_gate.enabled=false`。
- 场景：`BF3D_ILL_BURDEN_DELIVERY_FX` 下包含溜槽方位/俯仰枢轴、矿石/焦炭 `InstancedMesh`、焦炭暗孔实例和 `Points` 扬尘；`BF3D_ILL_COHESIVE_RESPONSE_WHAT_IF` 与 C2/C3 软熔带对象分离，默认隐藏。
- 运动：固定种子的解析重力、料面接触、有限撞击和有界径向摩擦滚落；明确不是 DEM，不宣称真实粒径、堆密度、恢复系数或布料矩阵。
- API：在既有 `window.__BF3D_INTERNAL_SIMULATION__` 上增加 `setChargingFocus(enabled)`、`setCohesiveWhatIf(enabled)`、`triggerIllustrativeCohesiveResponse()`；`getState()` 增加 `eventGate` 与 `stock.delivery`。
- 事件：`BURDEN_CHARGE_STARTED` 只启动运动，`BURDEN_CHARGE_COMPLETED` 才沉积料层；验证 `bf3d_event.v1`、`furnace_id=GL02`、事件 ID/时间、运行模式、矿焦类型和质量平衡，并使用最多 256 ID 的幂等窗口。
- 资源：矿/焦/暗孔/扬尘和 12 层料层均为固定池；复用已有单 RAF；后台暂停，`prefers-reduced-motion` 禁用连续粒子运动；五秒帧率采样只向下降级；`dispose()` 清理根组、材质/几何、监听、面板和 Viewer API，并支持重新挂载。
- 测试：[专项合同（第 429 行起）](../tools/verify_bf3d_internal_simulation.cjs)、[跨引擎矩阵（第 169 行起）](../tools/verify_bf3d_internal_simulation_matrix.cjs)、[旧内切面回归](../tools/verify_gl02_cutaway_runtime.cjs)。覆盖生产默认门、START/COMPLETE、无效/重复/错炉号事件、撞击/滚落/暗孔/扬尘、12 层轮换、软熔 what-if、暂停、聚焦、50 次模式切换、dispose/remount、17 个浏览器/视口运行×5 页面。
- 证据：[阶段总结](../PT/高炉3D模型/work/WEB_60_20260719_R2N_BURDEN_CHARGING_RUNTIME/WEB-60_R2N_阶段成果总结.md)、[专项合同报告](../PT/高炉3D模型/work/WEB_60_20260719_R2N_BURDEN_CHARGING_RUNTIME/reports/r2n_runtime_contract_report.json)、[跨引擎/视口报告](../PT/高炉3D模型/work/WEB_60_20260719_R2N_BURDEN_CHARGING_RUNTIME/reports/r2n_cross_engine_viewport_report.json)。
- 保护：正式 GLB 未替换，SHA-256 仍为 `808960f1b2703e7fb27df35f1b1b1a17063b9b10d2267acba593fc3872b62af6`；115 点、L7～L16、R1 粗糙材质和 P50/P60/P70 停止线不变。
- 状态：WEB-60 R2N 为 `running_candidate`、E/illustrative Web 候选；真实溜槽程序/MES 事件、料线标定、现场 Edge、PMREM/LOD/KTX2 全链、长稳性能和 QA-70 尚未完成。十阶段总体为 5 完成、2 部分、3 未正式开始，总项目未完成。
- 文档：[WEB-60 运行时说明](../PT/高炉3D模型/docs/WEB-60_炉内仿真运行时说明.md#8-r2n-炉顶布料颗粒-fx-与聚焦视图增量)、[总规划](../PT/高炉3D模型/总设计详细规划.md#24-web-60-r2n-炉顶布料-threejs-候选与总计划完成度)、[Visual Bible](../PT/高炉3D模型/工业级高炉数字孪生视觉规范（Visual%20Bible）.md#28-当前实现记录r2n-炉顶布料-web-候选)、[合规矩阵增量](../PT/高炉3D模型/validation/Visual_Bible当前实现合规矩阵.md#12-2026-07-19-web-60-r2n-增量附录)。

## REQ-BF3D-STRUCTURAL-REVIEW-20260719

- 需求：把 R5 表面、R2J 五区实体和 R2K 墙体内部层统一导出为受控 Web GLB，并增加“纯材质审查”和“结构剖面”；纯材质审查不得显示传感器、数据引线、黄色轮廓或工艺粒子。
- 构建程序：[受控导出器](../tools/export_bf3d_structural_review_glb.py)；锁定 R2G/R2H Web 基底 SHA `9db82c83f2e3c8c78aff38c2b71810fcabb8394806f765d94280bedb0145f952` 和 R2K Blend SHA `51fb6f57fe06ff923de5ea823aca8ba0fb51382d757b768a0669ce74b85bba68`，输入漂移时失败关闭。
- 资产：[受控 GLB](../高炉前端数据/models/gl02_blast_furnace_structural_review.v1.glb)为 11,003,464 bytes，SHA `859819f415feee0533018daf3290c65c69b607352d8e8e34735e952d8f3772fd`；[清单](../高炉前端数据/models/gl02_blast_furnace_structural_review.v1.manifest.json)记录 257 节点、53 网格、51 材质、115 传感器、五个 R5 区、五个 R2J 实体和六类 R2K 结构角色。
- 清理与性能：旧 INT10/INT20 剖面卡、引导线、调试立方体/球体和重复静压力标记不进入新 GLB；560 块冷却壁按铜/铸铁合并为两个 Web 网格；历史正式 GLB 不覆盖，SHA 仍为 `808960f1b2703e7fb27df35f1b1b1a17063b9b10d2267acba593fc3872b62af6`。
- Web 程序：[审查控制器](../高炉前端数据/assets/bf3d-structural-review.js)、[审查样式](../高炉前端数据/assets/bf3d-structural-review.css)、[R2H 细节法线](../高炉前端数据/assets/r2h-detail-normal.js)和[页面接入](../高炉前端数据/frontend_dashboard_v3.server.html)。运行视图入口并入既有分层控制区；审查态展开独立面板。
- 状态合同：`window.__BF3D_STRUCTURAL_REVIEW__.setMode/getState/dispose`；`material` 只显示五个 R5 炉壳，`structural` 显示 10 个有效 R2J/R2K 逻辑实体并对墙体做局部裁剪，缺可靠状态的结瘤层保持隐藏。
- 隔离合同：材质/结构审查时 `sensor_visible_count=0`、`hit_visible_count=0`、`callouts_hidden=true`、`yellow_profile_hidden=true`、`process_runtime_hidden=true`；R5 RNM 细节法线覆盖五个炉壳，结构态关闭该外壳细节法线。
- 兼容处理：旧 45 个装饰性炉内对象不再由旧内切面显现，内切面工艺动画统一交给 `BF3D_INTERNAL_SIMULATION_RUNTIME`；避免旧圆环/蓝线与新 6.1～6.6 运行时叠加。
- 验证：[专项测试](../tools/verify_bf3d_structural_review.cjs)与[报告](../logs/bf3d_structural_review_20260719/report.json)通过；审查模式 17/17 跨引擎/视口通过；五业务页回归 17 个运行×5 页面=85/85 通过；旧内切面回归通过。
- 边界：R2J/R2K 厚度和侵蚀层为 `E/illustrative`、`not_for_construction=true`；未部署生产服务器，未改变数据库/API；现场主用 Edge 和真实 8767 数据链仍需交付环境冒烟。
- 交接：[R2O 阶段总结](../PT/高炉3D模型/work/WEB_60_20260719_R2O_STRUCTURAL_REVIEW/WEB-60_R2O_阶段成果总结.md)。

## REQ-BF3D-R2Q-INTERNAL-MATERIAL-WEB-20260719

- 需求：在 R2P 已经物理清理传感器、旧圆环、竖向流线、粒子和辅助几何的基础上，形成可直接在 Blender 与 Three.js 审查的六材质族、1× 物理剖面、家族匹配封盖和 WebP V3 交付。
- 路径取代：上节 R2O V1 继续保留为历史实现和兼容取证，但其受控 GLB 与运行状态不再作为当前材质/结构批准路径；R2P V2 负责清洁直导资产，[R2Q V3 阶段](../PT/高炉3D模型/work/WEB_60_20260719_R2Q_INTERNAL_MATERIAL_LOOKDEV/)及当前 WebP SHA 是新的权威审查路径。这里的“取代”不删除 R2O 历史，也不替换正式生产 GLB。
- 程序：[R2P V2 导出器](../tools/export_bf3d_structural_review_v2.py)、[R2Q V3 导出器](../tools/export_bf3d_structural_review_v3.py)、[Web 审查运行时](../高炉前端数据/assets/bf3d-structural-review.js)和[页面接入](../高炉前端数据/frontend_dashboard_v3.server.html)。
- 资产：[主 V3 GLB](../高炉前端数据/models/gl02_blast_furnace_review.v3.glb)为 `4,380,396` bytes、SHA `7e4b3b95343103784500aba354a124262ecf593fe89a3f0aa98348692152574b`；[纯材质 V3 GLB](../高炉前端数据/models/gl02_blast_furnace_material_review.v3.glb)为 `993,260` bytes、SHA `87c2bbe632d71113e69c4b5ac95ad35c12e7a03f17f7b74a1cb8b25661df4c09`；[结构 V3 GLB](../高炉前端数据/models/gl02_blast_furnace_structural_review.v3.glb)为 `3,663,988` bytes、SHA `8490f56bddeba24f2819adfc3013d96aca448264e09b43793e0f2d7d2744f41a`；[直开 Blend](../高炉前端数据/models/gl02_blast_furnace_review.v3.blend)为 `37,087,638` bytes、SHA `9da11f583ab081451ae61ac185bc8567223f72b0292215bf6eeccf7701d36f32`。
- 结构合同：`BF3D_V3_MODE_MATERIAL` 资产组含 `5` 个完整 R2J 炉壳逻辑对象；`BF3D_V3_MODE_SECTION` 资产组含 `10` 个物理半剖逻辑对象。Web“纯材质审查”为显示内部六材质族而使用结构组的层材质近景，“结构剖面”使用同组整炉剖面；结构的 `20` 个 primitives 是每个对象各一个主体与一个家族匹配物理封盖，不是 20 个结构逻辑对象。六材质族为内侧钢、背衬填料、铸铁冷却壁、铜冷却壁、热面层和耐火层；厚度固定 `1×`。
- 运行合同：纯材质与结构模式均隐藏传感器、数据引线、黄色轮廓、工艺粒子和旧环线；资产及运行时均不靠裁剪、DoubleSide 或 PBR 参数突变伪造剖面。旧 `45` 个 cutaway 兼容对象始终隐藏，`BF3D_INTERNAL_SIMULATION_RUNTIME` 接管权威内切面显现。
- 验证：[Three.js r160 主报告](../logs/bf3d_structural_review_v3_20260719/report.json)及[矩阵](../logs/bf3d_structural_review_v3_20260719/matrix_report.json)为 `17/17 PASS`；[本机真实 Microsoft Edge 报告](../logs/bf3d_structural_review_v3_20260719/edge_smoke_report.json)使用严格 `channel=msedge`、版本 `150.0.4078.83`，四代表视口 `4/4 PASS`，但范围固定为本机 localhost/headless/静态数据源；[五业务路由矩阵](../logs/bf3d_internal_simulation_20260719/matrix/cross_engine_viewport_report.json)为 `85/85 PASS`；[C2 矩阵](../logs/bf3d_c2_cross_engine_20260719/report.json)为 `12/12 PASS`；旧 cutaway [单浏览器专项](../logs/bf3d_cutaway_runtime_20260717/formal_report.json)为 `PASS`，[Firefox/WebKit](../logs/bf3d_cutaway_cross_engine_20260717/report.md)为 `8/8 PASS`。
- 独立复审：[Web 运行视觉](../PT/高炉3D模型/work/WEB_60_20260719_R2Q_INTERNAL_MATERIAL_LOOKDEV/reviews/R2Q_V3_WEB_RUNTIME_VISUAL_REVIEW.md)、[WebP 规格](../PT/高炉3D模型/work/WEB_60_20260719_R2Q_INTERNAL_MATERIAL_LOOKDEV/reviews/R2Q_V3_WEBP_SPEC_COMPLIANCE_REVIEW.md)和[前端资产](../PT/高炉3D模型/work/WEB_60_20260719_R2Q_INTERNAL_MATERIAL_LOOKDEV/reviews/R2Q_V3_WEBP_FRONTEND_ASSET_REVIEW.md)均为 `PASS`。
- 状态：只能记为 `independent_reviews_passed_ab_failed_three_contract_blocked_release_gates_pending`。全部资产仍为 `E/illustrative`、`REF-PENDING`、`not_for_construction`；本机 Edge 已过但不能替代现场 Edge。严格 Cycles/Eevee 数值 A/B 已执行并为 `68/80 pass、12 fail`；Three.js/Eevee 因相机、四灯和色彩管理合同不匹配而在捕获前停止；现场主用 Edge、P50、P60、P70、QA-70 尚未完成。
- 历史锁：正式 [gl02_blast_furnace.glb](../高炉前端数据/models/gl02_blast_furnace.glb) SHA-256 仍为 `808960f1b2703e7fb27df35f1b1b1a17063b9b10d2267acba593fc3872b62af6`；十阶段统计仍为 `5` 完成、`2` 部分完成、`3` 未开始。

## REQ-BF3D-INT40-R0-TRUTH-BACKTEST-INPUT-GATE-20260719

- 需求：在不把前端合同测试、输入传感器或当前启发式输出冒充真值的前提下，为 INT-40 建立独立参考、历史回测、经验不确定性和适用范围的输入门。
- 输入锁：[input_lock.json](../PT/高炉3D模型/work/INT_40_20260719_R0_TRUTH_BACKTEST_INPUT_GATE/input_lock.json)记录估计器、YAML、8767、Three.js、测试/报告、数据源审计和正式 GLB 的字节数/SHA；正式 GLB 仍为 `808960f1...b62af6`。
- 参考合同：[label_contract.md](../PT/高炉3D模型/work/INT_40_20260719_R0_TRUTH_BACKTEST_INPUT_GATE/label_contract.md)只接受独立现场测量、炉役解剖、盲态专家弱标签或版本化离线物理场，并规定坐标、标高、单位、知识时间、不确定度、版本和 SHA；禁止当前估计器循环生成标签。
- 审计事实：[软熔带数据源只读核查](软熔带数据源只读核查_20260719.md)证明 L7～L13 温度、18 静压力、DP/PI、风氧煤、顶温顶压、料线及部分布料/冷却信号可读，但这些是输入而不是软熔带真实位置标签。
- 阻断：[blocked_no_accepted_reference.json](../PT/高炉3D模型/work/INT_40_20260719_R0_TRUTH_BACKTEST_INPUT_GATE/blocked_no_accepted_reference.json)为 `blocked_no_accepted_reference`；因此没有生成 dataset/split、封存集回放、准确率、经验覆盖率或适用范围。
- 状态：只阻断 INT-40 R0 子阶段，不把线程总目标标为 blocked；当前 C2 继续固定 `estimated/uncalibrated/control_use=prohibited/confidence<=0.45`。INT-40 未完成，INT-50 未开始，正式库/模型/GLB 均未改。

## REQ-BF3D-R2R-RENDERER-NUMERIC-AB-20260719

- 需求：以捕获前冻结、fail-closed 的合同验证 R2Q V3 在 Blender Eevee/Cycles 和 Three.js/Eevee 之间的相机、轮廓、亮度、材质族和重复性；任何必需指标失败、未评估或合同不匹配都不得写成通过。
- 阶段：[WEB-60 R2R](../PT/高炉3D模型/work/WEB_60_20260719_R2R_RENDERER_NUMERIC_AB_GATE/)；权威状态为 [pipeline_status.json](../PT/高炉3D模型/work/WEB_60_20260719_R2R_RENDERER_NUMERIC_AB_GATE/pipeline_status.json)。
- 程序：[Blender 捕获器](../tools/render_bf3d_r2q_ab_blender.py)、[数值比较器](../tools/compare_bf3d_r2q_ab.py)、[Three.js 合同预检/捕获器](../tools/capture_bf3d_r2q_ab_three.cjs)。
- 冻结合同：[capture_contract.json](../PT/高炉3D模型/work/WEB_60_20260719_R2R_RENDERER_NUMERIC_AB_GATE/capture_contract.json)在成功捕获前登记 `1920×1080`、RGBA、固定正交相机、P40 四灯、AgX/0 EV、三 shot、两 repeat、Eevee64/OptiX Cycles48、beauty+mask、无 CPU 回退和禁止改阈值。
- Blender 证据：[capture_manifest.json](../PT/高炉3D模型/work/WEB_60_20260719_R2R_RENDERER_NUMERIC_AB_GATE/capture_manifest.json)记录 `12/12` 捕获；[comparison_report.md](../PT/高炉3D模型/work/WEB_60_20260719_R2R_RENDERER_NUMERIC_AB_GATE/comparison_report.md)记录 `80` 必需指标为 `68 pass / 12 fail / 0 not-evaluated`。失败为四个结构亮度 SSIM 和四材质族×两 repeat 的八个相对亮度项。
- Three.js 证据：[three_contract_preflight.json](../PT/高炉3D模型/work/WEB_60_20260719_R2R_RENDERER_NUMERIC_AB_GATE/reports/three_contract_preflight.json)为 `13 pass / 8 fail / 2 blocked`；[three_capture_manifest.json](../PT/高炉3D模型/work/WEB_60_20260719_R2R_RENDERER_NUMERIC_AB_GATE/reports/three_capture_manifest.json)明确 `capture_attempted=false`、beauty/mask `0`、`ab_pass_claimed=false`。阻断为生产透视动态构图、缺顶部 Area/RectAreaLight/固定光向，以及 ACES/exposure `1.05` 与 AgX/0 EV 不等价。
- 独立复审：[规格复审](../PT/高炉3D模型/work/WEB_60_20260719_R2R_RENDERER_NUMERIC_AB_GATE/reviews/R2R_INDEPENDENT_SPEC_REVIEW.md)为 `FAIL_CONFIRMED`；[视觉复审](../PT/高炉3D模型/work/WEB_60_20260719_R2R_RENDERER_NUMERIC_AB_GATE/reviews/R2R_INDEPENDENT_VISUAL_REVIEW.md)为 `PASS_REVIEW_OF_FAIL`，只确认失败有效。
- 历史锁：正式 GLB 及 R2Q Blend/三份 GLB SHA 均未改变；无生产源文件改写，未放宽阈值。
- 后续：`WEB-60 R2S` 只能增加隔离审查捕获相机、补齐锁定 P40 四灯、预先批准色彩管理等价合同并逐变量修正后复跑原阈值；如改资产必须新版本和新 SHA。

## REQ-BF3D-R2S-RENDERER-CONTRACT-ALIGNMENT-20260720

- 需求：在不改变生产 Three.js 观察体验的前提下，将 R2R 冻结正交相机、P40 四灯和原阈值转为受控审查合同；色彩与光度未预批准时必须停止图像捕获。
- 输入锁：[input_lock.json](../PT/高炉3D模型/work/WEB_60_20260719_R2S_RENDERER_CONTRACT_ALIGNMENT/input_lock.json)已由根代理复算 `22/22` bytes/SHA 匹配；实施前控制器 SHA 为 `4b9e6867…bafb3aa6`。
- 程序：[Web 控制器](../高炉前端数据/assets/bf3d-structural-review.js)新增双门控 `getAuditCaptureCapability/getAuditShotManifest`；[硬化专项验证器](../tools/verify_bf3d_r2s_audit_contract.cjs)在真实生产 HTML 和合成 harness 上验证双门、三 shot、四灯、TOP 代理、13 阈值、递归冻结、输入锁和生产运行时无副作用。
- 门控：只有 URL `bf3d_test_capture=WEB-60_R2S` 与模块加载前 `window.__BF3D_TEST_CAPTURE_TOKEN__="WEB-60_R2S"` 同时成立时返回数值 manifest；默认、单门、错误令牌和迟注入均禁用。
- 捕获边界：[色彩决定](../PT/高炉3D模型/work/WEB_60_20260719_R2S_RENDERER_CONTRACT_ALIGNMENT/color_management_decision.json)和[光度决定](../PT/高炉3D模型/work/WEB_60_20260719_R2S_RENDERER_CONTRACT_ALIGNMENT/photometric_mapping_decision.json)均为 `pending_preapproval`；`captureEligible=false`，未实现 beauty/mask。
- 诊断：[Blender 光传输诊断](../PT/高炉3D模型/work/WEB_60_20260719_R2S_RENDERER_CONTRACT_ALIGNMENT/blender_transport_diagnosis.md)记录高金属薄层偏暗主要来自 Eevee/Cycles 的环境反射、间接镜面、GI 与阴影语义差异，不是贴图丢失。
- 增量身份：[implementation_delta_manifest.json](../PT/高炉3D模型/work/WEB_60_20260719_R2S_RENDERER_CONTRACT_ALIGNMENT/implementation_delta_manifest.json)记录控制器后 SHA `d99b6d8f…cb90b206`；生产页面、正式 GLB 和 R2Q Blend/三 GLB 均未改变。
- 验证：[r2s_audit_contract_verification.json](../PT/高炉3D模型/work/WEB_60_20260719_R2S_RENDERER_CONTRACT_ALIGNMENT/r2s_audit_contract_verification.json)为硬化 PASS：真实生产页和 harness 各 `9` 组负向门、两个独立 full-ready 上下文、应用脚本前 instrumentation、4 RAF + `450ms` 延迟快照、`22/22` 输入锁、`12` 捕获记录、`124/40` 个递归冻结对象、`12/12` 次突变拒绝、生产审计副作用 `0`；根代理最终版本独立复跑 `2/2 PASS`。验证器为 `112147` bytes、SHA `53b27a0e…5b20a9f`。原专项 PASS、矩阵 `17/17 PASS`、本机 Edge `4/4 PASS`、旧切面回归 PASS。
- 状态：`approval_granted=false`、`next_stage_allowed=false`；现场 Edge、P50/P60/P70/QA-70、Blender `80/80` 复跑和 Three.js/Eevee 数值门均待完成。

## REQ-BF3D-R2T-OCIO-PHOTOMETRIC-EQUIVALENCE-20260720

- 需求：把“V3 材质存在但 Web 中偏暗/发灰/层次压平”拆成可独立拒绝的色彩管理与光度映射合同；不以提高曝光、改 BaseColor 或逐灯调参伪造 Blender/Three 等价。
- 根因：[材质可见性诊断](../PT/高炉3D模型/work/WEB_60_20260720_R2T_OCIO_PHOTOMETRIC_EQUIVALENCE/material_visibility_diagnosis.md)记录用户截图选择的是旧 `structural_review.v1.glb`、尚未完成导入，且 Blender 仍处于 Solid/实体模式；8092 总览当前默认请求也仍是旧 V1，V3 只在点击“纯材质审查/结构剖面”后懒加载。V3 主资产实有 `13` 个 PBR 材质、`39` 个 texture、`21` 个 image，forbidden 对象为 `0`；默认画面的旧测点、环线和竖向辅助结构不能用于判定 V3 清理失败。生产 Web 审查仍是三 SUN + AmbientLight、`scene.environment=null`、无 TOP Area、ACES `1.05`，所以不是 Blender P40/AgX 等价路径。
- 输入锁：[input_lock.json](../PT/高炉3D模型/work/WEB_60_20260720_R2T_OCIO_PHOTOMETRIC_EQUIVALENCE/input_lock.json)冻结 `19` 个 R2S/R2R/R2Q/Three/Blender/OCIO 输入；缺失或 mismatch 必须新阶段/new SHA。
- 程序：[OCIO 生成器](../tools/generate_bf3d_r2t_ocio_assets.py)、[OCIO 独立验证器](../tools/verify_bf3d_r2t_ocio_assets.py)、[R2T 阶段验证器](../tools/verify_bf3d_r2t_stage.py)、[WebGL oracle 验证器](../tools/verify_bf3d_r2t_ocio_webgl.cjs)、[LTC runtime oracle 验证器](../tools/verify_bf3d_r2t_ltc_runtime.cjs)。
- 色彩资产：[color_management_candidate.json](../PT/高炉3D模型/work/WEB_60_20260720_R2T_OCIO_PHOTOMETRIC_EQUIVALENCE/color_management_candidate.json)固定 Blender 5.2 / PyOpenColorIO 2.5 processor `cb6dc6defbf01d33b84718a55c277f0a`；生成 `14155` bytes GLSL SHA `8e90dd51…494ac`，以及 37³/57³ RGB32F、RGBA32F LUT。`235846` 个 texel 位序/alpha 全量检查，8 个 CPU oracle 最大误差 `4.886817894789175e-10`；Three r160 内建默认 AgX 不作为等价替代。
- 光度合同：[photometric_calibration_contract.json](../PT/高炉3D模型/work/WEB_60_20260720_R2T_OCIO_PHOTOMETRIC_EQUIVALENCE/photometric_calibration_contract.json)预注册一个 family 一个非负标量：SUN `I=k_sun*E`、TOP `I=k_area*P/(πA)`，`k=1` 时 TOP `1.3275510357953`，world `L=k_env*C*S`；禁止按灯/材质/shot/browser 拟合。原生 Three 无 8° SUN、RectArea 阴影，因此不宣称完整等价。
- LTC 供应链：[vendor_three_r160_rect_area_ltc.py](../tools/vendor_three_r160_rect_area_ltc.py)从 three.js 固定 commit `d04539a…c548` 取证并验证官方 addon `313854` bytes/SHA `08085bc9…214`，同时受控保存 Three MIT 和 selfshadow LTC BSD-style/论文引用许可证；[vendor.lock.json](../高炉前端数据/libs/three/vendor.lock.json)固定 Three core、npm、commit、运行和 fail-closed 合同。供应商 verify-only PASS。
- LTC runtime oracle：[ltc_runtime_oracle_report.json](../PT/高炉3D模型/work/WEB_60_20260720_R2T_OCIO_PHOTOMETRIC_EQUIVALENCE/reports/ltc_runtime_oracle_report.json)记录 `node tools/verify_bf3d_r2t_ltc_runtime.cjs` PASS；Chromium、Firefox、WebKit 各两次新鲜运行，合计 `6/6 PASS`。六次均解析到同一 Three r160 ESM，有效 addon init 固定为 `1`，显式重复探针在进入 addon 前被拒绝；四张 `64×64` texture 的类型、payload 和 SHA 全通过：`LTC_FLOAT_1=cf5cf21e5c112d2095c7e2418cb0a1ac54636e275d73e42f3453646c67f26814`、`LTC_FLOAT_2=3b1b09080b26104498db277c14fc1733786465c6958e7a8403d688b1e24c2ff5`、`LTC_HALF_1=a391de32f868fd4aa8774917b793174b7be804c08e2fb8924c30f31d7aa8dcd7`、`LTC_HALF_2=fa1ecbc6deb3c85ddf603cdf1e98e30279444f905eb1cebb849d761b570dd696`；所有运行实际选择 `float` 分支。
- LTC fixture：单 RectAreaLight + `metalness=1` MeshStandardMaterial 平面，在无 environment、无 AmbientLight、无 emissive 的条件下点亮结果非黑；零强度控制为黑，同一引擎页内重复及两次独立运行字节一致；console/page/HTTP/external 四类错误均为 `0`。该 PASS **只批准隔离 LTC runtime prerequisite**，批准状态仍为 `candidate_not_approved`（报告顶层 `status=runtime_prerequisite_verified_candidate_not_approved`）；不证明 Blender/Three 光度等价，不证明 RectAreaLight 阴影，不解除 capture、production integration 或 next stage。
- 光度 fixture：[冻结定义](../PT/高炉3D模型/work/WEB_60_20260720_R2T_OCIO_PHOTOMETRIC_EQUIVALENCE/photometric_fixture/fixture_definition.json)为 `103102` bytes、SHA-256 `8d43067c8875c4e677330e830eda079b841d5d8a6fad05f13b26200f349bbcfd`，在 renderer 启动前冻结且 mismatch fail-closed。Blender Cycles 参考 `67/67`、Eevee WORLD held-out `8/8`、Three Chromium/Firefox/WebKit 各两次共 `6/6`，错误为 `0`。
- 光度 fit/held-out：[结果报告](../PT/高炉3D模型/work/WEB_60_20260720_R2T_OCIO_PHOTOMETRIC_EQUIVALENCE/reports/photometric_fit_held_out_report.json)得到 `k_sun=0.9414175269608743`、`k_area=0.9450029255130412`、`k_env=0.9299202953495894`，三个 WLS 分母分别为 `0.055471528149193094`、`0.0910057735916505`、`0.0019578534604496323`，均非零。fit 与 held-out 已执行且没有回用 held-out 拟合，但未预注册线性接受阈值；[独立验证报告](../PT/高炉3D模型/work/WEB_60_20260720_R2T_OCIO_PHOTOMETRIC_EQUIVALENCE/reports/photometric_verification_report.json)只能记为 `candidate_evidence_verified_not_approved`，`photometric_equivalence_approved=false`、`capture_eligible=false`、`production_integration_allowed=false`。DISK→equal-area square 为已记录的 known non-equivalence，不能用残差报告改写成等价。
- 测试：Blender bundled Python 生成与独立验证 PASS；`python -m py_compile tools/generate_bf3d_r2t_ocio_assets.py tools/verify_bf3d_r2t_ocio_assets.py tools/verify_bf3d_r2t_stage.py` PASS；`python tools/verify_bf3d_r2t_stage.py` 为 19 锁项、6 色彩资产、8 oracle、光度候选和正式 GLB 全 PASS。
- WebGL oracle：[ocio_webgl_oracle_report.json](../PT/高炉3D模型/work/WEB_60_20260720_R2T_OCIO_PHOTOMETRIC_EQUIVALENCE/reports/ocio_webgl_oracle_report.json)已在隔离页执行 Chromium、Firefox、WebKit。exact generated shader 为 `2 PASS / 1 FAIL`：Chromium、WebKit 通过，Firefox 黑点 RGBA32F 返回 `0`，而 CPU oracle 约为 `0.0002386`（最大误差 `0.000238734 > 2e-5`）；其余 7 点和全部默认 framebuffer RGBA8 通过，因此 exact 硬门整体 FAIL。literal-nextafter 候选同为 `2 PASS / 1 FAIL`、整体 FAIL；共享 highp uniform `0x00800001` 候选为 `3/3 PASS`，且非黑点副作用门通过，但状态仍为 `candidate_not_approved`，不能覆盖或满足 exact 硬门。
- 复验命令：`node tools/verify_bf3d_r2t_ocio_webgl.cjs`；当前预期退出码为 `1`，原因是 exact release hard gate 失败，不得把 uniform candidate 的通过改写成验证器整体通过。
- 隔离审查：[独立页面](../高炉前端数据/bf3d_review.server.html)只加载 `gl02_blast_furnace_review.v3.glb`（SHA-256 `7e4b3b95343103784500aba354a124262ecf593fe89a3f0aa98348692152574b`），通过 `response.arrayBuffer()` 完整消费资产，拥有独立 Scene/Renderer/Camera/RAF，固定审查“纯材质审查、内部层近景、结构剖面”。最终 [arrayBuffer ×2 稳定性主日志](../PT/高炉3D模型/work/WEB_60_20260720_R2T_OCIO_PHOTOMETRIC_EQUIVALENCE/preview/root_arraybuffer_stability_x2.stdout.log)汇总[第 1 轮](../PT/高炉3D模型/work/WEB_60_20260720_R2T_OCIO_PHOTOMETRIC_EQUIVALENCE/preview/bf3d_review_stability_run_1.json)与[第 2 轮](../PT/高炉3D模型/work/WEB_60_20260720_R2T_OCIO_PHOTOMETRIC_EQUIVALENCE/preview/bf3d_review_stability_run_2.json)：连续两轮各 `17/17`、`51` 图，合计 `34/34` viewport runs、`102` captures；`34/34` 的 review GLB 均 `requestfinished=1`、`request_failed=0`，console/page/HTTP/external/request_failed 五类错误累计 `0`。外表面横向变化是 R2J 五区实体交界/原始纹理，不是数据圆环或引线；底部深色楔是现有 V3 GLB 十个 Section 封口面共面叠合/遮挡，不是内腔，Web 未改写该几何。
- 边界：[pipeline_status.json](../PT/高炉3D模型/work/WEB_60_20260720_R2T_OCIO_PHOTOMETRIC_EQUIVALENCE/pipeline_status.json)继续保持 `capture_eligible=false`、`approval_granted=false`、`next_stage_allowed=false`；独立 V3 页面已解决 `E/illustrative`、`REF-PENDING` 的只读材质/结构可见性，但光度 fit/held-out、LTC 与 OCIO 均未批准 photometric equivalence 或 production。exact OCIO 仍为 `2 PASS / 1 FAIL`、整体硬门 FAIL，uniform workaround 仍为 `candidate_not_approved`；还需 OCIO/AgX LUT 专属许可、炉体 A/B 和发布门。正式 GLB SHA-256 仍为 `808960f1b2703e7fb27df35f1b1b1a17063b9b10d2267acba593fc3872b62af6`，8092 生产默认 V1 仍未修复或替换；十阶段统计仍为 `5` 完成、`2` 部分完成、`3` 未开始。

## REQ-BF3D-R2U-SECTION-CAP-CONTROLLED-V4-20260720

- 需求：清除 V3 结构剖面的跨炉膛封口叠合、旧黑色楔形、圆环和竖线遮挡；继续使用受控
  R5/R2J/R2K 材质，交付统一 V4 Web GLB、纯材质 GLB、结构剖面 GLB及可直接打开的
  Blend；纯材质审查必须隐藏传感器、引线、黄色轮廓和工艺粒子。
- 根因：用户截图选中历史 `structural_review.v1.glb` 且尚未执行“导入 glTF 2.0”，
  Blender 仍处于 Solid/实体模式；独立 V3 几何审计同时确认十个 Section 封口存在
  `18` 对、`87.53379024081863 m²` 共面重叠。
- 程序：[V3 审计](../tools/audit_bf3d_v3_section_caps.py)、
  [封口操作探针](../tools/probe_bf3d_v3_section_cap_fill_ops.py)、
  [V4 导出/验证器](../tools/export_bf3d_structural_review_v4.py)、
  [Khronos Validator 封装](../tools/validate_bf3d_glb_khronos.cjs)、
  [V4 Web 构建器](../tools/build_bf3d_review_v4_web.py)、
  [只读服务器](../tools/serve_bf3d_review_v4.py)和
  [跨浏览器验证器](../tools/verify_bf3d_review_v4_preview.cjs)。
- 资产：统一 GLB `4,275,268` bytes/SHA
  `e46508bcecc8fef76510a0b889e0598ad3cb2289cc00f6b99566c78e3ed3afd2`；纯材质 GLB
  `993,224` bytes/SHA `6ad5e9dc51a10259d41d0f4d55391bddc262e482da36e4a9a082e268e27e93f6`；
  结构 GLB `3,558,868` bytes/SHA
  `3299bfeceaceea51559c3b41cfc7782dfa3fa61d33501fa80e6d5590ee679d47`；V4 Blend
  `37,073,211` bytes/SHA
  `86bce712181ac0771ed460806f54b072659fd8f854334bd0a1ddf73b4e15c9c1`。
- 几何/材质：`5` 个外表面对象、`10` 个闭合正体积剖面对象，boundary/non-manifold
  均为 `0`、封口重叠 `0`；六类内部 PBR 材质，forbidden 角色为 `0`。
- 测试：Blend 重开、三 GLB factory import、正确 SHA 绑定的独立验证和负向自测 PASS；
  Khronos 三资产 `0 errors`、warning `21/0/21`；独立视觉 PASS；规范对 R2U PASS、
  对 P60 CONDITIONAL；前端资产确认 Three r160/GLTFLoader/EXT_texture_webp、相机与
  资源释放 PASS，但纹理解码约 `264/192/264 MiB`；跨浏览器两轮 `34/34` runs、
  `102` captures，五类错误 `0`。
- 证据：[根审查结论](../PT/高炉3D模型/work/WEB_60_20260720_R2U_SECTION_CAP_CONTROLLED_V4/WEB-60_R2U_根审查结论.md)、
  [独立结论](../PT/高炉3D模型/work/WEB_60_20260720_R2U_SECTION_CAP_CONTROLLED_V4/reports/independent_review_decisions.json)、
  [浏览器报告](../PT/高炉3D模型/work/WEB_60_20260720_R2U_SECTION_CAP_CONTROLLED_V4/reports/bf3d_review_v4_preview_report.json)。
- 边界：R2U 仅为 `E/illustrative`、`REF-PENDING` 的只读审查候选。42 条 tangent
  warning、三资产各四条本机绝对路径 extras、解码内存/真机性能、R1/R5 AO、生产
  8092、P50/P60/P70/QA-70、现场 Edge、长稳与数值光度等价仍阻塞；正式 GLB及
  生产数据均未改变。
| `OPS-VASTBASE-PSPACE-22012-DEFAULT-20260720` | 固定本机访问 Vastbase 与 pSpace 时默认经 220.12 跳板，并优先使用既有只读脚本和 MCP | [长期规则](../AGENTS.md)、[转发脚本](../tools/imes_22012_relay.py)、[Vastbase MCP](../高炉前端数据/智能助手/mcp/imes_relay_mcp_server.py)、[pSpace MCP 查询](../高炉前端数据/智能助手/mcp/gl02_remote_22012_pspace_query.py)、[远端执行](../tools/remote_22012_exec.py) | Vastbase：`127.0.0.1:15433 -> 220.12 -> 10.10.181.195:5432`；pSpace：220.12 本机 PythonSDK，或 `127.0.0.1:18889 -> 220.12 -> 10.22.181.243:8889` | 文档静态核对；不启动转发、不访问生产数据、不修改服务 | 仅当程序运行在 220.12 上或用户明确要求专项直连对照时允许例外；必须记录实际链路和原因 |

## REQ-BF3D-R2V-GLTF-PORTABILITY-TANGENT-BUDGET-20260720

- 需求：在 R2U V4 已清除黑楔、旧圆环和竖向辅助对象的基础上，消除 Web GLB 的本机
  绝对路径与生成切线 warning，保留 R5/R2J/R2K 材质、5 个完整炉壳和 10 个闭合
  物理剖面，并复验“纯材质审查/结构剖面”。
- 程序：[V5 导出器](../tools/export_bf3d_structural_review_v5.py)、
  [可移植性审计](../tools/audit_bf3d_glb_portability.py)、
  [切线诊断](../tools/diagnose_bf3d_v4_tangent_uv.py)、
  [Khronos 封装](../tools/validate_bf3d_glb_khronos.cjs)、
  [V5 Web 构建器](../tools/build_bf3d_review_v5_web.py)、
  [只读服务器](../tools/serve_bf3d_review_v5.py)、
  [跨浏览器验证器](../tools/verify_bf3d_review_v5_preview.cjs)和
  [失败关闭收口器](../tools/finalize_bf3d_review_v5.py)。
- 受控改动：10 个 Section 只做确定性三角化；4 个场景 provenance 值改为工作区相对
  POSIX 路径；只为 3 个未定义几何切线顶点生成法线正交回退。统一 GLB 与结构 GLB
  各写 3 个向量，共 6 次写入；有效非零切线未重归一化。
- 资产：统一 GLB `4,663,220` bytes/SHA
  `0ac031e626c9eaa0b0cdd8192cf9fda712324af174a4285f563a97309451ed3c`；
  纯材质 GLB `994,372` bytes/SHA
  `652be1b2c9147d5a7392497c7ae4964d19bdd7095b5435b87c105f9eb3fb66bc`；
  结构 GLB `3,945,984` bytes/SHA
  `e5c77d3834c631e2513209a690f6328d1c63dba2c8d489b2d2dbe17645465f71`；
  V5 Blend `37,121,148` bytes/SHA
  `3e6df5fb02d3734d14923d4432739a5918ac8249d6a3c8ad1415395429b27e3a`。
- 验证：V4→V5 的 10 个对象顶点位置、包围盒、材质槽、UV 边界和材质/内嵌图像身份
  保持；10/10 闭合正体积，boundary/non-manifold/跨对象封口重叠均为 `0`；三份
  GLB 的绝对路径、缺失切线风险、无效切线 accessor 均为 `0`；Khronos 均为
  `0 errors / 0 warnings`。
- Web：[V5 隔离页](../高炉前端数据/bf3d_review_v5.server.html)连续两轮覆盖
  Chromium 9 个固定视口、Firefox 4 个、WebKit 4 个，共 `34/34` runs、
  `102` captures，console/page/HTTP/external/request-failed 均为 `0`。
- 独立结论：R2V 静态审查范围 PASS with conditions；外表面全景对比偏弱，内部
  锈红/浅棕层间有一条物理遮挡窄缝，生产前应弱化或标注。它不是旧数据竖线。
- 证据：[根审查](../PT/高炉3D模型/work/WEB_60_20260720_R2V_GLTF_PORTABILITY_TANGENT_BUDGET/WEB-60_R2V_根审查结论.md)、
  [V5 manifest](../高炉前端数据/models/gl02_blast_furnace_review.v5.manifest.json)、
  [独立审查](../PT/高炉3D模型/work/WEB_60_20260720_R2V_GLTF_PORTABILITY_TANGENT_BUDGET/reports/independent_review_decisions.json)和
  [完整 Web 报告](../PT/高炉3D模型/work/WEB_60_20260720_R2V_GLTF_PORTABILITY_TANGENT_BUDGET/reports/bf3d_review_v5_preview_report.json)。
- 边界：三资产解码约 `720 MiB` RGBA8、完整 mip 约 `960 MiB`；现场/移动端性能、
  R5 AO 消费、P50/P60/P70/QA-70、生产 8092、现场 Edge、长稳与 Blender/Three
  数值光度等价仍阻塞。正式 GLB SHA 保持
  `808960f1b2703e7fb27df35f1b1b1a17063b9b10d2267acba593fc3872b62af6`。

## REQ-BF3D-R2W-MATERIAL-READABILITY-CAMERA-20260720

- 用户问题：V5 虽已保留具体 PBR 材质和内部物理层，为什么仍像普通灰色、内部黑线
  又应如何解释。
- 预注册：[R2W 合同](../PT/高炉3D模型/work/WEB_60_20260720_R2W_MATERIAL_READABILITY_AO_EDGE/WEB-60_R2W_阶段预注册合同.md)
  将工作拆成相机可读性、AO 消费和 L03→L04→L05 相邻层三条独立证据链；镜头 PASS
  不得替代 AO、P50 或结构连续性 PASS。
- 程序：[AO 只读审计](../tools/audit_bf3d_r2w_ao_consumption.py)、
  [相邻层只读审计](../tools/audit_bf3d_r2w_interface_gap.py)、
  [隔离页构建器](../tools/build_bf3d_review_r2w_web.py)、
  [只读服务器](../tools/serve_bf3d_review_r2w.py)、
  [跨浏览器验证器](../tools/verify_bf3d_review_r2w_preview.cjs)和
  [失败关闭收口器](../tools/finalize_bf3d_r2w_stage.py)。
- 实现：[R2W 隔离页](../高炉前端数据/bf3d_review_r2w.server.html)和
  [R2W 渲染器](../高炉前端数据/assets/bf3d-review-renderer-r2w.js)只新增外表面材质
  近景及相机框景；GLB、Blend、纹理、PBR 材质、灯光、曝光、环境、Tone Mapping
  和正式 8092 均未改变。
- Web 验证：[完整报告](../PT/高炉3D模型/work/WEB_60_20260720_R2W_MATERIAL_READABILITY_AO_EDGE/reports/bf3d_review_r2w_preview_report.json)
  连续两轮覆盖 Chromium 9 个视口、Firefox 4 个、WebKit 4 个，共 `34/34` runs、
  `136` captures，console/page/HTTP/external/request-failed 均为 `0`；
  `protected_files_unchanged=true`，PBR 改写、禁止对象和黄色轮廓均为 `0`。
- 独立视觉结论：[复核记录](../PT/高炉3D模型/work/WEB_60_20260720_R2W_MATERIAL_READABILITY_AO_EDGE/reports/independent_review_decisions.json)
  只条件批准相机可读性候选。外表面近景可读但仍显平，内部材质族可区分，未发现旧
  圆环、装饰性竖线或其他禁止对象。
- AO 结论：[AO 报告](../PT/高炉3D模型/work/WEB_60_20260720_R2W_MATERIAL_READABILITY_AO_EDGE/reports/ao_consumption_audit.json)
  证明当前 ORM.R 全部为 `255`，V5 glTF 无 `occlusionTexture`，Blend ORM.R
  未接入；旧 P50 R3 的 `P50_UV0/APPROX_GL02_*` 与当前 R2J UV/对象不兼容，
  禁止直接复用。`audit_passed=true` 只表示缺失事实审计完成，
  `ao_consumption_ready=false`。
- 结构结论：[相邻层报告](../PT/高炉3D模型/work/WEB_60_20260720_R2W_MATERIAL_READABILITY_AO_EDGE/reports/interface_gap_audit.json)
  证明 L03 为 `z=-20…7.55 m`、L04 为 `z=16…20 m`，共同高度、重叠和覆盖率为
  `0`；相邻层链不可测，`adjacent_layer_continuity_passed=false` 且需要权威
  设计参考。L03→L05 的 `14.816–49.456 mm` 只是非相邻诊断，`z=-1.2 m`
  异常是冷却壁拼缝/端面剖切诊断。
- 文档：[阶段总结](../PT/高炉3D模型/work/WEB_60_20260720_R2W_MATERIAL_READABILITY_AO_EDGE/WEB-60_R2W_阶段成果总结.md)和
  [根审查](../PT/高炉3D模型/work/WEB_60_20260720_R2W_MATERIAL_READABILITY_AO_EDGE/WEB-60_R2W_根审查结论.md)
  固定状态 `r2w_camera_readability_passed_ao_and_structure_blocked`。
- 发布边界：只批准 `E/illustrative`、`REF-PENDING` 的隔离镜头可读性候选。
  AO、相邻层连续性、施工尺寸、P50/P60/P70/QA-70、正式 GLB、生产 8092、现场
  Edge/性能/长稳和 Blender/Three 数值光度等价均未批准。

## REQ-BF3D-R2X-R2J-AO-REBAKE-CONSUMPTION-20260720

### Requirement / program / config

| 追踪项 | 受控记录 |
|---|---|
| Requirement | 为当前 R2J 五区炉壳建立独立 UV2 和 1K 局部接触 AO，只先验证 Blender/GLB/Three.js 是否正确生成、绑定和消费；代表视觉通过前不得运行完整矩阵或升级 2K。 |
| Program | [1K 候选构建器:L2243](../tools/build_bf3d_r2x_r2j_ao_candidate.py#L2243)、[V5 payload 重打包器:L2202](../tools/repack_bf3d_r2x_ao_v5_payload.py#L2202)、[独立审计器:L3787](../tools/audit_bf3d_r2x_ao_candidate.py#L3787)、[Web 构建器:L221](../tools/build_bf3d_review_r2x_web.py#L221)、[隔离服务:L305](../tools/serve_bf3d_review_r2x.py#L305)、[代表验证器:L990](../tools/verify_bf3d_review_r2x_preview.cjs#L990)、[阶段收口器:L2128](../tools/finalize_bf3d_r2x_stage.py#L2128)。 |
| Config / contract | [R2X 预注册合同](../PT/高炉3D模型/work/WEB_60_20260720_R2X_R2J_AO_REBAKE_CANDIDATE/WEB-60_R2X_阶段预注册合同.md)固定五个炉壳、`TEXCOORD_2 → uv2`、`aoMap.channel=2`，BaseColor/Normal/Roughness/Metalness 继续使用 channel `0`；off/on 只允许把 `aoMapIntensity` 从 `0` 切到导入值 `1`。页面必须标记 `1K smoke / E illustrative / not P50 / not production`。不新增 API、数据库、schema 或生产配置。 |

### Artifact / test evidence

- 最终受控候选为
  [gl02_blast_furnace_material_review.r2x-ao-smoke1k.v5payload.glb](../PT/高炉3D模型/work/WEB_60_20260720_R2X_R2J_AO_REBAKE_CANDIDATE/glb/gl02_blast_furnace_material_review.r2x-ao-smoke1k.v5payload.glb)，
  `1,115,216` bytes，SHA-256
  `bd074c23c237fe7ff3abac0f823bd9aef978021e4e829963b3f979e9b58f1c00`。
  [重打包报告](../PT/高炉3D模型/work/WEB_60_20260720_R2X_R2J_AO_REBAKE_CANDIDATE/reports/r2x_ao_v5_payload_repack_report.json)
  和
  [独立审计](../PT/高炉3D模型/work/WEB_60_20260720_R2X_R2J_AO_REBAKE_CANDIDATE/reports/r2x_ao_smoke1k_v5payload_audit.json)
  证明 UV2/AO 追加和 V5 非 AO payload 保持通过；Khronos
  [原始报告](../PT/高炉3D模型/work/WEB_60_20260720_R2X_R2J_AO_REBAKE_CANDIDATE/reports/khronos_gltf_validator_r2x_ao_v5payload.json)
  为 `0 errors / 0 warnings`。
- 首次重打包候选
  `c8b748ef03b516a78de658a3b25a5f2265fef9bd34cea334a3490fba1fbab139`
  越权追加第二个 clamp sampler，finding 为
  `UNAUTHORIZED_EXTRA_AO_CLAMP_SAMPLER`，已 `fail_closed`。该失败历史必须保留；
  最终候选改为复用锁定 V5 sampler `0`，sampler 数量保持 `1→1`。
- [代表 Three/视觉报告](../PT/高炉3D模型/work/WEB_60_20260720_R2X_R2J_AO_REBAKE_CANDIDATE/reports/bf3d_review_r2x_representative_report.json)
  记录 `machine_three_passed=true`：Chromium `1440×900` 完成全景 off/on、近景
  off/on 四张截图和两组配对，五类
  `console/page/http/external/request_failed` 错误均为 `0`。但两组
  `changed_pixels=0`，各自 off/on PNG SHA 完全相同，故
  `visual_gate_passed=false`。
- [独立视觉复核](../PT/高炉3D模型/work/WEB_60_20260720_R2X_R2J_AO_REBAKE_CANDIDATE/reports/r2x_independent_visual_review.json)
  的结论为 `fail_closed_ao_visual_signal_absent`。AO PNG 有 `99.6763%`
  像素为纯白，非白像素仅 `0.3237%`，当前代表视图没有可见 AO 信号。

### Decision / impact

- 阶段状态固定为 `r2x_machine_passed_three_visual_failed_closed`；
  `full_matrix_executed=false`，不升级 2K，不批准 P50/P60、正式 GLB、生产 8092
  或下一发布阶段。V5 与 formal 受保护资产哈希保持不变。
- AO 只是局部遮蔽乘子，不是“用户看不到具体材质”的完整修复。后续应回到可见的几何
  接触源、材质检视照明和近景模式，并取得权威结构参考；禁止用黑色圆环、装饰线或修改
  BaseColor 来伪造 AO/分层。最终边界见
  [R2X 根审查结论](../PT/高炉3D模型/work/WEB_60_20260720_R2X_R2J_AO_REBAKE_CANDIDATE/WEB-60_R2X_根审查结论.md)。

## REQ-BF3D-R2Y-MATERIAL-SIGNAL-VISIBILITY-DIAGNOSTIC-20260720

### Requirement / config

- [R2Y 预注册合同](../PT/高炉3D模型/work/WEB_60_20260720_R2Y_MATERIAL_SIGNAL_VISIBILITY_DIAGNOSTIC/WEB-60_R2Y_阶段预注册合同.md)
  把 `data present → visible texel hit → shader consumption → final 8-bit visibility`
  拆成四道独立门。范围固定为 `E/diagnostic`，不修改 V5、R2X、formal 或生产资产。
- 固定 Chromium `1440×900`、`960×540 @ DPR1`、Three.js r160、sRGB/ACES、
  `exposure=1`；代表门失败时禁止完整矩阵、2K、P50、P60 与生产。

### Program / artifact / test

- 输入锁：[verify_bf3d_r2y_input_gate.py](../tools/verify_bf3d_r2y_input_gate.py)。
- PBR 数据层：[audit_bf3d_r2y_pbr_texture_signal.py](../tools/audit_bf3d_r2y_pbr_texture_signal.py)。
- AO UV/相机/mip 层：[audit_bf3d_r2y_ao_uv_hit.py](../tools/audit_bf3d_r2y_ao_uv_hit.py)。
- 隔离运行层：[bf3d_review_r2y.server.html](../高炉前端数据/bf3d_review_r2y.server.html)、
  [bf3d-review-renderer-r2y.js](../高炉前端数据/assets/bf3d-review-renderer-r2y.js)、
  [serve_bf3d_review_r2y.py](../tools/serve_bf3d_review_r2y.py) 和
  [verify_bf3d_review_r2y_preview.cjs](../tools/verify_bf3d_review_r2y_preview.cjs)。
- [CPU 光栅报告](../PT/高炉3D模型/work/WEB_60_20260720_R2Y_MATERIAL_SIGNAL_VISIBILITY_DIAGNOSTIC/reports/r2y_ao_uv_hit_raster_audit.json)
  通过：全景/近景 mip 非白可见像素为 `785 / 6483`，排除当前审计视角下单纯的
  `uv_or_camera_miss`。AO WebGL 合成黑/浮点/8-bit liveness 未执行。
- [代表报告](../PT/高炉3D模型/work/WEB_60_20260720_R2Y_MATERIAL_SIGNAL_VISIBILITY_DIAGNOSTIC/reports/bf3d_review_r2y_representative_report.json)
  为 `23/26`：macro `0.962958 < 1`、anisotropy `1.021708 < 1.03`、
  environment changed ratio/mean diff 均为 `0`。五类浏览器错误均为 `0`，但
  `pbr_fixture_passed=false`、`full_matrix_executed=false`。
- 报告把三个通道明确区分为 `data_present=true`、`sampled=true`、
  `runtime_binding_present=true`、`consumed=null`、`visible=false`；原始统计与绑定
  不能替代逐通道 shader off/on 证明。

### Decision / impact

- [独立审查](../PT/高炉3D模型/work/WEB_60_20260720_R2Y_MATERIAL_SIGNAL_VISIBILITY_DIAGNOSTIC/reports/r2y_independent_review_decisions.json)
  发现 Normal 网格、Roughness 周期竖波和 beauty 平铺竖纹，结论为
  `fail_closed_material_signal_artifact_dominated_environment_nonobservable`。
- 根状态为 `r2y_cpu_hit_passed_pbr_visual_failed_ao_webgl_pending_fail_closed`。
  CPU 命中通过不代表 AO WebGL 可见；环境零差也不能直接归因为 PMREM wiring 故障。
  V5/R2X/formal/生产保持不变，权威边界见
  [阶段总结](../PT/高炉3D模型/work/WEB_60_20260720_R2Y_MATERIAL_SIGNAL_VISIBILITY_DIAGNOSTIC/WEB-60_R2Y_阶段成果总结.md)
  与[根审查](../PT/高炉3D模型/work/WEB_60_20260720_R2Y_MATERIAL_SIGNAL_VISIBILITY_DIAGNOSTIC/WEB-60_R2Y_根审查结论.md)。

## REQ-BF3D-STATIC-PRESSURE-18-PLACEMENT-20260721

### Requirement / program / data contract

| 追踪项 | 受控记录 |
|---|---|
| Requirement | 在用户认可的 P40 炉壳外观候选上增加三层、每层 A～F 的 18 个炉身静压力测量点；运行/测量审查可见，纯材质审查隐藏。同步补齐可用传感器数据集说明，禁止把旧三个平均代理复制为 18 个实测点。 |
| Data identity | 唯一语义 ID 为 `P_static_{lower|middle|upper}_{A-F}`，正式源分支为 `EQ/SI0/GL02/BT`。业务层名/标高固定为炉身下部 `20.350 m`、炉身中部 `23.488 m`、炉身上部 `28.976 m`；pSpace 原始描述另存为 `source_description_raw`。A～F 仅为相对顺序，固定 `orientation_status=relative_only`。逐点 Tag 见[静压力扩展目录](../高炉前端数据/智能助手/mcp/gl02_static_pressure_points.json)。 |
| Blender program | 隔离阶段构建器、源检查器和复开验证器位于 [VIS-30 scripts](../PT/高炉3D模型/work/VIS_30_20260721_STATIC_PRESSURE_18_PLACEMENT/scripts)。源 P40 showroom SHA-256 为 `722498eb60ad2a364c7d26fc8ae38977cbc0e45a4969c70c759303a84f89a7ef`；18 点几何从既有 INT-30 R1B R2 受控候选 append，未复制 P40 的三个汇总占位。 |
| Web program | [bf3d-internal-simulation.js](../高炉前端数据/assets/bf3d-internal-simulation.js)把 18 个 `measured/raw` 点拆为独立运行覆盖层；外观和剖面运行模式均可见，材质审查隐藏。`good/illustrative` 点位统一使用工业黄色 `#F2C94C` 身份色且不再按 `deviation_kpa` 改色，`stale` 使用明显变暗的黄色 `#8F7728`；`interpolated/periodic_interpolation` 色带与 `estimated` 偏流箭头仍属于剖面派生层。 |
| Dataset program | [build_hot_metal_si_dataset.py](../tools/build_hot_metal_si_dataset.py)只读本地静压力目录，为未来重建的数据字典补充 `semantic_id/business_level_name/height_m/position/orientation_status/source_description_raw/hmi_instrument_id_status/unit_status`；不改变宽表列名和值。说明见[铁水硅炉况传感器数据集](铁水硅炉况传感器数据集.md)和[8093 静压力同步合同](8093_MCP炉身静压力AF与PostgreSQL同步.md)。 |
| Count boundary | `115` 是正式 GLB 核心传感器节点合同；`133` 是同步目录物理点；`134` 是当前数据集构建时读取的启用注册点。18 个 A～F 点是独立动态 Overlay/数据特征，不改写 115 节点身份。 |
| API / DB / schema | 没有新增 API、数据库写入、schema 迁移或生产部署。现有 8767 `bf3d_snapshot.measured.static_pressure` 继续提供 18 点；本阶段没有连接生产库，也没有改写已有 CSV/Manifest。 |

### Runtime state / fail-closed behavior

- 点位中心按受控炉型半径外移 `0.12 m`；Blender Z 为工艺标高减 `20 m`，即
  `0.350 / 3.488 / 8.976 m`。绝对厂区零方位未对表，不输出东南西北。
- `good/illustrative` 点均以工业黄色 `#F2C94C` 身份色显示；`stale` 冻结最后有效值并以明显变暗的黄色 `#8F7728` 标陈旧；`missing` 或超过硬过期阈值隐藏。
- 点位身份色与 `deviation_kpa` 解耦；没有偏差值时，原始压力仍以黄色实测点显示，不再把约 300 kPa
  原值套入 `-12～+12 kPa` 偏差色标。同层 6 点全部有效且都有偏差值后，才允许
  生成有界插值带和估计偏流箭头；状态文案显示实际 `N/18`。
- HMI PE 仪表号存在冲突记录，单位 `kPa` 来自受控配置而现场源元数据为空；对应
  状态保持 `unconfirmed`，不得作为 Blender 稳定主键或声称已现场确认。

### Artifact / verification evidence

- 受控 Blender 候选：
  [VIS30_STATIC_PRESSURE_18_PLACEMENT_CANDIDATE.blend](../PT/高炉3D模型/work/VIS_30_20260721_STATIC_PRESSURE_18_PLACEMENT/blends/VIS30_STATIC_PRESSURE_18_PLACEMENT_CANDIDATE.blend)，
  SHA-256 `8f129ca5881a00d3ee6b06a45de3eebe06697d45f9e3f890f8addcf12c77d3aa`；18 点统一使用
  `MI_VIS30_STATIC_PRESSURE_INDUSTRIAL_YELLOW` / `#F2C94C` 身份材质；
  打开即进入 `STATIC_PRESSURE_ISOLATED_REVIEW` Scene/View Layer 和隔离全景相机。
- 独立 Web Overlay GLB：
  [VIS30_STATIC_PRESSURE_18_ONLY_OVERLAY.glb](../PT/高炉3D模型/work/VIS_30_20260721_STATIC_PRESSURE_18_PLACEMENT/glb/VIS30_STATIC_PRESSURE_18_ONLY_OVERLAY.glb)，
  SHA-256 `07b9e024bb994ac674d6238ed1743ef2c91f55f02a74517cdb3d93c8e73802fa`；重导入只含 18 个静压力点，
  `short_name/Tag/source_description_raw` 与权威目录逐点 `18/18` 匹配。
- [机器报告](../PT/高炉3D模型/work/VIS_30_20260721_STATIC_PRESSURE_18_PLACEMENT/reports/vis30_static_pressure_18_machine_report.json)
  与[重开验证](../PT/高炉3D模型/work/VIS_30_20260721_STATIC_PRESSURE_18_PLACEMENT/reports/vis30_static_pressure_18_reopen_validation.json)
  通过：`18=3×6`、精确高度/半径/相对角通过，旧三个代理隐藏，
  `STATIC_PRESSURE_REVIEW` 显示、`MATERIAL_REVIEW` 排除；新集合未新增黄色轮廓、
  圆周装饰环、长竖线或粒子。
- [隔离视觉证据](../PT/高炉3D模型/work/VIS_30_20260721_STATIC_PRESSURE_18_PLACEMENT/renders/VIS30_STATIC_PRESSURE_18_ISOLATED_CONTACT_SHEET.png)
  SHA-256 为 `549ddbaa4d23e8e6f0f4b90ca09804bbf06915b5cef8792cc3183a173d466eb5`：
  P40 材质全景已排除旧温度竖线、旧传感器和遮挡支撑；下/中/上三张 A～F
  证据图各有 6 个黄色点且 `level_tile_ring_count=0`。独立视觉复核批准为用户可见候选；
  二维标签只用于审查，不作为 GLB 运行标签。
- Web 合同测试：`node tools/verify_bf3d_internal_simulation.cjs` 通过；覆盖外观可见、
  材质审查隐藏、`good/illustrative` 黄色身份色与偏差色解耦、stale 深黄色冻结、missing/硬过期隐藏、每层 6 点门禁和
  `radiusAt(height)+0.12 m` 坐标。
- 跨浏览器/视口矩阵
  [cross_engine_viewport_report.json](../logs/bf3d_internal_simulation_20260719/matrix/cross_engine_viewport_report.json)
  为 `ok=true`：Chromium 9 个视口、Firefox 4 个、WebKit 4 个，共 `17` runs、
  `85` 路由组合；页面横向溢出、页面错误、console 错误和 HTTP 错误均为 `0`。
- 数据集离线回归：`pytest tests/test_build_hot_metal_si_dataset.py` 为 `5 passed`，
  Ruff 与 `py_compile` 通过；未连接生产数据库。
- 根 [pipeline_status.json](../reports/pipeline_status.json) 已登记为平行的
  `candidate_ready_for_review`，保留原 `current_stage`，不冒充正式发布阶段。

### Decision / impact

- 状态为 `candidate_ready_for_review`，且独立视觉复核已批准用户可见候选。本阶段批准
  P40 派生候选、独立 Overlay GLB、运行时18点显示与数据字典描述增强；不批准绝对
  厂区方位、施工定位、控制用途或正式发布。
- V5 纯材质审查 GLB、正式 115 节点 GLB、R2J/R2K、formal 资产和生产服务均未被
  覆盖。后续只有在现场完成 A～F 零方位、PE 仪表号和单位复核后，才可把
  `relative_only/unconfirmed` 升级为正式空间安装合同。
## 2026-07-24 WEB_60 img2threejs 外观原型浏览器验证

- 需求：`REQ-BF3D-IMG2THREEJS-PROTOTYPE-20260724`
- 程序：`tools/verify_bf3d_img2threejs_preview.mjs`
- 触发：手工执行；未注册计划任务，不属于自动值守。
- 输入：8096 只读静态页面、八层 DOM 合同和 Three.js 运行统计。
- 浏览器：Chromium 九个固定视口；Firefox/WebKit 各四个代表视口。
- 操作：风口层隐藏/恢复、展开/复位、灰模开关、风口聚焦、参考图折叠。
- 输出：`PT/高炉3D模型/work/WEB_60_IMG2THREEJS_20260724_R1/reports/browser_matrix.json|md` 和逐组合截图。
- 当前结果：`17/17` 通过，失败项、页面错误、控制台错误、资源失败和横向溢出均为 `0`。
- 数据库/API/生产写入：不适用；程序仅访问本机静态页面。
- 回滚：删除实验目录与本验证程序即可；正式 GLB、8092/8767 和数据库配置均未改动。

## 2026-07-24 WEB_60 img2threejs R2 语义细化浏览器验证

- 需求：`REQ-BF3D-IMG2THREEJS-SEMANTIC-DETAIL-R2-20260724`
- 程序：`tools/verify_bf3d_img2threejs_preview.mjs`
- 触发：手工执行；三浏览器并行运行；未注册计划任务，不属于自动值守。
- 输入：8096 只读静态页面、受控 `115/80/18/26/2` 数字合同和 `relative_only` 方位门禁。
- 浏览器：Chromium 九个固定视口；Firefox/WebKit 各四个代表视口。
- 操作：工艺区/L10/出铁口设备隐藏与恢复、80 点总控及单层禁用/启用、45% 展开/复位、灰模、风口/出铁口/进料口近景、参考图折叠。
- 输出：`PT/高炉3D模型/work/WEB_60_IMG2THREEJS_20260724_R1/reports/browser_matrix.json|md` 和逐组合截图。
- 当前结果：`17/17` 通过；运行统计为 `284` 网格、`599` 实例、`198,456` 三角面；失败项、页面错误、控制台错误、资源失败和横向溢出均为 `0`。
- 数据库/API/生产写入：不适用；程序仅访问本机静态页面。
- 回滚：恢复实验目录中的 `preview/` 和本验证程序即可；正式 GLB、8092/8767 和数据库配置均未改动。

## 2026-07-25 V4 8094 高炉本体资产热替换

- 需求：`REQ-BF3D-8094-FURNACE-BODY-ASSET-SWAP-20260725`；仅针对 V4 8094 预览，不改变 8093 生产页面。
- 守护程序：计划任务 `\BlastFurnaceServices\V3AutoPreviewProxy8094` → `tools\run_22012_8094_preview.ps1` → `ollama_proxy_server.py`；本次先停止任务并回收遗留的旧 8094 子进程，再启动同一任务。
- 资产：`GL02_FURNACE_BODY_R1.glb`；运行时点位清单 `sensor_billboards.v1.json`；正式传感器 `115`、静压力 `18`、合计 `133`。
- Web 程序：`高炉前端数据/assets/bf3d-furnace-body-billboard-adapter.js` 负责 manifest Billboard/拾取/live buffer 适配，`bf3d-internal-simulation.js` 负责新本体上的内部流线/负荷仿真；`tools/patch_8094_furnace_body_page.py` 为 SHA-256 守护页面补丁，`tools/verify_8094_furnace_body_swap.ps1` 为远端只读一致性检查。
- 数据/API/数据库：未增加数据库写入、schema 或生产 API；Billboard 仅按 canonical point id 读取现有页面 buffer，缺少实时值时保留无值状态，不伪造静压力数据。
- 备份：`backups/8094_furnace_body_swap_20260726_001347`，含替换前 HTML 与 GLB，可恢复。
- 验证：远端 page/manifest HTTP 200；远端 hash 与本地产物一致；计划任务 Running、8094 监听恢复；HTML contract、133 点位 manifest 和 flow runtime marker 全部通过。浏览器最终全矩阵尚未完成，原因是既有 8094 用户标签刷新时主线程长时间处于 GLB/Babel 解析状态；不得据此宣称跨浏览器矩阵已通过。
# 2026-07-26 8094 Billboard pSpace 实时 133 点

- `REQ-BF3D-BILLBOARD-PSPACE-LIVE-20260726`：将 8094 高炉本体的
  133 个 Billboard 从空值/页面缓冲升级为 pSpace `RealReadList` 逐点实时值。
- 实现、测试、部署与回滚入口见
  [专项交接](handoffs/2026-07-26-8094-billboard-pspace-live.md)。
- 原 115 字段诊断合同不变；新增 25 个 Billboard 兼容键后流字段为 140，
  其中物理 Billboard ID 精确为 133。
- 现有 `8768` 已确认是 PostgreSQL 30 秒桥并保持不变；新增
  `V4BillboardPspace8770` 计划任务，以 pSpace `RealReadList` 1 秒读取
  133 点，8094 Billboard 单独订阅 8770。
- 2026-07-26 12:05:57 外部真实探针返回 140 个流字段、133 个 Billboard
  元数据、133 个数值、133 个质量码、0 缺点；计划任务 Running。
- 三维背景默认护眼浅灰 `#eef2f1`，并提供纯白、钢灰、深色和自定义颜色；
  背景热发布未重启 8768/8770。
- `BUG-BF3D-8094-VIEWPORT-WHEEL-20260726`：修复旧版延迟样式把 3D 画布重新
  缩至左右各 24% 以及滚轮事件不能稳定到达 canvas 的问题；最终规则覆盖完整舞台，
  增加独立滚轮缩放和“全景”复位。Chromium `1366×768` 实测画布/舞台宽度比
  `0.9966`，滚轮后相机距离 `74.04 → 49.83`；证据见
  [专项交接](handoffs/2026-07-26-8094-billboard-pspace-live.md) 和
  `logs/8094_billboard_zoom_20260726/`。
- `BUG-BF3D-8094-MANIFEST-RETRY-STORM-20260726`：Billboard manifest 偶发空响应
  后不再每 120ms 紧密重试，改为 1s 起步、最高 15s 的指数退避，避免 8094 静态
  服务在网络波动时被重试请求放大；成功挂载后恢复初始退避。

## 2026-07-26 220.12 Ollama 27B / 30B 自动拉起链路只读核查

- 追踪编号：`OPS-22012-OLLAMA-AUTOSTART-AUDIT-20260726`。
- 结论：220.12 只有一个自动 Windows 服务 `BFOllama11434` 负责启动
  `ollama serve` 并监听 `11434`，不是 27B/30B 各自监听。每分钟计划任务
  `\BlastFurnaceServices\BFOllama11434HealthCheck` 运行
  `check_managed_nssm_service_health.ps1`，其配置向
  `chiqiong-blast-furnace:latest`（27.8B）发送极短 `/api/chat` 且
  `keep_alive=24h`，这是当前 27B 自动预热、续驻和失败重启入口。
- 30.5B 的 `bf-diagnosis-runtime:v1` 与
  `chiqiong-blast-furnace:latest_M` digest 相同，当前没有启用中的服务配置
  或健康任务自动加载；核查时 `/api/ps` 只显示 27B。这里记录的
  `OLLAMA_MAX_LOADED_MODELS=2` 是 **2026-07-26 修复前的核查阶段历史值**，
  当时只表示容量上限，不是双大模型自动加载开关；现行值已由
  `OPS-22012-OLLAMA-27B-ONLY-20260726` 收敛为 `1`。
- 当前 8092、8093、8094 受管代理均显式选择 27B。远端
  `start_v3_8092_python.py` 虽保留 30.5B 默认值，但只有脱离受管配置直接运行
  且不传模型参数时才可能加载 30.5B，不是当前自动拉起链。
- 旧 `BlastFurnaceV3Proxy8092/8093` 一次性任务动作脚本已不存在；
  `BlastFurnace8093Proxy_NewProject` 开机任务的动作脚本也已不存在，不能作为
  当前模型自动拉起来源。旧 V4 runner 中的
  `--public-model bf-diagnosis-runtime:v1` 仅是公开显示参数，真实
  `--model` 仍为 27B。
- 专项说明：[22012_Ollama_27B_30B自动拉起链路_20260726.md](22012_Ollama_27B_30B自动拉起链路_20260726.md)；
  主探针：[probe_22012_ollama_autostart.ps1](../tools/probe_22012_ollama_autostart.ps1)；
  旧任务排除探针：
  [probe_22012_ollama_legacy_launchers.ps1](../tools/probe_22012_ollama_legacy_launchers.ps1)。
- 验证：只读核对 Windows 服务/NSSM 参数、计划任务触发器、`11434` 监听进程、
  代理命令行、服务 JSON、`/api/tags`、`/api/ps` 和健康日志；没有启停、重启、
  切换或预热模型。健康日志中 2026-07-26 12:34 的自动重启由既有每分钟任务
  在 `/api/chat` 超时后触发，不是本次探针写操作。

## 2026-07-26 8094 智能助手无回复 PID/GPU 只读复核

- 追踪编号：`OPS-22012-8094-QA-PID-GPU-AUDIT-20260726`。
- 运行态：`11434/8092/8093/8094` 监听 PID 为
  `13620/12444/14172/5560`，父进程均存在；旧孤儿 runner PID `976`
  已消失。Ollama 当前同时驻留 27.8B PID `6972` 和 30.5B PID `18644`，
  不是用户观察到的单一 27B。
- GPU：L20 `46068 MiB` 中已用 `40408 MiB`、剩余 `5345 MiB`；
  两个 runner 分别占用约 `20084/20288 MiB`。连续三次采样 GPU 利用率均为
  `0%`，没有正在生成的信号。
- 定位：8094 PID `5560` 与用户客户端保持活动连接，但没有到 `11434` 的
  活动连接；因此无回复发生在代理进入 Ollama 之前，优先属于前置数据、
  RAG/MCP 或其它 I/O 等待，不是 27B GPU 推理过慢。双大模型驻留造成显存
  风险，但本次快照不能证明当前请求正在 OOM。
- 证据：[probe_22012_pid_gpu_only.ps1](../tools/probe_22012_pid_gpu_only.ps1)、
  [22012_pid_gpu_only_20260726_r2.json](../logs/22012_pid_gpu_only_20260726_r2.json)；
  详细说明见
  [22012_8093_v4_guard_ops.md](22012_8093_v4_guard_ops.md)。
- 操作边界：只读；没有 POST 问答、服务启停、模型卸载、进程清理或配置修改。

## 2026-07-26 11434 仅允许驻留 27B，阻止旧请求加载 30.5B

- 追踪编号：`OPS-22012-OLLAMA-27B-ONLY-20260726`。
- 需求：11434 同时只驻留一个生产大模型；8094 问答使用 11434 已经运行的
  27.8B，不允许浏览器或旧 API 请求再加载 30.5B。
- 程序：
  [ollama_proxy_server.py](../高炉前端数据/智能助手/backend/ollama_proxy_server.py)
  忽略调用方 `model`，仅从 `/api/ps` 选择
  `BF_ALLOWED_LOADED_MODELS` 中已驻留的模型；不再用 `/api/tags` 选择未加载
  模型。[8094 runner](../tools/run_22012_8094_preview.ps1) 不设置
  `BF_LLM_MODEL`，并固定 `BF_QA_KNOWLEDGE_SEARCH_MODE=keyword`；
  [本地整栈启动器](../tools/start_v3_full_python.py) 也不再默认注入固定模型，
  只有显式传 `--model` 时才锁定。
- Ollama 配置：远端
  `tools/service_configs/22012_BFOllama11434.json` 已将
  `OLLAMA_MAX_LOADED_MODELS` 从 `2` 改为 `1`；运行进程环境复核也是 `1`。
  27B 健康检查模型仍为 `chiqiong-blast-furnace:latest`。
- 模型清单：`bf-diagnosis-runtime:v1` 与
  `chiqiong-blast-furnace:latest_M` 的 manifest 已移动至
  `F:\Ollama\models\disabled-manifests\single_27b_20260726_143701`，
  blob 未删除，可按备份恢复。
- 部署边界：重启 `BFOllama11434` 与 8094；8093 PID 在操作前后均为
  `14172`，没有重启 8093、8768、8770 或数据库服务。一次性部署任务完成后
  已删除。
- 验证：`/api/ps` 仅有 `chiqiong-blast-furnace:latest`；直接请求 30.5B
  返回 HTTP 404；8094 状态 `ok/model_ok=true`；向 8094 故意提交旧 30.5B
  模型名后，实际响应模型仍是 27.8B，且请求后 `/api/ps` 未出现 30.5B。
- 2026-07-27 再核：`GET 11434/api/ps` 仍只返回
  `chiqiong-blast-furnace:latest`，8094 `/api/ollama/status` 为
  `ok=true/proxy_ok=true/model_ok=true`；没有发送可能超过 5 秒的问答请求，
  没有重启模型或服务。
- 测试：`python -m pytest -q -p no:cacheprovider
  tests/test_ollama_loaded_model_policy.py`，结果 `3 passed`。
- 证据与回滚：
  [部署结果](../logs/22012_30b_source_audit_20260726/deploy_27b_only_result.json)、
  [运行态复核](../logs/22012_30b_source_audit_20260726/runtime_verification.json)、
  [部署脚本](../tools/deploy_22012_8094_loaded_27b_only.ps1)、
  [专项说明](22012_Ollama_27B_30B自动拉起链路_20260726.md)。

## BUG-8093-MCP-TOP-PRESSURE-HOW-20260726：炉顶压力“如何”历史查询

- 需求：`最近半小时炉顶压力如何？` 必须从 PostgreSQL 分钟历史读取
  `P_top`，返回时间范围、样本数、均值、最小值、最大值、起止值和趋势。
- 根因：MCP 预取的数据意图词包含“怎么样/咋样”，遗漏“如何”，因此请求
  没有进入 `get_statistics`；同时补充 `P_top` 核心兜底目录，使可选映射配置
  缺失时仍可加载炉顶压力点位。
- 程序：[ollama_proxy_server.py](../高炉前端数据/智能助手/backend/ollama_proxy_server.py)、
  [bf_data_mcp_server.py](../高炉前端数据/智能助手/mcp/bf_data_mcp_server.py)。
- 测试：`python -m pytest 高炉前端数据/智能助手/tests/test_qa_latency_optimizations.py
  高炉前端数据/智能助手/tests/test_mcp_chart_expansion.py -q`，结果 `41 passed`。
- 部署：2026-07-26 15:11 受控更新 220.12 的 8093/8094 共享问答代码，只重启
  `BFV4PreviewProxy8093` 与 `V3AutoPreviewProxy8094`；8768、8770 PID 分别保持
  `15668`、`12956`，未重启。
- 现网验收：8093、8094 均返回 HTTP 200，`mcp_prefetch_used=true`、
  `kind=statistics`、`variables=["P_top"]`，精确问题自动验收均通过。

## REQ-MCP-AGENT-ORCHESTRATION-20260726：受控自主工具编排

- 目标：模型结合当前问题和最近对话，自主执行“目录发现→数据查询/计算→绘图
  →总结”，同时由服务端控制工具白名单、参数 Schema、调用规模和只读边界。
- 规划：
  [MCP受控自主工具编排规划与通用流程](../PT/MCP受控自主工具编排规划与通用流程.md)。
- 实现：
  [模型规划入口](../高炉前端数据/智能助手/backend/ollama_proxy_server.py#L3915)、
  [多轮工具循环](../高炉前端数据/智能助手/backend/ollama_proxy_server.py#L4175)、
  [服务端工具策略](../高炉前端数据/智能助手/backend/mcp_tool_policy.py#L110)。
- 安全约束：仅执行 MCP 实时工具目录中的工具；拒绝 Schema 外参数、错误类型、
  错误枚举、超长参数和超量数组；数据库变量和时间范围仍由 MCP 二次校验；
  不向模型开放 SQL、凭据或写操作。
- 测试：
  `python -m pytest 高炉前端数据/智能助手/tests/test_mcp_agent_orchestration.py
  高炉前端数据/智能助手/tests/test_qa_latency_optimizations.py
  高炉前端数据/智能助手/tests/test_mcp_chart_expansion.py -q`，结果 `49 passed`。
- 现网验收：8093/8094 对“分析最近半小时炉顶压力和总压差是否相关”均自主完成
  两次目录发现和一次相关性绘图，返回 `P_top`、`DP_total`、相关系数 `-0.33`
  及 PNG；证据见
  [验收 JSON](../logs/8093_8094_mcp_agent_orchestration_acceptance_20260726.json)。
- 部署边界：只重启 8093/8094；8768 PID=`15668`、8770 PID=`12956` 均未变化。

## REQ-MCP-AGENT-LATENCY-20260726：自主编排低延迟与可恢复基线

- 目标：保留27B自主规划能力，但规划阶段使用低温度、小上下文、小输出上限，
  不注入完整炉况或RAG证据；常见问题通过三级路径、复合工具、缓存和执行预算
  避免多轮模型往返。
- 可恢复基线：
  [SHA-256清单](../backups/mcp_route_baseline_20260726_1552/manifest.json)、
  [校验/恢复脚本](../tools/restore_mcp_route_baseline.py)。`--verify`只读；
  `--restore`只恢复本地文件，不部署、不重启服务。
- 实现：
  [轻量规划与标准复合路由](../高炉前端数据/智能助手/backend/ollama_proxy_server.py)、
  [工具策略](../高炉前端数据/智能助手/backend/mcp_tool_policy.py)。
- 默认预算：规划温度0、输出360 tokens、最近6条消息、每条1200字符、最多2轮
  规划、4次工具调用、30秒缓存、45秒单工具/整轮MCP执行预算。
- 回归：
  `python -m pytest 高炉前端数据/智能助手/tests/test_mcp_latency_optimization.py
  高炉前端数据/智能助手/tests/test_mcp_agent_orchestration.py
  高炉前端数据/智能助手/tests/test_qa_latency_optimizations.py
  高炉前端数据/智能助手/tests/test_mcp_chart_expansion.py -q`，结果`54 passed`。
- 同题现网：相关性分析工具数`3→1`；8093 `38.57s→15.43/25.94s`，
  8094 `45.22s→16.32s`。固定口语“最近半小时炉顶压力如何？”仍走
  `statistics/P_top`，12.26秒自动通过。
- 证据：
  [低延迟验收JSON](../logs/8093_8094_mcp_latency_optimization_acceptance_20260726.json)。
- 发布边界：最终只重启8093/8094；8768 PID=`15668`、8770 PID=`12956`
  均保持不变。

## REQ-MCP-BUSINESS-OBJECT-CATALOG-20260726：统一业务对象目录

- 总阶段入口：
  [MCP智能工具系统九阶段升级总表](../PT/MCP智能工具系统九阶段升级总表.md)。
- 合同：统一`object_id/object_type/display_name/aliases/unit/capabilities/status/executor`
  字段，覆盖sensor、heat、hot_metal_analysis、slag_analysis、feed_chemistry、
  report、qa_history、calculation、chart九类对象。
- 配置：
  [catalog目录](../高炉前端数据/智能助手/mcp/catalog/)包含Schema、manifest、
  sensors、heat_analysis、calculation_tools、chart_capabilities和knowledge_assets。
- 运行时：
  [统一目录加载器](../高炉前端数据/智能助手/mcp/business_object_catalog.py#L134)
  把实际`VARIABLES`转换为统一sensor对象并与静态业务目录合并。
- MCP工具：
  [list_business_objects](../高炉前端数据/智能助手/mcp/bf_data_mcp_server.py#L2065)、
  [search_business_objects](../高炉前端数据/智能助手/mcp/bf_data_mcp_server.py#L2095)、
  [get_business_object](../高炉前端数据/智能助手/mcp/bf_data_mcp_server.py#L2122)。
- 兼容性：旧`find_gl02_variables`保留；模型跨业务对象优先使用统一目录，仅在
  已确认传感器且需细点位匹配时使用旧目录。
- 测试：合同、9类对象、18/18静压力点、跨类型搜索和结构化错误合计纳入相关
  回归；总结果`61 passed`。
- 现网：8093搜索铁水硅含量命中`hot_metal_chemistry`；8094搜索相关散点图
  命中`correlation_chart`，均HTTP 200且只调用一次`search_business_objects`。
- 证据：
  [验收JSON](../logs/8093_8094_business_object_catalog_acceptance_20260726.json)。
- 发布边界：只重启8093/8094；8768/8770 PID保持`15668/12956`。

## REQ-MCP-CONVERSATION-CONTEXT-20260726：结构化追问与确定性低延迟执行

- 需求：短句和省略式追问必须继承上轮业务对象、时间窗和图表类型；去除Prompt
  仅用于MCP本体直连测速，不删除生产口语路由。
- 程序：
  [结构化状态](../高炉前端数据/智能助手/backend/mcp_conversation_context.py)、
  [问答路由与确定性计划](../高炉前端数据/智能助手/backend/ollama_proxy_server.py)、
  [MCP变量解析](../高炉前端数据/智能助手/mcp/bf_data_mcp_server.py)。
- 数据合同：状态仅保存对象ID、相对时间、分析目标、图表类型和证据摘要；禁止
  保存SQL、数据库凭据、完整系统提示和完整炉况资料。
- 安全修复：机器变量ID只允许精确匹配；本地最小目录加入已核实的
  `DP_total/SIO_GL02_BT_T0132`，阻止缺目录时把`DP_total`误映射为`P_top`。
- 延迟策略：清晰latest/history/statistics请求批量执行一次
  `query_gl02_sensors`；清晰图表/相关性请求一次执行复合工具；事实格式器直接
  返回数据和图片，27B只处理无法确定工具的复杂问题。
- 本地测试：相关回归`76 passed`。
- 现网验收：四个关键当前值问题4/4自动通过，中位总耗时`1117.6ms`；两个
  会话7轮少信息追问7/7通过；无Prompt直连4/4，总耗时`3730.5ms`。
- 证据：
  [关键四问](../logs/8093_phase3_four_priority_prompts_20260726.json)、
  [多轮追问](../logs/8093_mcp_context_followups_20260726.json)、
  [无Prompt直连](../logs/mcp_direct_no_prompt_20260726.json)。
- 发布：最终版本于`2026-07-26 18:21:19`部署；8093/8094为
  `16636/13924`，该次部署前后8768/8770保持`12672/12956`。部署过程中曾遇
  自动值守与服务启动竞争，脚本自动回滚成功；随后改为启动命令容忍瞬态竞争，
  并继续以端口与受保护PID作为最终判定。
- 说明：在几次独立部署之间观察到8768由外部自动值守更换PID
  `15668→2052→12672`；不是单次部署脚本触发。最终部署窗口内PID未变化。

## REQ-SI-FORMAL-LABEL-CONTRACT-V3-20260726：正式炉次Si标签、数据与训练

- 用户目标：用MES正式meltno替代试样号炉次推断，取得真实取样时间、铁口、
  铁罐和出铁阶段，并明确代表Si、下一试样Si、整炉Si分布三个任务。
- 只读源：
  `t_qpes_inner_batch/inner_batch_insp_bb/t_ipes_cond/v_qpes_mat_final`及
  `bf_sensor.sensor_registry/one_minute_values`；无生产数据库写入。
- 核查结论：2#正式化验24,821条、正式炉次9,337个、精确炉次连接24,705条；
  `takesampletime`为0条，可信铁口编号为0条；全历史铁罐号连接覆盖66.07%。
- 当前训练范围：5,936条正式试样、2,366炉；排除66炉完整标签在截止前已可见
  的非前瞻样本后，2,291炉通过标签与至少100点门禁；
  133物理点生成665个当前/60/120分钟候选特征，训练使用579个。
- 切分：按MES`opentime`的1,603/344/344时间外切分，同一正式meltno不跨段。
- 训练：代表Si ExtraTrees测试MAE `0.048851%`、`±0.05`命中`64.53%`；
  分布P50 MAE `0.048312%`；下一试样任务因取样时间缺失被合同阻止。
- 状态：`experimental_offline_formal_contract`；未授权接生产MCP、预警或操作
  建议。
- 程序：
  [正式标签](../PT/预测铁水Si含量/src/si_semantic_engine/formal_labels.py)、
  [数据拼装](../PT/预测铁水Si含量/src/si_semantic_engine/formal_dataset.py)、
  [只读抽取](../tools/build_formal_si_dataset_v3.py)、
  [训练](../PT/预测铁水Si含量/src/si_semantic_engine/train_v3.py)。
- 合同和证据：
  [数据合同](../PT/预测铁水Si含量/docs/data_contract.md)、
  [数据清单](../PT/预测铁水Si含量/data/processed/formal_v3_20260726/manifest.json)、
  [实验指标](../PT/预测铁水Si含量/reports/experiments/EXP-SI-V3-FORMAL-001_20260726_222525/metrics.json)。
- 回归：
  `python -m unittest discover -s PT/预测铁水Si含量/tests -v`，结果
  `Ran 23 tests / OK`。

## REQ-BF3D-8093-MEASURED-121-OVERVIEW-20260801：8093 炉体 121 点与全景相机

- 用户目标：左侧既有 28 核心变量面板完全不移动；三维炉体保留 121 个具有实际安装语义的点位；计算、设定与汇总变量不再贴在炉壳上；关闭点位聚焦。
- 121 点构成：80 个炉体温度、18 个 A～F 静压力、2 个南北出铁口温度、21 个设备/管线/炉顶实测点。炉壳直接物理测点为 100 个，另有 21 个实测设备点。
- 3D 排除 12 点：`DP_upper`、`DP_lower`、`DP_total`、`PI`、`GasUtil`、`TFT`、`PCI_set`、`L`、`P_top`、`P_static_20m35`、`P_static_23m49`、`P_static_28m98`。排除只作用于 8093 Three.js 场景，不删除数据，也不改变左侧 28 变量。
- 实现：[8093 点位筛选器](../高炉前端数据/assets/bf3d-physical-point-filter-8093.js)在共享 133 点 adapter 完成后原地筛选 Billboard、命中对象和传感器对象，保持悬停和实时更新闭包有效；[8093 全景相机](../高炉前端数据/assets/bf3d-surface-camera-guard-8093.js)固定炉心 target、全模型包围半径防穿透和无限方位角，不注册点位聚焦。
- 部署：[原子部署器](../tools/remote_deploy_8093_physical_points_overview.py)已部署到 `F:\高炉炼铁项目-real-sensor-v2_V4_8093_PREVIEW`，备份位于 `backups\8093_measured121_overview_20260801\20260801_202127`。8094 页面、共享 adapter、8094 相机运行时的部署前后 SHA-256 完全一致。
- 验证：JavaScript 语法、Python 语法与 7 项单元/隔离部署契约均通过；8093 页面及两个资源 HTTP 200，页面包含 `20260801-measured121-r2` 与 `20260801-overview-only-r6`。因正式页完整加载超过用户规定的单次 5 秒操作上限，本轮未用长等待声明完成远端视觉矩阵。

## DOC-BF-SELF-LEARNING-MECHANISM-20260802：冀南钢铁高炉智能体自学习机理

- 目标：将高炉智能体的“自学习”固定为滚动基线自适应、诊断/工具外部记忆和人工审核后的离线迭代，不把在线改权重或生产自动控制表述为当前能力。
- 说明：[项目版自学习机理说明](冀南钢铁高炉智能体自学习机理说明_项目版_20260802.md)。
- 原理图：[项目版自学习闭环 SVG](冀南钢铁高炉智能体自学习闭环_项目版_20260802.svg)。
- 运行链路：`one_minute_values` → 数据质量与同步门 → 30 天 `daily_baselines` / 60 分钟诊断窗口 / 5 分钟档位 → 规则、Chronos、RAG、MCP 证据融合 → 只读建议与安全门禁 → 队列/总结/工具轨迹沉淀。
- 学习边界：当前已实现滚动基线、短时队列、总结与追问承接；人工采纳/拒绝、实际操作结果和质量结果尚未统一为可训练标签表，后续必须经过时间外回测、影子运行和专家复核后才可版本回灌。
- 追踪入口：[自动诊断配置](../自动诊断服务/config.yaml)、[自动诊断表结构](../自动诊断服务/schema.sql)、[8767 状态/预测桥接](../自动诊断服务/local_pg_ws_bridge.py)、[建议引擎说明](调控结论生成引擎可追踪说明.md)。

## DOC-BF-SELF-LEARNING-SHORT-20260802：冀南钢铁高炉智能体自学习原理精简版

- 用途：用于汇报首页、论文方法概览或原理页，仅保留“感知—认知—融合—决策—学习”五个核心节点。
- 原理图：[冀南钢铁高炉智能体自学习原理 SVG](冀南钢铁高炉智能体自学习原理.svg)。
- 与详细版关系：[详细机理说明](冀南钢铁高炉智能体自学习机理说明_项目版_20260802.md)保留数据表、服务和学习边界；精简图不替代详细追踪说明。

## 2026-08-02：8093 初始全景放大与守卫覆盖审计（已部署）

- 相机运行时升级为 `bf3d.camera.overview-only.8093.v4`，初始/全景复位使用 `OVERVIEW_FIT_MARGIN=1.0` 与 `OVERVIEW_ORBIT_MARGIN=1.12`；相对旧 1.08 fit margin 约放大 8%。
- `minDistance=fullOrbitRadius`、近裁剪面 `0.05m`、炉心 target 和 360° 旋转均未改变，不修改 GLB。
- 使用 [守卫部署入口](../tools/remote_guarded_deploy_8093_initial_camera_framing.ps1)完成停—改—启：`guard_paused=true`、`guard_restored=true`、`ws8768_unchanged=true`、HTTP 200。
- 备份：`backups\8093_initial_camera_framing_20260802\20260802_213047`。最终页面 SHA-256 `A6A7D2D6...E3A`，相机 SHA-256 `1C87B11B...C6F0`。
- 部署前页面 SHA-256 仍为上一轮记录的 `F308993A...24FC1`；恢复守卫后新相机哈希仍为 `1C87B11B...C6F0`，未发现守卫回写旧代码。
- [远端/本机审计器](../tools/audit_8093_remote_local_parity.py)确认 5 个关键代码资产和受控 GLB 一致；整页 HTML 因远端专用运行时注入而与本机主 HTML 不同。详见[专项审计](8093_初始构图与远端本机一致性审计_20260802.md)。

## BUG-BF3D-CAD-BOTTOM-BAND-20260804：8093/8094 底部空白带

- 需求/问题：[问题追踪](question_traceability.md#q-bf3d-8093-cad-bottom-band-20260804)、[需求追踪](requirements_traceability.md#bug-bf3d-cad-bottom-band-20260804)。
- 程序：[共用补丁器](../tools/patch_8094_cad_bottom_band.py)、[远端 8094-only 初次部署器](../tools/remote_deploy_8094_cad_bottom_band.ps1)、[8094 重启入口](../tools/restart_22012_8094_preview.ps1)、[8093 守卫部署器](../tools/remote_guarded_deploy_8093_cad_bottom_band.ps1)、[只读状态探针](../tools/remote_probe_8093_8094_cad_panel_body_gap.ps1)、[8094 测试](../tests/test_8094_cad_bottom_band_fix.py)和[8093 测试](../tests/test_8093_cad_bottom_band_fix.py)。
- 配置/页面契约：R2 标记 `BUG-BF3D-CAD-PANEL-BODY-GAP-20260804-R2`；最终样式 ID `bf3d-cad-bottom-band-fix-20260804`；viewer bottom inset 与炉况总览直属 panel-body padding 均为 `0`，左右 inset 保持 `24%`。8094 重启必须证明监听 PID 变化且 8093/8768/8770 PID 不变；8093 写入必须暂停并恢复 `BFV4PreviewProxy8093`，并保护 8094/共享运行时哈希。
- 验证：7 项合同测试通过；8094 HTTP 200、页面哈希 `A13AB868...193C7`；8093 守卫暂停/恢复、HTTP 200，页面哈希 `0AB75FF7...A3F4`；Chrome 两页 `1552×816` 的 canvas/panel-body 底差约 `0.606px`、`padding-bottom=0px`、无横向溢出。旧 stage/viewer 通过结论因错误边界测量已作废。
- 运行记录：[2026-08-04 8094 修复交接](handoffs/2026-08-04-8094-cad-bottom-band-fix.md)。
## REQ-8096-DIAGNOSIS-MANUAL-SCORE-AND-SUGGESTION-20260804

- 触发：8096诊断页人工点击任一炉况卡，或异常自动弹窗提交复核。
- 只读输入：`bf_sensor.diagnosis_snapshots` 最新诊断快照；浏览器只传快照标识、目标炉况和人工输入，系统八类分由服务端重新读取。
- 本机写入：`bf_assistant.diagnosis_manual_score_events` 或 `bf_assistant.diagnosis_review_events`，仅允许 `BF_DIAG_REVIEW_PG*` 显式指定的回环PostgreSQL；唯一幂等键防重复。
- 关闭语义：弹窗关闭不执行POST、不创建“空评分”事件；仪表盘通过系统快照投影“未打分”。
- 查询输出：8890/隔离验收端口的 `/api/diagnosis-foreman-scores`，支持 `source=live_readonly|local_fixture`、标签/时间过滤和JSON/CSV/XLSX。默认真实来源，测试来源必须显式选择。
- 运行边界：本地8096/8769原型；未变更220.12的8093/8094/8768服务、任务或数据库。
- 证据：18项测试通过；本机两类 `local_fixture` 事件写入成功；Chromium九视口异常弹窗和四视口手动评分窗口通过。Firefox/WebKit自动矩阵因Python Playwright依赖下载被网络代理中断，保持未验收状态。

## REQ-THREE-RULES-RECOMMENDATION-ALIGNMENT-20260804

- 原始需求：把三规二制转换为可核对 Markdown，验证文字数量/内容一致，并按
  四类炉况调剂逐条审计现有建议引擎的完全一致升级路径。
- 原文链：[DOCX](冀钢炼铁三规二制.docx) →
  [转换器](../tools/convert_docx_to_markdown_verified.py) →
  [完整 Markdown](冀钢炼铁三规二制.md) →
  [验证报告](../logs/three_rules_markdown_validation.json)。
- 规则链：[5.1.8/5.3 逐条分析](三规二制四类炉况调剂与建议引擎完全一致升级分析_20260804.md) →
  [四类策略目录](../调控结论生成引擎/policy/three_rules_two_systems.yaml) →
  [策略评估](../调控结论生成引擎/recommendation/policy_evaluator.py) →
  [顺序规划](../调控结论生成引擎/recommendation/sequence_planner.py) →
  [冲突解析](../调控结论生成引擎/recommendation/conflict_resolver.py) →
  [引擎入口](../调控结论生成引擎/recommendation/core.py) →
  [8767适配](../自动诊断服务/recommendation_adapter.py)。
- 校验：转换单元测试 `1 test / OK`；4,934 个顶层段落中有 4,663 个可见
  文字段落、270 个空段落、1 个仅含空白，另有 122 张表和 6,943 个真实
  单元格；源与写入有序文本片段 SHA-256 相同。
- 当前状态：文档转换和现状审计完成；本地引擎/适配器已升级为
  `v5-three-rules-two-systems`，每条动作返回四态与完整审计字段，并兼容旧前端数组。
  v5专项测试 `11 tests / OK`，旧综合验证器3项后端子合同通过。
- 运行边界：未部署或重启220.12的8768/8093；前端完整详情、浏览器矩阵、历史
  回放、现场工艺签字和真实炉次/布料/人工事件数据接入仍未完成。

## OPS-8093-ASSISTANT-HEALTH-CHECK-20260804

- 目标：固定 8093 智能助手“服务正常但无回复”的分层检查流程，并把页面入口名称从“智能问答/知识助手”收敛为“智能助手”。
- 程序：[前端入口](../高炉前端数据/frontend_dashboard_v3.server.html)、[只读健康探针](../tools/probe_8093_assistant_health.ps1)、[只读日志尾部探针](../tools/probe_8093_assistant_log_tail.ps1)、[名称原子补丁器](../tools/remote_patch_8093_assistant_name.ps1)、[合同测试](../tests/test_8093_assistant_health_contract.py)。
- 检查链：服务与状态 GET → 11434 驻留模型 → 8093/11434 实际进程环境 → 四类代理日志 → 最后一次受控 `/api/qa/chat` SSE；状态接口绿灯不得替代 `start/delta/final` 验收。
- 2026-08-04 只读取证：`21:25` 第一层探针确认 8093/11434/8768 Running、状态接口 HTTP 200 且模型正常、`/api/ps` 仅 27.8B；日志尾部确认 `20:46`～`21:48` 健康守卫多次因 8093 TCP 或状态接口短时不可达而重启代理，这是在途 SSE 被切断的直接原因。8093 空搜索模式回退 `hybrid` 与 11434 单驻留 `1` 仍是独立的 embedding 争用风险。
- 名称部署：只热更新 8093 HTML，备份 `backups\8093_assistant_name_20260804\20260804_212113`，页面 SHA-256 `E091DDC33FC279F4A9EA67AA45F0417A1DCC7EF83A0A72B4E520867C8BF7EBCB`；cache-bust HTTP 和浏览器均确认“智能助手”可见，8094 页面 SHA-256 仍为 `A13AB868BA7D71FC04450D05BD88D23506DB6BB7103C1165D5CCFD2021D193C7`。
- 验证：`tests/test_8093_assistant_health_contract.py` 为 `4 passed`；三个 PowerShell 脚本解析通过；两层远端只读探针成功。浏览器可进入 `#qa` 工作区并看到“Ollama 正常”和“智能助手”。
- 运行边界：本节记录只读诊断与名称部署；正式守卫修复和真实 SSE 结果见下节，模型/RAG 配置仍未改变。

## OPS-8093-ASSISTANT-HEALTH-GUARD-FIX-20260804

- 目标：消除单次瞬时 TCP/HTTP 探测失败立即重启 8093、切断问答 SSE 的故障链，同时保留服务真正停止时的快速恢复。
- 程序：[共享守卫](../tools/check_managed_nssm_service_health.ps1)、[8093 配置补丁器](../tools/patch_8093_health_guard_config.py)、[运行时探针](../tools/probe_8093_health_guard_runtime.ps1)、[受控部署器](../tools/remote_guarded_deploy_8093_health_guard.ps1)、[单次 SSE 验收器](../tools/verify_8093_assistant_sse_once.py)、[远端验收包装器](../tools/remote_verify_8093_assistant_sse_once.ps1)、[合同/行为测试](../tests/test_8093_health_guard_recovery.py)。
- 配置：8093 `failureThreshold=3`、`serviceNotRunningFailureThreshold=1`、`preRestartBackoffSeconds=15`、`restartCooldownSeconds=600`；状态文件 `logs/proxy_8093.health.state.json`。无新字段的其它托管服务仍使用 `1/0/0` 默认值。
- 部署：2026-08-04 22:54 上线；只暂停并恢复 8093 健康检查任务，没有停止业务服务。脚本 SHA-256 `1A4B2C56D5E86BC6DCC7D82700142BF40B936492712A20AD34997953DCD9C2B3`，配置 SHA-256 `D20F01F1E66FF8973AB6720DDEB450AEE50FAE2AC6FFB023E1C04EACA066EACA`，回滚目录 `logs/deploy_backups/8093_health_guard_20260804_225350`。
- 隔离：部署前后 8093/8768/8094/8770/11434 PID、8093/8094 页面、8768 专用健康脚本、11434 配置均不变；任务执行结果 0，状态计数为 0，只驻留批准的 27.8B。
- 部署后观察：22:54～23:13 每分钟健康记录连续为 `ok`，任务保持 Ready/结果 0，`consecutiveFailures=0`、`lastRestartAt=null`，未发生新的守卫重启。
- SSE 验收：23:03 只提交 1 次新会话短问，收到两阶段 `start`、多个 `delta`、`final`、`done`；首个 delta `6321.2ms`、final `6583.6ms`、总计 `6583.7ms`，回答非空，期间无守卫重启且所有受保护 PID 保持。远端报告 `logs/acceptance/8093_health_guard_sse_20260804_20260804_230300/assistant_sse_once.json`。
- 测试：`python -m pytest -q -p no:cacheprovider tests/test_8093_health_guard_recovery.py tests/test_8093_assistant_health_contract.py` 为 `9 passed`；PowerShell 四个新增/修改脚本解析通过，两个 Python 工具 `py_compile` 通过。
- 长期交接：正式原因、7 组历史失败证据、现行守卫合同、复发分类、受控修复、一次 SSE 验收与回滚边界已固定到 [DOCX 手册](8093智能助手不可用原因与正式修复手册_20260804.docx)和 [AGENTS 长期记录](../AGENTS.md#8093-智能助手再次不可用时的直接修复记录长期固定)；生成器与无 Word 依赖的 OpenXML 合同测试分别为 [generate_8093_assistant_repair_docx.py](../tools/generate_8093_assistant_repair_docx.py)和 [test_8093_assistant_repair_doc_contract.py](../tests/test_8093_assistant_repair_doc_contract.py)。文档合同、守卫恢复和智能助手健康合同组合测试为 `13 passed`，产物已由 `python-docx 1.2.0` 重新打开检查。

## OPS-8093-8094-PROMPT-RAG-RUNTIME-20260805

- 目标：澄清固定 Prompt 与 attention/KV 的真实关系，并确认 8093/8094 当前是否加载公共 Prompt、PostgreSQL RAG 和 MCP 链路。
- 实现：[公共 Prompt 与规则](../高炉前端数据/智能助手/backend/ollama_proxy_server.py#L188-L270)、[知识意图门控](../高炉前端数据/智能助手/backend/ollama_proxy_server.py#L4771-L4876)、[动态上下文拼装](../高炉前端数据/智能助手/backend/ollama_proxy_server.py#L4880-L4938)、[PostgreSQL RAG](../高炉前端数据/智能助手/backend/bf_knowledge_rag.py#L666-L724)、[8094 runner](../tools/run_22012_8094_preview.ps1#L6-L31)。
- 语义：没有应用侧 attention score 配置或持久 KV cache ID；固定身份、安全、回答规则和工艺规则组成稳定 token 前缀，动态炉况、MCP、知识证据、对话和当前问题后置。真实复用程度只能用 `prompt_eval_count/prompt_eval_duration` 和首 token A/B 证明。
- 运行核查：2026-08-05 06:54 使用 [只读探针](../tools/probe_8093_8094_prompt_rag_runtime.ps1)确认两个监听进程均指向共享后端；Prompt、固定规则、知识门控、证据注入、MCP 预取/工具路由标记均存在。8093 PID=`12388`、8094 PID=`9976`；未发送 `/api/qa/chat`、未启停服务。
- 知识连通：探针对两端口强制 `mode=keyword` 的只读 `/api/qa/knowledge/search`，均 `ok/enabled=true`、返回 2 条证据，证明当前 PostgreSQL `bf_assistant.rag_*` 可访问；强制 keyword 避免触发 embedding。
- 后续状态：该次只读核查发现的差异已由 `OPS-8093-KNOWLEDGE-KEYWORD-MODE-20260805` 消除；8093 与 8094 现均显式使用 `keyword`。本条的 8093=`hybrid` 仅保留为变更前证据，不代表现行配置。
- 文档与测试：[专项说明](8093_8094_Prompt固定KV前缀与知识库回答链路_20260805.md)、[合同测试](../tests/test_8093_8094_prompt_rag_contract.py)。

## OPS-8093-KNOWLEDGE-KEYWORD-MODE-20260805

- 需求：把 8093 显式切换为关键词模式，让知识库使用 PostgreSQL 关键词/词法检索；继续加载公共 Prompt、知识意图门控和证据注入，不在共享 11434 上调用 embedding。
- 程序与配置：[配置补丁器](../tools/patch_8093_keyword_knowledge_mode.py)、[受控部署器](../tools/remote_guarded_deploy_8093_keyword_knowledge_mode.ps1)、[单次 SSE 验收器](../tools/verify_8093_assistant_sse_once.py)、[关键词知识验收包装器](../tools/remote_verify_8093_keyword_knowledge_sse_once.ps1)、[合同测试](../tests/test_8093_keyword_knowledge_mode.py)。唯一业务配置变化是 8093 服务环境增加 `BF_QA_KNOWLEDGE_SEARCH_MODE=keyword`；守卫继续保持 `3/1/15/600`，共享 11434 继续保持单 27B。
- 部署：`2026-08-05 07:25:21` 完成；远端备份 `logs/deploy_backups/8093_knowledge_keyword_20260805_072445`。8093 配置 SHA-256 从 `D20F01F1E66FF8973AB6720DDEB450AEE50FAE2AC6FFB023E1C04EACA066EACA` 变为 `8A24C83DF93008DD8E358682558E8755442D87052A09FB24F39778F2EAF51FDE`。PowerShell 5.1 部署时使用上传脚本并以 `Get-Content -Raw -Encoding UTF8` 构造 ScriptBlock，避免长 `--script` 命令和 ANSI 中文解析。
- 隔离：只重启 8093（PID `10996 -> 15352`）；8768=`15824`、8094=`9976`、8770=`12956`、11434=`6984` 均未变化。8093/8094 页面、共享后端 SHA `B4DFBDF15BD7C1D2D731BEB2A45238C881FEC75B71F2304D619DEF3D2F2C812A`、RAG SHA `C42CA839CD83541F679D348B6652B0BFFC1AAB2EE72D96C3B08395A70E6289AA`、守卫脚本及 11434 配置均未变化；任务恢复且结果 0，状态计数清零，`/api/ps` 仍只含批准 27.8B。
- 配置验收：实际 8093 监听进程环境为 `keyword`，默认 `/api/qa/knowledge/search` 返回 `search_mode=keyword`、`enabled=true` 和 2 条证据；不是通过请求参数强制 keyword 冒充运行配置生效。
- 真实问答：`2026-08-05 08:44:59` 只发送 1 个新会话 POST；准备态显示知识检索启用、未跳过、意图 `parameter_optimization`、MCP 工具调用关闭，完整收到 `start(preparing/prepared) -> delta -> final -> done`。首 delta `11709.7ms`、final `23885.4ms`、总计 `23885.6ms`；验收前后默认检索均为 keyword、各命中 2 条证据，所有受保护 PID/哈希/模型驻留保持，无守卫重启。报告：`logs/acceptance/8093_keyword_knowledge_20260805_20260805_084403/assistant_keyword_knowledge_sse_once.json`。
- 本地验证：关键词模式补丁/部署/SSE 合同组合 `16 passed`；Python 编译和两个 PowerShell 包装器解析通过。长期说明见[专项文档](8093_8094_Prompt固定KV前缀与知识库回答链路_20260805.md)、[配置参考](config_reference.md)、[8093 守卫运维记录](22012_8093_v4_guard_ops.md)与[DOCX 手册](8093智能助手不可用原因与正式修复手册_20260804.docx)。

## REQ-8093-CORE-PSPACE-REALTIME-20260804

- 数据链：8770 服务端 pSpace `RealReadList` 秒级流只覆盖 28 个核心指标当前值；8768 PostgreSQL 分钟流继续负责火花线、趋势、诊断、基线和统计。
- 页面合同：逐项显示数据时间、源值年龄和质量；用 8770 传输年龄判断实时链路，超过 12 秒或质量/连接异常时明确显示“已降级为分钟镜像”。
- 历史合同：`BF_HISTORY_MERGE_TIMESTAMP_PRIMARY_WINS_8093` 按时间戳合并，8768 主数组在重叠点优先，不完整 trend 序列不得覆盖完整历史。
- 程序、测试、部署备份、哈希和回滚见[专项记录](8093_核心指标pSpace秒级实时与分钟镜像降级_20260804.md)。生产验收为 Chrome 9 视口、Firefox/WebKit 各 4 视口、Edge 冒烟和 Chrome 主动断流 4 视口通过；合同测试 6 项通过。

## OPS-8093-MULTI-MCP-HOST-20260805

- 目标：让 8093 通过统一 MCP Host 按需发现并编排 `gl02-data` 与 `imes-readonly`，支持“当前/上一炉次 + MES 化验”这类跨域口语查询；选择的服务失败时返回结构化错误，不回退到无边界数据库查询。
- 程序：[MCP 服务注册表](../高炉前端数据/智能助手/backend/mcp_host/server_registry.json)、[服务发现](../高炉前端数据/智能助手/backend/mcp_host/server_registry.py)、[多服务客户端](../高炉前端数据/智能助手/backend/mcp_host/client_manager.py)、[域路由](../高炉前端数据/智能助手/backend/mcp_host/domain_router.py)、[8093 问答路由](../高炉前端数据/智能助手/backend/ollama_proxy_server.py)、[MES 中继工具](../高炉前端数据/智能助手/mcp/imes_relay_mcp_server.py)。
- 受控部署：2026-08-05 10:01 完成；只暂停、停止并重启 `BFV4PreviewProxy8093`，备份目录为 `F:\高炉炼铁项目-real-sensor-v2_V4_8093_PREVIEW\logs\deploy_backups\8093_multi_mcp_20260805_100117`。部署脚本为 [remote_guarded_deploy_8093_multi_mcp.ps1](../tools/remote_guarded_deploy_8093_multi_mcp.ps1)，失败路径会恢复备份并只重启 8093。
- 隔离验收：8093 PID `15352 -> 7348`；8768 PID `15824 -> 15824`、8094 PID `9976 -> 9976`、8770 PID `12956 -> 12956`，均保持不变；8093/8094 HTTP 均为 200；健康任务恢复且部署脚本记录结果码为 0；新后端 SHA-256 为 `8F38DA0286791A95722520D7278AE2A37544E3D4EB255D8A5950FC3CAD50EFD0`。
- 真实 MES 验收：单次 SSE 查询完整收到 `start -> tool_start -> tool_result -> delta -> final -> done`，实际调用 `imes__get_current_previous_heat_si_summary`（`server_id=imes-readonly`），耗时约 `2476.5 ms`。当前正式炉次为 `2#20240805-056`，上一炉次为 `2#20240805-055`；该时点 `sample_count=0`、Si 均值/最小值/最大值为空，返回 `NO_SI_SAMPLES` 并明确标注为数据源暂无样本，不是路由失败。
- 证据与回滚：[受控交接报告](handoffs/2026-08-05-8093-multi-mcp-deploy.md)；部署器会保留 8 个运行文件的同批次备份，并在复制、编译、启动或验收失败时恢复原文件、只重启 8093，8768/8094/8770 不在回滚范围内。
## OPS-IMES-LOCAL-MULTI-MCP-RELAY-20260805

- 目标：本机统一按需发现 GL02、Vastbase/IMES 和 IMES Web 三个只读 MCP 服务，
  并保持生产网络只通过 220.12 回环转发访问。
- 程序与配置：[本机注册表](../高炉前端数据/智能助手/backend/mcp_host/server_registry.json)、
  [领域路由](../高炉前端数据/智能助手/backend/mcp_host/domain_router.py)、
  [IMES Web MCP](../高炉前端数据/智能助手/mcp/imes_web_mcp_server.py)、
  [组合转发入口](../tools/start_imes_web_vastbase_relay_local.cmd)、
  [GUI 启动器](../tools/imes_web_launcher.py)。
- 自动化合同：Host 默认按问题选择服务；`--all` 仅用于发现/诊断。IMES Web 只调用
  已审计白名单，验证码或受控会话 Cookie 缺失时返回明确状态；Vastbase MCP 只使用
  `127.0.0.1:15433` relay，不自动降级直连。
- 状态：本地注册表三服务、35 个 Host 可见工具；组合转发命令和 GUI 已修复并通过
  本地契约检查。本轮没有停止、修改或重启 220.12 上的 8093/8768/数据库服务。

## OPS-8093-ASSISTANT-AUTO-RECOVERY-20260805

- 目标：把 8093 智能助手的网络恢复、只读取证、自动分类、已知最小修复、实际运行态复核、默认知识检索、唯一 SSE 和报告生成封装为统一入口，减少重复查找、临时上传和 PowerShell 解析失败。
- 程序：[本机编排器](../tools/assistant_8093_auto_recovery.py)、[远端合并诊断](../tools/remote_8093_assistant_diagnose.ps1)、[守卫部署器](../tools/remote_guarded_deploy_8093_health_guard.ps1)、[keyword 部署器](../tools/remote_guarded_deploy_8093_keyword_knowledge_mode.ps1)、[SSE 包装器](../tools/remote_verify_8093_keyword_knowledge_sse_once.ps1)。配置/使用见 [CLI](cli_usage.md)和[自动值守索引](自动值守程序配置索引.yaml)。
- 连通性合同：每次命令先并行探测 SSH 22、PostgreSQL 5432、8093、11434，并记录 aTrust 门户辅助探测；必需私网端口不全时先启动 aTrust、等待恢复，仍失败则退出码 3，不建立远端会话。连通性恢复与服务恢复计时分离。
- 包合同：远端根目录 `C:\ProgramData\BFV4\assistant-auto-recovery\packages`；包 ID 由 manifest 内容决定，PowerShell payload 使用 UTF-8 BOM，原子上传后逐文件远端 SHA-256。2026-08-06 当前包 `20260805_v2_72eff4ce55d3`、manifest `6459A6DCEC292E27C2F3B85E30046251F35050A44241BB0F1F469A920155467E`；13 个 payload 已逐文件验证。
- 分类合同：当前配置/守卫哈希且运行态 keyword/默认检索 keyword/单批准模型时为 healthy；已知旧配置、空值或 hybrid 直接映射 keyword 部署；已知旧守卫/合同漂移映射守卫部署；未知哈希、非批准模型或无法归类的运行错误拒绝自动覆盖。多个已知漂移固定先守卫、后 keyword。
- PowerShell 合同：远端只执行短 `powershell.exe -NoProfile -ExecutionPolicy Bypass -File "<package script>"`；禁止 `-EncodedCommand`、内联 ScriptBlock 和长命令传输。数字端口键在 PowerShell 5.1 中统一输出为对象数组。
- 本地验证：`python -m pytest -q -p no:cacheprovider tests/test_8093_assistant_auto_recovery.py tests/test_8093_keyword_knowledge_mode.py tests/test_8093_health_guard_recovery.py` 为 `22 passed`。覆盖包稳定性/BOM/SHA、healthy/keyword/守卫/未知哈希分类、真实 PS5.1 两组数字键序列化、阶段顺序、短 `-File` 和唯一 SSE。
- 远端只读结果：`2026-08-05 10:58` 端到端约 67 秒，远端合并探针 `17.333s`，分类 healthy；服务/监听/状态正常，进程和默认搜索均为 keyword，默认候选 117、返回 2 条证据，只驻留批准 27.8B，守卫 Ready/结果 0/计数 0/参数 3/1/15/600。
- 真实验收：`2026-08-05 11:03` 完整 recover 前后均 healthy，`repairs=[]`，未备份、未部署、未重启，服务阶段 `184.618s`。仅 1 个 SSE POST；首 delta `10118.5ms`、总计 `22185.9ms`，知识意图 `parameter_optimization`、keyword 证据 2 条、事件完整，所有受保护 PID/哈希/守卫/模型检查通过。
- 报告：本机 [20260805_110327_recover.json](../logs/assistant_8093_auto_recovery/20260805_110327_recover.json)；远端 `logs/acceptance/8093_keyword_knowledge_20260805_20260805_110253/assistant_keyword_knowledge_sse_once.json`。服务阶段返回后由 `docs` 子命令独立生成 Markdown 与 DOCX，不因文档失败再次触碰服务。

## REQ-8093-SYSTEM-CLOCK-AND-5S-DATA-20260805

- 显示链路：8093 当前值固定为 `pSpace -> 8770 -> 浏览器`；PostgreSQL/8768 只负责分钟历史、趋势、诊断、基线和实时流异常时的分钟镜像。顶栏系统时钟与分钟数据时间已经分离。
- 220.12 实测配置：8770 pSpace 轮询 1 秒；分钟同步进程 `continuous_poll_seconds=30`，源为 5 秒 raw/sample，目标为 60 秒 `PS_RAW_SAMPLE`；看门狗 5 分钟，显式 reconciliation 60 分钟。没有半小时主同步。
- 数据表（审计时状态）：`bf_sensor.one_minute_values` 为133点分钟主表、3年保留；当时 `raw_5s_values` 只到2026-07-16。该状态已于2026-08-05由 `REQ-PSPACE-MINUTE-CANONICAL-AVERAGE-20260805`修复，raw表现持续写入并保留30天。
- 聚合边界（审计时状态）：当时增量是 `PS_RAW_SAMPLE`。自2026-08-05 21:55起已切换为 `PS_RAW_AVERAGE/valid_raw_mean_v1`，旧sample段保留真实标签，详见本文后续同名需求章节。
- 5 秒验收门：源点时间戳 P95 年龄不超过 7.5 秒、8770 传输年龄不超过 2 秒、5 秒短期表覆盖率可审计、分钟聚合在闭窗后 90 秒内完成。当前顶压源点约 33–40 秒更新，不满足源端门槛，故本轮没有启动新的 5 秒生产任务。
- 部署：2026-08-05 10:26 只暂停/恢复 `BFV4PreviewProxy8093` 更新系统时钟；8768/8770/8094 PID 与受保护哈希未变化。页面 SHA-256 `356BB43BCC2DD45A28B208C3D5B24F91654851CAE10DDCF0B89861CC4B591DF1`，实时资源 SHA-256 `33195006D8F7C618C9904F540D27A4589A829A6F2FA08A03E4F3900F5C38E338`。

## OPS-IMES-HEAT-ACCOUNT-AND-CONTEXT-20260805

- 目标：修复 IMES 化验账号误判和当前/上一炉上下文错选，保证 8093/本机 Host 可按正式 `meltno` 精确查询。
- 远端证据：220.12 `operations/gl2#dmx` 已能读取 `2#20260805-065` 的 3 条正式化验，Si=`0.20/0.25/0.24`，均值=`0.23%`；所以不能继续把 operations 标成错误账号。
- 实现：[imes_relay_mcp_server.py](../高炉前端数据/智能助手/mcp/imes_relay_mcp_server.py) 使用受控 `IMES_DB_*` 作为本机两个 profile 的统一覆盖，化验 profile 默认 `operations`；`_query_recent_heat_context_rows` 先按 `COALESCE(opentime, workdate) DESC, meltno DESC` 排序，`get_current_heat_context` 再应用 72 小时新鲜度判定。
- 验证：`py_compile` 通过；项目 Python 3.11 的 relay 单元 `21 tests / OK`；炉次摘要回归和 MCP discovery 直接契约调用通过。未修改生产数据库。
- 发布边界：本项源代码修复尚未在本轮重启/部署远端 8093；若要让现网 8093 生效，必须使用现有受守卫的 8093 MCP 部署脚本，并在部署后重新执行指定炉次 065 与当前/上一炉两条 SSE 验收。

## OPS-OPT-MULTI-CONDITION-LLM-REVIEW-20260805

- 目标：把八类炉况的确定性建议与后台大模型分数复核接入参数优化页，同时保持模型和非当前炉况都不能越过规则、安全门禁与审批。
- 数据流：`诊断快照 -> recommendation_adapter.generate_recommendation_bundle -> 8767 recommendation_bundle -> 前端八炉况选择 -> 所选炉况曲线/动作详情`；模型支线为 `所选炉况白名单上下文 -> POST /api/diagnosis/model-review -> 结构化只读复核`。
- 唯一有效方案：只有 `active_plan` 合并实时主/次炉况。次炉况独立项标记 `supporting`，其余标记 `hypothetical`；任何条件预案都不进入当前执行队列。
- 运行状态：前端实现 preparing、retrieving、reasoning、completed、failed、stopped；模型失败或停止只影响解释面板，不影响规则建议和动作审计。
- 配置/缓存：`BF_DIAGNOSIS_MODEL_REVIEW_ENABLED=1`、`BF_DIAGNOSIS_MODEL_REVIEW_CACHE_SECONDS=900`；缓存仅在代理进程内，键包含规范化快照、所选炉况和模型身份。
- 测试：新合同 8 项、v5 引擎 11 项、综合静态合同 8 项、Babel 语法均通过；Chromium 九视口无横向溢出。Firefox/WebKit 未在本轮环境运行，保持未验收状态。
- 发布边界：本轮仅本机代码/文档/隔离浏览器验收；未停止、修改或重启 220.12 的 8093/8768/11434/数据库服务，未写生产数据库。

## OPS-FOREMAN-TREND-STANDALONE-PREVIEW-20260805

- 目标：为现场工长趋势截图提供独立可比的 HMI 预览页，避免影响当前正式趋势工作流。
- 依赖：静态文件 `foreman_trend_preview.html`、本地 ECharts、现有 8767 WebSocket；`fixture=1` 只作为布局验收夹具。
- 运行方式：8092 启动后访问 `foreman_trend_preview.html?fixture=1`；真实数据访问 `?ws_port=8767`。220.12 生产入口为 `http://10.30.220.12:8093/foreman_trend_preview.html?ws_port=8768`，复用既有 8093 静态服务和 8768 PostgreSQL 分钟流；页面只读，不新增数据库、计划任务或远端服务。
- 验收入口：`tests/test_foreman_trend_preview.py`、`tools/verify_foreman_trend_preview.cjs`、`tools/verify_foreman_trend_viewports.cjs`；报告存放在 `logs/foreman_trend_preview_20260805/`。
- 保护条件：不得把该预览页链接改写为正式 `#trend` 替换；2026-08-05 已在确认分钟实际数据绑定后通过 [受控部署器](../tools/remote_deploy_8093_foreman_trend_preview.ps1) 上线。备份为 `backups\\8093_foreman_trend_preview_20260805\\20260805_142959`，8093=`6892`、8768=`15824` 的 PID 前后不变。远端 Chromium 只读冒烟为 PASS：数据时间 `14:30:00`、29 项真实值/20 项真实缺失、`12/12` 与 `5/5` 曲线、无横向溢出、页面和控制台错误为 0；报告为 [remote_8093_live_report.json](../logs/foreman_trend_preview_20260805/remote_8093_live_report.json)。
## OPS-22012-DIRECT-SOURCE-RELAYS-20260805

- 目标：VPN 客户端只访问 220.12，即可进入 IMES Web，并通过固定端口连接
  Vastbase 与 pSpace。
- 程序：[Nginx补丁器](../tools/patch_22012_nginx_imes_web.py)、
  [受控部署器](../tools/remote_deploy_22012_direct_source_relays.ps1)、
  [只读探针](../tools/remote_probe_22012_direct_relays.ps1)。
- 网络合同：`18080 -> IMES Web`、`15433 -> Vastbase`、`18889 -> pSpace`；
  只允许核实的 VPN 客户端地址，数据库和 pSpace 认证合同不变。
- 实际结果：2026-08-05 Web HTTP 200，两条 TCP 成功；远端结果文件确认
  8093/8768/8094/8770 PID 前后不变；Nginx SHA-256 为
  `1FF815F024098B7E94A5158222B27F22A218A789A4A1D330380BA100745A6294`。
- 凭据：不进入 Nginx、portproxy、防火墙、日志或部署结果；IMES 登录仍在浏览器
  会话内完成，验证码按浏览器安全确认流程处理。

## OPS-8093-PSPACE-CONNECTION-AUDIT-20260805

- 分层链路：核心当前值为 `243:8889 pSpace -> 220.12:8770 -> aTrust应用代理浏览器 -> 8093页面`；分钟历史为 `pSpace历史 -> one_minute_values -> 8768 -> 8093`。本机系统路由和浏览器应用代理不是同一健康信号。
- 运行验收：2026-08-05 20:58–20:59，浏览器横幅为 `pSpace秒级实时 28/28`；7秒观察窗内最新时间推进6秒，指标年龄约8秒、质量良好、无降级，且无8770/pSpace/WebSocket页面错误。
- 变更边界：未改代码、配置、计划任务、数据库或生产服务；未重启8093/8770/8768/8094。健康链路只做只读证据采集。
- 存储语义（本次只读审计时）：当时仍为raw/sample。后续同日已按 `REQ-PSPACE-MINUTE-CANONICAL-AVERAGE-20260805`完成向前统一；该段仅保留为故障发现证据，不再代表现行配置。

## OPS-22012-IMES-MCP-PRODUCTION-SYNC-20260805

- 数据流：`8093口语 -> 生产领域路由 -> 四服务注册表 -> 按需启动对应stdio MCP -> 厂内只读数据源 -> 工具结果 -> SSE回答`。
- 发布流：`远端身份/基线哈希 -> 阶段文件哈希 -> 暂停8093守卫 -> 备份 -> 停止8093 -> 原子部署/配置补丁 -> py_compile -> 启动8093 -> 恢复守卫 -> HTTP/注册表/PID/哈希验收`。
- 安全边界：只重启 `BFV4PreviewProxy8093`；8768/8094/8770 PID 必须保持不变。注册表和服务配置只保存厂内端点及凭据环境变量名，不保存密码、Cookie 或验证码。
- 生产结果：四服务注册成功、MES 目录 315 项、当前炉次 72 小时门禁生效；8093=`14352`，受保护 PID 8768=`4340`、8094=`14416`、8770=`12956` 未变化，守卫恢复为 `Ready`。
- 业务验收：自动路由 MES 问题约 `6.69s`，自动路由炉身 13 层 C 点约 `22.22s`；两者均产生 MCP 工具事件。完整记录见[生产交接](handoffs/2026-08-05-22012-imes-mcp-production-sync.md)。

## REQ-PSPACE-MINUTE-CANONICAL-AVERAGE-20260805

- 数据流：`243 HisReadRaw -> 单次返回 -> raw_5s_values(30天) + Good raw分钟平均 -> one_minute_values(3年) -> 8768`；8093当前值另走`243 RealReadList -> 8770`。
- 调度：`BlastFurnaceV3PgContinuousSync30s`每30秒回看10分钟；Watchdog只做值守补漏；旧Realtime禁用。中文主目录与镜像包装器共用项目根排他锁。
- 质量：预期12样本/分钟但不补零，保存实际样本数、Good数、覆盖率、min/max/last和闭窗状态；60秒水位后才标完整。
- 生产结果：2026-08-05 21:55切换，备份`logs/deploy_backups/pspace_minute_average_20260805_220434`；历史sample标签保留；逐行重算无差异，133点同步错误0。
- 安全：pSpace凭据只在220.12 Machine环境；8093/8094/8768/8770未重启。完整说明见[pSpace分钟语义统一](pSpace分钟语义统一_20260805.md)。

## OPS-8093-8094-RECOMMENDATION-SYNC-20260806

- 链路：`三规二制政策/规则 -> 调控结论生成引擎 -> 8768 -> 8093与8094建议页`；两个页面使用同一引擎实例和同一输出契约。
- 发布：依据本地 20 文件 SHA-256 清单原子替换、重启 `BFV4PreviewWs8768`、逐文件远端复核；8093/8094 HTTP PID 保持不变。
- 契约：一次返回 8 类炉况；动作审计字段完整，状态仅允许 `eligible/blocked/needs_data/manual_confirm`，模型复核不覆盖规则建议。
- 结果：8768 PID `4340 -> 16200`，8093=`12368`、8094=`14416` 未变化，两页 HTTP 200。详见[生产交接](handoffs/2026-08-06-8093-8094-recommendation-engine-sync.md)。

## OPS-8093-ASSISTANT-FETCH-RESILIENCE-20260806

- 需求/错误：修复 8093 反复 `Failed to fetch`，并阻止并行部署/恢复再次制造端口空窗；对应 `REQ-8093-ASSISTANT-FETCH-RESILIENCE-20260806` 与 `ERR-8093-ASSISTANT-DEPLOYMENT-COLLISION-20260806`。
- 取证：首次门禁为 22/5432/11434 正常、8093 不通；SCM 在 09:57～10:29 多次停启，stderr 只有受控 `KeyboardInterrupt`，诊断期间后端/配置哈希变化。2026-08-05 的连接复用补丁已存在，当前默认检索能返回 keyword 证据，因此本轮不归因于 `PoolTimeout`。
- 程序：[统一编排器](../tools/assistant_8093_auto_recovery.py)、[合并诊断](../tools/remote_8093_assistant_diagnose.ps1)、[受控服务恢复](../tools/remote_guarded_recover_8093_service.ps1)、[页面补丁器](../tools/patch_8093_assistant_fetch_resilience.py)、[无停机页面部署器](../tools/remote_hot_deploy_8093_fetch_resilience.ps1)、[唯一 SSE 验收](../tools/remote_verify_8093_keyword_knowledge_sse_once.ps1)。
- 互斥/容错：新 8093 写入流程使用 `Global\BFV4PreviewProxy8093Deployment`；页面 GET 按 1.5/3 秒退避，POST/SSE 永不自动重发；诊断合并监听快照，8093 下线时不等待其 HTTP 超时。
- 页面发布：2026-08-06 10:41 原子热更新，备份 `logs/deploy_backups/8093_fetch_resilience_20260806_104046`，SHA-256 `4C552C...D31262 -> 4394D60B...FAC00`；8093/8094/8768/8770/11434 PID 保持 `7824/15064/9824/2096/12456`。
- 最终验收：本地报告 [20260806_105139_recover.json](../logs/assistant_8093_auto_recovery/20260806_105139_recover.json) 前后均 `healthy`、`repairs=[]`、`request_count=1`。事件 `preparing → prepared → delta → final → done`，首 delta `12272.7ms`、总计 `33993.3ms`；keyword 证据 2 条，只驻留 `chiqiong-blast-furnace:latest`，守卫计数 0 且所有受保护 PID/哈希不变。
- 回归：页面容错、自动恢复、PostgreSQL 连接复用、健康合同与 DOCX 合同组合 `41 passed`；Python 编译通过。
- 预置：完成文档和监听快照优化后，于 11:07 通过连通性门禁预置包 `20260805_v2_72eff4ce55d3`；报告 `logs/assistant_8093_auto_recovery/20260806_110722_prestage.json`。该阶段只上传不可变文件并验 SHA，不触碰服务或发送问答。

## OPS-8093-8094-DIAGNOSIS-CORE-19-TRENDS-20260806

- 数据流：`最新诊断 + bf_sensor分钟值 + 30天基线 -> build_core_variable_evidence -> /api/diagnosis-core-evidence -> 评分弹窗19项证据/60分钟曲线`；不经过模型、调剂引擎或知识库。
- 8093发布：本机生成并测试payload，逐文件上传；暂停 `BFV4PreviewProxy8093`，原子替换，在 `finally` 恢复。2026-08-06 11:20成功，备份 `logs/deploy_backups/diagnosis_ai_analysis_20260806_112034`，`guard_paused/restored=true`、`rollback=false`、HTTP 200、8768 PID不变。
- 异常记录：第一次r7部署仍以完整模型完成作为上线前置，长等待后资源请求遇到服务短窗，脚本自动回滚；端口复核确认8093/8768/8094/8770均恢复。随后把上线硬门槛改为独立轻量接口19/19，完整智能分析改为运行时异步验证。
- 网络边界：8094首次继续部署时SSH出现10060/10053，随后端口22探测超时；远端脚本未启动，不能把该事件归为8094代码失败。
- 本机可复现：合同 `44 passed`，跨浏览器 `17/17`；远端只读验证使用 `verify_diagnosis_core19_remote.py --lightweight`。

## REQ-FOREMAN-COLD-BLAST-PRESSURE-20260806

- 目标：把“加几个压/减几个压”唯一绑定到 `P_blast_cold`（冷风压力），把 `Q_blast` 保留为证据变量；喷煤动作唯一绑定 `PCI_set`。所有动作仍为只读建议，必须工长审批。
- 数值口径：压力硬下限 `400 kPa`、动态 30 天 Q3 为加压上限；压力步长按分数为 `3/5/10 kPa`。喷煤范围 `10–45 t/h`，普通步长 `1/2/3 t/h`，严重停煤候选为 `0 t/h`，普通建议生效于下一个整点。
- 程序与合同：[foreman_dual_control.py](../自动诊断服务/foreman_dual_control.py)、[recommendation_audit_store.py](../自动诊断服务/recommendation_audit_store.py)、[local_pg_ws_bridge.py](../自动诊断服务/local_pg_ws_bridge.py)、[双变量运行时验收器](../tools/verify_foreman_dual_control_runtime.py)。输出版本 `foreman-dual-control-v2`，控制范围版本 `foreman_dual_control.v2`。
- 数据库：220.12 `bf_sensor.daily_baselines` 已新增真实 `p25/p75`；审计表已安装 `recommendation_audit.v2` 字段。最新窗口为 `2026-07-08 00:00` 至 `2026-08-06 23:59`，`P_blast_cold` Q1=`449.374719`、Q3=`458.485260`、样本=`42747`、覆盖率=`0.989514`；未伪造任何基线行。

## OPS-ABC33-BASELINE-COVERAGE-20260809：全量30天基线重建

- 需求：逐项查清 ABC33 规则所需基线不足，修复一次性历史重建和每日 30 天维护程序，并用 220.12 已回填数据重新计算。
- 程序：`自动诊断服务/baseline_maintainer.py`、`tools/run_abc33_baseline_rebuild.ps1`、`tools/run_v4_daily_baseline.ps1`、`tools/verify_abc33_baseline_coverage.py`。
- 数据：`bf_sensor.one_minute_values -> bf_sensor.daily_baselines`；必需集合固定 137 项，最低有效覆盖率 75%。
- 修复前：83 项已有基线低于门禁，包括 74 个炉体温度点、4 个短历史工长点位、2 个南北料线、`P_soft_water`、`T_top_B` 和派生 `T_top`。
- 生产结果：2026-08-09 重建后 `required=137`、`available=137`、`missing=0`、`below_coverage=0`、`invalid_statistics=0`；计划任务继续使用 `\BlastFurnace8093DailyBaseline20d`，但动作已统一为 V4 全量构建加严格门禁。
- 边界：普通状态量最多保持 5 分钟，炉体温度最多 15 分钟；不跨长断档、不补零；膨胀罐按小时均值到日均值；铁口温度均值仍严格同分钟对齐。
- 完整证据：[交接记录](handoffs/2026-08-09-abc33-baseline-coverage-repair.md)。
- 部署闭环：完整 36 文件清单 `logs/deployment/8093_8094_recommendation_sync_20260806_r3/recommendation_sync.zip`，归档 SHA-256 `EF6F4F690C1D5003A15937ACC4E93EE2C6DA10FC19B9145AB9AE2147A23A5539`。先迁移数据库，再重启 `BFV4PreviewWs8768`，按共享 `8768` 更新 8094 并重启 `V3AutoPreviewProxy8094`，最后执行 8093 守卫停—部署—恢复。远端备份为 `backups\\foreman_dual_control_20260806\\20260807_004850`。
- 生产验收：8768 独立 WebSocket 返回 8 类炉况、16 条动作，四状态均可见（`blocked/eligible/manual_confirm/needs_data`）；控制变量集合严格为 `P_blast_cold/PCI_set`，`Q_blast` 仅证据。8093/8094 HTTP 均 `200`；8094 PID `16412 -> 1264`；8768 PID `14628 -> 18288`；8770、11434 PID 未变化；`BFV4PreviewProxy8093` 与 `BFV4PreviewWs8768` 均为 `Running`。
- 回归：`42 passed`；变更 Python 编译通过；生产 HTML 使用页面自身 Babel 解析通过；两个页面均包含视觉工作台标记、禁用旧前端回退标记和共享 8768 绑定。完整结果见 [2026-08-06-foreman-dual-control-migration.md](handoffs/2026-08-06-foreman-dual-control-migration.md)。

| REQ-8093-DIAGNOSIS-FOREMAN-KNOWLEDGE-ADVICE-20260807 | 5分钟智能分析只使用64主题高炉长知识库，逐项解释19个核心传感器，隐藏知识正文并通过详情链接查看 | 高炉前端数据/智能助手/backend/ollama_proxy_server.py、diag_ai_evidence.py、diagnosis_model_review.py、assets/bf-diagnosis-manual-score-local.js、bf_knowledge_rag.py | python -m pytest tests/test_diagnosis_ai_analysis.py tests/test_8093_assistant_pg_pool_reuse.py -q --basetemp D:\文件\冀南钢铁运行中第二版本\.tmp_pytest_diagnosis；知识来源固定为 bf_foreman_ops_v1，候选方向为只读人工确认 |

## OPS-BODY-TEMP-INFRARED-REPLAY-8892-20260808

- 需求：`REQ-BODY-TEMP-INFRARED-REPLAY-20260808`。
- 运行：220.12计划任务`\BlastFurnaceServices\SoftZoneTemperatureReplay8892`直接执行Python服务，监听`0.0.0.0:8892`，日志写入`logs\soft_zone_replay_8892.log`。
- 数据：只读`bf_sensor.sensor_registry`和`bf_sensor.one_minute_values`；无数据库写入、无生产控制写入。
- 部署：`remote_deploy_22012_soft_zone_replay_8892.ps1`执行备份、逐文件原子替换、任务/防火墙注册、真实数据查询和8093/8094健康门禁。
- 2026-08-08验收：8892任务Running；8093/8094 HTTP 200；最终曲线版部署中8093/8094/8768/8770 PID均未变化；真实80个温度点/18个静压力点载荷、温度8线/压力6线和浏览器生产冒烟通过。

## BUG-8093-DIAGNOSIS-AI-FALSE-DATA-LIMITS-20260808

- 现象：8093 五分钟智能分析把 `L_north`、`L_south`、`T_top_A-D` 的低采样密度显示成“数据限制”。
- 根因：这些点位在 220.12 注册表启用且有当前值/趋势，但旧提示词直接读取逐变量覆盖率，把采样密度误当成可用性。
- 修复：[diag_ai_evidence.py](../高炉前端数据/智能助手/backend/diag_ai_evidence.py) 由服务端按有效当前值或 60 分钟序列判定限制；[diagnosis_model_review.py](../高炉前端数据/智能助手/backend/diagnosis_model_review.py) 使用 v6 提示词并移除逐变量采样密度输入；[bf_knowledge_rag.py](../高炉前端数据/智能助手/backend/bf_knowledge_rag.py) 同步接受64主题知识库的来源过滤参数。
- 部署器：[8093 专用守卫部署器](../tools/remote_guarded_deploy_8093_ai_data_limit_fix.ps1) 只暂停/恢复 `BFV4PreviewProxy8093`，不操作 8094、8768、8770 或数据库。
- 证据与交接：[修复交接记录](handoffs/2026-08-08-8093-ai-data-limit-fix.md)。

## OPS-FOREMAN-PSPACE-EXTRA-METRICS-8770-20260808

- 目标：在不增加 pSpace 常驻读取程序的前提下，把工长趋势正式扩展点位接入既有 `V4BillboardPspace8770` 实时桥。
- 入口：[pspace_8092_realtime_bridge.py](../tools/pspace_8092_realtime_bridge.py)、[remote_deploy_foreman_pspace_extra_metrics_20260806.ps1](../tools/remote_deploy_foreman_pspace_extra_metrics_20260806.ps1)。
- 端口/任务：8770 仍由 `\BlastFurnaceServices\V4BillboardPspace8770` 维护；页面为8093工长趋势，8768分钟历史和8094均为受保护对象。
- 运行态：部署后157个流值、17个工长扩展值全部数值；最终8093/8094/8768/8770监听PID为4788/13748/10832/3732。
- 验收命令：[verify_billboard_pspace_8770.py](../tools/verify_billboard_pspace_8770.py) 与 [inspect_foreman_trend_remote_points.cjs](../tools/inspect_foreman_trend_remote_points.cjs)；浏览器状态必须为“pSpace秒级已连接 · 分钟历史已连接”。

## REQ-SI-V20-8093-8094-SHADOW-WORKBENCH-20260808

- 目标：独立展示候选炉次、当前 V20 影子预测、历史实际/预测曲线，并在后续化验到库后自动完成逐炉对比。
- 入口：[V20服务](../高炉前端数据/智能助手/backend/si_v20_shadow.py)、[独立页](../高炉前端数据/si_v20_workbench.html)、[快速部署器](../tools/deploy_si_v20_workbench_8093.ps1)。
- 数据合同：候选读220.12本地 `bf_imes.raw_rows`；实际平均Si读 `heat_performance_quality_summary.si_avg`；`requested_at` 与 `prediction_cutoff_ts` 分开保存；当前炉/未来化验禁止进入输入。
- 验收：本机后端8项、镜像回补单测、Chromium/Firefox/WebKit代表视口通过；220.12 8093状态接口和独立页面已验证。8094页面已存在，8094后端需另行受控同步。
- 运行态：`experimental_shadow`，只写预测审计，不改生产设定值。
- 2026-08-09 自动刷新闭环：五分钟任务与 API 实测正常；修复一年 immutable JS 使用旧版本 URL、跨午夜日期不推进和旧无时间占位优先三个页面侧缺陷。资源版本为 `20260809-auto-refresh-r2`，受控部署后最新实际 125 炉、候选 126 炉，真实 Chrome 冒烟通过。

## REQ-SI-V20-STRICT-HOURLY-CLOSED-LOOP-20260810

- 目标：建立与可调定时完全独立的严格自然整点基线，服务在稍后执行时仍只看`HH:00:00`及以前已到库数据。
- 程序：[严格上下文](../高炉前端数据/智能助手/backend/si_v20_strict_context.py)、[槽与审计服务](../高炉前端数据/智能助手/backend/si_v20_shadow.py)、[分钟任务](../tools/register_22012_si_v20_strict_hourly_task.ps1)、[工作台](../高炉前端数据/si_v20_workbench.html)。
- 数据/时间：Si首次可用时间不可覆盖；传感器业务时间与采集时间双门禁；整点、截止、发起、完成、最大数据时间、初始候选和固定实际炉次全部固化。
- 本机证据：相关回归`34 passed`，JS与PowerShell语法通过，纯Python模型与原LightGBM误差`1.11e-16`。
- 生产状态：2026-08-10 01:49最终受控部署，备份`backups\si_v20_strict_hourly_20260810\20260810_014636`；任务为SYSTEM/每分钟/IgnoreNew，最近完成结果0。首个01:00槽在两次受控修正后成功，发起`01:08:45.298`、完成`01:08:46.570`、P50=`0.318322%`，固定实际炉次仍等待下一炉。空参数人工补跑返回同一预测ID且领取槽数0，未产生重复。
- 验收：数据库表/唯一性/整点截止/Si可用时间检查通过；8093、8094各自17组规定浏览器/视口矩阵通过，无横向溢出与页面错误。9484条迁移前Si标记`legacy_availability_unknown`且严格首槽未读取，符合不伪造历史实时可见性的合同；未来新炉Si将记录真实首次可用时间。
- 待运行观察：需在2026-08-11 01:00后再证明连续24个自然小时形成24槽；当前只有首槽，不能提前宣称24小时连续性已经实测完成。
- 独立只读审查：未发现P0；提出GET状态/历史存在领域写入的P1后已修复并生产复验，连续5轮GET前后槽时间、尝试次数、预测ID和历史数量均不变。仍未关闭的P1只有“首个实际炉次尚未开口/化验”和“真实24小时尚未经过”，两者必须等待外部状态推进。
# 2026-08-10 ABC33 实时复合因子与南探尺基准

- 需求：`REQ-ABC33-REALTIME-FACTOR-LINE-20260810`。
- 主料线改为 `L_south` 的5分钟非负有效最大值，`L_north`只作为固定零偏校正后的辅助证据；同时保存两尺有效最大/最小、固定偏差偏离和下降速率差。
- pSpace实时同步增加可审计的有限状态保持：炉体20分钟、普通冷却10分钟、膨胀罐70分钟、料线10分钟；保持值使用 `PS_STATE_HOLD/bounded_state_hold_v1`，不冒充原始采样。
- 相关程序：`自动诊断服务/abc_feature_builder.py`、`自动诊断服务/config/abc_furnace_rules.v1.json`、`数据库同步和存取/src/raw_minute_pipeline.py`、`数据库同步和存取/src/sync_from_243_pg.py`、`数据库同步和存取/src/pg_store.py`、`数据库同步和存取/config/sync_config.json`。
- 测试：ABC相关109项通过；南探尺口径快照33/33可算、缺项0。
- 运行证据和待补验收见 `docs/handoffs/2026-08-10-abc33-realtime-factors-and-south-line.md`。

## REQ-OPS-POWERSHELL7-UTF8-20260810

- 目标：本机项目受控入口统一迁移到PowerShell 7 Core和UTF-8，禁止新命令或任务静默回退Windows PowerShell 5.1。
- 环境：2026-08-10通过官方WinGet包安装`Microsoft.PowerShell 7.6.4.0`，实际程序为`C:\Program Files\PowerShell\7\pwsh.exe`。
- 程序：[真实运行时验证器](../tools/verify_pwsh7_utf8.ps1)、[主启动入口](../start_v3_full.ps1)、[隐藏任务包装](../tools/run_hidden_ps1.vbs)。
- 文档：[AGENTS强制约束](../AGENTS.md)、[运行规范](./PowerShell7_UTF8运行规范.md)、[需求追踪](./requirements_traceability.md)、[测试参考](./test_reference.md)。
- 边界：不删除Windows内置5.1系统文件；本轮不修改非本项目计划任务，也不把本机安装状态外推为220.12已安装。远端旧入口按主机逐项迁移。
- 验收：PowerShell 7真实UTF-8回环`ok=true`；静态合同`4 passed`；Windows Terminal默认配置切到PowerShell 7，原配置备份后仅隐藏5.1入口。

## OPS-22012-POWERSHELL7-UTF8-20260810

- 目标：在不重启生产服务、不批量改计划任务的前提下，为220.12安装PowerShell 7并将远程运维跳板默认切到UTF-8 `pwsh.exe -File`。
- 环境：Windows Server 2016 Standard；原5.1.14393.206；无WinGet；安装后PowerShell`7.6.4 Core`位于`C:\Program Files\PowerShell\7\pwsh.exe`。
- 安装证据：官方MSI SHA-256=`D11942DF52FD12470169797ABFA4781D9480EFDC81000BA4FA55A5B921ED8DD0`，Microsoft签名有效，msiexec退出0，`reboot_required=false`。
- 程序：[远端跳板](../tools/remote_22012_exec.py)、[安装器](../tools/remote_install_22012_pwsh7.ps1)、[验证器](../tools/remote_verify_22012_pwsh7.ps1)、[冒烟](../tools/remote_smoke_22012_pwsh7.ps1)。
- 运行证据：中文输出和文件回环通过；6个关键脚本语法通过；8093/8094/8768/8770/5432 PID安装前后为`4044/4156/8524/3732/12372`；远端安装临时文件已清理。
- 边界：现有生产计划任务仍保持原Action，后续必须逐项运行验证后迁移，禁止全量替换。

## 2026-08-10 ABC33零分语义、状态对齐与双端试运行发布

- 需求：`REQ-ABC33-FURNACE-RULES-20260807`、`REQ-ABC33-REALTIME-FACTOR-LINE-20260810`。
- 规则语义：风险项允许有效0分；不可计算必须使用 `needs_data` 与空分数，禁止以“非零”作为运行门槛。
- 程序：`自动诊断服务/abc_feature_builder.py`、`abc_rule_engine.py`、`local_pg_ws_bridge.py`、`数据库同步和存取/src/raw_minute_pipeline.py`、`数据库同步和存取/config/sync_config.json`。
- 配置：`20260810.2-score-preview-alerts-off`，分数试运行可见，B/C告警关闭。
- 数据库证据：220.12审计批次654，时间2026-08-10 04:45+08:00，33项、缺失公式因子0、置信度均为1。
- 页面：8093与8094资源版本 `abc33-20260810-score-preview-r1`；8093守卫闭环备份 `backups/abc33_score_preview_ui_20260810_043631`。
- 测试：`python -m pytest tests/test_abc_rule_engine.py tests/test_abc_bridge_live_values.py tests/test_abc_production_ui.py -q`（29项通过）；通用/校准/状态保持测试81项通过。
- 数据核查：`data/abc33_22012_snapshot_20260810_0334/audit/abc33_rule_audit.md`、`abc33_three_day_shadow_replay_20260810.json`、`abc33_point_gap_report.md`。
- 发布边界：当前只展示试运行分数；历史回放显示部分炉体/冷却复合风险持续偏高，未开放B/C弹窗，未增加生产控制写权限。

## 2026-08-10 ABC33公式全字段血缘与生产验收

- 需求：`REQ-ABC33-FULL-AUDIT-ACCEPTANCE-20260810`，补齐每个规则小项的实际0–1因子值、权重、贡献、有效阈值、公式、来源传感器当前值、标准化派生值和30日基线快照。
- 程序：`自动诊断服务/abc_factor_audit.py`、`abc_feature_builder.py`、`abc_rule_engine.py`；全字段仅保存到受保护审计表，生产WebSocket和普通API继续白名单脱敏。
- 生产批次：662（2026-08-10 05:25+08:00），33条、`needs_data=0`、公式复算错误0、阈值错误0、血缘错误0；直接传感器数据库一致135/135，基线一致137/137。
- 零分语义：7条规则总分为0、154个公式小项为0，均为完整计算后的合法结果，不作为服务失败门槛。
- 运行验收：`BFV4PreviewWs8768=Running`；8768 WebSocket返回33条；8093/8094接口HTTP 200且各返回33条；8770/11434监听正常。
- 安全边界：普通生产接口未发现公式、权重、阈值、贡献、来源值或基线快照；匿名后台接口返回403。当前生产后台登录账号未配置，本轮未擅自生成管理员口令。
- 证据：[完整验收报告](handoffs/2026-08-10-abc33-production-acceptance.md)、`data/abc33_acceptance/abc33_acceptance_latest.json`、`data/abc33_acceptance/abc33_runtime_acceptance.json`。
# 2026-08-10 ABC33 C类严重事件交叉确认与逐点复核

- 需求：`REQ-ABC33-C-EVENT-CROSS-CONFIRMATION-20260810`。修复C4/C5/C7同源炉壳特征重复计分和单个冷却点将严重事件推高的问题。
- 程序：`自动诊断服务/abc_feature_builder.py`新增炉体共同偏离、同点偏高且上升、冷却第二独立证据；`abc_rule_engine.py`保留原文初算分并对生产操作分执行独立系统门禁；`abc_public_review.py`提供生产安全逐点详情；8093/8094代理和页面接入v2合同。
- 数据合同：普通详情只返回实际传感器、时间、基线、变化、波动和工艺语义，不返回公式、权重、精确阈值、归一化值或贡献；受保护后台继续保存原文公式初算和完整血缘。
- 测试：ABC相关测试122项通过；三天865批五分钟回放全部成功、0错误、无生产写入、无告警开放。
- 部署：8768受控备份/重启；8093守卫停—改—启；8094计划任务独立重启。最终8093/8094均HTTP 200、33条规则、C7详情100项/炉壳80项/冷却6项/缺数0，8770和11434未受影响。
- 验收报告：`docs/handoffs/2026-08-10-abc33-c-event-cross-confirmation-detail.md`。

# 2026-08-10 V20每小时持续验收、可用时间修复与任务运行时迁移

- 自动化`220-12-v20`每小时执行`tools/audit_si_v20_new_heat_acceptance.cjs`；证据只追加到`reports/acceptance/SI_V20_NEW_HEAT_20260810`，冻结基线130炉不得覆盖，闭环通过后仍继续运行。
- 08:37发现132炉已有平均Si但`si_available_at`为空。原因是`HeatPerformanceQualitySync`仍执行独立目录旧副本；已在保留任务XML和文件备份后更新独立副本，使用`aggregated_at`保守恢复，数据库缺失由1降为0。
- `IMESRealtime`、`HeatPerformanceQualitySync`、`SiV20StrictHourlyPrediction`、`SiV20ScheduledShadowPrediction`均已逐项迁移到PowerShell 7.6.4；远端探针现在记录每项Action并拒绝V20相关`powershell.exe`。
- 复验：01:00~08:00八个严格槽全部成功，重复/非整点/截止违规/陈旧/逾期为0；133炉已在08:52自动回填，严格预测6条完成评价、±0.05命中率50%。8093/8094、8768/8770/5432、每小时汇总表和CSV正常。最新通过证据为`reports/acceptance/SI_V20_NEW_HEAT_20260810/20260810T005251Z_check.json`。

# 2026-08-10 软熔带移动预测Word本机代码化

- 需求：`REQ-COHESIVE-ZONE-INTELLIGENT-DIAGNOSIS-20260810`；来源Word提供14类过程特征、上移/下移经验组合和4类炉况关联，但没有真实`H_cz`标签或训练参数。
- 程序：[特征融合诊断](../炉况规则引擎/features/cohesive_zone_intelligent_diagnosis.py)、[YAML参数](../炉况规则引擎/config/cohesive_zone_intelligent_diagnosis.yaml)、[CSV CLI](../tools/run_cohesive_zone_intelligent_diagnosis.py)、[验证入口](../tools/verify_cohesive_zone_intelligent_diagnosis.ps1)。
- 运行合同：15分钟当前窗口、15分钟隔离、15分钟参考；只读评价截止及以前数据；缺失不补0；压力/透气性和温度场为必需分组；输出方向概率、特征/趋势向量、逐项驱动和关联证据。
- 安全合同：固定`estimated/uncalibrated/control_use=prohibited/confidence<=0.45`；关联证据不覆盖现有8类炉况或ABC33分数；未冒充Chronos-2、TabPFN或Transformer训练结果。
- 验收：专项与既有C2估算器合计`30 passed`，CLI CSV→UTF-8 JSON通过，PowerShell 7.6.4 Core与UTF-8检查通过。未新增API/schema/task，未连接或修改本机/220.12数据库，未部署远端。
# 2026-08-10 ABC33手册形成原理与五步处置接入建议页面

- 需求：`REQ-ABC33-HANDBOOK64-MECHANISM-INTERVENTION-20260810`。
- 数据流：见习高炉长64章映射与ABC33补充文档 → `tools/export_abc_rule_guidance.py`机械导出 → `自动诊断服务/abc_rule_guidance.py`生产安全工艺目录 → `abc_rule_catalog.py`合并到33项规则 → 8768下一批计算写入`public_detail` → 8093/8094详情API白名单输出 → `abc-furnace-rules-production.js`显眼展示。
- 返回合同：沿用`principle`、`intervention_order`、`source_refs`，不扩展内部公式字段；每项形成原理专属、处置严格5步、章节引用至少1条。
- 页面位置：每条A/B/C规则点击“查看复核详情”后，状态卡下方优先展示“炉况形成原理”和“五步干预处置流程”，其后才是逐点传感器、缺数、人工复核、观察窗口与审批要求。
- 安全边界：本目录只含工艺层说明；公式、权重、精确阈值、归一化值、贡献和内部特征仍由后台保护。所有处置为只读建议，不授予生产写权限。
- 本机验收：Python/JavaScript语法通过，ABC33全套相关回归`128 passed`；本地浏览器夹具验证两个新增板块、5个有序步骤、手册章节和审批信息完整可见。
- 8093部署状态：2026-08-10 12:48已完成。先受控重启`BFV4PreviewWs8768`，再按`BFV4PreviewProxy8093`守卫停—改—启发布页面资源；最新API批次目录版本为`abc33-catalog.v3.handbook64-guidance`，返回33条规则、A1专属原理、严格5步流程和7条手册章节。
- 同批次修复：`abc_runtime_store.py`在`(furnace_id,evaluation_ts,config_hash)`冲突时同步刷新目录版本、配置版本、数据质量和公开包，避免页面内容已更新但批次元数据仍显示旧`v2.calibrated`。合同测试与规则/页面测试合计`31 passed`，ABC33全套相关回归`129 passed`。
- 运行隔离：8093 PID由`2044`变为`10008`，8768最终PID=`18436`；8094=`2988`、8770=`3732`、11434=`5968`均未重启。8094页面哈希保持不变，因此本次不得表述为8094已同步。

# 2026-08-10 HCZ专家弱标签8892部署

| 需求 | 程序 | 配置/任务 | 表/API | 验证 | 文档 |
|---|---|---|---|---|---|
| `REQ-HCZ-EXPERT-WEAK-LABEL-20260810`：无直接HCZ真值时由高炉长盲标并可追溯收集 | [标签合同](../高炉前端数据/智能助手/backend/hcz_expert_label.py)、[8892服务](../tools/soft_zone_replay_server.py)、[页面](../高炉前端数据/soft_zone_replay/hcz-labeling.html) | [运行入口](../tools/run_22012_soft_zone_replay_8892.ps1)、任务`SoftZoneTemperatureReplay8892`、[受控部署](../tools/remote_guarded_deploy_hcz_expert_label_8892.ps1) | [DDL](../高炉前端数据/智能助手/backend/schema/postgresql_hcz_expert_label.sql)、`/api/hcz-label-*` | [pytest](../tests/test_hcz_expert_label.py)、[17视口矩阵](../tools/verify_hcz_expert_label_ui.cjs)、[生产只读冒烟](../tools/verify_hcz_expert_label_remote_ui.cjs) | [交接](./handoffs/2026-08-10-hcz-expert-weak-label-production.md) |

自动化边界：任务只负责8892常开服务；不自动生成标签、不自动训练、不自动修改控制值。部署前备份文件和任务XML，失败恢复原任务/文件；成功后要求PowerShell 7 Action、真实API/页面、非法提交不落库及五个受保护端口PID不变。

# 2026-08-10 HCZ上移综合趋势经验规则8093部署

| 需求 | 程序 | 配置 | API/表 | 验证 | 文档 |
|---|---|---|---|---|---|
| `REQ-HCZ-UPWARD-EXPERT-RULE-20260810`：把高炉长综合经验公式固化为一个只读判断并上线8093 | [规则引擎](../炉况规则引擎/features/hcz_upward_expert_rule.py)、[8093适配器](../高炉前端数据/智能助手/backend/hcz_upward_rule_api.py)、[页面](../高炉前端数据/hcz_upward_rule.html) | [YAML](../炉况规则引擎/config/hcz_upward_expert_rule.yaml)、[受控部署](../tools/remote_guarded_deploy_hcz_upward_rule_8093.ps1) | `GET /api/hcz-upward-rule`；无新增表、无写API | [专项pytest](../tests/test_hcz_upward_expert_rule.py)、[17视口](../tools/verify_hcz_upward_rule_ui.cjs)、[生产Edge](../tools/verify_hcz_upward_rule_remote_ui.cjs) | [规则](./GL02软熔带上移综合趋势经验规则_20260810.md)、[交接](./handoffs/2026-08-10-hcz-upward-expert-rule-8093.md) |
| `REQ-HCZ-COLD-BLAST-PRESSURE-20260811`：风压口径改为真实冷风风压 | [规则配置](../炉况规则引擎/config/hcz_upward_expert_rule.yaml) | `P_blast -> P_blast_cold`；[只读预检](../tools/remote_probe_hcz_cold_blast_pressure_8093.ps1)；[单文件受控部署](../tools/remote_guarded_deploy_hcz_cold_blast_pressure_8093.ps1) | API路径不变；无数据库写入 | [专项pytest](../tests/test_hcz_upward_expert_rule.py)、[页面验收](../tools/verify_hcz_upward_rule_remote_ui.cjs) | [生产交接](./handoffs/2026-08-11-hcz-cold-blast-pressure-8093.md) |

运行边界：API请求时只读144小时分钟实测并缓存120秒，不新增自动任务；页面不写生产控制。最终部署通过8093守卫停—改—启，PID由12616变为15224；8094/8768/8770/5432/8892均未重启。真实结果为`not_triggered`，生产Edge无错误。

# OPS-8093-GUARDED-UPDATE-SKILL-20260810

- 自动化目标：把8093功能部署统一为“本机测试→远端只暂存→生产临界区→原子安装→服务恢复→业务与隔离验收→失败回滚”，减少临时命令、并发部署碰撞和守卫未恢复风险。
- Skill入口：项目版本源`.codex\skills\deploy-8093-guarded-update\SKILL.md`同步到全局`C:\Users\hmw20\.codex\skills\deploy-8093-guarded-update`运行镜像；只有用户明确授权生产部署时才允许进入远端写阶段，说明/评审/排障保持只读。
- Skill同步层：`tools/sync_deploy_8093_guarded_update_skill.ps1`使用14文件精确白名单；`ImportGlobalToProject`只作首次导入/恢复，`PublishProjectToGlobal`是日常发布方向，`Verify`要求两侧bundle SHA-256一致。同步只发生在本机，不调用SSH、服务管理或生产写入。
- 本机层：先由`tools/remote_22012_session.py ensure`建立或复用localhost代理持有的已认证Paramiko transport，再把`run -- --upload-only`和`run -- --script`作为两个独立channel调用；复杂payload保持为独立UTF-8 `.ps1`，禁止`-Command`/`EncodedCommand`传输正文。部署后保留会话；传输中断不自动重放远端命令。
- 远端层：非阻塞获取`Global\BFV4PreviewProxy8093Deployment`；校验基线哈希和暂存标记；备份；通过`manage_22012_managed_services.ps1`只暂停/恢复`BFV4PreviewProxy8093`；确认8093端口空窗；目标邻近临时文件原子替换；失败恢复备份；最终释放互斥。
- 验收层：必须同时证明新文件哈希、缓存版本/需求标记、8093 HTTP/API、`guard_paused/guard_restored/rollback_applied`、新监听PID和8094/8768/8770/5432/11434等受保护PID。HTTP 200或`Start-Service`单项成功不构成上线完成。
- 创建验收：Skill Creator结构校验通过；PowerShell 7.6.4只读合同验证通过并解析2份模板；`remote_write_performed=false`。本次没有上传文件、停止服务或修改220.12。

# OPS-22012-PERSISTENT-SSH-AND-PYTHON-PROTECTION-20260810

| 需求 | 程序 | 配置/状态 | 执行入口 | 测试 | 文档 |
|---|---|---|---|---|---|
| 220.12命令复用同一个SSH认证连接，并把可选Python源码保护加入8093 Skill | `tools/remote_22012_session.py`、`tools/remote_22012_exec.py::execute` | `%LOCALAPPDATA%\Codex\ssh-sessions\22012.json`只含localhost端口、随机令牌和会话身份；凭据只在代理内存 | `pwsh.exe -File tools/start_remote_22012_session.ps1`；后续`remote_22012_session.py run -- ...`；正常部署后不stop | `tests/test_remote_22012_persistent_session.py`；Skill合同/结构验证；PowerShell 7 UTF-8验证 | Skill的`project-contract.md`与`python-artifact-protection.md` |

固定状态机：`ensure→active/authenticated→run(channel N)→keepalive→run(channel N+1)`；只有请求之间检测到transport失效才重连。远端执行期间掉线返回`uncertain_execution=true`和`automatic_replay=false`，由操作者先核对生产状态，不能把部署命令自动再发一次。

源码保护发生在上传前：`source`保留`.py`；`bytecode`仅作兼容打包且不视为保密；`native`要求本机按Python 3.11 x64用Nuitka standalone/模块或Cython扩展构建、测试并生成清单，只上传`.exe`/standalone/`.pyd`及明确运行依赖。服务入口变更与产物一同备份、验收、回滚。HTML/JS/PS1/JSON不适用Python编译，任何编译产物都不能宣称绝对不可逆向。

# OPS-8093-SKILL-REUSE-METRICS-LEARNING-AND-RSSH-MCP-20260810

自动化链路：8093变更意图触发Skill → 读评审失败规则库 → Phase A本机构建/验证一次，同时运行Luna low最小diff审查与只读远端预检 → 密封`prepared-release` → Phase B刷新远端哈希并生成`delta-plan` → 只上传变化文件 → 8093守卫临界区 → 确定性HTTP/API优先验收 → 必要时浏览器等级验收 → 立即报告`deployed` → 文档/计时/失败指纹。计时与学习记录位于`%LOCALAPPDATA%\Codex\deploy-8093-guarded-update`，不写密码、命令正文、源码或生产响应。

准备清单把源、产物、验证结果、stage/target、允许基线、标记和等级绑定到内容SHA-256。部署脚本重新验证清单并以最新只读生产状态计算差量；任何篡改、源/产物漂移、未评审基线或范围扩大都返回Phase A。零差量不获取部署互斥、不停服务。清单优化只消除重复构建/测试和未变化上传，不削弱远端备份、原子替换、`finally`恢复、回滚或受保护PID检查。

Reliable SSH MCP的220.12固定实例启用一个常驻Plink会话、30秒SSH协议keepalive和60秒只读身份心跳；每个MCP调用仍是独立JSON请求。进程关闭或传输失败后，连接池只在下一次请求前重建；已经发出的命令不自动重放。诊断一键包不再通过`powershell.exe -Command`展开/启动，而由远端runner安全解压ZIP后精确调用`C:\Program Files\PowerShell\7\pwsh.exe -File remote_deploy_diag_rules.ps1`。

# REQ-8093-ABC33-B4-CANONICAL-SCORE-20260810 在线闭环

固定展示流：`abc_rule_evaluation_batches.public_bundle.rules[B4] → load_latest_abc33_review_score → apply_abc33_display_score → 异常复核/手动评分/AI解释`。查询禁止未来批次，优先精确`source_snapshot_id`，否则只接受15分钟内批次；墙钟超过20分钟、规则身份/0～100范围/版本/生产可用状态任一失败均显示`--`。旧`raw_scores.hot`只进入`legacy_score_archive`和事件JSONB的`_display_contract`，不改写历史行。

发布流：`51项本地合同 → 持久SSH upload-only → Global部署互斥 → 备份 → 只停8093 → 五文件原子替换 → 恢复8093 → latest/detail/context/资源/受保护PID验收`。第一次v1载荷因暂存标记与实际JS字面不一致在互斥/停服前停止；v2修正确定性标记后成功。最终批次839的B4和弹窗均为14.9623，旧分28.12保留，8768及数据库未修改。

# REQ-ABC33-HEAT-BATCH-RATE-CRITERION-20260810 在线闭环

固定数据流：`bf_imes.raw_rows(data2煤矿事件) → abc_burden_rate.py → BurdenRateDev/Slow/Fast → abc_feature_builder → A2/B4/B5 → 8768 abc_rule_bundle.v1 → 8093安全化复核详情`。前后30分钟按完整大批周期速率计算，昨日平均与滚动24小时同时保留；缺数、过期和窗口不足均保持不可用。

固定发布流：`test_abc33_burden_rate_local.ps1 → persistent SSH upload-only → remote_guarded_deploy_abc33_burden_rate_8093.ps1 → remote_restart_abc33_burden_rate_8768.ps1 → WebSocket/HTTP/浏览器验收`。2026-08-10生产结果：8093守卫恢复、未回滚；8768返回33条完整规则；持久SSH在请求5—8继续使用同一`session_id/connection_id`且`reconnect_count=0`。

# OPS-8093-RISK-TIERED-VALIDATION-20260810 自动化闭环

固定决策流：`识别改动边界 → quick(4)/standard(17)/full(85) → 本机或预览浏览器验收 → 失败/边界不清自动升级 → 生产定向冒烟`。浏览器等级只决定UI覆盖量，不得跳过部署互斥、备份、守卫暂停/恢复、原子替换、失败回滚、HTTP/API或受保护PID验证。

验证器按浏览器内核复用context，让同内核后续case复用不可变静态资源缓存；每个case仍使用独立page、精确viewport、控制台错误、溢出和核心交互检查。`full`不在生产循环加载85次，避免测试流量和冷缓存掩盖真实用户性能。

# OPS-CODEX-ECONOMICAL-DELEGATION-20260810 自动化闭环

固定决策流：`是否确定性 → 是否可独立验收 → 实时模型目录 → Luna/Terra/Sol或主任务 → 只读/明确所有权 → 一次执行 → 主任务独立验收 → 记录tokens/耗时/重试`。确定性任务直接脚本；一次低价模型失败即升级，不进入重复猜测循环。

8093相关委派只允许在本地准备阶段出现。任何凭据、远程命令、上传、部署锁、服务停启、原子替换、回滚和最终生产验收都由`deploy-8093-guarded-update`主流程持有。当前Luna最小化前后对照为89004ms/58097输入tokens与29197ms/38309输入tokens；网络回退仍是剩余延迟来源。

# REQ-8093-OVERVIEW-SI24H-20260811 本机待部署闭环

总览页右侧下方仅嵌入最近24个自然小时的V20严格整点Si预测，不搬入候选炉次、预测按钮、回放表或133点详情。组件只读调用`GET /api/si-v20/hourly-table?limit=24`并每60秒刷新；缺失保持`null`，不以0填充，完整操作继续跳转独立工作台。

图表使用同一连续时间轴但不强制点位对齐：预测P50/P10/P90按`schedule_slot_ts`落在整点，实际平均Si按`matched_actual_open_ts`落在真实开口时间，并按`matched_actual_meltno`去重。合同测试`python -B -m pytest tests/test_si_v20_shadow_workbench.py -q`为17项通过，前端构建与两份Babel语法检查通过。

2026-08-11已受控部署220.12：8093生产页、Vite主包和8094独立页目标SHA-256分别为`9B6ECCAB...A61F92`、`350D80AC...798880`、`C55FE8E4...03E196`，备份位于`backups\overview_si24h_20260811\20260811_094618`。8093守卫恢复后8093/8094均HTTP 200，两端`hourly-table?limit=24`均返回24行且schema为`bf.si.v20.hourly_table.v1`；8093、8094、8768、8770、5432、11434均保持监听。

# BUG-8093-CORE-PORTAL-BASELINE-20260811 自动化闭环

固定显示流：`8768 diagnosis.baseline_compare(数据库30日基线) + 8770 pSpace当前原始值 → 每个变量独立(raw-median)/IQR → iqrStatus → 行级data-baseline-evidence`。28行不得共享总状态；实时显示源降级时，判断必须使用同一次`coreMetricCurrent8093`返回的原始值。

固定发布流：`16项合同 + 总览17组合 + Luna low只读复核 → prepared-release/delta-plan → 持久SSH upload-only → Global互斥 → 备份 → 只停8093 → 两文件原子替换 → 恢复 → HTTP/哈希/受保护PID/生产浏览器复算`。首次尝试因并行发布改变生产基线而在停服前停止；重新取证并封存同源构建后成功，未回滚。
## 8093 ABC33总览入口受控发布（2026-08-11）

- 需求ID：`BUG-8093-ABC33-OVERVIEW-ENTRY-20260811`。
- 使用持久SSH会话完成upload-only预暂存，再由受控PowerShell 7脚本获取部署互斥锁、备份、仅暂停`BFV4PreviewProxy8093`、原子替换、恢复和验收。
- 备份：`F:\高炉炼铁项目-real-sensor-v2_V4_8093_PREVIEW\backups\abc33_overview_entry_8093_20260811_114520`。
- 结果：`guard_paused=true`、`guard_restored=true`、`rollback_applied=false`；8093 PID从3704切换为16428，受保护服务PID未变化。
# 2026-08-11 时间序列分时段融合实验

- 需求：`REQ-TS-FORECAST-SEGMENTED-ENSEMBLE-20260811`
- 程序：`tools/experiment_segmented_ensemble_19.py`
- 测试：`tests/test_segmented_timeseries_ensemble.py`
- 数据与结果：`PT/时间序列预测评测/results/segmented_ensemble_*_20260811_121921.*`
- 报告：`PT/时间序列预测评测/2026-08-11_Chronos与Ridge分时段融合实验报告.md`
- 运行边界：本机历史数据；Chronos仅调用8777只读推理；没有生产写入、服务重启或模型切换。
## ABC33实时探尺料速链路（2026-08-11）

- 每个ABC计算周期通过现有PostgreSQL连接读取`bf_sensor.one_minute_values`中南探尺、北探尺和料罐重量；不新增数据库写权限或独立计划任务。
- 识别顺序：探尺有效下降→回到提尺零位→南北同期合并→事件前2分钟料罐重量分型→计算前/后30分钟小批节奏→折算大批节奏→注入A2/B4/B5。
- 探尺或重量数据过期、窗口覆盖不足75%或无法形成有效周期时保持`needs_data`，禁止补0。

## 8093维护交接包生成链路（2026-08-11）

- 需求：`OPS-8093-MAINTAINER-HANDOFF-PACKAGE-20260811`。
- 输入：`tools/handoff/8093_handoff_manifest.json`的显式白名单和构建时当前工作区内容。
- 处理：PowerShell 7 UTF-8复制到随机本地暂存目录 → 禁止路径/扩展名检查 → 高置信敏感信息扫描 → Git快照与逐文件SHA-256 → ZIP → 回读归档逐项哈希验证 → 受控清理暂存目录。
- 输出：Git忽略的`handoff_packages/*.zip`，包内含`HANDOFF_README.md`和`PACKAGE_MANIFEST.json`。
- 失败策略：缺文件、敏感项、高风险扩展名、归档缺项或哈希不一致时立即失败，不留下可交付结果；暂存目录在`finally`内仅经父路径校验后清理。
- 权限边界：不读取凭据文件，不连接220.12，不取得`Global\BFV4PreviewProxy8093Deployment`，不暂停或重启任何服务。
## 2026-08-11 8093 炉喉变量、自动诊断与 PowerShell 7 闭环

| 需求/故障 | 程序与配置 | 确定性验证 | 生产结果 |
|---|---|---|---|
| `BUG-8093-REMOVE-THROAT-RESTORE-HEAT-QUERY-20260811` | `frontend_dashboard_v3.server.html`、Vite 主包、`bf-heat-performance-quality-8093-query-v2.js`、受控部署器 | 37 pytest；diagnosis standard 17/17；生产 Chromium 单页冒烟 | 32 项核心变量，移除 `T_throat_A-D`，保留 `T_top_A-D`；8093/资源 HTTP 200 |
| `BUG-AUTOGUARD-OLLAMA-SUMMARY-FALLBACK-20260811` | `llm_short_window_summarizer.py`、`auto_guard_once.py` | 404/主体失败专项 3 passed；Ollama `/api/chat` 最小请求成功 | 生产任务 2026-08-11 16:51 退出码 0；摘要异常可降级且不掩盖主体失败 |
| `OPS-8093-PWSH7-RUNTIME-MIGRATION-20260811` | NSSM wrapper、health、daily baseline、单目标迁移/回滚器 | 迁移 4 passed、健康守卫 5 passed、PS7/UTF-8 ok | 两旧任务 Disabled；服务包装、健康任务、每日基线均使用 PowerShell 7.6.4 |
| 旧哈希主包保留策略 | `cleanup_8093_dashboard_build_assets.py` | 默认 dry-run、哈希/路径/HTML引用门；7 passed | 保留当前+最近回滚，删除四个旧包 2,430,462 字节 |

完整生产证据见 [交接记录](handoffs/2026-08-11-8093-throat-autoguard-pwsh7.md)。

## 8093 诊断智能分析 JSONB 修复（2026-08-11）

- 错误：`ERR-8093-DIAGNOSIS-AI-JSON-DATETIME-20260811`。
- 链路：`/api/diagnosis-ai-analysis` → `run_five_minute_analysis_once()` →
  `DiagnosisReviewStore.begin_ai_analysis()` → PostgreSQL
  `bf_assistant.diagnosis_ai_analysis_snapshots.canonical_context`。
- 程序：[JSONB归一化](../高炉前端数据/智能助手/backend/diagnosis_review.py)、
  [回归测试](../tests/test_diagnosis_review_api.py)、
  [准备器](../tools/prepare_8093_diagnosis_ai_json_fix_release.ps1)、
  [受控部署器](../tools/deploy_8093_diagnosis_ai_json_fix_22012.ps1)。
- 验收：52 项定向测试；生产分析 `completed/attempt_count=1`；唯一 keyword SSE
  `request_count=1`，证据 2 条，全部受保护 PID 不变。
- 交接：[2026-08-11-8093-diagnosis-ai-jsonb-fix.md](handoffs/2026-08-11-8093-diagnosis-ai-jsonb-fix.md)。

## 220.12 可复用产物保留边界（2026-08-12）

- 需求：`OPS-22012-REUSABLE-ARTIFACT-RETENTION-20260812`。
- 目标：优先复用已审查脚本、模板、schema、无凭据夹具、密封产物和常驻 SSH broker，减少重复编码、验证与连接开销。
- 安全边界：Playwright `storageState`、Cookie、Token、密码、私钥以及含凭据环境变量的远端服务配置快照不得进入仓库或普通复用缓存；保留生成器、脱敏 schema、权威路径和刷新命令。
- 复用门：复用前检查 producer/source SHA-256、目标身份、运行时、合同测试、有效期和失效条件；远端 PID、监听、当前文件哈希与生产配置仍必须现场刷新。
- 实现：[Skill 主规则](../.codex/skills/deploy-8093-guarded-update/SKILL.md)、[详细保留策略](../.codex/skills/deploy-8093-guarded-update/references/reusable-artifact-retention.md)、[合同验证器](../.codex/skills/deploy-8093-guarded-update/scripts/validate_skill.ps1)。
- 本次结论：`viewport-storage-state.json` 是浏览器鉴权夹具，`22012_BFV4PreviewProxy8093.remote.json` 是一次性远端配置快照；二者都不是每次 SSH 连接生成的文件。常规连接复用由 `tools/remote_22012_session.py` 和 LocalAppData 中受保护的 broker 状态承担。
## OPS-22012-BIDIRECTIONAL-SYNC-20260813

- 任务：Codex 自动任务 `220-12`，每两小时只读检查 `10.30.220.12` 的 V4 生产项目是否出现源码或功能更新。
- 检测：远端 Git 可用时记录仓库身份、分支和 HEAD；不可用时使用白名单文件 SHA-256 清单形成 server version。复用 `tools/remote_22012_session.py` 和 `tools/remote_export_8093_authoritative_snapshot.ps1`。
- 同步：只下载变化的非敏感白名单文件；本地同路径存在并行修改时不覆盖，候选副本保存在 `reports/server_sync/incoming/<timestamp>/` 并通知人工审查。
- 验证：按文件类型运行语法、单元和合同测试；PowerShell 变更额外运行 `tools/verify_pwsh7_utf8.ps1`。失败时仅回退本轮自动替换，不触碰运行前已有本地改动。
- Git version：测试通过后只按精确 pathspec 暂存本轮同步文件，执行 cached diff 检查，创建普通 commit 和唯一的本地 annotated tag；不 push 外部 remote，不创建空 commit。
- 影响范围：远端只读；不得上传、停启 8093/8768/8094/Ollama/数据库，不修改远端 Git、任务或配置。完整边界见 [需求追踪](requirements_traceability.md#ops-22012-bidirectional-sync-20260813) 与 [交接记录](handoffs/2026-08-13-22012-two-hour-sync-automation.md)。
