# 8093 关键词知识检索正式切换交接

追踪编号：`OPS-8093-KNOWLEDGE-KEYWORD-MODE-20260805`

## 结果

8093 已从空值回退的 `hybrid` 正式切换为显式 `BF_QA_KNOWLEDGE_SEARCH_MODE=keyword`。8093 与 8094 现在都通过 PostgreSQL `bf_assistant.rag_*` 做关键词/词法检索；公共 Prompt、知识意图门控、证据注入、MCP/数据库实时链路和共享 11434 单 27B 策略保持不变。

## 部署

- 时间：`2026-08-05 07:25:21 +08:00`
- 入口：[patch_8093_keyword_knowledge_mode.py](../../tools/patch_8093_keyword_knowledge_mode.py) 与 [remote_guarded_deploy_8093_keyword_knowledge_mode.ps1](../../tools/remote_guarded_deploy_8093_keyword_knowledge_mode.ps1)
- 备份：`F:\高炉炼铁项目-real-sensor-v2_V4_8093_PREVIEW\logs\deploy_backups\8093_knowledge_keyword_20260805_072445`
- 配置 SHA-256：`8A24C83DF93008DD8E358682558E8755442D87052A09FB24F39778F2EAF51FDE`
- PID：8093 `10996 -> 15352`；8768=`15824`、8094=`9976`、8770=`12956`、11434=`6984` 未变化
- 保护结果：8093/8094 页面、共享后端/RAG、守卫脚本、11434 配置均未变化；健康合同仍为 `3/1/15/600`，任务结果 0、状态计数清零，`/api/ps` 仅批准的 27.8B

## 验收

- 配置文件与实际监听进程环境均为 `keyword`。
- 不传 `mode` 的默认知识搜索前后均返回 `search_mode=keyword`、`enabled=true` 和 2 条证据。
- `2026-08-05 08:44:59` 只提交 1 个真实问答 POST；准备态知识检索启用、未跳过、意图 `parameter_optimization`，MCP 工具调用关闭。
- SSE 完整收到 `start(preparing/prepared) -> delta -> final -> done`；首 delta `11709.7ms`，final `23885.4ms`，总计 `23885.6ms`。
- 验收期间无守卫重启，所有受保护 PID/哈希和模型驻留保持。
- 报告：`F:\高炉炼铁项目-real-sensor-v2_V4_8093_PREVIEW\logs\acceptance\8093_keyword_knowledge_20260805_20260805_084403\assistant_keyword_knowledge_sse_once.json`

## 复发入口

若以后 8093 知识问答再次不可用，先按 [AGENTS 固定流程](../../AGENTS.md#8093-智能助手再次不可用时的直接修复记录长期固定)区分守卫重启、知识模式漂移与其它 RAG/MCP/数据库故障。搜索模式漂移时核对实际进程环境与默认搜索接口，再使用同一受控部署器恢复；不得恢复双模型驻留。完整说明见 [Prompt/RAG 专项文档](../8093_8094_Prompt固定KV前缀与知识库回答链路_20260805.md)、[配置参考](../config_reference.md)与 [DOCX 修复手册](../8093智能助手不可用原因与正式修复手册_20260804.docx)。
