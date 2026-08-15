# 2026-08-10 HCZ上移经验规则8093生产交接

> 历史口径说明：本次交接记录的是2026-08-10首版部署，当时第五项使用热风压力`P_blast`。2026-08-11高炉长明确要求改为冷风风压，当前规则以`P_blast_cold`为准；下列旧压力数值只作当时部署证据。

## 交付结果

高炉长提供的“顶温、压差、透气性、煤气利用、风压、7～13层炉壁温度、连续12小时”经验公式已固化为单一严格AND规则，并部署到220.12的8093只读工作台。

- 页面：`http://10.30.220.12:8093/hcz_upward_rule.html`
- API：`GET http://10.30.220.12:8093/api/hcz-upward-rule`
- 规则：`HCZ-UP-FOREMAN-001`
- 证据类型：`expert_rule_indication`
- 自动控制：`prohibited`
- 数据库变更：无；API只读`bf_sensor`分钟实测。

规则全文见[GL02软熔带上移综合趋势经验规则](../GL02软熔带上移综合趋势经验规则_20260810.md)。

## 生产实测结果

最终复验时最新样本为`2026-08-10 13:20:00`，评价小时为`13:00`，数据覆盖充足，结论为`not_triggered`：

| 条件 | 24小时较前5天变化 | 阈值 | 结果 |
|---|---:|---:|---|
| 平均顶温 | -2.589829 ℃ | >= +15 ℃ | 未通过 |
| 全压差 | +2.988057 kPa | >= +5 kPa | 未通过 |
| 透气性指数 | -0.035440 | <= -0.5 | 未通过 |
| 煤气利用率 | -0.002003个百分点 | <= -1个百分点 | 未通过 |
| 热风压力 | +3.083382 kPa | >= +5 kPa | 未通过 |

炉壁上升层为空，最大连续合格小时为0。此状态只表示当前没有达到完整上移经验组合，不能反推“稳定”或“下移”。

## 部署证据

- 使用[本机部署入口](../../tools/deploy_hcz_upward_rule_22012.ps1)上传，再由[远端守卫脚本](../../tools/remote_guarded_deploy_hcz_upward_rule_8093.ps1)执行备份、停止8093、原子替换、恢复与验收。
- `BFV4PreviewProxy8093`旧PID `12616`，新PID `15224`；`guard_paused=true`、`guard_restored=true`。
- 受保护PID前后不变：8094=`2988`、8768=`18436`、8770=`3732`、5432=`12372`、8892=`5496`。
- 8094和8892受保护HTTP均为200。
- 最终备份：`F:\高炉炼铁项目-real-sensor-v2_V4_8093_PREVIEW\backups\hcz_upward_rule_8093_20260810_132053`。
- 本机部署日志：`.tmp/hcz_upward_rule_deploy_20260810_r3/stdout.log`。

## 验收证据

- `pytest tests/test_hcz_upward_expert_rule.py tests/test_hcz_upward_rule_api.py -q`：9项通过。
- Ruff、Python语法、JavaScript语法、两个PowerShell部署脚本语法均通过。
- `tools/verify_pwsh7_utf8.ps1`：PowerShell 7.6.4 Core和UTF-8通过。
- 本地UI：Chromium 9个固定视口，Firefox和WebKit各4个代表视口，共17/17通过。
- 生产Edge：1366×768，5项指标、7层炉壁、3个规则门均显示；横向溢出0；页面/控制台错误0；API安全字段通过。
- 生产截图：[edge_1366x768.png](../../logs/hcz_upward_rule_20260810/remote_22012/edge_1366x768.png)，报告：[report.json](../../logs/hcz_upward_rule_20260810/remote_22012/report.json)。

## 运行与回滚

8093请求时从本地PostgreSQL只读聚合144小时数据，进程内缓存120秒。没有新增计划任务、表或写接口。配置或公式变更后必须重新运行专项测试和17视口矩阵，再走同一8093守卫闭环部署；回滚使用上述备份恢复七个目标文件并恢复`BFV4PreviewProxy8093`，仍需核对全部受保护PID和HTTP。
