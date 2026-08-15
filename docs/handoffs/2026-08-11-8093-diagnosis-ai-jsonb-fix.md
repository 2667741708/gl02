# 8093 诊断智能分析 JSONB 修复交接

追踪编号：`BUG-8093-DIAGNOSIS-AI-JSON-DATETIME-20260811`

## 结论

8093 主智能助手问答、keyword 知识检索和 Ollama 本身正常；不可用的是
炉况卡中的五分钟诊断智能分析。ABC33 B4 接入后，完整诊断上下文携带
Python/PostgreSQL 原生 `datetime/Decimal` 值，在 `begin_ai_analysis()` 的 JSONB 写入前
抛 `TypeError`，因此接口一直是 `preparing`且 `attempt_count=0`。

## 修复

- [diagnosis_review.py](../../高炉前端数据/智能助手/backend/diagnosis_review.py)：
  ABC33 时间源转 ISO-8601；新增 `json_safe_value()`，所有诊断 JSONB 边界统一归一化。
- [回归测试](../../tests/test_diagnosis_review_api.py)：覆盖完整上下文、时间、Decimal、tuple 和非有限浮点。
- [准备器](../../tools/prepare_8093_diagnosis_ai_json_fix_release.ps1)、
  [部署器](../../tools/deploy_8093_diagnosis_ai_json_fix_22012.ps1)与
  [远端受控脚本](../../tools/remote_guarded_deploy_8093_diagnosis_ai_json_fix.ps1)：
  仅允许一个文件差量，密封基线/目标 SHA-256，失败回滚并恢复守卫。

## 验收证据

- 本机：52 项定向测试通过，三个后端模块 `py_compile` 通过。
- 生产差量：仅 `diagnosis_review.py`，安装 SHA-256
  `0C5EEC107593A090209107AA8422A80F176EDED47023F501F39C6F15E1F4B799`。
- 守卫：`guard_paused=true`、`guard_restored=true`、`rollback_applied=false`；
  备份 `F:\高炉炼铁项目-real-sensor-v2_V4_8093_PREVIEW\backups\diagnosis_ai_json_fix_8093_20260811_212736`。
- 诊断分析：首次正式验收为 `completed`、`attempt_count=1`、返回 40 字摘要；
  后续 code review 试验触发的受控回滚完成后，同一正式版本按 120 秒冷却策略自动重试，
  最终再次为 `completed`、`attempt_count=1`、`has_analysis=true`，最近失败日志为空。
- PID：8093 首次成功部署 `19076→436`，后续验收性增量失败回滚后最终为 `9152`；8094 `17432`、8768 `5628`、8770 `3732`、5432 `12372`、
  11434 `16232` 前后不变。
- 最终只读核验：`BFV4PreviewProxy8093=Running`、8093 HTTP 200、运行文件哈希仍为
  `0C5EEC107593A090209107AA8422A80F176EDED47023F501F39C6F15E1F4B799`，
  keyword 检索启用且返回 2 条证据，六个受控端口均正常监听。
- 唯一 SSE：`request_count=1`，`preparing→prepared→delta→final→done`，
  keyword 证据 2 条，首 delta `5027.5ms`，总时长 `16885.6ms`，验收期间无守卫重启。

## 维护规则

`preparing + attempt_count=0 + TypeError` 优先归类为“进入模型前的上下文/持久化
边界故障”。不要先重启 Ollama、改 Prompt、切换 RAG 或扩大 PostgreSQL 连接池。
验收脚本应校验当前语义字段与前后哈希不变，不应继续使用过期的历史
SHA-256 白名单。
