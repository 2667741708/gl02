# API 参考

## V24 核验最新值与完成状态（2026-09-17）

QA/SSE接口、owner与同源权限不变。简单最新值对象全覆盖时返回`verified_prefetch_facts`，缺单位仍`partial`；`model_request_count=0`不表示没有预取数据库。强制指定工具仍沿用原路径。图表返回`completed`但语义失败的实例已记录，不能用终态或非空判断成功。[合同与生产复测](handoffs/2026-09-17-qa-v24-latest-reuse-and-code-boundary.md)。

## REQ-QA-STATISTICAL-SCOPE-20260917：问答统计输出范围

V22保留现有QA/SSE接口和原统计字段；描述性CV仅在满足基本计算条件时展示，温标/缺单位/非正或近零均值明确限制，原均值与标准差仍保留。`trend_consistency`上游语义仅首末与回归，答案明示该范围并另列最近15分钟，不更改原工具合同。V23只调整正常单窗观察的只读路由，无新增写接口或匿名权限。[证据](handoffs/2026-09-17-qa-v23-single-window-routing.md)。

## REQ-QA-EXCLUSIVE-USE-20260916：使用中拒绝（V21已发布）

8093问答生成入口共用一个活动名额；注册时已有未完成请求，则HTTP409返回`ok=false`、`error=assistant_in_use`、`message=智能助手正在使用中，请等待当前请求结束后手动发送。`、`retryable=true`、`automatic_replay=false`。不返回占用者身份或会话/请求ID，不进入工具或模型调用。取消信号不立即释放，实际停止后才允许新人工发送。既有鉴权、owner隔离与同源合同保留。V21已受控发布，真实双角色/取消现场验收待测；[范围与验收](handoffs/2026-09-16-qa-exclusive-use-local.md)。

## V20 指代趋势追问（2026-09-16）

规划器新增“这个/那个/这些/它们/刚才/上面”指代识别，明确新对象仍优先当前问题。V19失败的30分钟追问现走确定性统计；真实五题与数据库只读来源各5/5通过，模型趋势解释被可信守卫拒绝单列。仅更新8093代理，模型配置不变；整体33项仍执行中。[权威证据](handoffs/2026-09-16-qa-routing-v20-production.md)。

## V18–V19 多轮来源与适配器修复（2026-09-16）

公开turn投影仍精确两条消息；私有工具上下文version3携带对象/窗口各自源消息ID，来自服务端持久化user行，不接受客户端身份/来源声明。来源核验通过不能把未完成答案升级为completed。 [权威证据](handoffs/2026-09-16-qa-routing-v18-v19-production.md)。

## V17 历史复合完成合同（2026-09-16）

`completion.history_subtasks` 标记历史查询终态与 `history_status`，no_match 是已完成查询但没有匹配记录。非历史子任务使用独立证据；整体 completed 需双方完成，否则 partial。`completion_basis` 区分既有原文合同与重新校验的最新工具载荷。策略阻断历史不抹掉允许的用户数据分析。[证据](handoffs/2026-09-16-qa-routing-v17-production.md)。

## V15多章节完成合同（2026-09-16）

正式多章节请求的`completion.subsection_subtasks`逐项给出终态，并公开请求/完成数量。所有章节完整才completed；明确缺章且有已完成章节时partial，保留有效原文。独立来源及选中章节一致覆盖门在原文回答前执行；不靠模型补写缺章。最新追问不能把旧窗口平均值当当前单点。[验证证据](handoffs/2026-09-16-qa-routing-v15-production.md)。

## QA当前复合完成合同与消息投影（2026-09-16）

`POST /api/qa/chat`可选`response_projection: "turn"`只返回当前精确user/assistant两条消息，`messages_projection`明确投影方式；省略字段保留默认会话合同。owner、同源和角色边界不变。
制度复合回答包含独立`document_subtasks`与`knowledge_manifest`；未知原文或缺项令整体partial。规范实时事实完成合同包含`unit_sources`及`missing_unit_objects`，单位未登记不能声称完成。
工具/模型失败保留有界可读成功证据；不输出原始错误或将未知结构当事实。`SSE done`/答案非空不是语义通过。
实现及生产证据：[V10–V14交接](handoffs/2026-09-16-qa-routing-v10-v14-production.md)。

## MCP：2# 高炉作业日志报表

追踪编号：`REQ-SI-FUELRATIO-MES-REPORT-PERSISTENCE-20260808`。

工具：`query_bf2_operation_log_report(workdate?, limit?)`（GL02 数据 MCP）。
默认查询当天，`limit` 最大 5000。数据来自 220.12 PostgreSQL 的
`bf_imes.v_bf2_operation_log_report`，每行包含报表日期、行号、全部原始/显示单元格、批数、
煤比和按 Raqsoft 页面公式重算的燃料比。响应中的 `material_rate` 当前为 `null`，并带
`material_rate_status=semantic_unconfirmed`；工具不会把 D 列批数伪装成料速。

实现：[bf_data_mcp_server.py](../高炉前端数据/智能助手/mcp/bf_data_mcp_server.py)；数据入口
[sync_bf2_operation_log_report.py](../数据库同步和存取/sync_bf2_operation_log_report.py)；报表代理地址
为 `http://10.30.220.12:18084/demo/reportJsp/showInput.jsp?sht=mes/jn_ts_glbb_tb.sht`。

## WebSocket diagnosis.recommendation_audit

追踪编号：`REQ-RECOMMENDATION-FULL-AUDIT-20260806`

8768的 `init/tick` 帧中，`diagnosis.recommendation_bundle` 只有在完整建议批次及全部动作已经写入审计库后才返回。新增 `diagnosis.recommendation_audit`：

- `state=persisted`：数据库批次与动作行数复核通过；
- `batch_id`：`bf_assistant.recommendation_audit_batches.id`；
- `created`：本次首次写入为true，幂等复用已有批次为false；
- `immutable=true/read_only=true`：审计内容不可由运行链路更新，且不是生产控制命令；
- `condition_count/action_count/status_counts`：与数据库实际行数对应；
- `idempotency_key`：诊断、引擎和策略版本的SHA-256身份。

