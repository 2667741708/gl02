"""高炉八类典型炉况的标准动作模板库。"""

ACTION_TEMPLATES = {
    "normal": {
        "goal": "维持当前顺行，避免无必要扰动。",
        "immediate_actions": [
            {"id": "keep_stable", "text": "保持当前制度稳定", "reason": "当前处于正常顺行状态"},
            {"id": "no_frequent_adjust", "text": "不建议频繁小调风、氧、煤、料制", "reason": "避免引入不必要的波动"},
        ],
        "followup_actions": [
            {"id": "monitor_trends", "text": "持续监测风压、顶压、透气性和顶温离散度", "reason": "例行监控"}
        ],
        "forbidden_actions": [
            {"id": "forbid_large_adjust", "text": "不建议因短时轻微波动主动大调参数", "reason": "防止操作过头"}
        ],
        "observe_items": ["风压", "顶压", "透气性指数", "顶温离散度"],
        "recheck_minutes": {"low": 15, "medium": 15, "high": 15, "critical": 15},
        "confirm_required": False,
    },
    "cold": {
        "goal": "先稳顺行，再补热，防止风口灌渣。",
        "immediate_actions": [
            {"id": "reduce_blast", "text": "建议先减风控料速", "reason": "炉凉初期需防止顺行恶化"},
            {"id": "hold_or_reduce_oxygen", "text": "暂缓强化富氧，必要时经现场确认后小幅减氧", "reason": "先稳顺行，避免下部扰动"},
        ],
        "followup_actions": [
            {"id": "raise_blast_temp", "text": "若顺行保持稳定，可提高风温补热", "reason": "补热手段"},
            {"id": "add_net_coke", "text": "必要时适量加净焦", "reason": "补充物理热"},
        ],
        "forbidden_actions": [
            {"id": "forbid_force_increase_blast", "text": "当前不建议强行加风", "reason": "防止压差过大导致悬料"},
            {"id": "forbid_restore_coal", "text": "当前不建议立即恢复喷煤强化", "reason": "防止进一步吸热"},
        ],
        "observe_items": ["风压", "顶温", "料速", "风口状态"],
        "recheck_minutes": {"low": 15, "medium": 10, "high": 10, "critical": 5},
        "confirm_required": True,
    },
    "hot": {
        "goal": "先下压热量，再防难行和悬料。",
        "immediate_actions": [
            {"id": "reduce_coal", "text": "减喷煤", "reason": "减少热量输入"},
            {"id": "reduce_blast_temp", "text": "视情况降风温", "reason": "快速调整热状态"},
        ],
        "followup_actions": [
            {"id": "adjust_burden", "text": "若属持续性偏热，可转入负荷调剂", "reason": "长期热补偿调整"}
        ],
        "forbidden_actions": [
            {"id": "forbid_increase_heat", "text": "不建议继续增煤、增氧", "reason": "防止热量堆积导致难行"}
        ],
        "observe_items": ["风压", "压差", "料速", "顶压波动"],
        "recheck_minutes": {"low": 15, "medium": 15, "high": 10, "critical": 5},
        "confirm_required": True,
    },
    "lowline": {
        "goal": "快速补料，严控料速，防止顶温超限及料柱崩落。",
        "immediate_actions": [
            {"id": "reduce_blast_lowline", "text": "减风控料速", "reason": "防止亏料进一步扩大"},
            {"id": "control_top_temp", "text": "若顶温过高，启动顶温控制", "reason": "保护炉顶设备"},
        ],
        "followup_actions": [
            {"id": "add_coke_for_lowline", "text": "根据亏料深度适量加净焦", "reason": "补偿热损失"},
            {"id": "loosen_edge", "text": "疏松边缘、发展两道气流", "reason": "改善透气性"},
        ],
        "forbidden_actions": [
            {"id": "forbid_restore_blast_lowline", "text": "不建议强行恢复风量", "reason": "亏料未补足前加风风险大"}
        ],
        "observe_items": ["料位", "顶温", "煤气分布", "风压"],
        "recheck_minutes": {"low": 15, "medium": 10, "high": 10, "critical": 5},
        "confirm_required": True,
    },
    "edge": {
        "goal": "疏松中心、抑制边沿，恢复合理煤气流分布。",
        "immediate_actions": [
            {"id": "adjust_charging_edge", "text": "调整装料制度，疏松中心、抑制边沿", "reason": "纠正气流分布"}
        ],
        "followup_actions": [
            {"id": "lighten_burden", "text": "适当减轻焦炭负荷", "reason": "提高料柱透气性"}
        ],
        "forbidden_actions": [
            {"id": "forbid_oxygen_edge", "text": "不建议在边缘已发展时继续强化富氧", "reason": "防止边缘过热及管道"}
        ],
        "observe_items": ["十字测温", "顶温离散度", "压差"],
        "recheck_minutes": {"low": 30, "medium": 20, "high": 15, "critical": 10},
        "confirm_required": True,
    },
    "center": {
        "goal": "疏松边缘、抑制中心，缓解憋压和崩悬风险。",
        "immediate_actions": [
            {"id": "adjust_charging_center", "text": "缩小矿石溜槽平均倾角或矿焦角差", "reason": "抑制中心过吹"}
        ],
        "followup_actions": [
            {"id": "reduce_blast_center", "text": "若炉况不顺，适当减风", "reason": "缓解憋压"}
        ],
        "forbidden_actions": [
            {"id": "forbid_increase_blast_center", "text": "不建议继续强行加风", "reason": "防止引发悬料"}
        ],
        "observe_items": ["十字测温中心值", "压差", "料速"],
        "recheck_minutes": {"low": 30, "medium": 20, "high": 15, "critical": 10},
        "confirm_required": True,
    },
    "channel": {
        "goal": "尽快破坏局部过分发展的通道，恢复均匀下料和顺行。",
        "immediate_actions": [
            {"id": "reduce_blast_channel", "text": "立即减风", "reason": "消除气流通道"},
            {"id": "reduce_oxygen_channel", "text": "确认管道征兆后按事故预案处理富氧，优先小幅减氧", "reason": "强处置必须由现场确认"},
        ],
        "followup_actions": [
            {"id": "special_charging", "text": "经授权可扇形或定点布料", "reason": "定点压制管道"}
        ],
        "forbidden_actions": [
            {"id": "forbid_restore_blast_channel", "text": "管道未消除前不建议恢复风量", "reason": "防止管道复发"}
        ],
        "observe_items": ["各点顶温波动", "风压波动", "透气性"],
        "recheck_minutes": {"low": 15, "medium": 10, "high": 10, "critical": 5},
        "confirm_required": True,
    },
    "column": {
        "goal": "解除悬料，恢复顺行，再恢复热量。",
        "immediate_actions": [
            {"id": "confirm_column_emergency_plan", "text": "确认悬料硬条件后，按事故预案处置富氧和喷煤", "reason": "强安全动作必须由现场值班长确认"},
            {"id": "reduce_blast_column", "text": "减风", "reason": "降低压差使料柱下落"},
        ],
        "followup_actions": [
            {"id": "sit_burden", "text": "组织坐料", "reason": "强制解除悬料"}
        ],
        "forbidden_actions": [
            {"id": "forbid_stop_blast_direct", "text": "悬料时不允许直接休风", "reason": "安全规程限制"},
            {"id": "forbid_top_water", "text": "坐料前必须停炉顶打水", "reason": "防止爆炸风险"},
        ],
        "observe_items": ["探尺状态", "风压", "顶压", "风口状态"],
        "recheck_minutes": {"low": 10, "medium": 5, "high": 5, "critical": 5},
        "confirm_required": True,
    },
}
