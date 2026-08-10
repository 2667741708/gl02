# 高炉调控结论生成引擎

本模块把标准炉况诊断转换为符合《冀钢炼铁三规二制》四类调剂结构的只读建议。输入包含主炉况、次炉况、诊断分数、8种炉况分数、实时量、现场配置、人工事件和炉次化验上下文；输出同时包含完整 `actions[]` 审计合同与兼容旧前端的立即/后续/禁止动作数组。

当前版本为 `v5-three-rules-two-systems`，覆盖 `normal`、`lowline`、`edge`、`center`、`channel`、`cold`、`hot`、`column` 八类炉况。主、次炉况不再限于两个组合特判，而是统一合并为上部、下部、负荷、碱度四类候选，再执行动作顺序、相反方向冲突和安全门禁。

每条动作固定返回：`source_refs`、`trigger_evidence`、`preconditions`、`blocking_reasons`、`delta`、`sequence`、`missing_inputs`、`observation_window`、`approval` 和 `read_only=true`。状态只使用 `eligible / blocked / needs_data / manual_confirm`；缺数据时不猜幅度，阻断时不删除动作。

运行示例：

```powershell
python 调控结论生成引擎\main.py diagnosis.json
python 调控结论生成引擎\main.py diagnosis.json --output recommendation.json
python tests\test_three_rules_recommendation_engine.py
python tools\verify_8093_recommendation_engine_contract.py
```

策略目录：[three_rules_two_systems.yaml](policy/three_rules_two_systems.yaml)。该文件采用 JSON 兼容 YAML，标准库即可加载，不给远端运行时新增 YAML 依赖。

安全边界：引擎只生成建议，不连接生产控制写接口；所有参数变更、布料、负荷、坐料和事故动作仍需现场授权确认。本地 v5 未自动部署到远端生产/预览服务。

8767 适配器另提供 `multi_condition_recommendation.v1`：`active_plan` 是当前主/次炉况的唯一有效合并方案，`conditions` 为八类炉况各自的只读查看项。选择非当前炉况只是在页面查看条件预案，不会改变诊断结果或当前动作顺序。

后台高炉大模型复核是独立解释层：它只返回对规则分数的支持程度、支持/矛盾证据、缺失数据和观察重点，不可改写本引擎的分数、动作四态、幅度、顺序、安全门禁或审批。

追踪文档：

- [docs 可追踪说明](../docs/调控结论生成引擎可追踪说明.md)
- [PT 交接说明](../PT/调控结论生成引擎可追踪说明.md)
