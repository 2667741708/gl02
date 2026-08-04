# BASE-00 阶段成果总结

> 需求：`REQ-BF3D-10STAGE-EXECUTION-20260718`  
> 证据包：`work/BASE_00_20260718_R1/`  
> 执行包状态：`candidate_ready_for_review`  
> 总控门禁结论：`approved`，但只批准 P40 基线锁定  
> 证据口径：仅使用本阶段证据包和[十阶段多智能体执行台账](../十阶段多智能体执行台账.md)。

## 阶段目标

把既有 P40 已批准 Blend 复制为字节一致的隔离只读检查点，重新锁定输入资产 SHA、固定相机、115 个传感器节点、L7～L16 十层和五个炉体工艺段，并证明 BASE-00 没有修改正式 GLB、P40 源文件、P50/P60 资产、前端或数据库。

## 输入及 SHA

| 输入 | SHA-256 | 证据 |
|---|---|---|
| `work/P40_FIXED_LOOKDEV_20260717_P36_FINAL/P40_LOOKDEV_APPROVED.blend` | `03635cf6608a54c4a671fb4d84adcb9451a36fe47cea7b564af2d4d3b69b2256` | [锁定资产清单](../work/BASE_00_20260718_R1/base00_locked_assets_manifest.json) |
| 隔离副本 `BASE00_SOURCE_LOCKED.blend` | `03635cf6608a54c4a671fb4d84adcb9451a36fe47cea7b564af2d4d3b69b2256` | [输出 SHA 清单](../work/BASE_00_20260718_R1/base00_output_sha256.json) |
| 正式 GLB（只校验、未修改） | `808960f1b2703e7fb27df35f1b1b1a17063b9b10d2267acba593fc3872b62af6` | [机器报告](../work/BASE_00_20260718_R1/base00_machine_report.json) |

输入与隔离副本字节数均为 `3,672,744`，清单记录 `byte_identical=true`、`content_modified=false`。

## 实际执行者与审核者

| 职责 | 身份 | 已知结论 |
|---|---|---|
| 执行 | `/root/base00_lock`，worker | 生成只读锁定与机器审计候选；不自批 |
| 视觉审核 | `/root/review_base00_visual` | `approve` |
| 规范审核 | `/root/spec_review_base_int_r2` | `approve` |
| 总控 | `/root` | 将 BASE-00 门禁更新为 `approved` |

角色和最终结论来自[执行台账](../十阶段多智能体执行台账.md)。允许证据内没有 BASE-00 两位独立审核者各自的单独审核文件；`reports/p40_visual_review.json` 是既有 P40 视觉审核镜像，不等同于 BASE-00 审核者的独立原始记录。

## 实际命令与退出码

外层入口在机器报告中记录为：

```text
D:\ProgramData\anaconda3\python.exe D:\文件\冀南钢铁运行中第二版本\PT\高炉3D模型\run_base00_execution.py
```

外层入口退出码：`unknown`，证据没有单独记录。

Blender 只读审计命令：

```text
"D:\Program Files\Blender Foundation\Blender 5.2\blender.exe" --background D:\文件\冀南钢铁运行中第二版本\PT\高炉3D模型\work\BASE_00_20260718_R1\BASE00_SOURCE_LOCKED.blend --python D:\文件\冀南钢铁运行中第二版本\PT\高炉3D模型\run_base00_execution.py -- --blender-audit-child --output-dir D:\文件\冀南钢铁运行中第二版本\PT\高炉3D模型\work\BASE_00_20260718_R1 --preset D:\文件\冀南钢铁运行中第二版本\PT\高炉3D模型\web\presets\lookdev_camera_v1.json
```

退出码：`0`。详见[命令记录](../work/BASE_00_20260718_R1/base00_execution_command.json)、[执行日志](../work/BASE_00_20260718_R1/base00_execution.log)、[标准输出](../work/BASE_00_20260718_R1/blender_stdout.log)和[标准错误](../work/BASE_00_20260718_R1/blender_stderr.log)。

## 主要产物

