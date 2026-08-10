# 8093/8094 炉况调剂建议引擎同步交接（2026-08-06）

## 结果

- 8093 与 8094 页面、共享 8768 WebSocket 桥、`调控结论生成引擎`、前端建议适配器已按本地最新代码同步。
- 两个页面均固定连接 `ws://<host>:8768`；未新建 8769，也未改动或重启 8093/8094 HTTP 服务进程。
- 引擎版本为 `v5-three-rules-two-systems`，运行契约为 `multi_condition_recommendation.v1`，一次返回 8 类炉况方案。
- 每条动作包含原文章节、触发证据、前置条件、阻断原因、调剂幅度、执行顺序、缺失数据、观察窗口、审批要求和执行边界；状态限定为 `eligible / blocked / needs_data / manual_confirm`。

## 部署与回滚

- 操作编号：`OPS-8093-8094-RECOMMENDATION-SYNC-20260806`。
- 发布包：`logs/deployment/8093_8094_recommendation_sync_20260806_r2`，20 个清单文件；ZIP SHA-256 为 `5047FC67809B8D92DA630415E2C347CC1A72543983A4EDECC050FC34FF9C3B2D`。
- 远端备份：`F:\高炉炼铁项目-real-sensor-v2_V4_8093_PREVIEW\backups\8093_8094_recommendation_sync_20260806\20260806_013734`。
- 回滚时恢复该备份内同路径文件并重启 `BFV4PreviewWs8768`；不要重启或覆盖正在独立维护的 8093/8094 HTTP 服务。

## 生产验收

- 8768 PID：`4340 -> 16200`；8093 PID `12368`、8094 PID `14416` 均未变化；8770 与 11434 亦未变化。
- 8093/8094 HTTP 均为 200；8768 初始化消息返回 8 类炉况、只读边界和正确引擎版本。
- 核心引擎 SHA-256：`C492DDD4E9936C190418A4E3C095C479FB643F29B266912F147CA7A312CE1130`。
- 调剂政策 SHA-256：`E3861512FC3A5D99BC58476EACB0B980584D489F3A115017C21DD6FAAC45D34E`。
- 前端适配器 SHA-256：`8DE2064CE31689595E0D7272087B88158F17E4CC67A2B9FE5E968C72E87E7222`。
- 8768 桥 SHA-256：`684339E9237C9C1FBD72EBC818FC0CA4F247C95A46476ABA6386EC28D101657D`。
- 8093 页面 SHA-256：`8E491CAD431D515E6AB98713EFD3ED8204763A84BC6D871D9144DE98AFCA9331`；8094 页面 SHA-256：`396E511978E87348160010EF072F7A55B9CBDA2A31A061AA62B2C060191B64F2`。

## 测试证据

- 规则、组合规则、模型复核与双端同步合同：26 项通过。
- 8093 独立契约检查：8/8 通过。
- Chromium 实页检查确认两页均显示 8 类方案及完整动作审计字段；报告和截图在 `logs/acceptance/8093_8094_recommendation_probe_20260806`。

