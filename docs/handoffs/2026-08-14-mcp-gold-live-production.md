# 8093 MCP 智能体金标逐条生产验收

> 状态：已完成  
> 最后核对：2026-08-14  
> 适用边界：`10.30.220.12:8093` 共享访客只读问答链路

## 结论

截图所示“并行查询 P_top 和上一炉 Si 却只返回 Si”已修复。根因是规范标识 `P_top` 没有命中
GL02 路由词项，而非数据库没有 P_top。修复后唯一一次 GOLD-003 SSE 同时调用 IMES 与 GL02，
返回 P_top `258.355 kPa`、上一炉 Si `0.42%`，两项时间和来源分开显示。

14 项金标逐条处理结果为：9 项生产通过；GOLD-005 的 `072` 被权威 72 小时炉次窗口证伪，状态为
`oracle_invalid`，但依赖门禁能力通过；4 项故障注入题因生产未开放注入接口而不发送生产请求，
mocked 合同均通过。权威机器汇总为
`logs/mcp_gold_live_20260814/final_summary.json`，人类可读汇总为同目录 `final_summary.md`。

## 本轮修复

1. `domain_router.py`：识别规范标识 `P_top`，保证 GL02 与 IMES 可同时入选。
2. `cross_source_executor.py`：工具返回 `ok=false/missing/error_code` 时形成真实失败；依赖步骤不执行。
3. `ollama_proxy_server.py`：
   - 当前问题中的显式对象优先于旧会话对象；
   - 歧义压力、未知 ID、写操作在工具前确定性拦截；
   - 同一 IMES 服务的口语炉次解析与化验查询进入依赖 DAG；
   - 未找到正式炉号时明确不猜测、不启动下游 Si；
   - 无实时请求和相关性答案补足证据边界。
4. 评测器：多轮聚合真实调用轨迹、中文证据字段评分、`oracle_invalid` 分类和零请求离线重评分。
5. 远端新增的诊断证据中文变量映射与 `r2` 缓存版本先同步回本机，再进入生产 Git 基线。

## 验收证据

- 本机聚焦回归：`82 passed`；诊断前端脚本 `node --check` 通过。
- GOLD-005 最终事件：`preparing → prepared → tool_start → tool_result → delta → final → done`。
- GOLD-005 工具：只启动 `imes__resolve_spoken_heat_reference({heat_reference:"072"})` 一次；返回
  `HEAT_REFERENCE_NOT_FOUND`。化验步骤只记录 `DEPENDENCY_FAILED`，没有 `tool_start`。
- 部署执行：`mcp-gold005-20260814-1205-r2`；文件回滚未触发；守卫已恢复、失败计数 0。
- 8093 PID：`8348→14124`；8094/8768/8770/5432/11434 分别保持
  `5912/4036/3732/12372/16232`。
- 最终代理 SHA-256：`B0FD19BFAFD403B7A37A62CC7FDC743185A2F20EBEF03075D99923163F8BEBD4`。
- 生产 Git：HEAD `67d2434cbbb69591ff8e35d4027fd47acfa37850`，Tag
  `prod-8093/20260814-proxy_only-67d2434cbbb6`，工作树 clean。

## 明确边界

GOLD-009/010/011/014 需要服务器主动制造超时、部分失败、全部失败和恶意工具结果。当前生产端没有
故障注入开关，因此这些题的 `local-live` 状态保持 `not_supported`，请求数为 0；不能把 mocked
结果宣传成生产实测。若以后需要做真实混沌验收，应在隔离预览端口增加短期、鉴权、默认关闭的
故障注入夹具，不在 8093 直接制造生产故障。
