# 高炉向量库 RAG 评测集说明 v2

更新时间：2026-05-08

## 1. 用途

本评测集用于衡量“高炉综合智能体”的统一知识库/向量库检索效果，重点评估：

- 意图识别是否正确。
- Top 1 / Top 3 是否命中正确知识类别。
- Top 3 是否召回预期来源文档。
- 不同难度、不同问法、不同任务类型下的检索稳定性。
- 后续优化 query rewrite、术语扩展、metadata 路由、rerank 后是否真正提升。

机器可跑测试集：

```text
高炉前端数据/智能助手/tests/bf_rag_eval_v2_queries.jsonl
```

人工示例文档：

```text
高炉前端数据/智能助手/docs/高炉向量库查询示例50条.md
```

## 2. 测试集规模

当前 v2 测试集共 150 条问题。

按任务分布：

| 任务组 | 数量 | 说明 |
|---|---:|---|
| process_qa | 25 | 工艺知识、术语、机理解释 |
| condition_diagnosis | 30 | 压差、风量、顶温、炉凉、煤气流等诊断 |
| parameter_optimization | 30 | 喷煤、富氧、风温、焦比、提产等参数协同 |
| operation_report | 20 | 班报、日报、领导汇报、边界表达 |
| fuzzy_mixed | 15 | 口语化、模糊名称、混合意图 |
| case_like | 10 | 类案例、复盘、经验教训问法 |
| safety_boundary | 5 | 不编造、不越权、不下指令边界 |
| gl02_bridge | 5 | GL02 变量名与知识检索桥接 |
| negative_control | 5 | 非业务、残缺输入、极短输入 |
| mixed_task | 5 | 解释 + 诊断 + 建议 + 报告混合任务 |

按难度分布：

| 难度 | 数量 |
|---|---:|
| easy | 28 |
| medium | 67 |
| hard | 55 |

按问法风格分布：

| 问法风格 | 数量 |
|---|---:|
| direct | 37 |
| paraphrase | 21 |
| fuzzy | 22 |
| mixed | 26 |
| boundary | 14 |
| case_like | 10 |
| safety | 7 |
| sensor_term | 5 |
| report_like | 3 |
| out_of_scope | 3 |
| malformed | 1 |
| too_short | 1 |

## 3. JSONL 字段

每行是一条独立测试用例。

```json
{
  "id": "E011",
  "group": "process_qa",
  "difficulty": "medium",
  "query_style": "paraphrase",
  "question": "只看铁水硅能不能判断即时炉况？",
  "expected_intent": "process_qa",
  "expected_categories": ["基础机理类", "工况诊断类"],
  "expected_sources": ["08-高炉主要运行指标及其意义.docx"]
}
```

字段说明：

| 字段 | 说明 |
|---|---|
| id | 测试用例编号，v2 使用 E001-E150 |
| group | 用例所属任务组，用于分组统计 |
| difficulty | easy / medium / hard |
| query_style | direct、fuzzy、mixed、boundary 等问法类型 |
| question | 用户自然语言问题 |
| expected_intent | 预期意图 |
| expected_intents / acceptable_intents | 可选，可写多个可接受意图 |
| expected_categories | 期望召回的知识类别 |
| expected_sources | 期望 Top 3 命中的来源文档 |

## 4. 本地运行命令

在 `D:\文件\服务器实际运行版` 下执行：

```powershell
$env:PYTHONIOENCODING = "utf-8"
$env:PYTHONUTF8 = "1"

python ".\高炉前端数据\智能助手\backend\run_bf_rag_testset.py" `
  ".\高炉前端数据\智能助手\tests\bf_rag_eval_v2_queries.jsonl" `
  --db-path ".\高炉前端数据\data\bf_unified_vectors.sqlite3" `
  --top-k 6 `
  --output summary
```

如果需要完整逐题结果，将 `--output summary` 改成：

```powershell
--output json
```

## 5. 2026-05-08 本地基线

当前本地向量库基线结果：

| 指标 | 结果 |
|---|---:|
| 总题数 | 150 |
| 综合通过率 | 56.7% |
| 意图识别通过率 | 66.0% |
| Top 1 类别命中率 | 74.7% |
| Top 3 类别命中率 | 82.0% |
| 平均检索耗时 | 约 64 ms |
| 最大检索耗时 | 约 1.15 s |

`220.12` 实际运行目录同步后基线结果：

| 指标 | 结果 |
|---|---:|
| 总题数 | 150 |
| 综合通过率 | 56.0% |
| 意图识别通过率 | 66.0% |
| Top 1 类别命中率 | 75.3% |
| Top 3 类别命中率 | 82.7% |
| 平均检索耗时 | 约 82 ms |
| 最大检索耗时 | 约 1.41 s |

分组结果：

| 任务组 | 通过率 | 观察 |
|---|---:|---|
| process_qa | 80.0% | 基础机理类较稳定 |
| condition_diagnosis | 63.3% | 典型诊断可用，复合诊断仍需增强 |
| parameter_optimization | 26.7% | 当前最弱，主要问题是调参意图和参数协同召回 |
| operation_report | 70.0% | 报告模板召回较稳定 |
| fuzzy_mixed | 40.0% | 口语化、模糊问法需要 query rewrite 和术语扩展 |
| case_like | 90.0% | 类案例问法能召回相近诊断知识，但真实案例库尚未结构化 |
| safety_boundary | 20.0% | 安全边界知识需要单独规则或边界文档增强 |
| gl02_bridge | 40.0% | GL02 变量名到工艺知识的桥接仍需加强 |
| negative_control | 80.0% | 非业务和残缺问题基本可控 |
| mixed_task | 40.0% | 混合任务需要先诊断、再建议、再报告的路由策略 |

## 6. 下一步优化优先级

建议按以下顺序优化，并每次优化后重复运行同一套 v2 测试集：

1. 参数优化意图识别：将“提高、降低、协调、稳妥、边界、先看哪些、怎么调”等表达优先映射到 `parameter_optimization`。
2. 参数协同召回：对喷煤、富氧、风温、焦比、燃料比、提产等词增加 query rewrite 和同义词扩展。
3. 模糊口语召回：将“炉子不顺、顶温乱、煤气走偏、想多喷点煤”等现场说法扩展为标准工艺术语。
4. 安全边界路由：把“唯一主因、确定阈值、必须立即、补未提供数值”等问题优先召回边界规则或系统提示词片段。
5. GL02 术语桥接：把页面变量、短名、描述信息映射到知识检索关键词，例如 `DP_total` 对应全炉压差、`PI` 对应透气性指数。
6. 混合任务策略：对“诊断并给建议”“解释后写报告”等问题采用多阶段检索，避免只命中单一模板。
7. Rerank：在 Top 10 初召回后，按任务类别、来源优先级和实体匹配进行二次排序。

## 7. 使用原则

这套测试集不是为了追求一次性 100% 通过，而是为了防止优化时“只改好几个演示问题，却破坏其它场景”。每次优化后应至少比较：

- 综合通过率是否提升。
- 弱项分组是否提升。
- 原本较强的 `process_qa`、`operation_report` 是否回退。
- 平均耗时和最大耗时是否仍可接受。
- 失败样例是否集中在同一类可解释问题上。
