# 排障手册

## 模型检查失败不等于模型卸载（2026-09-16）

Q-QA-QWEN-READINESS-CONCURRENCY-ORACLE-20260916：先区分成功读取/api/ps但批准模型缺席，与查询超时/HTTP失败/异常结构。当前resolve_resident吞fetch异常为空列表，model_ok=false原因不充分。本轮业务模型确认是允许且驻留的Qwen系列。[诊断证据与解决方案](handoffs/2026-09-16-qa-qwen-readiness-concurrency-oracle-plan.md)。旧冻结报告保留，后续按更细原因判定。

## V20 指代趋势追问（2026-09-16）

规划器新增“这个/那个/这些/它们/刚才/上面”指代识别，明确新对象仍优先当前问题。V19失败的30分钟追问现走确定性统计；真实五题与数据库只读来源各5/5通过，模型趋势解释被可信守卫拒绝单列。仅更新8093代理，模型配置不变；整体33项仍执行中。[权威证据](handoffs/2026-09-16-qa-routing-v20-production.md)。

## V18–V19 多轮来源与适配器修复（2026-09-16）

若问答准备失败提示CursorAdapter没有rowcount，定位上下文绑定UPDATE，使用RETURNING id准确核验。若只返回趋势时间范围，仍按答案失败收集；检查planner指代词及确定性执行路径。模型preflight失败不创建POST claim、不重放已提交题。 [权威证据](handoffs/2026-09-16-qa-routing-v18-v19-production.md)。

## V17 历史复合错误 partial（2026-09-16）

历史与其他子任务有结果而整体 partial 时，先检查原文执行器的完成字段和实时分支的 pending 合同。不得以答案非空强行 completed：应检查原文来源清单，或实际 latest 工具载荷的请求对象、单位、时间和只读来源。V16 三失败在 V17 新轮复测通过。[权威排障证据](handoffs/2026-09-16-qa-routing-v17-production.md)。

## 原文少答一章或最新追问沿用历史窗口

V15已补逐章节完成和最新窗口重置。先核对当前生产提交及三个文件哈希，再查`completion.subsection_subtasks`、来源完整性和继承依据；不要重发已发送/不确定题。超出只读检查时限时使用`check_qa_knowledge_candidate_readonly.py --summary --offset N --limit 100`分批核对，0 POST/模型/数据库写入；结果不能推断全题语义通过。[V15权威交接](handoffs/2026-09-16-qa-routing-v15-production.md)。

## 8093/8094 炉况卡显示“智能分析暂不可用”

2026-08-06已确认过一种明确根因：共享 `ollama_proxy_server.py` 已是支持v3单炉况调用的新版，但远端 `diagnosis_model_review.py` 和 `diagnosis_ai_analysis_api.py` 仍是旧版，形成模块版本错位；8094同时缺少启用环境变量。表现为Ollama健康正常，但分析长期停在准备态，或接口直接返回 `enabled=false`。

- 先请求 `GET /api/diagnosis-ai-analysis?label=normal`。HTTP 202表示后台正在生成，不应重复刷新；`failed` 表示本桶生成失败，需等待 `BF_DIAGNOSIS_AI_ANALYSIS_RETRY_SECONDS` 后重试。
- 检查目标端口实际进程是否启用 `BF_DIAGNOSIS_AI_ANALYSIS_ENABLED/BACKGROUND_ENABLED`，并确认 `BF_DIAG_REVIEW_PG*` 仍指向220.12回环PostgreSQL。
- 查询 `bf_assistant.diagnosis_ai_analysis_snapshots` 的 `generation_state/attempt_count/last_error_code/updated_at`；错误字段只记录类型，不保存Prompt、模型原文或密码。
- 确认 `bf_sensor.diagnosis_snapshots` 有最新诊断、8093 `/api/ollama/status` 正常且11434仍只驻留批准模型。
- 同时核对代理、模型合同、证据编排和分析API四个模块的版本/哈希，不能只看共享代理文件。v3正常标记为 `diagnosis_ai_analysis.v3` 和 `diagnosis-single-condition-five-minute.v3`。
- 不要通过浏览器构造诊断分数重试；后端只接受炉况标签并重读当前快照。8093走守卫闭环；8094使用 `remote_guarded_enable_8094_diagnosis_ai.ps1`，不得恢复8769旧架构。

### `preparing + attempt_count=0 + TypeError` 的快速分类

2026-08-11 已证实，这个组合表示后台在写入
`bf_assistant.diagnosis_ai_analysis_snapshots` 之前就失败，优先查
[begin_ai_analysis](../高炉前端数据/智能助手/backend/diagnosis_review.py)
的 `Jsonb(canonical_context)`：

1. 先证明 `/api/qa/chat`、`/api/qa/knowledge/search`、`/api/ollama/status` 正常，
   排除整体模型/RAG 故障。
2. 读分析接口的 `state/attempt_count`。`attempt_count=0` 不要等模型超时，
   因为请求尚未进入模型调用。
3. 用整体上下文回归覆盖 `datetime/date/Decimal`、嵌套容器和 `NaN/Inf`；
   所有 JSONB 写入必须经 `json_safe_value()`。
4. 部署只允许替换 `diagnosis_review.py`，失败自动回滚。验收要求
   `completed`、`attempt_count>=1`、摘要非空，并保护 8094/8768/8770/5432/11434 PID。

