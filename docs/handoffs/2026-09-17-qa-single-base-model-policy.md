# 智能助手单一底座强约束

状态：固定身份本机实现及候选已验证；禁切换管理器尚未安装，生产身份门未满足。当前路由候选及共享生产变更以[最新交接](2026-09-17-qa-shared-proxy-integration.md)为准；下文V27/V26记录为历史阶段证据。
最后核对：2026-09-17。需求：REQ-QA-SINGLE-BASE-MODEL-20260917、OPS-QA-SINGLE-BASE-GUARD-INSTALL-20260917，关联QAOPT-O01/QAOPT-T05。
权威来源：用户新增“不允许更换、切换模型”要求、Reliable SSH只读身份与文件哈希、候选AST保留检查、实际隔离回归及独立代码审查。

## 固定合同

固定业务别名`chiqiongblastfuenace:latest`，唯一底座digest：
`e4ad74c41d68de1c8004419d8141a2b2df2275fa08f0dcf326ca0e63fb6d8124`。
该底座来自已经冻结的V26复测身份及本轮初始实际驻留的版本1；不能因后续漂移重新选择。

|控制面|必须满足的规则|本机实现|
|---|---|---|
|普通问答/工具分析/降级回合|每次模型POST前都核验别名与唯一实际驻留的同一digest；不得按名称误判身份；覆盖客户端model元数据|V27三函数补丁、`qa_fixed_model_identity.resolve`|
|只读身份检查|tags→ps→tags，总预算6秒，最多3次GET检查；取消继续传播；不POST、不加载、不重放|固定身份模块，11项回归|
|模型恢复|仅允许同一已安装底座；已健康驻留不热身；无驻留时可重新加载同一底座；另一底座/多驻留直接阻断，不卸载或替代|固定管理器，16项回归|
|切换入口|Switch全部禁用，包括此前批准的版本0以及同目标Switch；Sanitize禁止模型修改；初始化和Repair只能固定底座|管理器5函数替换、5助手函数|
|别名元数据修复|只有没有其他底座驻留时，才允许已安装固定版本→固定公共别名；不得据此选择另一权重|固定Repair及真实控制流夹具|
|复测身份|plan必须携带上述固定name/digest；缺失、重新定义、另一版本、多digest池全部在发送前拒绝|batch 8项回归；旧双批准池窗口已在入口禁用|
|状态接口|required digest与实际已核验digest分开；身份失败不返回实际已核验digest，不报告model_ok|V27 status回归|

禁止其他模型不影响数据查询、确定性统计、现有证据分析和无工具问答。代码执行和生成代码示例继续禁用。路由、Prompt、工具合同与知识证据可以完善，但所有模型回合保持同一底座；不得通过换模型解释修复效果。

## 当前生产缺陷

本轮初始只读检查：实际驻留版本1，公共别名版本0，状态记录偏好/有效版本仍为1。
本轮后续独立只读检查：公共别名和实际驻留均变为版本0，说明原后台恢复任务仍在切换。
这些是先后两个真实快照，不应混写成同时状态；新约束没有在生产生效，不能声称已经阻止切换。

当前版本0的digest `9111be230d48e53a385a28930fb8cf6972767c83e93c0db51f6b331a534e30fb`不再是允许的替代底座。
固定管理器遇到它必须阻断，不能自动切换回版本1。安装禁切换管理器与恢复已经冻结底座需要分开证明和验收。

## 候选与保留边界

### V47集成期间的后续独立快照

UTC2026-09-17 11:59的Reliable SSH tags→ps→tags独立检查中，固定公共别名与唯一驻留记录均为`9111be…`，不符合冻结的`e4ad74…`。下文V46后快照中的tags=e4/ps=9111是较早观察，不能混写为本次同时状态。V47完整原生探针以合成e4身份测试拒绝/通过逻辑，不验证真实生产身份；0真实模型调用/原题POST/换模/生产写。仍不得自动修复标签或切换到另一个驻留权重，详见[最新集成交接](2026-09-17-qa-shared-proxy-integration.md)。

