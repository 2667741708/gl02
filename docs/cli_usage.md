# CLI 使用手册

## 炉次质量回看本机验证

只读 dry-run 示例：

```powershell
& 'D:\ProgramData\anaconda3\python.exe' '.\tools\sync_22012_heat_performance_quality.py' `
  --since-days 3 --repair-days 3 --repair-page-size 200 `
  --repair-max-rows 5000 --audit-detail-limit 100 --dry-run
```

dry-run 不写 PostgreSQL，`repair_prepared` 表示具备证据且已构造修复行的数量，`repaired=0`。生产正式执行和 DDL 迁移必须另行获得上线授权并走受控部署，不得把本命令直接当生产发布命令。

## 平均 Si V19 指定炉次一键预测

追踪编号：`REQ-SI-V19-ONE-CLICK-PREDICTION-20260807`

入口为 [predict_next_heat_si_v19.py](../tools/predict_next_heat_si_v19.py)。该命令只读 220.12 PostgreSQL，读取已经过 IMES 回看核验修复的 `bf_assistant.heat_performance_quality_summary`、分钟传感器和喷煤数据；预测结果只写入本机 `PT/预测铁水Si含量/reports/live_predictions/`，不写 220.12 业务表、不替换生产模型。

当前默认口径（2026-08-08）：不再使用全集上下文/V21 process133。日常单炉预测直接运行本节命令，不指定 `--model`，即使用之前的 V19 August holdout 默认模型。

按“上一炉”自动推断下一炉：

```powershell
python .\tools\predict_next_heat_si_v19.py --previous-meltno "2#20260807-094"
```

显式指定目标炉和截止炉：

```powershell
python .\tools\predict_next_heat_si_v19.py --target-meltno "2#20260807-095" --cutoff-meltno "2#20260807-094"
```

显式指定预测截止时刻：

```powershell
python .\tools\predict_next_heat_si_v19.py --target-meltno "2#20260807-095" --cutoff-ts "2026-08-07 07:40:00"
```

输出包含 `prediction.prediction`、经验 `p10/p50/p90` 区间、最大概率值代理、若目标炉已有化验则附 `actual_si_mean/absolute_error/signed_error`，并记录历史 Si、喷煤和传感器特征审计。运行前提是本机 VPN/SSH 到 `10.30.220.12` 可达；若网络不可达，命令会在建立隧道阶段失败，不会写入任何业务数据。

2026-08-07 起，一键预测默认时间统计窗口为 `30,60,120,240,360,480,720` 分钟，以覆盖约 5.6 小时料批到铁水的滞后时间；可用 `--windows-minutes` 显式覆盖：

```powershell
python .\tools\predict_next_heat_si_v19.py --target-meltno "2#20260807-095" --cutoff-ts "2026-08-07 07:30:00" --windows-minutes "30,60,120,240,360,480,720"
```

喷煤特征优先读取 `bf_sensor.v_coal_injection_hourly` 的正式小时喷煤量：上一完整小时可直接使用正式/实测优先值；当前小时只有在该小时行的数据水位不超过预测截止时刻时才使用，否则自动回退到 `PCI_rate` 分钟积分，避免回放时误读截止点之后的未来喷煤。

以指定炉次做 5 分钟滚动回放或实时采样，使用 [run_live_si_prediction_5min.py](../tools/run_live_si_prediction_5min.py)：

```powershell
python .\tools\run_live_si_prediction_5min.py --target-meltno "2#20260807-095" --start-ts "2026-08-07 07:00:00" --end-ts "2026-08-07 07:35:00" --step-minutes 5
```

采样程序会逐个截止时刻调用原子预测器，并生成本机 JSONL/CSV 预测流水。绘图使用 [plot_live_si_prediction_curve.py](../tools/plot_live_si_prediction_curve.py)：

```powershell
python .\tools\plot_live_si_prediction_curve.py --target-meltno "2#20260807-095"
```

若要隔离一次实验输出，可显式指定 `--output-dir` 和 `--atomic-output-dir`，例如把 95 炉回放写入 `PT/预测铁水Si含量/reports/live_predictions/heat95_5min_demo/`。

如果要批量按“每炉开口前 1 小时”预测并与实际 Si 对比，使用 [run_heat_open_minus_si_batch.py](../tools/run_heat_open_minus_si_batch.py)：

```powershell
python .\tools\run_heat_open_minus_si_batch.py --date-from "2026-08-07" --date-to "2026-08-07" --lead-minutes 60
```

按炉号范围批量回放：

```powershell
python .\tools\run_heat_open_minus_si_batch.py --meltno-from "2#20260807-089" --meltno-to "2#20260807-095" --lead-minutes 60
```

输出包括 `open_minus_si_predictions.csv/jsonl/png`，默认位于 `PT/预测铁水Si含量/reports/open_minus_predictions/`。该脚本先从 220.12 汇总表读取每炉有效 `open_ts`，自动把预测截止时刻设为 `open_ts - lead_minutes`，再逐炉调用原子预测器；目标炉已有实际 Si 时自动计算误差。

## 平均 Si V20 开口前命中率影子实验

追踪编号：`REQ-SI-V20-OPEN-MINUS-HITRATE-20260807`

