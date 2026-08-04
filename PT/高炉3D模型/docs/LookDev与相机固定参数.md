# GL02 高炉 LookDev 与相机固定参数

> 稳定编号：`VB-LOOK-001`  
> 需求编号：`REQ-BF3D-VISUAL-BIBLE-001`  
> 文档版本：v1.0  
> 对应 Visual Bible：v1.1  
> 日期：2026-07-18  
> 机器可读唯一参数源：[lookdev_camera_v1.json](../web/presets/lookdev_camera_v1.json)  
> Golden View 合同：[golden_views_v1.json](../validation/golden-images/golden_views_v1.json)

## 1. 结论和批准边界

本附件把已经存在于 P40 Blender 场景、P40 生成脚本和当前 Three.js
页面中的 LookDev、色彩管理、灯光和相机参数整理为受控参数。它的作用是让
Blender 制作、GLB 评审、Three.js 接线和视觉回归使用同一组数字，而不是靠
“看起来差不多”反复调光。

| 对象 | 当前状态 | 本附件如何处理 |
|---|---|---|
| P40 固定 LookDev 与七个相机 | `approved` | 固定为当前 Blender 基线 |
| P50 4K 材质 | `KEEP_P50_PENDING_NOT_APPROVED` | 只登记，不升级批准 |
| P60 GLB | `not_granted_preflight_only` | 只登记，不替换正式 GLB |
| 正式 GLB | 未替换；SHA-256 `808960f1…2af6` | 保持当前发布合同 |
| Three.js 色彩管理 | 已有 sRGB + ACES，曝光 1.05 | 记为当前审计值 |
| Three.js HDRI/PMREM | 未接线 | 记为不符合项，不能写“已完成” |
| `Industrial Sunset 2K` HDRI | 已登记 CC0 与 SHA | 受控候选，未获视觉批准 |
| Golden View PNG | P40 有批准范围内的证据图 | 尚未提升为自动 Golden 基准 |

“文档已固定参数”不等于“页面已经读取参数”。只有页面实际加载机器预设、
同机位对比通过并在[合规矩阵](../validation/Visual_Bible当前实现合规矩阵.md)
中更新状态后，Web 收敛条款才能变成 `compliant`。

## 2. 受控证据

| 证据 | 作用 | SHA-256 / 状态 |
|---|---|---|
| [P40_LOOKDEV_APPROVED.blend](../work/P40_FIXED_LOOKDEV_20260717_P36_FINAL/P40_LOOKDEV_APPROVED.blend) | Blender 批准场景 | `03635cf6608a54c4a671fb4d84adcb9451a36fe47cea7b564af2d4d3b69b2256` |
| [P40 参数报告](../work/P40_FIXED_LOOKDEV_20260717_P36_FINAL/p40_fixed_lookdev_candidate.json) | 相机、渲染矩阵和机器断言 | 18 张图完整 |
| [P40 人工评审](../work/P40_FIXED_LOOKDEV_20260717_P36_FINAL/p40_visual_review.json) | 批准边界 | `decision=approve` |
| [P40 生成脚本](../skills/bf3d-light-render/scripts/p40_fixed_lookdev_candidate.py) | 灯光和色彩参数来源 | `1f7dca16…59e8c` |
| [Three.js 页面](../../../高炉前端数据/frontend_dashboard_v3.server.html) | 当前 Web 运行值 | Three.js r160 |

## 3. 坐标和数值语义

- 长度统一为米；
- 相机位置和灯光位置是 Blender 资产空间；
- 相机旋转为 `XYZ Euler`，单位为弧度；
- Blender 相机前向轴为 `-Z`，相机上轴为 `+Y`；
- glTF 进入 Three.js 后必须先应用模型世界矩阵和坐标基变换；
- 禁止把 Blender Euler 角直接抄到 Three.js 相机后宣称同机位；
- 跨端机位用轮廓边缘、风口、炉顶、出铁口等投影地标验收。

机器预设中的数值允许误差：

