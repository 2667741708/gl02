"""Generate the auditable legacy-8 and ABC33 furnace-rule formula handbook.

The report is deterministic and contains no credentials or live production data.
Legacy-eight formulas are reconstructed from the retained threshold/weight YAML;
ABC33 formulas are read from the controlled Python catalogue and factor audit.
"""
from __future__ import annotations

import argparse
from datetime import date
from pathlib import Path
import sys
from typing import Any

import yaml


REQUIREMENT_ID = "REQ-FURNACE-RULE-FORMULA-HANDBOOK-20260814"


LEGACY_META: dict[str, dict[str, Any]] = {
    "normal": {
        "name": "正常顺行",
        "target": "当前炉况是否稳定顺行（维护分，越高越正常）",
        "terms": {
            "stable_top_pressure": ("g_N(zstd_P_top; 1.25)", "综合顶压短时稳定性"),
            "stable_delta_pressure": ("g_N(zstd_DP_total; 1.25)", "全炉压差短时稳定性"),
            "stable_permeability": ("g_N(zstd_PI; 1.25)", "透气性指数短时稳定性"),
            "stable_blast_pressure": ("g_N(zstd_P_blast; 1.25)", "热风压力短时稳定性"),
            "stable_top_temp_disp": ("g_N(DispTop_15; 0.28)", "四点顶温15分钟离散稳定性"),
            "stable_body_temperature": ("g_N(BodyTempRobust; 1.25)", "炉体温度三段稳健聚合稳定性"),
            "balanced_body_circumference": ("g_N(BodyCircumferenceRobust; 0.38)", "炉体十层圆周温差稳健聚合"),
            "stable_material_line": ("g_N(L_diff_NS; 0.80)", "南北料线差稳定性"),
        },
        "notes": [
            "历史文档记录炉体温度采用三段P75、圆周不均采用十层P80，以降低单点噪声支配。",
            "最高异常分大于60时，历史合同还执行 S_normal=min(S_normal,100-max_abnormal_score)。",
        ],
    },
    "lowline": {
        "name": "低料线",
        "target": "料面低于正常位置并持续或伴随顶温/炉体响应",
        "terms": {
            "low_line_depth": ("g_H(DeltaL; 0.5, 3.0)", "低料线深度"),
            "low_line_duration": ("g_H(duration_min; 5, 30)", "低料线持续时间"),
            "top_temp_rising": ("g_H(top_temp_slope; 0.1, 0.5)", "顶温上升趋势"),
            "upper_body_temperature_rising": ("g_H(z_upper_body; 0.8, 1.5)", "炉身上部温度升高"),
            "north_south_level_diff": ("g_H(abs(L_south-L_north); 0.25, 0.8)", "南北料线差"),
            "charging_fault": ("I(charging_fault)", "上料/装料故障二值证据"),
        },
    },
    "edge": {
        "name": "边缘煤气流发展",
        "target": "炉墙热负荷、热点方位和顶温离散支持边缘煤气流增强",
        "terms": {
            "body_upper_heat_load": ("g_H(z_body_upper; 0.8, 1.5)", "炉体上部热负荷"),
            "body_middle_lower_heat_load": ("g_H(z_body_middle_lower; 0.8, 1.5)", "炉体中下部热负荷"),
            "top_temp_rising": ("g_H(top_temp_slope; 0.1, 0.5)", "顶温上升趋势"),
            "hot_sector_bias": ("g_H(hot_sector_bias; 15, 60)", "圆周热点方位偏差"),
            "top_temp_dispersion": ("g_H(top_temp_dispersion; 0.15, 0.45)", "四点顶温离散"),
            "high_permeability": ("g_H(z_PI; 0.8, 1.5)", "透气性偏高"),
            "low_gas_utilization": ("g_L(z_GasUtil; -0.5, -1.0)", "煤气利用率偏低"),
        },
    },
    "center": {
        "name": "中心煤气流过强/中心过吹",
        "target": "低炉墙温度、压差和风压响应支持中心流增强",
        "terms": {
            "low_body_wall_temperature": ("g_L(z_body_wall; -0.8, -1.5)", "炉墙温度偏低"),
            "high_total_delta_p": ("g_H(z_DP_total; 0.8, 1.5)", "全炉压差偏高"),
            "high_upper_delta_p": ("g_H(z_DP_upper; 0.8, 1.5)", "上部压差偏高"),
            "high_blast_pressure": ("g_H(z_P_blast; 0.8, 1.5)", "热风压力偏高"),
            "low_permeability": ("g_L(z_PI; -0.8, -1.5)", "透气性偏低"),
            "low_top_temperature": ("g_L(z_T_top; -0.1, -0.5)", "综合顶温偏低"),
            "static_pressure_unbalanced": ("g_H(static_pressure_range; 8, 25)", "炉体静压力圆周不均"),
        },
    },
    "channel": {
        "name": "管道行程",
        "target": "顶压尖峰、压力振荡和局部热点跳变支持管道形成",
        "terms": {
            "top_pressure_spike_freq": ("g_H(spike_count_15; 1, 10)", "顶压尖峰频次"),
            "pressure_oscillation": ("g_H(pressure_oscillation; 1.0, 3.0)", "压力制度振荡"),
            "hot_spot_jump": ("g_H(hot_spot_jump; 0.8, 1.5)", "炉体局部热点跳变"),
            "top_temp_dispersion": ("g_H(top_temp_dispersion; 0.3, 0.8)", "四点顶温离散"),
            "probe_abnormal": ("I(probe_abnormal)", "探尺/料线异常二值证据"),
            "low_gas_utilization": ("g_L(z_GasUtil; -0.5, -1.0)", "煤气利用率偏低"),
        },
    },
    "cold": {
        "name": "热制度下行（炉凉）",
        "target": "当前热状态偏低，而不是未来风险概率",
        "terms": {
            "top_temp_down_trend": ("g_L(top_temp_slope; -0.1, -0.5)", "综合顶温下降趋势"),
            "low_body_temperature": ("g_L(z_body_temperature; -0.8, -1.5)", "炉体温度偏低"),
            "low_taphole_temp_proxy": ("g_L(z_T_taphole; -0.8, -1.5)", "出铁口温度代理偏低"),
            "low_blast_pressure": ("g_L(z_P_blast; -0.8, -1.5)", "热风压力偏低"),
            "high_permeability": ("g_H(z_PI; 0.8, 1.5)", "透气性偏高"),
            "low_gas_utilization": ("g_L(z_GasUtil; -0.5, -1.0)", "煤气利用率偏低"),
            "operation_heat_reduction": ("g_L(z_heat_operation; -0.5, -1.2)", "操作热输入降低"),
        },
    },
    "hot": {
        "name": "热制度上行（炉热）",
        "target": "当前热状态偏高，而不是未来风险概率",
        "terms": {
            "top_temp_rising": ("g_H(top_temp_slope; 0.1, 0.6)", "综合顶温上升趋势"),
            "high_body_temperature": ("g_H(z_body_temperature; 0.8, 1.5)", "炉体温度偏高"),
            "high_taphole_temp_proxy": ("g_H(z_T_taphole; 0.8, 1.5)", "出铁口温度代理偏高"),
            "high_total_delta_p": ("g_H(z_DP_total; 0.8, 1.5)", "全炉压差偏高"),
            "low_permeability": ("g_L(z_PI; -0.8, -1.5)", "透气性偏低"),
            "top_pressure_spikes": ("g_H(spike_count_15; 1, 5)", "顶压尖峰"),
            "operation_heat_increase": ("g_H(z_heat_operation; 0.5, 1.2)", "操作热输入增加"),
        },
    },
    "column": {
        "name": "料柱失稳（悬料/崩滑料）",
        "target": "料线停滞或突降及其压力响应",
        "subrules": {
            "hang": {
                "name": "悬料子规则",
                "terms": {
                    "stall_duration": ("g_H(stall_duration; 20, 40)", "料线停滞持续时间"),
                    "total_delta_p_rise": ("g_H(z_DP_total; 0.8, 1.5)", "全炉压差升高"),
                    "blast_pressure_rise": ("g_H(z_P_blast; 0.8, 1.5)", "热风压力升高"),
                    "pi_drop": ("g_L(z_PI; -0.8, -1.5)", "透气性下降"),
                    "top_temp_rise": ("g_H(top_temp_slope; 0.1, 0.5)", "顶温上升"),
                    "upper_body_temp_rise": ("g_H(z_upper_body; 0.8, 1.5)", "炉身上部温度上升"),
                },
            },
            "slip": {
                "name": "崩滑料子规则",
                "terms": {
                    "drop_magnitude": ("g_H(line_drop; 0.3, 2.0)", "料线突降幅度"),
                    "pressure_oscillation": ("g_H(pressure_oscillation; 0.8, 1.5)", "压力制度振荡"),
                    "top_pressure_spike": ("g_H(spike_count_15; 1, 5)", "顶压尖峰"),
                    "top_temp_dispersion": ("g_H(top_temp_dispersion; 0.15, 0.45)", "四点顶温离散"),
                    "north_south_level_diff": ("g_H(abs(L_south-L_north); 0.25, 0.8)", "南北料线差"),
                },
            },
        },
        "notes": ["当前仓库未保留历史Resolver实现，无法确认最终column分是max、加权合并还是带额外门控；手册只确认两个子分。"],
    },
}


