# 需求追踪

## REQ-ABC33-FURNACE-RULES-20260807

- 需求：将A9、B13、C11共33项炉况规则并行接入现有8类炉况页面，并建立生产安全合同、后台规则合同、B/C分级告警、人工复核详情和可审计存储。
- 规则目录与计算：[abc_rule_catalog.py](../自动诊断服务/abc_rule_catalog.py)、[abc_feature_builder.py](../自动诊断服务/abc_feature_builder.py)、[abc_rule_engine.py](../自动诊断服务/abc_rule_engine.py)。生产页面只接收 `public_rule` 白名单；公式、权重、阈值、归一化值和贡献仅保留在后台详情。
- 配置：[abc_furnace_rules.v1.json](../自动诊断服务/config/abc_furnace_rules.v1.json)，服务端校验33个唯一ID、分数带单调、数值有限和覆盖率/数据年龄门禁。
- 数据库/API：[abc_rule_schema.sql](../自动诊断服务/abc_rule_schema.sql)、[store.py](../自动诊断服务/store.py)、[local_pg_ws_bridge.py](../自动诊断服务/local_pg_ws_bridge.py)、[ollama_proxy_server.py](../高炉前端数据/智能助手/backend/ollama_proxy_server.py)。8768与8093/8094使用同一脱敏 `abc_rule_bundle.v1`；后台 `/api/admin/furnace-rules/evaluations/{evaluation_id}/{rule_id}` 要求管理员会话并返回403给普通账号。
- 页面：[furnace-rule-admin.html](../高炉前端数据/furnace-rule-admin.html) 为受权限保护的后台查看页；生产页面后续只需消费 `/api/furnace-rules/latest`、`detail` 和 `trends`，不在HTML/JS复制规则公式。
- 验证：[test_abc_rule_engine.py](../tests/test_abc_rule_engine.py)，执行 `D:\ProgramData\anaconda3\python.exe -m pytest -q tests/test_abc_rule_engine.py`，当前 `7 passed`。

## OPS-DIAG-RULES-ONE-CLICK-DEPLOY-20260806

- 需求：把8093/8094现行诊断数据模块、异常弹窗、免登录人工评分、单炉况核心变量证据与建议复盘整理为一个快速、可回滚、可审计的一键发布入口，并固定通过本机 `reliable_ssh` 访问220.12。
- 实现：[本机入口](../tools/deploy_diag_rules.py)默认委托[可靠SSH编排器](../tools/deploy_diag_rules_rssh.py)，把9个白名单业务文件和远端安装器压成单包；[可靠传输](../tools/reliable_ssh_22012_cli.mjs)使用固定目标、固定主机指纹、密码文件和审计日志，每次进程只校验一次身份；[远端安装器](../tools/remote_deploy_diag_rules.ps1)在220.12当前代理版本上合并诊断代码，避免覆盖已完成的MCP升级。
- 安全边界：只重启 `BFV4PreviewProxy8093` 与 `V3AutoPreviewProxy8094`；保护8768、8770、11434 PID；部署前备份、失败自动回滚。该快速包不更新诊断计算调度器或8768规则引擎进程。
- 正式结果：9个白名单业务文件以远端当前代理为基线合并并原子安装；8093守卫已暂停并恢复，8094只重启自身计划任务；两页HTTP均为200、页面资产版本和 `bootWhenBodyReady` 标记均通过，评分上下文 `enabled=true`、`can_submit=true`、`login_required=false`。8093/8094按本次发布更换自身页面服务PID，8768、8770、11434 PID保持不变；备份位于远端 `F:\高炉炼铁项目-real-sensor-v2_V4_8093_PREVIEW\logs\deploy_backups\diag_rules_20260806-2300-4b75678a08`。

## REQ-RECOMMENDATION-FULL-AUDIT-20260806

- 需求：8093/8094建议引擎输出必须完整、逐条、全字段写入220.12实际PostgreSQL，并可按诊断、炉况、状态、动作和策略版本审计。
- 数据合同：一个诊断快照和一版引擎/策略对应一个不可变批次；批次保存完整 `recommendation_bundle`，动作表逐行保存原文章节、完整触发证据、前置、阻断、幅度、顺序、缺数、观察窗口、审批及完整原始JSON。四种状态全部保留。
- 幂等与一致性：幂等键绑定炉号、诊断快照、引擎版本和策略SHA-256；重复刷新返回首次提交批次。审计写入失败时不向页面返回未审计建议。
- 安全：所有记录固定只读；运行账号只允许新表 `SELECT/INSERT`，禁止 `UPDATE/DELETE`，不得把建议入库解释为控制下发。
- 程序：[审计写入器](../自动诊断服务/recommendation_audit_store.py)、[DDL](../自动诊断服务/recommendation_audit_schema.sql)、[迁移器](../tools/migrate_recommendation_audit.py)、[8768接入](../自动诊断服务/local_pg_ws_bridge.py)、[验收器](../tools/verify_recommendation_audit_runtime.py)。
- 验证与部署状态：本地新增7项合同及相关26项回归通过；220.12首次上传前被SSLVPN系统路由缺失阻断，尚未发生远端修改。完整记录见[专项交接](handoffs/2026-08-06-recommendation-full-audit-persistence.md)。

## REQ-8093-8094-DIAGNOSIS-REVIEW-AI-20260806

- 需求：实验配置完成后，在220.12的8093、8094同时提供数据模块、异常弹窗/八卡手动评分、所选炉况公式特征解释，以及结合调剂引擎1和知识库的建议复盘；评分不要求高炉长登录。
- 模型口径：升级为 `diagnosis_ai_analysis.v3` / `diagnosis-single-condition-five-minute.v3`。浏览器每次只提交一个白名单炉况键，服务端只为该炉况进行一次模型调用；不再用一次调用生成八类文案。
- 数据与安全：诊断快照、八类系统分、规则变量、近5分钟变化、60分钟统计、30天基线、建议和知识证据均由服务端重读。人工评分追加写入事件表，不覆盖系统分；模型分析只读，不修改诊断、安全门禁或生产控制。
- 根因修复：8093曾出现共享代理已升级而 `diagnosis_model_review.py`、`diagnosis_ai_analysis_api.py` 仍为旧版的模块版本错位，接口长期停在准备态；8094则未设置复核和分析开关。2026-08-06已同步模块并分别受控重启对应代理。
- 部署结果：8093备份 `logs/deploy_backups/diagnosis_ai_analysis_20260806_072403`；8094备份 `logs/deploy_backups/8094_diagnosis_ai_20260806_073217`。8094仅更换自身PID，8093/8768/8770/11434 PID均未变化；两端均确认页面注入、免登录提交、分析完成、变量/建议/知识依据齐全。
- 程序：[证据编排](../高炉前端数据/智能助手/backend/diag_ai_evidence.py)、[单炉况模型合同](../高炉前端数据/智能助手/backend/diagnosis_model_review.py)、[分析API](../高炉前端数据/智能助手/backend/diagnosis_ai_analysis_api.py)、[代理调度](../高炉前端数据/智能助手/backend/ollama_proxy_server.py)、[评分弹窗](../高炉前端数据/assets/bf-diagnosis-manual-score-local.js)、[8094受控启用](../tools/remote_guarded_enable_8094_diagnosis_ai.ps1)。
- 验证：相关Python回归 `46 passed`；新增8094部署合同所在测试文件 `12 passed`。远端部署阻断检查确认两端分析schema为v3，8094分析含可信变量、建议与知识依据，空模型复核/评分请求均按合同返回400。

## REQ-8093-DIAGNOSIS-AI-EVIDENCE-GUIDANCE-20260805

- 用户场景：高炉长点击8093诊断页任一炉况后，不只看到模型结论，还能用现场口语理解“为什么是这个分数”，并直接核对对应变量、变化方向、规则门槛、调剂建议依据和知识来源。
- 服务端输入：只读 `diagnosis_snapshots.feature_snapshot`、最近60分钟 `one_minute_values`、30天 `daily_baselines`；系统计算当前值、近5分钟均值、前5分钟均值、变化量/变化率、60分钟范围和基线偏离。浏览器不能上传这些证据。
- 规则解释：八类炉况分别使用受控规则驱动项、阈值和权重；输出“支持/未触发/数据不足”的变量卡。解释只说明既有规则分的依据，不重新计算或覆盖规则分。
- 建议与知识：只读复用调剂引擎1（当前 `v5-three-rules-two-systems`）的动作、触发证据、前置/阻断、幅度、观察窗口、审批和制度章节；同时复用知识库检索，展示可追溯资料片段和来源。
- 防编造：模型只能引用服务端预先分配的 `driver_id/action_id/chunk_id`；返回未知ID时整批结果判为合同错误。最终变量、建议和知识卡由服务端可信上下文附加，不采用模型自报数值。
- 输出：口语化分数解释、详细变量依据、带数据的只读建议、知识库依据、指导意见和现场确认边界；原人工评分/建议、关闭不保存及系统分保留逻辑不变。
- 程序：[证据编排](../高炉前端数据/智能助手/backend/diag_ai_evidence.py)、[模型合同](../高炉前端数据/智能助手/backend/diagnosis_model_review.py)、[数据读取与调度](../高炉前端数据/智能助手/backend/ollama_proxy_server.py)、[数据查询](../高炉前端数据/智能助手/backend/diagnosis_review.py)、[弹窗](../高炉前端数据/assets/bf-diagnosis-manual-score-local.js)。
- 存储/API：不新增表或字段；继续使用 `diagnosis_ai_analysis_snapshots.canonical_context/analyses` JSONB 和既有GET/重试API，Prompt/Schema升级为v2。
- 验证：40项Python合同通过；Chromium规定九视口和应用内真实点击通过。当前v2 Firefox/WebKit因本机浏览器运行时下载网络不通尚未重跑，不沿用v1结果冒充本次通过。
- 边界：只读诊断源、调剂引擎和知识库，不连接生产控制；2026-08-06起功能范围包含8093与8094，各端口独立受控重启并保护8768/8770/11434。

## REQ-8093-DIAGNOSIS-AI-FIVE-MINUTE-ANALYSIS-20260805

- 用户场景：高炉长在8093诊断页点击八类炉况中的任意一类，立即查看智能助手对当前5分钟点的该炉况分析，并可继续填写原有人工评分或建议。
- 输入：服务端只读获取 `bf_sensor.diagnosis_snapshots` 最新快照、八类规则分、证据、数据覆盖和最近12个诊断点；浏览器只传所选炉况键。
- 处理：后台每30秒检查主诊断的新5分钟桶；主诊断或用户所选炉况按“一个炉况一次模型调用”生成结构化分析，失败后至少冷却120秒再重试。
- 输出：规则符合度、模型证据吻合度、判断状态、摘要、支持/矛盾证据、下一窗口关注和数据限制；模型分不是概率，不改写规则诊断、人工评分或安全门禁。

## BUG-8093-DIAGNOSIS-AI-FALSE-DATA-LIMITS-20260808

### 问题

8093 智能分析把 `L_north`、`L_south` 和部分 `T_top_A-D` 的稀疏分钟采样误显示为数据覆盖不足。220.12 `bf_sensor.sensor_registry` 中这些变量均已启用，且当前诊断窗口存在有效样本。

### 修复定位

