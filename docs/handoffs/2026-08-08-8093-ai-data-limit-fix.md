# 8093 智能分析数据限制误标修复（2026-08-08）

## 结论

`L_north`、`L_south` 和 `T_top_A-D` 在 220.12 的 `bf_sensor.sensor_registry` 中均已启用，并且最新诊断窗口存在有效值。原问题不是变量缺失，而是把“采样不是每分钟一条”当成“数据覆盖不足”，随后由模型写入 `data_limits`。

## 只读核验

核验脚本：[remote_probe_22012_diagnosis_data_coverage.ps1](../../tools/remote_probe_22012_diagnosis_data_coverage.ps1)。2026-08-08 14:40 诊断点核验结果：

- 6 个点位均有启用、非派生的注册记录；
- 6 个点位在最近 60 分钟均有有效 `one_minute_values` 行；
- `raw_5s_values` 也存在对应原始采样；
- 原逻辑查询不会因未审计零值过滤掉这些样本；
- 但每分钟采样密度不是 61/61，因此历史 `variable_coverage` 低于 1.0。这是采样密度，不是变量不可用。

本次只读核验未修改 220.12 数据库、诊断快照或采集任务。

## 修复内容

- [diag_ai_evidence.py](../../高炉前端数据/智能助手/backend/diag_ai_evidence.py) 新增 `build_truthful_data_limits()`：只有在规则项没有有效特征值、且关联变量没有当前值和 60 分钟趋势序列时，才生成数据限制。
- [diagnosis_model_review.py](../../高炉前端数据/智能助手/backend/diagnosis_model_review.py) 将逐变量采样密度从模型输入中移除，并将模型自由填写的 `data_limits` 替换为服务端事实结果。
- 远端同步时又发现 8093 的 `bf_knowledge_rag.py` 仍是旧接口，`search_knowledge()` 不接受 `source_doc_ids`，会让智能分析直接返回 `TypeError`；已同步本机适配器并重启 8093。
- 版本号升为 `diagnosis-single-condition-five-minute.v6`，避免继续读取旧版 v5 的错误分析缓存。
- 具有当前值或趋势序列的南北料线、四点顶温不得再被标为数据限制。

## 验证

```text
16 passed: tests/test_diagnosis_ai_analysis.py
manual data-limit assertions passed
Python AST syntax check passed
```

远端 8093 验收：`GET /api/diagnosis-ai-analysis?label=cold` 返回 HTTP 200、`state=completed`、`target_display_name=热制度下行`、`data_limits=[]`；响应中包含 T_top_A/B/C/D、T_blast、DP_total 等真实证据序列，`core_variable_count=19`。最终只读状态为 `BFV4PreviewProxy8093=Running`、8093 正在监听，`BFV4PreviewWs8768=Running`、8768 正在监听；未操作 8094。

## 部署边界

本阶段代码修复已在本机完成。远端只更新 8093 的智能分析后端与知识库适配器并重启 `BFV4PreviewProxy8093`；不操作 8094、8768、8770 或数据库。远端上线后必须重新请求 `GET /api/diagnosis-ai-analysis?label=<label>`，确认返回完成状态且 `analysis.analysis.data_limits` 不包含已有有效值的点位。
