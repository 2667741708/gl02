# 文档链接规范

> - 状态：当前规范
> - 最后核对：2026-08-11

## 仓库内链接

普通文档入口使用相对路径：

```md
[系统架构](architecture.md)
[PT 文档导航](../PT/README.md)
```

定位代码、配置或测试时，把路径与真实行号写在同一个链接中：

```md
[函数名 src/path/file.py:L120-L168](../src/path/file.py#L120-L168)
```

无法核实行号时使用 `TODO-LINES`，禁止编造：

```md
[函数名 src/path/file.py:TODO-LINES](../src/path/file.py)
```

## 状态与时间

容易变化的文档开头应包含：

```md
> - 状态：当前合同 / 参考 / 历史快照 / 已取代
> - 最后核对：YYYY-MM-DD
> - 权威来源：链接
> - 适用边界：一句话
```

带日期的 handoff、报告、PID、端口监听、哈希和数据库行数只是核查时点证据，不能省略日期，
也不能自动表述为今天仍有效。

## 禁止写法

- 只有路径或“第几行”，但没有可点击链接。
- 把一次性运行结果复制到多个“当前状态”文档。
- 链接不存在的文件或给旧文档贴上“当前”而不核对。
- 在链接、示例或截图中泄露密码、Cookie、Token、私钥或个人信息。

## 验证

修改文档后检查本地链接目标：

```powershell
python .\tools\check_markdown_links.py README.md AGENTS.md docs/project_onboarding.md PT/README.md
```

该工具只检查文件目标是否存在，不判断 Markdown 渲染器生成的标题锚点；中文标题锚点仍需在
实际仓库或应用渲染器中抽查。
