# 2026-08-11 HCZ经验阈值敏感性试算8093生产交接

追踪编号：`REQ-HCZ-RULE-SENSITIVITY-20260811`  
生产入口：`http://10.30.220.12:8093/hcz_upward_rule.html`

## 交付结果

- 页面可临时调整八项经验阈值，并选择最近7、30或90天真实历史进行只读回放。
- 同屏比较生产默认与试算场景的上移事件、命中小时、符号对称下移候选及新增/移除时刻。
- `GasUtil`由数据库0～1比例在API入口乘100一次；当前值和基线显示`%`，差值与阈值显示“个百分点”。
- 所有试算参数不保存、不写库、不改变YAML，禁止自动控制。下移仅为研究候选。

## 生产实测

2026-08-11 17:47部署后，近90天真实数据范围为2026-05-13 18:00至2026-08-11 17:00。把平均顶温阈值从15℃降至10℃：

| 口径 | 生产默认 | 试算场景 |
|---|---:|---:|
| 上移事件 | 0 | 0 |
| 对称下移候选事件 | 0 | 0 |

现场页面显示煤气利用率约`45.83%`，前5天基线约`46.38%`，变化约`-0.55个百分点`。当前规则状态为`not_triggered`。

## 验证证据

- `pytest`专项：15项通过。
- Ruff、Python编译检查、JavaScript语法检查：通过。
- 本地标准UI矩阵：Chromium九视口、Firefox/WebKit各四个代表视口，共17/17通过。
- 生产Edge冒烟：`1366×768`和`390×844`均通过；横向溢出0、控制台错误0、接口错误0。
- 受控部署：备份目录`F:\高炉炼铁项目-real-sensor-v2_V4_8093_PREVIEW\backups\hcz_rule_sensitivity_8093_20260811_174722`；8093 PID `12524→5052`；`guard_paused=true`、`guard_restored=true`、`rollback_applied=false`、HTTP 200。
- 受保护PID前后不变：8094=`17432`、8768=`5628`、8770=`3732`、5432=`12372`、8892=`5496`、11434=`16232`。

生产浏览器报告与截图位于`logs/hcz_rule_sensitivity_20260811/remote_22012/`。

## 运维入口

- 发布准备：[prepare_hcz_rule_sensitivity_8093_release.ps1](../../tools/prepare_hcz_rule_sensitivity_8093_release.ps1)
- 本机部署：[deploy_hcz_rule_sensitivity_22012.ps1](../../tools/deploy_hcz_rule_sensitivity_22012.ps1)
- 远端守卫部署：[remote_guarded_deploy_hcz_rule_sensitivity_8093.ps1](../../tools/remote_guarded_deploy_hcz_rule_sensitivity_8093.ps1)
- 生产UI复验：[verify_hcz_upward_rule_remote_ui.cjs](../../tools/verify_hcz_upward_rule_remote_ui.cjs)
