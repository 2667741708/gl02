"""Protected Chinese process semantics for ABC33 formula terms.

This module is server-side/admin-only. Production operator serializers must not
include these internal term names, thresholds, weights or contributions.
"""
from __future__ import annotations

from typing import Any


VARIABLES: dict[str, tuple[str, str]] = {
    "BlastEnergy": ("鼓风综合能量代理", "由送风压力、流量和温度反映鼓风输入强度"),
    "DPlower": ("下部压差", "高炉下部料柱阻力"),
    "DPupper": ("上部压差", "高炉上部料柱阻力"),
    "DP_total": ("全炉压差", "高炉整体料柱阻力"),
    "Hopper_weight": ("料斗重量", "装料批次与下料稳定性"),
    "L": ("综合料线", "炉内料面位置"),
    "O2rate": ("富氧率", "鼓风中的富氧比例"),
    "PCI": ("实际喷煤速率", "现场检测到的瞬时每小时喷煤速率，不等同累计喷煤量或喷煤设定"),
    "P_N2": ("氮气压力", "氮气系统压力保障状态"),
    "P_blast": ("热风压力", "进入高炉前热风侧压力"),
    "P_top": ("综合顶压", "炉顶煤气压力"),
    "Pcold": ("冷风压力", "鼓风机至热风系统前的冷风压力"),
    "Q_N2": ("氮气流量", "氮气系统供给流量"),
    "QO2": ("富氧流量", "送风系统补充氧气流量"),
    "Q_blast": ("冷风流量", "送入热风炉前的鼓风体积流量"),
    "Tblast": ("热风温度", "进入高炉的热风温度"),
    "TFT": ("理论燃烧温度", "风口前理论燃烧温度"),
    "Ttap": ("两铁口温度均值", "1号与2号出铁口温度按同一分钟对齐后的均值"),
    "Ttop": ("四点顶温综合值", "炉顶A/B/C/D四点温度同分钟均值"),
}