### 最新强约束核查（2026-09-17，V46后）

用户再次明确禁止更换或切换模型。固定名称和上述完整digest不变，禁止备用模型、同名更换权重、重新选择基线；身份失败不得发送模型POST或重放原题。已有固定身份实现无需改变pin。

本次Reliable SSH独立只读检查依次为tags→ps→tags：两次tags中`chiqiongblastfuenace:latest`均为冻结的`e4ad74…`，唯一实际驻留记录同名但digest为`9111be…`。该快照证明别名与实际驻留不一致，不证明已经锁定底座，也不据此认定变更执行者。没有进行cp、加载、卸载、切换、任务或服务变更，没有发送问答POST；线上同底座复测继续受阻。

同期生产HEAD为`cdd390cc386ce486d8a4685ebe060b8eeda7c38a`，代理SHA256为`d84cfe9d67ded7344e9c15b9de10c807d6d3846fc872b8f53d66b8bfaffe8382`；r3为953/953，PID18224查询计数为0。固定身份、旧双底座入口禁用、管理器控制流三组隔离回归实际**44通过，15.09秒**：

```powershell
python -m pytest -q tests/test_qa_fixed_model_identity.py tests/test_qa_fixed_model_window.py tests/test_qa_single_model_guard.py --basetemp=.codex_runtime/qa-immutable-base-constraint-20260917-r1-pytest
```

该basetemp已使用，复现必须换一个未存在的新目录。第一次默认系统Temp夹具出现23个权限错误、21通过；改用新工作树目录后44全部通过，不将夹具错误计为线上问题。首次Get-Process抑制错误查询返回非零且无结果，改为进程列表筛选计数后确认0；没有重启或重放。测试验证本机控制逻辑，不能推导生产已生效或回答准确率。原33项状态及原题统计保持不变。

### 用户再次确认后的只读复核（2026-09-17）

用户再次要求“不允许更换模型切换模型，持续使用完全相同的底座”；唯一允许的名称与digest继续按上述冻结合同执行，禁止将观察到的漂移作为新基线。

本次两个先后快照必须分别解释：第一次`tags`有4个已安装模型、`ps`有1个驻留模型，固定名称在两处均未匹配冻结digest，且同名不同digest；第二次`tags`中的该名称匹配冻结digest，但`ps`没有该名称对应的驻留记录。第二次仅证明该次查询时别名权重匹配，不证明稳定驻留或已完成禁切换。探测没有加载、卸载、复制或切换模型，没有发送问答POST，也不据此确认后台变更的执行者。

生产管理器仍为旧SHA256`856f38b6edb088327e2138b88e68961db1a153b451aedb6709bea9fd2a8e99fa`。独立`Get-ScheduledTask`查询确认恢复任务`Enabled=true`、`State=4`（Running）；此前XML查询未取得Enabled字段，不能将空字段解释为禁用。生产仍为V26，HEAD及代理hash与本记录基线一致；r3为953/953完成，初始PID18224不存活。

因此继续冻结线上复测发送，按既有单独授权边界安装禁切换管理器并验证固定身份后再恢复。路由、提示词、工具和知识证据修复可以继续在本机推进，不能用更换底座规避问题。

本次身份、管理器、旧双底座入口禁用、批次身份四组隔离回归实际46项通过（14.60秒）。命令：`python -m pytest -q --basetemp=.codex_runtime/qa-single-base-confirmation-20260917-r1 tests/test_qa_fixed_model_identity.py tests/test_qa_single_model_guard.py tests/test_qa_fixed_model_window.py tests/test_qa_batch_identity.py`。默认系统Temp曾触发31个夹具权限错误，改用全新工作树隔离目录后全部通过；不计为线上题目失败或回答准确率。

