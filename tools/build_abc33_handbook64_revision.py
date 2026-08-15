from __future__ import annotations

import argparse
import json
import re
from collections import defaultdict
from pathlib import Path

from docx import Document
from docx.enum.section import WD_SECTION
from docx.enum.table import WD_CELL_VERTICAL_ALIGNMENT, WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Cm, Pt, RGBColor


REQ_ID = "REQ-ABC33-HANDBOOK64-MECHANISM-INTERVENTION-20260810"
HEAT_BATCH_RATE_REQ_ID = "REQ-ABC33-HEAT-BATCH-RATE-CRITERION-20260810"
HEAT_BATCH_REFERENCE_LARGE_PER_HOUR = 7.5
HEAT_BATCH_NORMAL_DELTA_LARGE_PER_HOUR = 0.25
HEAT_BATCH_NORMAL_DELTA_SMALL_PER_HOUR = 0.5
HEAT_BATCH_HARD_DELTA_LARGE_PER_HOUR = 0.5
HEAT_BATCH_HARD_DELTA_SMALL_PER_HOUR = 1.0
HEAT_BATCH_TWO_HOUR_EXCESS_LARGE_PER_HOUR = 1.0
HEAT_BATCH_RATE_WEIGHT = 20
HEAT_BATCH_RATE_CRITERION = (
    "料速采用“前30 min—后30 min”对比，并以昨日平均料速作为正常料速基线，同时读取MES滚动24 h平均料速作在线对照。"
    "一般参考约7.5大批/h；煤或矿单独完成一次计1小批，煤与矿完成一组计1大批。连续1 h分别计算前30 min料速v前与"
    "后30 min料速v后：正常速率差|v后-v前|≤0.25大批/h或≤0.5小批/h；连续两个半小时的料速变化不宜过大，"
    "硬上限为|v后-v前|≤0.5大批/h或≤1小批/h。例如前30 min为7.0小批，后30 min应处于6.5—7.5小批。"
    "v后＜v前（后段变慢）支持炉温上行，v后＞v前（后段变快）支持炉温下行。若当前连续2 h大批料速高于MES 24 h平均值"
    "1大批/h及以上，按现场判据判定炉温必然下行，必须立即进入提炉温处置流程并由值班工长确认。该判据排在热制度维护、"
    "炉温上行风险和炉温下行风险的第一位；同时结合出铁口温度、综合顶温、理论燃烧温度、炉前渣铁状态及操作滞后复核。"
)
HEAT_BATCH_RATE_RULE_IDS = frozenset({"A2", "B4", "B5"})
HEAT_BATCH_RATE_FORMULA_ANCHORS = {
    "A2": "100-Score(30*g_A(z60_T_taphole_mean",
    "B4": "Score(25*g_H(z60_T_taphole_mean",
    "B5": "Score(25*g_L(z60_T_taphole_mean",
}
HEAT_BATCH_RATE_WEIGHTED_FORMULAS = {
    "A2": (
        "100-Score(20*BurdenRateDev（前后30分钟料速差、昨日平均料速、MES 24小时平均料速） + "
        "24*g_A(z60_T_taphole_mean（1#、2#出铁口温度均值）,0.6,1.2) + "
        "12*g_A(slope30_T_taphole_mean（1#、2#出铁口温度均值趋势）,0.5,1.2) + "
        "12*g_A(slope30_T_top（综合顶温趋势）,0.5,1.2) + 8*GasUtilDev（煤气利用率） + "
        "8*g_A(z60_PCI_rate（喷煤量/喷煤强度）,0.6,1.2) + 8*g_A(z60_T_blast（热风温度）,0.6,1.2) + "
        "8*g_A(z60_TFT（理论燃烧温度）,0.6,1.2))"
    ),
    "B4": (
        "Score(20*BurdenRateSlow（后30分钟料速变慢、前后30分钟料速差） + "
        "20*g_H(z60_T_taphole_mean（1#、2#出铁口温度均值）,0.8,1.5) + "
        "12*g_H(slope30_T_top（综合顶温趋势）,0.5,1.2) + 12*AirAcceptBad（热风压力、风量、压差） + "
        "8*g_H(z60_DP_upper（上部压差）,0.8,1.5) + 8*TopTempRange（顶温A-D） + "
        "12*g_H(max(z60_T_blast（热风温度）,z60_PCI_rate（喷煤量/喷煤强度）,z60_Q_O2（富氧流量）,"
        "z60_TFT（理论燃烧温度）),0.8,1.5) + 8*g_L(z60_PI（透气性指数）,-0.8,-1.5))"
    ),
    "B5": (
        "Score(20*BurdenRateFast（后30分钟料速变快、连续2小时料速超过MES 24小时均值） + "
        "20*g_L(z60_T_taphole_mean（1#、2#出铁口温度均值）,-0.8,-1.5) + "
        "12*g_L(slope30_T_top（综合顶温趋势）,-0.5,-1.2) + "
        "12*g_L(z60_P_blast（热风压力）,-0.8,-1.5) + 8*g_H(z60_Q_blast（冷风管道流量/风量）,0.8,1.5) + "
        "8*GasUtilDev（煤气利用率下降） + 12*g_L(min(z60_T_blast（热风温度）,z60_PCI_rate（喷煤量/喷煤强度）,"
        "z60_Q_O2（富氧流量）,z60_TFT（理论燃烧温度）),-0.8,-1.5) + "
        "8*BurdenSlip（主料线、顶压、压差）)"
    ),
}
REVISION_TITLE = "ABC33形成原理与干预处置流程（见习高炉长64章映射补充）"


CHAPTERS: dict[int, str] = {
    1: "总体判断原则",
    2: "正常顺行炉况",
    3: "管道行程",
    4: "悬料",
    5: "连续崩料",
    6: "炉热",
    7: "炉凉",
    8: "炉缸冻结风险",
    9: "边缘煤气流过分发展、中心过重",
    10: "中心煤气流过分发展、边缘负荷过重",
    11: "低料线或亏料线",
    12: "炉墙结厚或结瘤趋势",
    13: "冷却设备漏水引起炉凉",
    14: "偏料或偏行",
    15: "压差与透气性恶化",
    16: "渣铁排放不净",
    17: "控制室工长最终判断框架",
    18: "煤气流分布是否合理的判断",
    19: "利用炉喉CO₂曲线判断煤气流",
    20: "送风制度管理",
    21: "鼓风动能过大或过小",
    22: "风量调节经验",
    23: "风温调节经验",
    24: "喷煤调节与热滞后",
    25: "高喷煤状态下的判断重点",
    26: "富氧操作经验",
    27: "高压操作经验",
    28: "热制度管理",
    29: "原燃料质量变化的判断",
    30: "装料制度与上下部调剂",
    31: "装料制度调整的作用延迟",
    32: "造渣制度管理",
    33: "软熔带状态判断",
    34: "炉缸堆积",
    35: "含硅和含硫的联合判断",
    36: "控制室‘调剂—观察—复核’闭环",
    37: "工长最应避免的反向操作",
    38: "控制室工长的核心能力",
    39: "鼓风机突然停风",
    40: "事故状态下放风阀不能放风",
    41: "送风吹管发红、窝渣或烧穿",
    42: "风口烧穿或严重破损",
    43: "炉体跑火、炉壳发红或开裂",
    44: "炉缸、炉底烧穿风险",
    45: "冷却壁水温差或热流超标",
    46: "高炉上部炉衬脱落",
    47: "短期休风前的判断",
    48: "短期休风操作",
    49: "短期休风后复风",
    50: "长期休风前的热量和炉料准备",
    51: "长期休风期间炉体密封",
    52: "长期休风后复风",
    53: "倒流休风",
    54: "坐料安全控制",
    55: "封炉前的炉况准备",
    56: "封炉期间的主要风险",
    57: "护炉操作",
    58: "洗炉操作的控制边界",
    59: "碱金属负荷升高",
    60: "炼钢生铁转铸造生铁",
    61: "低硅生铁冶炼",
    62: "高强度冶炼的边界",
    63: "煤气爆炸风险",
    64: "剩余文档内容的筛选结论",
}