COMPOSITES: dict[str, dict[str, Any]] = {
    "AirAcceptBad": {"label": "送风接受恶化", "meaning": "热风压力升高、冷风流量降低、压差升高及风量波动共同反映炉料接受风量能力变差。"},
    "BodyColdDuration": {"label": "炉体低温持续风险", "meaning": "炉体测温低于正常状态并持续一定时间。"},
    "BodyColdRisk": {"label": "炉体低温风险", "meaning": "炉体多层多方位温度相对30日基线偏低或继续下降。"},
    "BodyHotRisk": {"label": "炉体高温风险", "meaning": "炉体多层多方位温度相对30日基线偏高或继续上升。"},
    "BodyTempRange": {"label": "炉体温度截面离散风险", "meaning": "同一时刻炉体测温点最大值与最小值差异过大。"},
    "BurdenSlip": {"label": "崩滑料代理", "meaning": "料线突变、料线波动、顶压波动与压差波动共同支持崩滑料风险。"},
    "BurdenStall": {"label": "悬料代理", "meaning": "料线停滞并伴随送风压力、压差和风量异常，反映下料不畅。"},
    "C2CompositeGate": {"label": "严重管道—崩滑料复合门", "meaning": "只有管道风险和崩滑料风险同时具备足够证据时才形成复合报警。"},
    "CoolingFlowLow": {"label": "冷却水流量不足", "meaning": "软水流量或高压水流量低于各自30日正常基线。"},
    "CoolingRisk": {"label": "冷却系统风险", "meaning": "软水/高压水/中压水流量压力下降或膨胀罐液位异常的组合风险。"},
    "DPDistributionBad": {"label": "上下部压差分配异常", "meaning": "上部与下部压差相对各自基线的偏离方向或幅度失衡。"},
    "DPHigh": {"label": "压差升高风险", "meaning": "全炉、上部和下部压差相对30日基线偏高的综合风险。"},
    "DrainProxy": {"label": "排渣出铁不良代理", "meaning": "铁口温度偏低、下部压差偏高、透气性异常和下料停滞共同反映渣铁排放困难。"},
    "EconomicIntensityEdge": {"label": "经济强化边界", "meaning": "实际风量、富氧率和实际喷煤速率偏高，并同时接近压差、透气性、利用率、排渣或冷却约束。"},
    "GasUtilDev": {"label": "煤气利用率下降", "meaning": "煤气利用率相对30日基线显著偏低。"},
    "HeatProxy": {"label": "热制度偏离代理", "meaning": "铁口温度、铁口温度趋势、综合顶温趋势或理论燃烧温度偏离正常基线。"},
    "LineBias": {"label": "南北料线偏差", "meaning": "南、北料线差值增大，反映料面偏斜。"},
    "LineBiasDuration": {"label": "料线偏差持续风险", "meaning": "南北料线偏差持续超过观察窗口。"},
    "LineLoss": {"label": "低料线偏离", "meaning": "当前料线相对现场批准的正常料线发生不利偏离。"},
    "LineLossDuration": {"label": "低料线持续风险", "meaning": "低料线状态持续超过观察窗口。"},
    "PIBad": {"label": "透气性异常", "meaning": "透气性指数偏离30日正常水平或短时波动显著增大。"},
    "SlipFreq60": {"label": "60分钟崩滑料频次", "meaning": "最近60分钟料线突变次数。"},
    "SpikeTopP15": {"label": "15分钟顶压尖峰", "meaning": "最近15分钟综合顶压极差相对自身30日IQR异常增大。"},
    "StaticPressRange": {"label": "炉体静压截面离散风险", "meaning": "同层各方位炉体静压最大值与最小值差异过大。"},
    "TopPressRange": {"label": "四点顶压离散风险", "meaning": "炉顶A/B/C/D四点压力在同一分钟的极差异常增大。"},
    "TopTempRange": {"label": "四点顶温离散风险", "meaning": "炉顶A/B/C/D四点温度在同一分钟的极差异常增大。"},
    "slopeBodyMax": {"label": "炉体温度最大上升趋势", "meaning": "炉体多点温度中最显著的30分钟上升趋势。"},
    "std15_blast_top_max": {"label": "送风—顶压最大短时波动", "meaning": "热风压力、冷风流量和综合顶压中最大的15分钟标准差风险。"},
    "std15_pressure_max": {"label": "压力制度最大短时波动", "meaning": "热风压力、全炉压差和透气性指数中最大的15分钟标准差风险。"},
    "high60_heat_input": {"label": "热输入升高", "meaning": "热风温度、实际喷煤速率、富氧流量或理论燃烧温度相对基线升高。"},
    "low60_heat_input": {"label": "热输入下降", "meaning": "热风温度、实际喷煤速率、富氧流量或理论燃烧温度相对基线降低。"},
}


def term_semantics(term: str) -> dict[str, str]:
    """Return a stable admin-facing physical explanation for one formula term."""
    if term in COMPOSITES:
        item = COMPOSITES[term]
        return {"label": str(item["label"]), "meaning": str(item["meaning"])}
    patterns = (
        ("std15_", "15分钟波动", "最近15分钟标准差相对30日IQR增大"),
        ("abs60_", "60分钟绝对偏离", "最近60分钟均值偏离30日中位数，不区分升降方向"),
        ("high60_", "60分钟偏高", "最近60分钟均值高于30日中位数"),
        ("low60_", "60分钟偏低", "最近60分钟均值低于30日中位数"),
        ("absSlope_", "30分钟趋势绝对偏离", "最近30分钟变化斜率异常，不区分升降方向"),
        ("highSlope_", "30分钟上升趋势", "最近30分钟呈异常上升趋势"),
        ("lowSlope_", "30分钟下降趋势", "最近30分钟呈异常下降趋势"),
    )
    for prefix, label_prefix, meaning_prefix in patterns:
        if term.startswith(prefix):
            key = term[len(prefix):]
            if key.endswith("_severe"):
                key = key[:-7]
                label_prefix = "严重" + label_prefix
            variable = VARIABLES.get(key, (key, key))
            return {
                "label": f"{variable[0]}{label_prefix}",
                "meaning": f"{variable[1]}；{meaning_prefix}，并转换为0–1风险因子。",
            }
    return {"label": term, "meaning": "受控规则因子；需在后台结合来源变量和计算可用性复核。"}

