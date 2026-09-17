# 数据结构参考

## REQ-QA-WINDOW-QUALITY-20260917：统计质量摘要

状态：V30本机r2候选，未部署；最后核对2026-09-17，不增加表、列或迁移。
statistics.quality_summary提供固定标签的样本计数；数据库非空值为分母，observed_rows与excluded_rows分别表示匹配行及未进入比例的空值行。schema/basis/计数一致性/请求窗口均需验证；queried_window仅表示SQL匹配行全量计数，不表示采样覆盖。序列returned_samples保持whole_window_verified=false，不声称源窗口完整。未知质量不猜测为Good，派生平均不代表物理传感器质量。字段权威：[API合同](api_reference.md)、[实现与验收边界](handoffs/2026-09-17-qa-v30-window-quality.md)。

## REQ-QA-FINAL-COMPLETION-20260917：普通问答完成合同

状态：V29本机候选，未部署；最后核对2026-09-17。不增加表、列或数据库迁移。
公开completion新增可选incomplete_reasons字符串数组，记录长度上限、未确认终止、空答案、空标题、流式未完成或模型分析未完成；有明确缺项时complete=false、terminal_state=partial。保留已有对象覆盖、子任务和来源字段，不根据非空文本升级为completed。新普通模型模块schema=qa-completion-v2；既有确定性执行器合同schema原样保留。权威：[API字段与行为](api_reference.md)、[实施及回归边界](handoffs/2026-09-17-qa-v29-final-completion.md)。

## `bf_sensor.sensor_registry` 罐重设定目录（2026-08-14）

`Hopper_weight_set_01`～`Hopper_weight_set_11` 是 pSpace 物理分量，分别对应
`SIO_GL02_LD_T0115/T0116/T0117/T0119–T0126`；`Hopper_weight_set` 是目录中的派生项，
语义为 11 个分量在同一分钟的状态和，单位 t。`T0118` 为布料圈数设定，不能作为重量分量。

目录登记不等于派生事实已物化：当前 11 个物理分量已有 `raw_5s_values` 和
`one_minute_values`，派生项尚无分钟事实。后续物化必须使用同一分钟状态、允许受控前向保持，
并在任一分量缺失时输出缺数状态而不是补零。追踪：
`OPS-SENSOR-REGISTRY-HOPPER-WEIGHT-SET-20260814`。

## `bf_sensor.coal_injection_hourly`（2026-08-06新增）

2号高炉整点喷煤记录，一小时一行。`metered_amount_t`来自确认点`SIO_GL02_PC_T0004`并归属上一完整小时；`integrated_amount_t`由`PCI_rate`分钟值按实际`interval_seconds/3600`积分；`average_rate_tph`保存小时平均速率，`coverage_ratio`保存有效覆盖率，缺测不补零。完整小时视图优先实测累计，当前小时视图使用速率积分。详见[工长趋势2号炉点位与整点喷煤量](工长趋势2号炉点位与整点喷煤量_20260806.md)。

## `bf_imes.imes_bf2_operation_log_report` / `bf_imes.v_bf2_operation_log_report`

追踪编号：`REQ-SI-FUELRATIO-MES-REPORT-PERSISTENCE-20260808`

220.12 已存在 2#高炉“冀南新区高炉作业日志”小时行镜像表和数值视图。2026-08-08 只读审计确认：宽表/视图共有 `4320` 行，覆盖约 `180` 天 × `24` 小时；保存了 `report_pulverized_coal`、`report_coal_ratio`、`report_fuel_ratio`、`report_batch_count`、`report_ore_batch`、`report_coke_batch`、`report_coke_breeze`、`report_moisture`、`report_headers`、`report_cells` 等字段。`report_fuel_ratio` 和 `report_coal_ratio` 来自 Raqsoft 页面公式复算，不是普通 IMES JSON 字段。

当前边界：该表只保存作业日志小时操作行 `7–32`，不保存“炉前出铁情况”块，因此没有报表内 `Si` 字段；`material_rate` 当前为 `NULL` 且 `material_rate_status='semantic_unconfirmed'`，同步脚本明确说明“报表D列语义为批数；未将批数直接当作料速”。若现场确认“料速”公式，应新增版本化派生字段或分析表，不能静默改写历史语义。

建议新增但尚未执行 DDL 的对象：

- `bf_imes.imes_bf2_operation_log_heat_block`：保存报表炉前出铁块中的炉次、开堵口、C/Si/Mn/P/S/Ti 和原始单元格；
- `bf_assistant.foreman_fuel_ratio_si_features`：保存工长燃料比经验法按炉次/cutoff 计算出的基准燃料比、当前前4小时燃料比、预测 Si、实际 Si 和命中指标；
- `bf_assistant.foreman_fuel_ratio_rule_versions`：保存 `5 kg/t -> 0.1% Si`、基准天数、默认基准 Si 等公式版本。