受控入口为 [prepare_8093_diagnosis_ai_json_fix_release.ps1](../tools/prepare_8093_diagnosis_ai_json_fix_release.ps1)
和 [deploy_8093_diagnosis_ai_json_fix_22012.ps1](../tools/deploy_8093_diagnosis_ai_json_fix_22012.ps1)。

## 8093 智能助手偶发无回复但状态稍后恢复正常

### 典型现象

- `/api/ollama/status` 稍后恢复 `ok/model_ok=true`，但当次 `/api/qa/chat` 没有完成。
- `logs/proxy_8093.health.log` 同期出现 TCP/HTTP 短时失败，旧记录紧跟 `restart_service`/`restart_service_done`。

### 现行判断

先运行 [第一层健康探针](../tools/probe_8093_assistant_health.ps1)、[日志尾部探针](../tools/probe_8093_assistant_log_tail.ps1)和[守卫运行时探针](../tools/probe_8093_health_guard_runtime.ps1)。当前 8093 正常合同为连续失败阈值 3、服务停止阈值 1、重启前退避 15 秒、重启冷却 600 秒；状态文件为 `logs/proxy_8093.health.state.json`。

单次瞬时失败的正常日志应为 `degraded ... consecutive_failures=1 threshold=3` 和 `restart_deferred`，不能出现 `restart_service`。一次成功检查必须出现 `ok`，并把 `consecutiveFailures` 清零。若仍在一次失败后重启，先核对共享脚本 SHA-256 `1A4B2C56...D9C2B3` 和现行 8093 配置 SHA-256 `8A24C83D...F51FDE`，不要连续手工重启服务。旧 `D20F01F1...66EACA` 是增加 keyword 环境变量之前的历史配置。

### 修复与验证入口

- 部署：[remote_guarded_deploy_8093_health_guard.ps1](../tools/remote_guarded_deploy_8093_health_guard.ps1)。
- 单次真实问答：[verify_8093_assistant_sse_once.py](../tools/verify_8093_assistant_sse_once.py)；必须只提交一次并完整收到 `start -> delta -> final -> done`。
- 回滚：使用部署输出的 `logs/deploy_backups/8093_health_guard_<时间戳>` 恢复共享脚本和 8093 配置；不得修改 8768、8094、8770 或 11434。

### 知识问答仍无回复或搜索模式漂移

1. 运行进程环境探针，确认 8093 实际监听进程而不只是 JSON 配置显示 `BF_QA_KNOWLEDGE_SEARCH_MODE=keyword`；8094 也应为 `keyword`。
2. 调用默认 `/api/qa/knowledge/search`（不传 `mode`）确认 `enabled=true`、`search_mode=keyword` 且返回证据。若只有显式 `?mode=keyword` 能成功，不能说明启动环境已修复。
3. 同时确认 11434 `/api/ps` 仅驻留批准的 27.8B，`OLLAMA_MAX_LOADED_MODELS=1`，不要通过恢复双驻留掩盖问题。
4. 若配置或实际进程为空/`hybrid`，使用 [关键词配置补丁器](../tools/patch_8093_keyword_knowledge_mode.py)和[受控部署器](../tools/remote_guarded_deploy_8093_keyword_knowledge_mode.ps1)恢复。该部署只允许重启 8093，并保护 8768/8094/8770/11434、页面、共享后端/RAG、守卫和 11434 配置。
5. 修复后使用 [关键词知识 SSE 单次包装器](../tools/remote_verify_8093_keyword_knowledge_sse_once.ps1)做一次新会话短问。必须在准备态看到知识检索启用、未跳过和知识意图，随后完整收到 `start -> delta -> final -> done`；禁止超时后重复 POST。

现行配置 SHA-256 为 `8A24C83DF93008DD8E358682558E8755442D87052A09FB24F39778F2EAF51FDE`，备份为 `logs/deploy_backups/8093_knowledge_keyword_20260805_072445`。2026-08-05 基准真实知识问答总耗时 `23.8856s`、默认检索命中 2 条证据，报告为 `logs/acceptance/8093_keyword_knowledge_20260805_20260805_084403/assistant_keyword_knowledge_sse_once.json`。

## 本机 PostgreSQL psql 参数错位与密码缺失

### 典型错误

- `could not translate host name "-p" to address`
- `fe_sendauth: no password supplied`
- `找不到路径 Env:\PGPASSWORD`

### 原因

1. `-h $env:BF_DIAG_REVIEW_PGHOST`对应的环境变量为空，psql把下一个参数名`-p`当成了主机值。
2. 小写`-w`是`--no-password`，会禁止psql询问密码；没有`PGPASSWORD`或密码文件时只能失败。
3. `Remove-Item Env:PGPASSWORD`默认要求变量存在，未设置时会报告路径不存在。

### 安全排查与修复

先检查非密码字段和密码是否已设置，不直接打印密码：

```powershell
$env:BF_DIAG_REVIEW_PGHOST
$env:BF_DIAG_REVIEW_PGPORT
$env:BF_DIAG_REVIEW_PGDATABASE
$env:BF_DIAG_REVIEW_PGUSER
if ($env:BF_DIAG_REVIEW_PGPASSWORD) { '数据库密码已设置' } else { '数据库密码未设置' }
```

