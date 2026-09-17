# 程序索引

## REQ-QA-LATEST-PREFETCH-REUSE-20260917 / V24

[qa_verified_facts.py](../高炉前端数据/智能助手/backend/qa_verified_facts.py)新增`reusable_latest_read`；[qa_evidence_policy.py](../高炉前端数据/智能助手/backend/qa_evidence_policy.py)补代码承诺清理；[候选构建器](../tools/build_qa_v24_latest_candidate.py)从当前生产字节只修改代理`qa_mcp_should_use_tools`，其他497节点保留，本机旧代理不能覆盖生产。[3写/24读与生产版本证据](handoffs/2026-09-17-qa-v24-latest-reuse-and-code-boundary.md)。行号TODO-LINES。

## REQ-QA-STATISTICAL-SCOPE-20260917 / REQ-QA-SINGLE-WINDOW-OBSERVATION-20260917

[qa_verified_facts.py](../高炉前端数据/智能助手/backend/qa_verified_facts.py)的`cv_contract/render_cv/trend_context`校验统计适用性并限定时间尺度；[qa_task_plan.py](../高炉前端数据/智能助手/backend/qa_task_plan.py)的`_explicit_live_request`补单窗观察且保留说明/用户数据边界。代理候选从当前生产字节确定性构建，497其他AST节点不变；本机旧代理不得直接覆盖生产。[V22/V23实施与作用域](handoffs/2026-09-17-qa-v23-single-window-routing.md)。行号TODO-LINES。

## REQ-QA-INITIAL-828-SEMANTIC-REVIEW-20260916：审阅结果验收

[validate_qa_initial_828_review.py](../tools/validate_qa_initial_828_review.py)仅核对完成报告是否覆盖原待审828唯一题、首次result_sha256、五类语义状态及禁公开字段。实际语义审阅由用户指定的单个`gpt-5.6-luna`子智能体完成，不调用生产，不以关键词规则替代语义判断；当前审阅进行中。

## REQ-QA-PAIRED-FAILURE-RETEST-20260916：失败题复测工具

`prepare_qa_paired_failure_retest.py`冻结原题与模型/目录/程序身份；`start_qa_paired_failure_batch.ps1`复用独立启动器；`run_qa_template_batch.py`串行单发送claim与发送前版本门。`export_qa_paired_round_readonly.py`和`assemble_qa_paired_snapshots.py`有界导出/验证私有证据；`record_qa_v21_observations.py`冻结已独立审核的4题脱敏报告。现有报告拒绝覆盖，当前409题未发送；[权威范围与命令](handoffs/2026-09-16-qa-routing-v21-paired-retest.md)。

## REQ-QA-EXCLUSIVE-USE-20260916：问答独占门（V21已发布）

