# 智能体工具能力评测与唯一语义点位路由设计

> 状态：设计审计，尚未实施  
> 最后核对：2026-08-13  
> 事项编号：`Q-MCP-SEMANTIC-POINT-ROUTER-20260813`

## 1. 当前结论

项目已经具备统一业务对象目录、别名匹配、目录搜索工具、多轮工具规划和跨 MCP DAG，
但还没有形成“点位唯一版本源 → 编译全部运行时产物 → 独立语义检索索引”的完整闭环。

此前所称固定 Prompt，不是预先修改模型 attention 权重，也不是应用保存了可寻址的持久 KV。
当前实现只是把身份、安全边界、回答规则和固定工艺规则放在动态上下文之前，维持稳定 token
前缀，使运行时有机会复用 KV 计算。是否命中必须用 `prompt_eval_count`、
`prompt_eval_duration` 和 TTFT A/B 观测证明。

## 2. 建议的能力评测维度

| 层次 | 核心指标 | 推荐生产门槛 |
|---|---|---|
| 点位语义解析 | exact/alias Top-1、口语 Top-1、Recall@3、歧义检出、未知点位拒识 | 精确别名 Top-1=100%；口语 Top-1≥97%；Recall@3≥99%；虚构 ID=0 |
| 工具选择 | 正确 MCP、正确工具、无关工具拒绝、并行/串行依赖正确 | 工具选择≥98%；无关工具误调≤1%；依赖顺序=100% |
| 参数构造 | 标准 object_id、时间窗、聚合、单位、方位和数组参数完全匹配 | exact-match≥99%；越权或写工具调用=0 |
| 可执行性 | MCP schema 合法、工具实际成功、结构化结果符合 output schema | 协议通过=100%；健康来源可执行成功≥99% |
| 多轮/组合任务 | 目录→查询、查询→计算、跨服务 DAG、错误恢复和停止条件 | 单次任务成功≥97%；`pass^5`≥90%；超轮次=0 |
| 答案落地 | 数值、单位、时间戳、来源、公式、引用与工具结果一致 | 数值/来源/时间戳忠实率=100%；计算误差≤1e-6或业务容差 |
| 失败安全 | 超时、缺数、部分成功、冲突数据、工具全失败、Prompt 注入 | 实时数值编造率=0；降级声明率=100%；写操作=0 |
| 性能成本 | 路由、MCP、TTFT、完成耗时、工具次数、输入/输出 token、KV 预填充 | 精确路由 p95≤100ms；语义候选 p95≤300ms；无冗余调用；一次用户请求不自动重发 |
| 并发稳定 | 6 并发、连接池、同源工具串行、跨源并行、重复调用抑制 | 死锁/PoolTimeout=0；受控重复率=0；结果隔离=100% |
| 安全审计 | owner/访客边界、Origin、只读策略、日志、凭据和工具授权 | 越权成功=0；敏感信息泄露=0；每次调用可追踪 |

其中 `pass^k` 按同一任务重复 k 次、要求 k 次全部成功的方式衡量一致性，不能只报告一次成功。
测试集必须包含简单、并行、多工具、多轮、无关工具、参数歧义、来源失败和对抗输入。

## 3. 唯一语义点位目录

建议建立一个权威目录，至少包含：

```text
catalog_version / catalog_hash
object_id                 # 唯一业务标准名，例如 P_top_A
display_name              # 顶压 A
aliases                   # 顶压A、A点顶压、A上升管煤气压力
deprecated_aliases        # P_top_gas_A，仅兼容输入
object_type               # physical_sensor / derived_metric / chemistry ...
unit
physical_point_id         # pSpace 权威长名或 IMES 对象键
source_system             # pspace / imes / postgres ...
capabilities              # latest/history/statistics/plot ...
dimensions                # furnace/position/layer/material ...
executor.server_id
executor.tool_name
executor.argument_template
status / confidence / effective_from / effective_to
source_evidence / last_verified_at
```

权威目录不保存密码或连接串。其他 TSV、MCP JSON、模型特征适配表、前端标签和测试夹具由该目录
确定性生成，并携带相同 `catalog_version/catalog_hash`，不再分别手工维护。

## 4. 推荐运行链路

