# 软熔带移动预测特征与智能诊断本机代码化交接

## 1. 需求与来源

- 追踪编号：`REQ-COHESIVE-ZONE-INTELLIGENT-DIAGNOSIS-20260810`。
- 来源：用户提供的本机Word《1780级高炉软熔带移动预测特征总结与智能诊断模型》。
- 目标：把Word中的预测特征、上移/下移判据和8类炉况融合关系转化为本机可执行、可测试、可解释代码。

Word给出了特征和经验方向，但没有真实软熔带中心高度`H_cz`标签、样本集、模型参数、训练代码或回测指标。因此本次实现选择解释型特征融合，不虚构已经训练完成的Chronos-2、TabPFN或Transformer。

## 2. 实现结果

### 2.1 特征与决策

[主诊断函数](../../炉况规则引擎/features/cohesive_zone_intelligent_diagnosis.py#L214-L432)执行：

1. 只保留`evaluation_time`及以前的数据；
2. 构造15分钟参考窗口、15分钟隔离区和15分钟当前窗口；
3. 按配置提取总压差、透气性、顶压波动、风压、顶温、炉身上中下部温度、煤气利用、CO、Si、铁水温度、燃料比、崩滑料和显式料速；
4. 按单位范围、新鲜度、最少样本和必需分组执行门禁；
5. 输出上移/稳定/下移概率、置信度、覆盖率、当前特征、归一化趋势、逐项驱动和关联炉况证据。

[YAML配置](../../炉况规则引擎/config/cohesive_zone_intelligent_diagnosis.yaml#L1-L209)集中维护字段别名、有效范围、变化尺度、方向和权重。压力/透气性保持最高权重；炉身中下部温度和燃料比在来源Word没有明确方向时只保留上下文，不强行计分。

### 2.2 与既有C2估算器关系

[组合函数](../../炉况规则引擎/features/cohesive_zone_intelligent_diagnosis.py#L434-L469)显式并行调用既有C2根部几何估算器，输出：

- `cohesive_zone`：既有根部高度、厚度、偏心和15分钟常速外推；
- `intelligent_diagnosis`：本次新增的特征融合方向和关联证据；
- `direction_consistency`：`consistent/review_required/not_comparable`。

本次没有把新字段自动注入8767快照，也没有修改8768、8093、8094或现有8类炉况/ABC33分数。

### 2.3 本机入口

[CSV CLI](../../tools/run_cohesive_zone_intelligent_diagnosis.py#L24-L88)支持：

```powershell
python .\tools\run_cohesive_zone_intelligent_diagnosis.py `
  --input .\data\cohesive_zone_minutes.csv `
  --evaluation-time '2026-08-10 10:00:00' `
  --include-geometry `
  --output .\output\cohesive_zone_diagnosis.json
```

退出码0表示诊断可用，2表示覆盖不足，1表示运行异常。

## 3. 安全与真实性边界

- 固定`evidence=estimated`。
- 固定`calibration_status=uncalibrated`。
- 固定`control_use=prohibited`。
- `confidence_cap<=0.45`，配置加载器会拒绝越界值。
- 关联炉况的`support`是证据关联，不是新的生产炉况分数。
- 缺失或越界输入保持缺失，不用0代替，不读评价时间后的未来行。
- 未新增数据库、API、任务、端口、服务或生产写路径；未远端部署。

## 4. 验证

[专项测试](../../tests/test_cohesive_zone_intelligent_diagnosis.py#L84-L161)覆盖：

- 上移、稳定、下移组合；
- 压力、温度、顶压波动和炉况关联证据；
- Si/铁水温度下降与热制度下行关联；
- 未来数据隔离；
- 必需分组缺失门禁；
- 与既有C2几何估算器组合；
- CSV读取和UTF-8 JSON端到端。

正式本机验证命令：

```powershell
pwsh.exe -NoLogo -NoProfile -File `
  .\tools\verify_cohesive_zone_intelligent_diagnosis.ps1 `
  -PythonExecutable 'C:\Users\hmw20\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe'
```

结果：

- `py_compile`通过；
- 新诊断与既有C2估算器：`30 passed`；
- CLI帮助通过；
- 真实PowerShell运行检查：`7.6.4 Core`、UTF-8、中文项目路径回环通过；
- Ruff：`All checks passed!`。

额外联跑`tests/test_local_pg_ws_bridge_cohesive_zone.py`时，43项中42项通过，1项既有失败：`test_init_and_tick_keep_existing_fields_and_append_snapshot`的`FakeConnection`没有当前`build_foreman_recommendation_context`调用所需的`execute`方法。本次未修改`local_pg_ws_bridge.py`，故没有为掩盖该历史测试替身债务改业务代码。

## 5. 后续生产化门禁

1. 取得经现场接受的软熔带位置/中心高度真值并记录标签首次可用时间；
2. 冻结训练、验证、测试时间段，禁止随机切分造成未来泄漏；
3. 使用当前`feature_vector/trend_vector`训练Chronos-2、TabPFN、Transformer或树模型候选；
4. 对方向准确率、`H_cz`误差、概率校准、输入覆盖和陈旧率进行历史回测；
5. 与既有C2几何估算器做一致性/差异性审计；
6. 现场专家确认字段单位、料速正方向、CO2与煤气利用语义后，再考虑接入8767或页面；
7. 未完成上述门禁前不得提高置信度、删除禁止控制标签或远端部署为生产控制信号。
