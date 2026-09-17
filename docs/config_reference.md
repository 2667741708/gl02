# 配置参考

## V24 配置边界（2026-09-17）

V24不调整模型、keyword检索、单模型限制、11434或计划任务。批准Qwen可驻留；批准:0/:1均合法，但已冻结复测digest不得混合。模型恢复健康不等于原版本对照可继续，须核对标签与实际驻留；独立固定窗口需要单独授权。[证据与剩余方案](handoffs/2026-09-17-qa-v24-latest-reuse-and-code-boundary.md)。

## REQ-QA-STATISTICAL-SCOPE-20260917：发布与评测配置

V22/V23不修改生产模型、keyword检索、单模型驻留或计划任务配置。复测冻结程序/语义目录哈希，批准Qwen两个digest发送前后分层采样；采样不一致停止并保留已发送记录。`BF_QA_RELEASE_CANDIDATE_REQUIRED=1`仅为本机测试门，候选缺失立即失败，不是生产开关。[范围](handoffs/2026-09-17-qa-v23-single-window-routing.md)。

## ERR-QA-MODEL-ALIAS-DRIFT-20260916：同名模型的权重漂移

V21未修改生产模型配置。只读确认`BFOllamaModelSelectionRecovery`自动Repair尝试两个版本并反复改写latest别名；曾出现tags与实际驻留digest不一致。两版本都是允许驻留的Qwen，检查模型名称/就绪布尔值不足以冻结实际版本。共享模型与任务控制须独立授权；[最小维护与恢复方案](handoffs/2026-09-16-qa-routing-v21-paired-retest.md)。

## Qwen驻留核对与诊断更正（2026-09-16）

本轮只读核对8093业务别名实际family=qwen35，已在BF_LLM_MODEL/BF_ALLOWED_LOADED_MODELS内并实际驻留；单加载槽允许该Qwen驻留，不等于禁止Qwen。前轮model_ok=false仅证明就绪检查失败，不能直接证明卸载；异常空列表需要与成功查询缺席分开。[方案与验收](handoffs/2026-09-16-qa-qwen-readiness-concurrency-oracle-plan.md)。本轮未修改生产配置。

## V20 指代趋势追问（2026-09-16）

规划器新增“这个/那个/这些/它们/刚才/上面”指代识别，明确新对象仍优先当前问题。V19失败的30分钟追问现走确定性统计；真实五题与数据库只读来源各5/5通过，模型趋势解释被可信守卫拒绝单列。仅更新8093代理，模型配置不变；整体33项仍执行中。[权威证据](handoffs/2026-09-16-qa-routing-v20-production.md)。

## V18–V19 多轮来源与适配器修复（2026-09-16）

V18/V19未修改模型允许清单、固定模型或其他服务配置。批准模型未驻留导致发送前阻断，恢复后仅续跑未发送题；启动健康与请求级健康分开记录。 [权威证据](handoffs/2026-09-16-qa-routing-v18-v19-production.md)。

## V17 发布配置边界（2026-09-16）

模型及生产路由配置保持；历史复合最多 4 个可分历史子任务，超额或无法分离则明确澄清；原计划禁工具在子计划继续生效。V17 发布仅 `qa_history_compound.py`，26 项精确依赖及 8093-only 守卫核验。[证据](handoffs/2026-09-16-qa-routing-v17-production.md)。

## 智能助手V15完整性与继承边界（2026-09-16）

代码执行和代码示例生成继续禁止，允许正常数据分析。明确最新读取清旧历史窗口；缺失/非法时钟和非法窗口不能继承。原文缓存绑定源及索引内容，章节缓存同时绑定岗位元数据；变更不能复用旧通过结果。未修改模型、数据库或8094配置。[当前V15交接](handoffs/2026-09-16-qa-routing-v15-production.md)。

## 智能助手V14证据单位与就绪合同（2026-09-16）

工具提供单位优先；缺单位仅按现有生产`mcp_host.cross_source_executor._CANONICAL_UNIT_FALLBACKS`规范对象映射复用并公开单位来源，未换算原值；未知映射保持partial。不能从量值或类似名称猜测。
部署就绪最多3次只读GET并记录状态，持续失败仍回滚；不修改Ollama、模型驻留、8094或数据库配置。代码执行和代码示例生成继续关闭。
权威证据：[V10–V14交接](handoffs/2026-09-16-qa-routing-v10-v14-production.md)。

## 工长趋势罐重设定点位（2026-08-14）

正式点位清单当前为 165 行：162 个物理点、3 个派生点。新增物理点
`Hopper_weight_set_01`～`Hopper_weight_set_11` 映射到
`SIO_GL02_LD_T0115/T0116/T0117/T0119–T0126`；派生项 `Hopper_weight_set` 表示同一分钟
11 个状态之和。`T0118` 是圈数设定，不属于该集合。登记入口为
`tools/register_hopper_weight_set_points.py`，默认只读，只有显式 `--apply` 才写
`bf_sensor.sensor_registry`。

派生项当前只登记语义，未配置分钟物化；分量缺失不得按 0 求和。完整生产状态见
[登记交接](handoffs/2026-08-14-hopper-weight-set-registry-production.md)。

## 炉次质量回看同步参数（2026-08-07）

`tools/sync_22012_heat_performance_quality.py` 的关键参数：`--repair-days` 为回看日期范围，`--repair-page-size` 为单页行数（1–500），`--repair-max-rows` 为单轮最大扫描行数（上限50000），`--audit-detail-limit` 为每类缺口明细上限，`--no-repair` 关闭异常回看，`--dry-run` 禁止 PostgreSQL 写入。达到最大扫描行数时必须返回 `repair_truncated=true`。`--dry-run` 的 `repaired` 固定为0，拟修复数量看 `repair_prepared`。

## 8093/8094 每5分钟单炉况智能分析

追踪编号：`REQ-8093-8094-DIAGNOSIS-REVIEW-AI-20260806`

| 环境变量 | 生产值 | 作用 |
|---|---:|---|
| `BF_DIAGNOSIS_AI_ANALYSIS_ENABLED` | `1` | 启用查询、重试和分析功能 |
| `BF_DIAGNOSIS_AI_ANALYSIS_BACKGROUND_ENABLED` | `1` | 启用后台新桶检查；本机固定场景设为0 |
| `BF_DIAGNOSIS_AI_ANALYSIS_BUCKET_MINUTES` | `5` | 按诊断时间划分5分钟桶 |
| `BF_DIAGNOSIS_AI_ANALYSIS_POLL_SECONDS` | `30` | 检查新桶的周期；不是模型调用周期 |
| `BF_DIAGNOSIS_AI_ANALYSIS_RETRY_SECONDS` | `120` | 失败后的最短重试冷却 |
| `BF_DIAGNOSIS_AI_ANALYSIS_HISTORY_LIMIT` | `12` | 进入白名单Prompt的最近诊断点上限 |

数据库复用 `BF_DIAG_REVIEW_PG*` 回环配置，模型复用当前受控模型。8093和8094均显式启用上述变量及 `BF_DIAGNOSIS_REVIEW_ENABLED=1`、`BF_DIAG_REVIEW_REQUIRE_LOGIN=0`。修改启动期变量后只受控重启对应代理；不得重启8768、8770、11434或数据库。8094必须继续使用共享 `ollama_proxy_server.py`，不得恢复过时的8769/隔离代理启动方式。

## 8093/8094 智能助手知识检索模式

追踪编号：`OPS-8093-KNOWLEDGE-KEYWORD-MODE-20260805`

| 配置 | 现行值 | 生效位置 | 作用 |
|---|---|---|---|
| `BF_QA_KNOWLEDGE_SEARCH_MODE` | 8093=`keyword`；8094=`keyword` | 代理服务启动期环境变量 | 让 PostgreSQL 知识库只做关键词/词法检索，不调用 embedding |
| `BF_QA_GUEST_ENABLED` | `1` | 代理服务启动期环境变量 | 是否让未登录局域网访问者进入共享匿名问答；关闭后恢复 `qa_session_required` |
| `BF_QA_GUEST_ROOM_KEY` | 空；回退当前 `Host:Port` | 代理服务启动期环境变量 | 共享匿名房间稳定键；8093/8094 默认隔离，集群多实例需显式设为同值 |
| `BF_QA_MCP_MAX_TOOL_ROUNDS` | `2` | 代理服务启动期环境变量 | MCP 模型规划上限；达到上限后不直接报错，转一次无工具模型回答 |
| `BF_QA_MCP_MAX_TOOL_CALLS` | `4` | 代理服务启动期环境变量 | 单次问答工具调用上限；不建议靠盲目增大掩盖工具合同缺口 |
| `BF_QA_KNOWLEDGE_ENABLED` | 未显式设置，代码默认 `true` | 智能助手后端 | 启用知识库链路 |
| `BF_QA_KNOWLEDGE_INTENT_GATE_ENABLED` | 未显式设置，代码默认 `true` | 智能助手后端 | 仅在知识意图命中时检索 |
| `BF_QA_KNOWLEDGE_TOP_K` | 未显式设置，代码默认 `6` | 智能助手后端 | 限制注入 Prompt 的知识证据数量 |
| `OLLAMA_MAX_LOADED_MODELS` | `1` | `BFOllama11434` | 共享 11434 只允许批准的 27.8B 驻留 |

