# 冷风压力与喷煤设定双变量建议引擎迁移交接

日期：2026-08-07（迁移批次需求编号：`REQ-FOREMAN-COLD-BLAST-PRESSURE-20260806`）

## 结论

220.12 的 8768、8094、8093 已完成双变量建议引擎迁移。系统保持只读建议模式，不向设备下发控制指令；现场审批仍是所有 `eligible` 动作的必要条件。

## 现场口径

- “加压/减压”唯一控制变量：`P_blast_cold`，中文名“冷风压力”，单位 kPa。
- `Q_blast`（冷风流量）只作为证据和趋势曲线，不产生可执行调节动作。
- 喷煤唯一控制变量：`PCI_set`，中文名“喷煤设定”，单位 t/h。
- 压力硬下限 400 kPa，加压上限为最新真实 30 天 Q3；不使用固定 460 kPa 限幅。
- 喷煤普通范围 10–45 t/h，严重异常可以生成停煤到 0 t/h 的人工紧急确认候选。

## 数据库迁移

远端数据库：`127.0.0.1:5432/bf_trend`。

`bf_sensor.daily_baselines` 已增加 `p25`、`p75`，并由真实 `one_minute_values` 回填最新窗口：

| 项目 | 值 |
|---|---:|
| 窗口 | 2026-07-08 00:00 – 2026-08-06 23:59 |
| 变量 | P_blast_cold |
| Q1 / p25 | 449.374719 |
| Q3 / p75 | 458.485260 |
| 样本数 | 42,747 |
| 覆盖率 | 0.989514 |

审计表已安装 `recommendation_audit.v2` 扩展字段、不可变触发器和读写角色权限。没有伪造基线行；数据库迁移是兼容性扩展。

## 部署顺序与备份

1. 本机 42 项合同测试、Python 编译、页面 Babel 解析和包级合同通过。
2. 上传 36 文件包：`logs/deployment/8093_8094_recommendation_sync_20260806_r3/recommendation_sync.zip`。
3. 数据库执行 p25/p75 DDL、审计 schema 和真实 30 天回填。
4. 停止/替换/恢复 `BFV4PreviewWs8768`，再用共享 8768 更新 8094 页面并重启 `V3AutoPreviewProxy8094`。
5. 按 8093 守卫“停—部署—恢复”闭环替换页面。

远端备份目录：`F:\高炉炼铁项目-real-sensor-v2_V4_8093_PREVIEW\backups\foreman_dual_control_20260806\20260807_004850`。

## 运行时验收

8768 独立 WebSocket 验收结果：

- `schema_version=foreman_dual_control.v2`
- 8 类炉况，16 条双变量动作
- `adjustable_variables=[P_blast_cold, PCI_set]`
- `evidence_only_variables=[Q_blast]`
- 四种状态均可见：`blocked / eligible / manual_confirm / needs_data`
- `read_only=true`，审批字段保持必需

最终状态：

- 8093 HTTP 200，8094 HTTP 200；两页均有视觉工作台标记、旧前端回退禁用标记和共享 8768 绑定。
- `BFV4PreviewProxy8093=Running`、`BFV4PreviewWs8768=Running`。
- 8768 PID `14628 -> 18288`；8094 PID `16412 -> 1264`。
- 8770、11434 PID 未变化。
- 8093 守卫恢复成功，最终 8093 PID 为 3052。

## 回归命令

```text
python -m pytest tests/test_recommendation_visual_workbench.py tests/test_foreman_dual_control_recommendations.py tests/test_three_rules_recommendation_engine.py tests/test_daily_baseline_quartiles.py tests/test_recommendation_audit_store.py -q
python -m py_compile 自动诊断服务/foreman_dual_control.py 自动诊断服务/local_pg_ws_bridge.py tools/migrate_foreman_pressure_quartiles.py tools/verify_foreman_dual_control_runtime.py
node tools/check_frontend_babel_syntax.js
```

结果：`42 passed`，Python 编译通过，页面 Babel 解析通过。

## 回滚

代码/页面回滚使用上方备份目录；p25/p75 是兼容性字段，不做破坏性删除。若 8768 不可用，页面必须显示 `needs_data`，不得重新启用旧的“调冷风流量”前端启发式建议。
