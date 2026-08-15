# API 参考

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
