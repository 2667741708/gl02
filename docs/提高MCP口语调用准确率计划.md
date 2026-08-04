# 提高 MCP 口语调用准确率计划

主题：如何提高 MCP 服务的调用准确率

## 1. 目标

让 8093 智能问答支持现场人员的自然口语表达，例如：

- “告诉我一下炉顶的温度”
- “给我说一下炉顶的压力”
- “现在顶温多少”
- “最近半小时顶压稳不稳”
- “画一下顶温和顶压这一个小时的走势”

系统应自动完成：

1. 识别用户口语中的真实工艺语义。
2. 将语义名称归一到标准变量名，例如 `T_top`、`P_top`。
3. 通过 MCP 查询变量元数据、具体点位、最新值、历史值、统计值或趋势图。
4. 在回答中说明使用的数据时间、变量名称、点位来源和必要的现场解释。

## 2. 可行性结论

该计划可行，且应优先采用“确定性解析 + MCP 工具描述增强 + 测试集验收”的组合方案。

只在大模型提示词或 MCP 工具说明中增加注释是不够的。工具注释可以提升模型选择工具的概率，但不能稳定保证每个口语问题都命中正确变量。真正可靠的方案是：在 8093 问答代理层先做口语归一化和变量解析，再把标准变量名交给 MCP。

当前已有基础：

- 8093 问答代理已有 `qa_mcp_variable()`，但候选词仍偏硬编码，见 [ollama_proxy_server.py](../高炉前端数据/智能助手/backend/ollama_proxy_server.py)。
- MCP 服务已有变量别名、变量搜索、变量解析能力，见 [bf_data_mcp_server.py](../高炉前端数据/智能助手/mcp/bf_data_mcp_server.py)。
- MCP 已有自然语言准确率测试资料，见 [MCP自然语言调用准确率测试集.md](../高炉前端数据/智能助手/docs/MCP自然语言调用准确率测试集.md)。
- 8093 MCP 链路和 `plot_gl02_trends` 修复记录见 [22012_8093_v4_guard_ops.md](22012_8093_v4_guard_ops.md)。

## 3. 当前问题

### 3.1 口语表达不稳定

现场人员不会总说“请调用 MCP 查询 T_top”。更常见的是：

| 口语表达 | 应识别语义 | 标准变量 |
| --- | --- | --- |
| 炉顶的温度 | 综合炉顶温度 | `T_top` |
| 顶温多少 | 综合顶温 | `T_top` |
| 上升管温度 | 综合顶温或 T_top_A-D 分量 | `T_top` / `T_top_A-D` |
| 炉顶的压力 | 综合顶压 | `P_top` |
| 顶压多少 | 综合顶压 | `P_top` |
| 煤气利用怎么样 | 煤气利用率 | `GasUtil` |
| 炉子透气性咋样 | 透气性指数 | `PI` |
| 压差起来了吗 | 总压差/上下部压差 | `DP_total` / `DP_lower` / `DP_upper` |

### 3.2 “工具调用准确”与“变量识别准确”是两件事

模型可能调用了 MCP，但参数错了；也可能没有调用 MCP，只基于上下文回答。验收时要同时检查：

- 是否调用了 MCP。
- 调用了哪个工具。
- 传入了哪个变量。
- 返回的点位、时间、数值是否正确。
- 回答是否使用了工具结果，而不是凭记忆编写。

## 4. 设计原则

1. 口语优先：按现场说法设计，不要求用户懂变量名。
2. 确定性优先：能用规则解析的，不交给模型猜。
3. 别名集中管理：同一个口语词不要散落在 prompt、代码和文档多处。
4. 低置信度要追问：同时命中多个变量时，系统应提示用户确认。
5. 所有 MCP 数据回答必须带数据时间和来源。
6. 修改后必须能用一组口语测试题回归。

## 5. 分层方案

### 5.1 第一层：口语清洗

新增口语清洗函数，将用户问题转成更容易匹配的短语。

建议处理：

- 去掉礼貌和填充词：告诉我一下、给我说一下、帮我看看、现在、当前、是多少、多少、咋样。
- 统一同义字：压力/压、温度/温、走势/趋势/变化。
- 保留时间词：最近半小时、近1小时、昨天、当前。

