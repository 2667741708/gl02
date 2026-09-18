# 完整候选原生加载与请求链路门

状态：V45-r2原生加载及完整合成Handler合同通过；生产固定身份阻断，候选未上线。最后核对：2026-09-17。
需求：REQ-QA-FULL-CANDIDATE-RUNTIME-20260917；关联QAOPT-T01/T03/T05/O01。权威：[脱敏证据](../../tests/qa_regression/full_candidate_runtime_20260917.json)、[33项执行账本](../../tests/qa_regression/optimization_execution_ledger_20260916.json)。

## 验证缺口与本轮补强

此前大量边界测试抽取冻结proxy的AST函数，不能证明完整应用入口和所有依赖可加载。本机隔离工作树缺少生产ASR和ABC运行时等模块，原主树又缺少部分新QA模块；不得混用旧模块或填假依赖后宣称候选可运行。

本轮新增[完整探针](../../tools/qa_full_candidate_probe.py)，在生产独立Python3.11.9进程中用RAM import finder执行冻结源字节；依赖使用实际生产源字节，禁用旧.pyc路径并复核执行前后哈希。全程不切换服务或模型，不上传、落盘候选Python源文件。完整加载16个冻结模块和59个实际项目依赖，两个入口proxy/MCP均成功，依赖无变化或未绑定项。

## 可逐项核对的结果

| 合成合同 | HTTP/事件 | 结果 |
|---|---|---|
| JSON已提供数据分析 | 200；1次模拟请求 | 通过；完整prepare、Prompt摘要、持久化与响应一致，无MCP工具 |
| JSON代码示例禁止 | 200；0次模拟请求 | 通过 |
| JSON跨owner | 404；0次模拟请求 | 通过；无消息写入 |
| JSON其他权重 | 500；0次模拟请求 | 通过；code=fixed_model_identity_not_ready，无助手消息 |
| JSON其他用户占用 | 409；0次模拟请求 | 通过；无自动重发 |
| JSON重复请求ID | 409；0次新增模拟请求 | 通过；无新消息 |
| JSON持久化前取消 | 409；1次模拟请求 | 通过；无助手消息 |
| SSE已提供数据分析 | start→start→delta→final→done | 通过；摘要与持久化一致 |
| SSE代码禁止 | start→start→delta→final→done | 通过；0次模拟请求 |
| SSE其他权重 | start→start→error | 通过；无final、模型请求或助手消息 |

认证session、数据库连接、传感器snapshot provider、模型transport和heartbeat线程启动五个外部边界为合成夹具。真实模块安装钩子、owner检查、完整prepare、JSON/SSE、固定底座解析/请求构建、完成策略、持久化与响应方法均执行；没有抽取AST代替完整模块。上述10项是合同验证，不能算真实模型答案、数据库、并发或生产准确率。取消用例的1次请求也是内存模拟，没有向生产模型发送。

34项本机边界与证据拒绝测试通过（7.25秒），gpt-5.6-luna low独立只读复审PASS。覆盖连接/监听/DNS/进程/写文件/线程/原生DB连接禁止、异常被捕获后仍不能判通过、真实缺失依赖拒绝、包内相对导入及源哈希绑定，以及陈旧/篡改/缺项/越界报告拒绝。

初始只读导入因Windows stdlib platform.machine()读取OS元数据需要ver子进程而被严格拦截；改为候选guard之前预热stdlib OS元数据，未放开候选进程权限。首轮完整JSON合同3通过、1未通过：探针错误读取error_code，实际稳定字段为code；修正探针后复核通过，不是助手代码修复或降低标准。保留私有初始证据。

## 发布前必须运行的门

[生成器](../../tools/build_qa_full_candidate_probe.py)绑定最新冻结manifest和探针源SHA，将脚本只写入本机忽略目录，O_EXCL拒绝覆写；不授予部署权限。两个CLI --help和以下生成、校验入口均实际通过：

```powershell
python -B -X utf8 tools/build_qa_full_candidate_probe.py --dependency-root 'F:/高炉炼铁项目-real-sensor-v2_V4_8093_PREVIEW' --output-script .codex_runtime/qa-full-import-20260917/remote-final-script.private.py
python -B -X utf8 tools/verify_qa_full_candidate_probe.py --evidence .codex_runtime/qa-full-import-20260917/remote-final.private.json --output-read-scope .codex_runtime/qa-full-import-20260917/transitive-read-scope-final.private.json
python -B -X utf8 -m pytest -q tests/test_qa_full_candidate_probe.py tests/test_qa_full_candidate_probe_evidence.py --tb=short --basetemp=.codex_runtime/qa-full-import-20260917/pytest-final-r3
```

首条生成命令不能直接重复执行原输出文件；参数须使用新的受控私有执行编号。脚本通过已验证Reliable SSH exec_argv的Python -B -X utf8 -和stdin执行，remote不落源码，不直接ssh或自动重放。成功JSON ok=true/退出0；任何加载、I/O或合同失败ok=false/退出1。传输不确定只能只读核对。

[证据校验器](../../tools/verify_qa_full_candidate_probe.py)拒绝非当前manifest/probe、非Python3.11、缺失冻结模块、失败合同、写入/调用计数、未绑定/变化依赖和越界路径。生成的全部59项transitive依赖及SHA必须纳入后续8093守卫read_set，密封前重新验证；不能仅沿用旧17项依赖。真正发布仍需要固定身份就绪、源库/迁移合同、EOL/recordability、完整范围/共享功能及8093受控切换验收。

## 生产现状与边界

当前HEAD df9dde1abe06b386906a2bfad508403732fd40ae新增四项总览静态资源路径，已只读确认与QA后端范围分离；proxy/MCP仍为V26哈希。r3为953/953 completed，原PID已退出；不重启、重发收集进程。

最新tags→ps→tags的latest别名和驻留仍为9111be…，与此前冻结e4ad74…不一致。用户明确禁止模型切换或重新定义底座，生产模型保持原状；暂停822原失败/partial题复问，不计算新版全量准确率。本轮0生产写入/真实模型调用/原题POST/销项，V45-r2候选字节、33项问题状态及历史语义统计未变。

旧恢复任务/管理器治理、11434固定驻留纠正和数据库源发布仍需分别按授权边界验收。完整合成链路和独立审查不能代替这些门或真实线上语义复测。