- 生产原管理器SHA256：`856f38b6edb088327e2138b88e68961db1a153b451aedb6709bea9fd2a8e99fa`。
- catalogSHA256：`723c4f2c6e5c2093060db8beaf5338dc857477a5b10d5db9f95ec79dfdc2f57a`；无需修改catalog。
- 固定管理器候选SHA256：`1dc63bc93135b4da644c5f6187f8002b9e6f5add2d4216e4e97ed3044f9772f0`。替换Activate-Model、Initialize-State、Invoke-Switch、Invoke-Sanitize、Invoke-Repair；保留30其他函数及顶层mutex/dispatch。
- V27从已验收V26代理SHA256`47b7e75f6a4c2b932ac21b0dd9628d4c049f7a6f2ee083537bbedf1a6c57f431`构建，仅改resolve_upstream_model、build_ollama_request、handle_ollama_status并增加固定身份模块导入，其余AST一致。
- V27代理SHA256：`79849e555560655cc12bda7c58a2617e47765106b266735d102524a2992b969e`；固定身份模块SHA256：`e1251801bb9e4e1eb29e78ee138b34ba3bea95b68b46a95f0f960d65ded48c1d`。
- 原r1/r2模型稳定性候选保留复现与审计价值，但已被本要求取代，**禁止部署r2的批准fallback策略**。旧复测窗口r2不再允许执行；未覆盖任何旧冻结计划或已发送题。

## 实際验证及复现

52项当前合同检查通过：固定身份11、固定管理器16、V27真实替换函数8、batch身份8、安装事务9。七个相关PowerShell文件本机解析通过，管理器和V27及独立安装器均经gpt-5.6-luna low只读独立代码审查PASS。

```powershell
python -m pytest tests/test_qa_fixed_model_identity.py tests/test_qa_v27_fixed_base_candidate.py -q
python -m pytest tests/test_qa_batch_identity.py -q --basetemp .codex_runtime/qa-single-base-model-20260917/pytest-batch-new
python -m pytest tests/test_qa_single_model_guard.py tests/test_qa_fixed_manager_install_transaction.py -q
```

`--basetemp`父目录须先存在，且每次使用新子目录。本轮合并执行曾出现19通过/5默认Temp权限夹具错误；仅batch改用工作树隔离目录重新5通过，增加3项固定plan检查后实际8通过。管理器夹具前次动态作用域变量错误已修复，最终16通过。不得将这些夹具错误记作线上问答失败。

## 独立生产安装方案与授权

受控安装器：[install_qa_single_base_manager.ps1](../../tools/install_qa_single_base_manager.ps1)，事务库：[qa_fixed_manager_install_transaction.ps1](../../tools/qa_fixed_manager_install_transaction.ps1)。该候选流程已审查，但没有运行：

1. 精确staging路径及候选、事务库哈希；独立operation mutex与持久化一次性操作目录；目录已存在则只读恢复，不重放。
2. 只暂停BFOllamaModelSelectionRecovery未来触发；原Enabled先记录并在部分失败前取得恢复责任。允许已有运行者结束，最长10分钟；取得Global\\BFOllamaModelSwitch并再次确认旧任务不Running。
3. 复核生产管理器/catalog基线、模型tags/ps和受保护端口PID。备份管理器，使用同卷File.Replace原子安装固定管理器；不改catalog，不执行cp、warmup、加载、卸载或切换模型，不停任何服务。
4. 复核新管理器hash、catalog不变、模型身份和受保护PID不变。只有源策略验收成功才恢复原Enabled；原禁用保持禁用。实际驻留非固定底座时`identity_ready=false`，不得伪称模型恢复。
5. 安装失败可回滚源，但Recovery必须保持禁用，避免再启动旧切换策略；finally失败、回滚失败均不得启用旧管理器，记录需要处理的失败状态。

项目AGENTS.md第5节要求计划任务修改“单独明确授权和独立验收”；部署skill要求相关scheduled task操作单独授权。先取得这项范围授权，再运行上述独立安装器。随后固定底座身份满足时才准备8093 V27密封发布、健康验收和Git记录；当前身份漂移不能跳过验收或触发自动换模。

V26原822题批次仍为0发送、0完成；首次1233有效题的636失败/186部分没有新增优化后答案。完整复测继续保留同题、同底座、无自动重放口径，不能从52项本机检查推导生产准确率提升。
