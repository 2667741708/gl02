# 模型身份切换修复：子智能体完整任务提示词

状态：交付独立修复子智能体执行；生产写入由主任务持有，本提示词不授权子智能体远程操作。
最后核对：2026-09-17。事项：BUG-QA-MODEL-RECOVERY-FALLBACK-SWITCH-20260917、REQ-QA-SINGLE-BASE-MODEL-20260917。
权威来源：[独立根因报告](2026-09-17-model-identity-switch-independent-audit.md)、[权重来源核验](2026-09-17-locked-qwen38-lineage-verification.md)、[已有固定策略及受控安装方案](2026-09-17-qa-single-base-model-policy.md)。

以下是可以直接执行的完整任务提示词。

---

## 你的目标

修复 220.12 智能助手模型恢复器的跨底座回退和频繁标签改写问题，并交付有实际回归证据、可独立审查、可由主任务受控安装的新候选。
同时完善失败阶段观测，避免把模型身份、模型驻留和 8093/8094 服务可达性混为一项。
完成代码与测试，不停留在建议，不通过换模型、删权重或放宽验收制造成功。

## 固定底座，禁止重新选择

- 业务名称：chiqiongblastfuenace:latest。
- 唯一批准 manifest SHA-256：e4ad74c41d68de1c8004419d8141a2b2df2275fa08f0dcf326ca0e63fb6d8124。
- 唯一批准权重 layer SHA-256：31629f53165ab6a7dad8c9847dcfd1fdf55829dac1e6e748f4a68581b0033d34。
- 已安装冻结版本：chiqiongblastfuenace:1，Qwen3.8-27B，Q4_K_M；Ollama 报告26.9B。
- 不允许替代：:0 / 9111be230d48e53a385a28930fb8cf6972767c83e93c0db51f6b331a534e30fb，实际权重 d4b8b4f4c350f5d322dc8235175eeae02d32c6f3fd70bdb9ea481e3abb7d7fc4。
- qwen35 是架构标记，不足以认定发布版本。冻结 GGUF general.name=Qwen3.8-27B，来源已单独核对。
- 不自动恢复当前漂移到9111的驻留、不卸载替代权重、不下载或重建模型、不增加其他底座批准池。

## 已证实根因，不重复猜测

恢复任务 BFOllamaModelSelectionRecovery 每分钟运行 Repair。旧管理器先 cp :1 到 latest，再执行预热和后续检查。任意后续异常触发 fallback :0，标签又改写；成功前才写 active-model.json，失败仍保留期望 :1。下一轮从 :1 开始，形成反复改写闭环。
实际代码位置：远端管理器 L469 cp、L473 warmup、L481 状态端点检查、L495 持久化、L607 fallback_order、L623 catch 后继续下一候选。
Ollama 两次预热 POST /api/chat 均200；不能断言预热失败、OOM 或 think 警告就是深层根因。
旧日志未标记失败阶段，具体后续HTTP或客户端响应失败仍未知。无需假定两个控制器竞争。

## 边界与文件所有权

唯一可写工作树：
D:/文件/冀南钢铁运行中第二版本/.codex_worktrees/qa-regression-corpus-20260915。

你负责以下文件：
1. tools/qa_single_model_guard_functions.ps1。
2. tools/build_qa_single_model_guard_candidate.ps1。
3. tests/qa_regression/single_model_guard_harness.ps1。
4. tests/test_qa_single_model_guard.py。
5. 如有必要，新增 tests/test_qa_single_base_observability.py 及独占无凭据夹具。
   实际互斥回归夹具可新增 tests/qa_regression/single_model_mutex_harness.ps1；禁止调用真实生产任务。
6. docs/handoffs/2026-09-17-model-identity-repair-implementation.md。

不要修改 root 正在处理的安装器、安装事务、8093部署器、预检绑定器、问题索引和来源报告；接口或密封哈希需要联动时向 root 交付精确变更清单。
你不是代码库里唯一的执行者，不回滚他人修改，适配已有改动。原主工作树只读。
遵守 AGENTS.md、traceable-development、适用部署及工具评估规则。
禁止远程写入、凭据读取、上传、任务启停、服务重启、数据库操作、模型推理及原题POST；remote只读如确有必要只用Reliable SSH，不能directSSH。

## 必须实现的行为

### A. 禁止跨底座操作

1. Repair 只能选择冻结底座，不能读取 fallback_order 再激活其他模型。
2. Switch 全部拒绝，包含 Switch 到相同底座；Sanitize 不得修改模型。
3. 固定 installed version 必须匹配完整摘要，不能仅匹配参数量/量化。
4. 错误或多个驻留模型立即阻断，不 unload、cp、warmup、pull、create 或重试替代模型。
5. 冻结底座已健康驻留时不重复预热。保持既有同底座别名修复和空驻留重载合同；明确前置身份、操作顺序和操作上限。不得把这项同底座能力表述成允许切换到另一底座。
6. 本轮候选构建和测试不执行实际恢复操作。