V20 是离线/影子实验，目标场景固定为“每炉开口前 1 小时预测该炉平均 Si”。它只读 220.12 修复后的炉次质量、传感器和喷煤数据；输出只写本机实验目录，不替换生产模型、不写 220.12 业务表。

构建 V20 多提前量数据集：

```powershell
python .\tools\build_open_minus_si_dataset_v20.py --date-from "2026-02-01" --date-to "2026-08-07"
```

默认不再使用全集上下文；V20 数据构建器当前默认使用核心 28 变量窗口。若需要显式声明，可写：

```powershell
python .\tools\build_open_minus_si_dataset_v20.py --date-from "2026-02-01" --date-to "2026-08-07" --sensor-name-scope core28
```

快速验证链路时可跳过较重的传感器长窗口和 IMES 化学背景：

```powershell
python .\tools\build_open_minus_si_dataset_v20.py --date-from "2026-08-06" --date-to "2026-08-07" --skip-sensor-windows --skip-chemistry --limit 40
```

训练和评估开口前 60 分钟模型：

```powershell
python .\tools\train_open_minus_si_v20.py --lead-minutes 60
```

若消融组验证集表现最好，并希望把消融组也保存为离线模型包，可显式加入：

```powershell
python .\tools\train_open_minus_si_v20.py --lead-minutes 60 --allow-ablation-selection
```

默认切分为：训练到 `2026-07-31`，验证 `2026-08-01~2026-08-05`，最终确认 `2026-08-06~2026-08-07`；样本不足时自动退化为滚动日验证。训练产物默认写入：

```text
PT\预测铁水Si含量\reports\experiments\EXP-SI-V20-OPEN-MINUS-20260807\training\
```

使用选定 V20 模型做单炉预测：

```powershell
python .\tools\predict_next_heat_si_v19.py --target-meltno "2#20260807-095" --cutoff-ts "2026-08-07 06:40:00" --model "PT\预测铁水Si含量\reports\experiments\EXP-SI-V20-OPEN-MINUS-20260807\training\selected_v20_open_minus.joblib"
```

注意：不指定 `--model` 时，一键预测器仍默认加载 V19，保持当前流程兼容。指定 V20 bundle 时，程序才额外构建 `history_mean__Si_lag_1~5`、未化验炉次间隔、8/12 小时喷煤和 `30/60/120/240/360/480/720` 分钟传感器窗口。

## 8093/8094 诊断功能一键部署（reliable_ssh）

本地检查和dry-run，不访问生产：

```powershell
python .\tools\deploy_diag_rules.py
```

确认dry-run通过后，一键部署到220.12的8093/8094：

```powershell
python .\tools\deploy_diag_rules.py --apply
```

需要额外执行完整API验收时：

```powershell
python .\tools\deploy_diag_rules.py --apply --verify full
```

入口固定使用本机 `reliable_ssh` 配置中的目标、主机指纹、密码文件和审计日志；不会在命令行或报告中输出密码。默认执行47项快速合同测试，只有已经单独跑过同一批测试时才可追加 `--skip-tests`。快速包只更新诊断解释、评分弹窗和相关后端/静态资产，不更新8768诊断调度器。

## 220.12 SSH复用、计时与MCP连接池（2026-08-10）

独立UTF-8 PowerShell双次验收与可选冷连接基线：

```powershell
pwsh.exe -NoLogo -NoProfile -File .\tools\verify_22012_persistent_ssh_reuse.ps1 -IncludeColdBaseline
```

仅查看持久会话：

```powershell
python .\tools\remote_22012_session.py status
```

验证Reliable SSH MCP在同一Plink进程复用请求：

```powershell
node .\tools\reliable_ssh_22012_cli.mjs pool-probe
```

查看最近50次部署计时与失败候选：

```powershell
python .\.codex\skills\deploy-8093-guarded-update\scripts\deployment_memory.py summary --window 50
```

项目内Skill是版本源；首次导入、修改后发布和只读一致性验证分别使用：

```powershell
pwsh.exe -NoLogo -NoProfile -File .\tools\sync_deploy_8093_guarded_update_skill.ps1 -Action ImportGlobalToProject
pwsh.exe -NoLogo -NoProfile -File .\tools\sync_deploy_8093_guarded_update_skill.ps1 -Action PublishProjectToGlobal
pwsh.exe -NoLogo -NoProfile -File .\tools\sync_deploy_8093_guarded_update_skill.ps1 -Action Verify
```

日常不得先执行`ImportGlobalToProject`覆盖项目版本；应先验证`.codex\skills\deploy-8093-guarded-update`，再执行`PublishProjectToGlobal`和`Verify`。脚本只操作本机两个Skill目录，不连接220.12。

8093两阶段快路径先封存已通过验证的产物，再用最新只读远端哈希生成差量：

```powershell
python .\.codex\skills\deploy-8093-guarded-update\scripts\release_manifest.py prepare --spec .\release-spec.json --output .\prepared-release.json
python .\.codex\skills\deploy-8093-guarded-update\scripts\release_manifest.py verify --manifest .\prepared-release.json
python .\.codex\skills\deploy-8093-guarded-update\scripts\release_manifest.py plan-delta --manifest .\prepared-release.json --remote-state .\remote-state.json --output .\delta-plan.json
```

