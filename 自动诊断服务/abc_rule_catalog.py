"""Server-side catalogue for the A9/B13/C11 furnace rule set.

The catalogue is intentionally not imported by the browser-facing code.  It is
the single semantic registry for rule identity, handbook guidance and the
controlled feature terms used by :mod:`abc_rule_engine`.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping


REQUIREMENT_ID = "REQ-ABC33-FORMULA-CALIBRATED-REPLAY-20260808"
CATALOG_VERSION = "abc33-catalog.v2.calibrated"


@dataclass(frozen=True)
class RuleSpec:
    rule_id: str
    category: str
    display_name: str
    direction: str
    terms: Mapping[str, float]
    primary_sensors: tuple[str, ...]
    primary_review: tuple[str, ...]
    expanded_review: tuple[str, ...]
    manual_review: tuple[str, ...]
    intervention_order: tuple[str, ...]
    observation_window: str
    approval: str
    principle: str
    source_refs: tuple[str, ...]
    safety_event: bool = False


def _r(rule_id: str, category: str, name: str, direction: str, terms: Mapping[str, float], sensors: tuple[str, ...], *, event: bool = False) -> RuleSpec:
    return RuleSpec(
        rule_id,
        category,
        name,
        direction,
        terms,
        sensors,
        sensors[:5],
        sensors[5:],
        ("现场确认风口、铁口、料面和仪表状态",),
        ("先确认数据有效性", "按手册顺序处置", "观察后复核并记录工长意见"),
        "普通趋势连续15–30分钟；安全事件立即进入专项处置",
        "只读建议；任何工艺调整须值班工长批准",
        "依据手册中‘调节—观察—复核’闭环，结合关键传感器趋势判断炉况。",
        ("见习高炉长手册·第17章判断框架", "见习高炉长手册·第36章调节—观察—复核"),
        event,
    )


RULES: tuple[RuleSpec, ...] = (
    _r("A1", "A", "正常顺行维护", "maintenance", {"TopPressRange": 12, "DP_total": 12, "Q_blast": 12, "P_blast": 10, "TopTempRange": 12, "LineBias": 10, "HeatProxy": 12, "CoolingRisk": 12}, ("P_top", "DP_total", "Q_blast", "P_blast", "T_top_A", "T_top_B", "T_top_C", "T_top_D", "L")),
    _r("A2", "A", "热制度维护", "maintenance", {"T_taphole_1": 30, "slope30_T_taphole_1": 15, "slope30_T_top": 15, "GasUtilDev": 10, "PCI_rate": 10, "T_blast": 10, "TFT": 10}, ("T_taphole_1", "T_top_A", "T_top_B", "T_blast", "TFT", "GasUtil", "PCI_rate")),
    _r("A3", "A", "煤气流平衡维护", "maintenance", {"TopTempRange": 20, "TopPressRange": 15, "StaticPressRange": 15, "GasUtilDev": 15, "BodyHotRisk": 15, "BodyColdRisk": 10, "BlastEnergy": 10}, ("T_top_A", "T_top_B", "T_top_C", "T_top_D", "P_top", "GasUtil", "T_body_L10_A")),
    _r("A4", "A", "送风稳定维护", "maintenance", {"Q_blast": 25, "P_blast": 20, "DPHigh": 20, "PIBad": 15, "z15std_Q_blast": 10, "z15std_P_blast": 10}, ("Q_blast", "P_blast", "DP_total", "PI", "P_blast_cold")),
    _r("A5", "A", "喷煤—富氧—风温维护", "maintenance", {"PCI_rate": 18, "O2_rate": 14, "Q_O2": 14, "T_blast": 14, "TFT": 14, "DPHigh": 14, "PIBad": 12}, ("PCI_rate", "PCI_set", "O2_rate", "Q_O2", "T_blast", "TFT", "DP_total", "PI")),
    _r("A6", "A", "装料维护", "maintenance", {"LineBias": 25, "LineLoss": 20, "BurdenStall": 20, "BurdenSlip": 15, "z15std_Hopper_weight": 10, "z15std_L": 10}, ("L", "L_south", "L_north", "Hopper_weight", "Hopper_weight_set")),
    _r("A7", "A", "渣铁维护", "maintenance", {"DrainProxy": 35, "T_taphole_1": 25, "DP_lower": 15, "PIBad": 15, "z15std_T_taphole_1": 10}, ("T_taphole_1", "T_taphole_2", "DP_lower", "PI")),
    _r("A8", "A", "冷却与炉体寿命维护", "maintenance", {"CoolingRisk": 35, "BodyHotRisk": 25, "BodyTempRange": 15, "TopTempRange": 15, "TopPressRange": 10}, ("T_body_L10_A", "T_body_L10_B", "T_top_A", "T_top_B", "P_top")),
    _r("A9", "A", "经济安全维护", "maintenance", {"DPHigh": 20, "PIBad": 15, "GasUtilDev": 15, "DrainProxy": 15, "CoolingRisk": 10, "low60_Ttap": 10, "EconomicIntensityEdge": 15}, ("DP_total", "PI", "GasUtil", "T_taphole_1", "T_taphole_2", "CoolingRisk", "Q_blast", "O2_rate", "PCI_rate")),
    _r("B1", "B", "管道风险", "risk", {"SpikeTopP_15": 20, "slope30_T_top": 18, "TopTempRange": 15, "TopPressRange": 15, "z15std_P_blast": 12, "GasUtilDev": 10, "BurdenSlip": 10}, ("P_top", "T_top_A", "T_top_B", "T_top_C", "T_top_D", "GasUtil", "L")),
    _r("B2", "B", "悬料风险", "risk", {"BurdenStall": 30, "P_blast": 20, "Q_blast": 15, "DPHigh": 15, "P_top": 10, "PIBad": 10}, ("L", "P_blast_cold", "P_blast", "Q_blast", "DP_total", "P_top", "PI")),
    _r("B3", "B", "崩料/滑料风险", "risk", {"BurdenSlip": 30, "SlipFreq60": 20, "z15std_P_blast": 15, "z15std_Q_blast": 15, "DPHigh": 15, "slope30_T_taphole_1": 10, "TopTempRange": 10}, ("L", "L_south", "L_north", "P_blast", "Q_blast", "DP_total", "T_taphole_1")),
    _r("B4", "B", "热制度上行风险", "risk", {"T_taphole_1": 25, "slope30_T_top": 15, "AirAcceptBad": 15, "DP_upper": 10, "TopTempRange": 10, "T_blast": 15, "PCI_rate": 10}, ("T_taphole_1", "T_top_A", "T_top_B", "T_blast", "PCI_rate", "Q_O2", "PI")),
    _r("B5", "B", "热制度下行风险", "risk", {"T_taphole_1": 25, "slope30_T_top": 15, "P_blast": 15, "Q_blast": 10, "GasUtilDev": 10, "T_blast": 15, "PCI_rate": 10}, ("T_taphole_1", "T_top_A", "T_top_B", "P_blast_cold", "P_blast", "Q_blast", "GasUtil", "PCI_rate")),
    _r("B6", "B", "低料线风险", "risk", {"LineLoss": 35, "LineLossDuration": 15, "slope30_T_top": 15, "TopTempRange": 10, "BodyHotRisk": 10, "LineBias": 10, "z15std_Hopper_weight": 5}, ("L", "L_south", "L_north", "T_top_A", "T_top_B", "Hopper_weight")),
    _r("B7", "B", "边缘煤气流过强风险", "risk", {"BodyHotRisk": 25, "TopTempRange": 20, "TopPressRange": 15, "StaticPressRange": 15, "GasUtilDev": 10, "PI": 10, "BlastEnergy": 5}, ("T_body_L10_A", "T_body_L10_B", "T_top_A", "T_top_B", "P_top", "PI")),
    _r("B8", "B", "中心煤气流过强风险", "risk", {"BodyColdRisk": 25, "DPHigh": 20, "P_blast": 15, "PIBad": 15, "slope30_T_top": 10, "StaticPressRange": 10, "BlastEnergy": 5}, ("T_body_L10_A", "T_body_L10_B", "DP_total", "P_blast", "PI", "T_top_A")),
    _r("B9", "B", "装料偏布风险", "risk", {"LineBias": 25, "TopTempRange": 20, "TopPressRange": 15, "BodyTempRange": 15, "z15std_Hopper_weight": 15, "LineBiasDuration": 10}, ("L", "L_south", "L_north", "Hopper_weight", "T_top_A", "T_top_B")),
    _r("B10", "B", "透气性恶化风险", "risk", {"DPHigh": 25, "PIBad": 20, "AirAcceptBad": 20, "DP_upper": 15, "BurdenStall": 10, "DrainProxy": 10}, ("DP_total", "DP_upper", "DP_lower", "PI", "Q_blast", "P_blast")),
    _r("B11", "B", "炉墙结厚/支架风险", "risk", {"BodyColdRisk": 30, "BodyColdDuration": 20, "DPHigh": 15, "PIBad": 15, "LineBias": 10, "LineLoss": 10}, ("T_body_L10_A", "T_body_L10_B", "DP_total", "PI", "L")),
    _r("B12", "B", "冷却水漏冷风险", "risk", {"CoolingRisk": 30, "T_taphole_1": 20, "slope30_T_top": 15, "BodyTempRange": 15, "slope30_T_taphole_1": 10, "CoolingFlowLow": 10}, ("CoolingRisk", "T_taphole_1", "T_top_A", "T_top_B", "T_body_L10_A")),
    _r("B13", "B", "排渣出铁不良风险", "risk", {"DrainProxy": 35, "T_taphole_1": 20, "DP_lower": 15, "PIBad": 15, "BurdenStall": 10, "z15std_Q_blast": 5}, ("T_taphole_1", "T_taphole_2", "DP_lower", "PI", "Q_blast")),
    _r("C1", "C", "炉缸冻结报警", "risk", {"T_taphole_1": 25, "slope30_T_top": 20, "DrainProxy": 15, "AirAcceptBad": 15, "BurdenSlip": 10, "CoolingRisk": 10, "GasUtilDev": 5}, ("T_taphole_1", "T_top_A", "T_top_B", "DP_lower", "PI", "CoolingRisk"), event=True),
    _r("C2", "C", "严重管道/崩滑料复合报警", "risk", {"B1_score": 40, "B3_score": 40, "SpikeTopP_15": 10, "BurdenSlip": 10}, ("P_top", "T_top_A", "T_top_B", "L", "DP_total"), event=True),
    _r("C3", "C", "炉缸堆积报警", "risk", {"DrainProxy": 30, "DP_lower": 25, "PIBad": 15, "AirAcceptBad": 15, "T_taphole_1": 10, "CoolingRisk": 5}, ("T_taphole_1", "DP_lower", "PI", "CoolingRisk"), event=True),
    _r("C4", "C", "冷却系统超负荷报警", "risk", {"CoolingRisk": 30, "BodyHotRisk": 25, "BodyTempRange": 20, "TopTempRange": 15, "TopPressRange": 10}, ("CoolingRisk", "T_body_L10_A", "T_body_L10_B", "T_top_A", "T_top_B", "P_top"), event=True),
    _r("C5", "C", "烧穿风险报警", "risk", {"BodyHotRisk": 30, "CoolingRisk": 25, "BodyTempRange": 15, "slope30_BodyTemp": 15, "DrainProxy": 10, "TopPressRange": 5}, ("T_body_L10_A", "T_body_L10_B", "CoolingRisk", "P_top", "T_taphole_1"), event=True),
    _r("C6", "C", "风口异常报警", "risk", {"CoolingRisk": 25, "z15std_Q_blast": 20, "z15std_P_blast": 20, "DPHigh": 15, "T_taphole_1": 10, "BodyHotRisk": 10}, ("Q_blast", "P_blast", "P_blast_cold", "DP_total", "CoolingRisk"), event=True),
    _r("C7", "C", "炉壳热点报警", "risk", {"BodyHotRisk": 30, "CoolingRisk": 25, "BodyTempRange": 15, "TopTempRange": 15, "TopPressRange": 10, "slope30_BodyTemp": 5}, ("T_body_L10_A", "T_body_L10_B", "CoolingRisk", "T_top_A", "T_top_B", "P_top"), event=True),
    _r("C8", "C", "炉衬脱落报警", "risk", {"BodyTempRange": 25, "z15std_DP_total": 20, "z15std_L": 15, "TopTempRange": 15, "slope30_T_taphole_1": 15, "CoolingRisk": 10}, ("T_body_L10_A", "T_body_L10_B", "DP_total", "L", "T_taphole_1"), event=True),
    _r("C9", "C", "鼓风机停机/倒流风险报警", "risk", {"Q_blast": 35, "P_blast": 20, "z15std_P_top": 15, "TopPressRange": 10, "P_blast_cold": 10, "Q_N2": 10}, ("Q_blast", "P_blast_cold", "P_blast", "P_top"), event=True),
    _r("C10", "C", "煤气爆炸代理风险报警", "risk", {"Q_N2": 30, "P_N2": 25, "TopPressRange": 15, "z15std_P_top": 15, "P_top": 15}, ("Q_N2", "P_N2", "P_top", "P_top_gas_A", "P_top_gas_B"), event=True),
    _r("C11", "C", "复风重启风险报警", "risk", {"T_taphole_1": 20, "DrainProxy": 20, "BurdenSlip": 15, "CoolingRisk": 15, "AirAcceptBad": 15, "z15std_P_top": 15}, ("T_taphole_1", "DP_lower", "L", "CoolingRisk", "P_top"), event=True),
)

# The source document defines every rule over already-normalized 0..1 risk
# factors.  Keep the operator metadata above, but replace the legacy physical-
# unit term maps atomically so a raw pressure/temperature can never be scored
# with the generic 0..1 threshold.
_CALIBRATED_TERMS: dict[str, dict[str, float]] = {
    "A1":{"std15_P_top":12,"std15_DP_total":12,"std15_Q_blast":12,"std15_P_blast":10,"TopTempRange":12,"TopPressRange":8,"LineBias":10,"HeatProxy":12,"CoolingRisk":12},
    "A2":{"abs60_Ttap":30,"absSlope_Ttap":15,"absSlope_Ttop":15,"GasUtilDev":10,"abs60_PCI":10,"abs60_Tblast":10,"abs60_TFT":10},
    "A3":{"TopTempRange":20,"TopPressRange":15,"StaticPressRange":15,"GasUtilDev":15,"BodyHotRisk":15,"BodyColdRisk":10,"abs60_BlastEnergy":10},
    "A4":{"abs60_Qblast":25,"abs60_Pblast":20,"DPHigh":20,"PIBad":15,"std15_Q_blast":10,"std15_P_blast":10},
    "A5":{"abs60_PCI":18,"abs60_O2rate":14,"abs60_QO2":14,"abs60_Tblast":14,"abs60_TFT":14,"DPHigh":14,"PIBad":12},
    "A6":{"LineBias":25,"LineLoss":20,"BurdenStall":20,"BurdenSlip":15,"std15_Hopper_weight":10,"std15_L":10},
    "A7":{"DrainProxy":35,"low60_Ttap":25,"high60_DPlower":15,"PIBad":15,"std15_Ttap":10},
    "A8":{"CoolingRisk":35,"BodyHotRisk":25,"BodyTempRange":15,"TopTempRange":15,"TopPressRange":10},
    "A9":{"DPHigh":20,"PIBad":15,"GasUtilDev":15,"DrainProxy":15,"CoolingRisk":10,"low60_Ttap":10,"EconomicIntensityEdge":15},
    "B1":{"SpikeTopP15":20,"highSlope_Ttop":18,"TopTempRange":15,"TopPressRange":15,"std15_pressure_max":12,"GasUtilDev":10,"BurdenSlip":10},
    "B2":{"BurdenStall":30,"high60_Pblast":20,"low60_Qblast":15,"DPHigh":15,"low60_Ptop":10,"PIBad":10},
    "B3":{"BurdenSlip":30,"SlipFreq60":20,"std15_blast_top_max":15,"std15_DP_total":15,"lowSlope_Ttap":10,"TopTempRange":10},
    "B4":{"high60_Ttap":25,"highSlope_Ttop":15,"AirAcceptBad":15,"high60_DPupper":10,"TopTempRange":10,"high60_heat_input":15,"low60_PI":10},
    "B5":{"low60_Ttap":25,"lowSlope_Ttop":15,"low60_Pblast":15,"high60_Qblast":10,"GasUtilDev":10,"low60_heat_input":15,"BurdenSlip":10},
    "B6":{"LineLoss":35,"LineLossDuration":15,"highSlope_Ttop":15,"TopTempRange":10,"BodyHotRisk":10,"LineBias":10,"std15_Hopper_weight":5},
    "B7":{"BodyHotRisk":25,"TopTempRange":20,"TopPressRange":15,"StaticPressRange":15,"GasUtilDev":10,"high60_PI":10,"high60_BlastEnergy":5},
    "B8":{"BodyColdRisk":25,"DPHigh":20,"high60_Pblast":15,"low60_PI":15,"lowSlope_Ttop":10,"StaticPressRange":10,"high60_BlastEnergy":5},
    "B9":{"LineBias":25,"TopTempRange":20,"TopPressRange":15,"BodyTempRange":15,"std15_Hopper_weight":15,"LineBiasDuration":10},
    "B10":{"DPHigh":25,"PIBad":20,"AirAcceptBad":20,"DPDistributionBad":15,"BurdenStall":10,"DrainProxy":10},
    "B11":{"BodyColdRisk":30,"BodyColdDuration":20,"DPHigh":15,"PIBad":15,"LineBias":10,"LineLoss":10},
    "B12":{"CoolingRisk":30,"low60_Ttap":20,"lowSlope_Ttop":15,"BodyTempRange":15,"lowSlope_Ttap":10,"CoolingFlowLow":10},
    "B13":{"DrainProxy":35,"low60_Ttap":20,"high60_DPlower":15,"PIBad":15,"BurdenStall":10,"std15_Q_blast":5},
    "C1":{"low60_Ttap":25,"lowSlope_Ttop":20,"DrainProxy":15,"AirAcceptBad":15,"BurdenSlip":10,"CoolingRisk":10,"GasUtilDev":5},
    "C2":{"C2CompositeGate":100},
    "C3":{"DrainProxy":30,"high60_DPlower":25,"PIBad":15,"AirAcceptBad":15,"low60_Ttap":10,"CoolingRisk":5},
    "C4":{"CoolingRisk":30,"BodyHotRisk":25,"BodyTempRange":20,"TopTempRange":15,"TopPressRange":10},
    "C5":{"BodyHotRisk":30,"CoolingRisk":25,"BodyTempRange":15,"slopeBodyMax":15,"DrainProxy":10,"TopPressRange":5},
    "C6":{"CoolingRisk":25,"std15_Q_blast":20,"std15_P_blast":20,"DPHigh":15,"low60_Ttap":10,"BodyHotRisk":10},
    "C7":{"BodyHotRisk":30,"CoolingRisk":25,"BodyTempRange":15,"TopTempRange":15,"TopPressRange":10,"slopeBodyMax":5},
    "C8":{"BodyTempRange":25,"std15_DP_total":20,"std15_L":15,"TopTempRange":15,"lowSlope_Ttap":15,"CoolingRisk":10},
    "C9":{"low60_Qblast_severe":35,"low60_Pblast_severe":20,"std15_P_top":15,"TopPressRange":10,"low60_Pcold_severe":10,"low60_QN2":10},
    "C10":{"low60_QN2":30,"low60_PN2":25,"TopPressRange":15,"std15_P_top":15,"abs60_Ptop":15},
    "C11":{"low60_Ttap":20,"DrainProxy":20,"BurdenSlip":15,"CoolingRisk":15,"AirAcceptBad":15,"std15_P_top":15},
}
RULES = tuple(RuleSpec(**{**rule.__dict__, "terms": _CALIBRATED_TERMS[rule.rule_id]}) for rule in RULES)


RULE_BY_ID = {rule.rule_id: rule for rule in RULES}


def validate_catalog() -> None:
    expected = {"A": 9, "B": 13, "C": 11}
    actual = {category: sum(rule.category == category for rule in RULES) for category in expected}
    if actual != expected or len(RULE_BY_ID) != 33:
        raise RuntimeError(f"ABC rule catalogue must contain A9/B13/C11, got {actual}")


validate_catalog()