审计启用但数据库写入或全字段校验失败时，`diagnosis.recommendation_bundle` 不返回，`diagnosis.recommendation_status.state=failed` 且 `reason=full_audit_persistence_required`，避免页面显示没有审计证据的建议。

## GET /api/diagnosis-ai-analysis

追踪编号：`REQ-8093-8094-DIAGNOSIS-REVIEW-AI-20260806`、`REQ-8093-DIAGNOSIS-AI-FIVE-MINUTE-ANALYSIS-20260805`、`REQ-8093-DIAGNOSIS-AI-EVIDENCE-GUIDANCE-20260805`

查询参数：`label`，必填，只允许 `normal/lowline/edge/center/channel/cold/hot/column`。

用途：8093/8094免登录读取服务端当前5分钟诊断桶中所选炉况的智能分析。v3按所选 `label` 单独调用模型，不批量生成其他七类文案。浏览器不能提交诊断快照、变量、规则权重、建议或系统分。未生成时返回202和 `preparing/reasoning`；完成时返回200。

v3完成结果包含：

- `score_explanation`：使用可信数值生成的口语化分数说明；
- `key_driver_ids`：模型选择的服务端规则驱动ID；
- `variable_evidence`：服务端附加的当前值、近5分钟变化、60分钟统计、30天基线、阈值、权重和信号状态；
- `guidance_summary/recommendation_action_ids/recommendation_basis`：调剂引擎1只读建议摘要、引用ID和完整受控动作依据；
- `knowledge_chunk_ids/knowledge_basis`：知识库引用ID和可追溯资料片段；
- `evidence_contract`：数据来源、只读边界和未知ID拒绝策略。

模型不能创造变量、动作或知识ID；最终数据卡均从服务端规范上下文附加。

## POST /api/diagnosis-ai-analysis/retry

请求体：`{"label":"cold"}`。只重试服务端当前诊断桶；完成结果不重复生成，运行中请求去重，失败冷却期内返回429。接口不写人工评分，不允许上传或覆盖诊断上下文。

实现：[独立处理器](../高炉前端数据/智能助手/backend/diagnosis_ai_analysis_api.py)、[调度和模型调用](../高炉前端数据/智能助手/backend/ollama_proxy_server.py)。完整合同见[专项说明](8093_每5分钟八炉况智能分析_20260805.md)。

## POST /api/diagnosis/model-review

追踪编号：`REQ-OPT-MULTI-CONDITION-LLM-REVIEW-20260805`

用途：请求后台高炉大模型对一个确定性炉况分数做只读复核。此接口不改变诊断分数、建议动作、安全门禁、幅度、顺序或审批，不写数据库。

请求主体：

```json
{
  "force": false,
  "reviewed_label": "cold",
  "diagnosis": {
    "diagnosis_ts": "2026-08-05T03:20:00Z",
    "main_label": "cold",
    "main_score": 76,
    "secondary_label": "lowline",
    "raw_scores": {"normal": 20, "lowline": 54, "edge": 31, "center": 18, "channel": 12, "cold": 76, "hot": 9, "column": 14},
    "evidence": ["结构化规则证据"],
    "baseline_compare": {},
    "data_coverage": {"available": 27, "total": 28, "ratio": 0.964}
  },
  "diagnosis_history": [],
  "recommendation": {"goal": "只读建议目标", "actions": []}
}
```

成功响应 `200`：

```json
{
  "ok": true,
  "model_review": {
    "schema_version": "diagnosis_model_review.v1",
    "state": "completed",
    "verdict": "agree",
    "reviewed_label": "cold",
    "rule_score": 76,
    "model_support_score": 84,
    "summary": "规则分数与给定证据基本一致。",
    "supporting_evidence": [],
    "contradicting_evidence": [],
    "missing_data": [],
    "attention_items": [],
    "risk_change": "stable",
    "manual_review_recommended": false,
    "read_only": true,
    "model_meta": {"public_name": "高炉大模型服务", "cache_hit": false}
  }
}
```

错误：`400` 为请求或模型 JSON 合同无效；`502` 为模型调用失败；`503` 为 `BF_DIAGNOSIS_MODEL_REVIEW_ENABLED=0`。错误响应仍带 `read_only=true`，前端必须保留规则建议并提供重试，不能用自由文本回退覆盖规则。

缓存：默认 900 秒内按规范化诊断快照、所选炉况和内部模型身份命中；`force=true` 跳过读取缓存。缓存仅在进程内，不持久化。

## GET /api/diagnosis-core-evidence

追踪编号：`REQ-8093-8094-DIAGNOSIS-CORE-19-TRENDS-20260806`

查询参数 `label` 为八类内部炉况键之一。接口只读读取最新诊断、分钟值与基线，不调用大模型、调剂引擎或知识库，也不等待 `/api/diagnosis-ai-analysis` 完成。

响应 `evidence.schema_version=diagnosis_core_evidence.v1`，`core_variable_count=19`，`core_variable_evidence` 固定按合同顺序返回。每项包含 `id/name/unit/current_value/change_5m/change_5m_pct/baseline_30d/data_ts/source/series_60m`；曲线点使用 `ts/value`，不得补零。`T_top`由四点均值派生时 `source` 明确标记派生来源。

该接口仅负责证据查看，不创建人工评分、复核或建议事件。验证命令：`python tools\verify_diagnosis_core19_remote.py --lightweight --base-url http://10.30.220.12:8093`。


## MCP：当前炉次与时间段铁水化验

追踪编号：`REQ-MCP-IMES-HEAT-SI-SAMPLES-20260807`。

### `imes__query_current_heat_chemistry`

参数：`as_of_time?: ISO-8601`、`components?: string[]`、`include_samples?: boolean`、`furnace_id?: string`。返回正式炉次、开堵口时间、`provisional/partial_heat`、逐成分汇总和逐试样明细。当前炉次尚未结束时，平均值只覆盖查询时点已发布样本。

### `imes__query_heat_chemistry_by_time_range`