```text
稳定公共 Prompt 前缀
  ├─ 身份、安全、回答和工具路由规则
  ├─ 目录合同、字段语义、歧义/拒识规则
  └─ MCP 工具 schema（稳定排序）

用户问题
  → 规则解析：标准 ID、精确别名、A-D/层号/时间窗展开
  → 目录检索：词法 + 可选独立语义索引
  → 返回 Top-K 小候选包（通常 3～8 项）
  → 模型只在候选中消歧并输出结构化 ToolPlan
  → 服务端校验 object_id、能力、只读策略和工具 schema
  → MCP 调用；独立跨源步骤并行，有依赖步骤按 DAG 串行
  → 结构化证据合并
  → 确定性计算优先；需要工艺解释时再由模型回答
```

完整目录不建议无条件塞入每轮 Prompt：目录越大，输入 token、预填充、上下文挤占和目录更新导致的
缓存失效越明显。更合适的是把稳定的目录合同和常用类别放入公共前缀，把每轮 Top-K 候选作为动态
上下文。若未来运行时提供可证明的持久模块化 KV，则可对完整目录模块做 A/B，再决定是否启用。

语义索引也不等同于大模型 attention。可优先用中文标准化、精确别名、规则展开和 BM25；只有
词法候选不足时才使用 embedding。若使用 embedding，应放在独立运行时或数据库索引，避免打破
8093/8094 单 27B 驻留边界。

## 5. 当前实现与缺口

- 已有：`business_object_catalog.py` 合并传感器和业务对象；MCP 提供
  `list_business_objects/search_business_objects/get_business_object`。
- 已有：`resolve_variable()` 接受标准 ID、历史 ID 和口语别名；未知机器 ID fail-closed。
- 已有：`qa_mcp_catalog_variables()`、模型工具规划、并行批处理和跨源 DAG。
- 已有：公共 Prompt 稳定前缀与 Ollama `prompt_eval_*` 采集。
- 缺口：目录仍由运行时变量、TSV、`sensors.json` 和专项 JSON 等多处合并，不是单一版本源。
- 缺口：没有独立的目录语义索引、候选置信度/歧义合同和端到端离线金标集。
- 缺口：没有证明“加入目录前缀”提高 KV 命中；目前只能说存在复用机会。

## 6. 实施顺序

1. 冻结 `semantic_point_catalog.v1` schema，以 pSpace/IMES 实际对象核对物理点位。
2. 合并标准名、别名、历史别名、单位、来源和 executor；检测重复别名和一对多冲突。
3. 从唯一目录生成 MCP 目录、TSV/前端标签、兼容映射和金标测试夹具。
4. 增加本地路由 API：输入口语问题，输出 candidates、confidence、ambiguity、catalog_hash。
5. 低置信度或并列候选必须追问，不允许模型自行拼写点位 ID。
6. ToolPlan 使用严格 JSON Schema；服务端按目录重新加载 executor，不接受模型自带服务器地址。
7. 建立至少 300 条中文金标：标准名、别名、错别字、A-D 组合、时间窗、跨源、未知和对抗样例。
8. 对“现状 / 全目录固定前缀 / 稳定规则前缀+Top-K候选”做 A/B；同时测准确率、
   `prompt_eval_count/duration`、TTFT、token、显存和缓存失效。
9. 通过门槛后先在 8094 预览，再按 8093 受控部署流程上线。

## 7. 参考标准

- [Berkeley Function-Calling Leaderboard](https://sky.cs.berkeley.edu/project/berkeley-function-calling-leaderboard/)：覆盖简单、并行、多工具、可执行调用和工具相关性判断。
- [τ-bench](https://arxiv.org/abs/2406.12045)：按最终状态评价多轮工具任务，并用 `pass^k` 衡量重复可靠性。
- [MCP Tools 规范](https://modelcontextprotocol.io/specification/draft/server/tools)：工具发现、JSON Schema、结构化结果、错误和确定性工具顺序。
- [Ollama FAQ](https://docs.ollama.com/faq)：KV cache 类型和并发上下文的运行边界；不构成应用已实现持久 Prompt cache 的证明。

本记录只做设计审计，没有修改或部署 8093/8094。
