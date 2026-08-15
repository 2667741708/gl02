# ABC33 上下文智能助手交接（2026-08-11）

## 当前状态

解释合同、权限只读接口、上下文会话、四张增量表、服务端 Prompt 绑定、首轮分析单航班缓存、33 个炉框入口、可最小化弹窗和六类来源筛选均已完成，并于 2026-08-12 受控部署到 8093。

## 固定排障顺序

```text
规则批次 → 解释上下文 → 会话来源 → 上下文快照 → 分析缓存 → 模型状态 → SSE → 助手页面索引
```

关键核对：

- 权威批次：`bf_sensor.abc_rule_evaluation_batches/items`。
- 解释：`GET /api/furnace-rules/{rule_id}/explanation-context?evaluation_id=...`，需 operator/admin 会话，响应 `Cache-Control: no-store`。
- 会话：`POST /api/qa/contextual-conversations` 只传标识符。
- 追踪表：`qa_context_snapshots`、`qa_conversation_origins`、`qa_message_context_snapshots`、`abc_rule_ai_explanations`。
- 首轮分析：`analysis_mode=initial_context_explanation` 且问题文本固定；PostgreSQL 原子 claim/租约保证跨 8093/8094 仅一个 owner，等待者读取同一完成缓存。
- SSE：单次 POST，阶段为 preparing/prepared/delta/final/done；断线不自动重发。
- 安全：QA 会话按 `owner_subject` 隔离；写请求要求同源 `application/json`；上下文会话只允许 `source_type/source_page/rule_id/evaluation_id/reuse_policy` 五个字段。
- 模型响应：先校验严格 JSON、公开公式项、数值引用、五步顺序和 C 类安全提示，再落完成缓存；校验失败不得标记完成。
- JSON 可靠性：Ollama `format` 使用上下文派生 JSON Schema；首次校验失败仅在同一 SSE 内允许一次受控 repair，仍由原 validator 最终裁决，失败不降级。

## 本机证据

- ABC33与既有助手相关回归：`62 passed`。
- JavaScript 语法：两个生产资源均通过 `node --check`。
- 并发合同：六线程结果固定为 `1 owner + 5 waiters`；缓存写入显式提交。
- 8094 隔离预演完成；最终浏览器矩阵为 85/85，原 3 个明确瞬时网络失败只各重试一次并保留首失败证据，真实模型请求为 0。
- 8094 首次真实 SSE 发现模型不满足严格 JSON，状态正确落为 `failed_retryable / InitialAnalysisValidationError`，未写助手消息；由此补上 JSON Schema 与单次 repair 后才允许进入生产。
- 8093 密封部署执行 ID：`abc33-prod-20260812-0156-866ec9d9`；备份目录 `backups/abc33_contextual_assistant_8093_20260812_015656`；`guard_paused=true`、`guard_restored=true`、`rollback_applied=false`。
- PID：8093 `9152 → 6060`；8094 `5912`、8768 `5628`、8770 `3732`、PostgreSQL `12372`、Ollama `16232` 均不变；HTTP 8093=200。
- 真实验收：`request_count=2`；首次解释与人工追问均包含 `preparing → prepared → delta → final → done`；context hash 为 `f901728047fcd25f2c50e514ed6795bcdf9385fd54b9cff906cfe1b50ccc7870`；回答分别为 849/501 字；问答期间 8093 PID 不变。
- 生产轻量冒烟：Chromium 的 optimization/qa 在 `1366×768` 与 `390×844` 共 4/4 通过，浏览器层真实模型请求为 0。

## 回滚

应用文件恢复备份并重启 8093；数据库新增表不删除。模型不可用时保留确定性解释，禁止回退到浏览器旧分数。