调度边界：220.12 已注册 `IMESBF2OperationLogReport5m`，每 5 分钟读取当天报表；2026-08-08
验收 `LastTaskResult=0`，日志显示当天 `24` 行。历史回填入口为
`数据库同步和存取/sync_bf2_operation_log_report.py`，按 `workdate + report_row_number`
幂等更新，异常日期可单独重跑。

完整检查和页面设计见[工长燃料比经验法数据落库与页面方案检查](../PT/预测铁水Si含量/docs/fuel_ratio_report_persistence_page_plan_20260808.md)。
报表同步已完成迁移、历史回填与计划任务上线；炉前出铁块/Si 仍是后续独立数据面，不能从当前作业日志行推断。

## bf_assistant.recommendation_audit_batches / recommendation_audit_actions

追踪编号：`REQ-RECOMMENDATION-FULL-AUDIT-20260806`

`recommendation_audit_batches` 保存八炉况完整原始建议包、诊断输入、当前核心变量、数据质量、引擎/策略谱系及输入输出SHA-256；`recommendation_audit_actions` 把每条建议物化为独立审计行。批次按诊断快照、引擎版本与策略哈希幂等，首次写入后不更新、不删除。

| 对象 | 关键字段 | 语义 |
|---|---|---|
| 批次身份 | `id/idempotency_key/furnace_id/diagnosis_snapshot_id/diagnosis_ts` | 一个诊断与一版策略的不可变建议决策 |
| 输入证据 | `diagnosis_payload/current_values/data_quality/source_context/input_payload_sha256` | 生成建议时实际使用的完整诊断、核心变量和质量边界 |
| 引擎谱系 | `engine_name/engine_version/recommendation_schema_version/policy_source/policy_sha256` | 证明由哪版程序和哪份三规二制策略生成 |
| 完整输出 | `condition_count/action_count/status_counts/recommendation_payload_sha256/recommendation_bundle` | 八炉况及全部动作的原始无损JSON |
| 动作定位 | `batch_id/condition_label/condition_score/condition_role/condition_scope/action_id/status` | 区分当前、辅助、假设炉况和四种动作状态 |
| 动作审计 | `source_refs/trigger_evidence/required_inputs/preconditions/blocking_reasons/delta/sequence_plan/missing_inputs/observation_window/approval` | 可直接查询的完整建议依据与执行边界 |
| 原始保真 | `action_payload/action_payload_sha256/read_only` | 保留引擎完整原始动作对象并固定为只读建议 |

运行写账号只具有新表 `SELECT/INSERT` 和序列使用权；只读账号只具有 `SELECT`。表间外键使用 `ON DELETE RESTRICT`，不存在级联清除审计证据。

## bf_assistant.heat_performance_quality_summary

追踪编号：`REQ-8093-HEAT-PERFORMANCE-QUALITY-20260806`

该表是从 IMES 正式炉次、生产实绩和铁水化验派生的一炉一行事实表，主键固定为正式 `meltno`。原始试样仍以 IMES `t_qpes_inner_batch.heatno + batchno -> inner_batch_insp_bb.batchno` 为权威来源，聚合表的均值、中位数和范围不得覆盖或替代原始记录。定义、读写边界和质量描述位于 [heat_performance_quality.py](../高炉前端数据/智能助手/backend/heat_performance_quality.py)，增量/全量同步入口为 [sync_22012_heat_performance_quality.py](../tools/sync_22012_heat_performance_quality.py)。

| 字段组 | 主要字段 | 含义 |
|---|---|---|
| 炉次锚点 | `meltno/furnace_no/work_date/open_ts/close_ts/duration_minutes` | 正式炉次号及 8093 默认使用的有效开堵口时间；异常炉次使用修复后时间 |
| 时间修复审计 | `raw_open_ts/raw_close_ts/repaired_open_ts/repaired_close_ts/time_anomaly_reasons/repair_checked_at/future_pending` | IMES 原始时间、有效修复时间、结构化原因、核验时刻与待核验隔离标记 |
| 矿批实绩 | `batch_start/batch_end/batch_count` | 该炉次记录的矿批起止和批数 |
| 出铁实绩 | `theory_iron_qty/actual_iron_qty/gross_weight_total/tare_weight_total/net_weight_total/output_count` | 理论/实绩铁量以及称量汇总；原始称量保存在 `output_details` |
| 每炉化验均值 | `c_avg/si_avg/mn_avg/p_avg/s_avg` | 该正式炉次全部有效试样的算术平均值，缺失保持 `NULL`，不得补0 |
| Si分布 | `si_median/si_min/si_max/si_spread/si_band` | 同炉全部有效 Si 的中位数、范围、极差和 0.20%–0.40%目标带描述 |
| 证据与完整性 | `chemistry_stats/sample_details/output_details/missing_elements/quality_status/quality_summary` | 全元素统计、原始试样/称量快照和缺失事实；`quality_summary`不是正式质量合格判定 |
| 谱系与版本 | `source_status/source_updated_at/aggregated_at/aggregation_version` | 源映射状态、源水位、聚合时间和算法版本；当前聚合合同为 `heat-performance-quality.v2` |

