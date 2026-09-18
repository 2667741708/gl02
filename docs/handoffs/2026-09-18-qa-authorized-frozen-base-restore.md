# 已授权固定底座恢复

状态：指定底座已恢复，8093原题复测已启动；8094依赖状态查询异常仍待独立处理。最后核对：2026-09-18。事项：OPS-QA-RESTORE-FROZEN-BASE-20260917、BUG-QA-CIM-TASK-STATE-20260918。

权威来源：本次用户明确“允许底座恢复”、Reliable SSH 身份/API/进程读取、单次远端执行结果及持久审计。适用范围：11434 指定底座恢复；不代表本机 V27–V50 路由候选上线。

## 冻结身份与边界

- 公开标签 `chiqiongblastfuenace:latest` 必须绑定已安装 `:1`：manifest `e4ad74c41d68de1c8004419d8141a2b2df2275fa08f0dcf326ca0e63fb6d8124`；GGUF layer `31629f53165ab6a7dad8c9847dcfd1fdf55829dac1e6e748f4a68581b0033d34`。
- 管理器 SHA-256 `1f871a8bbbaa553233d318b3d019a5a63e68be38d0f0caa7d29cca731d44434f`；目录 SHA-256 `723c4f2c6e5c2093060db8beaf5338dc857477a5b10d5db9f95ec79dfdc2f57a`。
- 不删除模型文件，不更换底座，不停启任何服务或任务；旧 Recovery 任务保持禁用。所有操作独立 claim，不确定不重放。
- 新鲜基线监听 PID：5432/12372、8093/6636、8094/16576、8768/7824、8770/844、11434/12656；8892 无监听。8093 相比前次10700已由其他生产工作更新，本次最小读集合全部28个源文件摘要仍匹配，不能以全局 PID/HEAD 历史变化误判路由变化。

## 中断及只读恢复

1. 旧控制器 r1 在 POST 与 claim 前拒绝。生产 CIM `MSFT_ScheduledTask.State` 在 PS7 返回数字 `1`，其字符串为 `1`；`Settings.Enabled` 为布尔 false。旧断言只接受 `Disabled`。独立读取证实旧 evidence 不存在、驻留不变，故无模型请求，不重放旧候选。
2. [卸载边界控制器](../../tools/unload_qa_unapproved_resident_once.ps1)仅新增精确 `1` 禁用码，仍要求 bool false，拒绝 0/2/3/4/01，更换唯一审计 r2。实际 AST 回归 **61 passed / 42.37秒**，独立审查 PASS。
3. r2 唯一 POST 已发，GIN 元数据 14:57:30 HTTP 200；即时退出验收失败，原审计 `failed_no_replay/uncertain_execution=true` 保留。06:58:07.922771 UTC Reliable GET 证实 resident=[]，11434 无 ESTABLISHED 连接、受保护 PID 不变，证明该卸载效果完成；没有重发 r2。
4. 06:58:49.209177 UTC 再读发现新生产请求重新加载旧9111，expires 14:58:48+24h。旧 alias 尚未恢复期间，分钟级 POST/chat 可重新加载模型。此前准备的空驻留独立 Repair 包装未执行，没有 claim。
5. [连贯恢复控制器](../../tools/restore_qa_frozen_base_once.ps1)使用新 r3 claim 针对后来驻留，在同一互斥临界区一次卸载、GET 等待实际退出、调用冻结 manager Repair 一次；严格 pin、精确唯一驻留、任务禁用及前后 PID 验收。保存卸载响应元数据，保留原 r2 审计，失败停机不重发。

## 检查与后续

- [实际边界及轮询 AST 回归](../../tests/test_qa_frozen_base_restore.py)：**15 passed / 11.13秒**，空驻留、延迟退出、耗尽、未知和身份变化均覆盖；无网络、生产调用或模型操作。生产 PS7 实际 tags/ps `.models` 类型均为 `System.Object[]`；不把 null 归一化成合法空驻留。
- 两组 JUnit：`.codex_runtime/qa-unload-cim-state-r2.junit.xml`、`.codex_runtime/qa-frozen-base-restore-r3.junit.xml`。PowerShell Core7.6.6 UTF-8 检查通过；包装与控制器 ParseFile 通过。
- 恢复终止后独立读取 tags/ps/tags、管理器状态、原后台PID9808身份和batch进度。只在固定e4稳定后允许现有822原题程序发送，串行每题一次，不另启动重复进程。有答案不能等同正确，最终答案审查后才统计准确率。

## 已核验的终止结果

- r3 frozen controller SHA-256 `009387a1b45da6f823eef3b277914af97e49fd2b298519aa5482b74203e006cc`，独立只读审查PASS。卸载响应严格 `done=true/done_reason=unload/model=latest`，等待实际空驻留后调用 manager Repair 一次。
- `manager-result.json` 返回 `ok=true/identity_ready=true/alias_changed=true`，预热一次 **27830.9ms**；state明确 `identity_locked=true/model_switch_allowed=false/fallback_active=false/recovery_complete=true`。07:07:12UTC写状态。独立 tags/ps/tags 均完整e4摘要，实际唯一驻留是latest，批准版本:1仍相同。
- 8093依赖通过，8094查询 `fixed_status8094_failed/io_error`，后续GET可复现 `RemoteDisconnected`。因此 manager 的 `dependencies_ready=false/assistant_ready=false`，外层r3审计为 `failed_no_replay`；原审计原样保留，不能称整体依赖验收通过，也不为此回滚正确模型或重试操作。所有受保护PID独立复核与新鲜基线一致。
- 原 supervisor PID9808/同一pythonw命令及创建时间已核验；固定身份三轮30秒观察后于 **07:08:09UTC** 进入running，batch已实际开始。随后快照为 **14/822完成，14次POST，15个question claim，1个结果文件处理中**，automatic_retries=0；再读19个完整结果均HTTP200/final存在/done=true/答案非空。上述仅传输与结果收集证据，**未进行正确性评分**。
- 运行中supervisor顶层requests/completed仍0；真正动态计数在batch/progress.json，collector结束后才累计。生成中的结果文件可为空，不把临时JSONDecodeError当新失败或重发理由。
- 本轮仍V26，绑定28个源码摘要全部匹配，V27–V50候选未部署。现有静默跟进已更新为“底座恢复完成，不重试模型操作，读取现有batch并等待最终答案审查”，保留原频率及静默通知偏好。
