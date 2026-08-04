# MCP 查询示例与远端测试记录

确认日期：2026-05-08

## 1. 测试结论

已在 `10.30.220.12` 服务器实际运行目录中完成 MCP 查询测试。

远端信息：

- 项目目录：`F:\高炉炼铁项目-real-sensor-v2_V3`
- MCP 目录：`F:\高炉炼铁项目-real-sensor-v2_V3\高炉前端数据\智能助手\mcp`
- Python：`C:\Program Files\Python311\python.exe`
- Python 版本：`3.11.9`
- MCP 包：已安装
- `FastMCP`：可导入
- GL02 1min SQLite：`F:\高炉炼铁项目-real-sensor-v2_V3\趋势分析\trend_backend\data\gl02_1min.sqlite3`

测试结果：

```text
测试总数：50
通过：50
失败：0
```

覆盖范围：

- 最新值查询
- 变量名查询
- 短名查询
- 中文模糊名查询
- 派生变量 `T_top` 查询
- 具体炉体温度层位查询
- 历史曲线查询
- 统计查询：`avg`、`min`、`max`、`count`、`first`、`last`、`all`
- 无时区时间查询
- `limit` 超大 / `limit` 非数字
- 缺失变量拒绝
- 反向时间窗拒绝
- 非法聚合拒绝
- 报表路径穿越拒绝
- 日报读取
- 历史问答检索

## 2. MCP 工具速查

| 目的 | 工具 |
|---|---|
| 查当前/最新值 | `get_latest_gl02_value` |
| 查变量信息、点位、描述 | `get_gl02_variable_info` |
| 按关键词找变量 | `find_gl02_variables` |
| 列出可用变量 | `list_gl02_available_variables` |
| 查历史曲线 | `query_gl02_history` |
| 查统计值 | `query_gl02_statistics` |
| 查最新炉况快照 | `get_latest_furnace_snapshot` |
| 列出报表 | `list_recent_reports` |
| 读取报表片段 | `read_report_excerpt` |
| 检索历史问答 | `search_qa_messages` |

## 3. 返回字段要求

GL02 变量相关工具返回的 `variable` 元数据应包含：

```text
variable_name
short_name
point_id
tag_long_name
tag
description
unit
path_group
status
confidence
max_history_range
notes
```

示例：

```json
{
  "variable_name": "P_blast",
  "short_name": "SIO_GL02_BT_T0149",
  "point_id": "\\冀南钢铁\\SIO\\GL02\\BT\\SIO_GL02_BT_T0149",
  "tag_long_name": "\\冀南钢铁\\SIO\\GL02\\BT\\SIO_GL02_BT_T0149",
  "description": "2号炉本体_高炉本体热风压力",
  "status": "available",
  "confidence": "high",
  "path_group": "BT"
}
```

## 4. 50 条可学习查询示例

