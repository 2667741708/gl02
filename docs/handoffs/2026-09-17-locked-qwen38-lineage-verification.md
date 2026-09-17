# 220.12 锁定底座 Qwen3.8-27B 来源核验

状态：只读来源核验及独立切换根因调查完成；生产禁切换策略尚未验收。
最后核对：2026-09-17。问题：Q-QA-LOCKED-QWEN38-LINEAGE-20260917。
权威来源：Reliable SSH 实际模型 API、Ollama manifest/config 和 GGUF 元数据，以及固定上游 revision 的文件摘要；历史交接仅作为来源索引。
适用边界：220.12 已安装的冻结底座身份与来源，不证明业务微调、模型效果或生产永久锁定。

## 结论与三层身份

用户指出锁定底座应为 Qwen3.8，已找到直接权重元数据支持。不能把 `qwen35` 架构名称直接解释成 Qwen3.5 发布版本。

|身份|冻结底座|本轮观察到的另一底座|
|---|---|---|
|版本标签|`chiqiongblastfuenace:1`|`chiqiongblastfuenace:0`|
|manifest SHA-256|`e4ad74c41d68de1c8004419d8141a2b2df2275fa08f0dcf326ca0e63fb6d8124`|`9111be230d48e53a385a28930fb8cf6972767c83e93c0db51f6b331a534e30fb`|
|模型权重 layer SHA-256|`31629f53165ab6a7dad8c9847dcfd1fdf55829dac1e6e748f4a68581b0033d34`|`d4b8b4f4c350f5d322dc8235175eeae02d32c6f3fd70bdb9ea481e3abb7d7fc4`|
|GGUF 文件字节数|18,973,870,432|17,420,420,832|
|Ollama 参数量 / 量化|26.9B / Q4_K_M|27.8B / Q4_K_M|
|GGUF 架构|`qwen35`|`qwen35`|
|直接来源证据|GGUF `general.name=Qwen3.8-27B`、`general.size_label=27B`|API `details.parent_model=qwen3.5:27b`|
|GGUF tensor / metadata 数|851 / 39|1307 / 53|

业务标签、manifest 摘要、实际权重 layer 摘要分别记录；同名标签不能代替权重身份检查。
26.9B 是本机导入产物的参数量报告，不能据此否定其 Qwen3.8-27B 来源，也不能与另一份 27.8B 权重混写。

## 来源闭环

- GGUF 在 `F:/Ollama/models/blobs/sha256-31629f53165ab6a7dad8c9847dcfd1fdf55829dac1e6e748f4a68581b0033d34` 实际存在，头部为 GGUF v3，模型名明确为 Qwen3.8-27B。
- 只解析文件头和元数据，跳过 tokenizer 数组；不加载权重，不读取模板正文，不调用推理。本轮没有对 19GB 文件重新执行完整内容哈希，文件名及 manifest layer 摘要不能表述为本轮全文件重算结果。
- 既有 model catalog 指向 `ggml-org/Qwen3.8-27B-GGUF`、固定 revision `0669b98607d47046c7c2b3f801011d54a08cfccf`、文件 `Qwen3.8-27B-Q4_K_M.gguf`，记录大小及 SHA-256 与上述产物身份一致。
- [固定 revision 上游文件](https://huggingface.co/ggml-org/Qwen3.8-27B-GGUF/blob/0669b98607d47046c7c2b3f801011d54a08cfccf/Qwen3.8-27B-Q4_K_M.gguf)公布的 SHA-256 亦为 `31629f…3d34`。
- [Qwen 官方 Qwen3.8-27B 配置](https://huggingface.co/Qwen/Qwen3.8-27B/blob/main/config.json)使用 `model_type=qwen3_5` 和 `Qwen3_5ForConditionalGeneration`，说明架构标记不足以区分发布版本；该上游页面是核对时的当前内容，产物来源仍以上述固定 revision 为准。

历史来源入口位于原主工作树 `docs/handoffs/2026-08-22-22012-ollama-one-click-switch-and-qwen38-evaluation.md` 与 `tools/ollama_model_switch/model_catalog.json`；只读保留，未修改这些文件。

## 微调证据边界

现有来源记录支持“导入固定 Qwen3.8-27B GGUF 并使用业务标签”。本轮没有核验到高炉业务训练 run、基座 revision、adapter、合并过程和最终导出血缘，不能据此宣称“已经基于 Qwen3.8 做过业务微调”。用户如有独立训练工件，后续按相同身份链核验；本次不重新下载、训练或更换底座。

## 时间线与生产边界

- 22:11:53（Asia/Shanghai）：`tags -> ps -> tags` 中 `latest` 与驻留摘要为冻结 `e4ad…`。
- 22:12:13：单独读取 `latest` 元数据返回另一权重 `d4b8…`；不与上一时刻合并成稳定快照。
- 22:12:34：`tags -> show -> ps -> tags` 中 `latest` 摘要为 `9111…`，权重为 `d4b8…`，显存报告 23,888,371,072 字节。
- 22:21:10：独立只读 API 核查再次观察 `latest/:0=9111…`、`:1=e4ad…`、唯一驻留 `latest=9111…`。生产 HEAD 为 `e3cca548033736f31500f703aa877a6b519a1977`，代理 SHA-256 为 `d84cfe9d67ded7344e9c15b9de10c807d6d3846fc872b8f53d66b8bfaffe8382`，r3 completed/total=953/953。

这些快照证实漂移，不单凭快照认定改写执行者；[独立调查](2026-09-17-model-identity-switch-independent-audit.md)已另核对每分钟恢复任务、实际 Repair 运行入口、先改标签后验收的代码以及双候选失败日志，支持跨底座 fallback 的反复改写闭环。两次预热服务端均返回200，后续具体失败阶段仍未核实，不能直接称为预热失败。
唯一允许的业务底座仍为 `chiqiongblastfuenace:latest + e4ad…`，禁止把 `9111…` 重新批准为基线。
本轮根因及来源调查没有模型切换、cp/create/rm、加载/卸载、任务或服务修改、业务问答 POST；`/api/show` 是只读元数据请求，不能计为推理或原题复测。

生产尚未完成禁切换验收，不能声称“已经确保仅使用冻结底座”。既有固定管理器安装方案与运行时门禁见[单一底座强约束](2026-09-17-qa-single-base-model-policy.md)。

## 本轮固定身份合同验证

五组已有回归实际 **61 passed，21.83秒**：固定身份、禁切换管理器、旧双摘要窗口禁用、批次身份及管理器安装事务。

```powershell
python -B -X utf8 -m pytest tests/test_qa_fixed_model_identity.py tests/test_qa_single_model_guard.py tests/test_qa_fixed_model_window.py tests/test_qa_batch_identity.py tests/test_qa_fixed_manager_install_transaction.py -q --basetemp .codex_runtime/qa-model-identity-audit-20260917-r1
```

该临时目录已经使用，复现时必须选择未存在的新目录。回归不调用生产推理，不能推导生产禁切换已生效、稳定驻留或原题准确率；本轮不更改既有33项问题关闭状态。