变量为空时，按[数据库账号配置说明](数据库账号配置说明.md#原生-postgresql-16-管理员连接)在同一PowerShell窗口重新赋值。临时人工验证可避免空变量和反引号续行，使用一行显式参数并让psql安全提示密码：

```powershell
& 'C:\Program Files\PostgreSQL\16\bin\psql.exe' -W -h 127.0.0.1 -p 18000 -U postgres -d bf_trend -c 'SELECT current_database(), current_user;'
```

如果由环境变量提供密码，先设置`PGPASSWORD`再使用小写`-w`，并在`finally`中幂等清理：

```powershell
$env:PGPASSWORD = $env:BF_DIAG_REVIEW_PGPASSWORD
try {
    & 'C:\Program Files\PostgreSQL\16\bin\psql.exe' -w -h 127.0.0.1 -p 18000 -U postgres -d bf_trend -c 'SELECT current_database(), current_user;'
} finally {
    Remove-Item Env:PGPASSWORD -ErrorAction SilentlyContinue
}
```

成功信号是返回`current_database=bf_trend`和预期`current_user`。本流程只检查本机数据库，不涉及220.12。

## 8093 智能助手一键诊断与自动修复

以后遇到 8093 智能助手无回复，先运行：

```powershell
python tools\assistant_8093_auto_recovery.py diagnose --allow-agents-password --no-auto-prestage
```

不要先重启或把多个探针手工拼成远端 PowerShell。输出分类处理如下：

- `healthy`：服务、端口、守卫、keyword、默认知识搜索和单模型驻留均正常。查看报告中的最近 POST/异常时间；需要端到端证明时运行一次 `recover`，它只发一个 SSE，不会在健康状态部署。
- `keyword_mode`：已知配置/实际进程/默认搜索漂移到空值或 hybrid。直接运行 `recover`，工具走既有 keyword 部署器；不要把 `OLLAMA_MAX_LOADED_MODELS` 改为 2，也不用重新调查已知 embedding 竞争风险。
- `guard_contract`：已知守卫脚本/配置或 3/1/15/600 合同漂移。`recover` 只在已知哈希内修复守卫。
- `manual_blockers` 非空：未知哈希、非批准模型或未能归入已知路径的服务/接口错误。保存报告并人工审计，不得扩展白名单或强制覆盖。
- 退出码 3：VPN/私网、SSH 22、5432、8093、11434 未全部恢复；此时服务部署计时尚未开始，也没有远端操作。
- 退出码 6：唯一一次 SSE 失败。禁止立刻再跑 recover；先读取报告、远端问答日志和守卫时间线，确认请求是否仍在后端运行。

若 package 缺失或工具代码升级，先单独运行 `prestage`。服务恢复后再运行 `docs --report <recover.json>`；文档失败不能触发服务回滚或第二次问答。完整说明见 [专项文档](8093智能助手自动诊断修复验收工具_20260805.md)。

## 参数优化页没有八炉况建议或模型复核失败

先区分规则链路与模型链路：

- 没有八炉况矩阵：检查 8767 诊断快照是否包含 `recommendation_bundle.schema_version=multi_condition_recommendation.v1` 和 8 个 `conditions`。只有旧 `recommendation` 时页面会兼容显示当前炉况摘要，但不会伪造其他炉况的完整动作。
- 某炉况显示“条件预案”：这是正常安全边界。只有 `scope=active` 的当前主炉况方案可以作为当前操作参考，`supporting/hypothetical` 不能加入有效动作队列。
- 模型显示失败：先检查 `BF_DIAGNOSIS_MODEL_REVIEW_ENABLED`，再只读调用 `POST /api/diagnosis/model-review`。HTTP 400 表示输入或模型 JSON 不符合合同，502 表示模型调用失败，503 表示功能关闭。规则建议不应随模型失败消失。
- 模型反复调用：确认诊断时间、所选炉况或 `force` 是否变化；默认缓存 900 秒，键包含快照、所选炉况和内部模型身份。缓存没有跨进程持久化。
- 页面字段缺失：检查每个 `actions[]` 是否仍包含 `source_refs/trigger_evidence/preconditions/blocking_reasons/delta/sequence/missing_inputs/observation_window/approval/read_only`。不得在前端用自由文本补造这些字段。

本机隔离复验可启动 `python tools\serve_multi_condition_browser_fixture.py --port 18093`，仅用于浏览器检查；完成后停止该精确进程。它不连接 PostgreSQL、8767 或生产模型。

## 参数优化页图表消失、19项证据不完整或抽屉打不开

1. 先检查页面包含 `REQ-OPT-VISUAL-COCKPIT-RESTORE-20260806` 且实际挂载 `OptimizationVisualWorkbenchLayout`。若仍挂载旧 `OptimizationMultiConditionCockpitLayout`，说明8093/8094页面版本未同步。
2. 用 [布局探针](../tools/probe_remote_recommendation_layout.cjs)测量 `.opt-cockpit-top` 和 `.opt-cockpit-bottom`。顶部应不小于280px、底部不小于250px；不得只判断DOM里是否存在Canvas。
3. 默认只显示4项主证据是正常状态。点击“展开19项证据与曲线”后，应有19个唯一 `data-core-evidence-id`；无历史数据的卡片显示等待/降级，不伪造曲线。
4. 完整动作字段位于“查看完整动作依据”抽屉；模型完整证据位于“查看复核详情”抽屉。抽屉为空时检查所选条件的 `recommendation.actions[]`，不要把空字段改成前端猜测。
5. 8094缺少新版组件时，使用 [8094功能块补丁器](../tools/patch_8094_multi_condition_review.py) 从最新8093源码重新生成候选页；正式更新使用[前端热更新部署器](../tools/remote_deploy_8093_8094_recommendation_visual_frontend.ps1)，不得为纯页面改动重启8768。
6. 8094若HTTP 200但页面空白，必须查控制台是否有 `useCoreMetricRealtime8093 is not defined`；这是旧R1功能块遗漏8093专属依赖，使用R2重新生成。不能用静态标记存在冒充运行通过。远端浏览器通道出现 `ERR_EMPTY_RESPONSE` 时，先在服务器本机核对HTTP、文件哈希和监听；普通本机 `Test-NetConnection` 可能受aTrust/私网通道影响而假阴性。只有服务器本机确认守卫Running但无监听时，才最小范围恢复对应的8093或8768守卫。

## 220.12 工长趋势独立页没有实时数据

先确认访问地址含 `?ws_port=8768`：`http://10.30.220.12:8093/foreman_trend_preview.html?ws_port=8768`。页面默认的 `8767` 仅适用于本机 8092 部署，不能直接用于 220.12。

只读排查顺序：确认 `BFV4PreviewProxy8093` 与 `BFV4PreviewWs8768` 为 Running、8093/8768 均监听，再在 cache-bust URL 上运行 [远端浏览器验收器](../tools/verify_foreman_trend_remote_8093.cjs)。正常情况下，缺失物理变量必须显示 `--`；不得为凑满 49 项填入 fixture 或默认值。若资源 404 或需求标记缺失，使用 [受控静态部署器](../tools/remote_deploy_8093_foreman_trend_preview.ps1) 重新发布三个独立资源，并核对它输出的备份目录和 8093/8768 PID 不变。
## 220.12:18080 不是 IMES 或 15433/18889 无法连接

- 18080 已有 Nginx 静态站点，不能用 portproxy 覆盖。应检查
  `OPS-22012-IMES-WEB-PROXY-20260805` 标记及 `/imes.web/`，旧站点在 `/g13.html`。
- 15433/18889 由 Windows `netsh interface portproxy show v4tov4` 核查；同时确认
  `iphlpsvc` 为 Running/Automatic。
- 防火墙只允许部署时的 VPN 客户端地址。VPN 重新拨号导致地址变化时，重新运行
  受控部署器更新来源，不要添加任意来源允许规则。
- 部署失败先检查最新 `logs/deploy_backups/22012_direct_source_relays_*`；不要按名称
  批量结束 Nginx/Python。8093/8768/8094/8770 属于受保护端口。

## 8093 看似不可访问或核心指标不再显示 pSpace 秒级实时

按以下边界逐层判断，不要一开始就重启8093：

1. 先区分系统路由与 aTrust 应用代理。`route print` 没有 `10.22/10.30`、VNIC断开时，PowerShell直连失败只证明普通本地路径不可用；仍应在已认证的 aTrust“高炉模型”应用中打开8093。
2. 浏览器先看核心指标横幅。`pSpace秒级实时 28/28`、最新时间持续推进、各行有数据时间/年龄/质量且没有“已降级为分钟镜像”，已经证明 `243 pSpace -> 8770 -> 浏览器` 当前链路可用，不执行生产重启。
3. 只有横幅降级或时间停住超过12秒，才查浏览器是否有8770 WebSocket错误、220.12的8770监听与 `V4BillboardPspace8770` 任务、8770日志、220.12到243:8889连通和 SDK `RealReadList`。上游243不可达时不得通过重启8093掩盖问题。
4. 8768和`one_minute_values`只负责火花线、趋势、诊断、基线及降级镜像；分钟数据正常不能证明8770正常，8770正常也不要求PowerShell具备私网系统路由。

分钟表口径排障时同时检查 `aggregate/semantic_version/window_complete/coverage_ratio`：`PS_HIS_AVERAGE` 是早期处理历史平均，`PS_RAW_SAMPLE` 是截止2026-08-05 21:54的旧分钟末样本，`PS_RAW_AVERAGE/valid_raw_mean_v1` 是之后的有效raw分钟平均。分钟最新时间约落后1–2分钟是分钟起始时间戳和60秒闭窗水位的结果；8093当前值实时性应看8770传输年龄，不能用8768分钟时间判断。若出现重复 `sync_runs`，先数 `run_realtime_sync_pg_bg.ps1` 包装器，中文主目录与镜像目录必须共用项目根排他锁。

## 220.12 已注册 MES MCP，但 8093 仍不调用或返回旧炉次

1. 先读生产 `backend/mcp_host/server_registry.json`，应有四个服务；`imes-readonly` 必须为 `direct_22012`，不能沿用本机 `127.0.0.1:15433`。
2. 检查 `imes_relay_mcp_server.py` 与 `imes_full_variable_catalog.json` 哈希及目录项数。生产目录应有 315 项，并启用 `IMES_ACTIVE_HEAT_MAX_AGE_HOURS=72`；缺少该门禁会让历史未关口炉次抢占“当前炉次”。
3. 用 `verify_8093_assistant_sse_once.py --auto-mcp-tools` 验证生产意图路由，不要只用强制工具模式。成功请求必须出现 `tool_start/tool_result`，且回答不能来自模型猜测。
4. Windows PowerShell 5.1 执行含中文路径的远端脚本时，脚本必须是 UTF-8 BOM。无 BOM 脚本会在预检阶段把项目路径解码错误；不要在未核查结果时重复部署。
5. SSH 调用端 30 秒超时不等于部署失败。先运行 `remote_probe_8093_imes_mcp_sync_result.ps1`，读取最新 `deployment_result.json`、服务、守卫和端口 PID；确认没有在途部署且结果明确失败后再决定回滚/重试。

## SSH已复用但部署仍不快

1. 运行`pwsh.exe -File tools/verify_22012_persistent_ssh_reuse.ps1 -IncludeColdBaseline`，分别看冷连接、两个复用请求和`connection_id`。
2. 如果连接ID相同但耗时仍高，分开检查SFTP通道创建、远端PowerShell启动、服务停启和HTTP验收；连接复用只优化认证/握手，不能消除业务重启时间。
3. 用`deployment_memory.py summary --window 50`比较总耗时和各阶段，不以单次RTT推导整次部署收益。
4. Reliable SSH MCP用`pool-probe`检查同一Plink PID和`requests_completed`；如果`reconnect_count`增加，检查VPN、220.12 SSH服务、30秒协议keepalive和60秒只读应用心跳。
5. 传输中断时先核对远端文件、部署结果、服务和端口；`uncertain_execution=true`或连接池错误绝不能直接自动重试。

### `remote_22012_session.py` 报 `unrecognized arguments: --prompt-password`

1. 这是本机命令行参数归属错误，不表示 ReliableSSH MCP、网络或 220.12 SSH 服务不可用。
2. `--prompt-password` 属于 `remote_22012_exec.py`；`remote_22012_session.py ensure` 不接受该参数。不要把旧临时交互脚本原样重试。
3. Codex 会话内优先使用已注册的 `reliable_ssh_10_30_220_12` MCP，先执行连接状态与身份探测，再分别上传、执行和验收。
4. MCP 前端等待 30 秒超时后，先查连接池 `in_flight/requests_completed/reconnect_count` 和远端部署结果。请求仍在执行时不得重发停服或部署命令。
5. 只有明确使用本地 broker 时才调用 `remote_22012_session.py ensure/serve/run` 的现有参数合同；密码继续通过受控凭据注入，不写入脚本或命令历史。

## 异常复核弹窗与ABC热制度上行分数不一致

2026-08-10后展示源固定为ABC33 B4，旧`raw_scores.hot`仅保留在`legacy_score_archive`。若再次不一致，比较两端`evaluation_id/evaluation_ts/batch_state/score_sources.hot`；同一评价ID必须同分。B4缺失、过期或无效时应显示`--`，不得通过前端回退或写死旧分。
6. `imes-web-readonly` 已注册不代表绕过验证码。需要登录态的 Web 查询仍必须由受控账号、密码及验证码/会话完成；数据库 MCP 与 Web MCP 的验收要分开记录。

## 8093 复合问题只回答 MES 或只回答传感器

先查最终 `mcp_tool_trace`，不要仅凭回答内容判断。当前快速计划使用
`imes_plan or chart_plan or standard_plan or sensor_plan`，同一问题命中多个领域时只执行
第一个非空计划并提前返回，所以“上一炉Si+当前顶压”通常只查MES，“072炉硅锰多少，
顺便看炉温和顶压”可能只查传感器。

如果轨迹进入 `model_planner`，再检查是否出现以下浪费：`find_gl02_variables` 后没有真实值
查询、同参数MES工具重复调用、正式炉次号被去掉 `2#`、`P_top` 被交给历史炉况工具、
单工具 `TimeoutError` 或 `TOOL_CALL_LIMIT_EXCEEDED`。这些情况不能通过继续增加 Prompt 文本根治；
应实现多确定性计划或单个跨源复合工具，并用确定性字段完整性校验生成最终回答。

## 8093 智能助手反复显示 Failed to fetch

1. 先运行 `python tools\assistant_8093_auto_recovery.py diagnose --allow-agents-password --no-auto-prestage`。门禁必须同时检查 SSH 22、PostgreSQL 5432、8093、11434；VPN/私网未通时先恢复链路，不开始部署计时。
2. 若只有 8093 不监听，先查 SCM 服务事件、守卫日志和文件哈希变化。受控 `KeyboardInterrupt`、密集停止/启动与同期哈希变化组合出现时，按 `ERR-8093-ASSISTANT-DEPLOYMENT-COLLISION-20260806` 判定部署碰撞，不要转去重启 11434、8768 或数据库。
3. 写入流程必须获取 `Global\BFV4PreviewProxy8093Deployment`；无法获取时立即退出并报告已有部署，不得并行停启。服务恢复只用 `remote_guarded_recover_8093_service.ps1`，页面修改只用 `remote_hot_deploy_8093_fetch_resilience.ps1`。
4. 页面英文 `Failed to fetch` 已替换为中文可操作提示。只读 GET 最多重试 3 次；POST/SSE 不自动重发，用户需在约 30 秒后手动重试，避免制造重复问答。
5. 修复后先确认默认知识检索为 keyword、证据非空、只驻留批准模型、守卫计数 0；随后只允许一次真实 SSE，完整事件序列与 PID/哈希保护全部通过才可关闭故障。

## PowerShell 中文乱码、变量提前展开或误用5.1

1. 先运行`pwsh.exe -NoLogo -NoProfile -File .\tools\verify_pwsh7_utf8.ps1`，确认进程为`pwsh.exe`且`PSEdition=Core`。
2. 如果找不到`pwsh.exe`，检查`C:\Program Files\PowerShell\7\pwsh.exe`和机器级PATH；使用`winget install --id Microsoft.PowerShell --exact --source winget`安装稳定版，不得回退5.1。
3. 若外层shell把`$false`、`$env:*`或引号提前展开，不要改写另一条长`-Command`重试；把逻辑写入`.ps1`并用一条`pwsh.exe -File`执行。
4. 中文路径必须使用`-LiteralPath`；脚本入口统一设置Console Input/Output、`$OutputEncoding`和默认文件编码为UTF-8。
5. 若错误来自220.12旧任务，先确认远端是否已安装PowerShell 7。未完成远端安装与计划任务验收前，不得机械替换全部`powershell.exe`。
6. 2026-08-10后本机跳板默认使用`pwsh.exe -File`。若仍出现`Unexpected attribute CmdletBinding`，检查是否使用旧版`remote_22012_exec.py`把payload拼到包装前导之后；新版必须上传独立payload。
7. 若远端报告找不到`pwsh.exe`，直接检查`C:\Program Files\PowerShell\7\pwsh.exe`；不要依赖Windows Server 2016当前SSH服务进程的旧PATH缓存。

## 软熔带智能诊断返回 unavailable 或方向异常

1. 先运行[专项验证入口](../tools/verify_cohesive_zone_intelligent_diagnosis.ps1#L1-L41)，确认代码、依赖、原C2基线和CLI正常。
2. `empty_input`或`no_data_at_or_before_evaluation_time`表示CSV为空、时间列无法解析，或评价截止早于首条数据；检查`--timestamp-column`和时区，不要删除历史截止门禁。
3. `insufficient_scored_features`表示可评分特征少于4项；`insufficient_pressure_permeability`或`insufficient_temperature_field`表示必需分组覆盖不足。缺失值不得改填0，应核对[字段别名和有效范围](../炉况规则引擎/config/cohesive_zone_intelligent_diagnosis.yaml#L33-L204)。
4. 特征存在但未参与时，检查最新样本是否超过5分钟、每个当前/参考窗口是否至少5个样本、数值是否落在`valid_min/max`内。
5. 方向与现场判断不一致时，先查看JSON中的`drivers`、`feature_vector`和`trend_vector`，确认变量单位、正方向和字段语义；不得直接调大权重或置信度掩盖单位错误。
6. `direction_consistency=review_required`只表示解释型特征融合方向与既有C2温度剖面几何方向不同，应进入人工复核和历史回测，不应选择其中一个自动控制。
7. 若需要Chronos-2、TabPFN或Transformer，先取得经接受的`H_cz`真值、冻结标签可用时间、按时间切分训练/验证/测试并完成现场标定；当前`ml_readiness.trained_sequence_model=false`是正确安全状态。

## 8892 HCZ标注服务不可用或无法保存

1. 先检查`http://10.30.220.12:8892/api/health`中的`hcz_label_enabled`和`hcz_label_blind_to_model`，再检查计划任务`\BlastFurnaceServices\SoftZoneTemperatureReplay8892`的Action是否为PowerShell 7入口。
2. 页面显示“尚未固定实测证据”时，确认标注时刻位于窗口内、结束时间不晚于最新实测、窗口不超过72小时；不要绕过哈希刷新门禁。
3. HTTP 400通常是字段/窗口/哈希变化；刷新证据后重提。HTTP 401是服务器身份或登录门禁；HTTP 503检查回环PostgreSQL写库配置和`soft_zone_replay_8892.log`，不得在日志中打印密码。
4. 启动报DDL或权限错误时，核对`BF_DIAG_REVIEW_PGSCHEMA`及写账号对`bf_assistant`的CREATE/INSERT/SELECT权限；不得改用GL02只读账号写标签。
5. 页面出现HCZ估计开关或估计卡即视为安全故障，停止标注并运行[跨引擎验收](../tools/verify_hcz_expert_label_ui.cjs)和[生产只读冒烟](../tools/verify_hcz_expert_label_remote_ui.cjs)。
6. 重新部署固定使用[deploy_hcz_expert_label_22012.ps1](../tools/deploy_hcz_expert_label_22012.ps1)；脚本只重启8892并要求8093/8094/8768/8770/5432 PID不变。

## 8093 HCZ上移规则显示数据不足、结果异常或页面不可用

1. 先访问`/api/hcz-upward-rule`。`insufficient_data`时查看`insufficient_reasons`和每项`current_valid_hours/baseline_valid_hours`，不得将缺数改填0。
2. 直接`T_top`无样本时属于已知现场情况；适配器应由`T_top_A~D`至少3个有效点组成平均顶温。若这些点也缺失，再排查`bf_sensor.one_minute_values`同步。
3. 炉壁点刷新较稀疏，使用“每点每小时至少1样本、每层至少4方位”；不要套核心指标每小时30点门禁，否则会错误地把7～13层全部判为缺数。
4. 结果与高炉长判断不一致时，先核对单位：煤气利用率阈值是1个百分点，全压差和风压阈值是kPa，PI使用`m³/(min·kPa)`；再检查24小时窗与之前5天是否连续且不重叠。
5. `not_triggered`表示至少一个AND门未通过，不代表软熔带稳定或下移。人工复核应结合8892盲标、炉料、风口、出铁和炉况事件。
6. 页面404或API503时，检查`BFV4PreviewProxy8093`、8093监听和后端导入；重新部署只能使用[受控入口](../tools/deploy_hcz_upward_rule_22012.ps1)，并核对8094/8768/8770/5432/8892 PID不变。

## 8093浏览器矩阵执行过慢或生产加载压力过大

1. 先确认改动范围：单个分数、文案、格式或局部弹窗默认使用`--profile quick`；单路由DOM/布局使用`standard`；共享CSS、导航、三维运行时、响应式基础设施或多页面改动才使用`full`。
2. 不得为每个组合新建browser context；当前验证器按内核复用context，静态资源缓存可在同一内核的后续页面复用。失败后再按风险升级，不要直接在生产反复跑85个冷页面。
3. 若用户单次页面仍慢，分别记录HTML传输、JS解析/编译、GLB下载、WebSocket首数和长任务。当前已知高成本包括约907KB未压缩HTML、浏览器Babel、React开发版和约8.23MB GLB。
4. 优化顺序：构建期编译并移除Babel → React生产版和路由拆包 → HTML gzip/Brotli与哈希静态资源缓存 → Three/GLB按路由延迟加载及Meshopt/Draco/KTX2 → 合并高频定时器并在后台标签暂停。
5. 这些优化涉及共享运行时；实施时应升级为`full`本机/预览验收，并在生产只做定向冒烟和真实性能采样。

## Codex CLI经济型委派没有变快或token仍然很高

1. 先判断任务是否确定性：哈希、格式化、文件枚举、固定命令和schema校验直接运行脚本，不要调用Luna。
2. 确认使用Skill包装器默认的`read-only + ephemeral + ignore-user-config + project_doc_max_bytes=4096`，并禁用无关apps/plugins/browser/computer/image工具。
3. 查看JSON中的`input_tokens/cached_input_tokens/output_tokens/duration_ms`。模型输出很短但输入很大，通常来自系统说明、项目AGENTS和技能目录，不等于业务prompt很长。
4. 日志出现`responses_websocket`重试后`falling back to HTTP`时，延迟来自当前网络到ChatGPT WebSocket的连接失败；不要通过重复启动更多子任务放大延迟。
5. 一次委派未通过验收就升级模型或回主任务，不允许让便宜模型反复猜测。节约必须把重试和主任务复核时间算入。

## 3D源页面与生产构建截图出现少量动态偏移

现象：炉体和广告牌样式肉眼一致，但整图像素差因跟随模型的工艺标注在不同渲染帧偏移数像素而超过阈值。

处理：先把活动canvas viewer设为全局viewer并重置相机；广告牌CanvasTexture、位置/缩放和DOM卡片计算样式做精确签名；隐藏动态广告牌/跟随标注后再比较炉体结构图。不得直接提高1%阈值或用一次偶然的0差异冒充稳定。

## 8093核心变量状态成批一致、显示`--`或弹窗被三维画布遮挡

1. 先检查`.core-detail-backdrop`的父节点必须是`document.body`、计算层级为`2147483647`；生产构建必须从`react-dom`导入`createPortal`，不能从`react-dom/client`取不存在的API或内联回退。
2. 对每行读取`data-baseline-evidence`，核对该变量自己的`raw/median/iqr/deviation/status`；公式固定为`(raw-median)/IQR`。不要用PostgreSQL分钟值判断pSpace秒级显示值。
3. 大量`--`时核对8768的`baseline_compare.items`和`bf_sensor.daily_baselines`最新日覆盖。基线维护刚完成时应新建页面连接重新取快照；不得用0或硬编码默认值冒充30日基线。
4. 状态恰好相同并不必然是故障；必须比较各行偏差证据。2026-08-11生产复验28行同时出现五种状态，证明判断是逐变量独立执行。
5. 曲线行为验收若只报`bf-heat-performance-quality-8093-query-v2.js` 404，应单独登记为既有炉次查询资源问题；不要把它误归因于Portal或基线公式。

## ABC33 智能助手弹窗不可用

固定顺序：`规则批次 → 解释上下文 → 会话来源 → 上下文快照 → 分析缓存 → 模型状态 → SSE → 助手页面索引`。

1. 先查 `abc_rule_evaluation_batches/items` 是否存在精确 `evaluation_id + rule_id`。
2. 登录 operator/admin 后请求 explanation-context；403是权限问题，409是批次/规则不匹配，503才是数据库链路。
3. 查 `qa_conversation_origins` 指向的 `context_snapshot_id` 与 `qa_context_snapshots.context_hash`。
4. 查 `abc_rule_ai_explanations` 的 Prompt版本、模型名和 `generation_state`；同键多请求只能有一个进程内 owner。
5. 模型生成时 PostgreSQL 活跃连接不应长期占用；SSE只发一次，不因 Failed to fetch 自动重放。
6. 模型故障但确定性解释也为空时，不要先改Prompt；先修权威行解析或上下文合同。

## 智能助手显示 `qa_session_required`

这是关闭共享访客模式后的会话鉴权提示，不是代理、PostgreSQL或大模型离线。8093 启用 `BF_QA_GUEST_ENABLED=1` 时，未登录 bootstrap 应返回 `access_mode=guest_shared`，不应进入此分支。

1. 先查 `/api/ollama/status`；若 `proxy_ok/ollama_ok/model_ok=true`，不要重启 8093 或 Ollama。
2. 先查服务配置中的 `BF_QA_GUEST_ENABLED`。显式关闭访客模式时，刷新 `#qa` 后通过 `/api/auth/login` 建立同源会话；启用时应直接进入共享访客问答。
3. 若匿名 bootstrap 已是 HTTP 200 / `guest_shared`，但页面仍显示“登录后使用智能助手”或私有导航，检查生产 HTML 是否同时包含 `function QaGuestNav`、`accessMode === 'guest_shared'`、`登录私有模式（可选）`。缺少任一标记说明前端发布字节过旧，应按 8093 受控更新流程部署页面；不要通过放宽后端鉴权处理。
4. 修复后用真实生产 URL 验证初始访客徽标可见、登录卡片不可见、可选登录可打开且“继续匿名使用”可返回访客界面。确认页面字节正确后再处理浏览器缓存。
5. 登录后页面只重新读取 `/api/qa/bootstrap`，不会重发之前的问题；如发送时会话过期，原问题会恢复到输入框，必须手动再次发送。

## 智能助手显示 `conversation_not_found`

1. 先匿名请求 `/api/qa/bootstrap`；若返回 `access_mode=guest_shared` 和固定 `conversation.id`，说明访客入口与数据库共享房间正常。
2. 旧标签页、登录/退出切换或浏览器缓存可能提交旧私有会话 ID。现行后端必须忽略访客提交的该 ID，并在模型准备前重新绑定当前 Host:Port 的固定共享会话；不得要求访客清 Cookie 才能恢复。
3. 若仍返回 404，检查生产 `ollama_proxy_server.py` 是否包含 `qa_chat_conversation_id`，并确认访客分支在 `qa_conversation_owned` 之前完成绑定。
4. 登录用户出现该错误时仍按安全事件处理：核对 owner 会话是否属于当前 `session.sub`，不得用访客兜底绕过私有 owner 隔离。
5. 修复验收只发送一次匿名 SSE，并故意提交一个不存在的会话 ID；`prepared/final` 中的会话 ID 必须等于 bootstrap 共享 ID。断线或失败不自动重放。

## 智能助手显示“数据库查询轮数超过上限”或 MCP 工具失败

1. 该文字是旧版 MCP 循环的硬编码终止文案，不等于 PostgreSQL 查询人数过多，也不是数据库连接池容量提示。
2. 现行实现达到 `BF_QA_MCP_MAX_TOOL_ROUNDS/BF_QA_MCP_MAX_TOOL_CALLS` 后只执行一次 `tools=None` 的最终模型回答，禁止继续请求工具。
3. 降级回答必须明确“实时数据库未核实”，只能使用已经注入的炉况快照、keyword 知识证据和通用工艺知识，不得声称已经确认当前软熔带上升或下降。
4. 若仍只出现错误文字，检查部署文件是否包含 `model_without_tools_after_mcp_failure`；若答案为空，再查 Ollama 调用错误，而不是扩大工具轮数。
5. 高频问题仍应补确定性复合工具和对象映射；模型降级用于保持可回答性，不替代实时数据合同。
6. 如果正确角色登录后仍返回 403，检查账号角色是否包含 operator/admin/操作/管理/炉长及 Cookie 的 Path/SameSite/签名；不得关闭 owner 隔离或允许匿名模型调用。

## 炉体逐层统计不完整或时间窗变成滚动分钟数

1. 先看 SSE 工具轨迹。7–13 层 A–H 的逐层平均/极差/标准差问题应恰好调用一次
   `gl02ext__query_body_temperature_statistics`；若出现多个单点工具或只返回第 7 层 A–E，说明仍是
   旧路由，不能通过提高工具调用上限修复。
2. 同时出现“最近一小时”和“15 分钟滚动”时，检查工具参数：`end_time-start_time` 应为 60 分钟，
   `rolling_window_minutes` 应为 15。若总窗也是 15 分钟，检查
   `qa_mcp_explicit_time_range()`，不得让滚动数字覆盖总时间范围。
3. 每层默认要求 A–H 8/8 同分钟有效。样本少于期望分钟时先读 coverage、missing、nonfinite、zero
   和质量分布；不得把缺测分钟插值或静默过滤后冒充完整层平均。
4. 最终统计必须来自工具确定性结果；若答案与 tool_result 的 count/min/max 不一致，检查
   `deterministic_mcp_answer()` 的复合工具分支，不要让模型重新计算原始序列。
5. 生产基线为 Git `849d9554060f7c1252722e8394a9cb224ff13488`；核查版本前仍须先做当前文件
   哈希和服务探测，不因历史提交号直接覆盖生产文件。

## ABC33 智能解释显示“问答接口 HTTP 400；本次提问未自动重发”

1. 先查响应错误码；`invalid_initial_analysis_question` 表示固定首问合同不一致，不表示
   Ollama、数据库或炉况快照不可用。
2. 前端 `streamQuestion(...,{initial:true})` 的文字必须与后端
   `ABC_RULE_INITIAL_QUESTION` 逐字一致；改动任一侧时运行跨文件一致性测试。
3. 请求因 400 被拒绝时不要自动重发。修复后由用户重新打开炉框触发一次新的 SSE；仍需保持
   owner、同源、上下文绑定和固定首问门禁。
4. 前端应展示 JSON 中的 `error/error_code/message`，不能只显示 HTTP 状态，否则会把合同错误
   误判为模型无法分析炉况。
5. 2026-08-14 生产修复已由一次真实固定首问验收：请求数 `1`，SSE 为
   `preparing → prepared → delta → final → done`。对应版本为 Git `d24543a` / 标签
   `prod-8093-abc33-http400-20260814-r2`；若再次出现 400，先比较浏览器实际加载的
   `bf-abc33-assistant-dialog.js` 缓存版本和响应 `error_code`，不要自动重发。
