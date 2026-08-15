# ABC33形成原理与五步干预处置流程接入建议页面

## 结论

需求编号：`REQ-ABC33-HANDBOOK64-MECHANISM-INTERVENTION-20260810`。

本机建议页面与220.12的8093生产预览均已完成接入。此前33项规则都返回同一段通用原理和通用三步流程；现在每一项都从受控运行时目录获得专属形成原理、严格五步干预处置流程和对应见习高炉长章节。

2026-08-10 12:48完成生产验收：8093与8768均为`Running`，8093 HTTP 200，最新批次返回33条规则且目录版本为`abc33-catalog.v3.handbook64-guidance`。本轮没有修改或重启8094、8770和11434。

## 实现位置

- 运行时工艺目录：[abc_rule_guidance.py](../../自动诊断服务/abc_rule_guidance.py)
- 规则目录合并：[abc_rule_catalog.py](../../自动诊断服务/abc_rule_catalog.py)
- 文档到运行时目录导出：[export_abc_rule_guidance.py](../../tools/export_abc_rule_guidance.py)
- 页面详情渲染：[abc-furnace-rules-production.js](../../高炉前端数据/assets/abc-furnace-rules-production.js)
- 页面资源版本：[frontend_dashboard_v3.server.html](../../高炉前端数据/frontend_dashboard_v3.server.html)
- 同时刻批次元数据刷新：[abc_runtime_store.py](../../自动诊断服务/abc_runtime_store.py)

## 页面行为

每条规则详情按以下顺序显示：

1. 规则状态、操作研判分、数据置信度和计算时刻。
2. 炉况形成原理及对应手册章节。
3. 五步干预处置流程。
4. 逐点传感器与趋势复核。
5. 缺失数据、人工复核、观察窗口和审批要求。

C类处置面板使用红色安全强调；A/B采用工艺蓝和琥珀色。窄屏自动改为单列，文字不使用不可恢复的省略号。

## 安全合同

- 普通接口继续只返回`principle`、`intervention_order`和`source_refs`等工艺层字段。
- 公式、权重、精确阈值、内部特征、归一化值和贡献不进入前端资源和普通响应。
- 所有处置仅为只读建议，仍需现场确认、工长审批、联锁和事故预案。

## 验收

```powershell
python -m py_compile .\自动诊断服务\abc_rule_guidance.py .\自动诊断服务\abc_rule_catalog.py .\自动诊断服务\abc_rule_engine.py .\tools\export_abc_rule_guidance.py
node --check .\高炉前端数据\assets\abc-furnace-rules-production.js
python -m pytest -q .\tests\test_abc_rule_engine.py .\tests\test_abc_production_ui.py --basetemp .\.tmp_pytest_abc33_guidance
```

结果：定向合同测试`30 passed`；ABC33规则、桥接、特征、公共因子、回放、页面和文档全套相关回归`128 passed`。本地浏览器夹具打开A1详情后，形成原理、5个步骤、章节、观察窗口和审批要求均可见。

部署中补充发现并修复同一分钟批次冲突时只更新`public_bundle`、不更新`catalog_version`的问题。新增测试[tests/test_abc_runtime_store.py](../../tests/test_abc_runtime_store.py)，与规则及页面合同合并执行结果为`31 passed`；最终ABC33全套相关回归为`129 passed`。

Chromium固定视口验收覆盖`1280×720`、`1366×768`、`1440×900`、`1546×864`、`1920×1080`、`1024×768`、`768×1024`、`390×844`和`375×667`：9个视口均无页面横向溢出、详情对话框可见、5个步骤完整、正文可滚动；`768×1024`及更窄视口正确切换为单列。页面控制台错误/警告为0。

## 8093生产发布凭据

- 8768备份：`F:\高炉炼铁项目-real-sensor-v2_V4_8093_PREVIEW\backups\abc33_handbook64_guidance_8768_20260810_124724`。
- 8093备份：`F:\高炉炼铁项目-real-sensor-v2_V4_8093_PREVIEW\backups\abc33_handbook64_guidance_8093_20260810_124057`。
- 守卫闭环：`guard_paused=true`、`guard_restored=true`；8093 PID由`2044`变为`10008`。
- 最终服务：8093 PID=`10008`，8768 PID=`18436`，8094 PID=`2988`，8770 PID=`3732`，11434 PID=`5968`。
- 受保护结果：8094、8770、11434 PID未变化；8094页面SHA-256保持`0FBD899EF6BF360F39BF5A7FB7881664B7CF1E4D87E90CCB7C94BE6B07B148C3`。
- 页面资源：版本`abc33-20260810-handbook64-guidance-r1`，资源SHA-256=`976EB61B2E0F089AEE36E4ADC91B62C4D48AFBD78BAD59A8FDF8E3F822FF5FB1`。
- 后端资源：`abc_rule_guidance.py`、`abc_rule_catalog.py`、`abc_runtime_store.py`与本机SHA-256逐项一致。
- 最新API批次：`2026-08-10 12:45:00+08:00`；33条规则；A1分数`73.5393`、状态`manual_confirm`，返回1段专属原理、5步处置和7条章节。
- 安全检查：普通详情未出现`formula_terms`、`normalized_value`、`contribution`、`feature_key`、`thresholds`或`weights`。
- 页面检查：缓存隔离URL成功加载，33项可计算、数据不足0；当前有效0分明确显示为规则结果，不再作为启动失败判据。

## 后续范围

8094本轮保持原样。若需要同步8094，必须单独执行8094受控发布与浏览器验收，不得把本次8093结果表述为8094已更新。
