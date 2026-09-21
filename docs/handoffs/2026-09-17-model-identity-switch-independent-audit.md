# 220.12 模型身份切换独立只读调查

状态：根因链已核对；生产策略尚未安装，不能声称生产已锁定。
最后核对：2026-09-17 22:26（Asia/Shanghai）。
事项：`BUG-QA-MODEL-RECOVERY-FALLBACK-SWITCH-20260917`，关联 `REQ-QA-SINGLE-BASE-MODEL-20260917`。
权威来源：本轮 Reliable SSH `jngt_22012` 只读任务/进程探测、远端管理器和事件/服务日志；谱系另见[锁定底座核验](2026-09-17-locked-qwen38-lineage-verification.md)。
边界：独立 Codex 子智能体调查；没有调用生产模型完成调查，没有远端写、推理、原始 QA POST、模型操作、服务或计划任务修改。只新增此本机脱敏报告，保留其他人的改动。

## 1. 已证实结论

正在运行的旧恢复任务本身具备反复改写 `latest` 的完整机制：

1. 状态文件期望模型为 `chiqiongblastfuenace-1`（批准摘要 `e4ad…`）。
2. 每分钟触发的 `Repair` 首先选择 `:1`，`Activate-Model` 在后续检查之前就将版本标签复制到 `latest`。
3. 任意后续异常被统一视为该候选失败，`Repair` 随即选择 `:0`（摘要 `9111…`），再次改写 `latest`。
4. 失败发生在状态持久化之前，状态文件保留旧的期望 `:1`，但标签可能已经变成 `:0`。
5. 下一轮从旧期望 `:1` 再次开始，形成 `e4ad → 9111 → e4ad → 9111` 循环。

这足以解释已观察到的频繁切换，不需要假定存在两个争抢控制器。互斥锁只避免旧管理器实例重叠，不禁止单个实例顺序切换不同底座。

## 2. 运行入口与真实行号

以下行号直接读取自远端文件，不是对本机候选行号的推断。

| 证据 | 实测位置或结果 |
|---|---|
| 主控制器 | `F:/Ollama/model-switch/manage_ollama_model_switch.ps1`；SHA-256 `856f38b6edb088327e2138b88e68961db1a153b451aedb6709bea9fd2a8e99fa` |
| 恢复任务 | `\BlastFurnaceServices\BFOllamaModelSelectionRecovery`，Enabled=true，重复间隔 `PT1M` |
| 任务执行动作 | PowerShell 7 `-File F:/Ollama/model-switch/manage_ollama_model_switch.ps1 -Action Repair -CatalogPath F:/Ollama/model-switch/model_catalog.json` |
| 运行实例 | 22:23:54 探测实际 `pwsh.exe` PID 18668、父 PID 988，22:23:31 创建，参数标记 `manage_ollama_model_switch.ps1` / `Repair` |
| 回退候选 | 管理器 L603-L607：读取 `desired_model_id` 并附加 `fallback_order` |
| 改写公共标签 | `Activate-Model` L465-L469：先 `Ensure-ModelTag`，再 `ollama cp version_tag public_alias` |
| 切换后检查 | L471-L481：驻留检查、预热、标签检查、驻留复核、状态接口检查 |
| 异常后改用下一底座 | L612-L625：遍历候选，catch 记录 `repair_candidate_failed` 后继续；没有恢复已改写标签 |
| 成功才写状态 | L482-L495：完成上述步骤后才写 `active-model.json` |
| 模型校验缺口 | L214-L228 `Test-ModelTag` 只核对量化与参数量模式，不要求已安装标签摘要等于批准摘要 |
| 互斥锁 | L756：`Global\BFOllamaModelSwitch`，不改变上述回退行为 |

目录实际包含两份底座：`:0` 的 preferred_digest=`9111be230d48e53a385a28930fb8cf6972767c83e93c0db51f6b331a534e30fb`；`:1` 的 preferred_digest=`e4ad74c41d68de1c8004419d8141a2b2df2275fa08f0dcf326ca0e63fb6d8124`；fallback_order 为 `[:1, :0]`。

状态文件当前 `desired_model_id` 与 `effective_model_id` 均为 `chiqiongblastfuenace-1`、digest=`e4ad…`，更新时间仍为 `2026-09-08T06:05:33.8504295Z`、last_action=`Repair`。因此仅检查状态文件不能证明当前公共标签或驻留身份。

历史设计已经说明“降级不覆盖期望值、后续轮次重试期望模型”：主工作树只读历史文档 `docs/handoffs/2026-08-22-22012-ollama-one-click-switch-and-qwen38-evaluation.md` L13。该旧设计与当前禁止底座切换的要求冲突。

## 3. 切换时间线

远端 `F:/Ollama/logs/ollama_11434.service.out.log` 记录以下元数据，均未读取或记录请求正文：

| 北京时间 | 日志行 / 事件 |
|---|---|
| 22:11:37 | out L95288：`POST /api/copy`，200 |
| 22:11:53 | 主任务独立快照：`latest` 与驻留摘要均为 `e4ad…` |
| 22:12:05 | out L95293：`POST /api/chat`，200，27.946 秒 |
| 22:12:06.578 | `F:/Ollama/model-switch/events.jsonl` L43967：`:1` 的 `repair_candidate_failed`，错误仅为 `An error occurred while sending the request.` |
| 22:12:06 | out L95317：又一次 `POST /api/copy`，200 |
| 22:12:34 | 主任务独立快照：`latest` 与驻留摘要均变为 `9111…` |
| 22:12:38 | out L95330：`POST /api/chat`，200，31.360 秒 |
| 22:12:39.986 | events L43968：`:0` 的 `repair_candidate_failed`，同一泛化错误 |
| 22:12:40.991 | events L43969：两个候选均失败，`repair_failures` |