RULES: list[dict[str, object]] = [
    {
        "id": "A1",
        "name": "正常顺行维护分",
        "chapters": [1, 2, 17, 36, 37, 38, 64],
        "mechanism": "正常顺行不是单一参数处在正常值，而是炉料下降、煤气上升、炉缸供热、渣铁排放和冷却系统形成动态平衡。料柱透气性稳定时，风压—风量—压差关系平稳，料尺均匀下降，圆周煤气流不过度偏边或偏中心，炉缸热状态和炉前排放能够相互支撑。任何一条链路持续偏离，都会先表现为维护分下降，再向相应B类异常演化。",
        "steps": [
            "先按总体判断框架核对炉温、煤气流、料线、压差、送风、排放和冷却，不以单点瞬时波动定性。",
            "状态稳定时维持现有制度，风量、风温、喷煤、富氧和布料不要同时改变。",
            "确需调剂时一次只改变一个主要方向，记录操作前值、操作量、时间和预期响应。",
            "按15—30分钟短期、60分钟中期及一个冶炼周期长期复核；方向错误时停止继续叠加操作。",
            "维护分持续下降时转入B类候选逐项排查；出现C类现场事件时立即越过普通维护流程。",
        ],
    },
    {
        "id": "A2",
        "name": "炉温管理稳定分",
        "chapters": [6, 7, 23, 28, 29, 35, 60, 61],
        "mechanism": "炉温由热量收入、热量消耗、料速和热滞后共同决定。风温、富氧、实际喷煤速率、焦炭负荷、原燃料质量和煤气利用改变热量来源；料速、渣铁排放、冷却漏水和炉缸工作状态改变热量消耗。出铁口温度、综合顶温和理论燃烧温度只能联合判断方向，不能用单点替代铁水成分和炉前观察。",
        "steps": [
            "先确定偏热、偏凉还是仅短时波动，并复核最近一次风温、喷煤、富氧、焦炭负荷和原燃料变化时间。",
            "核对出铁口温度均值与趋势、综合顶温趋势、理论燃烧温度、料速、煤气利用率及渣铁排放。",
            "偏热时优先削减过量热输入并等待热滞后；偏凉时补热、控料速、保透气和保出铁同步进行。",
            "炼钢铁转铸造铁、低硅冶炼等目标切换必须分阶段调整，禁止用一次大幅度操作追赶成分。",
            "连续两个复核窗口仍向错误方向发展时，停止原调剂并进入B4或B5处置。",
        ],
    },
    {
        "id": "A3",
        "name": "煤气利用与气流分布优化分",
        "chapters": [9, 10, 18, 19, 21, 30],
        "mechanism": "煤气流由下部鼓风动能、风口工作、软熔带形状和上部布料共同决定。合理分布要求中心与边缘都有适当通量，圆周方向基本对称，并保持足够煤气—炉料接触。中心或边缘单侧过强都会降低利用率，并通过四点顶温、四点顶压、静压力和炉体方位温度的离散性体现。CO₂曲线可作为工艺复核，但未接入的CO₂点位不进入自动评分。",
        "steps": [
            "先用顶温A—D、顶压A—D、各层静压力、炉体各层A—H和煤气利用率确认偏差是否同一方位、是否持续。",
            "再结合鼓风动能、风压—风量—压差关系和软熔带状态判断问题主要来自下部送风还是上部布料。",
            "下部调剂与上部布料不得同时大幅改变；先选主要矛盾，保留足够观察时间。",
            "气流趋于对称、利用率回升且压差未恶化后，才允许小步恢复强化参数。",
            "若偏边或偏中心持续强化，分别转入B7或B8；出现管道特征时转B1/C2。",
        ],
    },
    {
        "id": "A4",
        "name": "送风制度与压量关系维护分",
        "chapters": [15, 20, 21, 22, 27, 62],
        "mechanism": "送风制度决定煤气动力和下部工作状态。高炉能够接受风量时，冷风压力、热风压力、风量、上下部压差和透气性保持协调；料柱阻力或排放恶化时，常出现压力升高而风量下降。鼓风动能过大易强化中心或局部通道，过小则边缘不活、炉缸工作弱。高压和高强度只能建立在稳定透气与顺畅排放之上。",
        "steps": [
            "连续观察冷风压力、热风压力、冷风流量、全炉/上下部压差和透气性，不以压力单值判断可加风。",
            "先定位阻力来自上部料柱、软熔带、滴落带还是炉缸排放，再决定维持、减压或调整送风。",
            "日常调节采用小步、单方向、可回退原则；压力和风量变化后至少观察一个短期窗口。",
            "压差升高时同步检查料线、渣铁排放和气流分布，禁止只减风而不查根因。",
            "压量关系恢复且透气性稳定后分级恢复；持续恶化转B10，事故停风转C9。",
        ],
    },
    {
        "id": "A5",
        "name": "喷煤—富氧—风温协同优化分",
        "chapters": [23, 24, 25, 26, 37, 62],
        "mechanism": "喷煤、富氧和风温共同改变风口前理论燃烧温度、煤气量、焦比替代和软熔带状态。实际喷煤速率反映当前输送，喷煤设定反映工长目标，两者不可混用。喷煤和富氧的热效应存在滞后；透气性不足时继续强化会增加压差、中心气流和未燃煤粉风险。",
        "steps": [
            "区分喷煤设定与实际喷煤速率，核对实际值是否跟随设定、煤粉质量和输送是否稳定。",
            "联看富氧率/流量、热风温度、理论燃烧温度、压差、透气性和煤气利用率。",
            "一次只改变一个主要热输入方向，记录生效时刻并等待规定热滞后，禁止短时间连续反向调节。",
            "高喷煤或高富氧前先确认顺行、排放、冷却和气流分布具有余量。",
            "压差或气流恶化时先停止强化并复核；满足恢复条件后再分级增加。",
        ],
    },
    {
        "id": "A6",
        "name": "装料、料线和偏行维护分",
        "chapters": [11, 14, 29, 30, 31],
        "mechanism": "上部装料决定矿焦径向分布和料面形状，进而塑造煤气阻力。料线稳定、两尺下降速率协调时，上下部制度相互适应；设备零点、布料器、原料粒度或炉墙状态异常会造成固定方向偏差。南北探尺应同时比较长期工作均值、相对偏差和下降速率，不能只看绝对差。",
        "steps": [
            "先核对主料线和南北探尺有效性、零点、工作状态、长期均值偏差及下降速率。",
            "排除上料、称量、布料器和炉喉设备故障，再判断是真实偏料、低料线还是仪表偏差。",
            "调整装料制度时只改一个主要分布方向，并至少等待若干批料到达作用区域。",
            "观察料线、四点顶温/顶压、静压力、炉体方位温度和压差是否按预期响应。",
            "低料线转B6，固定偏行转B9，停滞或塌落分别转B2/B3。",
        ],
    },
    {
        "id": "A7",
        "name": "造渣与渣铁排放维护分",
        "chapters": [16, 32, 33, 34, 35, 60, 61],
        "mechanism": "造渣制度影响软熔带透气、脱硫、渣铁分离和炉缸热状态；排放节奏决定炉缸液位和下部阻力。渣铁排放不净会使下部压差升高、风口工作转弱并影响炉温。传感器代理只能提示风险，是否出净、铁口深度、渣铁流动性和成分必须由炉前确认。",
        "steps": [
            "核对出铁节奏、铁口深度、实际出铁量、渣铁流动性和渣中带铁等现场信息。",
            "联看出铁口温度、下部压差、透气性、料线和压量关系，区分上部阻力与炉缸积存。",
            "根据碱度、MgO/Al₂O₃、硫负荷和目标生铁品种分阶段调整造渣，禁止只追单一化验指标。",
            "先保证按时出净渣铁和炉缸通道，再讨论恢复风量、喷煤或富氧。",
            "排放代理恶化转B13；出现炉缸堆积或液泛证据转C3。",
        ],
    },
    {
        "id": "A8",
        "name": "冷却与长寿维护分",
        "chapters": [13, 45, 57, 58, 59],
        "mechanism": "冷却系统通过稳定水量、水压和热交换把炉衬热负荷控制在安全边界。气流偏斜、结厚脱落、碱金属侵蚀或强化过度都会改变局部热流。单点温度或水温差升高不能独立定性，必须与同层同方位、冷却流量/压力、长期基线和现场炉壳状态交叉确认。",
        "steps": [
            "逐系统核对软水、高压水、中压水和膨胀罐液位的数据新鲜度、压力、流量及趋势。",
            "按炉体层位和方位比较当前值、15/30/60分钟变化及30日基线，确认是否固定点持续偏离。",
            "同步复核煤气流、压差、排放和炉衬状态，区分气流热负荷、冷却故障与仪表异常。",
            "护炉、洗炉或处理碱金属时采用专项方案并持续监控，禁止把短期温度下降等同风险解除。",
            "漏水趋势转B12，热流超标转C4，炉壳/炉底安全事件转C5/C7。",
        ],
    },
    {
        "id": "A9",
        "name": "经济指标优化边界分",
        "chapters": [25, 26, 27, 29, 35, 59, 60, 61, 62],
        "mechanism": "低燃料比、高喷煤、高富氧、高压、高强度和低硅冶炼都会压缩炉况余量。经济优化只有在透气、煤气利用、炉温、排放和冷却均稳定时才可持续；原燃料或碱金属负荷恶化会使同一强化水平转为风险。实际喷煤速率用于判断当前强化负荷，喷煤设定只作为操作目标和执行偏差复核。",
        "steps": [
            "优化前建立顺行、透气、煤气利用、炉温、排放和冷却六项安全门。",
            "一次只推进一个经济目标，记录实际喷煤速率、富氧、风量和压力等真实负荷。",
            "原燃料质量、碱金属、含硅含硫或生铁品种变化时，重新评估边界，不沿用旧强度。",
            "任何安全门恶化时立即停止继续强化，优先恢复顺行和排放。",
            "稳定跨越完整观察周期后方可进入下一步；经济指标不得覆盖B/C类异常与安全报警。",
        ],
    },
    {
        "id": "B1",
        "name": "管道行程预警",
        "chapters": [3, 18, 30, 37],
        "mechanism": "料柱局部形成低阻通道后，煤气沿固定路径高速上窜，压力迅速传至炉顶，造成顶压尖峰、局部顶温升高和圆周分布失衡。通道区气速过高而其他区域煤气不足，煤气利用下降，并可进一步诱发滑料、崩料和炉温波动。",
        "steps": [
            "立即降低煤气动力，按现场批准幅度减压/减风；炉热诱发时同步削减热输入。",
            "严重或持续管道时停止喷煤和富氧候选，控制顶温与压差，禁止快速恢复。",
            "核对顶压尖峰、四点顶温/顶压、静压力、料线、压差和固定方位炉体温度。",
            "排除布料设备和原燃料异常后，用受控布料重新分配煤气流；常规调剂无效时按专项方案处理。",
            "顶压尖峰消失、料线恢复、圆周差收敛并持续稳定后，才小步恢复；严重组合升级C2。",
        ],
    },
    {
        "id": "B2",
        "name": "悬料预警",
        "chapters": [4, 15, 54],
        "mechanism": "料柱局部或整体阻力过高时，炉料下降停滞，热风压力和压差上升，风量下降，高炉表现为不接受风量。悬料持续会积累煤气和料柱势能，一旦突然坐下可能造成大崩料、炉顶压力冲击和炉况急剧波动。",
        "steps": [
            "确认主料线及探尺真实停滞，联看风压、风量、全炉/上下部压差、顶压和透气性。",
            "立即停止继续强化送风、富氧和喷煤，维持安全煤气动力并查明阻力部位。",
            "短时不能解除时准备坐料条件，明确人员撤离、炉顶和煤气系统状态。",
            "坐料必须按专项安全程序执行，未确认料柱坐下前禁止更换风口或开展危险作业。",
            "恢复下料后先观察压量关系和炉温，再分级恢复；连续塌落转B3/C2。",
        ],
    },
    {
        "id": "B3",
        "name": "连续崩料/滑料预警",
        "chapters": [5, 37, 54],
        "mechanism": "料柱反复停滞后突然塌落，意味着上部阻力和支撑结构周期性失稳。塌落会引起风压、风量、顶压和压差剧烈波动，破坏煤气分布，并使未充分还原和加热的炉料快速进入下部，造成炉温下降和排放恶化。",
        "steps": [
            "立即降低煤气动力至能够制止连续崩料，暂停强化操作并保护炉顶压力。",
            "核对60分钟突降频次、料线波动、顶压尖峰、压差和出铁口温度趋势。",
            "根据炉温和料柱状态补加净焦、缩小矿批或减轻负荷，组织好出铁。",
            "查明上部布料、原料粉末、设备和下部排放原因，不把一次落尺当作恢复。",
            "料线连续稳定、炉温回升、压量关系恢复后再逐级恢复；伴严重管道时升级C2。",
        ],
    },
    {
        "id": "B4",
        "name": "炉热预警",
        "chapters": [6, 23, 24, 28, 37],
        "mechanism": "热量收入超过炉料加热、还原、熔化和散热需求时，炉温逐步上行，软熔带可能下移或增厚，料柱阻力增加，出现风压升高、风量下降和料速变慢。炉热与难行叠加时，盲目加风、加氧或提顶压会进一步放大压差和管道风险。",
        "steps": [
            "用出铁口温度、综合顶温、理论燃烧温度、料速和压量关系确认持续偏热。",
            "回看喷煤、富氧、风温和焦炭负荷的操作时刻，区分当前升温与滞后效应。",
            "优先小步减少喷煤设定或其他过量热输入，保持渣铁排放，不同时多方向大改。",
            "炉热伴难行时先保透气和气流稳定，禁止强行加风、加氧或提压硬顶。",
            "热趋势回落且压差、料速恢复后保持观察，避免过度降热转为B5。",
        ],
    },
    {
        "id": "B5",
        "name": "炉凉/大凉预警",
        "chapters": [7, 13, 28, 29, 37],
        "mechanism": "热量收入不足、原燃料恶化、料速过快、漏水或连续崩料会使炉缸热储备下降。严重时渣铁黏度增加、排放变差、透气性恶化，形成‘炉凉—排放不畅—更难接受风量’的反馈。只增加热输入而不控制料速和透气，可能把炉凉推向悬料。",
        "steps": [
            "确认出铁口温度、综合顶温、理论燃烧温度和炉前流动性均支持向凉趋势。",
            "立即排查冷却漏水、原燃料质量、崩料、料速和喷煤实际执行，不能先假定为普通热不足。",
            "补热、控制料速、保持透气和组织出铁同步进行；必要时减轻焦炭负荷或补净焦。",
            "任何增煤建议必须通过压力制度、煤粉质量和顺行安全门，处于减压阶段时阻断增煤。",
            "温度和排放持续恶化时升级C1；确认漏水则转B12/C4。",
        ],
    },
    {
        "id": "B6",
        "name": "低料线/亏料线预警",
        "chapters": [11, 31, 37],
        "mechanism": "上料能力不足或下料速度超过补料速度时，料线偏离正常工作区。低料线使炉顶有效料柱缩短，煤气分布和热交换改变，持续时间越长，顶温冲高、局部气流、炉凉和炉墙粘结风险越大。探尺方向和零点必须先经现场确认。",
        "steps": [
            "以现场确认的主探尺工作值为核心，核对上料设备、称量、布料和探尺有效性。",
            "记录偏离正常料线的深度、开始时间和预计恢复时间，联看顶温、压差和气流分布。",
            "必要时按批准幅度降低冷风压力/煤气动力；持续或设备故障时准备休风。",
            "持续超过手册时限时根据炉温、深度和持续时间减轻焦炭负荷，避免恢复后立即全风。",
            "料线恢复后仍需等待料柱和气流稳定，再分级恢复参数。",
        ],
    },
    {
        "id": "B7",
        "name": "边缘煤气流过分发展预警",
        "chapters": [9, 18, 19, 21, 30],
        "mechanism": "边缘阻力偏低或中心负荷过重时，煤气沿炉墙上升，造成炉体固定方位温度偏高、四点顶温/顶压差扩大和煤气利用下降。过强边缘气流增加炉墙热负荷、结瘤脱落及炉壳安全风险。",
        "steps": [
            "用顶温、顶压、静压力和炉体温度的同方位一致性确认，不以单点高温定性。",
            "复核CO₂曲线（若现场可用）、煤气利用率、鼓风动能和上下部压差。",
            "判断由下部鼓风动能还是上部矿焦分布引起，选一个主要方向小步调剂。",
            "加强对应方位冷却和炉体温度观察，气流未稳定前不继续强化。",
            "固定热点、冷却异常或炉壳事件出现时转C4/C5/C7。",
        ],
    },
    {
        "id": "B8",
        "name": "中心煤气流过分发展预警",
        "chapters": [10, 18, 19, 21, 30],
        "mechanism": "中心阻力偏低或边缘负荷过重时，煤气集中穿过中心，边缘温度偏低且不活跃。中心气流过强会缩短煤气与炉料接触路径，降低利用率，并可能伴随风压、压差升高和透气性偏离。",
        "steps": [
            "核对炉体方位温度偏低、压差、透气性、顶温/顶压分布和静压力是否共同支持中心过强。",
            "复核鼓风动能、风口工作和上部布料，排除结厚或局部设备故障造成的假象。",
            "选择下部送风或上部布料中的一个主要方向调整，避免同时大幅改变。",
            "观察煤气利用率、圆周温度和压量关系是否改善，保留装料作用延迟。",
            "边缘长期不活并伴固定低温、压差恶化时转B11。",
        ],
    },
    {
        "id": "B9",
        "name": "偏料/偏行预警",
        "chapters": [14, 30, 31],
        "mechanism": "料面或矿焦分布固定向一侧偏移，会造成圆周阻力不均，继而使顶温、顶压、静压力和炉体温度呈同方向偏差。探尺零点误差、探锤故障、布料器磨损、炉喉钢瓦或风口进风不均也会产生类似信号。",
        "steps": [
            "比较南北探尺长期工作均值、当前相对偏差和下降速率，不直接用绝对差下结论。",
            "先检查探尺零点、探锤、布料器、炉喉设备和风口工作，排除测量与设备原因。",
            "用四点顶温/顶压、静压力和炉体方位温度确认真实偏行及方向。",
            "受控调整布料并等待若干批料作用，禁止一两批后再次反向修改。",
            "偏差收敛且料线平稳后保持；伴固定低温结厚特征时转B11。",
        ],
    },
    {
        "id": "B10",
        "name": "压差与透气性恶化预警",
        "chapters": [15, 20, 33, 34, 37],
        "mechanism": "料柱粒度、上部布料、软熔带、滴落带或炉缸液位均可增加阻力。阻力升高时表现为全炉或局部压差持续上升、透气性恶化、风压升高而风量下降。压差是结果，不直接说明阻力位置。",
        "steps": [
            "分解全炉、上部和下部压差，结合料线、风压—风量、透气性和排放定位阻力区域。",
            "检查原燃料粉末、布料、软熔带热状态、炉缸排放和冷却漏水。",
            "先降低不安全的煤气动力并保持出铁，禁止在原因未明时继续加风加氧。",
            "针对根因实施上部、热制度或炉前措施，一次只改变主方向。",
            "压差与透气性连续恢复后再分级恢复；悬料转B2，堆积转C3。",
        ],
    },
    {
        "id": "B11",
        "name": "炉墙结厚/结瘤趋势预警",
        "chapters": [12, 18, 29, 57, 58, 59],
        "mechanism": "局部炉墙长期低温、碱金属循环、原燃料粉末和气流偏斜可使炉料或渣相在炉墙黏结。结厚后圆周截面和阻力改变，造成固定方位低温、偏行、滑尺、管道或悬料；结瘤突然脱落又可能引起炉况和炉体安全波动。",
        "steps": [
            "确认固定层位/方位低温持续存在，并与同层其他点、冷却水和30日基线比较。",
            "联看料线偏差、压差、透气性、顶温/静压力分布和装料调整是否失去预期效果。",
            "排查原燃料粉末、碱金属负荷和冷却强度，禁止按一次温降直接判断结厚。",
            "护炉、洗炉或装料调整必须按专项方案分阶段执行，并监测脱落风险。",
            "温度突变、压差和料线强波动时警惕炉衬/结瘤脱落，转C8。",
        ],
    },
    {
        "id": "B12",
        "name": "冷却漏水导致炉凉预警",
        "chapters": [13, 45, 57],
        "mechanism": "冷却设备破损使水进入炉内，一方面直接吸收大量热量，另一方面破坏料柱和炉缸状态，导致炉温下降、压差和气流异常。冷却流量、压力、膨胀罐液位或对应方位炉体温度异常只能形成疑似信号，必须与现场排水、H₂和设备检查确认。",
        "steps": [
            "立即核对冷却系统各支路流量、压力、膨胀罐液位、回水和数据新鲜度，排除仪表故障。",
            "锁定异常层位和方位，联看炉体温度、出铁口温度、综合顶温、压差和料线。",
            "通知冷却与炉前现场检查；疑似漏水未排除前停止强化操作，禁止盲目补热掩盖。",
            "按现场制度隔离、倒换或处理故障冷却设备，同时保透气、保排放、防大凉。",
            "漏水证据增强或热流异常升级C4；出现炉壳/烧穿风险转C5/C7。",
        ],
    },
    {
        "id": "B13",
        "name": "渣铁排放不净预警",
        "chapters": [16, 32, 33, 34],
        "mechanism": "出铁不及时、铁口浅、渣铁流动性差或炉缸通道受阻会使液位升高并增加下部阻力，表现为下部压差升高、透气性恶化、风口活跃度下降和料线停滞。出铁口温度等传感器仅为代理，不能代替炉前出净确认。",
        "steps": [
            "立即向炉前确认开堵口、出铁量、铁口深度、渣铁流动性、出净情况和异常喷溅。",
            "联看下部压差、透气性、出铁口温度、料线和风压—风量关系。",
            "优先组织按时出净渣铁，调整出铁节奏和炉前作业，不在液位偏高时继续强化。",
            "复核造渣制度、炉温、焦炭质量、碱金属和冷却漏水等根因。",
            "排放恢复后观察下部压差；持续积存或液泛证据转C3。",
        ],
    },
    {
        "id": "C1",
        "name": "炉缸冻结专项报警",
        "chapters": [7, 8, 13, 34, 50, 52],
        "mechanism": "严重炉凉、漏水、长休风或连续崩料会耗尽炉缸热储备，使渣铁黏度升高、铁口通道难以建立，最终造成渣铁不能正常流动。冻结不是仅由温度低决定，必须同时出现炉前流动性、排放、压量关系和热状态证据。",
        "steps": [
            "立即启动厂级炉缸冻结专项预案并由值班负责人组织，系统仅提供只读证据。",
            "确认铁口能否建立通道、渣铁流动性、实际排放量、风口状态和是否存在漏水。",
            "降低不安全强化水平，集中恢复热量、透气和排放通道；操作次序按现场专项方案。",
            "长休风/复风场景严格核对热量准备、炉料、密封和初始风量，禁止强行快速复风。",
            "只有炉前通道、温度、排放和压量关系共同恢复并经人工确认后，才解除报警。",
        ],
    },
    {
        "id": "C2",
        "name": "严重管道/大崩料专项处理报警",
        "chapters": [3, 5, 37, 54],
        "mechanism": "严重管道与连续崩料同时发生时，局部高速煤气通道和料柱周期失稳相互强化，顶压尖峰、顶温快速上升、压差强波动并存，既可能损伤炉顶设备，也会使冷料快速下落造成大凉。该事件必须由管道、崩料和严重度证据交叉确认，不能由单一高分触发现场定论。",
        "steps": [
            "立即按专项流程快速降低煤气动力，停止喷煤和富氧候选，控制顶压、顶温和人员安全。",
            "确认顶压尖峰、顶温快速上升、连续落尺/崩料及压差强波动同时成立。",
            "必要时按厂级预案放风或坐料；相关阀门、炉顶和煤气系统状态必须人工确认。",
            "组织出铁、补热和负荷调整，防止大崩料后炉温快速下降。",
            "事件消退后仍需连续观察料线、压量关系和炉温，未经负责人批准不得快速恢复。",
        ],
    },
    {
        "id": "C3",
        "name": "炉缸堆积/液泛专项报警",
        "chapters": [16, 33, 34, 58, 59],
        "mechanism": "渣铁生成量超过排放能力、炉缸通道不畅、焦炭劣化或液体滞留时，炉缸液位和滴落带阻力上升，形成液泛或堆积。表现为下部压差升高、风口活跃度下降、铁口浅、出铁量不足和高炉不接受风量。",
        "steps": [
            "由炉前确认铁口深度、实际排放量、渣铁流动性和出净情况，不能只凭传感器评分。",
            "降低强化水平并组织出净渣铁，保持安全送风和炉缸热量。",
            "复核焦炭质量、造渣、软熔带、冷却漏水和碱金属负荷，确定堆积原因。",
            "洗炉或护炉措施必须执行专项审批和边界监测，不得把洗炉当作常规快速手段。",
            "下部压差、排放量和风口状态共同恢复并人工确认后解除。",
        ],
    },
    {
        "id": "C4",
        "name": "冷却壁热流/水温差超标专项报警",
        "chapters": [13, 45, 57],
        "mechanism": "冷却壁对应区域热负荷上升、结厚脱落、边缘气流冲刷或冷却供水异常，会造成水温差、热流、流量/压力及炉体方位温度异常。严重事件必须由冷却系统异常与同方位炉体热负荷交叉确认，单一水温差或单一温度点不足以判定。",
        "steps": [
            "立即锁定异常冷却回路、层位和方位，核对进回水、流量、压力、热流和仪表有效性。",
            "比较同层其他点、15/30/60分钟变化和30日基线，并联看顶温/顶压及炉体方位温度。",
            "通知冷却与炉体专业现场复核，必要时降低强化水平并加强相应方位冷却监护。",
            "排查边缘气流、结厚脱落、漏水和供水故障；未经确认不得仅靠调剂掩盖异常。",
            "热流和供水恢复且现场确认无泄漏/损伤后方可关闭；炉壳异常升级C5/C7。",
        ],
    },
    {
        "id": "C5",
        "name": "炉缸/炉底烧穿风险专项报警",
        "chapters": [44, 45, 57],
        "mechanism": "炉缸炉底耐材侵蚀、铁水环流冲刷、冷却失效或局部高热负荷会使固定点温度/热流持续抬升。当其与冷却异常、铁口过浅、排放不足、炉壳发红或炉基裂缝冒煤气等独立证据并存时，才构成高可信烧穿风险。",
        "steps": [
            "立即启动最高级炉体安全预案，划定警戒区并通知生产、设备和安全负责人。",
            "逐点核对炉缸/炉底全部测温点、对应冷却回路、变化速率和长期基线，不以单点高值定性。",
            "现场检查炉壳颜色、裂缝、煤气、铁口深度和排放，建立第二类独立证据。",
            "按厂级预案降强度、堵风口、组织出铁或休风凉炉；系统不得直接下发控制。",
            "只有多专业会签确认风险消除后才允许解除红色状态，传感器回落不能自动关闭。",
        ],
    },
    {
        "id": "C6",
        "name": "风口/吹管烧穿专项报警",
        "chapters": [41, 42],
        "mechanism": "吹管窝渣、发红、风口冷却破坏或机械损伤会造成高温煤气、渣铁外喷和冷却水入炉的双重风险。风量/压力波动和冷却异常只能作为辅助，发红、漏水、破损和喷溅必须现场确认。",
        "steps": [
            "立即通知风口平台和控制室，建立危险区域隔离并确认人员撤离。",
            "现场确认具体风口/吹管、发红、窝渣、漏水和喷溅情况，同时核对对应冷却回路。",
            "按事故预案停煤、停氧、降低压力和煤气动力，优先控制渣铁外喷与水入炉。",
            "组织出铁后按条件休风更换或封堵，任何作业必须在压力和料柱状态确认后进行。",
            "设备更换、冷却和炉况复核全部合格并经批准后复风。",
        ],
    },
    {
        "id": "C7",
        "name": "炉体跑火、炉壳发红或开裂专项报警",
        "chapters": [43, 45, 57],
        "mechanism": "炉衬或冷却壁失效、局部气流冲刷会使高温煤气和热量作用到炉壳，出现跑火、发红或开裂。自动评分中的炉体温度、方位极差和冷却风险只是趋势证据，必须与现场炉壳事件形成独立交叉确认。",
        "steps": [
            "立即启动炉体安全专项处置，划定警戒区并确认跑火、发红、裂缝的层位和方位。",
            "联查该区域全部测温点、冷却回路、顶温/顶压和气流方向，防止只展示少数点位。",
            "按现场预案采取打水、降压、减风或停风等措施，优先制止跑火并保护人员。",
            "检查冷却壁漏水、炉衬侵蚀和可能的结瘤脱落，必要时转烧穿风险处置。",
            "现场事件关闭、温度/冷却趋势稳定并经负责人批准后解除，禁止仅凭分数回落自动关闭。",
        ],
    },
    {
        "id": "C8",
        "name": "炉衬脱落专项报警",
        "chapters": [12, 46, 57, 58],
        "mechanism": "炉衬、结厚或结瘤局部脱落会突然改变炉墙热阻和料柱截面，造成对应层位温度突变、料线和压差波动、煤气流重新分配，严重时冷料下落导致炉凉并增加炉体暴露风险。",
        "steps": [
            "确认温度突变的层位、方位和范围，并与同层点位、冷却回路及历史基线比较。",
            "联看料线突变、压差、顶温分布、炉温和出铁，区分仪表故障、结瘤脱落与耐材脱落。",
            "降低不安全强化水平，加强冷却和炉体监护，必要时补净焦防止炉凉。",
            "护炉或洗炉措施必须根据脱落位置和炉体安全专项审批，不得盲目加剧冲刷。",
            "温度、冷却、料线和压差稳定并经设备/生产共同确认后解除。",
        ],
    },
    {
        "id": "C9",
        "name": "鼓风机突然停风/煤气倒流专项报警",
        "chapters": [39, 40, 53],
        "mechanism": "鼓风机或送风系统突然失压时，炉缸和煤气系统的压差关系瞬间改变；若混风阀、放风阀或止回条件异常，炉缸煤气可能倒入冷风管道。倒流休风同样需要受控建立气路，错误阀位会引发煤气和人员事故。",
        "steps": [
            "立即按事故联锁和厂级预案确认停风原因、风机、冷风/热风管道及阀门状态。",
            "关闭混风相关通路，停止喷煤和富氧，处理炉顶与煤气系统压力；不得依赖页面代替联锁。",
            "放风阀不能动作时执行备用泄压与隔离流程，禁止未经确认强行操作。",
            "按预案通入蒸汽或氮气，监测煤气倒流、压力和人员安全。",
            "恢复送风前完成设备、阀位、炉顶、煤气、炉缸热量和渣铁条件的联合确认。",
        ],
    },
    {
        "id": "C10",
        "name": "煤气爆炸风险专项报警",
        "chapters": [40, 51, 56, 63],
        "mechanism": "可燃煤气与空气在爆炸范围内混合并遇点火源时会爆炸。休风、封炉、阀门故障、密封破坏或氮气/蒸汽置换不足会增加混合风险。顶压和氮气参数只能形成代理提示；没有煤气浓度、氧含量、火源和检修状态时，系统不能自动判定真正爆炸条件。",
        "steps": [
            "任何现场煤气报警、密封破坏或检修事件立即服从煤气安全联锁和厂级事故预案。",
            "确认煤气浓度、氧含量、置换介质、阀位、密封、通风和点火源；缺一项不得由算法替代。",
            "按区域实施隔离、置换、检测和人员撤离，禁止带压、带煤气或未检测作业。",
            "休风/封炉期间持续保持规定密封与置换条件，记录每次检测和操作。",
            "只有安全专业确认气体检测合格、火源受控、设备隔离有效后才允许解除。",
        ],
    },
    {
        "id": "C11",
        "name": "长期休风/复风/封炉专项炉况报警",
        "chapters": [47, 48, 49, 50, 51, 52, 53, 54, 55, 56],
        "mechanism": "休风和封炉使炉内热量、料柱、压力与气氛从连续生产状态转入非稳态。休风前炉温不足、渣铁未出净、封炉料不合适或密封不良，会在复风时造成铁口通道难建、煤气分布异常、悬料、倒流和爆炸风险。",
        "steps": [
            "休风/封炉前确认炉况顺行、热量储备、渣铁出净、炉料方案、冷却和煤气系统条件。",
            "按短期、长期、倒流或封炉类型执行对应流程卡，明确阀位、密封、置换和坐料安全条件。",
            "休风期间持续检查炉体密封、煤气、冷却和温度，禁止把无数据误判为安全。",
            "复风前完成设备、人员、炉顶、煤气、铁口和热量联合确认；从规定初始风量/压力逐级恢复。",
            "复风后连续观察料线、顶压、压差、炉温和排放，出现异常立即停止升级并转对应B/C处置。",
        ],
    },
]