同步合同：全量首次回填；之后每5分钟回看最近3天并按 `meltno` 幂等 upsert，以吸收迟到化验。常规实时链路保留 `opentime <= now()+5min` 防未来误读；回看查询限制 `workdate < tomorrow` 并分页，达到 `repair_max_rows` 时返回 `repair_truncated=true`。只有存在真实出铁或铁水化验证据的异常炉次才可写汇总。`work_date` 与正式 `meltno` 日期不一致、或修复后开口仍晚于当前时间5分钟的记录标记为 `future_pending` 并由 API 默认隐藏；显式 `include_future=1` 仅供运维核验。普通增量 upsert 不得覆盖已有 `time_anomaly_repaired` 的原始/修复时间、状态、原因和核验时间；迟到化验和出铁明细仍可更新。单纯未来时间导致的 `future_pending` 在时间到达且普通增量获得有效记录后可自动解除；`meltno/workdate` 日期冲突必须保持隔离，直到来源锚点被明确修正。原始权威记录仍在 IMES/Vastbase，`sample_details/output_details` 只是页面与审计快照。

每次非 dry-run 同步同时输出三层缺口审计：Vastbase 源事实对 `bf_imes.raw_rows` 镜像的缺行/缺字段、源事实对汇总表的缺行、以及汇总表化验样本数变化。若镜像表不存在，返回 `mirror_audit_available=false`，不能把“无法审计”写成“0 个缺口”。数据库写入只允许 220.12 运行写账号执行；8093 `/api/heat-performance-quality` 只读。

## bf_assistant.diagnosis_ai_analysis_snapshots

追踪编号：`REQ-8093-8094-DIAGNOSIS-REVIEW-AI-20260806`、`REQ-8093-DIAGNOSIS-AI-FIVE-MINUTE-ANALYSIS-20260805`、`REQ-8093-DIAGNOSIS-AI-EVIDENCE-GUIDANCE-20260805`

该表保存可重新生成的5分钟智能分析状态，不属于人工不可覆盖事件。v3的 `prompt_version` 包含目标炉况键，因此同一时间桶可按需分别保存各炉况结果，而一次模型调用只处理一个炉况。定义位置：[diagnosis_review.py](../高炉前端数据/智能助手/backend/diagnosis_review.py)和[SQL参考](../高炉前端数据/智能助手/backend/schema/postgresql_diagnosis_review.sql)。

| 字段 | 含义 |
|---|---|
| `diagnosis_snapshot_id/diagnosis_ts` | 服务端读取的生产诊断快照和时间 |
| `bucket_ts/bucket_minutes` | 对齐后的5分钟桶及桶宽 |
| `main_label/system_raw_scores` | 当时主诊断与八类规则分 |
| `canonical_context` | 进入模型前的服务端白名单上下文 |
| `analyses` | 当前目标炉况的结构化分析JSON（历史v1/v2行可含八类） |
| `generation_state` | `preparing/reasoning/completed/failed` |
| `attempt_count/last_error_code` | 尝试次数和脱敏错误类型 |
| `prompt_version/snapshot_hash` | Prompt版本与服务器快照哈希 |
| `started_at/completed_at/updated_at` | 生成生命周期时间 |

v2不执行DDL迁移。`canonical_context` JSONB新增 `feature_snapshot/variable_stats/rule_drivers/recommendation_context/knowledge_context`；`analyses` JSONB中的每类结果新增 `score_explanation/key_driver_ids/guidance_summary/recommendation_action_ids/knowledge_chunk_ids`，并由服务端附加 `variable_evidence/recommendation_basis/knowledge_basis/evidence_contract`。旧v1行仍可读取；新的 `prompt_version` 使v2批次与旧结果并存。

唯一约束：`(furnace_id, bucket_ts, prompt_version)`。v3的目标炉况进入 `prompt_version`，保证同炉况同桶去重，同时允许八类按需分别生成。

人工复核与人工评分继续使用 `diagnosis_review_events`、`diagnosis_manual_score_events`，三张表之间没有覆盖更新关系。

## bf_sensor.one_minute_values 与 bf_sensor.raw_5s_values

追踪编号：`REQ-PSPACE-MINUTE-CANONICAL-AVERAGE-20260805`

`one_minute_values` 是一点一分钟的长期主表，字段 `aggregate` 记录值语义，唯一主键为 `(tag_long_name, ts)`。因此相同点位、相同分钟只有一个主值，upsert 会同时更新值、标签和审计字段。

