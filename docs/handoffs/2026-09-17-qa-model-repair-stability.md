# 模型恢复稳定性本机候选与回归证据

状态：历史候选，未部署；被用户新增单一底座强约束取代，r2批准fallback策略禁止部署。当前方案见[单底座合同](2026-09-17-qa-single-base-model-policy.md)。
最后核对：2026-09-17。需求：OPS-QA-MODEL-REPAIR-STABILITY-20260917，关联QAOPT-O01/QAOPT-T05。
权威来源：Reliable SSH只读生产脚本字节哈希、候选AST保留检查、实际依赖冻结fixture、pytest最终输出及独立审查。

## 已定位问题与修复措施

|编号|已证明的代码缺陷|r2修复|验证边界|
|---|---|---|---|
|MODEL-STABLE-01|已有批准模型健康驻留，Repair仍优先尝试desired并改变alias|保持当前健康批准驻留，实际effective/digest/版本与状态校准；desired保留，明确Switch才切偏好|真实Activate/Resident依赖下，批准fallback不cp、不热身、不暂停健康任务；辅助endpoint失败也不换alias|
|MODEL-STABLE-02|Repair候选cp后热身失败未恢复旧alias|捕获实际旧批准alias与匹配安装版本，失败后恢复并核验；回滚失败停止下一候选|注入两候选热身失败与回滚失败，核对cp顺序、状态、任务恢复和失败记录|
|MODEL-STABLE-03|恢复失败下一触发立即再尝试，易反复切换|持久化候选退避60/120/240/480/900秒，上限15分钟；损坏记录阻断自动激活|验证冷却跳过、到期边界、指数上限及非法计数/时间；只冷却失败候选，正常驻留优先|
|MODEL-STABLE-04|暂停健康任务部分失败发生在healthPaused标记前，finally失去恢复责任|在暂停操作前取得恢复责任，原禁用任务保持禁用|部分失败和原禁用状态两类实际控制流检查|
|MODEL-STABLE-05|Switch catch无条件按旧state回滚，即使没有进入Activate，且旧state可能与实际alias漂移|根据实际alias验证回滚模型；只有实际alias偏离才cp；未开始激活或alias未变时不热身；状态反映真实旧alias|保留前代fixture复现错误cp到版本1；r2同一暂停失败零cp/零热身，stale state下激活失败恢复实际版本0|

以下描述为强约束生效前的历史设计，不再允许执行批准fallback或Switch。Qwen驻留继续允许。批准模型偏好与健康驻留分开：一个批准fallback正常运行时，不为偏好自动打断它。MAX_LOADED_MODELS=1与keyword检索保持，模型管理器源代码中的现有服务/任务职责未扩大。

## 冻结来源和范围

- 原始生产管理器字节SHA256：`856f38b6edb088327e2138b88e68961db1a153b451aedb6709bea9fd2a8e99fa`，本机只读来源字节一致。
- r1候选`ed9cd6652852ef488170fa625eec2f44ac4270d0dd21e9cb920f5783a2da12c5`被独立审查阻断：保留了Switch的错误回滚。该候选没有部署，历史fixture用于回归复现。
- r2候选SHA256：`37cc7582d9dee079c010cd5f7b2e58289ca9f23fd6cfe0a3950f414a44c59f94`。
- 仅替换Invoke-Repair、Invoke-Switch和严格单驻留Test-PublicAliasResident；新增4个冷却策略函数；32个其他函数与顶层mutex/dispatch逐字保持。
- 新增冷却状态路径为现有模型state_path后缀`.repair-policy.json`，候选实际部署/执行时需要纳入独立授权、备份、回滚和验收；本机测试只写隔离临时目录。

构建器：[build_qa_model_repair_candidate.ps1](../../tools/build_qa_model_repair_candidate.ps1)。策略与替换函数：[冷却策略](../../tools/qa_model_repair_policy.ps1)、[Repair](../../tools/qa_model_repair_stable_function.ps1)、[Switch](../../tools/qa_model_switch_stable_function.ps1)。这些函数片段由受控PowerShell7 UTF8入口构建或加载，不能作为未审查生产入口独立调用。

## 检查结果与可复现命令

```powershell
python -m pytest tests/test_qa_model_repair_policy.py -q --basetemp .codex_runtime/qa-model-repair-stability-20260917/pytest-temp-new
```

最终26通过：13策略检查、10实际Activate/Resident依赖检查、3Switch缺陷/前代复现检查。中间r4为25通过/1夹具错误：真实Invoke-Warmup stub遗漏stale-state故障模式，已补该注入，r5完整26通过。没有把中间审查文字里的通过数当实际pytest输出。

实际Activate函数与生产原始依赖逐字一致，冻结[前代fixture](../../tests/qa_regression/model_activation_dependency_fixture.ps1)和[r2 fixture](../../tests/qa_regression/model_activation_dependency_fixture_r2.ps1)均无action dispatcher或顶层I/O。测试的cp/HTTP/Scheduled Task为隔离替身，不能证明现场模型稳定性或线上回答正确率。独立gpt-5.6-luna low最终代码审查PASS，r1FAIL历史保留。

## 历史计划与原授权边界（已取代）

先完成[固定模型窗口原822题复测](2026-09-17-qa-v26-model-window.md)所需独立授权。长期管理器部署须另外准备最小受控执行器并审查：暂停恢复任务未来触发、等待现有模型切换结束、核验原文件/任务/模型身份、备份和原子替换、finally恢复原Enabled、失败回滚、文件/任务/alias/resident/受保护PID验收。管理器或计划任务变更不能混入8093代码发布。

真实效果仍须完整审核822原失败/部分题最终答案，按模型digest分层统计。当前V26批次0发送，不能从本机26检查推导生产准确率提升。继续由[33项完整方案](2026-09-17-qa-full-optimization-plan.md)追踪全部剩余问题。