def esc(value: Any) -> str:
    return str(value).replace("|", "\\|").replace("\n", " ")


def weighted_formula(terms: dict[str, tuple[str, str]], weights: dict[str, Any], symbol: str) -> str:
    pieces = [f"{float(weights[key]):g}×{key}" for key in terms if key in weights]
    return f"{symbol} = 100 × ({' + '.join(pieces)}) / {sum(float(weights[k]) for k in terms if k in weights):g}"


def legacy_hard_lines(thresholds: dict[str, Any]) -> list[str]:
    hard = thresholds.get("hard") or {}
    rows = []
    if thresholds.get("hard_score_limit") is not None:
        rows.append(f"配置的硬条件分值参数：`hard_score_limit={thresholds['hard_score_limit']}`。")
    if hard:
        rows.append("硬条件阈值：" + "；".join(f"`{k}={v}`" for k, v in hard.items()) + "。")
    if rows:
        rows.append("注意：当前仓库缺少历史规则类实现，无法核实硬条件之间是AND还是OR，也无法核实该参数是保底分、封顶值或候选门；因此不把这一段写进确定性总分公式。")
    return rows


def build_legacy_section(threshold_cfg: dict[str, Any], weight_cfg: dict[str, Any]) -> list[str]:
    lines = ["# 第一部分：原炉况诊断8类规则", ""]
    lines += [
        "这8类用于主/次炉况竞争。异常项按现存阈值与权重配置还原为加权符合度；正常顺行是维护分。",
        "由于当前工作区没有历史 `炉况规则引擎/rules/` 与 `engine/` 实现，本部分对普通加权项有高置信度，对硬门及最终Resolver语义只保留配置事实。",
        "",
    ]
    for index, key in enumerate(("normal", "lowline", "edge", "center", "channel", "cold", "hot", "column"), start=1):
        meta = LEGACY_META[key]
        if index > 1:
            lines += ["<div class=\"page-break\"></div>", ""]
        lines += [f"## 1.{index} {meta['name']}（`{key}`）", "", f"判断目标：{meta['target']}。", ""]
        if key != "column":
            terms = meta["terms"]
            weights = weight_cfg[key]
            symbol = "S_normal" if key == "normal" else f"S_{key}"
            lines += ["数学公式：", "", "```text", weighted_formula(terms, weights, symbol), "```", ""]
            lines += ["|公式项|权重|归一化公式|具体含义|", "|---|---:|---|---|"]
            for term, (formula, meaning) in terms.items():
                lines.append(f"|`{term}`|{float(weights[term]):g}|`{esc(formula)}`|{esc(meaning)}|")
            lines.append("")
            t = threshold_cfg[key]
            for note in legacy_hard_lines(t):
                lines.append(f"- {note}")
        else:
            for subkey, sub in meta["subrules"].items():
                terms = sub["terms"]
                weights = weight_cfg["column"][subkey]
                lines += [f"### {sub['name']}", "", "```text", weighted_formula(terms, weights, f"S_{subkey}"), "```", ""]
                lines += ["|公式项|权重|归一化公式|具体含义|", "|---|---:|---|---|"]
                for term, (formula, meaning) in terms.items():
                    lines.append(f"|`{term}`|{float(weights[term]):g}|`{esc(formula)}`|{esc(meaning)}|")
                lines.append("")
                for note in legacy_hard_lines(threshold_cfg["column"][subkey]):
                    lines.append(f"- {note}")
        for note in meta.get("notes", []):
            lines.append(f"- {note}")
        lines.append("")
    return lines


