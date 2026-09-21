# QA V8/V9 原文范围与混合请求修复

- 状态：V9 已受控部署；本轮定向复测完成，剩余边界问题继续修复。
- 最后核对：2026-09-16。
- 需求：`REQ-QA-FULL-ISSUE-INVENTORY-20260916`。
- 权威来源：密封发布清单、Reliable SSH 只读基线、受控部署结果、逐题单发送记录。
- 适用边界：8093；代码执行与代码示例继续禁用；生产数据与原始答案只在受控私有证据中。

## V8 实际结果

生产提交 `379aefb120c84e12302e180503deebfacc9d88e5`；8093 PID `11544 → 8028`；四个目标哈希通过，HTTP 200，受保护服务 PID 不变。九次 POST、九次 done、零自动重放。语义结果 **5通过/3部分/1失败**。分页合同通过不等于全文已回答。

脱敏审阅：[routing_v8_production_review_20260916.json](../../tests/qa_regression/routing_v8_production_review_20260916.json)。V8 证明正式原文、目录、版本/哈希、未知文档澄清、表格完整块及分页可以确定性回答；同时发现小节范围错误及混合请求漏掉查询。

## V9 修复与验收

1. 编号与标题同时匹配；只截取该小节及其子编号，遇兄弟编号停止；多个规程匹配时澄清，不猜测。保留整张原文表格。
2. 纯代码请求才进入代码拒绝分支。混合请求保留正常查询，同时仅代码子任务受限，completion 为 partial/policy_limited。
3. 工具降级残余流式路径在完整禁代码检查后才发送可见 delta；结束标识与长度中止明确记录，禁止把非空当成 complete。

候选由接受的 V8 字节构建，不从旧代理工作树整文件覆盖。73项针对性回归通过；三个发布脚本解析、PowerShell7 UTF-8校验及独立应用/发布审查通过。远端17个依赖哈希一致，临时索引预检 recordable，raw/semantic均130行，无换行迁移。

生产提交 `36b8d938f23923fca81026d7d668891bbf928dfb`；执行ID `qa-routing-v9-20260916-r1`；8093 PID `8028 → 13300`；三目标哈希通过，HTTP200，未回滚。8094/8768/8770/5432/11434 PID 在切换前后均不变。guard恢复，CAS一次，原索引无关条目保留。激活34219.207ms，版本记录2165.711ms，复用SSH连接。

验证入口：`python -X utf8 -m pytest tests/test_qa_document_knowledge.py tests/test_qa_routing_v9_seams.py tests/test_qa_evidence_policy.py tests/test_qa_history_projection.py tests/test_qa_task_plan.py tests/test_qa_v6_contracts.py -q`。预期73passed。复测题集：[routing_v9_cases_20260916.json](../../tests/qa_regression/routing_v9_cases_20260916.json)。生产复测禁止自动重放；发生不确定状态先只读恢复。

## 仍需核对

V9五次POST、五次done、零自动重放，**3通过/2部分/0失败**。混合请求的正常查询子任务通过，代码子任务按用户要求受限，因此整个请求仍为partial；两条小节通过。完整表格存在一行下一节未编号标题，保留为partial。脱敏审阅：[routing_v9_production_review_20260916.json](../../tests/qa_regression/routing_v9_production_review_20260916.json)。

833知识题单独审阅，828旧题未完成语义审阅；发现部分题库编号/标题与标准答案冲突，必须先标记oracle冲突。文档章节末尾完整性需独立源索引证明，不能仅用已有分块连续编号代替。剩余复合知识来源门、多轮、超时隔离、模型外部依赖、最终历史载荷与角色并发仍按33项台账处理。
