# 8093 智能助手自动诊断—修复—验收报告

追踪编号：`OPS-8093-ASSISTANT-AUTO-RECOVERY-20260805`  
完成时间：`2026-08-06T10:51:39.260426+08:00`  
源报告：`D:\文件\冀南钢铁运行中第二版本\logs\assistant_8093_auto_recovery\20260806_105139_recover.json`

## 结论

- 成功：`true`
- 修复前分类：`healthy`
- 修复后分类：`healthy`
- 实施动作：`none`
- 真实问答请求数：`1`
- 服务恢复与验收耗时：`437.506s`
- 2026-08-06 本轮根因：8093 在并行部署/恢复流程的受控停启窗口中确实无监听，浏览器因而抛出 `Failed to fetch`；SCM 停启记录、受控 `KeyboardInterrupt` 与同期文件哈希变化相互印证。
- 排除项：本轮不是 PostgreSQL `PoolTimeout` 复发，也不是 11434/27B 模型整体宕机。

## 包与验收证据

- 远端受控包：`20260805_v2_69318ce805c3`
- 远端目录：`C:\ProgramData\BFV4\assistant-auto-recovery\packages\20260805_v2_69318ce805c3`
- 默认检索：`keyword`
- 默认证据数：`2`
- 模型驻留：`['chiqiong-blast-furnace:latest']`
- 页面哈希：`4394D60B059CD65BDDA16D63A680F19B57880B6822C6ECE87A4190AFEAAFAC00`
- 页面容错标记：`True`
- SSE 总耗时：`33993.3ms`
- 远端 SSE 报告：`F:\高炉炼铁项目-real-sensor-v2_V4_8093_PREVIEW\logs\acceptance\8093_keyword_knowledge_20260805_20260806_104611\assistant_keyword_knowledge_sse_once.json`

## 固定边界

- 连通性恢复时间与服务修复计时分离；VPN/SSH/8093/11434/PostgreSQL 未全通时不开始部署。
- 只自动修复已知哈希范围内的守卫合同或 keyword 漂移；未知哈希拒绝覆盖。
- 所有新 8093 写入流程使用 `Global\BFV4PreviewProxy8093Deployment` 互斥；纯页面修复使用原子热更新，不重启 8093。
- 只读 GET 可按 1.5s/3s 退避重试；问答 POST/SSE 绝不自动重发，防止重复会话与模型负载。
- 每次 recover 最多发送一个真实 SSE POST，失败后不自动重试。
- DOCX 与追踪报告在服务恢复后由独立 docs 阶段生成。