| 项目 | 允许误差 |
|---|---:|
| 相机位置、旋转、正交尺度 | `1e-6` |
| 灯光位置、旋转、能量 | `1e-4` |
| 1920×1080 轮廓边缘 P95 | `≤3 px` |
| 关键地标投影 | `≤4 px` |
| 中灰 `ΔE2000` | `≤3` |
| 材质色块 `ΔE2000` | `≤5` |
| 相对亮度 | `≤8%` |

## 4. Blender 色彩管理

### 4.1 中性材质评审

| 参数 | 固定值 |
|---|---|
| View Transform | `AgX` |
| Look | `AgX - Medium Low Contrast` |
| Exposure | `0.0 EV` |
| Display / Sequencer | `sRGB / sRGB` |
| World Color（线性 RGBA） | `(0.12, 0.12, 0.12, 1.0)` |
| World Strength | `0.72` |
| HDRI | 无 |
| 用途 | 判断 BaseColor、Roughness、Normal、焊缝和积灰，不追求气氛 |

### 4.2 P40 工业展示

| 参数 | 固定值 |
|---|---|
| View Transform | `AgX` |
| Look | `AgX - Medium High Contrast` |
| Exposure | `0.38 EV` |
| Display / Sequencer | `sRGB / sRGB` |
| World Color（线性 RGBA） | `(0.010, 0.015, 0.021, 1.0)` |
| World Strength | `0.52` |
| HDRI | 无 |
| 用途 | 暖主光、冷轮廓光的工业展示 |

P40 的批准不能被错误解释为 `Industrial Sunset` HDRI 已批准。P40 的中性和展示图
都使用程序 World 加灯组，没有 HDRI。

## 5. 固定灯组

颜色为 Blender 灯光线性 RGB；Sun 的 `energy` 是强度，Area 的 `power` 为瓦，
位置和尺寸单位为米。完整精度以机器预设为准。

### 5.1 中性灯组 `P40_LOOKDEV_NEUTRAL`

| 名称 | 类型 | 位置 | 颜色 | 能量/功率 | 角度/尺寸 |
|---|---|---|---|---:|---:|
| `P40_NEUTRAL_KEY` | Sun | `(46.132336,-46.132336,49.166168)` | `(1,1,1)` | `2.25` | `8°` |
| `P40_NEUTRAL_FILL` | Sun | `(-46.132336,-11.533084,19.180149)` | `(0.96,0.98,1)` | `1.05` | `8°` |
| `P40_NEUTRAL_RIM` | Sun | `(11.533084,46.132336,49.166168)` | `(0.90,0.95,1)` | `1.35` | `8°` |
| `P40_NEUTRAL_TOP` | Area Disk | `(0,0,60.699253)` | `(1,1,1)` | `3921.248535 W` | `34.599251 m` |

### 5.2 展示灯组 `P40_PRESENTATION_INDUSTRIAL`

| 名称 | 类型 | 位置 | 颜色 | 能量/功率 | 角度/尺寸 |
|---|---|---|---|---:|---:|
| `P40_PRESENT_KEY_WARM` | Sun | `(46.132336,-46.132336,49.166168)` | `(1,0.80,0.64)` | `2.90` | `8°` |
| `P40_PRESENT_FILL` | Sun | `(-46.132336,-11.533084,19.180149)` | `(0.90,0.95,1)` | `1.22` | `8°` |
| `P40_PRESENT_RIM_COOL` | Sun | `(11.533084,46.132336,49.166168)` | `(0.48,0.70,1)` | `2.05` | `8°` |
| `P40_PRESENT_TOP_SOFT` | Area Disk | `(0,0,58.392635)` | `(1,0.95,0.88)` | `4244.174805 W` | `27.679401 m` |
| `P40_PRESENT_FRONT_FILL` | Area Disk | `(0,-46.132336,6.724420)` | `(0.88,0.94,1)` | `3136.998779 W` | `28.602049 m` |

不允许在材质评审过程中临时增加“补亮灯”。如材质在中性灯组下不可读，应先检查
法线尺度、粗糙度、色彩空间和曝光，而不是用新灯掩盖问题。

## 6. 固定相机

