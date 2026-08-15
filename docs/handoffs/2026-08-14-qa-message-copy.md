# 智能助手问题与回复复制实施记录

> 状态：本机与 220.12:8093 已完成  
> 最后核对：2026-08-14  
> 需求编号：`REQ-QA-MESSAGE-COPY-20260814`  
> 权威来源：当前前端源码、聚焦测试和单视口浏览器报告

## 1. 需求与结果

智能助手现在会为每条已发送的用户问题显示“复制问题”，为每条助手回复显示“复制回复”。点击后只
复制该消息的可见正文；成功短暂显示“已复制”，浏览器拒绝剪贴板权限时显示“复制失败”。该动作不发起
网络请求，不会重复提问、生成新消息或修改数据库。

回复含 MCP 图表时，复制内容在正文后附加经过既有安全规则归一化的同源图表地址。消息时间、流式状态、
按钮文字、隐藏节点、脚本和样式不进入剪贴板。

## 2. 实现边界

- [frontend_dashboard_v3.server.html](../../高炉前端数据/frontend_dashboard_v3.server.html#L8920)：
  复用一个 DOM 观察器覆盖当前服务端会话和旧会话消息容器，避免分别维护多套 React 消息模板。
- 正文提取在克隆节点上完成，不改动原始消息 DOM；图表只接受既有
  `/data/mcp_charts/` 同源规则，未放宽为外部 URL。
- 优先调用 `navigator.clipboard.writeText`；非安全上下文或旧浏览器使用一次性只读 textarea 和
  `document.execCommand('copy')` 回退，随后立即删除临时节点。
- 本轮没有新增 API、数据库字段、配置项或后端行为。

## 3. 验证证据

- 聚焦测试：`14 passed`。
- JavaScript 语法：`node --check tools/verify_abc_contextual_assistant_viewports.cjs` 通过。
- Chromium `1366×768` QA 单视口：`1/1 passed`；问题正文完全匹配，回复正文包含图表地址且不含
  时间戳；无横向溢出、底栏遮挡、控制台错误或页面错误，真实模型请求 `0`。
- 报告：[report.json](../../logs/qa_message_copy_1366x768/report.json)；截图：
  [chromium_qa_1366x768.png](../../logs/qa_message_copy_1366x768/chromium_qa_1366x768.png)。
- 生产前端构建：`ok=true`、`contractMatch=true`、`changedPixelRatioOver4=0.0`。

## 4. 生产部署与版本

- 本机源码提交：`8e6e8fa9a295ded8d3c438b12141fb9612ae888b`，只包含生产 HTML。
- 受控部署执行：`qa-copy-recommendations-20260814-222600`；8093 PID `4928 → 14396`，HTTP 200，
  `guest_shared` bootstrap 正常，未回滚。
- 远端文件 SHA-256：`86C9CBBDF2A4FE1F0B9DCEB386BD7A70A4DFEBEB7BA2C96D6CBAFEFC6C4ADC80`。
- 生产 Git：`949d3dde6fc2451a4a28c753c651053d218b9353`；标签
  `prod-8093/20260814-qa-copy-recommendations-949d3dde6fc2`；生产工作树干净。
- 生产 Chromium `1366×768` 轻量冒烟 `1/1 passed`，复制问题、复制回复及图表链接均通过，
  真实模型请求为 0。报告：`logs/qa_copy_recommendations_8093_smoke_r2/report.json`。
- 8094、8768、8770、5432、11434、8892 的保护 PID 前后均未变化。