示例：

| 原问题 | 清洗后 |
| --- | --- |
| 告诉我一下炉顶的温度 | 炉顶温度 |
| 给我说一下炉顶的压力 | 炉顶压力 |
| 最近半小时顶压稳不稳 | 最近半小时 顶压 稳 |
| 画一下顶温和顶压这一个小时的走势 | 近1小时 顶温 顶压 趋势 |

### 5.2 第二层：口语别名词典

建立统一别名词典，建议放在 8093 问答代理层，后续可迁移到 JSON/YAML 配置。

首批建议：

| 标准变量 | 口语别名 |
| --- | --- |
| `T_top` | 炉顶温度、炉顶的温度、顶温、综合顶温、综合炉顶温、炉顶煤气温度、上升管温度平均 |
| `P_top` | 炉顶压力、炉顶的压力、炉顶压、顶压、综合顶压、炉顶煤气压力、煤气顶压 |
| `GasUtil` | 煤气利用率、煤气利用、煤气利用怎么样 |
| `PI` | 透气性指数、透气性、炉子透气性、顺不顺 |
| `DP_total` | 总压差、全炉压差、压差、压差起来 |
| `DP_lower` | 下部压差、下压差 |
| `DP_upper` | 上部压差、上压差 |
| `Q_blast` | 风量、送风量、热风流量 |
| `P_blast` | 风压、热风压力 |
| `T_blast` | 风温、热风温度 |
| `PCI_rate` | 喷煤量、喷煤率、煤量 |
| `L` | 料线、平均料线 |

### 5.3 第三层：语义意图识别

把用户问题分为几类，再选择 MCP 工具。

| 意图 | 触发词 | MCP 工具 |
| --- | --- | --- |
| 最新值 | 当前、现在、多少、告诉我 | `get_latest_gl02_value` |
| 统计 | 平均、最大、最小、稳不稳、波动 | `query_gl02_statistics` |
| 历史序列 | 历史、最近、过去、变化 | `query_gl02_history` |
| 趋势图 | 画、图、走势、趋势、对比 | `plot_gl02_trends` |
| 变量解释 | 是哪个点、点位、变量、元数据 | `find_gl02_variables` / `get_gl02_variable_info` |
| 炉况 | 炉况、正常吗、顺不顺、异常 | `get_latest_furnace_snapshot` |

### 5.4 第四层：变量消歧

当用户只说“炉顶”时，可能同时涉及 `T_top` 和 `P_top`。规则建议：

- 用户说“温/温度/顶温” -> `T_top`
- 用户说“压/压力/顶压” -> `P_top`
- 用户说“炉顶情况”且无温压词 -> 同时查询 `T_top`、`P_top`，或追问“您想看炉顶温度还是炉顶压力？”
- 用户说“顶温分布” -> 查询 `T_top_A`、`T_top_B`、`T_top_C`、`T_top_D`，并可补充 `T_top`

### 5.5 第五层：MCP 工具描述增强

需要对 MCP 工具说明增加口语提示，但作为辅助，不作为唯一方案。

建议增强位置：

- `find_gl02_variables()`：说明可处理“炉顶温度、炉顶压力、顶压、顶温、煤气利用、透气性”等口语词。
- `get_latest_gl02_value()`：说明用户问“告诉我一下某指标”“现在某指标多少”时适用。
- `query_gl02_statistics()`：说明用户问“稳不稳、波动、平均、最高、最低、变化”时适用。
- `plot_gl02_trends()`：说明用户问“画一下、走势、趋势、对比图”时适用。

### 5.6 第六层：回答兜底规范

每次通过 MCP 查询后，回答至少包含：

- 用户口语命中的标准变量。
- 变量中文解释。
- 数据时间。
- 数值和单位。
- 来源：PostgreSQL / pSpace / 派生变量。
- 若是派生变量，说明由哪些分量组成。

示例：

> 您说的“炉顶的温度”对应系统变量 `T_top`，即综合炉顶温度，由 A-D 四个顶温点平均得到。当前最新值为 xx ℃，数据时间为 yyyy-mm-dd hh:mm，来源为 PostgreSQL 1 分钟数据。

