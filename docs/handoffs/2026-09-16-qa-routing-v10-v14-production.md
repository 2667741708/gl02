# 智能助手 V10–V14 生产修复与逐项验收

状态：本轮已部署、定向复核完成；33项整体修复仍在执行。
最后核对：2026-09-16。
需求：`REQ-QA-FULL-ISSUE-INVENTORY-20260916`。
权威来源：密封清单、Reliable SSH只读生产记录、单发送claim、独立最终答案审查。
适用边界：8093智能助手；其他服务和模型配置不在本次修改范围。

## 当前结果

生产修复版本：`06db3d6db6371af381816cc1523cc294c0981a18`。
保留并发部署的ABC33/仪表盘修改，未以本机旧代理或旧页面覆盖生产。
代码执行和代码示例生成继续禁止；普通问答、用户数据分析及授权只读查询保留。

|版本|修复与真实结果|生产提交|针对性测试|
|---|---|---|---:|
|V10|完整表格边界、短术语、长原句和编号章节；5题独立核对通过|`6d2a47aeb16e24cf71e228c0c355b4931b6c6a27`|79|
|V11|受控turn消息投影；5题通过；另803知识题原文覆盖与来源合同核验通过|`9c52d69e2d027bc1dccc42cfd94c65254ee6e803`|88|
|V12|制度复合子任务隔离、可读工具失败证据、DAG依赖校验、条件性工艺因果；7题5通过/2失败|`7220e6867c62fb161d2333057fcf130a3dfabb0d`|137|
|V13|制度加简单实时读取使用类型化事实，消除模型追加指标；3题1通过/2因单位失败|`9f70a9241bce68599b3499bb4079f376b8059bad`|63+4就绪故障|
|V14|复用生产GL02规范单位合同、说明血缘、不换算原值；未知单位partial；3题全部独立语义通过|`06db3d6db6371af381816cc1523cc294c0981a18`|35+4就绪故障|

V14中未知制度题以`partial`准确声明未完成制度子任务，因此按预期合同通过；不能据此声称未知制度内容已经回答。
简单压力读取无模型请求；没有SSE外部工具事件不表示未读数据库，服务端预取仍是只读数据查询。
用户提供10、20、30的平均值20与制度原文分别完成，没有查询生产实时工具。

## 知识833题单列

- 原始833题：803题有效，30题存在编号/父路径或同问不同标准答案冲突，明确阻断。
- 803题均真实单次POST并取得确定结果，自动重试0。
- 803条答案均核验预期原文覆盖、确定性制度路由、来源、文档版本/哈希、参考ID及当前两条消息投影。
- 此结论是原文覆盖与合同通过，不能推断833题全部独立语义通过；新模型持出及旧结果逐ID对齐继续处理。
- 源原文5897个非空行在原子索引中均有覆盖；4540个原子片段连续属于权威原文；109个章节及805个主题片段的全部原文行均属于权威源。
- 聚合片段跳过中间标题，193个非连续聚合不能误报为193个伪造片段。执行器独立缺失末尾门仍需补齐。

脱敏证据：[803知识题覆盖](../../tests/qa_regression/knowledge_v11_production_coverage_20260916.json)、[权威源审计](../../tests/qa_regression/document_provenance_readonly_20260916.json)、[30个oracle冲突](../../tests/qa_regression/knowledge_oracle_audit_20260916.json)。

## 部署验收与中断处理

所有候选使用真实已接受生产字节构建差分；各次临时索引检查均无换行迁移。
V14精确替换`qa_verified_facts.py`，SHA256 `461364b60dc6f4e987d0f997f9e3f1e973cd07ea503a44d8ea3760b681bd63fa`。
V14激活前后8093 PID `18736 → 15940`，HTTP200，首次就绪检查proxy/ollama/model均通过。
8094/8768/8770/5432/11434的PID在各次成功激活前后不变，守卫已恢复，成功部署无回滚。
V14激活阶段38303.125ms，生产Git记录4615.486ms，CAS一次。

V12及V13首次启动健康检查失败，均先回滚并只读核对基线、服务和模型状态，没有自动重放部署或问题。
早期部署器没有保留具体false字段，因此不能把确切根因断言为模型启动竞态。
新就绪门最多3次GET，公开布尔状态及异常类型；持续失败仍回滚，未修改模型/驻留配置。
V13第一次回归只发送一题，第二题在claim之前因模型检查拦截；仅证明未发送的后两题续测，第一题排除。合计3次POST、0重放。
全部8条旧claim保守排除；历史原始采集的不确定题禁止重发。

## 已实施程序合同

- `qa_document_compound`：按独立子任务核验原文，正式制度不交给模型补写；模型仅看到非制度问题；最终合成保留来源、缺项与整体partial。
- `qa_tool_fallback`：晚期工具/模型失败保留有界可读事实，过滤连接串、SQL、凭据及原始异常；未知结构不充当证据。
- `CrossSourcePlan`：绑定路径必须指向声明的上游依赖，重复依赖、未知依赖和环在执行前拒绝。
- `qa_verified_facts`：按规范对象绑定读数/时间/来源；工具单位优先，缺失时复用已接受的GL02公开单位合同并注明来源；未登记单位partial。
- `response_projection=turn`：受控客户端只返回当前精确user/assistant两条消息，owner与角色校验保持；默认浏览器全会话合同兼容保留。
- 工艺分析：顶压受调节设定影响，不能仅凭顶压推透气性；风温/焦比/喷煤推断必须条件性说明热平衡、氧量、原燃料等限制。

符号行号：TODO-LINES；稳定合同入口见程序/API/测试参考，不编造行号。

## 逐项剩余验收

全部33项权威清单见[逐项执行台账](../../tests/qa_regression/optimization_execution_ledger_20260916.md)。
下一轮继续处理独立索引末尾校验、历史加实时复合任务、多轮继承清空、浏览器历史分页、全工具类型证据及故障矩阵。
生产A–D温度缺单位/全零/覆盖稀疏及外部批准模型占槽仍为明确依赖，不能通过猜单位、零填充或修改未授权服务掩盖。
30个oracle需按权威源独立审核后版本化修正；长期SLO属于持续运营项。

## 可复现入口

```text
python -X utf8 -m pytest tests/test_qa_v6_contracts.py tests/test_qa_v12_safety.py tests/test_qa_retest_persistence.py -q
python -X utf8 -m pytest tests/test_qa_release_readiness.py -q
pwsh.exe -NoLogo -NoProfile -File tools/verify_qa_routing_release.ps1
python -X utf8 tools/build_qa_remediation_execution_ledger.py
```

真实POST使用新round、持久claim和`run_qa_failed_retest_once.py`，不得重复执行已有round或不确定题。
原始答案/会话/测量及受保护认证状态仅在忽略提交的受控位置；公开Git只保存脱敏SHA、计数、状态和审查结论。

阶段报告：[V10](../../tests/qa_regression/routing_v10_production_review_20260916.json)、[V11](../../tests/qa_regression/routing_v11_production_review_20260916.json)、[V12](../../tests/qa_regression/routing_v12_production_review_20260916.json)、[V13](../../tests/qa_regression/routing_v13_production_review_20260916.json)、[V14](../../tests/qa_regression/routing_v14_production_review_20260916.json)。
