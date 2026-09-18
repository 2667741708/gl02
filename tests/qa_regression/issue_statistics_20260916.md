# 全来源问题统计与逐题台账

- 状态：首次采集历史快照（collection_accounted_pending_answer_review），以下分母和信号冻结保留，不能当成当前生产修复状态。当前更新、语义审核进度与原题复测见[逐项执行台账](optimization_execution_ledger_20260916.md)及[V24报告](../../docs/handoffs/2026-09-17-qa-v24-latest-reuse-and-code-boundary.md)。
- 核对时间：2026-09-16T11:26:31.313656（Asia/Shanghai）。
- 需求：REQ-QA-FULL-ISSUE-INVENTORY-20260916。
- 权威来源：只读提取的线上结果、模板索引及定向答案审阅；原始回答与参数留在私有目录。
- [逐题CSV](question_ledger_20260916.csv) / [逐题JSON](question_ledger_20260916.json) / [统计JSON](issue_statistics_20260916.json) / [逐项整改方案](optimization_checklist_20260916.md)。
- [运行版本与批次结束核验](audit_runtime_20260916.json)、[48条正常问题被禁代码误拒审阅](no_code_review_20260916.json)。

## 分母与完成状态

|项目|数量|
|---|---:|
|来源文件登记|77|
|来源条目|1418|
|来源状态 ready|1260|
|来源状态 skipped|11|
|来源状态 contract_only|84|
|来源状态 duplicate|56|
|来源状态 fixture_only|7|
|收集状态 collected|1259|
|收集状态 interrupted_unknown|1|
|收集状态 skipped|11|
|收集状态 contract_only|84|
|收集状态 duplicate|56|
|收集状态 fixture_only|7|

知识来源833行=818条独立ready题+15条重复来源。1260是导入ready数，包含结构说明误导入；不是清洗后有效问题分母。84条contract_only包括31条用户输入合同、40个代码块、13个系统模板，不能全部按普通用户问题发送。

## 内容审阅状态

|状态|数量|
|---|---:|
|pending_semantic_review|828|
|confirmed_failed_fixed_response|330|
|confirmed_failed_manual|75|
|not_reviewed|159|
|oracle_invalid_structural_line|26|

confirmed_failed_manual来自定向独立审阅；confirmed_failed_fixed_response来自明确无答案/生命周期固定错误/知识题误拒。两者互斥。其他已收集结果仍待全文语义审阅，绝不能计为通过。oracle_invalid_structural_line从正式正确率分母排除，但保留执行事实；本表延迟仍为包含误导入行的原始采集耗时，不是清洗后有效任务性能。

## 知识与其他题分别统计

|分组|来源条目|已收集|含工具题数|工具调用次数|p50秒|p95秒|
|---|---:|---:|---:|---:|---:|---:|
|knowledge|833|818|513|1283|43.046|121.157|
|nonknowledge|585|441|361|527|7.016|94.828|

## 可复算的诊断信号（可重叠，不是互斥失败分类）

这些信号也包含合理拒绝等情况，不全部代表错误；具体失败看独立审阅和任务合同。

|信号|题数|
|---|---:|
|tool_timeout|388|
|tool_error|400|
|lifecycle_error|258|
|fallback_failed_route|263|
|guard_rejected_route|88|
|realtime_refusal|120|
|no_code_response|53|
|success_then_lifecycle_error|43|
|incomplete_json|1|
|knowledge_history_tool|436|
|knowledge_test_marker_search|2|
|knowledge_report_tool|147|
|knowledge_report_directory_answer|67|
|knowledge_sensor_or_chart_tool|73|
|knowledge_no_document_capability|1|
|structural_arrow|26|
|no_answer|1|

## 工具错误（按调用计数）

|错误|次数|
|---|---:|
|TimeoutError|462|
|NO_DRAWABLE_DATA|3|
|TOOL_POLICY_REJECTED|3|
|INSUFFICIENT_VARIABLES|1|

## 路由分布（不能直接当通过率）

|路由|总计|知识|其他|
|---|---:|---:|---:|
|grounded_fact_only|158|5|153|
|general_model|103|79|24|
|partial_grounded_analysis|111|85|26|
|model_without_tools_after_mcp_failure_failed|263|219|44|
|grounding_guard_rejected|88|40|48|
|mcp_grounded_analysis|80|37|43|
|deterministic_formatter_with_grounded_model_explanation|5|0|5|
|realtime_failed_closed|52|22|30|
|model_without_tools_after_mcp_failure|263|231|32|
|deterministic_heat_dependency_failure|10|5|5|
|model_planner_then_deterministic_formatter|10|0|10|
|cross_source_with_analysis|1|0|1|
|mcp_grounded_analysis_fallback|68|64|4|
|deterministic_preflight_gate|11|0|11|
|cross_source_deterministic_formatter|5|1|4|
|no_final_route|1|0|1|
|analysis_required|30|30|0|

