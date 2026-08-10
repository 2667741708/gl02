# 排障手册

## 8093/8094 炉况卡显示“智能分析暂不可用”

2026-08-06已确认过一种明确根因：共享 `ollama_proxy_server.py` 已是支持v3单炉况调用的新版，但远端 `diagnosis_model_review.py` 和 `diagnosis_ai_analysis_api.py` 仍是旧版，形成模块版本错位；8094同时缺少启用环境变量。表现为Ollama健康正常，但分析长期停在准备态，或接口直接返回 `enabled=false`。

- 先请求 `GET /api/diagnosis-ai-analysis?label=normal`。HTTP 202表示后台正在生成，不应重复刷新；`failed` 表示本桶生成失败，需等待 `BF_DIAGNOSIS_AI_ANALYSIS_RETRY_SECONDS` 后重试。
- 检查目标端口实际进程是否启用 `BF_DIAGNOSIS_AI_ANALYSIS_ENABLED/BACKGROUND_ENABLED`，并确认 `BF_DIAG_REVIEW_PG*` 仍指向220.12回环PostgreSQL。
- 查询 `bf_assistant.diagnosis_ai_analysis_snapshots` 的 `generation_state/attempt_count/last_error_code/updated_at`；错误字段只记录类型，不保存Prompt、模型原文或密码。
- 确认 `bf_sensor.diagnosis_snapshots` 有最新诊断、8093 `/api/ollama/status` 正常且11434仍只驻留批准模型。
- 同时核对代理、模型合同、证据编排和分析API四个模块的版本/哈希，不能只看共享代理文件。v3正常标记为 `diagnosis_ai_analysis.v3` 和 `diagnosis-single-condition-five-minute.v3`。
- 不要通过浏览器构造诊断分数重试；后端只接受炉况标签并重读当前快照。8093走守卫闭环；8094使用 `remote_guarded_enable_8094_diagnosis_ai.ps1`，不得恢复8769旧架构。

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
