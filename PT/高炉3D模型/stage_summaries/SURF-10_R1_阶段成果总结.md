# SURF-10 R1 阶段成果总结

> 需求：`REQ-BF3D-10STAGE-EXECUTION-20260718`  
> 证据包：`work/SURF_10_20260718_R1/`  
> 机器状态：`candidate_ready_for_review`，`20/20 pass`  
> 最终门禁结论：`iterate`  
> 证据口径：仅使用本阶段证据包和[十阶段多智能体执行台账](../十阶段多智能体执行台账.md)。

## 阶段目标

只针对一个代表性炉壳段制作材质小样，在既有 P40 哑光粗糙方向上增加橘皮/细砂 Detail Normal、微点蚀、微粗糙变化和少量重力约束污迹，输出近、中、远中性 LookDev 及 BaseColor、Roughness、Normal 通道证据；不扩展到全炉，不导出或替换正式 GLB。

## 输入及 SHA

| 输入 | SHA-256 | 证据 |
|---|---|---|
| `work/P40_FIXED_LOOKDEV_20260717_P36_FINAL/P40_LOOKDEV_APPROVED.blend` | `03635cf6608a54c4a671fb4d84adcb9451a36fe47cea7b564af2d4d3b69b2256` | [执行命令记录](../work/SURF_10_20260718_R1/surf10_execution_command.json) |

[机器报告](../work/SURF_10_20260718_R1/surf10_machine_report.json)中的 `input_checkpoint` 实际指向输出候选并使用候选 SHA；它与命令记录的真实输入字段不一致。本总结以命令记录的 `input_blend/input_sha256` 为实际输入，机器报告该字段记为证据缺口。

## 实际执行者与审核者

| 职责 | 身份 | 已知结论 |
|---|---|---|
| R1 执行者 | `unknown` | 允许证据未记录 R1 智能体身份 |
| R1 视觉审核 | `/root/review_surf10_visual` | `iterate` |
| R1 规范审核 | `/root/review_surf10_spec` | `iterate` |
| R2 当前执行 | `/root/surf10_r2_execute`，`blender_stage_executor` | 仅说明后续归属，不是 R1 执行者 |
| 总控 | `/root` | R1 永久保留为失败证据，不批准 |

角色和结论来自[执行台账](../十阶段多智能体执行台账.md)。

## 实际命令与退出码

```text
"D:\Program Files\Blender Foundation\Blender 5.2\blender.exe" --background "D:\文件\冀南钢铁运行中第二版本\PT\高炉3D模型\work\P40_FIXED_LOOKDEV_20260717_P36_FINAL\P40_LOOKDEV_APPROVED.blend" --python "D:\文件\冀南钢铁运行中第二版本\PT\高炉3D模型\run_surf10_surface_sample.py" -- --blender-child --output-dir "D:\文件\冀南钢铁运行中第二版本\PT\高炉3D模型\work\SURF_10_20260718_R1" --width 1200 --height 800 --texture-resolution 1024
```

退出码：`0`。详见[执行命令记录](../work/SURF_10_20260718_R1/surf10_execution_command.json)、[标准输出](../work/SURF_10_20260718_R1/runner.stdout.log)和[标准错误](../work/SURF_10_20260718_R1/runner.stderr.log)。

## 主要产物

| 产物 | SHA-256 / 说明 |
|---|---|
| [SURF10_SURFACE_SAMPLE_CANDIDATE.blend](../work/SURF_10_20260718_R1/SURF10_SURFACE_SAMPLE_CANDIDATE.blend) | `be81cf00a2df07283f7cfcb53dff568b4009106ed51c43bba034de277019d923` |
| [surf10_machine_report.json](../work/SURF_10_20260718_R1/surf10_machine_report.json) | `bd90fcdc9c5b9ac071c2d0ea78ed170be1ff0eab5a8acc90ff486f51a977068a` |
| [surf10_material_manifest.json](../work/SURF_10_20260718_R1/surf10_material_manifest.json) | `9cf1bd6bad8d0b9d4b2a5f495392daabd184c18d4722f910e4a000895e6bb777` |
| [近景 Beauty](../work/SURF_10_20260718_R1/renders/beauty/SURF10_BEAUTY_NEAR_DETAIL.png) | `8c3edaf6a3e91fc84bd3a9dd4ed95d2d8921dfbf24afb68b786889680d8af37d` |
| [中景 Beauty](../work/SURF_10_20260718_R1/renders/beauty/SURF10_BEAUTY_MID_SAMPLE.png) | `90662ba6cbb6917f495b4ff77064c435d987a073ab8b3ccb6eeef02ad1f85701` |
| [远景 Beauty](../work/SURF_10_20260718_R1/renders/beauty/SURF10_BEAUTY_FAR_CONTEXT.png) | `7b4e97bf838ebcefd678ed560b573c1bcf0068a01e6342de574187320503e2e6` |
| [BaseColor 通道](../work/SURF_10_20260718_R1/renders/channels/SURF10_CHANNEL_BASECOLOR_NEAR.png) | `a17e3501b2cd48bd35c7165a7a5437c7bbecb54a5a165c0d8083932c8add8bbc` |
| [Roughness 通道](../work/SURF_10_20260718_R1/renders/channels/SURF10_CHANNEL_ROUGHNESS_NEAR.png) | `dbcab553f2ba24f79982b85c1e447049e0a528cc2d46dcbc96cde40e75a85298` |
| [Normal 通道](../work/SURF_10_20260718_R1/renders/channels/SURF10_CHANNEL_NORMAL_NEAR.png) | `985febad411466dec1e509d4873f263652f14d2e45ff008604bd933300ab135e` |
| [BaseColor 纹理](../work/SURF_10_20260718_R1/textures/SURF10_basecolor_orange_peel_dust_streaks.png) | `afe518818a25081c81b0b6d54dee0d2ce2e497615ab9a3d57c84be151316e2da` |
| [Roughness 纹理](../work/SURF_10_20260718_R1/textures/SURF10_roughness_micro_pitting_dust.png) | `67272de6f6249f79a62eb18b330ae3138434674287c7d4bd830397cfd08c9839` |
| [Normal 纹理](../work/SURF_10_20260718_R1/textures/SURF10_normal_orange_peel_fine_sand.png) | `76b95e47b969f50a01c02277e35e8133640f8d5b6a8fc42291de4fb41c6eebf2` |
| [artifact_sha256.json](../work/SURF_10_20260718_R1/artifact_sha256.json) | 包含 R1 证据及不应进入批准清单的 `.blend1` |