七个相机都为正交相机，`clip_start=0.05m`、`clip_end=1000m`。

| 相机 | 位置 | Euler 弧度 | Ortho Scale | 用途 |
|---|---|---|---:|---|
| `CAM_GLOBAL_FRONT` | `(42.369736,-102.289749,3.033833)` | `(1.570796,0,0.392699)` | `94.315002` | 全炉正面 |
| `CAM_GLOBAL_BACK` | `(-42.369736,102.289749,3.033833)` | `(1.570796,0,-2.748894)` | `94.315002` | 全炉背面 |
| `CAM_GLOBAL_LEFT` | `(-102.289749,-42.369736,3.033833)` | `(1.570796,0,-1.178098)` | `94.315002` | 全炉左侧 |
| `CAM_GLOBAL_RIGHT` | `(102.289749,42.369736,3.033833)` | `(1.570796,0,1.963495)` | `94.315002` | 全炉右侧 |
| `CAM_DETAIL_SHELL` | `(0,-35,8.5)` | `(1.561303,0,0)` | `6.2` | 炉壳板片、焊缝和微表面 |
| `CAM_DETAIL_TUYERE` | `(5.4,-32.200001,1.8)` | `(1.139001,0,0.185657)` | `2.0` | 风口法兰、螺栓和喷口 |
| `CAM_DETAIL_TAPHOLE` | `(0,-33.600449,-17.24)` | `(1.570796,0,0)` | `2.4` | 出铁口局部 |

三个局部相机的目标点：

| 相机 | Target |
|---|---|
| `CAM_DETAIL_SHELL` | `(0,-3.4,8.2)` |
| `CAM_DETAIL_TUYERE` | `(0,-3.449,-11.68)` |
| `CAM_DETAIL_TAPHOLE` | `(0,-3.60045,-17.24)` |

当前出铁口近景被 P40 评审明确记录为“几何仍偏抽象”的非阻断后续项。固定相机不等于
固定错误几何；后续改进出铁口几何时仍须保持机位，以便看到真实变化。

## 7. 渲染设置

| 用途 | 引擎 | 分辨率 | 关键参数 |
|---|---|---:|---|
| Blender 快速评审 | Eevee | `960×540` | PNG，100%，不透明背景 |
| Blender 路径追踪复核 | Cycles | `640×360` | 48 samples，Denoise，P40 使用 RTX 5070 OptiX |
| Web 首个跨端基准 | Chromium | `1920×1080` CSS viewport | DPR=1，缩放=100%，质量=high，禁用实时流 |

固定材质评审必须：

1. 冻结时间；
2. 禁用动画、呼吸环、粒子和实时 WebSocket；
3. 使用静态数据快照 `STATIC_VISUAL_REVIEW_NO_LIVE_DATA_V1`；
4. 记录 GLB、Blend、HDRI、预设和 PNG 的 SHA-256；
5. 不把 UI 时钟或流式数据差异纳入材质像素比较。

## 8. Three.js 当前值与收敛目标

当前页面审计值：

| 参数 | 当前实现 |
|---|---|
| Three.js | r160 |
| `renderer.outputColorSpace` | `THREE.SRGBColorSpace` |
| `renderer.toneMapping` | `THREE.ACESFilmicToneMapping` |
| `renderer.toneMappingExposure` | `1.05` |
| `scene.environment` | 未设置 |
| PMREM | 未实现 |
| HDRI | 未接线 |
| 本附件运行时加载 | 未实现 |

因此，当前 Web 只能记为 `partial`：有正确的输出色彩空间和 ACES Tone Mapping，但
缺少粗糙金属最关键的预过滤环境反射，也没有证明它读取了本受控预设。

Web 收敛顺序固定为：

1. 页面读取 [机器预设](../web/presets/lookdev_camera_v1.json)，不再复制常量；
2. 建立 Blender → glTF → Three.js 相机坐标转换；
3. 先完成无 HDRI 的 P40 同机位轮廓/色彩对比；
4. 再加载 HDRI，使用 `PMREMGenerator` 生成一次环境纹理并复用；
5. 销毁查看器时释放 HDR、PMREM、RenderTarget 和源纹理；
6. 复核传感器自发光、L7～L16 高亮和剖面对象没有被环境光淹没；
7. 通过数值阈值和人工视觉评审后，才更新合规矩阵。

