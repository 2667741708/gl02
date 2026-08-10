# 8093 智能助手自动诊断—修复—验收报告

追踪编号：`OPS-8093-ASSISTANT-AUTO-RECOVERY-20260805`  
完成时间：`2026-08-05T11:03:27.969388+08:00`  
源报告：`D:\文件\冀南钢铁运行中第二版本\logs\assistant_8093_auto_recovery\20260805_110327_recover.json`

## 结论

- 成功：`true`
- 修复前分类：`healthy`
- 修复后分类：`healthy`
- 实施动作：`none`
- 真实问答请求数：`1`
- 服务恢复与验收耗时：`184.618s`

## 包与验收证据

- 远端受控包：`20260805_v1_22e4eb675eee`
- 远端目录：`C:\ProgramData\BFV4\assistant-auto-recovery\packages\20260805_v1_22e4eb675eee`
- 默认检索：`keyword`
- 默认证据数：`2`
- 模型驻留：`['chiqiong-blast-furnace:latest']`
- SSE 总耗时：`22185.9ms`
- 远端 SSE 报告：`F:\高炉炼铁项目-real-sensor-v2_V4_8093_PREVIEW\logs\acceptance\8093_keyword_knowledge_20260805_20260805_110253\assistant_keyword_knowledge_sse_once.json`

## 固定边界

- 连通性恢复时间与服务修复计时分离；VPN/SSH/8093/11434/PostgreSQL 未全通时不开始部署。
- 只自动修复已知哈希范围内的守卫合同或 keyword 漂移；未知哈希拒绝覆盖。
- 每次 recover 最多发送一个真实 SSE POST，失败后不自动重试。
- DOCX 与追踪报告在服务恢复后由独立 docs 阶段生成。
