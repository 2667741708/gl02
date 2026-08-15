# 智能体工具能力评估与 153 点位稳定 Prompt 路由方案

> 状态：当前设计与本机验收基线  
> 最后核对：2026-08-13  
> 需求编号：`REQ-MCP-SEMANTIC-POINT-CATALOG-20260813`

## 1. 当前结论

权威 `点位清单.tsv` 当前有 **153** 条变量记录，其中正好是 **151 个物理点位 + 2 个派生变量**；
因此用户记忆中的“约151种点位”是正确的物理点位口径。两个派生变量为 `T_top`（顶温 A-D 平均）
和 `PCI_current_hour`（本小时喷煤积分）。其中包含 80 个
`T_body_L7_A`～`T_body_L16_H` 炉体温度点、顶温/顶压/静压等常用点，以及软水、高压水、
氮气、荒煤气成分和喷煤小时量等低频点。

已经为全部 153 条变量生成版本化语义目录：每条包含物理/派生类型、唯一标准 ID、中文显示名、至少两个短别称、
四个完整口语问法和物理来源。目录不包含密码、数据库连接串或可写能力。

本机严格评测结果：

- 运行时覆盖：`153/153`；
- 短别称精确解析：`1118/1118`；
- 每点首个完整口语问法唯一解析：`153/153`；
- 六类多点比较/计算路由：`6/6`，集合和顺序严格一致；
- 未知虚构点位：拒绝；
- 精确别称解析 p95：约 `0.430 ms`；
- 聚焦代码回归：`19 passed`。

这些数据证明本地目录、路由和工具参数合同通过；不代表 153 个物理数据源均已在生产逐条实取。
生产实取应抽样覆盖点位族与低频来源，避免发送 153 次模型请求。

## 2. 稳定公共 Prompt 的正确做法

应用没有固定模型内部 attention 分数，也没有保存可按目录哈希直接加载的持久 KV 文件。
当前方案维持相同 token 前缀，让运行时有机会复用 KV：

```text
固定身份与安全边界
→ 固定回答规则
→ 固定工具使用和只读规则
→ 固定语义目录合同（字段、歧义、拒识、ToolPlan schema）
→ 固定顺序的 MCP 工具 schema
→ 动态 Top-K 点位候选
→ 动态实时数据/MCP 结果
→ 对话与当前问题
```

不把完整 153 点目录无条件塞进每轮 Prompt。服务端先用标准 ID、别名和族规则确定性检索，
只把少量候选交给模型消歧。这样避免目录更新使大段公共前缀失效，也减少 token、预填充和上下文
挤占。是否真正复用 KV，仍须用 `prompt_eval_count`、`prompt_eval_duration` 和 TTFT A/B 证明。

## 3. 问答与 MCP 路由

```text
用户口语问题
→ 标准化但不删除上/下、前/后、本/上小时等区分词
→ 标准 ID / 唯一别名 / A-H 方位 / 7-16 层规则展开
→ 输出唯一点位或严格有序多点列表
→ 服务端根据目录选择只读 MCP 工具和参数
→ 独立来源并行，同一 stdio 服务串行
→ MCP 结构化结果
→ 确定性计算（均值、差值、比值、最大最小）
→ 模型只解释已确认事实
```

安全抑制规则包括：

- 物理 `P_static_20m35/23m49/28m98` 命中时，不重复调用旧 `*_mean` 兼容 ID；
- 上小时、本小时和实时喷煤量严格区分；
- 阀前与阀后富氧压力严格区分；
- 无方位的单独标高（如“16.860m”）有一对多歧义，不作为可执行别名；
- 未知机器 ID 和虚构口语点位 fail-closed，不做模糊硬猜。

## 4. 资产与维护

- 权威输入：`数据库同步和存取/config/点位清单.tsv`（151个物理点位、2个派生变量）。
- 语义伴生目录：`数据库同步和存取/config/点位语义目录.json`。
- 生成器：`tools/generate_semantic_point_catalog.py`。
- MCP 加载与解析：`高炉前端数据/智能助手/mcp/bf_data_mcp_server.py`。
- 问答路由：`高炉前端数据/智能助手/backend/ollama_proxy_server.py`。
- 评测 skill：`.codex/skills/agent-tool-capability-evaluation/`。
- 全量回归：`tests/test_semantic_point_catalog.py`。
- 机器报告：`logs/agent_tool_capability/semantic_point_catalog_evaluation.json`（运行产物）。

物理清单变化后执行：

```powershell
$env:PYTHONUTF8='1'
py .\tools\generate_semantic_point_catalog.py
py .\tools\generate_semantic_point_catalog.py --check
pytest -q .\tests\test_semantic_point_catalog.py
py .\.codex\skills\agent-tool-capability-evaluation\scripts\evaluate_semantic_point_catalog.py
```

如果别名碰撞，生成器删除歧义别名并在 `removed_alias_collisions` 记录；维护人员必须补充带方位、
层号或时间口径的唯一表达，不能通过降低匹配阈值绕过。

## 5. 十类能力门禁

固定评测语义解析、工具选择、参数构造、可执行性、多轮/组合、答案落地、失败安全、性能成本、
并发稳定和安全审计。实时数值编造、未授权写入、身份隔离失效、凭据泄露或错误自动重放均为
直接阻断，不能用总分抵消。详细评分以 skill 的 `references/evaluation-rubric.md` 为准。

## 6. 生产后续验收

本轮没有部署 8093/8094。上线前应按点位族分层抽样，而不是 153 次模型问答：

1. 顶温/顶压 A-D；
2. 炉体温度每层至少一个点并覆盖 A/H 边界；
3. 三层静压及 A/F 边界；
4. 热风/冷风、压差、透气性、喷煤与富氧；
5. 软水/高压水/氮气等低频来源；
6. 一次多点比较和一次跨 MCP 组合计算；
7. 一次不存在点位和一次数据源失败降级。

部署必须使用 8093 受控更新 skill，并分别报告路由通过、MCP 实取通过和模型答案忠实通过。
