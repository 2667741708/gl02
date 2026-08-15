# 工长趋势两位小数与百分数展示修复

状态：本机完成，未部署  
最后核对日期：2026-08-14  
需求编号：`REQ-FOREMAN-TREND-TWO-DECIMAL-PERCENT-20260814`

## 实现结果

- 顶部49项指标统一固定显示两位小数，包括原来按0、1或3位展示的值。
- 工长趋势原生悬浮提示和共享右键点位提示统一固定显示两位小数。
- `GasUtil` 历史原值在绝对值不超过1.5时按比例口径乘100，再进入曲线原始值第三维和提示；
  例如 `0.482998` 显示为 `48.30%`。
- pSpace、PostgreSQL、WebSocket原始合同和点位注册表均未修改。

## 实现与验证

- [工长趋势脚本](../../高炉前端数据/assets/foreman-trend-preview.js)
- [共享曲线检查器](../../高炉前端数据/assets/curve-inspector.js)
- [页面入口](../../高炉前端数据/foreman_trend_preview.html)
- [合同测试](../../tests/test_foreman_trend_preview.py)

验证命令：

```powershell
python -m unittest tests.test_foreman_trend_preview -v
```

验证结果：`7 tests` 全部通过；两份 JavaScript 均通过 `node --check`；本机 Chromium/Edge
`1280×1024` 冒烟 `PASS`，49项指标、两张曲线、工具栏和变量选择交互正常，页面错误、控制台
错误及横向溢出均为0。

## 影响边界

本轮只修改本机前端资源、静态合同和追踪文档；没有上传220.12、修改数据库或重启服务。