`release-spec.json`必须记录源文件、产物、精确stage/target、允许的生产基线SHA-256、标记、验证等级和已通过证据。任一源/产物字节变化会使清单失效；差量为空时不上传、不暂停8093。语义diff的Luna low审查与只读远端预检并行完成，机械哈希/清单不调用模型。

复用验收只创建远端临时payload并清理，不改生产目标、不停服务。`pool-probe`只调用身份探针。正式部署时间比较至少交错运行5组冷/热样本，并保证文件、测试、重启和网络条件一致。

## 8093 每5分钟八炉况智能分析验证

合同测试：

```powershell
python -m pytest -q -p no:cacheprovider tests\test_diagnosis_ai_analysis.py tests\test_diagnosis_review_api.py tests\test_diagnosis_review_contract.py tests\test_multi_condition_recommendation_and_model_review.py
```

Firefox/WebKit固定场景：

```powershell
$env:NODE_PATH='C:\Users\hmw20\.cache\codex-runtimes\codex-primary-runtime\dependencies\node\node_modules'
& 'C:\Users\hmw20\.cache\codex-runtimes\codex-primary-runtime\dependencies\node\bin\node.exe' 'tools\verify_diagnosis_ai_analysis_viewports.cjs'
```

生产部署前先用 `tools/check_ps1_syntax.ps1`检查脚本，再按[专项说明](8093_每5分钟八炉况智能分析_20260805.md)上传各个短步骤所需文件并通过 `-File`运行 `remote_guarded_deploy_8093_diagnosis_review.ps1`。不得把上传、执行和验证拼进同一条远端内联命令。

## 8093 智能助手自动诊断—修复—验收

追踪编号：`OPS-8093-ASSISTANT-AUTO-RECOVERY-20260805`

### 常用命令

首次或工具包升级后预置远端不可变包：

```powershell
python tools\assistant_8093_auto_recovery.py prestage --allow-agents-password
```

1–2 分钟只读分类，不发送问答、不启停服务：

```powershell
python tools\assistant_8093_auto_recovery.py diagnose --allow-agents-password --no-auto-prestage
```

自动分类、必要时最小修复，并且只发送一次真实 SSE：

```powershell
python tools\assistant_8093_auto_recovery.py recover --allow-agents-password --no-auto-prestage
```

服务阶段结束后，独立生成追踪文档和 DOCX：

```powershell
python tools\assistant_8093_auto_recovery.py docs --report logs\assistant_8093_auto_recovery\20260805_110327_recover.json
```

### 子命令

| 子命令 | 写入边界 | 输出 |
|---|---|---|
| `prestage` | 仅写远端受控 package 目录；manifest 最后写入 | 包 ID、目录、manifest/文件 SHA、复用或上传状态、JSON 报告 |
| `diagnose` | 只读远端；不发问答 | 连通性、合并诊断、自动分类、JSON 报告 |
| `recover` | 仅对已知哈希的守卫/keyword 漂移做备份与最小部署；最多一次 SSE | 修复前后诊断、动作、唯一 SSE、JSON 报告 |
| `docs` | 只写本机 docs；不连接远端、不发 SSE | 时间戳交接、最近报告、DOCX |

### 主要参数

| 参数 | 默认 | 说明 |
|---|---:|---|
| `--host` | `10.30.220.12` | 目标主机，可由 `BF_22012_HOST` 覆盖 |
| `--user` | `administrator` | SSH 用户，可由 `BF_22012_USER` 覆盖 |
| `--password-env` | `BF_22012_SSH_PASSWORD` | 只指定环境变量名，不打印值 |
| `--allow-agents-password` | false | 允许按既有受控项目入口取得凭据；不得把密码写入新日志/文档 |
| `--prompt-password` | false | 交互读取密码 |
| `--connect-timeout` | `3.0` | 单个 TCP 前置探测超时（秒） |
| `--vpn-timeout` | `90` | aTrust 启动后等待私网恢复上限（秒） |
| `--no-vpn-recovery` | false | 禁止自动启动 aTrust；连通性不足直接退出 |
| `--no-auto-prestage` | false | 只复用已验证包；缺包或哈希不符直接退出 |
| `--diagnostic-timeout` | `120` | 单次远端合并诊断上限（秒） |
| `--repair-timeout` | `600` | 单个已知修复阶段上限（秒） |
| `--acceptance-timeout` | `420` | 唯一 SSE 验收阶段上限（秒） |
| `--report` | 最近 recover 报告 | `docs` 阶段的本地 JSON 输入 |

### 退出码

| 码 | 含义 |
|---:|---|
| 0 | 成功 |
| 2 | 未知哈希/未知状态，拒绝自动修复 |
| 3 | VPN/SSH/PostgreSQL/8093/11434 连通性失败 |
| 4 | 凭据或远端包预置/校验失败 |
| 5 | 远端诊断或部署阶段失败 |
| 6 | 唯一一次 SSE 验收失败；不会自动重试 |
| 7 | 服务已结束后的文档生成失败 |

### 输出目录

- 本地 JSON：`logs/assistant_8093_auto_recovery/`
- 本地最新 Markdown：`docs/8093智能助手自动恢复最近报告.md`
- 本地交接：`docs/handoffs/<时间>-8093-assistant-auto-recovery.md`
- DOCX：`docs/8093智能助手不可用原因与正式修复手册_20260804.docx`
- 远端包：`C:\ProgramData\BFV4\assistant-auto-recovery\packages\<package_id>`

