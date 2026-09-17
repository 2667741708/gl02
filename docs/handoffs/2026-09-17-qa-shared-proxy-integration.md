# QA候选保留生产ABC33共享代理修复

状态：本机候选已冻结，32模块808项回归通过（116.21秒），19项原生合成合同已通过；完整本机回归结果见[机器证据](../../tests/qa_regression/shared_proxy_integration_20260917.json)。未部署，固定底座身份门仍阻断。
最后核对：2026-09-17。需求：REQ-QA-SHARED-PROXY-INTEGRATION-20260917，关联QAOPT-R01/R06/R07/R08/T03/T05/O01。
权威：用户固定底座约束、Reliable SSH固定Git对象及实际文件哈希、全AST差异证明、冻结V46-r2/V47-r1、Python3.11.9完整加载与实际Handler合成合同、独立代码审查。适用边界：8093候选集成，不授权11434、任务、DB或其他服务修改。

## 实施范围及保留证明

生产HEAD `cdd390cc386ce486d8a4685ebe060b8eeda7c38a`新增ABC33展示逻辑；旧V46代理不能直接覆盖。只合并下列3个函数及1个导入：

- `with_public_detail_semantics`
- `Handler.handle_furnace_rule_detail`
- `Handler.handle_public_furnace_rule_breakdown`
- `furnace_display_policy`的`build_display_policy/build_unified_summary/display_name`导入。

[只读差异探针](../../tools/probe_qa_shared_proxy_delta_readonly.py)将3个新函数归一化为旧函数并移除唯一审查导入，证明剩余全AST完全相同；不只比较具名函数，不放过新常量、顶层操作或其他导入。重复、缺失、未覆盖变化直接拒绝。

[候选构建器](../../tools/build_qa_shared_proxy_candidate.py)绑定V46-r2清单、生产HEAD/代理哈希、私有片段文件哈希和2个共享依赖哈希。候选16文件中15个逐字节继承；V46完整`prepare_qa_chat`源门保留，固定底座模块及Prompt绑定模块不变。生产静态文件和其他并行改动没有进入写集合，也没有被覆写。

类方法按原`Handler`作用域解析，避免`dedent`改变三引号字符串值。AST兼容层仅移除Python3.12+空`type_params`，非空泛型语义拒绝；显式保留3.13默认隐藏的空字段，使3.11与3.13证明一致。全文件仍执行UTF-8/LF及AST检查。

候选为V47-r1，manifest SHA256 `3deab6a3937a3a2afab099b0cabea0277c507176bf326f2529845a24116defe6`。冻结文件不覆盖，发布前还需新鲜生产探测和密封门。

## 原生与合成验收

[完整探针](../../tools/qa_full_candidate_probe.py)、[生成器](../../tools/build_qa_full_candidate_probe.py)、[证据校验器](../../tools/verify_qa_full_candidate_probe.py)在独立Python3.11.9进程RAM加载16候选模块和60实际项目依赖，不在服务器落候选源码，不查询真实业务数据，不调用真实模型。

2个共享依赖在执行源码前核验pin，执行后再次核对实际加载/当前文件字节。未导入、变化、被捕获的导入拒绝都不能变成通过；verifier要求pin与冻结manifest及完整来源记录一致。受控read_set为60个依赖；密封前必须重新检查，不能把一次探测当作永久状态。

10个原有QA合同覆盖JSON/SSE、给定数据、代码禁用、owner、固定权重、占用、重复请求及取消；受限sensor读取计数均0，保留页面快照归档并隔离证据。

9个共享实际Handler合同覆盖：公开breakdown.v2与综合判断、未发布分数不参与判断、公开detail.v3、过期detail无分数、受保护breakdown拒绝、非法evaluation、未知规则、缺批次、缺detail。配置阈值来自合成provider，未修改评分算法或现有公共/受保护边界。

QA合同有5个合成外部边界；共享合同另有配置provider、ABC数据库、持久化review、权限结果和HTTP捕获5个边界。实际Handler及实际展示/评分模块执行；这不验证真实数据库、权限会话、浏览器或模型答复。模型错误摘要必须停止发送，不能启用另一模型完成测试。

## 保留失败及复现

首轮构建发现跨Python AST空字段差异，随后发现类方法整体dedent改变SQL字符串；修正解析方式后6个新旧函数摘要匹配，原审查哈希未放宽。

首轮原生共享合成合同有1个失败：夹具误用输出字段`score_available`作为持久化输入。依据真实`abc_rule_engine.public_rule`改用`score_released=False`；“不参与判断、缺失增加、needs_data”断言保持。修后10QA+9共享全部通过；初始失败报告保留私有目录，不能算作原题生产失败。

首轮32模块本机回归806通过/2失败；2个失败为Windows子Python输出编码未固定UTF-8。测试子进程改为`-X utf8`及明确UTF-8读取，完整重跑结果见机器证据；不修改候选行为或评分。14项金标schema验证通过。gpt-5.6-luna low独立有界集成审查及夹具复审PASS。

```powershell
python -B -X utf8 tools/build_qa_shared_proxy_candidate.py --revision rN
python -B -X utf8 -m pytest -q tests/test_qa_shared_proxy_integration.py tests/test_qa_sensor_context_source_gate.py tests/test_qa_full_candidate_probe.py tests/test_qa_full_candidate_probe_evidence.py --basetemp=.codex_runtime/qa-shared-new-run
python tools/evaluate_mcp_gold_tasks.py --validate
```

rN只能选择未存在的r1/r2/r3/r4；basetemp也必须新建。完整32模块命令、最终计数与时长见机器证据。原生生成器、Reliable SSH stdin执行及证据校验输出均保留受控私有目录；公共产物只冻结脱敏合同/哈希/计数，无生产会话、原文条款、测量值、身份或凭据。

## 当前发布门与剩余工作

冻结模型名称`chiqiongblastfuenace:latest`及完整e4ad74…8124摘要不变，禁止切换、备用、同名换权重或新基线。前次只读看到tags为e4而ps为9111；随后UTC11:59独立tags→ps→tags均为9111。两个先后快照分别保留，说明身份仍不符合冻结合同，不据此判断变更执行者；没有模型操作或原题POST。

本轮0生产写、真实模型调用、原题重发、服务/任务修改或销项。33项状态、首次统计及822原失败/partial复测范围不变。公开共享接口合成通过也不能推导生产准确率。

下一步继续修复普通非受限免工具问题仍提前加载炉况的路径，同时保留多轮和ABC权威上下文。8093发布前须通过新鲜固定身份/依赖、完整共享功能、EOL/recordability、精确写读范围及受控守卫。管理器/恢复任务和DB源发布保持独立授权边界；不能用换底座绕过。满足发布门后再单次复问原题、逐项审查最终答案，才更新实际成功率和正确率。