## 6. 实施阶段

### 阶段一：快速增强

目标：让常见口语问题稳定命中变量。

任务：

1. 扩展 `qa_mcp_variable()` 的别名表。
2. 增加 `normalize_spoken_question()` 口语清洗函数。
3. 增加“炉顶温度/炉顶压力”优先规则。
4. 修改 MCP 工具 docstring，加入口语示例。
5. 建立 30 条口语测试题。

验收：

- “告诉我一下炉顶的温度”命中 `T_top`。
- “给我说一下炉顶的压力”命中 `P_top`。
- “最近半小时顶压稳不稳”调用 `query_gl02_statistics(P_top)`。
- “画一下顶温和顶压走势”调用 `plot_gl02_trends(["T_top","P_top"])`。

### 阶段二：统一词典

目标：减少硬编码，便于维护。

任务：

1. 将别名词典迁移为配置文件，例如 `高炉前端数据/智能助手/config/mcp_spoken_aliases.json`。
2. 配置字段包括：标准变量、口语别名、工艺类别、默认工具、歧义组、优先级。
3. 让 `qa_mcp_variable()` 和 MCP `find_gl02_variables()` 共用同一词典。
4. 在文档中记录每个口语词对应的变量和点位。

验收：

- 新增别名不需要改 Python 代码。
- 变量搜索和问答路由返回一致结果。

### 阶段三：低置信度追问

目标：减少误调用。

任务：

1. 对每次口语解析输出置信度。
2. 低于阈值时不直接查库，而是追问。
3. 对歧义词提供两个以内选项。

示例：

> 您说的“炉顶”可能是炉顶温度，也可能是炉顶压力。您要看哪一个？

验收：

- “炉顶咋样”不盲目只查 `T_top`。
- “煤气怎么样”不盲目查 `GasUtil`，必要时提示可看煤气利用率、顶压、顶温分布。

### 阶段四：端到端准确率评测

目标：形成可回归的质量门槛。

任务：

1. 建立 100 条口语问题集。
2. 每条记录期望工具、期望变量、期望是否画图。
3. 自动调用 8093 `/api/qa/chat`。
4. 统计：
   - MCP 调用率
   - 工具选择准确率
   - 变量解析准确率
   - 点位/数据来源正确率
   - 图片链接可访问率

目标指标：

- 口语变量解析准确率 >= 95%
- MCP 工具选择准确率 >= 95%
- 常见 28 核心变量覆盖率 = 100%
- 低置信追问误触发率 <= 10%

## 7. 首批测试问题

| 问题 | 期望变量 | 期望工具 |
| --- | --- | --- |
| 告诉我一下炉顶的温度 | `T_top` | `get_latest_gl02_value` |
| 给我说一下炉顶的压力 | `P_top` | `get_latest_gl02_value` |
| 现在顶温多少 | `T_top` | `get_latest_gl02_value` |
| 当前顶压多少 | `P_top` | `get_latest_gl02_value` |
| 最近半小时顶温变化大吗 | `T_top` | `query_gl02_statistics` |
| 最近半小时顶压稳不稳 | `P_top` | `query_gl02_statistics` |
| 画一下顶温和顶压这一小时走势 | `T_top`,`P_top` | `plot_gl02_trends` |
| 炉子透气性咋样 | `PI` | `get_latest_gl02_value` 或 `query_gl02_statistics` |
| 压差是不是起来了 | `DP_total` | `query_gl02_statistics` |
| 煤气利用怎么样 | `GasUtil` | `query_gl02_statistics` |

## 8. 风险与边界

- “炉顶”本身是歧义词，不能无条件映射到单一变量。
- “炉况怎么样”不是单变量问题，应优先查炉况快照，再补关键变量。
- 口语中“压力”可能指顶压、风压或压差，必须结合“炉顶、热风、压差”等上下文词。
- 变量别名过多可能造成误匹配，需要置信度和歧义组。
- 不应让前端或文档暴露生产密码、内部连接串或敏感字段。

## 9. 推荐落地点

代码层：

- `高炉前端数据/智能助手/backend/ollama_proxy_server.py`
  - `qa_mcp_variable()`
  - `qa_mcp_prefetch()`
  - `QA_MCP_INTENT_KEYWORDS`
  - 后续新增 `normalize_spoken_question()`、`resolve_spoken_mcp_targets()`

