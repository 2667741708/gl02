# 错误追踪

## ERR-FOREMAN-COAL-POINT-AND-INTEGRATION-20260806

- 现象：工长趋势的上小时/本小时喷煤量与2号高炉现场画面不一致；部分未映射点显示为0；接入8770秒级流后，本小时喷煤量会随消息帧数异常放大。
- 根因一：早期候选误用了`\冀南二期\EQ\SI0\GL02`树中数值相似但业务语义不对应的点位。生产画面属于`\冀南钢铁\SIO\GL02`；正确上小时点为`PC/T0004`，喷煤实际速率为`PC/T0007`。
- 根因二：旧积分把每个`PCI_rate`样本都按一分钟计算，即`sum(rate/60)`。8770每数秒更新后，同一分钟被累计多次。另有`Number(null)=0`使缺测被误显示为真实0。
- 修复：上小时优先直接读取T0004；本小时用相邻时间戳实际毫秒差把`t/h`积分为`t`，超过150秒的缺口不无限补算；空值保持`--`；新增点位全部限定GL02 SIO且写入本机点位目录。
- 回归：5秒采样一小时比例、11:00–11:19定值、10分钟长缺测三类Node测试通过；相关pytest 9项通过；本机目录150条并通过幂等核验。220.12部署因当前aTrust无活动路由仍待执行，不能把本机结果冒充生产验收。

## ERR-8093-DIAG-AI-MODULE-VERSION-SKEW-20260806

- 现象：炉况弹窗显示“本时间点的智能分析暂未生成成功”，8093分析接口长期为准备态；8094接口报告功能未启用，但两端 `/api/ollama/status` 正常。
- 根因：8093共享代理已升级到单炉况v3调用，远端 `diagnosis_model_review.py` 和 `diagnosis_ai_analysis_api.py` 仍为旧版，运行时代码合同不一致；8094启动器没有设置复核和AI分析开关。
- 修复：同步证据、模型合同和分析API模块；8093通过守卫停—改—启，8094在现有共享代理架构上补环境并精确重启自身。没有使用过时的8769/隔离代理部署器。
- 回归：8093、8094均能返回 `diagnosis_ai_analysis.v3`；部署验收确认分析包含变量、调剂建议和知识依据，免登录评分可提交。8094变更期间8093/8768/8770/11434 PID均未变化。
- 回滚：8093备份 `logs/deploy_backups/diagnosis_ai_analysis_20260806_072403`；8094备份 `logs/deploy_backups/8094_diagnosis_ai_20260806_073217`。

## ERR-LOCAL-PSQL-EMPTY-ENV-ARGSHIFT-20260804

