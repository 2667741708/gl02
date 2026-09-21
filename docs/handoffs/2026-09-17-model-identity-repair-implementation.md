# 模型身份恢复器修复实施与冻结证据

状态：本机实现、实际 PowerShell 回归与 r4 候选冻结完成；以下为本机冻结阶段证据，生产已由 root 完成 r5 安装，当前结果见[生产安装交接](2026-09-17-qa-single-base-manager-production-install.md)。最后核对：2026-09-17。

事项：BUG-QA-MODEL-RECOVERY-FALLBACK-SWITCH-20260917、REQ-QA-SINGLE-BASE-MODEL-20260917。
权威来源：[完整任务提示词](2026-09-17-model-identity-repair-agent-prompt.md)、[独立根因调查](2026-09-17-model-identity-switch-independent-audit.md)、[Qwen3.8 权重来源](2026-09-17-locked-qwen38-lineage-verification.md)。适用边界：模型管理器代码；不替代生产安装、实际底座恢复、8093 生成门禁或线上问答验收。

## 1. 修复结论及冻结身份

旧 Repair 的“激活 :1 → 后续异常 → 回退 :0 → 下一分钟再次激活 :1”已从候选控制流中移除。所有 Switch（包括同底座 Switch）、Sanitize 和直接 fallback 激活均明确拒绝。

唯一业务标签为 `chiqiongblastfuenace:latest`，安装源为 `chiqiongblastfuenace:1`：

- manifest SHA-256：`e4ad74c41d68de1c8004419d8141a2b2df2275fa08f0dcf326ca0e63fb6d8124`。
- 已核对的权重层 SHA-256：`31629f53165ab6a7dad8c9847dcfd1fdf55829dac1e6e748f4a68581b0033d34`，Qwen3.8-27B/Q4_K_M。
- 冻结 manifest 绑定实际权重；管理器运行时使用完整 manifest 身份判定，不用参数量或 qwen35 架构名重新选择模型。
- 若观测到错误驻留 9111…必须阻断；候选不会卸载、自动切回、下载、重建或选择替代底座。

## 2. 逐项行为与真实实现位置