不要手工拼接远端 PowerShell 多行命令；需要增加阶段时，把逻辑写入受测试的 `.ps1`，纳入 package manifest 后重新 `prestage`。
## 220.12 工长趋势独立页发布与只读验收

追踪编号：`OPS-FOREMAN-TREND-STANDALONE-PREVIEW-20260805`。正式访问地址为 `http://10.30.220.12:8093/foreman_trend_preview.html?ws_port=8768`。

受控部署入口为 [remote_deploy_8093_foreman_trend_preview.ps1](../tools/remote_deploy_8093_foreman_trend_preview.ps1)。它通过既有 `remote_22012_exec.py` 上传独立 HTML、CSS、JS 后原子替换；部署前后必须核对 8093/8768 都是 Running 且监听。不要停止 8768、8770、8094、11434 或数据库。

只读生产浏览器验收：

```powershell
$env:NODE_PATH='C:\Users\hmw20\.cache\codex-runtimes\codex-primary-runtime\dependencies\node\node_modules'
& 'C:\Users\hmw20\.cache\codex-runtimes\codex-primary-runtime\dependencies\node\bin\node.exe' .\tools\verify_foreman_trend_remote_8093.cjs
```

成功信号是 8768 实时连接、数据时间非 `--`、主/下方曲线为 `12/12` 和 `5/5`、无横向溢出且浏览器错误为 0。该页只使用分钟实际数据；不应把它说明成 8770 pSpace 秒级直连。

## MES 作业日志燃料比经验法核验

用途：只读核验现场“下达燃料比”经验法对铁水 Si 的解释能力。数据源限定为 MES Web 端“冀南新区高炉作业日志”报表源记，不使用 pSpace，不写 220.12 业务表。

先通过 220.12 下载 2#高炉最近半个月作业日志源 HTML：

```powershell
python .\tools\remote_22012_exec.py --allow-agents-password --no-profile --timeout 300 --script '.\tools\remote_fetch_imes_report_2d012_recent_days.ps1' --download 'C:\Users\Administrator\AppData\Local\Temp\imes_report_2d012_recent_days=PT\预测铁水Si含量\reports\experiments\EXP-SI-FUELRATIO-REPORT-20260808\source_probe\imes_report_2d012_recent_days'
```

再本机离线复现报表燃料比公式并生成 CSV、JSON、曲线图：

```powershell
python .\tools\evaluate_imes_fuel_ratio_rule.py
```

输出目录：

```text
PT\预测铁水Si含量\reports\experiments\EXP-SI-FUELRATIO-REPORT-20260808\fuel_ratio_rule_eval
```

当前边界：该 MES 作业日志入口每个日报 HTML 仅直接暴露一个“炉前出铁情况”块；若要做全炉次大样本验证，需要继续定位 MES Web 作业日志记录枚举/翻页入口，或在用户允许下用 220.12 修复后的逐炉质量汇总表对齐实际 Si。

### 220.12 作业日志燃料比落库可行性只读审计

用途：核查 220.12 PostgreSQL 是否已有 MES 作业日志燃料比/煤比/喷煤/批数数据，确认候选表名是否冲突，并输出后续页面所需的数据源边界。该命令通过既有 SSH 隧道和只读账号连接 220.12，不执行 DDL、不写业务表。

```powershell
python .\tools\audit_22012_fuelratio_report_surfaces.py --output 'PT\预测铁水Si含量\reports\experiments\EXP-SI-FUELRATIO-REPORT-20260808\db_surface_audit\fuelratio_report_surfaces.json'
```

成功信号：输出 JSON 中 `identity.read_only=on`，并列出 `bf_imes.imes_bf2_operation_log_report`、`bf_imes.v_bf2_operation_log_report`、`bf_assistant.heat_performance_quality_summary` 等对象。

## V21 平均Si传感器窗口预聚合缓存

用途：把 V20 开口前平均 Si 预测所需的 `core28/process133 × 多窗口` 传感器统计做成本机缓存，避免每次训练都在 220.12 上执行重型 `样本 × 窗口 × 点位` 聚合。只读 220.12，不写业务表。

暂停口径（2026-08-08）：用户已决定不再使用全集上下文，当前推荐和默认回到 V19 August holdout。以下 V21/process133 命令只保留为离线研究复现实验，不作为日常预测、默认训练或影子候选。

严格 133 点缓存：

```powershell
python .\tools\build_v20_sensor_window_cache.py --date-from 2026-03-01 --date-to 2026-08-07 --limit 5000 --lead-minutes-list 60 --sensor-name-scope process133 --sensor-windows-minutes 30,60,120,240,360,480,720 --statement-timeout-ms 300000 --local-tunnel-port 15451 --output-dir 'PT\预测铁水Si含量\reports\experiments\EXP-SI-V21-SENSOR-CACHE-20260808\cache_process133_2026'
```

合并缓存到训练数据：

