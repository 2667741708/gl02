# 8093 任意炉次化验与模型受控自主调用交接

## 上线结果

- 新 MCP 工具：`imes__query_heat_chemistry`。
- 支持炉次引用：正式 `meltno`、`YYYYMMDD-NNN`、72小时内唯一的2–4位短炉号。
- 支持成分：C、Si、Mn、P、S、Ti、V、Cr、Cu、Ni、As。
- 返回：正式炉次号、每个试样、取样/发布/判定时间、成分均值/最小/最大/最新、单位、来源和缺失原因。
- 数据库和工具保持只读；`query_imes_readonly_sql` 继续在生产注册表中排除。

## 模型自主调用证据

生产问题：`请查询2#20260805-065炉次的C、Si、Mn、P、S，并列出每个试样。`

模型实际生成的安全结构化调用：

```json
{
  "route": "model_planner",
  "server_id": "imes-readonly",
  "tool": "imes__query_heat_chemistry",
  "arguments": {
    "heat_reference": "2#20260805-065",
    "components": ["C", "Si", "Mn", "P", "S"],
    "include_samples": true
  }
}
```

调用结果：`ok=true`，共3个试样；模型未调用目录、未生成SQL、未重复调用工具，运行前后模型状态均为正常。生产返回的Si试样值为0.24%、0.25%、0.20%。

## 部署与恢复

- 最终发布包哈希：
  - `ollama_proxy_server.py`: `381516CB59B1C005844E3D1D322C96820194045B04D3AC1F35D71BDB88629509`
  - `imes_relay_mcp_server.py`: `ACCD9588DF61C9BDCA003E4DA6D93ABEB051ECBF49CCE5123F392CE0D410E7DC`
  - `heat_analysis.json`: `29AF8843176CD6FA1B4EB0C8B2ABE50C6F6009F94D3D3D35C7BE1372E1005BA8`
- 最终备份：`F:\高炉炼铁项目-real-sensor-v2_V4_8093_PREVIEW\logs\deploy_backups\8093_heat_chemistry_20260806_102321`。
- 部署过程中首次遇到SSH会话超时和半回滚，已通过生产文件差异核对确认代理只差本次127行最小改动；随后重新完整发布并执行干净的仅8093恢复。
- 恢复结果：`BFV4PreviewProxy8093=Running`、8093健康HTTP 200、守护任务为`Ready`；最终8093/8768/8094/8770四端口均可连接。
- 部署窗口内观察到8768/8094/8770 PID发生外部并发变化，因此本次不能宣称三个PID全程未变化；能够确认最终均正常监听，本次恢复脚本只操作8093。

## 性能口径

本机只规划测试约19秒；生产完整问答约40秒。耗时主要来自27B模型生成工具调用，不是MCP数据库查询。高频当前值仍保留确定性快速路由；只有指定炉次和复杂语义进入模型规划。