## 机器断言

- `20/20 pass`，失败项 0。
- 只从 `APPROX_GL02_FURNACE_SHAFT` 派生一个审查面板；原五个炉体段未改。
- 115 个传感器、80 个炉身测温点和 L7～L16 全部保留。
- 五个炉体段矩阵签名前后均为 `e70016d991ca06c7182da84f3ce8a9c52fe7cf8042af824dee9aa2f0e82f78ef`。
- 五个炉体段材质槽签名前后均为 `2d1977fa5d9eb99ae3ae4124125508178463b1a39bdcbeca969ee09f90ef3497`。
- 三张 Beauty、三张通道图和三张直接纹理均非空。
- 未生成 GLB，原炉体段没有被分配小样材质。

## 视觉审核结论

`/root/review_surf10_visual = iterate`。机器 `20/20` 不代表视觉通过。台账记录的失败点为：

- 近景微颗粒和微凹凸不可读；
- 点蚀呈数字化/方块状斑点，不够自然；
- 存在斜纹和重复感；
- 远景偏平涂，中远景缺少稳定的材质层次。

## 规范审核结论

`/root/review_surf10_spec = iterate`。主要包装问题是 `SURF10_SURFACE_SAMPLE_CANDIDATE.blend1` 被纳入[产物哈希清单](../work/SURF_10_20260718_R1/artifact_sha256.json)，但 Blender 备份文件不应进入批准清单。R2 必须禁用或排除该备份文件。

## 保护合同

- 只允许修改一个复制出的代表性炉壳材质小样。
- 原五个炉体段、115 个传感器、L7～L16 的名称、矩阵和材质槽保持不变。
- 不进行全炉材质铺开，不导出或替换正式 GLB。
- 不接 glTF/Three.js，不把程序纹理小样称为生产烘焙材质。
- R1 目录永久保留，不允许 R2 覆盖。

## 批准/迭代边界

- **机器通过**：仅说明文件存在、保护合同和产物数量满足自动检查。
- **未批准**：R1 材质外观、通道质量、包装清单、全炉推广、SURF-20 启动和正式 GLB。
- **正式结论**：`iterate`，不得写成 `approved`。
- R2 只可修复近景微凹凸、自然点蚀、中远景抗重复以及 `.blend1` 包装问题；不得顺带扩展全炉。

## 已知问题

- 小样是从炉身段包围盒派生的 clean-UV 曲面审查面板，不是烘焙完成或 GLB-ready 的生产材质。
- 通道图来自程序化小样贴图，尚无 glTF/Three.js 交接。
- 机器报告的 `input_checkpoint` 错指输出候选，与命令记录矛盾。
- R1 执行智能体身份在允许证据内为 `unknown`。
- 两位审核者的独立原始审核文件在允许证据内为 `unknown`；具体结论由台账记录。
- Blender 日志有 `Material.use_nodes` 弃用警告，不影响退出码，但应在后续 Blender 6.0 兼容工作中处理。

## 回滚点

本阶段没有专用 `rollback_point` 字段。可验证回滚基线是只读 P40 输入，SHA-256 为 `03635cf6608a54c4a671fb4d84adcb9451a36fe47cea7b564af2d4d3b69b2256`。R1 被拒绝时保留 `work/SURF_10_20260718_R1/` 作为失败证据，不向上游或正式资产推广任何 R1 产物。

## 下一停止线

R2 必须消除方块点和斜纹，提高近景微凹凸可读性，并让中、远景避免平涂和重复；批准清单不得包含 `.blend1`。只有 R2 再次通过机器检查、独立视觉审核和规范审核并由总控明确更新为 `approved`，才能启动 SURF-20。