```powershell
python .\tools\materialize_v21_dataset_from_sensor_cache.py --base-dataset 'PT\预测铁水Si含量\reports\experiments\EXP-SI-V21-SENSOR-CACHE-20260808\dataset_core28_60\v20_open_minus_dataset.csv' --sensor-cache 'PT\预测铁水Si含量\reports\experiments\EXP-SI-V21-SENSOR-CACHE-20260808\cache_process133_2026\v21_sensor_window_cache_process133_lead60.csv' --sensor-audit 'PT\预测铁水Si含量\reports\experiments\EXP-SI-V21-SENSOR-CACHE-20260808\cache_process133_2026\v21_sensor_window_cache_process133_lead60.audit.json' --sensor-variable-scope all --output-dir 'PT\预测铁水Si含量\reports\experiments\EXP-SI-V21-SENSOR-CACHE-20260808\dataset_process133_60'
```

高维训练可用 `--candidate-names` 跳过过重候选：

```powershell
python .\tools\train_open_minus_si_v20.py --dataset 'PT\预测铁水Si含量\reports\experiments\EXP-SI-V21-SENSOR-CACHE-20260808\dataset_process133_60\v20_open_minus_dataset.csv' --lead-minutes 60 --output-dir 'PT\预测铁水Si含量\reports\experiments\EXP-SI-V21-SENSOR-CACHE-20260808\training_process133_60_lightgbm' --allow-ablation-selection --candidate-names 'history_lag1_baseline,v20_lightgbm_huber,v20_hit_weighted_lightgbm,ablation_history,ablation_history_pci,ablation_long_windows'
```

当前结果记录见 `PT\预测铁水Si含量\docs\v21_sensor_cache_20260808.md`。核心结论：缓存技术可用，但 core28/process133 全窗口特征没有提升 2026-08-06~2026-08-07 确认集命中率，仍保持离线实验状态。

## 工长燃料比法与 V20 历史 Si 同炉次比较

用途：把 MES Web 作业日志炉前块和 V20 开口前 1 小时预测按炉号、开口时间双键
对齐，统一使用 220.12 每炉平均 Si 标签，输出并列指标和曲线。只读本地产物，
不写 220.12。

```powershell
python .\tools\compare_foreman_fuel_vs_v20_history.py
```

默认输出目录：

```text
PT\预测铁水Si含量\reports\experiments\EXP-SI-FUELRATIO-V20-COMPARE-20260808
```

主指标只使用 V20 的 validation+confirm 共同炉次；训练段会输出但明确标记为
`train_in_sample_not_for_ranking`。可通过 `--fuel-csv`、`--v20-csv`、
`--v19-metrics` 和 `--output-dir` 替换输入输出。

## 炉体温度红外回放

本地启动（只读）：

```powershell
python .\tools\soft_zone_replay_server.py --host 127.0.0.1 --port 8128
```

220.12部署必须先逐文件上传到部署脚本声明的临时路径，再单独执行：

```powershell
python .\tools\remote_22012_exec.py --allow-agents-password --no-profile --timeout 180 --workdir 'F:\高炉炼铁项目-real-sensor-v2_V4_8093_PREVIEW' --script '.\tools\remote_deploy_22012_soft_zone_replay_8892.ps1'
```

部署后用`tools\probe_22012_soft_zone_replay_8892.ps1`只读核查任务、监听和日志。页面入口为`http://10.30.220.12:8892/`。

## 8093/8094 V20 平均 Si 影子预测

追踪编号：`REQ-SI-V20-8093-8094-SHADOW-WORKBENCH-20260808`

浏览器打开 `http://10.30.220.12:8093/` 或 `http://10.30.220.12:8094/`，直接点击右上方“平均 Si 预测 / V20影子模式”，无需生产账号登录。

- 当前预测：填目标炉号和目标/预计开口时间，选择“服务器当前时刻”，点击“开始预测平均Si”。
- 生产整点预测：服务器任务每小时在 `HH:00:05` 调用本机8093 API，模型数据截止固定为 `HH:00:00`，不依赖浏览器保持打开。页面“补跑当前整点预测”按钮只作人工补跑，同一高炉、同一整点不会重复保存。
- 标准回放：选择“开口前60分钟回放”；程序自动使用该炉 `open_ts - 60min`，不需要手工挑前炉化验。
- 历史曲线：切换“历史曲线与回放”，选日期后先“查询已保存预测”；需要补做历史预测时点击“按开口前60分钟回放所选日期”。
- 化验随后发布后，再打开历史页即可看到实际平均 Si、绝对误差和 ±0.05 命中，无需重跑预测。

运维检查（只读）：

```powershell
Invoke-WebRequest -UseBasicParsing 'http://10.30.220.12:8093/api/si-v20/status'
Invoke-WebRequest -UseBasicParsing 'http://10.30.220.12:8094/api/si-v20/history?limit=20'
```

本功能只写预测审计表，不调整生产设定值；历史评价使用开口前60分钟口径，生产值守使用服务器整点口径，两者必须分开统计。

### 双口径自动化（220.12已部署）

历史回看仍按真实开口时间反推：

```text
cutoff_ts = open_ts - 60min
request_mode = historical_range_replay
实际对比 = 同一炉号的 si_avg
```

生产整点预测按当前整点数据进行：

```text
cutoff_ts = 当前小时 HH:00:00
request_mode = hourly_schedule
实际对比 = requested_at 之后最先真实开口的同高炉炉次
```

