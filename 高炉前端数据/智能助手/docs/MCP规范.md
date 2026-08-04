# MCP规范：GL02真实数采链路与Ollama工具调用

## 1. 强制生产链路

本项目的本地大模型本体部署在 `10.30.220.12`，GL02真实数采默认从备份数采服务器 `10.22.181.243:8889` 只读获取。以后凡是前端对话框、8092智能助手、Ollama模型、MCP工具组合查询GL02真实传感器数据，必须优先使用以下链路：

```text
用户浏览器
  -> 10.30.220.12:8092 前端/QA接口
  -> 10.30.220.12:11434 Ollama chiqiong-blast-furnace:latest
  -> MCP工具选择与调用
  -> 10.30.220.12 本机 PythonSDK
  -> 10.22.181.243:8889 pSpace备份数采
  -> 返回变量元数据、实时值、历史值、统计特征
```

不得默认让用户本机直连 `10.22.181.243:8889` 作为生产方案。用户本机可通过 `10.30.220.12` 做SSH跳板执行只读验证命令。

## 2. 数据源优先级

- 生产真实数据：`BF_MCP_DATA_SOURCE=pspace_243`。
- 本地开发回放：`BF_MCP_DATA_SOURCE=storage` 或默认SQLite。
- 若回答真实生产问题，模型回答必须说明数据来源是 `pspace_243` 或 `dev_sqlite`，不能混淆。

## 3. 安全边界

- 只访问 `10.22.181.243` 备份数采；没有明确授权不得访问或修改 `10.22.181.244` 主数采。
- 只读调用 `RealReadList`、`HisReadProcessed`、`QueryTag`、`GetTagProps` 等读取接口。
- 不暴露 pSpace账号密码、SSH密码、数据库DSN。
- 不允许模型生成任意SQL或任意pSpace路径扫描命令。
- GL02根路径强制为 `\冀南钢铁\SIO\GL02`，不得默认混用 `\冀南二期\EQ\SI0\GL02`。

## 4. MCP返回字段强制项

GL02变量、实时值、历史值、统计工具必须返回：

```text
variable_name
short_name
point_id
tag_long_name/tag
description
unit
path_group
status
confidence
max_history_range
notes
source.profile
source.read_policy
```

真实243链路的 `source.profile` 应为：

```text
pspace_243 或 pspace_243_via_22012
```

## 5. 流式体验强制项

前端与Ollama应尽量端到端流式输出。若MCP工具调用阶段无法真实流式，后端必须尽快给前端发送进度事件，例如：

```text
正在识别变量...
正在通过220.12访问243数采...
已获得数据，正在生成回答...
```

不得让用户长时间只看到“生成中”。

## 6. 本地通过220.12跳板查询243的标准命令

实时值：

```powershell
python ".\高炉前端数据\智能助手\mcp\gl02_remote_22012_pspace_query.py" latest --variable "T_blast" --allow-agents-password
```

历史数据：

```powershell
python ".\高炉前端数据\智能助手\mcp\gl02_remote_22012_pspace_query.py" history --variable "T_blast" --start "2026-05-01T00:00:00+08:00" --end "2026-05-08T18:24:00+08:00" --limit 20 --allow-agents-password
```

统计特征：

```powershell
python ".\高炉前端数据\智能助手\mcp\gl02_remote_22012_pspace_query.py" stats --variable "T_blast" --start "2026-05-01T00:00:00+08:00" --end "2026-05-08T18:24:00+08:00" --agg avg --allow-agents-password
```

## 7. 220.12本机终端查询243的标准方式

在 `10.30.220.12` 上执行：

```powershell
Set-Location "F:\高炉炼铁项目-real-sensor-v2_V3"
$env:BF_MCP_DATA_SOURCE = "pspace_243"
$env:PSPACE_SDK_ROOT = "F:\高炉炼铁项目-real-sensor-v2_V3\pythonSDK(1)"
$env:PSPACE_CONFIG = "F:\高炉炼铁项目-real-sensor-v2_V3\ghsc\src\main\resources\application-prod.yml"
$env:PSPACE_SERVER = "10.22.181.243"
$env:PSPACE_PORT = "8889"
```

然后执行MCP查询脚本：

```powershell
python ".\高炉前端数据\智能助手\mcp\gl02_mcp_python_sdk_query.py" latest --variable "T_blast"
```

如果仅使用原始采集脚本，可执行：

```powershell
python .\tools\pspace_collect_gl01_5d.py `
  --sdk-root ".\pythonSDK(1)" `
  --pspace-config ".\ghsc\src\main\resources\application-prod.yml" `
  --pspace-server 10.22.181.243 `
  --pspace-port 8889 `
  --scope GL02 `
  --root-path "\冀南钢铁\SIO\GL02" `
  --tag "\冀南钢铁\SIO\GL02\BT\SIO_GL02_BT_T0006" `
  --days 0.0069444444 `
  --interval-seconds 60 `
  --aggregate PS_HIS_AVERAGE `
  --split-mode per-tag `
  --batch-size 1 `
  --out-dir ".\高炉传感器数据\GL02_243_demo_T_blast"
```

## 8. 已验证结果

2026-05-09 已通过本机脚本化SSH访问 `10.30.220.12`，并由 `220.12` 使用 PythonSDK 只读访问 `10.22.181.243:8889`，成功采集 GL02热风温度。

```text
点位：\冀南钢铁\SIO\GL02\BT\SIO_GL02_BT_T0006
描述：2号炉本体_热风温度
采集窗口：2026-05-09 08:07:14 到 2026-05-09 08:17:14
行数：10
质量：Good(CALCULATED)
样例值：1242.8385413333333, 1241.007507, 1238.914225
```

同日还通过跳板脚本读取实时值成功：

```text
变量：T_blast
时间：2026-05-09 08:28:35.555
实时值：1187.01171875
质量：Good
来源：pspace_243_via_22012
```

## 9. 配套测试集

详见：`GL02_MCP_22012跳板真实数采测试集_100条.md`。

