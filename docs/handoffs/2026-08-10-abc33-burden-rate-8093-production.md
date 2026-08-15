# ABC33料批速度规则8093生产交接（2026-08-10）

## 结果

- 状态：`deployed`。
- 需求：`REQ-ABC33-HEAT-BATCH-RATE-CRITERION-20260810`。
- A2第一项：`20×BurdenRateDev`。
- B4第一项：`20×BurdenRateSlow`。
- B5第一项：`20×BurdenRateFast`。
- 其余原有项按0.8重平衡为80，三条规则总权重均为100。

## 数据与页面

- 原始源：`bf_imes.raw_rows`，`source_dataset=bf2_batch_input_detail_list_page_data2`。
- 大批语义：相邻矿批之间完成煤矿组合的完整周期；不使用作业日志汇报批数冒充料速。
- 页面显示：前后30分钟、昨日平均、滚动24小时、连续2小时和自然语言变化；料速位于A2/B4/B5“最重要复核点”首位。
- 安全合同：公共接口不返回公式项贡献、归一化值和精确阈值；缺失和过期返回不可用，不补0。

## 部署证据

- 本地：`119 passed`；Python语法、ABC配置、PowerShell 7脚本解析通过。
- 8093：备份`F:\高炉炼铁项目-real-sensor-v2_V4_8093_PREVIEW\backups\abc33_burden_rate_8093_20260810_180833`；`guard_paused=true`、`guard_restored=true`、`rollback_applied=false`；PID `19268→2332`；HTTP 200。
- 8768：PID `3684→8680`；33条规则、33条分数可用、33条数据完整；`eligible=27`、`manual_confirm=6`、`needs_data=0`。
- 隔离：8094、8770、5432、8892、11434在相应阶段PID未变化；8093在8768阶段PID未变化。
- SSH：同一`session_id`和`connection_id`完成暂存、8093部署、8768重启；`reconnect_count=0`，代理继续保留。

## 浏览器验收

- URL：`http://10.30.220.12:8093/?cb=abc33-burden-rate-20260810-final2#optimization`。
- A2/B4/B5详情均显示料速及完整窗口语义，详情和页面无横向溢出。
- 截图：`reports/abc33_burden_rate_8093_A2_20260810.png`（本机忽略目录）。
- 控制台：无运行时异常；存在1条既有Babel大内联脚本代码生成降级提示，未影响页面、API或本次功能。
