# V32最新值证据与完成状态修复

状态：本机r2冻结候选、284项相关回归及独立审查通过；未部署、0次线上提问。
最后核对：2026-09-17。需求：REQ-QA-LATEST-EVIDENCE-20260917、REQ-QA-UNMAPPED-TRIAGE-20260917；关联QAOPT-E02/E03/E05。
权威来源：V31冻结代理、已核验生产事实模块、真实函数隔离回归、首次最终判定及gpt-5.6-luna low只读审查。适用范围：普通传感器最新读数及部分完成披露；不改模型、制度原文或生产数据。

## 已确认缺陷与修复

|缺陷|证据及本机修复|
|---|---|
|最新值直接答复缺对象/来源门禁|V31真实函数可将DP_total元数据下的数值显示成P_top；V32同时校验请求列表、明确对象绑定、typed source、只读策略、有限数值及观测时间，非法项不输出正式事实|
|预取接受布尔来源、过大整数可能异常|生产原函数接受profile=true并转为字符串，finite对超大整数可抛OverflowError；新门禁拒绝，安全有限值检查保留其他统计逻辑|
|缺单位/质量释义/采集标记被当完整读取|TPL-254A275F94B2E4D5已记录单位与采集时间不足；保留已保存值，missing_evidence_fields列出缺项，complete=false/partial，0额外查询或模型回合|
|采集时间来源混淆|真实pSpace构造器以now_text写collected_at；答复标为接口读取标记时间，其他来源标为工具采集标记时间，明确不等于原传感器物理采样时刻，缺项不从数据时间推导|
|派生平均值组件可能缺失或时间不同|真实T_top函数按返回组件求平均并取最大字符串时间；答复核对A-D四个唯一组件、同一数据时刻、latest时间与均值复算；不齐全则保留返回值并明确不能作为同一时刻完整均值，保持partial|
|日期被当观测时刻|r2要求时间包含时分；date-only观测被拒绝、采集标记列缺项，不补造时间|

已登记精确单位继续继承并披露，原工具单位优先，未知单位不猜测、不转换数值。质量仅披露已识别标签或数值原始标记，未知任意文本不回显；Held不证明新增实测或炉况稳定，Bad/Uncertain及未核实质量不能支持正式正常/风险等级。单点保存值不能证明此刻无异常、历史趋势或因果关系。

## 两条真实答复路径

- [预取事实 qa_verified_facts.latest_item:L90](../../高炉前端数据/智能助手/backend/qa_verified_facts.py#L90)及[prefetch_outcome:L101](../../高炉前端数据/智能助手/backend/qa_verified_facts.py#L101)保留有效对象与逐字段缺项，不为补元数据再调用工具。
- [最新证据门禁:L212](../../高炉前端数据/智能助手/backend/qa_statistical_evidence.py#L212)、[时间质量披露:L236](../../高炉前端数据/智能助手/backend/qa_statistical_evidence.py#L236)及[直接工具完成合同:L286](../../高炉前端数据/智能助手/backend/qa_statistical_evidence.py#L286)在确定性renderer和异步工具出口共同使用。完整latest读取不使分析任务变成已完成；缺latest证据则即使有文字也保持partial。
- 代理仅改deterministic_mcp_answer、qa_mcp_tool_loop_async。事实模块仅改finite、latest_item、prefetch_outcome，其余AST保护；MCP、固定底座、V29完成模块与V30质量模块字节保留。没有新增API、配置、SQL查询、数据库迁移、模型切换或重试。

## 回归与冻结

生产事实模块及本机原始模块SHA256均15a43e3909e6528faa71456a4a6ec97b8a9ad2e758d2863ae5d7b1b8ba64cfeb；先核验再冻结私有baseline。V31代理基线bb3aae24828a85cba91dc1a24b7455f29c37d4b885b815bca069c379837c0679。

V32r2：代理a0348df3ac44ec7a2c5614fcd727a4450ff372f8f0c1d3623baa0460b673d260；统计证据模块cac4b4a3f8b3c769cdc0d6dec39c94a53dda48a8cce8ec8b7b4ecaab80445e4c；事实模块b89705dda837bcc3cacd61a851683d4ef7f0a2ba633f8261014195cbfb306101。
MCP继续2d85a74658db4efe5e241cf4158aa926a363957acf2689b916da0f18475d9e87；固定底座模块e1251801bb9e4e1eb29e78ee138b34ba3bea95b68b46a95f0f960d65ded48c1d；完成状态模块6eed7297677b04efce390be18fd9c76a44018a02bd6e7971220c026712b3a76b；质量模块62347c9ca913e52ff1dcab0829ddc2db4aa2b82023a398fd06e540541a5b7f8f。

```powershell
python tools/build_qa_v32_latest_evidence_candidate.py
python -m pytest tests/test_qa_latest_evidence.py tests/test_qa_v6_contracts.py tests/test_qa_latest_reuse_and_code_offers.py tests/test_qa_v12_safety.py tests/test_qa_renderer_contract.py tests/test_qa_statistics_evidence.py tests/test_qa_window_quality.py tests/test_qa_final_completion.py -q
```

r1聚焦116项、扩大282项均实际通过；r2增加两个日期反例后，最终284 passed（新latest证据46、既有读取/禁代码72、V31统计/质量126、完成状态40）。旧基础夹具明确补上Good与采集标记，缺字段的独立反例验证partial，未删除缺项场景。独立审查r1、r2及补充归类均PASS。
回归使用合成数据和真实提取函数；工具出口completion表达式有真实AST执行检查，未执行线上完整异步工具链或全处理器。冻结构建器拒绝覆盖候选，新克隆发布接缝依赖已核验私有源码种子。

## 九条漏分类记录

[补充归类](../../tests/qa_regression/unmapped_triage_supplement_20260917.json)关联3条工具读取/联合分析和6条完整制度原文缺项。以既有最终判定reason及33问题目录提出问题编号与验收门，保留原partial、source line、输入/结果hash，不改变首次1233题判定、822复测集合或旧冻结inventory。九条均root_cause_confirmed=false、repair/acceptance open；应用补充后提出归类的覆盖缺口为0，不等于根因已确认或问题已解决。

## 生产状态与未完成项

生产仍V26 HEAD 7d8a2b1a73fbd3e5b30cf800135ec32c3fa5548e，代理47b7e75f6a4c2b932ac21b0dd9628d4c049f7a6f2ee083537bbedf1a6c57f431；旧r3为953/953 completed，PID18224/952不存在，自动重试0。本轮没有重启旧批次、重放未知题或更改生产任务/模型/服务/数据库。

本轮两次独立GET快照：先出现别名不匹配冻结摘要、唯一驻留模型也不匹配；后一次别名匹配e4而驻留为空。只能证明状态波动，不能视为已锁定或当前仍驻留其他底座。旧管理器hash仍856f38b6edb088327e2138b88e68961db1a153b451aedb6709bea9fd2a8e99fa。唯一底座持续chiqiongblastfuenace:latest / e4ad74c41d68de1c8004419d8141a2b2df2275fa08f0dcf326ca0e63fb6d8124，不以漂移后的模型替换基线，不通过切换模型继续测试。

禁切换管理器/恢复任务的独立安装授权仍待回复，之后还须8093受控部署和822原失败/部分题同底座复测。未知题TPL-10C8C8FAF2C694EF永不自动重放。顶温未登记单位仍待权威元数据；采样新鲜度/覆盖、组件物理质量和制度全文依赖不因本机答复披露而销项。本轮没有线上准确率或成功回答率提升证据。