本机人工验证整点运行器（不写数据库）：

```powershell
python .\tools\run_si_v20_hourly_prediction.py --cutoff-ts "2026-08-09 20:00:00" --dry-run
```

当前生产可配置分钟分发任务已经部署；以下旧整点专用注册器仅作兼容/审计参考，不应与可配置任务重复启用：

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File '.\tools\set_22012_heat_quality_sync_1min.ps1'
powershell.exe -NoProfile -ExecutionPolicy Bypass -File '.\tools\register_22012_si_v20_hourly_task.ps1'
```

IMES镜像任务 `\GL02SensorSync\IMESRealtime` 已在220.12按一分钟尝试触发并使用 `IgnoreNew`。如果单轮同步超过一分钟，下一次触发会跳过而不会并发重入，因此“一分钟”表示调度周期，不保证慢任务也能每60秒完成一轮。

### 可配置1分钟/10分钟/30分钟/1小时/1天预测

页面保存周期后只更新`bf_assistant.si_v20_prediction_schedule`。服务器固定一分钟分发任务负责检查是否到期，因此不需要操作者保持页面打开，也不需要每次重新注册Windows任务。

本机验证分发器：

```powershell
python .\tools\run_si_v20_schedule_dispatcher.py --dry-run
```

220.12任务注册器（已执行，重复执行会先备份原任务XML再幂等覆盖）：

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File '.\tools\register_22012_si_v20_schedule_task.ps1'
```

API配置示例：

```powershell
$body = @{ cadence_minutes = 10; enabled = $true; furnace_no = '2' } | ConvertTo-Json
Invoke-RestMethod -Method Post -Uri 'http://127.0.0.1:8093/api/si-v20/schedule/configure' -ContentType 'application/json' -Body $body
```

历史批量示例：

```powershell
$body = @{ start_ts = '2026-08-08 00:00:00'; end_ts = '2026-08-08 23:59:00'; cadence_minutes = 10; furnace_no = '2' } | ConvertTo-Json
Invoke-RestMethod -Method Post -Uri 'http://127.0.0.1:8093/api/si-v20/scheduled-replay' -ContentType 'application/json' -Body $body
```

指定时刻示例：

```powershell
$body = @{ cutoff_ts = '2026-08-08 07:00:00'; cadence_minutes = 1; furnace_no = '2' } | ConvertTo-Json
Invoke-RestMethod -Method Post -Uri 'http://127.0.0.1:8093/api/si-v20/scheduled-replay' -ContentType 'application/json' -Body $body
```

单次历史批量最多5000个时间点。实时定时点和历史时间槽点使用不同匹配锚点，页面会分别展示预测候选炉次与最终匹配的真实炉次。

曲线筛选和下载：

- 上方开始/结束日期控制时间范围；
- “起始炉次/结束炉次”可填完整炉号，也可只填`124`这类炉次序号；
- “下载预测曲线 CSV”保留每个预测时间点和P10/P50/P90；
- “下载实际 Si 曲线 CSV”按炉次去重，避免一分钟预测把同一炉实际值重复导出。

### 8093 快速受控上传（用户可手动执行）

本机先完成静态检查和浏览器验收，再从项目根目录执行下面的一条命令。它更新共享V20后端、独立页、静态资源和分钟分发脚本；自动暂停/恢复`BFV4PreviewProxy8093`，迁移三表并注册一分钟任务，同时保护8768/8094/8770/11434。由于8094共享同一后端文件，命令成功后还需用既有`restart_22012_8094_preview.ps1`受控重启8094：

```powershell
Set-Location -LiteralPath 'D:\文件\冀南钢铁运行中第二版本'
powershell.exe -NoProfile -ExecutionPolicy Bypass -File '.\tools\deploy_si_v20_workbench_8093.ps1'
```

部署脚本会先把文件分段上传到远端临时目录，再执行远端原子替换、建表、任务注册和HTTP/API验收；输出中的`backup`是可回退目录。当前本机验收命令为：

```powershell
python -B tests\test_si_v20_shadow_workbench.py
python -B -c "import tests.test_heat_performance_quality_repair_loop as t; t.test_local_22012_mirror_recovers_completed_heat_average_without_external_imes(); print('mirror_test_ok')"
$env:NODE_PATH='C:\Users\hmw20\.cache\codex-runtimes\codex-primary-runtime\dependencies\node\node_modules'; & 'C:\Users\hmw20\.cache\codex-runtimes\codex-primary-runtime\dependencies\node\bin\node.exe' .\tools\verify_si_v20_standalone_ui.cjs
```

远端部署命令不会把预测值写入生产控制表；只追加预测审计。长等待主要来自 SSH 上传/连接、停止守卫后的端口释放、Python 服务冷启动和 HTTP 重试，而不是一次预测计算本身。普通单炉预测不应等待这些部署步骤。

## V20严格整点预测（独立常开）

本机手工检查当前及遗漏整点（不会使用浏览器时钟或页面候选）：

```powershell
python .\tools\run_si_v20_strict_hourly_dispatcher.py --base-url http://127.0.0.1:8093
```