- `高炉前端数据/智能助手/mcp/bf_data_mcp_server.py`
  - `find_gl02_variables()`
  - `get_latest_gl02_value()`
  - `query_gl02_statistics()`
  - `plot_gl02_trends()`

配置层：

- 后续建议新增：`高炉前端数据/智能助手/config/mcp_spoken_aliases.json`

文档层：

- 本计划文档。
- `docs/22012_8093_v4_guard_ops.md` 记录每次 8093 实际部署和验收。
- `高炉前端数据/智能助手/docs/MCP自然语言调用准确率测试集.md` 扩充口语测试集。

## 10. 最小可行版本

如果先做一个小版本，建议只做四件事：

1. 扩展 `T_top`、`P_top`、`GasUtil`、`PI`、`DP_total` 的口语别名。
2. 新增口语清洗函数。
3. 为 `qa_mcp_prefetch()` 接入清洗后的问题。
4. 用 30 条现场口语问题做 8093 实测。

完成后即可显著提升“告诉我一下炉顶的温度”“给我说一下炉顶的压力”这类问题的 MCP 调用准确率。

## 11. 2026-07-14 第一阶段实验记录

本次已执行第一阶段最小可行版本，并部署到 8093 预览服务。

实现内容：

1. 在 `高炉前端数据/智能助手/backend/ollama_proxy_server.py` 新增 `normalize_spoken_question()`，先清洗“帮我、给我、告诉我、说一下、看一下、一下、的、现在、当前”等口语填充词。
2. 在同一文件新增 `SPOKEN_MCP_VARIABLE_ALIASES`，覆盖 `T_top`、`P_top`、`GasUtil`、`PI`、`DP_total`、`DP_upper`、`DP_lower`、`T_blast`、`P_blast`、`Q_blast`、`PCI_rate`、`L` 等常用现场说法。
3. `qa_mcp_variable()` 已改为先做口语归一化，再映射标准变量。
4. `qa_mcp_prefetch()` 已把“告诉我、给我说、说一下、看一下、查一下、看看、怎么样、咋样”等纳入数据查询意图；“告诉我一下炉顶的温度”会预取 `T_top` 最新值，“给我说一下炉顶的压力”会预取 `P_top` 最新值。
5. `qa_mcp_should_use_tools()` 已同时检查原始问题和口语归一化文本。
6. `高炉前端数据/智能助手/mcp/bf_data_mcp_server.py` 的 `find_gl02_variables()`、`get_latest_gl02_value()`、`query_gl02_statistics()`、`plot_gl02_trends()` docstring 已补充口语示例，辅助模型选工具。

本地验证：

- `python -m py_compile 高炉前端数据\智能助手\backend\ollama_proxy_server.py 高炉前端数据\智能助手\mcp\bf_data_mcp_server.py` 通过。
- 15 条口语解析样例均命中预期标准变量，并触发 MCP 工具使用条件。
- 使用假 MCP 数据模块验证：
  - “告诉我一下炉顶的温度” -> `T_top` / `latest`
  - “给我说一下炉顶的压力” -> `P_top` / `latest`
  - “最近半小时炉顶压力有没有波动” -> `P_top` / `statistics`

8093 真实接口验收：

- 部署边界：只重启 `BFV4PreviewProxy8093`，不停止 `BFV4PreviewWs8768`。
- 远端备份：
  - `ollama_proxy_server.py.bak_spoken_mcp_aliases_20260714_214636`
  - `bf_data_mcp_server.py.bak_spoken_mcp_aliases_20260714_214636`
- `POST http://127.0.0.1:8093/api/qa/chat` 复测结果：
  - “告诉我一下炉顶的温度”：`mcp_tool_calling=true`、`mcp_prefetch.used=true`、`mcp_prefetch.kind=latest`、`mcp_prefetch.variable=T_top`
  - “给我说一下炉顶的压力”：`mcp_tool_calling=true`、`mcp_prefetch.used=true`、`mcp_prefetch.kind=latest`、`mcp_prefetch.variable=P_top`
  - “最近半小时炉顶压力有没有波动”：`mcp_tool_calling=true`、`mcp_prefetch.used=true`、`mcp_prefetch.kind=statistics`、`mcp_prefetch.variable=P_top`

