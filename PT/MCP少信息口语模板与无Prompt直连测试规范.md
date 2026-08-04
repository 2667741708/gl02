# MCP 少信息口语模板与无Prompt直连测试规范

需求编号：`REQ-MCP-CONVERSATION-CONTEXT-20260726`

## 1. 两种验收不能混淆

### 口语问答验收

经过8093/8094问答代理、对话状态、固定快速路由或27B规划，验证现场人员说得
简短、含糊或省略时，系统能否结合上文选择正确MCP工具。

### 无Prompt模板直连验收

直接通过MCP stdio协议调用明确工具和JSON参数：

```text
MCP Client → list_tools/call_tool → MCP Server
```

它不经过：

- 27B模型；
- 系统提示；
- 炉况上下文；
- RAG；
- 固定口语模板；
- 问答路由。

该模式用于测量MCP本体功能和纯工具耗时，不能替代自然语言端到端验收。

## 2. 少信息单句模板

### 当前值

```text
顶压呢？
南尺多少？
北边那个料线。
冷风压。
富氧现在呢？
煤量实际多少？
俩铁口温度。
中层静压。
23米那层各点。
七层A点。
```

### 历史和统计

```text
顶压半小时。
它稳不稳？
看看刚才那段。
最近有波动吗？
最高最低呢？
平均多少？
换成两小时。
看昨天这会儿。
前后差多少？
```

### 多变量与关系

```text
和压差一起看。
再加透气性。
它俩相关吗？
同步不？
哪个先变？
对比一下。
放一张图里。
画出来。
换散点。
改成相关矩阵。
```

### 炉次与化验

```text
这炉硅多少？
锰呢？
铁量呢？
这炉的渣。
碱度有吗？
最近那份进料。
二烧的。
今天最新样。
```

### 报表与历史问答

```text
最近日报。
概括两句。
上一份呢？
我问过顶压吗？
刚才的问题。
找压差相关的。
```

## 3. 推荐多轮验收序列

### 序列A：变量和时间继承

```text
用户：顶压最近半小时。
用户：和总压差一起看。
用户：画出来。
用户：换成两小时。
用户：改散点。
```

期望状态：

```json
{
  "selected_objects": ["P_top", "DP_total"],
  "time_range": {"mode": "relative", "minutes": 120},
  "analysis_goal": "plot",
  "preferred_chart": "correlation_scatter"
}
```

### 序列B：少信息传感器追问

```text
用户：南北探尺现在多少？
用户：过去一小时呢？
用户：哪个波动大？
用户：画一下。
```

### 序列C：炉次化验

```text
用户：查2#20260716-101这炉的铁水。
用户：只说硅锰。
用户：渣呢？
用户：和上一炉对比。
```

### 序列D：图表变换

```text
用户：看顶压和总压差最近半小时。
用户：画出来。
用户：换成散点。
用户：再给相关系数。
```

### 序列E：炉体矩阵

```text
用户：看7到16层A到F炉体温度。
用户：矩阵。
用户：每格放一小时曲线。
用户：扩到H方位。
```

## 4. 结构化对话状态

服务端每轮保存：

```json
{
  "selected_objects": ["P_top", "DP_total"],
  "time_range": {"mode": "relative", "minutes": 30},
  "analysis_goal": "correlation",
  "preferred_chart": "correlation_scatter",
  "last_tool_names": ["plot_gl02_analysis"],
  "last_evidence": [],
  "pending_clarification": null,
  "inheritance": {"objects": true, "time_range": true}
}
```

状态只包含业务对象和证据摘要，不保存SQL、凭据、完整炉况资料或系统提示。

## 5. 无Prompt模板测试命令

查看帮助：

```text
python tools/test_mcp_direct_no_prompt.py --help
```

运行全部直连用例：

```text
python tools/test_mcp_direct_no_prompt.py
```

仅测试目录：

```text
python tools/test_mcp_direct_no_prompt.py --case catalog
```

测试最新值和统计：

```text
python tools/test_mcp_direct_no_prompt.py --case latest --case statistics
```

输出报告：

```text
python tools/test_mcp_direct_no_prompt.py --output logs/mcp_direct_no_prompt.json
```

## 6. 延迟口径

| 指标 | 包含内容 |
|---|---|
| MCP直连耗时 | stdio初始化、工具执行和结果序列化 |
| 问答准备耗时 | 数据上下文、预取、知识意图判断 |
| 规划耗时 | 27B工具选择 |
| 最终回答耗时 | 27B解释生成 |
| 端到端耗时 | 从HTTP请求到最终done |

“无Prompt模板更快”只能说明模型和问答上下文占据了额外耗时，不能据此删除生产
口语路由。生产优化应优先使用固定快速路径、结构化对话状态和复合工具。

## 7. 2026-07-26 实施与验收

已实现：

- `backend/mcp_conversation_context.py`结构化状态；
- 变量、时间、目标和图表类型的多轮继承；
- latest/history/statistics确定性批量计划；
- 查询和图表事实格式器，明确路径不再追加一次27B回答；
- `tools/test_8093_mcp_context_followups.py`现网多轮验收；
- `tools/test_mcp_direct_no_prompt.py`纯MCP能力与耗时验收。

现网少信息序列：

```text
比较最近半小时炉顶压力和总压差
画出来
换成两小时
再加上透气性一起看

南探尺最近一小时
北尺也加上
一张图
```

结果为7/7；实际工具参数逐轮验证变量集合与30/60/120分钟窗口，所有生成图片
均返回`200 image/png`。关键四问4/4自动通过，单题只执行一次
`query_gl02_sensors`，中位总耗时约`1.12s`。回答保留正式中文名和单位。

无Prompt直连4/4通过：目录约`3ms`、单变量最新值约`296ms`、双变量统计约
`382ms`、相关散点图约`2.04s`，包含MCP进程初始化的总耗时约`3.73s`。

这里的“无Prompt”仅表示测试客户端直接提交工具名和JSON参数。生产问答仍保留：

```text
固定快速路由 → 结构化状态与确定性批量计划 → 27B受控规划兜底
```