- 现象：依次出现 `could not translate host name "-p"`、`fe_sendauth: no password supplied`，清理时又出现 `Env:\PGPASSWORD`不存在。
- 根因：当前PowerShell中的`BF_DIAG_REVIEW_PG*`变量全部为空，`-h`因此把后面的`-p`当成主机名；显式地址命令又使用了小写`-w`（禁止密码提示），但`PGPASSWORD`并未设置；最后对不存在的环境变量执行了非幂等删除。
- 处理：先在同一PowerShell窗口完成变量赋值并确认非空；使用`PGPASSWORD`时保留`-w`，需要手工输入时改用大写`-W`；清理使用`Remove-Item Env:PGPASSWORD -ErrorAction SilentlyContinue`。完整命令见[数据库账号配置说明](数据库账号配置说明.md#原生-postgresql-16-管理员连接)和[排障手册](troubleshooting.md#本机-postgresql-psql-参数错位与密码缺失)。
- 回归：2026-08-04使用受控本机配置只读登录`127.0.0.1:18000/bf_trend`成功，返回`current_user=postgres`、PostgreSQL `16.13`，并查询到`bf_assistant.diagnosis_review_events`和`diagnosis_manual_score_events`；说明数据库服务正常，故障仅在调用shell的临时环境与psql参数。

## ERR-8096-LOCAL-PORT-IN-USE-20260804

- 现象：执行 `python tools/start_diagnosis_review_preview.py --fixture-only` 时，启动器报告“本机端口 8096 已被占用”并退出。
- 根因：一份由较高权限会话启动的旧本机诊断复核 Python 进程仍监听 `127.0.0.1:8096`；启动器的端口预检按设计拒绝覆盖既有服务。
- 处理：先通过监听 PID和 `/api/diagnosis-review-context` 返回的 `local_fixture` 来源确认进程身份，再只结束精确 PID；普通权限收到 `Access is denied` 时，通过管理员 UAC 对同一 PID 执行 `taskkill /PID <PID> /F`，禁止按 `python.exe` 进程名批量结束。
- 回归：2026-08-04 已停止旧监听 PID `59568`；复查无 `8096 LISTENING` 记录且 `http://127.0.0.1:8096/` 不可访问，未操作220.12的8093、8094、8768或数据库服务。

## ERR-8094-RESTART-ORPHAN-20260804

- 现象：停止计划任务 `V3AutoPreviewProxy8094` 后，旧 Python 子进程仍可能继续监听 8094；计划任务自动拉起时也不一定出现可观察的端口空窗。新进程刚监听时，首次 HTTP 请求还可能被关闭连接。
- 根因：计划任务状态与其子进程生命周期并非严格同步，历史失败还会留下父进程已不存在的 V4 8094 孤儿进程。
- 修复：`tools/restart_22012_8094_preview.ps1` 只清理“命令行属于 V4 8094、父进程不存在、且不监听 8093/8094”的精确孤儿 PID；只在核对 8094 监听 PID、命令行和父进程链后结束旧监听进程；验收改为旧 PID 退出且新 PID 不同，并对冷启动 HTTP 做有限重试。禁止按进程名批量结束 Python。
- 回归：2026-08-04 `13:57:16` 成功清理孤儿 PID `13924`，8094 PID `2688 -> 9976`，HTTP 200；8093/8768/8770 PID 保持 `13788/10868/12956`。

## ERR-8093-GUARD-STATUS-ENUM-20260804

- 现象：首次运行 8093 底部空白守卫部署器时，`Get-Service` 返回的状态对象在远端执行链中显示为枚举数值 `4`，直接与字符串 `Running` 比较导致预检误报；预检失败发生在停服务和写文件之前。
- 根因：PowerShell 服务状态枚举跨执行/序列化边界后的比较类型不稳定。
- 修复：`tools/remote_guarded_deploy_8093_cad_bottom_band.ps1` 统一使用 `.Status.ToString()` 比较服务状态；任何预检失败仍不得进入写入阶段。
- 回归：该枚举修复后 R1 闭环通过；R2 最终再次通过 `guard_paused=true`、`guard_restored=true`、8093 HTTP 200，页面 SHA-256 为 `0AB75FF725FC889062C051ED1A6775C25E796F474151DACD95E791044896A3F4`，8094/8768/8770 和受保护文件未变化。

## ERR-BF3D-CANVAS-BOUNDARY-MEASUREMENT-20260804

- 现象：R1 截图仍存在明显深蓝底部空带，但验收报告却称 stage/viewer 底差约 `0.606px`、修复通过。
- 根因：验收量错了边界，只比较 `.furnace-stage-3d` 与 `.cad-furnace-viewer`，没有比较实际 Three.js canvas 与炉况总览 panel-body；因此漏掉旧 `.overview-grid>.panel:last-of-type .panel-body` 规则产生的 `46px`（窄断点 `66px`）底部 padding。
- 修复：R2 补丁新增炉况总览直属 panel-body `padding-bottom:0 !important`，并新增修订标记 `BUG-BF3D-CAD-PANEL-BODY-GAP-20260804-R2`。浏览器验收口径固定为 `canvas.bottom -> panel-body.bottom`，只允许 `0–1px`。
- 回归：8093/8094 Chrome `1552×816` 的真实底差均为 `0.606px`，panel-body `padding-bottom=0px`，横向溢出为 0；新截图中白色画布直达面板底部。旧验收报告已标记作废。

## ERR-8093-GUARD-ISOLATION-DIAGNOSTIC-20260804

- 现象：8093 R2 首次守卫闭环已完成补丁和服务恢复，但最后只返回笼统的“post-deploy isolation check failed”，没有指出失败项。
- 根因：部署器对 8094 计划任务状态的后置比较没有统一 `.ToString()`，且失败分支没有输出前后 PID、哈希和逐项布尔值。
- 修复：统一任务状态字符串比较，并在失败时输出 `failures`、`pid_before/pid_after`、`hashes_before/hashes_after`；成功结果引用真实逐项结果，不再写死 `true`。
- 回归：再次执行幂等守卫闭环成功，`guard_paused=true`、`guard_restored=true`，8094/8768/8770 PID 均未变化，受保护的 8094/共享资源哈希均未变化。

## ERR-8093-ASSISTANT-HYBRID-SINGLE-MODEL-RISK-20260804

- 现象：8093 智能助手页面无回复，但 `/api/ollama/status` 仍报告代理、Ollama 和模型全部正常。
- 取证：`BFV4PreviewProxy8093`、`BFOllama11434` 正在运行；状态接口 HTTP 200；11434 `/api/ps` 只驻留 27.8B。8093 实际进程 `BF_QA_KNOWLEDGE_SEARCH_MODE` 为空，代码默认值为 `hybrid`；Ollama 实际 `OLLAMA_MAX_LOADED_MODELS=1`。
- 原因判断：健康接口没有覆盖 `/api/qa/chat` 的数据库、RAG、MCP 和 SSE 全链路。空搜索模式与单模型驻留组合会在知识检索触发 `nomic-embed-text` 时争用唯一模型槽，属于独立的高风险配置候选；本轮已经确认的直接中断原因见下方守卫重启项。
- 固化：新增 [只读健康探针](../tools/probe_8093_assistant_health.ps1) 与 [AGENTS 分层流程](../AGENTS.md#8093-智能助手无回复固定检查流程2026-08-04)，明确状态绿灯不能替代一次真实 SSE 验收，也不得恢复 `OLLAMA_MAX_LOADED_MODELS=2`。
- 后续解决：2026-08-05 已通过 [8093 关键词模式受控部署器](../tools/remote_guarded_deploy_8093_keyword_knowledge_mode.ps1)把启动环境显式设为 `BF_QA_KNOWLEDGE_SEARCH_MODE=keyword`，没有迁移 embedding、没有重启 Ollama，也没有把 `OLLAMA_MAX_LOADED_MODELS` 改回 2。现行配置 SHA-256 为 `8A24C83DF93008DD8E358682558E8755442D87052A09FB24F39778F2EAF51FDE`，备份为 `logs/deploy_backups/8093_knowledge_keyword_20260805_072445`。
- 回归：实际 8093 监听进程与默认知识搜索均显示 `keyword`，默认搜索命中 2 条证据；08:44 只提交 1 次知识问答，准备态证明知识检索启用、意图 `parameter_optimization`、MCP 工具关闭，SSE 在 `23.8856s` 完成。验收期间未加载 embedding、没有守卫重启、8768/8094/8770/11434 PID 未变化。报告为 `logs/acceptance/8093_keyword_knowledge_20260805_20260805_084403/assistant_keyword_knowledge_sse_once.json`。

## ERR-8093-ASSISTANT-HEALTH-RESTART-LOOP-20260804

- 现象：智能助手正在等待回复时无首事件或响应中断，但稍后刷新 `/api/ollama/status` 又显示全部正常。
- 证据：[日志尾部探针](../tools/probe_8093_assistant_log_tail.ps1)在 `proxy_8093.health.log` 中确认 `20:46`、`20:47`、`20:51`、`20:56`、`21:48` 的本机 8093 TCP 短时不可达，以及 `20:59`、`21:15` 的状态接口不可达；每次失败后紧跟 `restart_service_done`。runner 日志存在对应新进程启动，错误尾部主要为受控中断产生的 `KeyboardInterrupt` 和客户端断开后的 `BrokenPipeError`，没有发现模型崩溃栈。
- 直接原因：健康守卫把短时 TCP/状态探测失败迅速升级为代理重启，重启会切断在途 `/api/qa/chat` SSE；这解释了“健康页之后恢复正常，但当次智能助手不回复”的现场表现。
- 根因代码：远端共享 [健康脚本](../tools/check_managed_nssm_service_health.ps1)旧版在单轮 `$failures.Count -gt 0` 后直接 `Restart-Service`；计划任务 `\BlastFurnaceServices\BFV4PreviewProxy8093HealthCheck` 每分钟运行，因此一次瞬时失败即可切断在途 SSE。
- 修复：仅为 8093 配置 `failureThreshold=3`、`serviceNotRunningFailureThreshold=1`、`preRestartBackoffSeconds=15`、`restartCooldownSeconds=600`；共享脚本增加跨任务运行的状态文件、连续失败计数、退避后二次确认和冷却抑制，其它未配置服务维持旧默认。
- 部署：2026-08-04 22:54 通过 [守卫部署器](../tools/remote_guarded_deploy_8093_health_guard.ps1)上线，脚本 SHA-256 `1A4B2C56D5E86BC6DCC7D82700142BF40B936492712A20AD34997953DCD9C2B3`，8093 配置 SHA-256 `D20F01F1E66FF8973AB6720DDEB450AEE50FAE2AC6FFB023E1C04EACA066EACA`，回滚目录 `logs/deploy_backups/8093_health_guard_20260804_225350`。
- 现行哈希说明：上述 `D20F...EACA` 是守卫修复当时配置；2026-08-05 只增加关键词知识模式后，完整配置现行 SHA-256 为 `8A24C83DF93008DD8E358682558E8755442D87052A09FB24F39778F2EAF51FDE`，守卫合同与共享脚本哈希未变。
- 验证：本地前两次失败均为 `restart_deferred` 且恢复后计数清零；远端任务执行结果 0，部署期间 8093/8768/8094/8770/11434 PID 均未变化。23:03 仅提交一次真实 SSE，完整收到 `start -> delta -> final -> done`，约 `6.58s` 完成，期间无守卫重启，模型仍只驻留批准的 27.8B。
- 长期修复入口：[AGENTS 直接修复记录](../AGENTS.md#8093-智能助手再次不可用时的直接修复记录长期固定)与 [DOCX 正式手册](8093智能助手不可用原因与正式修复手册_20260804.docx)。手册明确“有守卫重启证据”和“无守卫重启证据”两条分支，避免把所有无回复机械归因于同一问题。

## ERR-8093-MCP-HEAT-COMPOSITE-ROUND-LIMIT-20260805

- 现象：在8093询问“当前属于第几个炉次？上一个炉次铁水的硅含量平均值是多少？”后，页面返回“数据库查询轮数超过上限，请缩小问题范围或明确变量名”。
- 直接机制：该文字由[问答MCP循环](../高炉前端数据/智能助手/backend/ollama_proxy_server.py#L4497-L4751)在模型连续两轮仍要求调用工具时主动返回；当前代码默认`BF_QA_MCP_MAX_TOOL_ROUNDS=2`、总工具调用上限4次。它不是PostgreSQL、Vastbase或pSpace返回的数据库错误。
- 结构根因：8093一次问答只启动`BF_QA_MCP_DATA_SERVER`指定的一个stdio服务，默认是`bf_data_mcp_server.py`。统一目录虽然能发现“高炉炉次/铁水化学成分”，但其执行器指向独立的`imes-relay-mcp`；`query_hot_metal_chemistry_by_heat`不在8093当前列出的18个数据MCP工具中，跨服务执行没有接通。此外炉次对象仍引用不存在的`query_imes_business`，实际IMES服务提供的是`query_imes_object`等工具。
- 业务缺口：当前没有“确定当前炉次→求上一炉次→读取该炉次多次铁水试样→聚合Si平均值”的单一复合工具或确定性路由。原问题需要多步依赖，却落入通用模型规划；两轮延迟上限因此把合同缺口暴露成了误导性的“请缩小范围”。
- 运行核查：2026-08-05只读检查确认220.12同时部署了两个FastMCP实现文件；8093端口正在监听，空闲时没有`bf_data_mcp_server.py`或`imes_relay_mcp_server.py`常驻子进程，符合stdio按请求启动模型。8093 Windows服务同时处于`StartPending`但端口已监听，这是独立的服务生命周期异常，不是该轮数提示的来源。
- 取证边界：问答的`mcp_tool_trace`会写入`bf_assistant.qa_messages.hidden_context_json`，但本轮读取07:07:27记录时SSLVPN/220.12连接超时，因此没有宣称已还原该次具体工具序列；上述结论来自返回分支、当前运行配置、工具清单和目录/执行器合同的静态与运行交叉核对。
- 建议修复方向：为高频炉次问题增加只读复合工具和确定性口语路由，或让编排器显式联合数据MCP与IMES MCP；规划轮数限制只约束模型回合，不应限制复合工具内部的参数化只读查询。错误码应区分`PLAN_ROUND_LIMIT_EXCEEDED`、`TOOL_NOT_ATTACHED`、`NO_DATA`和`AMBIGUOUS_OBJECT`。
- 2026-08-05 本地修复：已实现两服务注册表、多 Client Host、IMES 命名空间、确定性 MES 意图门控和一次复合工具 `imes__get_current_previous_heat_si_summary`；统一目录中的错误工具名已修正。生产 Host 同时屏蔽 `query_imes_readonly_sql`。本地相关回归 `38 passed`，真实 MCP SDK 服务发现通过。
- 当前状态：2026-08-05 已完成 220.12 受控部署；真实 MES 单次 SSE 成功命中 `imes__get_current_previous_heat_si_summary`，原错误已关闭。验收返回上一炉有效 Si 试样数为 `0`/`NO_SI_SAMPLES`，这是数据源状态，不是路由失败。部署与 PID/备份证据见[交接记录](handoffs/2026-08-05-8093-multi-mcp-deploy.md)。

## ERR-8093-HEADER-MINUTE-TIME-AS-WALL-CLOCK-20260805

- 现象：8093 顶栏“时间”和“刷新”明显落后电脑时钟，现场误以为页面整体实时流延迟一到两分钟。
- 根因：两个位置都绑定 React `currentTime`；该状态由 8768 的 PostgreSQL 分钟镜像 `msg.timestamp` 更新，不是系统时钟，也不是 8770 pSpace 当前值时间。
- 修复：顶栏“时间”改为每秒更新的终端系统时钟；原分钟时间改名“分钟数据”并继续显示 `currentTime`。核心行仍显示独立的 pSpace 数据时间、源年龄和质量。
- 回归：系统时钟合同 7 项通过；受控部署 `system_clock_marker_served=true`，守卫已恢复，8768/8770/8094 未变化；Edge 实测秒差 `1.231s`。

## ERR-8093-STATIC-ASSET-EMPTY-RESPONSE-20260805

- 现象：系统时钟多视口验收连续重载完整页面时，前五个桌面视口可运行，随后部分请求出现 `ERR_CONNECTION_RESET` 或 `ERR_EMPTY_RESPONSE`；失败资源包括 `libs/echarts.min.js`、`OrbitControls.js` 和 `/api/trend/history`，资源缺失时 React 图表组件无法挂载。
- 判断：该故障不来自时钟补丁；同一轮已成功页面的时钟秒差、pSpace 28/28 和布局均正常，失败请求冷却后单独 HTTP 又返回 200。表现指向 8093 静态代理在连续大页面/大资源加载下的间歇响应压力。
- 验收处理：没有把窄屏失败写成通过；正式证据只引用成功的 Chrome 桌面视口和 Edge `1366×768`。验收器增加有限导航重试和显式视口，但不屏蔽真实资源错误。
- 后续：应单独压测 8093 静态资源并检查代理并发、连接复用和文件发送错误日志；修复需走独立需求，不能为了让矩阵变绿而忽略 ECharts/Three.js 加载失败。

## ERR-8093-MCP-STALE-OPEN-HEAT-20260805

- 现象：IMES Web 可显示 `2#20260805-065` 的 Si=0.23%，但 8093 复合工具返回旧的
  `2#20240805-056/055`，并给出 `NO_SI_SAMPLES`。
- 只读证据：220.12 `10.10.181.195:5432/vastbase` 的 `operations/gl2#dmx` 账号直接查询到
  `2#20260805-065` 的三条正式记录（Si=`0.20/0.25/0.24`，平均 `0.23%`），
  `2#20240805-056` 为零条；`t_ipes_cond` 的最新已完结排序为 `065`、`064`、`063`。
- 根因：`_query_recent_heat_context_rows` 的活动排序只检查 `closetime IS NULL`，没有限制未关口记录的
  时间新鲜度。一条 2024 年遗留的未关口行被判为“当前 active”，优先级高于 2026 年已完结的 065，
  因而复合工具读取了错误炉次；`NO_SI_SAMPLES` 是错误炉次选择的后果，不是数据库缺数。
- 连接边界：远端 `laboratory` profile 当前未配置，但 Si 065 已由 `operations` 的
  `t_qpes_inner_batch + inner_batch_insp_bb` 读取；laboratory 仍需为炉渣/进料视图另行补齐。
- 修复合同：活动炉次必须增加合理的最大活动时长/时间新鲜度约束，或改为先按正式炉次号和 `opentime`
  取最新记录、再单独计算 active；回归必须固定检查 `current=065`、`previous=064`、
  `sample_count=3`、`si_avg=0.23`，并保留旧未关口记录场景。

## ERR-8093-MCP-DIAGNOSIS-HISTORY-20260805

- 现象：用户询问“之前有一阵的管道分数上升，可能是什么原因？分析一下？”时，8093 返回“数据库查询轮数超过上限，请缩小范围或明确变量名”。
- 直接机制：该提示由[问答MCP循环](../高炉前端数据/智能助手/backend/ollama_proxy_server.py#L4592-L4867)在模型连续两轮仍未完成工具计划时生成；默认 `BF_QA_MCP_MAX_TOOL_ROUNDS=2`，总工具调用上限为4次。它不是 `bf_sensor` 查询为空，也不是数据库连接错误。
- 数据能力边界：后端已有 `recent_pg_diagnosis_snapshots_for_qa`，可以从 `bf_sensor.diagnosis_snapshots` 读取最近约8小时、5分钟粒度的诊断时间线，并在隐藏问答上下文中提供 `main_score`、`raw_scores.channel` 等分数。只读检查 `http://127.0.0.1:8093/api/automation/status` 返回 `ok=true`、`database_ok=true`；当时最新诊断为 `2026-08-05 13:05`、`main_label=normal`、`main_score=50.59`，运行队列记录了12个诊断点，说明历史分数正在生成。
- 结构缺口：8093 MCP目录当前只有[最新炉况快照工具](../高炉前端数据/智能助手/mcp/bf_data_mcp_server.py#L3314)，没有“历史诊断分数/某标签分数趋势”专用工具；“管道分数”也没有映射到确定性传感器或诊断标签路由。于是带“分析”的问题被送入通用模型规划，模型反复试探目录、快照或传感器工具，最终撞上两轮上限。
- 当前状态：本轮仅完成只读代码、接口和运行状态核查，未修改远端代码、配置、数据库或重启服务。结论是“历史炉况分数数据可由后端读取，但当前作为MCP能力并未稳定暴露”，不能把轮数提示解释成数据不存在。
- 推荐修复：新增只读 `query_furnace_diagnosis_history(start_time,end_time,target_labels,limit)`（或等价的最近窗口工具），返回时间戳、主/次炉况、分数、`channel` 分数、来源和覆盖率；为“管道分数/炉况分数/诊断分数/前几次/一阵”增加确定性路由，优先一次调用该工具并由格式化器分析上升段。若隐藏上下文已含所需时间线，也可直接走历史分析路径。单纯把模型轮数调大不是根治方案。

## ERR-8093-ASSISTANT-REPAIR-PROCESS-SLOW-20260805

- 现象：此前恢复智能助手耗时较长，需要重复查服务、端口、进程环境、守卫日志、知识模式、模型驻留，再临时上传部署脚本；PowerShell 5.1 中文编码、命令长度和 JSON 数字键还会在执行时才暴露。
- 流程根因：诊断入口分散，网络/VPN 恢复没有与部署计时分离；远端脚本没有预置 immutable package；部署和文档生成处于同一人工链；`hybrid + 单模型驻留` 已知风险没有编码成直接分类；缺少真实 PS5.1 序列化门禁。
- 修复：[统一编排器](../tools/assistant_8093_auto_recovery.py) 固定 `连通性 -> 只读取证 -> 分类 -> 条件备份 -> 最小部署 -> 运行态复核 -> 默认知识搜索 -> 唯一 SSE -> 报告`，以 SHA-256 包和短 `-File` 执行。已知 hybrid 漂移直接 keyword；未知哈希拒绝。
- 回归：本地 `22 passed`，其中两项调用真实 PowerShell 5.1；包 `20260805_v1_22e4eb675eee` 已预置并复用。真实 diagnose 约 67 秒完成 healthy 分类；完整 recover 服务阶段 `184.618s`、无部署、唯一 SSE `22185.9ms` 成功。
- 长期入口：[AGENTS 强制首选流程](../AGENTS.md#8093-智能助手一键自动诊断修复验收2026-08-05强制首选)、[专项文档](8093智能助手自动诊断修复验收工具_20260805.md)和[CLI](cli_usage.md)。

## ERR-8093-PSPACE-APP-VPN-MISDIAGNOSIS-20260805

- 现象：本机 `Invoke-WebRequest/Test-NetConnection` 无法连接 `10.30.220.12:8093`，容易被解释为 8093、8770 或 pSpace 通道已经关闭。
- 本机证据：aTrust 相关进程和服务仍在，但 Sangfor aTrust VNIC 显示断开，系统路由表没有 `10.22/10.30` 路由；启动托盘和打开门户不会自动给所有本地进程建立系统路由。
- 反证：同一时刻，经已认证 aTrust 门户“高炉模型”应用代理的 Chrome 能正常加载 8093；页面状态为 `pSpace秒级实时 28/28`，时间持续推进，数据年龄为秒级且质量良好。
- 根因分类：这是“普通本地网络路径与 aTrust 应用代理路径不同”造成的误判，不是已证实的生产服务故障。aTrust 扩展日志中存在自身 `content_main.js` 的空节点/Failed to fetch 错误，但8093页面没有 8770/pSpace/WebSocket 错误。
- 处理：健康状态下不重启 8093/8770/8768/8094，不修改数据库。以后先在授权浏览器中检查实时横幅和时间推进；只有出现“已降级为分钟镜像”、状态不推进或明确 WebSocket 错误时，才继续查 8770监听、计划任务、220.12→243:8889 和 pSpace SDK读取。

## ERR-PSPACE-DUPLICATE-SYNC-WRITERS-20260805

- 现象：`sync_runs` 成对出现，220.12同时存在两个孤儿`run_realtime_sync_pg_bg.ps1`包装器，各自启动pSpace同步子进程，导致重复读取与重复upsert。
- 根因：主任务和Watchdog历史上分别从中文主目录与`db_sync_storage`镜像启动；旧锁位于各自目录，不能互斥，且父任务结束后包装器仍存活。
- 修复：两套包装器统一使用`<项目根>\logs\realtime_sync_pg.lock`的`FileShare.None`排他锁；部署时定向停止3个相关PID后只启动主任务，Watchdog恢复后不得产生第二包装器；旧Realtime保持禁用。
- 验证：当前只有一个PowerShell包装器；其下虚拟环境启动器和实际Python解释器属于同一父子进程链。最近完成运行不再成对，`tags_ok=133/tags_error=0`。
- 边界：不得按`python.exe`名称批量结束进程；只匹配项目根及同步脚本命令行。回滚备份见[pSpace分钟语义统一](pSpace分钟语义统一_20260805.md)。

## ERR-8093-MODEL-API-WRONG-ORIGIN-20260806

- 现象：用户在 IMES Web 页面中使用高炉智能助手时提示无法连接高炉大模型。
- 只读证据：220.12 的 `http://127.0.0.1:8093/api/ollama/status` 返回 HTTP 200，`proxy_ok=true`、`ollama_ok=true`、`model_ok=true`；11434 `/api/ps` 正常加载 `chiqiong-blast-furnace:latest`。8093 真实 SSE 单次请求 HTTP 200，约 6.9 秒返回答案。
- 对照证据：`http://127.0.0.1:18080/api/ollama/status` 返回 Nginx `404 Not Found`。8093 前端的 `fetch('/api/qa/chat')` 和 `fetch('/api/ollama/status')` 是相对路径，页面必须从 8093 同源打开；从 18080/8092/本机其他端口打开时，请求会发往错误端口。
- 根因分类：模型后端没有宕机，问题是前端页面来源与问答 API 来源不一致；若必须从 18080 进入，需要把 `/api/qa/*`、`/api/ollama/*` 和相关 SSE 路径反向代理到 8093，并保持 SSE/缓存头。
- 当前处理：未重启服务、未修改数据库或生产配置。临时验证使用 `http://10.30.220.12:8093/frontend_dashboard_v3.server.html?ws_port=8768`，并执行 Ctrl+F5；正式修复应单独走 18080→8093 反向代理需求。

## ERR-8093-ASSISTANT-FETCH-RESET-20260806

- 现象：07:29 的顶压问答成功，07:38 的“最近4炉次硅含量”在浏览器显示 `Failed to fetch`，前端将其统一显示为“代理不可达或问答服务未启动”。
- 现场复核：当前 8093 `/api/ollama/status` 与 `/api/qa/mcp/health` 均 HTTP 200；同一 `/api/qa/chat` 端点使用 `Connection: close` 可完整收到 `event: done`。重复只读探针曾出现间歇性 `RemoteDisconnected`，成功请求延迟约 1–6 秒，说明失败窗口属于 8093 HTTP 连接重置/短时服务抖动，而非 11434 模型不可用。
- 边界：当前尚未取得 07:29–07:38 的远端守卫日志，不能把该时间段确定归因于一次服务重启；上线后的 8093 PID 曾发生过变化，需结合守卫日志确认。
- 建议：前端对 `/api/qa/chat` 增加一次带退避的安全重试，并在发送期间禁止重复提交；同时将守卫重启事件与 SSE 断开事件关联记录。不要通过提高模型轮数或重启 8768/8094/8770 处理。

## ERR-8093-MCP-RECENT-HEAT-SI-HISTORY-20260806

- 现象：“最近有几个炉次了”没有调用 MES，而是用隐藏炉况上下文回答无法确认；追问“看看更早炉次硅含量趋势”返回“数据库查询轮数超过上限”。
- 根因：`qa_mcp_imes_plan()` 只确定性覆盖“当前炉次”和“上一炉/前一炉 + Si”；`qa_mcp_imes_query_intent()` 的事实词没有“最近/几个/更早/趋势”。现有 IMES 工具只有当前/上一炉复合摘要，以及需要模型补日期参数的 `query_hot_metal_silicon(start_date,end_date)`，没有“最近 N 炉按炉次聚合 Si”工具。
- 结论：MES 数据源和当前 079/上一炉 078 查询本身可用；失败属于口语意图和工具合同缺口，不是 Vastbase 无数据。模型在缺少一次完成的历史炉次工具时重复规划，最终触发两轮上限。
- 推荐合同：新增只读 `imes__query_recent_heat_si_summaries(limit, before_heat_no, include_current)`，返回正式 `meltno`、每炉试样、样本数、均值、最小/最大值、取样时间和缺失原因；为“最近几个炉次/最近炉次 Si/更早炉次/硅含量趋势”建立确定性路由和上下文翻页，禁止通过提高模型轮数解决。

## ERR-8093-MCP-ARBITRARY-HEAT-CHEMISTRY-20260806

- 现象：底层已有按炉次化验查询，但工具名、结果合同和规划提示不够面向模型；指定炉次多成分问题可能先调用语义解析，再调用原始化验工具并继续规划，存在误选和轮数超限风险。
- 根因：能力目录只声明旧 `query_hot_metal_chemistry_by_heat`，没有“组件选择+样本+汇总”的单调用合同；模型规划时收到整个IMES服务的全部Schema。
- 修复：新增 `query_heat_chemistry`，内部解析炉次并一次返回完整事实；指定炉次化验仅向模型提供实时注册的两个相关Schema；模型选中事实工具后直接进入确定性格式器。
- 边界：本修复解决“任意指定炉次”；“最近几个/更早炉次趋势”仍由 `ERR-8093-MCP-RECENT-HEAT-SI-HISTORY-20260806` 的分页汇总工具单独解决，不以本工具冒充完成。

## ERR-OPT-COCKPIT-ZERO-HEIGHT-20260806

- 现象：升级8炉况矩阵后，1366×768 的建议页只剩文字/审计区域，原有主证据、炉况演化和基线偏离图表不可见或互相覆盖。
- 定位：[旧驾驶舱入口](../高炉前端数据/frontend_dashboard_v3.server.html#L10476)本身仍生成图表；外层新增矩阵、标题、驾驶舱、审计和模型面板后仍使用 `height:100%` 固定网格。只读测量得到 `.opt-cockpit-top=0px`，底部图表越界到审计区域；新版4项证据卡同时遗漏 `ChartBox`。
- 修复：[可视工作台](../高炉前端数据/frontend_dashboard_v3.server.html#L10591)使用单一内部纵向滚动和自动行高，驾驶舱顶部最小430px、底部图表最小300px；审计/模型进入固定抽屉；4项证据恢复独立迷你曲线。
- 防回归：[测试](../tests/test_recommendation_visual_workbench.py#L23)检查标记、19项集合、图表与抽屉；[浏览器矩阵](../tools/verify_remote_recommendation_pages.cjs)要求顶部高度至少280px、底部至少250px、4项主证据和19项核心证据均存在且无横向溢出。

## ERR-OPT-8094-CORE-EVIDENCE-RUNTIME-20260806

- 现象：首轮发布后8093正常，但8094进入建议页时React根节点卸载，控制台为 `ReferenceError: useCoreMetricRealtime8093 is not defined`；因此只检查HTTP 200和静态标记会漏掉真实运行错误。
- 根因：8094补丁器只复制建议功能块；首版19变量证据中心直接引用了位于8093专属后置运行时中的实时Hook和详情依赖，8094生产基线没有该Hook。4项主证据迷你曲线也曾只改在8093原驾驶舱定义里，没有进入可移植功能块。
- 修复：R2在功能块内增加独立的分钟缓冲当前值适配器、统计/相关性边界和8094专用4项主证据曲线；当基线已有完整详情组件时复用，缺失时使用可移植详情降级。8093继续复用其秒级实时详情，不重复主证据曲线。
- 防回归：测试必须从真实8094基线执行[补丁器](../tools/patch_8094_multi_condition_review.py)，再实际挂载页面；要求8炉况、4项主证据、19项唯一变量、详情弹窗和分组对比可用。最终8094补丁页SHA-256 `876C14DF1F5620D3333C0F4AAC6D202FACE508E5C4C82E707F4E4D939A187C69` 与远端一致，双页跨浏览器矩阵 `34 checks / PASS`。

## ERR-8093-ASSISTANT-DEPLOYMENT-COLLISION-20260806

- 现象：浏览器稳定显示 `接口状态：Failed to fetch`；首次连通性门禁确认 SSH 22、PostgreSQL 5432、Ollama 11434 正常，只有 8093 不监听，所以这不是前端误报。
- 证据：Windows SCM 在 `09:57、10:01、10:05、10:11、10:16、10:18、10:23、10:29` 记录 8093 停止/启动；`proxy_8093.service.err.log` 只有受控停止引发的 `KeyboardInterrupt`，没有同期自然崩溃堆栈；诊断期间后端和服务配置 SHA-256 仍在变化，证明另有部署流程在改写并重启同一服务。
- 根因：多个部署/恢复流程没有共享跨进程互斥，造成重叠的停止—修改—启动窗口。该端口空窗直接导致浏览器 fetch 失败，并可能切断在途 SSE；不是 2026-08-05 已修复的 PostgreSQL 连接池嵌套，也不是 11434/27B 整体宕机。
- 修复：统一恢复器和新页面热部署器使用 `Global\BFV4PreviewProxy8093Deployment`；服务恢复执行已知哈希、守卫 `finally` 恢复、15 秒退避和最多两次启动；纯页面变更原子热更新，不重启 8093。页面只对只读 GET 做 1.5 秒/3 秒有界退避，问答 POST/SSE 不自动重发。
- 验收：2026-08-06 10:51 唯一一次 SSE 为 `preparing → prepared → delta → final → done`，总计 `33993.3ms`，keyword 证据 2 条，问答前后 8093/8768/8094/8770/11434 PID、配置与守卫哈希均未变化；本地报告为 `logs/assistant_8093_auto_recovery/20260806_105139_recover.json`。

## ERR-FOREMAN-SYNC-CATALOG-ROLLBACK-20260807

- 现象：轻量注册器已把 CO/H2/CO2 和三项 BT 点写入 `sensor_registry`，但既有同步任务连续记录 `sync_runs.tags_ok=148`，新增跨子树点没有 `one_minute_values` 行。
- 根因：此前受控部署在注册后续阶段超时/失败，文件回滚恢复了旧清单；数据库注册写入未随文件回滚，因此形成“注册表新、同步清单旧”的部分状态。
- 修复：把 `run_realtime_sync_pg_bg.ps1` 纳入同一候选包，并在入口内显式传 `--config <ScriptRoot>\\config\\sync_config.json`；部署器、热更新器和文件安装器一并原子替换入口与清单。恢复任务后必须以入口哈希、153行清单、`tags_ok` 和新增点 Good 分钟值共同验收。
- 状态：本机修复已完成并通过11项测试；远端尚待重新分步上传、部署和验证，不能把当前148点运行态当作修复完成。
# BUG-ABC33-ENTRY-DETAIL-SCORE-20260808

- 现象：8094 的ABC33入口压在底部导航上；详情按钮通过浏览器 `alert` 展示而无法形成可用详情页；A类在全部公式项不可用时仍显示100分。
- 根因：ABC33运行时以固定定位创建入口；详情只执行 `alert(JSON.stringify(...))`；维护分采用 `100-risk_score`，无可用项时暂算风险为0，但生产序列化未屏蔽该无效暂算分。
- 修复：入口动态挂载到 `.bf-condition-switcher-head`，无宿主时才使用不遮挡导航的后备入口；详情改为可访问的生产详情抽屉；`needs_data` 的公开 `score` 固定为 `null` 并返回 `score_available=false`，内部暂算值只保留在受保护审计项。
- 安全边界：生产页仍不返回公式项、权重、阈值、归一化值、单项贡献或内部特征名；详情只展示复核参数、缺数、处置、观察窗口、审批、工艺依据和原文章节。
- 测试：`python -m pytest tests/test_abc_rule_engine.py tests/test_abc_production_ui.py -q`，14项通过；远端最新批次26验证A1为 `score=null/status=needs_data/score_available=false`，详情接口HTTP 200。
- 部署：8094资源版本 `abc33-20260808-r2`，远端备份 `backups\\abc33_8094\\20260808_103955`；8768新批次已生成。8093未修改。

## ERR-BODY-TEMP-REPLAY-REGISTRY-UNIT-20260808

- 现象：8892健康接口正常，但首次真实`/api/replay`返回503，日志为`bf_sensor.sensor_registry.unit does not exist`。
- 根因：本地早期回放查询假设注册表带`unit`列；220.12生产表的单位由受控显示合同维护，注册表没有该列。
- 修复：注册表查询只读取`variable_name/tag_long_name/description`；80个温度点和18个静压力点分别由代码布局固定℃/kPa。随后15分钟真实查询返回HTTP 200、80个温度点和3帧。
- 附带修复：Edge自动请求`/favicon.ico`产生控制台400，服务端现明确返回204；最终远端Edge/Firefox/WebKit生产冒烟控制台错误为0。
# BUG-ABC33-ZERO-CONFIDENCE-AND-UNVALIDATED-SCORES-20260808

- 现象：8094 的33项炉况全部显示 `needs_data/置信度0%`；修正数据接线后又短暂出现B5=100、C9=86.7的异常高分。
- 数据证据：同一时刻旧8类诊断 `data_coverage.coverage_ratio=1.0`、延迟约1–3分钟，而ABC批次34的 `coverage_ratio=0`、`data_age_seconds=NULL`。生产点位最近值实际持续写入。
- 根因一：8768回退适配器只把旧 `feature_snapshot` 传给ABC引擎，漏掉当前传感器值；同时从SQL未选入的行字段读取覆盖率和数据年龄，恒定得到0/NULL。
- 根因二：`latest_values` 按所有点位时间并集的最后一分钟取每个变量，点位相差1–2分钟时把仍在5分钟新鲜度内的值误判为NULL。
- 根因三：当前 `abc_rule_catalog.py` 尚未完全按《炉况计算规则补充》公式落地，部分物理原值被通用0–1阈值归一化，导致假高分。原文例如A1使用短时标准差、B5使用低向60分钟标准化量，不能直接使用物理原值。
- 修复：8768合并当前值与派生快照并读取真实质量字段；每个变量取5分钟内自己的最新有效值；生产配置恢复 `shadow_validation`，未标定分数不公开、B/C告警关闭，页面显示“公式核验中”。
- 验收：批次56共33项，31项置信度大于0；状态为 `needs_data=31/blocked=2`，公开可计算分数0、告警0。20项ABC合同/桥接/UI测试通过。
- 回滚：远端备份位于 `backups\abc33_live_data_fix_8094`、`backups\abc33_recent_values_8768`、`backups\abc33_shadow_gate_8094` 和 `backups\abc33_latest_batch_order_8094`。

# BUG-8093-DIAGNOSIS-AI-FALSE-DATA-LIMITS-20260808

- 现象：五分钟智能分析将南北料线、四点顶温标为数据限制。
- 根因：采样密度低于 100% 被模型误读为无数据；并非注册表缺失，也不是 220.12 采集断链。
- 修复：服务端事实函数只在没有当前值且没有趋势序列时生成限制；模型不再接收逐变量采样密度；提示词版本更新为 v6。
- 验收：本地 `tests/test_diagnosis_ai_analysis.py` 共 16 项通过；220.12 只读核验确认六点均启用并有最近 60 分钟有效值。

## ERR-FOREMAN-PSPACE-DEPLOY-RECOVERY-RACE-20260808

- 现象：工长趋势 8770 受控部署第一次在保护检查阶段发现 8094 监听探测不稳定；第二次文件替换完成后，脚本收尾阶段因计划任务状态刷新延迟报 `Existing 8770 task did not recover`。
- 根因：远端 `V4BillboardPspace8770` 的旧父进程被停止后，Windows 任务计划程序的 `State` 与新监听建立存在短暂竞态；失败路径还需要单独恢复 8093 守卫服务。
- 处置：未扩大终止范围；只读核对 8094/8768 监听后，手动启动同一个 `V4BillboardPspace8770` 任务，确认新桥已监听8770；随后按受控服务入口恢复 `BFV4PreviewProxy8093` 并等待 HTTP 200。
- 最终验证：8770 `stream_value_count=157`、`foreman_numeric_count=17`、`passed=true`；8093/8094/8768/8770 最终监听 PID 为 `4788/13748/10832/3732`。无第二套 pSpace 读取程序。
- 后续维护：部署脚本的保护检查和进程树核验必须保留；再次部署若出现同类状态竞态，应先按本错误记录的“任务启动→监听→HTTP”顺序短轮询，不得跳过受保护端口核对。

## ERR-FOREMAN-TREND-MIXED-MINUTE-PSPACE-BUFFER-20260808

- 发现：8768历史数据本身是60秒 `PS_RAW_AVERAGE`，但前端 `applyPspaceFrame()` 当前也把8770秒级帧追加到同一个趋势 `buffer`；因此实时尾部可能混入秒级点，`displayMinutes`按点数裁剪时不再严格等于分钟数。
- 影响：数据库历史语义仍正确，卡片当前值仍可用；但趋势图若要求“纯1分钟平均值”，当前实现需要把8768分钟历史缓冲与8770当前值状态分离，8770只更新卡片/状态，不追加趋势历史。
- 证据：[前端合并逻辑](../高炉前端数据/assets/foreman-trend-preview.js)、[8768分钟查询](../自动诊断服务/local_pg_ws_bridge.py)、[分钟配置](../数据库同步和存取/config/sync_config.json)。本次未修改代码，仅完成核验并记录风险。
## ERR-SI-V20-IMMUTABLE-ASSET-STOPS-AUTO-REFRESH-20260809

- 现象：220.12 本地 IMES 镜像和炉次质量汇总已继续更新，但已打开或重新打开的 V20 独立页仍停留在旧炉次。
- 根因：静态 JS 响应为一年 `immutable`，HTML 的 `?v=20260808-v1` 未随热更新变化；同时默认查询日期不会跨午夜推进，旧无时间占位炉次也会优先于最新候选。
- 修复位置：[独立页资源版本](../高炉前端数据/si_v20_workbench.html)、[刷新日期与质量新鲜度](../高炉前端数据/assets/bf-si-v20-workbench.js)、[候选过滤](../高炉前端数据/智能助手/backend/si_v20_shadow.py)。
- 验证：`python -B -m unittest tests.test_si_v20_shadow_workbench` 为 12 passed；Node 语法通过；8093 API 最新实际为 125 炉 `0.23`，候选为 126 炉；真实 Chrome 页面日期到 8 月 9 日且显示 125/124/123。
- 防回归：任何独立页 JS 更新必须同步提升 HTML 查询版本；默认日期仅在仍处于自动范围时滚动。
## ERR-SI-V20-STRICT-HOURLY-TIMEZONE-20260810

### 错误现象

220.12严格整点预测在03:00与04:00时间槽连续进入`failed_retryable`，报错：

```text
can't subtract offset-naive and offset-aware datetimes
```

### 运行证据

- 第0次：03:00槽持续重试；第1次：04:00槽第6次重试仍失败。
- 数据库截至04:10共有4个整点槽，成功1、可重试3、重复0、非整点0、截止违规0。
- Windows任务`SiV20StrictHourlyPrediction`仍按分钟触发，但最近结果为1；可调`SiV20ScheduledShadowPrediction`同期结果为0。
- 证据：[持续验收报告](../reports/acceptance/SI_V20_NEW_HEAT_20260810/acceptance_report.md)和[第1次数据库探针](../reports/acceptance/SI_V20_NEW_HEAT_20260810/evidence/api/20260809T201053Z_strict_hourly_database_probe.json)。

### 初步定位

错误发生在严格整点预测行构造中，把带时区的任务时间与不带时区的业务截止时间直接相减。修复在[严格整点分发服务](../高炉前端数据/智能助手/backend/si_v20_shadow.py)统一转换为服务器本地无时区时间后再计算；部署后01:00~08:00共8槽全部成功，失败/陈旧/逾期/重复/截止违规均为0。

### 影响与处理边界

历史失败次数和错误文本保留在槽账本，没有删除。跨时区/无时区datetime回归、部署回滚、任务/API/数据库和8093/8094浏览器复验均已完成。

## ERR-SI-AVAILABILITY-STANDALONE-SYNC-DRIFT-20260810

- 现象：132炉平均Si=`0.400%`已经进入页面，但严格数据库核验发现`si_avg IS NOT NULL AND si_available_at IS NULL`一行，导致本小时验收失败。
- 根因：`HeatPerformanceQualitySync`计划任务执行`standalone_heat_dashboard_8891`下的旧同步副本，而主项目后端已更新；旧副本在实时镜像先写平均Si的竞争顺序下没有补齐首次汇总可用时间。任务Action同时仍指向Windows PowerShell 5.1。
- 修复：[汇总存储](../高炉前端数据/智能助手/backend/heat_performance_quality.py)允许在已有Si但可用时间为空时使用本次观测或`aggregated_at`保守恢复；[同步包装](../tools/run_22012_heat_performance_sync.ps1)强制PowerShell 7；独立副本受控更新并备份，任务Action迁移到`pwsh.exe`。
- 验证：`33 passed`；生产核验`missing_availability=0`，01:00~08:00八槽全成功；8093/8094/8768/8770/5432 PID未改变。随后`IMESRealtime`和可调V20任务也按独立XML备份迁移到PowerShell 7。
