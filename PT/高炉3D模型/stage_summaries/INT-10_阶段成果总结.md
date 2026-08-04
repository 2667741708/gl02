# INT-10 阶段成果总结

> 需求：`REQ-BF3D-10STAGE-EXECUTION-20260718`  
> 证据包：`work/INT_10_20260718_R1/`  
> 执行包状态：`candidate_ready_for_visual_review`  
> 总控门禁结论：`approved`，仅批准 `E/illustrative` 四层灰模  
> 证据口径：仅使用本阶段证据包和[十阶段多智能体执行台账](../十阶段多智能体执行台账.md)。

## 阶段目标

在不改写原五段炉壳的前提下，新建钢壳、冷却壁、耐火层和工艺空间四层独立灰模，生成全体、半剖和四分之一剖的闭合体积证据；隐藏而不删除既有内部解释对象，不接实时数据，不进入 C1/C2/C3。

## 输入及 SHA

| 输入 | SHA-256 | 证据 |
|---|---|---|
| `work/P40_FIXED_LOOKDEV_20260717_P36_FINAL/P40_LOOKDEV_APPROVED.blend` | `03635cf6608a54c4a671fb4d84adcb9451a36fe47cea7b564af2d4d3b69b2256` | [命令记录](../work/INT_10_20260718_R1/command.json)、[阶段报告](../work/INT_10_20260718_R1/int10_internal_graybox_report.json) |

输入在报告中标为 `read_only_source=true`，批准状态为 `approved`。

## 实际执行者与审核者

| 职责 | 身份 | 已知结论 |
|---|---|---|
| 执行 | `/root/build_lookdev_camera_presets`，复用执行智能体 | 生成 INT-10 R1 候选 |
| 视觉审核 | `/root/review_int10_visual` | `approve` |
| 规范审核 | `/root/spec_review_base_int_r2` | `approve` |
| 总控 | `/root` | `approved` |

身份和独立审核结论来自[执行台账](../十阶段多智能体执行台账.md)。允许证据内未保存两位审核者各自的单独审核文件。

## 实际命令与退出码

主命令：

```text
"D:\Program Files\Blender Foundation\Blender 5.2\blender.exe" --background "D:\文件\冀南钢铁运行中第二版本\PT\高炉3D模型\work\P40_FIXED_LOOKDEV_20260717_P36_FINAL\P40_LOOKDEV_APPROVED.blend" --python "D:\文件\冀南钢铁运行中第二版本\PT\高炉3D模型\run_int10_internal_graybox.py" -- --inside-blender --input-blend "D:\文件\冀南钢铁运行中第二版本\PT\高炉3D模型\work\P40_FIXED_LOOKDEV_20260717_P36_FINAL\P40_LOOKDEV_APPROVED.blend" --output-dir "D:\文件\冀南钢铁运行中第二版本\PT\高炉3D模型\work\INT_10_20260718_R1" --width 1280 --height 720
```

退出码：`0`，记录在[阶段报告](../work/INT_10_20260718_R1/int10_internal_graybox_report.json)。

重新打开验证命令：

```text
"D:\Program Files\Blender Foundation\Blender 5.2\blender.exe" --background "PT\高炉3D模型\work\INT_10_20260718_R1\INT_10_INTERNAL_GRAYBOX_CANDIDATE.blend" --python-expr "import bpy; print('INT10_REOPEN', bpy.context.scene.get('bf3d_stage'), len([o for o in bpy.data.objects if o.name.startswith('APPROX_GL02_INT10_')]), len([o for o in bpy.data.objects if o.name.startswith('SENSOR_')]))"
```

进程退出码：`unknown`，验证文件没有单列；验证状态为 `pass`，观测输出为 `INT10_REOPEN INT_10_INTERNAL_GRAYBOX_CANDIDATE 12 115`。详见[重新打开验证](../work/INT_10_20260718_R1/reopen_validation.json)、[标准输出](../work/INT_10_20260718_R1/blender_stdout.log)和[标准错误](../work/INT_10_20260718_R1/blender_stderr.log)。

## 主要产物

