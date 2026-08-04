# INT-20 R1 阶段成果总结

> 需求：`REQ-BF3D-10STAGE-EXECUTION-20260718`  
> 证据包：`work/INT_20_20260718_R1/`  
> 当前状态：`candidate_ready_for_review`  
> 批准状态：`not_granted_requires_visual_and_spec_review`  
> 证据口径：仅使用本阶段证据包和[十阶段多智能体执行台账](../十阶段多智能体执行台账.md)。本总结不虚构独立审核通过，也不把 R2 已启动倒推为 R1 的正式 `iterate` 结论。

## 阶段目标

在已批准的 INT-10 四层灰模上，只增加钢壳、冷却壁、耐火层和工艺空间的示意材质及剖切可读性辅助对象，输出正视、侧视、半剖、四分之一剖、截面近景和材质色卡；所有材料、厚度、砖缝、冷却壁接缝和结厚提示继续保持 `E/illustrative`。

## 输入及 SHA

| 输入 | SHA-256 | 证据 |
|---|---|---|
| [INT_10_INTERNAL_GRAYBOX_CANDIDATE.blend](../work/INT_10_20260718_R1/INT_10_INTERNAL_GRAYBOX_CANDIDATE.blend) | `ee8387959d26612d2f03d2ff05651419fbdcb087cb546f4a8293d957233553fe` | [命令记录](../work/INT_20_20260718_R1/command.json)、[机器报告](../work/INT_20_20260718_R1/int20_machine_report.json) |

机器报告记录 `sha256_match=true`、`read_only_source=true`。

## 实际执行者与审核者

| 职责 | 身份 | 已知结论 |
|---|---|---|
| R1 执行 | `/root/int20_material_cutaway` | 生成候选、六张证据图和机器报告 |
| R1 视觉审核者 | `unknown` | 允许证据没有独立审核者身份或正式 verdict |
| R1 规范审核者 | `unknown` | 允许证据没有独立审核者身份或正式 verdict |
| R2 当前执行 | `/root/int20_r2_solid_cutaway`，`blender_stage_executor` | 后续修订归属，不代表 R1 已批准 |
| 总控 | `/root` | 台账保持 INT-20 为 `running_candidate`，R1 作为失败证据保留 |

角色边界来自[执行台账](../十阶段多智能体执行台账.md)。

## 实际命令与退出码

主命令：

```text
"D:\Program Files\Blender Foundation\Blender 5.2\blender.exe" --background "D:\文件\冀南钢铁运行中第二版本\PT\高炉3D模型\work\INT_10_20260718_R1\INT_10_INTERNAL_GRAYBOX_CANDIDATE.blend" --python "D:\文件\冀南钢铁运行中第二版本\PT\高炉3D模型\work\INT_20_20260718_R1\_int20_blender_stage.py"
```

退出码：`0`。

重新打开验证命令：

```text
"D:\Program Files\Blender Foundation\Blender 5.2\blender.exe" --background "D:\文件\冀南钢铁运行中第二版本\PT\高炉3D模型\work\INT_20_20260718_R1\INT_20_INTERNAL_MATERIAL_CUTAWAY_CANDIDATE.blend" --python "D:\文件\冀南钢铁运行中第二版本\PT\高炉3D模型\work\INT_20_20260718_R1\_int20_reopen_validate.py"
```

退出码：`0`。详见[命令记录](../work/INT_20_20260718_R1/command.json)、[主标准输出](../work/INT_20_20260718_R1/blender_stdout.log)、[主标准错误](../work/INT_20_20260718_R1/blender_stderr.log)、[重开标准输出](../work/INT_20_20260718_R1/reopen_stdout.log)和[重开标准错误](../work/INT_20_20260718_R1/reopen_stderr.log)。

## 主要产物

| 产物 | SHA-256 / 说明 |
|---|---|
| [INT_20_INTERNAL_MATERIAL_CUTAWAY_CANDIDATE.blend](../work/INT_20_20260718_R1/INT_20_INTERNAL_MATERIAL_CUTAWAY_CANDIDATE.blend) | `b4a9da38b0b8c58b41ec818ca912dc880a89c9638583e72330ebbde35706f9da` |
| [int20_machine_report.json](../work/INT_20_20260718_R1/int20_machine_report.json) | `f8c297a61d2ab47b23d109967ba1918f0c95b78c60c37ed9bdd6f66fade20493` |
| [int20_material_manifest.json](../work/INT_20_20260718_R1/int20_material_manifest.json) | `5d7b7e2ada2db45fcdb3b04b197ea835220cc237c0531a17d8eba74cfe576905` |
| [reopen_validation.json](../work/INT_20_20260718_R1/reopen_validation.json) | `58ae92b878949fc68684a25e0b5cba4ee080c74a94200996c3c4daf9d1028f74` |
| [INT20_FRONT.png](../work/INT_20_20260718_R1/renders/INT20_FRONT.png) | `ce7aa891eaf2ad940cf8cbdb7e341973c47c8adaaeee7d01b683cd0d86c28f4e` |
| [INT20_SIDE.png](../work/INT_20_20260718_R1/renders/INT20_SIDE.png) | `63c3b8d65fdda253ffe5d20ec5ce27bc7232cadc814df66b5554e47d8d3caa22` |
| [INT20_HALF_CUT.png](../work/INT_20_20260718_R1/renders/INT20_HALF_CUT.png) | `e1407204fb6960c8a60ea9ad5c3fa14b589fcce2885086fe0984b865ac20d5e7` |
| [INT20_QUARTER_CUT.png](../work/INT_20_20260718_R1/renders/INT20_QUARTER_CUT.png) | `07b04a714d54fdb1125f01b5edbab468a4e473349238c833074029b7c36a938a` |
| [INT20_CUTAWAY_CLOSEUP.png](../work/INT_20_20260718_R1/renders/INT20_CUTAWAY_CLOSEUP.png) | `f22cfb3971e01f7173f6e6c3e82f19c61ee1e11725e39f2d96f18eed2fd37196` |
| [INT20_MATERIAL_DIAGNOSTIC_COLORCARD.png](../work/INT_20_20260718_R1/renders/INT20_MATERIAL_DIAGNOSTIC_COLORCARD.png) | `9797021028b2ee7d21d4728062716ab22ab02b7b3ca89582a31b0b3438608eb2` |
| [artifact_sha256.json](../work/INT_20_20260718_R1/artifact_sha256.json) | 候选、脚本、日志、报告、重开验证和六张图的哈希清单 |