参数：`time_reference: string`、`components?: string[]`、`include_samples?: boolean`、`as_of_time?: ISO-8601`、`furnace_id?: string`、`heat_limit?: 1..24`。返回 `time_range`、`primary_heat_no`、`matched_heat_count` 和 `heats[]`；每个炉次包含匹配类型、开堵口时间及完整 `chemistry` 合同。时间范围超过 `IMES_HEAT_TIME_RANGE_MAX_HOURS` 时拒绝，默认上限 168 小时。

### 64主题知识库智能分析字段

GET /api/diagnosis-ai-analysis?label=<key> 的 analysis.recommendation_basis 当前只表示 source_mode=foreman_knowledge_only 的知识库候选建议；不再代表三规二制调控引擎。

- analysis.sensor_deviation_summary：19个核心传感器逐项当前值、近5分钟变化、30天基线、基线偏离和汇总偏离程度。
- analysis.knowledge_basis.evidence[*]：只返回 chunk_id、标题、来源和 detail_url，不在智能分析响应中返回知识正文。
- GET /api/qa/knowledge/chunk?chunk_id=<id>&format=html：只读打开指定64主题知识块正文。

## GET /api/heat-performance-quality

追踪编号：`REQ-HEAT-QUALITY-REPAIR-CLOSED-LOOP-20260807`。

只读查询一炉一行生产实绩与铁水质量汇总。支持 `limit`、`meltno`、`q`、`date_from`、`date_to`、`has_samples`。默认附加 `future_pending IS NOT TRUE`，避免把未来或双日期锚点冲突的待核验炉次进入正常生产列表。运维核验可显式传 `include_future=1`；响应 `filters.include_future` 会回显该选择。该参数只改变可见范围，不修改任何记录。

## REQ-ABC33-FURNACE-RULES-20260807

- `GET /api/furnace-rules/latest`：生产安全合同，只返回33项规则的中文名、类别、分数、四态状态、置信度、证据摘要、复核参数、处置顺序、观察窗口、审批和手册章节；不返回公式、权重、精确阈值、归一化值、贡献或内部特征名。当前批次同时返回`batch_state/evaluation_age_seconds`；评价时间缺失、未来超过1分钟或距墙钟超过20分钟时，规则分强制`null`。
- `GET /api/furnace-rules/{rule_id}/detail`：返回指定规则的生产详情，字段白名单由 `abc_rule_engine.public_rule` 固定。`principle`为该规则专属的炉况形成原理，`intervention_order`严格返回五步干预处置流程，`source_refs`返回其对应的见习高炉长手册章节；三类字段均为工艺层说明，不含评分公式、权重、精确阈值、归一化值或贡献。`sensor_review`中的`main_metrics/body_metrics/cooling_metrics/other_metrics`以`variable_name`为身份严格互斥；某指标进入`main_metrics`后不得再次出现在后续三组，四组合并仍覆盖该规则全部唯一复核指标。
- `GET /api/furnace-rules/{rule_id}/trends`：返回指定规则最近72个评分趋势点，并固定`series_scope=historical`，不得将历史点当作当前权威值。

`GET /api/diagnosis-review-context`的`context`追加`display_scores/display_main_score/score_sources/legacy_score_archive/score_contract_version`。`hot`展示源固定ABC33 B4；`raw_scores.hot`仍为legacy审计值。B4不可用时`display_scores.hot=null`，不得回退legacy。
- `GET /api/admin/furnace-rules/evaluations/{evaluation_id}/{rule_id}`：管理员权限接口，返回内部计算快照；普通会话固定403，响应 `Cache-Control: no-store`。
- `GET /api/admin/furnace-rules/config` / `POST /api/admin/furnace-rules/config/publish`：管理员读取和校验发布数值草稿；发布使用临时文件、fsync和原子替换，必须提交变更原因，普通会话固定403。
- 8768 WebSocket字段 `abc_rule_bundle` 与上述生产安全合同一致，服务端从 `abc_rule_bundle_internal` 重建，禁止把内部JSON直接透传。
# ABC33生产分数缺数语义（2026-08-08）

`GET /api/furnace-rules/latest` 与 `GET /api/furnace-rules/{rule_id}/detail` 在规则状态为 `needs_data` 时必须返回 `score: null`、`score_available: false`。禁止把A类内部暂算的100分展示为有效维护分。内部暂算分仅用于受保护的审计记录，不进入生产页面判定。

## 炉体温度红外回放 API（8892）

- `GET /api/health`：返回数据库可用状态、最新分钟时间、schema版本及可选根部代理是否安装。
- `GET /api/config`：返回层位/标高、区域、静压力物理标高、最大72小时/720帧限制及解释边界。
- `GET /api/replay?start=<时间>&end=<时间>&step_minutes=1|2|5|10|15|30&include_cohesive=0|1`：返回时间轴、80个温度点、18个静压力点、固定窗口色阶和覆盖率。默认最近6小时、5分钟步长；请求不得包含未来时间。
- 响应版本为`gl02.body-temperature-replay.v1`，来源固定为`bf_sensor.one_minute_values`。接口只读，不返回数据库连接参数。

## V20 平均 Si 影子预测 API（8093/8094）

追踪编号：`REQ-SI-V20-8093-8094-SHADOW-WORKBENCH-20260808`