| 产物 | SHA-256 / 说明 |
|---|---|
| [INT_10_INTERNAL_GRAYBOX_CANDIDATE.blend](../work/INT_10_20260718_R1/INT_10_INTERNAL_GRAYBOX_CANDIDATE.blend) | `ee8387959d26612d2f03d2ff05651419fbdcb087cb546f4a8293d957233553fe` |
| [int10_internal_graybox_report.json](../work/INT_10_20260718_R1/int10_internal_graybox_report.json) | `2bd9ef05d60a7f1827949c3398b1f27ef88b7db402c021ba3a4cd0b963188b12` |
| [int10_structure_manifest.json](../work/INT_10_20260718_R1/int10_structure_manifest.json) | `43bdcca1678b450cbe7f93c401dee90c6123e409cc3674ec16f33a1964e6b0e0` |
| [artifact_sha256.json](../work/INT_10_20260718_R1/artifact_sha256.json) | 候选、报告、日志、验证和四张图的哈希清单 |
| [INT10_FRONT.png](../work/INT_10_20260718_R1/renders/INT10_FRONT.png) | `a22f5656005150a65b166e1ca7c084ec24c8be0ef33bbbb5277fbc551e42b550` |
| [INT10_SIDE.png](../work/INT_10_20260718_R1/renders/INT10_SIDE.png) | `18f5391760aa0be6638e8e927c08e63fd95160cbb512dd4f39e80d733e23cdae` |
| [INT10_HALF_CUT.png](../work/INT_10_20260718_R1/renders/INT10_HALF_CUT.png) | `8b630e5fd2489c37898b3ab86261bc4f892c9096bad00d4ee4159d11bb016772` |
| [INT10_QUARTER_CUT.png](../work/INT_10_20260718_R1/renders/INT10_QUARTER_CUT.png) | `280c3a2cd9f3ed27a46f52ff54651ba3be455533102cdd0e9e2ae110079538d6` |

## 机器断言

- 新建 `INT10_INTERNAL_GRAYBOX` 集合及四个层集合，共 12 个新 Mesh、4 个新材质。
- 12 个灰模 Mesh 均为闭合体，所有对象 `non_manifold_edges=0`。
- 四层均具有正厚度；最小解析径向净距 `0.03 m`，合同检查无明显径向相交。
- 115 个传感器、五个炉体段、L7～L16 十个组和十个层带保持完整。
- 保护签名前后均为 `3329d29fecc774e7a817009caa520592554622ee80fac0ac0c3b02ba324942a7`，名称、父级和矩阵不变。
- 重新打开候选通过，场景阶段、12 个 INT-10 对象和 115 个传感器均可恢复。

## 视觉审核结论

`/root/review_int10_visual = approve`。四层灰模在半剖和四分之一剖证据中可区分，正视和侧视保留整体包络。该批准只针对灰模结构可读性。

## 规范审核结论

`/root/spec_review_base_int_r2 = approve`。批准条件是四层对象独立、闭合、非流形边为 0，且厚度和材料全部保持 `E/illustrative`；不构成工程确认尺寸或现场实测材料批准。

## 保护合同

- 原 P40 输入只读，原五段炉壳不改写。
- 115 个 `SENSOR_` 节点、80 个炉身测温点、L7～L16、五段炉体保持不变。
- 既有 55 个内部解释对象仅在证据图中隐藏，不删除。
- 正式 GLB、P40、P50、P60、前端均未修改。
- 钢壳、冷却壁、耐火层和工艺空间统一为 `E/illustrative`。

## 批准/迭代边界

- **已批准**：12 个闭合四层灰模、全体/半剖/四分之一剖结构、E/illustrative 参数边界。
- **未批准**：工程确认厚度、真实冷却壁分段与材料、炉衬磨损/结厚状态、任何 C1/C2/C3 数据或仿真、正式 GLB 替换。
- 该门禁允许进入 INT-20，但不能把 INT-20 自动视为通过。

## 已知问题

- 钢壳、冷却壁和耐火层厚度缺少 GL02 工程图或批准测绘。
- 冷却壁材料和分段布局缺少设备记录。
- 炉衬残厚、结厚/结瘤状态缺少模型或测量依据。
- 两位独立审核者的单独审核文件在允许证据内为 `unknown`；结论由台账记录。
- Blender 日志有 `World.use_nodes` 和 `Material.use_nodes` 的 Blender 6.0 弃用警告，不影响本次退出码。

## 回滚点

本阶段证据未提供专用 `rollback_point` 字段。可验证回滚基线是只读 P40 输入，SHA-256 为 `03635cf6608a54c4a671fb4d84adcb9451a36fe47cea7b564af2d4d3b69b2256`；若回退 INT-10，只丢弃隔离目录 `work/INT_10_20260718_R1/`，不得修改该输入或正式资产。

## 下一停止线

进入 INT-20 后，钢壳、冷却壁和炉衬必须继续保持闭合实体体积、独立内外表面与可靠切面封口；半剖、四分之一剖、爆炸剖和截面近景必须清楚区分各层。工程图到位前所有厚度仍必须标为 `E/illustrative`。
