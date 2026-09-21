# 锁定底座恢复授权与连接中断

状态：已获单次底座恢复授权；远端写操作未开始，连接探测阻断。最后核对：2026-09-18。

事项：OPS-QA-RESTORE-FROZEN-BASE-20260917。
权威来源：用户本轮明确回复“允许底座恢复”；Reliable SSH 工具结果及本机 TCP 连接探测。适用范围：恢复已批准同一底座，不能视为后续路由候选已部署。

## 授权范围

用户已授权单次卸载已核实错误驻留（不删除权重），随后通过已安装的冻结管理器执行一次 Repair，恢复 `chiqiongblastfuenace:latest` 到已安装 `:1` 的完整 manifest `e4ad74c41d68de1c8004419d8141a2b2df2275fa08f0dcf326ca0e63fb6d8124`，仅预热该同一底座一次。无需重复询问此授权。

管理器已安装 SHA-256 `1f871a8bbbaa553233d318b3d019a5a63e68be38d0f0caa7d29cca731d44434f`；复用[单次卸载控制器](../../tools/unload_qa_unapproved_resident_once.ps1)，本轮重新核实其摘要为 `e03a21bacf0a4aeaa5b1209083684e1734f091c03bf533cc268017051c49e411`。前置条件、单次 claim、不确定不重放及验收边界见[管理器安装记录](2026-09-17-qa-single-base-manager-production-install.md)。

不授予备用模型切换、下载、权重删除、配置变更、服务重启或启用 Recovery 计划任务权限。原题复测继续复用[已启动后台程序](2026-09-18-qa-quiet-background-retest.md)，不得重复启动。

## 本轮实际结果

授权前最后一次成功只读核验：生产应用 proxy 为 V26 摘要 `d84cfe9d67ded7344e9c15b9de10c807d6d3846fc872b8f53d66b8bfaffe8382`；后台 PID 9808 身份匹配，等待固定模型，requests=0、completed=0、total=822；latest 与实际驻留均为错误的 9111…，:1 为批准 e4ad…；原 r3 为 953/953 completed。此状态是最近成功观测，不冒充连接中断后的当前状态。

授权后 Reliable SSH 的 probe_identity、read_file、简化 exec_argv 和 probe_host_routes 均返回工具调用超时。本机到 `10.30.220.12:22` 的 3 秒 TCP 连接探测也超时；既有 localhost SSH broker status 超时。不能据此断言服务器故障或后台进程退出。

本轮没有发送卸载、Repair、模型生成、上传或远端服务/任务写操作，因此未发生远端写完成状态不确定。未绕过 Reliable SSH 使用直接 SSH，也未杀死连接进程或重启服务。

## 连接恢复后的继续顺序

1. 使用 Reliable SSH 先核对主机身份、r3、后台进程命令/创建时间、progress、当前生产摘要与 git log、tags/ps、Disabled Recovery、manager/catalog 摘要及恢复 claim/audit。
2. 若固定身份已恢复，跳过模型管理写操作，独立验收后观察现有后台程序。若错误驻留仍精确符合控制器前置且能够证明未发送，仅执行已审查控制器一次。
3. 独立只读验收空驻留及受保护 PID 不变；为 Repair 记录一次性持久审计，然后执行冻结管理器一次。若此前已发或完成不确定，只读恢复审计，不重放。
4. 核对 latest/:1/唯一驻留的完整 e4ad manifest、标签、健康与受保护 PID；现有 worker 连续三轮身份稳定后自动开始串行 822 原题。不要新建批次，不将非空回答计为准确。

现有静默跟进需保存本次授权和连接中断事实，保留原频率与通知偏好；连接未恢复或状态不变时保持安静，恢复成功、重要缺陷或复测审查完成时通知。