def _set_cell_shading(cell, fill: str) -> None:
    tc_pr = cell._tc.get_or_add_tcPr()
    shd = tc_pr.find(qn("w:shd"))
    if shd is None:
        shd = OxmlElement("w:shd")
        tc_pr.append(shd)
    shd.set(qn("w:fill"), fill)


def _set_cell_margins(cell, top: int = 80, start: int = 100, bottom: int = 80, end: int = 100) -> None:
    tc = cell._tc
    tc_pr = tc.get_or_add_tcPr()
    tc_mar = tc_pr.first_child_found_in("w:tcMar")
    if tc_mar is None:
        tc_mar = OxmlElement("w:tcMar")
        tc_pr.append(tc_mar)
    for edge, value in (("top", top), ("start", start), ("bottom", bottom), ("end", end)):
        node = tc_mar.find(qn(f"w:{edge}"))
        if node is None:
            node = OxmlElement(f"w:{edge}")
            tc_mar.append(node)
        node.set(qn("w:w"), str(value))
        node.set(qn("w:type"), "dxa")


def _set_repeat_table_header(row) -> None:
    tr_pr = row._tr.get_or_add_trPr()
    tbl_header = OxmlElement("w:tblHeader")
    tbl_header.set(qn("w:val"), "true")
    tr_pr.append(tbl_header)


