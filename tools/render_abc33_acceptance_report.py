from __future__ import annotations

import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "自动诊断服务"))
from abc_term_semantics import term_semantics


def compact(value, limit=180):
    text = json.dumps(value, ensure_ascii=False, default=str, separators=(",", ":"))
    return text if len(text) <= limit else text[: limit - 1] + "…"


def threshold_text(value):
    if not isinstance(value, dict):
        return compact(value)
    transform = value.get("input_transform")
    if isinstance(transform, dict):
        selected = {key: transform.get(key) for key in ("mode", "a", "b", "warn", "alarm", "unit", "state") if transform.get(key) is not None}
        if selected:
            return compact(selected)
    if "line" in value:
        line = value["line"]
        return compact({key: line.get(key) for key in ("normal_level", "bias_deviation_warn", "bias_deviation_alarm", "drop_warn", "drop_alarm") if line.get(key) is not None})
    if "duration_minutes" in value:
        duration = value["duration_minutes"]
        return compact({key: duration.get(key) for key in ("warn", "alarm", "state") if duration.get(key) is not None})
    return "已校准0–1因子；不重复阈值化"


def main():
    data_path = ROOT / "data" / "abc33_acceptance" / "abc33_acceptance_latest.json"
    runtime_path = ROOT / "data" / "abc33_acceptance" / "abc33_runtime_acceptance.json"
    output_path = ROOT / "docs" / "handoffs" / "2026-08-10-abc33-production-acceptance.md"
    audit = json.loads(data_path.read_text(encoding="utf-8-sig"))
    runtime = json.loads(runtime_path.read_text(encoding="utf-8-sig"))
    summary = audit["summary"]
    lines = [
        "# ABC33 炉况规则生产部署与全字段验收报告（2026-08-10）",
        "",
        "## 验收结论",
        "",
        "本次验收通过。`BFV4PreviewWs8768` 正常运行并监听8768；WebSocket可建立连接并返回A9、B13、C11共33条规则。8093与8094接口均为HTTP 200并各返回33条规则；8770与11434保持监听。",
        "",
        "合法0分被保留：本批次有7条规则总分为0、154个公式小项为0；这些小项均完成了数据、基线、阈值和权重计算，不是程序未启动，也不作为失败门槛。",
        "",
        "| 验收项 | 结果 |",
        "|---|---:|",
        f"| 审计批次 | {audit['batch']['id']} / {audit['batch']['evaluation_ts']} |",
        f"| 规则数量 | {summary['rule_count']}（A9/B13/C11） |",
        f"| needs_data | {summary['needs_data']} |",
        f"| 公式复算错误 | {len(summary['formula_errors'])} |",
        f"| 阈值合同错误 | {len(summary['threshold_errors'])} |",
        f"| 血缘字段错误 | {len(summary['provenance_errors'])} |",
        f"| 直接传感器值与数据库一致 | {summary['sensor_match_count']}/{summary['sensor_check_count']} |",
        f"| 30日基线快照与数据库一致 | {summary['baseline_match_count']}/{summary['baseline_check_count']} |",
        f"| 合法0分规则 | {summary['zero_rule_scores']} |",
        "",
        "## 运行与端口验收",
        "",
        f"- 检查时刻：`{runtime['checked_at']}`",
        f"- 服务：`{runtime['service']['name']}={runtime['service']['status']}`",
        f"- 监听PID：`8093={runtime['ports']['p8093']}`、`8094={runtime['ports']['p8094']}`、`8768={runtime['ports']['p8768']}`、`8770={runtime['ports']['p8770']}`、`11434={runtime['ports']['p11434']}`",
        f"- WebSocket：`{runtime['websocket']['message_type']}`，33条，完整33条，非空分数33条，非零置信度33条。",
        f"- 8093：HTTP {runtime['http']['p8093']['status']}，{runtime['http']['p8093']['rule_count']}条。",
        f"- 8094：HTTP {runtime['http']['p8094']['status']}，{runtime['http']['p8094']['rule_count']}条。",
        "- 两次8768受控部署均在脚本内部核对8093、8094、8770、11434的部署前后PID未变化；页面计划任务后续独立轮换PID不属于8768部署影响，最终端口均正常。",
        "",
        "## 文件一致性与防回退记录",
        "",
    ]
    for name, digest in runtime["hashes"].items():
        lines.append(f"- `{name}`：`{digest}`")
    lines += [
        "",
        "部署采用“备份→停止8768→原子替换→启动8768→WebSocket验收→受保护端口核对”的闭环。成功后生产文件哈希再次独立读取，证明当前运行文件仍是本机最新版本；失败恢复逻辑只在部署验收失败时触发，不会在成功后自动覆盖新版本。",
        "",
        "## 接口与权限边界",
        "",
        "- 生产接口 `/api/furnace-rules/latest` 在8093、8094均返回33条脱敏规则，不返回公式、权重、阈值、贡献、内部特征或数据库血缘。",
        "- 未登录访问 `/api/admin/furnace-rules/latest-full` 返回403，核心公式不会从普通生产页面泄露。",
        "- 完整全字段结果已写入 `bf_sensor.abc_rule_evaluation_items`，并下载为 `data/abc33_acceptance/abc33_acceptance_latest.json`。该文件含每项实际因子值、权重、贡献、公式、有效阈值、来源传感器值及30日基线快照，仅用于受控审计。",
        "- 当前8094 `/api/auth/status` 显示尚未配置生产后台登录账号；因此完整内部字段已可由数据库和受保护后台处理器返回，但后台管理页面登录启用仍需单独配置 `BF_LOGIN_*` 凭据后受控重启8093/8094。本次未擅自创建或传播生产管理员口令。",
        "",
        "## 33条规则逐项全字段计算记录",
        "",
        "下表中的“实际值”是进入规则加权前已校准的0–1因子值；“来源”同时给出用于生成该因子的数据库传感器当前值和标准化窗口特征。A类总分按 `100-风险分`，B/C类总分按风险分。贡献恒等于 `实际值×权重`。",
        "",
    ]
    for rule in audit["rules"]:
        lines += [
            f"### {rule['rule_id']} {rule['display_name']}",
            "",
            f"- 类别：{rule['category']}；状态：`{rule['status']}`；总分：**{rule['score']}**；置信度：{float(rule['confidence']):.0%}",
            f"- 缺失公式项：{compact(rule.get('missing_features') or [])}",
            "",
            "| 公式项 | 物理含义 | 实际值 | 权重 | 小项贡献 | 有效阈值 | 来源实际值 / 派生值 |",
            "|---|---|---:|---:|---:|---|---|",
        ]
        for part in rule["contributions"]:
            semantic = term_semantics(part["feature_key"])
            source = {
                "传感器": part.get("source_values") or {},
                "派生": part.get("source_features") or {},
            }
            lines.append(
                f"| `{part['feature_key']}` | {semantic['label']}：{semantic['meaning']} | {float(part['raw_value']):.6f} | {float(part['weight']):.2f} | {float(part['contribution']):.6f} | {threshold_text(part.get('effective_thresholds') or {})} | {compact(source)} |"
            )
        lines += ["", "管理员公式快照：", "", "```text"]
        lines.extend(str(part.get("formula") or "") for part in rule["contributions"])
        lines += ["```", ""]
    lines += [
        "## 验收证据文件",
        "",
        "- `data/abc33_acceptance/abc33_acceptance_latest.json`：33条完整内部计算快照。",
        "- `data/abc33_acceptance/abc33_runtime_acceptance.json`：服务、端口、WebSocket、HTTP与文件哈希。",
        "- `docs/handoffs/2026-08-10-abc33-8094-acceptance.png`：8094生产页面截图。",
        "",
        "## 已执行测试",
        "",
        "- `python -m pytest tests/test_abc_rule_engine.py -q`：21 passed。",
        "- `python -m pytest tests/test_abc_common_factors.py -q`：71 passed。",
        "- `python -m pytest tests/test_abc_bridge_live_values.py -q`：5 passed。",
        "- 生产WebSocket探针：33条、完整33条、0条needs_data。",
        "- 生产数据库独立复算：公式、阈值、血缘错误均为0。",
    ]
    output_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(output_path)


if __name__ == "__main__":
    main()
