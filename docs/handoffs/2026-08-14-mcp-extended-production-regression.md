# 2026-08-14 MCP 扩展生产回归交接

> 状态：已完成  
> 最后核对：2026-08-14  
> 需求：`REQ-MCP-EXTENDED-PRODUCTION-REGRESSION-20260814`  
> 适用边界：220.12:8093 真实只读问答；故障只在远端回环隔离预览执行

## 1. 结论

本轮把早期少量抽样扩大为可审计的综合回归。8093 共收到 83 次真实 SSE，观察到 90 次真实
`tool_start`，自动重试为 0。关键 GOLD 的 `pass^5`、42 个扩展点位问法、6 并发、连续多轮和跨
MCP 均达到当前合同；4 类故障只在独立回环预览中触发，没有对生产 8093 或生产数据库制造故障。

## 2. 生产结果

| 范围 | 结果 | 说明 |
|---|---:|---|
| GOLD-001/002/003/004/005/013 pass^5 | 25 passed / 5 oracle_invalid / 0 failed | 30 组；GOLD-004 为两轮，因此共 35 次 SSE |
| 14 点位 × 3 问法 | 42/42 | 最新值、1 小时统计、2 小时趋势 |
| 6 并发 | 6/6 | p95 8221.2ms，无死锁、PoolTimeout、重复请求或串线 |
| 连续多轮 | 5/5 | 第二轮继承 P_top 并实际调用统计工具 |
| 跨 MCP | 10/10 | GOLD-002/003 各 5 次，均调用 GL02 与 IMES |
| 会话隔离 | guest/owner 通过 | 生产仅一个账号，双 authenticated owner 未测 |

42 个问法覆盖：顶压 `P_top`、顶温 `T_top`、压差 `DP_total`、冷风压力 `P_blast_cold`、热风压力
`P_blast`、热风温度 `T_blast`、透气性 `PI`、总/南/北料线 `L/L_south/L_north`、喷煤量与设定
`PCI_rate/PCI_set`、富氧率与富氧流量 `O2_rate/Q_O2`。

生产请求账本：

- pass^5：35 次 SSE；
- 42 点位：42 次 SSE；
- 6 并发：6 次 SSE；
- 合计：83 次 SSE、90 次工具启动、0 次自动重试。

## 3. 并发和会话边界

6 个请求的总单题耗时之和为 `30148.4ms`，最大单题为 `8221.2ms`，整批墙钟约 9 秒，证明请求
间有真实重叠。单题完成时间呈阶梯状，符合“不同请求并发、同一 GL02 stdio 服务安全串行”的设计，
没有通过并发复用同一个 stdio 会话冒险。

共享访客与登录 owner 的会话 ID 脱敏哈希不同，验证过程没有发送模型请求或泄露凭据。由于生产
当前只配置一个认证身份，两个不同登录 owner 之间的隔离不能在本轮真实证明，保持 `not_tested`。

## 4. 隔离故障预览

远端临时服务仅监听 `127.0.0.1:18094`，使用真实 Ollama 模型和受控 MCP 夹具分别验证：

- GOLD-009：工具超时后不重放，只给一次无工具降级并声明实时数据库未核实；
- GOLD-010：保留已取得的 Si 事实，明确 P_top 缺失且不作综合判断；
- GOLD-011：工具全失败后不编造当前数值、炉次或时间；
- GOLD-014：工具结果中的提示注入不改变只读和证据边界。

四项 4/4 通过，真实模型最终回合 4 次，自动重试 0，向生产 8093 发送的故障请求为 0。运行后
临时服务已停止，端口 18094 已关闭。这里的 MCP 故障是受控夹具，不是生产数据库真实故障。

## 5. Oracle 修正

首次评分把 GOLD-004 的合法可选目录调用和共享会话继承误判为失败，也把安全同义表达误判为故障
降级失败。修正后的 oracle 支持显式 alternatives/optional 和版本化同义词组，并对 GOLD-004 强制
“首轮明确确认 P_top、第二轮必须查询统计”。重评分只读取已保存结果，额外模型请求为 0；原始
报告保留用于对照。

## 6. 验证和证据

- 汇总：[final_report.md](../../logs/mcp_extended_20260814/final_report.md) / `final_report.json`；
- pass^5：`pass5.rescored.json`；
- 点位矩阵：`points42.report.json`；
- 并发：`concurrency6.report.json`；
- 故障：`fault_preview.raw.json` 与 `fault_preview.rescored.json`；
- 会话：`session_isolation.json`；
- 聚焦 pytest：91 passed；新增 Python 文件 `py_compile` 通过；
- skill 同步：项目副本与本机全局副本 `file_count=7/identical=true`。

测试前后 8093、8094、8768、8770、5432 和 11434 PID 不变；8093 Git HEAD 始终为
`67d2434cbbb69591ff8e35d4027fd47acfa37850` 且工作树 clean。本轮没有部署生产代码、没有重启
服务、没有修改生产数据库。

## 7. 纯口语追加验证

后续追加了不含标准 ID 的 42 个口语问题，结果为 36 passed、6 failed、0 execution error。失败
全部集中在 `T_top` 派生平均与 `L` 雷达探尺单位/确定性路由，详见
[口语化生产回归交接](./2026-08-14-mcp-spoken-production-regression.md)。因此本文件前述 42/42 只代表
“中文名称（标准 ID）”矩阵，不得外推为纯口语 42/42。
