# 220.12 Ollama 模型问答测试与显存排查说明

> - 状态：历史排障快照（截至 2026-07-26）
> - 当前入口：[220.12 Ollama 自动拉起链路](../docs/22012_Ollama_27B_30B自动拉起链路_20260726.md)、
>   [项目排障手册](../docs/troubleshooting.md)
> - 适用边界：命令和判断口径可参考；当前模型、显存、runner 和服务状态必须重新只读探测。

日期：2026-07-08  
适用页面：`http://10.30.220.12:8093/#qa`  
目标模型：`bf-diagnosis-runtime:v1`  
Ollama 地址：`http://10.30.220.12:11434`

> **文档状态：2026-07-08～2026-07-14 历史取证。** 本文目标模型
> `bf-diagnosis-runtime:v1`（30.5B）和后续 `MAX_LOADED_MODELS=2` 段落不再是
> 现行生产配置。2026-07-26 起，11434 保持 `OLLAMA_MAX_LOADED_MODELS=1`，
> 只驻留 `chiqiong-blast-furnace:latest`（27.8B）；旧 30.5B manifest 已受控
> 隔离，直接请求应返回不可用。不得复制本文旧命令重新拉起 30.5B。现行说明见
> [22012 Ollama 单 27B 修复说明](../docs/22012_Ollama_27B_30B自动拉起链路_20260726.md)。

补充：系统守护服务的统一启停、热更新与参数修改规则已整理到 [22012_V4系统守护服务启停与热更新说明.md](22012_V4系统守护服务启停与热更新说明.md)。后续涉及 `BFV4PreviewProxy8093`、`BFV4PreviewWs8768`、`BFOllama11434`、Chronos 或服务配置 `arguments/env` 时，优先查看该文件。

## 一、快速测试命令

在本机 PowerShell 执行：

```powershell
cd /d "D:\文件\冀南钢铁运行中第二版本"
powershell -ExecutionPolicy Bypass -File ".\PT\test_22012_ollama_qa.ps1"
```

自定义问题：

```powershell
powershell -ExecutionPolicy Bypass -File ".\PT\test_22012_ollama_qa.ps1" -Question "请用一句话说明当前你是否能正常回答。"
```

该脚本会连续检查三层：

1. `http://10.30.220.12:11434/api/version`：Ollama 服务是否在线。
2. `http://10.30.220.12:11434/api/chat`：模型本体是否能直接回答。
3. `http://10.30.220.12:8093/api/qa/chat`：8093 页面实际使用的问答代理是否能回答。

## 二、单条命令测试

只看 Ollama 是否在线：

```powershell
Invoke-WebRequest -UseBasicParsing -Uri "http://10.30.220.12:11434/api/version" -TimeoutSec 15
```

直接测试 Ollama 模型对答：

```powershell
$payload = @{
  model = "bf-diagnosis-runtime:v1"
  stream = $false
  messages = @(@{ role = "user"; content = "请用一句话回答：你是谁？" })
  options = @{ temperature = 0.2; num_predict = 120 }
} | ConvertTo-Json -Depth 8

Invoke-WebRequest `
  -UseBasicParsing `
  -Uri "http://10.30.220.12:11434/api/chat" `
  -Method Post `
  -ContentType "application/json; charset=utf-8" `
  -Body $payload `
  -TimeoutSec 180
```

测试 8093 页面问答代理：

```powershell
$payload = @{
  message = "请用一句话回答：你是谁？"
  stream = $false
  current_snapshot = @{
    source = "manual_test"
    diagnosis = @{ main_label = "normal"; label = "normal" }
  }
} | ConvertTo-Json -Depth 8

Invoke-WebRequest `
  -UseBasicParsing `
  -Uri "http://10.30.220.12:8093/api/qa/chat" `
  -Method Post `
  -ContentType "application/json; charset=utf-8" `
  -Body $payload `
  -TimeoutSec 180
```

## 三、2026-07-08 实际核查结论

本次核查时，Ollama 服务本体是运行的：

- `BFOllama11434`：`Running`，启动类型 `Automatic`。
- `11434` 端口可访问。
- `GET /api/version` 返回 `0.20.2`。
- `GET /api/tags` 可看到 `bf-diagnosis-runtime:v1`。
- 直接调用 `POST /api/chat` 可以在约 1 秒内返回回答。

但 8093 页面实际走的 `POST /api/qa/chat` 返回过：