220.12由任务`\BlastFurnaceServices\SiV20StrictHourlyPrediction`每分钟调用`tools\run_22012_si_v20_strict_hourly.ps1`。它只补齐整点槽；页面上的1/10/30/60/1440分钟配置不会关闭或改变该任务。手工“补跑当前严格整点”调用服务器端整点接口，无需输入炉号。

模型导出仅在冻结模型更新时运行：

```powershell
python .\tools\export_si_v20_strict_context_model.py
```

## 本机 PowerShell 7 UTF-8

本机所有项目 `.ps1` 入口统一由PowerShell 7执行：

```powershell
pwsh.exe -NoLogo -NoProfile -File .\tools\verify_pwsh7_utf8.ps1
$env:GL02_LOCAL_PGUSER = 'postgres'
$env:GL02_LOCAL_PGPASSWORD = '<从受控配置输入>'
pwsh.exe -NoLogo -NoProfile -File .\start_v3_full.ps1
```

`start_v3_full.ps1` 默认使用 `127.0.0.1:18000/bf_trend` 本机原生 PostgreSQL，
并用 `GL02_LOCAL_PG*` 覆盖可能指向220.12的用户级 `GL02_PG*`。只有显式设置
`BF_USE_EXISTING_PG_ENV=1` 时才保留既有主连接；本地同步目标始终使用
`GL02_LOCAL_PG*`。脚本不再包含 Docker `15432` 或数据库密码默认值。

升级稳定版并复验：

```powershell
winget upgrade --id Microsoft.PowerShell --exact --source winget
pwsh.exe -NoLogo -NoProfile -File .\tools\verify_pwsh7_utf8.ps1
```

禁止使用`powershell.exe`启动本机项目脚本。完整边界见[PowerShell 7 UTF-8运行规范](./PowerShell7_UTF8运行规范.md)。

### 220.12远程PowerShell 7

安装完成后，跳板默认使用220.12的PowerShell 7，无需额外参数：

```powershell
python -B .\tools\remote_22012_exec.py --allow-agents-password --no-profile --script .\tools\remote_smoke_22012_pwsh7.ps1
```

成功信号包括`ps_version=7.6.4`、`ps_edition=Core`和中文`冀南钢铁：远端中文执行正常`。只有安装/回滚PowerShell 7本身时才允许显式追加`--remote-shell windows-powershell`；日常查询、部署和验证不得使用该旧运行时选项。

## 软熔带移动特征融合诊断

