# V52 原失败题定时复测启动交接

状态：`production_collection_running`

最后核对：2026-09-21 23:21（Asia/Shanghai）

权威来源：远端密封计划、`progress.json`、`batch/progress.json`、生产 Git HEAD、Ollama 只读身份接口和本仓库实现/测试。

适用边界：只覆盖 V52 上线后的 822 条既有失败/部分题再次收集和收集结束后的语义验收，不代表题目已经通过。

## 追踪项

- 需求：`REQ-QA-V52-SCHEDULED-FAILURE-RETEST-20260921`。
- 运维：`OPS-QA-V52-SCHEDULED-FAILURE-RETEST-20260921`。
- V52 路由基础提交：`19892017d93028fbf1cd6dcd0ed8799fca778fa0`。
- 当前生产提交：`5364bd590c0f7506b4a590c7707c0624dbac9313`，远端 Git 证明它是 V52 的后代；新增内容为同端口 WebSocket 转发及共享访客 owner 修复，未改变 V52 路由、Prompt、MCP 或模型身份。
- 固定模型：`chiqiongblastfuenace:latest`；唯一允许 digest 为 `e4ad74c41d68de1c8004419d8141a2b2df2275fa08f0dcf326ca0e63fb6d8124`。
- 禁止题：发送状态不确定的 `TPL-10C8C8FAF2C694EF` 不在 822 题计划中，不能自动重放。

## 程序和门禁

- [计划冻结器](../../tools/build_qa_v52_scheduled_retest.py)从 SHA-256 为 `ea4cf5af9a17cc1f034bf36dfc3d798f25a3f4c75801641a16205e3c28cedb1f` 的既有 822 题私有计划复制原问题，绑定当前生产的 78 个运行文件、点位目录、8093 PID/创建时间和固定模型。
- [密封器](../../tools/seal_qa_v52_scheduled_stage.py)只接受 `worker.py`、`batch.py`、`collector.py`、`plan.private.json`、`summary.py`、`start.ps1` 六个执行文件。
- [定时 supervisor](../../tools/run_qa_v52_scheduled_background.py)每天 22:30–07:30 运行。最近 300 秒存在非测试用户消息、GPU 利用率高于 5%、GPU 状态不可读、模型身份不一致、生产运行文件漂移时均等待且不 claim 下一题。8093 监听选择只接受命令行属于当前生产根目录的唯一 PID，并忽略 Windows 短暂返回的无归属或无关监听记录。
- [启动器](../../tools/start_qa_v52_scheduled_retest.ps1)通过唯一 `launch.claim` 和独立 `pythonw` 进程启动；输出目录已存在时拒绝重复启动。
- [脱敏收集摘要器](../../tools/summarize_qa_scheduled_retest.py)只保存题目 ID、结果/答案哈希、路由和传输计数，不复制问题和答案正文。HTTP 200、非空或工具成功都不是语义通过。

每题在发送前创建不可覆盖 claim，最多一次 POST。网络或进程状态不确定时状态变成 `blocked_no_replay`，只能只读恢复。程序不调用模型加载、切换、卸载、预热或服务停启，也不写业务数据库。

## 密封与启动证据

