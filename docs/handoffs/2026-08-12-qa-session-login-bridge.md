# 8093 QA 会话登录桥接交接

> 状态：已部署并验收  
> 最后核对：2026-08-12  
> 需求：`REQ-QA-SESSION-LOGIN-BRIDGE-20260812`  
> 错误：`ERR-8093-QA-SESSION-REQUIRED-20260812`

## 结论

`qa_session_required` 由受保护 QA 会话门禁返回，表示浏览器没有有效 operator/admin 会话；当时 8093、Ollama、keyword 知识检索与守卫均正常。旧页面没有登录入口，并把该 403 显示成“代理不可达”。

## 修复合同

- 后端鉴权、owner 隔离、同源校验不变。
- JSON 与 SSE 客户端保留 HTTP 状态和 `error` 代码。
- bootstrap 返回 `qa_session_required` 时显示同源登录框；密码不写本地或会话存储。
- 登录成功后只重新读取 bootstrap、项目与短时队列。
- 发送时会话过期，恢复输入并要求手动发送；不自动重放 SSE。

## 验证

- 聚焦 pytest：11 passed。
- dashboard 生产构建检查：通过。
- 本地 Chromium `1366×768`、`390×844`：403→一次登录→会话加载，模型/问答 POST 为 0。
- 生产执行：`qa-session-login-prod-20260812-2248`。
- 8093 PID：`16452→4308`。
- 受保护 PID：8094 `5912`、8768 `4036`、8770 `3732`、5432 `12372`、11434 `16232`，前后不变。
- 安装 SHA-256：`C5148D9BBE96F19935B71E470180C72EAD5E8DBA37DB1DDC192FBF33D6FC42FB`。
- 守卫已恢复，未回滚；匿名 bootstrap 仍为 HTTP 403；`/api/ollama/status` 全绿；本次未发送 SSE。

## 复发处理

先看错误码：`qa_session_required` 走登录恢复，不重启服务；只有健康接口失败、端口不监听或日志证明后端异常时才进入 8093 服务诊断流程。生产更新继续复用本次基线/锚点/Dry Run/互斥/备份/保护 PID/回滚模式。