| # | 用户可以这样问 | MCP 工具 | 参数示例 |
|---:|---|---|---|
| 1 | 热风压力现在是多少？ | `get_latest_gl02_value` | `{"variable":"热风压力"}` |
| 2 | 查 P_blast 最新值 | `get_latest_gl02_value` | `{"variable":"P_blast"}` |
| 3 | 按短名查热风压力 | `get_latest_gl02_value` | `{"variable":"SIO_GL02_BT_T0149"}` |
| 4 | 顶压平均现在是多少？ | `get_latest_gl02_value` | `{"variable":"顶压"}` |
| 5 | 透气性指数现在是多少？ | `get_latest_gl02_value` | `{"variable":"透气性指数"}` |
| 6 | 全炉压差最新值 | `get_latest_gl02_value` | `{"variable":"全炉压差"}` |
| 7 | 上部压差最新值 | `get_latest_gl02_value` | `{"variable":"上部压差"}` |
| 8 | 下部压差最新值 | `get_latest_gl02_value` | `{"variable":"下部压差"}` |
| 9 | 热风温度现在是多少？ | `get_latest_gl02_value` | `{"variable":"热风温度"}` |
| 10 | 冷风管道压力最新值 | `get_latest_gl02_value` | `{"variable":"冷风管道压力"}` |
| 11 | 冷风管道流量最新值 | `get_latest_gl02_value` | `{"variable":"冷风管道流量"}` |
| 12 | 喷煤设定现在是多少？ | `get_latest_gl02_value` | `{"variable":"PCI_set"}` |
| 13 | 喷煤量代理最新值 | `get_latest_gl02_value` | `{"variable":"PCI_rate"}` |
| 14 | 综合顶温 T_top 最新值 | `get_latest_gl02_value` | `{"variable":"T_top"}` |
| 15 | 顶温 A 替代点最新值 | `get_latest_gl02_value` | `{"variable":"T_top_A"}` |
| 16 | 7层A炉体温度最新值 | `get_latest_gl02_value` | `{"variable":"7层A炉体温度"}` |
| 17 | 16层H炉身温度最新值 | `get_latest_gl02_value` | `{"variable":"16层H炉身温度"}` |
| 18 | 查热风压力变量信息 | `get_gl02_variable_info` | `{"variable":"热风压力"}` |
| 19 | 查顶温有哪些候选 | `find_gl02_variables` | `{"keyword":"顶温","limit":8}` |
| 20 | 查炉体温度变量族 | `find_gl02_variables` | `{"keyword":"炉体温度","limit":5}` |
| 21 | 煤气利用率有没有点位？ | `find_gl02_variables` | `{"keyword":"煤气利用率","limit":5}` |
| 22 | 南尺有没有点位？ | `find_gl02_variables` | `{"keyword":"南尺","limit":5}` |
| 23 | 列出高置信可用变量 | `list_gl02_available_variables` | `{"include_medium_confidence":false,"limit":20}` |
| 24 | 列出包含中置信替代点的变量 | `list_gl02_available_variables` | `{"include_medium_confidence":true,"limit":40}` |
| 25 | 查最新炉况快照 | `get_latest_furnace_snapshot` | `{}` |
| 26 | 查过去10分钟透气性指数曲线 | `query_gl02_history` | `{"variable":"PI","start_time":"2026-05-08T18:14:00+08:00","end_time":"2026-05-08T18:24:00+08:00","limit":20}` |
| 27 | 查过去10分钟热风压力曲线 | `query_gl02_history` | `{"variable":"P_blast","start_time":"2026-05-08T18:14:00+08:00","end_time":"2026-05-08T18:24:00+08:00","limit":20}` |
| 28 | 查过去10分钟全炉压差曲线 | `query_gl02_history` | `{"variable":"DP_total","start_time":"2026-05-08T18:14:00+08:00","end_time":"2026-05-08T18:24:00+08:00","limit":20}` |
| 29 | 查过去10分钟综合顶温派生曲线 | `query_gl02_history` | `{"variable":"T_top","start_time":"2026-05-08T18:14:00+08:00","end_time":"2026-05-08T18:24:00+08:00","limit":20}` |
| 30 | 查过去10分钟7层A炉体温度曲线 | `query_gl02_history` | `{"variable":"7层A炉体温度","start_time":"2026-05-08T18:14:00+08:00","end_time":"2026-05-08T18:24:00+08:00","limit":20}` |
| 31 | 过去10分钟透气性指数平均值 | `query_gl02_statistics` | `{"variable":"PI","start_time":"2026-05-08T18:14:00+08:00","end_time":"2026-05-08T18:24:00+08:00","agg":"avg"}` |
| 32 | 过去10分钟热风压力最大值 | `query_gl02_statistics` | `{"variable":"P_blast","start_time":"2026-05-08T18:14:00+08:00","end_time":"2026-05-08T18:24:00+08:00","agg":"max"}` |
| 33 | 过去10分钟全炉压差最小值 | `query_gl02_statistics` | `{"variable":"DP_total","start_time":"2026-05-08T18:14:00+08:00","end_time":"2026-05-08T18:24:00+08:00","agg":"min"}` |
| 34 | 过去10分钟综合顶温全部统计 | `query_gl02_statistics` | `{"variable":"T_top","start_time":"2026-05-08T18:14:00+08:00","end_time":"2026-05-08T18:24:00+08:00","agg":"all"}` |
| 35 | 过去10分钟热风压力第一条 | `query_gl02_statistics` | `{"variable":"P_blast","start_time":"2026-05-08T18:14:00+08:00","end_time":"2026-05-08T18:24:00+08:00","agg":"first"}` |
| 36 | 过去10分钟热风压力最后一条 | `query_gl02_statistics` | `{"variable":"P_blast","start_time":"2026-05-08T18:14:00+08:00","end_time":"2026-05-08T18:24:00+08:00","agg":"last"}` |
| 37 | 过去10分钟热风压力有多少点？ | `query_gl02_statistics` | `{"variable":"P_blast","start_time":"2026-05-08T18:14:00+08:00","end_time":"2026-05-08T18:24:00+08:00","agg":"count"}` |
| 38 | 用无时区时间查透气性指数曲线 | `query_gl02_history` | `{"variable":"PI","start_time":"2026-05-08T18:14:00","end_time":"2026-05-08T18:24:00","limit":5}` |
| 39 | limit 超大时查热风压力曲线 | `query_gl02_history` | `{"variable":"P_blast","start_time":"2026-05-08T18:14:00+08:00","end_time":"2026-05-08T18:24:00+08:00","limit":999999}` |
| 40 | limit 是 abc 时查热风压力曲线 | `query_gl02_history` | `{"variable":"P_blast","start_time":"2026-05-08T18:14:00+08:00","end_time":"2026-05-08T18:24:00+08:00","limit":"abc"}` |
| 41 | 查不存在变量 | `get_gl02_variable_info` | `{"variable":"random_unknown_变量"}` |
| 42 | 直接解析煤气利用率 | `get_gl02_variable_info` | `{"variable":"煤气利用率"}` |
| 43 | 直接解析炉体温度变量族 | `get_gl02_variable_info` | `{"variable":"炉体温度"}` |
| 44 | 反向时间窗查历史 | `query_gl02_history` | `{"variable":"PI","start_time":"2026-05-08T18:24:00+08:00","end_time":"2026-05-08T18:14:00+08:00","limit":5}` |
| 45 | 非法聚合 median | `query_gl02_statistics` | `{"variable":"PI","start_time":"2026-05-08T18:14:00+08:00","end_time":"2026-05-08T18:24:00+08:00","agg":"median"}` |
| 46 | 路径穿越读 AGENTS | `read_report_excerpt` | `{"report_path":"../../AGENTS.md","mode":"excerpt","max_chars":500}` |
| 47 | 列出最近日报 | `list_recent_reports` | `{"report_type":"日报","start_date":"2026/05/08","end_date":"2026/05/09","limit":5}` |
| 48 | 读取 2026-05-08 日报片段 | `read_report_excerpt` | `{"report_path":"2026/05/08/日报/BF_DAILY_REPORT_20260508_0000_日报.md","mode":"excerpt","max_chars":800}` |
| 49 | 检索历史问答里的硅含量 | `search_qa_messages` | `{"keyword":"硅含量","limit":5}` |
| 50 | 检索历史问答里的热风压力 | `search_qa_messages` | `{"keyword":"热风压力","limit":5}` |