### B. 分开身份状态与依赖服务状态

1. 只有标签和唯一驻留摘要真实匹配冻结底座，才能标记 identity_ready。
2. 8093/8094 HTTP 或业务健康失败必须独立报告，不触发换底座、不重复预热、不伪称整个助手健康。
3. 同一个恢复请求不重放模型调用；错误摘要/无驻留情况下的业务生成继续由只读身份门禁阻断。
4. 状态文件写入基于已验证的真实身份，不用旧 desired/effective 状态假装当前已锁定。依赖降级与身份健康分别记录。
5. 保留现有互斥锁、顶层 dispatch 和其他无关功能；不得顺带改8094、Ollama服务、知识库或生产路由。

### C. 加入安全的阶段观测

记录 installed-version-check、resident-before、alias-check/repair、warmup、resident-after、status8093、status8094、state-write 等实际执行阶段。
失败仅记录阶段、稳定错误码、异常类型、HTTP状态、内层异常类型及已观察到的期望/实际摘要。未经读取的actual字段用unknown/null，不能填入期望摘要冒充实测。
禁止记录任意 Exception.Message、请求/响应正文、完整URL查询参数、Cookie、Token、连接串、进程环境和原始会话。
记录日志失败不能掩盖原始错误，也不能触发模型回退；不能吞掉取消或产生虚假的completed。

补充具体边界：
- 模型列表不能接受字符串、null 或 IDictionary 假冒数组；保留 PowerShell 函数返回数组的形状。
- HTTP 取消异常链包含明确 TimeoutException 时分类为依赖超时；纯取消及 PipelineStopped 必须传播，不能按普通依赖降级后继续操作。
- state-write started 日志之后再构建状态：先原子落盘 recovery_complete=false/assistant_ready=false 的pending状态，执行中间观测，再最终原子提交。最终提交后不再触发可失败的日志；中间观测纯取消/流水线终止或最终写失败时只留下pending false。日志一般故障可提交降级状态，observability_ok/assistant_ready=false，不增加模型操作。
- 真实操作失败时，日志异常不得替换原操作异常。未观察到的驻留摘要必须为null。

### D. 构建与冻结

复用已有经过哈希验证的旧管理器基线及构建器，不重写整份生产管理器。
基线SHA-256=856f38b6edb088327e2138b88e68961db1a153b451aedb6709bea9fd2a8e99fa。
通过PowerShell AST替换明确函数，核对未修改函数及顶层语句逐字保留；新增helper有明确清单，不用泛化宽松计数绕过保护。
输出新候选到新的隔离目录，不覆盖已冻结r1候选。交付候选路径、SHA-256、修改/保留函数清单、UTF-8无BOM/LF及PowerShell7语法证据。
旧安装器仍绑定旧候选哈希，不能冒充可直接安装新候选；将新密封字段交给root更新和独立审查。

## 必须完成的回归

使用实际PowerShell函数、可控假服务和假模型操作，禁止真实网络或生产模型调用。

- 冻结底座健康：无cp、无warmup、无换模。
- 同底座别名修复与空驻留重载：操作仅指向冻结底座，最多一次重载。
- 错误摘要、多个驻留、冻结版本缺失、目录篡改：阻断且无模型修改。
- 所有Switch、Sanitize、direct fallback：拒绝。
- cp、warmup、身份复核、state写入失败：不尝试其他底座、不写虚假成功。
- 8093/8094超时、连接失败、HTTP错误、响应字段缺失：各自准确归类，身份状态不被误改，绝不换模。
- 日志写入失败、嵌套异常及带凭据/个人信息的异常文本：原始错误保留，输出不泄密。
- 任务重入/互斥、未知或null API模型列表：fail closed；若互斥已有权威回归，明确引用实际执行证据。
- 候选AST：保护函数/顶层dispatch未改，UTF-8/LF、无BOM，输出不可覆盖。

每次pytest使用工作树中未存在的新basetemp，不重用触发递归删除的目录。先跑受影响回归，再跑必要关联身份/batch/安装事务检查；无需重跑无关975项路由集合。

## 完成定义与交付

交付所有修改、实际通过/失败数量、命令、候选哈希、真实行号、剩余缺口与影响面。
明确“本机代码及候选已修复，生产尚未安装”；只有root完成受控安装与真实低频观察后才可报告生产修复。
深层HTTP失败没有新证据时保留未知，不以本机合成案例冒充真实根因。
不要操作GitHub、生产任务或模型。root负责独立审查、密封安装接口、生产授权边界及后续线上验收。

---

主任务并行工作：复核生产只读现状、准备新候选安装接口与发布证据，保留无关改动。生产修复操作不会交给子智能体。