### 取值含义

- `keyword`：使用 PostgreSQL 关键词/词法候选，保留知识意图门控、证据打包和 Prompt 注入；不请求 embedding。当前 8093/8094 生产链路固定使用此值。
- `vector`：使用 pgvector 与 embedding。不得直接用于当前共享 11434；需要先把 embedding 迁到独立端口/运行时。
- `hybrid`：合并关键词与向量候选。后端代码默认值仍为 `hybrid`，所以环境变量缺失时会回退并可能请求 embedding；在单模型驻留生产链路中应视为配置漂移，不是允许的现行状态。

### 生效与验证

该变量在代理启动时读取，修改服务配置后必须只受控重启对应代理。8093 固定使用 [remote_guarded_deploy_8093_keyword_knowledge_mode.ps1](../tools/remote_guarded_deploy_8093_keyword_knowledge_mode.ps1)，不得直接改 JSON 后只看文件，也不得重启 8094、8768、8770、11434 或数据库。

完成标准必须同时满足：

1. 8093 服务配置包含 `BF_QA_KNOWLEDGE_SEARCH_MODE=keyword`。
2. 8093 实际监听进程环境显示 `keyword`。
3. 不传 `mode` 的 `/api/qa/knowledge/search` 返回 `search_mode=keyword`、`enabled=true` 并有证据。
4. `/api/ps` 仍只驻留批准的 27.8B，没有 `nomic-embed-text`。
5. 一次知识问题 SSE 的准备态显示知识检索启用且未跳过，最终完整收到 `start -> delta -> final -> done`。
6. 验收期间无守卫重启，8768/8094/8770/11434 未发生无关变化。

### 现行证据与回滚

- 2026-08-05 07:25 部署后 8093 配置 SHA-256：`8A24C83DF93008DD8E358682558E8755442D87052A09FB24F39778F2EAF51FDE`。
- 备份：`logs/deploy_backups/8093_knowledge_keyword_20260805_072445`。
- 2026-08-05 08:44 单次真实知识问答：默认 keyword 命中 2 条证据，总耗时 `23.8856s`，报告 `logs/acceptance/8093_keyword_knowledge_20260805_20260805_084403/assistant_keyword_knowledge_sse_once.json`。
- 失败回滚由受控部署器自动执行；手工恢复前必须先核对目标路径和备份内容，恢复后重新验证实际进程环境、默认搜索、SSE、守卫状态和隔离项。

详细 Prompt/RAG 说明见 [8093/8094 Prompt 固定 KV 前缀与知识库回答链路](8093_8094_Prompt固定KV前缀与知识库回答链路_20260805.md)，智能助手复发处理见 [DOCX 修复手册](8093智能助手不可用原因与正式修复手册_20260804.docx)。

## 本机 IMES/Vastbase/Web 转发与 MCP 注册表

追踪编号：`OPS-IMES-LOCAL-MULTI-MCP-RELAY-20260805`

| 项目 | 现行值 | 说明 |
|---|---|---|
| `BF_QA_MCP_SERVER_REGISTRY` | 默认 `高炉前端数据/智能助手/backend/mcp_host/server_registry.json` | 本机注册 `gl02-data`、`imes-readonly`、`imes-web-readonly` |
| `IMES_MCP_CONNECTION_MODE` | `relay` | 本机 IMES/Vastbase MCP 只连 `127.0.0.1:15433` |
| `IMES_RELAY_DB_HOST/PORT` | `127.0.0.1` / `15433` | 220.12 跳板到 `10.10.181.195:5432` |
| `IMES_WEB_URL` | `http://127.0.0.1:18080/imes.web/` | 220.12 跳板到 `10.10.181.209:8080` |
| `IMES_WEB_CAPTCHA` | 当前进程临时值 | 验证码登录时注入，不写文档/日志 |
| `IMES_WEB_SESSION_COOKIE` | 受控进程临时值 | 可选；不读取浏览器 Cookie，不返回会话值 |
| `IMES_DB_USER/IMES_DB_PASSWORD` | 本机受控 env 中的统一只读账号 | 同时作为 `operations` 与 `laboratory` 的默认覆盖；密码不得写入普通文档、日志或接口响应 |
| `IMES_OPS_DB_USER/IMES_OPS_DB_PASSWORD` | 未设置时继承 `IMES_DB_*` | 仅在远端明确配置独立作业账号时覆盖；未配置时兼容历史 `operations` 回退 |
| `IMES_LAB_DB_USER/IMES_LAB_DB_PASSWORD` | 未设置时继承 `IMES_DB_*` | 仅在明确配置实验室账号时覆盖，不由模型自行切换 |
| `IMES_CHEMISTRY_ACCOUNT_PROFILE` | `operations` | 当前远端已实测可读取 2026-08-05 的 065 化验；只有在实验室账号完成授权验收后才可设为 `laboratory` |
| `IMES_ACTIVE_HEAT_MAX_AGE_HOURS` | `72` | 当前炉次活动判定的新鲜度上限；过期未关口记录只作为 `latest_known`，不覆盖正式最新排序 |
| `IMES_HEAT_TIME_RANGE_MAX_HOURS` | `168` | 口语时间段反查炉次的最大跨度，代码硬上限同为168小时；超出时拒绝，避免一次查询过多炉次 |

组合转发入口为 [start_imes_web_vastbase_relay_local.cmd](../tools/start_imes_web_vastbase_relay_local.cmd)，
GUI 为 [imes_web_launcher.py](../tools/imes_web_launcher.py)。组合入口只绑定本机回环，
MCP 查询失败时不得静默切换到 `10.10.181.195:5432` 直连；SSLVPN 是否具备直连路由需单独验收。

## 8093 智能助手自动恢复工具

追踪编号：`OPS-8093-ASSISTANT-AUTO-RECOVERY-20260805`

| 配置 | 默认值 | 约束 |
|---|---|---|
| `BF_22012_HOST` | `10.30.220.12` | 覆盖目标主机；仍必须通过全连通门禁 |
| `BF_22012_USER` | `administrator` | SSH 用户；不得把密码写到普通文档/命令日志 |
| `BF_22012_SSH_PASSWORD` | 无 | 可选受控环境变量；输出只记录变量名，不记录值 |
| 远端 package 根 | `C:\ProgramData\BFV4\assistant-auto-recovery\packages` | ASCII 受控目录；immutable package ID + manifest SHA |
| VPN 恢复上限 | `90s` | 仅必需私网端口不全时启动 aTrust；不计入服务恢复计时 |
| 合并诊断上限 | `120s` | 目标 1–2 分钟完成分类 |
| 单修复阶段上限 | `600s` | 10–15 分钟总服务预算的一部分 |
| SSE 验收上限 | `420s` | 每次 recover 只允许一次 POST，不自动重试 |
| 自动知识模式 | `keyword` | 空值/hybrid 的已知漂移直接恢复；vector 需独立 embedding |
| 自动修复哈希 | 已记录的旧/现行基线 | 未知配置/守卫哈希拒绝覆盖 |

现行包 ID 为 `20260805_v2_72eff4ce55d3`，manifest SHA-256 为 `6459A6DCEC292E27C2F3B85E30046251F35050A44241BB0F1F469A920155467E`。PowerShell 文件按部署字节加 UTF-8 BOM；远端执行固定使用短 `-File` 命令。完整用法见 [CLI](cli_usage.md)，生产分类/修复边界见 [专项文档](8093智能助手自动诊断修复验收工具_20260805.md)。

## 诊断分数高炉大模型复核

追踪编号：`REQ-OPT-MULTI-CONDITION-LLM-REVIEW-20260805`

| 环境变量 | 默认值 | 说明 |
|---|---:|---|
| `BF_DIAGNOSIS_MODEL_REVIEW_ENABLED` | `1` | `0/false/no/off` 关闭只读复核接口；关闭不影响规则建议 |
| `BF_DIAGNOSIS_MODEL_REVIEW_CACHE_SECONDS` | `900` | 相同诊断快照、所选炉况和模型身份的内存缓存秒数；最小按模块约束为 1 秒 |

