# 固定底座运行时验收门修复

状态：本机合同测试和独立审查通过；生产只读核验阻断。最后核对：2026-09-17。
需求：REQ-QA-RUNTIME-PROBE-FIXED-PIN-20260917；关联 QAOPT-O01/T01/T05。
权威：[脱敏机器证据](../../tests/qa_regression/runtime_fixed_pin_20260917.json)、[33项执行账本](../../tests/qa_regression/optimization_execution_ledger_20260916.json)。

## 用户强约束

固定名称 `chiqiongblastfuenace:latest` 与摘要 `e4ad74c41d68de1c8004419d8141a2b2df2275fa08f0dcf326ca0e63fb6d8124`。
禁止切换模型、备用回退、同名替换权重或把当前驻留的其他摘要作为新基线。不一致时拒绝新的模型调用。

## 缺陷、修复及核对

1. 旧探测仅比较别名与驻留是否相等，两者同时换权重仍通过；未复核读取驻留后的别名。7个反例中3失败、4通过。
2. [身份判定](../../tools/probe_qa_paired_runtime_readonly.py:24)现在要求前后两次别名唯一且固定、单驻留名称及摘要固定；缺失、重复、其他权重或别名变化均拒绝。
3. [探测主入口](../../tools/probe_qa_paired_runtime_readonly.py:37)仅做 metadata GET，显式禁用 loopback 网络代理；GET失败保留已采集文件哈希，只输出异常类型。
4. [路径边界](../../tools/probe_qa_paired_runtime_readonly.py:13)拒绝绝对路径及仓库外路径。保留 --scope-file，新增互斥 --scope-json，二者使用同一审查范围，无远端文件上传。
5. 33项本机底座合同测试通过（0.15秒），gpt-5.6-luna low独立只读审查PASS。V44-r2冻结15文件全部哈希未变；本轮没有新运行时候选。

复现验证：

```powershell
python -X utf8 -m pytest -q tests/test_qa_runtime_probe_fixed_pin.py tests/test_qa_fixed_model_identity.py --tb=short --basetemp=.codex_runtime/qa-runtime-fixed-pin-final-20260917-r3
```

成功信号：33 passed；身份不符时探测 ok=false、退出1。合同通过不代表线上答复准确率。

## 新鲜生产只读状态

Reliable SSH身份检查已恢复。生产仍为V26，提交7d8a2b1a73fbd3e5b30cf800135ec32c3fa5548e，V27—V44未应用。
此前单独读取曾见固定别名与另一份驻留摘要不一致；最新 tags→ps→tags 三次读取均为 `9111be230d48e53a385a28930fb8cf6972767c83e93c0db51f6b331a534e30fb`，不满足固定底座。
旧恢复任务仍启用并运行，固定管理器未安装。旧 /api/ollama/status 返回ok不能证明固定摘要就绪。
r3集合953题已完成，原进程已退出，不重启或重放。822失败/部分题本轮零发送，无法给出新版全量准确率。
32个范围文件哈希已私有保留，17项只读依赖无缺失。源库只读启动连接确认两个CASCADE外键、无活跃用户触发器、public.vector；这不证明源库发布或迁移已完成。

## 后续门禁与影响面

只改本机只读验收工具、测试和追踪文档。0模型生成/切换/卸载，0原题POST，0服务重启/计划任务变更/数据库写/生产写，33项状态及历史语义统计不变、0销项。
旧恢复任务治理、11434驻留纠正和数据库源发布各需独立授权与验收；不得自动卸载其他驻留或恢复旧双模型切换策略。
通过固定身份、源库及8093守卫门禁后才进行原失败题单次复问。首次数据集同摘要未经证明，不能宣称严格同底座配对收益。