注意：最新值和统计类问题可能由 `qa_mcp_prefetch()` 直接查 MCP 数据模块并注入上下文，因此 `mcp_tool_trace` 不一定有通用工具调用记录；验收时应同时看 `mcp_prefetch` 与 `mcp_tool_trace`。

## 12. 2026-07-15 第二阶段修复执行记录

本阶段针对 `ERR-8093-MCP-COLLOQUIAL-002` 完成生产预览环境修复。

1. 口语词典扩展到南北探尺、A-D 上升管压力/温度、炉喉温度、理论燃烧温度、冷风压力、富氧、喷煤设定、出铁口、静压力、称量罐和煤气成分。
2. 增加标准变量边界匹配和父子变量抑制，精确变量不会再被较短父变量截获。
3. 增加多变量组解析，支持“四个上升管”“一号和二号出铁口”“三个高度静压力”等共享后缀口语。
4. 最近日报、报表摘要和历史问答改为直接工具意图；具体变量的“最近一小时趋势”保留完整工具轮。
5. 图表输出目录被约束在 8093 静态根目录内，并统一使用 `/data/mcp_charts` URL。
6. 本地 20 项回归测试通过，真实 8093 最新值、多变量、趋势图、日报和历史问答复测通过。
7. 仅重启 `BFV4PreviewProxy8093`，8768 实时数据服务保持运行。

## REQ-8093-MCP-CHART-003 数据绘图能力扩展

### 用户场景

现场用户不只需要“最近一小时折线图”，还需要不同单位双轴对比、多变量分面、移动平均、参考线、相关性、分布和箱线图；图表必须使用真实数据库时序数据，并保留可审计的时间窗、样本量和派生指标。

### 实现位置