## 5. 实际返回样例

### 热风压力

```text
variable_name: P_blast
short_name: SIO_GL02_BT_T0149
point_id: \冀南钢铁\SIO\GL02\BT\SIO_GL02_BT_T0149
description: 2号炉本体_高炉本体热风压力
latest.ts: 2026-05-08 22:51:00
latest.value: 453.7037099202474
source: gl02_1min.sqlite3 readonly
```

### 顶压平均

```text
variable_name: P_top
short_name: SIO_GL02_LD_T0034
point_id: \冀南钢铁\SIO\GL02\LD\SIO_GL02_LD_T0034
description: 2号炉炉顶_顶压平均
latest.value: 263.3662414550781
```

### 综合顶温

```text
variable_name: T_top
point_id: T_top_A-D avg
description: 由四个上升管煤气温度平均
quality: DERIVED_AVERAGE
说明: 这是派生值，不是单一物理点。
```

### 7层A炉体温度

```text
variable_name: T_body_L7_A
short_name: SIO_GL02_BT_T0155
point_id: \冀南钢铁\SIO\GL02\BT\SIO_GL02_BT_T0155
description: 2号炉本体_7层A炉体温度
```

## 6. 重要安全规则

- 不存在变量不会误查。
- `煤气利用率` 不会伪造。
- `炉体温度` 变量族不会误配成 `T_blast` 热风温度。
- `7层A炉体温度` 到 `16层H炉体温度` 可映射到具体 BT 点位。
- `T_top` 是派生平均，回答时必须说明 `DERIVED_AVERAGE`。
- 反向时间窗会被拒绝。
- 非法聚合会被拒绝。
- 报表路径穿越会被拒绝。
- `limit` 异常会被钳制或回落默认值。
- 所有数据源均按只读口径查询。

## 7. Ollama + MCP 端到端模型输出测试

在 220.12 上追加执行了 `chiqiong-blast-furnace:latest` + MCP 工具调用测试。测试方式为：用户问题进入 Ollama，模型返回 tool call，测试脚本执行 MCP 工具，再把工具结果返回给模型生成最终回答。

调用约束：

```text
model: chiqiong-blast-furnace:latest
think: false
stream: false
```

覆盖问题：

```text
1. 当前值查询：热风压力
2. 统计查询：透气性指数 10 分钟平均值
3. 派生变量查询：T_top 综合顶温
4. 具体炉体温度查询：7层A炉体温度
5. 缺失变量查询：煤气利用率
6. 模糊候选查询：顶温候选点
7. 报表查询：2026/05/08 日报
8. 历史问答检索：热风压力
```