## 整改事项覆盖

linked_cases包括确认缺陷、风险信号和回归范围，不能解释为该根因已确认影响的数量。

|编号|优先级|事项|证据状态|关联题数|关联已确认失败|
|---|---|---|---|---:|---:|
|QAOPT-R01|P0|统一任务决策，阻止关键词抢路由|confirmed|73|2|
|QAOPT-R02|P0|历史问答与业务证据分离|confirmed|3|3|
|QAOPT-R03|P1|完整解析多对象及范围|confirmed|3|3|
|QAOPT-R04|P1|多时间窗与历史基线|confirmed|2|2|
|QAOPT-R05|P1|报表工作流读取正文|confirmed|1|1|
|QAOPT-R06|P1|权威诊断和复合问题覆盖|confirmed|2|2|
|QAOPT-R07|P1|无工具、用户数据与已有证据优先|design_gap|0|0|
|QAOPT-R08|P0|禁代码策略不误伤正常回答|confirmed|53|48|
|QAOPT-R09|P1|统一能力说明与Prompt目标|confirmed|1|1|
|QAOPT-R10|P1|多轮范围继承与主题切换|design_gap|2|2|
|QAOPT-K01|P0|原文知识路由独立于现场数据|confirmed|161|90|
|QAOPT-K02|P0|禁止用聊天或回归记录替代权威知识|confirmed|436|106|
|QAOPT-K03|P1|完整章节及表格读取|confirmed|2|2|
|QAOPT-K04|P0|避免通用知识补写正式制度|confirmed|3|3|
|QAOPT-K05|P1|报表目录不能回答制度问题|confirmed|147|24|
|QAOPT-K06|P1|知识数据质量和更新可追踪|design_gap|0|0|
|QAOPT-E01|P0|成功证据不能被生命周期异常清空|confirmed|263|249|
|QAOPT-E02|P1|有类型的证据与适用范围|design_gap|0|0|
|QAOPT-E03|P0|字段级事实校验与合理舍入|confirmed|88|47|
|QAOPT-E04|P1|固定计算与统计定义|design_gap|1|0|
|QAOPT-E05|P0|输出字段边界及完整性|confirmed|1|1|
|QAOPT-E06|P1|多源证据冲突与分析深度|design_gap|0|0|
|QAOPT-O01|P0|模型就绪与请求间竞态|confirmed|1|1|
|QAOPT-O02|P1|工具超时和故障域隔离|confirmed|657|289|
|QAOPT-O03|P1|工具参数schema及步骤依赖|design_gap|0|0|
|QAOPT-O04|P1|状态、耗时与可观测性|design_gap|0|0|
|QAOPT-O05|P1|并发与角色边界|not_tested|0|0|
|QAOPT-T01|P0|题目状态、分母与未知发送隔离|confirmed|1|0|
|QAOPT-T02|P0|导入错误与评测污染|confirmed|28|2|
|QAOPT-T03|P1|系统Prompt绑定与故障夹具|not_tested|0|0|
|QAOPT-T04|P1|全答案审阅、持出集与重复可靠性|design_gap|0|0|
|QAOPT-T05|P1|版本冻结、候选对比与受控发布|design_gap|0|0|
|QAOPT-T06|P2|范围缺口与长期运营|not_tested|0|0|

## 未完成及未知状态逐项

|问题ID|状态|来源行|
|---|---|---|
|TPL-10C8C8FAF2C694EF|interrupted_unknown|PT/MCP可执行功能及口语调用模板.md:46|

## 未测项与依赖阻断

- whole-answer semantic accuracy
- knowledge original-text coverage
- all claims fidelity
- tool/parameter exact-match with reviewed gold
- pass^5
- six-user concurrency
- guest/operator/admin parity
- TTFT and token cost
- all raw-series independent statistics
- 缺失来源：docs/MCP_115变量诊断指标测试问题集.md
- 13个系统模板仍需按真实入口绑定；7条fixture_only需隔离候选执行；不把结构验证称为线上通过。

## 复现与校验

先通过Reliable SSH只读执行 tools/collect_qa_audit_snapshot.py，每100条保存一个私有压缩片段；不上传远端脚本，不发送问答。
本机运行：python -X utf8 tools/build_qa_issue_inventory.py --private-dir .codex_runtime/qa-live/full-audit-20260916。
生成器验证无重复结果、片段连续、来源映射、每题一次请求、无重放、分母恒等式、重复指向及事项依赖。

原始证据未修改；路由/模型/服务未改变。统计快照不是最终答案审阅冻结。
