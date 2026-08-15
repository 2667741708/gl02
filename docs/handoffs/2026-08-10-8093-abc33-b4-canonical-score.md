# 8093异常弹窗统一ABC33 B4分数交接（2026-08-10）

状态：`deployed`。

## 结果

- 8093异常复核弹窗、手动评分窗口、ABC33当前API和AI解释中的“热制度上行”统一使用B4生产安全分。
- 生产评价批次`839`中，ABC B4与弹窗均为`14.9623`；旧八类诊断分`28.12`保存在`legacy_score_archive`，不再展示。
- B4缺失、陈旧、未来、规则身份错误、超出0～100或缺少目录/配置版本时显示`--`，不回退旧分。
- 未修改ABC33公式/权重/阈值、8768、数据库schema、计划任务或8094。

## 部署证据

- 本地合同：评分/AI/ABC联合`92 passed`，持久SSH/原生构建`24 passed`；JS、Python和PowerShell语法通过。
- v1预检因JS标记字面不一致在互斥/停服前停止，生产未变；v2修正合同后成功。
- 备份：`F:\高炉炼铁项目-real-sensor-v2_V4_8093_PREVIEW\backups\abc33_b4_score_source_8093_20260810_195532`。
- 8093 PID：`2332→14436`；`guard_paused=true`、`guard_restored=true`、`rollback_applied=false`、HTTP 200。
- 受保护PID前后不变：8094=`18628`、8768=`9148`、8770=`3732`、5432=`12372`、8892=`5496`、11434=`5968`。
- 持久SSH保持同一`session_id=e23e3e9d681d42d489b7b607787ecdac`、`connection_id=f928ec393b5f4b4a9722937a159ed871`，请求计数到13、重连0、keepalive 30秒。

## 浏览器边界

本机固定场景85组合完成布局/控件检查，但15项因fixture-only没有WebSocket或附加API返回503而被控制台门禁判失败。生产`--live`矩阵在7分钟上限内未完成，因此不能宣称完整跨浏览器通过。生产API、缓存版本、静态资源和轻量HTTP健康复核均通过。
