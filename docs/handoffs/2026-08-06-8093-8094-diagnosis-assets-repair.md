# 8093/8094 诊断资源一致性修复与正式部署

## 结论

2026-08-06 已使用本机 `reliable_ssh` 一键部署器，把本机新版的异常弹窗、免登录人工评分、八卡手动评分、单炉况核心变量证据分析和建议复盘接口同步到 220.12 的 8093、8094。

本次故障的直接原因是：远端页面在 `</head>` 前注入诊断脚本，而远端旧脚本在 `document.body` 尚未创建时直接执行；新版脚本通过 `bootWhenBodyReady` 延后挂载，因此资源同步后可正常显示。后端配置、共享代理诊断块和评分 API 不是本次不可用的主要原因。

## 发布收据

- 本机门禁：`python .\tools\deploy_diag_rules.py`，`47 passed`，dry-run通过。
- 正式命令：`python .\tools\deploy_diag_rules.py --apply --verify fast`。
- 部署编号：`diag_rules_20260806-2300-4b75678a08`。
- 资产版本：`diag-20260806-2300-4b75678a08`。
- 本地收据：[logs/deploy_diag_rules/diag_rules_20260806-2300-4b75678a08.json](../../logs/deploy_diag_rules/diag_rules_20260806-2300-4b75678a08.json)。
- 远端备份：`F:\高炉炼铁项目-real-sensor-v2_V4_8093_PREVIEW\logs\deploy_backups\diag_rules_20260806-2300-4b75678a08`。
- 远端回执：`guardPaused=true`、`guardRestored=true`、`rollbackApplied=false`。

## 发布范围

原子包包含9个白名单业务文件：共享代理诊断块、4个诊断后端模块、评分/复核两个JavaScript和两个CSS。代理以远端当前版本为基线合并，保留已有跨数据库MCP代码。

只更新/重启：`BFV4PreviewProxy8093`、`V3AutoPreviewProxy8094`。没有更新8768规则引擎、8770或11434。

## 远端验收

- 8093页面HTTP 200，长度887011；8094页面HTTP 200，长度872600。
- 两端页面均命中本次资产版本；复核和手动评分脚本均HTTP 200，且包含 `bootWhenBodyReady`。
- 两端 `/api/diagnosis-review-context` 均返回 `enabled=true`、`can_submit=true`、`login_required=false`，当前免登录现场身份模式可用。
- 8093/8094页面服务按目标更新了PID；8768 PID `4288`、8770 PID `6848`、11434 PID `12456` 前后保持不变。

## 已知验收边界

本机浏览器连接初始化阶段遇到 Windows ACL 运行环境错误而退出，因此没有把浏览器截图或控制台结果写成“通过”。本轮结论以远端实际HTTP、脚本内容、API和PID验收为准；待本机浏览器环境恢复后，再补做完整视口矩阵。

