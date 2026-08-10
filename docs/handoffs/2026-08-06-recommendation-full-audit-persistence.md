# 建议引擎完整逐条全字段审计入库

追踪编号：`REQ-RECOMMENDATION-FULL-AUDIT-20260806`

## 目标

把8093/8094共用建议流中的八类炉况建议按“一个诊断快照一个不可变批次、一个动作一行”写入220.12 PostgreSQL。数据库必须同时保留完整原始 `recommendation_bundle` 与可查询动作列；`eligible`、`blocked`、`needs_data`、`manual_confirm` 四种状态全部保留。入库只形成建议审计证据，不授予生产控制权限。

## 数据模型

- `bf_assistant.recommendation_audit_batches`：保存诊断输入、当前核心变量、数据质量、引擎/策略版本、输入和输出哈希、状态计数以及完整原始建议矩阵。
- `bf_assistant.recommendation_audit_actions`：按炉况和动作拆行，保存原文章节、完整触发证据、必需输入、前置条件、阻断原因、幅度、顺序、缺失数据、观察窗口、审批要求和完整 `action_payload`。
- `bf_assistant.recommendation_audit_action_detail`：面向只读审计的联接视图。
- `bf_assistant.recommendation_audit_schema_versions`：记录已安装审计schema版本。

批次幂等键由炉号、诊断快照ID/时间、建议引擎名称、引擎版本和策略文件SHA-256构成。同一诊断和同一策略的首次提交成为不可变审计版本；重复页面初始化或刷新返回同一批次，不能覆盖原记录。引擎版本或策略哈希变化时自动形成新版本。

## 运行链路

1. 8768从 `bf_sensor.diagnosis_snapshots` 读取当前诊断及核心变量。
2. `recommendation_adapter.generate_recommendation_bundle()` 生成八炉况完整建议矩阵，并附加策略文件SHA-256。
3. `recommendation_audit_store.persist_recommendation_bundle()` 校验八炉况、四状态及所有强制字段。
4. 事务内先写不可变批次，再写全部动作，并复核实际动作行数。
5. 数据库冲突时读取首次已提交的完整建议包并返回页面，保证页面显示与审计库一致。
6. 审计启用但写入失败时，8768不返回未审计建议，`recommendation_status.reason=full_audit_persistence_required`。

## 权限边界

- 迁移由220.12数据库管理员在服务器回环地址执行。
- 运行账号 `gl02_sync` 只获得新表的 `SELECT/INSERT` 与序列 `USAGE/SELECT`，明确撤销 `UPDATE/DELETE/TRUNCATE/REFERENCES/TRIGGER`。
- 外部账号 `gl02_reader` 只获得新表和视图的 `SELECT`。
- 所有批次、炉况和动作固定 `read_only=true`；本功能没有下发PLC/DCS、修改设定值或执行调剂动作的代码。

## 程序与迁移入口

- [完整审计写入器](../../自动诊断服务/recommendation_audit_store.py)
- [数据库DDL](../../自动诊断服务/recommendation_audit_schema.sql)
- [建议适配器](../../自动诊断服务/recommendation_adapter.py)
- [8768实时桥接](../../自动诊断服务/local_pg_ws_bridge.py)
- [受控迁移](../../tools/migrate_recommendation_audit.py)
- [运行验收](../../tools/verify_recommendation_audit_runtime.py)
- [部署包构建](../../tools/build_recommendation_audit_deploy.py)
- [220.12受控部署](../../tools/remote_guarded_deploy_recommendation_audit.ps1)

## 本地验收

```powershell
python -m unittest tests.test_recommendation_audit_store -v
python -m unittest tests.test_three_rules_recommendation_engine tests.test_multi_condition_recommendation_and_model_review tests.test_recommendation_audit_store -v
python -m py_compile "自动诊断服务\recommendation_audit_store.py" "自动诊断服务\recommendation_adapter.py" "自动诊断服务\local_pg_ws_bridge.py" "tools\migrate_recommendation_audit.py" "tools\verify_recommendation_audit_runtime.py"
powershell.exe -NoProfile -ExecutionPolicy Bypass -File ".\tools\check_ps1_syntax.ps1" -Path ".\tools\remote_guarded_deploy_recommendation_audit.ps1"
```

2026-08-06本地结果：新增7项审计合同测试通过；与三规二制建议、多炉况合同合并后26项通过。真实测试夹具生成8类炉况、35条动作，完整字段校验通过；部署脚本通过PowerShell解析器。

## 220.12部署状态

2026-08-06首次部署前置检查被本机网络路径阻断：`10.30.220.12:22`连接超时，路由表没有 `10.30.220.12`路由，Sangfor aTrust VNIC虽存在但未建立系统路由。部署包尚未上传，数据库迁移、文件替换和服务重启均未发生。恢复SSLVPN系统隧道后，从“只读服务检查”步骤继续，不得把应用代理浏览器可访问误当成PowerShell/SSH系统路由已经恢复。