模型身份继续复用代理服务现有的受控模型配置，不新增浏览器可选内部模型 ID。缓存仅驻留进程内存，重启即清空；接口不写 PostgreSQL，也不保存完整 Prompt/回答到前端。
## 工长趋势独立页端口映射

追踪编号：`OPS-FOREMAN-TREND-STANDALONE-PREVIEW-20260805`

| 配置/地址 | 现行值 | 作用与约束 |
|---|---|---|
| 本机页面/流 | `8092` / `8767` | 本机以 `--db-profile 22012` 时，8767 读取 220.12 PostgreSQL 分钟实际数据。 |
| 220.12 页面/流 | `8093` / `8768` | 生产入口固定为 `/foreman_trend_preview.html?ws_port=8768`；8768 是既有 PostgreSQL 分钟流，不改为 8770 pSpace 秒级流。 |
| 夹具开关 | `fixture=1` | 仅布局校验；显式显示非生产状态，禁止用于生产值验证。 |
| 远端文件根 | `F:\高炉炼铁项目-real-sensor-v2_V4_8093_PREVIEW\高炉前端数据` | 只允许新增/更新该独立页及其专用 CSS、JS；禁止替换正式趋势页。 |

该映射没有新增密钥、数据库连接字段或服务环境变量。更新静态文件后必须使用受控部署器并以带 `ws_port=8768` 的 cache-bust URL 验证。
## 220.12 VPN 直达 IMES/Vastbase/pSpace（2026-08-05）

| 配置 | 当前值 | 说明与风险 |
| --- | --- | --- |
| Nginx IMES 入口 | `10.30.220.12:18080/imes.web/` | 上游固定 `10.10.181.209:8080`；端口根地址302跳转；旧页仍在 `/g13.html` |
| Vastbase 入口 | `10.30.220.12:15433` | Windows v4tov4 portproxy 到 `10.10.181.195:5432`；浏览器不能打开 |
| pSpace 入口 | `10.30.220.12:18889` | Windows v4tov4 portproxy 到 `10.22.181.243:8889`；仍需 SDK/MCP 业务认证 |
| 入站来源 | `10.30.200.18` | 当前 VPN 客户端精确地址；VPN 地址变化后必须受控更新，禁止放开到任意来源 |
| Nginx 标记 | `OPS-22012-IMES-WEB-PROXY-20260805` | 补丁器幂等验收信号；不得手工重复插入 |

这些入口不改变 MCP 的只读账号、SQL 限制或 pSpace 业务认证；它们只改变网络路径。

## pSpace实时流与分钟同步现行配置

追踪编号：`REQ-PSPACE-MINUTE-CANONICAL-AVERAGE-20260805`

| 配置 | 现行值 | 语义 |
|---|---:|---|
| 8770轮询 | 约1秒 | `RealReadList` 当前值桥接；不经过PostgreSQL |
| `continuous_poll_seconds` | 30 | 增量同步循环频率，不是半小时，也不是当前值刷新周期 |
| `continuous_lookback_minutes` | 10 | 每轮回看窗口，用upsert补齐迟到分钟 |
| `source_mode/source_interval_seconds` | `raw / 5` | 读取pSpace约5秒原始历史 |
| `source_aggregate` | `average` | 分钟桶对有效Good raw做算术平均 |
| `target_aggregate/target_interval_seconds` | `PS_RAW_AVERAGE / 60` | 自2026-08-05 21:55起的新分钟标签和间隔 |
| `minute_completion_lag_seconds` | `60` | 查询发起时刻减60秒以前的分钟才标记闭合 |
| `persist_raw_5s/raw_retention_days` | `true / 30` | 同次raw读取写入短期明细并保留30天 |
| 历史回填 | `PS_HIS_AVERAGE / 60` | 另一套历史平均语义 |
| 长期/短期保留 | 3年 / 30天 | 分别对应分钟主表与5秒原始表 |
| 共享单实例锁 | `<项目根>\logs\realtime_sync_pg.lock` | 中文主目录与镜像目录必须争用同一排他锁 |

旧 `PS_RAW_SAMPLE` 截止2026-08-05 21:54保持原标签；配置切换只负责新分钟，不伪装历史。pSpace账号与密码位于220.12 Machine环境变量，禁止写入该配置或普通文档。

## 220.12 8093 四服务 MCP 生产注册表（2026-08-05）

追踪编号：`REQ-22012-IMES-MCP-SYNC-20260805`

| 配置 | 生产值 | 说明 |
| --- | --- | --- |
| `BF_QA_MCP_SERVER_REGISTRY` | `F:/高炉炼铁项目-real-sensor-v2_V4_8093_PREVIEW/高炉前端数据/智能助手/backend/mcp_host/server_registry.json` | 8093 统一服务目录 |
| 已启用服务 | `gl02-data`、`gl02-extended`、`imes-readonly`、`imes-web-readonly` | 传感器/图表、历史炉况/炉身温度、MES数据库、IMES Web |
| `IMES_MCP_CONNECTION_MODE` | `direct_22012` | 生产机直连厂内数据库，不使用本机回环转发 |
| `IMES_RELAY_DB_HOST/PORT` | `10.10.181.195:5432` | Vastbase 只读入口；凭据值来自 Machine 环境变量 |
| `IMES_ACTIVE_HEAT_MAX_AGE_HOURS` | `72` | 防止历史未关口记录被误认为当前炉次 |
| `IMES_WEB_URL` | `http://10.10.181.209:8080/imes.web/` | 220.12 到 IMES Web 的厂内上游 |

`22012_BFV4PreviewProxy8093.json` 只登记 `IMES_DB_*`、`IMES_WEB_*` 等 Machine
环境变量名，禁止把密码或 Cookie 值写入注册表、普通文档、部署结果和 MCP 响应。
IMES Web MCP 即使已注册，也仍需有效登录态/验证码；数据库 MCP 可独立正常运行。

## 8093 部署互斥与 Failed to fetch 页面容错（2026-08-06）

追踪编号：`REQ-8093-ASSISTANT-FETCH-RESILIENCE-20260806`

| 配置/合同 | 现行值 | 作用 |
| --- | --- | --- |
| 全局命名互斥 | `Global\BFV4PreviewProxy8093Deployment` | 阻止多个新部署/恢复流程并行停启 8093 |
| 服务恢复退避 | `15s`，最多 `2` 次启动 | 等待旧进程/SCM 竞态收敛，不形成快速重启环 |
| 只读 GET | 最多 3 次，退避 `1.5s/3s` | 吸收短暂端口或反向代理抖动 |
| 问答 POST/SSE | 自动重试 `false` | 禁止重复会话、重复模型推理和重复工具调用 |
| 页面运行标记 | `OPS-8093-QA-FETCH-RESILIENCE-20260806` | 诊断器识别容错页面是否实际上线 |
| 页面 SHA-256 | `4394D60B059CD65BDDA16D63A680F19B57880B6822C6ECE87A4190AFEAAFAC00` | 2026-08-06 10:41 生产热更新基线 |

8093 实际知识检索继续固定为 `BF_QA_KNOWLEDGE_SEARCH_MODE=keyword`；现行多 MCP 配置已验收 SHA-256 为 `7541DB038ADD3CAB3F7DBDC6205117D049F4C440C636037EE92A5CC0E9517C5B`。页面容错不改变 Prompt、RAG、MCP、数据库或模型配置。

## 炉况19项核心证据（2026-08-06）

追踪编号：`REQ-8093-8094-DIAGNOSIS-CORE-19-TRENDS-20260806`

本功能不增加环境变量和数据库连接。它复用既有只读诊断/分钟值/基线连接；`/api/diagnosis-core-evidence`不调用模型，因此不依赖Ollama、调剂引擎或知识库完成。智能详细分析仍由既有 `BF_DIAGNOSIS_AI_ANALYSIS_ENABLED` 与5分钟桶配置控制，两条链路不得再次合并成同一可用性门槛。

## 当前项目数据库同步模块快照（2026-08-07）

追踪编号：`REQ-IMES-MATERIAL-FUEL-AUDIT-AND-DB-MODULE-SYNC-20260806`