## 9. HDRI 候选

| 字段 | 值 |
|---|---|
| Asset ID | `HDRI_INDUSTRIAL_SUNSET_2K_V1` |
| 本地文件 | [industrial_sunset_2k.hdr](../source/references/hdri/industrial_sunset_2k.hdr) |
| 来源 | [Poly Haven — Industrial Sunset](https://polyhaven.com/a/industrial_sunset) |
| 作者 | Sergej Majboroda |
| 许可 | CC0 |
| 大小 | 6,523,872 bytes |
| SHA-256 | `2a411097d65fcebfe00275641bd80350f95c7a1dbfc53b2260df85b296d2b990` |
| 当前状态 | `candidate_asset_registered_not_visual_approved` |
| Blender 初始强度候选 | `0.35`，不是批准值 |
| Web 要求 | 必须 PMREM；当前未接线 |

许可与边界同时记录于[第三方声明](../THIRD_PARTY_NOTICES.md#视觉参考与-hdri-资产)。
该 HDRI 是展示环境候选，不是 GL02 现场照明证据，也不能改变设备颜色校准结论。

## 10. Golden View

[Golden View 参数](../validation/golden-images/golden_views_v1.json)固定：

- 7 个 P40 相机；
- 中性与展示两套 LookDev；
- 视口、DPR、缩放、时间和动画状态；
- 静态数据快照；
- 程序材质、Shader、粒子、动画和相机抖动随机种子；
- P40 证据图路径及 SHA-256；
- Web 跨端视图和 HDRI 视图的阻断状态；
- 数值比较阈值与人工签字门槛。

P40 的 14 张 Eevee 图已经有 `approved_for_p40_lookdev_scope` 证据，但
`golden_baseline_state=not_promoted`。其原因是当前还没有完成：

1. 以本预设重新捕获；
2. 冻结并登记所有随机种子；
3. Web 同机位捕获；
4. 差异算法报告；
5. Golden reviewer、签字时间和接受偏差。

这比把已有截图直接改名为 Golden 更严格，也能避免未来用错误基线保护错误结果。

## 11. 固定随机种子

新捕获的 Golden View 使用：

| 系统 | Seed |
|---|---:|
| Procedural Material | `407181` |
| Shader Noise | `407182` |
| Particles | `407183` |
| Animation | `407184` |
| Camera Jitter | `0` |

现有 P40 PNG 早于本种子登记，不能追溯性声称使用了这些 Seed。重新捕获 Golden
时应把 Seed 写入 Blender 自定义属性、Web 快照和测试报告三处。

## 12. 批准与变更规则

下列任一变化都必须生成新预设版本并重跑 Golden View：

- 相机位置、旋转、正交尺度、FOV 或裁剪面；
- 灯光位置、颜色、大小、功率、World 或曝光；
- AgX/ACES、输出色彩空间或色调映射；
- HDRI 文件、旋转、强度或 PMREM 参数；
- 正式 GLB、PBR 通道或材质混合；
- 随机种子、数据快照或可见对象规则；
- 浏览器、Three.js 主版本或渲染管线。

变更记录必须同时更新：

1. 本文档；
2. `lookdev_camera_v1.json`；
3. `golden_views_v1.json`；
4. [当前实现合规矩阵](../validation/Visual_Bible当前实现合规矩阵.md)；
5. 对应测试报告和批准记录。

## 13. 当前执行判定

- P40 Blender 灯光、色彩和七相机：可作为受控已批准基线；
- P40 图片：是批准范围内证据，但尚不是自动 Golden；
- P50/P60：仍未批准；
- Three.js：色彩链部分符合，Preset/相机转换/HDRI/PMREM 未接；
- `Industrial Sunset 2K`：许可和哈希闭环完成，视觉批准未完成；
- 发布结论必须以合规矩阵为准，不能只看本参数表。
