# IMES 网络与 Vastbase 直连排障

## 0. 当前复核（2026-07-19 21:07）

当前故障已经不是下文 2026-07-16 的纯 TCP 超时：

- `10.10.181.209:8080` 与 `10.10.181.195:5432` 当前 TCP 均可建立；
- 两个目标都走 `10.10.0.0/16 -> Meta -> 198.18.0.2` 专用路由，
  不走 WLAN 默认路由；
- Chrome 访问 Web 返回 `ERR_EMPTY_RESPONSE`，页面提示“未发送任何数据”；
- `curl --noproxy "*"` 返回 `Empty reply from server`，PowerShell HTTP
  请求返回“基础连接已经关闭：连接被意外关闭”。

因此浏览器已经到达 `8080` 套接字，但该路径没有返回任何有效 HTTP
响应；这不是 URL 拼错、404、登录账号或验证码问题。故障范围已缩小到
“当前 Meta 私网路径的 HTTP 转发/访问策略”或
“`10.10.181.209:8080` Web 服务主动空响应/重置连接”。

备用的 220.12 跳板本次无法完成隔离验证：`10.30.220.12:22/5432`
当前均超时，`127.0.0.1:18080` 因转发器未能建立而返回
`ERR_CONNECTION_REFUSED`。在恢复 220.12 或正式 SSLVPN 路径后：

1. 若 `http://127.0.0.1:18080/imes.web/` 能返回登录页，则故障在本机
   当前 Meta 直连路径；
2. 若经 220.12 仍为 `Empty reply`，应由 IMES 运维检查 `.209` 上
   8080/Tomcat/应用日志、反向代理和源地址白名单。

不要把 `10.10.181.195:5432` 的 TCP 可达误写为 IMES 网页正常，也不要
把 Web 系统 `10.10.181.209:8080` 称作数据库端口；Vastbase 数据库是
`.195:5432`。

## 1. 当前结论（2026-07-16）

浏览器错误为 `ERR_CONNECTION_TIMED_OUT`。本机实测：

- `10.10.181.209:8080` 和 `10.10.181.195:5432` TCP 均失败；
- 两个目标均通过 WLAN 默认网关 `192.168.43.1`，没有更具体的 VPN 路由；
- `Sangfor aTrust VNIC` 状态为 `Disconnected`；
- 没有检测到 aTrust/SSL VPN 进程；
- Clash Verge 正在运行，系统代理为 `127.0.0.1:7897`，但绕过列表包含 `10.*`。

因此主要故障是 SSL VPN 数据隧道没有真正建立，或 VPN 策略没有下发 `10.10.181.0/24`。Clash 可能影响 VPN 客户端的登录过程，但不是当前 IMES 私网 HTTP 请求的直接转发路径。

## 2. 一键诊断

```powershell
.\tools\diagnose_imes_network.ps1 `
  -OutFile .\logs\imes_network_diagnosis_20260716.json
```

成功信号：

1. `Sangfor aTrust VNIC` 为 `Up`；
2. 目标 `specific_vpn_route=true`，且不再使用 `WLAN/0.0.0.0/0`；
3. Web 的 `tcp_ok=true`；
4. Vastbase 的 `tcp_ok=true` 后再测试数据库认证。

## 3. 推荐恢复顺序

1. 完全退出 aTrust/SSL VPN 客户端及残留登录页，再重新启动客户端并完成登录、二次认证和“连接”动作。
2. 登录后先运行诊断脚本，不要只依据客户端界面上的“已登录”。
3. 若 VNIC 仍为 `Disconnected`，检查/修复 aTrust 虚拟网卡驱动，必要时以管理员身份重启 aTrust 客户端。
4. 若 VNIC 已连接但没有 `10.10.181.0/24` 路由，联系 VPN 管理员核对账号资源组和分流策略；仅连通 `10.30.220.*` 或 `10.22.181.*` 不代表具有 IMES 网段权限。
5. Clash 可以保持运行，因为当前 `10.*` 已在系统代理绕过列表。若 aTrust 登录过程仍失败，可临时关闭 Clash 的“系统代理”后重新登录做隔离试验；登录成功后必须再次检查路由，不能只看网页提示。
6. 不要在不知道 aTrust 隧道网关的情况下手工添加永久路由；错误路由可能把其他生产网段送错出口。

## 4. 分层验证

```powershell
# 路由和端口
.\tools\diagnose_imes_network.ps1

# Vastbase 只测 TCP
python .\tools\export_vastbase_local.py --tcp-check

# TCP 成功后，发现数据库账号实际可读对象
python .\tools\export_vastbase_local.py --discover `
  --output-dir .\exports\imes_vastbase_catalog

# Web 端口成功后，再运行 Web 白名单客户端
python .\tools\export_imes_web_readonly.py --list-datasets
```

故障层次必须分开判断：路由失败不是账号错误；TCP 成功但 Vastbase 认证失败才是数据库账号/权限问题；Web 登录成功也不等于相同账号能直连 Vastbase。