def _format_run(run, *, size: float = 10.5, bold: bool = False, color: str | None = None) -> None:
    run.font.name = "SimSun"
    run._element.rPr.rFonts.set(qn("w:eastAsia"), "宋体")
    run.font.size = Pt(size)
    run.bold = bold
    if color:
        run.font.color.rgb = RGBColor.from_string(color)


def _format_paragraph(paragraph, *, size: float = 10.5, bold: bool = False, color: str | None = None) -> None:
    paragraph.paragraph_format.space_after = Pt(3)
    paragraph.paragraph_format.line_spacing = 1.15
    for run in paragraph.runs:
        _format_run(run, size=size, bold=bold, color=color)


def _add_labeled_paragraph(document: Document, label: str, text: str, *, color: str = "C00000") -> None:
    paragraph = document.add_paragraph()
    paragraph.paragraph_format.space_after = Pt(4)
    paragraph.paragraph_format.line_spacing = 1.2
    label_run = paragraph.add_run(label)
    _format_run(label_run, size=11, bold=True, color=color)
    text_run = paragraph.add_run(text)
    _format_run(text_run, size=10.5)


def _add_steps(document: Document, steps: list[str], *, color: str) -> None:
    heading = document.add_paragraph()
    heading_run = heading.add_run("【新增】干预处置流程")
    _format_run(heading_run, size=11, bold=True, color=color)
    heading.paragraph_format.space_after = Pt(2)
    for index, step in enumerate(steps, start=1):
        paragraph = document.add_paragraph()
        paragraph.paragraph_format.left_indent = Cm(0.35)
        paragraph.paragraph_format.first_line_indent = Cm(-0.35)
        paragraph.paragraph_format.space_after = Pt(2)
        run = paragraph.add_run(f"{index}. {step}")
        _format_run(run, size=10.5)


