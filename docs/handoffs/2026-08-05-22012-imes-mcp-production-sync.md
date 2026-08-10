# 220.12 MES/IMES MCP 生产配置同步交接（2026-08-05）

追踪编号：`REQ-22012-IMES-MCP-SYNC-20260805`

## 结果

220.12 原先并非完全没有 MES/IMES MCP，而是只有较早版本的 `gl02-data` 与
`imes-readonly` 两服务注册表。2026-08-05 已将本机统一 MCP 目录按生产网络边界
同步为四服务配置，并只重启 `BFV4PreviewProxy8093`：

| 服务 | 领域 | 生产状态 |
| --- | --- | --- |
| `gl02-data` | 传感器、图表、日报、历史问答、目录 | 已启用 |
| `gl02-extended` | 历史炉况分数、炉身温度 | 已启用 |
| `imes-readonly` | 炉次、铁水、炉渣、进料、MES/IMES | 已启用，220.12 直连只读数据库 |
| `imes-web-readonly` | IMES Web 只读接口 | 已启用；登录仍受账号、密码、验证码/会话约束 |

生产配置使用 `direct_22012`，数据库和 Web 指向 220.12 可达的厂内地址；没有把
本机 `127.0.0.1:15433` 转发配置复制到生产。服务配置只登记 Machine 环境变量名，
没有写入数据库或 Web 密码值。

## 实现与部署

- 生产注册表：[22012_mcp_server_registry.json](../../tools/service_configs/22012_mcp_server_registry.json)
- 服务配置补丁器：[patch_22012_8093_mcp_service_config.py](../../tools/patch_22012_8093_mcp_service_config.py)
- 受控部署器：[remote_guarded_deploy_8093_imes_mcp_sync.ps1](../../tools/remote_guarded_deploy_8093_imes_mcp_sync.ps1)
- 只读结果探针：[remote_probe_8093_imes_mcp_sync_result.ps1](../../tools/remote_probe_8093_imes_mcp_sync_result.ps1)
- MES MCP：[imes_relay_mcp_server.py](../../高炉前端数据/智能助手/mcp/imes_relay_mcp_server.py)
- 315 项语义目录：[imes_full_variable_catalog.json](../../高炉前端数据/智能助手/mcp/imes_full_variable_catalog.json)

远端备份目录：

`F:\高炉炼铁项目-real-sensor-v2_V4_8093_PREVIEW\logs\deploy_backups\8093_imes_mcp_sync_20260805_215323`

部署结果为 `rollback_applied=false`、`task_paused=true`、`task_restored=true`、
`service_restarted=true`、`http_8093=200`。第一次只读预检因 Windows PowerShell 5.1
按无 BOM UTF-8 误解中文路径而在任何生产写入前退出；重新以 UTF-8 BOM 传输脚本后
完成部署。以后含中文远端路径的 Windows PowerShell 5.1 脚本必须保留 BOM。

## 保护边界

| 端口 | 部署前 PID | 部署后 PID | 结果 |
| ---: | ---: | ---: | --- |
| 8093 | 7680 | 14352 | 按授权重启 |
| 8768 | 4340 | 4340 | 未重启 |
| 8094 | 14416 | 14416 | 未重启 |
| 8770 | 12956 | 12956 | 未重启 |

8093 守卫最终为 `Ready`，服务为 `Running`。部署器对七个目标文件逐项校验
SHA-256，任何异常会恢复备份、服务配置和守卫状态。

## 真实业务验收

1. 自动路由口语：`当前属于第几个炉次？上一个炉次铁水的硅含量平均值是多少？`
   - HTTP/SSE 200，事件包含 `tool_start/tool_result/final/done`。
   - 自动选择 `imes-readonly` 的 `imes__get_current_previous_heat_si_summary`。
   - 当前炉次 `2#20260805-072`，上一炉次 `2#20260805-071`。
   - 上一炉 3 个 Si 试样 `0.15、0.30、0.37`，平均 `0.273%`。
   - 总耗时约 `6.69s`。
2. 自动路由口语：`查询炉身13层C点当前温度，请带数据时间。`
   - 自动进入 MCP 工具调用，返回 `T_body_L13_C=89.37`。
   - 数据时间 `2026-08-05 22:06:00`，质量 `Good`。
   - 总耗时约 `22.22s`。

上述两次自动路由请求都没有强制指定服务或工具，证明生产意图路由可以选择新注册
服务。IMES Web 适配器是否能读取需要登录态的业务页面，仍取决于受控验证码或
`IMES_WEB_SESSION_COOKIE`，不能用数据库 MCP 已通过来替代 Web 登录验收。

## 验证命令

```powershell
python -m pytest -q tests\test_22012_imes_mcp_sync_deploy.py tests\test_verify_8093_mcp_mes_sse_once.py 高炉前端数据\智能助手\tests\test_mcp_multi_server_host.py tests\test_imes_relay_mcp_server.py tests\test_imes_mcp_full_variable_templates.py
python tools\verify_8093_mcp_mes_sse_once.py --url http://10.30.220.12:8093/api/qa/chat --timeout 90
python tools\verify_8093_assistant_sse_once.py --url http://10.30.220.12:8093/api/qa/chat --status-url http://10.30.220.12:8093/api/ollama/status --ps-url http://10.30.220.12:11434/api/ps --timeout 90 --auto-mcp-tools --question "查询炉身13层C点当前温度，请带数据时间。"
```