```json
{
  "ok": false,
  "error": "高炉大模型服务 HTTP 500",
  "detail": "{\"error\":\"model failed to load, this may be due to resource limitations or an internal error, check 高炉大模型服务 server logs for details\"}"
}
```

同时服务器显卡上 `nvidia-smi` 显示 L20 约 46GB 显存几乎被占满：

```text
Memory-Usage: 45688MiB / 46068MiB
```

占用显存的是多个 `F:\Ollama\ollama.exe` runner 进程，其中两个约各占 20GB，另一个约占 5GB。`ollama ps` 显示当前模型：

```text
bf-diagnosis-runtime:v1    20 GB    79%/21% CPU/GPU    32768
```

Ollama 日志中已有明确错误：

```text
available="65.4 MiB"
CUDA error: out of memory
model failed to load, this may be due to resource limitations
```

因此，`#qa` 页面“持续不回复”的直接原因不是 Ollama 服务没启动，而是 GPU 显存被多个 Ollama runner 占满后，8093 代理触发模型加载/切换时发生 CUDA OOM，代理返回 500，前端没有把这个错误明显展示出来。

## 四、2026-07-08 runner 进程追踪结论

当前 `11434` 对外监听进程只有一个：

```text
PID 8840  "F:\Ollama\ollama.exe" serve  StartTime=2026-07-07 18:40:00
```

三个占 GPU 的 `ollama.exe runner` 都不直接监听 `11434`，而是监听 `127.0.0.1` 的内部随机端口，由 `ollama serve` 调度：

| PID | 启动时间 | 父进程 | 内部端口 | 显存 | 判断 |
|---|---|---|---|---|---|
| `18112` | `2026-07-07 10:17:01` | `5852`，当前已不存在 | `54229` | 约 `20288MiB` | 旧 `ollama serve` 遗留 runner，疑似孤儿进程 |
| `356` | `2026-07-07 10:21:48` | `17396`，当前已不存在 | `54404` | 约 `20288MiB` | 服务安装/重试阶段遗留 runner，疑似孤儿进程 |
| `9360` | `2026-07-07 20:41:48` | 当前 `8840` | `53749` | 约 `5110MiB` | 当前 `BFOllama11434` 服务正常拉起的 `bf-diagnosis-runtime:v1` runner |

`11413` 端口未发现监听；本项目当前 Ollama 对外端口是 `11434`。

从 `F:\Ollama\logs\ollama_11434.nssm_install.log` 看，`2026-07-07 10:20:20` 安装服务时执行过：

```text
stop_existing_listener port=11434 pid=5852 command=F:\Ollama\ollama.exe serve
install_service name=BFOllama11434
start_service name=BFOllama11434
```

这说明昨天服务化安装确实停止了旧的 `11434` serve 并启动了新的 `BFOllama11434`。但停止旧 serve 时没有同步清理旧 serve 已经拉起的 runner，所以 PID `18112`、`356` 留在显卡上继续占用约 40GB 显存。后续当前服务在 `20:41:48` 又按请求拉起 PID `9360`，于是总显存接近打满。

### 2026-07-08 18:43 清理结果

按“保留当前 `11434` 服务链路，只清理父进程已不存在的 runner”的原则，已停止：

- `PID 18112`：父进程 `5852` 已不存在，占用约 `20288MiB`。
- `PID 356`：父进程 `17396` 已不存在，占用约 `20288MiB`。

已保留：

- `PID 8840`：当前 `ollama serve`，监听 `11434`。
- `PID 9360`：当前 `8840` 直接拉起的 `bf-diagnosis-runtime:v1` runner，占用约 `5110MiB`。

清理后 `nvidia-smi` 显示显存从约 `45688MiB / 46068MiB` 降到约 `5111MiB / 46068MiB`。随后运行 `PT\test_22012_ollama_qa.ps1` 复测：

- 直接 `11434/api/chat` 成功。
- `8093/api/qa/chat` 已恢复业务成功，不再返回 `model failed to load`。

## 五、服务器侧排查命令

在 220.12 服务器管理员 PowerShell 执行：

```powershell
Get-Service -Name BFOllama11434,BFV4PreviewProxy8093
Get-NetTCPConnection -LocalPort 11434,8093 -State Listen
nvidia-smi
F:\Ollama\ollama.exe ps
Get-Content -LiteralPath "F:\Ollama\logs\ollama_11434.service.err.log" -Tail 80
```

