# 实际系统Prompt摘要与缓存底座凭证

状态：V45-r2本机合同回归和独立审查通过，冻结未上线。最后核对：2026-09-17。
需求：REQ-QA-ACTUAL-PROMPT-BINDING-20260917；主要关联QAOPT-T03，问题状态保持partial。
权威：[脱敏证据](../../tests/qa_regression/actual_prompt_binding_20260917.json)、[33项账本](../../tests/qa_regression/optimization_execution_ledger_20260916.json)。

## 缺陷与逐项修复

1. 用户问题摘要不能证明实际系统Prompt。初始21例11fail/10pass，覆盖真实冻结proxy的请求、消息持久化、JSON/SSE、缓存及外层调度边界。
2. [外层上下文](../../高炉前端数据/智能助手/backend/qa_prompt_binding.py:44)每个HTTP问答独立；并发、异常或取消后finally重置，不收集owner身份。
3. [准备摘要](../../高炉前端数据/智能助手/backend/qa_prompt_binding.py:56)记录最终准备消息及本轮策略；[请求摘要](../../高炉前端数据/智能助手/backend/qa_prompt_binding.py:67)在固定身份检查和最终序列化之后记录实际请求体字节、消息、按位置排序的系统Prompt、工具schema、选项和输出schema摘要。规划/降级/修复按请求顺序记录，不改变上游body。
4. JSON/SSE final/error、现有助手hidden_context和host日志同步安全摘要。非问答请求无active trace时无新增字段；无模型请求的确定性回答requests_built=0。请求构建不证明已发送、完成或准确。
5. [缓存包络与读取](../../高炉前端数据/智能助手/backend/qa_prompt_binding.py:118)保留原验证analysis以及原生成摘要；只允许固定名称和e4摘要凭证。旧/畸形/未知权重缓存拒绝命中，缓存返回current_requests_built=0，保留owner校验。
6. [缓存版本](../../高炉前端数据/智能助手/backend/qa_prompt_binding.py:20)对配置版本幂等追加唯一.fixed-pin-binding.v1。独立审查发现r1重复后缀，3个实际候选常量反例全失败，r2修复；不把潜在缓存死等当已复现事实。新版本键避免沿用旧completed行，无破坏性迁移。

## 验证与影响面

30个新增回归聚焦通过；最终24模块643pass（83.68秒），14金标schema、22共享功能标记和gpt-5.6-luna low复审PASS。
命令完整列表见机器证据；聚焦命令：python -X utf8 -m pytest -q tests/test_qa_prompt_binding.py --tb=short。
冻结16文件：14个逐字节继承V44，仅proxy的11个函数加追踪钩子及ABC缓存版本表达式变化，新增binding模块；其他函数AST不变。读源、planner、固定底座、代码禁令和单用户模块均保持原字节。
原源读取保真沿用V44历史证据并证明reader源闭包不变；本轮没有重新宣称原源测试已执行。无DDL、原始Prompt/生产数据/身份/凭据进入公开报告。

## 新鲜生产只读门与后续核对

r3的953题已完成，原PID无进程，不恢复或重发。生产HEAD e6530983531251e7290d045d96e1aead065585fb新增三个总览展示路径，与本轮后端范围分离；后端proxy/MCP哈希仍为V26。
最新tags→ps→tags均是9111be230d48e53a385a28930fb8cf6972767c83e93c0db51f6b331a534e30fb，固定e4底座不满足。0模型调用/切换/生产写/原题复问/销项，822原失败partial题继续未发送。
按独立授权处理旧恢复任务、11434驻留纠正和源库；随后完成8093受控发布，并在原题真实单次SSE中核对prepared/每回合请求/最终答复/持久化摘要一致。
首次同底座未经证明，不发布严格配对收益；本机合同不计为线上答复正确率。未知发送题保持隔离。
