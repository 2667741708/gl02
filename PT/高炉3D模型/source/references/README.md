# 高炉三维项目参考资料登记册

版本：2026-07-18  
状态：受控参考索引（不含 GL02 现场实物批准资料）

## 1. 使用边界

本目录用于登记外部视觉参考与后续 GL02 现场采集资料。当前没有把外部图片复制到仓库，也没有在项目页面热链外部原图。

外部公开图片只允许用于：

- 理解高炉设备的大类形态、构造关系和工业环境；
- 形成材质、污渍、热态表现和拍摄机位的方向性假设；
- 制作内部评审用的参考清单。

外部公开图片不得用于：

- 证明 GL02 的真实尺寸、颜色、锈蚀位置、设备数量或安装关系；
- 直接覆盖为 GL02 的贴图；
- 反推 GL02 的工程参数；
- 在未满足署名、许可证和衍生作品要求时进入对外交付物。

所有尚未取得 GL02 现场证据的项目统一标记为 `REF-PENDING`。

## 2. 外部公开参考

| Reference ID | 主题 | 页面与作者 | 许可证 | 允许用途 | 限制与状态 |
|---|---|---|---|---|---|
| EXT-BF-001 | 风口平台、送风支管及高炉下部工业环境 | [Le plancher des tuyères](https://commons.wikimedia.org/wiki/File:Le_plancher_des_tuy%C3%A8res.jpg)，作者 Stephane Gaudry，2012-06-10 | CC BY 2.0 | 风口平台空间密度、管道/法兰关系、暗部与工业照明方向参考 | 非 GL02；不用于尺寸和材质数值标定；引用或改编须署名并链接许可证 |
| EXT-BF-002 | 出铁口、铁水和炉渣出铁场景 | [Iron and slag tapping from a blast furnace tap hole](https://commons.wikimedia.org/wiki/File:Iron_and_slag_tapping_from_a_blast_furnace_tap_hole_%E2%80%94_%D0%92%D0%B8%D0%BF%D1%83%D1%81%D0%BA_%D0%BF%D1%80%D0%BE%D0%B4%D1%83%D0%BA%D1%82%D1%96%D0%B2_%D0%BF%D0%BB%D0%B0%D0%B2%D0%BA%D0%B8_%D0%B7_%D0%BB%D1%8C%D0%BE%D1%82%D0%BA%D0%B8_%D0%B4%D0%BE%D0%BC%D0%B5%D0%BD%D0%BD%D0%BE%D1%97_%D0%BF%D0%B5%D1%87%D1%96_2.jpg)，作者 Blast furnace chip worker，2010s | CC BY-SA 3.0 | 铁水/炉渣亮度关系、沟槽附近积渣和烟尘方向参考 | 非 GL02；衍生物涉及相同方式共享要求；不用于温度反演 |
| EXT-BF-003 | 铁矿球团形态 | [Iron ore pellets from Kiruna](https://commons.wikimedia.org/wiki/File:Iron_ore_pellets_from_Kiruna.jpg)，作者 J I P，2008-12-23 | CC BY-SA 3.0 或 GFDL | 球团粒径离散、颜色和表面孔隙的初步形态参考 | 页面带“资料尚待复核”提示；只能作为低置信度形态参考，禁止作为 GL02 配料证据 |
| EXT-BF-004 | 烧成砖/耐火砖表面 | [A block of fired bricks](https://commons.wikimedia.org/wiki/File:A_block_of_fired_bricks.jpg)，作者 Sabina Bajracharya，2020-05-28 | CC BY-SA 4.0 | 砖体孔隙、倒角、灰缝和烧成色差方向参考 | 普通参考砖不等同于 GL02 炉衬砖种；不得据此确定砖型、蚀损或热态色 |
| EXT-BF-005 | 高炉整体与历史图片图集 | [Wikimedia Commons: Blast furnace](https://commons.wikimedia.org/wiki/Blast_furnace) | 每张图片单独许可 | 补充设备类别、轮廓、平台和管线的候选参考来源 | 使用任一具体图片前必须单独登记作者、许可证、永久链接和用途 |

外部参考缩略图没有纳入离线交付；Wikimedia 限流或页面变化不会影响本地文档打开。使用时访问来源页并重新核对该文件当时的作者与许可。

## 3. 受控 HDRI

| Environment ID | 本地文件 | 来源/作者/许可 | 完整性 | 使用范围 | 状态 |
|---|---|---|---|---|---|
| `HDRI-INDUSTRIAL-SUNSET-2K-001` | `hdri/industrial_sunset_2k.hdr` | Poly Haven “Industrial Sunset”；作者 Sergej Majboroda；CC0 | 6,523,872 bytes；SHA256 `2a411097d65fcebfe00275641bd80350f95c7a1dbfc53b2260df85b296d2b990` | PBR 材质展示、PMREM 环境光、Blender/Three.js 同环境对照候选 | 已入库、未完成 GL02 现场光照标定 |

该 HDRI 可以成为固定 LookDev 展示环境，但不得称为 GL02 现场照明。其旋转、强度、曝光和太阳/补光参数仍由 LookDev 预设文件冻结。

## 4. 本地生成证据

本地 `P30`、`P40`、`P50` 图片是项目生成的 LookDev/烘焙证据，不是现场照片：

| Evidence ID | 阶段 | 根目录 | 证据性质 | 最终批准状态 |
|---|---|---|---|---|
| LOC-P30 | P30 炉壳材质 | `../../work/P30_SHELL_MATERIAL_20260716_223620/` | 程序材质与通道候选；P30 阶段曾允许进入 P40 | 非最终资产批准 |
| LOC-P40 | P40 固定灯光与相机 | `../../work/P40_FIXED_LOOKDEV_20260717_P36_FINAL/` | 固定 LookDev 的 Eevee/Cycles 对照；P40 阶段曾允许进入 P50 | 非最终资产批准 |
| LOC-P50 | P50 4K 全炉烘焙 | `../../work/P50_MASTER_4K_20260717_R1/` | 4K BaseColor、NormalGL、ORM 和多视图候选 | `KEEP_P50_PENDING_NOT_APPROVED` |

阶段性通过只证明当时阶段门槛满足，不得转述为“GL02 最终视觉资产已经批准”。

## 5. GL02 现场参考采集清单

以下证据取得前，材质卡中的现场来源保持 `REF-PENDING`：

| 采集编号 | 必采对象 | 拍摄要求 | 标定要求 | 当前状态 |
|---|---|---|---|---|
| REF-GL02-SHELL-01 | 炉壳喷漆、裸钢、锈蚀、水痕、焊缝 | 同一区域远/中/近三档；正视和约 45° 掠射光；避免美颜/HDR 自动滤镜 | 灰卡、色卡、长度标尺；记录日期、方位、楼层和是否检修 | REF-PENDING |
| REF-GL02-TUYERE-01 | 风口、弯头、法兰、平台、栏杆 | 安全许可距离内四方向；包含设备整体和接触细节 | 已知尺寸参照；记录照明和设备运行状态 | REF-PENDING |
| REF-GL02-TAPHOLE-01 | 出铁口、主沟、积渣和热影响区 | 正常生产状态与停炉/检修状态分开；不得影响生产 | 记录炉次、时间、拍摄距离；热区禁止用照片亮度推算绝对温度 | REF-PENDING |
| REF-GL02-REFRACTORY-01 | 备用砖、修补料、浇注料和拆换件 | 干燥/潮湿、清洁/积灰各一组；微距纹理 | 标尺、砖牌号/批次/用途，若涉密则只留内部资产 ID | REF-PENDING |
| REF-GL02-COKE-01 | 实际焦炭样品 | 均匀漫射光；正面、断面、孔隙近照；至少 20 粒 | 色卡、毫米标尺、筛分粒级 | REF-PENDING |
| REF-GL02-BURDEN-01 | 烧结矿和球团样品 | 分物料拍摄，不混装；至少 30 粒 | 色卡、毫米标尺、粒级、采样时间 | REF-PENDING |
| REF-GL02-CAST-01 | 铸铁/铜冷却壁可见样件或检修照片 | 正视、掠射光、加工面、氧化面 | 材质牌号、使用位置、是否为 GL02 原件 | REF-PENDING |
| REF-GL02-CIVIL-01 | 混凝土、保温包覆、格栅和栏杆 | 清洁区、积灰区、潮湿区分别拍摄 | 标尺、位置和维护状态 | REF-PENDING |

## 6. 入库字段

任何新增参考必须登记：

```yaml
reference_id:
source_type: GL02_SITE | ENGINEERING_DRAWING | VENDOR | PUBLIC_REFERENCE | LOCAL_RENDER
title:
author_or_owner:
captured_at:
location_or_url:
license_or_internal_permission:
gl02_applicability: direct | analogous | none
objects:
material_families:
scale_reference:
color_reference:
allowed_uses:
forbidden_uses:
sha256:
reviewer:
review_status: pending | accepted_for_direction | rejected
notes:
```

只有 `source_type=GL02_SITE/ENGINEERING_DRAWING` 且 `gl02_applicability=direct`、权限明确、标尺/色彩信息满足要求的资料，才能把对应材质卡的现场状态从 `REF-PENDING` 提升为 GL02 直接证据。