- `GET /api/si-v20/status?limit=120`：模型状态、审计表状态、最近炉次和数据合同。
- `GET /api/si-v20/history?date_from=YYYY-MM-DD&date_to=YYYY-MM-DD&meltno=&limit=1000&latest_per_heat=1`：已保存预测与随后实际平均 Si、误差、±0.05 命中和汇总指标。
- `GET /api/si-v20/hourly-history?date_from=YYYY-MM-DD&date_to=YYYY-MM-DD&limit=1200`：生产整点预测汇总。每条 `hourly_schedule` 动态匹配 `requested_at` 之后最先真实开口的同高炉炉次，并返回候选炉号、实际匹配炉号、从发起/截止到开口的分钟数、实际平均 Si 和命中指标。
- `GET /api/si-v20/schedule`：读取当前生产自动预测配置、启停状态、周期、下一时间槽和最近运行结果；首次调用会幂等创建调度相关表和默认60分钟配置。
- `GET /api/si-v20/scheduled-history?date_from=YYYY-MM-DD&date_to=YYYY-MM-DD&cadence_minutes=1|10|30|60|1440&schedule_run_id=&limit=5000`：返回实时定时和历史时间槽预测曲线、候选炉次、实际匹配炉次及逐点指标。
- `GET /api/si-v20/data-readiness`：预测前返回截止时刻、特征覆盖、前1～5炉已发布平均 Si、缺失/陈旧警告和泄漏审计。
- `GET /api/si-v20/prediction-detail?prediction_id=<id>`：返回该次预测的完整输入特征快照、请求发起时间、模型合同和随后实际化验对比。
- `POST /api/si-v20/predict`：无需登录。请求含 `target_meltno`、`target_open_ts`、`cutoff_mode=now|open_minus_60|explicit`，显式模式另含 `cutoff_ts`。
- `POST /api/si-v20/hourly-predict`：按整点截止时间生成一次影子预测，保存 `request_mode=hourly_schedule`。同一高炉、同一整点截止幂等；服务器计划任务调用时无需指定目标炉号，由后端选取正式候选或推测下一炉。页面按钮只用于人工补跑当前整点。
- `POST /api/si-v20/schedule/configure`：保存生产定时配置。请求字段为 `cadence_minutes`、`enabled`和可选`furnace_no`；周期仅允许1、10、30、60或1440分钟。
- `POST /api/si-v20/schedule/dispatch`：后台分钟分发器入口；查找到期配置并生成 `scheduled_interval` 预测。同一 `schedule_id + schedule_slot_ts` 幂等。
- `POST /api/si-v20/scheduled-replay`：历史时间粒度预测。批量请求使用 `start_ts/end_ts/cadence_minutes`，指定时刻请求使用 `cutoff_ts/cadence_minutes`；单次最多5000点，输出`run_id`。
- `POST /api/si-v20/replay`：无需登录。按日期执行开口前60分钟回放，最多32天、200炉。

POST 只写预测审计，不写生产控制；非整点记录保持追加，整点记录按 `furnace_no + prediction_cutoff_ts` 幂等。V20 不检查生产登录会话；未登录请求使用审计身份 `local_operator/operator`。响应状态固定标记 `experimental_shadow`。

实际值血缘：API运行时只读取220.12本机 `bf_assistant.heat_performance_quality_summary.si_avg`；该字段上游来自IMES铁水化验，经既有同步链路落入220.12后形成每炉算术平均。API请求期间不直连IMES。

独立工作台入口：`/si_v20_workbench.html`。候选炉次来自本地 `bf_imes.raw_rows`，已完成实绩不会再作为下一炉候选；尚未开口的候选保留估计时间标签。预测审计的 `requested_at`（实际点击发起时间）与 `prediction_cutoff_ts`（模型数据截止时间）分开保存。化验到库后，历史接口用炉号并集自动补齐实际平均 Si、绝对误差和命中状态。

截至2026-08-09，本节的“双口径/整点匹配”代码已在本机完成但尚未部署到220.12；远端仍不能按该新合同宣称已严格每小时运行。

可配置调度响应仍固定为`experimental_shadow`。实时点以`requested_at`之后第一条真实开口为评价对象；历史时间槽以`schedule_slot_ts`当时或之后第一条真实开口为评价对象。改变预测周期不会写高炉设定值，也不会直接修改Windows计划任务。

## 8093 五分钟智能分析数据限制口径（2026-08-08）

`GET /api/diagnosis-ai-analysis?label=<label>` 的 `analysis.data_limits` 由服务端依据真实变量状态生成。变量存在当前有效值或 60 分钟趋势序列时，即使采样密度低于 100%，也不返回该变量的数据限制；只有当前值和趋势都不存在时才返回限制。当前提示词版本为 `diagnosis-single-condition-five-minute.v6`。

## V20严格整点预测API（2026-08-10）

- `GET /api/si-v20/strict-hourly/status`：返回当前整点、待处理/失败槽、最新严格预测、模型合同与独立常开状态。
- `GET /api/si-v20/strict-hourly/history?date_from=&date_to=&limit=`：只返回`request_mode=strict_hourly`，实际炉次使用已固化匹配，包含完成时间、数据最大时间、重试次数和命中指标。
- `GET /api/si-v20/hourly-table?date_from=&date_to=&meltno_from=&meltno_to=&limit=`：返回每个自然小时一行的预测—炉次—化验并集。优先严格整点记录，严格槽没有成功预测时才返回明确标记的60分钟临时对照；字段包含预测P10/P50/P90、匹配炉次、开堵口、逐次Si、平均Si、可用时间、误差和±0.05。响应不返回完整特征快照，详情仍走`prediction-detail`。
- `GET /api/si-v20/prediction-detail?prediction_id=`：严格整点记录额外返回初始候选、固定匹配、匹配规则、完整特征快照与各来源水位。
- `POST /api/si-v20/strict-hourly/predict`：服务器校验并补跑当前整点；忽略浏览器炉次与浏览器时钟，由服务器选择候选和整点。
- `POST /api/si-v20/strict-hourly/dispatch`：后台一分钟任务补齐/重试到期槽。失败槽保留，下一整点仍可独立创建。

旧`/hourly-history`和`/hourly-predict`仅作`hourly_schedule`兼容口径，不能作为严格整点统计来源。

## HCZ专家弱标签API（8892，2026-08-10）

- `GET /api/hcz-label-config`：返回固定标签版本、枚举、盲标合同和服务器控制的提交身份。
- `GET /api/hcz-label-context?observed_at=<时间>&start=<时间>&end=<时间>`：服务器读取实测窗口，返回知识时间模式、变量覆盖、实测快照和SHA-256；不返回HCZ模型结果。

- `GET /api/hcz-labels?start=&end=&limit=200`：按观察时间倒序读取GL02追加式弱标签，最大2000条。
- `POST /api/hcz-labels`：提交位置高低、移动方向、可选几何、可信等级、依据、备注和实际标注人。请求同源、最大64KB、幂等；模型字段、越界窗口和证据哈希变化均返回400。
- `GET /api/hcz-label-export?start=&end=&limit=`：导出UTF-8 BOM CSV。

