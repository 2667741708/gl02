# 8093 跨源 MCP Host 部署交接（2026-08-06）

## 结论

8093 跨数据库 MCP 修复已通过受控部署上线。确定性编排现在可在一个问题中并行调度 MES 与 GL02/pSpace；炉身温度使用 `gl02-extended` 能力，`P_top` 保持在 `gl02-data` 传感器工具；事实输出带值、单位、数据时间、来源和缺失状态。

## 本地验证

- `tests/test_cross_source_mcp.py`：`51 passed`，`0` 个 `pass # placeholder`。
- MCP Host、IMES 同步、会话上下文、延迟和守护相关组合：`108 passed`。
- 代理、跨源计划、执行器、领域路由、IMES relay、配置补丁 `py_compile`：通过。

## 生产验收

审计入口为 `tools/audit_8093_cross_database_mcp.py`，均使用自动路由单次 SSE：

1. “当前属于第几个炉次？上一炉铁水的硅含量平均值是多少？”调用 `imes-readonly`，返回正式当前/上一炉 `meltno`；无有效 Si 试样时返回 `NO_SI_SAMPLES`，没有把缺失当作0。
2. “当前炉顶压力是多少？”调用 `gl02-data/query_gl02_sensors`，返回最新值和数据时间。
3. “画最近一小时炉顶压力趋势图”调用 `plot_gl02_trends`，返回 `/data/mcp_charts/gl02_line_*.png`。
4. “上一炉 Si 平均值 + 当前顶压、冷风压力和富氧率”同时调用 `imes-readonly` 与 `gl02-data`，两个服务各执行一次；当前传感器使用 `query_type=latest`。
5. `2#20260805-065` 化验 + `13层C点` + 顶压同时调用 IMES、`gl02-extended/gl02ext__query_body_temperature`、`gl02-data/query_gl02_sensors`；化验返回3条真实 Si 样本。无炉身点位采样时明确列为缺失。
6. “7–12层 A–F 炉身温度矩阵”调用矩阵图工具并返回 PNG 地址；真实矩阵耗时约48秒，属于展示型步骤，未阻塞事实路由。

## 部署隔离

- 备份：`F:\高炉炼铁项目-real-sensor-v2_V4_8093_PREVIEW\logs\deploy_backups\8093_multi_mcp_20260806_012857`。
- 最终 8093 PID：`12368`；部署前 `17936`。
- 8768 PID `4340`、8094 PID `14416`、8770 PID `12956`，部署前后保持不变。
- `BFV4PreviewProxy8093=Running`，健康守护任务恢复且 `LastTaskResult=0`；8093/8094 HTTP 200。
- `/api/qa/mcp/health` 返回 `ok=true`，注册表四服务、跨源模块和统一目录均存在。

## 回滚

优先使用上述备份目录，由 `remote_guarded_deploy_8093_multi_mcp.ps1` 的失败路径恢复文件和服务配置；回滚只重启 `BFV4PreviewProxy8093`，不得操作 8768、8094、8770、数据库或243采集服务。
