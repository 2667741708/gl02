# 共享匿名智能助手与 MCP 降级交接

- 状态：本机实现与聚焦回归完成，未部署 220.12
- 日期：2026-08-13
- 需求：`REQ-QA-SHARED-GUEST-AND-MCP-FALLBACK-20260813`

## 用户可见结果

- 未登录打开智能助手时，默认进入当前服务地址唯一的“局域网共享访客会话”。
- 其他浏览器通过同一地址进入后，最多约5秒看到数据库中的新消息和时间戳；轮询不触发模型请求。
- 访客提问携带页面当前炉况快照及来源时间，并保存在本地 PostgreSQL；项目资料、报表和私有上下文不向访客开放。
- 登录入口仍存在，成功后切换到原有 owner 隔离的私有会话中心。
- MCP/数据库工具失败或达到规划上限时，页面不再直接显示“数据库查询轮数超过上限”，而由模型执行一次无工具降级回答，并明确实时数据未核实。

## 代码与数据

- 后端：`高炉前端数据/智能助手/backend/ollama_proxy_server.py`
- 前端：`高炉前端数据/frontend_dashboard_v3.server.html`
- Schema：`高炉前端数据/智能助手/backend/schema/postgresql_assistant.sql`
- 增量迁移：`高炉前端数据/智能助手/backend/schema/20260811_abc_contextual_assistant.sql`
- 测试：`tests/test_qa_mcp_model_fallback.py`、`tests/test_qa_shared_guest_mode.py`

## 验证结果

- 新增聚焦测试：8 passed。
- 与登录桥接、ABC上下文后端组合：36 passed。
- Python `py_compile`：通过。
- 前端 Babel：通过；仅有既有大文件 deoptimised 提示。
- 扩展套件额外发现一个既有无关失败：`test_8093_8094_prompt_rag_contract.py` 仍断言旧 8094 文件名，未为此恢复旧启动入口。

## 部署边界

本轮没有连接或修改 220.12。部署前必须使用 `deploy-8093-guarded-update`，核对增量 schema、服务配置、匿名 bootstrap、双浏览器共享、唯一一次 SSE、keyword 知识证据、守卫恢复和受保护 PID。