标签响应版本为`hcz-expert-weak-label.v1`，证据版本为`gl02.hcz-label-source.v1`。POST只向`bf_assistant.hcz_expert_label_events`追加事件，不更新生产控制或传感器数据；修订通过新事件的`supersedes_label_id`表达。

## HCZ上移综合趋势经验规则API（8093，2026-08-10）

- `GET /api/hcz-upward-rule`：只读220.12本地`bf_sensor`分钟实测，返回`HCZ-UP-FOREMAN-001`在最新完整小时的判断。
- 状态为`triggered | not_triggered | insufficient_data`；响应包含`metrics`五项24小时/5天均值和差值、`body_temperature.layers`七层覆盖/升温、`sustained_trend.hours`逐小时门禁、结论和数据时间。
- 安全字段固定为`evidence_type=expert_rule_indication`、`direct_measurement_truth=false`、`calibrated_model=false`、`automatic_control=prohibited`。
- 端点无参数、无数据库写入，进程内缓存120秒。缺数不会被补0；`not_triggered`只表示未达到完整上移组合。
- 同源页面为`/hcz_upward_rule.html`。完整合同见[规则文档](./GL02软熔带上移综合趋势经验规则_20260810.md)。

### `GET /api/hcz-rule-sensitivity`（2026-08-11）

- 对最近`7 | 30 | 90`天的真实小时数据进行只读规则回放；默认90天。允许查询参数：`top_temperature_delta_c`、`total_pressure_drop_kpa`、`permeability_drop`、`gas_utilisation_drop_pp`、`cold_blast_pressure_rise_kpa`、`body_temperature_delta_c`、`min_directional_layers`、`required_consecutive_hours`。
- 返回生产默认阈值`baseline`、本次输入`scenario`、上移事件/命中小时、符号对称的下移候选以及新增/移除命中时刻。未知参数或越界参数返回HTTP 400，数据不可用返回503。
- 固定安全合同：`read_only_trial=true`、`production_defaults_changed=false`、`automatic_control=prohibited`；参数不会写入配置或数据库。下移仅为`symmetric_mirror_candidate_only`，不是已确认生产规则。
- `GasUtil`数据库值按0～1比例读取，在API入口只转换一次为0～100百分数；当前值/基线显示`%`，差值与阈值单位为“个百分点”。

## 时间序列排行榜接口（2026-08-11）

### `GET /api/timeseries/leaderboard`

- 服务：多模型旁路8778。
- 实现：[timeseries_sidecar_service.py](../tools/timeseries_sidecar_service.py)。
- 数据文件：`PT/时间序列预测评测/results/timeseries_model_leaderboard_current.json`。
- 成功：HTTP 200，`schema=bf.timeseries.leaderboard.v1`，返回公共切点、固定权重、分维度冠军和模型条目。
- 不可用：HTTP 503，返回`status=unavailable`和脱敏错误；不回退到旧排行榜或伪造空榜。
- 该接口只读，不改变8778默认模型，也不授权生产趋势页切换预测来源。

## ABC33 上下文助手

- `GET /api/furnace-rules/{rule_id}/explanation-context?evaluation_id=<id>`：公共只读、`no-store`；返回 `operator_explanation/context_hash/context_summary/stale`，不创建会话或调用模型。错误码为 `invalid_rule_id`、`evaluation_not_found`、`evaluation_rule_mismatch`、`context_incomplete`、`database_unavailable`。
- `POST /api/qa/contextual-conversations`：只接受 `source_type=abc_rule`、`source_page`、`rule_id`、`evaluation_id`、`reuse_policy`；同操作者、同规则、同8小时班次复用活动会话，`force_new`可强制新建。
- `GET /api/qa/conversations`：新增 `source_type/source_ref_id/evaluation_id/status/date_from/date_to/q/limit` 过滤。
- `POST /api/qa/chat`：上下文会话由服务端注入绑定快照；首轮设置 `analysis_mode=initial_context_explanation`，SSE POST不自动重放。

## QA 共享访客与登录合同（8093/8094）

- `POST /api/auth/login`：同源 JSON `{username,password}`，成功设置 HttpOnly 会话 Cookie；前端不得持久化密码。
- `GET /api/qa/bootstrap`：启用访客模式时，未登录返回 `access_mode=guest_shared`、固定共享会话及其带时间戳消息；同一 Host:Port 的客户端共享该会话。关闭访客模式且无有效 operator/admin 会话时才返回 HTTP 403、`error=qa_session_required`。
- `POST /api/qa/chat`：访客可提交 `conversation_id/message/current_snapshot`；服务端忽略缺失、过期或来自旧登录状态的 `conversation_id`，并重新绑定当前 Host:Port 的固定共享访客会话，避免返回 `conversation_not_found`。登录用户仍对提交的会话执行严格 owner 校验。项目、附件、手工上下文或 ABC `analysis_mode` 返回 `guest_context_not_allowed`。
- 工具失败：MCP 无法完成或达到轮数/调用上限时，服务端执行一次不带 tools 的最终模型回合；成功响应附带 `answer_route=model_without_tools_after_mcp_failure` 与 `termination_reason`，答案必须声明实时数据未核实。
- `GET/POST /api/qa/projects`、`POST /api/qa/project-assets`、`POST /api/qa/open-path`、`POST /api/qa/contextual-conversations` 和会话管理动作仍要求 operator/admin。

## MCP 炉体温度分层统计合同（8093）

- 工具：`gl02ext__query_body_temperature_statistics`，只读；QA 对匹配问题只允许一次调用。
- 输入：`start_layer/end_layer` 为 7–16，`positions` 为 A–H 子集，显式
  `start_time/end_time`，`rolling_window_minutes`，以及默认开启的 `require_all_positions`；
  单次最多覆盖 80 个点，时间窗不超过 24 小时。
- 逐层输出：对齐分钟数/期望分钟数/覆盖率、AVG、STDDEV_POP、min、max、range、first、last、
  delta、每分钟 slope、CV；滚动标准差与滚动极差分别返回首末、变化、最小、最大和趋势。
- 单点输出：同一统计口径，同时返回 raw/expected/missing/nonfinite/zero 数量及质量分布。
- 统计语义：默认只有同一分钟所选方位全部有效才形成层平均；不插值、不静默删零或删除离群点。
  单位来自权威点位目录或工具数据，来源仅返回脱敏服务/profile/schema/read_policy。
