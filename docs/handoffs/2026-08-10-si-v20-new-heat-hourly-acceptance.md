# V20新炉次每小时持续验收交接

## 目标

以`2#20260810-130`为冻结基线，每小时检查220.12本地IMES镜像、炉次质量汇总、V20页面、可调定时预测和严格整点预测。出现更晚炉次并完成实际Si与预测关联后，生成最终验收报告并暂停心跳。

## 入口与证据

- 验收程序：[audit_si_v20_new_heat_acceptance.cjs](../../tools/audit_si_v20_new_heat_acceptance.cjs)
- 远端探针：[remote_probe_si_v20_acceptance.ps1](../../tools/remote_probe_si_v20_acceptance.ps1)
- 报告：[acceptance_report.md](../../reports/acceptance/SI_V20_NEW_HEAT_20260810/acceptance_report.md)
- HTML报告：[acceptance_report.html](../../reports/acceptance/SI_V20_NEW_HEAT_20260810/acceptance_report.html)
- 自动化：`220-12-v20`，名称`220.12 V20新炉次每小时验收`，每小时运行。

## 第0次验收

- 基线实际炉次：`2#20260810-130`，开口`2026-08-10 00:28:00`，平均Si`0.470%`，样本数1。
- 候选炉次：131、132、133；均为220.12本地镜像中的MES占位，尚无正式开口时间。
- 页面：8093加载正常、每60秒刷新、无页面错误、无横向溢出；预测曲线和实际Si曲线CSV按钮均完成真实下载。
- 服务：8093、8094、8768、8770、5432均监听；PowerShell为`7.6.4 Core`；HeatPerformanceQualitySync、StrictHourly、ScheduledShadow最近任务结果为0。
- 异常：严格整点03:00槽为`failed_retryable`，报错`can't subtract offset-naive and offset-aware datetimes`。该问题不影响页面和可调60分钟任务读取，但阻止严格整点门禁通过，必须继续监督，不得签署最终通过。

## 完成门禁

新实际炉次必须严格晚于130，同时出现在status/history、不再作为未开口候选、存在预测关联；页面截图和CSV下载有效；严格整点槽恢复健康且无重复/缺口/截止违规。新炉已开口但尚无Si时继续等待。

## 第1次验收（2026-08-10 04:10）

- 最新实际炉次仍为`2#20260810-130`；尚无严格晚于基线的新实际Si。
- 131、132、133占位镜像时间更新为`04:10:25`，说明本地IMES镜像仍在刷新，但三炉仍无MES正式开口时间。
- 可调60分钟任务已成功生成04:00时间槽，下一槽为05:00；页面显示86条预测、无页面错误、无横向溢出，两个CSV再次成功下载。
- 严格04:00槽为`failed_retryable`，第6次尝试仍报`can't subtract offset-naive and offset-aware datetimes`；任务最近结果为1。
- 数据库累计4个严格整点槽：成功1、可重试3、重复0、非整点0、截止违规0。该故障已连续影响03:00与04:00，不是偶发波动。
- 8093、8094、8768、8770、5432均监听；HeatPerformanceQualitySync与ScheduledShadow任务最近结果0。8768监听PID由上次`1192`变为`18420`，表明期间服务进程发生过重建，但当前端口和页面仍健康；后续继续观察是否反复变化。验收保持未通过，自动化继续运行。

## 安全边界

当前自动化只读生产数据，不重启服务、不修改计划任务、不手工补跑预测、不改变控制值。异常修复需要独立授权。