| `aggregate` | 当前生成方式 | `value` 语义 |
|---|---|---|
| `PS_HIS_AVERAGE` | 历史回填读取 pSpace 60秒处理历史 | 该分钟的pSpace历史平均值 |
| `PS_RAW_SAMPLE` | 2026-08-05 21:54 以前的旧增量 | 该分钟最后一个有效raw样本；仅保留真实历史标签 |
| `PS_RAW_AVERAGE` | 2026-08-05 21:55 起从同一次 raw 读取聚合 | 有效数值且质量为空/192/Good 的raw算术平均 |

`one_minute_values` 的新审计字段为 `sample_count`、`numeric_sample_count`、`good_sample_count`、`expected_sample_count`、`coverage_ratio`、`min_value`、`max_value`、`last_value`、`window_complete` 和 `semantic_version`。开放分钟在60秒闭合水位前为 `window_complete=false`，后续10分钟回看会重新聚合并更新为完整窗口。

`raw_5s_values` 是约5秒短期表，按 `(tag_long_name, ts)` 唯一、按天分区、保留30天。它与分钟平均共用一次 `HisReadRaw` 结果，不增加第二次 pSpace 网络读取。旧 `PS_RAW_SAMPLE` 不做标签重写；历史回算必须作为单独迁移。完整边界见[pSpace分钟语义统一](pSpace分钟语义统一_20260805.md)。

## diagnosis_core_evidence.v1（运行时只读结构）

追踪编号：`REQ-8093-8094-DIAGNOSIS-CORE-19-TRENDS-20260806`

这是HTTP运行时结构，不是数据库表，本需求不执行DDL迁移。`core_variable_evidence`精确包含19项，每项携带当前值、5分钟变化、30天基线、数据时间、来源和最多61个60分钟曲线点。原规则主证据另行保留并优先展示，不会因固定19项集合而被删除。

人工评分和可选建议仍写入既有不可覆盖事件表；仅展开变量、切换变量或查看曲线不产生数据库记录。


## 当前炉次与时间段 Si 查询来源合同

`REQ-MCP-IMES-HEAT-SI-SAMPLES-20260807` 不新增数据库表。正式炉次和开堵口时间读取 `public.t_ipes_cond.meltno/opentime/closetime`；试样通过 `public.t_qpes_inner_batch.heatno/batchno` 与 `public.inner_batch_insp_bb.batchno` 连接；铁罐只按 `batchno -> public.v_qpes_mat_final.thankno` 精确关联。试样时间优先 `takesampletime`，缺失时依次回退 `judgetime`、`publishtime`，响应必须携带 `sample_time_type`，不得把回退时间冒充真实取样时间。

## REQ-ABC33-FURNACE-RULES-20260807

增量DDL见 [abc_rule_schema.sql](../自动诊断服务/abc_rule_schema.sql)：`bf_sensor.abc_rule_evaluation_batches` 保存每个5分钟批次和安全 bundle，`abc_rule_evaluation_items` 保存33项完整内部计算快照，`bf_assistant.abc_rule_config_versions` 保存草稿/发布/回滚，`abc_alert_episodes` 与 `abc_alert_event_log` 保存告警生命周期。生产账号使用 `bf_sensor.abc_rule_evaluation_public` 或接口白名单，不能读取内部公式列。

## bf_assistant.si_v20_prediction_audit

追踪编号：`REQ-SI-V20-8093-8094-SHADOW-WORKBENCH-20260808`、`REQ-SI-V20-DUAL-TIMING-AND-HOURLY-MATCH-20260809`。该表保存 V20 操作员影子预测；实际平均 Si 不复制进该表作为最终事实，而是在查询时从 `bf_assistant.heat_performance_quality_summary.si_avg` 动态读取。该 `si_avg` 的数据血缘为“IMES铁水化验 → 独立实时/回看同步 → 220.12炉次质量汇总表 → V20读取”，不是V20直接查询IMES。

主要字段：`prediction_id/request_id/target_meltno/furnace_no/target_open_ts/prediction_cutoff_ts/requested_at/requested_by/requested_role/request_mode/lead_minutes/prediction_si_mean/prediction_p10/prediction_p50/prediction_p90/actual_si_at_prediction/actual_available_ts_at_prediction/model_schema/model_name/model_sha256/feature_snapshot/model_contract/prediction_status`。非整点记录保持追加；`request_mode='hourly_schedule'` 通过部分唯一索引 `uq_si_v20_hourly_cutoff(furnace_no,prediction_cutoff_ts)` 保证每炉号系统/整点只有一条审计记录。

历史回看行按 `target_meltno` 与同炉实际值比较。生产整点行的 `target_meltno` 只是预测发起时的候选身份，最终结果不据此强行绑定；`/api/si-v20/hourly-history` 以 `requested_at` 为锚，动态选择同高炉 `open_ts >= requested_at` 的第一条真实炉次。这一匹配不会回写或覆盖原预测快照，既保留当时判断，也能在化验迟到后自动完成评价。