从本机通过远程脚本执行：

```powershell
python tools\remote_22012_exec.py --allow-agents-password --timeout 120 --command "nvidia-smi; F:\Ollama\ollama.exe ps; Get-Content -LiteralPath 'F:\Ollama\logs\ollama_11434.service.err.log' -Tail 80"
```

## 六、判断口径

- `11434/api/chat` 能回答，说明 Ollama 本体和模型基本可用。
- `8093/api/qa/chat` 失败，说明页面代理、上下文构造、模型加载或代理到 Ollama 的调用存在问题。
- `nvidia-smi` 显示显存剩余很少，并且 Ollama 日志出现 `CUDA error: out of memory`，说明优先处理显存占用。
- `api/ollama/status` 只证明服务和模型名可见，不等于一次完整问答一定能生成成功。

## 七、建议修复方向

1. 清理重复或残留的 Ollama runner，只保留 `BFOllama11434` 服务管理下的必要 runner。
2. 复查是否同时加载了多个同体量模型，避免 `bf-diagnosis-runtime:v1` 与其他大模型重复占用 20GB 级显存。
3. 8093 的 `/api/qa/chat` 应把 `model failed to load`、`CUDA out of memory` 明确返回给前端，不要只表现为页面无回复。
4. 健康检查不要只调用 `/api/tags` 或 `/api/ollama/status`，应增加一次小 `POST /api/chat` 冒烟，以发现“服务在线但生成失败”的状态。

## 八、2026-07-08 单模型常驻与系统守护修复

结论：`bf-diagnosis-runtime:v1` 不是一个独立 Windows 服务。它是 `BFOllama11434` 这个 Ollama 服务中的模型 runner，由 `11434/api/chat` 或 8093 代理请求触发加载。8093 代理服务是 `BFV4PreviewProxy8093`。

本次已把 8093 代理实际生成模型统一为：

```text
bf-diagnosis-runtime:v1
```

涉及配置：

- `F:\高炉炼铁项目-real-sensor-v2_V4_8093_PREVIEW\tools\service_configs\22012_BFV4PreviewProxy8093.json`
  - `--model` 已改为 `bf-diagnosis-runtime:v1`
  - `BF_LLM_MODEL` 已改为 `bf-diagnosis-runtime:v1`
- `F:\高炉炼铁项目-real-sensor-v2_V4_8093_PREVIEW\tools\service_configs\22012_BFOllama11434.json`
  - `OLLAMA_MAX_LOADED_MODELS=1`，限制同一 Ollama 服务只加载一个模型。
  - `OLLAMA_KEEP_ALIVE=24h`，避免默认几分钟后卸载。
  - 健康检查增加 `POST /api/chat` 极短问答，并在请求中设置 `keep_alive=24h`。

新增系统守护控制脚本：

```text
F:\高炉炼铁项目-real-sensor-v2_V4_8093_PREVIEW\tools\manage_22012_managed_services.ps1
```

常用命令如下。

查看所有 V4 系统服务状态：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File "F:\高炉炼铁项目-real-sensor-v2_V4_8093_PREVIEW\tools\manage_22012_managed_services.ps1" -Action status
```

保证服务存在且运行：服务已在线时不重复启动；服务停止时启动；服务缺失时按配置安装并启动：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File "F:\高炉炼铁项目-real-sensor-v2_V4_8093_PREVIEW\tools\manage_22012_managed_services.ps1" -Action ensure
```

只停止 Ollama 守护服务：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File "F:\高炉炼铁项目-real-sensor-v2_V4_8093_PREVIEW\tools\manage_22012_managed_services.ps1" -Action stop -ConfigPath "F:\高炉炼铁项目-real-sensor-v2_V4_8093_PREVIEW\tools\service_configs\22012_BFOllama11434.json"
```

只启动 Ollama 守护服务：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File "F:\高炉炼铁项目-real-sensor-v2_V4_8093_PREVIEW\tools\manage_22012_managed_services.ps1" -Action start -ConfigPath "F:\高炉炼铁项目-real-sensor-v2_V4_8093_PREVIEW\tools\service_configs\22012_BFOllama11434.json"
```

