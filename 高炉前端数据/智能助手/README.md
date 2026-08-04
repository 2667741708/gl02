# 智能助手目录

这个目录用于收拢 8092 智能助手相关的后端实现、设计资料和后续拆分模块，避免智能问答、报表上下文、项目管理逻辑继续散在前端数据目录根部。

## 当前结构

- `backend/ollama_proxy_server.py`：8092 智能助手后端主体，包含静态页面服务、Ollama 代理、QA 会话、项目、报表上下文和文件打开接口。
- `docs/智能助手设计手册.md`：智能助手界面与交互设计手册，记录项目侧边栏、报表选择器、上下文篮、右键菜单和流式输出等规则。
- 报表预览页：前端入口为 `#reports`，后端接口为 `/api/reports/templates`、`/api/reports/preview`、`/api/reports/instances`、`/api/reports/tree`。

## 兼容入口

历史入口 `高炉前端数据/ollama_proxy_server.py` 仍然保留，但只作为兼容壳转发到本目录下的后端主体。新的启动脚本 `高炉前端数据/run_proxy_8092.ps1` 已直接指向 `智能助手/backend/ollama_proxy_server.py`。

## 路径原则

后端虽然放在本目录下，但运行时的 `BASE_DIR` 仍固定为 `高炉前端数据/`，因此页面文件、SQLite、logs、projects、reports、libs 等路径不会因为迁移而改变。

## 报表文件

报表实例默认写入 `高炉前端数据/data/reports/`，并按 `年/月/报表类型/日期或小时` 分层。每个实例同时生成 Markdown 和 Word，供模型上下文和现场阅读分别使用。
