# V20严格整点Si预测生产交接（2026-08-10）

追踪编号：`REQ-SI-V20-STRICT-HOURLY-CLOSED-LOOP-20260810`

## 交付状态

- 8093、8094已上线独立常开的`strict_hourly`通道；可调`scheduled_interval`任务未被替换或关闭。
- Windows任务：`\BlastFurnaceServices\SiV20StrictHourlyPrediction`，SYSTEM、每分钟、`IgnoreNew`，不可由页面周期设置关闭。
- 生产表：`bf_assistant.si_v20_strict_hourly_slot`、`bf_assistant.si_v20_prediction_audit`、`bf_assistant.heat_performance_quality_summary.si_available_at/si_availability_confidence`。
- 最终部署备份：`F:\高炉炼铁项目-real-sensor-v2_V4_8093_PREVIEW\backups\si_v20_strict_hourly_20260810\20260810_014636`。

## 首条生产证据

- 槽/截止：`2026-08-10 01:00:00`，两者完全相等。
- 初始候选：`2#20260810-130`；实际评价炉次尚未开口，状态为等待匹配/化验。
- 发起：`2026-08-10 01:08:45.298260+08:00`；完成：`01:08:46.569839+08:00`。
- P50：`0.318322%`；P10–P90：`0.261695%–0.384624%`。
- 数据库验证：槽1、成功1、重复0、非整点0、截止合同违规0、Si可用时间缺失0。
- 模型：`v20_lightgbm_huber`，7549特征、420树，SHA-256=`4555c44f69326068f41023c2f4cfdff4bce0fb7ced693af1085003d0f3a4e4f4`。

## 防泄漏与迁移边界

- 传感器同时要求`source_ts<=slot_ts`和`collected_at<=slot_ts`；首槽7537/7549个模型特征可用。
- 迁移前9484条Si只有业务时间、无法证明首次入库时刻，统一标记`legacy_availability_unknown`，首槽未读取这些历史Si。未来新出现Si会记录`observed_first_ingest`并可在后续整点严格使用。
- 炉料化学只从220.12本地镜像探测；当前冻结模型未包含化学列，页面和审计明确列为低置信度可选背景，不连接外部IMES。

## 部署中发现并保留的审计事实

1. 首次服务恢复失败是公共后端引用的`abc_term_semantics.py`未同步；补齐依赖后8093恢复，随后依赖纳入正式部署清单。
2. 首槽前两次尝试因JSONB水位中datetime不能序列化失败，槽保留并在第3次成功；没有删除失败次数。
3. 首条审计的数据库默认发起时间曾晚于完成约24ms；已改为预测函数进入时间，并用槽领取时间修复该条，当前顺序正确。
4. 页面空参数补跑曾会把当前秒误作整点校验；已改为服务器自动下取当前`HH:00:00`。生产POST `{}`返回原`prediction_id=623`、`claimed_slot_count=0`，证明补跑可用且不重复写入。

## 验收与未完成观察

- 本机相关回归：`35 passed`；纯Python模型与原LightGBM真实样本差`1.11e-16`。
- 8093与8094：各自Chromium 9个视口、Firefox 4个、WebKit 4个全部通过，页面错误0、横向溢出0。
- 8768、8770、11434受保护PID部署前后未变化；8093守卫恢复成功，8094受控重启成功。
- 必须在`2026-08-11 01:00`以后再次只读核对24个连续整点槽；目前不能把算法测试写成24小时生产实测。

## 独立只读审查

- 结论：未发现P0，主链首槽可用；不能提前宣称24小时稳定闭环。
- 审查提出GET状态/历史会创建槽或执行匹配UPDATE的P1。现已把建槽、重试和匹配固化全部留在分钟分发任务，严格GET只检查schema并查询。
- 生产复验连续调用5轮status/history，前后`slot_id=1`、`updated_at=01:08:46.668992`、`attempt_count=3`、`prediction_id=623`、history count=1均不变。
- 仍待外部状态的两项：预测623尚无预测完成后实际开口炉次；真实24小时尚未经过。到时由一分钟任务自动固化匹配并补实际Si，再重新执行独立只读审查。
