# 8093 共享访客会话恢复

- 状态：后端会话恢复与前端匿名入口均已通过 ReliableSSH MCP 部署至 8093，并完成生产 Git 与浏览器验收
- 最后核对：2026-08-14
- 需求：`BUG-8093-GUEST-CONVERSATION-RECOVERY-20260814`
- 适用边界：仅 8093 普通共享访客问答；不开放私有项目、附件、报表、ABC 上下文或管理员接口。

## 根因

8093 匿名 bootstrap 已正常返回 `guest_shared` 和固定共享会话，但聊天 POST 先使用浏览器提交的 `conversation_id` 执行私有 owner 校验，之后才判断访客模式。旧标签页或登录状态切换遗留的会话 ID 因此返回 `conversation_not_found`。

## 修复

- 新增 `qa_chat_conversation_id()`：访客请求始终调用 `ensure_shared_guest_conversation()` 并绑定当前 Host:Port 的固定共享会话。
- 访客提交的缺失、过期或私有会话 ID 不再参与 owner 判断；登录用户继续严格校验 owner。
- `guest_context_not_allowed` 在会话绑定前执行，项目、附件、手工上下文和 ABC 分析仍不向访客开放。
- SSE 失败或会话恢复均不自动重放用户问题。

## 本机证据

- `python -m py_compile 高炉前端数据/智能助手/backend/ollama_proxy_server.py`：通过。
- `python -m pytest tests/test_qa_shared_guest_mode.py tests/test_qa_session_login_bridge.py -q`：13 passed；包含从 handler 入口到模型准备前 payload 会话 ID 已重绑定的方法级回归。
- 生产匿名 `GET /api/qa/bootstrap`：HTTP 200，`access_mode=guest_shared`，证明登录门禁已放开且共享房间存在。
- 生产精确基线 SHA-256：`9BF931B3A14F3FBA96C62E9B8B1663E4DACEF10D2E0E0D8D23D625637E95AC1E`；部署产物从该远端副本叠加单一修复生成，不使用包含其他开发改动的本机整文件。

## ReliableSSH 调用结论

最初的交互启动脚本失败不是 ReliableSSH MCP 故障。脚本把 `--prompt-password` 传给了
`remote_22012_session.py ensure`，但该参数属于 `remote_22012_exec.py`，前者的参数解析器因此在
建立 SSH 会话前直接退出。随后通过 Codex 已注册的
`reliable_ssh_10_30_220_12` MCP 完成身份探测、分块上传、远端执行和只读复核；连接池复用正常，
未发生重连或自动重放。

MCP 调用端在部署过程中达到 30 秒响应上限，但远端请求仍在原连接内执行。此次没有重发部署
命令，而是等待连接池 `in_flight` 归零后读取文件、服务、PID、HTTP 和 Git 状态确认结果。

## 生产验收

- 部署前生产文件 SHA-256：`9BF931B3A14F3FBA96C62E9B8B1663E4DACEF10D2E0E0D8D23D625637E95AC1E`。
- 部署后生产文件 SHA-256：`4C0421A8D9D31735D21138EA7B864629133A601031751CEE5CF653312F42D888`。
- 8093 服务 PID：`16232 -> 8944`；服务恢复为 `Running`，HTTP 200。
- 8094/8768/8770/5432/11434/8892 PID 分别保持
  `5912/6220/3732/12372/18704/404`，未连带重启。
- `/api/ollama/status` 的 `proxy_ok/ollama_ok/model_ok` 均为 true，目标模型为
  `炽穹·高炉炼铁大模型`；MCP health 正常。
- 匿名 bootstrap 返回 `access_mode=guest_shared`，共享会话为
  `qa_guest_4f942a3e6bdfc48b4d26b5ea`。
- 验收只发送一次 SSE，并故意提交 `stale-private-conversation`；服务端在 `prepared` 阶段已改绑
  bootstrap 共享会话，随后产生非空 `final`。用户/助手消息 ID 为 `1648/1649`，没有自动重放。
- 备份目录：
  `F:\高炉炼铁项目-real-sensor-v2_V4_8093_PREVIEW\backups\mcp_gold_8093_20260814_175726`。

## 生产版本

- 旧 HEAD：`849d9554060f7c1252722e8394a9cb224ff13488`。
- 新 HEAD：`e863634b23715bb9cff66e819b2b26be8531ebca`。
- 标签：`prod-8093/20260814-proxy_only-e863634b2371`。
- 提交只包含 `高炉前端数据/智能助手/backend/ollama_proxy_server.py`；部署前已有的
  `assets/abc-furnace-rules-production.js` 与 `backend/abc_score_explanation.py` 改动未被纳入或覆盖。
- 版本清单：
  `F:\BF_Git\V4_8093_PREVIEW.release.guest-conversation-recovery-20260814-1754.json`。

## 前端强制登录回归续修

- 续修编号：`BUG-8093-GUEST-UI-RECOVERY-20260814`。
- 根因：匿名 `GET /api/qa/bootstrap` 已返回 HTTP 200 和 `access_mode=guest_shared`，但生产
  `frontend_dashboard_v3.server.html` 仍是旧发布字节，缺少 `QaGuestNav` 与 `accessMode` 访客路由，
  因而前端错误显示“登录后使用智能助手”。这不是鉴权接口、模型或 ReliableSSH 故障。
- 修复：普通问答默认显示共享匿名访客界面；私有登录改为可选入口，登录框提供“继续匿名使用”。
  operator/admin 私有会话、owner 隔离、同源检查和私有功能门禁保持不变。
- 发布范围：从生产基线 SHA-256
  `25DF40E5FACBA9CBF9DC37FCDA293F1C42970C5CAA9894F9F0A2757A91FCAD4E` 生成最小页面产物，
  只替换 `高炉前端数据/frontend_dashboard_v3.server.html`；安装后 SHA-256 为
  `2D4F344C100FF37BDB82A32CAB47EAFF8D6C44A64EDDEC234A8902FC958F40F2`。
- 本机验证：16 项聚焦回归通过；完成阶段标准矩阵 17/17 通过，覆盖 Chromium 9 个视口、
  Firefox 4 个视口和 WebKit 4 个视口，且没有自动发送 `/api/qa/chat`。
- 生产浏览器：直接打开 8093 页面后可见“共享匿名访客模式”，初始登录框不可见；可选登录框可打开，
  点击“继续匿名使用”可回到访客界面；bootstrap 三次均为 HTTP 200 / `guest_shared`，页面错误和控制台错误均为 0。
- 运行验收：8093 PID `15392 -> 17632`；8094/8768/8770/5432/11434/8892 PID 继续保持
  `5912/18648/3732/12372/18704/404`，未回滚。
- 备份：`F:\高炉炼铁项目-real-sensor-v2_V4_8093_PREVIEW\backups\guest_ui_recovery_20260814_201731`。
- 生产提交：`32130a518f77061633d2fdb32a7cd65033453fa3`，父提交
  `d153ed5cd5e4865f91aab669c6c8dc23c1bc5a38`；提交只含上述 HTML。
- 标签：`prod-8093/20260814-guest-ui-32130a518f77`。
- 版本清单：
  `F:\BF_Git\V4_8093_PREVIEW.guest-ui.guest-ui-recovery-20260814-201723.json`。