| 配置 | 路径 | 口径 |
| --- | --- | --- |
| 点位清单 | `数据库同步和存取/config/点位清单.tsv` | 153行：151物理、2派生；确认项19项；新增 `CO_top=SIO_CC_GF2_T0112`、`CO2_top=SIO_CC_GF2_T0113`、`H2_top=SIO_CC_GF2_T0111` |
| 同步配置 | `数据库同步和存取/config/sync_config.json` | pSpace raw约5秒、分钟有效样本平均、30秒轮询、10分钟回看、分钟3年、raw30天 |
| IMES清单 | `数据库同步和存取/config/IMES可读数据清单.tsv` | IMES Web接口、业务标签、目标表、时间范围与补采边界 |
| 同步清单 | `数据库同步和存取/module_sync_manifest.json` | 43个白名单文件的字节数和SHA-256 |

快照不包含 `.env` 或明文密码。料速和燃料比尚未加入点位清单或正式派生表；其候选公式和待确认语义见 [专项报告](IMES料速与燃料比只读核验_20260806.md)。

## 工长趋势同步配置入口（2026-08-07）

| 配置/入口 | 现行口径 | 验收重点 |
| --- | --- | --- |
| `数据库同步和存取/run_realtime_sync_pg_bg.ps1` | 每轮显式传 `--config <ScriptRoot>\\config\\sync_config.json` | 不能依赖当前工作目录或 Python 默认路径 |
| `config/sync_config.json:point_catalog_tsv` | `数据库同步和存取/config/点位清单.tsv` | 当前 165 行、162 物理点、3 派生点；2026-08-07 部署基线为153/151/2 |
| `tools/remote_deploy_foreman_points_coal_20260806.ps1` | 入口、配置、清单和注册器同包原子替换 | 注册确认19项后再恢复 `BlastFurnaceV3PgContinuousSync30s` |

一次失败部署曾留下“注册表已更新、清单回滚、`tags_ok=148`”的部分状态；后续必须用入口哈希、清单标记、`sync_runs.tags_ok` 和新增点 `one_minute_values` Good 行共同验收。

2026-08-07 已完成上述受控部署：入口与配置哈希已和本机候选一致，最近完成同步轮次为 `tags_ok=151,tags_error=0`，CO/H2/CO2 及三项 BT 点均有最新 Good 分钟值。

## REQ-ABC33-FURNACE-RULES-20260807

唯一可编辑数值配置为 [abc_furnace_rules.v1.json](../自动诊断服务/config/abc_furnace_rules.v1.json)。`quality` 定义覆盖率、最大数据年龄和窗口；`score_bands` 固定 A 维护分、B 55分黄色/70分琥珀/85分确认、C 70分红色报警；`rules` 必须完整包含 A1–A9、B1–B13、C1–C11。公式实现来自 [abc_rule_engine.py](../自动诊断服务/abc_rule_engine.py)，JSON 不执行任意表达式。
当前已显式登记手册中的公共阶段阈值：`TopTempRange=10..35`、`TopPressRange=8..25`、`DPHigh=0.8..1.5`、`PIBad=0.6..1.2`；其余阶段阈值继续由 `z60_default/z15std_default` 和后台发布流程维护。

## 220.12炉体温度回放配置（2026-08-08）

| 配置 | 值/来源 |
|---|---|
| 页面 | `http://10.30.220.12:8892/` |
| 计划任务 | `\BlastFurnaceServices\SoftZoneTemperatureReplay8892`，SYSTEM、开机启动、失败重试3次 |
| 远端根目录 | `F:\高炉炼铁项目-real-sensor-v2_V4_8093_PREVIEW` |
| 数据库配置 | 复用受控只读配置`tools\service_configs\22012_BFV4PreviewProxy8093.json`，API和日志不输出凭据 |
| 数据范围 | 最多72小时、最多720帧；默认6小时、5分钟步长 |
| 防火墙 | `BlastFurnaceSoftZoneReplay8892`，仅Domain/Private TCP 8892 |
| 日志 | `logs\soft_zone_replay_8892.log` |

远端V4当前没有C2根部代理模块，`cohesive_available=false`。这是可选覆盖层，不影响80点炉体温度回放。

## 传感器曲线统一交互（2026-08-11）

220.12 上运行的 8093 工长趋势、8094 趋势分析、8095 预览、8096 基线影子页以及 8892 炉体历史曲线统一支持：时间范围按整小时（`step=3600`）调整，`−1h/+1h`移动窗口；在曲线上右键会显示点位ID、曲线值和原始时间戳。8093/8094/8095/8096 的 ECharts 图表使用共享 `高炉前端数据/assets/curve-inspector.js`（8096 同步到其旧版 V3 前端 `assets` 目录），8892 的温度/静压力 Canvas 使用页面内命中检测。该交互只读，不改变 8768 分钟历史、8770 pSpace 实时桥或数据库采集链路。

2026-08-11 生产验收：8093 备份为 `curve_inspector_8093_20260811_180912`，8094 备份为 `curve_inspector_8094_20260811_181624`，8095 备份为 `curve_inspector_static_8095_20260811_182215`，8096 备份为旧 V3 根目录下 `curve_inspector_static_8096_20260811_182358`；8093/8094/8095/8096/8892 HTTP 均为 200，统一检查器资源可读，受保护端口 PID 未变化。

## 软熔带移动特征融合配置（2026-08-10）