- 趋势图参数、自动选图和渲染：[bf_data_mcp_server.py:L1334-L1699](../高炉前端数据/智能助手/mcp/bf_data_mcp_server.py#L1334-L1699)
- 关系/分布图渲染与工具合同：[bf_data_mcp_server.py:L1738-L1920](../高炉前端数据/智能助手/mcp/bf_data_mcp_server.py#L1738-L1920)、[bf_data_mcp_server.py:L2228-L2639](../高炉前端数据/智能助手/mcp/bf_data_mcp_server.py#L2228-L2639)
- 确定性口语绘图计划与工具执行：[ollama_proxy_server.py:L3456-L3533](../高炉前端数据/智能助手/backend/ollama_proxy_server.py#L3456-L3533)、[ollama_proxy_server.py:L3885-L4078](../高炉前端数据/智能助手/backend/ollama_proxy_server.py#L3885-L4078)
- 绘图专项测试：[test_mcp_chart_expansion.py:L64-L164](../高炉前端数据/智能助手/tests/test_mcp_chart_expansion.py#L64-L164)
- 口语与工具链既有回归：[test_qa_latency_optimizations.py:L65-L231](../高炉前端数据/智能助手/tests/test_qa_latency_optimizations.py#L65-L231)

### 输入与输出合同

- `plot_gl02_trends` 向后兼容原参数，新增 `chart_type`、`moving_average_points`、`show_extrema`、`show_latest`、`reference_values`、`theme`。
- `plot_gl02_analysis` 新增 `correlation_scatter`、`correlation_heatmap`、`distribution`、`boxplot`。
- 成功结果固定返回 `image_url`、`data_path`、实际图型、变量统计摘要、数据源和部分失败项；相关图额外返回对齐点数、Pearson 系数或相关矩阵。
- PNG 与 JSON 旁车均位于 8093 静态目录 `/data/mcp_charts/`；时间窗无数据、变量不足或同分钟对齐点不足时返回结构化错误。

### 验证命令

```powershell
python -X utf8 高炉前端数据\智能助手\tests\test_mcp_chart_expansion.py -v
python -X utf8 高炉前端数据\智能助手\tests\test_qa_latency_optimizations.py -v
python -X utf8 tools\test_8093_colloquial_prompts.py --groups mcp --case mcp_latest_probe_pair --case mcp_latest_top_gas_pressure_abcd --case mcp_latest_cold_blast_pressure --case mcp_latest_oxygen_pair
```

影响边界：只读查询时序数据和写入前端静态图表目录，不修改 PostgreSQL 表结构、不写生产控制、不重启 8768。

### 2026-07-15 实施与验收

- 初次现网扩展验收 6 条中只有 3 条真正产图；失败用例均为模型先调用 `find_gl02_variables` 后提前作答，并出现“图表生成中”假完成，另有模型猜测非标准变量名。该问题登记为 `ERR-8093-MCP-CHART-EARLY-ANSWER-003`。
- 修复后由 `qa_mcp_chart_plan()` 确定性解析标准变量、时间窗、图型、缩放和主题，并在 `qa_mcp_tool_loop_async()` 中直接调用绘图 MCP；模型只负责解释已生成结果，不再决定是否继续画图。
- 本地测试：绘图专项 6/6，既有问答/路由回归 22/22，Python 编译通过。
- 真实 8093：双轴、三分面、相关散点、相关矩阵、分布直方、箱线图 6/6 自动验收通过；报告见 [8093_mcp_chart_expansion_remote_after_deterministic_20260715.json](../logs/8093_mcp_chart_expansion_remote_after_deterministic_20260715.json)。
- 六张图片均为 HTTP `200 image/png`；视觉检查发现相关矩阵默认标题过长后，已改为简洁本地时间并加宽画布，专项复测见 [8093_mcp_heatmap_title_retest_20260715.json](../logs/8093_mcp_heatmap_title_retest_20260715.json)。
- 最终远端代理 SHA-256：`F2184B97C8F1FF90C9C16973DF4C32AC649932E452864720A80EAB945F74940F`；MCP SHA-256：`0977A7CA100FC75C6F8A29296AE29F7E9CEC90E749C355BF626689AE7ECDA753`。

## REQ-8093-MCP-BODY-MATRIX-004 炉体温度热力趋势矩阵

### 用户场景与合同

- 用户要求把炉身、炉腹、炉缸 7–16 层、A–F 方位绘成 10×6 大矩阵；每格同时展示最近 1 小时历史趋势和当前值。
- 点位合同为 `T_body_L{layer}_{position}`；层号只接受 7–16，方位支持 A–H，本次口语默认 A–F。
- 底色表示当前温度；格内曲线表示时间窗趋势；当前值、采样时刻、升降方向直接写入单元格。
- 缺测格显示灰色“无数据”，不插值；结果返回覆盖率、当前温度范围、PNG URL 和 JSON 旁车。

### 实现、测试与故障闭环

- MCP 工具：`plot_gl02_body_temperature_matrix()`；渲染器：`render_body_temperature_matrix()`；位置规范化：`normalize_body_temperature_positions()`。
- 问答路由：`qa_mcp_chart_plan()` 解析层范围、A-F/A-H 和最近时长；`qa_mcp_should_use_tools()` 在炉况上下文短路前识别确定性绘图计划。
- 首轮现网调用因“无单变量”被炉况上下文门禁提前短路，登记 `ERR-8093-MCP-BODY-MATRIX-GATE-004`；修复后按原句稳定调用专用工具。
- 60 格原始审计结果曾超过事件摘要长度，导致正确 PNG URL 未进入事件；现将紧凑单元格摘要用于问答、完整摘要写入 JSON 旁车，并为截断事件保留权威 `image_url`。
- 本地联合回归 32/32，包含 MCP schema、矩阵渲染、缺测不插值、口语参数和截断链接恢复。

### 2026-07-15 现网验收

- 原句自动验收 1/1，实际工具为 `plot_gl02_body_temperature_matrix`，实参为 7–16 层、A–F、60 分钟；报告：[8093_body_temperature_matrix_prompt_visual_final_20260715.json](../logs/8093_body_temperature_matrix_prompt_visual_final_20260715.json)。
- 最终 PNG：[gl02_body_temperature_matrix_20260715_171338_c8e8e1a5.png](../logs/gl02_body_temperature_matrix_20260715_171338_c8e8e1a5.png)，HTTP `200 image/png`，`552160` 字节；60/60 点有效，温度范围 `39.9306–114.3663℃`。
- 视觉验收确认 10×6 单元格、当前值、采样时刻、格内趋势、趋势文字和底部独立色标均完整，第 16 层无遮挡。
- 最终远端 SHA-256：代理 `A64D1862E0F3B816B45FFDBC5259632148C74D31CD349FC4794F21F4580CD527`；MCP `833F1BA9A9A00AEDD6F3F896DF30C2C2E64B953B428D0D514D0976DCA0E43E52`。
- 部署只滚动重启 `BFV4PreviewProxy8093`；`BFV4PreviewWs8768` 全程保持运行和监听。

## REQ-8093-MCP-GENERIC-SENSOR-005 任意单个/多个传感器查询与绘图

### 用户目标与边界

- 对任意已进入 GL02 映射目录的传感器，支持单点或多点当前值、历史数据、同窗统计和趋势绘图。
- 口语、标准变量名、短名、点ID、完整长名和唯一描述统一解析为标准变量；不提供任意 SQL，不越过 GL02 只读数据边界。
- 炉体温度整层简称属于多点查询：“7层炉温”展开 A–H 八点，不创建不存在的整层平均点。

### 实现合同

- MCP 新增 `query_gl02_sensors(variables, query_type, start_time, end_time, agg, max_points_per_variable, source_preference)`，支持 `latest/history/statistics` 和逐项部分失败。
- `qa_mcp_body_temperature_variables()` 支持单点、A到H、A/B/C 列举、层范围和整层默认八方位。
- `qa_mcp_catalog_variables()` 从运行期完整变量目录识别任意标准变量名及唯一目录字段；既有固定口语别名仍优先保留。
- `plot_gl02_trends(chart_type=auto)` 在单位缺失但典型数量级相差至少 20 倍时自动双轴/分面，避免多传感器原始值同轴失真。
- 配置和数据库表结构无变化；批量工具最多接受 80 个查询变量，普通趋势图最多接受 16 个变量，炉体大范围继续使用专用矩阵。

### 2026-07-16 验收

- 本地 `py_compile` 通过，MCP/路由联合回归 38/38；覆盖批量历史、部分失败、动态目录匹配、整层炉温、任意三点绘图及数量级自动分面。
- 真实 8093 新增口语 3/3：7层炉温 A–H、多类型三传感器当前值、多类型三传感器趋势图；报告：[8093_generic_sensor_access_20260716.json](../logs/8093_generic_sensor_access_20260716.json)。
- “7层炉温”实际预取 `T_body_L7_A` 至 `T_body_L7_H` 八点；“T_body_L7_A、P_top_gas_B、Q_O2”实际预取三点并返回各自时间。
- 最终绘图专项 1/1，`auto` 产出 `small_multiples`；报告：[8093_generic_sensor_chart_final_20260716.json](../logs/8093_generic_sensor_chart_final_20260716.json)。
- 最终 PNG：[gl02_generic_sensor_small_multiples_20260716_114257_ff84d6c1.png](../logs/gl02_generic_sensor_small_multiples_20260716_114257_ff84d6c1.png)，HTTP `200 image/png`，`243418` 字节，视觉验收三条曲线均清晰。
- 最终远端 SHA-256：代理 `C2A9EEE2945546E92A05249F3CA29D4D529644DE8F4C6CFE7AD31FF7089DC35C`；MCP `D1F675B42370B02A969F8950988847A3045DC3DE27436A53B3854814D36F5BE2`。
- 只滚动重启 `BFV4PreviewProxy8093`，`BFV4PreviewWs8768` 全程保持监听。

### ERR-8093-MCP-LAYER-SENSOR-GROUP-005

- 修复前“7层炉温”没有标准变量，未执行实际查询；“7层A到H”只预取 A 点并误称 B–H 未提供。
- 根因是旧 `qa_mcp_body_temperature_variable()` 只接受“炉体温度/炉身温度 + 单层 + 单方位”，多变量组规则也未覆盖炉体温度层位。
- 修复后使用复数解析函数统一展开；现网 A、B、H 单点和 A–H 整层均已证实有最新数据，因此该故障不是数据源无采样。