可配置调度新增字段：`schedule_id/schedule_run_id/schedule_slot_ts/cadence_minutes`。实时配置点以`schedule_id + schedule_slot_ts`唯一，历史批次点以`schedule_run_id + schedule_slot_ts`唯一。这样一分钟曲线每分钟只有一个预测点，重复分发不会产生重复行。

## bf_assistant.si_v20_prediction_schedule

保存生产自动预测配置，不为每一种周期建立独立表。主要字段：`schedule_id/schedule_key/furnace_no/enabled/cadence_minutes/next_slot_ts/last_slot_ts/last_run_status/last_error/created_by/updated_by/created_at/updated_at`。默认记录`schedule_key=production_default`、`cadence_minutes=60`、`enabled=true`。周期检查约束固定为1、10、30、60或1440分钟。

容量提示：一分钟周期理论上产生1440点/天，10分钟144点/天，30分钟48点/天，60分钟24点/天，1440分钟1点/天。当前合同不自动删除预测审计；后续若制定归档周期，应先导出/汇总再清理，不得无审计直接删除。

## bf_assistant.si_v20_prediction_run

保存历史批量或指定时刻预测批次。主要字段：`run_id/run_kind/schedule_id/cadence_minutes/range_start_ts/range_end_ts/requested_by/requested_at/started_at/completed_at/run_status/point_count/success_count/failure_count/parameters/error_summary`。逐点结果不复制到本表，而是通过`si_v20_prediction_audit.schedule_run_id`关联。

## V20严格整点数据合同（2026-08-10）

- `heat_performance_quality_summary.si_available_at`保存平均Si首次在220.12汇总中可见的时间，普通同步不得覆盖；`si_availability_confidence`取`observed_first_ingest`、`recovered_aggregation_timestamp`或`legacy_availability_unknown`。当实时镜像先写入`si_avg`而可用时间为空时，使用数据库`aggregated_at`保守恢复，禁止使用开口时间。严格回放只接纳`si_available_at<=slot_ts`。
- `bf_assistant.si_v20_strict_hourly_slot`是一小时一行的调度账本：`schedule_slot_ts=prediction_cutoff_ts=HH:00:00`，状态为`pending/running/failed_retryable/success`，保存尝试次数、下次重试、预测ID、初始候选、完成时间和来源水位。
- `si_v20_prediction_audit`为严格记录增加`execution_completed_at/dispatch_delay_seconds/attempt_count/initial_target_meltno/matched_actual_meltno/matched_actual_open_ts/actual_match_frozen_at/actual_match_rule_version/feature_watermarks`。
- “每小时Si预测与炉次化验汇总”不是新物理业务表，而是严格槽、`si_v20_prediction_audit`和`heat_performance_quality_summary`的只读API视图；逐次化验Si从`sample_details`抽取，平均Si只取`si_avg`。
- 唯一性：`request_mode='strict_hourly'`时按`furnace_no + schedule_slot_ts + model_sha256`唯一；匹配炉次一旦固化只补实际值，不再换炉。

## bf_assistant.hcz_expert_label_events（2026-08-10）

追踪编号：`REQ-HCZ-EXPERT-WEAK-LABEL-20260810`。DDL见[postgresql_hcz_expert_label.sql](../高炉前端数据/智能助手/backend/schema/postgresql_hcz_expert_label.sql)。

- 主键/幂等：`id`、唯一`reference_id`、唯一`idempotency_key`。
- 类型/版本：`reference_type=expert_weak_label`、`label_version=hcz-expert-weak-label.v1`、`furnace_id=GL02`。
- 知识时间：`observed_at`、`available_at`、`source_window_start`、`source_window_end`及`context_mode`。
- 标签：`root_level_label`、`movement_label`、可空`center_height_m/thickness_m/eccentric_sector`、`confidence_grade`、`evidence_codes`和`note`。
- 责任链：手填`operator_name`、服务器`reviewer_username/reviewer_role/identity_mode`、可空`supersedes_label_id`。
- 证据：`blind_to_model=true`、`source_schema_version`、64位`source_data_hash`和`source_context` JSONB。

表只提供追加写入与读取API，不提供UPDATE/DELETE入口。标签是专家弱标签，不等价于HCZ直接真值。

2026-08-11首条生产标签为`id=1`、`reference_id=HCZ-28cf0aad-63af-4e64-a27d-679ca79dbfdd`：观察时刻`2026-08-09 22:00+08:00`，方向`up`，绝对位置`uncertain`，可信等级4，证据窗口`2026-08-09 20:00`至`2026-08-10 06:00`。记录为事后证据型盲标注，`source_data_hash=1cd05b954ab2053a1ccad58c27ae78e7a5dfd274b1a363cc345cafcda256163e`。

## HCZ上移综合趋势规则的数据边界（2026-08-10）

