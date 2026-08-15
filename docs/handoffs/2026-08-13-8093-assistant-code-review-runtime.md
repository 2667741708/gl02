# 8093 智能助手代码审查与真实运行验收

- 状态：`usable_with_review_findings`
- 最后核对：2026-08-13 12:15 +08:00
- 事项：`Q-8093-ASSISTANT-CODE-REVIEW-RUNTIME-20260813`
- 目标：`10.30.220.12:8093`；用户原文“820.12”按上下文纠正为 220.12。
- 边界：只读审查与一次真实 SSE；没有修改或重启生产服务。

## 结论

8093 智能助手当前可以正常建立共享访客会话、持久化消息并返回模型回答。真实验收只发送
一次 `/api/qa/chat` SSE，收到 `preparing → prepared → delta → final → done`，答案 568 字，
问答前后 8093 PID 均为 `15368`；8094/8768/8770/5432/11434 PID 均未变化。

代码审查仍发现两个需要后续修复的可靠性问题。它们没有让本次请求失败，但会造成完成语义或
“恰好一次降级”合同不准确。

## 运行证据

- SSH 22、8093、11434、5432 均可达；复用已认证 SSH transport。
- `BFV4PreviewProxy8093`、`BFOllama11434`、`BFV4PreviewWs8768` 均为 Running。
- `/api/ollama/status` HTTP 200，`proxy_ok/ollama_ok/model_ok=true`。
- Ollama 只驻留 `chiqiong-blast-furnace:latest`，27.8B Q4_K_M，context 32768。
- 8093 使用 `keyword`；服务配置显式为共享访客、5 轮规划、最多 5 次工具调用和跨服务并行。
- 两个独立匿名 Web session 得到同一会话
  `qa_guest_4f942a3e6bdfc48b4d26b5ea`；验收后消息数为 4。
- Chromium 1366×768 QA 路由只读冒烟 1/1 通过：ready、无横向溢出、控制台阻断错误 0、
  pageerror 0、真实模型请求 0。报告：`logs/code_review_8093_assistant_20260813/report.json`。
- 聚焦回归 38 项通过；后端 Python 编译和弹窗 JavaScript 语法检查通过。

## Code review findings

### P1：长度截断仍被当作完整成功

真实答案在“2. 检查炉顶温度分布（气流分布）—原理”处结束，明显不是完整句子，但 SSE 仍发送
`final` 和 `done(ok=true)`，消息也作为普通 assistant 消息落库。流式循环虽然通过
`ollama_response_timing()` 保存 `done_reason`，完成分支没有根据 `done_reason=length` 或
响应是否完整改变状态，也没有把 `truncated=true` 暴露给前端。

最小修复：保留模型的最终 `done_reason`；若为 `length`，不得伪装为完整回答。可在同一原请求内
执行有界续写并拼接，或保存/返回 `truncated=true`、清晰提示“回答达到长度上限，请继续”，但
不得静默发送普通成功。增加 `done_reason=length` 的 SSE、落库和前端状态回归。

### P1：失败的无工具降级可能被调用两次

`qa_mcp_tool_loop_async()` 达限时已经执行 `qa_mcp_final_fallback()`；若这次模型调用异常，返回
`fallback_used=true, answer=''`。上层 `qa_mcp_result_with_fallback()` 只判断答案是否为空，未判断
`fallback_used`，因此会再执行一次 `qa_mcp_final_fallback()`。这违反“工具失败后恰好一次无工具
最终模型回合”，并可能造成重复 token 消耗。

最小修复：`qa_mcp_result_with_fallback()` 遇到 `fallback_used=true` 时原样返回，不再调用模型；
补一项“首次 fallback 模型异常时总调用次数仍为 1”的回归，JSON 与 SSE 两个调用点都覆盖。

## 守卫核对

日志中的 `threshold=1` 发生在服务明确为 `Stopped` 的受控部署窗口，使用的是
`serviceNotRunningFailureThreshold=1`，不是普通探测阈值漂移。当前权威配置为
`failureThreshold=3 / serviceNotRunningFailureThreshold=1 / 15s / 600s`，服务 Running、
监听 PID 15368。当前未发现守卫在本次问答期间自动重启。

## 后续验证合同

修复上述两项后至少运行：

1. `tests/test_qa_mcp_model_fallback.py`：失败 fallback 不得二次调用模型。
2. 新增长度结束合同：`done_reason=length` 不得作为无标记完整回答。
3. 相关 QA/共享访客/并行规划聚焦回归。
4. 生产只发送一次真实 SSE，验证完整答案、PID 稳定和受保护端口不变。