def factor_spec(term: str, factor_audit: Any, term_semantics: Any) -> tuple[str, str, str]:
    raw = factor_audit.COMPOSITES.get(term) or factor_audit._primitive(term) or {}
    semantic = term_semantics.term_semantics(term)
    formula = str(raw.get("formula") or "clip(受控成品因子,0,1)")
    formula = formula.replace("g_high(", "g_H(").replace("g_low(", "g_L(").replace("g_absolute(", "g_A(")
    sources = raw.get("sources") or raw.get("features") or []
    source_text = "、".join(map(str, sources)) if sources else str(raw.get("sources_prefix") or "受控派生特征")
    return formula, str(semantic["label"] + "：" + semantic["meaning"]), source_text


def build_abc_section(catalog: Any, factor_audit: Any, term_semantics: Any) -> list[str]:
    lines = ["# 第二部分：ABC33规则", ""]
    lines += [
        "ABC33由A类9条维护规则、B类13条风险规则和C类11条安全事件代理组成。所有目录公式项在进入加权前已经转换为0～1因子。",
        "",
        "通用可用项公式：",
        "",
        "```text",
        "R = 100 × Σ(i∈A) [w_i × clip(f_i,0,1)] / Σ(i∈A) w_i",
        "A类维护分：S_A = 100 - R",
        "B/C类风险分：S_BC = R",
        "置信度：confidence = Σ(i∈A)w_i / Σ(all)i w_i",
        "```",
        "",
        "其中A是通过覆盖率、数据年龄、基线和点位完整性门禁的可用项集合。当前配置要求覆盖率不低于75%，数据年龄不超过300秒；缺项不补0，而是在可用权重内重新归一，并降低置信度。",
        "",
    ]
    category_index = {"A": 0, "B": 0, "C": 0}
    for rule in catalog.RULES:
        category_index[rule.category] += 1
        lines += ["<div class=\"page-break\"></div>", "", f"## {rule.rule_id} {rule.display_name}", ""]
        direction = "维护分（越高越接近正常维护目标）" if rule.direction == "maintenance" else "风险分（越高风险越强）"
        lines += [f"- 类别：{rule.category}；方向：{direction}。", f"- 判断原理：{rule.principle}", f"- 观察窗口：{rule.observation_window}", ""]
        terms = dict(rule.terms)
        total = sum(float(v) for v in terms.values())
        numerator = " + ".join(f"{float(weight):g}×{term}" for term, weight in terms.items())
        lines += ["规则总公式：", "", "```text"]
        if rule.direction == "maintenance":
            lines.append(f"S_{rule.rule_id} = 100 - 100 × ({numerator}) / {total:g}")
        else:
            lines.append(f"S_{rule.rule_id} = 100 × ({numerator}) / {total:g}")
        lines += ["```", ""]
        lines += ["|公式项|权重|因子数学公式|具体含义|主要来源|", "|---|---:|---|---|---|"]
        for term, weight in terms.items():
            formula, meaning, sources = factor_spec(term, factor_audit, term_semantics)
            lines.append(f"|`{term}`|{float(weight):g}|`{esc(formula)}`|{esc(meaning)}|{esc(sources)}|")
        lines.append("")
        if rule.rule_id == "C4":
            lines += ["独立证据门：`S_operator = S_C4 × min(CoolingConcurrence, BodyHotConcurrence)`。", ""]
        elif rule.rule_id == "C5":
            lines += ["独立证据门：`S_operator = S_C5 × min(CoolingConcurrence, BodyHotConcurrence, BodyHotEscalation)`。", ""]
        elif rule.rule_id == "C7":
            lines += ["独立证据门：`S_operator = S_C7 × min(BodyHotConcurrence, max(CoolingConcurrence, TopTempRange, TopPressRange, DrainProxy))`。", ""]
        lines += ["建议复核顺序："]
        for order, step in enumerate(rule.intervention_order, start=1):
            lines.append(f"{order}. {step}")
        lines.append("")
    return lines