| 产物 | SHA-256 / 说明 |
|---|---|
| [BASE00_SOURCE_LOCKED.blend](../work/BASE_00_20260718_R1/BASE00_SOURCE_LOCKED.blend) | `03635cf6608a54c4a671fb4d84adcb9451a36fe47cea7b564af2d4d3b69b2256` |
| [base00_machine_report.json](../work/BASE_00_20260718_R1/base00_machine_report.json) | `87d5112b887b63b277688d46c7b0b1a1257a71b37670f0f28948249bb1e530cc` |
| [base00_blender_scene_audit.json](../work/BASE_00_20260718_R1/base00_blender_scene_audit.json) | `20bfe3889bb49a977bbe100df3208f634aef2e4acbef3baf6d6073f83dc0f75d` |
| [base00_locked_assets_manifest.json](../work/BASE_00_20260718_R1/base00_locked_assets_manifest.json) | `1e24103683b1c313266f5aa7adcf0164d05a44ca6cfd13c1ded37b98f14afef0` |
| [base00_fixed_camera_index.json](../work/BASE_00_20260718_R1/base00_fixed_camera_index.json) | `db21dafb8d5874b64a6785b44a737df02e7b135255f3f547c199dc92f3eb4045` |
| [base00_output_sha256.json](../work/BASE_00_20260718_R1/base00_output_sha256.json) | 九项核心输出的哈希清单 |
| [BASE00_REVIEW_HANDOFF.md](../work/BASE_00_20260718_R1/reports/BASE00_REVIEW_HANDOFF.md) | 复审边界及 14 张固定视角哈希 |
| [中性正视图](../work/BASE_00_20260718_R1/renders/P40_NEUTRAL_CAM_GLOBAL_FRONT.png) / [展示正视图](../work/BASE_00_20260718_R1/renders/P40_PRESENTATION_CAM_GLOBAL_FRONT.png) | 14 张镜像证据中的代表项 |
| [中性风口细节](../work/BASE_00_20260718_R1/renders/P40_NEUTRAL_CAM_DETAIL_TUYERE.png) / [展示炉壳细节](../work/BASE_00_20260718_R1/renders/P40_PRESENTATION_CAM_DETAIL_SHELL.png) | 14 张镜像证据中的代表项 |

## 机器断言

- `82/82 pass`，失败项为 0；输入锁 `29/29 pass`。
- Blender `5.2.0 LTS`；只读审计未重新渲染。
- 场景对象 256、Mesh 对象 191、Mesh 数据块 42、材质 34、固定相机 7。
- `SENSOR_` 节点 115，炉身测温点 80。
- L7～L16 共 10 层，每层 8 点；五个 `APPROX_GL02_FURNACE_*` 工艺段均存在。
- 正式 GLB 与 P40 对比无传感器缺失、意外节点、父级不匹配或工艺段位置不匹配；最大传感器位置误差约 `9.16e-7 m`。
- 14 张既有 P40 固定视角已哈希核对并镜像，但没有提升为自动化 Golden 图。

机器证据见[机器报告](../work/BASE_00_20260718_R1/base00_machine_report.json)和[Blender 场景审计](../work/BASE_00_20260718_R1/base00_blender_scene_audit.json)。

## 视觉审核结论

`/root/review_base00_visual = approve`。批准对象是“P40 已批准外观证据被完整锁定并可作为 BASE-00 参照”，不是新材质、新几何或新 Golden 图批准。既有 [P40 视觉审核镜像](../work/BASE_00_20260718_R1/reports/p40_visual_review.json)记录哑光风化钢、焊缝/板缝和风口细节可读，Eevee 与 Cycles 方向一致。

## 规范审核结论

`/root/spec_review_base_int_r2 = approve`。总控只批准 BASE-00 基线锁定；执行器报告仍正确保留 `candidate_ready_for_review` 和 `self_approved=false`，没有越权自批。

## 保护合同

- P40 已批准源文件保持只读，隔离副本与源文件字节一致。
- 正式 GLB 未替换，SHA 保持 `808960...2af6`。
- P50、P60、前端、Web、数据库均未修改。
- 115 个传感器、L7～L16 十层、五个炉体段的名称、父级和空间合同保持不变。
- BASE-00 不进行新渲染，不把既有 PNG 提升为自动化 Golden。

## 批准/迭代边界

- **已批准**：P40 基线的只读锁定、29 项输入锁、82 项机器审计、7 个相机参数和 14 张既有固定视角的证据索引。
- **未批准**：P50（`KEEP_P50_PENDING_NOT_APPROVED`）、P60（`not_granted_preflight_only`）、P70、正式 GLB 替换、Golden 图、Web 跨引擎图和候选 HDRI。
- BASE-00 批准不得外推为任何后续阶段已通过。

## 已知问题

- 炉口正面细节仍较抽象；属于后续独立几何阶段的非阻断跟进项。
- 炉体纵横比极端，全球视图存在较多横向留白。
- Web 固定视图尚未捕获；预设加载、相机基变换、HDRI/PMREM 和跨引擎收敛仍未完成。
- Golden 参数已锁，但 Golden 图片未批准。
- BASE-00 独立视觉/规范审核的单独原始文件在允许证据内为 `unknown`；最终结论目前只由台账记录。

## 回滚点

明确回滚点为 [BASE00_SOURCE_LOCKED.blend](../work/BASE_00_20260718_R1/BASE00_SOURCE_LOCKED.blend)，SHA-256 为 `03635cf6608a54c4a671fb4d84adcb9451a36fe47cea7b564af2d4d3b69b2256`。若拒绝该候选，只删除 `work/BASE_00_20260718_R1/`；上游和正式资产均保持不变。

## 下一停止线

BASE-00 已满足自身停止线。任何下游阶段若破坏 115 个传感器、L7～L16、五个炉体段、P40 锁定 SHA 或正式 GLB 只读合同，必须立即停止全部下游工作并回到本回滚点。
