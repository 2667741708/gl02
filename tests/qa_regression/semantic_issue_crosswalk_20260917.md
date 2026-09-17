# 全题核对与补充语义问题统计

状态：2026-09-17 冻结输入派生统计；多标签不能相加。
来源：initial_semantic_summary_20260917.json；输入哈希见 verified_inventory_20260917.json。
语义审核标签是答案缺陷，不代表已经证明其底层代码根因；映射仅作为后续排查入口。

|语义标签|问题|关联题数|判定分布|建议对应整改项|
|---|---|---:|---|---|
|BUG-QA-SEM-DIRECTION-CONSISTENCY-20260916|趋势方向自相矛盾|4|{"partial": 4}|QAOPT-E04, QAOPT-E06|
|BUG-QA-SEM-MISSING-SUBTASK-20260916|遗漏用户子任务|58|{"partial": 29, "failed": 29}|QAOPT-R01, QAOPT-E05|
|BUG-QA-SEM-CV-DOMAIN-20260916|变异系数适用范围错误|2|{"partial": 2}|QAOPT-E03, QAOPT-E04|
|BUG-QA-SEM-UNVERIFIED-REALTIME-20260916|未经证据核实的实时断言|57|{"partial": 56, "failed": 1}|QAOPT-E02, QAOPT-E03|
|BUG-QA-SEM-CONCEPT-SCOPE-20260916|业务概念或适用范围错误|1|{"partial": 1}|QAOPT-R01, QAOPT-E06|
|BUG-QA-SEM-OBJECT-MISMATCH-20260916|回答对象不匹配|2|{"failed": 2}|QAOPT-R03, QAOPT-E02|
|BUG-QA-SEM-GROUNDING-GUARD-20260916|事实守卫误拒或校验错误|3|{"partial": 3}|QAOPT-E03|
|BUG-QA-SEM-STAT-SIGNIFICANCE-20260916|统计显著性判断无依据|1|{"partial": 1}|QAOPT-E04, QAOPT-E06|
|BUG-QA-SEM-UNRESOLVED-MAPPING-20260916|点位语义未解析|1|{"partial": 1}|QAOPT-R03|
|BUG-QA-SEM-AMBIGUOUS-INPUT-20260916|歧义输入处理不当|2|{"failed": 1, "partial": 1}|QAOPT-R01|
|BUG-QA-SEM-ERROR-DETAIL-20260916|错误说明缺少可定位信息|1|{"failed": 1}|QAOPT-O02, QAOPT-O04|
|BUG-QA-SEM-SAFETY-REFUSAL-20260916|正常任务被安全策略误拒|1|{"failed": 1}|QAOPT-R08|
|BUG-QA-SEM-UNSUPPORTED-INTERNAL-RULE-20260916|内部制度主张缺少依据|2|{"failed": 2}|QAOPT-K04|
|BUG-QA-SEM-KNOWLEDGE-ORIGINAL-MISSING-20260917|缺少所需知识原文|11|{"failed": 11}|QAOPT-K01, QAOPT-K03|
|BUG-QA-SEM-UNSUPPORTED-LIVE-CLAIM-20260917|现场断言超出数据支持|2|{"failed": 2}|QAOPT-E02, QAOPT-E03|
|BUG-QA-SEM-KNOWLEDGE-ORIGINAL-PARAPHRASE-20260917|原文请求被改写|2|{"partial": 2}|QAOPT-K03, QAOPT-E05|
|BUG-QA-SEM-KNOWLEDGE-TRUNCATED-20260917|知识原文被截断|1|{"partial": 1}|QAOPT-K03, QAOPT-E05|
|BUG-QA-SEM-KNOWLEDGE-ANSWER-QUALITY-20260917|知识答案质量或针对性不足|204|{"failed": 176, "partial": 28}|QAOPT-K01, QAOPT-K03, QAOPT-E05|
|BUG-QA-SEM-MISSING-UNIT-20260917|数值缺单位|16|{"partial": 15, "failed": 1}|QAOPT-E02, QAOPT-E03|
|BUG-QA-SEM-ANSWER-CONTRACT-20260917|最终答案不满足要求|39|{"insufficient_evidence": 12, "partial": 23, "failed": 4}|QAOPT-E05|

## 尚缺根因标签的失败/部分题

以下题已有语义判定，但无问题标签；保留未归类状态，不擅自推断根因。

|case_id|类别|判定|来源行|
|---|---|---|---|
|TPL-254A275F94B2E4D5|other|partial|PT/MCP可执行功能及口语调用模板.md:187|
|TPL-4F3E4DA366EA5176|other|partial|PT/MCP少信息口语模板与无Prompt直连测试规范.md:65|
|TPL-AC03EBFC7B6DE0C9|other|partial|PT/MCP少信息口语模板与无Prompt直连测试规范.md:107|
|TPL-BD6C66D1AE3A2397|knowledge|partial|PT/三规二制高炉长工长知识库测试题库.md:113|
|TPL-0138CEF2A2BA93B3|knowledge|partial|PT/三规二制高炉长工长知识库测试题库.md:153|
|TPL-DF40C86F676DD002|knowledge|partial|PT/三规二制高炉长工长知识库测试题库.md:753|
|TPL-1AB4BD6D5D30DFFA|knowledge|partial|PT/三规二制高炉长工长知识库测试题库.md:761|
|TPL-B2385F77F4DDF9B9|knowledge|partial|PT/三规二制高炉长工长知识库测试题库.md:793|
|TPL-5FCE8B443C84E4A8|knowledge|partial|PT/三规二制高炉长工长知识库测试题库.md:809|
