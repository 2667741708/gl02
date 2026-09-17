# 测试参考

## REQ-QA-LATEST-PREFETCH-REUSE-20260917 / V24

[最新值复用与禁代码承诺回归](../tests/test_qa_latest_reuse_and_code_offers.py)连同证据策略/统计范围共76项通过。5道原题真实发送后独立全文审核1通过/3部分/1失败，传输5/5；身份稳定4题完整1题，仅小样本。402题逐条依赖阻断，已发送不重放。[复现、结果哈希和剩余方案](handoffs/2026-09-17-qa-v24-latest-reuse-and-code-boundary.md)。

## REQ-QA-STATISTICAL-SCOPE-20260917 / REQ-QA-SINGLE-WINDOW-OBSERVATION-20260917

新增[test_qa_statistical_scope.py](../tests/test_qa_statistical_scope.py)、[test_qa_single_window_routing.py](../tests/test_qa_single_window_routing.py)、[test_qa_batch_identity.py](../tests/test_qa_batch_identity.py)，覆盖总体标准差独立复算、CV无效域、趋势双信号范围、实际生产渲染前后对比、单窗观察正反例和模型标签/驻留不一致。最终105项通过，真实V22六题单列全文审阅，V23的407失败题复测进行中；正确率与传输率不混用。[复現与验收](handoffs/2026-09-17-qa-v23-single-window-routing.md)。

## REQ-QA-INITIAL-828-SEMANTIC-REVIEW-20260916：待审全集一致性门

限定`gpt-5.6-luna`逐题离线审阅828份首次已有答复，进行中，无生产POST。完成后运行`python -X utf8 tools/validate_qa_initial_828_review.py --report tests/qa_regression/initial_828_semantic_review_20260916.json`，预期`ok=true`、`reviewed=828`、`remaining=0`及首次结果哈希一致。此命令只验证范围与隐私字段，不重新判语义，不代表已通过全量审核或准确率。

## REQ-QA-PAIRED-FAILURE-RETEST-20260916：原题复测观察

首次405确认失败题加原8题的新轮413题计划已冻结；4题有确定结果，内容独立审核3通过/1部分正确，观察内容准确率75%、传输完成率100%，不能外推全集或称固定模型评测完成。模型digest漂移在第5题发送前阻断；409题未发送。前后模型身份核验仍需补强，真实双角色/取消验收待测。[脱敏逐题报告](../tests/qa_regression/routing_v21_paired_observations_20260916.json)、[复核与阻断证据](handoffs/2026-09-16-qa-routing-v21-paired-retest.md)。

## REQ-QA-EXCLUSIVE-USE-20260916：全角色独占回归

[test_qa_exclusive_use.py](../tests/test_qa_exclusive_use.py)以真实控制模块、合成身份验证6组角色对、取消保持占用、失败释放和同时注册竞态，共9项通过；关联来源绑定与测试持久化共35项通过，独立应用审查通过。命令：`python -X utf8 -m pytest tests/test_qa_exclusive_use.py tests/test_qa_context_provenance.py tests/test_qa_retest_persistence.py -q --basetemp .codex_runtime/pytest-exclusive-new-run`。0生产POST、0模型调用；V21已受控发布并通过字节/PID/CAS验收；真实角色409与取消现场行为仍待测。[证据](handoffs/2026-09-16-qa-exclusive-use-local.md)。

## V20 指代趋势追问（2026-09-16）

规划器新增“这个/那个/这些/它们/刚才/上面”指代识别，明确新对象仍优先当前问题。V19失败的30分钟追问现走确定性统计；真实五题与数据库只读来源各5/5通过，模型趋势解释被可信守卫拒绝单列。仅更新8093代理，模型配置不变；整体33项仍执行中。[权威证据](handoffs/2026-09-16-qa-routing-v20-production.md)。

## V18–V19 多轮来源与适配器修复（2026-09-16）

V19发布前107项不同测试通过，包括真实PgCompatConnection/CursorAdapter；生产6POST、5passed/1answer_contract_failed、0重发；6/6数据库只读来源proof。续跑器新增2项已发送claim拒绝和会话依赖恢复测试（持久化共7项）。 [权威证据](handoffs/2026-09-16-qa-routing-v18-v19-production.md)。

## V17 历史复合回归（2026-09-16）

长期反例见 `tests/test_qa_history_completion.py`，覆盖旧原文合同、对象不符、重复对象、非有限值、缺时间/来源、明确失败、趋势分析和禁工具。合并历史/来源/原文/持久化回归 133 项通过；实际生产五题独立通过，已发轮次不得重放。[复现与脱敏报告](handoffs/2026-09-16-qa-routing-v17-production.md)。

## V15生产复测与长期回归（2026-09-16）

新增`tests/test_qa_context_boundaries.py`、原文多引用测试及选中章节缓存删改失效测试。112个不同聚焦测试通过；9批实际KB只读检查803项覆盖候选通过、30项阻断。真实5题均逐题独立审查通过，非空和done不计为通过。可复现命令及脱敏产物：[V15交接](handoffs/2026-09-16-qa-routing-v15-production.md)。

## BUG-QA-SELECTED-SCOPE-TAIL-20260916

- 本机候选：完整原子索引不能掩盖所选章节索引的末页缺失；新增同岗位/规程跨索引覆盖门。
- 命令：python -X utf8 -m pytest tests/test_qa_document_integrity.py tests/test_qa_document_knowledge.py -q；38 passed。
- [反例、修复及远端阻断](handoffs/2026-09-16-qa-document-scope-tail-local.md)。尚未部署；真实索引兼容性、原子条款边界及scope元数据独立核验待做。

## TEST-QA-FULL-ISSUE-INVENTORY-20260916：V10–V14

本轮V14针对性35项及实际PowerShell GET就绪故障4项通过，真实定向3题独立语义通过，0自动POST重放。V12/V13分别保留2个失败答案的阶段报告，V14解决压力单位/额外指标问题。
833知识源中有效803题完成一次POST并核验原文覆盖/来源/版本合同；30个oracle冲突阻断，不声称833题全部语义通过。当前数值取[逐项台账](../tests/qa_regression/optimization_execution_ledger_20260916.md)，历史828待审不能直接当当前剩余分母。
命令、独立审查与脱敏报告见[V10–V14交接](handoffs/2026-09-16-qa-routing-v10-v14-production.md)。

## TEST-QA-EVIDENCE-FIRST-REGRESSION-20260915

```powershell
python -X utf8 tools/qa_regression.py
python -X utf8 tools/qa_regression.py --list
python -X utf8 -m unittest discover -s tests -p test_qa_regression.py -v
```

- 对应需求：REQ-QA-EVIDENCE-FIRST-REGRESSION-20260915；[目录、格式、评分及持续扩展](../tests/qa_regression/README.md)。
- 首批验证：30条用例、11组完全合成夹具合法；17项评分器测试通过，包含舍入/编号、伪造值、错误载荷、跨owner、部分失败、时限及审阅绑定。
- 只验证集合与评分器，没有实际模型或生产MCP执行；不报告生产通过率。
- `python -X utf8 tools/qa_regression.py --results tests/qa_regression/run.example.json` 预期退出1：仅有一条人工构造示例，报告待审阅及其余未运行，不得当作全绿。

## TEST-SENSOR-REGISTRY-HOPPER-WEIGHT-SET-20260814

```powershell
python .\tools\verify_foreman_local_point_catalog.py --root .\数据库同步和存取
python .\tools\register_hopper_weight_set_points.py --root .\数据库同步和存取
```

- 本机成功信号：清单 165 行、162 个物理点、3 个派生点、19 个确认项，重复 tag 为 0；
  登记器与 pSpace 搜索/映射脚本均通过 Python 语法检查。
- 生产成功信号：`expected_rows=14`、`registered_rows=14`、`mismatches={}`；既有同步器
  `tags_ok=11`、`tags_error=0`，写入 59 条分钟值和 71 条 raw 值。
- 未通过项不得隐去：`Hopper_weight_set` 本身尚未物化分钟事实；当前验证只证明目录登记与
  11 个物理分量采集成功。
- 证据：[生产登记交接](handoffs/2026-08-14-hopper-weight-set-registry-production.md)。

## TEST-FOREMAN-TREND-TWO-DECIMAL-PERCENT-20260814

```powershell
python -m unittest tests.test_foreman_trend_preview -v
```

- 覆盖：顶部指标固定两位小数、工长趋势原生提示固定两位、共享右键提示固定两位、
  `GasUtil` 历史比例先乘100，以及页面缓存版本入口。
- 成功信号：`7 tests` 全部通过；本机 Chromium/Edge `1280×1024` 冒烟通过，49项指标、
  两张曲线、交互、无横向溢出、页面错误和控制台错误均为0。
- 影响边界：静态前端合同，不连接生产数据库或220.12服务。

## TEST-DIAG-RULES-RELIABLE-DEPLOY-20260806

```powershell
node --check .\tools\reliable_ssh_22012_cli.mjs
python -m py_compile .\tools\deploy_diag_rules.py .\tools\deploy_diag_rules_rssh.py .\tools\build_diag_proxy_payload.py
powershell.exe -NoProfile -ExecutionPolicy Bypass -File '.\tools\check_ps1_syntax.ps1' -Path '.\tools\remote_deploy_diag_rules.ps1'
python -m pytest tests\test_diagnosis_ai_analysis.py tests\test_diagnosis_review_api.py tests\test_diagnosis_review_contract.py tests\test_diag_rules_deployer.py tests\test_diag_rules_reliable_deployer.py -q
python .\tools\deploy_diag_rules.py
```

- 结果：Node、Python、PowerShell语法检查通过；合同测试 `47 passed`；dry-run生成9个业务文件的白名单并确认只重启8093/8094、保护8768/8770/11434。
- 远端只读验证：`reliable_ssh`身份探测成功，目标主机为 `WIN-54B94HVHKBA`、地址包含 `10.30.220.12`、身份为 `administrator`。单独MCP `exec_argv`受30秒客户端窗口限制超时；部署入口使用240秒命令窗口。
- 生产状态：本轮没有运行 `--apply`，所以不记录部署成功或生产验收通过。

## TEST-RECOMMENDATION-FULL-AUDIT-20260806

```powershell
python -m unittest tests.test_recommendation_audit_store -v
python -m unittest tests.test_three_rules_recommendation_engine tests.test_multi_condition_recommendation_and_model_review tests.test_recommendation_audit_store -v
python -m py_compile "自动诊断服务\recommendation_audit_store.py" "自动诊断服务\recommendation_adapter.py" "自动诊断服务\local_pg_ws_bridge.py" "tools\migrate_recommendation_audit.py" "tools\verify_recommendation_audit_runtime.py"
powershell.exe -NoProfile -ExecutionPolicy Bypass -File ".\tools\check_ps1_syntax.ps1" -Path ".\tools\remote_guarded_deploy_recommendation_audit.ps1"
```

- 本地结果：新增7项审计合同通过；三规二制、多炉况和审计组合26项通过。
- 覆盖：八炉况完整性、35条真实动作、四状态枚举、所有审计字段、缺失顺序拒绝、策略哈希、非有限值转JSON空值、幂等首次写入、重复读取不覆盖、8768入库失败关闭建议返回、DDL追加式约束。
- 远端验收器：连接8768两次，必须获得同一 `batch_id`；数据库必须有8个炉况、动作行数与WebSocket一致、完整 `action_payload`、唯一幂等行、运行账号无更新/删除权限、只读账号可查询。
- 当前远端状态：首次部署前置检查被SSLVPN系统路由缺失阻断，尚未执行220.12迁移或重启。

## TEST-8093-HEAT-PERFORMANCE-QUALITY-20260806

- 命令：`python -m pytest tests/test_heat_performance_quality.py 高炉前端数据/智能助手/tests/test_imes_heat_summary_tools.py tests/test_cross_source_mcp.py -q --basetemp .tmp/pytest_heat_bundle4`
- 结果：`66 passed`；包含 psycopg `dict_row` 命名列读取、`date`/`datetime`/`Decimal` JSON序列化回归。
- 结果：64项通过。
- 静态验证：`py_compile`覆盖聚合存储、8093代理和同步器；`node --check`覆盖8093炉次实绩资源；PowerShell解析器覆盖同步运行脚本和受控部署脚本。
- 数据合同：同炉三个Si试样 `0.20/0.25/0.24` 的算术平均值为`0.23`、中位数`0.24`、范围`0.20–0.25`；原始试样保留3条；C/Si/Mn/P/S缺失保持`NULL`而非0。
- UI合同：具备加载、空、失败、刷新、最近炉次和原始试样展开状态；访问8094时不安装8093专用区域。
- 生产验收：全量同步9622炉、增量刷新43炉、服务器本机页面/API 200、最新082炉三试样均值复算一致、每5分钟同步任务和受保护PID检查均通过；本机经VPN浏览器仍出现空响应，未计入浏览器通过项。完整证据见[交接记录](handoffs/2026-08-06-8093-heat-performance-quality.md)。

## TEST-HEAT-QUALITY-REPAIR-CLOSED-LOOP-20260807

```powershell
& 'D:\ProgramData\anaconda3\python.exe' -m pytest `
  'tests\test_heat_performance_quality.py' `
  'tests\test_heat_performance_quality_query.py' `
  'tests\test_heat_performance_quality_repair_loop.py' -q
```

- 结果：`17 passed`。
- 覆盖：修复状态和原始/修复时间不被普通 upsert 覆盖；未到期 `future_pending` 受保护、到期后允许正常同步解除；API 默认过滤未来待核验；结构化原因/核验时间 DDL；Vastbase→原始镜像、Vastbase→汇总、样本数变化三类审计；跨午夜；炉号日期与 `workdate` 冲突；分页、截断和精确指标名。
- 静态编译：`heat_performance_quality.py`、`ollama_proxy_server.py`、`sync_22012_heat_performance_quality.py` 均通过 `py_compile`。
- 边界：本轮是本机实现验证，没有执行 220.12 DDL、同步任务或 8093 生产验收。

## TEST-8093-8094-DIAGNOSIS-REVIEW-AI-20260806

```powershell
python -m pytest -q -p no:cacheprovider tests\test_diagnosis_ai_analysis.py tests\test_diagnosis_review_api.py tests\test_diagnosis_review_contract.py tests\test_multi_condition_recommendation_and_model_review.py tests\test_8094_multi_condition_deploy.py
```

- 结果：`46 passed`；其中 `tests/test_diagnosis_ai_analysis.py` 单独复跑 `12 passed`。
- 覆盖：v3单炉况Prompt与解析、可信变量/建议/知识引用、防篡改、免登录评分、事件表合同、8094共享代理启用脚本、拒绝8769旧架构和隔离保护。
- 远端：8093部署确认分析完成；8094部署返回 `analysisState=completed`、`analysisSchema=diagnosis_ai_analysis.v3`，变量/建议/知识三类依据均存在；8093/8768/8770/11434 PID不变。
- Chrome现场冒烟：实际打开8093、8094诊断页并点击“正常顺行”卡；两端弹窗均显示“已完成”，且可见“智能助手判断 / 为什么得到这个分数 / 调剂引擎1建议依据 / 知识库依据与指导”。8093首次加载遇到一次既有 `three.module.js` 瞬时失败，单次干净重载后页面正常；未把该基础资源问题误记为本功能失败。
- 边界：空模型复核和空人工评分请求返回400，仅验证路由与校验，不写入伪造验收记录。

## TEST-8093-DIAGNOSIS-AI-EVIDENCE-GUIDANCE-20260805

```powershell
python -m pytest -q -p no:cacheprovider tests\test_diagnosis_ai_analysis.py tests\test_diagnosis_review_api.py tests\test_diagnosis_review_contract.py tests\test_multi_condition_recommendation_and_model_review.py
```

- 结果：40项通过。新增覆盖分钟变量统计、规则驱动阈值/权重、调剂引擎1只读复用、知识引用、未知证据ID拒绝、v2固定场景和纯8093部署合同。
- Chromium：`1280×720`、`1366×768`、`1440×900`、`1546×864`、`1920×1080`、`1024×768`、`768×1024`、`390×844`、`375×667` 九视口通过；证据、建议、知识卡完整，弹窗可滚动，页面横向溢出为0。
- 应用内浏览器：实际点击“热制度下行”卡，确认口语化分数解释、变量/基线、调剂引擎1依据、知识来源、安全边界均出现，手动关闭后弹窗不可见。
- 当前v2 Firefox/WebKit：浏览器运行时未安装，下载受当前网络阻断，未重跑；不能把此前v1的8/8结果记作本次v2通过。
- 控制台：新增模块错误为0；现存Babel超大内联脚本去优化提示不属于本模块功能错误。

## TEST-8093-DIAGNOSIS-AI-FIVE-MINUTE-20260805

```powershell
python -m pytest -q -p no:cacheprovider tests\test_diagnosis_ai_analysis.py tests\test_diagnosis_review_api.py tests\test_diagnosis_review_contract.py tests\test_multi_condition_recommendation_and_model_review.py
```

- 结果：37项通过；覆盖5分钟对齐、八类不遗漏/不重复、Prompt禁止改写规则、独立数据库短连接、固定场景、API路由、派生表唯一约束、纯8093部署边界和组合弹窗合同。
- Chromium：规定九视口全部无横向溢出，弹窗在视口内、内容区可滚动、免登录评分可用。
- Firefox/WebKit：`tools/verify_diagnosis_ai_analysis_viewports.cjs` 在 `1920×1080`、`1366×768`、`768×1024`、`390×844` 共8/8通过；新增功能错误和HTTP错误为0。原页面Babel超大内联脚本去优化日志不属于本模块。
- 生产：纯8093守卫部署成功、未回滚，8093 HTTP/API 200，当前5分钟批次 `completed`，8768 PID和监听不变；派生表新增真实批次，人工评分表未写入验收记录。最终备份为 `logs/deploy_backups/diagnosis_ai_analysis_20260805_212403`。

## TEST-8093-DIAGNOSIS-REVIEW-NO-LOGIN-PRODUCTION-20260804

```powershell
python -m pytest tests/test_diagnosis_review_api.py tests/test_diagnosis_review_contract.py -q
python -m py_compile `
  '高炉前端数据\智能助手\backend\diagnosis_review.py' `
  '高炉前端数据\智能助手\backend\ollama_proxy_server.py'
```

- 结果：22项通过；默认仍要求登录，只有显式 `BF_DIAG_REVIEW_REQUIRE_LOGIN=0` 才生成 `onsite_anonymous` 服务端身份；命名密码环境变量、身份模式和前端 `can_submit` 合同均覆盖。
- 远端部署检查：8093 HTTP 200、`enabled/can_submit=true`、`login_required=false`、`identity_mode=onsite_anonymous`、存储可写；历史GET未登录401；无效匿名POST返回400且不写表。
- 数据库：PostgreSQL 16.13 `127.0.0.1:5432/bf_trend`；两张事件表存在，部署验收后行数均为0。
- 隔离：`BFV4PreviewProxy8093`守卫暂停/恢复成功；8768与8094 PID不变；8094页面SHA-256不变。
- 浏览器：真实8093手动评分无需登录，关闭不保存；规定9视口无横向溢出，弹窗可滚动。当前真实诊断正常，自动异常弹窗未以伪造生产数据触发；评分模块日志0，页面既有Babel警告/去优化日志仍存在。Firefox/WebKit/现场Edge待补。
- 完整记录：[8093异常炉况评分免登录部署](8093_异常炉况评分免登录部署_20260804.md)。

## TEST-22012-POSTGRES-ACCOUNT-READONLY-PROBE-20260804

```powershell
$env:PYTHONPATH = (Resolve-Path -LiteralPath '.tmp_pylibs').Path
python .\tools\remote_22012_exec.py --allow-agents-password --no-profile --timeout 30 --script .\tools\remote_probe_22012_pg_accounts.ps1
```

- 预期：返回PostgreSQL 16.13、`127.0.0.1:5432/bf_trend`、运行账号`gl02_sync`；`gl02_reader`为`SELECT=true/INSERT=false`；`postgres`为超级用户。
- 密码验证：只输出三项密码的存在状态、长度和SHA-256，不输出正文；完整值只允许存在于`docs/数据库账号配置说明.md`。
- 边界：全部SQL为`SELECT`，不创建账号、不变更密码、不执行DDL/DML，不修改220.12服务。

## TEST-8093-DIAGNOSIS-REVIEW-LOCAL-PROTOTYPE-20260803

```powershell
python -m pytest tests/test_diagnosis_review_api.py tests/test_diagnosis_review_contract.py -q
python tools/verify_diagnosis_review_local.py --base-url http://127.0.0.1:8096
```

- 模块/契约测试：14项通过。
- 浏览器矩阵：需先启动8096/8769；Chromium覆盖5页面×9视口，Firefox/WebKit各覆盖5页面×4视口。
- 数据库验收：查询 `bf_assistant.diagnosis_review_events`，确认真实/测试来源标记、八类分数和身份完整；220.12只做提交前后只读计数对比，不执行写入。

## TEST-BF3D-8093-BILLBOARD-EMPHASIS-20260802

```powershell
node --check "高炉前端数据/assets/bf3d-tooltip-stable-hover-8093.js"
python -m unittest tests.test_8093_stable_tooltip_hover
```

- 预期：6 项测试通过；运行时包含 `BILLBOARD_SCALE_MULTIPLIER = 1.22`，共享 adapter 不变。
- 页面信号：`.cad-furnace-viewer` 的 `data-status=loaded`、`data-billboard-count=121`、`data-point-policy=measured-121-8093`、`data-billboard-emphasis-scale=1.22`、`data-billboard-emphasis=moderate-8093`。
- 2026-08-02 Chrome 现场页通过上述信号并完成目视检查；独立冷启动专项仍受 8093 静态依赖偶发空响应阻断。

## TEST-BF3D-8093-STABLE-TOOLTIP-HOVER-20260802

```powershell
node --check "高炉前端数据/assets/bf3d-tooltip-stable-hover-8093.js"
python -m py_compile tools/remote_deploy_8093_stable_tooltip_hover.py tests/test_8093_stable_tooltip_hover.py
python -m unittest tests.test_8093_stable_tooltip_hover
python tools/verify_8093_stable_tooltip_hover.py --headed --ready-timeout-ms 120000
```

- 结果：JavaScript/Python 语法通过，6 项 unittest 通过；远端守卫停—改—启、8093/8768 监听、HTTP 200 和资源标记通过。
- 覆盖：单一写入者、视口固定坐标、迟滞参数、无周期位置写入、冷启动安装重试、无 `viewer.THREE` 依赖、页面补丁幂等、8094/共享文件保护。
- 专项输出：`logs/8093_tooltip_hover_acceptance_20260802.json` 与同名 PNG；2026-08-02 最新两次冷启动均因 8093 多个静态依赖出现 `ERR_EMPTY_RESPONSE/ERR_CONNECTION_RESET`，viewer 未初始化，故专项当前是失败诊断证据而非通过证据。Chromium 专项不替代全跨浏览器/视口矩阵。

## TEST-IMES-MCP-FULL-VARIABLE-TEMPLATES-20260727

| 项目 | 内容 |
|---|---|
| 对应需求 | `REQ-IMES-MCP-FULL-VARIABLE-TEMPLATES-20260727` |
| 最终模板 | [IMES_Vastbase_MCP指令模板全集.md](../PT/IMES_Vastbase_MCP指令模板全集.md) |
| 自动生成 | [update_imes_mcp_full_variable_templates.py](../tools/update_imes_mcp_full_variable_templates.py) |
| 机器目录 | [imes_full_variable_catalog.json](../高炉前端数据/智能助手/mcp/imes_full_variable_catalog.json) |
| 覆盖测试 | [test_imes_mcp_full_variable_templates.py](../tests/test_imes_mcp_full_variable_templates.py) |
| MCP检索测试 | [test_imes_relay_mcp_server.py](../tests/test_imes_relay_mcp_server.py) |
| 覆盖证据 | [imes_mcp_full_variable_coverage_20260727.json](../logs/imes_mcp_full_variable_coverage_20260727.json) |

验证命令：

```powershell
python .\tools\update_imes_mcp_full_variable_templates.py --check
python -m py_compile `
  .\tools\update_imes_mcp_full_variable_templates.py `
  .\高炉前端数据\智能助手\mcp\imes_relay_mcp_server.py
python -m unittest `
  tests.test_imes_mcp_full_variable_templates `
  tests.test_imes_relay_mcp_server -v
```

2026-07-27 实测：真实目录包含11个可读对象和315个“对象×字段”，
模板与机器目录均覆盖315/315，无缺失对象、额外对象或未登记字段。
5项模板覆盖测试和19项MCP测试共24项通过。口语检索已验证
“24号料仓投料”→`public.batch_input.value_24`、
“烧结矿QD强度”→`public.v_qpes_sinter_machine_sample_insp_final.qdvalue`、
“炼钢钨”→`public.v_qpes_steel_final.wmdvalue`、
“铁口深度”→`public.t_ipes_cond.depth`。数字边界测试防止24号料仓
串命中4号料仓。

## TEST-IMES-MULTI-ACCOUNT-ANY-READ-MCP-20260727

| 项目 | 内容 |
|---|---|
| 对应需求 | `REQ-IMES-MULTI-ACCOUNT-ANY-READ-MCP-20260727` |
| MCP实现 | [imes_relay_mcp_server.py](../高炉前端数据/智能助手/mcp/imes_relay_mcp_server.py) |
| 单元测试 | [test_imes_relay_mcp_server.py](../tests/test_imes_relay_mcp_server.py) |
| 真实冒烟 | [smoke_test_imes_multi_account_mcp.py](../tools/smoke_test_imes_multi_account_mcp.py) |
| stdio契约冒烟 | [smoke_test_imes_mcp_stdio.py](../tools/smoke_test_imes_mcp_stdio.py) |
| 证据 | `logs/imes_multi_account_mcp_smoke_20260727.json`、`logs/imes_mcp_stdio_schema_smoke_20260727.json` |

验证命令：

```powershell
python -m py_compile .\高炉前端数据\智能助手\mcp\imes_relay_mcp_server.py
python -m unittest tests.test_imes_relay_mcp_server -v
python .\tools\smoke_test_imes_multi_account_mcp.py
python .\tools\smoke_test_imes_mcp_stdio.py
```

2026-07-27 实测：原16项多账号与只读边界测试通过；随后逐变量语义目录
增强新增3项检索测试，当前本文件共19项测试通过。真实Vastbase只读冒烟发现
`operations=6`、`laboratory=5`个可读对象；结构化变量查询分别返回
10和7行；任意参数化只读SQL分别返回5和1行；写SQL被拒绝；所有成功
结果均声明`read_policy=readonly`。stdio实际列出13个工具，新增四个核心工具
及其账号、时间窗、参数和行数Schema完整。MCP账号目录和状态接口不返回密码。

## TEST-HEAT-SI-DISTRIBUTION-20260726

| 项目 | 内容 |
|---|---|
| 对应需求 | `REQ-HEAT-SI-DISTRIBUTION-20260726` |
| 后端统计 | [summarize_hot_metal_si](../db_dashboard/heat_service.py) |
| 页面实现 | [heat.html](../db_dashboard/heat.html) |
| 单元/契约测试 | [test_heat_service.py](../tests/test_heat_service.py)、[test_heat_dashboard_si_distribution.py](../tests/test_heat_dashboard_si_distribution.py) |
| 真实样例 | `2#20260725-329`，Si=`0.21/0.19/0.59` |

验证命令：

```powershell
python -m py_compile db_dashboard\heat_service.py tools\build_heat_centric_docx.py
python -m pytest tests\test_heat_service.py tests\test_heat_dashboard_si_distribution.py -q
Invoke-RestMethod "http://127.0.0.1:8890/api/heat-detail?meltno=2%2320260725-329&window=pre_tap&group=core"
curl.exe -I "http://127.0.0.1:8890/api/heats?limit=24&format=xlsx"
```

2026-07-26 实测：pytest `8 passed`。API 返回 `sample_count=3`、
`valid_count=3`、`median=0.21`、`min=0.19`、`max=0.59`、
`spread≈0.40`；XLSX HTTP 200。页面图表包含 55 个全部 Si 样本点、
24 个中位点和 24 组最小—最大范围。Chromium 九个规定视口、
Firefox/WebKit 各四个代表视口、Edge `1366×768` 均无横向溢出，
正式标题、刷新、导出、详情和四条图表 series 可见，控制台与页面错误为 0。
初始详情未完成时立即点选 `329` 的竞态反例保持标题和选中行均为 `329`。

## TEST-HEAT-CENTRIC-DASHBOARD-20260725

| 项目 | 内容 |
|---|---|
| 对应需求 | `REQ-HEAT-CENTRIC-DASHBOARD-20260725` |
| 聚合服务 | [heat_service.py](../db_dashboard/heat_service.py) |
| 页面与 API | [heat.html](../db_dashboard/heat.html)、[server.py](../db_dashboard/server.py) |
| DOCX 构建器 | [build_heat_centric_docx.py](../tools/build_heat_centric_docx.py) |
| 单元测试 | [test_heat_service.py](../tests/test_heat_service.py) |

验证命令：

```powershell
python -m py_compile `
  db_dashboard\server.py `
  db_dashboard\heat_service.py `
  tools\start_db_dashboard_python.py `
  tools\build_heat_centric_docx.py
python -m pytest tests\test_heat_service.py -q
Invoke-RestMethod "http://127.0.0.1:8890/api/heats?limit=24"
Invoke-RestMethod "http://127.0.0.1:8890/api/heat-detail?meltno=2%2320260725-327&window=pre_tap&group=all"
```

2026-07-25 实测：炉次列表和明细均来自当前只读数据源；样例炉次
`2#20260725-327` 返回铁水 3 条、炉渣 1 条、开口前 12 小时烧结矿 7 条、
全部物理点 133 个。`core/static/body/all` 分组分别为 17/18/80/133 个点。
Chromium 在 9 个规定 CSS 视口无横向溢出，Edge `1366×768` 页面、按钮和
真实明细通过；2026-07-26 的 Si 分布升级已补齐 Firefox/WebKit 代表视口。
DOCX 已验证为可解压的 Office Open XML 包，包含 62 个段落、11 张表格和
1 张真实页面截图；本机 Word COM 类型库异常，未生成分页 PDF 作为视觉审查件。

## TEST-DB-RELAY-DASHBOARD-20260725

| 项目 | 内容 |
|---|---|
| 对应需求 | `OPS-DB-RELAY-DASHBOARD-20260725` |
| 回环转发 | [imes_22012_relay.py](../tools/imes_22012_relay.py) |
| 炉况页启动器 | [start_db_dashboard_python.py](../tools/start_db_dashboard_python.py) |
| 页面与 API | [db_dashboard](../db_dashboard/) |
| 运行手册 | [本机数据库转发与炉况汇总页面](本机数据库转发与炉况汇总页面_20260725.md) |

验证命令：

```powershell
python -m py_compile `
  tools\imes_22012_relay.py `
  tools\start_db_dashboard_python.py `
  db_dashboard\server.py
Invoke-WebRequest http://127.0.0.1:18080/imes.web/
Invoke-RestMethod http://127.0.0.1:8890/api/overview
Invoke-RestMethod "http://127.0.0.1:8890/api/diagnosis?hours=24"
Invoke-RestMethod "http://127.0.0.1:8890/api/summaries?limit=5"
```

2026-07-25 实测：三条 SSH direct-tcpip 目标探测成功；IMES Web HTTP 200；
Vastbase 业务角色登录成功，数据库/schema CREATE 权限均为 false，两个目标
化验视图 SELECT 为 true；pSpace 243 经 18889 的 PythonSDK 认证返回 0。
8890 总览、24 小时诊断和近期总结 API 成功。Chromium `1440×900` 和
`390×844` 无横向溢出。分钟值总行数来自 PostgreSQL 统计估算并以 `≈`
显示，不作为审计精确计数；本轮未完成 Firefox、WebKit 与全部规定视口。

## TEST-HOT-METAL-SI-DATASET-20260719

| 项目 | 内容 |
|---|---|
| 对应需求 | `REQ-HOT-METAL-SI-DATASET-20260719` |
| 构建程序 | [build_hot_metal_si_dataset.py](../tools/build_hot_metal_si_dataset.py) |
| 离线验证 | [validate_hot_metal_si_dataset.py](../tools/validate_hot_metal_si_dataset.py) |
| 单元测试 | [test_build_hot_metal_si_dataset.py](../tests/test_build_hot_metal_si_dataset.py) |
| 数据口径 | [铁水硅炉况传感器数据集](铁水硅炉况传感器数据集.md) |
| 产物目录 | [铁水硅炉况传感器数据集_20260719](../reports/铁水硅炉况传感器数据集_20260719) |

运行命令：

```powershell
python -m py_compile `
  tools\build_hot_metal_si_dataset.py `
  tools\validate_hot_metal_si_dataset.py
python -m pytest tests\test_build_hot_metal_si_dataset.py -q
python tools\validate_hot_metal_si_dataset.py `
  --dataset-dir reports\铁水硅炉况传感器数据集_20260719
```

2026-07-19 结果：单元测试 `3 passed`，离线产物验证 `PASS`。完整集
5,699 行、312 列，严格训练版 4,090 行；主键重复、特征截止越界、
炉况未来匹配、传感器年龄超限、`cold/hot` 展示映射错误均为 0，
manifest 内文件大小和 SHA-256 全部匹配。该测试验证数据对齐和产物完整性，
不批准生产 Si 预测模型；取样/出铁时间仍需现场链路补齐。

## TEST-BF3D-VISUAL-BIBLE-BUNDLE-20260718

| 项目 | 内容 |
|---|---|
| 对应需求 | `REQ-BF3D-VISUAL-BIBLE-001` |
| 规范入口 | [工业级高炉数字孪生视觉规范](../PT/高炉3D模型/工业级高炉数字孪生视觉规范（Visual%20Bible）.md) |
| 验证程序 | [validate_visual_bible_bundle.py](../PT/高炉3D模型/validate_visual_bible_bundle.py) |
| 受控参数 | [lookdev_camera_v1.json](../PT/高炉3D模型/web/presets/lookdev_camera_v1.json) |
| 数据附件 | [GL02数据映射附件.md](../PT/高炉3D模型/docs/GL02数据映射附件.md) |
| 合规证据 | [Visual_Bible当前实现合规矩阵.md](../PT/高炉3D模型/validation/Visual_Bible当前实现合规矩阵.md) |

运行命令：

```powershell
python -m py_compile PT\高炉3D模型\validate_visual_bible_bundle.py
python -B PT\高炉3D模型\validate_visual_bible_bundle.py
python -B PT\高炉3D模型\validate_visual_bible_bundle.py --json
```

验收信号：

- `RESULT: PASS`；
- Visual Bible 为 v1.1，且包含 `REQ-BF3D-VISUAL-BIBLE-001` 和七个受控附件编号；
- 小 FOV=窄视角、大 FOV=广角的语义正确；
- LookDev 与 Golden View JSON 可解析；
- P40 七个固定相机齐全，LookDev 引用文件存在，CC0 HDRI SHA-256 与本地文件一致；
- Golden View 共 16 个唯一 ID，14 张 P40 证据图路径与 SHA-256 一致，且没有误标为已批准 Golden；
- 材质卡恰好 18 张且 ID 唯一；
- 合规机器镜像恰好 45 个唯一 ID，状态计数和批准边界与 Markdown 矩阵一致；
- 数据附件包含 115 点、L7～L16、18 个静压力点、三轴来源/派生/质量和七类时间；
- 合规矩阵保留 P50 pending、P60 preflight only 的批准边界；
- 所有受控 Markdown 相对链接均存在。

2026-07-18 当前结果：22 项检查全部 `PASS`，最终 `RESULT: PASS`。

## TEST-BF3D-PROCESS-DOCX-20260717

| 项目 | 内容 |
|---|---|
| 对应需求 | `REQ-BF3D-PROCESS-DOCX-20260717` |
| 生成器 | [tools/build_bf3d_process_docx.py](../tools/build_bf3d_process_docx.py) |
| 分页验证器 | [tools/verify_bf3d_process_docx_render.py](../tools/verify_bf3d_process_docx_render.py) |
| 隔离预览 | [tools/serve_bf3d_preview.py](../tools/serve_bf3d_preview.py) |
| Word 产物 | [高炉3D模型制作过程与内切面验收记录_20260717.docx](../PT/高炉3D模型/高炉3D模型制作过程与内切面验收记录_20260717.docx) |
| 图像清单 | [高炉3D模型制作过程图片清单_20260717.csv](../PT/高炉3D模型/高炉3D模型制作过程图片清单_20260717.csv) |
| 生成报告 | [高炉3D模型制作过程文档生成报告_20260717.json](../PT/高炉3D模型/高炉3D模型制作过程文档生成报告_20260717.json) |

运行命令：

```powershell
C:\Users\hmw20\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe `
  -m py_compile tools\build_bf3d_process_docx.py tools\serve_bf3d_preview.py
C:\Users\hmw20\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe `
  tools\build_bf3d_process_docx.py
python -m py_compile tools\verify_bf3d_process_docx_render.py
python tools\verify_bf3d_process_docx_render.py
```

验收信号：

- 源图数量固定为 308，PNG=307、GIF=1；
- P35=6、P36=6、P40=106、P50=170、浏览器 QA=20；
- 266 个唯一 SHA-256，42 个迭代副本仍分别编入附录；
- DOCX ZIP `testzip()` 返回空，308 个 `图 A-NNN` 编号全部存在；
- Word 重分页为 70 页；封面、目录、正文、附录中段和末页抽查无裁切、重叠或缺图；
- `webkit_390x844_FAIL.png` 图注明确为历史失败取证，最终 WebKit 390×844 仍以通过截图和 manifest 为准；
- 8094 预览模型路由映射到 P60 隔离候选，正式 GLB 文件和 SHA-256 不变。

## TEST-BF3D-SKILL-PACK-20260716

| 项目 | 内容 |
|---|---|
| 对应需求 | `REQ-BF3D-SKILL-PACK-20260716` |
| 校验程序 | [PT/高炉3D模型/validate_skill_pack.py](../PT/高炉3D模型/validate_skill_pack.py) |
| Skill 清单 | [bundle-manifest.json](../PT/高炉3D模型/skills/bundle-manifest.json) |
| 版本与哈希 | [sources.lock.json](../PT/高炉3D模型/skills/sources.lock.json) |
| 设计与门禁 | [总设计详细规划.md](../PT/高炉3D模型/总设计详细规划.md) |

运行命令：

```powershell
python -m py_compile PT/高炉3D模型/validate_skill_pack.py
python -B PT/高炉3D模型/validate_skill_pack.py
$validator='C:\Users\hmw20\.codex\skills\.system\skill-creator\scripts\quick_validate.py'
Get-ChildItem -LiteralPath 'PT\高炉3D模型\skills' -Directory | Where-Object Name -Like 'bf3d-*' | ForEach-Object { python $validator $_.FullName }
```

可选上游复核：

```powershell
python -B PT/高炉3D模型/validate_skill_pack.py --upstream-repo "cc-blender-skill=C:\path\to\cc-blender-skill"
```

预期结果：七个 Skill 的 frontmatter 仅含 `name/description`，名称与目录一致，`agents/openai.yaml` 的默认提示包含对应 `$skill-name`；锁文件包含六个仓库的 40 位 commit/tree 和选定文件 64 位 SHA-256；本地 PythonCAD、GLB、manifest 哈希无漂移。验证只检查 Skill Pack 和源基线，不代表 Blender 材质或浏览器视觉已经完成。

独立前向测试（2026-07-16）：使用 `$bf3d-orchestrate` 处理“真实哑光风化钢、保留 115 点、导出 Three.js GLB”请求时，正确路由至第一阶段 `$bf3d-geometry-audit`，要求 P00/P10、世界矩阵基线和五视图证据；未跳过 UV/PBR/浏览器门禁，也未修改模型。

## TEST-BF3D-P35-P40-LAYER-CONTRACT-20260717

| 项目 | 内容 |
|---|---|
| 对应需求 | `REQ-BF3D-P35-P40-LAYERS-20260717` |
| P35 检查点 | [P35_DETAIL_GEOMETRY_APPROVED.blend](../PT/高炉3D模型/work/P35_DETAIL_GEOMETRY_20260717_135927/P35_DETAIL_GEOMETRY_APPROVED.blend) |
| P36 检查点 | [P36_LAYER_SEGMENTATION_APPROVED.blend](../PT/高炉3D模型/work/P36_LAYER_SEGMENTATION_20260717_P35_INTEGRATED/P36_LAYER_SEGMENTATION_APPROVED.blend) |
| P40 检查点 | [P40_LOOKDEV_APPROVED.blend](../PT/高炉3D模型/work/P40_FIXED_LOOKDEV_20260717_P36_FINAL/P40_LOOKDEV_APPROVED.blend) |
| 追踪说明 | [十层运行时与 P50 法线修复追踪](../PT/3D模型构建显示.md#116-2026-07-17-十层运行时与-p50-法线修复追踪) |

验收信号：P35、P36、P40 各自具有批准文件及独立视觉复核；P36 包含 L7～L16 共 10 个独立网格和 10 个独立材质，每层关联 A～H 8 个点；模型仍为 115 个传感器和 80 个炉体温度点。该检查不代表 P50、P60 或 P70 已批准。

正式 GLB 防覆盖复核：

```powershell
Get-FileHash -Algorithm SHA256 -LiteralPath '高炉前端数据\models\gl02_blast_furnace.glb'
```

预期 SHA-256：`808960f1b2703e7fb27df35f1b1b1a17063b9b10d2267acba593fc3872b62af6`。

## TEST-BF3D-LAYERED-UI-EDGE-20260717

| 项目 | 内容 |
|---|---|
| 对应需求 | `REQ-BF3D-THREE-RUNTIME-20260717` |
| 页面实现 | [frontend_dashboard_v3.server.html](../高炉前端数据/frontend_dashboard_v3.server.html) |
| 专项脚本 | [verify_gl02_layered_model_ui.py](../tools/verify_gl02_layered_model_ui.py) |
| 已测浏览器/视口 | 本机 Edge，`1366×768` |
| 数据边界 | 静态数据源；使用 `--allow-offline-data-source` |

运行命令：

```powershell
python -m py_compile tools/verify_gl02_layered_model_ui.py
python tools/verify_gl02_layered_model_ui.py `
  --base-url http://127.0.0.1:18092 `
  --page-path /frontend_dashboard_v3.server.html `
  --ws-port 8767 `
  --allow-offline-data-source
```

断言范围：L7～L16 每层只显示对应 A～H 8 点；高亮进入、回弹、呼吸、切层和清除状态正确；正常/关注/严重/无数据状态色正确；哑光材质参数与纹理存在；同层重复选择不重启动画；连续切层 100 次后对象和 GPU 资源不持续增长；页面错误和非预期控制台错误为 0。

边界：该结果只证明静态页面、模型、动画与资源合同。未连接 8767 实时流和生产数据库，因此不覆盖生产实时值、实时状态色或完整数据链路；生产验收时不得使用 `--allow-offline-data-source`。

## TEST-BF3D-LAYER-MATRIX-20260717

| 项目 | 内容 |
|---|---|
| 对应需求 | `REQ-BF3D-THREE-RUNTIME-20260717` |
| Chromium 报告 | [manifest.json](../logs/bf3d_layer_matrix_20260717/manifest.json) |
| Firefox/WebKit 报告 | [manifest.json](../logs/bf3d_layer_cross_engine_20260717/manifest.json) |
| Edge 专项 | [verify_gl02_layered_model_ui.py](../tools/verify_gl02_layered_model_ui.py) |
| 数据边界 | 三组均为静态数据源 |

结果：Chromium 九个规定视口为 9/9；Firefox 四个代表视口和 WebKit 四个代表视口合计 8/8；Edge `1366×768` 专项通过。各视口均验证十层按钮、L7/L10/L13/L16 单层八点、115 点模型合同、无横向溢出、控制栏不被底栏遮挡，以及除已声明离线项外无页面、控制台和资源错误。

边界：manifest 只允许把 `127.0.0.1:8767` WebSocket 和静态服务器 `/api/*` 失败记录为 expected offline。8767 实时流、生产数据库、实时值与实时状态色均未验证；该矩阵不是 P70 或生产实时链路批准。

## TEST-BF3D-P50-NORMAL-FIX-SMOKE-20260717

| 项目 | 内容 |
|---|---|
| 对应问题 | `BUG-BF3D-P50-FLAT-NORMAL-20260717` |
| 烘焙程序 | [p50_full_furnace_bake_candidate.py](../PT/高炉3D模型/skills/bf3d-uv-bake/scripts/p50_full_furnace_bake_candidate.py) |
| 旧 1K 复核 | [p50_1k_visual_review.json](../PT/高炉3D模型/work/P50_FULL_FURNACE_BAKE_1024_20260717_153648_R2/p50_1k_visual_review.json) |
| 256px 修复报告 | [p50_full_furnace_bake_candidate.json](../PT/高炉3D模型/work/P50_FULL_FURNACE_BAKE_20260717_NORMAL_FIX_SMOKE256_R2/p50_full_furnace_bake_candidate.json) |
| 256px 独立复核 | [p50_normal_fix_smoke_review.json](../PT/高炉3D模型/work/P50_FULL_FURNACE_BAKE_20260717_NORMAL_FIX_SMOKE256_R2/p50_normal_fix_smoke_review.json) |

旧 1K 候选的独立结论为 `ITERATE`：NormalGL 有效像素为恒定 `(0.5019608, 0.5019608, 1.0)`，图集有效占比 `21.743%`，并缺少背部接缝和分区边界视觉证据。它不是 P50 批准文件。

修复后的 256px R2 采用 `4×` 法线编码放大和 `0.25` 运行时法线强度，新增 `normal_contains_quantization_safe_microdetail` 门禁；结果为 `26/26`、重复纹理哈希一致，115 点、80 个炉体温度点和 L7～L16 十层保持不变。

复现命令：

```powershell
python PT/高炉3D模型/run_p50_full_furnace_bake_candidate.py `
  --output-dir PT/高炉3D模型/work/P50_NORMAL_FIX_SMOKE256_REPRO `
  --texture-size 256 `
  --margin 4 `
  --samples 8 `
  --skip-render
```

预期信号：报告新增且通过 `normal_contains_quantization_safe_microdetail`，总断言为 `26/26`，`normal_policy.encoding_amplification=4.0`，运行时强度为 `0.25`。该测试只批准法线修复 smoke；后续三列 1K 已补做高分辨率、图集占比与背缝/边界证据，但局部接触 AO、旋转 shimmer 和 P60/P70 仍未批准。

## TEST-BF3D-P50-3COL-1K-SMOKE-20260717

| 项目 | 内容 |
|---|---|
| 对应问题 | `BUG-BF3D-P50-FLAT-NORMAL-20260717` |
| 1K 机器报告 | [p50_full_furnace_bake_candidate.json](../PT/高炉3D模型/work/P50_FULL_FURNACE_BAKE_1024_3COL_20260717_R1/p50_full_furnace_bake_candidate.json) |
| 独立复核 | [p50_3col_visual_review.json](../PT/高炉3D模型/work/P50_FULL_FURNACE_BAKE_1024_3COL_20260717_R1/p50_3col_visual_review.json) |
| 八机位生成脚本 | [render_p50_multiview_review.py](../PT/高炉3D模型/work/P50_FULL_FURNACE_BAKE_1024_3COL_20260717_R1/review/render_p50_multiview_review.py) |
| P50 运行入口 | [run_p50_full_furnace_bake_candidate.py](../PT/高炉3D模型/run_p50_full_furnace_bake_candidate.py) |

实测信号：机器断言 32/32；三列图集有效像素占比 `57.297%`；有效纹素密度 `25.580 texel/m`；NormalGL 通过非平坦与 8 位量化安全微细节门禁；115 个传感器、80 个炉体温度点、L7～L16 十层及每层 A～H 八点保持不变。

独立结论仅为 `APPROVE_SMOKE`，且 `p50_stage_approval=false`。这证明三列布局和非平坦 Normal 可继续迭代，不表示 P50 已批准。

复现机器候选：

```powershell
python PT/高炉3D模型/run_p50_full_furnace_bake_candidate.py `
  --output-dir PT/高炉3D模型/work/P50_3COL_1K_REPRO `
  --texture-size 1024 `
  --margin 4 `
  --samples 16 `
  --skip-render
```

## TEST-BF3D-P50-METALLIC-R2-20260717

| 项目 | 内容 |
|---|---|
| 对应问题 | `BUG-BF3D-P50-METALLIC-SHIMMER-20260717` |
| R2 机器报告 | [p50_full_furnace_bake_candidate.json](../PT/高炉3D模型/work/P50_FULL_FURNACE_BAKE_1024_METALLIC_FIX_20260717_R2/p50_full_furnace_bake_candidate.json) |
| 八机位证据 | [p50_multiview_review_evidence.json](../PT/高炉3D模型/work/P50_FULL_FURNACE_BAKE_1024_METALLIC_FIX_20260717_R2/review/p50_multiview_review_evidence.json) |
| R1/R2 量化 | [p50_r1_r2_boundary_metrics.json](../PT/高炉3D模型/work/P50_FULL_FURNACE_BAKE_1024_METALLIC_FIX_20260717_R2/review/p50_r1_r2_boundary_metrics.json) |
| 比较脚本 | [compare_r1_r2_boundary.py](../PT/高炉3D模型/work/P50_FULL_FURNACE_BAKE_1024_METALLIC_FIX_20260717_R2/review/compare_r1_r2_boundary.py) |

实测信号：R2 机器断言 35/35；按同一阈值统计，Metallic 近二值比例从 R1 的 `79.87%` 降到 `0.043%`；R2 相邻像素差 P95 为 `0.0667`，大跳变比例为 `0`，局部脉冲比例为 `0`。八机位覆盖前、后、左、右、背缝、工艺段边界、近距离 mip 和远距离 mip。

当前结论是 `approval=not_granted_comparison_only`：静态机位已经证明盐粒与局部突刺改善，但尚未完成 Three.js 旋转 shimmer 验证。

## TEST-BF3D-BOSH-BELLY-KNUCKLE-20260717

| 项目 | 内容 |
|---|---|
| 对应追踪 | `Q-BF3D-BOSH-BELLY-KNUCKLE-20260717` |
| 诊断结论 | [p50_boundary_diagnosis_conclusion.json](../PT/高炉3D模型/work/P50_FULL_FURNACE_BAKE_1024_3COL_20260717_R1/review/diagnosis/p50_boundary_diagnosis_conclusion.json) |
| 像素与通道报告 | [p50_boundary_diagnosis.json](../PT/高炉3D模型/work/P50_FULL_FURNACE_BAKE_1024_3COL_20260717_R1/review/diagnosis/p50_boundary_diagnosis.json) |
| 复跑脚本 | [p50_boundary_diagnosis.py](../PT/高炉3D模型/work/P50_FULL_FURNACE_BAKE_1024_3COL_20260717_R1/review/diagnosis/p50_boundary_diagnosis.py) |

预期信号：炉腹—炉腰 `z=-1.4` 的平均几何法线夹角保持 `7.5°～7.9°`，实测 `7.67°`；炉腰—炉身对照不高于 `0.1°`，实测 `0.004°`。BaseColor、NormalGL、Metallic、几何法线及无 Normal 统一材质分通道证据共同支持“合法炉型折角，非贴图断裂”。不得为消除该高光而改动批准顶点。

以上三个测试是 P50 的历史中间证据，本身都不批准 P50、P60 或 P70。后续局部接触 AO 人工观察、4K 母版、24 帧旋转审查和 P60 内部预检已经完成，见下文对应测试；Khronos Validator 与 P50/P60/P70 阶段批准仍未完成。正式 GLB SHA-256 继续为 `808960f1b2703e7fb27df35f1b1b1a17063b9b10d2267acba593fc3872b62af6`，115 点、80 个炉体温度点和 L7～L16 十层合同不变。

## TEST-BF3D-P50-LOCAL-AO-R3-20260717

| 项目 | 内容 |
|---|---|
| 对应追踪 | `TEST-BF3D-P50-LOCAL-AO-R3-20260717` |
| 候选报告 | [p50_full_furnace_bake_candidate.json](../PT/高炉3D模型/work/P50_LOCAL_CONTACT_AO_1K_20260717_1702_R3/p50_full_furnace_bake_candidate.json) |
| 八视角证据 | [p50_multiview_review_evidence.json](../PT/高炉3D模型/work/P50_LOCAL_CONTACT_AO_1K_20260717_1702_R3/review/p50_multiview_review_evidence.json) |
| 人工观察 | [p50_multiview_manual_observations.json](../PT/高炉3D模型/work/P50_LOCAL_CONTACT_AO_1K_20260717_1702_R3/review/p50_multiview_manual_observations.json) |
| R2/R3 比较脚本 | [compare_r2_r3_ao.py](../PT/高炉3D模型/work/P50_LOCAL_CONTACT_AO_1K_20260717_1702_R3/review/compare_r2_r3_ao.py) |
| P50 运行入口 | [run_p50_full_furnace_bake_candidate.py](../PT/高炉3D模型/run_p50_full_furnace_bake_candidate.py) |

白名单合同：`local_contact_whitelist_v1` 仅允许炉壳焊缝、加强圈、风口法兰本体和风口螺栓参与局部接触 AO；平台、结构塔架、内部构件、`SENSOR_` 节点及 L7～L16 诊断覆盖层必须排除，且烘焙结束后对象隐藏/渲染状态必须完全恢复。

参数与机器信号：

- `distance=0.12m`、`strength=0.28`、`floor=0.78`、`samples=32`；
- 41/41 断言通过；
- AO min `0.780392`、mean `0.996459`、std `0.022720`；
- 非纯白占比 `5.197%`、`<0.98` 占比 `2.852%`、`<0.82` 占比 `0.723%`；
- 五段炉壳几何、对象矩阵、隐藏态、115 个传感器、80 个炉体温度点和 L7～L16 十层均不变。

固定哈希：

| 产物 | SHA-256 |
|---|---|
| 候选 `.blend` | `1b6e9e5ec2257787c5859615c10e9d5c06244654f36fdc641b45e656d2b89977` |
| AO 1K | `a2686f4355e430dd06288178ed4d8356dcfb37a83dd3fc19f0f85412dd8ac358` |
| NormalGL 1K | `15b1dea80a2ab1edb5f1e62f5c1b2df1d6c1a21cebf827fef8dc4647ce33583b` |
| 候选报告 | `5744b6585d036852c3c0756f9d14d46d7b361ea1659404e19db4d73b1892c179` |

复现机器候选：

```powershell
python PT/高炉3D模型/run_p50_full_furnace_bake_candidate.py `
  --output-dir PT/高炉3D模型/work/P50_LOCAL_CONTACT_AO_1K_REPRO `
  --texture-size 1024 `
  --margin 4 `
  --samples 32 `
  --skip-render
```

人工观察已完成，结论为 `AO_MAP_LOCALIZED_VISUAL_CONSUMPTION_PENDING_P60`、`approval=not_granted`：八机位未出现平台黑带或整体压暗，但 Blender EEVEE 当时没有消费 ORM R 通道，所以该报告只证明 AO 数据范围受控，不能单独证明浏览器最终 AO 强度。后续 4K 母版、24 帧旋转审查和 P60 内部预检已经完成，见以下测试；P50/P60 仍未批准，正式 GLB 未覆盖。

## TEST-BF3D-P50-4K-ROTATION-20260717

| 项目 | 内容 |
|---|---|
| 对应追踪 | `TEST-BF3D-P50-4K-ROTATION-20260717` |
| 4K 机器报告 | [p50_full_furnace_bake_candidate.json](../PT/高炉3D模型/work/P50_MASTER_4K_20260717_R1/p50_full_furnace_bake_candidate.json) |
| 贴图清单 | [p50_texture_manifest.json](../PT/高炉3D模型/work/P50_MASTER_4K_20260717_R1/p50_texture_manifest.json) |
| 24 帧联系表 | [P50_ROTATION_CONTACT_SHEET_24.png](../PT/高炉3D模型/work/P50_MASTER_4K_20260717_R1/review/P50_ROTATION_CONTACT_SHEET_24.png) |
| 旋转指标 | [p50_rotation_contact_sheet_metrics.json](../PT/高炉3D模型/work/P50_MASTER_4K_20260717_R1/review/p50_rotation_contact_sheet_metrics.json) |
| 人工观察 | [p50_master_4k_manual_observations.json](../PT/高炉3D模型/work/P50_MASTER_4K_20260717_R1/review/p50_master_4k_manual_observations.json) |

实测信号：4K 母版机器断言 41/41；BaseColor、Roughness、Metallic、NormalGL、AO 与 ORM 全部存在；115 个传感器、80 个炉体温度点和 L7～L16 十层合同保持不变。24 帧整圈旋转审查未发现明显背缝、盐粒噪点、UV 方向翻转或静态摩尔纹。

停止线：人工观察的决定为 `KEEP_P50_PENDING_NOT_APPROVED`，`approval=not_granted`。41/41 与 24 帧审查是候选证据，不得命名为 `P50_BAKE_APPROVED`。

## TEST-BF3D-P60-PREFLIGHT-20260717

| 项目 | 内容 |
|---|---|
| 对应追踪 | `TEST-BF3D-P60-PREFLIGHT-20260717` |
| 隔离 GLB | [P60_PREFLIGHT_4K_UNCOMPRESSED.glb](../PT/高炉3D模型/work/P60_PREFLIGHT_4K_20260717_R1/P60_PREFLIGHT_4K_UNCOMPRESSED.glb) |
| 预检报告 | [p60_preflight_report.json](../PT/高炉3D模型/work/P60_PREFLIGHT_4K_20260717_R1/p60_preflight_report.json) |
| manifest | [p60_preflight_manifest.json](../PT/高炉3D模型/work/P60_PREFLIGHT_4K_20260717_R1/p60_preflight_manifest.json) |
| 文件哈希 | [p60_preflight_sha256.json](../PT/高炉3D模型/work/P60_PREFLIGHT_4K_20260717_R1/p60_preflight_sha256.json) |
| Validator 状态 | [gltf_validator_status.json](../PT/高炉3D模型/work/P60_PREFLIGHT_4K_20260717_R1/gltf_validator_status.json) |

实测信号：20/20 内部检查及 Blender 回读通过；炉壳为 `OPAQUE`、BaseColor alpha 为 `1`；BaseColor、Normal 和 ORM 全部嵌入，ORM 同时供 Metallic-Roughness 与 Occlusion 使用；无外部 URI、无 Draco/Meshopt 依赖；115 个传感器、80 个炉体温度点、L7～L16 十层和 45 个内部工艺示意对象保持不变。

停止线：本机 Khronos glTF Validator 不可用，因此状态是 `internal_preflight_passed`、`approval=not_granted_preflight_only`。该 GLB 只用于隔离预览和浏览器预检，不得替换正式生产 GLB。

## TEST-BF3D-CUTAWAY-RUNTIME-20260717

| 项目 | 内容 |
|---|---|
| 对应需求 | `REQ-BF3D-CUTAWAY-20260717` |
| 页面实现 | [frontend_dashboard_v3.server.html](../高炉前端数据/frontend_dashboard_v3.server.html) |
| 专项脚本 | [verify_gl02_cutaway_runtime.cjs](../tools/verify_gl02_cutaway_runtime.cjs) |
| 正式模型边界 | 默认正式 GLB 只读；可用 `--model` 指向 P60 隔离候选 |

运行命令：

```powershell
node --check tools\verify_gl02_cutaway_runtime.cjs
node tools\verify_gl02_cutaway_runtime.cjs
node tools\verify_gl02_cutaway_runtime.cjs `
  --model="PT\高炉3D模型\work\P60_PREFLIGHT_4K_20260717_R1\P60_PREFLIGHT_4K_UNCOMPRESSED.glb"
```

断言合同：

- 默认“外观”模式精确识别 45 个内部对象且可见数为 0；
- “内切面”启用局部裁剪平面，按料柱、软熔带和气流/炉缸流体分阶段显现；
- 内切面临时隐藏 5 组外部遮挡附件，开启两盏炉内补光和两条炉型剖切边缘；复位后全部恢复/关闭；
- 状态文字包含“工艺示意，非实时断面测量”；
- L7～L16 每层仍只显示 A～H 八点；
- 炉壳外观保持 `transparent=false`、`opacity=1`、`depthWrite=true`，并保留已有 BaseColor、Roughness、Metallic、Normal 和 AO 通道；
- 连续切换模式后对象、材质和几何资源数量不增长，复位恢复 OrbitControls 位置/目标并隐藏内部对象；
- “总览→炉况诊断→总览”后新查看器重新挂载完整 API/状态，旧 RAF 停止且资源释放。

运行接口为 `setCutawayMode()`、`playCutaway()`、`pauseCutaway()`、`resetCutaway()` 和 `getCutawayState()`；DOM 状态为 `data-cutaway-mode`、`data-cutaway-phase`、`data-internal-count` 和 `data-internal-visible-count`。

实测：正式 GLB 与 P60 4K 隔离候选两轮运行均 `ok=true`，意外页面、控制台和 HTTP 错误均为 0；Chromium 九个规定视口已复跑为 9/9；[Firefox/WebKit 专项报告](../logs/bf3d_cutaway_cross_engine_20260717/report.md)为 8/8。边界：这仍不提前声明 P70，现场 Edge、性能、8767 和数据库实时链路按正式交付门禁继续补齐。

## TEST-IMES-GRANTED-VIEWS-AUDIT-20260716

| 项目 | 内容 |
|---|---|
| 对应运维项 | `OPS-IMES-GRANTED-VIEWS-20260716` |
| 审计程序 | [tools/audit_imes_granted_views.py](../tools/audit_imes_granted_views.py) |
| 单元测试 | [tests/test_audit_imes_granted_views.py](../tests/test_audit_imes_granted_views.py) |
| 真实报告 | [logs/imes_granted_views_audit_20260716.json](../logs/imes_granted_views_audit_20260716.json) |

运行命令：

```powershell
python -m py_compile .\tools\audit_imes_granted_views.py .\tests\test_audit_imes_granted_views.py
python -m unittest .\tests\test_audit_imes_granted_views.py -v
. .\PT\load_imes_vastbase_local.ps1
python .\tools\audit_imes_granted_views.py --sample-limit 50 --statement-timeout-ms 60000
```

预期信号：单元测试通过；真实会话显示 `current_user=lg_fq`、`read_only=on`、`Found views: 5; missing: 0`，五个视图均为 `select=True`。报告不得包含 `IMES_DB_PASSWORD` 的值。

## TEST-8093-OVERVIEW-ADAPTIVE-20260716

| 项目 | 内容 |
|---|---|
| 对应问题 | `BUG-8093-OVERVIEW-ADAPTIVE-CLIP-20260716` |
| 测试文件 | [tools/verify_overview_adaptive_layout.py](../tools/verify_overview_adaptive_layout.py) |
| 页面实现 | [最终响应式覆盖](../高炉前端数据/frontend_dashboard_v3.server.html#L10656) |
| Chromium 报告 | [45/45 manifest](../logs/overview_adaptive_qa_20260716/manifest.json) |
| 跨引擎报告 | [45/45 manifest](../logs/overview_adaptive_qa_20260716_cross_engine/manifest.json) |

运行命令：

```powershell
python -m py_compile .\tools\verify_overview_adaptive_layout.py
python .\tools\verify_overview_adaptive_layout.py --static-only --url "http://127.0.0.1:18093/frontend_dashboard_v3.server.html?ws_port=8767#overview"
python .\tools\verify_overview_adaptive_layout.py --url "http://127.0.0.1:18093/frontend_dashboard_v3.server.html?ws_port=8767#overview" --engines chromium --out-dir .\logs\overview_adaptive_qa_20260716
python .\tools\verify_overview_adaptive_layout.py --url "http://127.0.0.1:18093/frontend_dashboard_v3.server.html?ws_port=8767#overview" --engines firefox,webkit,msedge --out-dir .\logs\overview_adaptive_qa_20260716_cross_engine
```

断言范围：正式头部和底部导航位于视口内；5 个核心路由可渲染；页面及主内容区横向溢出为 0；总览核心变量两页各 14 行名称、数值、页签和趋势入口不裁切；变量详情弹层可打开和关闭；桌面保持三栏，平板/手机按核心变量、炉体、右栏顺序纵向可达。静态服务器未启动 8767 与后端 API，因此脚本只忽略明确的连接拒绝/404，其他页面与控制台错误仍判失败。

## TEST-IMES-WEB-READONLY-20260715

| 项目 | 内容 |
|---|---|
| 对应需求 | `REQ-IMES-UNIFIED-TIME-QUERY-20260715`、`OPS-IMES-VASTBASE-20260715` |
| 测试文件 | [tests/test_export_imes_web_readonly.py:L42-L163](../tests/test_export_imes_web_readonly.py#L42-L163) |
| 被测白名单 | [DATASETS:L41-L137](../tools/export_imes_web_readonly.py#L41-L137) |
| 被测时间窗口 | [build_query_windows:L200-L211](../tools/export_imes_web_readonly.py#L200-L211) |
| 被测统一接口 | [query_dataset:L244-L269](../tools/export_imes_web_readonly.py#L244-L269) |

运行命令：

```powershell
python -m py_compile .\tools\export_imes_web_readonly.py .\tests\test_export_imes_web_readonly.py
python .\tools\export_imes_web_readonly.py --help
python .\tools\export_imes_web_readonly.py --list-datasets
python -m unittest .\tests\test_export_imes_web_readonly.py -v
```

预期结果：9 个单元测试全部通过；帮助文本包含 `--dataset`、`--all-datasets`、`--start-date`、`--end-date`、`--workdate`。

真实只读冒烟：`batch_mining` 在 `2026-07-13~2026-07-14` 生成 2 个查询窗口，返回 334 行，其中 7月13日 165 行、7月14日 169 行。测试数据仅写系统临时目录并在核对后删除。

失败排查：

- 登录失败：检查 `IMES_WEB_USER/IMES_WEB_PASSWORD/IMES_WEB_CAPTCHA`，不得打印变量值。

## TEST-IMES-VASTBASE-DISCOVERY-20260716

| 项目 | 内容 |
|---|---|
| 对应需求 | `REQ-IMES-VASTBASE-DISCOVERY-20260716` |
| 测试文件 | [tests/test_export_vastbase_local.py](../tests/test_export_vastbase_local.py) |
| 被测程序 | [tools/export_vastbase_local.py](../tools/export_vastbase_local.py) |
| 网络诊断 | [tools/diagnose_imes_network.ps1](../tools/diagnose_imes_network.ps1) |

```powershell
python -m py_compile .\tools\export_vastbase_local.py .\tests\test_export_vastbase_local.py
python .\tools\export_vastbase_local.py --help
python -m unittest .\tests\test_export_vastbase_local.py -v
python .\tools\export_vastbase_local.py --tcp-check --connect-timeout 3
.\tools\diagnose_imes_network.ps1 -OutFile .\logs\imes_network_diagnosis_20260716.json
```

预期：7 个离线单元测试通过；无 VPN 路由时 TCP 检查以退出码2返回结构化超时，不泄露账号密码；网络诊断 JSON 应包含目标路由、端口、系统代理绕过、VPN 网卡和诊断摘要。

## TEST-IMES-22012-RELAY-MCP-20260716

| 项目 | 内容 |
| --- | --- |
| 对应需求 | `REQ-IMES-22012-RELAY-MCP-20260716` |
| 转发器 | [tools/imes_22012_relay.py](../tools/imes_22012_relay.py) |
| Vastbase 本机一键入口 | [tools/start_imes_vastbase_relay_local.cmd](../tools/start_imes_vastbase_relay_local.cmd) |
| MCP 服务 | [imes_relay_mcp_server.py](../高炉前端数据/智能助手/mcp/imes_relay_mcp_server.py) |
| 完整性审计 | [audit_imes_vastbase_completeness.py](../tools/audit_imes_vastbase_completeness.py) |
| 单元测试 | [tests/test_imes_22012_relay.py](../tests/test_imes_22012_relay.py)、[tests/test_imes_relay_mcp_server.py](../tests/test_imes_relay_mcp_server.py) |
| 审计测试 | [tests/test_audit_imes_vastbase_completeness.py](../tests/test_audit_imes_vastbase_completeness.py) |

```powershell
python -m py_compile .\tools\imes_22012_relay.py .\高炉前端数据\智能助手\mcp\imes_relay_mcp_server.py
python -m unittest .\tests\test_imes_22012_relay.py .\tests\test_imes_relay_mcp_server.py -v
python .\tools\imes_22012_relay.py --allow-agents-password --check
.\tools\start_imes_vastbase_relay_local.cmd
python -m unittest .\tests\test_audit_imes_vastbase_completeness.py -v
```

实际验收：2026-07-16 三条 SSH direct-tcpip 通道均成功；本机 `http://127.0.0.1:18080/imes.web/` 返回 HTTP 200；Vastbase目录发现为260可见对象、9个可读、6个MES对象；MCP `query_hot_metal_silicon` 返回真实炉次 `2#20260508-120` 与 `Si=0.27`。2026-07-19 新增的 Vastbase 一键入口固定只启动 `127.0.0.1:15433 -> 10.30.220.12 -> 10.10.181.195:5432`，未保存密码；窗口关闭或按 `Ctrl+C` 即停止。同轮离线转发测试 4/4 通过，自定义映射解析通过，真实 `--check` 返回 `all_ok=true`、目标连通耗时 79ms。完整性审计在 2026-05-01 至 2026-07-16 成功聚合 6 个业务对象并生成逐日计数；审计单元测试 3/3 通过。详情见 [跳板转发与MCP](22012_IMES跳板转发与MCP.md)。

远端验收：同日已同步到 220.12 `F:\高炉炼铁项目-real-sensor-v2_V4_8093_PREVIEW`；按用户授权扩展后的 `direct_22012` 冒烟返回 `status_ok=true`、`catalog_objects=9`，从 `public.t_ipes_out_put` 返回 3 行，并用 `query_imes_readonly_sql` 成功执行只读总行数聚合。语义增强后，“查一下2号炉昨天每炉出了多少铁”实际解析为 `public.t_ipes_out_put.ironquan`；MCP 单元测试 10/10。冒烟入口为 [tools/smoke_22012_imes_mcp.py](../tools/smoke_22012_imes_mcp.py)。
- HTTP 超时：先检查 `10.10.181.209:8080` 连通性，再缩小日期范围。
- 超过最大页数：缩小日期范围或明确提高 `--max-pages`。
- 字段变化：对照 [MES 数据集说明](mes数据集.md) 与实际 `manifest.json.fields`，更新白名单、测试和文档。

## TEST-8093-MCP-GENERIC-SENSOR-005 通用传感器查询与绘图

| 项目 | 内容 |
|---|---|
| 对应需求 | `REQ-8093-MCP-GENERIC-SENSOR-005` |
| MCP 测试 | `test_batch_sensor_tool_supports_multiple_history_series`、`test_batch_sensor_tool_keeps_partial_latest_failures` |
| 路由测试 | `test_layer_body_temperature_colloquialism_expands_to_a_through_h`、`test_arbitrary_catalog_sensor_description_and_id_are_resolved` |
| 绘图测试 | `test_layer_body_temperature_chart_routes_all_eight_sensors`、`test_auto_trend_uses_small_multiples_for_large_scale_gap_even_without_units` |

运行命令：

```powershell
python -X utf8 -m unittest "高炉前端数据.智能助手.tests.test_mcp_chart_expansion" "高炉前端数据.智能助手.tests.test_qa_latency_optimizations"
python -X utf8 tools\test_8093_colloquial_prompts.py --url "http://10.30.220.12:8093/api/qa/chat" --case mcp_body_temperature_layer7_all --case mcp_generic_multi_sensor_latest --case mcp_generic_multi_sensor_chart
```

预期结果：本地 38 项全部通过；现网三条均 `auto_pass=true`，整层预取八个 `T_body_L7_A-H`，绘图工具为 `plot_gl02_trends` 且最终 `image_url` 返回 `200 image/png`。

## TEST-BF3D-INTERNAL-RUNTIME-6X-20260719

| 项目 | 内容 |
|---|---|
| 对应需求 | `REQ-BF3D-INTERNAL-RUNTIME-6X-20260719` |
| 运行时 | [bf3d-internal-simulation.js](../高炉前端数据/assets/bf3d-internal-simulation.js) |
| 配置 | [bf3d_internal_simulation.v1.json](../高炉前端数据/config/bf3d_internal_simulation.v1.json) |
| 旧内切面回归 | [verify_gl02_cutaway_runtime.cjs](../tools/verify_gl02_cutaway_runtime.cjs) |
| 专项合同 | [verify_bf3d_internal_simulation.cjs](../tools/verify_bf3d_internal_simulation.cjs) |
| 浏览器矩阵 | [verify_bf3d_internal_simulation_matrix.cjs](../tools/verify_bf3d_internal_simulation_matrix.cjs) |
| 完整说明 | [WEB-60 炉内仿真运行时说明](../PT/高炉3D模型/docs/WEB-60_炉内仿真运行时说明.md) |

```powershell
node --check .\tools\verify_bf3d_internal_simulation.cjs
node --check .\tools\verify_bf3d_internal_simulation_matrix.cjs
node .\tools\verify_gl02_cutaway_runtime.cjs
node .\tools\verify_bf3d_internal_simulation.cjs
node .\tools\verify_bf3d_internal_simulation_matrix.cjs
```

断言范围：

- 正式 GLB 115 点、L7～L16 每层八点、旧内切面相机/裁剪/资源生命周期不回归；
- 数据态在门禁和输入不足时隐藏料面形变、软熔带、18 点、滴落和炉缸液面；
- 教学态固定种子、明确 `illustrative`，软熔带为闭合参数化壳并带估计置信区间；
- 26 风口统一强度，不从总量随机制造圆周差异；喷煤使用 `Points`；
- 18 点、三条插值带和 `−12～+12kPa` 固定色标；压力箭头不命名为真实流线；
- 上料事件必须 `mass_balance_valid=true`，铁口事件只开/关等宽流束；
- 50 次模式切换后场景根、层池、实例、Points 容量、面板和控制器不增长；
- Chromium 九视口、Firefox/WebKit 各四代表视口，每个走五个核心页面，共 85 个页面组合，无横向溢出、核心路由不可达或意外错误。

结果：

- [专项合同报告](../logs/bf3d_internal_simulation_20260719/runtime_contract_report.json)：`ok=true`；
- [跨引擎矩阵](../logs/bf3d_internal_simulation_20260719/matrix/cross_engine_viewport_report.json)：17 个视口运行、85 个页面组合；
- 静态验收只忽略明确的 8767 连接拒绝和后端 API 404，不能替代现场 Edge、生产数据库和实时快照链路验收。

## TEST-BF3D-STRUCTURAL-REVIEW-20260719

| 项目 | 内容 |
|---|---|
| 对应需求 | `REQ-BF3D-STRUCTURAL-REVIEW-20260719` |
| GLB 构建 | [export_bf3d_structural_review_glb.py](../tools/export_bf3d_structural_review_glb.py) |
| 资产清单 | [gl02_blast_furnace_structural_review.v1.manifest.json](../高炉前端数据/models/gl02_blast_furnace_structural_review.v1.manifest.json) |
| 模式专项 | [verify_bf3d_structural_review.cjs](../tools/verify_bf3d_structural_review.cjs) |
| 旧内切面回归 | [verify_gl02_cutaway_runtime.cjs](../tools/verify_gl02_cutaway_runtime.cjs) |
| 五页跨引擎回归 | [verify_bf3d_internal_simulation_matrix.cjs](../tools/verify_bf3d_internal_simulation_matrix.cjs) |

```powershell
& 'D:\Program Files\Blender Foundation\Blender 5.2\blender.exe' --background --python-exit-code 1 --python '.\tools\export_bf3d_structural_review_glb.py'
node --check .\高炉前端数据\assets\bf3d-structural-review.js
node .\tools\verify_bf3d_structural_review.cjs
node .\tools\verify_bf3d_structural_review.cjs --matrix
node .\tools\verify_gl02_cutaway_runtime.cjs
node .\tools\verify_bf3d_internal_simulation_matrix.cjs
```

关键断言：

- 受控 GLB SHA 为 `859819f415feee0533018daf3290c65c69b607352d8e8e34735e952d8f3772fd`，正式回滚 GLB SHA 不变；
- 五个 R5 外壳、五个 R2J 实体、R2K 背衬/铜与铸铁冷却壁/热面/残余耐火层齐全，结瘤层按 missing 隐藏；
- 纯材质审查只剩五个可见炉壳，传感器、拾取体、引线、黄色剖面和工艺运行时全部隐藏；
- 结构剖面显示 10 个有效逻辑结构对象、25 个多材质渲染 primitive，并显示 E/illustrative 图例；
- 30 次模式往返后逻辑对象数、材质克隆数和传感器数不增长，返回运行视图后 115 点恢复；
- Chromium 九视口、Firefox/WebKit 各四代表视口共 17/17；五业务页回归 85/85，无横向溢出、核心按钮遮挡或意外页面/控制台错误。

证据：[专项报告](../logs/bf3d_structural_review_20260719/report.json)、[模式矩阵](../logs/bf3d_structural_review_20260719/matrix_report.json)、[材质审查截图](../logs/bf3d_structural_review_20260719/material_review_1440x900.png)、[结构剖面截图](../logs/bf3d_structural_review_20260719/structural_section_1440x900.png)。

## TEST-BF3D-R2Q-V3-MATERIAL-STRUCTURE-EDGE-20260719

| 项目 | 内容 |
|---|---|
| 对应需求 | `REQ-BF3D-R2Q-INTERNAL-MATERIAL-LOOKDEV-V3-20260719`、`REQ-BF3D-R2R-LOCAL-EDGE-SMOKE-20260719` |
| 受控资产 | [V3 主 GLB](../高炉前端数据/models/gl02_blast_furnace_review.v3.glb)、[V3 纯材质 GLB](../高炉前端数据/models/gl02_blast_furnace_material_review.v3.glb)、[V3 结构 GLB](../高炉前端数据/models/gl02_blast_furnace_structural_review.v3.glb)、[直开 Blend](../高炉前端数据/models/gl02_blast_furnace_review.v3.blend) |
| 运行时 | [bf3d-structural-review.js](../高炉前端数据/assets/bf3d-structural-review.js) |
| 验证器 | [verify_bf3d_structural_review.cjs](../tools/verify_bf3d_structural_review.cjs) |
| 跨引擎报告 | [17/17 matrix](../logs/bf3d_structural_review_v3_20260719/matrix_report.json) |
| 本机 Edge 报告 | [4/4 edge smoke](../logs/bf3d_structural_review_v3_20260719/edge_smoke_report.json) |

```powershell
node .\tools\verify_bf3d_structural_review.cjs
node .\tools\verify_bf3d_structural_review.cjs --matrix
node .\tools\verify_bf3d_structural_review.cjs --edge-smoke
```

关键断言：

- V3 主/材质/结构 GLB SHA 分别固定为 `7e4b3b95...574b`、`87c2bbe6...4c09`、`8490f56b...f41a`；直开 Blend 为 `9da11f58...f32`；正式生产 GLB 保持 `808960f1...b62af6`；
- 纯材质审查使用 10 个物理半剖对象和层材质近景相机，使钢壳、背衬、铜/铸铁冷却、热面与耐火层可见；结构剖面使用同一 10 个对象和整炉相机；
- 两种审查模式均隐藏传感器、拾取体、数据引线、黄色轮廓、工艺粒子和旧环线；返回运行视图恢复 115 点；
- Chromium 九视口、Firefox/WebKit 各四代表视口共 `17/17`；
- 本机真实 Microsoft Edge `150.0.4078.83` 以严格 `channel=msedge` 在 `1920×1080`、`1366×768`、`768×1024`、`390×844` 完成 `4/4` 模式切换，意外页面/控制台/HTTP 错误为 `0`。

Edge 报告的 `scope` 固定为 `local Microsoft Edge stable smoke; not on-site Edge acceptance`。它是本机 localhost、headless、静态数据源验证；现场主机、实际交付 URL、真实 8767 数据、现场 GPU/驱动/组策略和人工 headed 冒烟仍未验收，禁止用本机报告关闭 `field_edge_smoke`。

严格 Cycles/Eevee 和 Three.js/Eevee 数值 A/B 另由 `WEB-60 R2R` 失败关闭门管理；17/17 浏览器功能矩阵及 Edge 冒烟都不能替代相机、四灯、色彩与逐图数值合同。

## TEST-BF3D-INT40-R0-TRUTH-INPUT-GATE-20260719

| 项目 | 内容 |
|---|---|
| 对应需求 | `REQ-BF3D-INT40-R0-TRUTH-BACKTEST-INPUT-GATE-20260719` |
| 输入锁 | [input_lock.json](../PT/高炉3D模型/work/INT_40_20260719_R0_TRUTH_BACKTEST_INPUT_GATE/input_lock.json) |
| 参考合同 | [label_contract.md](../PT/高炉3D模型/work/INT_40_20260719_R0_TRUTH_BACKTEST_INPUT_GATE/label_contract.md) |
| 阻断报告 | [blocked_no_accepted_reference.json](../PT/高炉3D模型/work/INT_40_20260719_R0_TRUTH_BACKTEST_INPUT_GATE/blocked_no_accepted_reference.json) |
| 阶段状态 | `blocked_no_accepted_reference`；INT-40 未完成，INT-50 未开始 |

当前可验证的只是：

- 输入工件、测试、报告和正式 GLB 的字节数/SHA 已锁定；
- 当前根部估计器继续为 `uncalibrated/control_use=prohibited/confidence<=0.45`；
- 浏览器 `12/12` 只证明字段和渲染合同；
- 数据源审计证明可读输入，不证明真实软熔带位置、厚度或偏心。

没有签署的独立参考时，不执行或伪造封存集准确率、经验置信区间与适用范围。解除门后必须验证输入 SHA、字段/单位/时区/方位、知识时间无未来泄漏、切分隔离、同输入确定性、缺失/陈旧/错位降级，以及高度/厚度误差、方向识别、区间覆盖率、可用率、漂移和基线比较。

## TEST-BF3D-CLEAN-STRUCTURAL-REVIEW-20260719

- 对应需求：`REQ-BF3D-CLEAN-STRUCTURAL-REVIEW-20260719`
- 被测程序：[V2 导出器](../tools/export_bf3d_structural_review_v2.py)、[Blender 复开/GLB 直导验证](../tools/verify_bf3d_structural_review_v2_blender.py)
- 资产清单：[V2 manifest](../高炉前端数据/models/gl02_blast_furnace_structural_review.v2.manifest.json)
- 预期：
  - 纯材质 GLB 仅 5 个 `steel_shell` 节点；
  - 结构 GLB 仅 10 个节点，角色为 5 钢壳、1 背衬、1 热面、1 耐火、2 冷却壁；
  - `SENSOR/PRESSURE/FLOW/STREAMLINE/BURDEN/TEMP_LAYER/PARTICLE/GUIDE/RING` 等禁止对象为 0；
  - 直接打开 Blend 后结构剖面集合默认可见、完整材质集合默认隐藏、27 张图像已打包；
  - Blender 的 Layout/实体着色不作为材质缺失判断；复开时以已打包图像、材质 ID 和 `Z → M` 材质预览为检查口径；
  - 正式 GLB 与 V1 GLB 哈希不变。
- 验证命令：

```powershell
& 'D:\Program Files\Blender Foundation\Blender 5.2\blender.exe' --background `
  'D:\文件\冀南钢铁运行中第二版本\高炉前端数据\models\gl02_blast_furnace_structural_review.v2.blend' `
  --python-exit-code 1 `
  --python 'D:\文件\冀南钢铁运行中第二版本\tools\verify_bf3d_structural_review_v2_blender.py'

& 'D:\Program Files\Blender Foundation\Blender 5.2\blender.exe' --background `
  --factory-startup --python-exit-code 1 `
  --python 'D:\文件\冀南钢铁运行中第二版本\tools\verify_bf3d_structural_review_v2_blender.py' `
  -- --glb-import
```

- 结果：[复开报告](../PT/高炉3D模型/work/WEB_60_20260719_R2P_CLEAN_STRUCTURAL_REVIEW/reopen_validation.json) 与 [GLB 导入报告](../PT/高炉3D模型/work/WEB_60_20260719_R2P_CLEAN_STRUCTURAL_REVIEW/glb_import_validation.json) 均 `ok=true`。

## TEST-BF3D-C2-ROOT-MOTION-20260719

| 项目 | 内容 |
|---|---|
| 对应需求 | `REQ-BF3D-C2-ROOT-MOTION-20260719` |
| 实现记录 | [软熔带移动预测趋势.md](../PT/软熔带移动预测趋势.md) |
| 估计器 | [cohesive_zone_estimator.py](../炉况规则引擎/features/cohesive_zone_estimator.py) |
| 参数 | [cohesive_zone_estimator.yaml](../炉况规则引擎/config/cohesive_zone_estimator.yaml) |
| 8767 适配 | [local_pg_ws_bridge.py](../自动诊断服务/local_pg_ws_bridge.py) |
| Three.js 运行时 | [bf3d-internal-simulation.js](../高炉前端数据/assets/bf3d-internal-simulation.js) |

```powershell
python -m pytest `
  .\tests\test_cohesive_zone_estimator.py `
  .\tests\test_local_pg_ws_bridge_cohesive_zone.py -q

python -m py_compile `
  .\炉况规则引擎\features\cohesive_zone_estimator.py `
  .\自动诊断服务\local_pg_ws_bridge.py `
  .\tools\check_v3_ws_bridge_python.py

node --check .\高炉前端数据\assets\bf3d-internal-simulation.js
node --check .\tools\verify_bf3d_internal_simulation.cjs
node --check .\tools\verify_bf3d_c2_cross_engine.cjs
node .\tools\verify_bf3d_internal_simulation.cjs
node .\tools\verify_bf3d_c2_cross_engine.cjs
node .\tools\verify_bf3d_internal_simulation_matrix.cjs
node .\tools\verify_gl02_cutaway_runtime.cjs
```

关键断言：

- 当前窗口与参考窗口只使用共同的 L7～L13 层和共同方位，避免缺层造成伪上移/下移；
- 温度和静压力均先在同一标高去除周向均值，再计算共同方位偏心；
- 压力数据必须在五分钟新鲜度门内，静压力至少两个标高才参与纵向梯度；
- 热风、富氧、喷煤等热力修正逐概念执行五分钟新鲜度门；陈旧项只被忽略，
  不阻断主估计，也不能制造虚假上移；
- 禁止读取 `evaluation_time` 之后的数据，缓存按数据源和单调知识时间隔离；
- 可用输出必须在 8767 和浏览器两侧分别满足有限值、几何范围、形状、
  运动、外推和安全元数据合同；
- 固定 `evidence=estimated`、`calibration_status=uncalibrated`、
  `control_use=prohibited`、`confidence<=0.45`；
- 陈旧或失效输出保留明确状态后隐藏，不以 fixture 冒充当前在线炉况。

结果：

- 后端估计器与 8767 桥接：`34 passed`；
- [Three.js 专项报告](../logs/bf3d_internal_simulation_20260719/runtime_contract_report.json)：`ok=true`；
- [C2 三引擎专项](../logs/bf3d_c2_cross_engine_20260719/report.json)：Chromium、Firefox、WebKit 各四个代表视口，`12/12`；
- [跨引擎/视口矩阵](../logs/bf3d_internal_simulation_20260719/matrix/cross_engine_viewport_report.json)：17 个视口运行、85 个页面组合全部通过；
- [旧内切面回归](../logs/bf3d_cutaway_runtime_20260717/formal_report.json)：`ok=true`；
- [确定性验收截图](../logs/bf3d_internal_simulation_20260719/chromium_1440x900_c2_root_prediction.png)只证明前端运行合同，不代表当前生产炉况；
- 本机 `bf_trend` 当前缺少 `bf_sensor`，220.12 本轮直连超时，因此现场只读在线值验证尚未执行。

## TEST-TAPHOLE-HEAT-ALIGNMENT-20260719

对应问题：
[Q-TAPHOLE-HEAT-INFERENCE-20260719](question_traceability.md#q-taphole-heat-inference-20260719)。

测试入口：

- [纯函数测试](../tests/test_analyze_taphole_heat_alignment.py)
- [只读对齐程序](../tools/analyze_taphole_heat_alignment.py)

运行命令：

```powershell
python -m unittest tests.test_analyze_taphole_heat_alignment -v

python tools\analyze_taphole_heat_alignment.py `
  --start "2026-07-12 00:00:00" `
  --end "2026-07-19 00:00:00" `
  --statement-timeout-ms 180000 `
  --out-dir "reports\出铁口温度炉次对齐_20260712_20260718"
```

成功信号：

- 纯函数测试 `3/3 OK`；
- 两个温度变量均从 `bf_sensor.sensor_registry` 解析到唯一物理点；
- 两个点各返回 10,080 个分钟值；
- IMES 返回 89 个 2# 正式炉次；
- `summary.json` 明确记录
  `can_infer_official_heat_number_from_temperatures_alone=false`；
- 数据库事务只读，报告和 CSV 仅写本地 `reports/`。

## TEST-BF3D-R2R-RENDERER-NUMERIC-AB-20260719

- 对应需求：`REQ-BF3D-R2R-RENDERER-NUMERIC-AB-20260719`
- 预注册合同：[capture_contract.json](../PT/高炉3D模型/work/WEB_60_20260719_R2R_RENDERER_NUMERIC_AB_GATE/capture_contract.json)
- Blender 捕获：[render_bf3d_r2q_ab_blender.py](../tools/render_bf3d_r2q_ab_blender.py)
- 数值比较：[compare_bf3d_r2q_ab.py](../tools/compare_bf3d_r2q_ab.py)
- Three.js 预检：[capture_bf3d_r2q_ab_three.cjs](../tools/capture_bf3d_r2q_ab_three.cjs)
- 阶段状态：[pipeline_status.json](../PT/高炉3D模型/work/WEB_60_20260719_R2R_RENDERER_NUMERIC_AB_GATE/pipeline_status.json)

静态检查：

```powershell
python -m py_compile `
  tools\render_bf3d_r2q_ab_blender.py `
  tools\compare_bf3d_r2q_ab.py

node --check tools\capture_bf3d_r2q_ab_three.cjs
```

Blender 捕获和比较入口：

```powershell
& 'D:\Program Files\Blender Foundation\Blender 5.2\blender.exe' `
  --background `
  --python-exit-code 1 `
  --python tools\render_bf3d_r2q_ab_blender.py

python tools\compare_bf3d_r2q_ab.py
```

Three.js 合同预检：

```powershell
node tools\capture_bf3d_r2q_ab_three.cjs
```

当前结果不是成功门：

- Blender 捕获完成 `12/12`，严格 OptiX、无 CPU/CUDA 回退；
- 数值比较进程应因真实失败返回非零，[comparison_report.md](../PT/高炉3D模型/work/WEB_60_20260719_R2R_RENDERER_NUMERIC_AB_GATE/comparison_report.md)必须为 `80 required / 68 pass / 12 fail / 0 not-evaluated`；
- Three.js 进程应因合同不匹配返回非零，[three_contract_preflight.json](../PT/高炉3D模型/work/WEB_60_20260719_R2R_RENDERER_NUMERIC_AB_GATE/reports/three_contract_preflight.json)必须为 `blocked_contract_mismatch`、`13 pass / 8 fail / 2 blocked`；
- [three_capture_manifest.json](../PT/高炉3D模型/work/WEB_60_20260719_R2R_RENDERER_NUMERIC_AB_GATE/reports/three_capture_manifest.json)必须保持 `capture_attempted=false`、beauty/mask `0`、`ab_pass_claimed=false`；
- 输入锁 before/after/current、正式 GLB 和 R2Q 候选 SHA 必须一致；
- 任何阈值捕获后放宽、`not_evaluated` 视为通过、平均两个 repeat 掩盖单项失败或伪造 Three.js 截图，都应使门禁失败。

R2S 的成功信号必须是同一冻结阈值下 Blender `80/80`，且 Three.js 预检全通过后再执行并通过 Three.js/Eevee 数值 A/B；浏览器页面矩阵或人工观感不能替代这两个数值门。

## TEST-BF3D-R2S-RENDERER-CONTRACT-ALIGNMENT-20260720

- 对应需求：`REQ-BF3D-R2S-RENDERER-CONTRACT-ALIGNMENT-20260720`
- 状态：[pipeline_status.json](../PT/高炉3D模型/work/WEB_60_20260719_R2S_RENDERER_CONTRACT_ALIGNMENT/pipeline_status.json)
- 增量清单：[implementation_delta_manifest.json](../PT/高炉3D模型/work/WEB_60_20260719_R2S_RENDERER_CONTRACT_ALIGNMENT/implementation_delta_manifest.json)
- 专项验证器：[verify_bf3d_r2s_audit_contract.cjs](../tools/verify_bf3d_r2s_audit_contract.cjs)
- 结果记录：[r2s_audit_contract_verification.json](../PT/高炉3D模型/work/WEB_60_20260719_R2S_RENDERER_CONTRACT_ALIGNMENT/r2s_audit_contract_verification.json)

执行：

```powershell
node --check 高炉前端数据\assets\bf3d-structural-review.js
node --check tools\verify_bf3d_r2s_audit_contract.cjs
node tools\verify_bf3d_r2s_audit_contract.cjs
node tools\verify_bf3d_structural_review.cjs
node tools\verify_bf3d_structural_review.cjs --matrix
node tools\verify_bf3d_structural_review.cjs --edge-smoke
node tools\verify_gl02_cutaway_runtime.cjs
```

成功信号：

- 真实生产 HTML 和合成 harness 各 `9` 组负向门均禁用，精确双门只开放冻结数值 manifest；
- instrumentation 在应用脚本前建立，两个独立 full-ready 上下文完成 ready、API、4 RAF 和 `450ms` 延迟核查；
- `input_lock.json` 根文件与 `22/22` 锁项前后匹配；R2R 合同/捕获清单 SHA 固定；
- `12` 个 engine × repeat × shot 记录、三个正交 shot、P40 四灯、TOP/world 和原 `13` 项阈值匹配；
- capability/manifest 的递归冻结对象为 `124/40`，`12/12` 次突变以 `TypeError` 拒绝；
- `colorState=pending_preapproval`、`captureEligible=false`、beauty/mask 不可用；
- API 前后生产 Viewer、PerspectiveCamera、OrbitControls、renderer、scene、灯光、资源、viewport/scissor/render target、RAF 和 ACES `1.05` 引用/状态不变，审计副作用为 `0`；
- 硬化验证器为 `112147` bytes、SHA `53b27a0e…5b20a9f`；根代理在最终状态字符串锁定后独立复跑 `2/2 PASS`；
- 原专项 PASS，矩阵 `17/17 PASS`，本机真实 Edge `4/4 PASS`，旧切面错误为 `0`；
- 正式 GLB SHA 仍为 `808960f1…62af6`。

失败信号：

- 单门即可启用、迟注入令牌可绕过模块加载门，或普通生产 URL暴露 capture；
- 缺任一 shot、P40 TOP/方向或原阈值；
- 未批准色彩/光度时生成 beauty/mask；
- 生产相机、控制器、renderer、ACES、页面或 GLB 被修改；
- 将数值合同 PASS 写成跨渲染器图像 PASS。

## TEST-BF3D-R2T-OCIO-PHOTOMETRIC-EQUIVALENCE-20260720

- 对应需求：`REQ-BF3D-R2T-OCIO-PHOTOMETRIC-EQUIVALENCE-20260720`
- 状态：[pipeline_status.json](../PT/高炉3D模型/work/WEB_60_20260720_R2T_OCIO_PHOTOMETRIC_EQUIVALENCE/pipeline_status.json)
- 输入锁：[input_lock.json](../PT/高炉3D模型/work/WEB_60_20260720_R2T_OCIO_PHOTOMETRIC_EQUIVALENCE/input_lock.json)
- 色彩候选：[color_management_candidate.json](../PT/高炉3D模型/work/WEB_60_20260720_R2T_OCIO_PHOTOMETRIC_EQUIVALENCE/color_management_candidate.json)
- 光度合同：[photometric_calibration_contract.json](../PT/高炉3D模型/work/WEB_60_20260720_R2T_OCIO_PHOTOMETRIC_EQUIVALENCE/photometric_calibration_contract.json)
- 生成器：[generate_bf3d_r2t_ocio_assets.py](../tools/generate_bf3d_r2t_ocio_assets.py)
- OCIO 验证器：[verify_bf3d_r2t_ocio_assets.py](../tools/verify_bf3d_r2t_ocio_assets.py)
- 阶段验证器：[verify_bf3d_r2t_stage.py](../tools/verify_bf3d_r2t_stage.py)
- WebGL oracle 验证器：[verify_bf3d_r2t_ocio_webgl.cjs](../tools/verify_bf3d_r2t_ocio_webgl.cjs)
- WebGL oracle 报告：[ocio_webgl_oracle_report.json](../PT/高炉3D模型/work/WEB_60_20260720_R2T_OCIO_PHOTOMETRIC_EQUIVALENCE/reports/ocio_webgl_oracle_report.json)
- LTC runtime oracle 验证器：[verify_bf3d_r2t_ltc_runtime.cjs](../tools/verify_bf3d_r2t_ltc_runtime.cjs)
- LTC runtime oracle 报告：[ltc_runtime_oracle_report.json](../PT/高炉3D模型/work/WEB_60_20260720_R2T_OCIO_PHOTOMETRIC_EQUIVALENCE/reports/ltc_runtime_oracle_report.json)
- 光度 fixture 构建/验证：[build_bf3d_r2t_photometric_fixture.py](../tools/build_bf3d_r2t_photometric_fixture.py)、[verify_bf3d_r2t_photometric_fixture.py](../tools/verify_bf3d_r2t_photometric_fixture.py)
- 光度 fixture 证据：[冻结定义](../PT/高炉3D模型/work/WEB_60_20260720_R2T_OCIO_PHOTOMETRIC_EQUIVALENCE/photometric_fixture/fixture_definition.json)、[fit/held-out 报告](../PT/高炉3D模型/work/WEB_60_20260720_R2T_OCIO_PHOTOMETRIC_EQUIVALENCE/reports/photometric_fit_held_out_report.json)、[独立验证报告](../PT/高炉3D模型/work/WEB_60_20260720_R2T_OCIO_PHOTOMETRIC_EQUIVALENCE/reports/photometric_verification_report.json)
- 隔离审查验证：[verify_bf3d_review_preview.cjs](../tools/verify_bf3d_review_preview.cjs)、[arrayBuffer ×2 稳定性主日志](../PT/高炉3D模型/work/WEB_60_20260720_R2T_OCIO_PHOTOMETRIC_EQUIVALENCE/preview/root_arraybuffer_stability_x2.stdout.log)、[第 1 轮明细](../PT/高炉3D模型/work/WEB_60_20260720_R2T_OCIO_PHOTOMETRIC_EQUIVALENCE/preview/bf3d_review_stability_run_1.json)、[第 2 轮明细](../PT/高炉3D模型/work/WEB_60_20260720_R2T_OCIO_PHOTOMETRIC_EQUIVALENCE/preview/bf3d_review_stability_run_2.json)

执行：

```powershell
& 'D:\Program Files\Blender Foundation\Blender 5.2\5.2\python\bin\python.exe' `
  'tools\generate_bf3d_r2t_ocio_assets.py'

& 'D:\Program Files\Blender Foundation\Blender 5.2\5.2\python\bin\python.exe' `
  'tools\verify_bf3d_r2t_ocio_assets.py'

python -m py_compile `
  tools\generate_bf3d_r2t_ocio_assets.py `
  tools\verify_bf3d_r2t_ocio_assets.py `
  tools\vendor_three_r160_rect_area_ltc.py `
  tools\verify_bf3d_r2t_stage.py

python tools\vendor_three_r160_rect_area_ltc.py --verify-only
python tools\verify_bf3d_r2t_stage.py
node tools\verify_bf3d_r2t_ocio_webgl.cjs
node tools/verify_bf3d_r2t_ltc_runtime.cjs
python tools\build_bf3d_r2t_photometric_fixture.py
python tools\verify_bf3d_r2t_photometric_fixture.py
python tools\serve_bf3d_review.py --check-only
node tools\verify_bf3d_review_preview.cjs
```

OCIO WebGL oracle 命令当前预期退出码为 `1`：exact generated shader 是 release hard gate，
Firefox 黑点 float 失败；该退出码是当前可复现的失败证据，不应改写为脚本异常或整体 PASS。
独立的 LTC runtime oracle 命令当前为 PASS；它只验证 runtime prerequisite，不能覆盖前一条
exact OCIO 硬门失败。

当前成功信号：

- 19 个 R2S/R2R/R2Q/Three/Blender/OCIO 输入 bytes/SHA 全匹配；
- PyOpenColorIO `2.5.0`，processor cache 为 `cb6dc6defbf01d33b84718a55c277f0a`；
- GLSL ES3 为 `14155` bytes、SHA `8e90dd51…494ac`；
- 37³/57³ RGB32F 与 RGBA32F 资源 SHA 匹配；
- `235846` 个 texel 的 RGB 位序和 alpha `0x3f800000` 全量通过；
- 黑、中灰、白、HDR、红、绿、蓝共 8 个 CPU oracle 均通过，最大绝对误差 `4.886817894789175e-10`；
- Three r160 内建 AgX 只记录静态负向事实，不宣称与 Blender Medium Low 等价；
- SUN/TOP/world 只登记 family-level `k=1` 解析候选；TOP `I(k=1)=1.3275510357953`；
- Three r160 官方 LTC addon 为 `313854` bytes、SHA `08085bc9…214`，Three MIT、selfshadow LTC 许可证和 `vendor.lock.json` 全部 verify-only 通过；
- 阶段保持 `capture_eligible=false`、`approval_granted=false`、`next_stage_allowed=false`。
- fixture 定义在 renderer 前冻结为 `103102` bytes、SHA-256 `8d43067c8875c4e677330e830eda079b841d5d8a6fad05f13b26200f349bbcfd`；Blender Cycles `67/67`、Eevee WORLD held-out `8/8`，Three Chromium/Firefox/WebKit 各两次合计 `6/6`，错误 `0`；
- WLS 为 `k_sun=0.9414175269608743`、`k_area=0.9450029255130412`、`k_env=0.9299202953495894`，分母分别为 `0.055471528149193094`、`0.0910057735916505`、`0.0019578534604496323`，均非零；
- fit/held-out 已执行且 held-out 未参与 refit；因未预注册线性接受阈值，只能验证 candidate evidence 完整性，状态为 `candidate_evidence_verified_not_approved`，`photometric_equivalence_approved=false`、`capture_eligible=false`、`production_integration_allowed=false`；
- 隔离审查只请求 SHA-256 `7e4b3b95343103784500aba354a124262ecf593fe89a3f0aa98348692152574b` 的 `review.v3`，以 `response.arrayBuffer()` 完整消费 GLB，使用独立 Scene/Renderer/Camera/RAF，并检查纯材质审查、内部层近景、结构剖面；V3 为 `13` 个 PBR 材质、`39` 个 texture、`21` 个 image、forbidden 对象 `0`；
- arrayBuffer 稳定性门连续执行两轮，每轮 `17/17`、`51` 图，合计 `34/34` viewport runs、`102` captures；`34/34` review GLB 均 `requestfinished=1`、`request_failed=0`，console/page/HTTP/external/request_failed 五类错误累计 `0`；
- 可解释性检查必须确认：外表面横向变化为 R2J 五区实体交界/原始纹理，不是数据圆环/引线；底部深色楔为现有 V3 GLB 十个 Section 封口面共面叠合/遮挡，不是内腔，且 Web 没有修复或改写该几何。

最新 WebGL oracle 结果：

- exact generated shader：Chromium、WebKit 通过，Firefox 失败，即 `2 PASS / 1 FAIL`，exact 硬门整体 FAIL；Firefox 黑点 RGBA32F 为 `0`，CPU oracle 约为 `0.0002386`，最大误差 `0.000238734 > 2e-5`；
- exact 的其余 7 点、三引擎全部默认 framebuffer RGBA8、两次重复，以及页面/控制台/HTTP/外部请求隔离检查均通过；
- literal-nextafter 候选仍是 `2 PASS / 1 FAIL`，候选整体 FAIL；
- 共享 highp uniform `0x00800001` 候选为 `3/3 PASS`，非黑点副作用门也通过，但其审批状态为 `candidate_not_approved`，不能满足或覆盖 exact release hard gate；
- oracle 隔离页未加载或改动生产页面、生产控制器或正式 GLB，也没有执行生产集成。

最新 LTC runtime oracle 结果：

- `node tools/verify_bf3d_r2t_ltc_runtime.cjs` PASS；Chromium、Firefox、WebKit 各执行 `2` 次新鲜运行，结果 `6/6 PASS`；
- oracle 与 `RectAreaLightUniformsLib` 解析到同一 Three r160 ESM；每次只有 `1` 次有效 addon init，显式重复探针均在调用 addon 前被拒绝；
- 四张 `64×64` DataTexture 的类型、payload 与 SHA 通过：`LTC_FLOAT_1=cf5cf21e5c112d2095c7e2418cb0a1ac54636e275d73e42f3453646c67f26814`、`LTC_FLOAT_2=3b1b09080b26104498db277c14fc1733786465c6958e7a8403d688b1e24c2ff5`、`LTC_HALF_1=a391de32f868fd4aa8774917b793174b7be804c08e2fb8924c30f31d7aa8dcd7`、`LTC_HALF_2=fa1ecbc6deb3c85ddf603cdf1e98e30279444f905eb1cebb849d761b570dd696`；六次运行实际选择均为 `float` 分支；
- 单 RectAreaLight + `metalness=1` MeshStandardMaterial 平面在无 environment、无 AmbientLight、无 emissive 时读回非黑；零强度控制为黑；同一引擎的页内重复和两次独立运行字节一致；
- console/page/HTTP/external 四类错误均为 `0`；
- 报告只批准隔离 LTC runtime prerequisite；审批状态仍为 `candidate_not_approved`（顶层 `status=runtime_prerequisite_verified_candidate_not_approved`），不证明 Blender/Three 光度等价，不证明 RectAreaLight 阴影，也不解除 capture、production integration 或 next stage。

当前失败/停止信号：

- exact generated shader 在 Firefox 黑点超过 float `2e-5` 阈值；即使 uniform candidate 为 `3/3 PASS`，exact 硬门仍必须保持 FAIL；
- 3D LUT 轴序、filter、wrap、颜色空间或最后 OETF 与合同不同；
- 浏览器路径对 OCIO 输出再执行一次 sRGB OETF；
- 后续若 `RectAreaLightUniformsLib` 与 renderer 不再解析到同一 Three ESM、有效 init 不为 `1`、重复探针未在 addon 前拒绝、四张 `64×64` LTC texture/扩展分支任一不成立，则 LTC runtime prerequisite 必须 fail closed；
- 按灯、材质、shot、engine 或 browser 分别拟合光强；
- 把 SUN 8°角、RectArea 阴影、DISK/square 或 PMREM/path tracing 写成原生解析等价；
- 把已执行但无预注册接受阈值的 fit/held-out 写成 photometric equivalence PASS，或把 DISK→equal-area square 的 known non-equivalence 写成等价；
- 把 `E/illustrative`、`REF-PENDING` 的隔离审查矩阵 PASS 写成生产页、正式 GLB、Blender/Three 数值 A/B 或阶段批准；
- 许可取证未完成却把 LUT payload 复制到生产 Web 资产；
- 在色彩和光度门通过前生成炉体 beauty/mask 或替换生产 ACES/GLB。

因此 capture、生产接入和 next stage 继续阻断；LTC runtime prerequisite 的 PASS 不改变
exact OCIO 硬门整体 FAIL。独立 V3 页面已解决 `E/illustrative`、`REF-PENDING` 的只读
材质/结构可见性，但光度 fit/held-out、LTC 与 OCIO 均未批准 photometric equivalence 或
production；仍需 OCIO LUT 专属许可、炉体 A/B 和发布门，不能把候选结果写成阶段完成。
正式 GLB SHA-256 仍为 `808960f1b2703e7fb27df35f1b1b1a17063b9b10d2267acba593fc3872b62af6`，
8092 生产默认 V1 仍未修复或替换；十阶段统计仍为 `5` 完成、`2` 部分完成、`3` 未开始。

## TEST-BF3D-R2U-V4-SECTION-CAP-WEB-20260720

| 项目 | 内容 |
|---|---|
| 对应需求 | `REQ-BF3D-R2U-SECTION-CAP-CONTROLLED-V4-20260720` |
| 阶段目录 | [WEB_60_20260720_R2U_SECTION_CAP_CONTROLLED_V4](../PT/高炉3D模型/work/WEB_60_20260720_R2U_SECTION_CAP_CONTROLLED_V4/) |
| 根审查 | [WEB-60_R2U_根审查结论.md](../PT/高炉3D模型/work/WEB_60_20260720_R2U_SECTION_CAP_CONTROLLED_V4/WEB-60_R2U_根审查结论.md) |
| 几何报告 | [section_topology_validation.json](../PT/高炉3D模型/work/WEB_60_20260720_R2U_SECTION_CAP_CONTROLLED_V4/reports/section_topology_validation.json)、[section_cap_overlap_validation.json](../PT/高炉3D模型/work/WEB_60_20260720_R2U_SECTION_CAP_CONTROLLED_V4/reports/section_cap_overlap_validation.json) |
| 独立验证 | [root_independent_verifier_v4.json](../PT/高炉3D模型/work/WEB_60_20260720_R2U_SECTION_CAP_CONTROLLED_V4/reports/root_independent_verifier_v4.json) |
| Khronos | [khronos_gltf_validator_v4.json](../PT/高炉3D模型/work/WEB_60_20260720_R2U_SECTION_CAP_CONTROLLED_V4/reports/khronos_gltf_validator_v4.json) |
| Web 报告 | [bf3d_review_v4_preview_report.json](../PT/高炉3D模型/work/WEB_60_20260720_R2U_SECTION_CAP_CONTROLLED_V4/reports/bf3d_review_v4_preview_report.json) |

固定复验命令：

```powershell
& 'D:\Program Files\Blender Foundation\Blender 5.2\blender.exe' `
  --background `
  --python tools\export_bf3d_structural_review_v4.py `
  -- `
  --verify `
  --blend '高炉前端数据\models\gl02_blast_furnace_review.v4.blend' `
  --output 'PT\高炉3D模型\work\WEB_60_20260720_R2U_SECTION_CAP_CONTROLLED_V4\reports\root_independent_verifier_v4.json' `
  --expected-input-sha256 '86bce712181ac0771ed460806f54b072659fd8f854334bd0a1ddf73b4e15c9c1'

node tools\verify_bf3d_review_v4_preview.cjs
```

预期信号：

- 独立 Blender 验证 `passed=true`，10 个 Section 全部闭合正体积，boundary/non-manifold
  均为 `0`，跨对象封口重叠为 `0`；
- 三份 GLB factory import PASS；Khronos errors 均为 `0`；
- Web `overall_status=full_matrix_passed_illustrative_only`，连续两轮 `34/34`
  viewport runs、`102` captures，五类错误为 `0`，`protected_files_unchanged=true`；
- 独立视觉 PASS；规范只批准 R2U 结构候选，不批准 P60/生产；前端资产隔离加载和
  资源释放 PASS，但统一/纯材质/结构纹理解码估算约 `264/192/264 MiB`。

已知非通过项：主 GLB 与结构 GLB 各有 21 条 generated tangent-space warning；每份
GLB 各有四条本机绝对路径 extras；解码内存/真机性能、R1/R5 AO、生产 8092、现场
Edge、P50/P60/P70/QA-70、长稳和 Blender/Three 数值光度等价仍待。不得把本测试的 isolated illustrative
PASS 写成正式 GLB、生产页或阶段批准。

## QA V8/V9 当前验收增量（2026-09-16）

V9验证：`python -X utf8 -m pytest tests/test_qa_document_knowledge.py tests/test_qa_routing_v9_seams.py tests/test_qa_evidence_policy.py tests/test_qa_history_projection.py tests/test_qa_task_plan.py tests/test_qa_v6_contracts.py -q`预期73passed。真实5次POST/5done/零自动重放，3通过/2部分/0失败；混合请求正常子任务通过仍因代码策略partial。833题库一致性审计不等于语义通过，原始生产答案禁止提交。见[V8/V9交接](handoffs/2026-09-16-qa-routing-v8-v9-production.md)。

## TEST-BF3D-R2V-V5-PORTABILITY-WEB-20260720

| 项目 | 受控值 |
|---|---|
| 对应需求 | `REQ-BF3D-R2V-GLTF-PORTABILITY-TANGENT-BUDGET-20260720` |
| 阶段目录 | [WEB_60_20260720_R2V_GLTF_PORTABILITY_TANGENT_BUDGET](../PT/高炉3D模型/work/WEB_60_20260720_R2V_GLTF_PORTABILITY_TANGENT_BUDGET/) |
| V5 manifest | [gl02_blast_furnace_review.v5.manifest.json](../高炉前端数据/models/gl02_blast_furnace_review.v5.manifest.json) |
| 可移植性 | [v5_portability_audit.json](../PT/高炉3D模型/work/WEB_60_20260720_R2V_GLTF_PORTABILITY_TANGENT_BUDGET/reports/v5_portability_audit.json) |
| 切线最小修复 | [glb_tangent_vector_sanitization.json](../PT/高炉3D模型/work/WEB_60_20260720_R2V_GLTF_PORTABILITY_TANGENT_BUDGET/reports/glb_tangent_vector_sanitization.json) |
| Khronos | [khronos_gltf_validator_v5.json](../PT/高炉3D模型/work/WEB_60_20260720_R2V_GLTF_PORTABILITY_TANGENT_BUDGET/reports/khronos_gltf_validator_v5.json) |
| Web 矩阵 | [bf3d_review_v5_preview_report.json](../PT/高炉3D模型/work/WEB_60_20260720_R2V_GLTF_PORTABILITY_TANGENT_BUDGET/reports/bf3d_review_v5_preview_report.json) |
| 独立审查 | [independent_review_decisions.json](../PT/高炉3D模型/work/WEB_60_20260720_R2V_GLTF_PORTABILITY_TANGENT_BUDGET/reports/independent_review_decisions.json) |

固定复验命令：

```powershell
python tools\audit_bf3d_glb_portability.py `
  --asset '高炉前端数据\models\gl02_blast_furnace_review.v5.glb' `
  --asset '高炉前端数据\models\gl02_blast_furnace_material_review.v5.glb' `
  --asset '高炉前端数据\models\gl02_blast_furnace_structural_review.v5.glb' `
  --output 'PT\高炉3D模型\work\WEB_60_20260720_R2V_GLTF_PORTABILITY_TANGENT_BUDGET\reports\v5_portability_audit.json' `
  --require-release-ready

python tools\serve_bf3d_review_v5.py --check-only
node tools\verify_bf3d_review_v5_preview.cjs
python tools\finalize_bf3d_review_v5.py
```

预期信号：

- 三 GLB 绝对路径 `0`、normal-map 缺失切线风险 `0`、无效显式切线 accessor `0`；
- 10 个 Section 顶点/边界/材质槽/UV 合同保持，10/10 闭合正体积，封口重叠 `0`；
- 3 个未定义几何切线顶点只在统一/结构 GLB 各回退一次，有效非零切线改写数 `0`；
- Khronos 三资产均 `0 errors / 0 warnings`；
- Web 两轮 `34/34` viewport runs、`102` captures，五类错误 `0`；
- 收口器输出 `r2v_scope_passed=true`、`next_release_stage_allowed=false`。

已知非通过项：默认外表面全景材质对比偏弱；内部两实体层之间的窄黑缝可能被误读为
竖线；`EXT_texture_webp` 为必需扩展；三资产同时解码约 `720 MiB`，完整 mip 约
`960 MiB`。现场 Edge、移动端/现场性能、R5 AO、P50/P60/P70/QA-70、生产接入和
Blender/Three 数值光度等价继续待办。

## TEST-BF3D-R2W-CAMERA-AO-INTERFACE-20260720

| 项目 | 受控值 |
|---|---|
| 对应需求 | `REQ-BF3D-R2W-MATERIAL-READABILITY-CAMERA-20260720` |
| 阶段目录 | [WEB_60_20260720_R2W_MATERIAL_READABILITY_AO_EDGE](../PT/高炉3D模型/work/WEB_60_20260720_R2W_MATERIAL_READABILITY_AO_EDGE/) |
| 预注册 | [WEB-60_R2W_阶段预注册合同.md](../PT/高炉3D模型/work/WEB_60_20260720_R2W_MATERIAL_READABILITY_AO_EDGE/WEB-60_R2W_阶段预注册合同.md) |
| Web 构建 | [web_candidate_build_report.json](../PT/高炉3D模型/work/WEB_60_20260720_R2W_MATERIAL_READABILITY_AO_EDGE/reports/web_candidate_build_report.json) |
| Web 矩阵 | [bf3d_review_r2w_preview_report.json](../PT/高炉3D模型/work/WEB_60_20260720_R2W_MATERIAL_READABILITY_AO_EDGE/reports/bf3d_review_r2w_preview_report.json) |
| AO 审计 | [ao_consumption_audit.json](../PT/高炉3D模型/work/WEB_60_20260720_R2W_MATERIAL_READABILITY_AO_EDGE/reports/ao_consumption_audit.json) |
| 相邻层审计 | [interface_gap_audit.json](../PT/高炉3D模型/work/WEB_60_20260720_R2W_MATERIAL_READABILITY_AO_EDGE/reports/interface_gap_audit.json) |
| 独立视觉复核 | [independent_review_decisions.json](../PT/高炉3D模型/work/WEB_60_20260720_R2W_MATERIAL_READABILITY_AO_EDGE/reports/independent_review_decisions.json) |
| 根结论 | [WEB-60_R2W_根审查结论.md](../PT/高炉3D模型/work/WEB_60_20260720_R2W_MATERIAL_READABILITY_AO_EDGE/WEB-60_R2W_根审查结论.md) |

固定复验命令：

```powershell
python tools\audit_bf3d_r2w_ao_consumption.py

& 'D:\Program Files\Blender Foundation\Blender 5.2\blender.exe' `
  --background '高炉前端数据\models\gl02_blast_furnace_review.v5.blend' `
  --python 'tools\audit_bf3d_r2w_interface_gap.py'

python tools\build_bf3d_review_r2w_web.py
python tools\serve_bf3d_review_r2w.py --check-only
node tools\verify_bf3d_review_r2w_preview.cjs
```

预期信号：

- Web 构建范围为 `camera_only=true`；GLB、材质、灯光、曝光、环境、Tone Mapping
  和 AO 均未改变；
- 双轮矩阵为 `34/34` runs、`136` captures，五类错误 `0`，受保护文件不变，
  PBR 改写、禁止对象与黄色轮廓均为 `0`；
- 独立视觉复核只返回
  `conditional_pass_r2w_camera_readability_candidate_only`；
- ORM.R 为全 `255`，glTF `occlusionTexture` 和 Blend ORM.R 消费均不存在；
  `audit_passed=true`，但 `ao_consumption_ready=false`；
- 旧 P50 R3 的 UV 名称和对象身份与 V5 R2J 不兼容，
  `reuse_old_p50_atlas_allowed=false`；
- L03/L04 高度范围不重叠，覆盖率为 `0`，
  `adjacent_layer_continuity_passed=false`、`design_reference_required=true`；
- L03→L05 的 `14.816–49.456 mm` 必须标为非相邻诊断；`z=-1.2 m` 只标为
  冷却壁拼缝/端面剖切诊断。

失败关闭解释：相机可读性 PASS 只说明同一 V5 PBR 在受控近景中更容易看清，不表示
新增或消费了 AO，也不表示相邻层结构连续、P50/P60/P70/QA-70 或生产通过。受控收口器
`python tools\finalize_bf3d_r2w_stage.py` 会写阶段/根状态 JSON 和清单，只能由阶段
所有者在上述文档和证据锁定后执行，不属于只读复验命令。

## TEST-BF3D-R2X-R2J-AO-SMOKE1K-20260720

| 项目 | 受控值 |
|---|---|
| 对应需求 | `REQ-BF3D-R2X-R2J-AO-REBAKE-CONSUMPTION-20260720` |
| 阶段状态 | `r2x_machine_passed_three_visual_failed_closed` |
| 阶段目录 | [WEB_60_20260720_R2X_R2J_AO_REBAKE_CANDIDATE](../PT/高炉3D模型/work/WEB_60_20260720_R2X_R2J_AO_REBAKE_CANDIDATE/) |
| 预注册 | [WEB-60_R2X_阶段预注册合同.md](../PT/高炉3D模型/work/WEB_60_20260720_R2X_R2J_AO_REBAKE_CANDIDATE/WEB-60_R2X_阶段预注册合同.md) |
| 最终候选 | [gl02_blast_furnace_material_review.r2x-ao-smoke1k.v5payload.glb](../PT/高炉3D模型/work/WEB_60_20260720_R2X_R2J_AO_REBAKE_CANDIDATE/glb/gl02_blast_furnace_material_review.r2x-ao-smoke1k.v5payload.glb) |
| 重打包 / 独审 | [r2x_ao_v5_payload_repack_report.json](../PT/高炉3D模型/work/WEB_60_20260720_R2X_R2J_AO_REBAKE_CANDIDATE/reports/r2x_ao_v5_payload_repack_report.json)、[r2x_ao_smoke1k_v5payload_audit.json](../PT/高炉3D模型/work/WEB_60_20260720_R2X_R2J_AO_REBAKE_CANDIDATE/reports/r2x_ao_smoke1k_v5payload_audit.json) |
| Khronos | [khronos_gltf_validator_r2x_ao_v5payload.json](../PT/高炉3D模型/work/WEB_60_20260720_R2X_R2J_AO_REBAKE_CANDIDATE/reports/khronos_gltf_validator_r2x_ao_v5payload.json) |
| Three / pixel diff | [bf3d_review_r2x_representative_report.json](../PT/高炉3D模型/work/WEB_60_20260720_R2X_R2J_AO_REBAKE_CANDIDATE/reports/bf3d_review_r2x_representative_report.json) |
| 独立视觉 | [r2x_independent_visual_review.json](../PT/高炉3D模型/work/WEB_60_20260720_R2X_R2J_AO_REBAKE_CANDIDATE/reports/r2x_independent_visual_review.json) |
| 根结论 | [WEB-60_R2X_根审查结论.md](../PT/高炉3D模型/work/WEB_60_20260720_R2X_R2J_AO_REBAKE_CANDIDATE/WEB-60_R2X_根审查结论.md) |

受控复验命令：

```powershell
python tools\finalize_bf3d_r2x_stage.py --preflight
python tools\repack_bf3d_r2x_ao_v5_payload.py
python tools\audit_bf3d_r2x_ao_candidate.py
python tools\build_bf3d_review_r2x_web.py
python tools\serve_bf3d_review_r2x.py --check-only
node tools\verify_bf3d_review_r2x_preview.cjs
```

机器通过信号：

- 最终候选为 `1,115,216` bytes，SHA-256
  `bd074c23c237fe7ff3abac0f823bd9aef978021e4e829963b3f979e9b58f1c00`；
  五壳具有 `TEXCOORD_2/uv2`，AO texture 绑定 channel `2`，BaseColor、Normal、
  Roughness、Metalness channel 继续为 `0`。
- 非 AO V5 payload 保持，sampler 数量 `1→1`；Khronos `0 errors / 0 warnings`，
  独立审计 `audit_passed=true`。
- Chromium `1440×900` 代表测试共四张截图、两组 off/on pair；运行时只有
  `aoMapIntensity: 0→1` 改变，五类
  `console/page/http/external/request_failed`
  错误均为 `0`，受保护 V5、formal 与生产文件不变。

必须保留的失败证据：

- 首版候选 SHA
  `c8b748ef03b516a78de658a3b25a5f2265fef9bd34cea334a3490fba1fbab139`
  因越权新增第二个 clamp sampler 触发
  `UNAUTHORIZED_EXTRA_AO_CLAMP_SAMPLER`，结果为 `fail_closed`。
- 最终候选的全景和近景两组 `changed_pixels` 均为 `0`，每组 off/on PNG SHA
  完全相同；AO PNG `99.6763%` 为纯白，非白像素仅 `0.3237%`。因此
  `machine_three_passed=true` 但 `visual_gate_passed=false`，独立视觉结论必须是
  `fail_closed_ao_visual_signal_absent`。

四张代表截图：

- [global off](../PT/高炉3D模型/work/WEB_60_20260720_R2X_R2J_AO_REBAKE_CANDIDATE/preview/screenshots/r2x_chromium_1440x900_global-off.png)
- [global on](../PT/高炉3D模型/work/WEB_60_20260720_R2X_R2J_AO_REBAKE_CANDIDATE/preview/screenshots/r2x_chromium_1440x900_global-on.png)
- [detail off](../PT/高炉3D模型/work/WEB_60_20260720_R2X_R2J_AO_REBAKE_CANDIDATE/preview/screenshots/r2x_chromium_1440x900_detail-off.png)
- [detail on](../PT/高炉3D模型/work/WEB_60_20260720_R2X_R2J_AO_REBAKE_CANDIDATE/preview/screenshots/r2x_chromium_1440x900_detail-on.png)

失败关闭边界：`full_matrix_executed=false`。本测试不得触发 2K，不批准
P50/P60、正式 GLB、生产 8092 或下一发布阶段，也不能把 AO 机器绑定通过描述为“具体
材质已经可见”。后续验证应针对可见几何接触源、材质检视照明、近景模式和权威结构参考，
禁止用黑圆环或 BaseColor 改色伪造视觉通过。

## TEST-BF3D-R2Y-MATERIAL-SIGNAL-DIAGNOSTIC-20260720

用途：分离验证 R2Y 的输入哈希、PBR raw signal、AO UV/相机命中、Three.js 代表
fixture 与最终视觉边界；仅为 `E/diagnostic`。

```powershell
python tools\verify_bf3d_r2y_input_gate.py
python tools\audit_bf3d_r2y_ao_uv_hit.py
python tools\audit_bf3d_r2y_pbr_texture_signal.py
python tools\build_bf3d_review_r2y_web.py
python tools\serve_bf3d_review_r2y.py --check-only
node tools\verify_bf3d_review_r2y_preview.cjs
```

预期结果：

- 前五个入口必须成功；输入和受保护资产前后哈希不变；
- CPU UV/AO 门通过，全景/近景 mip 非白可见像素分别为 `785 / 6483`；
- 代表 verifier 捕获 Chromium `1440×900` 下的 13 个状态，五类错误为 `0`；
- 最后一个命令当前预期退出 `1`，因为 macro `0.962958 < 1`、anisotropy
  `1.021708 < 1.03`、environment changed ratio/mean diff 均为 `0`。这是预注册
  fail-closed，不是基础设施运行失败；
- AO WebGL liveness 必须保持 `NOT_EXECUTED`；不得把 CPU 命中或 raw-signal PASS
  合并写成阶段 PASS。

权威输出：

- [CPU AO/UV 报告](../PT/高炉3D模型/work/WEB_60_20260720_R2Y_MATERIAL_SIGNAL_VISIBILITY_DIAGNOSTIC/reports/r2y_ao_uv_hit_raster_audit.json)
- [PBR raw signal 报告](../PT/高炉3D模型/work/WEB_60_20260720_R2Y_MATERIAL_SIGNAL_VISIBILITY_DIAGNOSTIC/reports/r2y_pbr_texture_signal_audit.json)
- [代表报告](../PT/高炉3D模型/work/WEB_60_20260720_R2Y_MATERIAL_SIGNAL_VISIBILITY_DIAGNOSTIC/reports/bf3d_review_r2y_representative_report.json)
- [独立审查](../PT/高炉3D模型/work/WEB_60_20260720_R2Y_MATERIAL_SIGNAL_VISIBILITY_DIAGNOSTIC/reports/r2y_independent_review_decisions.json)

失败关闭边界：完整浏览器/视口矩阵未执行；不批准 beauty、Golden、2K、P50/P60、
正式 GLB 或生产替换。

## TEST-BF3D-ASSET-CONTROLLED-MASTER-R1-20260721

对应需求：`REQ-BF3D-ASSET-CONTROLLED-MASTER-R1-20260721`。

```powershell
& 'D:\Program Files\Blender Foundation\Blender 5.2\blender.exe' --background --python-exit-code 1 --python 'PT\高炉3D模型\work\ASSET_10_20260721_R1_CONTROLLED_MASTER\scripts\build_controlled_master_r1.py'
& 'D:\Program Files\Blender Foundation\Blender 5.2\blender.exe' --background --python-exit-code 1 --python 'PT\高炉3D模型\work\ASSET_10_20260721_R1_CONTROLLED_MASTER\scripts\verify_controlled_master_r1.py'
node tools\validate_bf3d_glb_khronos.cjs --module-dir 'PT\高炉3D模型\work\WEB_60_20260720_R2U_SECTION_CAP_CONTROLLED_V4\vendor\gltf-validator-runtime' --asset 'PT\高炉3D模型\work\ASSET_10_20260721_R1_CONTROLLED_MASTER\glb\bf3d_base.r1.glb' --asset 'PT\高炉3D模型\work\ASSET_10_20260721_R1_CONTROLLED_MASTER\glb\bf3d_sensors.r1.glb' --asset 'PT\高炉3D模型\work\ASSET_10_20260721_R1_CONTROLLED_MASTER\glb\bf3d_combined_review.r1.glb' --asset 'PT\高炉3D模型\work\ASSET_10_20260721_R1_CONTROLLED_MASTER\glb\bf3d_structural_section.r1.glb' --output 'PT\高炉3D模型\work\ASSET_10_20260721_R1_CONTROLLED_MASTER\reports\khronos_gltf_validator_r1.json'
```

预期：输入哈希门通过；母版十个模块集合齐全；静压力点18个；四个GLB网格计数为 `5/18/23/10`；禁用对象为0；Khronos四资产均为0错误、0警告；正式GLB哈希不变。

浏览器运行态补充：打开 `http://127.0.0.1:8095/高炉前端数据/bf3d_controlled_master_r1.server.html`，依次点击组合审查、基础炉体、18点传感器、结构剖面。预期Three.js网格数分别为 `23 / 5 / 18 / 25`，其中结构剖面的25个Web网格来自10个源对象按材质primitive拆分；四项状态均为“可用”，控制台错误和警告为0，页面无横向溢出。证据见[浏览器组件复核报告](../PT/高炉3D模型/work/ASSET_10_20260721_R1_CONTROLLED_MASTER/reports/browser_component_review.json)。

完整总装补充：`bf3d_full_assembly.r1.glb`必须在Blender工厂导入为33个对象，其中5个外壳、10个R2J/R2K结构对象、18个静压力点；Khronos必须为0错误、0警告。浏览器“整体高炉”和“整体剖切”必须加载同一总装GLB并显示 `48/48` Web网格；前者可见23个网格，后者可见43个网格，二者静压力均为18/18，控制台错误/警告为0。

Blender 直接打开工程补充：

```powershell
& 'D:\Program Files\Blender Foundation\Blender 5.2\blender.exe' --background --python-exit-code 1 --python 'PT\高炉3D模型\work\ASSET_10_20260721_R1_CONTROLLED_MASTER\scripts\create_full_assembly_direct_open_blend.py'
& 'D:\Program Files\Blender Foundation\Blender 5.2\blender.exe' --background 'PT\高炉3D模型\work\ASSET_10_20260721_R1_CONTROLLED_MASTER\blends\BF3D_FULL_ASSEMBLY_R1_DIRECT_OPEN.blend' --python-exit-code 1 --python 'PT\高炉3D模型\work\ASSET_10_20260721_R1_CONTROLLED_MASTER\scripts\verify_full_assembly_direct_open_blend.py'
& 'D:\Program Files\Blender Foundation\Blender 5.2\blender.exe' --background 'PT\高炉3D模型\work\ASSET_10_20260721_R1_CONTROLLED_MASTER\blends\BF3D_FULL_ASSEMBLY_R1_DIRECT_OPEN.blend' --python-exit-code 1 --python 'PT\高炉3D模型\work\ASSET_10_20260721_R1_CONTROLLED_MASTER\scripts\render_direct_open_internal_default_preview.py'
```

预期：输出 `.blend` 可由 Blender 5.2 原生复开，并同时存在 `内部工艺_默认 / 完整外观 / 墙体分层` 三个视图层。默认帧为 `432`，活动视图层必须为 `内部工艺_默认`；可见网格总数 `113`，其中矿焦料柱/料面 `11`、内部剖面 `10`、黄色静压力 `18`、布料溜槽 `9`、受控模拟内部模块 `54`。内部模拟模块固定为软熔带 `1`、统一响应回旋区 `26`、死料柱 `1`、滴落液滴 `24`、铁水/炉渣液面 `2`，必须带 `illustrative/simulated` 与 `control_use=prohibited` 标签。默认层可见辅助线为 `0`；`完整外观` 只显示整壳与静压力，`墙体分层` 只显示 R2J/R2K 与静压力。复开报告和视觉门均必须 `passed=true`。

Web 边界：现有 `bf3d_full_assembly.r1.glb` 仍只验证结构总装，文件头保持 `glTF/version 2` 且哈希锁定；上述新增工艺仿真模块尚未纳入该 GLB。GLB 必须通过“文件→导入→glTF 2.0”加载，不得使用“文件→打开”。

## TEST-BF3D-COMPLETE-EXTERIOR-COHESIVE-DRIP-ANIMATION-R2-20260721

对应需求：`REQ-BF3D-COMPLETE-EXTERIOR-COHESIVE-DRIP-ANIMATION-R2-20260721`。

```powershell
& 'D:\Program Files\Blender Foundation\Blender 5.2\blender.exe' --background --python-exit-code 1 --python 'PT\高炉3D模型\work\ASSET_10_20260721_R1_CONTROLLED_MASTER\scripts\create_full_assembly_direct_open_blend.py'
& 'D:\Program Files\Blender Foundation\Blender 5.2\blender.exe' --background 'PT\高炉3D模型\work\ASSET_10_20260721_R1_CONTROLLED_MASTER\blends\BF3D_FULL_ASSEMBLY_R1_DIRECT_OPEN.blend' --python-exit-code 1 --python 'PT\高炉3D模型\work\ASSET_10_20260721_R1_CONTROLLED_MASTER\scripts\verify_full_assembly_direct_open_blend.py'
& 'D:\Program Files\Blender Foundation\Blender 5.2\blender.exe' --background 'PT\高炉3D模型\work\ASSET_10_20260721_R1_CONTROLLED_MASTER\blends\BF3D_FULL_ASSEMBLY_R1_DIRECT_OPEN.blend' --python-exit-code 1 --python 'PT\高炉3D模型\work\ASSET_10_20260721_R1_CONTROLLED_MASTER\scripts\render_direct_open_exterior_preview.py'
& 'D:\Program Files\Blender Foundation\Blender 5.2\blender.exe' --background 'PT\高炉3D模型\work\ASSET_10_20260721_R1_CONTROLLED_MASTER\blends\BF3D_FULL_ASSEMBLY_R1_DIRECT_OPEN.blend' --python-exit-code 1 --python 'PT\高炉3D模型\work\ASSET_10_20260721_R1_CONTROLLED_MASTER\scripts\render_direct_open_animation_keyframes.py'
```

成功信号：

- 源审查壳圆周覆盖审计为 `301.5°`，新 `BF3D_R2_COMPLETE_EXTERIOR` 固定为 5 个 `360°` 闭合区段；
- `完整外观` 可见网格为 `23`：闭合外壳 `5`、静压力 `18`、Section `0`、SIM `0`；
- 时间轴为 `1–480`、`24 fps`；软熔带五个高度样本总变化不小于 `0.75 m`；
- 液滴 01 在帧 `1/49/96/97` 的 Z 位置约为 `+4.35/-5.15/-16.85/+4.35 m`，完整落距大于 `20 m`，循环重生有效；
- 复开、完整外观视觉门、动画双关键帧视觉门全部 `passed=true`。

失败边界：不得用换相机视角掩盖 58.5° 开口；不得把 R2 旋转重建外壳解释为施工几何；不得把时间轴示意动画解释为 C2、CFD、实测液滴或生产控制输出。现有 Web GLB 未同步 R2 对象。

## TEST-BF3D-COMPLETE-EQUIPMENT-PRESENCE-AUDIT-20260721

```powershell
& 'D:\Program Files\Blender Foundation\Blender 5.2\blender.exe' --background 'PT\高炉3D模型\work\ASSET_10_20260721_R1_CONTROLLED_MASTER\blends\BF3D_CONTROLLED_MASTER_R3_EQUIPMENT_MERGED.blend' --python-exit-code 1 --python 'PT\高炉3D模型\work\ASSET_10_20260721_R1_CONTROLLED_MASTER\scripts\audit_complete_equipment_presence.py'
```

当前预期（R3 完成门）：炉顶设备网格 `2`、炉缸底部临时闭合网格 `1`、两个铁口相关网格 `3`、风口/围管可见总成网格 `3`、逐风口位置锚点 `26`；回旋区模拟仍单独为 `26`，报告必须保持 `tuyere_hardware_must_not_be_inferred_from_raceway_simulation=true`，并令 `complete_equipment_assembly_present=true`、缺失设备列表为空。炉缸底部详细建模必须保持 `deferred_after_interim_visible_closure`。

## TEST-BF3D-CONTROLLED-EQUIPMENT-MERGE-R3-20260721

对应需求：`REQ-BF3D-CONTROLLED-EQUIPMENT-MERGE-R3-20260721`。

```powershell
& 'D:\Program Files\Blender Foundation\Blender 5.2\blender.exe' --background --python-exit-code 1 --python 'PT\高炉3D模型\work\ASSET_10_20260721_R1_CONTROLLED_MASTER\scripts\create_full_assembly_direct_open_blend.py'
& 'D:\Program Files\Blender Foundation\Blender 5.2\blender.exe' --background 'PT\高炉3D模型\work\ASSET_10_20260721_R1_CONTROLLED_MASTER\blends\BF3D_CONTROLLED_MASTER_R3_EQUIPMENT_MERGED.blend' --python-exit-code 1 --python 'PT\高炉3D模型\work\ASSET_10_20260721_R1_CONTROLLED_MASTER\scripts\verify_full_assembly_direct_open_blend.py'
& 'D:\Program Files\Blender Foundation\Blender 5.2\blender.exe' --background 'PT\高炉3D模型\work\ASSET_10_20260721_R1_CONTROLLED_MASTER\blends\BF3D_CONTROLLED_MASTER_R3_EQUIPMENT_MERGED.blend' --python-exit-code 1 --python 'PT\高炉3D模型\work\ASSET_10_20260721_R1_CONTROLLED_MASTER\scripts\render_controlled_equipment_details.py'
```

成功信号：

- P40 输入 SHA-256 必须为 `d268759a0e923cf9412da91400cee85e7b94e3418c1c41363053a15c372dd478`，仅允许附加登记白名单中的对象；
- R3 母版与兼容直开副本字节一致，SHA-256 为 `5e5298d014e61be8ec0949367e2b40fb3f7d82f8cc544e5c0ecf9956e96d5640`；
- `完整外观` 可见网格 `32 = 5闭合炉壳 + 18静压力 + 9设备`，Section/SIM 均为 `0`；`内部工艺_默认` 可见设备网格 `9`；`墙体分层` 设备网格 `0`；
- 26个风口锚点编号连续、同高 `Z=-11.8 m`、圆周半径约 `2.8886 m`；不得从26个回旋区模拟反推风口设备；
- 炉顶、风口/围管、铁口三个设备近景视觉门均 `passed=true`；复开失败项和可见辅助线均为 `0`。

边界：R3 是 Blender 受控母版，不覆盖 R1 基线，不同步现有 Web GLB；炉缸底部仅为可见闭合占位，冷却、砖衬、基础和施工结构必须等待后续单独建模。

## TEST-BF3D-IMG2THREEJS-PROTOTYPE-20260724

对应需求：`REQ-BF3D-IMG2THREEJS-PROTOTYPE-20260724`。

启动页面：

```powershell
python -m http.server 8096 --bind 127.0.0.1
```

规格门：

```powershell
python <img2threejs>\forge\stage1_intake\probe_image.py 'PT\高炉3D模型\work\WEB_60_IMG2THREEJS_20260724_R1\reference\gl02_blast_furnace_exterior_layered_reference.png'
python <img2threejs>\forge\stage1_intake\check_reference_admission.py 'PT\高炉3D模型\work\WEB_60_IMG2THREEJS_20260724_R1\reference\gl02_blast_furnace_exterior_layered_reference.png' --viewpoint three-quarter-front --json
python <img2threejs>\forge\stage2_spec\validate_sculpt_spec.py 'PT\高炉3D模型\work\WEB_60_IMG2THREEJS_20260724_R1\spec\object_sculpt_spec.json' --strict-quality --json
```

本机浏览器矩阵：

```powershell
$env:BF_PLAYWRIGHT_CORE_URL='file:///C:/Users/hmw20/.codex/playwright-runtime/node_modules/playwright/node_modules/playwright-core/index.mjs'
node tools\verify_bf3d_img2threejs_preview.mjs
```

成功信号：

- 参考图 `1024×1536`，准入通过，最大连通主体比例 `0.9513`；
- PBR 五通道提取 `confidence=0.86`；
- 严格规格 `ok=true`、25 构件、4 材质；
- 页面为 `ready`，合同通过，八层均可恢复显示；
- 分层隐藏/恢复、45% 展开/复位、灰模、风口聚焦和参考图折叠全部闭环；
- 页面统计为 `239` 网格、`424` 实例构件、`134,720` 三角面；
- Chromium 九视口、Firefox/WebKit 各四个代表视口，共 `17/17` 通过、失败项 `0`。

权威报告：

- [浏览器矩阵 JSON](../PT/高炉3D模型/work/WEB_60_IMG2THREEJS_20260724_R1/reports/browser_matrix.json)
- [浏览器矩阵 Markdown](../PT/高炉3D模型/work/WEB_60_IMG2THREEJS_20260724_R1/reports/browser_matrix.md)
- [img2threejs 管线报告](../PT/高炉3D模型/work/WEB_60_IMG2THREEJS_20260724_R1/reports/img2threejs_pipeline_report.md)

失败边界：不得把生成图的附属结构解释为现场实测、BIM 或施工几何；不得覆盖正式 GLB 或切换 8092 生产路由。

## TEST-BF3D-IMG2THREEJS-SEMANTIC-DETAIL-R2-20260724

对应需求：`REQ-BF3D-IMG2THREEJS-SEMANTIC-DETAIL-R2-20260724`。

本机浏览器矩阵：

```powershell
$env:BF_PLAYWRIGHT_CORE_URL='file:///C:/Users/hmw20/.codex/playwright-runtime/node_modules/playwright/node_modules/playwright-core/index.mjs'
node tools\verify_bf3d_img2threejs_preview.mjs
```

成功信号：

- 页面为 `ready`，运行合同为“合同通过”；
- 工艺大区 `8`，L7～L16 `10` 层，炉体测温 `80` 点；
- 正式传感器 `115`，新增静压力 `18`，风口 `26`，出铁口 `2`；
- 方位状态固定为 `relative_only`，页面不得显示东南西北结论；
- 工艺区、L10、80 点总开关和出铁口设备可隐藏并由“全部显示”恢复；
- 80 点总开关关闭时，L7～L16 单层开关禁用；恢复后重新启用；
- 展开滑块 `45% → 0%` 反馈正确，灰模开关可逆；
- 风口、出铁口、进料口近景和参考图折叠可执行；
- 页面统计为 `284` 网格、`599` 实例构件、`198,456` 三角面；
- Chromium 九视口、Firefox/WebKit 各四个代表视口，共 `17/17` 通过、失败项 `0`；
- 页面错误、控制台错误、资源失败和页面横向溢出均为 `0`。

权威证据：

- [R2 需求追踪](../PT/高炉3D模型/work/WEB_60_IMG2THREEJS_20260724_R1/REQ-BF3D-IMG2THREEJS-SEMANTIC-DETAIL-R2-20260724_追踪.md)
- [浏览器矩阵 JSON](../PT/高炉3D模型/work/WEB_60_IMG2THREEJS_20260724_R1/reports/browser_matrix.json)
- [浏览器矩阵 Markdown](../PT/高炉3D模型/work/WEB_60_IMG2THREEJS_20260724_R1/reports/browser_matrix.md)

失败边界：不得把正式 115 点与新增 18 点混为一组；不得把 3 个旧静压力节点复制成 18 个实测值；不得伪造单风口差异；不得把诊断覆盖层解释为断开的机械炉壳。

## TEST-BF3D-FURNACE-BODY-BILLBOARD-R1-20260725

对应需求：`REQ-BF3D-FURNACE-BODY-BILLBOARD-R1-20260725`。

本机验证：

```powershell
$env:BF_PLAYWRIGHT_CORE_URL='file:///C:/Users/hmw20/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright-core/index.mjs'
node tools\export_bf3d_furnace_body_billboard_asset.mjs
node tools\verify_bf3d_furnace_body_billboards.mjs
node tools\capture_bf3d_asset_catalog_previews.mjs
node tools\verify_bf3d_asset_catalog.mjs
```

成功信号：

- 本体 GLB 中正式传感器、静压力、非实体数据环和上料/外部除尘节点均为 `0`；
- 点位清单为正式传感器 `115`、静压力 `18`、总计 `133`；
- 网页创建 `133` 个 `THREE.Sprite`，图层切换、查找、点选和数据适配器通过；
- Chromium 1440×900 与 390×844 无横向溢出、控制台错误或页面错误；
- Khronos glTF Validator 错误 `0`，GLB 可移植性 `release_ready=true`；
- 分布式资产库共 `9/9` 加载与完整性验证通过。

证据：

- [本体与 Billboard 需求追踪](../PT/高炉3D模型/模型资产库/09_高炉本体133点Billboard/REQ-BF3D-FURNACE-BODY-BILLBOARD-R1-20260725_追踪.md)
- [网页运行时报告](../PT/高炉3D模型/模型资产库/09_高炉本体133点Billboard/billboard_validation_report.json)
- [点位清单](../PT/高炉3D模型/模型资产库/09_高炉本体133点Billboard/sensor_billboards.v1.json)
- [资产库完整性报告](../PT/高炉3D模型/模型资产库/asset_catalog_validation.json)

失败边界：Billboard 是网页运行时数据层，默认数值为空；不得把测试值写入资产、
不得把坐标清单解释为新增实测数据，也不得切换 8092 生产路由。

## TEST-BF3D-FURNACE-BODY-BILLBOARD-CN-R1-20260725

对应需求：`REQ-BF3D-FURNACE-BODY-BILLBOARD-CN-R1-20260725`。

本机验证：

```powershell
node tools\build_bf3d_furnace_body_billboard_cn_variant.mjs
$env:BF_PLAYWRIGHT_CORE_URL='file:///C:/Users/hmw20/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright-core/index.mjs'
node tools\verify_bf3d_furnace_body_billboards_cn.mjs
node tools\capture_bf3d_asset_catalog_previews.mjs
node tools\verify_bf3d_asset_catalog.mjs
```

成功信号：

- 中文点位清单为 `133` 项，且 `133/133` 个缩写均含中文；
- 中文版与原 09 资产的原始 ID 集合完全相同，唯一 ID 为 `133`；
- `SENSOR_T_taphole_1/2` 分别显示“南铁口温/北铁口温”；
- `SENSOR_T_body_L10_A` 显示“身下温·L10A”；
- `GL02_INT30_PRESSURE_MIDDLE_B` 显示“身中静压·B”；
- 运行时 locale 为 `zh-CN`，`THREE.Sprite` 为 `133`；
- Chromium 1440×900 与 390×844 通过，资产总库 `10/10` 通过。

证据：

- [中文版本需求追踪](../PT/高炉3D模型/模型资产库/09_高炉本体133点Billboard_cn/REQ-BF3D-FURNACE-BODY-BILLBOARD-CN-R1-20260725_追踪.md)
- [中文逐点映射](../PT/高炉3D模型/模型资产库/09_高炉本体133点Billboard_cn/cn_label_mapping.v1.json)
- [中文版本验证报告](../PT/高炉3D模型/模型资产库/09_高炉本体133点Billboard_cn/cn_variant_validation_report.json)

失败边界：不得改写点位 ID、坐标、类别或实时数据绑定键；中文缩写只属于显示层。
# REQ-BF3D-BILLBOARD-PSPACE-LIVE-20260726

- 合同测试：
  `python -m pytest tests\test_pspace_billboard_realtime_bridge.py -q`。
  成功信号为 140 个兼容流字段、133 个 Billboard `point_meta`、
  `billboard_mapped=133`、缺失为 0。
- 浏览器测试：
  `node tools\verify_bf3d_furnace_body_billboards_cn.mjs`。
  测试在页面加载前安装 pSpace WebSocket 合同桩，向 133 个
  `canonical_id` 下发真实帧形状的值、时间和 `Good` 质量码；桌面与手机均需
  通过，控制台/页面错误为 0。
- 生产验收：
  [受控远端发布脚本](../tools/remote_deploy_8094_billboard_pspace_live.ps1)
  新建并启动独立 `V4BillboardPspace8770`，不重启 8768；随后运行
  `python tools\verify_billboard_pspace_8770.py` 读取真实 WebSocket tick；必须返回
  `stream_value_count=140`、`billboard_meta_count=133`、
  `numeric_billboard_values=133`、`quality_metadata_count=133`、
  `billboard_missing_count=0` 和 `required_keys_present=true`。
- 背景验收：8094 与独立预览均应默认 `soft-light/#eef2f1`，背景控件必须包含
  护眼浅灰、纯白、钢灰、深色和自定义；切换背景不得重启或改动 8768/8770。

## 8093/8094 炉顶压力“如何”趋势回归（2026-07-26）

- 精确提示词：`最近半小时炉顶压力如何？`
- 路由断言：`mcp_prefetch_used=true`、`mcp_prefetch_kind=statistics`、
  `mcp_prefetch_variables=["P_top"]`。
- 内容断言：回答必须包含半小时时间范围、数值范围、平均值、起止变化和
  上升/下降/平稳趋势；不得出现“未提供连续数据”或“无法判断”。
- 单元与图表回归：
  `python -m pytest 高炉前端数据/智能助手/tests/test_qa_latency_optimizations.py
  高炉前端数据/智能助手/tests/test_mcp_chart_expansion.py -q`，应为 `41 passed`。
- 2026-07-26 现网结果：8093、8094 均 HTTP 200、自动验收通过，并各产生一次
  MCP statistics 工具结果。

## TEST-MCP-AGENT-ORCHESTRATION-20260726

- 对应需求：`REQ-MCP-AGENT-ORCHESTRATION-20260726`。
- 测试文件：
  [test_mcp_agent_orchestration.py](../高炉前端数据/智能助手/tests/test_mcp_agent_orchestration.py#L28)。
- 覆盖内容：合法调用、未知工具、Schema 外 SQL 参数、缺少必填参数、错误枚举、
  数组/载荷上限、多步分析路由、纯知识问题不误触发，以及流式入口保持多轮工具
  执行。
- 回归命令：
  `python -m pytest 高炉前端数据/智能助手/tests/test_mcp_agent_orchestration.py
  高炉前端数据/智能助手/tests/test_qa_latency_optimizations.py
  高炉前端数据/智能助手/tests/test_mcp_chart_expansion.py -q`。
- 预期与实测：`49 passed`。
- 现网测试：8093/8094 对半小时顶压与总压差相关性问题均执行
  `find_gl02_variables × 2 + plot_gl02_analysis × 1`，HTTP 200、自动验收通过；
  [结果 JSON](../logs/8093_8094_mcp_agent_orchestration_acceptance_20260726.json)。

## TEST-MCP-AGENT-LATENCY-20260726

- 对应需求：`REQ-MCP-AGENT-LATENCY-20260726`。
- 测试文件：
  [test_mcp_latency_optimization.py](../高炉前端数据/智能助手/tests/test_mcp_latency_optimization.py)。
- 覆盖：相关性复合单工具计划、规划上下文排除完整炉况/RAG、低温度和小输出
  默认值、成功结果缓存、失败结果不缓存、规划预算和工具超时接线。
- 基线保护测试：
  `python tools/restore_mcp_route_baseline.py --verify`，必须显示3个文件全部
  `ok=true`；不得在常规测试中运行`--restore`。
- 全量相关回归结果：`54 passed`。
- 现网性能验收：同题工具调用由3次降至1次；8093优化后样本15.43/25.94秒，
  8094优化后16.32秒；固定统计路由仍为HTTP 200和自动通过。
- 证据：
  [性能验收JSON](../logs/8093_8094_mcp_latency_optimization_acceptance_20260726.json)。

## TEST-MCP-BUSINESS-OBJECT-CATALOG-20260726

- 对应需求：`REQ-MCP-BUSINESS-OBJECT-CATALOG-20260726`。
- 测试文件：
  [test_business_object_catalog.py](../高炉前端数据/智能助手/tests/test_business_object_catalog.py)。
- 覆盖：
  - 7个catalog JSON文件存在且可解析；
  - 9种业务对象类型齐全；
  - 每个对象满足统一必填合同；
  - 18个静压力点全部进入sensor目录；
  - 炉顶压力、铁水硅、炉渣、进料、日报和相关图表可搜索；
  - list/get/search工具合同和未知对象错误。
- 回归命令：
  `python -m pytest 高炉前端数据/智能助手/tests/test_business_object_catalog.py
  高炉前端数据/智能助手/tests/test_mcp_latency_optimization.py
  高炉前端数据/智能助手/tests/test_mcp_agent_orchestration.py
  高炉前端数据/智能助手/tests/test_qa_latency_optimizations.py
  高炉前端数据/智能助手/tests/test_mcp_chart_expansion.py -q`。
- 结果：`61 passed`；8093/8094统一目录口语2/2自动通过。
- 证据：
  [目录验收JSON](../logs/8093_8094_business_object_catalog_acceptance_20260726.json)。

## TEST-MCP-CONVERSATION-CONTEXT-20260726

- 测试文件：
  [test_mcp_conversation_context.py](../高炉前端数据/智能助手/tests/test_mcp_conversation_context.py)、
  [test_business_object_catalog.py](../高炉前端数据/智能助手/tests/test_business_object_catalog.py)。
- 覆盖：首轮对象/时间记录、低信息追问继承、时间替换、对象合并与替换、图表
  切换、相关矩阵优先级、latest不误触发图表、确定性事实回答、未知变量ID禁止
  模糊匹配。
- 相关回归：
  `python -m pytest test_mcp_conversation_context.py test_business_object_catalog.py
  test_mcp_latency_optimization.py test_mcp_agent_orchestration.py
  test_qa_latency_optimizations.py test_mcp_chart_expansion.py -q`。
- 结果：`76 passed`。
- 现网多轮：
  `python tools/test_8093_mcp_context_followups.py
  --output logs/8093_mcp_context_followups_20260726.json`，结果`7/7`。
- 关键四问：
  `python tools/test_8093_colloquial_prompts.py --groups mcp
  --case mcp_latest_probe_pair --case mcp_latest_top_gas_pressure_abcd
  --case mcp_latest_cold_blast_pressure --case mcp_latest_oxygen_pair`，
  结果`4/4`自动通过，中位总耗时`1117.6ms`，回答包含正式中文名和单位。
- 无Prompt直连：
  `python tools/test_mcp_direct_no_prompt.py
  --output logs/mcp_direct_no_prompt_20260726.json`，结果4/4，总耗时
  `3730.5ms`；报告明确`llm_used=false/qa_router_used=false/rag_used=false`。
## TEST-PT-SIX-PRODUCTION-ANALYTICS-20260726

- 对应需求：`REQ-PT-SIX-PRODUCTION-ANALYTICS-20260726`
- 测试文件：[tests/test_pt_six_analysis_modules.py](../tests/test_pt_six_analysis_modules.py)
- 命令：

  ```powershell
  python -m pytest -q tests/test_pt_six_analysis_modules.py --basetemp .tmp/pytest_pt_six
  ```

- 验证范围：六个入口均能读取标准CSV并生成各自结果；测试样本贯通炉次、Si、
  炉况质量、矿焦批次、分钟传感器和烧结矿背景。
- 2026-07-26 实际结果：`1 passed`。默认系统临时目录曾返回 WinError 5，改用
  工作区内受控 `--basetemp` 后通过，该错误与模块逻辑无关。
## TEST-HEAT-MULTISOURCE-EXPLORER-20260727

- 需求：`REQ-HEAT-MULTISOURCE-EXPLORER-20260727`
- 本地契约：`tests/test_heat_service.py`、`tests/test_external_sources.py`、
  `tests/test_heat_data_explorer_contract.py`、
  `tests/test_heat_dashboard_si_distribution.py`。功能改造后首次完整回归为
  `17 passed`；移动端 CSS 定点修复后，JavaScript `node --check` 与 4 个前端
  直接契约断言再次通过。
- 远端 API：31 项目录；Vastbase 双账号、PostgreSQL、pSpace ready；
  IMES Web `authorization_required`；正式炉次 `2#20260726-345` 以
  `heatno+batchno` 双键精确返回；CSV/XLSX 文件头通过。
- 远端页面：真实 pSpace UI 查询返回 2 行；Chromium 固定视口
  `1280×720`、`1366×768`、`1440×900`、`1546×864`、`1920×1080`、
  `1024×768`、`768×1024`、`390×844`、`375×667` 为 9/9；无页面横向
  溢出、核心查询按钮可达、表格内部可滚动、宋体生效、浏览器错误 0。
- 证据：
  `F:\高炉炼铁项目-real-sensor-v2_V4_8093_PREVIEW\logs\acceptance\8891_multisource_20260727\8891_multisource_acceptance.json`
  及同目录截图。Firefox、WebKit、现场 Edge 本次未执行，不能写成完整跨浏览器通过。

## TEST-BF3D-8094-SURFACE-CAMERA-GUARD-20260801

- 对应需求：`REQ-BF3D-8094-SURFACE-CAMERA-GUARD-20260801`。
- 本地静态验证：

  ```powershell
  node --check 高炉前端数据/assets/bf3d-surface-camera-guard-8094.js
  python -m py_compile tools/patch_8094_surface_camera_guard.py tools/verify_remote_8094_surface_camera_guard.py
  python tests/test_8094_surface_camera_guard_contract.py
  ```

- 契约结果：`2 tests OK`。补丁器幂等且会备份；守卫必须替换旧炉心滚轮处理器、
  设置炉壳表面 target 并在向内移动前执行壳体 Raycast。
- 远端交互：Chrome/CDP 打开真实 8094 页面，确认 133 个 Billboard；连续 54 次
  向内滚轮最多在首次碰撞时即停止，真实炉壳法向间距为 `1.200m`，target 保持
  同一炉壳表面点；点击“全景”后仍为 `shell-raycast` 表面 target。
- Chromium 视口：`1280×720`、`1366×768`、`1440×900`、`1546×864`、
  `1920×1080`、`1024×768`、`768×1024`、`390×844`、`375×667` 全部通过；
  无页面横向溢出、3D 视口可见、守卫就绪、target 模式为 `furnace-surface`。
- 证据：
  `F:\高炉炼铁项目-real-sensor-v2_V4_8093_PREVIEW\logs\acceptance\8094_surface_camera_guard_20260801_r1`。
  Firefox、WebKit、现场 Edge 未执行。

## TEST-BF3D-8093-NEAR-CLIP-20260801

- 对应缺陷：`BUG-BF3D-8093-NEAR-CLIP-20260801`。
- 本地验证：

  ```powershell
  node --check 高炉前端数据/assets/bf3d-surface-camera-guard-8094.js
  node --check 高炉前端数据/assets/bf3d-surface-camera-guard-8093.js
  python -m py_compile tools/verify_remote_8093_furnace_body_no_simulation.py tools/run_remote_22012_with_local_deps.py
  python -m unittest tests.test_8093_furnace_body_no_simulation_contract
  ```

- 结果：语法检查通过，`2 tests OK`。契约覆盖 8093 缓存版本、`0.05m`
  端口专属近裁剪面、滚轮纠偏、周期纠偏和运行时纠偏计数；8094 默认端口分支
  不启用该锁定。
- 部署探针：远端磁盘和 8093 HTTP 返回同时包含新标记；入口哈希
  `01231424...D462F9`，共享守卫哈希 `0C331DE1...AB929`，主页面哈希
  `8DF482B7...01B9D6`；外层入口和模块内部均使用 `near-plane-r4`；资源回滚目录
  包含 2 文件，主页面另有独立回滚备份。
- 真实 Chrome 核心回归：10 次标准 `WheelEvent` 后停止在炉壳外 `1.2m`；
  `cameraNear=0.05m < signedShellGap=1.2m`；模型、133 点、端口作用域、无仿真
  面板、无仿真运行时和浏览器错误 0 均通过，共 10/10 核心断言。
- 核心报告：
  `F:\高炉炼铁项目-real-sensor-v2_V4_8093_PREVIEW\logs\acceptance\8093_near_plane_fix_20260801_r8\8093_furnace_body_no_simulation_acceptance.json`。
- 本轮没有生成新截图或重跑 45 组合：服务器无界面 Chrome 的截图和尺寸切换
  超过单次 5 秒等待限制。布局仍引用
  `8093_furnace_body_no_simulation_20260801_r1` 的 45/45 基线；Firefox、WebKit、
  现场 Edge 与用户端视觉复核待补。

## TEST-BF3D-8093-FURNACE-BODY-NO-SIM-20260801

- 对应需求：`REQ-BF3D-8093-FURNACE-BODY-NO-SIM-20260801`。
- 本地契约与语法：

  ```powershell
  node --check 高炉前端数据/assets/bf3d-surface-camera-guard-8094.js
  node --check 高炉前端数据/assets/bf3d-surface-camera-guard-8093.js
  python -m py_compile tools/patch_8093_furnace_body_no_simulation.py tools/verify_remote_8093_furnace_body_no_simulation.py
  python tests/test_8093_furnace_body_no_simulation_contract.py
  ```

- 契约结果：`2 tests OK`。验证 21 个静压兼容点、两处 viewer 句柄合同、133 点
  适配器、8093 端口作用域相机、内联 favicon，以及内部仿真 JS/CSS 均未加载。
- 远端资产：`models/gl02_blast_furnace.glb` 为 `8,229,120` bytes，SHA-256
  `150DF18B68F0410B9A168F80C2DF34EFDA86384FC51D37226F81C2ACD244ED53`。
- Chrome 真实交互：133 点；schema 为
  `bf3d.surface-camera-shell-guard.8093.v1`；连续滚轮触发炉壳碰撞并停在 `1.2m`；
  仿真面板数量 0，仿真运行时不存在。
- Chromium 完整矩阵：总览、炉况诊断、参数优化建议、趋势分析、智能问答 ×
  `1280×720`、`1366×768`、`1440×900`、`1546×864`、`1920×1080`、
  `1024×768`、`768×1024`、`390×844`、`375×667`，共 45/45 通过；无页面
  横向溢出、正式头部可见、浏览器错误 0。
- 证据：
  `F:\高炉炼铁项目-real-sensor-v2_V4_8093_PREVIEW\logs\acceptance\8093_furnace_body_no_simulation_20260801_r1`。
  Firefox、WebKit、现场 Edge 未执行。

## TEST-BF3D-8093-DUAL-CAMERA-MODES-20260801

- 对应需求：`REQ-BF3D-8093-DUAL-CAMERA-MODES-20260801`；本节取代上文 v1
  固定表面 target 的相机交互口径，但不推翻 45/45 页面布局基线。
- 本地语法与契约：

  ```powershell
  node --check 高炉前端数据/assets/bf3d-surface-camera-guard-8093.js
  python -m py_compile tools/patch_8093_furnace_body_no_simulation.py tools/remote_deploy_8093_dual_camera_modes.py tools/deploy_8093_dual_camera_modes_smb.py tools/verify_remote_8093_furnace_body_no_simulation.py
  python -m unittest tests.test_8093_furnace_body_no_simulation_contract tests.test_8093_dual_camera_deploy
  ```

- 结果：JavaScript、4 个 Python 文件均通过语法检查；模型纠错后 `4 tests OK`。契约覆盖
  `bf3d.camera.dual-mode.8093.v2`、炉心 target、全模型包围半径、无限方位角、
  累计方位行程、Billboard 聚焦、动态方位 Raycast、退出复位和 8094 隔离；临时
  根目录部署测试还验证备份存在、8093 原子替换成功、8094 页面及运行时哈希不变；
  新增契约固定专项页只能加载 `GL02_FURNACE_BODY_R1.glb`、`8,229,120` bytes 和
  受控 SHA-256，不得退回本机 `4,314,736` bytes 的同名旧模型。
- 模型纠错：首次记录的累计 `650.8°`、动态更新 `8→125` 和碰撞结果来自错误的
  本机旧模型，只保留为算法原型历史，不属于正式模型验收。
- 正确资产浏览器冒烟：`GL02_FURNACE_BODY_R1` 实际/预期字节数均为 `8229120`，
  `assetVerified=true`，133 点、`overview/furnace-center`、near `0.050m`、包围半径
  `25.769`，浏览器 error/warning 为 0。完整旋转、点位聚焦与碰撞交互待按正确
  资产重新执行。
- 未完成项：截至记录时远端 8093 未部署，故不能把本机专项结果表述为 220.12
  验收。远端恢复后运行
  `tools/remote_deploy_8093_dual_camera_modes.py` 与
  `tools/verify_remote_8093_furnace_body_no_simulation.py`，再补远端 Edge、Firefox、
  WebKit 及规定视口矩阵。

## TEST-BF3D-8093-MEASURED-121-OVERVIEW-20260801

- 对应需求：`REQ-BF3D-8093-MEASURED-121-OVERVIEW-20260801`；本节取代上文双相机/点位聚焦运行口径，不推翻既有页面布局基线。
- 验证命令：

  ```powershell
  node --check 高炉前端数据/assets/bf3d-physical-point-filter-8093.js
  node --check 高炉前端数据/assets/bf3d-surface-camera-guard-8093.js
  python -m py_compile tools/remote_deploy_8093_physical_points_overview.py tests/test_8093_physical_points_overview.py
  python -m unittest tests.test_8093_physical_points_overview tests.test_8093_furnace_body_no_simulation_contract
  ```

- 结果：JavaScript 与 Python 语法通过；`Ran 7 tests / OK`。测试固定 121 个可见点、12 个排除点、100 个炉壳物理点、21 个设备实测点、左侧变量面板零改动、点位聚焦缺失、炉心 target、全模型半径、无限方位角和 8094 三项资源哈希隔离。
- 远端静态验收：8093 页面、筛选器和相机资源均为 HTTP 200；页面版本为 `20260801-measured121-r2` 与 `20260801-overview-only-r6`。部署备份为 `F:\高炉炼铁项目-real-sensor-v2_V4_8093_PREVIEW\backups\8093_measured121_overview_20260801\20260801_202127`。
- 浏览器边界：正式页加载超过用户限定的单次 5 秒操作窗口，本轮没有通过延长等待补做全量视觉矩阵；不得把静态/契约验收写成 Firefox、WebKit 或现场 Edge 已通过。

## TEST-BF3D-8094-CAD-BOTTOM-BAND-20260804

- 对应故障：`BUG-BF3D-CAD-BOTTOM-BAND-20260804`。
- 验证命令：

  ```powershell
  python -m unittest -v tests.test_8094_cad_bottom_band_fix tests.test_8093_cad_bottom_band_fix
  python -m py_compile tools/patch_8094_cad_bottom_band.py
  ```

- 结果：7 项合同测试通过，补丁器语法通过；覆盖 8093/8094 scope、首次插入、R2 `padding-bottom:0`、旧补丁自动升级、`bottom:0` 及紧凑断点、幂等、无关页面拒绝、8093 守卫部署和 8094 精确 PID 重启合同。
- 远端结果：8094 任务 Running、HTTP 200，R2 HTML SHA-256 `A13AB868BA7D71FC04450D05BD88D23506DB6BB7103C1165D5CCFD2021D193C7`。8093 部署 `guard_paused=true`、`guard_restored=true`、HTTP 200，R2 HTML SHA-256 `0AB75FF725FC889062C051ED1A6775C25E796F474151DACD95E791044896A3F4`；闭环内 8094/8768/8770 PID 和保护哈希不变。
- 浏览器结果：旧 `1552×765` stage/viewer 测量因未覆盖 panel-body padding 已作废。R2 Chrome 两页 `1552×816` 均为 `readyState=complete`、R2 标记存在、三维 canvas 存在；canvas/panel-body 底差约 `0.606px`、`padding-bottom=0px`、横向溢出为 0。截图位于 `logs/acceptance/8093_8094_cad_bottom_band_20260804_r2/`。

## TEST-8096-DIAGNOSIS-MANUAL-SCORE-20260804

- 对应需求：`REQ-8096-DIAGNOSIS-MANUAL-SCORE-AND-SUGGESTION-20260804`。
- 静态与模块验证：

  ```powershell
  python -m py_compile 高炉前端数据/智能助手/backend/diagnosis_review.py 高炉前端数据/智能助手/backend/ollama_proxy_server.py db_dashboard/server.py
  node --check 高炉前端数据/assets/bf-diagnosis-review-local.js
  node --check 高炉前端数据/assets/bf-diagnosis-manual-score-local.js
  python -m pytest tests/test_diagnosis_review_api.py tests/test_diagnosis_review_contract.py -q
  ```

- 结果：`18 passed`；仅有工作区中文路径下pytest缓存目录权限警告，不影响测试。覆盖准确八类键、人工分0～100、建议单独提交、空表单关闭提示、快照防篡改、回环库边界、两类事件表和仪表盘合同。
- 本机数据库：PostgreSQL 16 `127.0.0.1:18000` 保存手动评分 `cold=73` 与异常弹窗复核 `channel=66/uncertain` 两条验收事件；各自保留8个服务端系统分，来源均为 `local_fixture`。直接关闭另一炉况窗口前后，手动评分表记录数保持1。
- 鉴权/幂等：未登录查询返回401；测试账号登录返回200，Cookie包含 `HttpOnly` 与 `SameSite=Strict`；重放同一幂等键返回 `created=false`，手动事件数仍为1。
- 生产边界：只读查询220.12:5432确认 `bf_assistant.diagnosis_review_events` 与 `diagnosis_manual_score_events` 均不存在；本次没有在220.12新增或修改复核记录。
- 远端健康：验收收尾时220.12的8093、8094、8768均在监听，8093/8094 HTTP均为200；本次未执行远端服务启停或部署。
- 页面/API：正常炉况不自动弹窗；八张炉况卡全部可手动打开评分；异常弹窗包含人工分和建议；两类窗口均可关闭。`/api/diagnosis-foreman-scores` 的真实来源显示“未打分”，本机测试来源可查到两条人工分；CSV和XLSX均HTTP 200。
- Chromium响应式：异常弹窗通过 `1280×720`、`1366×768`、`1440×900`、`1546×864`、`1920×1080`、`1024×768`、`768×1024`、`390×844`、`375×667`；手动评分窗口通过四个代表视口。全部无横向溢出、弹窗在视口内、内容可滚动、关闭和保存按钮可呈现。
- 未完成矩阵：Python Playwright包下载在网络代理处多次中断，因此项目自动验证器和Firefox/WebKit未运行。Chromium控制台只有主HTML既有Babel大脚本去优化提示；未观察到本次评分模块JavaScript错误。不得据此宣称Firefox/WebKit通过。

## TEST-THREE-RULES-DOCX-MARKDOWN-20260804

- 对应需求：`REQ-THREE-RULES-RECOMMENDATION-ALIGNMENT-20260804`。
- 测试文件：[test_convert_docx_to_markdown_verified.py](../tests/test_convert_docx_to_markdown_verified.py)。
- 运行命令：

  ```powershell
  python -m unittest tests.test_convert_docx_to_markdown_verified -v
  python tools\convert_docx_to_markdown_verified.py `
    docs\冀钢炼铁三规二制.docx docs\冀钢炼铁三规二制.md `
    --report logs\three_rules_markdown_validation.json
  ```

- 预期：单元测试通过；报告中 `exact_ordered_text_payload_match=true`，源文本片段
  与写入文本片段 SHA-256 相同，表格数为 122。
- 本次结果：`1 test / OK`；源与写入有序文本片段完全一致。精确片段数和
  SHA-256 以每次生成的校验报告为准。
- 边界：该测试证明正文文字和表格单元格没有在转换时遗漏或改写，不证明
  Word 分页、字体、页眉页脚或视觉版式与 Markdown 相同。

## TEST-THREE-RULES-RECOMMENDATION-V5-20260804

- 对应需求：`REQ-THREE-RULES-RECOMMENDATION-ALIGNMENT-20260804`。
- 测试文件：[test_three_rules_recommendation_engine.py](../tests/test_three_rules_recommendation_engine.py)。
- 运行命令：

  ```powershell
  python -B tests\test_three_rules_recommendation_engine.py
  $env:PYTHONPATH = (Resolve-Path -LiteralPath '.tmp_pylibs').Path
  python -B tools\verify_8093_recommendation_engine_contract.py `
    RecommendationEngineContractTests.test_all_eight_conditions_generate_structured_actions `
    RecommendationEngineContractTests.test_combined_condition_and_safety_gate `
    RecommendationEngineContractTests.test_8767_payload_contains_ready_recommendation
  ```

- 覆盖：每条动作固定字段和四态；热制度下行/上行原文顺序；严重失常阻断增煤并
  返回停煤；高压阻断坐料；低料线净焦不猜量；碱度缺理论计算时不猜方向；任意
  主次炉况组合；字符串 `"0"` 不再误判为真。
- 结果：v5 专项 `11 tests / OK`；旧综合验证器的上述3项后端/8767子测试通过。
- 已知独立项：不带测试名运行旧综合验证器时，当前页面已经改名/重构的三个历史
  HTML结构断言失败；它们不依赖本次引擎文件，需在后续前端合同维护中单独更新。
- 边界：未部署远端8768/8093，未运行完整详情前端的跨浏览器/视口矩阵。

## TEST-8093-ASSISTANT-HEALTH-CONTRACT-20260804

- 对应运维项：`OPS-8093-ASSISTANT-HEALTH-CHECK-20260804`。
- 测试文件：[test_8093_assistant_health_contract.py](../tests/test_8093_assistant_health_contract.py)。
- 运行命令：`python -m pytest -q -p no:cacheprovider tests/test_8093_assistant_health_contract.py`。
- 覆盖：8093 导航只显示“智能助手”；`AGENTS.md` 包含分层检查链路；第一层探针不含服务/文件修改命令；远端名称补丁器使用精确计数、原子替换、HTTP 复核和 8094 哈希隔离。
- 结果：`4 passed`；三个 PowerShell 脚本通过解析检查；第一层健康探针与第二层日志尾部探针均在 220.12 成功返回只读证据。
- 远端验收：补丁后用 cache-bust 读取 8093 HTML，旧名称计数为 0、新名称计数为 1，页面 SHA-256 为 `E091DDC33FC279F4A9EA67AA45F0417A1DCC7EF83A0A72B4E520867C8BF7EBCB`；8094 页面 SHA-256 前后保持 `A13AB868BA7D71FC04450D05BD88D23506DB6BB7103C1165D5CCFD2021D193C7`。Chrome 实页截图确认底部“智能助手”可见并能进入 `#qa`，但该静态/浏览器验收不能替代一次 `/api/qa/chat` SSE 回答验收。

## TEST-8093-ASSISTANT-HEALTH-GUARD-RECOVERY-20260804

- 对应运维项：`OPS-8093-ASSISTANT-HEALTH-GUARD-FIX-20260804`。
- 测试文件：[test_8093_health_guard_recovery.py](../tests/test_8093_health_guard_recovery.py)。
- 运行命令：`python -m pytest -q -p no:cacheprovider tests/test_8093_health_guard_recovery.py tests/test_8093_assistant_health_contract.py`。
- 本地结果：`9 passed`。其中 Windows 行为测试用 Running 的 EventLog 服务和永不达到第三次的失败序列证明前两次只写 `restart_deferred`、没有 `Restart-Service`；随后健康恢复，状态计数清零。
- 静态结果：共享守卫、运行时探针、部署器、远端 SSE 包装器 PowerShell 解析通过；配置补丁器和 SSE 验收器 `py_compile` 通过。
- 远端部署：任务暂停/恢复、任务结果 0；脚本/配置为 `3/1/15/600`；8093/8768/8094/8770/11434 PID、8093/8094 页面、8768 专用健康脚本和 11434 配置均不变。
- 真实 SSE：只提交 1 次；事件为两次 `start`、多个 `delta`、`final`、`done`，首 delta `6321.2ms`、final `6583.6ms`、总计 `6583.7ms`；回答非空、会话 ID 存在、无守卫重启、模型仍仅批准的 27.8B。报告在远端 `logs/acceptance/8093_health_guard_sse_20260804_20260804_230300/assistant_sse_once.json`。

## TEST-8093-ASSISTANT-REPAIR-DOC-CONTRACT-20260804

- 对应运维项：`OPS-8093-ASSISTANT-HEALTH-GUARD-FIX-20260804`。
- 生成器：[generate_8093_assistant_repair_docx.py](../tools/generate_8093_assistant_repair_docx.py)；产物：[8093智能助手不可用原因与正式修复手册_20260804.docx](8093智能助手不可用原因与正式修复手册_20260804.docx)。
- 测试文件：[test_8093_assistant_repair_doc_contract.py](../tests/test_8093_assistant_repair_doc_contract.py)。
- 运行命令：`python -m pytest -q -p no:cacheprovider tests/test_8093_assistant_repair_doc_contract.py tests/test_8093_health_guard_recovery.py tests/test_8093_assistant_health_contract.py`。
- 预期：DOCX 可作为有效 ZIP/OpenXML 打开；正文包含确认根因、7 组历史失败、`3/1/15/600`、为什么可行、复发流程、`start → delta → final → done`、`6.5837` 秒守卫验收和 `23.8856` 秒 keyword 知识验收；`AGENTS.md` 包含 DOCX 权威入口、修复分类、keyword 现行配置与哈希漂移保护；文档不含密码、Token 或已知敏感口令。
- 2026-08-04 实际结果：上述组合测试 `13 passed`；另用项目捆绑 `python-docx 1.2.0` 重新打开产物，确认 63 个正文段落、9 个表格、2 个 section，标题与追踪编号元数据正确。
- 2026-08-05 更新结果：加入 keyword 配置、公共 Prompt/KV 说明和真实知识问答证据后，DOCX/关键词模式/Prompt-RAG/守卫/健康五组合同联跑 `25 passed`；产物已重新生成并再次用项目捆绑 `python-docx` 打开验证。

## TEST-8093-8094-PROMPT-RAG-CONTRACT-20260805

- 对应运维项：`OPS-8093-8094-PROMPT-RAG-RUNTIME-20260805`。
- 测试文件：[test_8093_8094_prompt_rag_contract.py](../tests/test_8093_8094_prompt_rag_contract.py)与[既有固定前缀顺序测试](../高炉前端数据/智能助手/tests/test_qa_latency_optimizations.py#L459-L477)。
- 运行命令：`python -m pytest -q -p no:cacheprovider tests/test_8093_8094_prompt_rag_contract.py '高炉前端数据/智能助手/tests/test_qa_latency_optimizations.py::QaLatencyOptimizationTests::test_fixed_rules_precede_all_dynamic_prompt_sections'`。
- 本地结果：`6 passed`。
- 覆盖：固定规则位于动态炉况/MCP/知识之前；知识与 MCP 默认开关；PostgreSQL keyword/vector/hybrid 能力；8093/8094 现行显式 keyword；运行探针无服务启停；文档明确 attention score、公共 KV 前缀和 RAG 意图门控。
- 远端只读验收：`probe_8093_8094_prompt_rag_runtime.ps1` 于 2026-08-05 06:54 成功；两个端口共用后端，变更前为 8093=`hybrid`、8094=`keyword`，两端口强制 keyword 搜索均返回 2 条证据。该历史差异已由后续关键词模式部署消除，见下一测试项。

## TEST-8093-KNOWLEDGE-KEYWORD-MODE-20260805

- 对应运维项：`OPS-8093-KNOWLEDGE-KEYWORD-MODE-20260805`。
- 测试文件：[test_8093_keyword_knowledge_mode.py](../tests/test_8093_keyword_knowledge_mode.py)；程序包括[配置补丁器](../tools/patch_8093_keyword_knowledge_mode.py)、[受控部署器](../tools/remote_guarded_deploy_8093_keyword_knowledge_mode.ps1)、[SSE 验收器](../tools/verify_8093_assistant_sse_once.py)和[知识验收包装器](../tools/remote_verify_8093_keyword_knowledge_sse_once.ps1)。
- 本地结果：关键词配置/部署/SSE 相关组合 `16 passed`；Python 编译和 PowerShell 解析通过。覆盖空值/`hybrid` 迁移、幂等、错误服务/端口/守卫/`vector` 拒绝、部署隔离/回滚、默认搜索模式、实际进程环境和唯一 POST 约束。
- 远端部署：`2026-08-05 07:25:21` 完成；配置 SHA-256 为 `8A24C83DF93008DD8E358682558E8755442D87052A09FB24F39778F2EAF51FDE`，备份 `logs/deploy_backups/8093_knowledge_keyword_20260805_072445`。只更换 8093 PID；8768/8094/8770/11434 PID、页面与受保护哈希未变化，健康任务结果 0、状态清零、仅批准 27.8B 驻留。
- 配置验收：实际监听进程的 `BF_QA_KNOWLEDGE_SEARCH_MODE=keyword`；不带 mode 的默认知识搜索返回 `search_mode=keyword`、`enabled=true` 和 2 条证据。
- 真实 SSE：`2026-08-05 08:44:59` 只发送 1 个 POST；准备态知识检索启用、未跳过、意图 `parameter_optimization`、MCP 工具调用关闭；事件完整，首 delta `11709.7ms`、final `23885.4ms`、总计 `23885.6ms`，期间无守卫重启或受保护状态变化。报告 `logs/acceptance/8093_keyword_knowledge_20260805_20260805_084403/assistant_keyword_knowledge_sse_once.json`。

## TEST-8093-CORE-PSPACE-REALTIME-20260804

- 合同测试：`python -m unittest tests.test_8093_core_metrics_pspace_live -v`，2026-08-05 加入系统时钟合同后 7 项通过。
- 静态检查：补丁器与 Python 验收器 `py_compile` 通过；实时 JS 与 Node 验收器 `node --check` 通过；守卫部署器与只读审计器 PowerShell 解析通过。
- 生产实时矩阵：Chrome/Chromium 9 视口全部通过；Firefox、WebKit 各 4 个代表视口通过；Edge `1366×768` 冒烟通过。每个视口均检查 28 个唯一 ID、`pspace_realtime`、时间、年龄、质量、值、横向溢出及页面/控制台错误。
- 生产降级矩阵：显式 `core_pspace_disabled=1&ws_port=8768`，Chrome 4 个代表视口全部通过；28/28 都有 `postgres_minute` 值和时间戳，且逐行标题与全局横幅包含“已降级为分钟镜像”。
- 部署与哈希：[专项记录](8093_核心指标pSpace秒级实时与分钟镜像降级_20260804.md)。
- 系统时钟增量验收：守卫部署结果包含 `system_clock_marker_served=true`；Edge `1366×768` 为通过，时钟与浏览器当前时间差 `1.231s`、分钟数据 `11:03`、pSpace `28/28`、横向溢出 0、错误 0。Chrome `1920×1080` 与 `1366×768` 时钟差分别为 `1.084s`、`1.380s`。
- 已知运行风险：连续重载完整页面时，8093 静态代理曾对 `echarts.min.js`、`OrbitControls.js` 和趋势 API 返回 `ERR_EMPTY_RESPONSE`，导致窄屏矩阵无法完成；单独 HTTP 随后均为 200。该项没有被记为时钟回归通过，见 `ERR-8093-STATIC-ASSET-EMPTY-RESPONSE-20260805`。

## TEST-8093-MULTI-MCP-HOST-20260805

- 对应需求：`REQ-8093-MULTI-MCP-HOST-20260805`。
- 测试文件：[test_mcp_multi_server_host.py](../高炉前端数据/智能助手/tests/test_mcp_multi_server_host.py)、[test_imes_heat_summary_tools.py](../高炉前端数据/智能助手/tests/test_imes_heat_summary_tools.py)，并联跑既有对话状态、延迟和工具策略测试。
- 命令：

  ```powershell
  python -m pytest -p no:cacheprovider `
    高炉前端数据/智能助手/tests/test_mcp_multi_server_host.py `
    高炉前端数据/智能助手/tests/test_imes_heat_summary_tools.py `
    高炉前端数据/智能助手/tests/test_mcp_conversation_context.py `
    高炉前端数据/智能助手/tests/test_mcp_latency_optimization.py `
    高炉前端数据/智能助手/tests/test_mcp_agent_orchestration.py -q
  ```

- 结果：`38 passed`；另有既有问答延迟测试 `28 passed, 1 deselected`。被暂时 deselect 的绘图静态目录用例只因默认 Python 3.13 缺少既有 `mcp` SDK，扩大联跑时在模块导入阶段失败，不是本次行为断言失败。
- 真实 SDK 服务发现：使用项目现有 Python 3.11 环境运行 `tools/test_mcp_multi_server_discovery.py`；IMES 问题选择 1 服务/14 工具，GL02 问题选择 1 服务/18 工具，跨源问题选择 2 服务/32 工具；三次退出码均为 0。
- 安全断言：IMES Server 原生有 15 个工具，Host 可见 14 个，差异项固定为 `query_imes_readonly_sql`。
- 边界：本记录所覆盖的本地单元测试不直接调用真实 MES；真实 MES/8093 SSE 已由受控部署交接记录单独验收，见 [交接记录](handoffs/2026-08-05-8093-multi-mcp-deploy.md)。
## TEST-IMES-LOCAL-MULTI-MCP-RELAY-20260805

- 对应需求：[REQ-IMES-LOCAL-MULTI-MCP-RELAY-20260805](requirements_traceability.md#req-imes-local-multi-mcp-relay-20260805)。
- 覆盖文件：[test_imes_web_launcher.py](../tests/test_imes_web_launcher.py)、
  [test_imes_web_mcp_server.py](../tests/test_imes_web_mcp_server.py)、
  [test_mcp_multi_server_host.py](../高炉前端数据/智能助手/tests/test_mcp_multi_server_host.py)、
  [test_mcp_multi_server_discovery.py](../tools/test_mcp_multi_server_discovery.py)。
- 已执行：项目 Python 3.11 环境 `py_compile`；relay/IMES 原有 `23 tests / OK`；
  启动器、Web MCP、Host 注册表手动契约检查均通过；三服务 stdio `tools/list` 全部成功，
  `--all` 发现结果 `ok=true`、`tool_count=35`。路由口语“Web网页状态”在路由扩展后应只选
  `imes-web-readonly`（3 工具）。
- 备注：默认 Python 3.13 的 pytest 收集会因现有 MCP SDK/pydantic 二进制环境不匹配而失败，
  本次以项目 Python 3.11 的编译、unittest 和直接契约调用为准，未把该环境问题误报为行为失败。

## TEST-8093-ASSISTANT-AUTO-RECOVERY-20260805

- 对应需求：`REQ-8093-ASSISTANT-AUTO-RECOVERY-20260805`；测试文件：[test_8093_assistant_auto_recovery.py](../tests/test_8093_assistant_auto_recovery.py)。
- 组合命令：`python -m pytest -q -p no:cacheprovider tests/test_8093_assistant_auto_recovery.py tests/test_8093_keyword_knowledge_mode.py tests/test_8093_health_guard_recovery.py`。
- 结果：`22 passed`。
- 包覆盖：package ID/manifest 可重复、所有 `.ps1` 部署字节带 UTF-8 BOM、远端命令只使用短 `powershell.exe ... -File`，不存在 `-EncodedCommand` 或内联 ScriptBlock。
- 分类覆盖：现行 healthy；已知旧配置/hybrid 直接映射 keyword；守卫与 keyword 双漂移按固定顺序；未知配置哈希拒绝修复。
- PowerShell 5.1：两项测试直接启动系统 `powershell.exe -File`，向远端诊断器和 keyword 部署器输入包含 `"8093"/"8768"/"11434"` 数字字符串键的 JSON，断言输出是带 `port` 字段的数组。测试副本使用与远端 package 相同的 UTF-8 BOM，能提前发现中文路径和数字属性序列化问题。
- 流水线覆盖：fake remote 精确断言 `诊断 -> keyword 部署 -> 再诊断 -> SSE`，且 `remote_verify_...sse_once.ps1` 只调用一次。
- 真实预置：包 `20260805_v1_22e4eb675eee` 的 8 个 payload 和 manifest 已在远端逐文件 SHA-256 复核；后续 diagnose 报告 `reused=true`。
- 真实诊断：约 67 秒完成，分类 healthy，远端合并采集 `17.333s`。
- 真实 recover：前后 healthy、无部署，服务阶段 `184.618s`；唯一 SSE `request_count=1`、总计 `22185.9ms`、keyword 证据 2 条，所有隔离/守卫/模型检查通过。报告：[20260805_110327_recover.json](../logs/assistant_8093_auto_recovery/20260805_110327_recover.json)。

## TEST-IMES-HEAT-ACCOUNT-AND-CONTEXT-20260805

- 对应需求：`REQ-IMES-HEAT-ACCOUNT-AND-CONTEXT-20260805`。
- 被测代码：[imes_relay_mcp_server.py](../高炉前端数据/智能助手/mcp/imes_relay_mcp_server.py)；[炉次摘要回归](../高炉前端数据/智能助手/tests/test_imes_heat_summary_tools.py)；[账号与化验工具测试](../tests/test_imes_relay_mcp_server.py)。
- 合同覆盖：本机 `IMES_DB_USER/IMES_DB_PASSWORD` 同时覆盖两个 profile；化验查询使用可配置但默认 `operations` 的 profile；精确炉次使用官方 `meltno`；当前/上一炉不再让 `closetime IS NULL` 的历史行抢占，活动状态有 72 小时新鲜度上限。
- 验证命令：

  ```powershell
  $py='C:\Users\hmw20\.conda\envs\torch_cuda128_whm\python.exe'
  & $py -X utf8 -m py_compile `
    .\高炉前端数据\智能助手\mcp\imes_relay_mcp_server.py `
    .\高炉前端数据\智能助手\tests\test_imes_heat_summary_tools.py `
    .\tests\test_imes_relay_mcp_server.py
  & $py -X utf8 -m unittest tests.test_imes_relay_mcp_server -v
  ```

- 结果：`21 tests / OK`；炉次摘要四项回归通过；MCP discovery 可见 `imes__query_hot_metal_chemistry_by_heat`。真实远端证据为 `2#20260805-065` 三个 Si 样本 `0.20/0.25/0.24`、均值 `0.23%`，不在本项测试中重复写入或修改生产数据库。
- 环境说明：默认 Python 3.13 的 pytest 收集受既有 MCP SDK/pydantic 二进制环境影响，未把该环境失败误报为代码行为失败；以项目 Python 3.11 编译、unittest 和直接契约调用为准。

## TEST-OPT-MULTI-CONDITION-LLM-REVIEW-20260805

- 对应需求：[REQ-OPT-MULTI-CONDITION-LLM-REVIEW-20260805](requirements_traceability.md#req-opt-multi-condition-llm-review-20260805)。
- Python 编译：适配器、8767 bridge、模型复核模块、代理服务和浏览器夹具服务均通过 `python -m py_compile`。
- 新合同：`python tests\test_multi_condition_recommendation_and_model_review.py`，结果 `8 tests / OK`。
- 引擎回归：`python tests\test_three_rules_recommendation_engine.py`，结果 `11 tests / OK`。
- 综合静态合同：为已有 `psycopg` 测试依赖加入本机 `.tmp_pylibs` 后运行 `tools\verify_8093_recommendation_engine_contract.py`，结果 `8 tests / OK`。
- 前端语法：`node tools\check_frontend_babel_syntax.cjs`，结果 `Babel syntax OK: 1 script`；500KB deoptimised 是既有浏览器 Babel 架构提示，不是 JSX 编译失败。
- Chromium 浏览器：隔离夹具下实际出现 8 张炉况卡；切到 `edge` 后 `data-selected-condition=edge`、详情标题/曲线上下文变化、4 条动作分别显示四态、模型状态为 `completed`。展开阻断动作确认十个审计字段全部存在且阻断原因可见。
- 视口矩阵：`1280×720`、`1366×768`、`1440×900`、`1546×864`、`1920×1080`、`1024×768`、`768×1024`、`390×844`、`375×667` 均为 8 卡、导航可见、页面/主区/建议页横向溢出 0；矩阵按 4/2/1 列响应，详情页内部纵向滚动。Firefox/WebKit 本轮运行环境未提供对应浏览器连接，未宣称通过。
- 浏览器日志：无本功能产生的 TypeError/未捕获异常；仍存在页面既有的 in-browser Babel transformer 警告及超过 500KB 的代码生成降级日志，需后续构建预编译专项消除。

## TEST-FOREMAN-TREND-STANDALONE-PREVIEW-20260805

- 对应需求：[REQ-FOREMAN-TREND-STANDALONE-PREVIEW-20260805](requirements_traceability.md#req-foreman-trend-standalone-preview-20260805)。
- 静态合同：`python -m unittest tests.test_foreman_trend_preview -v`，结果 `4 tests / OK`；新页面 JS 与两个 Node 验收器均 `node --check` 通过。
- 单页浏览器：`node tools/verify_foreman_trend_preview.cjs`，Edge/Chromium `1280×1024`；49 个指标值、12 条主曲线、5 条下方曲线、缩放和图例动作、6 个导航链接、横纵溢出 0、页面/控制台错误 0。
- 跨浏览器矩阵：`node tools/verify_foreman_trend_viewports.cjs`，Edge/Chromium 9 个固定视口，Firefox/WebKit 各 4 个代表视口，共 `17 checks / PASS`。桌面视口无溢出；1024/768/390/375 宽度保留 1180px 工控画布并验证水平滚动、短视口验证底部导航可达。
- 截图/报告：[1280×1024 对比图](../logs/foreman_trend_preview_20260805/foreman_trend_1280x1024.png)、[单页报告](../logs/foreman_trend_preview_20260805/report.json)、[矩阵报告](../logs/foreman_trend_preview_20260805/viewport_matrix/report.json)。
- 220.12 发布/浏览器冒烟：`$env:NODE_PATH='C:\Users\hmw20\.cache\codex-runtimes\codex-primary-runtime\dependencies\node\node_modules'; & 'C:\Users\hmw20\.cache\codex-runtimes\codex-primary-runtime\dependencies\node\bin\node.exe' .\tools\verify_foreman_trend_remote_8093.cjs`。目标为 `8093/foreman_trend_preview.html?ws_port=8768`；确认实时连接、数据时间、真实值/缺失值覆盖、12+5 曲线、无横向溢出及页面/控制台错误为 0。2026-08-05 结果为 PASS，报告为 [remote_8093_live_report.json](../logs/foreman_trend_preview_20260805/remote_8093_live_report.json)。
- 发布隔离：2026-08-05 已通过 [受控部署器](../tools/remote_deploy_8093_foreman_trend_preview.ps1) 更新 220.12 的独立静态资源；未重启任何服务，8093 PID `6892` 与 8768 PID `15824` 保持不变，未写生产数据库，旧正式趋势页没有被修改。
## TEST-22012-DIRECT-SOURCE-RELAYS-20260805

| 项目 | 内容 |
| --- | --- |
| 对应需求 | `OPS-22012-DIRECT-SOURCE-RELAYS-20260805` |
| 单元测试 | [tests/test_patch_22012_nginx_imes_web.py](../tests/test_patch_22012_nginx_imes_web.py) |
| 部署器 | [tools/remote_deploy_22012_direct_source_relays.ps1](../tools/remote_deploy_22012_direct_source_relays.ps1) |
| 运行探针 | [tools/remote_probe_22012_direct_relays.ps1](../tools/remote_probe_22012_direct_relays.ps1) |

```powershell
python -m pytest -q tests\test_patch_22012_nginx_imes_web.py
Invoke-WebRequest http://10.30.220.12:18080/imes.web/
Test-NetConnection 10.30.220.12 -Port 15433
Test-NetConnection 10.30.220.12 -Port 18889
```

2026-08-05 结果：补丁测试 `3 passed`；Web 为 HTTP 200、8593 字节且包含 IMES
标记。用户提交验证码后，代理日志确认登录、桌面、主页面及炉次化验等真实业务请求
均返回 200。Vastbase 经 15433 完成认证、`BEGIN READ ONLY`、服务端身份核验并回滚；
pSpace 经 18889 使用现有 SDK/业务账号读取真实静压力点，质量 `Good`。8093/8768/
8094/8770 的部署前后 PID 完全一致。

## TEST-8093-PSPACE-CONNECTION-AUDIT-20260805

- 对应需求：[OPS-8093-PSPACE-CONNECTION-AUDIT-20260805](requirements_traceability.md#ops-8093-pspace-connection-audit-20260805)。
- 本机路径证据：aTrust进程/服务存在，VNIC断开且系统路由无 `10.22/10.30`；PowerShell直连失败被记录为普通本地路径不可用，不作为生产服务失败结论。
- 浏览器端到端：已认证aTrust“高炉模型”应用中的8093总览显示 `pSpace秒级实时 28/28`；第一次状态为 `20:58:57`，等待7秒后为 `20:59:03`。
- 行级证据：当前分页14项均具有 `pSpace秒级实时` title，抽样数据时间 `20:59:10`、年龄 `8秒`、质量“良好”；没有“已降级为分钟镜像”。
- 日志证据：过滤8770/pspace/websocket/socket错误后没有页面业务错误；仅见aTrust Chrome扩展自己的 `content_main.js` 错误，已与生产页面分离记录。
- 安全边界：本测试只读；未启停8093/8770/8768/8094，未访问写接口，未修改数据库或243。

## TEST-22012-IMES-MCP-SYNC-20260805

- 对应需求：[REQ-22012-IMES-MCP-SYNC-20260805](requirements_traceability.md#req-22012-imes-mcp-sync-20260805)。
- 合同测试：部署范围与回滚、四服务生产注册表、315 项目录、72 小时当前炉次门禁、服务配置幂等且不写秘密值、轻量运行探针、SSE 强制/自动路由模式。
- 本地组合结果：`46 passed`。组合覆盖 `tests/test_22012_imes_mcp_sync_deploy.py`、`tests/test_verify_8093_mcp_mes_sse_once.py`、MES relay/模板和多服务 host 回归。
- 真实 MES 自动路由：HTTP/SSE 200，调用 `imes-readonly`，返回当前 `2#20260805-072`、上一炉 `071`、3 个 Si 试样及 `0.273%` 平均值，总耗时约 `6.69s`。
- 真实炉身温度自动路由：HTTP/SSE 200，事件包含 `tool_start/tool_result`，返回 `T_body_L13_C=89.37`、`2026-08-05 22:06:00`、质量 `Good`，总耗时约 `22.22s`。
- 部署验收：8093 服务/守卫恢复且 HTTP 200；8768/8094/8770 PID 不变；七个生产文件哈希与本机发布包一致。完整证据见[交接记录](handoffs/2026-08-05-22012-imes-mcp-production-sync.md)。

## TEST-8093-CROSS-DATABASE-MCP-20260805

- 审计入口：[audit_8093_cross_database_mcp.py](../tools/audit_8093_cross_database_mcp.py)，以自动路由模式发起一次真实 SSE，并压缩输出 `server_id/tool/route/result/source/latency/answer`。
- 覆盖：6类口语策略、7次有效SSE（另有1次响应头前断开并单列为连接抖动）。包括典型“上一炉Si+当前传感器”、炉次化验+炉身/顶压证据审查、两边交叉核对、完整变量名短回答和高度口语化查询。
- 结论：至少一次轨迹同时出现 `imes-readonly` 与 `gl02-data`，证明跨库工具层可用；但没有一个复杂口语同时满足“自动、两库、字段完整、工具不重复、最终回答完整”全部条件，因此端到端判定为未通过。
- 单元合同：[test_8093_cross_database_mcp_audit.py](../tests/test_8093_cross_database_mcp_audit.py) 验证生产状态 URL 和工具证据压缩结构。完整结果见[专项记录](handoffs/2026-08-05-8093-cross-database-mcp-audit.md)。

## TEST-PSPACE-MINUTE-CANONICAL-AVERAGE-20260805

- 对应需求：[REQ-PSPACE-MINUTE-CANONICAL-AVERAGE-20260805](requirements_traceability.md#req-pspace-minute-canonical-average-20260805)。
- 合同测试：`python -m unittest tests.test_pspace_minute_average_semantics -v`，6项通过；覆盖Good/192质量、坏值排除但保留raw审计、平均值、60秒闭窗水位、DDL/配置、processed回填标签隔离和项目根共享锁。
- pSpace不写库试算：133点中124点有短窗数据、9点明确“时间范围内无数据”、硬错误0、1,165条raw全部`Good(RAW)`；最新分钟为`window_complete=false`。
- 生产数据库：1,159行`PS_RAW_AVERAGE/valid_raw_mean_v1`与`raw_5s_values`重算，差异行0、样本数差异0，最大浮点误差约`3.64e-12`；最近20分钟raw为4,398行/133点。
- 运行：最近6次完成运行均`tags_ok=133/tags_error=0`；单包装器；8093/8094/8768/8770 PID未变。
- 流：8770返回`pspace_realtime`、133/133数值和质量；8768按设计返回`postgresql_realtime`；8093页面与实时资源HTTP 200且资源使用8770。

## TEST-8093-CROSS-SOURCE-MCP-20260806

- 对应需求：[REQ-8093-CROSS-SOURCE-MCP-20260805](requirements_traceability.md#req-8093-cross-source-mcp-20260805)。
- 专项测试：`tests/test_cross_source_mcp.py` 当前 `51 passed`，无 `pass # placeholder`；MCP Host、IMES 同步、会话上下文和守护回归组合 `108 passed`，相关 Python `py_compile` 通过。
- 真实验收：自动路由同时调用 `imes-readonly` 与 `gl02-data` 的 Si + 当前顶压/冷风压力/富氧率；精确炉次 `2#20260805-065` 同时调用 IMES 化验、`gl02-extended` 炉身温度能力和 `gl02-data` 顶压；趋势图与 7–12 层 A–F 温度矩阵均返回 `/data/mcp_charts/*.png`。
- 数据边界：无最新化验或炉身点位时，回答明确列出缺失，不把缺失当作零或编造值；当前炉次/上一炉 Si 查询返回正式 `meltno` 和 `NO_SI_SAMPLES`。
- 部署：最终备份 `logs/deploy_backups/8093_multi_mcp_20260806_012857`；`BFV4PreviewProxy8093` 仅更换 PID，健康任务恢复且结果为0；8768/8094/8770 PID 保持 `4340/14416/12956`。
# 8093/8094 建议引擎同步（2026-08-06）

- `python -m pytest -q -p no:cacheprovider tests\test_8093_8094_recommendation_sync.py tests\test_8094_multi_condition_deploy.py tests\test_three_rules_recommendation_engine.py tests\test_multi_condition_recommendation_and_model_review.py`
- `PYTHONPATH=.tmp_pylibs python tools\verify_8093_recommendation_engine_contract.py`
- `node tools\check_frontend_babel_syntax.cjs 高炉前端数据\frontend_dashboard_v3.server.html`
- 生产浏览器：`tools/probe_remote_recommendation_page.cjs` 与 `tools/verify_remote_recommendation_pages.cjs`。
# 建议页视觉结构核查（2026-08-06）

- `node tools/probe_remote_recommendation_layout.cjs <8093或8094 URL> 1366 768`
- 验收目标：驾驶舱顶部高度大于 0；驾驶舱、图表和审计区边界不重叠；页面内部可滚动到全部内容。
- 2026-08-06 修复前证据：1366×768 下 `.bf-engine-cockpit .opt-cockpit-top` 高度为 0，确认视觉回归。

## TEST-OPT-VISUAL-COCKPIT-RESTORE-20260806

- 对应需求：[REQ-OPT-VISUAL-COCKPIT-RESTORE-20260806](requirements_traceability.md#req-opt-visual-cockpit-restore-20260806)。
- 静态合同：[test_recommendation_visual_workbench.py](../tests/test_recommendation_visual_workbench.py)验证活动入口、8套4项主证据、精确19项变量、4种动作状态、9类审计字段、延迟挂载曲线、模型自动/手动策略和8094补丁终点。
- 部署合同：[test_recommendation_visual_frontend_deploy.py](../tests/test_recommendation_visual_frontend_deploy.py)验证只含前端的哈希包、先8094后8093、无服务启停、PID保护和失败回滚。
- 语法：`node tools\check_frontend_babel_syntax.cjs 高炉前端数据\frontend_dashboard_v3.server.html`。
- 浏览器：`tools/verify_remote_recommendation_pages.cjs <URL>`；Chromium覆盖9个固定视口，Firefox/WebKit各4个代表视口。验收19个唯一变量、4项主证据、抽屉审计字段、图表正高度、无横向溢出和页面错误为0。
- 2026-08-06最终结果：相关合同 `36 passed`；8093源页与远端8094哈希一致补丁页的跨浏览器矩阵共 `34 checks / PASS`（Chromium每页9视口、Firefox/WebKit每页各4代表视口）；报告为 [8093_8094_recommendation_visual_20260806.json](../logs/acceptance/8093_8094_recommendation_visual_20260806.json)。远端服务器本机复核8093/8094 HTTP 200，8093/8094/8768/8770/11434均监听；页面SHA-256分别为 `4C552CBA92D70379E3CBFD6447195F6B1105403009D3C6B39512BF5EF5D31262` 和 `876C14DF1F5620D3333C0F4AAC6D202FACE508E5C4C82E707F4E4D939A187C69`。

## TEST-8093-AUTONOMOUS-HEAT-CHEMISTRY-MCP-20260806

- 工具测试：`test_imes_heat_summary_tools.py` 覆盖成分中英文归一、样本/汇总、缺失不当零、未知元素拒绝和MCP注册；`test_imes_relay_mcp_server.py` 覆盖语义推荐工具。
- Host测试：`test_mcp_multi_server_host.py` 启动真实 IMES MCP stdio，会话确认暴露名为 `imes__query_heat_chemistry`，Schema包含必填 `heat_reference` 和可选 `components` 数组。
- 编排测试：`test_mcp_agent_orchestration.py` 覆盖短炉号进入模型规划、实时注册Schema裁剪、SQL禁止提示和SSE安全工具调用字段。
- 真实模型只规划测试：注册表共16个IMES只读工具，能力裁剪后提供2个相关Schema；27B实际输出 `imes__query_heat_chemistry`，参数为正式炉次号、`[C,Si,Mn,P,S]` 和 `include_samples=true`，没有生成文本答案或SQL。
- 复现：`PYTHONPATH=.tmp_pylibs python tools/probe_model_mcp_tool_selection.py --question "请查询2#20260805-065炉次的C、Si、Mn、P、S，并列出每个试样。"`。
- 本地回归：相关IMES、Host、编排、跨源与延迟测试合计 `155 passed`，Python `py_compile` 通过。
- 生产验收：模型实际选择 `imes-readonly/imes__query_heat_chemistry`，单次参数为正式炉次号、5元素和试样明细；结果 `ok=true`、3个试样、无SQL、无重复工具，问答前后运行状态均正常。完整证据见[交接记录](handoffs/2026-08-06-8093-arbitrary-heat-chemistry-mcp.md)。

## TEST-8093-ASSISTANT-FETCH-RESILIENCE-20260806

- 对应需求：[REQ-8093-ASSISTANT-FETCH-RESILIENCE-20260806](requirements_traceability.md#req-8093-assistant-fetch-resilience-20260806)。
- `tests/test_8093_assistant_fetch_resilience.py`：验证页面标记、中文错误分类、只读 GET 最多 3 次与 1.5/3 秒退避、问答 POST/SSE 不自动重发、补丁幂等和热部署器全局互斥/PID保护。
- `tests/test_8093_assistant_auto_recovery.py`：验证 service_recover 分类、已知/未知哈希、页面热修复、PowerShell 5.1 数字键、监听快照、SSH 重试、守卫恢复、启动退避与唯一 SSE 合同。
- 组合命令：`python -m pytest tests\test_8093_assistant_fetch_resilience.py tests\test_8093_assistant_auto_recovery.py tests\test_8093_assistant_pg_pool_reuse.py tests\test_8093_assistant_health_contract.py tests\test_8093_assistant_repair_doc_contract.py -q`。
- 结果：`41 passed`；相关 Python `py_compile` 通过。pytest 缓存目录写入警告不影响测试结论。
- 生产验收：`logs/assistant_8093_auto_recovery/20260806_105139_recover.json` 记录 `request_count=1`、完整事件序列、keyword 证据 2 条、答案非空、守卫无重启和全部受保护状态不变。
- 最新预置合同：`logs/assistant_8093_auto_recovery/20260806_110722_prestage.json` 记录包 `20260805_v2_72eff4ce55d3` 的 13 个 payload 与 manifest 远端 SHA-256 全部一致。

## TEST-8093-8094-DIAGNOSIS-CORE-19-TRENDS-20260806

- 合同命令：`python -m pytest tests\test_diagnosis_ai_analysis.py tests\test_diagnosis_review_api.py tests\test_diagnosis_review_contract.py tests\test_multi_condition_recommendation_and_model_review.py -q`；结果 `44 passed`。
- 本地浏览器：Chromium 9个规定视口、Firefox 4个、WebKit 4个，共 `17/17`；验证主证据优先、19个唯一变量、展开、点击曲线、无横向溢出及功能控制台错误为0。
- 远端轻量接口：`python tools\verify_diagnosis_core19_remote.py --lightweight --base-url http://10.30.220.12:8093 --base-url http://10.30.220.12:8094`。
- 8093生产验收：`diagnosis_core_evidence.v1`、精确19项ID、19项均有60分钟序列、HTTP 200、守卫恢复、8768 PID不变；首次部署因旧验收仍等待完整模型而在资源阶段自动回滚，修正为轻量接口硬门槛后成功且 `rollback_applied=false`。

## TEST-IMES-MATERIAL-FUEL-AND-DB-MODULE-SYNC-20260806

- 单元/语义组合：`python -m pytest -q -p no:cacheprovider tests/test_audit_imes_material_fuel_metrics.py tests/test_pspace_minute_average_semantics.py tests/test_foreman_points_and_coal_storage.py`，结果 `14 passed`。
- 当前目录验证：`python tools/verify_foreman_local_point_catalog.py --root 数据库同步和存取`；2026-08-07 增加 `CO_top`、`CO2_top`、`H2_top` 后结果为153行、151物理、2派生、19确认项，DDL/同步钩子/喷煤模块/Python语法全部通过。
- 模块同步：`tools/sync_v4_db_module_to_current.ps1 -WhatIfMode` 预演43文件；正式执行后逐文件SHA-256一致，清单写入 `数据库同步和存取/module_sync_manifest.json`。
- Vastbase：只读事务成功；目标表和全局元数据均未发现料速/燃料比直接字段。
- 220.12 IMES镜像：6个主要数据集更新到14:53–14:59；字段和值搜索无直接命中；批次明细确认存在批次时间、矿批合计、焦批合计等派生基础量。
- 生产 pSpace：243:8889可达；主任务/Watchdog/旧任务状态符合单写入者合同；分钟最新15:01、148点、约3.141分钟延迟；5秒最新15:01:58、148点；新增15物理点全部有15:02实际值；本小时喷煤派生视图通过。
- 配置一致性：220.12主目录、守卫镜像目录与当前项目的点位清单SHA-256均为`E13821CACCC5BC86826A23AA6976F484D3A5ED91063DEBE00FA311A48C6C0F62`。

## TEST-IMES-REPORT-PERSISTENCE-20260808

- 解析器合同：`pytest -q tests/test_imes_report_client.py`，结果 `2 passed`；验证 Raqsoft HTML 网格的全部单元格、D列批数、燃料比公式重算、NaN归一化和稳定行键。
- 220.12 代理：作业日志首段/查询段均 HTTP 200；`18084` 代理资源可加载，8093/8768/8094/8770 PID 未变化。
- 220.12 数据库：`bf_imes.v_bf2_operation_log_report` 共4320行、180个业务日（2026-02-09至2026-08-08），`report_fuel_ratio` 非空4113行，`material_rate` 非空0行，重复 `(workdate, report_row_number)` 0；活动 V4 MCP 的 `query_bf2_operation_log_report` 工具列表和 2026-08-08 直接调用均通过（19 个工具、返回2行）。
- 计划任务：`IMESBF2OperationLogReport5m` 已注册；2026-08-08 最近一次 `LastTaskResult=0`，日志当天读取/写入24行。

## TEST-8093-8094-DIAGNOSIS-ASSET-PARITY-DEPLOY-20260806

- 对应需求：`OPS-DIAG-RULES-ONE-CLICK-DEPLOY-20260806`、`Q-8093-8094-DIAGNOSIS-ASSET-PARITY-20260806`。
- 本机门禁：`python .\tools\deploy_diag_rules.py`，结果 `47 passed`、dry-run通过；正式命令为 `python .\tools\deploy_diag_rules.py --apply --verify fast`。
- 正式收据：[diag_rules_20260806-2300-4b75678a08.json](../logs/deploy_diag_rules/diag_rules_20260806-2300-4b75678a08.json)，`guardPaused=true`、`guardRestored=true`、`rollbackApplied=false`，9个业务文件原子上传。
- 远端运行态：8093/8094页面HTTP 200；两页均命中 `diag-20260806-2300-4b75678a08`，评分和复核脚本均为200、均含 `bootWhenBodyReady`；`/api/diagnosis-review-context` 返回 `enabled=true`、`can_submit=true`、`login_required=false`。
- 保护边界：8093/8094按目标更新服务；8768 PID `4288`、8770 PID `6848`、11434 PID `12456`前后不变。浏览器工具在本机初始化阶段因ACL运行环境错误退出，未将其计入通过项；远端HTTP/资源/API/PID验收通过。

## TEST-MCP-IMES-HEAT-SI-SAMPLES-20260807

| 项目 | 内容 |
|---|---|
| 对应需求 | `REQ-MCP-IMES-HEAT-SI-SAMPLES-20260807` |
| 工具测试 | [test_imes_heat_summary_tools.py](../高炉前端数据/智能助手/tests/test_imes_heat_summary_tools.py) |
| 路由测试 | [test_mcp_multi_server_host.py](../高炉前端数据/智能助手/tests/test_mcp_multi_server_host.py) |
| 命令 | `python -m pytest 高炉前端数据\智能助手\tests\test_imes_heat_summary_tools.py 高炉前端数据\智能助手\tests\test_mcp_multi_server_host.py -q` |
| 预期 | 当前炉次阶段性平均、开口时间、逐罐试样、时间回退标签、昨天钟点解析、多炉次重叠、鸬鹚路由和确定性回答全部通过 |

2026-08-07 本地结果：`29 passed in 1.93s`；三个相关 Python 文件 `py_compile` 通过。

| REQ-8093-DIAGNOSIS-FOREMAN-KNOWLEDGE-ADVICE-20260807 | 64主题来源限定、正文不直显、详情链接、19传感器逐项偏离、四类候选调节方向 | python -m pytest tests/test_diagnosis_ai_analysis.py tests/test_8093_assistant_pg_pool_reuse.py -q --basetemp D:\文件\冀南钢铁运行中第二版本\.tmp_pytest_diagnosis |
## TEST-TREND-19-LANE-MERGE-20260807

- 对应需求：[REQ-TREND-19-LANE-MERGE-20260807](requirements_traceability.md#req-trend-19-lane-merge-20260807)。
- 静态合同：`python -m pytest -q -p no:cacheprovider tests\test_front2_trend_19_lane_merge.py`。
- Babel语法：`node tools\check_frontend_babel_syntax.cjs 高炉前端数据\front2\frontend_dashboard_front2.server.html`。
- 跨浏览器：`python tools\verify_front2_trend_19_lane.py`；Chromium覆盖9个固定视口，Firefox与WebKit各覆盖4个代表视口，共17项。
- 硬门槛：左侧单面板、19个唯一目标、19条历史线、19条预测虚线、原始值提示、图例显隐、右侧3面板不变、无横向溢出且页面/控制台错误为0。
- 2026-08-07结果：静态合同`4 passed`、Babel语法通过、跨浏览器矩阵`17/17 PASS`；报告为[front2_trend_19_lane_20260807.json](../logs/acceptance/front2_trend_19_lane_20260807.json)，截图为[front2_trend_19_lane_1366x768.png](../logs/acceptance/front2_trend_19_lane_20260807/front2_trend_19_lane_1366x768.png)。

## TEST-ABC33-RULE-CONTRACT-20260807

- 对应需求：[REQ-ABC33-FURNACE-RULES-20260807](requirements_traceability.md#req-abc33-furnace-rules-20260807)。
- 命令：`D:\ProgramData\anaconda3\python.exe -m pytest -q tests/test_abc_rule_engine.py`。
- 覆盖：A9/B13/C11完整性、配置校验、33项计算、缺数 `needs_data`、B类颜色分带存在、C类红色安全事件，以及生产白名单不含公式/权重/阈值/贡献。
- 当前结果：`11 passed`；规则模块、调度器、WebSocket桥和8092代理 `py_compile` 通过。
# ABC33决策中心常驻布局验收（2026-08-08）

- 自动测试：`python -m pytest tests/test_abc_production_ui.py tests/test_abc_rule_engine.py -q`，预期14项通过。
- 浏览器夹具：`tests/fixtures/abc33_decision_center_fixture.html`，验证全部33个详情按钮、详情抽屉及缺数分数门禁。
- 视口：Chromium内核覆盖1280×720、1366×768、1440×900、1546×864、1920×1080、1024×768、768×1024、390×844、375×667；横向溢出必须为0。
- 远端：8094主页必须包含版本 `abc33-20260808-r3-decision-center`，ABC资源必须包含标题“AI决策中心 · 33项炉况研判”。

## TEST-BODY-TEMP-INFRARED-REPLAY-20260808

- 合同测试：`pytest -q .\tests\test_soft_zone_replay_server.py`，结果`6 passed`。
- 本地浏览器矩阵：设置捆绑Playwright的`NODE_PATH`后运行`node tools\verify_soft_zone_replay_ui.cjs`；Edge/Chromium 9个固定视口，Firefox/WebKit各4个代表视口，共17项通过。
- 生产冒烟：设置`SOFT_ZONE_REPLAY_BASE_URL=http://10.30.220.12:8892`和`SOFT_ZONE_REPLAY_REMOTE_SMOKE=1`后运行同一脚本；Edge桌面/手机、Firefox桌面、WebKit手机共4项通过，错误态和空态可见。
- 硬门槛：真实数据库状态、播放帧推进、温度曲线8条、静压力曲线6条、联动游标、横向零溢出、SimSun、控制可达、页面/控制台错误为0；报告位于`logs/soft_zone_replay_20260808/viewport_matrix/report.json`与`remote_22012_matrix/report.json`，每个视口另存`*_trends.png`曲线截图。
# ABC33数据接线与影子门专项验收（2026-08-08）

- 命令：`D:\ProgramData\anaconda3\python.exe -m pytest tests/test_abc_bridge_live_values.py tests/test_abc_rule_engine.py tests/test_abc_production_ui.py -q`。
- 结果：20 passed；覆盖实时值与质量字段合并、覆盖率0失败关闭、稀疏分钟5分钟内最新有效值、超过5分钟不回填、33项完整性、防泄漏、页面延迟宿主挂载以及影子模式不发布分数/告警。
- 生产：批次56为33项、31项非零置信度、公开分数0、告警0；8094主页和资源分别包含 `abc33-20260808-r5-shadow-gate` 与 `BUG-ABC33-INLINE-RENDER-RACE-20260808-R4`。

## TEST-8093-DIAGNOSIS-AI-DATA-LIMITS-20260808

- 本地合同：`tests/test_diagnosis_ai_analysis.py`，结果 `16 passed`；另有人工断言和 Python AST 语法检查通过。
- 远端只读：`tools/remote_probe_22012_diagnosis_data_coverage.ps1` 核验 220.12 注册表、最近 60 分钟 `one_minute_values`、`raw_5s_values` 和 30 天基线，未写入数据库。
- 发布验收：使用 `tools/remote_guarded_deploy_8093_ai_data_limit_fix.ps1`，要求 8093 HTTP 200、提示词 v6、目标点位不再被误报、8768 PID/监听保持不变。
- 实际远端结果：8093 HTTP 200，分析 `completed`，`data_limits=[]`，`core_variable_count=19`；服务和监听最终恢复，8094 未操作。

## TEST-FOREMAN-PSPACE-EXTRA-METRICS-20260808

- 本地合同：`pytest.exe -q -p no:cacheprovider --basetemp .tmp_pytest_foreman_actual_points tests\test_pspace_billboard_realtime_bridge.py tests\test_foreman_trend_missing_value_semantics.py tests\test_foreman_trend_preview.py tests\test_foreman_points_and_coal_storage.py`，结果 `14 passed`。
- 远端8770：`python tools/verify_billboard_pspace_8770.py --url ws://10.30.220.12:8770 --open-timeout 20 --frame-timeout 20 --require-numeric 100`，结果 `stream_value_count=157`、`foreman_numeric_count=17`、`passed=true`。
- 远端页面：设置Playwright `NODE_PATH` 后运行 `node tools/inspect_foreman_trend_remote_points.cjs`；页面状态为 `pSpace秒级已连接 · 分钟历史已连接`，目标扩展点均为 `source=pspace`。
## TEST-SI-V20-INDEPENDENT-WORKBENCH-20260808

- 后端合同：`python -B tests\\test_si_v20_shadow_workbench.py`，9项通过；覆盖候选状态、实际实绩并集、数据就绪度、预测详情、路由和开口前60分钟回放截止时刻。
- 镜像回补：`python -B -c "import tests.test_heat_performance_quality_repair_loop as t; t.test_local_22012_mirror_recovers_completed_heat_average_without_external_imes(); print('mirror_test_ok')"`。
- 浏览器：`tools/verify_si_v20_standalone_ui.cjs` 在 Chromium、Firefox、WebKit 代表视口通过；候选、曲线和历史行可见，控制台错误为0。
- 必测语义：未预测历史炉次仍显示实际Si；预测行保留 `requested_at`（实际发起时间）和 `prediction_cutoff_ts`（模型截止时间）；后续化验到库后按炉号自动补齐实际值和误差。
# ABC33通用特征与影子回放（REQ-ABC33-COMMON-FEATURES-FIRST-20260808）

- 测试：`python -m pytest tests/test_abc_common_factors.py tests/test_abc_calibrated_features.py tests/test_abc_rule_engine.py tests/test_abc_replay.py tests/test_abc_bridge_live_values.py tests/test_abc_production_ui.py -q`
- 结果：2026-08-08为`100 passed`。
- 30天通用回放：`python tools/replay_abc33_rules.py --days 30 --step-minutes 5 --output logs/abc33_common_feature_replay_30d.json`，`8641/8641`批，0错误。
- 三天影子诊断：`python tools/replay_abc33_rules.py --days 3 --step-minutes 5 --evaluate-rules-shadow --output logs/abc33_rule_shadow_3d_corrected_20260808.json`，`865/865`批，0错误；不得据此自动开放生产分数或告警。
## TEST-HEAT-QUALITY-REPAIR-PRODUCTION-20260809

- 追踪：`REQ-HEAT-QUALITY-REPAIR-CLOSED-LOOP-20260807`
- 范围：炉号/工作日期双锚点、跨午夜、未来隔离、镜像差异、镜像过期后的汇总血缘重算、时间专用更新、SYSTEM 计划任务退出码。
- 本地：相关六个测试文件共 `38 passed`，相关 Python 入口 `py_compile` 通过。
- 生产：`HeatPerformanceQualitySync LastTaskResult=0`；089/090 精确查询和结构化原因通过；8093/8768 运行，8094/8770 未重启。
- 证据：[2026-08-09 生产交接](handoffs/2026-08-09-heat-quality-closed-loop-production.md)。
## TEST-SI-V20-AUTO-REFRESH-CACHE-20260809

- 需求/故障：`Q-SI-V20-WHY-QUALITY-NOT-AUTO-UPDATED-20260809`、`ERR-SI-V20-IMMUTABLE-ASSET-STOPS-AUTO-REFRESH-20260809`。
- 命令：`python -B -m unittest tests.test_si_v20_shadow_workbench`，结果 12 passed；`node --check .\高炉前端数据\assets\bf-si-v20-workbench.js`，结果 0。
- 运行验收：8093 status 推荐 126 炉，最新实际 125 炉 `0.23`；HTML HTTP 200、`no-store` 且引用 `20260809-auto-refresh-r2`；真实 Chrome 日期到 8 月 9 日，前三行 125/124/123，横向溢出 0。
- 注意：仓库独立 Playwright 脚本在本机会因未安装 `playwright` 包而无法启动，本轮跨浏览器基线沿用 2026-08-08；本次新增逻辑用真实 Chrome 补做生产冒烟。
## TEST-IMES-REALTIME-1MIN-20260809

- 对应运维目标：`OPS-IMES-REALTIME-1MIN-20260809`。
- 本地：`tools/check_ps1_syntax.ps1` 校验通过；`tests/test_set_22012_imes_realtime_1min.py` 合同测试通过。
- 部署：本机/远端 PS1 SHA-256 均为 `E21BCAEACE48D89AE517738B16832F727402560059B33E1243464704853B13BF`；任务由 `PT5M` 变更为 `PT1M`，`IgnoreNew` 生效，回滚未触发。
- 独立远端复核：`2026-08-09 19:44:45 +08:00` 任务正在运行，下一次计划时间 `19:45:45`；`bf2_output_list_cond_data` 镜像更新到 `19:44:39`；8093/8768/8094/8770 PID 前后一致。
- `19:47:27` 再次复核：`LastRunTime=19:46:46`、`NextRunTime=19:47:47`，三个目标镜像时间推进到 `19:44:39/19:44:40/19:44:48`；运行态的`0x800710E0`不冒充已完成轮失败，最终成功以日志和镜像推进确认。
- 边界：任务单轮可超过两分钟，1分钟是尝试触发周期；下游 `HeatPerformanceQualitySync` 仍为5分钟。
## TEST-SI-V20-HOURLY-CADENCE-AUDIT-20260809

- 本机命令：`powershell.exe -NoProfile -ExecutionPolicy Bypass -File '.\tools\audit_si_v20_prediction_cadence.ps1'`。
- 远端命令：通过 `remote_22012_exec.py --script .\tools\remote_audit_si_v20_hourly_tasks.ps1` 在220.12只读执行。
- 结果：匹配V20/Si小时预测的服务器任务0个；审计427行中 `hourly_schedule=1`、严格开口前小时预测0；该记录误差0.087845、±0.05未命中；去重60分钟回放112炉、MAE 0.049087、±0.05命中63.39%。
- 失败判定：若以后部署服务器小时任务，必须同时验证任务动作、整点截止、幂等键、请求早于真实开口、连续小时无缺口及后续实际值自动回填。

## TEST-SI-V20-DUAL-TIMING-LOCAL-20260809

- 覆盖文件：`tests/test_si_v20_shadow_workbench.py`、`tests/test_si_v20_hourly_automation.py`、`tests/test_set_22012_imes_realtime_1min.py`。
- 合同：历史回看固定 `open_ts-60min`；生产截止整点化；同高炉同整点幂等；过期候选可按最新炉次和中位炉间隔推进；整点结果按 `requested_at` 后第一条真实开口匹配；生产任务不依赖页面常开；炉次汇总一分钟任务保留Action/Principal、IgnoreNew、备份回滚和端口保护。
- 本机命令：`python -B -m pytest -q tests\test_si_v20_shadow_workbench.py tests\test_si_v20_hourly_automation.py tests\test_set_22012_imes_realtime_1min.py`。
- 当前结果：22项通过；JavaScript `node --check` 通过；整点运行器 dry-run 通过；三个新增PowerShell脚本经 Windows PowerShell AST 解析均为 `syntax_ok`。浏览器连接对本机私网测试URL返回阻止访问，因此本轮未完成浏览器视口矩阵，部署前仍是硬性待办，不能以静态测试代替。
- 生产边界：注册器尚未在220.12执行，因此不能用本机测试替代“连续整点无缺口”生产验收。

## TEST-SI-V20-CONFIGURABLE-SCHEDULE-20260809

- 需求：`REQ-SI-V20-CONFIGURABLE-SCHEDULE-20260809`。
- 文件：`tests/test_si_v20_configurable_schedule.py`，并复用V20工作台、小时自动化和IMES一分钟合同测试。
- 覆盖：1/10/30/60/1440白名单；时间槽向下/向后对齐；配置保存后下一槽；到期分发和推进；历史批量包含首尾；配置/批次/审计表合同；API路由；页面控件；分钟任务IgnoreNew。
- 命令：`python -B -m pytest -q tests\test_si_v20_shadow_workbench.py tests\test_si_v20_hourly_automation.py tests\test_si_v20_configurable_schedule.py tests\test_set_22012_imes_realtime_1min.py`。
- 2026-08-09结果：`28 passed`；生产只读验证器确认三表存在、默认60分钟配置和23:00首个调度点。8093浏览器完成下载控件、炉次124~127筛选4行、实际Si导出4炉及无横向溢出检查；8094 API和r6资源HTTP通过。完整Firefox/WebKit矩阵尚未补跑。
- 本机结果：28项通过；前端`node --check`通过；分钟分发器dry-run通过；两个新增PowerShell脚本AST语法通过。
- 待办：本机私网URL仍受浏览器连接策略限制，部署前必须在可访问测试面完成规定视口矩阵；220.12尚未注册分钟分发任务。

## TEST-ABC33-BASELINE-COVERAGE-20260809

- 需求：`OPS-ABC33-BASELINE-COVERAGE-20260809`。
- 本机命令：`python -m pytest -q -p no:cacheprovider tests/test_daily_baseline_quartiles.py tests/test_abc_common_factors.py tests/test_abc_rule_engine.py`。
- 结果：`95 passed`；覆盖普通状态量5分钟有界保持、炉体温度15分钟有界保持、四点顶温派生、膨胀罐小时/日聚合、四分位入库及规则基线门禁。
- 生产命令：`tools/run_abc33_baseline_rebuild.ps1 -BackfillDays 1 -EndDay 2026-08-09`，随后由 `tools/verify_abc33_baseline_coverage.py --day 2026-08-09 --minimum-coverage 0.75` 严格校验。
- 生产结果：137/137可用，缺失0、低覆盖0、统计无效0；重建日志为 `logs/abc33_baseline_rebuild_20260809_234917.json`。
- 修复后本机规则审计：`8/33`完整、`16/33`置信度不低于75%；剩余25项为实时派生因子或现场阈值缺口，不得再次归因于30天基线缺失。

## TEST-SI-V20-STRICT-HOURLY-20260810

- 命令：`python -m pytest -p no:cacheprovider tests/test_si_v20_strict_hourly.py tests/test_si_v20_configurable_schedule.py tests/test_si_v20_hourly_automation.py tests/test_si_v20_shadow_workbench.py -q`。
- 本机结果：`35 passed`；覆盖整点毫秒边界、迟到Si可用时间、传感器`collected_at`边界、失败重试、唯一槽、24个自然小时槽、严格GET无领域写入、模型与页面/API/任务合同。
- 模型一致性：process133冻结LightGBM与gzip纯Python推理在真实样本上的绝对差为`1.11e-16`；导出模型7549特征、420棵树、SHA-256=`4555c44f69326068f41023c2f4cfdff4bce0fb7ced693af1085003d0f3a4e4f4`。
- 静态检查：工作台JavaScript `node --check`通过；两个PowerShell任务脚本AST解析通过。
- 生产结果：220.12三表存在；首槽成功1、重复0、非整点0、截止违规0、Si可用时间缺失0。8093与8094均完成Chromium 9视口、Firefox 4视口、WebKit 4视口，页面错误0、横向溢出0。
- 审计修正：首次运行发现JSONB水位含datetime无法序列化，失败槽按合同保留并重试；修复后第3次成功。随后发现数据库默认发起时间晚于计算完成约24ms，迁移为槽领取时间后满足`requested_at<=execution_completed_at`。两项均有失败次数/时间记录，未删除审计。
- 待办：连续24小时24槽必须在真实经过24小时后复核；单元测试只证明槽生成算法，不能替代生产连续性证据。
- 独立审查整改：审查发现严格GET会建槽/固化匹配；已移除状态/历史中的`ensure_strict_hourly_slots`与`reconcile_strict_hourly_matches`。生产连续调用5轮status/history前后，slot `updated_at=2026-08-10 01:08:46.668992+08:00`、`attempt_count=3`、`prediction_id=623`、history count=1均不变。
- 2026-08-10持续结果：扩展回归为`37 passed`；补充炉次可用时间并发写入回归后，`tests/test_heat_performance_quality.py`、修复回看及严格整点合计`33 passed`。生产01:00~08:00共8槽全部成功，失败/运行/陈旧/逾期/重复/非整点/截止违规均为0，Si可用时间缺失0。
- 页面矩阵：8093、8094各17个浏览器/视口组合通过，横向溢出0、控制台错误0；每小时汇总表、独立截图和第三个页面下载CSV均进入验收产物。

## TEST-OPS-POWERSHELL7-UTF8-20260810

- 需求：`REQ-OPS-POWERSHELL7-UTF8-20260810`、`REQ-OPS-LOCAL-NATIVE-POSTGRES-START-20260811`。
- 测试：[静态合同](../tests/test_pwsh7_runtime_contract.py)、[真实运行时验证器](../tools/verify_pwsh7_utf8.ps1)。
- 命令：`python -m pytest -q tests\test_pwsh7_runtime_contract.py`。
- 真实运行命令：`pwsh.exe -NoLogo -NoProfile -File .\tools\verify_pwsh7_utf8.ps1`。
- 本机原生数据库dry-run：`pwsh.exe -NoLogo -NoProfile -File .\start_v3_full.ps1 -DryRun -SkipAssistant -SkipFrontend -SkipDiagnosis -SkipRealtimeBridge -SkipLocalSyncLoop`；成功信号为`mode=local-native target=127.0.0.1:18000/bf_trend user=postgres`且输出不包含密码值。
- 2026-08-11结果：`5 passed`；真实JSON返回`ok=true`、`PSEdition=Core`、`ps_version=7.6.4`，三项编码均为`utf-8`，中文读写回环无错误；本机dry-run输出原生目标，脚本不含Docker `15432`或数据库密码默认值。
- 失败排查：先确认`C:\Program Files\PowerShell\7\pwsh.exe`存在，再运行`winget list --id Microsoft.PowerShell --exact`；不得改为5.1回退。

## TEST-22012-POWERSHELL7-UTF8-20260810

- 需求：`OPS-22012-POWERSHELL7-UTF8-20260810`。
- 测试：[合同测试](../tests/test_remote_22012_pwsh7_runtime.py)、[真实远端冒烟](../tools/remote_smoke_22012_pwsh7.ps1)。
- 本机命令：`python -B -m pytest -q tests\test_remote_22012_pwsh7_runtime.py tests\test_pwsh7_runtime_contract.py`。
- 本机结果：`7 passed`；Python编译通过；PowerShell 7 AST解析通过。
- 远端结果：`ps_version=7.6.4`、`ps_edition=Core`、中文输出正确；8093/8094/8768/8770/5432均监听且PID为`4044/4156/8524/3732/12372`，与安装前一致。
- 安装门禁：MSI SHA-256=`D11942DF52FD12470169797ABFA4781D9480EFDC81000BA4FA55A5B921ED8DD0`，Microsoft签名有效，安装退出0，不需要重启。

## TEST-SI-V20-NEW-HEAT-HOURLY-ACCEPTANCE-20260810

- 需求：`OPS-SI-V20-NEW-HEAT-HOURLY-ACCEPTANCE-20260810`。
- 语法检查：`node --check .\tools\audit_si_v20_new_heat_acceptance.cjs`。
- 单次验收：`node .\tools\audit_si_v20_new_heat_acceptance.cjs --output-dir .\reports\acceptance\SI_V20_NEW_HEAT_20260810`；退出码`2`表示证据已保存但仍在等新炉次/完整闭环，退出码`0`才表示验收通过。
- 远端只读探测：`python -B .\tools\remote_22012_exec.py --allow-agents-password --no-profile --timeout 60 --workdir 'F:\高炉炼铁项目-real-sensor-v2_V4_8093_PREVIEW' --script '.\tools\remote_probe_si_v20_acceptance.ps1'`。
- 第0次结果：截图、两个页面下载CSV、三类审计CSV和API JSON均已生成；页面错误0、横向溢出0。严格03:00槽因时间时区类型不一致持续重试，故预期退出2并保持监控。
- 08:37结果：132炉已进入status/history，实际平均Si=`0.400%`。首次检查因该炉`si_available_at`为空退出1；修复独立同步副本和upsert竞争条件后，数据库核验`ok=true`、缺失0，验收退出0。最新证据为`reports/acceptance/SI_V20_NEW_HEAT_20260810/20260810T003743Z_check.json`，自动化仍保持每小时运行。
- 08:52结果：133炉开口/堵口/平均Si已自动回填；严格整点8槽全成功，其中6条完成评价、±0.05命中率50%。每小时汇总10行、评价8行、命中率37.5%；证据为`reports/acceptance/SI_V20_NEW_HEAT_20260810/20260810T005251Z_check.json`。
# TEST-ABC33-HANDBOOK64-DOCX-20260810

- 对应需求：`REQ-ABC33-HANDBOOK64-MECHANISM-INTERVENTION-20260810`。
- 被测入口：[tools/build_abc33_handbook64_revision.py](../tools/build_abc33_handbook64_revision.py)。
- 验证命令：

```powershell
python -m py_compile .\tools\build_abc33_handbook64_revision.py
python .\tools\build_abc33_handbook64_revision.py --source <规则DOCX> --handbook <见习高炉长DOCX> --output <修订DOCX> --mapping-json <映射JSON> --audit-json <审计JSON> --audit-md <审计Markdown>
python .\tools\inspect_docx_hierarchy.py <修订DOCX> --major-only --limit 120
```

- 预期结果：`rule_count=33`、`chapter_count=64`、`mapped_chapter_count=64`、`unmapped_chapters=[]`；修订DOCX重新打开成功，新增33个规则三级标题、33段形成原理和33套干预处置流程。

### 前后30分钟料批速度加粗判据

- 对应需求：`REQ-ABC33-HEAT-BATCH-RATE-CRITERION-20260810`。
- 关键断言：A2/B4/B5原公式单元格和补充章节共6处全段加粗；公式单元格内排在Score公式之前；料速项权重为`20`，其余原有项按0.8比例压缩后合计`80`，三条公式总权重均为100；小批按煤、矿分别计数；正常范围、硬上限、示例、双基线和连续2小时强预警条件均存在。
- 测试位置：[test_abc33_handbook64_revision.py:L56-L67](../tests/test_abc33_handbook64_revision.py#L56-L67)。
- 实际文件验证器：[verify_abc33_heat_batch_rate_docx.py:L24-L104](../tools/verify_abc33_heat_batch_rate_docx.py#L24-L104)。

```powershell
pytest .\tests\test_abc33_handbook64_revision.py -q --basetemp .\.tmp_pytest_heat_batch_rate
python .\tools\verify_abc33_heat_batch_rate_docx.py .\docs\炉况计算规则补充_ABC33形成原理与干预处置流程_料批速度判据加粗修订版_20260810.docx
```

- 预期结果：A2、B4、B5三处均包含同一完整判据，全部文本run为粗体；输出`criterion_paragraph_count=3`、`fully_bold=true`、参考值`7.5批/h`、容差`0.5批/h`。
- 2026-08-10结果：实际DOCX重新打开成功，三处文本完整且全段粗体；专项测试`3 passed`。

### 在线料批速度评分与8093/8768生产验收

```powershell
pwsh.exe -NoLogo -NoProfile -NonInteractive -File .\tools\test_abc33_burden_rate_local.ps1
pwsh.exe -NoLogo -NoProfile -NonInteractive -File .\tools\deploy_abc33_burden_rate_22012.ps1
```

- 本地结果：料速周期、规则、公共复核、公共因子、回放和持久SSH合同共`119 passed`；9个Python目标`py_compile`通过；ABC配置校验和8个PowerShell 7脚本AST解析通过。
- 8093结果：`guard_paused=true`、`guard_restored=true`、`rollback_applied=false`、HTTP 200；PID由`19268`变为`2332`；A2/B4/B5首项料速均为`available`。
- 8768结果：PID由`3684`变为`8680`；WebSocket返回33条规则、33条有效分数、33条数据完整、0条`needs_data`；受保护PID全部不变。
- 浏览器结果：A2/B4/B5均显示料速、前后30分钟、昨日平均、滚动24小时、连续2小时和实际变化语义；详情与页面横向溢出均为0。控制台无运行时异常；存在1条既有Babel大内联脚本代码生成降级提示，不属于本次料速功能错误。

### 建议页面运行时接入

```powershell
python -m py_compile .\自动诊断服务\abc_rule_guidance.py .\自动诊断服务\abc_rule_catalog.py .\自动诊断服务\abc_rule_engine.py .\tools\export_abc_rule_guidance.py
node --check .\高炉前端数据\assets\abc-furnace-rules-production.js
pytest .\tests\test_abc_runtime_store.py .\tests\test_abc_rule_engine.py .\tests\test_abc_production_ui.py -q
```

- 预期结果：33项形成原理逐条不同；每项严格返回5个处置步骤和至少1个手册章节；普通接口与前端不含公式、权重、阈值、归一化值和贡献。
- 2026-08-10本机结果：Python与JavaScript语法通过；先执行定向合同测试`30 passed`，再执行ABC33规则、桥接、特征、公共因子、回放、页面和文档全套相关回归`128 passed`。浏览器夹具打开A1详情后可见“炉况形成原理”“五步干预处置流程”、5个有序步骤、手册章节、观察窗口和审批要求。Chromium九个规定视口均无横向溢出、窄屏单列正确、控制台错误/警告0。
- 8093发布补充测试：`test_abc_runtime_store.py`断言同一分钟冲突批次同步刷新`catalog_version/config_version/coverage_ratio/data_age_seconds/public_bundle`；与规则和页面合同合并执行`31 passed`，ABC33全套相关回归`129 passed`。远端最终接口返回目录版本`abc33-catalog.v3.handbook64-guidance`、33条规则及A1严格5步流程。

## TEST-COHESIVE-ZONE-INTELLIGENT-DIAGNOSIS-20260810

| 项目 | 内容 |
|---|---|
| 对应需求 | `REQ-COHESIVE-ZONE-INTELLIGENT-DIAGNOSIS-20260810` |
| 被测函数 | [diagnose_cohesive_zone_movement:L214-L432](../炉况规则引擎/features/cohesive_zone_intelligent_diagnosis.py#L214-L432) |
| 组合函数 | [estimate_and_diagnose_cohesive_zone:L434-L469](../炉况规则引擎/features/cohesive_zone_intelligent_diagnosis.py#L434-L469) |
| 测试 | [test_cohesive_zone_intelligent_diagnosis.py:L84-L161](../tests/test_cohesive_zone_intelligent_diagnosis.py#L84-L161) |
| 验证入口 | [verify_cohesive_zone_intelligent_diagnosis.ps1:L1-L41](../tools/verify_cohesive_zone_intelligent_diagnosis.ps1#L1-L41) |

```powershell
pwsh.exe -NoLogo -NoProfile -File `
  .\tools\verify_cohesive_zone_intelligent_diagnosis.ps1 `
  -PythonExecutable python
```

关键断言：

- 文档中的“顶凉、压高、料慢、风紧”组合判为上移，“顶热、压松、炉凉”组合判为下移，无显著变化判稳定；
- 归一化概率和为1，置信度不超过0.45，固定`uncalibrated/control_use=prohibited`；
- 当前/参考窗口之间有隔离区，评价时间后的行不能改变历史结果；
- 缺少压力/透气性或温度场必需分组时返回`unavailable`，不输出貌似可信的方向；
- Si和铁水温度下降只形成热制度下行关联证据，不覆盖现有8类炉况规则；
- CSV入口可以写出UTF-8 JSON，组合入口保留既有C2几何安全合同。

2026-08-10结果：`30 passed`；`py_compile`、CLI帮助和PowerShell 7 UTF-8运行检查均通过。另行联跑既有8767桥接测试时有1项历史测试替身缺少`FakeConnection.execute`，该文件不在本次修改范围，详见交接记录。

## HCZ专家弱标签验收（2026-08-10）

- `python -m pytest tests/test_hcz_expert_label.py tests/test_soft_zone_replay_server.py -q`：12项，覆盖盲标字段拒绝、无法判断说明、稳定哈希、知识时间模式、服务器身份、追加DDL和原8892回归。
- `ruff check tools/soft_zone_replay_server.py 高炉前端数据/智能助手/backend/hcz_expert_label.py tests/test_hcz_expert_label.py`：通过。
- `node tools/verify_hcz_expert_label_ui.cjs`：Chromium 9个固定视口、Firefox/WebKit各4个代表视口，共17/17通过，包含真实表单提交夹具、无横向溢出和估计控件不可见断言。
- `node tools/verify_hcz_expert_label_remote_ui.cjs`：220.12 Edge只读冒烟；不得在生产验收中写测试标签。
- `python tools/audit_pspace_top4_hcz_aug9.py`（220.12临时执行）：pSpace四点直读成功，20:00四点均温`109.330℃`、22:00为`124.728℃`，`errors={}`，证据SHA-256=`14a3d5fc9bc90897a59ab2e8f570eec3e69cf8e1a5f7c752e37041632f8e2e85`。
- `pwsh.exe -NoLogo -NoProfile -File tools/remote_submit_hcz_aug9_upward_label.ps1`（220.12临时执行）：写入前同日期0条，POST返回`created=true`；回读按观察时刻、方向和实测哈希精确命中1条，`blind_to_model=true`、`model_outputs_included=false`。
- `pytest tests/test_hcz_expert_label.py tests/test_soft_zone_replay_server.py -q -p no:cacheprovider`：2026-08-11复跑`12 passed`。
- `pwsh.exe -NoLogo -NoProfile -File tools/verify_pwsh7_utf8.ps1`：PowerShell 7.6.4 Core与UTF-8通过。

证据见[生产交接](./handoffs/2026-08-10-hcz-expert-weak-label-production.md)和[首条上移标签交接](./handoffs/2026-08-11-hcz-aug9-upward-expert-label.md)。

## HCZ上移综合趋势经验规则验收（2026-08-10，2026-08-11冷风口径与阈值试算更新）

- `python -m pytest tests/test_hcz_upward_expert_rule.py tests/test_hcz_upward_rule_api.py -q -p no:cacheprovider`：15项通过；除原规则合同外，覆盖顶温15→10事件量变化、下移对称候选、参数拒绝、90天只读缓存与`GasUtil 0.456→45.6`单次换算。
- `ruff check 炉况规则引擎/features/hcz_upward_expert_rule.py 高炉前端数据/智能助手/backend/hcz_upward_rule_api.py tests/test_hcz_upward_expert_rule.py tests/test_hcz_upward_rule_api.py`：通过。
- `node tools/verify_hcz_upward_rule_ui.cjs`：Chromium 9个固定视口、Firefox/WebKit各4个代表视口，共17/17通过；验证表单试算、事件数刷新、`%`和“百分点”。
- `node tools/verify_hcz_upward_rule_remote_ui.cjs`：生产Edge `1366×768`与`390×844`通过；5项指标、7层、3门、90天15→10试算齐全，横向溢出0，页面/控制台错误0。
- `pwsh.exe -NoLogo -NoProfile -File tools/verify_pwsh7_utf8.ps1`：PowerShell 7.6.4 Core与UTF-8通过。

生产API最新实测为`not_triggered`，不是测试造数；煤气利用率约`45.83%`，相对前五天变化约`-0.55个百分点`。近90天顶温阈值15→10时上移和下移候选均为`0→0`。部署过程保护8094/8768/8770/5432/8892/11434 PID不变。证据见[规则初始交接](./handoffs/2026-08-10-hcz-upward-expert-rule-8093.md)和[阈值试算交接](./handoffs/2026-08-11-hcz-rule-sensitivity-8093.md)。

## 8093“严重事件交叉确认”提示移除验收（2026-08-10）

- `node --check 高炉前端数据/assets/abc-furnace-rules-production.js`：通过。
- `pytest tests/test_abc_production_ui.py -q`：6项通过，包含8093端口级不渲染合同。
- 生产守卫闭环：`guard_paused=true`、`guard_restored=true`、8093 HTTP 200。
- 受保护运行态：8094、8768、8770、11434 PID部署前后完全一致；8094页面文件SHA-256未改变。
- 缓存版本：`abc33-20260810-hide-cross-confirmation-8093-r1`。

完整证据见[上线记录](./handoffs/2026-08-10-8093-remove-cross-confirmation-banner.md)。

## 8093处置首屏与工艺依据按钮验收（2026-08-10）

- `node --check 高炉前端数据/assets/abc-furnace-rules-production.js`：通过。
- `pytest tests/test_abc_production_ui.py -q`：7项通过；覆盖处置顺序先于按钮、按钮`aria-expanded=false`、隐藏内容、工艺依据、操作原理及8093分支不使用章节索引。
- 生产B4详情：`rule_id=B4`、`intervention_order=5`，原有后端合同未丢失。
- 生产守卫闭环：`guard_paused=true`、`guard_restored=true`、8093 HTTP 200。
- 受保护运行态：8094、8768、8770、11434 PID部署前后完全一致；8094页面文件未修改。
- 缓存版本：`abc33-20260810-action-first-basis-toggle-r1`。

完整证据见[上线记录](./handoffs/2026-08-10-8093-action-first-basis-toggle.md)。

## 8093 ABC33复核点中文名称验收（2026-08-10）

- `node --check 高炉前端数据/assets/abc-furnace-rules-production.js`：通过。
- `pytest tests/test_abc_production_ui.py tests/test_abc_public_review_labels.py -q`：`10 passed`。
- 上线前全量扫描：33条规则详情全部可读，118个唯一复核指标中6个未中文化，影响7条规则。
- 上线后全量扫描：`rule_count=33`、`detail_error_count=0`、`unique_metric_count=118`、`issue_metric_count=0`。
- 生产守卫闭环：`guard_paused=true`、`guard_restored=true`、8093 HTTP 200；8093监听PID由13064更新为3648。
- 受保护运行态：8094 PID 2988、8768 PID 18436、8770 PID 3732、11434 PID 5968均未变化；8094页面SHA-256未改变。
- 缓存版本：`abc33-20260810-chinese-metric-labels-r1`。

完整证据见[上线记录](./handoffs/2026-08-10-8093-abc33-chinese-metric-labels.md)。

## 8093 ABC33复核分组去重验收（2026-08-10）

- `node --check 高炉前端数据/assets/abc-furnace-rules-production.js`：通过。
- Python语法检查：`abc_public_review.py`和`audit_abc33_review_group_duplicates.py`通过。
- `pytest tests/test_abc_production_ui.py tests/test_abc_public_review_labels.py -q`：`12 passed`。
- 上线前生产审计：33条详情无读取错误，`metric_occurrence_count=669`、`affected_rule_count=33`、`duplicate_variable_count=39`、`duplicate_occurrence_count=196`。
- 上线后生产审计：33条详情无读取错误，`metric_occurrence_count=473`、`affected_rule_count=0`、`duplicate_variable_count=0`、`duplicate_occurrence_count=0`；中文标签问题仍为0。
- 守卫闭环：`guard_paused=true`、`guard_restored=true`、8093 HTTP 200；8093 PID由3648更新为6432。
- 受保护运行态：8094 PID 2988、8768 PID 18436、8770 PID 3732、11434 PID 5968均未变化；8094页面SHA-256未改变。
- 缓存版本：`abc33-20260810-disjoint-review-groups-r1`。

完整证据见[上线记录](./handoffs/2026-08-10-8093-abc33-disjoint-review-groups.md)。

## 8093 ABC33复核表纵向语义布局验收（2026-08-10）

- `node --check 高炉前端数据/assets/abc-furnace-rules-production.js`：通过。
- `pytest tests/test_abc_production_ui.py tests/test_abc_public_review_labels.py -q`：`13 passed`。
- 生产33项语义审计：`rule_count=33`、`metric_occurrence_count=473`、`semantic_count=473`、`missing_semantic_count=0`；最长语义为A5的`Q_O2`，128字。
- 生产资源合同：包含`overflow-x:hidden`、`max-height:none`、`table-layout:fixed`、`abc33-metric-semantic-row`和`colspan="6"`；不包含`min-width:1120px`。
- 守卫闭环：`guard_paused=true`、`guard_restored=true`、8093 HTTP 200；8093 PID由6432更新为19268。
- 受保护运行态：8094 PID 2988、8768 PID 18436、8770 PID 3732、11434 PID 5968均未变化；8094页面SHA-256未改变。
- 缓存版本：`abc33-20260810-vertical-metric-layout-r1`。
- 浏览器导航：新缓存URL已打开；生产大屏主线程繁忙使深层DOM自动化超时，因此不能据此声称控制台0错误或完整跨视口通过。

完整证据见[上线记录](./handoffs/2026-08-10-8093-abc33-vertical-metric-layout.md)。

## TEST-8093-GUARDED-UPDATE-SKILL-20260810

- 对应需求：`OPS-8093-GUARDED-UPDATE-SKILL-20260810`。
- Skill合同验证：`pwsh.exe -NoLogo -NoProfile -File .\.codex\skills\deploy-8093-guarded-update\scripts\validate_skill.ps1`。
- 结构验证：设置`PYTHONUTF8=1`后执行`python C:\Users\hmw20\.codex\skills\.system\skill-creator\scripts\quick_validate.py .\.codex\skills\deploy-8093-guarded-update`。
- 清单脚本自测：`python -B .\.codex\skills\deploy-8093-guarded-update\scripts\release_manifest.py --self-test`。
- 项目/全局同步验证：先执行`PublishProjectToGlobal`，再执行`pwsh.exe -NoLogo -NoProfile -File .\tools\sync_deploy_8093_guarded_update_skill.ps1 -Action Verify`；要求`schema=bf.codex.skill-sync.v1`、`file_count=14`、`identical=true`和`remote_write_performed=false`。
- 覆盖：PowerShell 7/Core与UTF-8、两层模板语法、源/产物/验证证据完整性密封、篡改拒绝、实时基线差量、空差量不重启、upload-only先于远端payload、全局部署互斥、基线SHA-256、路径根约束、备份/回滚、`finally`恢复、8094/8768/8770/5432/11434保护和结构化结果字段。
- 结果：合同验证`ok=true`、PowerShell=`7.6.4`、解析模板2份、确定性脚本2份、`remote_write_performed=false`；清单四个schema自测通过；Skill Creator返回`Skill is valid!`。项目/全局14文件bundle SHA-256均为`F75B6DA1C3FC1F410A5DF6FAC4C09D42E67459B9E5BCF20471B4A6EC9B6FA323`。未执行生产前向测试，因为那会暂停8093并产生生产写入，需要由具体部署需求单独授权。

## TEST-22012-PERSISTENT-SSH-SESSION-20260810

- 对应需求：`OPS-22012-PERSISTENT-SSH-AND-PYTHON-PROTECTION-20260810`。
- 单元测试：`python -m pytest -q tests/test_remote_22012_persistent_session.py tests/test_remote_22012_pwsh7_runtime.py`。
- 覆盖：会话状态位于仓库外的`LOCALAPPDATA`、同一已认证transport复用、30秒协议keepalive、调用者持有client不被`remote_22012_exec.py`关闭、远端传输异常只执行一次且`automatic_replay=false`、`run --`参数保持。
- Skill覆盖：本机模板必须先`ensure`，upload-only与script通过同一会话运行，最后只做status并保留代理；保护参考必须明确`.pyb`非标准、`.pyc`不保密、Nuitka/Cython本机构建和不可承诺绝对防逆向。
- 结果：专项与既有PowerShell 7运行时测试共`8 passed`；Skill合同验证和Skill Creator结构验证通过。只读生产双命令的同一`session_id/connection_id`、递增`request_count`另由运行证据确认。

### TEST-22012-WINDOWS-CREDENTIAL-SSH-RECOVERY-20260814

- 对应需求：`OPS-22012-WINDOWS-CREDENTIAL-SSH-RECOVERY-20260814`。
- 静态合同：`python -m pytest -q tests/test_22012_credential_recovery.py`，验证固定凭据目标/用户、`CredReadW/CredFree`、Reliable SSH 受保护源回退、脱敏占位符拒绝、DACL 和零秘密输出合同。
- 运行验收：先运行 `pwsh.exe -NoLogo -NoProfile -File .\tools\restore_22012_ssh_secret_from_windows_credential.ps1`；随后以两个独立进程连续运行两次 `pwsh.exe -NoLogo -NoProfile -File .\tools\configure_22012_reliable_ssh_secret.ps1`。
- 新连接成功信号：停止旧 Paramiko broker 后重新 `ensure`，返回 `ssh_authenticated=true`、新 `connection_id`、`reconnect_count=0`；Reliable SSH `probe_identity` 返回 `WIN-54B94HVHKBA / 10.30.220.12 / administrator`，且 `automatic_replay=false`。
- 2026-08-14 实际结果：静态组合 `13 passed`；恢复器 `ok=true` 且 `password_value_emitted=false`；两次配置均 `ok=true/migrated=false`。全新 Paramiko `session_id=72cd59fe...`、`connection_id=b3d3bc1b...`，双独立 `.ps1` 耗时 `1643/1589ms`、请求 `1→2`、重连 `0`。Reliable SSH 连接池请求 `56/56` 完成、重连 `0`、自动重放关闭。

## TEST-8093-SKILL-REUSE-METRICS-AND-RSSH-MCP-20260810

- 对应需求：`OPS-8093-SKILL-REUSE-METRICS-LEARNING-AND-RSSH-MCP-20260810`。
- 项目测试：`python -m pytest -q --basetemp C:\Users\hmw20\AppData\Local\Codex\pytest\persistent_ssh tests/test_diag_rules_reliable_deployer.py tests/test_remote_22012_persistent_session.py tests/test_remote_22012_pwsh7_runtime.py tests/test_22012_persistent_ssh_reuse_ps1.py`，结果`16 passed`。
- Skill测试：`validate_skill.ps1`通过并执行`deployment_memory.py --self-test`；Skill Creator `quick_validate.py`返回`Skill is valid!`；隐式调用策略为true。
- MCP测试：在`D:\文件\网络登录服务器管理\reliable-ssh-mcp`执行`npm run check`和`npm test`，结果30项通过；覆盖Plink/Windows启动参数、OpenSSH keepalive、ZIP防穿越解压、UTF-8子进程、连接池配置和范围校验。
- 现场MCP只读：`node tools/reliable_ssh_22012_cli.mjs pool-probe`在一个Plink PID上完成4个请求；握手`19732ms`，后续两次`299/323ms`，`reconnect_count=0`、`automatic_replay=false`。
- 现场`.ps1`只读：`pwsh.exe -NoLogo -NoProfile -File .\tools\verify_22012_persistent_ssh_reuse.ps1 -IncludeColdBaseline`；相同会话/连接，请求`1→2`，远端PowerShell`7.6.4`，冷`22225ms`、复用`16943/17010ms`、初次单样本节约23.6%，生产写/服务重启均false。
- 统计边界：一条冷/热样本只证明机制可测，不足以承诺长期部署收益。正式报告至少5组交错样本，输出总部署与SSH阶段的median/p90。

## TEST-8093-ABC33-B4-CANONICAL-SCORE-20260810

- 本机：`92 passed`覆盖复核、AI、ABC规则/页面/存储/8768桥接；另`24 passed`覆盖持久SSH、独立`.ps1`和原生构建器。两份JS `node --check`、三个Python后端`py_compile`及六份PowerShell AST解析通过。
- 生产：守卫闭环`guard_paused=true/guard_restored=true/rollback_applied=false`，8093 HTTP 200，PID `2332→14436`。评价批次839中`latest_b4_score=context_display_hot=14.9623`，legacy归档28.12；8094/8768/8770/5432/8892/11434 PID前后相同。
- 备份：`F:\高炉炼铁项目-real-sensor-v2_V4_8093_PREVIEW\backups\abc33_b4_score_source_8093_20260810_195532`。
- 浏览器边界：本机85组合的布局/控件断言均执行，但15项因fixture-only未启动WebSocket或诊断附加API返回503而按控制台错误失败；生产`--live`矩阵在7分钟上限内未完成，不能宣称完整跨浏览器通过。生产API、资源标记和轻量HTTP复核通过。

## TEST-SI-V20-HOURLY-ACCEPTANCE-DOWNLOAD-TIMEOUT-20260810

- 对应错误：`ERR-SI-V20-ACCEPTANCE-DOWNLOAD-SAVE-HANG-20260810`。
- 语法：`node --check tools/audit_si_v20_new_heat_acceptance.cjs`通过。
- 完整验收：`node tools/audit_si_v20_new_heat_acceptance.cjs --output-dir reports/acceptance/SI_V20_NEW_HEAT_20260810`在60.2秒内完成，退出码0。
- 结果：139炉实际平均Si=`0.27%`；17:00严格整点槽`success`、重复0、逾期0、截止违规0；3个页面CSV、API快照、运行时探针、数据库探针和两张截图全部落盘。
- 证据：[结构化结果](../reports/acceptance/SI_V20_NEW_HEAT_20260810/20260810T093559Z_check.json)与[持续验收报告](../reports/acceptance/SI_V20_NEW_HEAT_20260810/acceptance_report.md)。

## TEST-SI-V20-ACCEPTANCE-PROBE-KEEPALIVE-20260810

- 对应错误：`ERR-SI-V20-ACCEPTANCE-API-PROBE-KEEPALIVE-20260810`。
- 8094受控恢复：旧PID2988、新PID18628；8093 PID2332、8768 PID9556、8770 PID3732、11434 PID5968在重启事务内未改变，8094 HTTP 200。
- 远端探针：PowerShell 7.6.4 Core；8093/8094/8768/8770/5432监听；四项V20/IMES任务均为`pwsh.exe`；六个8093/8094 API检查通过；耗时8.6秒。
- 数据库：01:00～19:00共19个严格整点槽全部成功，重复0、非整点0、可重试0、running/stale/逾期0、截止违规0，`missing_availability=0`。
- 完整验收：`node tools/audit_si_v20_new_heat_acceptance.cjs --output-dir reports/acceptance/SI_V20_NEW_HEAT_20260810`耗时21.6秒、退出码0；140炉实际平均Si=`0.29%`，截图和三个页面CSV均已保存。
- 证据：[结构化结果](../reports/acceptance/SI_V20_NEW_HEAT_20260810/20260810T114733Z_check.json)与[持续验收报告](../reports/acceptance/SI_V20_NEW_HEAT_20260810/acceptance_report.md)。

## TEST-8093-RISK-TIERED-BROWSER-VALIDATION-20260810

- `python -m pytest -q tests/test_diagnosis_review_browser_profiles.py`：3项通过，固定`quick=4`、`standard=17`、`full=85`以及受影响路由和1546×864合同。
- `python -m ruff format --check ...`与`python -m ruff check ...`：两个文件通过。
- `python tools/verify_diagnosis_review_local.py --base-url http://127.0.0.1:8096 --engines chromium,firefox,webkit --profile quick`：4/4通过，9.019秒；报告位于`logs/diagnosis_review_browser_20260810_202317/report.json`。
- 本次不跑85项的原因是改动只涉及诊断弹窗及验收流程，不影响全局导航、共享CSS、三维运行时或五路由结构；若定向项失败必须升级。

## TEST-UI-VIEWPORT-TWO-STAGE-20260814

- 开发阶段固定入口：受影响路由 Chromium `1366×768` 单视口；检查核心交互、横向溢出、关键裁切、底栏遮挡、中文和页面/控制台错误，不启动跨浏览器矩阵。
- 完成阶段入口：功能、自动化测试与评审完成并冻结发布候选后，按风险运行 `quick=4`、`standard=17` 或 `full=85`；生产部署与最终交付属于该阶段。
- 本次证据：`node tools/verify_abc_contextual_assistant_viewports.cjs --base-url http://127.0.0.1:18093/frontend_dashboard_v3.server.html --route qa --engine all --output-dir logs/qa_composite_trace_local_standard_20260814_final --timeout-ms 20000`，最终 `17/17` 通过；此前后端未启动导致的404报告仅作为失败诊断，不作为功能缺陷或通过证据。

## TEST-CODEX-ECONOMICAL-DELEGATION-20260810

- `codex --version`：`codex-cli 0.144.3`。
- `invoke_codex_delegate.ps1 -ListModels`：实时目录成功返回Sol/Terra/Luna等7个可见模型及各自reasoning levels。
- PowerShell Parser：`invoke_codex_delegate.ps1`无语法错误；Skill `quick_validate.py`通过。
- Luna low只读前向测试：两次都正确返回`validation_matrix; default=quick; quick=4, standard=17, full=85`，无文件修改、无生产连接。
- 最小化前：89004ms，input 58097、cached 27392、output 184；最小化后：29197ms，input 38309、cached 17152、output 235。耗时下降67.2%、输入下降34.1%，但网络WebSocket失败回退HTTP仍产生约29秒总耗时。

## REQ-8093-FRONTEND-PERF-R1 本地验收

- `npm run check`：构建源提取合同通过。
- `npm run build`：浏览器Babel和React开发版移除；GLB URL与Billboard绘制合同保持；生产HTML约221.8KB，gzip约40.5KB，Brotli约31.3KB。
- `python -B -m pytest -q -p no:cacheprovider ...`：相关20项测试通过。
- `python tools/verify_8093_frontend_production_build.py`：Chromium 1366x768核心冒烟通过；结构像素差0，广告牌/工艺标注合同一致，诊断页3D重资源为0。
- `pwsh.exe -NoLogo -NoProfile -File .\tools\deploy_8093_frontend_perf_22012.ps1`：生产受控部署通过；8093守卫恢复、HTTP 200、gzip/Brotli、immutable缓存、安装哈希、受保护PID和同一SSH会话复用均通过，未回滚。
- 未执行：本轮按用户要求停止85项全矩阵；最终兼容阶段可显式增加`--full-matrix`。

## TEST-SI-V20-ACCEPTANCE-API-RETRY-20260811

- 对应错误：`ERR-SI-V20-ACCEPTANCE-8094-STATUS-TRANSIENT-TIMEOUT-20260811`。
- `pwsh.exe -NoLogo -NoProfile -File tools/remote_probe_si_v20_acceptance.ps1`：本机PowerShell 7脚本可解析并完整执行；本机无生产端口/任务，因此业务检查按预期失败但输出结构有效。
- `python -B tools/remote_22012_exec.py ... --script tools/remote_probe_si_v20_acceptance.ps1`：220.12 PowerShell 7.6.4 Core、5个端口、4个任务及8093/8094六个API全部通过，正常接口`attempt_count=1`。
- `python -B tools/verify_si_v20_strict_hourly_production.py`：01:00～次日01:00共25个槽全部成功；重复、非整点、running/stale、逾期和截止违规均为0。
- 修复后完整验收：[结构化结果](../reports/acceptance/SI_V20_NEW_HEAT_20260810/20260810T172956Z_check.json)退出码0；页面截图、每小时表截图和三个页面CSV下载均正常。
## TEST-TS-LEADERBOARD-20260811

- 需求：`REQ-TS-LEADERBOARD-CORRECTION-20260811`。
- 测试：[tests/test_timeseries_leaderboard.py](../tests/test_timeseries_leaderboard.py)。
- 命令：`python -m pytest tests/test_timeseries_leaderboard.py -q --basetemp .tmp_pytest_timeseries_leaderboard`。
- 通过信号：`3 passed`；覆盖共同完整切点过滤、综合/方向冠军、缺失指标拒绝和错误schema拒绝。
- 接口冒烟：在本机临时端口18778启动8778后运行`python tools/check_timeseries_sidecar_python.py --url http://127.0.0.1:18778`，要求状态OK且排行榜schema正确。

## TEST-8093-CORE-PORTAL-BASELINE-20260811

- `python -B -m pytest -q tests/test_8093_core_metrics_pspace_live.py tests/test_8093_frontend_performance_build.py`：16项通过。
- `python -B tools/verify_8093_core_spark_detail.py --profile standard --local-html 高炉前端数据/frontend_dashboard_v3.production.html`：总览页17/17组合通过，未运行5路由×17的85项。
- `python -B tools/verify_8093_frontend_production_build.py`：Portal最上层、GLB/Billboard合同、诊断页不加载3D和视觉结构像素差0均通过。
- 生产`verify_8093_core_metrics_pspace_live.py --matrix single`：28/28行存在数据库30日基线，逐行公式和阈值匹配；唯一失败项为部署前既有`bf-heat-performance-quality-8093-query-v2.js` 404。
- `pwsh.exe -NoLogo -NoProfile -File tools/deploy_8093_core_modal_baseline_22012.ps1`：36.129秒成功，上传3.856秒、守卫闭环31.561秒，同一SSH连接请求号4→6。
## 8093 ABC33炉况总览入口

- `python -m pytest -q tests/test_abc_production_ui.py tests/test_abc_rule_engine.py tests/test_abc_public_review_labels.py`：39 passed。
- `node tools/verify_abc33_overview_entry_standard.cjs`：Chromium/Firefox/WebKit共17个视口组合全部通过。
- `node tools/verify_abc33_overview_entry_production.cjs`：8093生产入口嵌入、点击33张卡、关闭按钮、无横向溢出和无页面错误全部通过。
## TEST-8093-DIAGNOSIS-EVIDENCE-CACHE-MARKER-20260815

- 对应错误：`ERR-8093-DIAGNOSIS-EVIDENCE-CACHE-MARKER-CONTRACT-20260815`。
- 覆盖：诊断中文证据前端合同、代理注入的`20260814-evidence-cn-r2`缓存版本、诊断模型解析上下文及8093交接包忽略规则。
- 命令：`pytest -q tests/test_diagnosis_ai_analysis.py tests/test_diagnosis_review_contract.py tests/test_8093_handoff_package.py`。
- 成功信号：27项全部通过；不连接或修改220.12。

## ABC33 pSpace探尺料速

- 命令：`pwsh.exe -NoLogo -NoProfile -File .\tools\verify_abc33_probe_burden_rate.ps1`。
- 覆盖：提尺零位、小批识别、南北同期去重、料罐重量矿/焦分型、前后30分钟速率、A2/B4/B5缺数门禁及真实8093数据回放。
- 当前结果：36 passed；真实数据回放三个料速因子均为available。

## 8093维护交接包

- `pytest -q .\tests\test_8093_handoff_package.py`：验证清单schema、关键连接/守卫/服务/前端入口、所有源文件存在、无重复项、敏感路径排除和Git忽略规则。
- `pwsh.exe -NoLogo -NoProfile -File .\tools\build_8093_handoff_package.ps1`：复制当前工作区白名单文件，执行高置信敏感信息扫描，生成逐文件SHA-256，并回读ZIP逐项校验。
- `pwsh.exe -NoLogo -NoProfile -File .\tools\verify_pwsh7_utf8.ps1`：验证本机入口使用PowerShell 7 Core及无BOM UTF-8。
- 该组测试和构建均为本机操作；远端部署状态固定为`not_started`。

## TEST-8093-DIAGNOSIS-AI-JSON-DATETIME-20260811

- 对应错误：`ERR-8093-DIAGNOSIS-AI-JSON-DATETIME-20260811`。
- 红测：`test_abc33_score_source_is_json_serializable_for_ai_snapshot_store` 修复前精确失败为
  `TypeError: Object of type datetime is not JSON serializable`。
- 绿测：`python -B -m pytest -q -p no:cacheprovider tests/test_diagnosis_review_api.py tests/test_diagnosis_ai_analysis.py tests/test_diagnosis_review_contract.py --basetemp .tmp\pytest-diagnosis-json-boundary`，结果 `52 passed`。
- 边界：测试覆盖 ABC33 `evaluation_ts`、嵌套 `datetime`、`Decimal`、tuple 和
  `NaN`，并要求完整上下文可被 `json.dumps`。
- 语法：`python -B -m py_compile` 检查 `diagnosis_review.py`、
  `diagnosis_model_review.py`、`ollama_proxy_server.py`通过；
  `pwsh.exe -NoLogo -NoProfile -File .\tools\verify_pwsh7_utf8.ps1` 通过。
- 生产：诊断分析 `completed`、`attempt_count=1`；仅 8093 PID
  `19076→436`，后续验收性回滚恢复后最终 PID `9152`；8094/8768/8770/5432/11434 PID 不变。唯一 SSE
  `request_count=1`，keyword 证据 2 条，首 delta `5027.5ms`、总时长 `16885.6ms`，
  守卫失败计数清零且验收期间无自动重启。
- 回滚后运行态复核：正式版本经 120 秒冷却后自动恢复为
  `completed/attempt_count=1/has_analysis=true`，最近失败日志为空；只读预检确认服务
  Running、8093 HTTP 200、运行哈希匹配、keyword 证据 2 条及六个受控端口正常。

## ABC33 上下文助手

- `tests/test_abc_rule_explanation_context.py`：33项解释结构、语义、分数方向、门禁、JSON与哈希。
- `tests/test_abc_contextual_conversations_backend.py`：权威PG行、四表、只读接口、Prompt绑定和缓存写入。
- `tests/test_abc_contextual_assistant_concurrency.py`：六并发单航班与显式缓存提交。
- `tests/test_abc33_contextual_assistant_ui.py`：每卡唯一按钮、IDs-only事件、弹窗状态、单次SSE和六类来源筛选。
- 2026-08-11本机ABC33与既有助手相关结果：`62 passed`；完整85组合和生产真实SSE在上线阶段执行。

## TEST-QA-SESSION-LOGIN-BRIDGE-20260812

- `python -m pytest -q tests/test_qa_session_login_bridge.py tests/test_abc33_contextual_assistant_ui.py`：11 passed。
- `node 高炉前端数据/dashboard_build/scripts/build-dashboard.mjs --check`：JSX 提取与生产构建检查通过。
- `node tools/verify_qa_session_login_bridge.cjs <url> <report> 1366x768` 与 `390x844`：403→登录→bootstrap 通过，`login_posts=1`、`model_or_chat_posts=0`、登录框密码输入销毁。
- 生产冒烟使用真实 8093 HTML 和浏览器内模拟鉴权响应，不发送真实问答；模型健康另由 `/api/ollama/status` 验证。
## TEST-QA-SHARED-GUEST-MCP-FALLBACK-20260813

- 覆盖：同地址稳定共享房间、8093/8094默认隔离、消息时间戳、访客私有上下文拒绝、成功工具不重复调用模型、MCP 空失败与轮数耗尽执行单次无工具模型回答。
- 测试：[MCP降级](../tests/test_qa_mcp_model_fallback.py)、[共享访客](../tests/test_qa_shared_guest_mode.py)。
- 命令：`python -m pytest tests/test_qa_mcp_model_fallback.py tests/test_qa_shared_guest_mode.py -q`。
- 成功信号：8项以上全部通过，前端 Babel 检查通过，源码不再包含旧“数据库查询轮数超过上限”最终文案。
- `tests/test_qa_mcp_parallel_planning.py`：验证 5 轮/5 次默认限制、不同 MCP 服务并发、同一 stdio 服务串行、结果顺序稳定以及相关数值挑选 Prompt 合同。

## TEST-8093-GUEST-CONVERSATION-RECOVERY-20260814

- 覆盖：访客携带旧私有会话 ID 时直接重绑定固定共享会话，且不进入私有 owner 校验；登录用户提交其他 owner 会话时仍拒绝。
- 命令：`python -m pytest tests/test_qa_shared_guest_mode.py tests/test_qa_session_login_bridge.py -q`。
- 成功信号：13 项通过，`ollama_proxy_server.py` 编译通过；生产验收仅发送一次匿名 SSE，返回的 `conversation_id` 必须等于匿名 bootstrap 的共享会话 ID，且不得出现 `conversation_not_found`。

## TEST-8093-GUEST-UI-RECOVERY-20260814

- 覆盖：bootstrap 已是 `guest_shared` 时前端默认显示共享访客导航，不显示强制登录卡片；可选私有登录可打开并能继续匿名使用；恢复过程不自动发送聊天 POST。
- 聚焦命令：`python -m pytest tests/test_qa_shared_guest_mode.py tests/test_qa_session_login_bridge.py tests/test_8093_guest_ui_recovery_deploy_scripts.py -q -p no:cacheprovider`。
- 浏览器命令：`node tools/verify_8093_guest_frontend_matrix.cjs .tmp/8093-guest-ui-recovery-20260814/frontend_dashboard_v3.server.html .tmp/8093-guest-ui-recovery-20260814/browser-standard.json`。
- 生产冒烟：`node tools/probe_8093_guest_browser.cjs "http://10.30.220.12:8093/高炉前端数据/frontend_dashboard_v3.server.html#qa" .tmp/8093-guest-ui-recovery-20260814/production-browser-smoke.json`。
- 成功信号：16 项聚焦回归通过；标准矩阵 17/17；生产页面访客徽标可见、初始登录框不可见、可选登录和继续匿名均成功，bootstrap 为 HTTP 200 / `guest_shared`，页面与控制台错误为空。

## TEST-MCP-SEMANTIC-POINT-CATALOG-20260813

- `py tools/generate_semantic_point_catalog.py --check`：权威TSV与语义目录字节一致，153条且无重复ID。
- `pytest -q tests/test_semantic_point_catalog.py 高炉前端数据/智能助手/tests/test_business_object_catalog.py tests/test_qa_mcp_parallel_planning.py`：成功信号 `19 passed`。
- `py .codex/skills/agent-tool-capability-evaluation/scripts/evaluate_semantic_point_catalog.py`：成功信号 `ok=true/failure_count=0`；153/153覆盖、1118/1118别称、153/153唯一口语、6/6严格多变量。
- 边界：不访问生产数据或模型；可执行MCP、生产权限和实时数值必须另做受控抽样验收。

## TEST-MCP-SENSOR-REASONING-20260813

- `python -X utf8 tools/evaluate_8093_mcp_sensor_reasoning.py --dry-run`：只打印 T1/T2/T3，模型请求数为0。
- `pytest -q tests/test_evaluate_8093_mcp_sensor_reasoning.py`：验证工具层/答案层分离评分、极差/CV复算、
  跨源完整结果中的 Pearson r 与对齐样本读取。
- 生产单题使用 `--case T1`、`--case T2` 或 `--case T3`；每题恰好一次 SSE，禁止自动重试。
- 2026-08-13 实测：SSE 3/3、MCP 3/3、跨 MCP 并行 1/1、最终答案合同 0/3；原始摘要为
  `logs/mcp_sensor_reasoning_20260813/report.json`。工具成功不能覆盖答案不完整。

## TEST-MCP-TEMPLATE-LINES-20260814

- `python -X utf8 tools/evaluate_mcp_template_lines.py --list-only`：不发送模型请求，当前稳定清点
  160 行、125 unique ready、11 duplicate、24 skipped。
- `pytest -q tests/test_evaluate_mcp_template_lines.py tests/test_agent_tool_capability_skill.py`：验证源行号、
  占位符/重复、工具与答案分层、四类能力、检查点和同步清单；工作区 basetemp 结果 `7 passed`。
- Skill 官方结构校验：`quick_validate.py .codex/skills/agent-tool-capability-evaluation`，成功信号
  `Skill is valid!`。
- `pwsh.exe -NoLogo -NoProfile -File tools/sync_agent_tool_capability_evaluation_skill.ps1 -Action Verify`：
  要求 `file_count=7/identical=true/remote_write_performed=false`。
- 生产逐行结果：125 个唯一 SSE、禁止重试；工具合同 103/125、答案忠实 28/123、综合 24/125、
  静压力 `TaskGroup` 错误 2 条。完整报告见 `logs/mcp_template_line_eval/report_full_20260813.json`。

## TEST-MCP-AGENT-GOLDEN-SUITE-20260814

- 权威清单：`PT/智能体工具能力金标任务清单.v1.json`；14 项覆盖单工具、多工具、并行、多轮、
  依赖、无关工具、歧义、未知对象、超时、部分失败、全失败、对抗输入、确定性计算和工具结果注入。
- `python tools/evaluate_mcp_gold_tasks.py --validate --write-catalog-markdown`：成功信号
  `ok=true/case_count=14`，Markdown 中记录当前 JSON SHA-256。
- `python tools/evaluate_mcp_gold_tasks.py --execute --mode mocked --pass-k 5 --concurrency 6`：
  成功信号 `runs=70/passed=70/failed=0/errors=0`。该模式只证明合同、故障夹具和 oracle，
  不代表生产 MCP 或模型实测通过。
- 聚焦回归：`python -m pytest -q --basetemp .pytest_tmp_mcp_gold tests/test_mcp_gold_tasks.py
  tests/test_mcp_lifecycle_diagnostics.py tests/test_mcp_evidence_formatter.py tests/test_cross_source_mcp.py
  tests/test_evaluate_mcp_template_lines.py tests/test_qa_mcp_parallel_planning.py tests/test_qa_mcp_model_fallback.py`；
  加上部署合同、唯一 SSE 验收器和炉温同步回归，2026-08-14 成功信号 `87 passed`。
- 生产单工具验收：执行 ID `mcp-gold-20260814-1035-r3`；恰好一次 SSE 调用
  `gl02-data/query_gl02_sensors(latest, P_top)`，事件包含
  `preparing/prepared/tool_start/tool_result/delta/final/done`，并返回值、单位、数据时间、质量、采集时间
  和只读来源。`request_count=1`，无自动重试。该题命中确定性传感器路由，服务端未提供底层模型
  调用计数，因此不得把 HTTP 200 或 SSE 成功等同为一次模型调用。
- 生产逐条结果：9 项 `passed`、GOLD-005 为 `oracle_invalid` 但“不猜测/不启动下游”能力通过；
  GOLD-009/010/011/014 因生产未开放故障注入而为 `not_supported`，对应 mocked 合同 4/4 通过。
  不把 mocked 通过写成生产实测通过。汇总见
  `logs/mcp_gold_live_20260814/final_summary.json` 与 `final_summary.md`。
- GOLD-004 复用已经发出的两轮真实响应离线重评分，`network_request_count_during_rescore=0`；
  结果见 `logs/mcp_gold_live_20260814/GOLD-004.rescored.json`。
- 最终聚焦回归：
  `pytest -q tests/test_mcp_gold_tasks.py tests/test_cross_source_mcp.py tests/test_mcp_gold_runtime_boundaries.py tests/test_mcp_gold_sse_once.py tests/test_mcp_gold_deploy_scripts.py`，
  成功信号 `82 passed`；远端最终 HEAD `67d2434cbbb69591ff8e35d4027fd47acfa37850`、工作树 clean。

## TEST-MCP-EXTENDED-PRODUCTION-REGRESSION-20260814

- 关键稳定性：GOLD-001/002/003/004/005/013 各运行 5 次。零请求重评分后的结果为
  `25 passed / 5 oracle_invalid / 0 failed`；5 个 `oracle_invalid` 全部是 GOLD-005 的不存在炉次
  `072`，实际能力合同均满足“不猜炉号、不启动依赖下游”。
- 点位覆盖：14 个标准变量 × 最新值/1小时统计/2小时趋势，共 42 个真实生产问法，42/42 通过；
  p50 `1395.8ms`、p95 `1621.6ms`。变量覆盖 `P_top/T_top/DP_total/P_blast_cold/P_blast/
  T_blast/PI/L/L_south/L_north/PCI_rate/PCI_set/O2_rate/Q_O2`。
- 并发：6 个不同点位同批提交，6/6 通过、p95 `8221.2ms`；总单题耗时之和明显大于批次墙钟时间，
  证明请求存在真实重叠；同一 GL02 stdio 服务仍按安全合同串行，没有死锁、PoolTimeout、重复调用
  或答案串线。
- 多轮与跨源：GOLD-004 连续两轮 5/5；GOLD-002/003 跨 GL02 与 IMES 共 10/10，实际调用两个服务。
- 隔离：共享访客与已登录 owner 的会话哈希不同且模型请求为 0；由于生产仅一个认证身份，
  “两个 authenticated owner”记为 `not_tested`。
- 故障：在远端仅回环临时服务 `127.0.0.1:18094` 执行 GOLD-009/010/011/014，真实模型最终回合
  4 次、4/4 通过、自动重试 0、生产故障请求 0；测试后端口关闭。MCP 故障输入是受控夹具，
  没有使生产数据库或 8093 主服务进入失败状态。
- 请求账本：生产真实 SSE `83`，真实 `tool_start` `90`，自动重试 `0`；故障预览另有真实模型请求
  `4`。总报告为 `logs/mcp_extended_20260814/final_report.json` 与 `final_report.md`。
- 聚焦回归：金标、扩展评测器、故障预览、跨源、运行边界、SSE 和部署合同共 `91 passed`；新增
  Python 文件 `py_compile` 通过；项目与全局评估 skill `file_count=7/identical=true`。

## TEST-MCP-SPOKEN-PRODUCTION-REGRESSION-20260814

- 题集：`PT/智能体工具能力口语化生产回归.v1.json`；42 个 prompt 均不得出现完整 153 点位目录
  中的任何标准 `object_id`，只使用“炉顶压力、四个顶温的平均值、风温、南尺、实际喷煤量、
  鼓风富氧比例”等现场表达。独立 A-H 方位字母允许，英文/下划线组合技术名禁止。
- 静态合同：`pytest -q tests/test_evaluate_mcp_extended_production.py tests/test_agent_tool_capability_skill.py`，
  成功信号 `8 passed`；明确验证“顶温 A 点/7 层 A-H”允许，`P_top/T_top_A/DP_total/L/PI` 和
  未知 `P_top_gas_X` 在发请求前拒绝。
- 生产执行：42 次串行 SSE、自动重试 0；结果 `36 passed / 6 failed / 0 errors`，p50
  `1139.9ms`、p95 `29513.7ms`。
- 路由：39/42 走确定性传感器路由；3 个 `L/雷达探尺` 问题走模型规划，其中一小时统计耗时
  `75943.7ms`。所有 42 题均收到 `final/done`，失败属于语义/证据合同，不是网络或执行错误。
- 失败对象：`T_top` 0/3，原因是回答四个分点而非派生平均；`L` 0/3，原因是单位元数据和工具路径
  合同不完整。其余 12 个对象 36/36。
- 原始证据：`logs/mcp_spoken_20260814/report.json`、`report.md` 和逐题 `checkpoint.jsonl`。

## TEST-MCP-BODY-LAYER-STATISTICS-20260814

- 逐层生产探针：纯中文询问 2026-08-14 08:00–09:00 的 7–13 层 A–H 层平均、极差、变化量、
  STDDEV_POP 和 15 分钟滚动标准差；一次 SSE、无重试，结果 5 个工具调用、`156890.7ms`，只完成
  第 7 层 A–E，合同失败。
- 单点生产探针：纯中文询问同一时段第 10 层 C 点统计；一次 SSE、无重试，重复调用同一工具 2 次、
  `29957.2ms`。工具 count/min 与答案 count/min 冲突，最终答案忠实度失败。
- 本机修复验证：相关 MCP/QA/部署合同累计先后 `78 passed`、`85 passed`；时间窗修复后聚焦
  `77 passed`，最终部署与炉体统计合同 `12 passed`。Python 编译、PowerShell 7 UTF-8 和全部新增
  部署脚本 AST 检查通过。
- 生产验收：逐层题和单点题各 1 次真实 SSE，均恰好 1 个
  `gl02ext__query_body_temperature_statistics`，事件包含
  `start(preparing) → start(prepared) → tool_start → tool_result → delta → final → done`，
  `request_count_total=2`、`model_request_count=0`。
- 时间窗验收：`最近一小时 + 15 分钟滚动` 的实际总窗为 14:04–15:04，滚动窗保持 15 分钟；
  7–13 层完整返回 7 行，每层 60/61 个对齐/期望分钟。
- 运行边界：8093 PID `14380 → 9468`；8094/8768/8770/5432/11434 PID 均不变；守卫失败计数 0，
  keyword 检索返回 2 条证据，仅驻留 `chiqiong-blast-furnace:latest`。
- 当前状态：`passed_in_production`；生产 Git 为 `849d9554060f7c1252722e8394a9cb224ff13488`。
- 人工回归暴露的答案完整性缺陷已加入本机测试：三个实际失败的纯中文逐层问法必须命中一次复合
  工具；第 12 层 A–H 必须开启逐方位统计；八个权威 tag 必须唯一；超过通用结果上限的结构化统计
  必须保持可解析；嵌套 `result` 载荷必须输出不同的方位值。最终相关 MCP/QA/领域路由/DAG 优先级/
  部署合同共 `116 passed`。
- 直接复合 MCP（不经过模型和 QA 路由）实测最近一小时 7–13 层 A–H：`3248` 行、7 层均
  `58` 个完整对齐样本，耗时 `2520.9ms`，来源 `bf_sensor.one_minute_values`。
- R4/R5 生产验收均失败并自动回滚，分别定位“中文层号未选择扩展 MCP”和“跨源 DAG 抢在复合
  计划前展开 56 点”；生产答案完整性状态仍为待部署，不复用此前 `passed_in_production` 结论。

### 本机执行轨迹与受控模型解释增量

- `tests/test_body_temperature_layer_statistics.py` 新增中文数字层号、数据库批量函数只调用一次、
  `public_trace` 脱敏字段、模型新增数字拒绝，以及从自然语言到单次复合 MCP、六段执行事件和最终
  解释的端到端模拟。
- `tests/test_qa_tool_execution_trace_ui.py` 验证前端分发 `trace/tool_start/tool_result/
  analysis_start/analysis_result`，当前 `QaTab` 接线完整，并且渲染器只读取 `public_trace`。
- 聚焦命令：

  ```powershell
  $env:PYTEST_DISABLE_PLUGIN_AUTOLOAD='1'
  python -m pytest tests/test_body_temperature_layer_statistics.py tests/test_semantic_point_catalog.py tests/test_qa_tool_execution_trace_ui.py -q
  ```

  成功信号：`23 passed`。
- 扩展回归命令覆盖并行规划、工具失败降级、证据格式、金标运行边界和共享访客；成功信号：
  `62 passed`。`python tools/verify_8093_frontend_production_build.py` 必须返回 `ok=true` 和
  `contractMatch=true`。
- 本机真实只读探针：

  ```powershell
  python tools/probe_body_temperature_statistics_mcp.py --server "高炉前端数据/智能助手/mcp/bf_data_extended_mcp_server.py" --minutes 60 --include-points
  ```

  2026-08-14 18:11 的成功信号为：恰好一次复合 MCP 调用、`layer_count=7`、`point_count=56`、
  `raw_row_count=3304`、7 层各 `59` 个对齐样本、`elapsed_ms=3327.2`，且
  `production_write_performed=false`。该探针失败时不得自动重发。
- 生产验收：先审查并保留远端 `32130a5` 匿名访客 UI 更新，再执行密封增量部署
  `body-temperature-trace-20260814-2046-r3`。唯一一次真实 SSE 的事件为
  `start(preparing) → start(prepared) → trace ×2 → tool_start → tool_result → analysis_start →
  analysis_result → delta → final → done`；`request_count_total=1`、`model_request_count=1`、
  工具调用数为 1，返回 56 点、3304 行、7 层各 59/61 个对齐/期望分钟，答案非空。
- 部署边界：8093 PID `9616 → 4928`；8094=`5912`、8768=`18648`、8770=`3732`、
  5432=`12372`、11434=`18704`、8892=`404` 均保持不变；守卫失败计数为 0。
- 浏览器生产冒烟：共享访客标识可见、无需登录、控制台/页面错误均为 0；未追加模型请求。
- 生产版本：Git `5d23c0e5e2456c597ad9ba5a9a8c03627c2c5ae9`，标签
  `prod-8093/20260814-body_trace-5d23c0e5e245`。

## REQ-QA-MCP-VISUAL-RECOMMENDATIONS-20260814

- 聚焦合同：

  ```powershell
  $env:PYTEST_DISABLE_PLUGIN_AUTOLOAD='1'
  python -m pytest tests/test_qa_mcp_visual_recommendations.py tests/test_qa_tool_execution_trace_ui.py tests/test_body_temperature_layer_statistics.py -q
  ```

  成功信号：`24 passed`。覆盖“矩阵热度图”单工具路由、7–13 层/A–H 参数、同源 PNG 安全边界、
  12 条常用 MCP 模板、滚动列表、本浏览器固定/自定义持久化、final 后相关问题以及单次 chat POST。
- 前端发布构建：`python tools/verify_8093_frontend_production_build.py` 返回 `ok=true`、
  `contractMatch=true`、`changedPixelRatioOver4=0.0`。
- 开发阶段单视口：Chromium `1366×768` QA 路由 `1/1 passed`；验证模板可见、列表可滚动、添加
  自定义问题后同时写入 custom/pinned、相关问题事件可见、无横向溢出和底栏遮挡，
  同源 PNG 在答案内可见，`real_sent=0`。报告：
  `logs/qa_mcp_visual_recommendations_1366x768_final2/report.json`。
- 本轮没有运行 quick/standard/full 矩阵，符合 `OPS-UI-VIEWPORT-TWO-STAGE-20260814`；发布候选冻结后
  再按风险选择完成阶段矩阵。

## ERR-QA-HTTP400-FURNACE-ANALYSIS-20260814

- 静态/后端合同：`tests/test_abc33_contextual_assistant_ui.py` 与
  `tests/test_abc_contextual_conversations_backend.py` 共 `32 passed`；新增测试从 Python 后端常量
  提取固定首问，并验证 JavaScript 初始 `streamQuestion` 使用完全相同的文字。
- JavaScript：`node --check 高炉前端数据/assets/bf-abc33-assistant-dialog.js` 通过。
- 本机浏览器：参数优化页 `quick` 共 4 个组合通过——Chromium `1366×768`、`390×844`，
  Firefox/WebKit `1366×768`；控制台/页面错误为 0，真实模型请求为 0。
- 生产状态：2026-08-14 已通过受控部署与一次真实首问验收。请求数 `1`，不再返回 HTTP 400，
  SSE 为 `preparing → prepared → delta → final → done`，答案 `679` 字；8093 PID
  `240 → 15392`，8094/8768/8770/5432/11434 PID 均保持不变。Git 提交 `d24543a`，标签
  `prod-8093-abc33-http400-20260814-r2`。
- 当前复核：生产 HEAD 已前进到 `d153ed5`，但 `d24543a` 仍是其祖先且标签未漂移；HTTP 实际 JS
  SHA-256 仍为 `CEAEA43D…E39C`。第二次真实固定首问仍只发送 `1` 次，SSE 完整、答案 `720` 字，
  8093 PID `15392` 与五个保护 PID 在复核前后均不变；因此判定为已修复的生产 no-op，无需重复部署。

## REQ-QA-MESSAGE-COPY-20260814

- 聚焦合同：

  ```powershell
  $env:PYTEST_DISABLE_PLUGIN_AUTOLOAD='1'
  python -m pytest tests/test_qa_message_copy_ui.py tests/test_qa_mcp_visual_recommendations.py tests/test_qa_tool_execution_trace_ui.py -q
  ```

  成功信号：`14 passed`。覆盖用户/助手双角色标签、可访问名称、可见正文提取、时间与隐藏内容排除、
  同源 MCP 图表地址、Clipboard API/旧浏览器回退、成功/失败反馈和复制路径零 QA 请求。
- 开发阶段单视口：

  ```powershell
  node tools/verify_abc_contextual_assistant_viewports.cjs --base-url http://127.0.0.1:18093/frontend_dashboard_v3.server.html --output-dir logs/qa_message_copy_1366x768 --engine chromium --route qa --viewport 1366x768 --timeout-ms 30000
  ```

  成功信号：`1/1 passed`，`copyQuestionVisible=true`、`copyAnswerVisible=true`、
  `copiedQuestionBody=true`、`copiedAnswerBodyAndChart=true`、`real_sent=0`，且控制台/页面错误为 0。
- 发布构建：`python tools/verify_8093_frontend_production_build.py` 返回 `ok=true`、
  `contractMatch=true`、`changedPixelRatioOver4=0.0`。
- 本轮处于正常开发阶段，只运行 Chromium `1366×768` 一个代表视口，没有提前运行完成阶段矩阵。

## REQ-QA-LOCAL-RECOMMENDATION-PRESERVATION-20260814

- 聚焦命令：

  ```powershell
  $env:PYTEST_DISABLE_PLUGIN_AUTOLOAD='1'
  python -m pytest tests/test_qa_mcp_visual_recommendations.py tests/test_qa_message_copy_ui.py tests/test_qa_tool_execution_trace_ui.py -q
  ```

  成功信号：`15 passed`。新增合同验证“原有常用问题”先于“常用 MCP 模板”，动态 `props.common`
  与固定 `mcpCommon` 分开传递，滚动区有 `tabIndex=0` 和可访问名称，禁止恢复数组拼接。
- Chromium `1366×768` 单视口：报告
  `logs/qa_local_recommendations_1366x768_final/report.json` 为 `1/1 passed`；
  `originalCommonVisible/mcpCommonVisible/promptScrollerKeyboardAccessible/
  promptScrollerManuallyScrollable` 全部为 `true`，`real_sent=0`，控制台和页面错误为 0。
- 发布构建：`python tools/verify_8093_frontend_production_build.py` 返回 `ok=true`、
  `contractMatch=true`、`changedPixelRatioOver4=0.0`。
- 本轮仍处于正常开发阶段，没有运行 quick/standard/full 完成阶段矩阵。

## REQ-FURNACE-RULE-FORMULA-HANDBOOK-20260814

- 生成Markdown：

  ```powershell
  D:\ProgramData\anaconda3\python.exe tools\generate_furnace_rules_formula_handbook.py --output docs\炉况诊断8类与ABC33规则数学公式手册_20260814.md
  ```

  成功信号：`ok=true`、`rules=41`。
- PowerShell 7导出PDF：

  ```powershell
  pwsh.exe -NoLogo -NoProfile -File tools\export_furnace_rules_handbook_pdf.ps1 -MarkdownPath docs\炉况诊断8类与ABC33规则数学公式手册_20260814.md -PdfPath docs\炉况诊断8类与ABC33规则数学公式手册_20260814.pdf
  ```

  成功信号：JSON `ok=true`、运行时`7.6.4`、PDF大于10KB。
- 结构与PDF文本验证：

  ```powershell
  C:\Users\hmw20\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe tools\verify_furnace_rules_formula_handbook.py --markdown docs\炉况诊断8类与ABC33规则数学公式手册_20260814.md --pdf docs\炉况诊断8类与ABC33规则数学公式手册_20260814.pdf
  ```

  本次成功信号：`legacy_rules=8`、`abc_rules=33`、`pdf_pages=55`，正常顺行在第2页、B4在第26页、
  C11在第54页；封面、B4和C11页面另外完成PNG视觉检查，中文与表格可读。

## REQ-QA-ROUTING-ASSISTANT-UPDATE-20260916

- 构建精确候选：

  ```powershell
  python tools/build_qa_routing_candidate.py --proxy-baseline <V2代理基线> --selection-baseline <V2工具选择基线> --output .codex_runtime/qa-routing-v3/candidate
  ```

  成功信号：两个基线 SHA-256 精确匹配；`syntax=passed`、`production_changed=false`。
- 聚焦测试：

  ```powershell
  python -m pytest tests/test_qa_task_plan.py tests/test_qa_evidence_claims.py tests/test_qa_routing_candidate.py tests/test_qa_evidence_policy.py -q
  ```

  本次成功信号：`44 passed`。覆盖公开失败模板的文档/历史/实时三联路由、工具域隔离、JSON围栏、
  混合代码问题、合理舍入、错对象和生命周期异常后的事实保留。
- 回归合同与既有目录：

  ```powershell
  python tools/evaluate_qa_task_plan_contracts.py
  python tools/qa_regression.py
  python tools/evaluate_mcp_gold_tasks.py --validate
  ```

  本次成功信号：TaskPlan `ok=true checked=15`；合成问答 `corpus_valid case_count=32`；MCP 金标
  `ok=true case_count=14`。
- 生产逐题复测：

  ```powershell
  python -X utf8 tools/run_qa_failed_retest_once.py --help
  ```

  实际执行使用新建的 Git 忽略输出目录、显式 `--execute` 和逐题不可覆盖 claim。16 道既有失败题共
  POST 16 次，自动重试 0；14 次完整 `done`，1 次明确模型未驻留 SSE 错误，1 次同源客户端合同拒绝。
  人工审阅为通过 2、部分通过 6、失败 7、客户端合同阻断 1。脱敏逐题结果见
  [routing_retest_review_20260916.json](../tests/qa_regression/routing_retest_review_20260916.json)，原始回答不得提交。

## TEST-QAOPT-R03-MULTI-ENTITY-20260916

- 构建：

  ```powershell
  python -X utf8 tools/build_qa_routing_v4_candidate.py --v3-candidate .codex_runtime/qa-routing-v3/candidate --mcp-baseline .codex_runtime/qa-routing-v4/production-baseline/bf_data_mcp_server.py --output .codex_runtime/qa-routing-v4/candidate
  ```

- 聚焦验证：

  ```powershell
  python -m pytest tests/test_qa_entity_resolution.py tests/test_qa_task_plan.py tests/test_qa_routing_v4_candidate.py -q -p no:cacheprovider
  ```

- 成功信号：`19 passed`；V4候选固定到已验收V3代理哈希。三气体解析为
  `CO_top/CO2_top/H2_top`，炉喉`A-D`展开四点，南北探尺按用户顺序保留两个对象，未知对象不生成虚构ID。
- 生产状态：本机候选验证通过，尚未部署；部署后每道代表题只允许一次POST，禁止自动重放。

### QAOPT-R04/R05：窗口及报表工作流回归

- 2026-09-16本机相关回归98 passed；命令、环境和完整限制见[V4交接](handoffs/2026-09-16-qa-routing-v4-temporal-report-local.md)。
- [时间窗测试](../tests/test_qa_time_window_plan.py)：独立窗口成员集合、算术复算、基线时间/对象/质量、部分失败不重放。
- [报表依赖测试](../tests/test_qa_report_workflow.py)：真实原题TaskPlan门禁、目录→正文顺序、失败停止、路径和代码限制。
- [中文截断测试](../tests/test_qa_report_excerpt_contract.py)：执行真实本机及生产差分候选读取函数；中文全文不误报，实际截断仍标记。
- [候选接缝测试](../tests/test_qa_routing_v4_candidate.py)：实际代理AST接缝与精确生产基线；不导入无关生产模块。
- 不包含生产复测、模型驻留竞争或并发通过证明；非空不记语义通过。
# QA V4 生产复测补充（2026-09-16）

REQ-QA-FULL-ISSUE-INVENTORY-20260916：六题各一次POST，3通过/1部分/2失败；
见[生产交接](handoffs/2026-09-16-qa-routing-v4-production-and-retest.md)和
[脱敏审阅](../tests/qa_regression/routing_v4_production_review_20260916.json)。
`run_qa_failed_retest_once.py`仅在POST claim创建之前对就绪GET最多重查三次，记录四项布尔状态；
所有已发送或发送不确定的问题仍禁止自动重放。
## QA V5 回归补充（2026-09-16，候选）

103项聚焦pytest通过，覆盖实际代理/MCP接缝、两owner SQL、当前消息排除、通配符、未知模型、
超时、取消和真实报表摘要结构；TaskPlan15/15，MCP金标14/14仅结构验证。
新增`test_qa_routing_v5_candidate.py`、`test_qa_history_projection.py`、`test_qa_model_readiness.py`。
生产验收待受控部署；详细范围见[V5交接](handoffs/2026-09-16-qa-routing-v5-local-candidate.md)。

## QA V5生产与V6回归（2026-09-16）

V5真实八题2通过/4部分/2失败，七题SSE落盘，第八题只读恢复答案而未恢复事件。V6共106项聚焦回归通过；新增`test_qa_v6_contracts.py`检查有限值/来源/对象/单位/窗口、质量缺项、截断压缩和继承；`test_qa_retest_persistence.py`复现元数据缺少时已发送结果保全。生产Python3.11只编译不执行模型，临时索引原始/语义275行一致，没有换行迁移。[权威交接](handoffs/2026-09-16-qa-routing-v5-production-and-v6-candidate.md)。


### V23真实复测冻结补记（2026-09-17）

407题已发8题：2通过、3部分、3失败；399明确未发送，模型身份未核实中断。只计算观察小样本，不发布全量准确率。详情见[逐题核验](handoffs/2026-09-17-qa-v23-single-window-routing.md)与[受控模型窗口/V24方案](handoffs/2026-09-17-qa-model-window-and-v24-plan.md)。


### V23续跑终止补记（2026-09-17）

在只读证明未发送的范围内续跑r2，首题TPL-A60B0CD794D49E48返回真实顶压值但仍部分完成，随后身份不可核实中断。两轮累计9次单POST，2通过、4部分、3失败；398原失败题明确未发送，逐题记录为模型依赖阻断。身份稳定7题中的2通过仅是小样本观察，不代表全量准确率。下一步需受控固定模型窗口，原9题不自动重放。

## V25智能助手更新与首次全题统计（2026-09-17）

状态：V25已部署；首次1233题判定已合并。最新权威方案见 [33项优化与核对方案](handoffs/2026-09-17-qa-full-optimization-plan.md)。

明确钟点/跨午夜窗口不回落最近一小时，历史记录和质量保留；18点绘图已进入正确路由，但生产工具只返回16点且生命周期降级遗漏图，仍待修复。

本机159检查、14黄金题结构、4写24读/490 AST/22标记、8093受控发布和CAS通过。新版822原失败/部分题复测只发1题且失败，821题证明未发。首次完整正确269/可判1091=24.66%，不能报告优化后全量准确率。

## V26图表证据修复及固定模型复测（2026-09-17）

状态：V26已部署，174本机检查和独立审查通过；822原失败/部分题发送前因Qwen身份变化拦截，零发送。线上语义修复效果未确认。
需求：REQ-QA-CHART-COVERAGE-20260917、OPS-QA-FIXED-MODEL-WINDOW-20260917。
最新权威来源：[V26部署与固定模型复测方案](handoffs/2026-09-17-qa-v26-model-window.md)、[33项优化方案](handoffs/2026-09-17-qa-full-optimization-plan.md)、[V26生产哈希](../tests/qa_regression/routing_v26_production_20260917.json)、[822未发题证据](../tests/qa_regression/routing_v26_unattempted_dependencies_20260917.json)。
执行器见 [窗口owner](../tools/run_qa_fixed_model_window.ps1)、[独立启动器](../tools/start_qa_fixed_model_window.ps1)、[只读准备器](../tools/prepare_qa_fixed_model_window.py)；11项真实控制流/截止预算隔离测试通过，另有8项身份/续跑合同回归通过。窗口仅本机准备，计划任务操作尚未授权执行；继续保留V25历史记录，不以非空答复计算正确率。

## 历史：模型恢复稳定性本机候选（2026-09-17，已取代）

需求OPS-QA-MODEL-REPAIR-STABILITY-20260917，关联QAOPT-O01。健康批准驻留优先、候选失败alias/state恢复、最长15分钟冷却、暂停失败恢复责任及Switch实际alias回滚已形成r2本机候选；32其他函数和顶层mutex/dispatch保持，26隔离回归与独立代码审查通过，未部署管理器。
当前生产仍为V26，822失败/部分题均未发送。真实任务/模型验收和管理器变更独立授权仍待完成；本机检查不等同线上语义成功。
权威来源：[候选和26项证据](handoffs/2026-09-17-qa-model-repair-stability.md)、[候选冻结元数据](../tests/qa_regression/model_repair_stability_candidate_20260917.json)、[构建器](../tools/build_qa_model_repair_candidate.ps1)、[聚焦回归](../tests/test_qa_model_repair_policy.py)。

## REQ-QA-SINGLE-BASE-MODEL-20260917：固定同一底座

状态：本机候选52项检查及独立审查通过，未部署；生产仍V26。唯一e4ad74…底座，Switch/替代fallback禁用，每次模型POST与复测plan核验相同digest；旧双批准池窗口已停用。恢复任务仍曾自行漂移版本0，不能声称生产已锁定。管理器/计划任务维护独立授权，安装失败不能再启用旧切换策略。
当前权威：[单底座合同、代码和验收方案](handoffs/2026-09-17-qa-single-base-model-policy.md)、[候选冻结证据](../tests/qa_regression/single_base_model_candidate_20260917.json)。前代r2批准fallback候选仅保留历史复现，禁止部署。

## REQ-QA-STATISTICS-EVIDENCE-20260917：V28统计证据与答复

状态：本机候选，生产仍为V26；最后核对2026-09-17。关联QAOPT-E01/E02/E03/E04/E05。
V28保留固定同一底座身份检查，仅修复统计预取、证据完整性和确定性答复三个函数。完整保留stddev/单位/质量及来源窗口；非零微量不舍入成0；缺单位仅继承现有精确合同并披露，Held端点不证明整窗质量或炉况稳定。直接答复同样校验请求对象、来源和时间窗，未核实不得输出正式STDDEV/CV/趋势。没有新增API或配置，不改模型、生产数据库或ABC33合同。
权威：[实施、回归及未完成项](handoffs/2026-09-17-qa-v28-statistics-evidence.md)、[机器检查证据](../tests/qa_regression/statistical_evidence_candidate_20260917.json)、[实际函数回归](../tests/test_qa_statistics_evidence.py)。本机通过不得写成线上准确率提高；822原失败/部分题尚未发送。

## REQ-QA-FINAL-COMPLETION-20260917：V29最终答复完成状态

状态：本机r2候选、92项聚焦回归及独立审查通过，未部署；最后核对2026-09-17，关联QAOPT-E05/O04/T03。
统一识别模型截断、未知终止、空答案和末行空标题；工具后解释未完成时保留事实并标部分，MCP降级仍最多一次无工具回合。普通免工具问答保留原有一次有界补答；JSON/SSE核对实际最终answer，图表/文档追加不能擦除已记录的空标题。固定底座、V28统计合同及其他AST保留，无新增配置、工具重试或数据库变更。
权威：[实施、实际检查及剩余边界](handoffs/2026-09-17-qa-v29-final-completion.md)、[候选机器证据](../tests/qa_regression/final_completion_candidate_20260917.json)、[真实函数回归](../tests/test_qa_final_completion.py)。处理器接缝为AST与合同检查，尚未执行线上处理器/822原题语义验收；这些问题未销项。

## REQ-QA-WINDOW-QUALITY-20260917：V30质量窗口证据

状态：本机r2候选、独立审查通过，未部署；最后核对2026-09-17，关联QAOPT-E02/E04/E06。
数据库在原统计SELECT同一tag/窗口中追加质量计数，非空数值为分母，空值行单列；原参数、查询次数和数值公式保持。pSpace/派生只声明实际返回样本，不声称整窗完整。质量总和、类型、schema/basis及请求窗口必须匹配，未知标签不猜测为Good，不由Held/Bad或派生标记判正式稳定/风险等级。固定同一底座与V29完成状态保持，没有新配置或数据库迁移。
权威：[实施、质量范围与验收边界](handoffs/2026-09-17-qa-v30-window-quality.md)、[机器证据](../tests/qa_regression/window_quality_candidate_20260917.json)、[实际MCP函数回归](../tests/test_qa_window_quality.py)。本机合同尚未在真实数据库或原822题验证，不标线上有效或销项。


## REQ-QA-RENDERER-CONTRACT-20260917：V31答复格式与字段兼容

状态：本机冻结候选、126项相关回归及独立审查通过，未部署；最后核对2026-09-17，关联QAOPT-E02/E03/E05。
传感器字符串列表按实际工具拆分、去重，保持80个上限，请求与外层结果规范化列表必须一致；顶层字符串和非字符串项不放宽为合法调用。单位仅从明确元数据绑定继承规范合同并披露，原单位优先、不换算或猜描述。异常结果容器逐项明示并保留相邻有效事实；对象、来源、只读策略与窗口门禁保持。仅修改一个代理函数和统计证据模块，无新增API、配置、工具或模型回合，固定同一底座保持。
权威：[确认缺陷、程序与未完成验收](handoffs/2026-09-17-qa-v31-renderer-contract.md)、[机器回归证据](../tests/qa_regression/renderer_contract_candidate_20260917.json)、[实际冻结函数回归](../tests/test_qa_renderer_contract.py)。本机通过不能用于线上准确率或问题销项；禁切换管理器安装、8093部署及822原题复测仍待完成。


## REQ-QA-LATEST-EVIDENCE-20260917：V32最新值与完成合同

状态：本机r2冻结候选、284项相关回归及独立审查通过，未部署；最后核对2026-09-17。
实际284 passed：新latest证据46、既有读取/禁代码72、renderer/统计/质量126、完成状态40；r1/r2独立审查PASS。回归含旧错对象显示、typed source与溢出反例、日期缺时分、未登记单位、pSpace时间标记、混时/缺组件派生值及工具出口表达式。合成数据/真实函数接缝不代替完整线上链路及822题语义验收。
权威：[确认缺陷、实现及生产依赖](handoffs/2026-09-17-qa-v32-latest-evidence.md)、[机器证据](../tests/qa_regression/latest_evidence_candidate_20260917.json)、[实际函数回归](../tests/test_qa_latest_evidence.py)、[九条提出归类补充](../tests/qa_regression/unmapped_triage_supplement_20260917.json)。本轮0线上问题，不改首次1233题判定，822原题复测仍待完成。

## REQ-QA-SINGLE-BASE-MODEL-20260917：强约束再次复核

状态：本机47项通过；最后核对2026-09-17；生产管理器安装未完成。历史双底座窗口的六种真实PowerShell隔离场景均必须拒绝执行且无任务/HTTP操作，保留截止时间与请求预算测试。固定身份、禁切换管理器、退役窗口及安装事务共47项通过。生产只读快照显示固定名称未匹配冻结摘要、驻留为空，未使用其他底座继续测试。
权威：[本轮缺陷及可复现命令](handoffs/2026-09-17-qa-fixed-base-constraint-recheck.md)、[退役窗口回归](../tests/test_qa_fixed_model_window.py)。本机通过不代表生产已锁定，也不代表原题准确率提高。

## 2026-09-17：只读启动与制度短条款回归

151 passed：52项[只读审计](../tests/test_qa_readonly_pg.py)、55项[原书标题与源解析](../tests/test_three_rules_heading_boundaries.py)、44项既有文档合同。真实数据库默认/当前事务均readonly=on；原DOCX旧解析与生产96fd哈希相同，修复后fbf583哈希不同、两制度章补回123片段。比较旧authority退出1是必须受控重建知识库的信号，不放宽为语义通过。
权威：[命令、逐类检查与未完成验收](handoffs/2026-09-17-qa-readonly-audit-and-source-repair.md)、[机器证据](../tests/qa_regression/readonly_audit_source_repair_20260917.json)。独立审查PASS；未生产写入、未复问原题、不更新线上准确率。

## REQ-QA-SOURCE-SCOPE-20260917：独立源及冻结回归

实际202 passed：新增[原始位置/范围mutation](../tests/test_qa_source_scope_contract.py)、[身份与私有冻结边界](../tests/test_qa_source_candidate_freeze.py)，并覆盖标题、启动只读和既有文档合同。实际原书28章/4663item、5587chunk绑定通过，缺失/额外item为0；topic完整性及语义不宣称通过。
权威：[可复现命令与候选hash](handoffs/2026-09-17-qa-independent-source-scope.md)、[机器证据](../tests/qa_regression/source_scope_candidate_20260917.json)。独立审查PASS，0数据库/模型/问题操作，822原题未复测。

## REQ-QA-KEYWORD-SOURCE-RELEASE-20260917：源绑定反例及准备验收

实际253 passed：新增[51项绑定/准备回归](../tests/test_qa_knowledge_source_binding.py)，覆盖固定SHA/JSON字段、集合/内容/所有检索元数据、可选岗位/规程/块位置、文档来源路径、旧CAS漂移及私有输出。真实原书5587规划行准备检查通过，database_snapshot_verified=false。初次独立审查FAIL后补齐元数据检查，最终PASS；未执行DB发布/回滚事务，不能代替其验收。
权威：[复现命令、冻结hash和剩余验收](handoffs/2026-09-17-qa-keyword-source-release-preparation.md)、[机器证据](../tests/qa_regression/keyword_source_release_preparation_20260917.json)。0生产写入/模型/问答操作，不更新线上准确率。

## REQ-QA-KEYWORD-SOURCE-TRANSACTION-20260917：真实隔离PG事务验收

状态：本机271项及独立静态复审通过，2026-09-17核对；生产未应用。
实际271 passed（49.28秒），其中[事务18项](../tests/test_qa_keyword_source_transaction.py)使用原生PostgreSQL16.13和真实pgvector，[合成SQL夹具](../tests/qa_regression/keyword_source_pg_fixture.sql)没有原制度内容。覆盖完整回滚、跨文档隔离、提交两种不确定状态、漂移、外键/触发器和并发DDL阻断。0生产写入/问题POST，不能换算线上准确率。
当前权威：[事务、真实依赖与剩余发布门](handoffs/2026-09-17-qa-keyword-source-transaction.md)、[机器证据](../tests/qa_regression/keyword_source_transaction_20260917.json)。上节253项报告是准备阶段历史快照，当前执行器状态以本节为准。

## REQ-QA-SOURCE-RELEASE-ENTRY-20260917：入口反例与真实身份

状态：2026-09-17本机验证，生产未执行。
入口20项及既有271项合并291 passed（16.81秒），真实原生PG16.13/pgvector。DB实例/主机/root/配置封存、单次尝试、提交后收据失败恢复及明确keyword反例；静态复审PASS，不计线上准确率。
当前权威：[封存包、291项及剩余授权/部署门](handoffs/2026-09-17-qa-source-release-entry.md)、[机器证据](../tests/qa_regression/source_release_entry_20260917.json)。上节271项为事务库阶段快照，当前入口状态以本节为准。


## REQ-QA-ORIGINAL-SOURCE-READER-20260917：制度原书读取门禁

状态：2026-09-17本机验证/复审并冻结，生产未接入。

合并356 passed（22.76秒），新门禁44项使用隔离原生PG16.13/真实public.vector：19检索+4文档字段篡改、缺源/回滚/向量、删除尾片段、并发写后一致快照、岗位选择/澄清及综合降级。另真实私有原源5587索引、11组14次确定性读取逐块保留，0生产请求/模型调用。旧44文档选择/完整性层测试不计为原源验证，测试命令见机器证据。

当前权威：[读取门禁交接](handoffs/2026-09-17-qa-original-source-reader.md)、[脱敏机器证据](../tests/qa_regression/original_source_reader_20260917.json)。291项入口报告是历史阶段，完整源发布及822原题现场验收尚未完成。


## REQ-QA-FORMAL-DOCUMENT-SCOPE-20260917：书名与全部请求范围

状态：2026-09-17本机378项/复审及V34-r1冻结，生产未应用。

新增22项；V33初19项实际16fail/3pass，补充规程作用域3项修复前3fail。修复后合并378 passed（28.86秒），独立静态复审PASS。中途5例测试适配器属性误用已单列，不算产品失败；ask已有独立单SELECT断言。更新读取器后私有原源11组14次保真验证再次通过（15.17秒），0生产/模型请求。

当前权威：[范围修复交接](handoffs/2026-09-17-qa-document-scope-resolution.md)、[脱敏机器证据](../tests/qa_regression/document_scope_resolution_20260917.json)。V33/356项为前阶段快照；822原题现场验证未完成。


## REQ-QA-DOCUMENT-REGULATION-SCOPE-20260917：条款规程范围与逐项覆盖

状态：2026-09-17本机400项/复审通过，V35-r1冻结，生产未应用。

V34初19项17fail/2pass；后续中间候选另3分页项2fail/1pass，分开记录。最终400 passed/34.85秒；随后只加全JSON断言的22项再次通过/5.92秒，运行代码不变。独立审查复核完整not-chosen控制流后纠正初判并PASS。实际私有原源11组14读再次通过/15.07秒。0模型/生产请求，不推导线上准确率。

当前权威：[规程范围交接](handoffs/2026-09-17-qa-document-regulation-scope.md)、[脱敏机器证据](../tests/qa_regression/document_regulation_scope_20260917.json)。V34/378项保留为历史阶段；822原题现场复问未完成。


## REQ-QA-FIXED-MODEL-OVERRIDE-20260917：唯一固定底座禁止参数覆盖

状态：2026-09-17本机61项/独立审查通过，V36-r1冻结，生产未应用。

5覆盖反例在旧17项运行实际5fail/12pass，修复17pass。相关五组最终61pass/38.05秒；先前38pass/23默认Temp权限夹具错误单列，改用工作树独立basetemp，未修改共享ACL或删目录。独立Luna low语义PASS；实际PowerShell隔离harness不代表生产经理执行。V35/400为历史未重跑，不虚构合并461或原题准确率。

当前权威：[固定参数门交接](handoffs/2026-09-17-qa-fixed-model-override.md)、[脱敏机器证据](../tests/qa_regression/fixed_model_override_20260917.json)。源/制度前阶段以V35报告保留；822原失败partial题0复问。


## REQ-QA-COMPOUND-SOURCE-SCOPE-20260917：复合子任务与来源禁令

状态：2026-09-17本机557项相关回归及独立审查通过，V37-r2冻结，生产未应用。

新增34项回归；初始23项17fail/6pass，追加制度禁止读库3项全部失败后修复。最终相关24组557pass/79.81秒，110项聚焦4.16秒；实际私有原源11组14次读取保真，1pass/15.77秒。先前554项属于补齐前r1，不作最终验收；3个异步测试适配错误单列。独立Luna low复审PASS，未调用助手模型，未复问822原题。

权威：[逐项交接](handoffs/2026-09-17-qa-compound-source-scope.md)、[脱敏证据](../tests/qa_regression/compound_source_scope_20260917.json)。0生产销项，原题准确率未验证。


## REQ-QA-MATH-FUNCTION-POLICY-20260917：正常数学函数问答

状态：2026-09-17本机225项相关回归/独立审查通过，V38-r2冻结，生产未应用。

初始22项11fail/11pass；新增数学29项及历史质量4反例。最终10模块225pass/18.27秒，独立Luna low复审PASS，金标schema14项通过。首次扩展218pass/3fail为2个AST测试依赖遗漏及1个旧成功fixture，已保留过程并补反例；不与V37/557项合并成当前运行数。

权威：[逐项交接](handoffs/2026-09-17-qa-math-function-policy.md)、[脱敏机器证据](../tests/qa_regression/math_function_policy_20260917.json)。本轮0助手模型调用/生产写入/原题发送/销项。


## REQ-QA-USER-DATA-SOURCE-SCOPE-20260917：用户给定数据与外部来源范围

状态：2026-09-17本机286项相关回归/独立审查通过，V39-r3冻结，生产未应用。

初始23项17fail/6pass；新增43项含实际代理alias、实体冻结、MCP门、时窗和时钟输入测试。最终13模块286pass/27.70秒，Luna low复审PASS、共享22标记通过。r2虽276pass但范围审查FAIL，过程保留并新增10例；本机通过不是线上正确率。

权威：[逐项交接](handoffs/2026-09-17-qa-user-data-source-scope.md)、[脱敏机器证据](../tests/qa_regression/user_data_source_scope_20260917.json)。本轮0助手模型调用/生产写入/原题发送/销项。


## REQ-QA-DECLARED-INPUT-SCOPE-20260917：声明输入与现场核验

状态：2026-09-17本机327项相关回归/独立审查通过，V40-r2冻结，生产未应用。

初始27项19fail/8pass；新增41例。r1曾323pass/29.38秒和静态PASS，主任务再发现4个钟点/日期输入误判，均失败后修正r2。最终14模块327pass/29.07秒，Luna low复审PASS，14金标schema及22共享标记通过；不是线上正确率。

权威：[逐项交接](handoffs/2026-09-17-qa-declared-input-scope.md)、[脱敏机器证据](../tests/qa_regression/declared_input_scope_20260917.json)。本轮0助手模型调用/生产写入/原题发送/销项；R07重新开放。