入口：[run_cohesive_zone_intelligent_diagnosis.py:L24-L88](../tools/run_cohesive_zone_intelligent_diagnosis.py#L24-L88)。输入必须是带时间列的一分钟CSV；默认时间列名为`timestamp`。命令只读输入文件，默认把UTF-8 JSON打印到标准输出。

```powershell
python .\tools\run_cohesive_zone_intelligent_diagnosis.py --help

python .\tools\run_cohesive_zone_intelligent_diagnosis.py `
  --input .\data\cohesive_zone_minutes.csv

python .\tools\run_cohesive_zone_intelligent_diagnosis.py `
  --input .\data\cohesive_zone_minutes.csv `
  --evaluation-time '2026-08-10 10:00:00' `
  --include-geometry `
  --output .\output\cohesive_zone_diagnosis.json
```

参数：

- `--input`：必填CSV路径。
- `--timestamp-column`：时间列名，默认`timestamp`。
- `--evaluation-time`：可选历史截止；程序丢弃其后的所有行，防未来数据泄漏。
- `--config`：可选诊断YAML。
- `--estimator-config`：可选既有C2几何估算器YAML，仅在`--include-geometry`时使用。
- `--include-geometry`：同时输出现有根部高度、厚度、偏心和15分钟常速外推，并给出方向一致性。
- `--output`：可选JSON文件；省略时写标准输出。

退出码：`0`表示诊断可用；`2`表示输入成功解析但覆盖不足；`1`表示文件、时间列、配置或运行异常。完整验证使用：

```powershell
pwsh.exe -NoLogo -NoProfile -File `
  .\tools\verify_cohesive_zone_intelligent_diagnosis.ps1 `
  -PythonExecutable python
```

## 220.12持久SSH与8093料速规则部署

本会话和后续8093受控部署均使用PowerShell 7；不允许用`powershell.exe`、内联多行`-Command`或每条命令重新建立SSH认证连接。

```powershell
pwsh.exe -NoLogo -NoProfile -NonInteractive -File `
  .\tools\start_remote_22012_session.ps1

pwsh.exe -NoLogo -NoProfile -NonInteractive -File `
  .\tools\verify_remote_22012_session_reuse.ps1

pwsh.exe -NoLogo -NoProfile -NonInteractive -File `
  .\tools\deploy_abc33_burden_rate_22012.ps1
```

部署入口会依次执行本地119项门禁、持久连接`ensure`、upload-only暂存、8093守卫停—改—启、A2/B4/B5详情检查和8768独立重启。正常完成后保留SSH代理；只有用户明确要求、凭据轮换或主机/用户/工作目录需要改变时才运行：

```powershell
pwsh.exe -NoLogo -NoProfile -NonInteractive -File `
  .\tools\stop_remote_22012_session.ps1
```

### SSH耗时基准、原生编译和B4分数部署

```powershell
pwsh.exe -NoLogo -NoProfile -File `
  .\tools\benchmark_22012_ssh_command_latency.ps1 -SampleCount 5

pwsh.exe -NoLogo -NoProfile -File `
  .\tools\build_python_native_artifact.ps1 -Spec .\path\artifact-spec.json -PlanOnly

pwsh.exe -NoLogo -NoProfile -File `
  .\tools\build_python_native_artifact.ps1 -Spec .\path\artifact-spec.json -Build -BootstrapPython311 -InstallBuildDeps -Manifest .\path\artifact-manifest.json

pwsh.exe -NoLogo -NoProfile -File `
  .\tools\deploy_abc33_b4_score_source_22012.ps1
```

原生构建默认只生成计划；创建Python 3.11 x64环境、安装Nuitka/Cython依赖及真实编译均要求显式开关。产物提高逆向成本但不保证不可查看。B4部署只更新8093五个文件，不重启8768或修改数据库。

## 8093浏览器验收分级

```powershell
python .\tools\verify_diagnosis_review_local.py --profile quick
python .\tools\verify_diagnosis_review_local.py --profile standard
python .\tools\verify_diagnosis_review_local.py --profile full
```

默认`quick`只验证受影响的诊断路由，跨内核共4项；`standard`为单路由17项；`full`为五路由85项。生产环境只做受影响路由定向冒烟，完整矩阵在本机或预览环境运行。需要同时复核手动评分弹窗时增加`--check-manual-score`。

## Codex CLI经济型委派

```powershell
pwsh.exe -NoLogo -NoProfile -File `
  'C:\Users\hmw20\.codex\skills\codex-economical-delegation\scripts\invoke_codex_delegate.ps1' -ListModels

pwsh.exe -NoLogo -NoProfile -File `
  'C:\Users\hmw20\.codex\skills\codex-economical-delegation\scripts\invoke_codex_delegate.ps1' `
  -PromptFile .\delegate-task.txt -Model gpt-5.6-luna -ReasoningEffort low -Workdir .
```

默认是只读、ephemeral和最小工具面。需要本地写入时必须同时指定`-Sandbox workspace-write -AllowWorkspaceWrite`并给出精确文件所有权；不得用该入口操作220.12或8093生产。运行结果输出模型、reasoning、sandbox、耗时、exit code、tokens和最终消息。

## 8093前端生产构建与核心冒烟

```powershell
Set-Location -LiteralPath '.\高炉前端数据\dashboard_build'
npm run check
npm run build
Set-Location -LiteralPath '..\..'
python .\tools\verify_8093_frontend_production_build.py
```

默认只运行Chromium 1366x768核心组合。最终兼容阶段才显式追加`--full-matrix`；小功能开发阶段禁止默认运行85项。

生产部署使用独立UTF-8 PowerShell 7脚本：

```powershell
pwsh.exe -NoLogo -NoProfile -File .\tools\deploy_8093_frontend_perf_22012.ps1
```

该入口复用`tools/remote_22012_session.py`维护的已认证连接，先上传暂存，再由远端脚本完成互斥、备份、8093守卫停—改—启和失败回滚；成功输出必须同时包含`guard_restored=true`、`rollback_applied=false`、HTTP 200、压缩/缓存结果以及受保护PID前后一致。

## 构建220.12:8093维护交接包

```powershell
pwsh.exe -NoLogo -NoProfile -File .\tools\build_8093_handoff_package.ps1
```

默认输出到被Git忽略的`handoff_packages/`。入口只读取本机白名单文件，不连接220.12；构建成功时输出ZIP绝对路径、大小、SHA-256、文件数、敏感扫描状态和`productionMutation=not_started`。

## MCP 扩展生产回归

先只读校验扩展问题集：

```powershell
D:\ProgramData\anaconda3\python.exe -X utf8 .\tools\evaluate_mcp_extended_production.py --validate
```

生产执行必须显式给出 8093 SSE URL、输出路径和并发数；工具不自动重试。故障夹具不得指向 8093，
只允许由 `tools/mcp_fault_preview_acceptance.py` 在独立回环预览中运行。完整复现命令和请求账本见
[扩展生产回归交接](handoffs/2026-08-14-mcp-extended-production-regression.md)。

## REQ-QA-SOURCE-RELEASE-ENTRY-20260917：keyword单文档入口

状态：2026-09-17本机291项及静态审查通过，生产未执行。先运行python tools/qa_keyword_source_release_entry.py --help（实际通过）；入口参数为--root、--artifact-dir、--contract、--contract-sha、--action及--operation-id。
action=plan无DB连接、秘密配置读取或记录写入；recover启动只读，publish/rollback要求用户单独数据库授权及显式--authorized-database-write。该标志不授予授权。原始contract/封存包仅私有，不把身份或秘密值填入普通文档。
预期成功输出ok=true及安全计数/状态；失败ok=false与稳定error_code，退出2。重复执行编号直接拒绝，无第二次连接；提交/收据不确定只能新只读recover，不自动重放。
增量表须先通过独立受控DDL和完整schema验收，入口不创建表。生产使用Reliable SSH精确argv，不直接ssh，不串接上传/执行/验证。完整候选闭包/read_set/命令合同见[当前交接](handoffs/2026-09-17-qa-source-release-entry.md)、[机器证据](../tests/qa_regression/source_release_entry_20260917.json)。
