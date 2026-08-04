# 第三方来源与许可证说明

本目录的七个 `bf3d-*` Skill 是针对 GL02 高炉、Codex、Windows 和 Three.js 的中文项目适配版。它们重新组织并重写了公开工作流概念，不把上游 `SKILL.md` 原样作为可触发 Skill，也没有复制上游可执行脚本。精确 commit、tree、文件路径与 SHA-256 见 [skills/sources.lock.json](skills/sources.lock.json)。

## 锁定来源

| 项目 | 固定版本 | 许可证 | 用途 |
|---|---|---|---|
| [ahujasid/blender-mcp](https://github.com/ahujasid/blender-mcp/tree/6641189231caf3752302ae20591bc87fda85fc4e) | `6641189231caf3752302ae20591bc87fda85fc4e` | MIT，Copyright 2025 Siddharth Ahuja | 可选 MCP 执行层 |
| [RobLe3/cc-blender-skill](https://github.com/RobLe3/cc-blender-skill/tree/11016c9a5847897491dde935c346571bd7548e3d) | `11016c9a5847897491dde935c346571bd7548e3d` | MIT，Copyright 2026 RobLe3 | 主工作流、UV、材质、灯光、渲染与导出 |
| [ra100/blender-claude-plugin](https://github.com/ra100/blender-claude-plugin/tree/78e9151fdc9e01ce37f1d16a9b677c3047411885) | `78e9151fdc9e01ce37f1d16a9b677c3047411885` | MIT，Copyright 2026 ra100 | Blender 5.x API 参考 |
| [BlendOps](https://github.com/ThanhNguyxnOrg/blendops/tree/cf43f70eb636e5174e7c88d47288f0d25806c82d) | `cf43f70eb636e5174e7c88d47288f0d25806c82d` | MIT，Copyright 2026 BlendOps Contributors | QA、证据与 Web handoff |
| [jithinolickal/blender](https://github.com/jithinolickal/blender/tree/6bfca4973e7086696b08b108bfe6aae62ede33c0) | `6bfca4973e7086696b08b108bfe6aae62ede33c0` | Apache-2.0 | 多视角、检查点和单变量迭代纪律 |
| [dcc-mcp-blender](https://github.com/dcc-mcp/dcc-mcp-blender/tree/9052c4b2d69297c776f6f1ac7f842f3b1feaa81e) | `9052c4b2d69297c776f6f1ac7f842f3b1feaa81e` | MIT，Copyright 2024 Long Hao | 可选结构化 UV、烘焙、Shader 与验证工具 |

`vladmdgolam/agent-skills@0872d44b6e426603a9a74b6307a7c874b17b4ea5` 仅作为调研线索登记。该仓库在本次核查时没有完整 `LICENSE` 文件，因此没有复制其文字或代码；GLB/Three.js 规则由本项目独立重写。

## 视觉参考与 HDRI 资产

| 本地文件 | 来源 | 作者 | 许可证 | 校验和 | 用途与边界 |
|---|---|---|---|---|---|
| `source/references/hdri/industrial_sunset_2k.hdr` | [Poly Haven — Industrial Sunset](https://polyhaven.com/a/industrial_sunset) | Sergej Majboroda | [CC0](https://docs.polyhaven.com/en/faq) | MD5 `d601641106c0a0a2829b210b63f04f67`；SHA-256 `2a411097d65fcebfe00275641bd80350f95c7a1dbfc53b2260df85b296d2b990` | `HDRI_INDUSTRIAL_SUNSET_2K_V1` 展示环境候选；不代表 GL02 现场光照，不得未经视觉审核直接成为生产默认 |

该 HDRI 由 Poly Haven 官方文件接口取得，文件大小 `6,523,872` bytes。中性材质判断仍使用固定程序灯光；HDRI 只提供具有工业语境的 IBL/PMREM 候选，并须在 Blender 与 Three.js 同机位对比后才能改为视觉批准。

## Three.js r160 RectAreaLight LTC 供应商文件

R2T 为 P40 顶部面积灯的隔离光度标定固定了与本地核心字节级同版本的官方
`RectAreaLightUniformsLib.js`。所有来源、运行合同和许可证身份见
[vendor.lock.json](../../高炉前端数据/libs/three/vendor.lock.json)。

| 本地文件 | 固定来源 | 许可证/归属 | Bytes / SHA-256 | 用途与边界 |
|---|---|---|---|---|
| `高炉前端数据/libs/three/lights/RectAreaLightUniformsLib.js` | [three.js commit d04539a](https://github.com/mrdoob/three.js/blob/d04539a76736ff500cae883d6a38b3dd8643c548/examples/jsm/lights/RectAreaLightUniformsLib.js) | Three.js MIT；Copyright © 2010-2023 three.js authors | `313854` / `08085bc942253cd54948bf936fecb66b54514a135872656e475a1cab09b55214` | r160 `RectAreaLight` 的 64×64 Float/HalfFloat LTC 表与 `UniformsLib` 初始化；不提供 RectArea 阴影 |
| `高炉前端数据/libs/three/LICENSE-three-r160.txt` | [three.js r160 LICENSE](https://github.com/mrdoob/three.js/blob/d04539a76736ff500cae883d6a38b3dd8643c548/LICENSE) | MIT | `1081` / `852e0e8699169bf9f6fdc6bda3e682d078dcbc738b5d33e74df594721bff271d` | Three.js 源码再分发的完整许可与免责声明 |
| `高炉前端数据/libs/three/LICENSE-ltc_code-5c0770b.txt` | [selfshadow/ltc_code commit 5c0770b](https://github.com/selfshadow/ltc_code/blob/5c0770b74114b5dd38e9dae1b93f8486af7eac1b/LICENSE) | BSD-style，包含论文引用条件 | `1718` / `692a54e97fcadd0f04b14027386e53809c1dcf96de3e15b15af15731b15c1e94` | Three 内嵌 LTC 数值的上游归属、条件与免责声明 |

Three `r160` annotated tag 的 peeled commit 为
`d04539a76736ff500cae883d6a38b3dd8643c548`；本地
`three.module.js` 为 `1,272,972` bytes、SHA-256
`76dea8151bc9352aef3528b4262e249b2604f62543828328db978d060d61a495`，与该提交的
官方 build 完全一致。供应商安装器
[vendor_three_r160_rect_area_ltc.py](../../tools/vendor_three_r160_rect_area_ltc.py)
只接受不可变 commit URL 和上述 bytes/SHA，不允许 `latest`、`master`、未校验 CDN 或
自动更新哈希。

运行时必须让插件中的裸导入 `three` 指向同一 ESM 实例，在第一盏 RectAreaLight 前且
每个模块实例只调用一次 `RectAreaLightUniformsLib.init()`；四张 LTC 纹理及
`64×64` 尺寸不成立、WebGL 扩展不足或出现官方 missing-extension 错误时必须
fail-closed。Three r160 官方能力没有 RectArea 阴影，不能把另一盏灯的阴影写成
TOP Area 的等价功能。

## 修改声明

相对于上述来源，本项目版本已经做出显著修改：

- 删除 Claude 专属 `allowed-tools` 和固定 `mcp__blender__*` 工具名；
- 改为 MCP 能力语义映射和无 MCP 的 Blender 后台脚本回退；
- 改为 Windows/PowerShell 路径与项目本地 Skill 结构；
- 加入 115 传感器、L7～L16、五个工艺段、GL02 坐标和 Three.js r160 合同；
- 将通用资产流程改写为高炉哑光风化钢、UV/PBR 烘焙与浏览器验收流程；
- Apache-2.0 来源仅用于流程思想参考，项目文字为显著修改后的独立表达。

## 许可证正文

完整许可证可在各锁定 commit 的 `LICENSE` 文件中取得，其文件 SHA-256 已写入锁文件。若后续把任何上游原文、脚本或二进制实际复制进本目录，必须同时复制对应完整许可证，并在本文件增加具体文件级归属；不得只依赖当前“语义适配”说明。
