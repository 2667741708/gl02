from pathlib import Path
import sys


SERVICE = Path(__file__).resolve().parents[1] / "自动诊断服务"
sys.path.insert(0, str(SERVICE))

from abc_public_review import _group_metrics, _label, _unit


def test_all_previously_raw_operator_labels_are_chinese():
    expected = {
        "TFT": "理论燃烧温度",
        "T_blast": "热风温度",
        "Hopper_weight": "料罐重量",
        "Hopper_weight_set": "料罐重量设定",
        "P_N2": "氮气压力",
        "Q_N2": "氮气流量",
    }
    for variable, label in expected.items():
        assert _label(variable) == label


def test_units_are_retained_for_newly_labeled_metrics():
    assert _unit("TFT") == "°C"
    assert _unit("T_blast") == "°C"
    assert _unit("P_N2") == "kPa"
    assert _unit("Q_N2") == "m³/min"


def test_review_groups_never_repeat_a_main_metric_in_later_sections():
    metrics = [
        {"variable_name": "T_top_A", "review_priority": 10},
        {"variable_name": "T_body_L10_A", "review_priority": 9},
        {"variable_name": "Q_soft_water", "review_priority": 8},
        {"variable_name": "DP_total", "review_priority": 7},
        {"variable_name": "T_top_B", "review_priority": 6},
        {"variable_name": "T_top_C", "review_priority": 5},
        {"variable_name": "T_top_D", "review_priority": 4},
        {"variable_name": "P_top", "review_priority": 3},
        {"variable_name": "T_body_L10_B", "review_priority": 2},
        {"variable_name": "P_soft_water", "review_priority": 1},
        {"variable_name": "PI", "review_priority": 0},
    ]
    main, body, cooling, other = _group_metrics(metrics)
    groups = [main, body, cooling, other]
    keys = [
        str(metric["variable_name"])
        for group in groups
        for metric in group
    ]

    assert len(main) == 8
    assert [metric["variable_name"] for metric in body] == ["T_body_L10_B"]
    assert [metric["variable_name"] for metric in cooling] == ["P_soft_water"]
    assert [metric["variable_name"] for metric in other] == ["PI"]
    assert len(keys) == len(set(keys)) == len(metrics)
