# 8093 多 MCP Host 受控部署与真实 MES 验收交接

日期：2026-08-05  
需求：`OPS-8093-MULTI-MCP-HOST-20260805`

## 部署范围

使用 [remote_guarded_deploy_8093_multi_mcp.ps1](../../tools/remote_guarded_deploy_8093_multi_mcp.ps1)
完成“健康任务暂停 → 8093 停止 → 文件备份 → 多 MCP 文件原子替换 → Python 编译 →
8093 启动 → 健康任务恢复 → 端口/哈希验收”。本次没有停止或重启 8768、8094、8770。

部署文件包括：

- `backend/ollama_proxy_server.py`
- `backend/mcp_host/{__init__,server_registry,domain_router,client_manager}.py`
- `backend/mcp_host/server_registry.json`
- `mcp/imes_relay_mcp_server.py`
- `mcp/catalog/heat_analysis.json`

## 受控结果

- 执行时间：`2026-08-05T10:01:52+08:00`
- 备份目录：`F:\高炉炼铁项目-real-sensor-v2_V4_8093_PREVIEW\logs\deploy_backups\8093_multi_mcp_20260805_100117`
- 8093：PID `15352 → 7348`，服务 Running，HTTP `200`
- 8768：PID `15824 → 15824`，保持监听
- 8094：PID `9976 → 9976`，HTTP `200`
- 8770：PID `12956 → 12956`，保持监听
- 健康任务：恢复启用，部署脚本验收 `LastTaskResult=0`
- 新后端 SHA-256：`8F38DA0286791A95722520D7278AE2A37544E3D4EB255D8A5950FC3CAD50EFD0`

## 真实 MES 单次 SSE

验收器：[verify_8093_mcp_mes_sse_once.py](../../tools/verify_8093_mcp_mes_sse_once.py)。
只提交 1 个请求：

```text
当前属于第几个炉次？上一个炉次铁水的硅含量平均值是多少？
```

结果：

- HTTP `200`，事件完整：`start → start → tool_start → tool_result → delta → final → done`
- 路由：`deterministic_imes_query`
- 工具：`imes__get_current_previous_heat_si_summary`
- 服务：`imes-readonly`
- 耗时：约 `2476.5ms`
- 当前正式炉次：`2#20240805-056`
- 上一正式炉次：`2#20240805-055`
- 上一炉有效 Si 试样：`0`
- 返回：`NO_SI_SAMPLES`，Si 平均值为 `null`，明确未将缺失当作 0
- 查询时间：`2026-08-05T10:02:16`

这证明本次问题已经成功进入真实 MES MCP 并完成正式炉次解析；当前没有平均值是
MES 化验数据状态，不是 MCP 路由失败。

## 回滚

备份目录保留部署前全部运行文件。若后续真实数据核对发现合同问题，只允许停止并
回滚 `BFV4PreviewProxy8093`，恢复健康任务后再次核对 8768/8094/8770 PID；不得使用
批量结束 Python 进程，也不得重启 8768。
