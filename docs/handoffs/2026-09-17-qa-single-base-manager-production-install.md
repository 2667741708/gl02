# 固定底座管理器生产安装与复测边界

状态：管理器生产源码安装成功；实际驻留恢复及线上复测尚未执行。最后核对：2026-09-17。

此状态是2026-09-17安装快照；2026-09-18用户另行授权后，指定e4底座已恢复、现有822原题程序已启动，8094依赖查询异常单列。当前状态以[授权恢复和复测实证](2026-09-18-qa-authorized-frozen-base-restore.md)为准，原安装审计保留。

事项：OPS-QA-SINGLE-BASE-GUARD-INSTALL-20260917、BUG-QA-ATOMIC-REPLACE-NULL-BACKUP-20260917、OPS-QA-RESTORE-FROZEN-BASE-20260917。
权威来源：生产 r4/r5 安装审计、安装后独立只读文件摘要及 Ollama tags/ps；[恢复器实现](2026-09-17-model-identity-repair-implementation.md)、[固定底座规则](2026-09-17-qa-single-base-model-policy.md)。适用范围：模型管理器独立安装；不代表 V50 路由已部署，不代表最终答案正确率提升。

## 1. 已安装内容

目标为 `F:/Ollama/model-switch/manage_ollama_model_switch.ps1`，生产安装后独立只读 SHA-256：

`1f871a8bbbaa553233d318b3d019a5a63e68be38d0f0caa7d29cca731d44434f`。

它拒绝 Switch/Sanitize、错误/多个/未知驻留及跨底座 fallback。健康固定驻留零复制、零预热；空驻留只允许已核实的冻结同底座预热一次。源码安装没有卸载、加载、复制或删除任何模型。

## 2. 实际安装过程与故障修复

| 独立操作 | 终止结果 | 是否替换生产管理器 | 模型操作 | 审计 |
|---|---|---|---:|---|
| single-base-20260917-r4 | 安装器 File.Replace 空备份参数被 PowerShell 转成空路径，替换前失败 | 否，仍为旧 856f… | 0 | `F:/Ollama/model-switch/updates/single-base-20260917-r4/install.json` |
| single-base-20260917-r5 | guard_installed，guard_install_accepted=true，atomic_replace_completed=true，rollback_applied=false | 是，独立读回为 1f871… | 0 | `F:/Ollama/model-switch/updates/single-base-20260917-r5/install.json` |

r4 的失败记录、claim 和旧源码备份保留。r5 是修复安装器后经审查的新操作，没有重放 r4。安装器使用明确且非空的原子备份路径，拒绝覆盖已有备份。

r5 安装器 SHA-256：`cbc3537307c64cda3fb699fdf95551b1bc0b6eb2877ff9f7e9e757239bf5cfb7`。
事务库 SHA-256：`7214925ad79e5c4ecd10dc018f0121378769893ea269601df2c47a7e6fa93d91`。

新增真实 Windows 临时文件 File.Replace 回归 **12 passed，0 failed/skip，8.71 秒**，覆盖安装、回滚、空/空白/已有备份及缺失路径，并复现旧空参数缺陷；不执行生产安装器顶层。证据：`.codex_runtime/qa-manager-atomic-replace-tests-r5.junit.xml`。独立只读 Luna 审查新安装器 PASS。

## 3. 服务影响与当前身份

以下受保护监听 PID 在 r5 安装前后保持一致：

| 端口 | PID |
|---:|---:|
| 5432 | 12372 |
| 8093 | 10700 |
| 8094 | 16576 |
| 8768 | 7824 |
| 8770 | 844 |
| 11434 | 12656 |

8892 前后均无监听。没有重启这些服务。Recovery 任务因 r4 失败保持禁用；r5 读取到原状态 false，安装后仍为 false，未恢复旧行为。

当前 `:1` 是批准的完整 manifest `e4ad74c41d68de1c8004419d8141a2b2df2275fa08f0dcf326ca0e63fb6d8124`。但 `latest` 和唯一驻留仍为旧任务加载的 `9111be230d48e53a385a28930fb8cf6972767c83e93c0db51f6b331a534e30fb`，新管理器按规则阻断，不能自动卸载或切回。

安装审计明确 `acceptance_scope=manager_source_only`、`production_model_lock_verified=false`、`qa_retest_authorized=false`、`identity_ready=false`。这些安装审计字段不撤销用户原题复测授权；它们表示尚未满足实际固定底座验收门槛。当前真实问答 POST **0**，没有新的准确率或成功回答率结果。

## 4. 剩余单次恢复与复测

1. 另行明确授权后，执行已审查的单次错误驻留卸载控制器；严格 Disabled 任务、源/目录摘要、安装 e4 与唯一错误 9111 驻留二次核验，一次性 claim，POST 前持久记录，不确定不重放。只卸载驻留，不删除权重文件。
2. 独立确认空驻留后，冻结新管理器只执行一次 Repair，将 latest 恢复到已安装的 :1/e4，只预热该既定底座一次。失败停止，不选替代底座、不自动重试。
3. tags/ps 完整摘要与精确名称持续一致后，复测首次收集判定的 **822 个 failed/partial 原题**；保留原题摘要、原结果摘要和原评分绑定，永久排除状态不确定的 `TPL-10C8C8FAF2C694EF`，每题一次 POST，串行，不自动重放。
4. 区分有回答、完整正确、部分正确、失败、金标依赖阻断。先独立检查最终答案与证据，再计算完整正确率及成功回答率；833 知识题单列，禁止将答案非空判为通过。

生产应用当前仍为 V26。此次修复的效果是切断跨底座恢复链；V27–V50 本机路由候选需另行完成发布登记、密封和 8093 受控切换，不能把本次管理器安装当作那些路由修复上线。

单次卸载控制器 SHA-256：`e03a21bacf0a4aeaa5b1209083684e1734f091c03bf533cc268017051c49e411`。实际 AST 提取纯边界函数回归 **56 passed，0 failed/skip，41.35 秒**，覆盖 2 个正例、53 个拒绝反例和编码检查；JUnit 为 `.codex_runtime/qa-unapproved-resident-unload-boundary-tests-r1.junit.xml`，独立只读 Luna 审查 PASS。未执行控制器顶层 Execute。

当前复测准备清单为 `.codex_runtime/qa-routing-v26/single-base-retest-r4/preparation.manifest.json`；计划摘要 `52f75675b23e5fdccfb01383a42162b87aec88721e50ca3f85388d736a93cd2d`，生产 HEAD 观察值 `e3cca548033736f31500f703aa877a6b519a1977`。r3 准备文件原封保留、未使用；r4 仅将继承的中间审查计数更新为已绑定初次最终摘要的 269/186/636/53/89，删除旧 V22/V23 中间计数，原题内容、集合和结果绑定不变。该计划严格仅 e4；准备成功不是发送或驻留验证成功。新鲜只读证明旧 V26 批次 requests/completed/claim/result 均为 0，无匹配 QA batch 进程；旧 PID 952 已被 sshd-session.exe 复用，不能仅用 pid_exists 推断旧测试仍运行。
