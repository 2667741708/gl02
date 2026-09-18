# V15 原文完整性、多章节和最新追问修复

- 状态：已部署并完成定向复测；33 项整体仍执行中。
- 最后核对：2026-09-16。需求：`REQ-QA-FULL-ISSUE-INVENTORY-20260916`；问题：QAOPT-K03/K06/R10/E05。
- 权威来源：冻结发布清单、受控部署输出及独立逐题审查；仅适用于 8093。
- 生产提交：`25d4cd1cc4777153bcbe1d8cd38b4ab1755f9874`；父提交 `06db3d6db6371af381816cc1523cc294c0981a18`。
- 记录后当前主线又前进至 `3677b242720ddfa1bf5a20a31c98e4f70ea7c01f`，只修改 `thermal-trend-live.css`；只读核对本轮三文件哈希不变，保留该并行页面修复。上面的提交是智能助手发布版本，不冒充最终主线 HEAD。

## 修复和可核对证据

1. `qa_document_integrity.inspect` 独立核对来源权限、原文哈希、原子块归属、聚合块原文行序及全文缺行；不以连续片段编号推断末页完整。
2. `inspect_selected_scope` 逐岗位/规程核对选中章节与原子/主题索引的一致覆盖；删除聚合末尾而原子仍在时不会错误 completed。缓存绑定原文及岗位元数据，删改即失效。
3. `qa_document_knowledge._original_subsections` 逐一处理全部明确章节引用：已知章节保留原文，缺章单列，整体 partial；明确上限不会截断后伪称完成。
4. `mcp_conversation_context.update_tool_context` 最新读取清除旧历史窗口；无效时钟、非有限数值及非法窗口不允许继承。公开继承字段来源和依据；来源消息 ID 尚未全链路绑定。
5. 同时禁止代码执行和代码示例生成；正常用户数据分析继续允许。

符号行号：TODO-LINES。

## 验证

复现本机聚焦回归：`python -X utf8 -m pytest tests/test_qa_context_boundaries.py tests/test_qa_v6_contracts.py 高炉前端数据/智能助手/tests/test_mcp_conversation_context.py tests/test_qa_document_integrity.py tests/test_qa_document_knowledge.py tests/test_qa_v12_safety.py tests/test_qa_retest_persistence.py tests/test_qa_release_readiness.py -q`。
部署模板验证：`pwsh.exe -NoLogo -NoProfile -File tools/verify_qa_routing_release.ps1`。实际原文候选只读检查复用 `check_qa_knowledge_candidate_readonly.py --summary --offset N --limit 100`，N为0、100至800，最后一批33题。已发生产复测不得自动重复此轮。

- 112 个不同针对性测试通过：110 项完整聚焦回归，加 2 项缓存原文/岗位元数据变更失效测试；新测试加入长期回归集合。
- 3 个部署模板及只读检查入口语法通过；PowerShell 7 UTF-8 验证 19 个标准入口通过。
- 实际生产 KB 分 9 批完成 833 项只读候选核查：803 项原文覆盖候选通过，30 项 oracle 冲突单列；0 缺口，0 POST，0 模型，0 数据库写入。此结果不等于833题全量独立语义通过。
- [知识候选报告](../../tests/qa_regression/knowledge_v15_candidate_readonly_20260916.json)。
- 新轮真实生产 5 次 POST，5 次确定结果，0 自动重发；独立审查 5 passed。多章节及未知章 0 工具/模型；历史窗口种子与最新读取各 1 工具；混合代码题正常分析均值且按策略 partial。
- [逐题脱敏报告](../../tests/qa_regression/routing_v15_production_review_20260916.json)。原始答案和生产读数仅保存在忽略提交的受控运行目录。

## 部署验收

- 8093 PID：15940 → 12608；HTTP 200；守卫暂停后恢复；未回滚。
- 保护进程：8094/8768/8770/5432/11434 部署前后一致；8892 均无监听。
- 备份：`F:/高炉炼铁项目-real-sensor-v2_V4_8093_PREVIEW/backups/qa-routing-v15-20260916-r1-20260916-210751`。
- 激活 36736.417 ms；版本记录 7506.597 ms；CAS 1 次；199 行实际语义变化，0 换行迁移。
- 精确目标仅 `qa_document_knowledge.py`、新增 `qa_document_integrity.py`、`mcp_conversation_context.py`；23 项依赖哈希一致，保护既有无关改动。

## 适用限制和剩余工作

完整性门证明原文归属与覆盖，岗位元数据真实性、语义角色和条款边界仍需独立审核。30 项 oracle 不允许为通过测试自动改写。历史加当前数据复合任务、浏览器有界消息与分页、全部工具故障矩阵及数据单位/零值/稀疏覆盖依赖继续按 [33项执行台账](../../tests/qa_regression/optimization_execution_ledger_20260916.md) 推进。

此前 [仅本机章节缺尾记录](2026-09-16-qa-document-scope-tail-local.md) 是已被本轮取代的阶段快照；保留审计价值。
