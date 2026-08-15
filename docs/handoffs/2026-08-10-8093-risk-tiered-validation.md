# 8093风险分级验收与加载审计交接（2026-08-10）

追踪编号：`OPS-8093-RISK-TIERED-VALIDATION-20260810`。

## 结论

8093的小范围改动默认不再跑85项。浏览器验收分为`quick=4`、`standard=17`和`full=85`；失败、边界不清或共享运行时变更自动升级。所有等级都保留生产部署事务安全门禁。

## 实现

- `tools/verify_diagnosis_review_local.py`新增`--profile`和`--check-manual-score`。
- 同一浏览器内核复用一个context，case之间只新建page并调整viewport，避免重复冷缓存。
- `tests/test_diagnosis_review_browser_profiles.py`固定三档数量、受影响路由和完整矩阵关键尺寸。
- `deploy-8093-guarded-update` Skill新增`references/validation-tiers.md`，并由Skill验证器检查该合同。

## 验证证据

- profile合同：3项pytest通过。
- 格式与静态检查：Ruff通过。
- 本机预览跨内核quick：4/4通过、9.019秒，结构化报告为`logs/diagnosis_review_browser_20260810_202317/report.json`。
- 相对full减少81项，即95.3%。这证明的是本次定向验收时间，不代表全站85项已经通过。

## 页面加载审计

- 生产HTML正文约907KB，响应没有gzip/Brotli，缓存策略为`no-store`。
- 页面仍加载React/ReactDOM开发版、Babel和ECharts，并在浏览器中编译`text/babel`；本地四项依赖合计约5.35MB。
- overview首屏使用约8.23MB GLB；单体HTML还包含多个路由和多组高频定时器。
- 推荐顺序：移除浏览器Babel并构建期打包、切React生产版、按路由拆包、启用HTML压缩、Three/GLB延迟和压缩加载、合并/暂停定时器。

本次只修改本机验证流程、文档和全局Skill，没有连接或修改生产8093。
