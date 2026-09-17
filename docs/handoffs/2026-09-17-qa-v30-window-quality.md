# V30统计窗口质量证据

状态：本机r2冻结候选及独立审查通过；未部署，线上质量计数与语义效果未验收。
最后核对：2026-09-17。需求：REQ-QA-WINDOW-QUALITY-20260917；关联QAOPT-E02/E04/E06。
权威来源：V24原题质量缺项、V26已验收MCP源、V29r2代理、实际函数隔离回归及gpt-5.6-luna low只读审查。适用范围：普通传感器统计与质量披露；不改风险制度、模型或高炉设定值。

## 原缺陷与修复

TPL-01EEE414179DB624已记录Held质量未讨论。V28仅披露首末标记，不能确认窗口全部样本质量。本轮给工具和答复提供可核对的质量证据：

|来源|计数范围与分母|边界|
|---|---|---|
|bf_sensor_postgresql|原统计SELECT及同一tag/时间条件，原COUNT(value)为分母，COUNT(*)单列观察行数|查询匹配行全部计数，不证明采样覆盖率、没有漏采或新增实测数量|
|postgresql_compatible|原统计SELECT及同一炉号/tag/时间条件，原COUNT(one_minute_average_value)为分母|不新增查询，不改变原均值/总体标准差/趋势公式|
|pSpace与派生序列|statistics_from_rows实际用于数值统计的返回样本|可能受条数上限或派生处理影响，whole_window_verified=false，不能称整窗完整|

五种明确标签Good、Held、Bad、Uncertain、DERIVED_AVERAGE加Unknown分别计数。空数值行不进入数据库质量比例，单列excluded_rows。未知文本、数值标志或空质量不猜测为Good，不回显任意未知标签。质量缺项、计数类型错误、总和不一致或时间窗不匹配时继续保留“质量比例未核实”，不补零。

Held说明保持值不能证明新增实测或真实炉况稳定；Bad/Uncertain/Unknown不能支持正式风险/稳定等级；派生平均标记不证明原传感器Good。缺制度阈值仍不能给出正式稳定等级，本轮没有自动剔除Bad样本或改变统计数值。

## 合同与程序

`statistics.quality_summary`包含schema、scope、basis、sample_count、counts和whole_window_verified。数据库结果另含observed_rows、excluded_rows、start_time/end_time；queried_window只表示该查询条件匹配行没有LIMIT截断，不表示物理采样覆盖完整。returned_samples不作整窗声明。

程序：[质量合同 qa_window_quality.py:L22](../../高炉前端数据/智能助手/backend/qa_window_quality.py#L22)、[答复质量上下文 qa_statistical_evidence.py:L52](../../高炉前端数据/智能助手/backend/qa_statistical_evidence.py#L52)、[冻结构建器](../../tools/build_qa_v30_window_quality_candidate.py)、[实际函数回归](../../tests/test_qa_window_quality.py)。
构建器从已验收V26MCP仅改query_postgres_statistics、statistics_from_rows并增加一个后端模块导入，其余AST保留。从V29代理只改deterministic_mcp_answer中的质量时间窗传参，其余AST及固定底座/完成状态修复保留。

## 冻结hash与固定底座

- V29r2代理基线SHA256：464e866fca464beffc10aaea1c8536cf8483270970550b13f88bbfe0425f84d0。
- V26MCP基线SHA256：42d81acb60a0d3b28897c55e5c692e71f75ca5cf262dc8088fa4d1dcc6817884。
- V30代理：92e628b65d373504cdc3b2a73962b7cf3b53d3f6c024f34094b9d97700f497d1。
- V30MCP：2d85a74658db4efe5e241cf4158aa926a363957acf2689b916da0f18475d9e87。
- 质量模块：62347c9ca913e52ff1dcab0829ddc2db4aa2b82023a398fd06e540541a5b7f8f。
- 统计证据模块：bfb955e460012acd4593a9e984fdec017fb3ea3c4e84901f2da117ca407fdca5。
- 完成模块6eed7297677b04efce390be18fd9c76a44018a02bd6e7971220c026712b3a76b、固定身份模块e1251801bb9e4e1eb29e78ee138b34ba3bea95b68b46a95f0f960d65ded48c1d原字节保留。

唯一底座继续chiqiongblastfuenace:latest / digest e4ad74c41d68de1c8004419d8141a2b2df2275fa08f0dcf326ca0e63fb6d8124；不切换、替代或备用模型兜底。
生产只读仍为V26 HEAD 7d8a2b1a73fbd3e5b30cf800135ec32c3fa5548e，代理47b7e75f6a4c2b932ac21b0dd9628d4c049f7a6f2ee083537bbedf1a6c57f431。旧批次953/953 completed，PID18224与952不存在，没有重放旧题。

## 验证及未完成项

r1相关101项通过；r2增加布尔count不能冒充1样本的反例后，质量34项通过，最终组合结果以[机器证据](../../tests/qa_regression/window_quality_candidate_20260917.json)为准。独立审查r1及r2差异均PASS。两种数据库profile实际函数夹具证明原5次查询、参数、范围及数值公式不变；行序列函数前后数值独立复算均值1、总体标准差1一致（合成样本），只新增质量字段。

```powershell
python tools/build_qa_v30_window_quality_candidate.py
python -m pytest tests/test_qa_window_quality.py tests/test_qa_statistics_evidence.py tests/test_qa_statistical_scope.py -q --basetemp .codex_runtime/qa-single-base-model-20260917/pytest-window-quality-fresh
```

构建器拒绝覆盖冻结候选。真实接缝测试依赖已核验私有V26MCP/V29代理种子；不使用本机旧代理替代生产派生版本，不宣称新克隆无需种子可执行全部发布回归。SQL本轮为源码与合成游标验证，未在真实数据库执行；线上SQL耗时、实际质量字段语义、pSpace上限与派生样本还需独立运行验收。采样覆盖率、正式阈值和未登记单位仍待核实。
原822题本轮0发送，没有新线上准确率。计划任务禁切换安装授权仍待回复，未更改生产任务、模型或数据库。所有关联问题保持待线上验收，没有因本机计数合同通过销项。