端到端测试结果：

```text
模型工具调用测试：8 条
可用回答：8 条
发现并修复问题：1 条
```

发现并修复的问题：

```text
问题：模型先把 “7层A炉体温度” 解析为 T_body_L7_A，再用 T_body_L7_A 查询最新值；旧版 resolve_variable 尚不支持 T_body_L7_A 或 SIO_GL02_BT_T0155 直接反查。
修复：body_temperature_variable_from_text 增加 T_body_L{layer}_{sector}、SIO_GL02_BT_T0155..T0234、完整 tag 三种解析方式。
复测：7层A炉体温度、T_body_L7_A、SIO_GL02_BT_T0155、完整 tag 均可成功查询。
```

### 7.1 模型输出：热风压力当前值

用户问题：

```text
热风压力现在是多少？请带上点位、描述和时间。
```

模型调用工具：

```json
{
  "tool": "get_latest_gl02_value",
  "args": {
    "variable": "热风压力"
  },
  "ok": true
}
```

模型输出：

```text
热风压力的最新数据如下：
- 点位: \冀南钢铁\SIO\GL02\BT\SIO_GL02_BT_T0149
- 描述: 2号炉本体_高炉本体热风压力
- 变量名: P_blast
- 时间: 2026-05-08 22:59:00
- 值: 450.92230733235675

该值为高置信度原始值，采集于2026-05-08 23:00:02。
```

### 7.2 模型输出：透气性指数平均值

用户问题：

```text
过去10分钟透气性指数平均值是多少？时间范围 2026-05-08T18:14:00+08:00 到 2026-05-08T18:24:00+08:00。
```

模型调用工具：

```json
{
  "tool": "query_gl02_statistics",
  "args": {
    "variable": "透气性指数",
    "start_time": "2026-05-08T18:14:00+08:00",
    "end_time": "2026-05-08T18:24:00+08:00",
    "agg": "avg"
  },
  "ok": true
}
```

模型输出：

```text
在时间范围 2026-05-08T18:14:00+08:00 到 2026-05-08T18:24:00+08:00 内，透气性指数的统计信息如下：

- 变量名：PI
- 点位：\冀南钢铁\SIO\GL02\BT\SIO_GL02_BT_T0101
- 描述：2号炉本体_透气性指数
- 置信度：高
- 统计值（平均值）：22.62
- 数据计数：9 个有效数据点

该变量为高置信度直接测量值，非派生值。
```

### 7.3 模型输出：综合顶温 T_top

用户问题：

```text
综合顶温 T_top 现在是多少？说明它是不是物理点。
```

模型调用工具：

```json
[
  {
    "tool": "get_latest_gl02_value",
    "args": {
      "variable": "T_top"
    },
    "ok": true
  },
  {
    "tool": "get_gl02_variable_info",
    "args": {
      "variable": "T_top"
    },
    "ok": true
  }
]
```

模型输出：

```text
综合顶温 T_top 的当前信息如下：

- 变量名：T_top
- 点位：T_top_A-D avg
- 描述：由四个上升管煤气温度平均
- 时间：2026-05-08 22:59:00
- 值：126.03

T_top 不是直接的物理点，而是一个派生变量，置信度为中。
它由 T_top_A、T_top_B、T_top_C、T_top_D 四个上升管煤气温度平均计算得到。
计算方式为 AVG(T_top_A,T_top_B,T_top_C,T_top_D)。
```

### 7.4 模型输出：7层A炉体温度

用户问题：

```text
7层A炉体温度现在是多少？给出点ID。
```

工具直接复测结果：

```text
7层A炉体温度 -> T_body_L7_A / SIO_GL02_BT_T0155 / ok
T_body_L7_A -> T_body_L7_A / SIO_GL02_BT_T0155 / ok
SIO_GL02_BT_T0155 -> T_body_L7_A / SIO_GL02_BT_T0155 / ok
\冀南钢铁\SIO\GL02\BT\SIO_GL02_BT_T0155 -> T_body_L7_A / SIO_GL02_BT_T0155 / ok
```

模型调用工具：

```json
{
  "tool": "get_latest_gl02_value",
  "args": {
    "variable": "7层A炉体温度"
  },
  "ok": true
}
```

模型输出：

```text
以下是您查询的7层A炉体温度的详细信息：

- 变量名: T_body_L7_A
- 点ID: \冀南钢铁\SIO\GL02\BT\SIO_GL02_BT_T0155
- 描述: 2号炉本体_7层A炉体温度
- 时间: 2026-05-08 23:02:00
- 值: 47.22222137451172
```

### 7.5 模型输出：煤气利用率缺失