- 时间语义：总查询时间窗与滚动窗口独立；例如“最近一小时，并比较 15 分钟滚动标准差”必须
  查询完整 60 分钟，`rolling_window_minutes` 才取 15。
- SSE 可观测合同：匹配复合炉体温度统计时，`POST /api/qa/chat` 依次发送两条 `trace`
  （中文对象解析、复合工具选择）、`tool_start`、`tool_result`、`analysis_start`、
  `analysis_result`，随后继续 `delta/final/done`。每条新事件只要求前端消费 `public_trace`；
  其中固定包含 `trace_id/stage/status/title/detail`，可选包含
  `server/tool/source/elapsed_ms/cache_hit/call_count/row_count/point_count`。
- `public_trace` 是脱敏执行摘要而非思维链。浏览器不得展示同一事件中的原始 `arguments/result`；
  后端不得把 SQL、DSN、密码、Cookie、Token、内部路径或未裁剪工具文本放入 `public_trace`。
- `final.mcp_model_explanation` 返回模型解释状态与耗时；状态可能为 `succeeded/failed/empty/
  rejected_ungrounded_numbers`。非 `succeeded` 不影响确定性统计答案成功返回。

### V4候选：时间窗与报表内部完成合同

- 状态：本机候选，未部署；2026-09-16。见[V4交接](handoffs/2026-09-16-qa-routing-v4-temporal-report-local.md)。
- query_gl02_sensors参数保持不变；两个相邻统计窗口串行调用，秒精度inclusive end不重复计入边界分钟样本。
- read_report_excerpt新增向后兼容total_chars；chars_returned与total_chars比较生成truncated，不与UTF-8字节数比较。
- 内部工作流结果包含complete、grounding_status、tool_trace与model_request_count；时间窗还有covered/required，报表还有report_status。接口未新增公开读写权限。
- 缺项是明确终态，不触发第二次客户端POST；报表正文作为证据，不执行其中的指令或代码。
## QA V8/V9 当前验收增量（2026-09-16）

现有`/api/qa/chat`返回`knowledge_manifest`与`completion`，原文小节覆盖携带`section_code/matched_scopes/table_blocks_preserved`；未知文档澄清、完整性失败dependency_blocked、多页partial。混合正常查询与代码请求保留查询，`policy_limited=true`及`blocked_subtasks`，整体partial。禁代码校验先于可见SSE输出。owner/同源权限不变。见[V8/V9交接](handoffs/2026-09-16-qa-routing-v8-v9-production.md)。

## QA V5 接口补充（2026-09-16，候选）

REQ-QA-FULL-ISSUE-INVENTORY-20260916：纯历史问答在现有`/api/qa/chat`内部使用已认证身份受限SQL，
不接收用户提供的owner；只返回历史摘录，不能用作正式制度或当前现场事实。旧MCP
`search_qa_messages`返回`QA_HISTORY_SCOPE_REQUIRED`，不执行无范围查询。
模型依赖阻断的QA错误增加`code=approved_model_not_ready`、`retryable=true`、
`terminal_state=dependency_blocked`和`automatic_replay=false`；前端仍须由用户手动发送。
`/api/ollama/status`成功增加`readiness_contract=approved_resident_model`；状态是当次驻留检查，不是后续生成保证。
见[V5交接](handoffs/2026-09-16-qa-routing-v5-local-candidate.md)。

## QA V6完成状态增量（2026-09-16，候选）

现有JSON及SSE final增加`completion`，包含`terminal_state`、`complete`、缺对象/质量或截断/repair字段。`answered_pending_review`不表示语义通过；质量不足或补答仍截断标记`partial`。内部压缩补答最多一次，外部SSE POST不自动重放。单点预取回答固定对象、采集时间、单位与来源，不宣称正常、匹配或历史趋势。[权威交接](handoffs/2026-09-16-qa-routing-v5-production-and-v6-candidate.md)。

## V25智能助手更新与首次全题统计（2026-09-17）

状态：V25已部署；首次1233题判定已合并。最新权威方案见 [33项优化与核对方案](handoffs/2026-09-17-qa-full-optimization-plan.md)。

明确钟点/跨午夜窗口不回落最近一小时，历史记录和质量保留；18点绘图已进入正确路由，但生产工具只返回16点且生命周期降级遗漏图，仍待修复。

本机159检查、14黄金题结构、4写24读/490 AST/22标记、8093受控发布和CAS通过。新版822原失败/部分题复测只发1题且失败，821题证明未发。首次完整正确269/可判1091=24.66%，不能报告优化后全量准确率。

## V26图表证据修复及固定模型复测（2026-09-17）

状态：V26已部署，174本机检查和独立审查通过；822原失败/部分题发送前因Qwen身份变化拦截，零发送。线上语义修复效果未确认。
需求：REQ-QA-CHART-COVERAGE-20260917、OPS-QA-FIXED-MODEL-WINDOW-20260917。
最新权威来源：[V26部署与固定模型复测方案](handoffs/2026-09-17-qa-v26-model-window.md)、[33项优化方案](handoffs/2026-09-17-qa-full-optimization-plan.md)、[V26生产哈希](../tests/qa_regression/routing_v26_production_20260917.json)、[822未发题证据](../tests/qa_regression/routing_v26_unattempted_dependencies_20260917.json)。
执行器见 [窗口owner](../tools/run_qa_fixed_model_window.ps1)、[独立启动器](../tools/start_qa_fixed_model_window.ps1)、[只读准备器](../tools/prepare_qa_fixed_model_window.py)；11项真实控制流/截止预算隔离测试通过，另有8项身份/续跑合同回归通过。窗口仅本机准备，计划任务操作尚未授权执行；继续保留V25历史记录，不以非空答复计算正确率。

## 历史：模型恢复稳定性本机候选（2026-09-17，已取代）

