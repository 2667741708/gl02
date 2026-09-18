# V29最终答复完成状态修复

状态：本机r2候选及独立审查通过，未部署；原822题本轮0发送，线上效果尚未确认。
最后核对：2026-09-17。需求：REQ-QA-FINAL-COMPLETION-20260917；关联QAOPT-E05/O04/T03。
权威来源：V24冻结答案审阅、V28r4冻结候选、实际函数隔离回归与独立代码审查。适用范围：普通问答、工具后模型解释及公开JSON/SSE完成元数据；不修改模型、数据库、计划任务或ABC33严格JSON验证器。

## 问题和行为

原题TPL-01EEE414179DB624在V24已记录最后“待核实项”没有正文；传输结束不能证明答案完整。实际V28代码还存在三类漏口：

1. qa_grounded_mcp_analysis与qa_body_temperature_model_explanation未检查模型正常终止，达到长度上限的文字仍可作为成功解释。
2. 普通SSE只识别done_reason=length，遗漏max_tokens、token_limit和异常终止原因。
3. 公开completion只返回已有字段，不核对实际合成后答案；图表/文档追加可能掩盖模型末尾没有正文的标题。

本轮修复：

|接缝|行为|回归证据|
|---|---|---|
|统一完成模块|识别三种长度上限、空答案、明确未终止/未知原因和白名单空标题；正常stop/eos/end_turn或done=true无reason继续可用|正反例、未知/畸形终止字段|
|普通免工具问答|复用原有一次有界补答；保留原输入，tools=None，补答仍不完整就partial，最多两次模型回合|空答案/长度/空标题/终止失败、第三次调用禁止、取消传播|
|有证据综合分析|未完整结束的模型文字不进入最终分析；保留确定性已核验事实，明确分析部分未完成|实际旧函数复现false success，新函数同样响应回退事实|
|炉体温度解释|截断解释丢弃；确定性统计继续由原工具答复提供|实际函数旧/新对照，一次无工具调用|
|JSON与SSE公开出口|三个出口均传实际最终answer到完成门；有明确不完整证据时降为partial，不覆盖成功事实|实际候选AST出口检查、纯函数合同检查|
|流式结束与合成|必须收到正常done事件；EOF、未知原因、长度上限不算正常完成；图表和文档追加前记录空标题，后续追加不能擦除该缺项|共享finish gate及已记录空标题的合成反例|

MCP失败降级仍最多一次无工具模型回合，没有在本轮增加MCP补答或工具重试。取消/中断继续传播。白名单空标题仅检测单独末行，不执行自然语言正确性判断；输出完整也仍须独立语义审核。

## 同一底座与冻结产物

固定业务别名chiqiongblastfuenace:latest，唯一底座digest为`e4ad74c41d68de1c8004419d8141a2b2df2275fa08f0dcf326ca0e63fb6d8124`。从V28r4代理SHA256`bc815f53bb5242b762eaf6d5071bf8cf6481a1ecdf356884026e8b2a5108cfd3`构建，仅修改两个解释函数和两个QA处理方法，其他AST保留；V28统计模块及V27固定身份模块原字节复制。禁止替代模型、备用模型兜底和自动换模。

r2代理SHA256：`464e866fca464beffc10aaea1c8536cf8483270970550b13f88bbfe0425f84d0`。
完成模块SHA256：`6eed7297677b04efce390be18fd9c76a44018a02bd6e7971220c026712b3a76b`。
生产本轮只读HEAD仍为`7d8a2b1a73fbd3e5b30cf800135ec32c3fa5548e`，代理SHA256仍为V26的`47b7e75f6a4c2b932ac21b0dd9628d4c049f7a6f2ee083537bbedf1a6c57f431`。r3原收集953/953 completed，旧PID18224与952均不存在；没有在本輪重启或重发旧题。

## 实际验证

92项聚焦回归通过，包含40项新完成检查和52项既有空间比较、完成、历史及证据合同检查。新测试直接抽取冻结代理变换后的真实解释函数；处理器出口用AST确认接缝和纯函数合同验证，未启动生产处理器或实际模型。独立gpt-5.6-luna low只读审查r2 PASS。

```powershell
python tools/build_qa_v29_completion_candidate.py
python -m pytest tests/test_qa_final_completion.py tests/test_qa_v6_contracts.py tests/test_qa_history_completion.py tests/test_qa_evidence_policy.py -q --basetemp .codex_runtime/qa-single-base-model-20260917/pytest-completion-fresh
```

构建器拒绝覆盖已冻结候选；复建需先审查新的私有输出目录。pytest使用新的basetemp子目录。程序：[qa_completion.py](../../高炉前端数据/智能助手/backend/qa_completion.py)、[V29构建器](../../tools/build_qa_v29_completion_candidate.py)；回归：[test_qa_final_completion.py](../../tests/test_qa_final_completion.py)；机器证据：[候选元数据](../../tests/qa_regression/final_completion_candidate_20260917.json)。

这些真实接缝回归依赖已核验SHA的私有V28r4候选种子，不宣称新克隆可直接执行全部发布回归；公开核心32题及金标合同校验仍可独立运行。不得用本机旧代理代替冻结的实际生产派生种子。

## 边界和后续验收

- 完成门不等于语义评分；不能证明每个子任务正确、风险阈值有依据或知识引用完整。
- 普通语法断句、Markdown强调标题和非白名单未完成形式仍依赖语义审阅；不把启发式检测包装成完整性证明。
- 生产禁切换管理器及Recovery任务暂停/恢复授权仍待回复，未修改任务或模型。
- 原822失败/部分题没有新增本轮答案；第一次1233有效题的269通过、186部分、636失败、89标准阻断、53证据不足保持原冻结口径，不能用92项本机回归推算线上准确率。
- 后续经固定底座身份及受控8093验收，逐题复测原失败/部分集合，审阅事实、子任务覆盖、截断、图表和知识来源；原发送未知题禁止重放。QAOPT-E05/O04/T03继续保留未销项状态。