| 项目 | 最终行为 | 文件与真实行号 |
|---|---|---|
| 冻结目录与源版本 | 唯一完整摘要、精确 latest/:1；重复绑定、错标签、缺失/漂移拒绝 | [Get-FixedModelPin](../../tools/qa_single_model_guard_functions.ps1#L11)、[Assert-FixedInstalledVersion](../../tools/qa_single_model_guard_functions.ps1#L114) |
| 驻留列表合同 | 必须是实际集合，拒绝 null/缺字段/字符串/字典/单对象；唯一 resident 名称和摘要均精确匹配 | [Get-FixedResidentSnapshot](../../tools/qa_single_model_guard_functions.ps1#L97) |
| 健康驻留 | 零 cp、零 warmup，不重复预热 | [Activate-Model](../../tools/qa_single_model_guard_functions.ps1#L170) |
| 同底座别名修复 | 先核实源版本及驻留；不存在不同驻留时，仅 cp 冻结 :1→latest，最多一次，并立即复核 | [Invoke-Repair](../../tools/qa_single_model_guard_functions.ps1#L221) |
| 同底座空驻留 | 仅在标签/安装身份已核实时调用现有 warmup，最多一次；随后复核别名和驻留 | [Activate-Model](../../tools/qa_single_model_guard_functions.ps1#L170) |
| 错误/多个驻留 | 无 cp、warmup、unload、Switch 或替代重试 | [Get-FixedResidentSnapshot](../../tools/qa_single_model_guard_functions.ps1#L97) |
| 初始化 | 空/错误/多个驻留拒绝，不能用期望摘要写假 identity_ready | [Initialize-State](../../tools/qa_single_model_guard_functions.ps1#L203) |
| 禁止切换与模型修改 | Switch/Sanitize 明确稳定码拒绝，直接其他底座/fallback 激活拒绝 | [Invoke-Switch/Invoke-Sanitize](../../tools/qa_single_model_guard_functions.ps1#L218)、[Activate-Model](../../tools/qa_single_model_guard_functions.ps1#L170) |
| 依赖健康 | 分别查询精确本机 8093/8094 状态端点；model_ok 必须为 true 布尔值；失败不换模、不重 warmup | [Get-FixedDependencyHealth](../../tools/qa_single_model_guard_functions.ps1#L135) |
| 身份与助手状态 | identity_ready/identity_locked 为实际已核实身份；dependencies_ready/assistant_ready 分开，依赖降级不能伪称整体助手健康 | [New-FixedModelState](../../tools/qa_single_model_guard_functions.ps1#L156) |
| 安全阶段观测 | 固定阶段/错误码/类型/HTTP码/合法64hex摘要；不记录 Message、响应正文、URL查询、凭据或会话 | [Write-FixedStageEvent](../../tools/qa_single_model_guard_functions.ps1#L20) |
| 当前观测未知 | 每次安装/别名/驻留读取前清空该 actual 字段，失败或未知 schema 不复用上次 e4 冒充当前 | [Get-FixedResidentSnapshot](../../tools/qa_single_model_guard_functions.ps1#L97)、[Assert-FixedInstalledVersion](../../tools/qa_single_model_guard_functions.ps1#L114)、[Assert-FixedPublicAlias](../../tools/qa_single_model_guard_functions.ps1#L123) |
| 取消与 HTTP 超时 | 纯取消/PipelineStopped 停止；带明确 TimeoutException 的 typed 链按 timeout 处理，不凭异常文本猜测 | [Invoke-FixedStage](../../tools/qa_single_model_guard_functions.ps1#L63) |

8093/8094 超时、连接拒绝、HTTP 503、嵌套超时、字段缺失/false/字符串 truthy 的观测分别记录 timeout、connection_error、http_error 或 contract_error。依赖降级可以返回已核实 identity_ready=true，但 assistant_ready=false；顶层 action 的 ok 不能解释为整个助手健康。

## 3. 状态最终写入与取消安全

`state-write` 使用两步原子状态写入：

1. 构建并写 pending 状态：`recovery_complete=false`、`assistant_ready=false`，身份字段仍只来自已核实实况。
2. 记录 `outcome=pending/code=state_pending_written` 的中间阶段观测；这只证明 pending 已写，不能解释为最终完成。
3. 未发生取消后，写最终状态：`recovery_complete=true`；只有身份、依赖和 observability 全部通过才允许 assistant_ready=true。最终 commit 后不再调用 logger。

因此 logger 首次在 state-write started/pending 时失败不会留下假绿；纯取消、原生 PipelineStopped 或最终原子写失败只留下 pending false，不返回 completed。日志普通写入失败降级 observability/assistant 状态。已有 operation 异常被捕获后，logger 的失败或取消不覆盖其原始异常；对外只输出稳定码，原异常仅作为未序列化的 inner exception 保留。

原生 PipelineStopped 会结束 PowerShell 主机管道，连测试夹具最后的 JSON 都可能没有。回归使用持久合成信号、无模型 mutation trace、无成功输出以及 pending false 状态验证，不能把无 JSON 自动重试成第二次恢复操作。

## 4. 候选、AST 与安装接口

最终冻结文件（Git 忽略，不上传生产目录快照）：

`.codex_runtime/qa-model-identity-repair-20260917/candidate-r4/manage_ollama_model_switch.ps1`

SHA-256：`1f871a8bbbaa553233d318b3d019a5a63e68be38d0f0caa7d29cca731d44434f`。

构建基线为原主工作树只读文件 `tools/ollama_model_switch/manage_ollama_model_switch.ps1`，SHA-256 `856f38b6edb088327e2138b88e68961db1a153b451aedb6709bea9fd2a8e99fa`，与独立核对的生产管理器一致。

[AST 构建器](../../tools/build_qa_single_model_guard_candidate.ps1#L16) 实际验证：替换 5 个明确函数（Activate-Model、Initialize-State、Invoke-Switch、Invoke-Sanitize、Invoke-Repair）；30 个其他原函数和 14 个顶层语句逐字保留，包含原互斥和 dispatch；新增 helper 的 9 个精确名称在[明确清单](../../tools/build_qa_single_model_guard_candidate.ps1#L31)核对，不允许同名碰撞或泛化计数绕过保护。候选及交付代码 UTF-8/无 BOM/LF，PowerShell 7 语法通过，冻结输出已存在时拒绝覆盖。

- r1 原冻结文件保持不动。
- r2 SHA `384cd4c599ca80a4dc77e80d29fda0b06159cf0f29812bea6cd70e1d9e6963a0` 已证实存在 state-write 末尾取消假绿缺陷，**禁止安装**。
- r3 SHA `6f644e337af6373093abebe62bb8f8c70c06d244bd4f4619bd6707e79b9f1bf7` 被 r4 的 actual-reset 观测修复取代，不作最终候选。
- root 独占的[安装器](../../tools/install_qa_single_base_manager.ps1#L10)已精确绑定 r4；最终源码 SHA `810a6409c62f26298f2954b32c98380d2dc4e6e0a5c3a98309380c9e35b6f38f`。本子任务没有修改或执行安装器。
- 安装器 acceptance_scope 为 manager_source_only，production_model_lock_verified=false、qa_retest_authorized=false。安装源码本身不证明错误驻留已恢复，也不授权原题复测。

## 5. 实际测试结果及可核对证据

所有测试均为本机实际 PowerShell 函数/控制流与受控假模型、假服务；没有真实网络、推理或生产模型操作。

| 最终证据组 | 实际结果 | 时间 | 私有终止证据 |
|---|---:|---:|---|
| 固定 guard + observability 主集合，含 AST、输出冻结、原 mutex 顶层 dispatch 跨进程 Busy/Normal | 86 passed，0 failed/skip | 74.93s | `.codex_runtime/qa-model-identity-repair-tests-r8.junit.xml` |
| 后续 API null schema 清空旧驻留摘要增量 | 1 passed，45 deselected | 1.06s | `.codex_runtime/qa-model-identity-repair-null-r4.junit.xml` |
| 既有固定身份、单次 window、runtime pin、安装事务关联集合 | 53 passed，0 failed/skip | 11.54s | `.codex_runtime/qa-model-identity-repair-associated-r2.junit.xml` |

最终受影响集合共 **87 个不同用例**，关联集合 **53 个不同用例**。历史 r2/r3/r4/r5/r6/r7 以及敏感 digest 单跑均不重复计入最终数量。早期 27 个实现失败（PowerShell 输出枚举破坏数组形状）和 1 个原生 PipelineStopped 夹具解析失败已保留历史，属于本机实现/夹具回归，不计入任何线上数据集失败次数或成功率。

实际命令（历史证据；再次运行必须选择未存在的新 basetemp，不重用这些目录）：

```powershell
python -B -X utf8 -m pytest tests/test_qa_single_model_guard.py tests/test_qa_single_base_observability.py -q --basetemp .codex_runtime/qa-model-identity-repair-tests-r8 --junitxml .codex_runtime/qa-model-identity-repair-tests-r8.junit.xml
python -B -X utf8 -m pytest tests/test_qa_single_base_observability.py -q -k null_schema_after --basetemp .codex_runtime/qa-model-identity-repair-null-r4 --junitxml .codex_runtime/qa-model-identity-repair-null-r4.junit.xml
python -B -X utf8 -m pytest tests/test_qa_fixed_model_identity.py tests/test_qa_fixed_model_window.py tests/test_qa_runtime_probe_fixed_pin.py tests/test_qa_fixed_manager_install_transaction.py -q --basetemp .codex_runtime/qa-model-identity-repair-associated-r2 --junitxml .codex_runtime/qa-model-identity-repair-associated-r2.junit.xml
```

模型拒绝/同底座上限见[guard 回归](../../tests/test_qa_single_model_guard.py#L24)；依赖分层、取消、状态终止和敏感 digest 见[observability 回归](../../tests/test_qa_single_base_observability.py#L17)；互斥执行复用候选的原始顶层代码，测试仅将 global mutex 名替换成唯一 synthetic 名，见[无凭据 mutex 夹具](../../tests/qa_regression/single_model_mutex_harness.ps1#L1)。

## 6. 影响与剩余未验证项

- 本子任务只改 guard 库、builder、两个无凭据 PowerShell 夹具、两份 pytest 和本实施 handoff；没有改 root 安装/事务/8093 发布器或既有来源审计。
- 远程写入、计划任务启停、服务操作、模型加载/卸载/复制/删除、真实推理和原题 POST 均为 0；无 Git commit/push/GitHub 操作。
- 两次生产 warmup 服务端 HTTP 200 已有证据；后续真实 HTTP/客户端失败阶段仍未知。本机合成 timeout/503/字段缺失不能冒充线上深层根因。
- 生产安装与独立审查由 root 持有；安装后需单独证明恢复任务采用新 manager、固定摘要门禁有效，并进行覆盖实际触发周期的低频只读观察。
- 当前错误/空驻留不会被本候选自行跨身份恢复。持续驻留、真正固定 latest 权重、线上最终问答、822 题配对准确率均仍需要 root 的受控后续实施与真实验收。