def _add_heat_batch_rate_criterion(document: Document, *, rule_id: str, color: str) -> None:
    """Add the operator's bold 30+30 minute burden-batch speed criterion."""
    paragraph = document.add_paragraph()
    paragraph.paragraph_format.space_before = Pt(2)
    paragraph.paragraph_format.space_after = Pt(5)
    paragraph.paragraph_format.line_spacing = 1.25
    label = "首要维护判据" if rule_id == "A2" else "首要风险判据"
    paragraph.add_run(f"【{label}·料速】")
    paragraph.add_run(HEAT_BATCH_RATE_CRITERION)
    for item in paragraph.runs:
        _format_run(item, size=10.5, bold=True, color=color)


def _prepend_heat_batch_rate_formula_items(document: Document) -> None:
    """Put the burden-speed precondition first in A2/B4/B5 formula cells."""
    matched: set[str] = set()
    for table in document.tables:
        for row in table.rows:
            for cell in row.cells:
                for paragraph in list(cell.paragraphs):
                    for rule_id, anchor in HEAT_BATCH_RATE_FORMULA_ANCHORS.items():
                        if rule_id in matched or anchor not in paragraph.text:
                            continue
                        item = paragraph.insert_paragraph_before()
                        item.paragraph_format.space_after = Pt(3)
                        label = "料速维护项" if rule_id == "A2" else "料速风险项"
                        item.add_run(f"【第一位·{label}（权重{HEAT_BATCH_RATE_WEIGHT}）】")
                        item.add_run(HEAT_BATCH_RATE_CRITERION)
                        for run in item.runs:
                            _format_run(run, size=9.5, bold=True, color=_rule_color(rule_id))
                        paragraph.text = HEAT_BATCH_RATE_WEIGHTED_FORMULAS[rule_id]
                        _format_paragraph(paragraph, size=9.5)
                        matched.add(rule_id)
    missing = sorted(set(HEAT_BATCH_RATE_FORMULA_ANCHORS) - matched)
    if missing:
        raise ValueError(f"未找到需要插入料速首项的公式单元格：{missing}")


