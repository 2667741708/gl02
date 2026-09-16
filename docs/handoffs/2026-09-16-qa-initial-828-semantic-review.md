# 首次线上828题离线语义审核交接

状态：已完成；规则初筛仅作历史层，人工语义层已逐题完成828/828。

需求：`REQ-QA-INITIAL-828-SEMANTIC-REVIEW-20260916`。

## 范围与冻结证据

- 审核范围精确为 `collection_status=collected` 且 `answer_review_status=pending_semantic_review` 的828个唯一 `case_id`。
- 首次结果文件哈希、台账哈希和 case ID 集合已冻结；私有冻结文件位于 `.codex_runtime/qa-live/semantic-review-828-20260916/freeze.private.json`。
- 原问题、原答复和工具轨迹只保存在忽略目录的私有检查点；未重发问题、未调用其他模型、未连接生产或修改生产数据。
- 原1题发送状态未知的 `TPL-10C8C8FAF2C694EF` 未进入审核范围。

## 结果

### 历史规则初筛（不可作为语义结论）

此前自动规则层输出的370/157/210/10/81仅保留为 `preliminary_rule_screening` 历史证据。该层存在默认通过和规则匹配局限，不能用于语义准确率、通过率或失败集合。

### 人工语义层（当前检查点）

逐题人工阅读层已完成828/828，剩余0。append-only 决策日志位于忽略目录：`.codex_runtime/qa-live/semantic-review-828-20260916/manual-decisions.appendonly.jsonl`；包含1条更正追加记录，当前日志SHA-256为`d9c3179e55ca1b7e4cdf94b03544829daac09a619182aa0a66452c6347052a14`。

|状态|数量|
|---|---:|
|passed|269|
|partial|186|
|failed|231|
|oracle_blocked|89|
|insufficient_evidence|53|
|已人工审核合计|828|
|remaining|0|

上述人工计数来自逐题阅读完整原题、完整最终答复及必要工具证据后的人工语义决策；`partial`不计完整通过信用。

有效可判题分母为`passed+partial+failed=686`，完整正确语义准确率为`269/686=39.21%`；按全828题计算的保守完整正确覆盖率为`269/828=32.49%`。`oracle_blocked`与`insufficient_evidence`不进入有效可判题分母。

旧规则层快照如下，仅供历史追溯：

|状态|数量|
|---|---:|
|passed|370|
|partial|157|
|failed|210|
|oracle_blocked|10|
|insufficient_evidence|81|
|合计|828|

不得从旧规则层计算有效可判题、完整语义准确率或全828覆盖率；`partial` 不计完整通过信用。

## 主要缺陷类别

- `BUG-QA-SEM-NEGATIVE-CV-20260916`：均值非正或接近零时仍把标准CV当作可解释的相对变异指标；负均值不应被简单取绝对值或笼统称为算错，需结合变量比例尺度与定义域说明CV不可用的边界。
- `BUG-QA-SEM-DIRECTION-CONSISTENCY-20260916`：首末方向与回归方向冲突时仍标记 `consistent`；`recent_direction`属于另一时间尺度，单独相反不构成该缺陷。
- `BUG-QA-SEM-MISSING-SUBTASK-20260916`：比较、历史问答、异常性判断或完整制度条款子任务未完成。
- `BUG-QA-SEM-UNVERIFIED-REALTIME-20260916`：工具失败后仍夹带无法由本轮证据追溯的实时断言。

知识库题先调用 `audit_qa_knowledge_oracles.py` 的 `parse_cases`/`inspect` 做标准一致性筛查；当前89条 `oracle_blocked` 均因权威原文/评分依据缺失而记为 `oracle_invalid`，未发现可确认的标准互相冲突，不能把证据阻断伪装成模型通过或失败。

## 复现与验收

```text
python -X utf8 tools/evaluate_mcp_gold_tasks.py --validate
python -X utf8 tools/review_qa_initial_828.py --build
python -X utf8 tools/validate_qa_initial_828_review.py --report tests/qa_regression/initial_828_semantic_review_20260916.json
```

人工层已凑齐828条并发布最终报告；离线校验结果为 `reviewed=828`、`remaining=0`、`scope_and_hashes_verified=true`。机器可读报告见 [initial_828_semantic_review_20260916.json](../../tests/qa_regression/initial_828_semantic_review_20260916.json)，人类视图见 [initial_828_semantic_review_20260916.md](../../tests/qa_regression/initial_828_semantic_review_20260916.md)。规则初筛仍单独标记为 `preliminary_rule_screening` 历史层；公开原因已脱敏，不含真实计算读数或相关系数。

## 未验证边界

此交接只覆盖首次线上答复的离线语义审核，不代表重新调用线上问答、模型独立复核或生产修复已完成；原始答案和工具返回字段不能从公开报告恢复。
