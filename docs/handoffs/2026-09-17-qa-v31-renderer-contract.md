# V31工具结果答复合同修复

状态：本机冻结候选、126项相关回归及独立审查通过，未部署。
最后核对：2026-09-17。需求：REQ-QA-RENDERER-CONTRACT-20260917；关联QAOPT-E02/E03/E05。
权威来源：V30r2冻结代理及MCP源码、实际函数隔离回归、gpt-5.6-luna low只读审查。适用范围：普通传感器统计及结果格式兼容性；不改变模型、工具策略或生产数据。

## 确认缺陷与修复

|问题|旧行为|本机修复及验收|
|---|---|---|
|合法变量列表格式误拒|工具接受列表内分隔符、首尾空格与去重，答复门禁却匹配原字符串|按实际传感器工具相同分隔符拆分、去重，保持80个上限；规范化后的请求与结果外层变量列表必须一致|
|别名单位缺失|元数据明确绑定到P_top的别名无法继承P_top登记单位|只在canonical/aliases/legacy/short_name/point_id/tag明确绑定后继承规范单位并披露来源；原工具单位优先，不換算数值|
|异常字段导致整轮失败|source=true等容器可能触发.get异常，影响相邻有效项|逐项检查元数据、来源、最新值、统计及首末样本容器；异常项明确记录，继续保留相邻有效事实|

名称不做描述猜测；对象、来源、只读策略和窗口不匹配仍拒绝正式统计。仅支持工具JSON schema声明的字符串列表，不将运行时兼容的顶层字符串或非字符串项作为合法调用。空容器与缺字段不补成已核实证据。

程序：[变量规范化 qa_statistical_evidence.py:L77](../../高炉前端数据/智能助手/backend/qa_statistical_evidence.py#L77)、[明确对象绑定:L53](../../高炉前端数据/智能助手/backend/qa_statistical_evidence.py#L53)、[容器校验:L86](../../高炉前端数据/智能助手/backend/qa_statistical_evidence.py#L86)、[正式统计门禁:L175](../../高炉前端数据/智能助手/backend/qa_statistical_evidence.py#L175)、[候选构建器:L18](../../tools/build_qa_v31_renderer_contract_candidate.py#L18)、[旧缺陷复现回归:L62](../../tests/test_qa_renderer_contract.py#L62)。

## 冻结与验证

V30r2代理基线SHA256为92e628b65d373504cdc3b2a73962b7cf3b53d3f6c024f34094b9d97700f497d1。V31仅修改deterministic_mcp_answer及统计证据模块；其余代理AST、MCP、固定底座、完成状态与窗口质量模块字节保留。

- V31代理：bb3aae24828a85cba91dc1a24b7455f29c37d4b885b815bca069c379837c0679。
- 统计证据模块：ba362f4a9e0312c6decdce81f30ed3c3c9e4346af4013fd967308708aff730c3。
- MCP：2d85a74658db4efe5e241cf4158aa926a363957acf2689b916da0f18475d9e87。
- 固定底座模块：e1251801bb9e4e1eb29e78ee138b34ba3bea95b68b46a95f0f960d65ded48c1d。
- 完成状态模块：6eed7297677b04efce390be18fd9c76a44018a02bd6e7971220c026712b3a76b。
- 窗口质量模块：62347c9ca913e52ff1dcab0829ddc2db4aa2b82023a398fd06e540541a5b7f8f。

唯一底座继续chiqiongblastfuenace:latest，digest e4ad74c41d68de1c8004419d8141a2b2df2275fa08f0dcf326ca0e63fb6d8124；禁止换模型、切换或备用底座。

```powershell
python tools/build_qa_v31_renderer_contract_candidate.py
python -m pytest tests/test_qa_renderer_contract.py tests/test_qa_statistics_evidence.py tests/test_qa_window_quality.py -q
```

新答复合同40项、统计证据52项、窗口质量34项，实际126 passed。初跑8个失败均为两类测试断言问题：重复规范名仍满足旧门禁，STDDEV_POP同时出现在数值行和CV公式；修正反例及计数断言后组合全通过，候选源码未改。独立审查PASS。测试使用合成数据、真实冻结函数及受保护源码种子，不访问生产数据库；冻结构建器拒绝覆盖候选。

## 生产与剩余边界

本轮只读确认生产仍V26，HEAD 7d8a2b1a73fbd3e5b30cf800135ec32c3fa5548e；代理47b7e75f6a4c2b932ac21b0dd9628d4c049f7a6f2ee083537bbedf1a6c57f431。r3为953/953 completed，PID18224/952不存在，没有重启旧批次。

本轮0次线上提问，未改生产模型、任务、服务或数据库。禁切换管理器/恢复计划任务的独立安装授权仍待回复；本机候选通过不代表生产锁定已生效。待该依赖解决、8093受控部署及真实原题复测完成后，才可计算效果和销项。

本轮未扩大历史查询、图表、IMES或最新值的事实验证范围；它们仍遵守各自证据合同。异常项明示也不代表整轮语义通过，822原失败/部分题准确率继续未验证。