在 13:00 UTC 起至本次约 14:22 UTC 读取时，事件日志共有 84 条候选失败、42 条双候选失败记录，没有成功 activation 事件。这不是原始问答失败次数，也不能加入 822 题准确率分母。

## 4. 深层失败原因的已知与未知

**不能把以上错误直接称为“模型预热失败”。** 两次对应 `/api/chat` 的服务端日志均为 200。较可能是切换后的状态接口请求或客户端响应处理出错，但旧日志没有阶段、异常类型、HTTP 状态和内层异常，尚不能断言具体位置。

管理器 `Test-StatusEndpoints` L393-L400 依次 GET 8093、8094 的 `/api/ollama/status`，这个环节也可触发 `Repair` 回退。生产锁定不应取决于另一个预览服务是否可访问。

同窗口 Ollama err.log 共 88 条 INFO、4 条 WARN；WARN 为 `invalid option provided option=think`（L153308、L153354、L153365、L153411）。没有该窗口 ERROR、OOM 或崩溃证据；不能据此认定 think 选项就是触发根因，也不应盲目增大超时。

原健康任务 `BFOllama11434HealthCheck` 实际运行入口为项目 `tools/check_managed_nssm_service_health.ps1`。配置健康检查只有 TCP 11434 与 `/api/version`、`/api/tags` GET，无 `httpPost`。`F:/Ollama/logs/ollama_11434.health.log` L90598（22:11:24）、L90599（22:13:24）以及后续至 L90605（22:25:24）持续 `ok service=Running checks=ok`。未发现该窗口健康任务重启 Ollama 的证据。

22:23:54 活进程快照没有发现 `run_qa_fixed_model_window.ps1` 实例。本机旧双摘要窗口已经在[入口 L10](../../tools/run_qa_fixed_model_window.ps1#L10)无条件拒绝执行；代码仍有旧逻辑不是它正在生产切换的证据，不能证明历史从未执行。

## 5. 最小修复与可核对验收

1. 按独立授权边界安装已审查的固定身份管理器，替换旧 `Repair` 的跨底座 fallback。拒绝 `Switch`、新建或下载权重以及其他底座；冻结底座已经驻留时允许修复同一底座别名，空驻留时允许重新加载同一底座。错误或多个驻留身份直接阻断，健康底座不重复预热。
2. 固定唯一 identity：`chiqiongblastfuenace:latest` + 完整摘要 `e4ad…` + 实际权重 `31629…`。运行时只读门禁遇到错误摘要或空驻留时明确失败且模型操作为 0；管理器的同底座恢复是另外的受控合同，不自动选择 `:0`，不删除权重掩盖根因。
3. 安装前暂停未来恢复触发、排空当前旧实例并持有同一互斥锁；安装过程不得改模型身份。失败时按受控事务保持任务禁用，成功后只恢复其原启用状态。现有[安装器](../../tools/install_qa_single_base_manager.ps1#L78)校验管理器及目录基线，并在 [L95](../../tools/install_qa_single_base_manager.ps1#L95)核对身份与受保护 PID 未改变。
4. 将“批准底座恢复”与“禁切换管理器安装”区分：当前漂移身份不能因为安装新检查器自动变成批准身份。只有主任务持有的明确授权操作才能恢复批准身份，禁止子智能体自行 copy/load。
5. 添加观测阶段：copy、warmup、alias/resident-check、status8093、status8094；失败日志只记录 stage、脱敏异常 type/status/innerType、期望与实际摘要，不记录响应正文。日志改善只能定位问题，不能重新引入回退。
6. 分别验收两类合同：运行时只读门禁在错误摘要、空驻留等不满足身份条件时阻断且模型操作为 0；管理器按[真实回归](../../tests/test_qa_single_model_guard.py)允许同一冻结底座的别名修复与空驻留重载，错误或多个驻留身份阻断，健康底座不重复预热，禁止替代底座和新建/下载权重。覆盖重复任务、管理器重启、配置缺失、健康端点失败，确保不会触发跨底座回退。对真实生产低频采样 `tags → ps → tags`，至少覆盖恢复触发周期及一次任务执行，证明摘要不再变化。不能把本机模拟通过当作线上固定完成。

主任务报告本轮固定身份、禁切换管理器、旧窗口拒绝、batch 身份和安装事务五组回归 **61 passed / 21.83 秒**。这是本机候选验证结果，不是本子智能体执行结果，也不证明生产安装。本轮远端仍为旧管理器 SHA `856f…`，所以生产禁切换策略**尚未生效**。

## 6. 本轮验证方法与限制

- Reliable SSH `probe_identity` 确认 `WIN-54B94HVHKBA` / `10.30.220.12` / Python 3.11.9 / Windows AMD64。
- Reliable SSH 只读 `exec_argv`：任务动作、间隔与运行信息；Win32_Process 参数在服务器内过滤后只返回 PID、创建时间、脚本标记和 Action。
- Python 只读解析管理器实际行号、目录白名单字段、状态字段和选定日志行；不输出服务环境、凭据或请求正文。
- 没有跟踪系统级每次文件写入的执行者，因此对 `copy` 的直接 PID 归属是运行入口、代码和对应时间线共同支持，不能冒充 ETW/Sysmon 逐次归属证据。
- 最终生产修改、批准身份恢复、长期观察及真实问答复测由主任务执行，未纳入本独立只读调查。