- 服务端事实判定：[build_truthful_data_limits()](../高炉前端数据/智能助手/backend/diag_ai_evidence.py#L422-L500)
- 模型上下文脱敏和版本：[diagnosis_model_review.py](../高炉前端数据/智能助手/backend/diagnosis_model_review.py#L29-L40)
- 完成态替换模型自由数据限制：[diagnosis_model_review.py](../高炉前端数据/智能助手/backend/diagnosis_model_review.py#L892-L972)
- 220.12 只读核验：[remote_probe_22012_diagnosis_data_coverage.ps1](../tools/remote_probe_22012_diagnosis_data_coverage.ps1)

### 规则

只要变量拥有当前值或 60 分钟趋势序列，就不属于 `data_limits`。采样密度仍可保留在内部数据质量字段中，但不能直接转化为用户可见的“数据限制”。

### 验证

`tests/test_diagnosis_ai_analysis.py` 共 16 项通过；专项交接记录见 [2026-08-08-8093-ai-data-limit-fix.md](handoffs/2026-08-08-8093-ai-data-limit-fix.md)。远端还同步了 [bf_knowledge_rag.py](../高炉前端数据/智能助手/backend/bf_knowledge_rag.py) 以修复 `source_doc_ids` 接口不匹配；8093 实测返回 `completed`、`data_limits=[]`、`core_variable_count=19`。
- 程序：[批量分析合同](../高炉前端数据/智能助手/backend/diagnosis_model_review.py)、[调度与路由](../高炉前端数据/智能助手/backend/ollama_proxy_server.py)、[HTTP处理器](../高炉前端数据/智能助手/backend/diagnosis_ai_analysis_api.py)、[派生表](../高炉前端数据/智能助手/backend/diagnosis_review.py)、[组合弹窗](../高炉前端数据/assets/bf-diagnosis-manual-score-local.js)。
- API/表：`GET /api/diagnosis-ai-analysis`、`POST /api/diagnosis-ai-analysis/retry`；`bf_assistant.diagnosis_ai_analysis_snapshots`。
- 配置：`BF_DIAGNOSIS_AI_ANALYSIS_*`；数据库复用既有回环 `BF_DIAG_REVIEW_PG*`，不新增密钥。
- 边界：该段记录2026-08-05的8093初始部署；2026-08-06双端口现行状态以 `REQ-8093-8094-DIAGNOSIS-REVIEW-AI-20260806` 为准。
- 验证：37项Python合同通过；Chromium九视口，Firefox/WebKit各四代表视口通过。部署和运行说明见[专项文档](8093_每5分钟八炉况智能分析_20260805.md)。
- 生产状态：2026-08-05已部署，最终备份 `logs/deploy_backups/diagnosis_ai_analysis_20260805_212403`；8093 HTTP与AI API为200、当前5分钟批次完成，8768不变，人工评分表未写入验收数据。诊断资产版本为 `20260805-ai5m-r1`。

## REQ-8093-KNOWLEDGE-KEYWORD-MODE-20260805

- 需求：把 8093 显式设置为关键词模式，让知识库做关键词和词法检索；继续加载既有公共 Prompt 和知识库回答链路，不恢复 Ollama 双模型驻留。
- 实现：[配置补丁器](../tools/patch_8093_keyword_knowledge_mode.py)只允许把 8093 空值/`hybrid` 幂等改为 `keyword`；[受控部署器](../tools/remote_guarded_deploy_8093_keyword_knowledge_mode.ps1)只停止/启动 8093，失败回滚并验证实际进程环境、默认知识搜索、守卫/PID/哈希隔离和单 27B 驻留；[知识 SSE 包装器](../tools/remote_verify_8093_keyword_knowledge_sse_once.ps1)只允许一个真实 POST。
- 配置：8093 与 8094 现均显式为 `BF_QA_KNOWLEDGE_SEARCH_MODE=keyword`；`BF_QA_KNOWLEDGE_ENABLED`、意图门控和 `top_k=6` 延用默认，`OLLAMA_MAX_LOADED_MODELS=1` 不变。keyword 使用 PostgreSQL `bf_assistant.rag_*` 词法候选并把证据注入动态 Prompt，不调用 embedding。
- 部署：`2026-08-05 07:25:21` 完成；8093 配置 SHA-256 `8A24C83DF93008DD8E358682558E8755442D87052A09FB24F39778F2EAF51FDE`，备份 `logs/deploy_backups/8093_knowledge_keyword_20260805_072445`。只更换 8093 PID；8768/8094/8770/11434、页面、共享后端/RAG、守卫和 11434 配置未变化。
- 验证：实际进程和默认知识搜索均为 keyword，默认检索命中 2 条证据。08:44 唯一一次知识问答准备态显示知识检索启用、意图 `parameter_optimization`、MCP 工具关闭，完整收到 SSE，总耗时 `23.8856s`；无守卫重启或隔离项变化。报告在 `logs/acceptance/8093_keyword_knowledge_20260805_20260805_084403/assistant_keyword_knowledge_sse_once.json`；本地相关合同 `16 passed`。
- 长期记录：[Prompt/RAG 专项文档](8093_8094_Prompt固定KV前缀与知识库回答链路_20260805.md)、[配置参考](config_reference.md)、[交接](handoffs/2026-08-05-8093-keyword-knowledge-mode.md)、[DOCX 修复手册](8093智能助手不可用原因与正式修复手册_20260804.docx)和 [AGENTS 固定流程](../AGENTS.md#8093-智能助手再次不可用时的直接修复记录长期固定)。

## REQ-8093-DIAGNOSIS-REVIEW-NO-LOGIN-PRODUCTION-20260804

- 需求：把本机已验收的异常弹窗、三态复核、可选人工分/建议和八卡手动评分部署到220.12:8093，并取消评分前必须登录高炉长账号的限制。
- 实现：[复核后端](../高炉前端数据/智能助手/backend/diagnosis_review.py)增加可配置现场身份与密码环境变量间接引用；[8093代理](../高炉前端数据/智能助手/backend/ollama_proxy_server.py)只对两个POST评分接口启用免登录身份；[异常弹窗](../高炉前端数据/assets/bf-diagnosis-review-local.js)和[手动评分](../高炉前端数据/assets/bf-diagnosis-manual-score-local.js)改用 `auth.can_submit`，不再把表单绑定到 `authenticated`。
- 数据：220.12回环PostgreSQL `bf_trend` 新建 `bf_assistant.diagnosis_review_events`、`diagnosis_manual_score_events`；匿名提交固定记录 `onsite_8093/现场高炉长/onsite_anonymous`，系统快照和八类分由服务端重读。
- 权限：POST复核/评分免登录；历史GET、其他登录和后台接口继续受保护；生产测试场景关闭，浏览器不能自报身份或覆盖系统分。
- 部署：[守卫脚本](../tools/remote_guarded_deploy_8093_diagnosis_review.ps1)已完成停—改—启，`guard_paused/guard_restored=true`、未回滚；8768与8094 PID、8094页面哈希均未改变。备份为 `logs/deploy_backups/diagnosis_review_20260804_202017`。
- 验证：22项测试通过；远端API、表结构和无伪造记录检查通过；真实8093手动评分免登录、关闭不保存及9视口检查通过。当前真实主诊断正常，未篡改生产数据制造异常弹窗；Firefox/WebKit/现场Edge未新增证据。详见[部署说明](8093_异常炉况评分免登录部署_20260804.md)。

## REQ-8096-DIAGNOSIS-MANUAL-SCORE-AND-SUGGESTION-20260804

- 需求：异常复核弹窗允许高炉长可选填写0～100人工匹配分和建议；没有自动弹窗时，也能点击炉况诊断页任一炉况卡进行人工评分/建议。关闭不保存，系统八类分不得被覆盖。
- 实现：[人工评分后端与事件表](../高炉前端数据/智能助手/backend/diagnosis_review.py)、[手动评分模块](../高炉前端数据/assets/bf-diagnosis-manual-score-local.js)、[手动评分样式](../高炉前端数据/assets/bf-diagnosis-manual-score-local.css)、[异常弹窗增量字段](../高炉前端数据/assets/bf-diagnosis-review-local.js)、[API入口](../高炉前端数据/智能助手/backend/ollama_proxy_server.py)。
- 数据：`bf_assistant.diagnosis_manual_score_events` 追加保存目标炉况、服务端八类系统分、人工分、建议、诊断时间、登录身份和来源；异常弹窗的人工分/建议保存在 `diagnosis_review_events` 新字段。仅允许显式回环PostgreSQL。
- 查询：[炉况数据仪表盘](../db_dashboard/index.html)新增“高炉长评分”页签，[查询接口](../db_dashboard/server.py)并列投影系统分与人工分，支持JSON/CSV/XLSX；真实诊断和 `local_fixture` 必须显式分源查询。
- 验证：18项专项/契约测试通过；本机PostgreSQL实写两类 `local_fixture` 事件成功；正常不弹窗、八卡手动评分、异常弹窗评分、关闭不写库和仪表盘查询/导出均通过。Chromium异常弹窗9视口、手动窗口4视口无横向溢出且可滚动。Firefox/WebKit矩阵因Python Playwright依赖下载被网络代理中断，未宣称通过。
- 边界：只完成本机8096/8769原型；没有修改、重启或部署220.12的8093、8094、8768或数据库服务。

## REQ-8093-DIAGNOSIS-REVIEW-LOCAL-PROTOTYPE-20260803

- 需求：在隔离的本机8096/8769原型中，对非“正常顺行”的主诊断居中告警，并允许高组长查看规则符合度、其余七类分数并进行三态人工复核。
- 实现：[后端边界](../高炉前端数据/智能助手/backend/diagnosis_review.py)、[独立交互模块](../高炉前端数据/assets/bf-diagnosis-review-local.js)、[样式](../高炉前端数据/assets/bf-diagnosis-review-local.css)、[测试场景](../高炉前端数据/diagnosis_review_local_test.html)、[启动器](../tools/start_diagnosis_review_preview.py)。
- 数据边界：220.12只读；复核事件只写显式指定的回环PostgreSQL；现有主HTML不硬编码原型资源。
- 验证：[专项测试](../tests/test_diagnosis_review_api.py)、[契约测试](../tests/test_diagnosis_review_contract.py)、[浏览器矩阵](../tools/verify_diagnosis_review_local.py)。
- 状态：本地代码及18项模块/契约测试通过；本机PostgreSQL写入、异常弹窗、关闭逻辑、九视口Chromium检查和仪表盘查询/导出均已完成。Firefox/WebKit自动矩阵仍受本机依赖下载网络问题限制。详见[专项说明](8093_异常炉况诊断人工复核本地原型_20260804.md)。

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

- 需求：排除 8093 页面底部空白带的直接原因，先把最小修复更新到 8094；经用户后续授权，再真实重启 8094、把同一修复受控更新到 8093，并把长期运维规则写入 `AGENTS.md`。全程不得越界停止 8768/8770 或改动共享运行时。
- 根因：除 `ops-cad-ghost-bands-fix` 的 `bottom:5%/6%` 外，旧 `.overview-grid>.panel:last-of-type .panel-body` 在当前三列布局误命中炉况总览，增加 `46px/66px` 底部 padding；用户截图中的大空带主要来自后者，不是 GLB 缺面。
- 实现：[共用补丁器](../tools/patch_8094_cad_bottom_band.py)、[8094-only 初次部署器](../tools/remote_deploy_8094_cad_bottom_band.ps1)、[8094 重启入口](../tools/restart_22012_8094_preview.ps1)、[8093 守卫部署器](../tools/remote_guarded_deploy_8093_cad_bottom_band.ps1)、[只读状态探针](../tools/remote_probe_8093_8094_cad_panel_body_gap.ps1)、[8094 合同测试](../tests/test_8094_cad_bottom_band_fix.py)和[8093 合同测试](../tests/test_8093_cad_bottom_band_fix.py)。R2 标记为 `BUG-BF3D-CAD-PANEL-BODY-GAP-20260804-R2`。
- 验证：本地 `7 tests / OK`；8094 HTTP 200；8093 `guard_paused=true`、`guard_restored=true`、HTTP 200，闭环内 8094/8768/8770 PID 和保护哈希不变。Chrome 两页 `1552×816` 的实际 canvas 到 panel-body 底差均为 `0.606px`，`padding-bottom=0px`、横向溢出为 0。旧 stage/viewer `1552×765` 验收因量错边界已作废。
- 记录：[专项交接说明](handoffs/2026-08-04-8094-cad-bottom-band-fix.md)。

## REQ-THREE-RULES-RECOMMENDATION-ALIGNMENT-20260804

- 需求：把《冀钢炼铁三规二制》保真转换为可审阅 Markdown，并按高炉工长
  `5.1.8` 与 `5.3` 的上部、下部、负荷、碱度四类调剂逐条审计现有建议引擎，
  形成完全一致的只读升级方案。
- 原文与校验：[完整 Markdown](冀钢炼铁三规二制.md)、
  [文字一致性报告](../logs/three_rules_markdown_validation.json)、
  [转换工具](../tools/convert_docx_to_markdown_verified.py)。
- 升级前结论：八类静态模板仅部分覆盖四类调剂；热制度上下行动作顺序与
  `5.1.8.4-5` 不一致，碱度调剂为零覆盖，动作缺来源、条件、幅度、阻断、
  缺失数据和审批字段。
- 目标设计：[逐条升级分析](三规二制四类炉况调剂与建议引擎完全一致升级分析_20260804.md)。
- 本地实现：[策略目录](../调控结论生成引擎/policy/three_rules_two_systems.yaml)、
  [动作合同](../调控结论生成引擎/recommendation/action_contract.py)、
  [策略评估](../调控结论生成引擎/recommendation/policy_evaluator.py)、
  [顺序规划](../调控结论生成引擎/recommendation/sequence_planner.py)、
  [冲突解析](../调控结论生成引擎/recommendation/conflict_resolver.py)、
  [v5适配器](../自动诊断服务/recommendation_adapter.py)。
- 输出合同：`engine_meta.version=v5-three-rules-two-systems`、
  `schema_version=three_rules_two_systems.v1`；每条动作固定返回四态与原文章节、
  证据、前置、阻断、幅度、顺序、缺失数据、观察窗口、审批和只读标记。
- 验证：[v5合同测试](../tests/test_three_rules_recommendation_engine.py) `11 tests / OK`；
  旧综合验证器的3项后端引擎/8767子合同通过，历史前端结构断言因当前页面组件已
  改版仍需单独更新，不能算作引擎失败。
- 边界：本地引擎已升级，但没有部署/重启远端8768/8093，也没有完成完整详情前端、
  浏览器矩阵或现场工艺签字；接入生产前仍须影子回放和受控部署。

## REQ-8093-CORE-PSPACE-REALTIME-20260804

- 需求：核心指标当前值使用服务端 pSpace 秒级流；火花线、趋势、诊断和基线继续使用 PostgreSQL 分钟数据；每项显示数据时间、年龄、质量，断流时明确降级；不完整 trend 历史不得覆盖 8768 完整数组。
- 实现：[8093 页面](../高炉前端数据/frontend_dashboard_v3.server.html)、[秒级运行时](../高炉前端数据/assets/bf-core-metrics-pspace-live-8093.js)、[页面补丁器](../tools/patch_8093_core_metrics_pspace_live.py)、[守卫部署器](../tools/remote_guarded_deploy_8093_core_metrics_pspace_live.ps1)。
- 验收：28/28 实时值、时间和质量元数据可见；传输停帧阈值 12 秒；主动断流时 28/28 获得 8768 分钟值及时间戳并显示“已降级为分钟镜像”；6 项合同测试及 Chrome/Firefox/WebKit/Edge 生产浏览器矩阵通过。
- 证据与回滚：[专项记录](8093_核心指标pSpace秒级实时与分钟镜像降级_20260804.md)。

## REQ-8093-MULTI-MCP-HOST-20260805

- 需求：8093 应按问题挂载 GL02 或 MES/IMES MCP，支持单源与跨源查询；“当前炉次 + 上一炉 Si 平均值”必须一次业务调用完成，不再返回查询轮数超过上限。
- 服务合同：[server_registry.json](../高炉前端数据/智能助手/backend/mcp_host/server_registry.json)、[注册表校验](../高炉前端数据/智能助手/backend/mcp_host/server_registry.py)、[领域路由](../高炉前端数据/智能助手/backend/mcp_host/domain_router.py)、[Client Manager](../高炉前端数据/智能助手/backend/mcp_host/client_manager.py)。
- 问答接入：[ollama_proxy_server.py](../高炉前端数据/智能助手/backend/ollama_proxy_server.py)；高频 MES 工具：[imes_relay_mcp_server.py](../高炉前端数据/智能助手/mcp/imes_relay_mcp_server.py)。
- 权限：生产 Host 不暴露 `query_imes_readonly_sql`；所有新工具只读；缺失 Si 返回 `NO_SI_SAMPLES` 和 `null`，不得写成 0。
- 验证：相关单元与回归 `38 passed`；真实 SDK `tools/list` 为 IMES 14、GL02 18、跨源 32 个 Host 可见工具。
- 状态：P0 本地代码、配置、测试和文档已完成；2026-08-05 已受控部署 220.12 的 8093，并用真实 MES 单次 SSE 验收通过。上一炉有效 Si 试样数为 0，返回 `NO_SI_SAMPLES`。
- 决策：[ADR-0001](adr/0001-8093-multi-mcp-host.md)；复核与实施记录：[专项文档](8093_MCP按需服务发现与MES多服务编排复核_20260805.md)。

## REQ-IMES-LOCAL-MULTI-MCP-RELAY-20260805

- 需求：把 8093 已有的 GL02 与 IMES MCP 能力加载到本机项目，并增加 IMES Web
  白名单查询，使 Web 与 Vastbase 两类数据都能从同一 MCP Host 按需访问；同时修复
  本机 GUI 只转发 Web、未转发 Vastbase 的问题。
- 本地实现：[server_registry.json](../高炉前端数据/智能助手/backend/mcp_host/server_registry.json)
  注册 `gl02-data`、`imes-readonly`、`imes-web-readonly` 三个 stdio 服务；Host 可见
  工具为 `18 + 14 + 3 = 35`。Web 服务见
  [imes_web_mcp_server.py](../高炉前端数据/智能助手/mcp/imes_web_mcp_server.py)，只允许
  已审计的 IMES Web 数据集，不开放任意 URL/SQL/写入。
- 转发实现：[start_imes_web_vastbase_relay_local.cmd](../tools/start_imes_web_vastbase_relay_local.cmd)
  与 [imes_web_launcher.py](../tools/imes_web_launcher.py) 统一使用 `--profile imes`，
  建立 `127.0.0.1:15433 -> 10.10.181.195:5432` 和
  `127.0.0.1:18080 -> 10.10.181.209:8080`，GUI 在报运行中前同时检查 TCP/HTTP。
- 网络边界：SSLVPN 不等价于已获准直连；当前可靠合同仍是经 220.12 跳板。MCP 不可达
  时不得静默切换生产直连；Web 验证码/会话 Cookie 需由受控进程注入，缺失时返回
  `IMES_WEB_CAPTCHA_REQUIRED`。
- 验证：`tools/test_mcp_multi_server_discovery.py --all`、三服务 stdio `tools/list`、
  Web/GUI/Host 契约测试和 relay 单元测试；本轮仅修改本机代码与文档，未部署/重启 8093。

## REQ-8093-ASSISTANT-AUTO-RECOVERY-20260805

- 需求：建立统一的一键智能助手诊断—修复—验收入口，在 1–2 分钟内输出服务、端口、实际进程环境、守卫日志、默认知识检索、模型驻留和最近问答异常并完成分类；任何远端操作前检查 VPN/私网、SSH、PostgreSQL、8093、11434。
- 流水线：`连通性 -> 只读取证 -> 自动分类 -> 条件备份 -> 最小部署 -> 进程复核 -> 默认知识搜索 -> 唯一一次 SSE -> JSON 报告`；服务阶段与 DOCX/追踪文档阶段分离。
- 实现：[Python 编排器](../tools/assistant_8093_auto_recovery.py)、[远端合并诊断](../tools/remote_8093_assistant_diagnose.ps1)、[keyword 部署器](../tools/remote_guarded_deploy_8093_keyword_knowledge_mode.ps1)、[守卫部署器](../tools/remote_guarded_deploy_8093_health_guard.ps1)、[单次 SSE 包装器](../tools/remote_verify_8093_keyword_knowledge_sse_once.ps1)。
- 安全边界：远端不可变包先 SHA-256 校验再以短 `powershell.exe ... -File` 执行；未知哈希拒绝覆盖；`recover` 最多一个真实 SSE POST且不重试；健康状态不备份、不重启、不部署。
- 配置决策：8093/8094 固定 `keyword`，共享 11434 固定单 27.8B；已知 `hybrid + 单模型驻留` 漂移直接进入 keyword 部署器，需要向量检索时必须使用独立 embedding 运行时。
- 验收：本地组合 `22 passed`，包含真实 PowerShell 5.1 数字键 JSON 序列化；远端包 `20260805_v1_22e4eb675eee` 校验通过；诊断约 67 秒分类 healthy；完整服务阶段 `184.618s`，前后 healthy、无部署，唯一 SSE `22185.9ms`、keyword 证据 2 条、所有保护检查通过。
- 证据：[专项文档](8093智能助手自动诊断修复验收工具_20260805.md)、[源报告](../logs/assistant_8093_auto_recovery/20260805_110327_recover.json)、[CLI](cli_usage.md)和[DOCX](8093智能助手不可用原因与正式修复手册_20260804.docx)。

## REQ-8093-SYSTEM-CLOCK-AND-5S-DATA-20260805

- 需求：8093 顶栏“时间”必须显示终端真实系统时钟，不能继续冒用 8768 分钟数据时间；同时核清 pSpace 到 220.12 的读取、落库和展示周期，给出可长期运行的 5 秒实时与分钟保存方案。
- 已实现：[8093 页面](../高炉前端数据/frontend_dashboard_v3.server.html)使用每秒更新的 `systemTime`；原 `currentTime` 改为独立的“分钟数据”时间。[页面补丁器](../tools/patch_8093_core_metrics_pspace_live.py)和[守卫部署器](../tools/remote_guarded_deploy_8093_core_metrics_pspace_live.ps1)固定标记 `REQ-8093-HEADER-SYSTEM-CLOCK-20260805`。
- 核查结论：8093 当前值走 `243 pSpace -> 8770 RealReadList -> 浏览器`，不经过 PostgreSQL；历史链路是 pSpace 原始/处理历史经过 30 秒同步循环写入 `one_minute_values`，再由 8768 提供给火花线、趋势、诊断和基线。30 秒不是“半小时”，也不是当前值刷新周期。
- 存储语义（核查时状态）：长期表一点一分钟、保留3年；当时增量仍为`PS_RAW_SAMPLE`且raw短期任务已停。该发现随后由`REQ-PSPACE-MINUTE-CANONICAL-AVERAGE-20260805`修复，现行状态见后续需求章节。
- 5 秒边界：8770 当前已按 1 秒轮询，页面传输年龄约 1 秒；现场顶压点源时间仍约 33–40 秒成批更新。因此 5 秒目标必须先把 243 侧 SIO/OPC/pSpace 点位发布周期降到不超过 5 秒，再启用独立 5 秒短期原始表并从完整分钟窗口聚合长期分钟表。仅把 30 秒落库循环改成 5 秒不能改善页面当前值。
- 状态：系统时钟已于 2026-08-05 受控部署；5 秒采集/存储改造本轮只完成只读核查和目标设计，未擅自修改 243 采集配置、220.12 同步计划任务或生产表聚合语义。

## REQ-IMES-HEAT-ACCOUNT-AND-CONTEXT-20260805

- 需求：修复“IMES Web 已显示 065 化验、MCP 却查询不到”和“当前/上一炉返回历史炉次”的账号与查询合同，确保按正式 `meltno` 能准确取得化验结果。
- 证据：[用户页面核查与远端只读复核](question_traceability.md#q-imes-heat-lab-65-vs-mcp-20260805)证明 `operations/gl2#dmx` 已能读取 `2#20260805-065` 的 3 条样本，Si 为 `0.20、0.25、0.24`，均值 `0.23%`；此前把该账号判为错误账号是不准确的。
- 根因：旧 `_query_recent_heat_context_rows` 先按 `closetime IS NULL` 排序，历史 `2#20240805-056` 因未关口字段为空而抢到当前位置；复合查询随即查询错误的上一炉号。
- 实现：[imes_relay_mcp_server.py](../高炉前端数据/智能助手/mcp/imes_relay_mcp_server.py) 的 `database_profiles` 允许本机受控 `IMES_DB_*` 统一覆盖两个历史账号，化验专用 profile 默认固定为已验证的 `operations`；当前/上一炉按 `COALESCE(opentime, workdate) DESC, meltno DESC` 选取，并以 `IMES_ACTIVE_HEAT_MAX_AGE_HOURS=72` 限制活动状态。
- 接口合同：`query_hot_metal_chemistry_by_heat("2#20260805-065")` 使用正式炉次号精确查询；`get_current_previous_heat_si_summary` 返回 `account_profiles`、`official_meltno`、样本数/均值和 `NO_SI_SAMPLES`，缺失值不填零。
- 验证：[relay 单元测试](../tests/test_imes_relay_mcp_server.py)、[炉次摘要回归](../高炉前端数据/智能助手/tests/test_imes_heat_summary_tools.py)；项目 Python 3.11 环境 `21 tests / OK`，新增排序合同的直接调用通过，代码 `py_compile` 通过。pytest 默认环境因既有 MCP/pydantic 二进制依赖不匹配未作为行为验收依据。
- 边界：本项修复本机源代码、配置合同和文档；Web MCP 仍需受控验证码或 `IMES_WEB_SESSION_COOKIE`，不自动读取浏览器 Cookie；生产 8093 需按守卫部署脚本单独发布后才会采用本修复。

## REQ-OPT-MULTI-CONDITION-LLM-REVIEW-20260805

- 需求：参数优化建议页不能只显示当前主炉况；必须同时可查看八类炉况的完整建议，并让所选炉况驱动建议、证据、曲线和模型复核上下文。每条动作必须可恢复查看原文章节、触发证据、前置条件、阻断原因、幅度、顺序、缺失数据、观察窗口、审批要求和只读边界，并区分 `eligible / blocked / needs_data / manual_confirm`。
- 规则实现：[recommendation_adapter.py](../自动诊断服务/recommendation_adapter.py) 新增 `multi_condition_recommendation.v1`。`active_plan` 是唯一合并当前主/次炉况并经过冲突解析的有效方案；其余七类分别以单一假设主炉况生成，只标记为 `supporting/hypothetical`，不进入当前执行队列。
- 实时合同：[local_pg_ws_bridge.py](../自动诊断服务/local_pg_ws_bridge.py) 在诊断快照中同时返回兼容字段 `recommendation` 与新字段 `recommendation_bundle`，失败时两者同时清理并返回明确 `recommendation_status=failed`。
- 模型复核：[diagnosis_model_review.py](../高炉前端数据/智能助手/backend/diagnosis_model_review.py) 和 `POST /api/diagnosis/model-review` 只解释规则分数与证据/历史是否一致；模型不能改写规则分数、动作、幅度、顺序、安全门禁或审批。响应固定为 `diagnosis_model_review.v1`，仅暴露公共模型名和只读元数据。
- 页面实现：[frontend_dashboard_v3.server.html](../高炉前端数据/frontend_dashboard_v3.server.html) 新增八炉况矩阵、当前/次要/条件预案边界、完整动作审计、模型 `preparing/retrieving/reasoning/completed/failed/stopped` 状态与停止/重试；选择炉况后复用原优化驾驶舱，因此曲线、证据和建议上下文同步变化。
- 数据边界：没有新增或修改数据库表；模型复核仅使用白名单诊断快照、最多 12 条诊断历史和动作状态摘要，使用 900 秒默认内存缓存，不持久化模型文本，不连接生产控制写接口。
- 验证：新增合同 `8 tests / OK`，v5 引擎回归 `11 tests / OK`，8093 静态合同 `8 tests / OK`，Babel 语法通过；隔离浏览器夹具验证八炉况切换、四态、十类动作字段、模型完成态和 Chromium 九个固定视口无横向溢出。

## REQ-FOREMAN-TREND-STANDALONE-PREVIEW-20260805

- 需求：在保留当前正式趋势页的前提下，新增一个独立的“工长趋势1”预览页，用于与现场工长趋势画面比较布局；不得删除或改写现有 `#trend` 页面。
- 实现：[独立页面](../高炉前端数据/foreman_trend_preview.html)、[HMI 样式](../高炉前端数据/assets/foreman-trend-preview.css)、[数据与交互运行时](../高炉前端数据/assets/foreman-trend-preview.js)。页面包含 7×7 指标矩阵、主 12 通道趋势、下方 5 通道周期趋势、灰色工具栏、图例/缩放/复位/导出动作和底部真实路由入口。
- 数据边界：`fixture=1` 仅用于截图布局校验并明确显示“布局校验数据 · 非生产”；去掉 fixture 后连接既有 WebSocket。该页在本机使用 `ws_port=8767`，220.12 已发布版本使用 `ws_port=8768` 读取 `bf_trend` 的分钟实际数据。缺少实时变量时显示 `--`，不生成伪生产值；没有新增数据库表、接口或服务端配置。
- 保留边界：当前正式页 `frontend_dashboard_v3.server.html#trend` 未加入新页面资源引用，也未删除或替换原 `TrendTab`。
- 验证：[静态合同测试](../tests/test_foreman_trend_preview.py) `4 tests / OK`；[浏览器矩阵](../tools/verify_foreman_trend_preview.cjs) Edge/Chromium `1280×1024` 通过；[跨引擎与视口矩阵](../tools/verify_foreman_trend_viewports.cjs) Edge/Chromium 9 项、Firefox 4 项、WebKit 4 项，共 `17 checks / PASS`；页面与控制台错误为 0。
- 入口：`http://127.0.0.1:8092/foreman_trend_preview.html?fixture=1`（固定夹具）或 `?ws_port=8767`（实时流）。
- 220.12 实流核验：用 torch_cuda128_whm Python 环境启动 tools/start_v3_full_python.py --db-profile 22012 --restart --skip-postgres-start --ollama-base-url http://10.30.220.12:11434；8767 返回 481 个历史点，页面实时连接成功，49 项中 30 项有值、19 项按合同显示 --，12+5 条曲线均有真实数据，页面/控制台错误为 0。缺失项不以 fixture 或默认值填充。
- 远端部署：新增页面、CSS、JS 已上传到 220.12 V4 8093 静态目录，备份为 F:\高炉炼铁项目-real-sensor-v2_V4_8093_PREVIEW\backups\8093_foreman_trend_preview_20260805\20260805_142812；8093/8768 服务保持 Running，监听 PID 未变，原正式页 SHA-256 仍为 356BB43BCC2DD45A28B208C3D5B24F91654851CAE10DDCF0B89861CC4B591DF1。
- 远端入口：http://10.30.220.12:8093/foreman_trend_preview.html?ws_port=8768；Edge 1280×1024 远端实流验收通过，页面显示“实时流已连接”，29 项有值，12+5 条曲线有数据，页面/控制台错误为 0。
- 220.12 发布：2026-08-05 使用 [受控静态资源部署器](../tools/remote_deploy_8093_foreman_trend_preview.ps1) 原子更新三个页面资源；远端入口为 `http://10.30.220.12:8093/foreman_trend_preview.html?ws_port=8768`。部署备份为 `F:\高炉炼铁项目-real-sensor-v2_V4_8093_PREVIEW\backups\8093_foreman_trend_preview_20260805\20260805_142959`，8093 PID `6892` 与 8768 PID `15824` 均未变化。
- 远端验收：[只读远端浏览器验收器](../tools/verify_foreman_trend_remote_8093.cjs) 通过：数据时间 `2026-08-05 14:30:00`，29 项真实值、20 项真实缺失、主/下方曲线 `12/12` 与 `5/5` 完整、无横向溢出、页面/控制台错误为 0；报告见 [remote_8093_live_report.json](../logs/foreman_trend_preview_20260805/remote_8093_live_report.json)。
## OPS-22012-DIRECT-SOURCE-RELAYS-20260805

- 用户目标：VPN 客户端只连接 220.12，即可打开 IMES Web，并通过固定 TCP 端口
  使用 Vastbase 与 pSpace；不再要求客户端常驻 SSH 回环转发器。
- 实现：[Nginx补丁器](../tools/patch_22012_nginx_imes_web.py)、
  [受控远端部署](../tools/remote_deploy_22012_direct_source_relays.ps1)、
  [运行态探针](../tools/remote_probe_22012_direct_relays.ps1)。
- 配置合同：`18080 -> IMES Web`、`15433 -> Vastbase`、`18889 -> pSpace`；
  防火墙只允许当前 VPN 客户端；原 `g13.html` 保留；不得重启
  8093/8768/8094/8770。
- 测试：[Nginx补丁合同测试](../tests/test_patch_22012_nginx_imes_web.py)；真实验收见
  [交接记录](handoffs/2026-08-05-22012-direct-source-relays.md)。
- 业务验收：浏览器验证码登录后成功进入 IMES 桌面并读取炉次化验等真实业务页；
  Vastbase 通过 15433 在只读事务中认证到真实上游；pSpace 通过 18889 使用现有 SDK
  读取真实静压力点且质量为 `Good`。
- 回滚：远端部署备份包含 `nginx.conf.before`、`portproxy.before.txt` 和受保护 PID；
  部署器中途失败会自动恢复本轮新增项。

## OPS-8093-PSPACE-CONNECTION-AUDIT-20260805

- 用户目标：核验 8093 是否失去 pSpace 通道，区分本机 VPN、8093 页面、8770 桥接和 243 pSpace 上游故障；仅在确认生产服务异常时执行最小修复，并先统一分钟表语义。
- 运行结论：本机 aTrust 进程存在，但系统 VNIC 为断开且没有 `10.22/10.30` 系统路由；与此同时，经 aTrust 门户“高炉模型”应用访问的 Chrome 页面仍能连接 8093。这表明当前接入是应用级代理路径，不能用 PowerShell 直连失败单独判定 8093/8770 故障。
- 端到端证据：8093 总览显示 `pSpace秒级实时 28/28`；状态时间在 7 秒观察窗内从 `20:58:57` 推进到 `20:59:03`，可见指标数据时间约 `20:59:10`、年龄约 `8秒`、质量“良好”，未出现“已降级为分钟镜像”；页面日志没有 8770/pSpace/WebSocket 错误。
- 修复决策：没有重启或修改 `BFV4PreviewProxy8093`、8770、8768、8094、数据库或 243。健康链路下重启会制造不必要中断；本轮只恢复/核对 aTrust 应用入口并完成只读浏览器验收。
- 分钟表边界：`one_minute_values` 当前同时容纳历史 `PS_HIS_AVERAGE` 与增量 `PS_RAW_SAMPLE`；后者是每分钟最后一个有效约5秒样本。由于主键仅为 `(tag_long_name, ts)`，同点同分钟不能并存两种聚合，后写会覆盖前写。统一语义前不得直接改字段名或标签。
- 关联记录：[问题追踪](question_traceability.md#q-8093-pspace-connection-and-minute-semantics-20260805)、[故障辨析](error_traceability.md#err-8093-pspace-app-vpn-misdiagnosis-20260805)、[数据结构](data_schema_reference.md#bf_sensorone_minute_values-与-bf_sensorraw_5s_values)、[专项说明](8093_核心指标pSpace秒级实时与分钟镜像降级_20260804.md)。

## REQ-PSPACE-MINUTE-CANONICAL-AVERAGE-20260805

- 需求：8770继续提供秒级当前值；8768继续提供分钟历史；`one_minute_values` 新增量统一为有效raw分钟算术平均；同时持续保存30天5秒原始明细、审计样本覆盖，并消除重复同步写入者。
- 实现：新增 `raw_minute_pipeline.py`，一次 `HisReadRaw` 同时生成raw明细与分钟均值；`pg_store.py` upsert审计字段；DDL新增10个nullable审计列；配置切为 `average/PS_RAW_AVERAGE`，闭合水位60秒；两套包装器使用项目根共享排他锁。
- 历史边界：旧 `PS_HIS_AVERAGE` 和截至2026-08-05 21:54的 `PS_RAW_SAMPLE` 不改名；自21:55起为 `PS_RAW_AVERAGE/valid_raw_mean_v1`。
- 生产状态：备份 `F:\高炉炼铁项目-real-sensor-v2_V3\logs\deploy_backups\pspace_minute_average_20260805_220434`；主任务运行、Watchdog正常完成、旧Realtime禁用；一个包装器进程链；8093/8094/8768/8770 PID未变。
- 验收：6项合同测试通过；生产1,159行与raw重算差异0、样本计数差异0；最近同步133/133点、错误0；8770为`pspace_realtime`且133/133数值，8768按合同保持`postgresql_realtime`；8093页面/资源HTTP 200且明确连接8770。
- 证据：[专项说明](pSpace分钟语义统一_20260805.md)、[配置](config_reference.md#pspace实时流与分钟同步现行配置)、[表结构](data_schema_reference.md#bf_sensorone_minute_values-与-bf_sensorraw_5s_values)、[测试](test_reference.md#test-pspace-minute-canonical-average-20260805)。

## REQ-22012-IMES-MCP-SYNC-20260805

- 需求：把本机已有的 MES/IMES 数据库 MCP 及其依赖服务加入 220.12 的 8093 生产服务配置，使 220.12 模型能够按口语自动调用；只重启 `BFV4PreviewProxy8093`，保护 8768/8094/8770。
- 现状判定：220.12 原有早期 `imes-readonly`，并非只有本机才有；远端缺少本机的 315 项目录、当前炉次 72 小时新鲜度修复、`gl02-extended` 与 `imes-web-readonly`。
- 实现：生产注册表固定四服务 `gl02-data/gl02-extended/imes-readonly/imes-web-readonly`；数据库 MCP 使用 `direct_22012`，不复制本机回环转发地址。服务配置仅引入 Machine 环境变量名，不写密码值。
- 部署：使用 [受控部署器](../tools/remote_guarded_deploy_8093_imes_mcp_sync.ps1) 暂停守卫、备份、原子替换、补丁配置、只重启 8093、恢复守卫并验收。结果备份为 `logs\deploy_backups\8093_imes_mcp_sync_20260805_215323`，`rollback_applied=false`、HTTP 200。
- 保护证据：8093 PID `7680 -> 14352`；8768=`4340`、8094=`14416`、8770=`12956` 部署前后均未变化。
- 业务验收：自动路由问题返回当前炉次 `072`、上一炉次 `071`、上一炉 Si 平均 `0.273%`；另一个自动路由问题返回 `T_body_L13_C=89.37`、时间 `22:06:00`、质量 `Good`。
- 证据：[生产同步交接](handoffs/2026-08-05-22012-imes-mcp-production-sync.md)、[配置参考](config_reference.md#22012-8093-四服务-mcp-生产注册表2026-08-05)、[测试参考](test_reference.md#test-22012-imes-mcp-sync-20260805)。
## REQ-8093-CROSS-SOURCE-MCP-20260805

- 目标：让 MES 与 GL02/pSpace 复合口语在一次受控 Host 编排中并行查询，统一返回事实、单位、数据时间、来源和缺失原因。
- 实现：[跨源计划与事实合同](../高炉前端数据/智能助手/backend/mcp_host/cross_source_plan.py)、[DAG执行器](../高炉前端数据/智能助手/backend/mcp_host/cross_source_executor.py)、[问答入口](../高炉前端数据/智能助手/backend/ollama_proxy_server.py)、[领域路由](../高炉前端数据/智能助手/backend/mcp_host/domain_router.py)。
- 安全边界：只读工具、实时 Schema 校验、45 秒总预算、30 秒缓存；部分数据保留事实但禁止不完整分析；不开放任意 SQL。
- 验证：[专项测试](../tests/test_cross_source_mcp.py)及相关 MCP 回归；生产验收使用 6 类固定口语，部署时只重启 `BFV4PreviewProxy8093`，保护 8768/8094/8770。
- 上线结果（2026-08-06）：专项 `51 passed`、相关组合 `108 passed`；生产已验证 MES+GL02 并行、炉次化验+炉身温度能力+顶压、趋势图和 7–12 层 A–F 矩阵。最终备份与 PID 隔离证据见[部署交接](handoffs/2026-08-06-8093-cross-source-mcp-deployment.md)。
# 2026-08-06：8093/8094 建议引擎完全一致

- 需求：8093、8094 的所有炉况调剂建议使用本地最新实现并完全一致。
- 实现：共同连接 8768；同步 `调控结论生成引擎`、政策配置、前端适配器、WebSocket 桥和两个入口页。
- 验收：`tests/test_8093_8094_recommendation_sync.py`、规则/复核测试共 26 项通过；生产初始化消息为 8 类炉况和 `multi_condition_recommendation.v1`。
- 交接：[2026-08-06-8093-8094-recommendation-engine-sync.md](handoffs/2026-08-06-8093-8094-recommendation-engine-sync.md)。

## REQ-OPT-VISUAL-COCKPIT-RESTORE-20260806

- 用户场景：8类炉况建议引擎升级后，现场仍需在首屏直观看到炉况数字、4项主证据曲线、实时监测、风险门禁、得分演化、30天基线偏离和建议队列；完整审计与模型说明不能挤压这些图表。
- 输入：8768 的 `multi_condition_recommendation.v1`、当前诊断、分钟历史缓冲、30天基线和既有 pSpace 当前值流。
- 输出：紧凑8炉况切换、随所选炉况变化的4项主证据、可展开的固定19项核心证据中心、单变量30分钟/2小时/8小时详情、四点顶压/顶温对比、完整动作审计抽屉和模型复核抽屉。
- 19项合同：4点顶压、综合顶压、4点顶温、综合顶温、冷风流量、冷风压力、热风压力、热风温度、透气性指数、全炉/上部/下部压差和煤气利用率；不把低料线等炉况特有主证据错误删除。
- 安全边界：`eligible/blocked/needs_data/manual_confirm` 和原文章节、证据、前置条件、阻断、幅度、顺序、缺失数据、观察窗口、审批要求全部保留；页面只读，模型不改写规则分数、安全门禁或动作合同。
- 实现：[建议工作台与证据中心](../高炉前端数据/frontend_dashboard_v3.server.html#L10530)、[19项证据中心](../高炉前端数据/frontend_dashboard_v3.server.html#L10587)、[页面热更新部署器](../tools/remote_deploy_8093_8094_recommendation_visual_frontend.ps1#L109)。
- 测试：[静态功能合同](../tests/test_recommendation_visual_workbench.py#L23)、[前端部署合同](../tests/test_recommendation_visual_frontend_deploy.py#L21)、[跨浏览器矩阵](../tools/verify_remote_recommendation_pages.cjs#L31)。
- 验收：本地 Babel 通过；专项与关联合同 `36 passed`。对8093源页与由8094基线生成、且SHA-256与远端完全一致的补丁页，完成Chromium每页9视口、Firefox每页4视口、WebKit每页4视口，共 `34 checks / PASS`；所有组合均为8种炉况、4项主证据、19个唯一核心变量、9类审计字段且无横向溢出。
- 上线：2026-08-06 R2已更新220.12的8093/8094；备份为 `F:\高炉炼铁项目-real-sensor-v2_V4_8093_PREVIEW\backups\8093_8094_recommendation_visual_20260806\20260806_095324`。最终8093/8094页面SHA-256分别为 `4C552CBA92D70379E3CBFD6447195F6B1105403009D3C6B39512BF5EF5D31262`、`876C14DF1F5620D3333C0F4AAC6D202FACE508E5C4C82E707F4E4D939A187C69`；服务器本机确认8093/8094 HTTP 200，8093/8094/8768/8770/11434均监听，8093与8768守卫均为Running。

## REQ-8093-AUTONOMOUS-HEAT-CHEMISTRY-MCP-20260806

- 用户场景：用正式炉次号、日期炉次号或“065炉”一类口语短号，查询该炉次任意组合的 C、Si、Mn、P、S、Ti、V、Cr、Cu、Ni、As，并可列出每个试样。
- 工具合同：`imes__query_heat_chemistry(heat_reference, components, include_samples, furnace_id)`；工具内部完成72小时唯一短炉号解析，返回正式 `meltno`、样本明细、各成分均值/最小/最大/最新值、单位、数据时间、来源和缺失原因。
- 编排：高频当前/上一炉仍走确定性快速路径；指定炉次化验由模型在实时注册且按能力裁剪的工具 Schema 中选择。模型只生成结构化工具名与参数，工具调用仍经过注册表、JSON Schema、只读策略、缓存和超时校验。
- 安全：不开放 `query_imes_readonly_sql`，不允许模型发明工具、账号、连接参数或 SQL；对事实查询，模型选完工具后由确定性格式器输出，避免再次规划导致查询轮数超限。
- 证据：[IMES MCP](../高炉前端数据/智能助手/mcp/imes_relay_mcp_server.py)、[问答编排](../高炉前端数据/智能助手/backend/ollama_proxy_server.py)、[能力目录](../高炉前端数据/智能助手/mcp/catalog/heat_analysis.json)、[模型选择审计器](../tools/probe_model_mcp_tool_selection.py)。
- 上线：生产模型已实际生成并执行 `imes__query_heat_chemistry`，查询 `2#20260805-065` 的 C/Si/Mn/P/S 共3个试样；部署、恢复、哈希和端口证据见[交接记录](handoffs/2026-08-06-8093-arbitrary-heat-chemistry-mcp.md)。

## REQ-8093-ASSISTANT-FETCH-RESILIENCE-20260806

- 用户场景：8093 智能助手反复出现 `接口状态：Failed to fetch` 时，应在 1–2 分钟内区分链路、端口、服务、部署碰撞、数据库、知识库和模型问题，并恢复到可完成真实问答的状态。
- 输入/诊断：VPN/私网、SSH 22、PostgreSQL 5432、8093、11434；服务/监听快照、实际进程环境、守卫日志、SCM 事件、默认知识检索、模型驻留、页面哈希和最近问答异常。
- 修复合同：所有新 8093 写入流程共享全局互斥；已知服务停止才执行守卫暂停、备份/退避启动/恢复/验证；纯页面变更不重启。只读 GET 可有限重试，问答 POST/SSE 禁止自动重发。
- 验收合同：自动分类 `healthy`；keyword 证据至少 1 条；仅批准 27B 驻留；守卫 `3/1/15/600` 且计数 0；唯一一次 SSE 事件完整、回答非空、知识未跳过，受保护 PID/哈希不变。
- 实现/测试：[自动恢复器](../tools/assistant_8093_auto_recovery.py)、[页面容错](../高炉前端数据/frontend_dashboard_v3.server.html)、[专项测试](../tests/test_8093_assistant_fetch_resilience.py)与[恢复合同测试](../tests/test_8093_assistant_auto_recovery.py)。最终组合 `41 passed`，生产报告为 `logs/assistant_8093_auto_recovery/20260806_105139_recover.json`。

## REQ-8093-8094-DIAGNOSIS-CORE-19-TRENDS-20260806

- 用户场景：在炉况诊断评分弹窗中先看所选炉况的规则主证据，再展开查看全套核心变量；点击任一变量可查看当前值、5分钟变化、30天基线和最近60分钟曲线。
- 固定19项及顺序：`P_top_gas_A-D`、`T_top_A-D`、`P_top`、`T_top`、`Q_blast`、`P_blast_cold`、`P_blast`、`T_blast`、`PI`、`DP_total`、`DP_upper`、`DP_lower`、`GasUtil`。
- 数据口径：只读当前诊断和分钟值；曲线最多61点。`T_top`直接值缺失时只允许由四点顶温有效值均值派生，并返回来源标记；缺失值不得补零。
- 可用性：新增 `GET /api/diagnosis-core-evidence`，不等待模型、调剂引擎或知识库，使19项证据与曲线在智能分析仍为 preparing/failed 时继续可用；详细智能分析仍只对用户选中的一个炉况异步生成。
- 交互边界：查看或切换变量不写库；只有原人工评分/建议提交动作写入既有事件表。
- 实现：[证据构造](../高炉前端数据/智能助手/backend/diag_ai_evidence.py)、[轻量接口](../高炉前端数据/智能助手/backend/ollama_proxy_server.py)、[弹窗模块](../高炉前端数据/assets/bf-diagnosis-manual-score-local.js)。
- 验收：本地专项合同 `44 passed`，本地跨浏览器 `17/17`；8093于2026-08-06完成守卫闭环，HTTP 200、19/19 ID与19/19曲线、8768 PID不变，备份 `logs/deploy_backups/diagnosis_ai_analysis_20260806_112034`。

## REQ-IMES-MATERIAL-FUEL-AUDIT-AND-DB-MODULE-SYNC-20260806

- 用户目标：确认 IMES 是否存在料速、燃料比数据；把相关数据库同步配置和程序完整同步到当前项目；再次验证 220.12 生产落库闭环。
- 输入：Vastbase 只读表元数据及样本、220.12 `bf_imes.raw_rows`、V4 `数据库同步和存取` 模块、220.12 pSpace 同步任务/进程/分钟表/5秒表。
- 输出：只读字段审计结果、当前项目 43 文件哈希清单、150行点位清单与代码验证、生产新增点位和整点喷煤验证结果。

## REQ-FOREMAN-CO2-FORMAL-POINT-20260807

- 用户目标：确认工长趋势“二氧化碳”是否为真实 pSpace 数据，并在确认后加入正式点位清单。
- 点位合同：`CO2_top` 对应 `\冀南钢铁\SIO\CC\GF2\SIO_CC_GF2_T0113`，描述“2号炉干法除尘_二氧化碳”，单位 `%`；它是跨 `GL02` 子树的白名单物理点，不是页面示例值或派生值。
- 实测证据：2026-08-07 通过 `10.30.220.12:18889` 只读 SDK 查询，实时值 `22.100332260131836`、质量 `Good`、源时间 `11:05:00.94`。同一时点220.12 `sensor_registry` 尚无CO2条目，因此不得把旧页面字段表述为已落库。
- 实现：[正式点位清单](../数据库同步和存取/config/点位清单.tsv)、[可重复点位补丁器](../tools/apply_foreman_points_and_coal_storage.py)、[8770映射](../tools/pspace_8092_realtime_bridge.py)、[工长趋势字段](../高炉前端数据/assets/foreman-trend-preview.js)。
- 验证：[桥接合同测试](../tests/test_pspace_billboard_realtime_bridge.py)、[点位补丁测试](../tests/test_foreman_points_and_coal_storage.py)和[本机清单验证器](../tools/verify_foreman_local_point_catalog.py)。本轮只完成本机正式定义，未部署或重启220.12的8770/同步服务。
- 安全：Vastbase 与 PostgreSQL 查询均只读；凭据只从受控环境/既有授权加载器注入；模块同步排除 `.env`、日志、备份、导出和缓存；本次不部署、不重启、不改生产表。
- 语义门禁：在现场确认料速单位/批次边界，以及燃料比的干湿基、燃料构成与统计周期前，不创建正式派生字段或对外 API。
- 证据：[专项报告](IMES料速与燃料比只读核验_20260806.md)、[同步清单](../数据库同步和存取/module_sync_manifest.json)、[测试](test_reference.md#test-imes-material-fuel-and-db-module-sync-20260806)。

## REQ-IMES-REPORT-PERSISTENCE-20260808

- 用户目标：把“报表管理 → 冀南高炉报表 → 冀南新区高炉作业日志”的 2# 高炉报表全部返回数据纳入 220.12 数据库，并提供可调用的燃料比/批数查询入口。
- 实现：[Raqsoft 报表解析器](../数据库同步和存取/src/imes_report_client.py)、[同步入口](../数据库同步和存取/sync_bf2_operation_log_report.py)、[PostgreSQL schema/view](../数据库同步和存取/schema/postgresql_imes.sql)、[采集清单](../数据库同步和存取/config/IMES可读数据清单.tsv)、[GL02 MCP 工具](../高炉前端数据/智能助手/mcp/bf_data_mcp_server.py#L2074-L2150)。
- 网络与调度：220.12 `18084 -> 10.10.181.205:8080` 报表代理；计划任务 `IMESBF2OperationLogReport5m` 每5分钟同步当天；历史回填 2026-02-09 至 2026-08-08。
- 数据合同：`bf_imes.raw_rows` 保留全部单元格；`bf_imes.v_bf2_operation_log_report` 暴露报表字段；M 列燃料比为公式重算，D 列为批数；料速未确认，不得把批数冒充料速。
- 验证：报表代理/查询 HTTP 200；历史 4320 行、180 天、重复键 0；计划任务 `LastTaskResult=0`；活动 V4 MCP 工具 `query_bf2_operation_log_report` 列表与 2026-08-08 直接调用通过（19 个工具、返回2行）；`pytest -q tests/test_imes_report_client.py` 2 passed。
- 状态：`production_report_sync_deployed`；炉前出铁块 Si 和现场料速公式仍是后续独立需求。

## REQ-FOREMAN-CO-H2-WIND-REGISTRY-20260807

- 用户目标：把一氧化碳、氢气、鼓风动能、标准风速、实际风速纳入本机工长趋势正式点位；下一次生产部署必须先写入 220.12 `bf_sensor.sensor_registry`，再恢复现有同步任务采集，不新增 pSpace 常驻读取程序。
- 点位合同：`CO_top=SIO_CC_GF2_T0112`、`CO2_top=SIO_CC_GF2_T0113`、`H2_top=SIO_CC_GF2_T0111`；`BlastEnergy=SIO_GL02_BT_T0136`、`BlastSpeedStd=SIO_GL02_BT_T0133`、`BlastSpeedActual=SIO_GL02_BT_T0134`。CC/GF2 点按跨子树白名单读取，BT 点按 GL02 既有批量同步读取。
- 本机实现：[正式清单](../数据库同步和存取/config/点位清单.tsv)、[可重复补丁器](../tools/apply_foreman_points_and_coal_storage.py)、[8770桥接](../tools/pspace_8092_realtime_bridge.py)；当前清单153行，其中151个物理点、2个派生点，确认项19项。
- 注册顺序：[轻量注册器](../tools/init_foreman_points_pg_light.py)先执行 schema/`upsert_registry` 并要求19项确认；[受控部署器](../tools/remote_deploy_foreman_points_coal_20260806.ps1)随后才启动原有 `BlastFurnaceV3PgContinuousSync30s`，并保留旧 Realtime 任务 Disabled。
- 生产边界：2026-08-07 已在220.12完成受控替换；先注册19项，再恢复既有 `BlastFurnaceV3PgContinuousSync30s`，未增加新的 pSpace 常驻读取程序。新增六点均已在 `one_minute_values` 产生最新质量 Good 数据。
- 验证：本机 `pytest.exe -q -p no:cacheprovider --basetemp .tmp_pytest_co_h2 tests\\test_pspace_billboard_realtime_bridge.py tests\\test_foreman_points_and_coal_storage.py tests\\test_foreman_trend_missing_value_semantics.py`（8 passed）；配置入口专项11项通过；远端最近完成轮次 `sync_runs.tags_ok=151,tags_error=0`，六点最新时间推进至 `2026-08-07 15:05:00`，入口与配置 SHA-256 分别为 `6140366FB0FFC364E7DD96DC945DF0D8DFC98A72FFAA312ED94DCE0512FCE684`、`B1FF7512E3CF18A4B8CF4F5EE51982FD7A1B66C1EF315CF0F5062A46DCA202A6`。

## REQ-FOREMAN-SYNC-CONFIG-ENTRY-20260807

- 用户目标：继续修改工长趋势采集配置入口，使现有 220.12 同步任务明确读取正式点位清单，而不是继续沿用旧默认路径导致 `tags_ok=148`。
- 实现：[实时同步入口](../数据库同步和存取/run_realtime_sync_pg_bg.ps1)在每轮调用 `sync_from_243_pg.py` 时显式传递脚本目录下的 `config\\sync_config.json`；[受控部署器](../tools/remote_deploy_foreman_points_coal_20260806.ps1)、[热更新器](../tools/remote_hot_deploy_foreman_points_coal_20260806.ps1)和[文件安装器](../tools/remote_install_foreman_point_files_only.ps1)均把该入口纳入候选包。
- 配置合同：`config/sync_config.json` 的 `point_catalog_tsv` 仍指向 `数据库同步和存取/config/点位清单.tsv`；部署包必须同时包含入口、配置、153 行清单和注册器，避免只写 `sensor_registry` 而同步仍读取旧清单。
- 验证：`pytest.exe -q -p no:cacheprovider --basetemp .tmp_pytest_config_entry tests\\test_foreman_points_and_coal_storage.py tests\\test_pspace_minute_average_semantics.py`（11 passed）；两个 PowerShell 入口通过 `tools/check_ps1_syntax.ps1`。
- 状态：`production_deployed_verified`；入口、配置和正式清单已在220.12生效，最近完成轮次 `tags_ok=151,tags_error=0`，新增点均有 Good 分钟值。

## REQ-FOREMAN-PSPACE-EXTRA-METRICS-LIVE-20260808

- 用户目标：把工长趋势新增的鼓风、水系统、氮气、富氧阀前后压力、罐重以及 CO/H2/CO2 点位接入生产页的实时数据流，并保持与既有 8770 pSpace 采集程序共用一条读取链路。
- 实现：[8770实时桥](../tools/pspace_8092_realtime_bridge.py)的 `FOREMAN_EXTRA_SENSORS`/确认点位映射、[工长趋势页面](../高炉前端数据/assets/foreman-trend-preview.js)、[受控部署器](../tools/remote_deploy_foreman_pspace_extra_metrics_20260806.ps1)；页面缓存标记为 `20260806-pspace-extra-r3`。
- 运行态证据：部署前远端 8770 仅返回144个流值且新增水/气体点位缺失；替换后同一 `V4BillboardPspace8770` 任务返回157个流值、133个Billboard值，17个工长扩展值全部为数值，无新增 pSpace 常驻读取程序。
- 2026-08-08 远端实测：`CO_top=25.6879%`、`CO2_top=21.2686%`、`H2_top=4.0303%`、`BlastEnergy=11770.56`、`BlastSpeedStd=258.90m/s`、`BlastSpeedActual=266.58m/s`、`Q_soft_water=4382.78m³/h`、`P_soft_water=0.799MPa`、`Q_high_pressure_water=873.05m³/h`、`P_high_pressure_water=1.588MPa`、`P_medium_pressure_water=0.870MPa`、`ExpansionTankLevel=3.854m`、`Q_N2=1312.30Nm³/h`、`P_N2=609.34kPa`、`P_O2_valve_in=0.683MPa`、`P_O2_valve_out=0.471MPa`。
- 验证：[8770流验证器](../tools/verify_billboard_pspace_8770.py)报告 `foreman_numeric_count=17`、`passed=true`；[远端页面点位检查](../tools/inspect_foreman_trend_remote_points.cjs)确认页面状态为“pSpace秒级已连接 · 分钟历史已连接”，目标点均为 `source=pspace`；8093/8094/8768/8770最终监听分别为 `4788/13748/10832/3732`。
- 影响边界：仅替换既有 8770 桥、工长趋势 JS/HTML/煤量积分资源；不新增读取进程，不改变 8768、8094 服务或数据库同步任务。


## REQ-MCP-IMES-HEAT-SI-SAMPLES-20260807

- 用户场景：查询当前炉次时显示开口时间、当前已经发布的全部试样、每个试样/铁罐的 Si 与时间，并在尚未结束出铁时计算阶段性平均值；用户只给大概时间段时，反查对应正式炉次并展示各炉次平均 Si 和逐罐试样。
- MCP 工具：`imes__query_current_heat_chemistry(as_of_time, components, include_samples, furnace_id)`；`imes__query_heat_chemistry_by_time_range(time_reference, components, include_samples, as_of_time, furnace_id, heat_limit)`。
- 数据合同：炉次身份与开堵口时间来自 `public.t_ipes_cond`；试样与 Si 来自 `t_qpes_inner_batch + inner_batch_insp_bb`；铁罐号只允许 `batchno -> public.v_qpes_mat_final.thankno` 精确关联。真实取样时间缺失时依次使用判定时间、发布时间并显式标记时间类型。
- 编排：当前炉次 Si 和时间段 Si 走零规划轮确定性路由；“鸬鹚”规范化为“炉次”。当前炉次尚未结束时 `provisional=true`、`partial_heat=true`，平均值只使用查询时点已发布的非空数值样本。
- 边界：时间范围默认最多 168 小时；所有查询只读；不开放 SQL；时间段覆盖多个炉次时全部返回，未覆盖时返回最近炉次并要求用户确认。
- 实现：[IMES MCP](../高炉前端数据/智能助手/mcp/imes_relay_mcp_server.py)、[问答路由与格式器](../高炉前端数据/智能助手/backend/ollama_proxy_server.py)、[领域路由](../高炉前端数据/智能助手/backend/mcp_host/domain_router.py)、[能力目录](../高炉前端数据/智能助手/mcp/catalog/heat_analysis.json)。
- 测试：[工具测试](../高炉前端数据/智能助手/tests/test_imes_heat_summary_tools.py)、[路由与回答测试](../高炉前端数据/智能助手/tests/test_mcp_multi_server_host.py)；2026-08-07 本地专项 `29 passed`，相关 Python `py_compile` 通过。
- 状态：`implemented_local_not_deployed_8093`；必须按 8093 受控部署流程另行发布后，生产服务才会使用本修复。

## REQ-HEAT-QUALITY-REPAIR-CLOSED-LOOP-20260807

- 目标：防止普通增量覆盖已修复炉次时间和状态；隔离未来/日期锚点冲突；真实输出镜像、汇总和样本变化缺口；结构化保存异常原因；分页扫描并使用准确指标名。
- 数据合同：[表与 upsert](../高炉前端数据/智能助手/backend/heat_performance_quality.py)、[同步与回看](../tools/sync_22012_heat_performance_quality.py)、[幂等迁移](../tools/migrate_heat_quality_time_repair_columns_22012.py)。
- 状态门禁：`time_anomaly_repaired` 的时间谱系不被普通同步覆盖；`future_pending` 默认不由 API 返回，时间成熟且普通数据有效后可解除；正式炉号日期与 `workdate` 不一致时不得静默猜日期。
- 审计：输出 `anomaly_detected/evidence_eligible/repair_prepared/repaired/skipped_no_evidence/future_pending/future_workdate_filtered/repair_truncated`；缺口按 Vastbase→`bf_imes.raw_rows`、Vastbase→汇总表和样本数变化分开统计。
- 验证：[专项测试](../tests/test_heat_performance_quality.py)、[回看测试](../tests/test_heat_performance_quality_repair_loop.py)、[查询测试](../tests/test_heat_performance_quality_query.py)；本机 17 项通过，相关文件 `py_compile` 通过。
- 状态：`implemented_local_not_deployed`；本轮未迁移 220.12 表、未替换远端同步器、未重启 8093 或其他服务。

| REQ-8093-DIAGNOSIS-FOREMAN-KNOWLEDGE-ADVICE-20260807 | 5分钟智能分析禁用三规二制建议来源，仅使用 bf_foreman_ops_v1 64主题知识库；展示19个核心传感器偏离、正常分距100分差值、四类只读候选方向，并以详情链接查看正文 | ollama_proxy_server.py / diag_ai_evidence.py / diagnosis_model_review.py / bf-diagnosis-manual-score-local.js | tests/test_diagnosis_ai_analysis.py |
## REQ-TREND-19-LANE-MERGE-20260807

- 用户场景：趋势分析页左侧不再用多个小面板分散显示核心变量，而是参照工长趋势，在一张公共 `0-100` 画布中同时查看19项历史与未来趋势。
- 固定19项及顺序：`P_top`、`P_top_gas_A-D`、`T_top`、`T_top_A-D`、`Q_blast`、`P_blast_cold`、`P_blast`、`T_blast`、`PI`、`DP_total`、`DP_upper`、`DP_lower`、`GasUtil`。
- 可视化合同：每项变量按历史窗口中位数和10/90分位波动范围映射到固定水平趋势带；历史与预测共享参数，缺失不补零；图形坐标不进入提示框，提示框只显示原始值、单位和历史/预测状态。
- 预测合同：手动与自动 `chronos_predict_recommended_batch.target_ids` 均使用完整19项；前端接收直接ID和`*_mean`返回名。既有8767/8768桥接已经支持19目标，本需求不修改后端接口、数据库或模型服务。
- 实现：[front2趋势页](../高炉前端数据/front2/frontend_dashboard_front2.server.html)、[可重复补丁器](../tools/patch_front2_trend_19_lane.py)。
- 验证：[静态合同](../tests/test_front2_trend_19_lane_merge.py)、[跨浏览器矩阵](../tools/verify_front2_trend_19_lane.py)。
# REQ-ABC33-DECISION-CENTER-PROMINENT-20260808

- 需求：A9、B13、C11共33项炉况必须作为优化建议页AI决策中心的显眼常驻工作区，不再依赖右下角悬浮入口。
- 实现：[abc-furnace-rules-production.js](../高炉前端数据/assets/abc-furnace-rules-production.js) 在 `.bf-recommendation-summary-v2` 之后、原AI决策中心主体之前动态挂载；默认同时显示A/B/C三列，并支持全部33项、A9、B13、C11筛选和逐项详情。
- 接口：继续使用 `GET /api/furnace-rules/latest` 与 `GET /api/furnace-rules/{rule_id}/detail`，不新增生产写入权限。
- 测试：[test_abc_production_ui.py](../tests/test_abc_production_ui.py)、[abc33_decision_center_fixture.html](../tests/fixtures/abc33_decision_center_fixture.html)。
- 部署：8094资源版本 `abc33-20260808-r3-decision-center`；8093未修改。

## REQ-BODY-TEMP-INFRARED-REPLAY-20260808

- 用户场景：高炉长选择过去最多72小时的时间窗，把L7～L16、A～H共80个炉体离散测温点按固定窗口P05～P95红外色谱快速回放，拖动时间轴观察热区纵向和周向移动，并可在现场Edge导出WebM视频；同页按层显示温度A～H八线、按物理标高显示静压力A～F六线，游标与回放帧联动。
- 数据合同：只读 `bf_sensor.sensor_registry` 与 `bf_sensor.one_minute_values`；温度单位由受控点位布局定义为℃，不依赖生产注册表中不存在的 `unit` 列；不补未来值、不写数据库。
- 解释边界：画面是离散炉体测温点的空间插值，不是红外相机图像；颜色只用于历史回看，不能直接代表炉内连续温度场或自动控制依据。220.12 V4未安装C2估算器，页面明确禁用“根部代理”，不影响温度回放。
- 实现：[只读回放服务](../tools/soft_zone_replay_server.py)、[页面](../高炉前端数据/soft_zone_replay/index.html)、[前端运行时](../高炉前端数据/soft_zone_replay/soft-zone-replay.js)、[样式](../高炉前端数据/soft_zone_replay/soft-zone-replay.css)。
- 部署：220.12独立端口`8892`，计划任务`\BlastFurnaceServices\SoftZoneTemperatureReplay8892`；未嵌入或重启8093/8094。
- 验证：[合同测试](../tests/test_soft_zone_replay_server.py) 6项通过；本地跨浏览器17项通过；220.12真实数据生产冒烟4项通过，报告见[交接记录](handoffs/2026-08-08-soft-zone-infrared-replay-8892.md)。

## REQ-ABC33-COMMON-FEATURES-FIRST-20260808

- 阶段门禁：先独立实现和验收通用窗口特征及复合风险因子，再开始A类9项；B/C真实分数和告警在通用特征、A类及历史回放完成前持续关闭。
- 窗口公式：`z60_X=(最近60分钟均值-对应日期30天基线中位数)/IQR`；`z15std_X=最近15分钟样本标准差/(IQR/1.35)`；`slope30_X=最近30分钟按真实时间线性拟合斜率×30/IQR`。
- 数据质量：以评价时刻为窗口终点，按分钟去重和对齐；每个窗口覆盖率至少75%，数据年龄不超过300秒；缺数、陈旧、基线无效或阈值未获现场批准时保持不可用，禁止补0或借用其他变量基线。
- 复合因子：严格实现顶温/顶压/静压范围、煤气利用、压差、透气、送风接受、料线停滞/滑落、料线损失/偏差、炉体冷热、冷却、热制度和排渣代理；公式规定的输入缺失时不得用剩余项计算半成品。
- 实现：[通用特征构建器](../自动诊断服务/abc_feature_builder.py)、[运行时历史与基线接入](../自动诊断服务/local_pg_ws_bridge.py)、[只读历史回放](../tools/replay_abc33_rules.py)。
- 验证：[通用特征专项测试](../tests/test_abc_calibrated_features.py)；最终结果以本机测试和220.12只读历史回放报告为准。
## REQ-SI-V20-8093-8094-SHADOW-WORKBENCH-20260808

- 需求：独立展示候选炉次、当前影子预测、历史实际/预测曲线，并在后续化验到库后自动完成逐炉对比。
- 数据合同：候选来自220.12本地 `bf_imes.raw_rows`；实际平均Si固定来自 `bf_assistant.heat_performance_quality_summary.si_avg`；当前炉和截止时刻后发布的化验不得进入输入。
- 实现：[V20服务](../高炉前端数据/智能助手/backend/si_v20_shadow.py)、[独立页](../高炉前端数据/si_v20_workbench.html)、[8093快速部署](../tools/deploy_si_v20_workbench_8093.ps1)。
- 时间审计：`requested_at` 保存实际开始预测时间，`prediction_cutoff_ts` 保存特征截止时间；估计开口时间和正式MES时间分标签显示。
- 状态：保持 `experimental_shadow`，只写预测审计，不改生产设定值。
# REQ-ABC33-FORMULA-DOC-AUDIT-20260809

- 目标：将ABC33运营核验版DOCX保真转换为Markdown，并逐条核对33项公式、通用因子、权重、方向、阈值和运行就绪性。
- 原文转换：[炉况计算规则补充_三大模块_最终运营核验优化版_原文.md](./炉况计算规则补充_三大模块_最终运营核验优化版_原文.md)
- 机器核验转储：[炉况计算规则补充_三大模块_最终运营核验优化版_机器保真转储.md](./炉况计算规则补充_三大模块_最终运营核验优化版_机器保真转储.md)
- 人工可读转换程序：[convert_abc33_docx_to_clean_markdown.py](../tools/convert_abc33_docx_to_clean_markdown.py)
- 核验报告：[ABC33公式与原文逐条一致性核验_20260809.md](./ABC33公式与原文逐条一致性核验_20260809.md)
- 转换程序：[convert_docx_to_markdown_verified.py](../tools/convert_docx_to_markdown_verified.py)
- 转换证据：[abc33_source_docx_markdown_validation_20260809.json](../logs/abc33_source_docx_markdown_validation_20260809.json)
- 结论：31项规则级因子/权重一致；A9和C2存在确定不等价；多个阶段阈值和完整点位门禁尚未就绪，继续保持影子模式。

## REQ-ABC33-A9-ECONOMIC-BOUNDARY-20260809

- 目标：明确`PCI_rate`为实际喷煤速率、`PCI_set`为小时目标设定，并把A9由单项最大/三项均分修订为强化程度与炉况约束耦合风险。
- 修订建议：[炉况计算规则补充_A9经济边界公式修订建议版_20260809.md](./炉况计算规则补充_A9经济边界公式修订建议版_20260809.md)
- 规则目录：[abc_rule_catalog.py](../自动诊断服务/abc_rule_catalog.py)
- 因子实现：[abc_feature_builder.py](../自动诊断服务/abc_feature_builder.py)
- 测试：[test_abc_calibrated_features.py](../tests/test_abc_calibrated_features.py)、[test_abc_common_factors.py](../tests/test_abc_common_factors.py)
- 发布边界：继续处于影子核验状态；完成30天回放和工艺审核前不开放真实分数。
## REQ-SI-V20-AUTO-QUALITY-REFRESH-20260809

- 需求：220.12 本地 IMES 镜像新增/迟到的炉次质量经五分钟汇总后，V20 页面无需用户清缓存或重开页面即可出现；跨午夜继续显示新一天；旧候选不能遮挡最新炉次。
- 数据流：`bf_imes.raw_rows` → `HeatPerformanceQualitySync` → `bf_assistant.heat_performance_quality_summary.si_avg` → `/api/si-v20/history` → 60 秒页面刷新。
- 实现：[候选过滤](../高炉前端数据/智能助手/backend/si_v20_shadow.py)、[自动日期与质量新鲜度](../高炉前端数据/assets/bf-si-v20-workbench.js)、[不可变资源版本](../高炉前端数据/si_v20_workbench.html)。
- 测试：[合同测试](../tests/test_si_v20_shadow_workbench.py)、[测试记录](test_reference.md#test-si-v20-auto-refresh-cache-20260809)。
- 边界：页面只读汇总实际值，不直连外部 IMES；同步周期最多约 5 分钟，页面显示再延迟最多约 60 秒；V20 仍为影子预测。

## REQ-SI-V20-DUAL-TIMING-AND-HOURLY-MATCH-20260809

- 需求：220.12 的 IMES 本地镜像按一分钟任务尝试更新；炉次质量汇总也改为一分钟任务尝试更新。平均 Si 预测严格拆为两种口径：历史回看固定使用该炉 `open_ts - 60min`，生产定时预测固定每个整点执行一次，并把该次预测评价到“预测发起之后最先真实开口的炉次”。
- 实现：[V20服务](../高炉前端数据/智能助手/backend/si_v20_shadow.py)、[API路由](../高炉前端数据/智能助手/backend/ollama_proxy_server.py)、[整点运行器](../tools/run_si_v20_hourly_prediction.py)、[220.12整点包装](../tools/run_22012_si_v20_hourly_prediction.ps1)、[整点任务注册器](../tools/register_22012_si_v20_hourly_task.ps1)、[炉次质量一分钟任务调整器](../tools/set_22012_heat_quality_sync_1min.ps1)、[独立工作台](../高炉前端数据/si_v20_workbench.html)。
- 数据合同：实际平均 Si 只来自 `bf_assistant.heat_performance_quality_summary.si_avg`；V20 API 不直连外部 IMES。生产整点截止必须为 `HH:00:00`；同一 `furnace_no + prediction_cutoff_ts` 只能有一条 `hourly_schedule`；最终实际炉次按 `open_ts >= requested_at` 排序取第一条。
- 页面：历史区域可在“实际炉次/开口前60分钟回放”与“生产整点预测汇总”之间切换；生产整点任务不依赖浏览器常开，页面按钮只用于幂等补跑当前整点。
- 验收：相关 pytest、JavaScript 语法和本机浏览器矩阵；部署后还必须检查三项计划任务、连续整点无缺口、汇总表新鲜度、下一真实炉次匹配和页面自动出现迟到化验。
- 当前状态：旧`hourly_schedule`实现已由`REQ-SI-V20-STRICT-HOURLY-CLOSED-LOOP-20260810`取代；旧任务未部署是预期状态，不再作为严格整点基线。生产严格整点使用独立`strict_hourly`任务/API/页面，首槽已验证，24小时连续性仍待真实运行确认。

## REQ-SI-V20-CONFIGURABLE-SCHEDULE-20260809

- 需求：高炉长/操作者可在V20页面把生产自动预测周期调整为1、10、30、60或1440分钟；默认60分钟，可启用或暂停。后台不依赖页面常开。历史上支持任意起止时刻按相同粒度批量预测，也支持单个指定时刻预测，并按预测时间槽绘制曲线。
- 架构：Windows后台分发任务固定每分钟调用一次API；真实周期保存在数据库，不因页面改周期而反复修改计划任务。数据库使用规范化三层结构：`si_v20_prediction_schedule`保存配置，`si_v20_prediction_run`保存批次，`si_v20_prediction_audit`保存逐时间点预测。
- 实现：[V20服务](../高炉前端数据/智能助手/backend/si_v20_shadow.py)、[API路由](../高炉前端数据/智能助手/backend/ollama_proxy_server.py)、[分钟分发器](../tools/run_si_v20_schedule_dispatcher.py)、[220.12包装](../tools/run_22012_si_v20_schedule_dispatcher.ps1)、[任务注册器](../tools/register_22012_si_v20_schedule_task.ps1)、[工作台](../高炉前端数据/si_v20_workbench.html)。
- 匹配合同：实时定时点按实际 `requested_at` 后第一条真实开口匹配；历史时间槽按 `schedule_slot_ts` 当时或之后第一条真实开口匹配。实际平均Si仍只来自 `heat_performance_quality_summary.si_avg`。
- 约束：允许周期白名单为 `1/10/30/60/1440`；单次历史批量最多5000点；预测截止不得位于服务器未来；同一配置/时间槽和同一批次/时间槽均幂等；只写影子预测审计，不写生产控制值。
- 模型边界：当前V20仍按开口前60分钟训练。1/10/30分钟和日频是同一模型在不同提前量上的影子趋势实验，必须按周期和距实际开口时间分层评价，禁止与标准开口前60分钟命中率混算。
- 曲线导出：工作台沿用开始/结束日期，并增加起止炉次筛选；可分别下载“预测曲线CSV”和“实际平均Si曲线CSV”。实际曲线按炉号去重；导出与当前日期、炉次和显示筛选一致，并使用UTF-8 BOM和CSV公式注入防护。
- 测试与生产状态：[可配置调度测试](../tests/test_si_v20_configurable_schedule.py)及原V20合同测试共`28 passed`。2026-08-09已部署220.12：三张生产表均存在，默认配置`60min/enabled`，任务`\BlastFurnaceServices\SiV20ScheduledShadowPrediction`为SYSTEM、每分钟触发、`IgnoreNew`；23:00首个时间槽成功写入。8093/8094的schedule与scheduled-history API均返回200，页面资源版本为`20260809-curve-export-r6`。

## REQ-SI-V20-CURVE-EXPORT-20260809

- 需求：操作者可按日期范围或炉次范围查看曲线，并分别下载V20预测曲线和实际平均Si曲线用于离线分析。
- 实现：[独立工作台](../高炉前端数据/si_v20_workbench.html)和[页面逻辑](../高炉前端数据/assets/bf-si-v20-workbench.js)。预测CSV保留发起时间、时间槽、截止时间、候选/匹配炉次、P10/P50/P90、实际值和命中；实际CSV按真实炉次去重。
- 验收：8093真实页面炉次`124~127`筛选为4行；实际Si导出提示“已导出4炉”；页面无横向溢出。8094资源与API通过HTTP验证。

## REQ-SI-V20-STRICT-HOURLY-CLOSED-LOOP-20260810

- 需求：新增不受可调周期影响、永久启用的严格整点通道；每个自然小时唯一一个`strict_hourly`时间槽，截止严格固定为`HH:00:00`，失败保留重试且不阻塞后续小时。
- 实现：[严格上下文推理](../高炉前端数据/智能助手/backend/si_v20_strict_context.py)、[V20服务与槽账本](../高炉前端数据/智能助手/backend/si_v20_shadow.py)、[API](../高炉前端数据/智能助手/backend/ollama_proxy_server.py)、[分钟分发器](../tools/run_si_v20_strict_hourly_dispatcher.py)、[任务注册](../tools/register_22012_si_v20_strict_hourly_task.ps1)、[工作台](../高炉前端数据/si_v20_workbench.html)。
- 数据合同：历史Si同时满足业务时间和首次可用时间不晚于整点；传感器同时满足`ts<=slot_ts`与`collected_at<=slot_ts`；缺失保持缺失。旧Si无法证明首次入库时间时标记`legacy_availability_unknown`。模型使用前1~5炉Si、8/12小时PCI及133点多窗口；本地炉料化学若无可验证镜像则只记录缺失，不直连外部IMES。
- 匹配合同：保存初始候选；预测完成后固化`open_ts > execution_completed_at`的第一炉为评价炉次，化验到库只补该固定炉次，查询时不动态改配。
- 状态：`production_deployed_initial_slot_verified`。相关回归`35 passed`，便携模型与原LightGBM单样本差`1.11e-16`；8093/8094 API及两页规定视口矩阵通过。首个`2026-08-10 01:00`槽成功、无重复/非整点/截止违规，P50=`0.318322%`、P10–P90=`0.261695%–0.384624%`，等待预测完成后下一炉及化验。严格GET状态/历史已改为纯查询；连续24小时24槽仍需到`2026-08-11 01:00`后作运行态确认。
- 2026-08-10 08:45状态：01:00~08:00共8个严格槽全部成功，失败/运行/陈旧/逾期/重复/非整点/截止违规均为0。131炉已固化到01:00预测并完成实际Si对比；132炉进入本地汇总后发现一条`si_available_at`空值，已修复独立同步副本与并发upsert合同，缺失恢复为0。

## REQ-SI-V20-HOURLY-PREDICTION-QUALITY-TABLE-20260810

- 需求：在同一工作台持续列出每个自然小时的预测平均Si，并显示其最终关联炉次的实际开口、堵口、逐次化验Si、平均Si、误差和±0.05结果；支持日期/炉次范围和CSV导出。
- 实现：[只读聚合服务](../高炉前端数据/智能助手/backend/si_v20_shadow.py)、`GET /api/si-v20/hourly-table`、[工作台](../高炉前端数据/si_v20_workbench.html)和[页面逻辑](../高炉前端数据/assets/bf-si-v20-workbench.js)。不新增重复业务表，读取严格槽、预测审计与炉次质量汇总的并集。
- 合同：每小时仅一行；优先`strict_hourly`，严格槽失败/重试时才明确标记`scheduled_interval_fallback`；缺失不填0。逐次Si来自`sample_details`，平均Si固定来自`heat_performance_quality_summary.si_avg`。
- 验收：8093/8094页面、API、汇总CSV与截图纳入每小时自动验收；截至08:45表格10行、严格预测8行、严格失败槽0。

## REQ-OPS-POWERSHELL7-UTF8-20260810

- 需求：本机项目命令、启动入口和新任务只使用最新稳定版 PowerShell 7 Core，以无 BOM UTF-8 处理中文路径和中文输出，不再静默调用 Windows PowerShell 5.1。
- 实现：[强制约束](../AGENTS.md)、[运行规范](./PowerShell7_UTF8运行规范.md)、[运行时验证器](../tools/verify_pwsh7_utf8.ps1)、[本机主启动入口](../start_v3_full.ps1)、[隐藏任务包装](../tools/run_hidden_ps1.vbs)。
- 运行合同：`PSEdition=Core`、主版本不低于7、进程为`pwsh.exe`；输入/输出编码统一为UTF-8；缺少PowerShell 7时失败，不允许回退到`powershell.exe`。
- 系统边界：Windows PowerShell 5.1是Windows自带组件，不删除系统目录；本项目通过禁止调用实现逻辑撤销。220.12及其他主机必须先独立安装和验收PowerShell 7后再迁移。
- 验收：`pwsh.exe -NoLogo -NoProfile -File .\tools\verify_pwsh7_utf8.ps1`和`python -m pytest -q tests\test_pwsh7_runtime_contract.py`。

## OPS-22012-POWERSHELL7-UTF8-20260810

- 需求：在220.12安装支持中文和UTF-8的PowerShell 7，并让本机到220.12的日常远程命令默认由7执行，同时保持生产服务和现有任务稳定。
- 实现：[跳板入口](../tools/remote_22012_exec.py)、[远端探针](../tools/remote_probe_22012_pwsh7.ps1)、[安装器](../tools/remote_install_22012_pwsh7.ps1)、[验证器](../tools/remote_verify_22012_pwsh7.ps1)、[冒烟](../tools/remote_smoke_22012_pwsh7.ps1)、[清理器](../tools/remote_cleanup_22012_pwsh7_installer.ps1)。
- 数据/安全合同：MSI必须匹配固定SHA-256和Microsoft有效签名；远程脚本使用独立UTF-8文件和短`pwsh.exe -File`；安装过程不得改变8093/8094/8768/8770/5432 PID。
- 任务边界：现有计划任务Action本轮不批量迁移；必须逐任务备份、验证、切换和回滚。
- 结果：PowerShell`7.6.4 Core`、中文回环和6个关键脚本语法通过；五个受保护端口PID不变，无需重启；远端MSI临时文件已删除。
- 任务迁移：2026-08-10已逐项备份并迁移`IMESRealtime`、`HeatPerformanceQualitySync`、`SiV20StrictHourlyPrediction`、`SiV20ScheduledShadowPrediction`到PowerShell 7；任务探针现在检查Action，不能用探针自身为Core来替代任务Action验收。

## OPS-SI-V20-NEW-HEAT-HOURLY-ACCEPTANCE-20260810

- 需求：以首次检查时的最新实际炉次为冻结基线，每小时只读验收220.12 IMES镜像、炉次质量汇总、V20页面、可调定时预测和严格整点预测；一直监控到更晚的新炉次实际平均Si进入页面并与已保存预测闭环，再生成带截图和CSV/JSON证据的最终报告。
- 实现：[验收原子程序](../tools/audit_si_v20_new_heat_acceptance.cjs)、[远端只读探针](../tools/remote_probe_si_v20_acceptance.ps1)、Codex心跳自动化`220-12-v20`和[报告目录](../reports/acceptance/SI_V20_NEW_HEAT_20260810/)；基线一经建立不得重置。
- 通过门禁：新炉次严格晚于基线；实际Si同时出现在status/history；不再作为未开口候选；存在预测关联；页面无错误/横向溢出且两个CSV下载可用；严格整点槽无持续失败、重复、缺口或截止违规。
- 安全边界：生产数据库、任务和控制值只读；验收不补跑预测、不重启服务、不调整设定值。发现异常只记录并持续监督，修复须另行授权。
- 2026-08-10 03:08基线：`2#20260810-130`，平均Si=`0.470%`。8093/8094页面与API、可调60分钟任务、五个受保护端口正常；严格03:00槽为`failed_retryable`，错误为`can't subtract offset-naive and offset-aware datetimes`，因此当前未通过。
- 2026-08-10 04:10复验：最新实际仍为130，131~133本地镜像水位已推进到04:10:25但仍为无正式开口占位；可调60分钟04:00预测成功。严格04:00槽第6次重试仍报同一时区错误，数据库累计4槽中仅1成功、3个`retryable`，重复0、非整点0、截止违规0；继续监控。
- 2026-08-10 08:37修复后复验：最新实际为132，平均Si=`0.400%`；严格01:00~08:00共8槽全部成功。验收曾因132炉`si_available_at`为空失败，定位到计划任务使用旧`standalone_heat_dashboard_8891`同步副本；受控更新后缺失0，端口、任务、API、页面、截图和三类CSV全部通过。自动化保持每小时运行，不因闭环通过而暂停。
- 2026-08-10 08:52持续验收：133炉已自动进入页面，开口`06:50`、堵口`08:30`、平均Si=`0.400%`。严格整点8个预测中6个已完成实际匹配，±0.05命中率`50%`；每小时汇总10行、已评价8行、命中率`37.5%`，继续按小时积累样本。
