# 2026-08-11 8093 炉喉变量、自动诊断与 PowerShell 7 生产闭环

## 结果

- 8093 炉况诊断页核心诊断变量从 36 项调整为 32 项，仅移除 `T_throat_A-D`；`T_top_A-D` 保留，通用传感器目录和后端数据未删除。
- 恢复生产缺失的 `assets/bf-heat-performance-quality-8093-query-v2.js`，保留炉次/日期/化验筛选、出铁段和原始试样功能。
- 五分钟自动诊断的 Ollama 摘要异常改为结构化 `degraded` 降级，不再把质量、诊断和队列均成功的一轮误标为失败；2026-08-11 16:51 生产任务退出码为 0。
- 禁用两个旧启动任务：`\BlastFurnaceV3Proxy8093`、`\BlastFurnace8093Proxy_NewProject`。
- `BFV4PreviewProxy8093` NSSM 包装、`\BlastFurnaceServices\BFV4PreviewProxy8093HealthCheck`、`\BlastFurnace8093DailyBaseline20d` 已迁移到 `C:\Program Files\PowerShell\7\pwsh.exe`。
- 远端构建目录只保留当前 `dashboard-main-GX_5dx5H.js` 和最近回滚 `dashboard-main-CcxwpZA4.js`；删除四个更旧主包，共 2,430,462 字节。

## 8093 快速上线证据

- 不可变发布清单：`.tmp/8093-remove-throat-20260811/prepared-release.json`，内容 SHA-256 `0E75E0AC7B41395DC2F3ED286C7668D3449107B4A46C69AFA57D33FF907386C0`。
- 增量上传 3 文件：4.388 秒。
- 守卫停—替换—启及 HTTP/哈希/隔离验收：28.607 秒。
- 快速上线合计：约 32.995 秒；未重复执行构建和 17 组合矩阵。
- 备份：`F:\高炉炼铁项目-real-sensor-v2_V4_8093_PREVIEW\backups\8093_remove_throat_restore_query_20260811_163549`。
- 8093 上线时 PID `8840 -> 19080`；后续 PowerShell 7 包装迁移后当前监听 PID 为 `9068`。
- 8768/8094/8770/5432/8892/11434 在各阶段均保持原 PID。

## 验收

- 聚焦 pytest：37 passed；PowerShell 迁移复核：9 passed。
- 本机炉况诊断页 standard 矩阵：17/17，39.061 秒。
- Luna：`gpt-5.6-luna`、low、read-only，结论 PASS。
- 生产 Chromium `1366×768`：32 张核心卡、炉喉 0 张、炉顶四点齐全、炉次查询资源 200、控制台错误 0。
- 生产截图：`logs/8093_remove_throat_smoke_20260811_165415/diagnosis-1366x768.png`。

## 受控失败与修正

- 浏览器验证器的 `--base-url` 只能传站点根地址；传入完整页面会重复拼接路径。夹具补齐了诊断复核资产、唯一 episode、ABC latest API，并在每个固定场景清理 localStorage。
- NSSM 2.24 的 `get` 输出在 PowerShell 7 管道中出现 UTF-16 空字符；只读和迁移校验改为读取服务注册表的 `Application/AppParameters/AppDirectory`，写入仍使用 NSSM。
- Windows Server 2016 的计划任务 CIM 状态返回数字 1/3/4；迁移器统一映射为 Disabled/Ready/Running。
- 每日基线 `ValidateOnly` 暂存验证不能按暂存目录寻找配置；新增显式 `-ProjectRoot`，生产计划任务不传参数时仍保持原路径语义。

这些失败指纹已形成候选经验，但尚未满足同一指纹三次出现和同一修复成功两次的自动晋升条件，未越权写入 learned playbook。