用户问题：

```text
煤气利用率有没有可用点位？不要伪造。
```

模型调用工具：

```json
{
  "tool": "find_gl02_variables",
  "args": {
    "keyword": "煤气利用率",
    "limit": 10
  },
  "ok": true
}
```

模型输出：

```text
GL02 高炉清单中没有直接的“煤气利用率”变量或可直接计算的炉顶 CO/CO2 组合点位。

- 变量名: GasUtil
- 点位: 无
- 描述: GL02 清单无煤气利用率，也无可直接计算的炉顶 CO/CO2 组合。
- 状态: missing
- 置信度: missing

结论：当前无煤气利用率的可用点位，请勿尝试伪造或强行计算。
```

### 7.6 模型输出：顶温候选点

用户问题：

```text
顶温有哪些候选点？说明哪些是替代点。
```

模型调用工具：

```json
{
  "tool": "find_gl02_variables",
  "args": {
    "keyword": "顶温",
    "limit": 20
  },
  "ok": true
}
```

模型输出摘要：

```text
GL02 高炉没有明确命名的“顶温A-D”精确变量。系统当前仅包含四个上升管煤气温度点位，它们被用作替代点。

替代点：
- T_top_A: \冀南钢铁\SIO\GL02\LD\SIO_GL02_LD_T0040，2号炉炉顶_上升管煤气温度，中置信
- T_top_B: \冀南钢铁\SIO\GL02\LD\SIO_GL02_LD_T0043，2号炉炉顶_上升管煤气温度，中置信
- T_top_C: \冀南钢铁\SIO\GL02\LD\SIO_GL02_LD_T0064，2号炉炉顶_上升管煤气温度，中置信
- T_top_D: \冀南钢铁\SIO\GL02\LD\SIO_GL02_LD_T0072，2号炉炉顶_上升管煤气温度，中置信

派生值：
- T_top: T_top_A-D avg，由四个上升管煤气温度平均，非直接传感器点位。
```

### 7.7 模型输出：日报查询

用户问题：

```text
列出 2026/05/08 的日报，并读一小段摘要。
```

模型调用工具：

```json
[
  {
    "tool": "list_recent_reports",
    "args": {
      "start_date": "2026-05-08",
      "end_date": "2026-05-08",
      "limit": 10
    },
    "ok": true
  },
  {
    "tool": "read_report_excerpt",
    "args": {
      "report_path": "2026/05/08/日报/BF_DAILY_REPORT_20260508_0000_日报.md",
      "max_chars": 500
    },
    "ok": true
  }
]
```

模型输出摘要：

```text
已找到 2026-05-08 的 GL02 高炉日报：

- 文件名: BF_DAILY_REPORT_20260508_0000_日报.md
- 路径: 2026/05/08/日报/
- 修改时间: 2026-05-08 17:32:21

摘要：
- 报表类型: 日报
- 时间范围: 2026-05-08 00:00 至 2026-05-08 23:59
- 快照数量: 119 条
- 最新诊断: center
- 全压差: 237 kPa，均值 227 kPa
- 透气性指数: 18.6，均值 19.6
```

### 7.8 模型输出：历史问答检索

用户问题：

```text
检索历史问答里有没有热风压力相关内容。
```

模型调用工具：

```json
{
  "tool": "search_qa_messages",
  "args": {
    "keyword": "热风压力"
  },
  "ok": true
}
```

模型输出摘要：

```text
检索到 2 条与“热风压力”相关的历史问答记录。

记录一：
- 关联变量: 热风压力 P_blast
- 历史数值: 481-502 kPa
- 上下文: 高炉处于“中心过吹”导致的憋压风险状态

记录二：
- 关联变量: 热风压力 P_blast
- 历史数值: 481-503 kPa
- 上下文: 用于判定“中心过吹、边缘不足”

提示：这些是历史问答中的记录值，不是当前实时值。
```

## 8. 完善度判断

当前测试已经覆盖 MCP 查询数据库数据的主要路径：

- 工具函数层：1476 条本地回归，0 失败。
- 远端工具层：50 条真实远端查询，50 通过。
- 模型调用层：8 类典型自然语言问题，覆盖实时、统计、派生、缺失、报表、历史问答。
- 安全边界层：缺失变量、反向时间窗、非法聚合、路径穿越均验证拒绝。

仍需后续生产前补充：

- 8092 `/api/qa/chat` 正式接入后的浏览器端流式验证。
- pSpace 243 实时读取工具接入后的只读联调。
- PostgreSQL/Vastbase 生产库 profile 的只读账号权限审计。
- 工具调用审计日志和用户权限隔离。