def _fix_known_rule_cross_references(document: Document) -> None:
    """Correct the A2 hot/cold handoff from the source document in the revision."""
    old = "偏热或偏凉时分别进入B5/B6"
    new = "偏热或偏凉时分别进入B4/B5"
    replacements = 0
    paragraphs = list(document.paragraphs) + [
        paragraph
        for table in document.tables
        for row in table.rows
        for cell in row.cells
        for paragraph in cell.paragraphs
    ]
    for paragraph in paragraphs:
        for run in paragraph.runs:
            if old in run.text:
                run.text = run.text.replace(old, new)
                replacements += 1
    if replacements != 1:
        raise ValueError(f"A2 B4/B5交叉引用修订数量异常：{replacements}")


def _rule_color(rule_id: str) -> str:
    return {"A": "00875A", "B": "C67C00", "C": "C00000"}[rule_id[0]]


def _rule_fill(rule_id: str) -> str:
    return {"A": "D9EAD3", "B": "FCE5CD", "C": "F4CCCC"}[rule_id[0]]


def _chapter_text(chapter_ids: list[int]) -> str:
    return "；".join(f"第{chapter_id}章《{CHAPTERS[chapter_id]}》" for chapter_id in chapter_ids)


def validate_catalog() -> dict[str, object]:
    ids = [str(rule["id"]) for rule in RULES]
    if len(ids) != 33 or len(set(ids)) != 33:
        raise ValueError(f"ABC规则必须为33项且ID唯一，当前={len(ids)}，唯一={len(set(ids))}")
    expected_ids = [f"A{i}" for i in range(1, 10)] + [f"B{i}" for i in range(1, 14)] + [f"C{i}" for i in range(1, 12)]
    if ids != expected_ids:
        raise ValueError("ABC规则ID顺序或完整性不符合A1-A9/B1-B13/C1-C11")
    mapped: set[int] = set()
    for rule in RULES:
        chapters = [int(value) for value in rule["chapters"]]
        unknown = set(chapters) - set(CHAPTERS)
        if unknown:
            raise ValueError(f"{rule['id']}包含未知手册章节：{sorted(unknown)}")
        if not str(rule["mechanism"]).strip():
            raise ValueError(f"{rule['id']}缺少形成原理")
        steps = list(rule["steps"])
        if len(steps) < 3:
            raise ValueError(f"{rule['id']}干预处置流程少于3步")
        mapped.update(chapters)
    missing = sorted(set(CHAPTERS) - mapped)
    if missing:
        raise ValueError(f"见习高炉长64章存在未映射章节：{missing}")
    return {
        "requirement_id": REQ_ID,
        "rule_count": len(RULES),
        "chapter_count": len(CHAPTERS),
        "mapped_chapter_count": len(mapped),
        "unmapped_chapters": missing,
    }