需求OPS-QA-MODEL-REPAIR-STABILITY-20260917，关联QAOPT-O01。健康批准驻留优先、候选失败alias/state恢复、最长15分钟冷却、暂停失败恢复责任及Switch实际alias回滚已形成r2本机候选；32其他函数和顶层mutex/dispatch保持，26隔离回归与独立代码审查通过，未部署管理器。
当前生产仍为V26，822失败/部分题均未发送。真实任务/模型验收和管理器变更独立授权仍待完成；本机检查不等同线上语义成功。
权威来源：[候选和26项证据](handoffs/2026-09-17-qa-model-repair-stability.md)、[候选冻结元数据](../tests/qa_regression/model_repair_stability_candidate_20260917.json)、[构建器](../tools/build_qa_model_repair_candidate.ps1)、[聚焦回归](../tests/test_qa_model_repair_policy.py)。

## REQ-QA-SINGLE-BASE-MODEL-20260917：固定同一底座

状态：本机候选52项检查及独立审查通过，未部署；生产仍V26。唯一e4ad74…底座，Switch/替代fallback禁用，每次模型POST与复测plan核验相同digest；旧双批准池窗口已停用。恢复任务仍曾自行漂移版本0，不能声称生产已锁定。管理器/计划任务维护独立授权，安装失败不能再启用旧切换策略。
当前权威：[单底座合同、代码和验收方案](handoffs/2026-09-17-qa-single-base-model-policy.md)、[候选冻结证据](../tests/qa_regression/single_base_model_candidate_20260917.json)。前代r2批准fallback候选仅保留历史复现，禁止部署。

## REQ-QA-STATISTICS-EVIDENCE-20260917：V28统计证据与答复

状态：本机候选，生产仍为V26；最后核对2026-09-17。关联QAOPT-E01/E02/E03/E04/E05。
V28保留固定同一底座身份检查，仅修复统计预取、证据完整性和确定性答复三个函数。完整保留stddev/单位/质量及来源窗口；非零微量不舍入成0；缺单位仅继承现有精确合同并披露，Held端点不证明整窗质量或炉况稳定。直接答复同样校验请求对象、来源和时间窗，未核实不得输出正式STDDEV/CV/趋势。没有新增API或配置，不改模型、生产数据库或ABC33合同。
权威：[实施、回归及未完成项](handoffs/2026-09-17-qa-v28-statistics-evidence.md)、[机器检查证据](../tests/qa_regression/statistical_evidence_candidate_20260917.json)、[实际函数回归](../tests/test_qa_statistics_evidence.py)。本机通过不得写成线上准确率提高；822原失败/部分题尚未发送。

## REQ-QA-FINAL-COMPLETION-20260917：V29最终答复完成状态

状态：本机r2候选、92项聚焦回归及独立审查通过，未部署；最后核对2026-09-17，关联QAOPT-E05/O04/T03。
统一识别模型截断、未知终止、空答案和末行空标题；工具后解释未完成时保留事实并标部分，MCP降级仍最多一次无工具回合。普通免工具问答保留原有一次有界补答；JSON/SSE核对实际最终answer，图表/文档追加不能擦除已记录的空标题。固定底座、V28统计合同及其他AST保留，无新增配置、工具重试或数据库变更。
权威：[实施、实际检查及剩余边界](handoffs/2026-09-17-qa-v29-final-completion.md)、[候选机器证据](../tests/qa_regression/final_completion_candidate_20260917.json)、[真实函数回归](../tests/test_qa_final_completion.py)。处理器接缝为AST与合同检查，尚未执行线上处理器/822原题语义验收；这些问题未销项。

`completion.incomplete_reasons`为可选字符串数组；本轮原因包括output_limit、termination_unverified、empty_answer、unfinished_heading、stream_incomplete、model_analysis_incomplete。发现明确不完整证据时terminal_state=partial、complete=false；保留原合同中的covered/missing及子任务字段。新模块默认schema=qa-completion-v2，既有结构化执行器的schema继续原样保留。answered_pending_review不等于语义通过，semantic_review_required继续为true；不增加新的API端点或重发指令。

## REQ-QA-WINDOW-QUALITY-20260917：V30统计质量合同

状态：本机r2候选，102项相关回归及独立审查通过，未部署；最后核对2026-09-17。
普通传感器完整统计可新增statistics.quality_summary：schema=qa-window-quality-v1、scope、basis、sample_count、counts与whole_window_verified。counts固定Good/Held/Bad/Uncertain/DERIVED_AVERAGE/Unknown非负整数，和必须等于原统计count。数据库scope=queried_window、basis=non_null_values，另提供observed_rows/excluded_rows/start_time/end_time，并绑定同一请求窗；该标记不证明物理采样覆盖或新增实测。序列scope=returned_samples、basis=returned_numeric_rows、whole_window_verified=false，不把有限返回结果当整窗完整。无有效质量计数或窗口不匹配时继续说明质量未核实；没有新增工具名、端点、重试或模型切换。
权威：[实现、范围及未验收项](handoffs/2026-09-17-qa-v30-window-quality.md)、[机器回归证据](../tests/qa_regression/window_quality_candidate_20260917.json)、[实际函数回归](../tests/test_qa_window_quality.py)。SQL与最终答案本轮未在生产验证。


## REQ-QA-RENDERER-CONTRACT-20260917：V31答复格式与字段兼容

状态：本机冻结候选、126项相关回归及独立审查通过，未部署；最后核对2026-09-17，关联QAOPT-E02/E03/E05。
传感器字符串列表按实际工具拆分、去重，保持80个上限，请求与外层结果规范化列表必须一致；顶层字符串和非字符串项不放宽为合法调用。单位仅从明确元数据绑定继承规范合同并披露，原单位优先、不换算或猜描述。异常结果容器逐项明示并保留相邻有效事实；对象、来源、只读策略与窗口门禁保持。仅修改一个代理函数和统计证据模块，无新增API、配置、工具或模型回合，固定同一底座保持。
权威：[确认缺陷、程序与未完成验收](handoffs/2026-09-17-qa-v31-renderer-contract.md)、[机器回归证据](../tests/qa_regression/renderer_contract_candidate_20260917.json)、[实际冻结函数回归](../tests/test_qa_renderer_contract.py)。本机通过不能用于线上准确率或问题销项；禁切换管理器安装、8093部署及822原题复测仍待完成。