def build_markdown(root: Path) -> str:
    service_dir = root / "自动诊断服务"
    sys.path.insert(0, str(service_dir))
    import abc_factor_audit  # type: ignore
    import abc_rule_catalog  # type: ignore
    import abc_term_semantics  # type: ignore

    thresholds = yaml.safe_load((root / "炉况规则引擎/config/thresholds.yaml").read_text(encoding="utf-8"))["rules"]
    weights = yaml.safe_load((root / "炉况规则引擎/config/rule_weights.yaml").read_text(encoding="utf-8"))["rules"]
    lines = [
        "# 炉况诊断8类与ABC33规则数学公式手册",
        "",
        f"- 追踪编号：`{REQUIREMENT_ID}`",
        f"- 状态：当前代码与配置的可审计导出；最后核对：{date.today().isoformat()}",
        "- 适用边界：规则解释、人工复核、历史回放设计；不授权自动修改高炉设定值。",
        "- 权威来源：旧8类阈值/权重YAML；ABC33服务端规则目录、特征审计公式、术语字典和数值配置。",
        "",
        "## 阅读结论",
        "",
        "原8类是主/次炉况竞争体系；ABC33是A维护、B风险、C严重事件代理的分层体系。名称相似不代表目标相同，尤其原`hot/cold`描述当前状态，B4/B5描述继续上行/下行风险。",
        "",
        "## 统一数学符号",
        "",
        "```text",
        "clip(x,0,1) = min(1,max(0,x))",
        "g_H(x;a,b) = clip((x-a)/(b-a),0,1)                 [b>a，偏高风险]",
        "g_L(x;a,b) = clip((a-x)/(a-b),0,1)                 [a>b，偏低风险]",
        "g_A(x;a,b) = clip((abs(x)-a)/(b-a),0,1)            [绝对偏离风险]",
        "g_N(x;a)   = clip(1-abs(x)/a,0,1)                  [正常稳定度]",
        "I(condition)=1（条件成立），否则0",
        "z60_X=(最近60分钟均值-30日中位数)/30日IQR",
        "z15std_X=最近15分钟标准差/(30日IQR/1.35)",
        "slope30_X=最近30分钟线性斜率×30/30日IQR",
        "省略参数时：z60/std15的g_H默认(0.8,1.5)，g_L默认(-0.8,-1.5)，z60的g_A默认(0.6,1.2)",
        "趋势项省略参数时：g_H默认(0.5,1.2)，g_L默认(-0.5,-1.2)，g_A默认(0.5,1.2)",
        "```",
        "",
        "当IQR无效、覆盖不足、点位不完整或数据陈旧时，相关项必须进入缺数/低置信度路径，不能把缺数当成0风险。",
        "",
        "## 8类与ABC33主要重合映射",
        "",
        "|原8类|ABC33主要对应|关系|",
        "|---|---|---|",
        "|正常顺行|A1，并受A2～A9共同约束|部分重合；A1不是完整主诊断替代|",
        "|低料线|B6|高度重合|",
        "|边缘煤气流发展|B7|当前状态与风险趋势重合|",
        "|中心过吹|B8|当前状态与风险趋势重合|",
        "|管道行程|B1；严重时C2|B1普通风险、C2复合升级|",
        "|热制度下行|B5；严重冷却/冻结时部分关联C1|当前状态与下行风险不同|",
        "|热制度上行|B4|当前状态与上行风险不同|",
        "|料柱失稳|B2悬料、B3崩滑料；严重时C2|ABC33拆分更细|",
        "",
    ]
    lines += build_legacy_section(thresholds, weights)
    lines += build_abc_section(abc_rule_catalog, abc_factor_audit, abc_term_semantics)
    lines += [
        "<div class=\"page-break\"></div>",
        "",
        "# 第三部分：发布边界与权威来源",
        "",
        "## 当前发布边界",
        "",
        "ABC33当前数值配置为`score_preview`：允许显示分数但关闭B/C告警。多项现场阈值仍标记为预设或暂定，必须经过带人工标签的历史回放和高炉长确认后才能声称优于原规则。",
        "",
        "## 权威文件",
        "",
        "- [原8类阈值](../炉况规则引擎/config/thresholds.yaml)",
        "- [原8类权重](../炉况规则引擎/config/rule_weights.yaml)",
        "- [原8类可诊断性](../炉况规则引擎/config/diagnosability.yaml)",
        "- [ABC33规则目录](../自动诊断服务/abc_rule_catalog.py)",
        "- [ABC33因子审计公式](../自动诊断服务/abc_factor_audit.py)",
        "- [ABC33术语语义](../自动诊断服务/abc_term_semantics.py)",
        "- [ABC33评分器](../自动诊断服务/abc_rule_engine.py)",
        "- [ABC33数值配置](../自动诊断服务/config/abc_furnace_rules.v1.json)",
        "",
        "## 已知未核实项",
        "",
        "1. 当前仓库没有原8类历史`rules/`与`engine/`实现，硬条件组合、`hard_score_limit`精确语义及`column`最终聚合方式不能从配置单独证明。",
        "2. 数学结构一致不等于现场准确率更高；最终优劣必须以高炉长标注事件、误报率、漏报率、提前量和状态切换稳定性评估。",
        "3. 本手册不包含密码、数据库连接串、现场实时值或生产控制指令。",
        "",
    ]
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate the legacy-8 and ABC33 formula handbook")
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    root = args.root.resolve()
    output = args.output if args.output.is_absolute() else root / args.output
    text = build_markdown(root)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(text + "\n", encoding="utf-8", newline="\n")
    print(f"ok=true output={output} chars={len(text)} rules=41")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