def build_document(source_docx: Path, output_docx: Path) -> dict[str, object]:
    audit = validate_catalog()
    document = Document(source_docx)
    _fix_known_rule_cross_references(document)
    _prepend_heat_batch_rate_formula_items(document)

    section = document.add_section(WD_SECTION.NEW_PAGE)
    section.top_margin = Cm(1.8)
    section.bottom_margin = Cm(1.8)
    section.left_margin = Cm(2.0)
    section.right_margin = Cm(2.0)

    heading = document.add_heading("十二、" + REVISION_TITLE, level=1)
    _format_paragraph(heading, size=16, bold=True, color="1F4E78")

    note = document.add_paragraph()
    note.alignment = WD_ALIGN_PARAGRAPH.LEFT
    note.add_run("修订说明：")
    note.add_run(
        "本章以本文件A9、B13、C11共33项规则为主结构，将《最终版本见习高炉长_点位页面语义补充标注版》64个一级章节全部建立主/辅映射，并补充每项规则的形成原理与干预处置流程。"
        "A2、B4、B5原公式第一位新增权重20的料速项；其余原有权重统一按0.8比例压缩至合计80，保持各项相对比例不变，使总权重仍为100；其余规则公式、权重和阈值保持不变。"
        "新增内容用彩色标识。所有操作均为只读建议，必须服从现场规程、联锁、事故预案和值班负责人审批。"
    )
    _format_paragraph(note, size=10.5)
    if note.runs:
        _format_run(note.runs[0], size=10.5, bold=True, color="C00000")

    meta = document.add_table(rows=4, cols=2)
    meta.alignment = WD_TABLE_ALIGNMENT.CENTER
    meta.style = "Table Grid"
    meta_rows = [
        ("需求编号", REQ_ID),
        ("规则覆盖", "A类9项、B类13项、C类11项，共33项"),
        ("手册覆盖", "一级章节1—64全部纳入映射；第64章为筛选结论，不作为独立报警炉况"),
        ("安全边界", "本章不替代三规二制、联锁、事故预案、炉前/设备/煤气专业确认和审批"),
    ]
    for row, (label, value) in zip(meta.rows, meta_rows):
        row.cells[0].text = label
        row.cells[1].text = value
        _set_cell_shading(row.cells[0], "D9EAF7")
        for cell in row.cells:
            _set_cell_margins(cell)
            cell.vertical_alignment = WD_CELL_VERTICAL_ALIGNMENT.CENTER
            for paragraph in cell.paragraphs:
                _format_paragraph(paragraph, size=9.5, bold=cell is row.cells[0])

    document.add_heading("十二.一、64章到ABC33的映射口径", level=2)
    mapping_table = document.add_table(rows=1, cols=4)
    mapping_table.style = "Table Grid"
    mapping_table.alignment = WD_TABLE_ALIGNMENT.CENTER
    headers = ["手册章", "手册标题", "主对应规则", "辅助对应规则"]
    for cell, header in zip(mapping_table.rows[0].cells, headers):
        cell.text = header
        _set_cell_shading(cell, "1F4E78")
        for paragraph in cell.paragraphs:
            for run in paragraph.runs:
                _format_run(run, size=9, bold=True, color="FFFFFF")
    _set_repeat_table_header(mapping_table.rows[0])

    reverse: dict[int, list[str]] = defaultdict(list)
    for rule in RULES:
        for chapter in rule["chapters"]:
            reverse[int(chapter)].append(str(rule["id"]))
    for chapter_id in range(1, 65):
        row = mapping_table.add_row()
        mapped_rules = reverse[chapter_id]
        primary = mapped_rules[0]
        secondary = "、".join(mapped_rules[1:]) if len(mapped_rules) > 1 else "—"
        values = [str(chapter_id), CHAPTERS[chapter_id], primary, secondary]
        for cell, value in zip(row.cells, values):
            cell.text = value
            _set_cell_margins(cell, top=55, bottom=55)
            for paragraph in cell.paragraphs:
                _format_paragraph(paragraph, size=8.5)

    document.add_page_break()
    for module, module_title in (
        ("A", "十二.二、模块A：正常运行维护与优化形成原理及干预流程"),
        ("B", "十二.三、模块B：常见异常预警形成原理及干预流程"),
        ("C", "十二.四、模块C：专项安全炉况形成原理及干预流程"),
    ):
        module_heading = document.add_heading(module_title, level=2)
        _format_paragraph(module_heading, size=14, bold=True, color=_rule_color(module + "1"))
        for rule in [item for item in RULES if str(item["id"]).startswith(module)]:
            rule_id = str(rule["id"])
            rule_heading = document.add_heading(f"{rule_id} {rule['name']}", level=3)
            _format_paragraph(rule_heading, size=12.5, bold=True, color=_rule_color(rule_id))
            if rule_id in HEAT_BATCH_RATE_RULE_IDS:
                _add_heat_batch_rate_criterion(
                    document,
                    rule_id=rule_id,
                    color=_rule_color(rule_id),
                )
            p = document.add_paragraph()
            p.paragraph_format.space_after = Pt(4)
            label = p.add_run("对应见习高炉长章节：")
            _format_run(label, size=10, bold=True)
            value = p.add_run(_chapter_text(list(rule["chapters"])))
            _format_run(value, size=10)
            _add_labeled_paragraph(
                document,
                "【新增】形成原理：",
                str(rule["mechanism"]),
                color=_rule_color(rule_id),
            )
            _add_steps(document, list(rule["steps"]), color=_rule_color(rule_id))
            boundary = document.add_paragraph()
            boundary.paragraph_format.space_after = Pt(7)
            boundary.add_run("处置边界：")
            if module == "A":
                boundary.add_run("以维持和优化为主；出现B/C证据时停止普通优化并转入相应流程。")
            elif module == "B":
                boundary.add_run("属于趋势预警；必须复核数据与现场，任何定量调整均需工长审批。")
            else:
                boundary.add_run("属于高危专项入口；不得仅凭算法自动定论或自动关闭，必须按厂级预案人工确认。")
            _format_paragraph(boundary, size=9.5)

    document.add_heading("十二.五、使用与维护说明", level=2)
    final_points = [
        "本补充章中的‘形成原理’用于解释工艺因果，不等同于评分公式中的单项贡献。",
        "‘干预处置流程’给出先后关系和复核要求，不授予系统生产控制写权限。",
        "未接入的CO₂、H₂、煤气浓度、氧含量、炉壳颜色、铁口深度等必须显示为人工复核或缺失数据，不得补零。",
        "C类事件必须具有现场事件或第二类独立证据；单一传感器高值、单一复合因子或单一高分不得直接宣布严重事故成立。",
        "后续若修改公式、权重或阈值，应单独建立版本、变更原因、审批和回滚记录，不在本手册补充文本中静默修改。",
        "料批速度的前30分钟—后30分钟对比是高炉长现场复核判据，本次只补入工艺文档，尚未纳入ABC33自动评分公式。",
    ]
    for item in final_points:
        paragraph = document.add_paragraph(style=None)
        paragraph.paragraph_format.left_indent = Cm(0.35)
        paragraph.paragraph_format.first_line_indent = Cm(-0.35)
        run = paragraph.add_run("• " + item)
        _format_run(run, size=10.5)

    output_docx.parent.mkdir(parents=True, exist_ok=True)
    document.save(output_docx)
    audit.update(
        {
            "source_docx": str(source_docx),
            "output_docx": str(output_docx),
            "output_size": output_docx.stat().st_size,
        }
    )
    return audit


