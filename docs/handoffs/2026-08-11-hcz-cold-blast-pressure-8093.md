# 2026-08-11 HCZ冷风风压口径8093生产交接

追踪编号：`REQ-HCZ-COLD-BLAST-PRESSURE-20260811`

## 结果

HCZ上移经验规则第五项已从热风压力改为冷风风压。显示名为“冷风风压”，实际数据源由`P_blast`切换为`P_blast_cold`，方向和阈值保持`increase / +5kPa`。本次没有修改其他四项指标、炉壁层数、连续12小时门、安全合同、数据库或API路径。

## 生产验收

- 页面：`http://10.30.220.12:8093/hcz_upward_rule.html`
- API标签：`冷风风压`
- 配置变量：`P_blast_cold`
- 部署时实测变化：`+0.589619kPa`
- 阈值：`+5kPa`
- 当前状态：`not_triggered`
- 最新样本：`2026-08-11 11:09:00`
- 生产Edge：5项指标、7层炉壁、3个规则门齐全，横向溢出0，页面/控制台/HTTP错误0。

## 受控部署证据

- 准备清单：`bf.deploy.prepared-release.v1`，封印`1D46C47377064832A30166898C38E3F4183EB8AAFB2CC40B5147783EAB002246`。
- 增量：仅[HCZ规则配置](../../炉况规则引擎/config/hcz_upward_expert_rule.yaml)，安装SHA-256为`E91A22D114C934B2C6B18C7A71629B4112636D173278D8CD521FA05ECE7A87F1`。
- 备份：`F:\高炉炼铁项目-real-sensor-v2_V4_8093_PREVIEW\backups\hcz_cold_blast_pressure_8093_20260811_111023`。
- `guard_paused=true`、`guard_restored=true`、`rollback_applied=false`。
- 8093 PID：`6528 -> 3704`。
- 受保护PID前后不变：8094=`18628`、8768=`404`、8770=`3732`、5432=`12372`、8892=`5496`、11434=`5968`。
- 持久SSH会话和连接标识在预检、预暂存、部署及后检之间保持一致；会话部署后继续保留。

## 本地验收

- `pytest tests/test_hcz_upward_expert_rule.py tests/test_hcz_upward_rule_api.py -q -p no:cacheprovider`：`10 passed`。
- Ruff：通过。
- JavaScript和PowerShell语法：通过。
- 本地跨引擎页面：17/17通过，并锁定“冷风风压”且不出现“热风压力”。
- PowerShell 7.6.4 Core与UTF-8运行检查：通过。

## 实现入口

- [配置](../../炉况规则引擎/config/hcz_upward_expert_rule.yaml)
- [规则测试](../../tests/test_hcz_upward_expert_rule.py)
- [API合同测试](../../tests/test_hcz_upward_rule_api.py)
- [只读生产预检](../../tools/remote_probe_hcz_cold_blast_pressure_8093.ps1)
- [本机差量部署入口](../../tools/deploy_hcz_cold_blast_pressure_22012.ps1)
- [远端守卫部署器](../../tools/remote_guarded_deploy_hcz_cold_blast_pressure_8093.ps1)

历史三个月报告中的压力数值来自旧变量`P_blast`，已明确标为旧口径；如需按新冷风风压口径重算历史上下移，必须重新回放`P_blast_cold`，不能只改报告名称。
