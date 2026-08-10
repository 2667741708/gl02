# 工长双变量调剂建议范围（本机实现）

## 1. 需求与结论

- 需求编号：`REQ-FOREMAN-DUAL-CONTROL-20260806`
- 当前建议引擎只允许对 `Q_blast`（风量）和 `PCI_set`（喷煤设定）生成可执行、可量化的调节建议。
- 热风温度、富氧率、氧气流量、焦炭负荷、布料制度、碱度等其他可调变量暂不生成“调多少”的动作，统一保持不动。
- 其他核心变量不从诊断中删除，仍可作为触发证据、前置条件、安全门禁、阻断原因、缺失数据和观察窗口使用。
- 所有建议仍为只读辅助决策，必须保留现场确认或审批要求，不直接写入 PLC/DCS。

## 2. 三规二制口径

《冀钢炼铁三规二制》给出了加风、减风、加煤、减煤和停煤的适用条件，但没有给出适用于所有炉况的统一固定步长。因此引擎不得自行编造风量或喷煤设定的固定幅度。

量化幅度必须来自现场批准配置；批准步长或边界缺失时，对应动作返回 `needs_data`，且 `delta=null`。规则或安全门禁不满足时返回 `blocked`。满足规则且数据齐全时才返回 `eligible` 或规则本身要求的 `manual_confirm`。

## 3. 可执行变量白名单

| 变量 | 中文名称 | 支持动作 | 单位 |
| --- | --- | --- | --- |
| `Q_blast` | 风量 | 增加、减少 | `Nm³/min` |
| `PCI_set` | 喷煤设定 | 增加、减少、停煤归零 | `t/h` |

当前动作映射：

- `LOW-BLAST-UP-GATE`：增加风量。
- `LOW-BLAST-DOWN-02`、`LOW-BLAST-DOWN-04`、`LOW-BLAST-DOWN-05`：减少风量。
- `LOW-PCI-UP-02`：增加喷煤设定。
- `LOW-PCI-DOWN-02`：减少喷煤设定。
- `LOW-PCI-DOWN-05`：严重失常时停煤，目标值为 0。

不在白名单内的原始动作不进入工长可执行建议列表，但会记录到 `control_scope.suppressed_actions`，供审计追溯。

## 4. 现场批准配置

| 上下文字段 | 环境变量 | 含义 |
| --- | --- | --- |
| `approved_q_blast_step_up` | `BF_APPROVED_Q_BLAST_STEP_UP` | 单次批准加风步长 |
| `approved_q_blast_step_down` | `BF_APPROVED_Q_BLAST_STEP_DOWN` | 单次批准减风步长 |
| `approved_q_blast_min` | `BF_APPROVED_Q_BLAST_MIN` | 风量批准下限 |
| `approved_best_blast` | 既有诊断上下文字段 | 当前炉况允许的最佳/批准风量上界 |
| `approved_pci_set_step_up` | `BF_APPROVED_PCI_SET_STEP_UP` | 单次批准加煤步长 |
| `approved_pci_set_step_down` | `BF_APPROVED_PCI_SET_STEP_DOWN` | 单次批准减煤步长 |
| `approved_pci_set_min` | `BF_APPROVED_PCI_SET_MIN` | 喷煤设定批准下限 |
| `approved_pci_set_max` | `BF_APPROVED_PCI_SET_MAX` | 喷煤设定批准上限 |

当前值优先从实时建议上下文读取。步长和边界可由建议上下文显式传入，也可由上述环境变量提供。不得把现场批准值硬编码到前端。

## 5. 返回契约

每个保留动作继续包含原文章节/规则来源、触发证据、前置条件、阻断原因、幅度、顺序、缺失数据、观察窗口和审批要求。新增或明确以下字段：

- `control_variable`：只可能是 `Q_blast` 或 `PCI_set`。
- `adjustment_direction`：`increase`、`decrease` 或 `stop`。
- `delta.current`：当前设定值。
- `delta.min` / `delta.max`：本次建议调节量；现场批准为单值时二者相同。
- `delta.target_min` / `delta.target_max`：应用本次建议后的目标设定值。
- `delta.approved_step_field`：使用的现场批准步长字段。
- `delta.approved_boundary_field`：使用的现场批准边界字段。
- `control_scope.mode=foreman_dual_control_only`：双变量范围标记。
- `control_scope.read_only=true`：只读辅助决策标记。
- `control_scope.suppressed_actions`：被范围策略抑制的其他动作审计记录。

状态口径：

- `eligible`：规则、门禁、当前值、批准步长和边界均齐全，可以提交现场确认。
- `blocked`：规则或安全门禁不允许执行，或当前值已经到达批准边界。
- `needs_data`：缺少当前值、现场批准步长、批准边界或规则要求的数据，不返回调节量。
- `manual_confirm`：规则允许提出方案，但必须由工长/炉长现场确认后执行。

## 6. 程序链路

- 完整三规二制规则本体保留在 `自动诊断服务/recommendation_adapter_full.py`，用于规则审计和回归。
- 生产建议入口为 `自动诊断服务/recommendation_adapter/__init__.py` 的 `generate_recommendation_bundle()`。
- 双变量范围与量化计算位于 `自动诊断服务/foreman_dual_control.py`。
- 页面继续从建议 bundle 的 `actions` 渲染“建议调多少”；因为输出层已经过滤，页面不会把其他变量显示为可执行调节动作。

## 7. 验证记录

- 语法检查：相关 Python 模块 `py_compile` 通过。
- 双变量合同与三规二制规则回归：`python -m pytest tests/test_three_rules_recommendation_engine.py tests/test_foreman_dual_control_recommendations.py -q`
- 结果：`15 passed`。
- 新增合同覆盖：热制度下行、热制度上行、批准步长缺失、全部八类炉况输出白名单和动作计数一致性。

## 8. 当前交付边界

- 本次为本机代码实现，尚未更新 220.12 的 8768 自动诊断服务。
- 在现场确认并配置上述批准步长与边界前，不得把缺失值替换成猜测值；对应动作应保持 `needs_data`。
- 后续远程部署涉及 Python 建议适配器，必须更新受控部署清单并重启/验证 8768；不需要为了这一后端范围策略替换 8093/8094 页面文件。