## REQ-QA-LATEST-EVIDENCE-20260917：V32最新值与完成合同

状态：本机r2冻结候选、284项相关回归及独立审查通过，未部署；最后核对2026-09-17。
completion新增可选missing_evidence_fields对象，按对象列出unit、quality_meaning、collection_time、readonly_policy或derived_component_alignment缺项；保留covered_objects/missing_objects。缺字段是partial，非空不算通过；完整最新值读取也不能使所需分析标完整。最新答复写最近已保存值，不冒充此刻无异常；采集/接口标记不等于物理采样。没有新增端点或重试。
权威：[确认缺陷、实现及生产依赖](handoffs/2026-09-17-qa-v32-latest-evidence.md)、[机器证据](../tests/qa_regression/latest_evidence_candidate_20260917.json)、[实际函数回归](../tests/test_qa_latest_evidence.py)、[九条提出归类补充](../tests/qa_regression/unmapped_triage_supplement_20260917.json)。本轮0线上问题，不改首次1233题判定，822原题复测仍待完成。


## REQ-QA-ORIGINAL-SOURCE-READER-20260917：制度原书读取门禁

状态：2026-09-17本机验证/复审并冻结，生产未接入。

未增加HTTP路由。制度答复completion.coverage.original_source包含来源范围/数据库快照核验与摘要；未核来源completion.terminal_state=dependency_blocked，不补写正式条款；综合数据+制度中数据可保留、总体partial。分页partial仍不等同全问题完成，来源通过仍semantic_verified=false。

当前权威：[读取门禁交接](handoffs/2026-09-17-qa-original-source-reader.md)、[脱敏机器证据](../tests/qa_regression/original_source_reader_20260917.json)。291项入口报告是历史阶段，完整源发布及822原题现场验收尚未完成。


## REQ-QA-FORMAL-DOCUMENT-SCOPE-20260917：书名与全部请求范围

状态：2026-09-17本机378项/复审及V34-r1冻结，生产未应用。

无新路由。书名未知在任何DB查询前needs_clarification/document_reference_unresolved；chapter_unknown、chapter_range_invalid、chapter_reference_conflict明确澄清。已请求岗位在规程筛选后缺失时保留可读原文，terminal_state=partial，coverage含requested_chapters/available_chapters/missing_chapters；available是范围可用数，不冒充当前页全部已回答。

当前权威：[范围修复交接](handoffs/2026-09-17-qa-document-scope-resolution.md)、[脱敏机器证据](../tests/qa_regression/document_scope_resolution_20260917.json)。V33/356项为前阶段快照；822原题现场验证未完成。


## REQ-QA-DOCUMENT-REGULATION-SCOPE-20260917：条款规程范围与逐项覆盖

状态：2026-09-17本机400项/复审通过，V35-r1冻结，生产未应用。

无新HTTP路由。coverage新增missing_regulations_by_chapter/excluded_regulations_by_chapter；多原子结果含missing_regulations/ambiguous_regulations及page/pages。唯一内容与缺项并存时partial；矛盾范围regulation_scope_conflict澄清。整表保留，单页不冒充所有页已答；全结果严格JSON可序列化。

当前权威：[规程范围交接](handoffs/2026-09-17-qa-document-regulation-scope.md)、[脱敏机器证据](../tests/qa_regression/document_regulation_scope_20260917.json)。V34/378项保留为历史阶段；822原题现场复问未完成。


## REQ-QA-FIXED-MODEL-OVERRIDE-20260917：唯一固定底座禁止参数覆盖

状态：2026-09-17本机61项/独立审查通过，V36-r1冻结，生产未应用。

无新路由或错误码。非固定name/digest入口参数立即FixedModelUnavailable，code=fixed_model_identity_not_ready，不访问上游。显式同pin继续GET tags→ps→tags/单驻留核验，模型请求体的调用方model仍被代理替换为固定身份；身份漂移阻断后续生成。

当前权威：[固定参数门交接](handoffs/2026-09-17-qa-fixed-model-override.md)、[脱敏机器证据](../tests/qa_regression/fixed_model_override_20260917.json)。源/制度前阶段以V35报告保留；822原失败partial题0复问。


## REQ-QA-COMPOUND-SOURCE-SCOPE-20260917：复合子任务与来源禁令

状态：2026-09-17本机557项相关回归及独立审查通过，V37-r2冻结，生产未应用。

无新增HTTP接口。正式原文入口在任何SQL前检查all_tools_disabled，返回dependency_blocked/document_lookup_policy_blocked；明确原文未读取。全局禁令传播到制度子句和历史remainder；仅禁止现场查询仍允许对应历史/报表工具。历史读取保留owner和当前消息ID截止。

权威：[逐项交接](handoffs/2026-09-17-qa-compound-source-scope.md)、[脱敏证据](../tests/qa_regression/compound_source_scope_20260917.json)。0生产销项，原题准确率未验证。


## REQ-QA-MATH-FUNCTION-POLICY-20260917：正常数学函数问答

状态：2026-09-17本机225项相关回归/独立审查通过，V38-r2冻结，生产未应用。

无新增HTTP接口；正常数学不再被code_disabled短路。混合数学+代码保留正常子任务，完成状态partial/policy_limited及blocked_subtasks=code_generation_or_execution保持。

权威：[逐项交接](handoffs/2026-09-17-qa-math-function-policy.md)、[脱敏机器证据](../tests/qa_regression/math_function_policy_20260917.json)。本轮0助手模型调用/生产写入/原题发送/销项。


## REQ-QA-USER-DATA-SOURCE-SCOPE-20260917：用户给定数据与外部来源范围

状态：2026-09-17本机286项相关回归/独立审查通过，V39-r3冻结，生产未应用。

无新增HTTP接口。任务计划区分user_message与live_readonly_data，原始问题保留给最终答案及子任务完成校验；仅向prefetch/对象/时间解析传递外部子句。明确全局工具禁令保持tool_policy_conflict。

权威：[逐项交接](handoffs/2026-09-17-qa-user-data-source-scope.md)、[脱敏机器证据](../tests/qa_regression/user_data_source_scope_20260917.json)。本轮0助手模型调用/生产写入/原题发送/销项。