`REQ-HCZ-UPWARD-EXPERT-RULE-20260810`不新增表、字段、视图或迁移。8093端点只读既有`bf_sensor.one_minute_values`及其变量目录，查询最近144小时并在应用层生成小时聚合；计算结果仅在进程内缓存120秒，不持久化为事实表，也不写生产控制数据。

## ABC33 B4展示分归档（2026-08-10）

`REQ-8093-ABC33-B4-CANONICAL-SCORE-20260810`不新增DDL、不改写`bf_sensor.diagnosis_snapshots`历史行。`raw_scores/main_score`及人工事件表中的对应数值字段继续保持旧八类诊断语义；新事件在既有JSONB分数字段中追加`_display_contract`对象，保存`display_scores/display_main_score/score_sources/legacy_score_archive/score_contract_version`。旧行没有该对象即代表legacy合同。禁止将B4展示分覆盖到旧数值键中。

## ABC33 上下文助手增量表（2026-08-11）

- `bf_assistant.qa_context_snapshots`：按 `context_hash` 去重的不可变上下文。
- `bf_assistant.qa_conversation_origins`：会话来源、初始批次、返回路由、操作者与班次。
- `bf_assistant.qa_message_context_snapshots`：消息与当时快照的多对多绑定，唯一键含 `usage_kind`。
- `bf_assistant.abc_rule_ai_explanations`：按 `context_snapshot_id + prompt_version + model_name` 唯一的生成状态和完成缓存。

迁移为 `schema/20260811_abc_contextual_assistant.sql`；代码回滚不删除表。
## QA 共享匿名房间（2026-08-13）

- 继续复用 `bf_assistant.qa_conversations` 与 `qa_messages`，不建立第二套消息表。
- 共享房间的 `owner_subject=guest:<sha256(room_key)[:24]>`、`owner_role=anonymous_guest`，会话 ID 为 `qa_guest_<room_id>`。
- 条件唯一索引 `uq_qa_shared_guest_room(owner_subject) WHERE owner_role='anonymous_guest'` 保证每个房间只有一条持久会话。
- `qa_messages.created_at` 保存每条用户/助手消息的 UTC ISO 时间戳；`snapshot_id` 和 `hidden_context_json` 保留当次页面炉况及其来源时间。
- 访客记录属于共享可见数据，不得写入项目资料、报表附件、登录主体私有会话或 ABC 私有上下文表。

## REQ-QA-RENDERER-CONTRACT-20260917：V31工具结果容器

状态：本机候选126项相关回归及独立审查通过，未部署；最后核对2026-09-17。
query_gl02_sensors的items必须为列表；每项的variable/source/latest/statistics及统计first/last字段存在且非null时必须是对象，None缺项仍表示未核实。错误容器不写成正式统计，不影响相邻有效项。字符串列表规范化与实际工具一致，限80项；参数与返回variables规范化列表须一致。明确别名绑定才继承canonical登记单位，不新增数据库表、字段或迁移。见[实现与边界](handoffs/2026-09-17-qa-v31-renderer-contract.md)、[机器证据](../tests/qa_regression/renderer_contract_candidate_20260917.json)。

## REQ-QA-LATEST-EVIDENCE-20260917：最新值逐字段缺项

状态：本机r2冻结候选、284项相关回归及独立审查通过，未部署；最后核对2026-09-17。
latest.value必须有限且非布尔，ts须含时分且可解析；source名称为非空字符串，策略仅readonly或缺项，缺项不能补成readonly。completion.missing_evidence_fields按对象提供缺项数组；缺字段partial、有效值保留。collected_at是来源工具标记，不推断物理采样；T_top.components须唯一A-D、同一时刻及均值复算，否则derived_component_alignment缺项。无数据库迁移。见[合同及真实来源范围](handoffs/2026-09-17-qa-v32-latest-evidence.md)、[机器证据](../tests/qa_regression/latest_evidence_candidate_20260917.json)。

## REQ-QA-SOURCE-SCOPE-20260917：私有源manifest

`bf.qa.source-scope-manifest.v1`保存原DOCX、旧/新authority hash、独立OOXML块/行位置、角色hash、规程类别及chunk指纹，原文只在私有候选。item核完整有序，atomic/section核完整源绑定；topic仅有序子集。`bf.qa.private-keyword-source-candidate.v1`精确doc_id、预期旧authority、全文及chunk绑定manifest SHA256。公开证据只含hash/计数/检查结果，无原文、凭据或生产测量。本轮未迁移表或发布数据库。
权威：[实际源范围、冻结及后续发布](handoffs/2026-09-17-qa-independent-source-scope.md)、[脱敏证据](../tests/qa_regression/source_scope_candidate_20260917.json)。

## REQ-QA-KEYWORD-SOURCE-RELEASE-20260917：归档/绑定表候选

