# 2026-08-05 220.12 VPN 直达 IMES/Vastbase/pSpace 交接

## 结果

需求 `OPS-22012-DIRECT-SOURCE-RELAYS-20260805` 已部署：

| 入口 | 目标 | 验收 |
| --- | --- | --- |
| `http://10.30.220.12:18080/` | IMES Web `10.10.181.209:8080` | HTTP 200，根地址进入 `/imes.web/` |
| `10.30.220.12:15433` | Vastbase `10.10.181.195:5432` | 数据库认证、只读事务和上游身份核验通过 |
| `10.30.220.12:18889` | pSpace `10.22.181.243:8889` | SDK 认证并读取真实静压力点，质量 `Good` |

18080 原有页面保留在 `/g13.html`。防火墙只允许本轮核实的 VPN 客户端地址
`10.30.200.18`。VPN 地址变化后需受控更新，不得扩大为任意来源。

## 实现与测试

- [Nginx配置补丁](../../tools/patch_22012_nginx_imes_web.py)
- [受控远端部署](../../tools/remote_deploy_22012_direct_source_relays.ps1)
- [运行态只读探针](../../tools/remote_probe_22012_direct_relays.ps1)
- [补丁合同测试](../../tests/test_patch_22012_nginx_imes_web.py)

本地测试为 `3 passed`。首次部署因远端旧 NetSecurity 模块不接受
`New-NetFirewallRule -DisplayGroup` 而自动回滚；移除该兼容性参数后第二次部署成功。
最终远端结果：

- 备份：`F:\高炉炼铁项目-real-sensor-v2_V4_8093_PREVIEW\logs\deploy_backups\22012_direct_source_relays_20260805_151949`
- Nginx SHA-256：`1FF815F024098B7E94A5158222B27F22A218A789A4A1D330380BA100745A6294`
- 8093 PID：`6892 -> 6892`
- 8768 PID：`4340 -> 4340`
- 8094 PID：`12908 -> 12908`
- 8770 PID：`12956 -> 12956`

## 登录与业务页验收

用户已在浏览器内输入口令并提交验证码。220.12 Nginx 访问日志确认本次登录全程使用
`Host: 10.30.220.12:18080`：`POST /imes.web/login.do` 成功后立即返回
`GET /imes.web/mes/desktop.do` 与 `GET /imes.web/mes/main.do`，随后炉次化验、生产实绩、
炉渣检验等业务列表请求均返回 HTTP 200。这证明不是本机 `127.0.0.1` 跳板会话，也不只是
登录页可达，而是浏览器登录后的 IMES 业务会话已通过 220.12 反向代理正常工作。

账号口令、验证码和 `JSESSIONID` 只存在于受控配置或浏览器会话，不写入本交接、Nginx
配置、端口转发、防火墙或验收日志。

数据库协议验收使用 `BEGIN READ ONLY`：连接入口为 `10.30.220.12:15433`，服务端报告
实际地址 `10.10.181.195:5432`、数据库 `vastbase`，`transaction_read_only=on`，随后
`ROLLBACK`。pSpace 协议验收使用现有 Python SDK 和业务账号连接
`10.30.220.12:18889`，读取 `P_static_lower_A` 对应真实点成功，返回实时数据时间、数值和
`Good` 质量码。两项均未写生产数据。

## 回滚

如需回滚，先恢复备份中的 `nginx.conf.before` 并执行 Nginx `-t`/`-s reload`，
再只删除 `10.30.220.12:15433` 与 `10.30.220.12:18889` 两条本项目 portproxy，
最后删除名称以 `BFSourceRelay` 开头的三条本项目防火墙规则。禁止停止 Nginx 主机
上的无关站点，也禁止重启 8093/8768/8094/8770。