- 首次 stage/output 后缀为 `r1`，manifest 为 `b195a951907133e550f10ccd4ac9eadc860f44b2e085f86253d56acb621ae4fe`，plan 为 `a085e75a43ac9f4699b925d7d3ddcd4602c8432fbdbdd9121a49fc43d756dae0`。PID18428 完成 2 题后因 Windows 枚举出临时多监听候选而 fail-closed，状态 `blocked_no_replay`，随后正常退出。
- r1 的两题均有 claim 和结果，`request_count=1`、`automatic_retries=0`、HTTP 200、`terminated/done=true`、无传输错误。它们被作为哈希绑定的 `prior_completed_records` 写入续跑计划，绝不重发。
- 续跑 stage：`C:\Users\Administrator\AppData\Local\Temp\qa-v52-scheduled-retest-20260921-r2`。
- 续跑输出：`F:\高炉炼铁项目-real-sensor-v2_V4_8093_PREVIEW\logs\qa_v52_scheduled_retest_20260921_r2`。
- r2 manifest 为 `ae014d037f9f31484944577e7fab17117f521dcc67a7674daede06eee9f5af7f`，plan 为 `a5e76dc750f33834c7481f8ed7e119e4fb28be1c4ff0e0e2ecc3325650280377`。PID19280 又完成 2 个单次请求后，在下一题 claim 前捕获同一代理文件的瞬态读取不一致并 fail-closed；待发 active case 没有 claim/result，未发送。
- r2 的两个完整结果也按 claim/result SHA-256 加入续跑 prior，因此 r1+r2 共 4 题绝不重发。
- r3 stage：`C:\Users\Administrator\AppData\Local\Temp\qa-v52-scheduled-retest-20260921-r3`；输出：`F:\高炉炼铁项目-real-sensor-v2_V4_8093_PREVIEW\logs\qa_v52_scheduled_retest_20260921_r3`。
- r3 manifest SHA-256：`820356d399d3e7d7b1ce590abf15d7c17a59f054a62d91e9c68d765f89c8e305`。
- r3 plan SHA-256：`efc011c712914da640e50cb2d9c8261761062e1c65e2eedb75a035056fddbaa3`。PID6388 完成 4 题后，在下一题 claim 前发现生产代理文件持续变化并 fail-closed；四题均为完整单次结果。r1+r2+r3 合计 8 题按 claim/result SHA-256 进入后续 prior，绝不重发。
- r4 只在本机和远端预暂存，未创建输出目录、未启动、未发送问题。r5 在启动前只读预检发现同端口 WebSocket 修复已被提交到新的生产 HEAD，未启动、未 claim、未发送问题。
- 当前 r6 stage：`C:\Users\Administrator\AppData\Local\Temp\qa-v52-scheduled-retest-20260921-r6`；输出：`F:\高炉炼铁项目-real-sensor-v2_V4_8093_PREVIEW\logs\qa_v52_scheduled_retest_20260921_r6`。
- r6 manifest SHA-256：`9494897f5c6248ef8a74bd62c54e5006bb80883d215e4376e07480c0f9236cbb`；plan SHA-256：`67b2a67b74b9c7e87682dd7cc76eb191477e5fd3fd285adc3068864115542349`；814 题待测、8 题 prior，合计授权 822 题。
- r6 owner 初始 PID2208、创建时间 `1790003846.03116`。绑定的 8093 PID10212、创建时间 `1790003038.3367703`；任一身份改变都在下一题 claim 前停止。运行 hash 首次不一致时最多 5 次复核，只有连续 3 次恢复到预期 bytes 才继续。
- r6 启动前门禁：全部 78 pin、Git、点位目录、固定模型、用户静默和 GPU 0% 均通过。启动后已跨过此前中断位置；23:21 快照为 r6 完成 6/814、累计 14/822，`requests=6`、`automatic_retries=0`，六题前后模型名称与 digest 均一致。答案语义仍为 `pending_review`。
- 当前受保护监听快照：8093/10212、8094/16576、8768/6796、8770/844、5432/12372、11434/12656。

## 本机验证

- `python -m pytest -q tests/test_qa_v52_scheduled_retest.py --basetemp .codex_runtime/pytest-v52-schedule-20260921-r11`：26 passed，包含监听候选过滤、进程身份绑定、跨批不重放续跑、传输汇总和瞬态/持续 hash 分流。
- 三个执行 Python 和密封器通过 `py_compile`。
- 新启动器通过本机和远端 PowerShell 7 AST 解析。
- 远端四个 Python 文件通过 Python 3.11 `py_compile`；远端 `verify_inputs` 对 manifest、plan、78 个运行文件、点位目录、Git 祖先、8093 进程身份和固定模型全部通过。

## 收集结束后的验收

现有 Codex heartbeat `automation` 已改为每小时只读检查。正常运行、等待时间窗、等待真实用户或 GPU 空闲时保持安静。收集完成后必须逐条读取完整答案，与冻结的 V26 同题结果配对，并分别统计完整正确、部分、失败、标准/知识冲突阻断、证据不足和 oracle 阻断。知识题单列，成功回答率与可判准确率必须同时给出明确分母。

原始问题、完整答案、会话、生产数据和凭据继续留在 Git 忽略的私有目录。只有脱敏状态、计数、哈希、路由和合成证据可以进入 GitHub。