DDL候选qa_knowledge_source_releases保存release_id、doc_id、applied/rolled_back状态、完整before_snapshot_json及before/after/manifest/plan hash、操作时间；旧vector保存精确文本用于还原，不重新推理。qa_knowledge_source_bindings保存doc_id、release_id、authority/manifest SHA及原始manifest_text；manifest保留字节顺序避免JSONB重排后hash失配。未执行迁移或保存快照，IF NOT EXISTS不验证已有表合同。
实际rag_chunk无chapter_code/regulation_type/chapter_title/源块位置列，检索字段按固定候选投影核对；私有计划与公开证据分离。权威：[真实旧源/schema核查与发布/回滚合同](handoffs/2026-09-17-qa-keyword-source-release-preparation.md)、[机器证据](../tests/qa_regression/keyword_source_release_preparation_20260917.json)。

## REQ-QA-KEYWORD-SOURCE-TRANSACTION-20260917：源事务schema与快照

状态：本机271项及独立静态复审通过，2026-09-17核对；生产未应用。
当前事务库严格核对五表列集合/类型、PK、全部传入/传出FK、启用用户触发器及public.vector，并用NOWAIT关系锁保持目录合同稳定。完整before JSONB含11/21/6字段集合及先前绑定；向量以原native vector文本恢复。恢复仅读状态及规范hash；生产增量表/归档尚未创建。
当前权威：[事务、真实依赖与剩余发布门](handoffs/2026-09-17-qa-keyword-source-transaction.md)、[机器证据](../tests/qa_regression/keyword_source_transaction_20260917.json)。上节253项报告是准备阶段历史快照，当前执行器状态以本节为准。

## REQ-QA-SOURCE-RELEASE-ENTRY-20260917：契约与独占记录

状态：2026-09-17本机验证，生产未执行。
private-source-release-entry契约仅私有，绑定action/operation/root/host/DB实例/config/hash/固定底座。独占jsonl记录claim/identity/write_started/committed或unresolved，只含安全错误码/计数/hash，不存凭据或源行；源表迁移仍待授权执行。
当前权威：[封存包、291项及剩余授权/部署门](handoffs/2026-09-17-qa-source-release-entry.md)、[机器证据](../tests/qa_regression/source_release_entry_20260917.json)。上节271项为事务库阶段快照，当前入口状态以本节为准。


## REQ-QA-ORIGINAL-SOURCE-READER-20260917：制度原书读取门禁

状态：2026-09-17本机验证/复审并冻结，生产未接入。

没有新增DDL。读取现有rag_document/rag_chunk、待授权迁移的qa_knowledge_source_bindings/releases及目标embedding计数，一条MVCC SELECT返回同一快照。核binding.manifest_text精确字节、applied release及全量after摘要；不读取before归档或vector正文。迁移表缺失稳定阻断。

当前权威：[读取门禁交接](handoffs/2026-09-17-qa-original-source-reader.md)、[脱敏机器证据](../tests/qa_regression/original_source_reader_20260917.json)。291项入口报告是历史阶段，完整源发布及822原题现场验收尚未完成。


## REQ-QA-FORMAL-DOCUMENT-SCOPE-20260917：书名与全部请求范围

状态：2026-09-17本机378项/复审及V34-r1冻结，生产未应用。

无DDL变化。请求级章节与规程作用域为确定性内存结构，来自已核同一数据库快照；正式binding/release/全量after摘要继续必需。缺组合不删除源行或改标准，22项语义选择测试使用合成原文，另私有真实原源验证使用原生产投影常量。

当前权威：[范围修复交接](handoffs/2026-09-17-qa-document-scope-resolution.md)、[脱敏机器证据](../tests/qa_regression/document_scope_resolution_20260917.json)。V33/356项为前阶段快照；822原题现场验证未完成。


## REQ-QA-DOCUMENT-REGULATION-SCOPE-20260917：条款规程范围与逐项覆盖

状态：2026-09-17本机400项/复审通过，V35-r1冻结，生产未应用。

无DDL变化。请求级include/exclude集合仅用于内存选择，不写数据库或泄漏进JSON。正式原源binding、applied release、全量after与单MVCC快照门禁不变；不改原题ID/裁判标准/源冲突记录。

当前权威：[规程范围交接](handoffs/2026-09-17-qa-document-regulation-scope.md)、[脱敏机器证据](../tests/qa_regression/document_regulation_scope_20260917.json)。V34/378项保留为历史阶段；822原题现场复问未完成。


## REQ-QA-FIXED-MODEL-OVERRIDE-20260917：唯一固定底座禁止参数覆盖

状态：2026-09-17本机61项/独立审查通过，V36-r1冻结，生产未应用。

无DDL变化。台账current_local_candidate由旧V26部署状态更新为实际V36本机候选，旧字段完整保留在prior_scoped_local_candidate；production_commit保持历史最后核验V26并明确连接失败。33条问题state不变，不把本机通过当生产销项。

