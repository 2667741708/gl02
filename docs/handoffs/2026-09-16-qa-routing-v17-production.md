# V17 历史复合完成合同修复

- 状态：已部署并完成定向复测；33 项整体仍执行中。
- 最后核对：2026-09-16。需求：`REQ-QA-FULL-ISSUE-INVENTORY-20260916`；问题：QAOPT-R02/E05/E03。
- 权威来源：密封候选、受控部署、生产版本记录及独立逐题最终答案审查；仅适用于 8093。
- 生产提交：`ab0dafa3f2008b819ed40211b43a17858ecf654c`；父提交 `19952490c9757602c70534a070bf398ea4cf7b85`。

## 问题与修复

[V16 真实复测](2026-09-16-qa-routing-v16-production.md) 三种历史复合题出现错误 partial。本轮补 `qa_history_compound.normalize_present`：

1. 已完成的正式原文执行器合同缺少布尔完成字段时，仅在识别到正式文档 schema、已验证原文原因与知识清单后归一化为完成；显式 false 不覆盖。
2. 简单实时读取使用旧待审合同的分支，按服务端对象上下文重新检查本请求实际唯一工具轨迹、最新读取类型、全部对象及唯一性，再复用 `qa_verified_facts.prefetch_outcome` 核验有限数值、单位、时间与只读来源并确定性渲染。
3. 未知合同、明确失败、需要模型收尾、分析/趋势/统计任务及无工具策略均不会因非空文本升级为完成。缺单位/时间/来源或对象不符保持 partial。
4. 历史 owner 和消息截止 ID 隔离、历史与当前证据分离、失败保留有效任务继续执行。

符号行号：TODO-LINES。唯一发布目标为 `qa_history_compound.py`；不更换模型或全量旧代理。

## 验证

复现：`python -X utf8 -m pytest tests/test_qa_history_completion.py tests/test_qa_history_compound.py tests/test_qa_history_compound_seams.py tests/test_qa_history_projection.py tests/test_qa_v12_safety.py tests/test_qa_context_boundaries.py tests/test_qa_document_knowledge.py tests/test_qa_document_integrity.py tests/test_qa_retest_persistence.py -q`。

- 133 项针对性测试通过，其中新增 21 项真实缺陷及不能误升级的反例；独立发布审查 43 项通过。
- 部署模板语法通过；远端 Python 3.11 编译、候选哈希、26 项依赖及作用域 Git 状态通过；61 行语义变化，无换行迁移。
- 新轮 5 次真实生产 POST、5 个确定结果、0 自动重发；独立语义审查 5 passed。
- 历史+实时、无匹配历史+实时、历史+正式原文均 completed；缺章、禁止工具+用户均值计算按预期 partial，不隐藏缺项。
- [逐题脱敏报告](../../tests/qa_regression/routing_v17_production_review_20260916.json)。不上传原始答案、生产数值、身份或凭据。

## 部署验收

- 8093 PID：7392 → 6716；HTTP 200；守卫恢复；未回滚。
- 8094/8768/8770/5432/11434 PID 不变，8892 无监听。
- 激活耗时 44515.285 ms；版本记录 2489.895 ms；CAS 1 次。
- 备份：`F:/高炉炼铁项目-real-sensor-v2_V4_8093_PREVIEW/backups/qa-routing-v17-20260916-r1-20260916-213658`。
- 安装 SHA-256：`a7b1cd2cde3b9ce53df5e6611164e3330dae7af0c604e6f627a191072e99ab9a`。

## 剩余边界

本轮修复已知可分历史复合任务；不能据此声称所有复合问题、工具类型和角色并发通过。来源消息 ID 全链路、多角色多轮、浏览器有界历史、知识语义元数据及 30 项 oracle 冲突继续按 [33项执行台账](../../tests/qa_regression/optimization_execution_ledger_20260916.md) 推进。
