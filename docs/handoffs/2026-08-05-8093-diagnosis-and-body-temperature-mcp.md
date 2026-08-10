# 8093 历史炉况分数与炉身温度 MCP 扩展

## 需求

- 增加历史炉况分数（包括管道 `channel` 分数）只读查询。
- 恢复炉身温度的口语查询，覆盖 L7–L16、A–H；例如“炉身13层温度”和“C点温度”。

## 当前实现

- 新增 `mcp/bf_data_extended_mcp_server.py`，在旧 GL02 FastMCP 实例上注册：
  - `query_furnace_diagnosis_history`：读取 `bf_sensor.diagnosis_snapshots`，按
    `diagnosis_ts` 去重，支持窗口、时间范围、标签过滤和趋势差值。
  - `query_body_temperature`：按层/方位查询 `T_body_L{7..16}_{A..H}`，支持当前值和历史窗口。
- `bf_data_mcp_server.py` 增加 80 个炉身温度点的运行期目录生成，缺少可选映射文件时仍生成正确的
  `SIO_GL02_BT_T0155..T0234` 与 `\\冀南钢铁\\SIO\\GL02\\BT\\...` 点位合同。
- Host 注册表增加 `gl02-extended`，并在 `domain_router.py` 中把“管道分数/炉况分数/诊断分数”
  路由到诊断服务，把“炉身/炉腹/炉缸温度”路由到扩展服务。默认 GL02 服务和 IMES 服务不受影响。
- 统一目录更新：传感器默认工具包含 `query_body_temperature`；计算目录增加
  `furnace_diagnosis_history` 对象。

## 验证

```powershell
python -m py_compile 高炉前端数据/智能助手/mcp/bf_data_mcp_server.py 高炉前端数据/智能助手/mcp/bf_data_extended_mcp_server.py 高炉前端数据/智能助手/backend/mcp_host/domain_router.py
python -m pytest 高炉前端数据/智能助手/tests/test_mcp_multi_server_host.py -q
```

当前注册表测试为 `12 passed`。完整数据服务测试在本机缺少 `mcp` Python 包时会在导入阶段失败；该环境依赖问题与本次代码语法无关。

使用已配置 MCP Python 环境做了只读实测：`T_body_L13_C` 映射到
`SIO_GL02_BT_T0205` 并返回当前值；L13 A–H 八点和 L7–L16 C 列十点均成功返回。
历史分数工具在最近8小时返回5个诊断点，示例 `channel_score` 为
`10.00、10.00、14.39、21.04、34.57`，同时返回主分数和诊断时间。

## 生产边界

本轮只修改本地代码、注册表、目录和文档，未部署 220.12，未重启 `BFV4PreviewProxy8093`，未改动 8768/8094/8770 或数据库。生产验收应在受控部署后分别测试：

1. “之前一阵的管道分数上升，可能是什么原因？”：工具轨迹包含 `gl02ext__query_furnace_diagnosis_history`，返回时间戳和 `channel_score`。
2. “查一下炉身13层温度”：返回 L13 A–H 当前值及数据时间。
3. “查一下炉身C点温度”：返回 L7–L16 C 点，或在界面明确提示已按 C 列展开。