当前权威：[固定参数门交接](handoffs/2026-09-17-qa-fixed-model-override.md)、[脱敏机器证据](../tests/qa_regression/fixed_model_override_20260917.json)。源/制度前阶段以V35报告保留；822原失败partial题0复问。


## REQ-QA-COMPOUND-SOURCE-SCOPE-20260917：复合子任务与来源禁令

状态：2026-09-17本机557项相关回归及独立审查通过，V37-r2冻结，生产未应用。

无新增或修改数据库结构；本轮只修正允许读库的条件与历史检索词。隔离真实PostgreSQL/vector夹具验证已有增量源发布、绑定及单快照读合同，不表示生产DB迁移/发布已授权或执行。

权威：[逐项交接](handoffs/2026-09-17-qa-compound-source-scope.md)、[脱敏证据](../tests/qa_regression/compound_source_scope_20260917.json)。0生产销项，原题准确率未验证。


## REQ-QA-MATH-FUNCTION-POLICY-20260917：正常数学函数问答

状态：2026-09-17本机225项相关回归/独立审查通过，V38-r2冻结，生产未应用。

无结构或数据修改。历史完成成功测试前置条件补齐已要求的质量及采集标记；缺质量/未知质量/缺采集时间/缺只读策略仍partial，已有值可保留，不更改生产完成门槛。

权威：[逐项交接](handoffs/2026-09-17-qa-math-function-policy.md)、[脱敏机器证据](../tests/qa_regression/math_function_policy_20260917.json)。本轮0助手模型调用/生产写入/原题发送/销项。


## REQ-QA-USER-DATA-SOURCE-SCOPE-20260917：用户给定数据与外部来源范围

状态：2026-09-17本机286项相关回归/独立审查通过，V39-r3冻结，生产未应用。

无DDL或生产数据改动。台账prior_local_candidate_v38保留V38冻结证据，current_local_candidate为V39-r3；33项state和生产历史结果保持不变，用户给定数值不伪装成现场记录。

权威：[逐项交接](handoffs/2026-09-17-qa-user-data-source-scope.md)、[脱敏机器证据](../tests/qa_regression/user_data_source_scope_20260917.json)。本轮0助手模型调用/生产写入/原题发送/销项。


## REQ-QA-DECLARED-INPUT-SCOPE-20260917：声明输入与现场核验

状态：2026-09-17本机327项相关回归/独立审查通过，V40-r2冻结，生产未应用。

无DDL/生产数据改动。prior_local_candidate_v39保留旧候选；R07原production_verified/两题证据及next_gate完整存档，新状态deployed_partial_verified。另32状态及初始题判定/生产复测不变，0销项。

权威：[逐项交接](handoffs/2026-09-17-qa-declared-input-scope.md)、[脱敏机器证据](../tests/qa_regression/declared_input_scope_20260917.json)。本轮0助手模型调用/生产写入/原题发送/销项；R07重新开放。


## REQ-QA-RESPONSE-STYLE-SOURCE-SCOPE-20260917：回答形式与资料来源

状态：2026-09-17本机395项相关回归/独立审查通过，V41-r1冻结，生产未应用。

无DDL和生产数据修改。prior_local_candidate_v40保存历史候选；33项状态、R07重新开放记录和旧线上证据均保留，0销项。

权威：[逐项交接](handoffs/2026-09-17-qa-response-style-source-scope.md)、[脱敏机器证据](../tests/qa_regression/response_style_source_scope_20260917.json)。本轮0助手模型调用/生产写入/原题发送/销项。


## REQ-QA-SOURCE-CONCEPT-SCOPE-20260917：来源概念与具体记录

状态：2026-09-17本机436项相关回归/独立审查通过，V42-r1冻结，生产未应用。

无DDL/生产数据修改。prior_local_candidate_v41保存历史候选；33项状态、R07重新开放及旧生产证据不变，0销项。

权威：[逐项交接](handoffs/2026-09-17-qa-source-concept-scope.md)、[脱敏机器证据](../tests/qa_regression/source_concept_scope_20260917.json)。本轮0助手模型调用/生产写入/原题发送/销项。


## REQ-QA-SOURCE-EXCLUSION-SCOPE-20260917：来源排除与子任务继承

状态：2026-09-17本机498项相关回归、原源保真及独立审查通过，V43-r6冻结，生产未应用。

无DDL或生产数据修改。prior_local_candidate_v42保留旧候选；33项状态及首次/历史线上判断不变，0销项。具名排除是本请求私有范围，不写成新的模型或知识源基线。

权威：[逐项交接](handoffs/2026-09-17-qa-source-exclusion-scope.md)、[脱敏机器证据](../tests/qa_regression/source_exclusion_scope_20260917.json)。0助手模型调用/生产写入/原题发送/销项。