配置文件：[cohesive_zone_intelligent_diagnosis.yaml:L1-L209](../炉况规则引擎/config/cohesive_zone_intelligent_diagnosis.yaml#L1-L209)。

| 字段 | 类型/默认值 | 含义与风险 |
|---|---|---|
| `model.confidence_cap` | `float / 0.45` | 未标定诊断置信度上限；加载器拒绝大于0.45的值 |
| `model.control_use` | `string / prohibited` | 固定禁止自动控制；加载器拒绝其他值 |
| `time.current_window_minutes` | `int / 15` | 当前窗口长度 |
| `time.reference_window_minutes` | `int / 15` | 历史参考窗口长度 |
| `time.reference_separation_minutes` | `int / 15` | 当前与参考窗口间隔离区，防相邻噪声混叠 |
| `time.max_age_minutes` | `int / 5` | 每个特征最新样本年龄上限 |
| `decision.stable_score_threshold` | `float / 0.18` | 合成分数在正负阈值内判稳定 |
| `decision.min_scored_features` | `int / 4` | 形成诊断的最少有权重特征数 |
| `decision.required_groups` | `list` | 必须至少覆盖压力/透气性和温度场两组 |
| `features.*.columns` | `list[string]` | 同一概念的受控字段别名；按配置选择或聚合 |
| `features.*.valid_min/max` | `float` | 单位相关有效范围；越界值转缺失，不钳制成正常值 |
| `features.*.delta_scale` | `float` | 当前相对参考变化归一化尺度；修改会改变灵敏度 |
| `features.*.direction_up` | `-1/0/1` | 当前值上升对软熔带上移证据的方向；0只保留上下文 |
| `features.*.movement_weight` | `float>=0` | 移动方向融合权重；压力/透气性保持最高权重 |
| `features.*.risk_links` | `mapping` | 只形成关联证据，不改现有8类炉况分数 |

验证：[verify_cohesive_zone_intelligent_diagnosis.ps1:L1-L41](../tools/verify_cohesive_zone_intelligent_diagnosis.ps1#L1-L41)。没有现场标定前，不得提高置信度上限或取消禁止控制标签。

## V20 平均 Si 影子工作台配置（2026-08-08）

追踪编号：`REQ-SI-V20-8093-8094-SHADOW-WORKBENCH-20260808`

| 配置 | 默认值 | 说明 |
|---|---|---|
| `BF_SI_V20_MODEL_PATH` | `智能助手/backend/models/si_v20_history_portable_v1.json.gz` | 便携 ExtraTrees 模型路径 |
| `BF_SI_V20_REQUIRE_LOGIN` | `false` | V20预测与回放默认无需登录；仅在未来明确恢复权限时设为 `true` |
| 数据库连接 | 复用 `BF_HEAT_PERFORMANCE_*` / `GL02_*` | 不新增明文凭据 |
| 模型状态 | `experimental_shadow` | 不替换生产默认模型 |

8093/8094 共用同一模型和审计表；取消登录后的最新部署备份位于远端 `backups/si_v20_shadow_20260808/20260808_131338`。

### V20 访问与本地数据库边界

- 2026-08-08 用户明确要求 V20 不配置生产账号；`predict/replay` 允许所有能访问8093/8094页面的用户执行。
- 该设置不改变后台管理、人工复核和其他接口的既有权限；`BF_LOGIN_*` 与会话配置不再是 V20 依赖。
- 数据库：V20 复用 220.12 本机 `GL02_*`/`BF_HEAT_PERFORMANCE_*` 连接，只读本机同步数据。平均Si的上游业务来源仍是IMES铁水化验，但由独立同步程序提前实时/回看下载到220.12；不得从V20请求链实时访问外部IMES。

## 工长趋势 pSpace 实时扩展（2026-08-08）

| 配置/入口 | 口径 |
|---|---|
| 既有任务 | `\BlastFurnaceServices\V4BillboardPspace8770`，使用 `V3/tools/pspace_8092_realtime_bridge.py` |
| 页面 | `http://10.30.220.12:8093/foreman_trend_preview.html?ws_port=8768&pspace_ws_port=8770` |
| 页面资源版本 | `20260806-pspace-extra-r3` |
| 实时合同 | 157 个流值、133 个Billboard值、17 个工长扩展值；扩展值缺失保持 `--`，不补零 |
| 数据源 | 既有 pSpace 采集链；本次不新增读取进程或上游连接 |
| 验收 | `tools/verify_billboard_pspace_8770.py`、`tools/inspect_foreman_trend_remote_points.cjs` |
## 220.12 IMESRealtime 一分钟调度（2026-08-09）

追踪编号：`OPS-IMES-REALTIME-1MIN-20260809`

| 配置 | 当前值 | 说明 |
|---|---:|---|
| 计划任务 | `\GL02SensorSync\IMESRealtime` | 原Action与Principal保持不变 |
| 重复周期 | `PT1M` | 每一分钟尝试触发 |
| 重叠策略 | `IgnoreNew` | 上一轮未结束时不启动重叠实例 |
| 部署器 | `tools/set_22012_imes_realtime_1min.ps1` | 自动备份任务XML并在失败时恢复 |
| 下游汇总周期 | 5分钟 | `HeatPerformanceQualitySync`本次未修改 |

单轮IMES同步实测可能超过两分钟，因此`PT1M`不等于每分钟必然完成一轮；实际完成频率受单轮耗时和`IgnoreNew`共同约束。完整证据见[部署记录](handoffs/2026-08-09-imes-realtime-1min.md)。
# V20可配置预测周期（2026-08-09）

| 配置 | 默认 | 可选值 | 保存位置 | 说明 |
|---|---:|---|---|---|
| `cadence_minutes` | `60` | `1/10/30/60/1440` | `bf_assistant.si_v20_prediction_schedule` | 生产自动预测周期；分别对应1分钟、10分钟、30分钟、1小时和1天 |
| `enabled` | `true` | `true/false` | 同上 | 启用或暂停后台预测；不影响历史查询 |
| `furnace_no` | `2` | 数字炉号 | 同上 | 当前工作台默认2号炉 |
| 分发任务周期 | `1min` | 固定 | `\BlastFurnaceServices\SiV20ScheduledShadowPrediction` | 只负责检查配置是否到期，页面改周期不修改该任务 |

`cadence_minutes`不是传感器采样间隔，而是生成预测审计点的间隔。模型在每个时间槽仍按自己的历史Si和截止时间窗口构建输入。生产仍为影子模式，不允许通过该配置写控制设定值。

## ABC33 30天基线配置（2026-08-09）

|配置|生产值|说明|
|---|---:|---|
|`baseline_days`|30|基线日之前的连续30个完整自然日|
|`minimum_effective_coverage`|0.75|137项必需原始/派生基线的失败关闭门禁|
|普通状态量最大保持|5分钟|仅用于状态语义，不跨长断档、不补零|
|炉体温度最大保持|15分钟|适配变化触发/非满分钟上报|
|`T_top`对齐|四点各自最多保持5分钟后同分钟求均值|四点不齐则该分钟不生成派生值|
|`T_taphole_mean`对齐|严格同分钟|两个铁口任一点缺失则该分钟不生成均值|
|膨胀罐液位|分钟观测→小时均值→日均值→30日分位数|不按43200个分钟点计算覆盖率|

每日入口为 `tools/run_v4_daily_baseline.ps1`，历史重建入口为 `tools/run_abc33_baseline_rebuild.ps1`，严格验证入口为 `tools/verify_abc33_baseline_coverage.py`。完整生产状态见[交接记录](handoffs/2026-08-09-abc33-baseline-coverage-repair.md)。

## V20严格整点预测配置（2026-08-10）

|配置|默认值|说明|
|---|---:|---|
|`BF_SI_V20_STRICT_MODEL_PATH`|`智能助手/backend/models/si_v20_strict_context_lgbm_v1.json.gz`|7549特征、420树的便携完整上下文模型|
|严格任务周期|1分钟|只检查/重试整点槽，不改变60分钟槽边界|
|补槽回看|24小时|首次运行或短时故障后补齐；历史大范围回放需显式离线执行|
|重试间隔|1分钟|失败槽保留，不推进成成功|
|任务名|`\BlastFurnaceServices\SiV20StrictHourlyPrediction`|独立常开，不受操作者配置影响|

严格通道只读220.12本地业务库；禁止在预测请求中访问外部IMES。炉料化学本地镜像不可用时保留缺失与水位审计，不回退外部连接。

## HCZ专家弱标签配置（8892，2026-08-10）

服务复用8093托管配置中的GL02只读连接和诊断复核写库配置，但只读取显式白名单环境变量。写库必须为本机回环地址：`BF_DIAG_REVIEW_PGHOST/PGPORT/PGDATABASE/PGUSER/PGPASSWORD[_ENV]/PGSCHEMA`。现场无登录模式由`BF_DIAG_REVIEW_REQUIRE_LOGIN=0`、`BF_DIAG_REVIEW_ANONYMOUS_USERNAME`和`BF_DIAG_REVIEW_ANONYMOUS_ROLE`控制；浏览器传入的身份字段无效。

固定限制：单窗口最多72小时、请求体64KB、备注2000字符、中心高度10–35m、厚度0.5–8m、可信等级1–5、历史单次最多2000条。配置与实现见[hcz_expert_label.py](../高炉前端数据/智能助手/backend/hcz_expert_label.py)和[soft_zone_replay_server.py](../tools/soft_zone_replay_server.py)。

## HCZ上移综合趋势经验规则配置（8093，2026-08-10）

配置文件：[hcz_upward_expert_rule.yaml](../炉况规则引擎/config/hcz_upward_expert_rule.yaml)。

| 配置 | 固定值 | 说明 |
|---|---:|---|
| `windows.current_hours` | 24 | 当前小时窗 |
| `windows.baseline_days` | 5 | 当前窗之前连续基准天数 |
| `windows.required_consecutive_hours` | 12 | 完整组合的最小连续小时 |
| `coverage.min_core_samples_per_hour` | 30 | 核心指标每小时最小分钟点数 |
| `coverage.min_body_sectors_per_layer_hour` | 4 | 炉壁层小时均值最少方位数 |
| `coverage.min_current_valid_hours` | 18 | 当前24小时最少有效小时 |
| `coverage.min_baseline_valid_hours` | 96 | 前120小时最少有效小时 |
| `body_temperature.min_rising_layers` | 2 | 升温10℃触发层数 |
| `body_temperature.strong_rising_layers` | 3 | 强证据层数；同时要求至少1层升20℃ |

五项阈值分别为顶温`+15℃`、全压差`+5kPa`、PI`-0.5`、GasUtil`-1个百分点`、冷风风压`P_blast_cold`上升`+5kPa`。2026-08-11已明确禁止把热风压力`P_blast`仅改名冒充冷风风压。任何变更都必须保留`automatic_control: prohibited`并同步规则文档、测试和部署证据。

页面历史试算允许在不修改生产配置的前提下临时调整上述五项阈值，以及炉壁升温阈值`0～40℃`、方向层数`1～7`、连续小时`1～24`；历史范围只允许`7/30/90`天。顶温、全压差、PI、煤气利用率、冷风风压的合法范围分别为`0～40℃`、`0～20kPa`、`0～5`、`0～10个百分点`、`0～20kPa`。这些值仅作为单次查询参数，不落库、不更新YAML。

`GasUtil`源值固定按0～1比例解释，API入口乘100后参与“百分点”比较。页面当前值和前五天基线使用`%`；差值及阈值使用“个百分点”，禁止重复乘100。

## 220.12持久SSH会话配置（2026-08-10）

| 配置 | 默认值 | 说明 |
|---|---|---|
| `BF_22012_HOST` | `10.30.220.12` | 会话固定远端；切换时先显式stop旧会话 |
| `BF_22012_USER` | `administrator` | 与状态身份严格匹配 |
| `BF_22012_PROJECT_ROOT` | `F:\高炉炼铁项目-real-sensor-v2_V4_8093_PREVIEW` | 8093受控部署工作目录 |
| `BF_22012_SSH_PASSWORD` | 无 | 首选凭据环境变量；值不写状态、日志或Skill |
| keepalive | 30秒 | Paramiko SSH协议保活；不是应用命令 |
| monitor | 请求时 | 请求之间发现失效transport后才重连；在途命令不重放 |
| 状态文件 | `%LOCALAPPDATA%\Codex\ssh-sessions\22012.json` | 仅localhost代理端口、随机令牌、PID、会话/远端身份；不在仓库 |

### Windows 凭据管理器恢复边界（2026-08-14）

| 配置 | 固定值 | 约束 |
|---|---|---|
| 授权目标 | `TERMSRV/10.30.220.12` | 不允许通配或改用于其他主机/协议 |
| 预期用户 | `administrator` | 读取后只比较用户名，不输出秘密 |
| 恢复入口 | `tools/restore_22012_ssh_secret_from_windows_credential.ps1` | 仅 PowerShell 7；输出不含密码、长度、哈希 |
| 受控回退 | `C:\Users\hmw20\.codex\secrets\reliable-ssh-10-30-220-12.password` | 仅 Windows 不导出秘密时使用；必须先验证 Owner、继承保护和允许 ACE |
| 密码文件 | `%LOCALAPPDATA%\Codex\secrets\reliable-ssh\22012.pw` | 仅当前用户和 `SYSTEM` 完全控制；禁止进入 Git/日志/模型上下文 |
| 验收 | 两次 `configure_22012_reliable_ssh_secret.ps1` + 一次全新 SSH 登录 | 两次配置必须是独立 `pwsh -File` 进程 |

该恢复授权只修复本机认证材料，不自动授权远程文件写入、服务停启或数据库操作。Reliable SSH MCP
可用于已授权的 220.12 操作，但必须先通过主机身份校验并保持 `automatic_replay=false`。

入口为`tools/start_remote_22012_session.ps1`、`tools/remote_22012_session.py status/run`和显式`tools/stop_remote_22012_session.ps1`。`run`不自动重放传输中断的命令；部署者必须先核对远端实际状态。

## Reliable SSH MCP 220.12连接池配置（2026-08-10）

配置位置：`C:\Users\hmw20\.codex\config.toml`的`mcp_servers.reliable_ssh_10_30_220_12`。

| 参数 | 值 | 作用 |
|---|---:|---|
| `--ssh-flavor` | `plink` | Windows密码认证与固定主机公钥 |
| `--remote-python` | `python` | 220.12 Windows远端runner入口 |
| `--pool-size` | `1` | 单服务器MCP维持一个认证连接；0关闭 |
| `--keepalive-interval` | `30`秒 | SSH协议层保活 |
| `--heartbeat-interval` | `60`秒 | 常驻runner的只读`probe_identity`应用心跳 |
| `--connect-timeout` | `8`秒 | 初次连接阶段超时 |
| `--command-timeout` | `25`秒 | 默认远端操作超时，部署器可显式提高 |

连接池状态通过MCP工具`connection_status`或`tools/reliable_ssh_22012_cli.mjs pool-probe`查看。修改`config.toml`后需重新加载对应MCP进程；不能把密码复制到参数、日志或文档。掉线后的连接只在后续请求前重建，在途命令不重放。

## Codex经济型委派参数

| 参数 | 默认值 | 说明 |
| --- | --- | --- |
| `-Model` | `gpt-5.6-luna` | 每次先从`codex debug models`实时目录验证 |
| `-ReasoningEffort` | `low` | 支持值必须同时出现在该模型目录中 |
| `-Sandbox` | `read-only` | `workspace-write`还必须显式给出`-AllowWorkspaceWrite` |
| `-PersistSession` | false | 默认`--ephemeral`，避免无关历史上下文 |
| `-UseUserConfig` | false | 默认不加载用户MCP/配置，减少工具面与启动成本 |
| `project_doc_max_bytes` | `4096` | 委派专用内联覆盖，不修改全局Codex配置 |

委派入口还默认禁用apps、plugins、browser、computer、image和tool suggestion。以上是单次CLI覆盖，不改变主Codex应用或当前会话配置。

## 8093静态压缩配置

| 配置 | 默认值 | 说明 |
| --- | --- | --- |
| `BF_HTTP_COMPRESSION_MIN_BYTES` | `1024` | 低于此字节数不压缩；文本、HTML、JS、CSS、JSON、SVG参与协商 |

Brotli库为可选能力；缺失时服务仍可启动并回退gzip。HTML保持`no-store`，带哈希或显式版本的静态资源使用一年`immutable`缓存。

## 8093部署Skill项目镜像同步参数

| 参数 | 默认值 | 说明 |
| --- | --- | --- |
| `-Action` | `Verify` | `ImportGlobalToProject`仅首次导入/恢复；`PublishProjectToGlobal`从项目版本源发布到全局运行镜像；`Verify`只比较精确清单和哈希 |
| `-GlobalSkillPath` | 当前用户`.codex\skills\deploy-8093-guarded-update` | 允许显式指定Codex运行镜像目录；项目源固定为仓库`.codex\skills\deploy-8093-guarded-update` |

同步入口为`tools/sync_deploy_8093_guarded_update_skill.ps1`，固定要求PowerShell 7 Core和UTF-8。它只处理14个白名单文件；发现额外文件、缺失文件或bundle SHA-256差异时失败，不删除文件，也不连接220.12。

## 8093维护交接包配置

| 配置 | 默认值 | 说明 |
| --- | --- | --- |
| `-ManifestPath` | `tools/handoff/8093_handoff_manifest.json` | 交接包明确白名单、顶层说明源和禁止路径片段 |
| `-OutputDirectory` | `handoff_packages` | 本地ZIP与临时暂存目录；已被Git忽略 |

构建器固定拒绝`.env`、私钥/证书容器扩展名、数据库账号文档、日志、备份和数据目录，并扫描私钥头、常见访问令牌、带用户口令的数据库URI及明文字面量密钥赋值。

## V3本机原生PostgreSQL启动配置（2026-08-11）

| 配置 | 默认值 | 必需 | 使用位置 | 风险与验证 |
| --- | --- | --- | --- | --- |
| `GL02_LOCAL_PGHOST` | `127.0.0.1` | 是 | `start_v3_full.ps1`、本地同步子进程 | 只允许获批本机目标；启动输出核对目标但不输出密码 |
| `GL02_LOCAL_PGPORT` | `18000` | 是 | 同上 | 用服务、监听和`SELECT version()`验证，不依据客户端版本猜测 |
| `GL02_LOCAL_PGDATABASE` | `bf_trend` | 是 | 助手、诊断、实时桥接和同步目标 | 缺少所需schema时只能运行降级/fixture测试 |
| `GL02_LOCAL_PGUSER` | `postgres` | 是 | 启动器复制到`GL02_PGUSER` | 可由获批本机运行角色覆盖；不得使用远端只读角色冒充本机写账号 |
| `GL02_LOCAL_PGPASSWORD` | 无 | 是 | 仅当前进程环境 | 不写脚本、普通文档或日志；缺失时正常启动失败 |
| `BF_USE_EXISTING_PG_ENV` | 未启用 | 否 | `start_v3_full.ps1`主连接选择 | 只有`1/true/yes`保留既有`GL02_PG*`；本地同步仍使用`GL02_LOCAL_PG*` |

默认模式为`local-native`，会覆盖用户级环境中可能指向220.12的`GL02_PGHOST/PORT/DATABASE/USER/PASSWORD`。
历史 Docker `15432` 不再是该入口的默认值或回退目标。

## ABC33 上下文助手

| 环境变量 | 默认值 | 说明 |
|---|---:|---|
| `BF_ABC_RULE_ASSISTANT_PROMPT_VERSION` | `abc_rule_explanation.v1` | 首轮解释缓存版本；改变即生成新缓存 |
| `BF_ABC_RULE_ASSISTANT_WAIT_SECONDS` | `300` | 同上下文并发等待唯一 owner 的最长秒数 |
| `BF_ABC_RULE_ASSISTANT_CONTEXT_MAX_BYTES` | `262144` | 完整不可变解释快照上限 |
| `BF_ABC_RULE_ASSISTANT_PROMPT_CONTEXT_MAX_BYTES` | `24576` | 注入模型的有界单炉框上下文上限 |

知识库继续使用 `BF_QA_KNOWLEDGE_SEARCH_MODE=keyword`；模型仍只驻留一个。
### 8093 MCP 并行规划（REQ-8093-MCP-PARALLEL-5-AND-GUEST-DEPLOY-20260813）

- `BF_QA_MCP_MAX_TOOL_ROUNDS=5`：一次问答最多进行 5 轮模型规划。
- `BF_QA_MCP_MAX_TOOL_CALLS=5`：一次问答累计最多执行 5 个工具请求，跨轮次合计。
- `BF_QA_MCP_PARALLEL_TOOL_CALLS=1`：允许同一规划轮内的独立只读工具调用并行执行。
- `BF_QA_MCP_MAX_PARALLEL_TOOL_CALLS=5`：单轮并行协程上限为 5；同一 MCP server 的 stdio 调用仍由服务级锁串行。
- 并行不会放宽工具白名单、JSON Schema、参数大小、单工具超时或整次执行预算。超过上限或工具失败时只进行一次禁用工具的模型降级回答，并明确实时数据未核实。
## 220.12 每两小时更新同步配置

| 配置项 | 当前值 | 说明 |
|---|---|---|
| 事项编号 | `OPS-22012-BIDIRECTIONAL-SYNC-20260813` | 服务器更新检测、本地同步与 Git 版本保存 |
| 自动任务 ID | `220-12` | Codex 项目级本地自动任务 |
| 执行频率 | 每两小时 | 无更新时只保存轻量检查记录，不创建空版本 |
| 本地项目 | `D:\文件\冀南钢铁运行中第二版本` | 运行前必须保存 `git status --short` 基线 |
| 远端项目 | `F:\高炉炼铁项目-real-sensor-v2_V4_8093_PREVIEW` | 本任务仅允许只读探测与脱敏快照 |
| 运行证据 | `reports/server_sync/` | Git 忽略目录，保存快照、候选、状态和报告 |
| Git 保存 | 精确 pathspec commit + 唯一本地 annotated tag | 禁止全量暂存、amend、强制覆盖 tag 和外部 push |

敏感路径、运行日志、备份、数据库、模型权重、缓存、虚拟环境、依赖目录和浏览器认证状态不进入监视或同步范围。本地与远端同文件并行变化时状态必须为 `conflict_needs_review`，不得自动覆盖。

### V4 QA工作流本机候选策略值

- 状态：候选，未部署；2026-09-16；权威实现为[时间窗模块](../高炉前端数据/智能助手/backend/qa_time_window_plan.py)与[报表模块](../高炉前端数据/智能助手/backend/qa_report_workflow.py)。未修改生产模型或路由环境变量。
- 时间：Asia/Shanghai、一个请求锚点、秒精度适配器、每窗不超过24小时；调用数仍受现有QA_MCP_MAX_TOOL_CALLS与请求时间预算约束。
- 基线：30日；MIN_BASELINE_COVERAGE=0.8是证据质量门，未标定为生产报警规则。时间晚于查询起点、截断或IQR无效时拒用。
- 报表：目录limit=20，正文max_chars=10000仍由工具系统上限夹紧；摘录最多2500字符，缩短即标记范围不完整。
## QA V8/V9 当前验收增量（2026-09-16）

V8/V9未修改生产路由环境、模型配置或工具预算。正式文档执行器单页目标9000字符、完整单块上限30000字符、索引最多2000片段；超限不截表格或伪称全文完成。代码执行及代码示例继续禁用。见[V8/V9交接](handoffs/2026-09-16-qa-routing-v8-v9-production.md)。

## QA V5 固定预算（2026-09-16，候选）

模型解析仅查询已驻留允许清单，最多3次`GET /api/ps`，总体6秒预算，每次最多2秒、间隔0.2秒；
取消检查贯穿复核。没有新增模型加载、驻留数量或知识检索模式配置。
历史检索上限10条、摘录600字符，绑定服务端owner和当前消息ID；无身份范围旧MCP入口关闭。
见[V5交接](handoffs/2026-09-16-qa-routing-v5-local-candidate.md)。

## QA V6预算增量（2026-09-16，候选）

多轮查询状态超过600秒、主题切换或禁止实时时不继承旧对象/窗口，上一轮数值证据不复用。无工具模型输出720 token检测长度终止，同请求最多一次720 token压缩补答，目标最多250汉字；不盲目扩大工具轮数、加载数量或改变keyword模式。[权威交接](handoffs/2026-09-16-qa-routing-v5-production-and-v6-candidate.md)。

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
没有新增配置。唯一底座及权重摘要固定，不改Ollama驻留上限或keyword模式。两次独立GET快照先身份不符、后别名符合但驻留为空；旧管理器hash未变，不能声称生产已锁定。管理器/恢复计划任务安装仍待单独授权，不自动加载、卸载或切换模型以继续测试。
权威：[确认缺陷、实现及生产依赖](handoffs/2026-09-17-qa-v32-latest-evidence.md)、[机器证据](../tests/qa_regression/latest_evidence_candidate_20260917.json)、[实际函数回归](../tests/test_qa_latest_evidence.py)、[九条提出归类补充](../tests/qa_regression/unmapped_triage_supplement_20260917.json)。本轮0线上问题，不改首次1233题判定，822原题复测仍待完成。

## 2026-09-17：审计连接配置

[readonly_pg_connect](../tools/qa_readonly_pg.py#L59)复用进程内受控PG环境参数，不打印或缓存凭据。连接启动固定default_transaction_read_only=on、autocommit=False、已校验schema/bf_sensor/public搜索路径，statement_timeout默认20000ms（范围1..60000且拒绝bool）、lock_timeout=3000ms、connect_timeout封顶8s；不使用普通池/初始化。此为审计进程配置，不改生产服务或数据库schema，固定模型名称/摘要继续保持。
权威：[缺陷、验证和发布边界](handoffs/2026-09-17-qa-readonly-audit-and-source-repair.md)。

## REQ-QA-SOURCE-SCOPE-20260917：私有源冻结配置

固定原DOCX/hash及唯一底座，候选搜索为keyword，embedding_generation=false。输出必须为Git忽略的`.codex_runtime/qa-source-scope-20260917`下全新子目录；已有目录只读恢复，不重放覆盖。源manifest与文档候选hash互相绑定，生产更新预期旧authority使用CAS，不放宽为任意文档替换。当前无生产环境变量、模型或数据库配置修改。
权威：[冻结身份、目录及受控发布门](handoffs/2026-09-17-qa-independent-source-scope.md)、[机器证据](../tests/qa_regression/source_scope_candidate_20260917.json)。

## REQ-QA-KEYWORD-SOURCE-RELEASE-20260917：keyword发布准备合同

无生产配置修改。doc_id/原源/candidate/manifest SHA固定；准备器只接收已只读复核的v1.0-hierarchical旧authority及5454索引/向量基线，规划新5587行keyword且embedding_generation=false。输出为Git忽略source-scope下全新目录，源路径沿用旧doc，模型唯一底座保持。DDL与单文档事务须另获数据库写入授权，不因计划或源码存在而执行。
权威：[私有计划与授权/验收边界](handoffs/2026-09-17-qa-keyword-source-release-preparation.md)、[脱敏证据](../tests/qa_regression/keyword_source_release_preparation_20260917.json)。

## REQ-QA-KEYWORD-SOURCE-TRANSACTION-20260917：事务边界与底座不可变

状态：本机271项及独立静态复审通过，2026-09-17核对；生产未应用。
新鲜连接必须autocommit=false且无活跃事务；写入需authorized=true及生产单独授权。固定plan SHA7ca284…16d，锁等待3秒/statement20秒，advisory及关系锁非阻塞。只读恢复启动default_transaction_read_only=on、REPEATABLE READ。唯一名称chiqiongblastfuenace:latest及唯一e4ad74…d8124摘要不变，禁止换底座/同名权重更新；无新增生产环境修改。
当前权威：[事务、真实依赖与剩余发布门](handoffs/2026-09-17-qa-keyword-source-transaction.md)、[机器证据](../tests/qa_regression/keyword_source_transaction_20260917.json)。上节253项报告是准备阶段历史快照，当前执行器状态以本节为准。

## REQ-QA-SOURCE-RELEASE-ENTRY-20260917：严格配置/实例门

状态：2026-09-17本机验证，生产未执行。
contract SHA固定；配置从受控root读取且hash必须一致，BF_QA_KNOWLEDGE_SEARCH_MODE必须显式keyword。所有连接默认启动只读，核真实实例后才开启授权write事务，恢复保留只读；CLI标志不授予生产授权。
当前权威：[封存包、291项及剩余授权/部署门](handoffs/2026-09-17-qa-source-release-entry.md)、[机器证据](../tests/qa_regression/source_release_entry_20260917.json)。上节271项为事务库阶段快照，当前入口状态以本节为准。


## REQ-QA-ORIGINAL-SOURCE-READER-20260917：制度原书读取门禁

状态：2026-09-17本机验证/复审并冻结，生产未接入。

没有新增环境开关来绕过来源核验。固定r2 release、manifest、四字段文档与十九字段检索投影摘要；仅keyword且目标源零vector。模型名及e4ad74…d8124摘要固定，不允许备用模型或同名权重替换。

当前权威：[读取门禁交接](handoffs/2026-09-17-qa-original-source-reader.md)、[脱敏机器证据](../tests/qa_regression/original_source_reader_20260917.json)。291项入口报告是历史阶段，完整源发布及822原题现场验收尚未完成。


## REQ-QA-FORMAL-DOCUMENT-SCOPE-20260917：书名与全部请求范围

状态：2026-09-17本机378项/复审及V34-r1冻结，生产未应用。

无新环境开关。FORMAL_TITLE_ALIASES精确注册短名/正式名，不接受标题包含关系；显式章节选择最多64组，每组数值最长3位，范围受目录及上限核验。同一模型名称/digest固定，无fallback或同名权重替换。

当前权威：[范围修复交接](handoffs/2026-09-17-qa-document-scope-resolution.md)、[脱敏机器证据](../tests/qa_regression/document_scope_resolution_20260917.json)。V33/356项为前阶段快照；822原题现场验证未完成。


## REQ-QA-DOCUMENT-REGULATION-SCOPE-20260917：条款规程范围与逐项覆盖

状态：2026-09-17本机400项/复审通过，V35-r1冻结，生产未应用。

无新环境开关。固定chiqiongblastfuenace:latest及e4ad74c41d68de1c8004419d8141a2b2df2275fa08f0dcf326ca0e63fb6d8124，禁止切换/fallback/同名权重变化。规程范围支持显式肯定/否定与明确分句，不宣称覆盖全部自然语言。

当前权威：[规程范围交接](handoffs/2026-09-17-qa-document-regulation-scope.md)、[脱敏机器证据](../tests/qa_regression/document_regulation_scope_20260917.json)。V34/378项保留为历史阶段；822原题现场复问未完成。


## REQ-QA-FIXED-MODEL-OVERRIDE-20260917：唯一固定底座禁止参数覆盖

状态：2026-09-17本机61项/独立审查通过，V36-r1冻结，生产未应用。

无新环境开关。固定chiqiongblastfuenace:latest及e4ad74c41d68de1c8004419d8141a2b2df2275fa08f0dcf326ca0e63fb6d8124，resolve显式参数只能等于这组值。禁止另一个批准版本、同名替换权重、动态接受当前驻留成为新基线；管理器/任务授权边界保持。

当前权威：[固定参数门交接](handoffs/2026-09-17-qa-fixed-model-override.md)、[脱敏机器证据](../tests/qa_regression/fixed_model_override_20260917.json)。源/制度前阶段以V35报告保留；822原失败partial题0复问。


## REQ-QA-COMPOUND-SOURCE-SCOPE-20260917：复合子任务与来源禁令

状态：2026-09-17本机557项相关回归及独立审查通过，V37-r2冻结，生产未应用。

无新增环境开关；公开任务计划包含no_live_lookup和all_tools_disabled。仅禁止现场查询不取消明确请求的资料、历史或报表；禁止全部工具时同时关闭prefetch/MCP/keyword资料检索和制度内部SQL。唯一固定底座名称及摘要继承V36，不允许备用或同名换权重。

权威：[逐项交接](handoffs/2026-09-17-qa-compound-source-scope.md)、[脱敏证据](../tests/qa_regression/compound_source_scope_20260917.json)。0生产销项，原题准确率未验证。


## REQ-QA-MATH-FUNCTION-POLICY-20260917：正常数学函数问答

状态：2026-09-17本机225项相关回归/独立审查通过，V38-r2冻结，生产未应用。

无新增开关或模型配置。qa-evidence-no-code-v8-math-functions保持原Prompt全文和同一模型pin；数学名词不等于可执行函数，不能通过数学表述放行Python/脚本/SQL/伪代码。

权威：[逐项交接](handoffs/2026-09-17-qa-math-function-policy.md)、[脱敏机器证据](../tests/qa_regression/math_function_policy_20260917.json)。本轮0助手模型调用/生产写入/原题发送/销项。


## REQ-QA-USER-DATA-SOURCE-SCOPE-20260917：用户给定数据与外部来源范围

状态：2026-09-17本机286项相关回归/独立审查通过，V39-r3冻结，生产未应用。

无新增开关；名称chiqiongblastfuenace:latest及固定digest不变，模型切换/备用回退/同名换权重禁止。user-data scope只调整来源路由，禁代码、单用户和keyword合同不变。

权威：[逐项交接](handoffs/2026-09-17-qa-user-data-source-scope.md)、[脱敏机器证据](../tests/qa_regression/user_data_source_scope_20260917.json)。本轮0助手模型调用/生产写入/原题发送/销项。


## REQ-QA-DECLARED-INPUT-SCOPE-20260917：声明输入与现场核验

状态：2026-09-17本机327项相关回归/独立审查通过，V40-r2冻结，生产未应用。

无新增配置；qa-task-plan-v5-declared-input-scope只改输入来源判断。固定同一名称/digest，切换/备用/同名换权重仍禁止；禁代码、keyword和单用户限制不变。

权威：[逐项交接](handoffs/2026-09-17-qa-declared-input-scope.md)、[脱敏机器证据](../tests/qa_regression/declared_input_scope_20260917.json)。本轮0助手模型调用/生产写入/原题发送/销项；R07重新开放。


## REQ-QA-RESPONSE-STYLE-SOURCE-SCOPE-20260917：回答形式与资料来源

状态：2026-09-17本机395项相关回归/独立审查通过，V41-r1冻结，生产未应用。

无新增配置；固定模型名称/digest，禁止切换、备用、同名换权重。Prompt、禁代码、keyword、单用户及源门禁字节不变。

权威：[逐项交接](handoffs/2026-09-17-qa-response-style-source-scope.md)、[脱敏机器证据](../tests/qa_regression/response_style_source_scope_20260917.json)。本轮0助手模型调用/生产写入/原题发送/销项。


## REQ-QA-SOURCE-CONCEPT-SCOPE-20260917：来源概念与具体记录

状态：2026-09-17本机436项相关回归/独立审查通过，V42-r1冻结，生产未应用。

无新增配置；固定模型name/digest，禁止切换、备用、同名换权重。Prompt、禁代码、keyword、单用户、正式源和owner隔离不变。

权威：[逐项交接](handoffs/2026-09-17-qa-source-concept-scope.md)、[脱敏机器证据](../tests/qa_regression/source_concept_scope_20260917.json)。本轮0助手模型调用/生产写入/原题发送/销项。


## REQ-QA-SOURCE-EXCLUSION-SCOPE-20260917：来源排除与子任务继承

状态：2026-09-17本机498项相关回归、原源保真及独立审查通过，V43-r6冻结，生产未应用。

无新增配置。固定底座与禁止切换/备用/同名换权重不变。具名禁书关闭无法按书过滤的通用keyword检索，明确允许正式来源仍按canonical docID绑定读取。

权威：[逐项交接](handoffs/2026-09-17-qa-source-exclusion-scope.md)、[脱敏机器证据](../tests/qa_regression/source_exclusion_scope_20260917.json)。0助手模型调用/生产写入/原题发送/销项。


## REQ-QA-SUPPLIED-RECORD-SCOPE-20260917：已给记录数据与来源核验

状态：2026-09-17本机546项相关回归、原源保真和独立审查通过，V44-r2冻结，生产未应用。

无新增配置；同一模型名称和摘要固定，禁止切换/备用/同名权重替换。无额外数据读取权限或工具能力。

权威：[逐项交接](handoffs/2026-09-17-qa-supplied-record-scope.md)、[脱敏证据](../tests/qa_regression/supplied_record_scope_20260917.json)。0生产助手模型调用/生产写入/原题发送/销项。


## REQ-QA-RUNTIME-PROBE-FIXED-PIN-20260917：固定底座只读验收门

状态：2026-09-17本机33项合同测试及独立审查通过，生产V26固定身份阻断。

无新增生产配置。固定名称chiqiongblastfuenace:latest及e4ad74c41d68de1c8004419d8141a2b2df2275fa08f0dcf326ca0e63fb6d8124；禁止模型切换、备用、动态基线及同名换权重。loopback GET不使用环境网络代理。

权威：[交接](handoffs/2026-09-17-qa-runtime-fixed-pin.md)、[脱敏证据](../tests/qa_regression/runtime_fixed_pin_20260917.json)。0生产写入/模型调用/原题重发/销项。
