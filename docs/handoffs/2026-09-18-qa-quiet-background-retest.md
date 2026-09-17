# 原题静默后台复测启动

状态：远端后台程序已启动并独立核验存活；等待锁定底座，尚未发送原题。最后核对：2026-09-18。

事项：OPS-QA-QUIET-ORIGINAL-RETEST-20260918、REQ-QA-PAIRED-FAILURE-RETEST-20260916。
权威来源：远端 launch.json、progress.json、真实进程身份与源文件摘要；[管理器生产安装](2026-09-17-qa-single-base-manager-production-install.md)、[首次最终语义摘要](../../tests/qa_regression/initial_semantic_summary_20260917.json)。适用范围：启动复测程序及静默等待；不代表固定驻留恢复、V50 路由部署或新准确率验证完成。

## 1. 已实际启动

- 主机：已通过 Reliable SSH 重新核验的 jngt_22012 / 220.12。
- 进程：PID **9808**，`pythonw.exe`，命令匹配封存 worker.py；创建 epoch `1789662678.2172005`。检查 PID 时必须同时核对命令和创建时间，防止 PID 复用。
- 启动方法：Win32_Process.Create 独立隐藏进程，生命周期不依赖 SSH 通道。没有修改计划任务或停止服务。
- stage：`C:/Users/Administrator/AppData/Local/Temp/qa-single-base-background-20260918-r2`。
- output：`F:/高炉炼铁项目-real-sensor-v2_V4_8093_PREVIEW/logs/qa_single_base_background_20260918_r1`。
- manifest SHA：`e944704763514fb71f87abe5111e94a8dff700942c5bb2c6ed5b9a55fa13844d`。
- 封存计划 SHA：`ea4cf5af9a17cc1f034bf36dfc3d798f25a3f4c75801641a16205e3c28cedb1f`。

启动后通过独立只读探测确认：`waiting_for_fixed_model`，`total=822`，`requests=0`，`completed=0`，`stable_observations=0`，模型管理操作 0，原题 claim/result 0。实际 worker claim 与 launch claim 已持久保存；不能因为等待而重复启动。

## 2. 原题与身份边界

822 题来自首次最终判定的 636 failed +186 partial。保持原问题文本、原问题摘要和原结果摘要；永久排除不确定发送的 `TPL-10C8C8FAF2C694EF`。269 已正确题、89 标准阻断、53 证据不足及知识 833 来源审计不伪装成此次 822 题分母。

复用已准备的原题计划 `52f75675b23e5fdccfb01383a42162b87aec88721e50ca3f85388d736a93cd2d`，只增加后台轮次/来源摘要元数据和封存 collector 字节绑定；完整 cases 集合逐项相等。既有 batch 的 stage 副本归一化为 UTF-8/无 BOM/LF，归一化前后 Python AST 完全相等；主工作树和既有 collector 文件未重写。早期本机 r1 准备目录在 LF 检查时中止，未上传或启动；采用新 r2 stage，实际远端启动仅一次。

唯一允许标签 `chiqiongblastfuenace:latest`，安装源 `:1`，完整 manifest 必须同时为 `e4ad74c41d68de1c8004419d8141a2b2df2275fa08f0dcf326ca0e63fb6d8124`，唯一 resident 的 name/digest 也严格相同。

生产当前仍为旧任务留下的 9111… latest/驻留，管理器源码已为 1f871…、Recovery 保持 Disabled。新的后台程序不卸载、不切换、不复制、不预热、不下载、不删除权重。单次卸载错误驻留并恢复唯一冻结底座的 11434 授权仍待用户明确回复；本次“启动复测程序”不冒充该授权。

## 3. 程序合同与核验位置

- [identity_matches](../../tools/run_qa_single_base_background.py#L33)：精确名称、完整大小写摘要、唯一 latest/:1/resident；未知 schema 拒绝。
- [verify_inputs](../../tools/run_qa_single_base_background.py#L92)：manifest 和五个封存文件、固定管理器、目录及当前 V26 runtime 摘要不变，禁止越出 root 的路径。
- [run](../../tools/run_qa_single_base_background.py#L113)：先 claim，再 GET-only 每 30 秒观察，连续三轮匹配且严格布尔健康才进入同一封存 batch。等待期间不调用生成、工具或模型管理。
- [guarded_verify / guarded_budget](../../tools/run_qa_single_base_background.py#L151)：每次 batch.verify 前后复核完整身份及源码；`STOP` 在发题预算门阻止下一题，不杀正在执行的请求。
- [独立启动](../../tools/start_qa_single_base_background.ps1#L41)：唯一 output 目录加 launch.claim，创建已知 pythonw 进程；已有目录拒绝覆盖或重启。

串行 batch.main 仅调用一次，复用现有每题 `*.claim`、私有原始结果及前后身份核验。断线、超时、已发题或不确定结果不自动重放。source/目录漂移永久中止该轮，不用新的 hash 替换冻结输入。非空答案保持 pending_semantic_review，不计算为完整正确。

## 4. 验证及服务影响

- 新 supervisor 无真实网络的本机回归：**36 passed，0 failed，0.38 秒**，证据 `.codex_runtime/qa-single-base-background-tests-20260918-r3.junit.xml`。
- 历史 r1 的 4 个失败为测试夹具 Windows 路径字符串比较未归一；r2 的 1 个失败为测试夹具写回同一目录字节、没有制造漂移；均已修复，历史证据保留，不计入线上失败题。
- starter/invoker 实际 PowerShell7 ParseInput 和 UTF-8/无 BOM/LF 检查通过；项目 `verify_pwsh7_utf8.ps1` 通过。
- 服务器 Python3.11.9 实际编译三个封存 Python 文件并执行只读 verify_inputs，五文件摘要、822 数量及生产 runtime pin 通过。
- gpt-5.6-luna 有界独立只读语义审查 PASS；不代表生产问答正确。

上传、启动前后受保护监听 PID 不变：8093=10700、8094=16576、8768=7824、8770=844、5432=12372、11434=12656；8892 均无监听。管理器 hash 与当前应用 proxy hash 不变。生产 HEAD 观察值 `e3cca548033736f31500f703aa877a6b519a1977`；最新四条 git log 均为已保留的其他页面/ABC 功能，未冒称 V50 助手候选已上线。

## 5. 静默跟进与完成判定

复用现有心跳“智能助手回归续跑与优化”，更新为先检查此 output/progress.json 和 batch/progress.json，保留原频率与 ACTIVE 状态；不新增重复自动任务。正常等待、运行及同一阻断不变保持安静，只报告重要新缺陷、实质变化、审核完成或新的用户行动项。

后台程序进入 running 后，逐题进度以 `output/batch/progress.json` 为准；supervisor 的 progress 指向它，终止时同步批次计数。若终止或 transport 状态未知，先只读恢复 claim/result/进程及持久会话记录，不能通过重启制造第二次 POST。若要停止，在该 output 创建 `STOP`，观察当前已发题结束与下一题未发送；该文件不会改模型或服务。

收集完成后独立审查最终答案，分别报告完整正确、部分、失败、标准阻断和证据不足，计算可判分母与全部有效分母，工具合同与答案合同分开。不上传原始问答、私有计划、生产数值、身份或凭据到 GitHub。