重启 Ollama 并重新健康检查：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File "F:\高炉炼铁项目-real-sensor-v2_V4_8093_PREVIEW\tools\manage_22012_managed_services.ps1" -Action restart -ConfigPath "F:\高炉炼铁项目-real-sensor-v2_V4_8093_PREVIEW\tools\service_configs\22012_BFOllama11434.json"
```

人工执行健康检查：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File "F:\高炉炼铁项目-real-sensor-v2_V4_8093_PREVIEW\tools\check_managed_nssm_service_health.ps1" -ConfigPath "F:\高炉炼铁项目-real-sensor-v2_V4_8093_PREVIEW\tools\service_configs\22012_BFOllama11434.json"
```

2026-07-08 20:08 复核结果：

```text
ollama_health_exit=0
proxy_health_exit=0
ollama ps:
bf-diagnosis-runtime:v1    20 GB    100% GPU    32768    24 hours from now
nvidia-smi:
20323 MiB / 46068 MiB
8093 /api/ollama/status:
target_model = bf-diagnosis-runtime:v1
```

2026-07-08 20:09 复核 `8093/api/qa/chat`：

```text
elapsed_ms=7494
ok=true
answer=当前模型服务在线，系统持续提供炉况诊断与优化建议。
ollama ps 仍仅显示 bf-diagnosis-runtime:v1，100% GPU，24 hours from now
```

## 九、2026-07-14 8093 模型供应切换补充

2026-07-14 已将 8093 代理底层模型供应从 `bf-diagnosis-runtime:v1` 切换为：

```text
chiqiong-blast-furnace:latest
```

当前公开状态接口返回：

```text
target_model = 炽穹·高炉炼铁大模型
```

注意：`target_model` 是公开显示名，不是底层 Ollama 标签。真实底层模型以 8093 父进程命令行和服务配置共同确认：

```text
start_v3_8092_python.py ... --model chiqiong-blast-furnace:latest --public-model 炽穹·高炉炼铁大模型 --port 8093
```

本次切换暴露的关键规则：

- 只改 `env.BF_LLM_MODEL` 不够；`22012_BFV4PreviewProxy8093.json` 的 `arguments` 中如果仍有旧 `--model`，启动脚本会用命令行参数覆盖环境变量。
- 普通 `Restart-Service` 有时不能清掉已经由守护脚本拉起的 8093 Python 子进程；旧子进程继续占用端口时，页面仍会返回旧模型状态。
- 修改模型供应、端口、Python 入口、后端环境变量这类启动期参数时，必须停止对应守护服务、确认端口释放或清理仅属于 `V4_8093_PREVIEW` 的旧监听进程，再启动服务。
- 修改 HTML/CSS/前端 JS 静态内容时，通常可以直接刷新页面或加 cache-bust 参数热生效，不需要停止守护进程。

详细启停命令、热重载边界和验证清单见 [22012_V4系统守护服务启停与热更新说明.md](22012_V4系统守护服务启停与热更新说明.md)。

## 十、2026-07-14 RAG 检索保留 27B 常驻修正

8093 问答链路启用 RAG 时会调用 `nomic-embed-text` 生成查询向量。此前 `BFOllama11434` 使用 `OLLAMA_MAX_LOADED_MODELS=1`，embedding 小模型加载时可能把 27B `chiqiong-blast-furnace:latest` 从 Ollama runner 中换出，随后正式回答又要重新加载 27B，造成首 token 延迟明显升高。

当前已将 `F:\高炉炼铁项目-real-sensor-v2_V4_8093_PREVIEW\tools\service_configs\22012_BFOllama11434.json` 调整为：

```text
OLLAMA_MAX_LOADED_MODELS=2
OLLAMA_KEEP_ALIVE=24h
```

该设置的目的不是同时常驻多个大模型，而是允许 27B 主问答模型与 `nomic-embed-text` embedding 小模型同时驻留。这样 RAG 检索阶段调用 embedding 后，27B 仍保持常驻，降低每轮问答重新加载大模型带来的等待。

运维边界：

- 健康检查和 8093 代理仍以 `chiqiong-blast-furnace:latest` 为主模型。
- 不应主动常驻旧的 `bf-diagnosis-runtime:v1` 或其它 20GB 级大模型，避免重新打满显存。
- 修改 `OLLAMA_MAX_LOADED_MODELS`、`OLLAMA_KEEP_ALIVE` 等启动期参数后，必须重启 `BFOllama11434` 并用 `/api/ps`、`/api/qa/chat` 验证 27B 与 RAG 检索链路。