def write_mapping_json(output_json: Path) -> None:
    reverse: dict[int, list[str]] = defaultdict(list)
    for rule in RULES:
        for chapter_id in rule["chapters"]:
            reverse[int(chapter_id)].append(str(rule["id"]))
    payload = {
        "requirement_id": REQ_ID,
        "chapters": [
            {
                "chapter": chapter_id,
                "title": CHAPTERS[chapter_id],
                "primary_rule": reverse[chapter_id][0],
                "supporting_rules": reverse[chapter_id][1:],
            }
            for chapter_id in range(1, 65)
        ],
        "rules": RULES,
    }
    output_json.parent.mkdir(parents=True, exist_ok=True)
    output_json.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def write_audit_markdown(output_md: Path, source_docx: Path, handbook_docx: Path, output_docx: Path) -> None:
    reverse: dict[int, list[str]] = defaultdict(list)
    for rule in RULES:
        for chapter_id in rule["chapters"]:
            reverse[int(chapter_id)].append(str(rule["id"]))
    lines = [
        "# ABC33形成原理与干预处置流程：64章映射审计",
        "",
        f"- 需求编号：`{REQ_ID}`",
        f"- 主文档：`{source_docx}`",
        f"- 知识来源：`{handbook_docx}`",
        f"- 生成结果：`{output_docx}`",
        "- 覆盖结果：A类9项、B类13项、C类11项，共33项；见习高炉长一级章节1—64全部映射，未映射0章。",
        "- 修订边界：A2/B4/B5公式单元格新增第一位权重20的料速项；原有各项按0.8等比例压缩、合计80，使每条公式总权重仍为100；其余规则公式、权重和阈值保持原样；新增形成原理、处置流程、64章映射和安全边界。",
        f"- 现场补充判据：`{HEAT_BATCH_RATE_REQ_ID}`；料速判据同时位于A2/B4/B5原公式单元格第一位，以及补充章节的A2首要维护项、B4/B5首要风险项，全部加粗；料速项权重20，昨日均值为正常基线，MES 24 h均值为在线对照，正常差值不超过0.25大批/h或0.5小批/h，硬上限不超过0.5大批/h或1小批/h，连续2 h高出MES均值1大批/h触发提炉温处置。",
        "- 编号修正：修订版将A2系统用途中的‘偏热或偏凉分别进入B5/B6’更正为‘B4/B5’，不覆盖来源原件。",
        "",
        "## 映射表",
        "",
        "| 章 | 见习高炉长标题 | 主对应规则 | 辅助对应规则 |",
        "|---:|---|---|---|",
    ]
    for chapter_id in range(1, 65):
        rules = reverse[chapter_id]
        supporting = "、".join(rules[1:]) if len(rules) > 1 else "—"
        lines.append(f"| {chapter_id} | {CHAPTERS[chapter_id]} | {rules[0]} | {supporting} |")
    lines.extend(
        [
            "",
            "## 验收口径",
            "",
            "1. 生成的DOCX可由`python-docx`重新打开，且保留原文11个一级章节。",
            "2. 新增章节包含33个三级规则标题、33段“形成原理”和33套“干预处置流程”。",
            "3. 映射并集严格等于1—64，不能遗漏，也不能把第64章筛选结论当作独立报警。",
            "4. C类处置均明确人工确认、厂级预案和不可自动关闭边界。",
            "5. 未接入的现场项保持人工复核/缺失，不得补零或伪装为传感器证据。",
            "6. A2、B4、B5均包含全段加粗的料批速度前后30分钟对比判据，且明确7.5批/h参考、0.5批/h容差及上行/下行方向。",
            "",
        ]
    )
    output_md.parent.mkdir(parents=True, exist_ok=True)
    output_md.write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Append handbook-derived mechanisms and intervention flows to ABC33 DOCX.")
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--handbook", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--mapping-json", type=Path, required=True)
    parser.add_argument("--audit-json", type=Path, required=True)
    parser.add_argument("--audit-md", type=Path, required=True)
    args = parser.parse_args()

    if not args.source.exists():
        raise FileNotFoundError(args.source)
    audit = build_document(args.source, args.output)
    write_mapping_json(args.mapping_json)
    write_audit_markdown(args.audit_md, args.source, args.handbook, args.output)
    args.audit_json.parent.mkdir(parents=True, exist_ok=True)
    args.audit_json.write_text(json.dumps(audit, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(audit, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