[qa_request_control.py](../高炉前端数据/智能助手/backend/qa_request_control.py#L135)在现有注册锁内检查所有未完成请求，先拒绝其他发送，再进入原问答。锁不覆盖模型等待；取消保持占用直到实际finally结束。[生命周期测试](../tests/test_qa_exclusive_use.py)与[实施记录](handoffs/2026-09-16-qa-exclusive-use-local.md)。V21生产字节/PID/CAS验收通过，真实角色与取消现场行为待测。

## V20 指代趋势追问（2026-09-16）

规划器新增“这个/那个/这些/它们/刚才/上面”指代识别，明确新对象仍优先当前问题。V19失败的30分钟追问现走确定性统计；真实五题与数据库只读来源各5/5通过，模型趋势解释被可信守卫拒绝单列。仅更新8093代理，模型配置不变；整体33项仍执行中。[权威证据](handoffs/2026-09-16-qa-routing-v20-production.md)。

## V18–V19 多轮来源与适配器修复（2026-09-16）

`mcp_conversation_context.load_owned_tool_context/bind_persisted_context/persist_owned_context_binding`统一来源门；代理在add_message后绑定ID。适配器兼容使用RETURNING ID。测试及只读核查工具见交接，符号行号TODO-LINES。 [权威证据](handoffs/2026-09-16-qa-routing-v18-v19-production.md)。

## V17 历史复合执行入口（2026-09-16）

`qa_history_compound.split_request/execute/model_messages/normalize_present/compose` 管理历史与非历史子任务；生产代理 JSON/两条 SSE 使用相同合成接缝。完成归一化复用已核验原文合同或实际最新工具事实，不根据非空答案升级。[权威实施](handoffs/2026-09-16-qa-routing-v17-production.md)，符号行号 TODO-LINES。

## 智能助手V15当前实现（2026-09-16）

原文独立完整性门`qa_document_integrity.inspect/inspect_selected_scope`；多章节逐项完成`qa_document_knowledge._original_subsections`；最新读取及无效时钟窗口继承门`mcp_conversation_context.update_tool_context`。符号行号TODO-LINES。新增版本元数据统一在`tools/qa_routing_release_extensions.json`定义并由现有冻结发布器消费；仍要求精确三目标部署和远端只读验证。证据：[V15生产交接](handoffs/2026-09-16-qa-routing-v15-production.md)。

## 智能助手V10–V14当前实现（2026-09-16）

`REQ-QA-FULL-ISSUE-INVENTORY-20260916`：制度原文复合隔离`qa_document_compound`、可读失败证据`qa_tool_fallback`、两条消息投影`qa_response_projection`、已登记单位血缘/缺项终态`qa_verified_facts`、DAG依赖完整性`CrossSourcePlan`。符号行号TODO-LINES。
生产代理差分必须复用`build_qa_routing_v11/v12/v13_candidate.py`及已接受生产快照，不能上传本机旧完整代理。
当前合同及验证见[V10–V14交接](handoffs/2026-09-16-qa-routing-v10-v14-production.md)。

## 智能助手证据优先回归集

- `tools/qa_regression.py`：只读校验用例和合成夹具，生成规范用例列表，评分由可信收集器提供的候选运行记录；不连接模型、生产接口或数据库。
- `tests/qa_regression/cases.v1.json` / `fixtures.v1.json`：问答合同与合成数据的唯一机器权威；`run.example.json` 仅演示格式。
- `tests/test_qa_regression.py`：评分器的正反例及防误报检查。
- 需求与边界：[回归集维护说明](../tests/qa_regression/README.md)，REQ-QA-EVIDENCE-FIRST-REGRESSION-20260915。

## 罐重设定 sensor_registry 登记

- `tools/register_hopper_weight_set_points.py`：从正式 TSV 读取南北探尺、11 个罐重设定物理
  分量和 1 个派生目录项；默认只审计，`--apply` 才事务 upsert，并在提交后复核映射与历史覆盖。
- `数据库同步和存取/config/点位清单.tsv`：登记的唯一权威来源；当前 165 行，其中
  162 个物理点、3 个派生点。
- `数据库同步和存取/src/sync_from_243_pg.py`：继续承担 11 个物理分量的 raw/分钟同步；
  本轮没有新增 pSpace 常驻读取器。
- 追踪：`OPS-SENSOR-REGISTRY-HOPPER-WEIGHT-SET-20260814`；
  [生产交接](handoffs/2026-08-14-hopper-weight-set-registry-production.md)。

## 工长趋势两位小数与百分数显示

- `高炉前端数据/assets/foreman-trend-preview.js`：统一顶部指标和原生曲线提示为两位小数；
  `GasUtil` 历史序列先从 `0–1` 比例转换为百分数。
- `高炉前端数据/assets/curve-inspector.js`：所有共享右键曲线数值固定两位小数，并为
  `GasUtil` 提供同一百分数口径。
- `高炉前端数据/foreman_trend_preview.html`：更新两项脚本的缓存版本。
- `tests/test_foreman_trend_preview.py`：锁定两位小数和先转百分数的静态合同。
- 追踪：`REQ-FOREMAN-TREND-TWO-DECIMAL-PERCENT-20260814`。

## 8093/8094 诊断功能 reliable_ssh 一键部署

- `tools/deploy_diag_rules.py`：用户统一入口；直接运行是本地测试和dry-run，`--apply`才允许生产部署。
- `tools/deploy_diag_rules_rssh.py`：生成单个压缩包和清单，调用本机可靠SSH传输，不使用Paramiko或旧的 `remote_22012_exec.py`。
- `tools/reliable_ssh_22012_cli.mjs`：复用本机 `reliable-ssh-mcp` 的固定目标、主机指纹、密码文件、身份门禁、超时和审计实现；同一进程只做一次身份握手。
- `tools/build_diag_proxy_payload.py`、`tools/build_8093_diag_single_payload.py`：在远端当前 `ollama_proxy_server.py` 上只合并诊断块和资产版本，不把本机其它未发布代理改动带入生产。
- `tools/remote_deploy_diag_rules.ps1`：校验白名单与SHA-256，备份并原子安装，受控重启8093/8094，保护8768/8770/11434，失败回滚。
- `tests/test_diag_rules_deployer.py`、`tests/test_diag_rules_reliable_deployer.py`：覆盖文件边界、固定服务范围、单包传输、远端当前代理合并和dry-run默认值。
- 追踪：`OPS-DIAG-RULES-ONE-CLICK-DEPLOY-20260806`。
- 2026-08-06正式发布：`diag_rules_20260806-2300-4b75678a08` 已更新8093/8094的评分、弹窗、单炉况证据分析和后端接口；远端HTTP/API/资源验收通过，8768/8770/11434受保护PID未变化。详见[部署交接](handoffs/2026-08-06-8093-8094-diagnosis-assets-repair.md)。

## 8093/8094 单炉况智能分析与免登录评分

- `高炉前端数据/智能助手/backend/diagnosis_model_review.py`：`v3`单炉况Prompt、严格JSON与可信引用ID校验；一次模型调用只处理当前所选炉况。
- `高炉前端数据/智能助手/backend/diag_ai_evidence.py`：读取公式驱动变量、近5分钟变化、60分钟统计、30天基线、调剂引擎1和知识库，生成服务端可信解释上下文。
- `高炉前端数据/智能助手/backend/diagnosis_ai_analysis_api.py`：按 `label` 查询/排队/重试当前5分钟桶；浏览器不能上传系统分和证据。
- `高炉前端数据/智能助手/backend/diagnosis_review.py`：保存分析派生状态以及复核/手动评分追加事件，系统分与人工分并列保留。
- `高炉前端数据/assets/bf-diagnosis-review-local.js`、`bf-diagnosis-manual-score-local.js`：异常自动弹窗、手动八卡入口、可选评分/建议和关闭不提交。
- `tools/remote_guarded_enable_8094_diagnosis_ai.ps1`：在当前共享代理架构上幂等启用8094，精确重启8094并保护8093/8768/8770/11434；拒绝恢复过时8769/隔离代理方案。
- 追踪：`REQ-8093-8094-DIAGNOSIS-REVIEW-AI-20260806`。

## 8093 每5分钟智能分析（历史v1/v2入口）

- `高炉前端数据/智能助手/backend/diag_ai_evidence.py`：把规则特征、分钟实测、30天基线、规则阈值/权重、调剂引擎1和知识库证据规范化为可信只读上下文；为模型分配可验证引用ID。
- `高炉前端数据/智能助手/backend/diagnosis_model_review.py`：现已升级为v3单炉况Prompt；旧的单次八类说明仅用于理解历史v1/v2数据。
- `高炉前端数据/智能助手/backend/diagnosis_ai_analysis_api.py`：免登录读取所选炉况分析和受冷却限制的失败重试；不接受浏览器上传诊断分数。
- `高炉前端数据/智能助手/backend/ollama_proxy_server.py`：读取生产诊断、30秒轮询新桶、模型调用去重、启动后台线程和API路由。
- `高炉前端数据/智能助手/backend/diagnosis_review.py`：维护 `diagnosis_ai_analysis_snapshots` 派生表及开始/完成/失败状态。
- `高炉前端数据/assets/bf-diagnosis-manual-score-local.js/css`：诊断卡点击后显示“智能分析与人工评分”同一窗口。
- `tools/verify_diagnosis_ai_analysis_viewports.cjs`：Chromium九个规定视口和Firefox/WebKit代表视口验证；`tests/test_diagnosis_ai_analysis.py`覆盖批量合同、证据来源、未知ID拒绝、调剂引擎复用与前后端标记。
- `tools/remote_guarded_deploy_8093_diagnosis_review.ps1`：守卫闭环部署并等待真实5分钟分析完成，只保护8768，不访问或依赖8094。
- 需求与运行说明：[REQ-8093-DIAGNOSIS-AI-FIVE-MINUTE-ANALYSIS-20260805](requirements_traceability.md#req-8093-diagnosis-ai-five-minute-analysis-20260805)、[专项文档](8093_每5分钟八炉况智能分析_20260805.md)。

## 8093 异常炉况评分免登录生产部署

- `高炉前端数据/智能助手/backend/diagnosis_review.py`：`BF_DIAG_REVIEW_REQUIRE_LOGIN=0`时使用服务端固定现场身份；`BF_DIAG_REVIEW_PGPASSWORD_ENV`只引用机器环境中的密码，不输出或复制密码。
- `高炉前端数据/智能助手/backend/ollama_proxy_server.py`：评分POST使用服务端身份，历史GET继续登录保护；上下文返回 `login_required/can_submit/identity_mode`。
- `高炉前端数据/assets/bf-diagnosis-review-local.js`、`bf-diagnosis-manual-score-local.js`：按 `can_submit`显示表单，免登录模式隐藏登录与退出按钮。
- `tools/remote_guarded_deploy_8093_diagnosis_review.ps1`：仅停启 `BFV4PreviewProxy8093`，备份并原子部署六个功能文件和8093服务配置，保护8768/8094并在失败时自动回滚。
- `tools/remote_probe_8093_diagnosis_review.ps1`：只读核对服务、端口、配置变量名、文件哈希和HTTP状态，敏感配置只输出存在性和长度。
- `tools/remote_probe_8093_review_pg.ps1`、`remote_probe_8093_review_pg.py`：使用220.12机器环境执行只读PostgreSQL身份、权限、表存在性和行数检查，不输出密码。
- 需求与运行说明：[REQ-8093-DIAGNOSIS-REVIEW-NO-LOGIN-PRODUCTION-20260804](requirements_traceability.md#req-8093-diagnosis-review-no-login-production-20260804)、[部署记录](8093_异常炉况评分免登录部署_20260804.md)。

## 220.12 PostgreSQL账号只读探针

- `tools/remote_probe_22012_pg_accounts.ps1`：从220.12机器/用户环境读取PostgreSQL连接元数据，只输出密码是否存在、长度和SHA-256指纹，不输出密码正文；分别用`gl02_sync`、`gl02_reader`和`postgres`执行只读身份/权限验证。
- `tools/remote_22012_exec.py`：通过受控SSH通道把探针脚本放到220.12临时位置执行，不修改数据库或远端配置。
- 配置落点：用户明确授权后，三类账号的完整值只记录在 `docs/数据库账号配置说明.md`，其他索引、日志和脚本不得复制。

## 本机异常炉况诊断复核原型

- `高炉前端数据/智能助手/backend/diagnosis_review.py`：回环库配置边界、签名会话、异常段、准确八类炉况键、服务端快照校验、异常复核与手动评分追加事件存储。
- `高炉前端数据/assets/bf-diagnosis-review-local.js/.css`：按开关注入的居中异常弹窗、七类候选分数、三态复核、可选人工分与建议。
- `高炉前端数据/assets/bf-diagnosis-manual-score-local.js/.css`：把诊断页八张炉况卡改造成可访问的手动评分入口；人工分或建议至少一项，关闭不写入。
- `高炉前端数据/智能助手/backend/ollama_proxy_server.py`：签名登录与 `/api/diagnosis-review-context`、`/api/diagnosis-reviews`、`/api/diagnosis-manual-scores`；所有系统分均由服务端重新读取。
- `db_dashboard/server.py`、`db_dashboard/index.html`：只读“高炉长评分”查询，真实诊断/本机测试分源展示，JSON/CSV/XLSX导出；未评分保留系统分并显示“未打分”。
- `高炉前端数据/智能助手/backend/schema/postgresql_diagnosis_review.sql`：`diagnosis_review_events` 增量字段及 `diagnosis_manual_score_events` 追加事件表。
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

## tools/patch_8094_cad_bottom_band.py

- 需求：`BUG-BF3D-CAD-BOTTOM-BAND-20260804` / `BUG-BF3D-CAD-PANEL-BODY-GAP-20260804-R2`。
- 职责：对 8093/8094 页面幂等维护最终 R2 样式，同时清除 viewer bottom inset 和炉况总览直属 panel-body 的底部 padding；能自动升级旧的 stage-only 补丁，拒绝不含既定 CAD 基线标记的页面。
- 入口：`python tools/patch_8094_cad_bottom_band.py --path <html> --scope 8093|8094`。
- 测试：[test_8094_cad_bottom_band_fix.py](../tests/test_8094_cad_bottom_band_fix.py)、[test_8093_cad_bottom_band_fix.py](../tests/test_8093_cad_bottom_band_fix.py)。

## tools/remote_guarded_deploy_8093_cad_bottom_band.ps1

- 职责：只停止/恢复 `BFV4PreviewProxy8093`，在守卫窗口内应用 R2 页面补丁，并验证 8093 HTTP/R2 标记；全过程保护 8094/8768/8770 PID 和 8094 页面、共享 adapter、8094 相机哈希。
- 失败诊断：输出逐项失败键、前后 PID 与哈希；`finally` 中仍必须恢复 8093 服务。
- 只读复核：[remote_probe_8093_8094_cad_panel_body_gap.ps1](../tools/remote_probe_8093_8094_cad_panel_body_gap.ps1)。

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

## tools/convert_docx_to_markdown_verified.py

### 文件职责

按 DOCX 正文 XML 顺序把段落和真实表格单元格转换为 Markdown，并生成字符数、
有序文本片段 SHA-256 和逐项相等结果。对应
`REQ-THREE-RULES-RECOMMENDATION-ALIGNMENT-20260804`。

### 相关文件

- [完整三规二制 Markdown](冀钢炼铁三规二制.md)
- [转换验证测试](../tests/test_convert_docx_to_markdown_verified.py)
- [四类调剂升级分析](三规二制四类炉况调剂与建议引擎完全一致升级分析_20260804.md)

## docs/三规二制四类炉况调剂与建议引擎完全一致升级分析_20260804.md

### 文件职责

把高炉工长 `5.1.8` 与 `5.3` 原文逐条映射到当前建议引擎，记录现状冲突、
四类调剂规则 ID、输入与缺失数据、动作顺序、门禁、输出合同、代码改造位置
和验收场景。2026-08-04 已完成本地 v5 核心实施；远端部署、完整详情前端与现场
工艺验收仍未执行。

## 调控结论生成引擎/policy/three_rules_two_systems.yaml

### 文件职责

三规二制四类调剂的版本化策略目录，保存动作 ID、原文章节、幅度、所需输入、
观察窗口和审批角色。由 `policy_evaluator.py` 加载，`sequence_planner.py` 排序，
`conflict_resolver.py` 处理相反方向冲突，`formatter.py` 输出完整动作和旧数组。

### 相关测试

- [v5四态/顺序/冲突合同](../tests/test_three_rules_recommendation_engine.py)
- [引擎与8767综合合同](../tools/verify_8093_recommendation_engine_contract.py)

## tools/probe_8093_assistant_health.ps1

8093 智能助手第一层只读健康快照。汇总 8093/11434/8768 服务状态、8093 模型状态、11434 驻留模型、关键启动配置和当前日志文件新鲜度；不发送问答、不写数据库、不启停服务。详细进程环境继续使用 `audit_22012_proxy_model_env.ps1`。

## tools/probe_8093_assistant_log_tail.ps1

第二层只读日志探针。仅取 8093 当前 stdout/stderr 的有限尾部，筛选 `/api/qa/chat`、超时/断连、RAG/数据库异常，并返回 runner 与健康检查的最近记录；避免全文件扫描拖慢远端检查。

## tools/probe_8093_8094_prompt_rag_runtime.ps1

8093/8094 公共 Prompt、知识库和 MCP 当前运行态只读探针。核对两个监听进程是否使用共享 `ollama_proxy_server.py`，读取非敏感开关并计算默认生效值，验证固定规则早于动态上下文、PostgreSQL RAG 的 keyword/vector 能力，并对两个端口执行强制 `mode=keyword` 的只读知识检索；不发送问答、不启停服务、不写数据库、不触发 embedding。专项说明见 [8093/8094 Prompt 固定 KV 前缀与知识库回答链路](8093_8094_Prompt固定KV前缀与知识库回答链路_20260805.md)。

## tests/test_8093_8094_prompt_rag_contract.py

覆盖固定 Prompt 顺序、知识/MCP 默认开关、PostgreSQL RAG 双模式、8093/8094 显式 keyword 现行口径、探针只读边界和专项文档关键结论。

## tools/remote_patch_8093_assistant_name.ps1

把 8093 正式页导航名称精确、幂等地从“智能问答/知识助手”改为“智能助手”；写入前时间戳备份，使用同目录原子替换，HTTP cache-bust 复核，并验证 8094 预览页面 SHA-256 未变化。

## tests/test_8093_assistant_health_contract.py

校验页面名称、`AGENTS.md` 分层流程、只读探针无服务/文件修改命令，以及远端名称补丁器的精确计数、幂等和 8094 隔离合同。

## tools/check_managed_nssm_service_health.ps1

托管 NSSM 服务的共享健康检查入口。兼容旧配置的单次失败默认行为；配置新字段时维护跨运行状态、连续失败阈值、重启前退避复查和重启冷却。8093 状态写入 `logs/proxy_8093.health.state.json`，成功检查清零计数。

## tools/patch_8093_health_guard_config.py

只允许处理 `BFV4PreviewProxy8093` 配置，幂等设置 `3/1/15/600` 健康合同并使用同目录原子替换；服务名或 8093 TCP 检查不匹配时拒绝写入。

## tools/probe_8093_health_guard_runtime.ps1

只读返回 8093 健康任务动作、分钟触发器、共享脚本哈希、配置健康段、服务配置清单、状态计数、服务状态和健康日志尾部，用于部署前后确认真实运行合同。

## tools/remote_guarded_deploy_8093_health_guard.ps1

正式部署 8093 健康守卫修复。校验旧脚本/配置基线哈希，暂停并恢复 8093 健康任务，备份、原子替换、运行一次健康任务，并验证 8093/8768/8094/8770/11434 PID及页面/配置隔离；失败自动回滚。

## tools/verify_8093_assistant_sse_once.py

只提交一次无生产控制含义的智能助手短问，要求 `start(preparing/prepared) -> delta -> final -> done`、非空回答和会话 ID；请求前后验证 8093 状态与 11434 仅驻留批准的 27.8B。

## tools/remote_verify_8093_assistant_sse_once.ps1

在 220.12 包装单次 SSE 验收，保存报告，并核对验收期间无守卫重启、健康状态计数为 0、任务启用及 8093/8768/8094/8770/11434 PID不变。

## tools/patch_8093_keyword_knowledge_mode.py

只允许修改 `BFV4PreviewProxy8093` 服务配置，验证 8093 端口与 `3/1/15/600` 守卫合同后，幂等设置 `BF_QA_KNOWLEDGE_SEARCH_MODE=keyword` 并原子替换。空值/`hybrid` 可迁移，错误服务、端口、守卫漂移或 `vector` 配置会拒绝写入。

## tools/remote_guarded_deploy_8093_keyword_knowledge_mode.ps1

220.12 上的 8093 关键词知识模式正式部署器。校验已知配置与守卫/后端/RAG 哈希，暂停健康任务，只停止/启动 8093，验证实际监听进程环境和默认知识搜索均为 keyword，并保护 8768/8094/8770/11434、页面、共享代码和单 27B 驻留；任何失败自动回滚。

## tools/remote_verify_8093_keyword_knowledge_sse_once.ps1

只包装一次真实知识问答 POST。请求前后核对默认搜索模式、实际进程环境、守卫日志/状态、受保护 PID/哈希和模型驻留；要求准备态知识检索启用且未跳过、存在知识意图、MCP 工具调用关闭，并保存 SSE JSON 报告。

## tests/test_8093_keyword_knowledge_mode.py

覆盖关键词配置补丁器的精确性、幂等性与漂移拒绝，受控部署器的隔离/回滚/默认搜索合同，以及 SSE 验收器只提交一次、必须证明知识链路参与和禁止 MCP 工具调用的合同。

## tools/generate_8093_assistant_repair_docx.py

使用项目捆绑的 `python-docx` 生成 [8093 智能助手不可用原因与正式修复手册](8093智能助手不可用原因与正式修复手册_20260804.docx)。手册固定历史失败证据、`3/1/15/600` 守卫合同、keyword 知识检索、复发分类流程、单次 SSE 验收、隔离/回滚标准和已知边界；不写入密码、Token 或数据库口令。

## tests/test_8093_assistant_repair_doc_contract.py

不依赖 Word 的 DOCX/AGENTS 合同测试。直接读取 DOCX OpenXML，验证正式标题、历史失败时间、现行参数、修复可行性、复发处理、单次 SSE 结果和敏感信息禁写约束，并验证 `AGENTS.md` 存在长期固定入口。

## tests/test_8093_health_guard_recovery.py

覆盖配置补丁器精确性/幂等/服务隔离、共享守卫关键合同、部署隔离、SSE 单请求约束；Windows 行为测试证明前两次失败延后且成功后计数清零，不触发真实服务重启。

## 高炉前端数据/assets/bf-core-metrics-pspace-live-8093.js

8093 专用核心指标实时运行时。浏览器只连接服务端 8770，维护 28 个点的值、源时间、传输年龄、质量和连接状态；传输超过 12 秒时向页面发布可降级状态，不接管任何分钟历史。

## tools/patch_8093_core_metrics_pspace_live.py

幂等修改 8093 页面：为核心指标当前值接入实时状态，增加数据时间/年龄/质量与分钟镜像提示，把顶栏“时间”绑定到每秒更新的终端系统时钟并把 8768 时间独立标为“分钟数据”，同时把 8768/trend 历史合并改为按时间戳、8768 主数组优先且拒绝不完整序列。

## tools/remote_guarded_deploy_8093_core_metrics_pspace_live.ps1

只暂停并恢复 `BFV4PreviewProxy8093` 的远端原子部署入口；同时验证实时标记、系统时钟标记和 `systemTime` 合同，保护 8768、8770、8094、共享 Billboard adapter 和 8094 相机资源，失败时恢复 8093 页面/资源并在 `finally` 中恢复守卫。

## tools/remote_audit_8093_core_metrics_pspace_live.ps1

只读输出 8093/8094/8768/8770 服务、监听、HTTP、页面标记、schema、SHA-256 和最新备份。

## tools/verify_8093_core_metrics_pspace_live.cjs

生产浏览器验收器。逐个检查两页共 28 个指标的数据源、时间戳、源年龄、传输年龄、质量、值、降级横幅、顶栏系统时钟秒差、独立分钟数据时间、横向溢出和页面/控制台错误；支持显式视口、有限导航重试以及 Chrome/Edge、Firefox、WebKit 和实时/分钟镜像两种路径。

## tests/test_8093_core_metrics_pspace_live.py

覆盖 28 点/8770 合同、当前值与分钟历史边界、真实系统时钟与分钟时间分离、时间戳历史合并、不完整数组拒绝、补丁幂等、守卫隔离和浏览器验收合同。

## 高炉前端数据/智能助手/backend/mcp_host/

8093 问答 Host 的多 MCP 编排模块：`server_registry.py` 校验服务、领域、脚本、环境默认值和生产排除工具；`domain_router.py` 以低延迟规则选择 GL02、IMES 或二者；`client_manager.py` 管理所选 stdio Client，将 `imes__` 暴露名路由到实际服务会话和原生工具名。目录名不能改成 `backend/mcp`，否则会遮蔽官方 Python SDK。

## tools/test_mcp_multi_server_discovery.py

不调用数据库、不调用 27B 的真实 MCP SDK 服务发现工具。输入一条口语问题，输出所选服务、领域、Host 可见工具及服务错误，用于验证按需挂载、命名空间和生产排除工具合同。

## 高炉前端数据/智能助手/tests/test_mcp_multi_server_host.py

覆盖两服务注册表、单源/跨源领域选择、IMES 命名空间、暴露名到原生工具路由、MES 问答进入工具循环、复合计划和事实格式器。

## 高炉前端数据/智能助手/tests/test_imes_heat_summary_tools.py

覆盖 MES 正式 `meltno`、上一炉所有有效 Si 试样的聚合、缺失不当作 0，以及非法炉号参数拒绝；数据库调用使用测试替身，不写生产数据。

## tools/assistant_8093_auto_recovery.py

8093 智能助手统一编排入口，提供 `prestage`、`diagnose`、`recover`、`docs` 四个子命令。先检查 VPN/私网、SSH、PostgreSQL、8093、11434，再复用经过 manifest/SHA-256 校验的远端不可变包。分类器只自动处理已知守卫合同和 keyword 漂移，未知哈希拒绝；完整 recover 最多一个 SSE POST，服务阶段和文档阶段分离。

## tools/remote_8093_assistant_diagnose.ps1

远端一次性只读采集器。输出服务、PostgreSQL 服务、5432/8093/8094/8768/8770/11434 监听 PID、8093/11434 实际环境、守卫配置/任务/状态、状态接口、Ollama 驻留、默认知识搜索和近期问答/异常/runner 日志。`SimulationInputPath` 用于 PowerShell 5.1 数字键 JSON 回归，不接触生产服务。

## tools/remote_guarded_deploy_8093_keyword_knowledge_mode.ps1

除既有隔离部署外，现支持从受控 package 内显式解析补丁器路径，并提供无远端依赖的 JSON 模拟分支。只允许在已知哈希范围内把 8093 恢复到 keyword；失败回滚且保护 8768/8094/8770/11434。

## tools/remote_guarded_deploy_8093_health_guard.ps1

除既有守卫受控部署外，现支持 package 内守卫源/配置补丁器，接受已记录的旧与现行基线哈希。未知哈希仍拒绝，不能把哈希扩展当作绕过审计。

## tests/test_8093_assistant_auto_recovery.py

覆盖远端包稳定 ID、PowerShell BOM、健康/keyword/守卫/未知哈希分类、阶段顺序、短 `-File` 远端命令、唯一 SSE 和 CLI 退出码。Windows 上直接运行 PowerShell 5.1 两个模拟场景，验证数字字符串端口键不会触发序列化回归。

## 自动诊断服务/recommendation_adapter.py

建议引擎与 8767 实时诊断之间的适配器。`generate_recommendation_bundle()` 一次返回当前主/次炉况的唯一有效 `active_plan` 和八类炉况的独立只读条件预案，schema 为 `multi_condition_recommendation.v1`。不得把 `hypothetical` 预案合并进当前动作队列。

## 高炉前端数据/智能助手/backend/diagnosis_model_review.py

高炉大模型诊断分数复核的白名单、Prompt、JSON 校验和 TTL 缓存模块。输入只保留八类分数、证据、基线、覆盖率、最近 12 条诊断和动作状态摘要；输出只解释支持/矛盾/缺失数据和观察重点，不具备动作改写权。

## 高炉前端数据/智能助手/backend/ollama_proxy_server.py

新增 `POST /api/diagnosis/model-review`。复用现有 Ollama 模型调用，只接受结构化复核合同；关闭开关、非法输入和模型错误分别返回明确 HTTP 状态，不回显内部模型标识、Prompt 或敏感配置。

## tests/test_multi_condition_recommendation_and_model_review.py

覆盖八炉况 bundle、当前/条件预案隔离、模型上下文白名单、对象形态基线/覆盖率、严格 JSON、Prompt 禁止改写、缓存隔离和前后端静态契约标记。

## tools/check_frontend_babel_syntax.cjs

使用项目本地 Babel standalone 编译 V3 页面内全部 `text/babel` 脚本，发现 JSX/语法错误时非零退出，不启动前端服务。

## tools/serve_multi_condition_browser_fixture.py

只用于本机浏览器验收的隔离 HTTP 服务。在内存响应中注入 `tests/fixtures/multi_condition_browser_fixture.js`，模拟 8767 WebSocket 和只读模型复核，不连接数据库或生产服务。

## 高炉前端数据/foreman_trend_preview.html

独立的现场“工长趋势1”布局预览页。保留旧式工业 HMI 的 7×7 指标矩阵、两段全宽曲线、灰色工具栏和底部导航；`fixture=1` 是明确标记的非生产布局夹具，去掉后连接现有 8767 WebSocket。该页不替换 `frontend_dashboard_v3.server.html#trend`。

## 高炉前端数据/assets/foreman-trend-preview.js 与 foreman-trend-preview.css

预览页的 vanilla JS 数据适配、ECharts 曲线、工具栏动作、实时/夹具边界和工业 HMI 视觉样式；使用本地 ECharts 资源，不依赖 React 或新增服务。

## tools/verify_foreman_trend_preview.cjs 与 tools/verify_foreman_trend_viewports.cjs

前者验证 49 个矩阵值、12+5 条曲线、缩放/图例、真实导航与 `1280×1024` 截图；后者覆盖 Edge/Chromium 的 9 个固定视口以及 Firefox/WebKit 的 4 个代表视口，并验证窄屏固定画布的可滚动只读访问。

## tests/test_foreman_trend_preview.py

独立预览页静态合同测试：检查 7×7 数据契约、两段图表和可操作工具栏、本地资源/实时边界，以及原正式趋势页仍保留。

## tools/verify_foreman_trend_live_22012.cjs 与 tools/verify_foreman_trend_remote_8093.cjs

前者只读验收已经按 db-profile 22012 启动的本机 8092/8767，确认页面实际连上 8767、数据时间存在、49 项变量的真实覆盖率、两段曲线有数据且浏览器无错误。后者对 `10.30.220.12:8093` 和既有 8768 执行相同的只读生产冒烟，额外检查无横向溢出；二者均不写数据库、不启停远端服务。

## tools/remote_deploy_8093_foreman_trend_preview.ps1

该受控部署器仅原子替换独立页的 HTML、CSS 和 JS：部署前要求 8093/8768 均服务正常且监听，写入前备份三个目标，写入后复核 HTTP/需求标记与服务状态，并在 manifest 记录两端 PID。它不替换正式 `#trend` 页面，也不停止 8093、8768、8094、8770 或数据库。

## tools/verify_foreman_trend_remote_viewports_8093.cjs

覆盖 220.12:8093 实际页面的 Edge/Chromium 9 个固定视口以及 Firefox/WebKit 各 4 个代表视口，验证 8768 实时连接、真实曲线数据、桌面无溢出和窄屏固定画布可滚动。
## 220.12 VPN 直达数据源转发（2026-08-05）

| 程序 | 职责 | 需求 |
| --- | --- | --- |
| [tools/patch_22012_nginx_imes_web.py](../tools/patch_22012_nginx_imes_web.py) | 幂等修改现有 18080 Nginx，仅增加 IMES 路径和根跳转，保留 g13 页面 | `OPS-22012-DIRECT-SOURCE-RELAYS-20260805` |
| [tools/remote_deploy_22012_direct_source_relays.ps1](../tools/remote_deploy_22012_direct_source_relays.ps1) | 备份、Nginx校验/重载、portproxy、防火墙、PID保护与失败回滚 | 同上 |
| [tools/remote_probe_22012_direct_relays.ps1](../tools/remote_probe_22012_direct_relays.ps1) | 只读检查目标连通、监听、进程、portproxy、HTTP与受保护服务 | 同上 |
| [tests/test_patch_22012_nginx_imes_web.py](../tests/test_patch_22012_nginx_imes_web.py) | 验证补丁内容、旧页面保留、幂等与歧义拒绝 | 同上 |

## 220.12 8093 MES/IMES MCP 生产同步（2026-08-05）

| 程序 | 职责 | 需求 |
| --- | --- | --- |
| [tools/service_configs/22012_mcp_server_registry.json](../tools/service_configs/22012_mcp_server_registry.json) | 生产四服务 MCP 注册表及 220.12 直连端点 | `REQ-22012-IMES-MCP-SYNC-20260805` |
| [tools/patch_22012_8093_mcp_service_config.py](../tools/patch_22012_8093_mcp_service_config.py) | 幂等补充非秘密环境配置及 Machine 凭据变量名 | 同上 |
| [tools/remote_guarded_deploy_8093_imes_mcp_sync.ps1](../tools/remote_guarded_deploy_8093_imes_mcp_sync.ps1) | 哈希预检、备份、暂停/恢复守卫、只重启 8093、失败回滚与受保护 PID 验证 | 同上 |
| [tools/remote_probe_8093_imes_mcp_sync_result.ps1](../tools/remote_probe_8093_imes_mcp_sync_result.ps1) | 只读输出部署结果、四端口 PID、注册服务、非秘密配置和文件哈希 | 同上 |
| [tools/verify_8093_mcp_mes_sse_once.py](../tools/verify_8093_mcp_mes_sse_once.py) | 单次真实 MES SSE 与工具轨迹验收 | 同上 |
| [tools/verify_8093_assistant_sse_once.py](../tools/verify_8093_assistant_sse_once.py) | 支持强制 MCP 或生产自动路由模式的单次 SSE 验收 | 同上 |

## 8093 跨数据库 MCP 口语审计（2026-08-05）

| 程序 | 职责 | 追踪编号 |
| --- | --- | --- |
| [tools/audit_8093_cross_database_mcp.py](../tools/audit_8093_cross_database_mcp.py) | 用自动路由模式执行单个复杂口语，输出实际服务、工具、路由、来源、耗时与回答，不修改生产状态 | `AUDIT-8093-CROSS-DATABASE-MCP-20260805` |
| [tests/test_8093_cross_database_mcp_audit.py](../tests/test_8093_cross_database_mcp_audit.py) | 验证审计器状态URL与跨服务工具证据摘要合同 | 同上 |

## 8093 跨源 MCP Host 与守护探针（2026-08-06）

| 程序 | 职责 | 追踪编号 |
| --- | --- | --- |
| [backend/mcp_host/cross_source_plan.py](../高炉前端数据/智能助手/backend/mcp_host/cross_source_plan.py) | FactRequest/CrossSourcePlan 及按能力编译的 MES + GL02 DAG | `REQ-8093-CROSS-SOURCE-MCP-20260805` |
| [backend/mcp_host/cross_source_executor.py](../高炉前端数据/智能助手/backend/mcp_host/cross_source_executor.py) | 实时 Schema 校验、跨服务并发/同服务串行、缓存、部分事实合同和依赖绑定 | 同上 |
| [backend/ollama_proxy_server.py](../高炉前端数据/智能助手/backend/ollama_proxy_server.py) | 确定性跨源路由、统一事实/SSE、`/api/qa/mcp/health` 只读探针 | 同上 |
| [backend/mcp_host/domain_router.py](../高炉前端数据/智能助手/backend/mcp_host/domain_router.py) | MES、GL02、炉身温度和炉次口语域选择 | 同上 |
| [mcp/catalog/](../高炉前端数据/智能助手/mcp/catalog/) | 传感器、炉次化验、图表和计算能力统一目录 | 同上 |
| [tools/remote_guarded_deploy_8093_multi_mcp.ps1](../tools/remote_guarded_deploy_8093_multi_mcp.ps1) | 备份、暂停/恢复8093健康任务、原子部署、只重启8093、保护8768/8094/8770 | `OPS-8093-MULTI-MCP-HOST-20260805` |

## pSpace分钟平均统一（2026-08-05）

| 程序 | 职责 | 需求 |
|---|---|---|
| `数据库同步和存取/src/raw_minute_pipeline.py` | 一次raw读取生成5秒明细、Good样本分钟平均与审计量 | `REQ-PSPACE-MINUTE-CANONICAL-AVERAGE-20260805` |
| `数据库同步和存取/src/sync_from_243_pg.py` | 重试、分区、raw与分钟同事务写入、30天raw保留 | 同上 |
| `数据库同步和存取/src/pg_store.py` | 含审计字段的幂等分钟upsert | 同上 |
| [tools/remote_deploy_pspace_minute_average.ps1](../tools/remote_deploy_pspace_minute_average.ps1) | 双目录备份、定向停止重复写入者、DDL、部署、任务恢复、PID保护和失败回滚 | 同上 |
| [tools/verify_22012_pspace_minute_average.py](../tools/verify_22012_pspace_minute_average.py) | 只读比较分钟值与raw重算平均、延迟、列结构和同步运行 | 同上 |
| [tools/remote_verify_8093_pspace_contract.ps1](../tools/remote_verify_8093_pspace_contract.ps1) | 验证8093服务、HTTP资源、8770连接和历史合并标记 | 同上 |
| [tests/test_pspace_minute_average_semantics.py](../tests/test_pspace_minute_average_semantics.py) | 质量过滤、闭窗水位、配置、DDL和共享单实例锁合同 | 同上 |
# 8093/8094 建议引擎同步工具（2026-08-06）

- `tools/build_8093_8094_recommendation_sync.py`：生成带 SHA-256 清单的同步包。
- `tools/remote_deploy_8093_8094_recommendation_sync.ps1`：远端备份、原子部署、仅重启 8768 并验收。
- `tools/remote_probe_8093_8094_recommendation_sync.ps1`：只读核对端口、服务、页面标记和哈希。
- `tools/verify_remote_recommendation_pages.cjs`：8093/8094 跨浏览器、跨视口建议页验收。
# 建议页布局只读探针（2026-08-06）

- `tools/probe_remote_recommendation_layout.cjs`：使用 Chromium 读取建议页关键容器的边界、滚动高度和 overflow，用于定位多炉况矩阵引入后的图表裁切与重叠，不修改页面或生产数据。

## 参数优化建议可视工作台（2026-08-06）

| 程序 | 职责 | 追踪编号 |
|---|---|---|
| [frontend_dashboard_v3.server.html:L10530](../高炉前端数据/frontend_dashboard_v3.server.html#L10530) | 恢复驾驶舱可视区、8炉况切换、4项主证据曲线、19项证据中心、动作/模型抽屉 | `REQ-OPT-VISUAL-COCKPIT-RESTORE-20260806` |
| [patch_8094_multi_condition_review.py](../tools/patch_8094_multi_condition_review.py) | 从8093最新源码抽取R2可移植功能块并幂等更新8094，补齐8094独立当前值适配器与4项主证据曲线，保持共享8768 | 同上 |
| [build_8093_8094_recommendation_visual_frontend.py:L30](../tools/build_8093_8094_recommendation_visual_frontend.py#L30) | 生成只含页面源码和8094补丁器的SHA-256前端包 | 同上 |
| [remote_deploy_8093_8094_recommendation_visual_frontend.ps1:L109](../tools/remote_deploy_8093_8094_recommendation_visual_frontend.ps1#L109) | 先8094后8093原子热更新、失败回滚并证明8093/8094/8768/8770/11434 PID不变 | 同上 |
| [verify_remote_recommendation_pages.cjs](../tools/verify_remote_recommendation_pages.cjs) | Chromium/Firefox/WebKit固定视口交互与几何验收 | 同上 |
| [serve_multi_condition_browser_fixture.py](../tools/serve_multi_condition_browser_fixture.py) | 用固定诊断流启动隔离页面；`--page-source`可原样加载远端下载页或8094候选页，同时复用本地静态资源 | 同上 |
| [remote_probe_recommendation_visual_frontend.ps1](../tools/remote_probe_recommendation_visual_frontend.ps1) | 从服务器本机只读核对五个监听、两项守卫、双HTTP、页面哈希与版本标记 | 同上 |
| [remote_probe_ws8768_service.ps1](../tools/remote_probe_ws8768_service.ps1) | 仅在8768外部探测冲突时读取守卫进程和服务器本机监听PID，不修改服务 | `ERR-OPT-8094-CORE-EVIDENCE-RUNTIME-20260806` |

## 任意炉次化验与模型受控自主调用（2026-08-06）

| 程序 | 职责 | 追踪编号 |
| --- | --- | --- |
| [mcp/imes_relay_mcp_server.py](../高炉前端数据/智能助手/mcp/imes_relay_mcp_server.py) | 暴露 `query_heat_chemistry`，按任意正式/口语炉次查询所选成分、试样和汇总 | `REQ-8093-AUTONOMOUS-HEAT-CHEMISTRY-MCP-20260806` |

## 8093 炉次生产实绩与铁水质量（2026-08-06）

| 程序 | 责任 | 追踪编号 |
|---|---|---|
| [heat_performance_quality.py](../高炉前端数据/智能助手/backend/heat_performance_quality.py) | 一炉一行表合同、多试样统计、修复状态优先 upsert、未来待核验默认隔离、镜像/汇总缺口审计 | `REQ-HEAT-QUALITY-REPAIR-CLOSED-LOOP-20260807` |
| [sync_22012_heat_performance_quality.py](../tools/sync_22012_heat_performance_quality.py) | IMES 全量/增量同步、`workdate+meltno` 双锚点回看、分页异常扫描、结构化原因和精确计数 | 同上 |
| [migrate_heat_quality_time_repair_columns_22012.py](../tools/migrate_heat_quality_time_repair_columns_22012.py) | 幂等增加原始/修复时间、异常原因、核验时刻和未来隔离字段；仅在批准的生产迁移时执行 | 同上 |
| [run_22012_heat_performance_sync.ps1](../tools/run_22012_heat_performance_sync.ps1) | 220.12 每5分钟同步任务入口，凭据只从机器环境和ACL受限文件注入 | 同上 |
| [bf-heat-performance-quality-8093.js](../高炉前端数据/assets/bf-heat-performance-quality-8093.js) | 8093“炉次实绩”入口、最近炉次表格、加载/空/错误/重试及原始试样展开 | 同上 |
| [ollama_proxy_server.py](../高炉前端数据/智能助手/backend/ollama_proxy_server.py) | 暴露只读 `GET /api/heat-performance-quality` | 同上 |
| [test_heat_performance_quality.py](../tests/test_heat_performance_quality.py) / [test_heat_performance_quality_repair_loop.py](../tests/test_heat_performance_quality_repair_loop.py) | 聚合、修复谱系保护、未来隔离、真实缺口审计、跨午夜和分页合同测试 | 同上 |
| [backend/ollama_proxy_server.py](../高炉前端数据/智能助手/backend/ollama_proxy_server.py) | 混合路由、实时Schema能力裁剪、模型工具调用事件和事实确定性格式化 | 同上 |
| [mcp/catalog/heat_analysis.json](../高炉前端数据/智能助手/mcp/catalog/heat_analysis.json) | 声明短炉号、成分选择、多试样和聚合能力 | 同上 |
| [tools/probe_model_mcp_tool_selection.py](../tools/probe_model_mcp_tool_selection.py) | 只向模型提供注册Schema并打印其结构化工具调用，不执行数据库工具、不输出隐藏推理 | 同上 |

## 8093 Failed to fetch 诊断、互斥恢复与页面容错（2026-08-06）

| 程序 | 职责 | 追踪编号 |
| --- | --- | --- |
| [assistant_8093_auto_recovery.py](../tools/assistant_8093_auto_recovery.py) | 连通性门禁、不可变包、只读分类、已知最小修复、唯一 SSE 与报告/DOCX 分离 | `REQ-8093-ASSISTANT-FETCH-RESILIENCE-20260806` |
| [remote_8093_assistant_diagnose.ps1](../tools/remote_8093_assistant_diagnose.ps1) | 一次监听快照汇总服务、端口、运行环境、守卫、SCM、知识、模型与异常 | 同上 |
| [remote_guarded_recover_8093_service.ps1](../tools/remote_guarded_recover_8093_service.ps1) | 全局互斥、已知哈希、守卫 finally、15 秒退避、最多两次受控启动和 PID 保护 | 同上 |
| [patch_8093_assistant_fetch_resilience.py](../tools/patch_8093_assistant_fetch_resilience.py) | 幂等加入中文网络提示、GET 有界重试、POST/SSE 禁止自动重发 | 同上 |
| [remote_hot_deploy_8093_fetch_resilience.ps1](../tools/remote_hot_deploy_8093_fetch_resilience.ps1) | 全局互斥、备份、页面原子热更新、失败回滚和无重启验证 | 同上 |
| [remote_verify_8093_keyword_knowledge_sse_once.ps1](../tools/remote_verify_8093_keyword_knowledge_sse_once.ps1) | 唯一一次知识问答，验证事件、RAG、模型、守卫、PID 与哈希 | 同上 |

## 炉况评分弹窗19项核心证据与趋势（2026-08-06）

| 程序 | 职责 | 追踪编号 |
| --- | --- | --- |
| [diag_ai_evidence.py](../高炉前端数据/智能助手/backend/diag_ai_evidence.py) | 固定19项变量、规则主证据、5分钟变化、30天基线和60分钟序列 | `REQ-8093-8094-DIAGNOSIS-CORE-19-TRENDS-20260806` |
| [diagnosis_ai_analysis_api.py](../高炉前端数据/智能助手/backend/diagnosis_ai_analysis_api.py) | 安装智能分析与独立核心证据HTTP处理器 | 同上 |
| [ollama_proxy_server.py](../高炉前端数据/智能助手/backend/ollama_proxy_server.py) | 提供不依赖模型完成的 `/api/diagnosis-core-evidence` 只读接口 | 同上 |
| [bf-diagnosis-manual-score-local.js](../高炉前端数据/assets/bf-diagnosis-manual-score-local.js) | 主证据优先、19项展开、变量详情与SVG趋势图 | 同上 |
| [verify_diagnosis_core19_remote.py](../tools/verify_diagnosis_core19_remote.py) | 验证精确ID、数量、曲线及轻量接口只读合同 | 同上 |
| [verify_diagnosis_ai_analysis_viewports.cjs](../tools/verify_diagnosis_ai_analysis_viewports.cjs) | Chromium/Firefox/WebKit交互、溢出、弹窗滚动和曲线验收 | 同上 |

## IMES 料速/燃料比审计与数据库模块同步（2026-08-06）

| 程序 | 职责 | 追踪编号 |
| --- | --- | --- |
| [audit_imes_material_fuel_metrics.py](../tools/audit_imes_material_fuel_metrics.py) | 白名单 Vastbase 对象的只读列/注释/样本审计，不执行任意 SQL | `REQ-IMES-MATERIAL-FUEL-AUDIT-AND-DB-MODULE-SYNC-20260806` |
| [run_imes_material_fuel_audit.ps1](../tools/run_imes_material_fuel_audit.ps1) | 从受控本机 IMES/Vastbase 加载器注入凭据并在 finally 清理进程环境 | 同上 |
| [remote_audit_imes_metric_fields.ps1](../tools/remote_audit_imes_metric_fields.ps1) | 只读核对 220.12 IMES 镜像新鲜度、字段名和批次投料结构样本 | 同上 |
| [sync_v4_db_module_to_current.ps1](../tools/sync_v4_db_module_to_current.ps1) | 白名单同步 V4 数据库模块，排除秘密/数据/日志并逐文件校验 SHA-256 | 同上 |
| [verify_foreman_coal_hourly_db.py](../tools/verify_foreman_coal_hourly_db.py) | 只读验证新增15物理点、派生点注册和本小时喷煤视图 | 同上 |
| [数据库同步和存取](../数据库同步和存取/README.md) | 当前项目的完整同步模块：IMES、pSpace、PostgreSQL、分钟/5秒存储与守卫 | 同上 |



## 当前炉次阶段性 Si 与时间段反查（2026-08-07）

| 程序 | 职责 | 追踪编号 |
|---|---|---|
| [mcp/imes_relay_mcp_server.py](../高炉前端数据/智能助手/mcp/imes_relay_mcp_server.py) | `query_current_heat_chemistry` 汇总当前已发布试样；`query_heat_chemistry_by_time_range` 解析口语时间并匹配正式炉次；精确关联铁罐号 | `REQ-MCP-IMES-HEAT-SI-SAMPLES-20260807` |
| [backend/ollama_proxy_server.py](../高炉前端数据/智能助手/backend/ollama_proxy_server.py) | 当前炉次 Si、时间段 Si 的零规划轮路由及确定性事实格式化 | 同上 |
| [backend/mcp_host/domain_router.py](../高炉前端数据/智能助手/backend/mcp_host/domain_router.py) | 将“鸬鹚”语音误识别归入 IMES 领域 | 同上 |
| [mcp/catalog/heat_analysis.json](../高炉前端数据/智能助手/mcp/catalog/heat_analysis.json) | 声明当前阶段性化验、时间段反查、逐罐/逐样本能力 | 同上 |

| 5分钟智能分析知识来源 | 高炉前端数据/智能助手/backend/ollama_proxy_server.py、diag_ai_evidence.py、diagnosis_model_review.py、assets/bf-diagnosis-manual-score-local.js | 固定只读检索 bf_foreman_ops_v1；知识详情 /api/qa/knowledge/chunk |
## front2趋势页19变量工长式同平面（2026-08-07）

| 程序 | 职责 | 追踪编号 |
|---|---|---|
| [frontend_dashboard_front2.server.html](../高炉前端数据/front2/frontend_dashboard_front2.server.html) | 单面板19变量稳健趋势带、原始值提示、历史/预测衔接、完整Chronos目标请求和返回映射 | `REQ-TREND-19-LANE-MERGE-20260807` |
| [patch_front2_trend_19_lane.py](../tools/patch_front2_trend_19_lane.py) | 幂等安装页面覆盖、完整目标请求和结果映射 | 同上 |
| [test_front2_trend_19_lane_merge.py](../tests/test_front2_trend_19_lane_merge.py) | 变量集合、单面板、稳健缩放、缺失语义、预测样式和请求合同 | 同上 |
| [verify_front2_trend_19_lane.py](../tools/verify_front2_trend_19_lane.py) | 模拟真实WebSocket历史/预测，执行Chromium/Firefox/WebKit视口验收 | 同上 |

## 炉体温度红外时空回放（2026-08-08）

| 程序 | 职责 | 追踪编号 |
|---|---|---|
| [soft_zone_replay_server.py](../tools/soft_zone_replay_server.py) | 只读查询80个炉体温度点和18个静压力点，限幅时间窗/帧数并提供静态页面 | `REQ-BODY-TEMP-INFRARED-REPLAY-20260808` |
| [soft_zone_replay](../高炉前端数据/soft_zone_replay/index.html) | 历史时间选择、红外插值画布、播放/拖动、温度8线与静压力6线联动、区域筛选、分层统计和WebM导出 | 同上 |
| [remote_deploy_22012_soft_zone_replay_8892.ps1](../tools/remote_deploy_22012_soft_zone_replay_8892.ps1) | 备份、原子部署、注册8892任务、防火墙、真实数据及受保护服务验收 | 同上 |
| [verify_soft_zone_replay_ui.cjs](../tools/verify_soft_zone_replay_ui.cjs) | 本地17项矩阵和220.12真实数据生产冒烟 | 同上 |

## A9/B13/C11炉况规则（2026-08-07）

| 程序 | 职责 | 追踪编号 |
|---|---|---|
| [abc_rule_guidance.py](../自动诊断服务/abc_rule_guidance.py) | 33项逐条炉况形成原理、严格五步干预处置流程和64章手册来源；仅含生产安全工艺说明 | `REQ-ABC33-HANDBOOK64-MECHANISM-INTERVENTION-20260810` |
| [abc_rule_catalog.py](../自动诊断服务/abc_rule_catalog.py) | 33项规则身份、传感器复核与手册处置目录 | `REQ-ABC33-FURNACE-RULES-20260807` |
| [abc_feature_builder.py](../自动诊断服务/abc_feature_builder.py) | 当前值、窗口趋势、基线和质量门禁特征 | 同上 |
| [abc_rule_engine.py](../自动诊断服务/abc_rule_engine.py) | 受控评分、置信度、四态和生产/后台序列化 | 同上 |
| [abc_rule_config_store.py](../自动诊断服务/abc_rule_config_store.py) | 草稿校验、fsync原子发布和配置哈希 | 同上 |
| [abc_runtime_store.py](../自动诊断服务/abc_runtime_store.py) | 8768实时批次与33项明细入库；同一分钟同配置冲突时同步刷新目录版本、质量快照和公开详情 | `REQ-ABC33-HANDBOOK64-MECHANISM-INTERVENTION-20260810` |
| [abc_rule_schema.sql](../自动诊断服务/abc_rule_schema.sql) / [store.py](../自动诊断服务/store.py) | ABC计算批次、明细、配置和告警审计表 | 同上 |
| [ollama_proxy_server.py](../高炉前端数据/智能助手/backend/ollama_proxy_server.py) | 生产详情、趋势与管理员内部详情接口 | 同上 |
| [abc-furnace-rules-production.js](../高炉前端数据/assets/abc-furnace-rules-production.js) | 生产页A/B/C页签、逐点复核，以及显眼的炉况形成原理/五步干预处置流程 | `REQ-ABC33-HANDBOOK64-MECHANISM-INTERVENTION-20260810` |

## 8093 智能分析数据限制误报修复（2026-08-08）

| 程序 | 职责 | 追踪编号 |
|---|---|---|
| [diag_ai_evidence.py](../高炉前端数据/智能助手/backend/diag_ai_evidence.py) | 按真实有效当前值/趋势判定数据限制，忽略可用稀疏序列的采样密度 | `BUG-8093-DIAGNOSIS-AI-FALSE-DATA-LIMITS-20260808` |
| [diagnosis_model_review.py](../高炉前端数据/智能助手/backend/diagnosis_model_review.py) | 五分钟单炉况提示词 v6、服务端事实覆盖模型输出的 data_limits | 同上 |
| [bf_knowledge_rag.py](../高炉前端数据/智能助手/backend/bf_knowledge_rag.py) | 64主题知识库来源过滤与检索适配 | 同上 |
| [remote_guarded_deploy_8093_ai_data_limit_fix.ps1](../tools/remote_guarded_deploy_8093_ai_data_limit_fix.ps1) | 仅对 8093 执行停—替换—启—验收闭环 | 同上 |

## V20 平均 Si 独立预测工作台（2026-08-08）

| 程序 | 职责 | 追踪编号 |
|---|---|---|
| [si_v20_shadow.py](../高炉前端数据/智能助手/backend/si_v20_shadow.py) | 候选炉次、历史实际/预测并集、数据就绪度和预测详情 | `REQ-SI-V20-8093-8094-SHADOW-WORKBENCH-20260808` |
| [ollama_proxy_server.py](../高炉前端数据/智能助手/backend/ollama_proxy_server.py) | V20 status/history/readiness/detail 路由及预测审计 | 同上 |
| [si_v20_workbench.html](../高炉前端数据/si_v20_workbench.html) / [bf-si-v20-workbench.js](../高炉前端数据/assets/bf-si-v20-workbench.js) | 独立全屏工作台、候选、曲线、筛选和逐炉审计 | 同上 |
| [deploy_si_v20_workbench_8093.ps1](../tools/deploy_si_v20_workbench_8093.ps1) | 8093 分段上传、守卫停启、原子替换和 API 验收 | 同上 |
## tools/set_22012_imes_realtime_1min.ps1

- 追踪编号：`OPS-IMES-REALTIME-1MIN-20260809`。
- 用途：将220.12计划任务`\GL02SensorSync\IMESRealtime`受控调整为一分钟周期，固定`IgnoreNew`防重入；同时完成原XML备份、失败回滚、镜像新鲜度和8093/8768/8094/8770 PID保护校验。
- 部署与验收：[2026-08-09 IMES实时一分钟部署记录](handoffs/2026-08-09-imes-realtime-1min.md)。
## V20 Si预测节拍审计（2026-08-09）

- [remote_audit_si_v20_hourly_tasks.ps1](../tools/remote_audit_si_v20_hourly_tasks.ps1)：在220.12只读枚举任务名称及动作，定位 V20/Si/hourly 服务器计划任务；不修改任务。
- [audit_si_v20_prediction_cadence.ps1](../tools/audit_si_v20_prediction_cadence.ps1)：读取8093 history/status API，按请求模式计数，核算小时预测相对真实开口时间、实际Si误差，并对开口前60分钟回放按炉次去重评估。
- 关联问题：`Q-SI-V20-STRICT-HOURLY-ACCURACY-20260809`；当前结论为没有严格服务器整点自动化。

## V20 双预测时序与服务器整点任务（本机实现，2026-08-09）

- [si_v20_shadow.py](../高炉前端数据/智能助手/backend/si_v20_shadow.py)：拆分历史 `open_ts-60min` 和生产整点口径；实现整点幂等、候选下一炉推断及“预测发起后第一条真实开口”动态匹配。
- [ollama_proxy_server.py](../高炉前端数据/智能助手/backend/ollama_proxy_server.py)：新增 `GET /api/si-v20/hourly-history`。
- [run_si_v20_hourly_prediction.py](../tools/run_si_v20_hourly_prediction.py)：整点预测 HTTP 原子入口，支持严格整点参数和 dry-run。
- [run_22012_si_v20_hourly_prediction.ps1](../tools/run_22012_si_v20_hourly_prediction.ps1)：220.12 本机8093调用与日志包装。
- [register_22012_si_v20_hourly_task.ps1](../tools/register_22012_si_v20_hourly_task.ps1)：注册 `\BlastFurnaceServices\SiV20HourlyShadowPrediction`，每小时 `HH:00:05`、SYSTEM、IgnoreNew。
- [set_22012_heat_quality_sync_1min.ps1](../tools/set_22012_heat_quality_sync_1min.ps1)：在保留Action/Principal、备份与失败回滚的前提下，将炉次质量汇总任务调整为一分钟尝试调度。
- [si_v20_workbench.html](../高炉前端数据/si_v20_workbench.html)、[bf-si-v20-workbench.js](../高炉前端数据/assets/bf-si-v20-workbench.js)：删除依赖页面常开的小时定时器，增加生产整点预测汇总与候选/实际炉次并列展示。
- 当前状态：`local_implementation_ready_not_deployed`。

## V20可配置分钟级预测（220.12已部署，2026-08-09）

- [si_v20_shadow.py](../高炉前端数据/智能助手/backend/si_v20_shadow.py)：配置/批次DDL、周期对齐、到期分发、历史时间槽预测、下一真实炉次匹配与曲线指标。
- [ollama_proxy_server.py](../高炉前端数据/智能助手/backend/ollama_proxy_server.py)：调度配置、分发、批量回放和定时历史API。
- [run_si_v20_schedule_dispatcher.py](../tools/run_si_v20_schedule_dispatcher.py)：调用本机8093分钟分发API。
- [run_22012_si_v20_schedule_dispatcher.ps1](../tools/run_22012_si_v20_schedule_dispatcher.ps1)：220.12运行包装和日志。
- [register_22012_si_v20_schedule_task.ps1](../tools/register_22012_si_v20_schedule_task.ps1)：固定一分钟、SYSTEM、IgnoreNew后台任务注册器。
- [si_v20_workbench.html](../高炉前端数据/si_v20_workbench.html)、[bf-si-v20-workbench.js](../高炉前端数据/assets/bf-si-v20-workbench.js)：周期配置、批量/指定时刻预测、定时时间槽曲线、日期/炉次范围筛选及预测/实际曲线CSV下载。
- [test_si_v20_configurable_schedule.py](../tests/test_si_v20_configurable_schedule.py)：周期白名单、槽对齐、配置保存、到期分发、批次和UI/API/任务合同。
- [verify_si_v20_schedule_production.py](../tools/verify_si_v20_schedule_production.py)：只读核对生产三表、默认配置和已写入的定时时间槽。
- [remote_restart_8094_detached_worker.ps1](../tools/remote_restart_8094_detached_worker.ps1)：SSH通道不稳定时，在远端工作目录内调用既有受控8094重启器并保存结果；不替代其进程归属和受保护端口检查。

## V20严格整点预测闭环（2026-08-10）

- [si_v20_strict_context.py](../高炉前端数据/智能助手/backend/si_v20_strict_context.py)：读取冻结LightGBM树，按整点构造历史Si、PCI和133点多窗口严格上下文，并输出数据水位。
- [export_si_v20_strict_context_model.py](../tools/export_si_v20_strict_context_model.py)：把V21 process133模型导出为无需LightGBM运行库的gzip JSON。
- [si_v20_shadow.py](../高炉前端数据/智能助手/backend/si_v20_shadow.py)：整点槽账本、失败重试、唯一预测、完成后固定炉次匹配和结果补齐。
- [run_si_v20_strict_hourly_dispatcher.py](../tools/run_si_v20_strict_hourly_dispatcher.py)、[run_22012_si_v20_strict_hourly.ps1](../tools/run_22012_si_v20_strict_hourly.ps1)：一分钟调用原子程序及220.12包装。
- [register_22012_si_v20_strict_hourly_task.ps1](../tools/register_22012_si_v20_strict_hourly_task.ps1)：注册永久启用的`SiV20StrictHourlyPrediction`，SYSTEM、每分钟、IgnoreNew。
- [test_si_v20_strict_hourly.py](../tests/test_si_v20_strict_hourly.py)：边界、防迟到泄漏、槽重试、24小时连续性及UI/API合同。
- [verify_si_v20_strict_hourly_production.py](../tools/verify_si_v20_strict_hourly_production.py)：只读核对生产表、槽唯一性、整点截止和Si首次可用时间。
- [verify_si_v20_strict_hourly_production_ui.cjs](../tools/verify_si_v20_strict_hourly_production_ui.cjs)：对8093/8094执行规定的跨引擎与视口矩阵。
- [deploy_si_v20_strict_hourly_22012.ps1](../tools/deploy_si_v20_strict_hourly_22012.ps1)、[remote_guarded_deploy_si_v20_strict_hourly.ps1](../tools/remote_guarded_deploy_si_v20_strict_hourly.ps1)：分段上传、8093守卫闭环、8094受控重启、API/任务/受保护端口验收。

## 本机 PowerShell 7 UTF-8 运行时（2026-08-10）

- [verify_pwsh7_utf8.ps1](../tools/verify_pwsh7_utf8.ps1)：验证当前进程为PowerShell 7 Core、统一UTF-8编码、中文项目路径可读及中文临时文件回环一致。
- [start_v3_full.ps1](../start_v3_full.ps1)：本机主启动入口；增加PowerShell 7硬门，子PowerShell使用`pwsh.exe`，默认将助手、诊断、实时桥接和同步目标统一到`GL02_LOCAL_PG*=127.0.0.1:18000/bf_trend`，并删除Docker `15432`与脚本内数据库密码回退。只有`BF_USE_EXISTING_PG_ENV=1`才保留既有主连接。
- [run_hidden_ps1.vbs](../tools/run_hidden_ps1.vbs)：本机隐藏计划任务固定调用`C:\Program Files\PowerShell\7\pwsh.exe`，缺失时退出3，不回退Windows PowerShell 5.1。
- [set_windows_terminal_pwsh7_default.ps1](../tools/set_windows_terminal_pwsh7_default.ps1)：备份并原子切换Windows Terminal默认配置到PowerShell 7，同时隐藏5.1配置但不删除系统组件。
- [PowerShell7_UTF8运行规范.md](./PowerShell7_UTF8运行规范.md)：记录命令、编码模板、升级方式、远端迁移边界和验收口径。

## 220.12 PowerShell 7远端运行时（2026-08-10）

- [remote_22012_exec.py](../tools/remote_22012_exec.py)：远端默认运行时改为PowerShell 7；SFTP暂存UTF-8 wrapper/payload，以短`-File`命令执行并自动清理，显式保留旧5.1引导选项。
- [remote_probe_22012_pwsh7.ps1](../tools/remote_probe_22012_pwsh7.ps1)：只读采集系统、PowerShell、WinGet、计划任务Action和受保护端口现状。
- [remote_install_22012_pwsh7.ps1](../tools/remote_install_22012_pwsh7.ps1)：校验官方MSI哈希/签名、静默安装、调用7验证并保护端口PID。
- [remote_verify_22012_pwsh7.ps1](../tools/remote_verify_22012_pwsh7.ps1)：验证Core版本、UTF-8中文回环及关键生产脚本语法。
- [remote_smoke_22012_pwsh7.ps1](../tools/remote_smoke_22012_pwsh7.ps1)：验证带参数块payload、中文输出、中文工作目录和五个监听端口。
- [remote_cleanup_22012_pwsh7_installer.ps1](../tools/remote_cleanup_22012_pwsh7_installer.ps1)：仅删除已核准远端Temp目录中的MSI/验证payload，保留已安装运行时。

## V20新炉次每小时持续验收（2026-08-10）

- [audit_si_v20_new_heat_acceptance.cjs](../tools/audit_si_v20_new_heat_acceptance.cjs)：冻结最新实际炉次基线，采集8093 API、页面状态和截图，实际执行页面的预测/实际CSV下载，同时导出history、strict-hourly和scheduled-interval明细，更新Markdown/HTML报告。
- [remote_probe_si_v20_acceptance.ps1](../tools/remote_probe_si_v20_acceptance.ps1)：通过PowerShell 7只读检查8093/8094/8768/8770/5432、四项同步/预测任务Action，以及8093/8094的status/history/strict-hourly/hourly-table API；V20相关任务仍调用`powershell.exe`时判失败。
- [verify_si_v20_strict_hourly_production.py](../tools/verify_si_v20_strict_hourly_production.py)：只读核验严格槽连续性、失败/运行/陈旧/逾期、重复、截止违规及缺失Si可用时间，并列出具体异常炉次。
- [remote_repair_heat_si_availability_20260810.ps1](../tools/remote_repair_heat_si_availability_20260810.ps1)：备份并更新独立炉次质量同步副本，迁移任务到PowerShell 7，执行一次同步后保护端口/API。
- [remote_migrate_v20_data_tasks_pwsh7_20260810.ps1](../tools/remote_migrate_v20_data_tasks_pwsh7_20260810.ps1)：逐任务备份XML，把IMES实时和可调V20分发任务迁移到PowerShell 7并验证运行。
- [SI_V20_NEW_HEAT_20260810](../reports/acceptance/SI_V20_NEW_HEAT_20260810/)：冻结基线、逐小时JSONL、时间戳截图、API快照、CSV导出和最终报告目录。
- Codex心跳自动化ID为`220-12-v20`，每小时持续运行；完整闭环通过后也不暂停，继续监督新炉次、严格整点和每小时汇总表。
# tools/build_abc33_handbook64_revision.py

- 职责：以《炉况计算规则补充（6）》为原始DOCX，追加ABC33形成原理、干预处置流程和见习高炉长64章映射；把权重20的料速项插入A2/B4/B5原公式第一位，原有项按0.8比例压缩为合计80；并在补充章节中作为A2首要维护项、B4/B5首要风险项，全部加粗。判据使用昨日平均和MES 24小时平均双基准，区分正常范围、硬上限和连续2小时强制提炉温条件；不覆盖来源文件。
- 对应需求：[REQ-ABC33-HANDBOOK64-MECHANISM-INTERVENTION-20260810](./requirements_traceability.md#req-abc33-handbook64-mechanism-intervention-20260810)、[REQ-ABC33-HEAT-BATCH-RATE-CRITERION-20260810](./requirements_traceability.md#req-abc33-heat-batch-rate-criterion-20260810)。
- 输入：规则补充DOCX、见习高炉长DOCX；输出：完整修订DOCX、64章映射JSON、构建审计JSON和Markdown审计。
- 核心校验：A1—A9、B1—B13、C1—C11严格完整唯一；64章全部被至少一个规则引用；每项必须具有形成原理和不少于3步的处置流程。
- 修改风险：章节映射和处置文字属于工艺知识；修改时必须保留现场规程、联锁、审批和C类独立证据边界，不得把建议改成自动控制命令。

# tools/verify_abc33_heat_batch_rate_docx.py

- 职责：重新打开实际生成DOCX，同时扫描正文与表格，核对A2/B4/B5共6处料速判据、公式第一位、权重20、其余权重合计80、双基线、正常/硬上限、两小时强预警和全段粗体格式。
- 对应需求：[REQ-ABC33-HEAT-BATCH-RATE-CRITERION-20260810](./requirements_traceability.md#req-abc33-heat-batch-rate-criterion-20260810)。
- 入口：[verify_document:L24-L104](../tools/verify_abc33_heat_batch_rate_docx.py#L24-L104)。

# 自动诊断服务/abc_burden_rate.py

- 职责：从`bf_imes.raw_rows`的`bf2_batch_input_detail_list_page_data2`煤/矿事件重建完整大批周期，计算前后30分钟、连续2小时、滚动24小时和昨日平均料速，并生成`BurdenRateDev/Slow/Fast`。
- 对应需求：[REQ-ABC33-HEAT-BATCH-RATE-CRITERION-20260810](./requirements_traceability.md#req-abc33-heat-batch-rate-criterion-20260810)。
- 数据合同：大批按相邻矿批之间完成煤矿组合的周期计速；缺窗口、事件过期或基线不足时返回不可用，不填0。

# tools/deploy_abc33_burden_rate_22012.ps1

- 职责：PowerShell 7本地门禁、持久SSH复用、9个精确文件暂存、8093守卫部署和独立8768重启验收。
- 配套：[8093远端互斥部署](../tools/remote_guarded_deploy_abc33_burden_rate_8093.ps1)、[8768受控重启](../tools/remote_restart_abc33_burden_rate_8768.ps1)、[本地测试门禁](../tools/test_abc33_burden_rate_local.ps1)。
- 生产边界：8093阶段保护8094/8768/8770/5432/8892/11434 PID；8768阶段保护8093/8094/8770/5432/8892/11434 PID。

# docs/ABC33_B类关键变量核对_20260810.md

- 职责：逐条比较B1—B13规则公式、校准因子、复合因子真实传感器依赖和`primary_sensors`，记录历史缺项及2026-08-10在线修复结果。
- 核心结论：B类权重合计与方向正确；复核目录已补齐实际依赖，B4/B5已接入`BurdenRateSlow/Fast`和权重20；`P_blast/PCI_rate`语义边界保持不变。
- 报告：[ABC33 B类关键变量核对](./ABC33_B类关键变量核对_20260810.md)。

## 软熔带移动特征融合诊断（2026-08-10）

| 程序 | 职责 | 追踪编号 |
|---|---|---|
| [cohesive_zone_intelligent_diagnosis.py:L63-L469](../炉况规则引擎/features/cohesive_zone_intelligent_diagnosis.py#L63-L469) | 校验安全配置，按历史截止切分当前/参考窗口，提取Word定义的特征，生成方向概率、逐项驱动、关联炉况证据，并可与现有C2几何估算器组合 | `REQ-COHESIVE-ZONE-INTELLIGENT-DIAGNOSIS-20260810` |
| [cohesive_zone_intelligent_diagnosis.yaml:L9-L209](../炉况规则引擎/config/cohesive_zone_intelligent_diagnosis.yaml#L9-L209) | 特征别名、有效范围、变化尺度、方向、权重、覆盖门禁和炉况关联映射 | 同上 |
| [run_cohesive_zone_intelligent_diagnosis.py:L24-L88](../tools/run_cohesive_zone_intelligent_diagnosis.py#L24-L88) | 本机CSV读取、历史截止、可选C2组合和UTF-8 JSON输出 | 同上 |
| [verify_cohesive_zone_intelligent_diagnosis.ps1:L1-L41](../tools/verify_cohesive_zone_intelligent_diagnosis.ps1#L1-L41) | PowerShell 7 Core与UTF-8门禁、语法、30项pytest和CLI帮助检查 | 同上 |
| [test_cohesive_zone_intelligent_diagnosis.py:L84-L161](../tests/test_cohesive_zone_intelligent_diagnosis.py#L84-L161) | 三方向、风险证据、防未来泄漏、缺失输入、组合包装和CSV端到端合同 | 同上 |

修改风险：特征方向、单位、有效范围和`delta_scale`共同决定诊断方向；修改YAML时必须保持`confidence_cap<=0.45`和`control_use=prohibited`，并运行专项验证。没有经接受的`H_cz`真值时不得把`prediction_method`改成训练模型名称。

## HCZ专家弱标签工作台（2026-08-10）

| 程序 | 职责 |
|---|---|
| [hcz_expert_label.py](../高炉前端数据/智能助手/backend/hcz_expert_label.py) | 校验人工标签、知识时间、盲标字段，计算实测窗口SHA-256并追加写入PostgreSQL |
| [soft_zone_replay_server.py](../tools/soft_zone_replay_server.py) | 在8892提供标签配置、实测上下文、追加提交、历史和CSV导出API |
| [hcz-labeling.html](../高炉前端数据/soft_zone_replay/hcz-labeling.html) / [hcz-labeling.js](../高炉前端数据/soft_zone_replay/hcz-labeling.js) | 高炉长任务表单、实测回放选时、证据固定、状态反馈、历史和修订入口 |
| [soft-zone-replay.js](../高炉前端数据/soft_zone_replay/soft-zone-replay.js) | `labeling_blind=1`时强制`include_cohesive=0`并隐藏估计控件，通过同源消息传递标注时刻 |
| [deploy_hcz_expert_label_22012.ps1](../tools/deploy_hcz_expert_label_22012.ps1) | 上传受控文件并调用远端部署 |
| [remote_guarded_deploy_hcz_expert_label_8892.ps1](../tools/remote_guarded_deploy_hcz_expert_label_8892.ps1) | 备份、只重启8892、迁移任务到PowerShell 7、验证API/页面/受保护PID并失败回滚 |
| [audit_pspace_top4_hcz_aug9.py](../tools/audit_pspace_top4_hcz_aug9.py) | 在220.12只读直连pSpace，读取GL02四点顶温并输出小时均值、样本数和证据SHA-256 |
| [remote_submit_hcz_aug9_upward_label.ps1](../tools/remote_submit_hcz_aug9_upward_label.ps1) | 在PowerShell 7中刷新8892盲证据哈希、拒绝同刻重复并追加/回读8月9日上移弱标签 |

追踪编号：`REQ-HCZ-EXPERT-WEAK-LABEL-20260810`。修改盲标、知识时间或追加式存储合同后必须运行[专项测试](../tests/test_hcz_expert_label.py)和[跨引擎UI验收](../tools/verify_hcz_expert_label_ui.cjs)。

## HCZ上移综合趋势经验规则（2026-08-10）

| 程序 | 职责 |
|---|---|
| [hcz_upward_expert_rule.py](../炉况规则引擎/features/hcz_upward_expert_rule.py) | 聚合小时输入，比较24小时与前5天，执行五项核心、炉壁层数和连续12小时严格AND门禁 |
| [hcz_upward_expert_rule.yaml](../炉况规则引擎/config/hcz_upward_expert_rule.yaml) | 固化阈值、单位、覆盖条件、变量映射和安全合同 |
| [hcz_upward_rule_api.py](../高炉前端数据/智能助手/backend/hcz_upward_rule_api.py) | 从220.12本地`bf_sensor`只读聚合144小时数据并提供120秒缓存 |
| [ollama_proxy_server.py](../高炉前端数据/智能助手/backend/ollama_proxy_server.py) | 注册`GET /api/hcz-upward-rule`同源路由 |
| [hcz_upward_rule.html](../高炉前端数据/hcz_upward_rule.html) / [hcz-upward-rule.js](../高炉前端数据/assets/hcz-upward-rule.js) | 展示结论、5项指标、7层温度、3个规则门和完整公式 |
| [deploy_hcz_upward_rule_22012.ps1](../tools/deploy_hcz_upward_rule_22012.ps1) | PowerShell 7本机上传入口 |
| [remote_guarded_deploy_hcz_upward_rule_8093.ps1](../tools/remote_guarded_deploy_hcz_upward_rule_8093.ps1) | 8093守卫停—改—启、原子部署、回滚和受保护端口验收 |
| [remote_probe_hcz_cold_blast_pressure_8093.ps1](../tools/remote_probe_hcz_cold_blast_pressure_8093.ps1) | 只读核对生产配置哈希、压力标签、实际变量口径和受保护监听 |
| [deploy_hcz_cold_blast_pressure_22012.ps1](../tools/deploy_hcz_cold_blast_pressure_22012.ps1) | 验证准备清单、生成单文件差量、复用持久SSH预暂存并调用守卫部署 |
| [remote_guarded_deploy_hcz_cold_blast_pressure_8093.ps1](../tools/remote_guarded_deploy_hcz_cold_blast_pressure_8093.ps1) | 只替换HCZ规则YAML，验证`P_blast_cold`、API标签、阈值、回滚和受保护PID |
| [hcz_upward_expert_rule.py](../炉况规则引擎/features/hcz_upward_expert_rule.py) | 复用准备后的小时序列，按生产默认与单次试算参数回放上移及符号对称下移候选 |
| [hcz_upward_rule_api.py](../高炉前端数据/智能助手/backend/hcz_upward_rule_api.py) | 提供`GET /api/hcz-rule-sensitivity`，缓存90天只读小时数据并在入口完成`GasUtil × 100` |
| [verify_hcz_upward_rule_ui.cjs](../tools/verify_hcz_upward_rule_ui.cjs) | 标准17组合验证阈值15→10、诊断量变化、百分数/百分点单位和响应式布局 |
| [prepare_hcz_rule_sensitivity_8093_release.ps1](../tools/prepare_hcz_rule_sensitivity_8093_release.ps1) / [deploy_hcz_rule_sensitivity_22012.ps1](../tools/deploy_hcz_rule_sensitivity_22012.ps1) | 封存六文件发布清单并执行持久SSH差量部署 |
| [remote_guarded_deploy_hcz_rule_sensitivity_8093.ps1](../tools/remote_guarded_deploy_hcz_rule_sensitivity_8093.ps1) | 在全局互斥下备份、仅暂停8093、原子替换、恢复、真实90天试算和受保护PID验收 |

追踪编号：`REQ-HCZ-UPWARD-EXPERT-RULE-20260810`、`REQ-HCZ-RULE-SENSITIVITY-20260811`。2026-08-11第五项已按高炉长口径切换为冷风风压`P_blast_cold`；禁止只改中文标签而继续读取热风压力`P_blast`。页面试算值不保存；正式阈值、单位、变量或持续时间变化仍属于工艺规则变更，必须同步更新[规则文档](./GL02软熔带上移综合趋势经验规则_20260810.md)、专项测试并重新走守卫部署。

## 8093炉况详情提示精简（2026-08-10）

| 程序 | 职责 |
|---|---|
| [abc-furnace-rules-production.js](../高炉前端数据/assets/abc-furnace-rules-production.js) | 8093详情不创建“严重事件交叉确认”提示元素；8094保持原显示逻辑 |
| [test_abc_production_ui.py](../tests/test_abc_production_ui.py) | 锁定8093端口级渲染门禁，防止提示条回归 |
| [remote_guarded_remove_8093_cross_confirmation_banner.ps1](../tools/remote_guarded_remove_8093_cross_confirmation_banner.ps1) | 仅暂停/恢复8093守卫，原子更新资源、缓存版本、失败回滚并保护其他端口 |

追踪编号：`REQ-8093-REMOVE-CROSS-CONFIRMATION-BANNER-20260810`。本项仅为8093显示精简，不得借此修改ABC33公式、分数、接口合同或8094页面。

## 8093炉况处置首屏与工艺依据按钮（2026-08-10）

| 程序 | 职责 |
|---|---|
| [abc-furnace-rules-production.js](../高炉前端数据/assets/abc-furnace-rules-production.js) | 8093详情首屏显示处置顺序，按钮展开工艺依据/操作原理，不渲染来源章节索引 |
| [test_abc_production_ui.py](../tests/test_abc_production_ui.py) | 锁定处置顺序、按钮可访问状态、两块内容和8093无章节索引合同 |
| [remote_guarded_deploy_8093_action_first_basis_toggle.ps1](../tools/remote_guarded_deploy_8093_action_first_basis_toggle.ps1) | 只暂停/恢复8093守卫，备份、原子部署、API合同和受保护端口验证 |

追踪编号：`REQ-8093-ABC33-ACTION-FIRST-BASIS-TOGGLE-20260810`。来源章节继续保留在后台审计与文档，不得重新暴露到8093生产操作详情。

## 8093 ABC33复核点中文名称统一（2026-08-10）

| 程序 | 职责 |
|---|---|
| [abc_public_review.py](../自动诊断服务/abc_public_review.py) | 生产复核详情的中文名称和单位目录；补齐理论燃烧温度、热风温度、料罐重量/设定及氮气压力/流量 |
| [abc-furnace-rules-production.js](../高炉前端数据/assets/abc-furnace-rules-production.js) | 复核点只渲染中文名称，不在操作页面展示内部变量键；内部键仅作为不可见审计属性保留 |
| [audit_abc33_operator_metric_labels.py](../tools/audit_abc33_operator_metric_labels.py) | 遍历生产最新33条详情的全部指标，报告非中文、内部键直出和详情读取错误 |
| [test_abc_public_review_labels.py](../tests/test_abc_public_review_labels.py) | 锁定后端中文名称与单位合同 |
| [test_abc_production_ui.py](../tests/test_abc_production_ui.py) | 锁定前端中文优先和不显示内部变量键合同 |
| [remote_guarded_deploy_8093_chinese_metric_labels.ps1](../tools/remote_guarded_deploy_8093_chinese_metric_labels.ps1) | 仅暂停/恢复8093守卫，原子部署前后端文件，并以33项全量扫描作为上线硬门禁 |

追踪编号：`REQ-8093-ABC33-CHINESE-METRIC-LABELS-20260810`。新增复核变量时必须同时配置中文名称，并通过全量生产扫描后方可发布。

## 8093 ABC33复核分组互斥（2026-08-10）

| 程序 | 职责 |
|---|---|
| [abc_public_review.py](../自动诊断服务/abc_public_review.py) | `_group_metrics`按重要性选出主复核点，再从剩余变量构造炉壳、冷却和其他分组，保证四组互斥 |
| [abc-furnace-rules-production.js](../高炉前端数据/assets/abc-furnace-rules-production.js) | `disjointReviewGroups`提供浏览器端第二道按变量键去重，后续分组标题明确为“其余”点位 |
| [audit_abc33_review_group_duplicates.py](../tools/audit_abc33_review_group_duplicates.py) | 逐条读取33项生产详情，统计跨组重复变量、重复展示次数和受影响规则；`--require-clean`作为部署硬门禁 |
| [test_abc_public_review_labels.py](../tests/test_abc_public_review_labels.py) | 验证后端四组变量并集不丢失、交集为空 |
| [test_abc_production_ui.py](../tests/test_abc_production_ui.py) | 锁定前端去重顺序、`seen`保护和“其余”分组渲染 |
| [remote_guarded_deploy_8093_disjoint_review_groups.ps1](../tools/remote_guarded_deploy_8093_disjoint_review_groups.ps1) | 守卫停—改—启、原子部署、中文标签回归和33项零重复硬门禁 |

追踪编号：`REQ-8093-ABC33-DISJOINT-REVIEW-GROUPS-20260810`。后续新增分组时必须接在同一去重顺序之后，不得重新从完整指标集构造页面分组。

## 8093 ABC33复核表纵向语义布局（2026-08-10）

| 程序 | 职责 |
|---|---|
| [abc-furnace-rules-production.js](../高炉前端数据/assets/abc-furnace-rules-production.js) | 复核数值使用无最小宽度的6列固定布局；语义独占下一整行；详情禁止横向溢出、允许纵向增长，窄屏改为两列卡片 |
| [test_abc_production_ui.py](../tests/test_abc_production_ui.py) | 锁定无1120px强制宽度、无内部固定高度、语义跨6列、自动换行和窄屏结构 |
| [audit_abc33_review_group_duplicates.py](../tools/audit_abc33_review_group_duplicates.py) | 在既有跨组去重审计之外统计473条语义覆盖率、缺失数和最长语义压力样本 |
| [remote_guarded_deploy_8093_vertical_metric_layout.ps1](../tools/remote_guarded_deploy_8093_vertical_metric_layout.ps1) | 只更新8093页面资源，校验纵向布局标记、33项语义完整性和受保护服务PID |

追踪编号：`REQ-8093-ABC33-VERTICAL-METRIC-LAYOUT-20260810`。不得重新引入表格固定最小宽度、语义末列或表格内部横向滚动。

## 8093受控更新Skill（2026-08-10）

| 程序/资源 | 职责 |
|---|---|
| [SKILL.md](../.codex/skills/deploy-8093-guarded-update/SKILL.md) | 项目版本源；固化准备一次/差量上线、持久SSH复用、upload-only暂存、8093守卫停—改—启、验收和失败回滚的低自由度流程 |
| [project-contract.md](../.codex/skills/deploy-8093-guarded-update/references/project-contract.md) | 记录220.12根目录、服务身份、PowerShell 7、部署互斥、受保护端口和最小证据合同 |
| [two-phase-fast-deployment.md](../.codex/skills/deploy-8093-guarded-update/references/two-phase-fast-deployment.md) | 不可变准备清单、Luna/只读预检并行、差量上传、确定性验收和即时生效通知合同 |
| [release_manifest.py](../.codex/skills/deploy-8093-guarded-update/scripts/release_manifest.py) | 生成/校验`prepared-release`，依据实时远端哈希生成密封`delta-plan`并拒绝失效产物、未评审基线和错误create边界 |
| [python-artifact-protection.md](../.codex/skills/deploy-8093-guarded-update/references/python-artifact-protection.md) | 规定`.pyc`/Nuitka/Cython选择、本机构建、只传原生产物、入口切换、验收和逆向风险边界 |
| [sync_deploy_8093_guarded_update_skill.ps1](../tools/sync_deploy_8093_guarded_update_skill.ps1) | 以14文件白名单在项目版本源和全局Codex运行镜像之间执行显式导入、单向发布和逐文件哈希校验；不访问生产环境 |
| [remote_22012_session.py](../tools/remote_22012_session.py) | localhost会话代理：持有一个已认证SSH transport、keepalive、断线重连计数、每请求独立channel且不重放不确定命令 |
| [start_remote_22012_session.ps1](../tools/start_remote_22012_session.ps1) | PowerShell 7/UTF-8入口；确保会话存在并复用，代理自身以隐藏进程持续运行 |
| [stop_remote_22012_session.ps1](../tools/stop_remote_22012_session.ps1) | 显式停止会话代理；正常部署结束不调用 |
| [deploy_8093_guarded_update.ps1.template](../.codex/skills/deploy-8093-guarded-update/assets/deploy_8093_guarded_update.ps1.template) | 本机Phase B模板：校验准备清单和远端状态、生成差量、只上传变化文件、复用会话并输出即时通知信号 |
| [remote_guarded_deploy_8093.ps1.template](../.codex/skills/deploy-8093-guarded-update/assets/remote_guarded_deploy_8093.ps1.template) | 消费密封差量计划，执行基线哈希、互斥、备份、原子安装、恢复、验收与回滚 |
| [validate_skill.ps1](../.codex/skills/deploy-8093-guarded-update/scripts/validate_skill.ps1) | 只读检查Skill关键合同并用PowerShell解析两份模板；不访问生产环境 |

追踪编号：`OPS-8093-GUARDED-UPDATE-SKILL-20260810`、`OPS-22012-PERSISTENT-SSH-AND-PYTHON-PROTECTION-20260810`。实际部署仍必须在仓库`tools/`生成或复用经过评审的功能专用脚本；不得直接执行未替换占位符、未加功能验收的模板。

## 8093 Skill复用计时、受控学习与Reliable SSH MCP保活（2026-08-10）

| 程序/资源 | 职责 |
|---|---|
| [verify_22012_persistent_ssh_reuse.ps1](../tools/verify_22012_persistent_ssh_reuse.ps1) | 本机PowerShell 7入口；冷连接可选、同一会话双次独立`.ps1`、连接/请求号断言、延迟与本机JSONL证据 |
| [remote_probe_22012_persistent_session.ps1](../tools/remote_probe_22012_persistent_session.ps1) | 远端独立UTF-8只读探针，输出PowerShell版本/Core、UTF-8、主机、PID和时间 |
| [remote_22012_exec.py](../tools/remote_22012_exec.py) | 允许调用者注入并持有SSH和SFTP客户端；普通单次入口仍自行关闭资源 |
| [remote_22012_session.py](../tools/remote_22012_session.py) | 同时复用认证transport和串行SFTP通道，断线不重放命令 |
| [deployment_memory.py](../.codex/skills/deploy-8093-guarded-update/scripts/deployment_memory.py) | 本机部署耗时、失败脱敏、指纹聚合、候选学习和统计摘要 |
| [connection-pool.js](../../网络登录服务器管理/reliable-ssh-mcp/src/connection-pool.js) | OpenSSH/Plink常驻远端runner、应用心跳、请求指标、按请求前恢复且不自动重放 |
| [server.js](../../网络登录服务器管理/reliable-ssh-mcp/src/server.js) | 单服务器MCP可选连接池并提供`connection_status` |
| [reliable_ssh_22012_cli.mjs](../tools/reliable_ssh_22012_cli.mjs) | 220.12连接池验证和诊断包传输；远端ZIP结构化解压后使用PowerShell 7 `-File` |
| [benchmark_22012_ssh_command_latency.ps1](../tools/benchmark_22012_ssh_command_latency.ps1) | 5组冷/复用交错样本，输出median、p90、分阶段耗时、每命令节约和新会话盈亏平衡点 |
| [build_python_native_artifact.ps1](../tools/build_python_native_artifact.ps1) | PowerShell 7原生构建入口；默认计划模式，显式创建Python 3.11 x64环境、安装依赖和执行Nuitka/Cython |
| [build_python_native_artifact.py](../tools/build_python_native_artifact.py) | 校验构建spec、生成三类原生产物命令和哈希/ABI/入口/回滚清单，源码保密模式拒绝`.py/.pyw`产物 |
| [deploy_abc33_b4_score_source_22012.ps1](../tools/deploy_abc33_b4_score_source_22012.ps1) | 复用持久SSH，上传五个精确文件并执行8093守卫部署 |
| [remote_guarded_deploy_abc33_b4_score_source_8093.ps1](../tools/remote_guarded_deploy_abc33_b4_score_source_8093.ps1) | 基线哈希、全局互斥、备份、原子安装、B4/归档/API/PID验收和失败回滚 |

追踪编号：`OPS-8093-SKILL-REUSE-METRICS-LEARNING-AND-RSSH-MCP-20260810`。

评分源追踪编号：`REQ-8093-ABC33-B4-CANONICAL-SCORE-20260810`。

## 8093风险分级浏览器验收（OPS-8093-RISK-TIERED-VALIDATION-20260810）

| 程序 | 作用 |
| --- | --- |
| [verify_diagnosis_review_local.py](../tools/verify_diagnosis_review_local.py) | 提供`quick/standard/full`三档矩阵，按内核复用浏览器context并记录导航与总耗时 |
| [test_diagnosis_review_browser_profiles.py](../tests/test_diagnosis_review_browser_profiles.py) | 固定4/17/85项数量、受影响路由边界及1546×864完整矩阵合同 |
| [validation-tiers.md](C:/Users/hmw20/.codex/skills/deploy-8093-guarded-update/references/validation-tiers.md) | 8093 Skill的风险选择、升级条件与生产定向冒烟规则 |

## Codex经济型委派（OPS-CODEX-ECONOMICAL-DELEGATION-20260810）

| 程序 | 作用 |
| --- | --- |
| [SKILL.md](C:/Users/hmw20/.codex/skills/codex-economical-delegation/SKILL.md) | 选择“不调用模型/Luna/Terra/Sol”、委派边界、验收与成本核算 |
| [invoke_codex_delegate.ps1](C:/Users/hmw20/.codex/skills/codex-economical-delegation/scripts/invoke_codex_delegate.ps1) | PowerShell 7 UTF-8入口；实时模型探测、只读默认、最小工具面、JSON用量/耗时输出 |
| [model-routing.md](C:/Users/hmw20/.codex/skills/codex-economical-delegation/references/model-routing.md) | 当前CLI能力、任务分级和委派prompt合同 |

## 8093前端生产构建与轻量运行时（REQ-8093-FRONTEND-PERF-R1）

| 程序 | 作用 |
| --- | --- |
| `高炉前端数据/dashboard_build/scripts/build-dashboard.mjs` | 从现有HTML提取React入口并用Vite/esbuild生成生产HTML和哈希资源 |
| `高炉前端数据/dashboard_build/src/overview-route-loader.js` | 只在总览路由顺序加载共享连接与3D运行时 |
| `高炉前端数据/assets/bf-shared-runtime-scheduler.js` | 合并周期任务并在页面隐藏时暂停 |
| `高炉前端数据/智能助手/backend/http_static_compression.py` | gzip/Brotli协商压缩 |
| `tools/verify_8093_frontend_production_build.py` | 默认Chromium 1366x768核心冒烟；显式参数才运行85项矩阵 |
| `tools/deploy_8093_frontend_perf_22012.ps1` | 本机构建、定向验证、持久SSH预暂存、远端受控部署和同会话复核入口 |
| `tools/remote_guarded_deploy_8093_frontend_perf.ps1` | 远端互斥、备份、只暂停8093守卫、原子替换、恢复、压缩/缓存/PID验收与失败回滚 |

## 8093核心变量弹窗与独立基线（BUG-8093-CORE-PORTAL-BASELINE-20260811）

| 程序 | 作用 |
| --- | --- |
| [verify_8093_core_spark_detail.py](../tools/verify_8093_core_spark_detail.py) | 验证弹窗挂载到body、最高层显示、可交互、无横向溢出；支持受影响路由17组合 |
| [verify_8093_core_metrics_pspace_live.py](../tools/verify_8093_core_metrics_pspace_live.py) | 逐行复算raw、median、IQR、deviation、status并核对28变量证据 |
| [deploy_8093_core_modal_baseline_22012.ps1](../tools/deploy_8093_core_modal_baseline_22012.ps1) | 校验不可变清单、复用SSH、只上传HTML与哈希主包并调用受控上线 |
| [remote_guarded_deploy_8093_core_modal_baseline.ps1](../tools/remote_guarded_deploy_8093_core_modal_baseline.ps1) | 全局互斥、备份、只暂停8093、原子替换、恢复、HTTP/哈希/受保护PID验收与回滚 |
## 时间序列排行榜（2026-08-11）

| 程序 | 责任 | 风险边界 |
|---|---|---|
| [tools/timeseries_leaderboard.py](../tools/timeseries_leaderboard.py) | 合并同切点评测明细，计算综合和分维度排名，输出JSON/CSV/Markdown | 离线只读，不切换模型 |
| [tools/timeseries_sidecar_service.py](../tools/timeseries_sidecar_service.py) | 在8778热加载排行榜JSON并提供只读接口 | 文件缺失返回503，预测默认模型保持独立 |
| [tools/check_timeseries_sidecar_python.py](../tools/check_timeseries_sidecar_python.py) | 检查8778状态、模型目录和排行榜schema | 只读HTTP检查 |
| [tests/test_timeseries_leaderboard.py](../tests/test_timeseries_leaderboard.py) | 验证共同切点、排名和schema拒绝 | 本机测试 |
## 8093 ABC33炉况总览入口（2026-08-11）

- 页面运行时：`高炉前端数据/assets/abc-furnace-rules-production.js`
- 页面装载：`高炉前端数据/frontend_dashboard_v3.server.html`
- 标准矩阵：`tools/verify_abc33_overview_entry_standard.cjs`
- 生产冒烟：`tools/verify_abc33_overview_entry_production.cjs`
- 受控部署：`tools/deploy_abc33_overview_entry_22012.ps1`
## pSpace探尺实时料速（2026-08-11）

- 计算入口：`自动诊断服务/abc_burden_rate.py::fetch_burden_rate_snapshot`
- 小批识别：`_probe_events`；南北合并：`_merge_probe_events`；重量分型：`_classify_charge_events`。
- 规则消费者：A2 `BurdenRateDev`、B4 `BurdenRateSlow`、B5 `BurdenRateFast`。
- 测试：`tests/test_abc_burden_rate.py`、`tools/verify_abc33_probe_burden_rate.ps1`、`tools/audit_8093_probe_burden_rate_http.py`。

## 220.12:8093维护交接包（2026-08-11）

- 构建入口：`tools/build_8093_handoff_package.ps1`
- 源文件白名单：`tools/handoff/8093_handoff_manifest.json`
- 包内接手说明源：`tools/handoff/8093_HANDOFF_README.md`
- 合同测试：`tests/test_8093_handoff_package.py`
- 本地输出：`handoff_packages/`（Git忽略）

## ABC33 上下文智能助手

- 解释合同：`自动诊断服务/abc_rule_explanation.py`
- 权威适配：`高炉前端数据/智能助手/backend/abc_rule_assistant_analysis.py`
- API/会话/SSE：`高炉前端数据/智能助手/backend/ollama_proxy_server.py`
- 数据迁移：`高炉前端数据/智能助手/backend/schema/20260811_abc_contextual_assistant.sql`
- 炉框入口：`高炉前端数据/assets/abc-furnace-rules-production.js`
- 弹窗：`高炉前端数据/assets/bf-abc33-assistant-dialog.js` 与 `.css`

## 8093 QA 会话登录桥接（2026-08-12）

- 页面与传输：[frontend_dashboard_v3.server.html](../高炉前端数据/frontend_dashboard_v3.server.html)：类型化保留 HTTP 错误码，识别 `qa_session_required`，显示同源登录框并在成功后重新 bootstrap。
- 浏览器合同：[verify_qa_session_login_bridge.cjs](../tools/verify_qa_session_login_bridge.cjs)：模拟 403→登录→会话加载，断言模型/问答 POST 为 0、密码输入框销毁。
- 生产更新：[remote_guarded_deploy_qa_session_login_bridge_8093.ps1](../tools/remote_guarded_deploy_qa_session_login_bridge_8093.ps1)：基线哈希、唯一锚点、Dry Run、互斥、备份、仅停 8093、受保护 PID 和回滚。
## QA 共享访客与 MCP 最终回答降级（2026-08-13）

- [ollama_proxy_server.py](../高炉前端数据/智能助手/backend/ollama_proxy_server.py)：`shared_guest_identity/ensure_shared_guest_conversation/qa_access_identity` 固定共享房间；`qa_mcp_final_fallback/qa_mcp_result_with_fallback` 保证工具失败后仍有一次无工具模型最终回答。
- [frontend_dashboard_v3.server.html](../高炉前端数据/frontend_dashboard_v3.server.html)：未登录默认显示共享访客窗口和数据库时间戳，私有登录入口独立保留。
- [postgresql_assistant.sql](../高炉前端数据/智能助手/backend/schema/postgresql_assistant.sql)：条件唯一索引保证每个访客房间只有一个会话。

## 153点位语义目录与智能体评测（2026-08-13）

- `tools/generate_semantic_point_catalog.py`：从七列权威TSV生成版本化别名、完整问法、碰撞和哈希。
- `数据库同步和存取/config/点位语义目录.json`：153个标准ID的语义伴生目录，不含凭据。
- `高炉前端数据/智能助手/mcp/bf_data_mcp_server.py`：加载语义别名和完整物理fallback目录，精确解析。
- `高炉前端数据/智能助手/backend/ollama_proxy_server.py`：单点/组合路由和静压、喷煤小时、阀前后抑制。
- `.codex/skills/agent-tool-capability-evaluation/`：十类指标、评分规则与机器评测入口。
- `tests/test_semantic_point_catalog.py`：全量别名、唯一口语、多点集合和未知拒识回归。

## MCP传感器推断与多工具计算评测（2026-08-13）

- `tools/evaluate_8093_mcp_sensor_reasoning.py`：三题生产 SSE 评估入口；每题只发一次、不重试，
  分开计算工具合同与答案合同，并独立复算极差、CV 和相关性证据。
- `tools/probe_8093_cross_mcp_computation.py`：底层共享访客 bootstrap、SSE 解析和工具轨迹采集。
- `tests/test_evaluate_8093_mcp_sensor_reasoning.py`：验证分层评分、统计复算和完整 source_status 证据读取。
- `PT/MCP可执行功能及口语调用模板.md` 第16节：固定题目、字段合同、执行命令和判分口径。
- `.codex/skills/agent-tool-capability-evaluation/scripts/evaluate_mcp_template_lines.py`：逐行解析、
  预期/实际比较、四类能力评分、检查点续跑与报告生成的权威实现。
- `tools/evaluate_mcp_template_lines.py`：项目根目录薄入口，不重复实现 Skill 逻辑。
- `tools/sync_agent_tool_capability_evaluation_skill.ps1`：七文件精确清单，从项目版本源发布到全局运行镜像并校验哈希。

## MCP 扩展生产回归与隔离故障预览（2026-08-14）

- `PT/智能体工具能力扩展生产回归.v1.json`：14 个权威变量、42 个真实问法和证据合同。
- `tools/evaluate_mcp_extended_production.py`：逐题或 6 并发执行生产 SSE，记录事件、工具轨迹、
  证据字段、请求数、重试数和延迟，不自动重发失败请求。
- `tools/mcp_fault_preview_acceptance.py`：只供隔离回环预览使用，注入超时、部分失败、全失败与
  工具结果注入夹具；禁止把该入口指向生产 8093。
- `tools/rescore_mcp_gold_report.py` 与 `tools/rescore_mcp_fault_preview.py`：只读重评分已保存报告，
  输出 `additional_model_requests=0`，保留原始结果。
- `tools/build_mcp_extended_regression_summary.py`：合并 pass^5、42 点位、并发、会话隔离和故障报告。
- `tools/remote_verify_8093_guest_owner_isolation.ps1`：只读验证共享访客与登录 owner 的会话隔离，
  不回显凭据、不发送模型问答。
- `PT/智能体工具能力口语化生产回归.v1.json`：不含任何内部变量 ID 的 42 个现场口语问题；
  A-H 只作为独立方位字母。与标准名矩阵分开统计，避免把 `中文名称（ID）` 的成功冒充为纯口语
  解析成功。
- `tools/evaluate_mcp_extended_production.py::validate_spoken_prompt_policy`：发送请求前加载完整点位目录，
  拒绝已知内部 ID 和未知下划线技术串；违规题零模型请求。

## 炉体温度分层与单点确定性统计（2026-08-14）

| 程序 | 职责 | 追踪编号 |
|---|---|---|
| [bf_data_extended_mcp_server.py](../高炉前端数据/智能助手/mcp/bf_data_extended_mcp_server.py#L308) | 单次只读批量查询 7–16 层 A–H，计算逐层、单点、滚动波动和完整质量事实 | `REQ-MCP-BODY-LAYER-STATISTICS-20260814` |
| [ollama_proxy_server.py](../高炉前端数据/智能助手/backend/ollama_proxy_server.py#L4286) | 解析中文层范围/时间范围，生成一次复合调用并确定性格式化答案 | 同上 |
| [cross_source_executor.py](../高炉前端数据/智能助手/backend/mcp_host/cross_source_executor.py#L413) | 将紧凑统计结果投影为 `body_temperature_statistics` 事实 | 同上 |
| [calculation_tools.json](../高炉前端数据/智能助手/mcp/catalog/calculation_tools.json#L71) | 登记 `body_temperature_layer_statistics` 计算能力 | 同上 |
| [test_body_temperature_layer_statistics.py](../tests/test_body_temperature_layer_statistics.py) | 覆盖 7–13 层展开、显式钟点、总窗/滚动窗分离、工具计算和证据格式 | 同上 |
| [ollama_proxy_server.py 执行摘要与解释边界](../高炉前端数据/智能助手/backend/ollama_proxy_server.py) | 生成脱敏 `public_trace`、一次复合调用耗时/证据计数，并对模型解释执行新增数字拒绝 | `REQ-QA-COMPOSITE-MCP-EXECUTION-TRACE-20260814` |
| [frontend_dashboard_v3.server.html](../高炉前端数据/frontend_dashboard_v3.server.html) | 消费五类 SSE 进度事件，将 `public_trace` 实时显示为“执行详情”，不渲染原始工具参数/结果 | 同上 |
| [test_qa_tool_execution_trace_ui.py](../tests/test_qa_tool_execution_trace_ui.py) | 验证 SSE 分发、当前 QA 页面接线和只消费脱敏字段 | 同上 |

受控发布入口为 `tools/prepare_8093_body_temperature_statistics_release.ps1` 与
`tools/run_8093_body_temperature_statistics_deploy_20260814.ps1`；时间窗增量修复使用对应
`body_temperature_window_fix` 脚本。生产 Git 已保存为 `849d9554060f7c1252722e8394a9cb224ff13488`。
# REQ-QA-MCP-VISUAL-RECOMMENDATIONS-20260814

- [ollama_proxy_server.py:L4662-L4712](../高炉前端数据/智能助手/backend/ollama_proxy_server.py#L4662-L4712)：
  纯中文炉体温度矩阵热度图路由，生成单个 `plot_gl02_body_temperature_matrix` 调用。
- [frontend_dashboard_v3.server.html:L8881-L8882](../高炉前端数据/frontend_dashboard_v3.server.html#L8881-L8882)：
  安全解析并渲染同源 MCP PNG。
- [frontend_dashboard_v3.server.html:L9223-L9252](../高炉前端数据/frontend_dashboard_v3.server.html#L9223-L9252)：
  常用 MCP 模板、相关追问、浏览器固定/自定义持久化和滚动推荐区。
- [verify_abc_contextual_assistant_viewports.cjs:L350-L388](../tools/verify_abc_contextual_assistant_viewports.cjs#L350-L388)：
  QA 单视口验证固定、自定义、相关问题与零真实模型请求。
- 修改风险：调整模板顺序会影响推荐排序；调整安全图片正则会影响历史图表显示，禁止放宽为任意 URL。

## REQ-QA-MESSAGE-COPY-20260814

- [frontend_dashboard_v3.server.html:L8920](../高炉前端数据/frontend_dashboard_v3.server.html#L8920)：
  统一处理 `.qa-server-msg` 和旧 `.qa-msg`，为用户/助手消息分别注入“复制问题/复制回复”。
- [frontend_dashboard_v3.server.html:L8938](../高炉前端数据/frontend_dashboard_v3.server.html#L8938)：
  从克隆节点提取可见正文，移除时间、按钮和隐藏内容，并附带经既有同源规则归一化的 MCP 图表地址。
- [test_qa_message_copy_ui.py](../tests/test_qa_message_copy_ui.py)：验证双角色、正文边界、图表 URL、
  Clipboard 回退、状态反馈和零 QA API 调用。
- [verify_abc_contextual_assistant_viewports.cjs](../tools/verify_abc_contextual_assistant_viewports.cjs)：
  在 QA 只读夹具中实际点击两种复制按钮，检查剪贴板正文并证明 `real_sent=0`。
- 修改风险：复制器采用 DOM 观察器适配流式更新与历史消息；若消息容器类名变化，必须同步更新选择器和
  浏览器验收。禁止将隐藏 Prompt、上下文快照、时间元数据或任意外部图片 URL 纳入复制内容。

## REQ-QA-LOCAL-RECOMMENDATION-PRESERVATION-20260814

- [QaPromptRecommendations:L9325](../高炉前端数据/frontend_dashboard_v3.server.html#L9325)：
  将原有动态常用问题与固定 MCP 模板作为独立分区渲染，旧问题排在 MCP 模板之前；滚动容器支持
  鼠标/触控滚动和键盘聚焦。
- [QaPromptRecommendationsPersistent:L9331](../高炉前端数据/frontend_dashboard_v3.server.html#L9331)：
  `props.common` 保留原动态推荐，`QA_MCP_RECOMMENDED_PROMPTS` 单独作为 `mcpCommon`，不再合并后
  失去来源和顺序语义。
- [test_original_common_questions_are_preserved_before_mcp_templates](../tests/test_qa_mcp_visual_recommendations.py#L72)：
  验证分区、顺序、可访问滚动合同和禁止恢复旧拼接写法。
- 修改风险：不得把动态问题重新追加到 MCP 数组尾部；新增推荐来源时必须使用独立分区或显式来源字段，
  并保持点击只填入、不自动发送。

## 炉况诊断8类与ABC33数学公式手册（2026-08-14）

| 程序/产物 | 职责 | 追踪编号 |
|---|---|---|
| [generate_furnace_rules_formula_handbook.py](../tools/generate_furnace_rules_formula_handbook.py) | 从旧8类YAML和ABC33服务端目录/审计公式生成41规则Markdown | `REQ-FURNACE-RULE-FORMULA-HANDBOOK-20260814` |
| [export_furnace_rules_handbook_pdf.ps1](../tools/export_furnace_rules_handbook_pdf.ps1) | 在PowerShell 7.6.4中通过Pandoc和Edge无头模式导出PDF | 同上 |
| [verify_furnace_rules_formula_handbook.py](../tools/verify_furnace_rules_formula_handbook.py) | 校验8+33章节、关键公式、PDF页数和中文文本标记 | 同上 |
| [furnace_rules_handbook.css](../tools/furnace_rules_handbook.css) | A4、中文字体、公式块和跨页表格排版 | 同上 |
| [公式手册Markdown](./炉况诊断8类与ABC33规则数学公式手册_20260814.md) / [PDF](./炉况诊断8类与ABC33规则数学公式手册_20260814.pdf) | 用户可阅读与打印的当前审计产物 | 同上 |

修改风险：ABC目录、因子公式或旧YAML变化后必须重新生成并验证；不得手工修改生成文件后不更新生成器。
原8类历史实现缺失期间，禁止把硬门和Resolver语义从推测写成确定事实。

## REQ-QA-ROUTING-ASSISTANT-UPDATE-20260916

| 程序/合同 | 职责 | 修改风险 |
|---|---|---|
| [qa_task_plan.py](../高炉前端数据/智能助手/backend/qa_task_plan.py) | 在知识和工具路由前拆分指令/引文并生成来源、预取和工具域计划 | 新工具必须先归入证据域；未知写工具不得默认归为只读实时域 |
| [qa_evidence_policy.py](../高炉前端数据/智能助手/backend/qa_evidence_policy.py) | 统一普通回答目标，保留数学和数据分析，阻止代码生成/执行 | 不能用任意 Markdown 围栏作为代码判据；混合回答不能整段抹除 |
| [qa_evidence_claims.py](../高炉前端数据/智能助手/backend/qa_evidence_claims.py) | 对象/统计字段数值绑定和显示精度舍入 | 增加别名时要防同值跨对象误认；单位和时间尚未在此模块校验 |
| [build_qa_routing_candidate.py](../tools/build_qa_routing_candidate.py) | 对精确 V2 生产基线应用可审查修改并输出本机 V3 候选 | 基线哈希变化必须停止并重新审查，不能放宽哈希门禁 |
| [evaluate_qa_task_plan_contracts.py](../tools/evaluate_qa_task_plan_contracts.py) | 验证公开模板与合成反例的确定性路由合同 | 不得将线上原始答案、身份、生产数值或 oracle 传给模型 |
| [run_qa_failed_retest_once.py](../tools/run_qa_failed_retest_once.py) | 对人工确认失败题执行逐题 claim、单次生产 SSE 和无重放核算 | 原始回答仅写入 Git 忽略目录；明确或不确定的已发送题均不得自动重发 |

生产已记录为 `70b36c52c2ccddb1fa08429fc0fe6455cfff4ba9`。完整边界、16 题脱敏审阅和
下一轮修复项见 [QA 路由 V3 生产更新与复测](./handoffs/2026-09-16-qa-routing-v3-production-and-retest.md)。

### REQ-QA-FULL-ISSUE-INVENTORY-20260916 / QAOPT-R03

| 程序/合同 | 职责 | 修改风险 |
|---|---|---|
| [qa_entity_resolution.py](../高炉前端数据/智能助手/backend/qa_entity_resolution.py) | 展开共享前缀列表、字母范围和成对对象，返回有序 canonical ID | 只允许显式审查的别名/范围；未知对象不得生成虚构ID |
| [build_qa_routing_v4_candidate.py](../tools/build_qa_routing_v4_candidate.py) | 从已验收V3精确哈希生成V4候选，并将解析结果接入执行器 | 基线不符立即停止；不能顺带重写代理主文件其他逻辑 |
| [build_qa_remediation_execution_ledger.py](../tools/build_qa_remediation_execution_ledger.py) | 校验33项状态覆盖并生成可核对执行台账 | 状态必须来自测试/生产证据，不能把计划标成已解决 |
| [qa_time_window_plan.py](../高炉前端数据/智能助手/backend/qa_time_window_plan.py#L40) | QAOPT-R04固定锚点、两窗及基线工作流与确定性答案 | 基线质量门不能替代炉况报警；不得合并成单窗 |
| [qa_report_workflow.py](../高炉前端数据/智能助手/backend/qa_report_workflow.py#L73) | QAOPT-R05目录→选定→正文→摘要摘录 | 依赖失败停止；目录、历史报表及实时数据分开 |

V4构建器新增准确生产MCP SHA-256绑定与字符截断差分。本机旧代理/MCP不作整文件生产候选，细节见[V4交接](handoffs/2026-09-16-qa-routing-v4-temporal-report-local.md)。
## QA V8/V9 当前验收增量（2026-09-16）

`qa_document_knowledge.execute_document_question/_original_subsection`：核验正式文档、唯一编号/标题范围及完整块分页；`qa_prompt_sources.build_source_messages`：保留允许证据与原prompt目标；`qa_evidence_policy.apply_request_boundary/boundary_result`：混合请求仅代码受限。`tools/build_qa_routing_v9_candidate.py`仅从已接受V8字节构建；发布模板支持V3至V9。符号行号TODO-LINES。见[V8/V9交接](handoffs/2026-09-16-qa-routing-v8-v9-production.md)。

## QA V5 程序索引（2026-09-16，候选）

- `backend/qa_history_projection.py::fetch_owned_history/history_outcome`：已认证owner限定SQL、排除当前消息、历史摘录投影。
- `backend/qa_model_readiness.py::resolve_resident/public_error_fields`：允许驻留模型的有限只读复核、明确依赖阻断。
- `tools/build_qa_routing_v5_candidate.py`：以准确V4生产字节构建七文件差分候选。
- `prepare_qa_routing_v3_release.py`及三个受控发布脚本：兼容V3/V4/V5精确写集，不覆盖共享配置。

以上backend路径相对`高炉前端数据/智能助手`；需求及测试见[V5交接](handoffs/2026-09-16-qa-routing-v5-local-candidate.md)。

## QA V6程序索引（2026-09-16，候选）

- `qa_verified_facts.py::EvidenceItem/prefetch_outcome/temperature_comparison`：对象/时间/来源/单位范围、确定性均值差及质量缺项。
- `qa_completion.py::complete_model_response/public_completion`：JSON/SSE共用一次同请求压缩补答、独立完成状态。
- `qa_history_projection.py::fetch_owned_history`：历史检索生成答案排除和回答角色过滤。
- `mcp_conversation_context.py::update_tool_context`：明确追问继承、主题切换/过期重置、旧数值证据不复用。
- `tools/build_qa_routing_v6_candidate.py`：精确V5生产代理补丁；发布脚本V6为五文件精确写集。上述backend路径相对`高炉前端数据/智能助手/backend`，定位行号TODO-LINES；[权威证据](handoffs/2026-09-16-qa-routing-v5-production-and-v6-candidate.md)。

## V25智能助手更新与首次全题统计（2026-09-17）

状态：V25已部署；首次1233题判定已合并。最新权威方案见 [33项优化与核对方案](handoffs/2026-09-17-qa-full-optimization-plan.md)。

明确钟点/跨午夜窗口不回落最近一小时，历史记录和质量保留；18点绘图已进入正确路由，但生产工具只返回16点且生命周期降级遗漏图，仍待修复。

本机159检查、14黄金题结构、4写24读/490 AST/22标记、8093受控发布和CAS通过。新版822原失败/部分题复测只发1题且失败，821题证明未发。首次完整正确269/可判1091=24.66%，不能报告优化后全量准确率。

## V26图表证据修复及固定模型复测（2026-09-17）

状态：V26已部署，174本机检查和独立审查通过；822原失败/部分题发送前因Qwen身份变化拦截，零发送。线上语义修复效果未确认。
需求：REQ-QA-CHART-COVERAGE-20260917、OPS-QA-FIXED-MODEL-WINDOW-20260917。
最新权威来源：[V26部署与固定模型复测方案](handoffs/2026-09-17-qa-v26-model-window.md)、[33项优化方案](handoffs/2026-09-17-qa-full-optimization-plan.md)、[V26生产哈希](../tests/qa_regression/routing_v26_production_20260917.json)、[822未发题证据](../tests/qa_regression/routing_v26_unattempted_dependencies_20260917.json)。
执行器见 [窗口owner](../tools/run_qa_fixed_model_window.ps1)、[独立启动器](../tools/start_qa_fixed_model_window.ps1)、[只读准备器](../tools/prepare_qa_fixed_model_window.py)；11项真实控制流/截止预算隔离测试通过，另有8项身份/续跑合同回归通过。窗口仅本机准备，计划任务操作尚未授权执行；继续保留V25历史记录，不以非空答复计算正确率。

## 历史：模型恢复稳定性本机候选（2026-09-17，已取代）

需求OPS-QA-MODEL-REPAIR-STABILITY-20260917，关联QAOPT-O01。健康批准驻留优先、候选失败alias/state恢复、最长15分钟冷却、暂停失败恢复责任及Switch实际alias回滚已形成r2本机候选；32其他函数和顶层mutex/dispatch保持，26隔离回归与独立代码审查通过，未部署管理器。
当前生产仍为V26，822失败/部分题均未发送。真实任务/模型验收和管理器变更独立授权仍待完成；本机检查不等同线上语义成功。
权威来源：[候选和26项证据](handoffs/2026-09-17-qa-model-repair-stability.md)、[候选冻结元数据](../tests/qa_regression/model_repair_stability_candidate_20260917.json)、[构建器](../tools/build_qa_model_repair_candidate.ps1)、[聚焦回归](../tests/test_qa_model_repair_policy.py)。

## REQ-QA-SINGLE-BASE-MODEL-20260917：固定同一底座

状态：本机候选52项检查及独立审查通过，未部署；生产仍V26。唯一e4ad74…底座，Switch/替代fallback禁用，每次模型POST与复测plan核验相同digest；旧双批准池窗口已停用。恢复任务仍曾自行漂移版本0，不能声称生产已锁定。管理器/计划任务维护独立授权，安装失败不能再启用旧切换策略。
当前权威：[单底座合同、代码和验收方案](handoffs/2026-09-17-qa-single-base-model-policy.md)、[候选冻结证据](../tests/qa_regression/single_base_model_candidate_20260917.json)。前代r2批准fallback候选仅保留历史复现，禁止部署。

## REQ-QA-STATISTICS-EVIDENCE-20260917：V28统计证据与答复

状态：本机候选，生产仍为V26；最后核对2026-09-17。关联QAOPT-E01/E02/E03/E04/E05。
V28保留固定同一底座身份检查，仅修复统计预取、证据完整性和确定性答复三个函数。完整保留stddev/单位/质量及来源窗口；非零微量不舍入成0；缺单位仅继承现有精确合同并披露，Held端点不证明整窗质量或炉况稳定。直接答复同样校验请求对象、来源和时间窗，未核实不得输出正式STDDEV/CV/趋势。没有新增API或配置，不改模型、生产数据库或ABC33合同。
权威：[实施、回归及未完成项](handoffs/2026-09-17-qa-v28-statistics-evidence.md)、[机器检查证据](../tests/qa_regression/statistical_evidence_candidate_20260917.json)、[实际函数回归](../tests/test_qa_statistics_evidence.py)。本机通过不得写成线上准确率提高；822原失败/部分题尚未发送。

## REQ-QA-FINAL-COMPLETION-20260917：V29最终答复完成状态

状态：本机r2候选、92项聚焦回归及独立审查通过，未部署；最后核对2026-09-17，关联QAOPT-E05/O04/T03。
统一识别模型截断、未知终止、空答案和末行空标题；工具后解释未完成时保留事实并标部分，MCP降级仍最多一次无工具回合。普通免工具问答保留原有一次有界补答；JSON/SSE核对实际最终answer，图表/文档追加不能擦除已记录的空标题。固定底座、V28统计合同及其他AST保留，无新增配置、工具重试或数据库变更。
权威：[实施、实际检查及剩余边界](handoffs/2026-09-17-qa-v29-final-completion.md)、[候选机器证据](../tests/qa_regression/final_completion_candidate_20260917.json)、[真实函数回归](../tests/test_qa_final_completion.py)。处理器接缝为AST与合同检查，尚未执行线上处理器/822原题语义验收；这些问题未销项。

## REQ-QA-WINDOW-QUALITY-20260917：V30质量窗口证据

状态：本机r2候选、独立审查通过，未部署；最后核对2026-09-17，关联QAOPT-E02/E04/E06。
数据库在原统计SELECT同一tag/窗口中追加质量计数，非空数值为分母，空值行单列；原参数、查询次数和数值公式保持。pSpace/派生只声明实际返回样本，不声称整窗完整。质量总和、类型、schema/basis及请求窗口必须匹配，未知标签不猜测为Good，不由Held/Bad或派生标记判正式稳定/风险等级。固定同一底座与V29完成状态保持，没有新配置或数据库迁移。
权威：[实施、质量范围与验收边界](handoffs/2026-09-17-qa-v30-window-quality.md)、[机器证据](../tests/qa_regression/window_quality_candidate_20260917.json)、[实际MCP函数回归](../tests/test_qa_window_quality.py)。本机合同尚未在真实数据库或原822题验证，不标线上有效或销项。


## REQ-QA-RENDERER-CONTRACT-20260917：V31答复格式与字段兼容

状态：本机冻结候选、126项相关回归及独立审查通过，未部署；最后核对2026-09-17，关联QAOPT-E02/E03/E05。
传感器字符串列表按实际工具拆分、去重，保持80个上限，请求与外层结果规范化列表必须一致；顶层字符串和非字符串项不放宽为合法调用。单位仅从明确元数据绑定继承规范合同并披露，原单位优先、不换算或猜描述。异常结果容器逐项明示并保留相邻有效事实；对象、来源、只读策略与窗口门禁保持。仅修改一个代理函数和统计证据模块，无新增API、配置、工具或模型回合，固定同一底座保持。
权威：[确认缺陷、程序与未完成验收](handoffs/2026-09-17-qa-v31-renderer-contract.md)、[机器回归证据](../tests/qa_regression/renderer_contract_candidate_20260917.json)、[实际冻结函数回归](../tests/test_qa_renderer_contract.py)。本机通过不能用于线上准确率或问题销项；禁切换管理器安装、8093部署及822原题复测仍待完成。


## REQ-QA-LATEST-EVIDENCE-20260917：V32最新值与完成合同

状态：本机r2冻结候选、284项相关回归及独立审查通过，未部署；最后核对2026-09-17。
程序：[最新值门禁 qa_statistical_evidence.py:L212](../高炉前端数据/智能助手/backend/qa_statistical_evidence.py#L212)、[逐字段披露:L236](../高炉前端数据/智能助手/backend/qa_statistical_evidence.py#L236)、[直接工具完成合同:L286](../高炉前端数据/智能助手/backend/qa_statistical_evidence.py#L286)、[事实预取 qa_verified_facts.py:L101](../高炉前端数据/智能助手/backend/qa_verified_facts.py#L101)。候选仅修改代理两个及事实三个函数，其他AST与MCP/固定底座/完成/质量模块保留。
权威：[确认缺陷、实现及生产依赖](handoffs/2026-09-17-qa-v32-latest-evidence.md)、[机器证据](../tests/qa_regression/latest_evidence_candidate_20260917.json)、[实际函数回归](../tests/test_qa_latest_evidence.py)、[九条提出归类补充](../tests/qa_regression/unmapped_triage_supplement_20260917.json)。本轮0线上问题，不改首次1233题判定，822原题复测仍待完成。

## 2026-09-17：只读审计及制度源解析

程序：[启动只读连接:L59](../tools/qa_readonly_pg.py#L59)、[SELECT封装:L46](../tools/qa_readonly_pg.py#L46)、[数据库来源诊断:L52](../tools/probe_qa_readonly_pg.py#L52)、[源DOCX元数据审计:L12](../tools/audit_qa_source_docx_readonly.py#L12)、[整行标题识别:L149](../tools/build_three_rules_hierarchical_kb.py#L149)。四个审计入口迁移，manifest输出使用白名单；源解析只改变类别/标题分界，不改条款原文。151项及独立审查通过，生产知识库/代理尚未更新。
权威：[确认缺陷、发布范围与未验证项](handoffs/2026-09-17-qa-readonly-audit-and-source-repair.md)、[机器证据](../tests/qa_regression/readonly_audit_source_repair_20260917.json)。

## REQ-QA-SOURCE-SCOPE-20260917：独立源校验程序

程序：[独立OOXML源范围及item/chunk绑定](../tools/qa_source_scope_contract.py)、[私有keyword候选冻结](../tools/freeze_qa_source_scope_candidate.py)、[精确岗位/规程源解析](../tools/build_three_rules_hierarchical_kb.py)。符号行号TODO-LINES。校验器不调用builder抽取函数；标题政策数据显式共享，非语义oracle。私有文件不能覆盖或公开上传，冻结使用同一BytesIO校验身份与解析。
权威：[实现、实际检查和未完成发布](handoffs/2026-09-17-qa-independent-source-scope.md)、[脱敏证据](../tests/qa_regression/source_scope_candidate_20260917.json)。202项及独立审查通过，生产知识库未变。

## REQ-QA-KEYWORD-SOURCE-RELEASE-20260917：源绑定及发布准备

程序：[固定源绑定、确定性keyword行和准备/DB入口](../高炉前端数据/智能助手/backend/qa_knowledge_source_binding.py)、[私有单文档计划准备器](../tools/prepare_qa_keyword_source_release.py)、[增量归档/绑定表DDL候选](../schema/20260917_qa_keyword_source_release.sql)。符号行号TODO-LINES。纯模块及准备器不连接DB/模型，不发布；已补齐所有实际检索字段及可选解析源元数据检查。
权威：[初次审查缺口、修复和执行器待办](handoffs/2026-09-17-qa-keyword-source-release-preparation.md)、[253项及冻结证据](../tests/qa_regression/keyword_source_release_preparation_20260917.json)。读取器尚未接入，生产未更新。

## REQ-QA-KEYWORD-SOURCE-TRANSACTION-20260917：事务库与只读依赖入口

状态：本机271项及独立静态复审通过，2026-09-17核对；生产未应用。
程序：[调用者新连接事务库](../tools/qa_keyword_source_transaction.py)、[启动只读目录依赖探针](../tools/probe_qa_keyword_source_dependencies_readonly.py)。符号publish、rollback_release、recover_release、_begin、_schema；行号TODO-LINES。库不获取连接或凭据，不执行SSH或模型调用；生产入口尚未实现。
当前权威：[事务、真实依赖与剩余发布门](handoffs/2026-09-17-qa-keyword-source-transaction.md)、[机器证据](../tests/qa_regression/keyword_source_transaction_20260917.json)。上节253项报告是准备阶段历史快照，当前执行器状态以本节为准。

## REQ-QA-SOURCE-RELEASE-ENTRY-20260917：受控执行入口

状态：2026-09-17本机验证，生产未执行。
新增[plan/publish/rollback/recover入口](../tools/qa_keyword_source_release_entry.py)，符号load_contract/_connection/_claim/run/main（TODO-LINES）。实例与配置核验、独占执行记录和恢复委托；不调用pool/schema初始化/模型，不创建DDL表。
当前权威：[封存包、291项及剩余授权/部署门](handoffs/2026-09-17-qa-source-release-entry.md)、[机器证据](../tests/qa_regression/source_release_entry_20260917.json)。上节271项为事务库阶段快照，当前入口状态以本节为准。


## REQ-QA-ORIGINAL-SOURCE-READER-20260917：制度原书读取门禁

状态：2026-09-17本机验证/复审并冻结，生产未接入。

[单语句读取门禁](../高炉前端数据/智能助手/backend/qa_knowledge_reader_source_gate.py)的SNAPSHOT_SQL/projection/verify与[公开执行入口](../高炉前端数据/智能助手/backend/qa_document_knowledge.py:360)使用同一帧；内部选择函数仅在已核快照内组织原文，层级测试不替代公开入口。新gate符号行号TODO-LINES。

当前权威：[读取门禁交接](handoffs/2026-09-17-qa-original-source-reader.md)、[脱敏机器证据](../tests/qa_regression/original_source_reader_20260917.json)。291项入口报告是历史阶段，完整源发布及822原题现场验收尚未完成。


## REQ-QA-FORMAL-DOCUMENT-SCOPE-20260917：书名与全部请求范围

状态：2026-09-17本机378项/复审及V34-r1冻结，生产未应用。

[读取器](../高炉前端数据/智能助手/backend/qa_document_knowledge.py:133)新增_requested_chapters；_regulation_scopes第189行、_chapter_coverage第210行，公开execute_document_question第463行。纯确定性选择不增加SQL/模型；旧V33源门禁及其他9候选文件字节保留。

当前权威：[范围修复交接](handoffs/2026-09-17-qa-document-scope-resolution.md)、[脱敏机器证据](../tests/qa_regression/document_scope_resolution_20260917.json)。V33/356项为前阶段快照；822原题现场验证未完成。


## REQ-QA-DOCUMENT-REGULATION-SCOPE-20260917：条款规程范围与逐项覆盖

状态：2026-09-17本机400项/复审通过，V35-r1冻结，生产未应用。

[作用域字面保护](../高炉前端数据/智能助手/backend/qa_document_knowledge.py:120)、[规程范围](../高炉前端数据/智能助手/backend/qa_document_knowledge.py:207)、[覆盖门](../高炉前端数据/智能助手/backend/qa_document_knowledge.py:258)、[原子选择](../高炉前端数据/智能助手/backend/qa_document_knowledge.py:280)、[公开入口](../高炉前端数据/智能助手/backend/qa_document_knowledge.py:575)。其余9候选文件与V34逐字节相同。

当前权威：[规程范围交接](handoffs/2026-09-17-qa-document-regulation-scope.md)、[脱敏机器证据](../tests/qa_regression/document_regulation_scope_20260917.json)。V34/378项保留为历史阶段；822原题现场复问未完成。


## REQ-QA-FIXED-MODEL-OVERRIDE-20260917：唯一固定底座禁止参数覆盖

状态：2026-09-17本机61项/独立审查通过，V36-r1冻结，生产未应用。

[resolve身份入口](../高炉前端数据/智能助手/backend/qa_fixed_model_identity.py:30)在回调前拒绝非硬编码pin；版本qa-fixed-model-identity-v2。V36继承V35其余9文件，完整源门禁/规程分页代码逐字节相同；代理每轮和fallback仍重新核验。

当前权威：[固定参数门交接](handoffs/2026-09-17-qa-fixed-model-override.md)、[脱敏机器证据](../tests/qa_regression/fixed_model_override_20260917.json)。源/制度前阶段以V35报告保留；822原失败partial题0复问。


## REQ-QA-COMPOUND-SOURCE-SCOPE-20260917：复合子任务与来源禁令

状态：2026-09-17本机557项相关回归及独立审查通过，V37-r2冻结，生产未应用。

[任务计划](../高炉前端数据/智能助手/backend/qa_task_plan.py:404)、[制度入口](../高炉前端数据/智能助手/backend/qa_document_knowledge.py:582)、[制度复合](../高炉前端数据/智能助手/backend/qa_document_compound.py:13)、[历史计划](../高炉前端数据/智能助手/backend/qa_history_compound.py:54)、[历史选择词](../高炉前端数据/智能助手/backend/qa_history_projection.py:16)及[候选生成器](../tools/build_qa_compound_scope_candidate.py:55)为变更入口。冻结代理只改3个谓词，反向恢复后其余AST一致，22项共享功能标记保留。

权威：[逐项交接](handoffs/2026-09-17-qa-compound-source-scope.md)、[脱敏证据](../tests/qa_regression/compound_source_scope_20260917.json)。0生产销项，原题准确率未验证。


## REQ-QA-MATH-FUNCTION-POLICY-20260917：正常数学函数问答

状态：2026-09-17本机225项相关回归/独立审查通过，V38-r2冻结，生产未应用。

[code_requested](../高炉前端数据/智能助手/backend/qa_evidence_policy.py:56)局部区分数学名词；[生成器](../tools/build_qa_math_function_candidate.py:13)只更新policy，冻结15文件中14文件与V37一致；实际代理qa_answer_route未修改。

权威：[逐项交接](handoffs/2026-09-17-qa-math-function-policy.md)、[脱敏机器证据](../tests/qa_regression/math_function_policy_20260917.json)。本轮0助手模型调用/生产写入/原题发送/销项。


## REQ-QA-USER-DATA-SOURCE-SCOPE-20260917：用户给定数据与外部来源范围

状态：2026-09-17本机286项相关回归/独立审查通过，V39-r3冻结，生产未应用。

[user_data_scope](../高炉前端数据/智能助手/backend/qa_task_plan.py:269)与live_query_text限定外部来源；[生成器](../tools/build_qa_user_data_scope_candidate.py:26)对实际冻结代理施加6处可逆接缝，13文件逐字节继承V38；alias、时窗、时钟、分析扩展和实体冻结均使用外部子任务。

权威：[逐项交接](handoffs/2026-09-17-qa-user-data-source-scope.md)、[脱敏机器证据](../tests/qa_regression/user_data_source_scope_20260917.json)。本轮0助手模型调用/生产写入/原题发送/销项。


## REQ-QA-DECLARED-INPUT-SCOPE-20260917：声明输入与现场核验

状态：2026-09-17本机327项相关回归/独立审查通过，V40-r2冻结，生产未应用。

[_declared_input_clause](../高炉前端数据/智能助手/backend/qa_task_plan.py:308)区分声明、字面值、数值核验及时间；[_explicit_live_request](../高炉前端数据/智能助手/backend/qa_task_plan.py:364)保留当前数值问句。冻结[生成器](../tools/build_qa_declared_input_candidate.py:13)仅替换task_plan，15文件中14继承V39。

权威：[逐项交接](handoffs/2026-09-17-qa-declared-input-scope.md)、[脱敏机器证据](../tests/qa_regression/declared_input_scope_20260917.json)。本轮0助手模型调用/生产写入/原题发送/销项；R07重新开放。


## REQ-QA-RESPONSE-STYLE-SOURCE-SCOPE-20260917：回答形式与资料来源

状态：2026-09-17本机395项相关回归/独立审查通过，V41-r1冻结，生产未应用。

[任务计划](../高炉前端数据/智能助手/backend/qa_task_plan.py:404)仅调整VERSION与_DOCUMENT_TERMS；[冻结生成器](../tools/build_qa_response_style_candidate.py)15文件中14继承V40。实际制度入口和代理外层MCP选择均有回归。

权威：[逐项交接](handoffs/2026-09-17-qa-response-style-source-scope.md)、[脱敏机器证据](../tests/qa_regression/response_style_source_scope_20260917.json)。本轮0助手模型调用/生产写入/原题发送/销项。


## REQ-QA-SOURCE-CONCEPT-SCOPE-20260917：来源概念与具体记录

状态：2026-09-17本机436项相关回归/独立审查通过，V42-r1冻结，生产未应用。

[_conceptual_source_clause](../高炉前端数据/智能助手/backend/qa_task_plan.py:249)过滤概念子句；[任务计划](../高炉前端数据/智能助手/backend/qa_task_plan.py:404)保留实际历史/报表子任务。[生成器](../tools/build_qa_source_concept_candidate.py:13)15文件中14继承V41。

权威：[逐项交接](handoffs/2026-09-17-qa-source-concept-scope.md)、[脱敏机器证据](../tests/qa_regression/source_concept_scope_20260917.json)。本轮0助手模型调用/生产写入/原题发送/销项。


## REQ-QA-SOURCE-EXCLUSION-SCOPE-20260917：来源排除与子任务继承

状态：2026-09-17本机498项相关回归、原源保真及独立审查通过，V43-r6冻结，生产未应用。

[来源约束](../高炉前端数据/智能助手/backend/qa_task_plan.py:202)、[具名书目](../高炉前端数据/智能助手/backend/qa_task_plan.py:213)、[继承](../高炉前端数据/智能助手/backend/qa_task_plan.py:231)和[正式入口](../高炉前端数据/智能助手/backend/qa_document_knowledge.py:582)构成读前校验。冻结15文件，4个修改/11个继承V42，代理字节不变。

权威：[逐项交接](handoffs/2026-09-17-qa-source-exclusion-scope.md)、[脱敏机器证据](../tests/qa_regression/source_exclusion_scope_20260917.json)。0助手模型调用/生产写入/原题发送/销项。


## REQ-QA-SUPPLIED-RECORD-SCOPE-20260917：已给记录数据与来源核验

状态：2026-09-17本机546项相关回归、原源保真和独立审查通过，V44-r2冻结，生产未应用。

[_declared_input_clause](../高炉前端数据/智能助手/backend/qa_task_plan.py:308)识别来源核验；[任务计划](../高炉前端数据/智能助手/backend/qa_task_plan.py:404)不从纯声明子句生成外部来源意图。冻结15文件，14个继承V43，代理和所有其他模块不变。

权威：[逐项交接](handoffs/2026-09-17-qa-supplied-record-scope.md)、[脱敏证据](../tests/qa_regression/supplied_record_scope_20260917.json)。0生产助手模型调用/生产写入/原题发送/销项。


## REQ-QA-RUNTIME-PROBE-FIXED-PIN-20260917：固定底座只读验收门

状态：2026-09-17本机33项合同测试及独立审查通过，生产V26固定身份阻断。

[身份判定](../tools/probe_qa_paired_runtime_readonly.py:24)、[路径边界](../tools/probe_qa_paired_runtime_readonly.py:13)、[metadata探测](../tools/probe_qa_paired_runtime_readonly.py:37)只读核验固定摘要；不上传远端源码、不生成或切换模型。

权威：[交接](handoffs/2026-09-17-qa-runtime-fixed-pin.md)、[脱敏证据](../tests/qa_regression/runtime_fixed_pin_20260917.json)。0生产写入/模型调用/原题重发/销项。


## REQ-QA-ACTUAL-PROMPT-BINDING-20260917：实际系统Prompt与缓存凭证

状态：2026-09-17 V45-r2本机回归及独立审查通过，生产未应用。

[实际请求绑定](../高炉前端数据/智能助手/backend/qa_prompt_binding.py:67)、[准备绑定](../高炉前端数据/智能助手/backend/qa_prompt_binding.py:56)、[缓存版本](../高炉前端数据/智能助手/backend/qa_prompt_binding.py:20)由确定性候选构建器注入已审查proxy边界；不重建或覆盖旧单体。

权威：[交接](handoffs/2026-09-17-qa-actual-prompt-binding.md)、[脱敏证据](../tests/qa_regression/actual_prompt_binding_20260917.json)。33项状态不变，0生产写/模型调用/原题发送/销项。


## REQ-QA-FULL-CANDIDATE-RUNTIME-20260917：完整候选原生门

状态：2026-09-17已完成原生加载与合成合同，生产固定身份仍阻断。

tools/qa_full_candidate_probe.py负责RAM源加载、只读I/O边界、执行源哈希及完整合成Handler合同；tools/build_qa_full_candidate_probe.py绑定最新冻结manifest/probe SHA并OEXCL生成私有脚本；tools/verify_qa_full_candidate_probe.py校验完整证据并导出59项传递依赖read_set，不授予部署授权。

权威：[当前交接](handoffs/2026-09-17-qa-full-candidate-runtime.md)、[脱敏机器证据](../tests/qa_regression/full_candidate_runtime_20260917.json)。0真实模型调用/原题POST/生产写/销项。


## V46炉况源执行门（2026-09-17）

build_qa_sensor_context_candidate.py只改冻结prepare；完整探针统计sensor读取、归档次数及证据隔离，校验器拒绝缺证据。

[实施/复现/限制](handoffs/2026-09-17-qa-sensor-context-source-gate.md)；[脱敏证据](../tests/qa_regression/sensor_context_source_gate_20260917.json)。15其他模块与固定底座不变；最新生产ABC33共享代理需要合并保留，身份仍阻断。0销项/原题重发/生产写；历史统计不变。


## V47共享代理发布保护（2026-09-17）

probe_qa_shared_proxy_delta_readonly证明全AST差异仅3函数/1导入；build_qa_shared_proxy_candidate按类作用域保留字面量；完整探针执行前校验2共享依赖pin。

[实施/验证/未验证项](handoffs/2026-09-17-qa-shared-proxy-integration.md)；[脱敏证据](../tests/qa_regression/shared_proxy_integration_20260917.json)。本机集成通过，尚未部署，固定身份阻断及33项原题复测范围保持。