## 机器断言

- 机器报告列出的 9 个命名断言标志全部为 `true`；报告没有单独的 `total/passed/failed` 汇总，不额外虚构分母。
- 输入 SHA 匹配，候选保存成功；主执行和重新打开验证退出码均为 0。
- 115 个传感器、80 个炉身测温点、L7～L16 十层和五个炉体段数量保持不变。
- 传感器签名前后均为 `406b658749ef74acad8c4b022d2a86272ad82e74bfd0ad63b57eaa44f1df0304`，名称、父级和矩阵不变。
- INT-10 的 12 个对象名称、矩阵和几何保持不变，并完成 12 项材质赋值。
- 29 个 INT-20 辅助/诊断对象全部标为 `E/illustrative`。
- 六张证据图均存在；候选重新打开状态为 `pass`。

## 视觉审核结论

当前没有独立视觉审核文件或审核者 verdict，**不能写成 `approve`**。对允许证据的只读复核显示：

- [半剖图](../work/INT_20_20260718_R1/renders/INT20_HALF_CUT.png)整体过暗，内层大面积压黑；
- [四分之一剖图](../work/INT_20_20260718_R1/renders/INT20_QUARTER_CUT.png)层间对比不足；
- [截面近景](../work/INT_20_20260718_R1/renders/INT20_CUTAWAY_CLOSEUP.png)不能可靠读出钢壳、冷却壁和炉衬厚度关系。

因此 R1 目前只能保持 `candidate_ready_for_review`，视觉上尚不具备批准条件。

## 规范审核结论

独立规范审核结论为 `unknown`，不得虚构通过。机器证据能证明 `E/illustrative` 标记、保护对象和文件存在性，但没有独立规范审核文件确认剖切可见层的闭合实体厚度、独立内外表面和切面封口均满足最终停止线。R2 的停止线仍要求重新证明这些项目。

## 保护合同

- INT-10 输入保持只读；12 个 INT-10 对象的名称、矩阵和几何保持不变。
- 115 个传感器、80 个炉身测温点、L7～L16、五个炉体段保持不变。
- 既有 55 个解释对象继续隐藏，未删除。
- 钢壳、冷却壁、耐火层、工艺空间、砖缝、冷却壁接缝和结厚提示均为 `E/illustrative`。
- 不声称工程确认厚度、现场实际材料或真实磨损状态。
- 正式 GLB、P40、P50、P60 和前端均未修改。

## 批准/迭代边界

- **当前只允许写**：`candidate_ready_for_review`、机器断言通过、重开验证通过。
- **不得写**：视觉 `approve`、规范 `approve`、总控 `approved`、工程厚度确认、现场材料确认或正式资产可替换。
- 允许证据尚无 R1 正式审核 verdict，因此本总结也不把 R1 擅自定为正式 `iterate`；台账中 R2 已启动只说明后续修订正在进行。
- R1 必须保留为失败/待审证据，不得被 R2 覆盖。

## 已知问题

- 半剖、四分之一剖和近景过暗，层厚关系不可读。
- 材质是示意 LookDev，不是现场实测冶金材质或炉衬状态。
- 砖缝、冷却壁接缝和结厚提示只是可读性辅助，不代表真实设备布局、厚度或磨损。
- 独立视觉审核者、规范审核者、审核命令和正式 verdict 均为 `unknown`。
- 机器报告没有断言总数汇总，也没有逐对象的 INT-20 切面封口审核结果。
- `INT_20_INTERNAL_MATERIAL_CUTAWAY_CANDIDATE.blend1` 存在于哈希清单；是否允许进入后续批准包为 `unknown`，应按 SURF-10 R1 的包装经验显式排除。
- 主日志有 `Material.use_nodes` 弃用警告，不影响本次退出码。

## 回滚点

本阶段没有专用 `rollback_point` 字段。可验证回滚基线为 [INT_10_INTERNAL_GRAYBOX_CANDIDATE.blend](../work/INT_10_20260718_R1/INT_10_INTERNAL_GRAYBOX_CANDIDATE.blend)，SHA-256 为 `ee8387959d26612d2f03d2ff05651419fbdcb087cb546f4a8293d957233553fe`。回退时保留 R1 证据目录，不把 R1 候选推广到任何正式资产。

## 下一停止线

R2 必须以可读照明和明确剖切证据证明钢壳、冷却壁、耐火层是闭合实体厚度并有可靠封口；半剖、四分之一剖、爆炸剖和截面近景必须清楚区分各层。随后必须完成独立视觉审核、独立规范审核和总控汇总；在三项结论齐全前不得进入 `approved`。
