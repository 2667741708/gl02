# ADR-0004：共享匿名访客与 MCP 最终回答降级

- 状态：本机实现完成，待受控部署
- 日期：2026-08-13
- 需求：`REQ-QA-SHARED-GUEST-AND-MCP-FALLBACK-20260813`

## 决策

1. 未登录访问者不再进入全局无 owner 的旧会话，而是映射到稳定的 `anonymous_guest` owner。默认房间键为当前 `Host:Port`，可由 `BF_QA_GUEST_ROOM_KEY` 固定。
2. 每个房间只有一条 `qa_conversations`，复用既有 `qa_messages` 持久化正文、角色、UTC 时间戳、炉况快照引用和隐藏上下文；所有同地址客户端以5秒只读轮询共享消息，不重放模型请求。
3. 访客只允许普通问答、页面当前炉况和公共 keyword 知识证据。项目、报表、本地路径、会话管理、ABC上下文和操作员历史继续要求登录。
4. MCP 工具循环继续保留轮数、次数、超时和策略上限。若没有可用答案，工具错误作为内部轨迹保留，然后在同一用户请求内执行恰好一次 `tools=None` 模型回合。
5. 降级模型必须声明实时数据库未核实，区分已知事实、条件性判断和复核项，禁止编造当前数值、趋势、炉次和时间戳。若模型本身也失败，才返回可追踪错误。

## 取舍

- 不采用两个互相独立的用户会话。工具回合与最终回答回合共享同一消息上下文，才能让最终模型看到已经取得的部分事实和失败边界。
- 不通过无限增加工具轮数解决高频问题。高频意图仍需要确定性路由或复合只读工具；最终降级只保证“可回答”，不把未核实数据伪装成实时结论。
- 共享访客窗口刻意不是私有空间。任何需要项目资料、个人身份或操作审计的内容必须登录后进入 owner 隔离会话。

## 验证

```powershell
& 'D:\ProgramData\anaconda3\python.exe' -m pytest tests/test_qa_mcp_model_fallback.py tests/test_qa_shared_guest_mode.py -q
node tools/check_frontend_babel_syntax.cjs "高炉前端数据/frontend_dashboard_v3.server.html"
```

