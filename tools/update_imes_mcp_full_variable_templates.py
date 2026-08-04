"""Generate the complete IMES MCP variable and colloquial-template appendix.

The source of truth for actual object/column names is the user-authorized
one-row-per-object audit JSON. Business meanings are deliberately conservative:
confirmed laboratory mappings are named, while uncertain legacy/status fields
are marked as structural or pending-dictionary instead of being guessed.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
import json
from pathlib import Path
import re
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SOURCE = (
    ROOT
    / "logs"
    / "imes_complete_row_samples_20260727"
    / "imes_complete_row_samples.json"
)
DEFAULT_TARGET = ROOT / "PT" / "IMES_Vastbase_MCP指令模板全集.md"
DEFAULT_MANIFEST = ROOT / "logs" / "imes_mcp_full_variable_coverage_20260727.json"
DEFAULT_CATALOG = (
    ROOT
    / "高炉前端数据"
    / "智能助手"
    / "mcp"
    / "imes_full_variable_catalog.json"
)
START_MARKER = "<!-- AUTO:IMES-FULL-VARIABLES:START -->"
END_MARKER = "<!-- AUTO:IMES-FULL-VARIABLES:END -->"


@dataclass(frozen=True)
class VariableSpec:
    meaning: str
    aliases: tuple[str, ...] = ()
    confidence: str = "structural"
    note: str = ""


@dataclass(frozen=True)
class ObjectSpec:
    profile: str
    label: str
    purpose: str
    time_field: str
    identity_fields: tuple[str, ...]
    exact_filter: dict[str, Any]
    speech_scope: str


OBJECT_SPECS: dict[str, ObjectSpec] = {
    "public.batch_input": ObjectSpec(
        "operations",
        "批次投料",
        "矿批/焦批、1—24号料仓或称量通道及批次合计",
        "workdate",
        ("workdate", "lot", "charge"),
        {"prodcentercode": "2D012"},
        "2号炉昨天的批次投料",
    ),
    "public.inner_batch_insp_bb": ObjectSpec(
        "operations",
        "铁水旧化验结果",
        "化验批号、取样/判定时间以及C、Si、Mn等元素",
        "judgetime",
        ("batchno", "judgetime", "publishtime"),
        {"prodcentercode": "2"},
        "2号高炉昨天发布的铁水化验",
    ),
    "public.slag_inspection": ObjectSpec(
        "operations",
        "炉渣旧检验",
        "炉次、渣样号以及尚未取得正式编号映射的12个旧指标",
        "workdate",
        ("workdate", "meltno", "sampleno"),
        {"prodcentercode": "2D012"},
        "2号炉昨天的旧炉渣检验",
    ),
    "public.t_ipes_cond": ObjectSpec(
        "operations",
        "炉次作业条件",
        "开堵铁口、出铁时长、批次范围、铁量和渣比",
        "workdate",
        ("workdate", "meltno"),
        {"prodcentercode": "2D012"},
        "2号炉昨天的炉次作业",
    ),
    "public.t_ipes_out_put": ObjectSpec(
        "operations",
        "生产实绩",
        "炉次生产、铁量、称重、铁水罐和出库状态",
        "workdate",
        ("workdate", "meltno"),
        {"prodcentercode": "2D012"},
        "2号炉昨天的生产实绩",
    ),
    "public.t_qpes_inner_batch": ObjectSpec(
        "operations",
        "炉次化验索引",
        "炉次、化验批号、取样、判定和检验流程状态",
        "businessdate",
        ("businessdate", "heatno", "batchno"),
        {},
        "昨天的铁水化验索引",
    ),
    "public.v_qpes_inner_batch_insp_final_sample": ObjectSpec(
        "laboratory",
        "高炉铁水完整化验视图",
        "铁水试样、人员、班次和C/Si/Mn/P/S等最终结果",
        "发布时间",
        ("试样号", "发布时间", "发布日期"),
        {"高炉": "2"},
        "2号高炉昨天的最终铁水化验",
    ),
    "public.v_qpes_mat_final": ObjectSpec(
        "laboratory",
        "高炉铁水精简化验视图",
        "铁水试样及元素结果；与完整铁水视图同源，不能重复累计",
        "publishtime",
        ("batchno", "publishtime"),
        {"prodcentercode": "2"},
        "2号高炉昨天的精简铁水化验",
    ),
    "public.v_qpes_sinter_machine_sample_insp_final": ObjectSpec(
        "laboratory",
        "烧结矿最终化验视图",
        "烧结机试样流程、TFe、FeO、CaO、SiO2、R2等",
        "业务日期",
        ("试样单号", "业务日期", "检验批号"),
        {"加工中心编码": "JS2"},
        "2号烧结机昨天的烧结矿化验",
    ),
    "public.v_qpes_slag_insoection_final": ObjectSpec(
        "laboratory",
        "高炉炉渣命名化验视图",
        "渣样、炉次、命名氧化物和R2/R3/R4",
        "publishtime",
        ("sampleno", "meltno", "publishtime"),
        {"prodcentercode": "JLZ2"},
        "2号炉昨天发布的炉渣化验",
    ),
    "public.v_qpes_steel_final": ObjectSpec(
        "laboratory",
        "炼钢最终化验视图",
        "炼钢试样、钢种、工序和合金/残余元素；不是高炉铁水",
        "businessdate",
        ("sampleno", "businessdate", "furnacenumber"),
        {},
        "昨天的炼钢最终试样",
    ),
}


COMMON_FIELDS: dict[str, VariableSpec] = {
    "id": VariableSpec("内部记录ID", ("记录号", "内部ID", "主键"), "structural"),
    "workdate": VariableSpec("业务时间/生产日期", ("业务时间", "生产日期", "工作日期"), "confirmed"),
    "workdate2": VariableSpec("辅助业务时间", ("第二业务时间", "辅助时间"), "structural", "具体口径待MES字典确认"),
    "businessdate": VariableSpec("业务日期", ("业务日", "生产日期"), "confirmed"),
    "prodcentercode": VariableSpec("生产/加工中心编码", ("中心编码", "高炉编码", "工序编码"), "structural"),
    "prodcentername": VariableSpec("生产/加工中心名称", ("中心名称", "高炉名称", "工序名称"), "structural"),
    "batchno": VariableSpec("检验批号/试样批号", ("化验批号", "检验批号", "样品批号"), "confirmed"),
    "meltno": VariableSpec("高炉炉次号", ("炉次", "炉号", "铁次"), "confirmed"),
    "sampleno": VariableSpec("试样号", ("样品号", "试样编号"), "confirmed"),
    "publishtime": VariableSpec("结果发布时间", ("发布时间", "发布日期", "结果发布时刻"), "confirmed"),
    "createtime": VariableSpec("记录创建时间", ("创建时间", "录入时间"), "structural"),
    "updatetime": VariableSpec("记录更新时间", ("更新时间", "最后修改时间"), "structural"),
    "creator": VariableSpec("创建人", ("录入人", "创建人员"), "structural", "人员信息，限制使用"),
    "creatorid": VariableSpec("创建人ID", ("录入人账号", "创建账号"), "structural", "账号信息，限制使用"),
    "updater": VariableSpec("更新人", ("修改人", "更新人员"), "structural", "人员信息，限制使用"),
    "updaterid": VariableSpec("更新人ID", ("修改账号", "更新账号"), "structural", "账号信息，限制使用"),
    "status": VariableSpec("记录状态", ("状态", "有效状态", "记录状态"), "structural"),
    "remark": VariableSpec("备注", ("说明", "备注信息"), "structural"),
    "remark1": VariableSpec("备注1", ("第一备注", "备注一"), "structural"),
    "remark2": VariableSpec("备注2", ("第二备注", "备注二"), "structural"),
    "remark3": VariableSpec("备注3", ("第三备注", "备注三"), "structural"),
    "remark4": VariableSpec("备注4", ("第四备注", "备注四"), "structural"),
    "workshift": VariableSpec("生产班次", ("班次", "白班夜班", "作业班次"), "structural"),
    "workclass": VariableSpec("生产班组", ("班组", "甲乙丙班"), "structural"),
    "workstaff": VariableSpec("作业人员", ("操作人", "当班人员"), "structural", "人员信息，限制使用"),
    "judgetime": VariableSpec("结果判定时间", ("判定时间", "审核时间", "化验完成时间"), "confirmed"),
    "judgeclass": VariableSpec("判定班组", ("审核班组", "判定甲乙丙班"), "structural"),
    "judgeshift": VariableSpec("判定班次", ("审核班次", "判定白夜班"), "structural"),
    "judgestaff": VariableSpec("判定/审核人员", ("审核人", "判定人"), "structural", "人员信息，限制使用"),
    "takesampletime": VariableSpec("取样时间", ("采样时间", "取铁水样时间"), "confirmed"),
    "takesamplestaff": VariableSpec("取样人员", ("采样人", "取样人"), "structural", "人员信息，限制使用"),
    "takesampleshift": VariableSpec("取样班次", ("采样班次", "取样白夜班"), "structural"),
    "takesampleclass": VariableSpec("取样班组", ("采样班组", "取样甲乙丙班"), "structural"),
    "inspshift": VariableSpec("检验班次", ("化验班次", "检验白夜班"), "structural"),
    "inspstaff": VariableSpec("检验人员", ("化验人", "检验人"), "structural", "人员信息，限制使用"),
    "inspphyclass": VariableSpec("检验物理分类/检验类别", ("检验类别", "物检分类"), "uncertain", "正式中文名称待MES字典确认"),
    "materialcode": VariableSpec("物料编码", ("物料代码", "材料编码"), "structural"),
    "materialname": VariableSpec("物料名称", ("物料", "材料名称"), "structural"),
    "steelgrade": VariableSpec("钢种/牌号", ("钢种", "牌号"), "structural"),
}


OBJECT_FIELDS: dict[str, dict[str, VariableSpec]] = {
    "public.batch_input": {
        "charge": VariableSpec("装料批别（矿批/焦批）", ("矿批", "焦批", "批别"), "confirmed"),
        "lot": VariableSpec("料批序号/批次标识", ("第几批", "料批", "批号"), "confirmed"),
        "value_sum": VariableSpec("本批投料合计", ("投料总量", "批次合计"), "confirmed"),
        "mining_batch_sum": VariableSpec("矿批合计", ("矿批量", "矿石批量"), "confirmed"),
        "coke_charge_sum": VariableSpec("焦批合计", ("焦批量", "焦炭批量"), "confirmed"),
    },
    "public.inner_batch_insp_bb": {
        "inspshift": VariableSpec("检验班次", ("化验班次",), "structural"),
        "inspstaff": VariableSpec("检验人员", ("化验人", "检验人"), "structural", "人员信息，限制使用"),
    },
    "public.t_ipes_cond": {
        "costaccuno": VariableSpec("成本核算单元编号", ("成本单元", "核算单元号"), "uncertain", "按字段名解释，正式字典待确认"),
        "outputno": VariableSpec("出铁/产出记录编号", ("产出编号", "出铁记录号"), "uncertain", "正式字典待确认"),
        "sumbatchstart": VariableSpec("炉次起始投料批次", ("起始批次", "从哪批开始"), "confirmed"),
        "sumbatchend": VariableSpec("炉次结束投料批次", ("结束批次", "到哪批结束"), "confirmed"),
        "sumbatch": VariableSpec("炉次累计批次数", ("批次数", "累计料批"), "structural"),
        "opentime": VariableSpec("开铁口时间", ("开口时间", "开始出铁时间"), "confirmed"),
        "closetime": VariableSpec("堵铁口/出铁结束时间", ("堵口时间", "结束出铁时间"), "confirmed"),
        "tappingtime": VariableSpec("出铁持续时间", ("出铁时长", "这一炉出了多久"), "confirmed"),
        "tappingpitch": VariableSpec("出铁口节距/相关位置量", ("出铁口节距", "铁口位置量"), "uncertain", "字段中文及单位待现场字典确认"),
        "theorys": VariableSpec("理论硫S", ("理论硫", "预计硫"), "structural"),
        "theorysi": VariableSpec("理论硅Si", ("理论硅", "预计硅"), "structural"),
        "tappingtemp": VariableSpec("出铁温度", ("铁水温度", "出铁温度"), "confirmed", "通常按℃，正式单位以字典为准"),
        "isnull": VariableSpec("源记录空值/完整性标志", ("空值标志", "是否缺失"), "uncertain", "业务含义待MES字典确认"),
        "depth": VariableSpec("铁口深度", ("泥包深度", "铁口深度"), "structural", "单位待确认"),
        "mudweight": VariableSpec("堵口泥量/炮泥重量", ("泥量", "炮泥重量"), "structural", "单位待确认"),
        "ironquan": VariableSpec("炉次实际铁量", ("实际铁量", "出了多少铁"), "confirmed", "通常按吨"),
        "theoryquan": VariableSpec("炉次理论铁量", ("理论铁量", "预计产量"), "confirmed", "通常按吨"),
        "downtime": VariableSpec("停机/休风相关时长", ("停机时间", "休风时长"), "uncertain", "正式业务口径待确认"),
        "angle": VariableSpec("铁口角度", ("铁口角度", "出铁口角度"), "structural", "单位待确认"),
        "clearstatus": VariableSpec("炉次清账/清除状态", ("清账状态", "清除状态"), "uncertain", "正式状态枚举待确认"),
        "meltnoj": VariableSpec("关联炉次号J字段", ("关联炉次", "炉次J"), "uncertain", "字段用途待MES字典确认"),
        "changestatus": VariableSpec("炉次变更状态", ("变更状态", "是否改炉次"), "structural"),
        "taskstatus": VariableSpec("炉次任务状态", ("任务状态", "炉次是否完成"), "structural"),
        "ironmaterialbatch": VariableSpec("铁料批次/铁水物料批次", ("铁料批次", "物料批号"), "uncertain", "精确谱系含义待确认"),
        "irondifference": VariableSpec("实际与理论铁量差值", ("铁量差", "产量偏差"), "structural"),
        "irondifference2": VariableSpec("第二铁量差值口径", ("第二铁量差", "铁量差2"), "uncertain", "计算公式待确认"),
        "slagrate": VariableSpec("渣比", ("炉渣比", "每吨铁渣量"), "confirmed"),
        "slagloadingtime": VariableSpec("装渣/渣处理时间", ("装渣时间", "渣处理时刻"), "uncertain", "正式业务口径待确认"),
    },
    "public.t_ipes_out_put": {
        "heatcode": VariableSpec("出铁实绩炉位/罐次代码", ("实绩代码", "罐次代码"), "uncertain", "正式字典待确认"),
        "unitcode": VariableSpec("计量单位编码", ("单位代码", "计量单位编码"), "structural"),
        "unitname": VariableSpec("计量单位名称", ("单位", "计量单位"), "structural"),
        "ironquan": VariableSpec("实际铁水量", ("铁量", "出铁量", "每炉出了多少铁"), "confirmed", "通常按吨"),
        "datasour": VariableSpec("数据来源", ("数据源", "来源系统"), "structural"),
        "grossweigh": VariableSpec("称重毛重", ("毛重", "总重"), "confirmed"),
        "tareweigh": VariableSpec("称重皮重", ("皮重", "空罐重"), "confirmed"),
        "sendstaff": VariableSpec("发运/送出人员", ("发运人", "送出人员"), "structural", "人员信息，限制使用"),
        "senddate": VariableSpec("发运/送出时间", ("发运时间", "送出时间"), "structural"),
        "outstocktype": VariableSpec("出库类型", ("出库方式", "出库类型"), "structural"),
        "status1": VariableSpec("辅助状态1", ("状态1", "第二状态"), "uncertain", "状态枚举待确认"),
        "usestatus": VariableSpec("使用状态", ("是否使用", "使用状态"), "structural"),
        "ladleage": VariableSpec("铁水罐龄/罐次使用次数", ("罐龄", "铁水包龄"), "uncertain", "正式定义与单位待确认"),
        "mheatcode": VariableSpec("关联热次/炉次代码", ("关联炉次代码", "M热次代码"), "uncertain", "正式字典待确认"),
        "weightstatus": VariableSpec("称重状态", ("过磅状态", "计量状态"), "structural"),
        "directstatus": VariableSpec("直送状态", ("是否直送", "直送状态"), "structural"),
        "weighttime": VariableSpec("称重时间", ("过磅时间", "计量时间"), "confirmed"),
        "postslag": VariableSpec("后续渣/带渣记录字段", ("后渣", "带渣情况"), "uncertain", "正式业务含义待确认"),
    },
    "public.t_qpes_inner_batch": {
        "sources": VariableSpec("样品/任务来源", ("检验来源", "样品来源"), "structural"),
        "inspplancode": VariableSpec("检验计划编码", ("检验方案代码", "化验计划号"), "structural"),
        "inspplanname": VariableSpec("检验计划名称", ("检验方案", "化验计划"), "structural"),
        "takesamplesite": VariableSpec("取样地点", ("采样位置", "取样点"), "confirmed"),
        "judgeresult": VariableSpec("判定结果", ("化验结论", "是否合格"), "structural"),
        "teststatus": VariableSpec("检验状态", ("化验状态", "是否已检"), "confirmed"),
        "heatno": VariableSpec("对应炉次号", ("炉次", "化验对应哪一炉"), "confirmed"),
    },
}


IRON_ELEMENTS = {
    1: ("铁水碳C", ("碳", "C", "碳含量")),
    2: ("铁水硅Si", ("硅", "Si", "硅含量", "铁水硅")),
    3: ("铁水锰Mn", ("锰", "Mn", "锰含量")),
    4: ("铁水磷P", ("磷", "P", "磷含量")),
    5: ("铁水硫S", ("硫", "S", "硫含量")),
    6: ("铁水钛Ti", ("钛", "Ti", "钛含量")),
    7: ("铁水钒V", ("钒", "V", "钒含量")),
    8: ("铁水铬Cr", ("铬", "Cr", "铬含量")),
    9: ("铁水铜Cu", ("铜", "Cu", "铜含量")),
    10: ("铁水镍Ni", ("镍", "Ni", "镍含量")),
    11: ("铁水砷As", ("砷", "As", "砷含量")),
}


LAB_VIEW_FIELDS: dict[str, dict[str, VariableSpec]] = {
    "public.v_qpes_inner_batch_insp_final_sample": {
        "试样号": VariableSpec("铁水试样/检验批号", ("试样号", "化验批号"), "confirmed"),
        "发布时间": VariableSpec("结果判定或审核完成时间", ("判定时间", "化验完成时间"), "confirmed"),
        "发布日期": VariableSpec("结果发布日期", ("发布日期", "发布业务日"), "confirmed"),
        "高炉": VariableSpec("高炉编号", ("几号高炉", "高炉号"), "confirmed"),
        "罐号": VariableSpec("铁水罐号", ("铁水包号", "罐号"), "confirmed"),
        "班次": VariableSpec("化验判定班组", ("甲乙丙班", "判定班次"), "confirmed"),
        "检验人": VariableSpec("执行检验人员", ("化验人", "检验员"), "confirmed", "人员信息，限制使用"),
        "审核人": VariableSpec("审核发布人员", ("审核员", "发布人"), "confirmed", "人员信息，限制使用"),
    },
    "public.v_qpes_mat_final": {
        "thankno": VariableSpec("铁水罐号", ("罐号", "铁水包号"), "confirmed"),
    },
    "public.v_qpes_sinter_machine_sample_insp_final": {
        "试样单id": VariableSpec("烧结试样单内部ID", ("试样记录ID",), "structural"),
        "试样单号": VariableSpec("烧结试样单编号", ("试样号", "烧结样号"), "confirmed"),
        "业务日期": VariableSpec("样品生产业务日", ("生产日期", "样品日期"), "confirmed"),
        "检验批号": VariableSpec("烧结化验检验批号", ("化验批号", "检验批次"), "confirmed"),
        "加工中心编码": VariableSpec("烧结机/加工中心编码", ("烧结机代码", "JS1或JS2"), "confirmed"),
        "加工中心名称": VariableSpec("烧结机名称", ("1号烧结机", "2号烧结机"), "confirmed"),
        "制样时间": VariableSpec("样品制备时间", ("制样时刻", "样品制备时间"), "confirmed"),
        "接样人": VariableSpec("接收样品人员/账号", ("接样人", "收样人"), "confirmed", "人员信息，限制使用"),
        "接样时间": VariableSpec("化验室接样时间", ("收样时间", "样品到实验室时间"), "confirmed"),
        "接样班次": VariableSpec("接样白班/夜班", ("接样班次", "白班夜班"), "confirmed"),
        "接样班别": VariableSpec("接样甲/乙/丙班组", ("接样班组", "甲乙丙班"), "confirmed"),
        "发布人": VariableSpec("化验结果发布人员", ("发布人", "结果审核人"), "confirmed", "人员信息，限制使用"),
        "发布时间": VariableSpec("化验结果正式发布时间", ("结果发布时间", "化验完成时间"), "confirmed"),
        "tfevalue": VariableSpec("烧结矿全铁TFe", ("全铁", "TFe", "总铁"), "confirmed"),
        "caovalue": VariableSpec("烧结矿氧化钙CaO", ("氧化钙", "CaO"), "confirmed"),
        "mgovalue": VariableSpec("烧结矿氧化镁MgO", ("氧化镁", "MgO"), "confirmed"),
        "sio2value": VariableSpec("烧结矿二氧化硅SiO2", ("二氧化硅", "SiO2"), "confirmed"),
        "al2o3value": VariableSpec("烧结矿三氧化二铝Al2O3", ("三氧化二铝", "Al2O3"), "confirmed"),
        "pvalue": VariableSpec("烧结矿磷P", ("磷", "P"), "confirmed"),
        "tio2value": VariableSpec("烧结矿二氧化钛TiO2", ("二氧化钛", "TiO2"), "confirmed"),
        "mnovalue": VariableSpec("烧结矿氧化锰MnO", ("氧化锰", "MnO"), "confirmed"),
        "znvalue": VariableSpec("烧结矿锌Zn", ("锌", "Zn"), "confirmed"),
        "crvalue": VariableSpec("烧结矿铬Cr", ("铬", "Cr"), "confirmed"),
        "r2value": VariableSpec("烧结矿二元碱度R2", ("碱度", "二元碱度", "R2"), "confirmed"),
        "feovalue": VariableSpec("烧结矿氧化亚铁FeO", ("氧化亚铁", "FeO"), "confirmed"),
        "svalue": VariableSpec("烧结矿硫S", ("硫", "S"), "confirmed"),
        "mgalvalue": VariableSpec("烧结矿镁铝比MgO/Al2O3", ("镁铝比",), "confirmed"),
        "alsivalue": VariableSpec("烧结矿铝硅比Al2O3/SiO2", ("铝硅比",), "confirmed"),
        "qdvalue": VariableSpec("烧结矿QD强度类指标", ("QD", "强度指标"), "uncertain", "确切试验名、算法和单位待字典确认"),
    },
    "public.v_qpes_slag_insoection_final": {
        "sampleno": VariableSpec("炉渣试样号", ("渣样号", "炉渣样品号"), "confirmed"),
        "meltno": VariableSpec("对应高炉炉次号", ("炉次", "这份渣是哪一炉"), "confirmed"),
        "prodcentercode": VariableSpec("炉渣加工中心/高炉编码", ("JLZ1", "JLZ2", "炉渣中心编码"), "confirmed"),
        "publishtime": VariableSpec("炉渣化验发布时间", ("渣样发布时间", "炉渣结果时间"), "confirmed"),
        "tfe": VariableSpec("炉渣全铁TFe", ("全铁", "渣中TFe"), "confirmed", "历史覆盖较低"),
        "feo": VariableSpec("炉渣氧化亚铁FeO", ("氧化亚铁", "渣中FeO"), "confirmed"),
        "cao": VariableSpec("炉渣氧化钙CaO", ("氧化钙", "渣中CaO"), "confirmed"),
        "mgo": VariableSpec("炉渣氧化镁MgO", ("氧化镁", "渣中MgO"), "confirmed"),
        "sio2": VariableSpec("炉渣二氧化硅SiO2", ("二氧化硅", "渣中SiO2"), "confirmed"),
        "al2o3": VariableSpec("炉渣三氧化二铝Al2O3", ("三氧化二铝", "渣中Al2O3"), "confirmed"),
        "tio2": VariableSpec("炉渣二氧化钛TiO2", ("二氧化钛", "渣中TiO2"), "confirmed"),
        "r2": VariableSpec("炉渣二元碱度R2", ("二元碱度", "R2", "炉渣碱度"), "confirmed"),
        "r3": VariableSpec("炉渣三元碱度R3", ("三元碱度", "R3"), "structural", "正式公式待确认"),
        "r4": VariableSpec("炉渣四元碱度R4", ("四元碱度", "R4"), "structural", "正式公式待确认"),
        "mgo_al2o3": VariableSpec("炉渣镁铝比MgO/Al2O3", ("镁铝比",), "confirmed"),
        "sio2_al2o3": VariableSpec("炉渣硅铝比SiO2/Al2O3", ("硅铝比",), "confirmed", "当前核查样本全空"),
    },
}


LAB_IRON_ELEMENTS = {
    "cvalue": ("铁水碳C", ("碳", "C", "碳含量")),
    "sivalue": ("铁水硅Si", ("硅", "Si", "硅含量", "铁水硅")),
    "mnvalue": ("铁水锰Mn", ("锰", "Mn", "锰含量")),
    "pvalue": ("铁水磷P", ("磷", "P", "磷含量")),
    "svalue": ("铁水硫S", ("硫", "S", "硫含量")),
    "tivalue": ("铁水钛Ti", ("钛", "Ti", "钛含量")),
    "vvalue": ("铁水钒V", ("钒", "V", "钒含量")),
    "crvalue": ("铁水铬Cr", ("铬", "Cr", "铬含量")),
    "nivalue": ("铁水镍Ni", ("镍", "Ni", "镍含量")),
    "cuvalue": ("铁水铜Cu", ("铜", "Cu", "铜含量")),
    "asvalue": ("铁水砷As", ("砷", "As", "砷含量")),
}


STEEL_FIELDS = {
    "sampleno": ("炼钢试样号", ("钢样号", "试样号"), "confirmed", ""),
    "femdvalue": ("钢样铁Fe", ("铁", "Fe"), "confirmed", "部分样品不发布"),
    "cmdvalue": ("钢样碳C", ("碳", "C"), "confirmed", ""),
    "simdvalue": ("钢样硅Si", ("硅", "Si"), "confirmed", ""),
    "mnmdvalue": ("钢样锰Mn", ("锰", "Mn"), "confirmed", ""),
    "pmdvalue": ("钢样磷P", ("磷", "P"), "confirmed", ""),
    "nimdvalue": ("钢样镍Ni", ("镍", "Ni"), "confirmed", ""),
    "momdvalue": ("钢样钼Mo", ("钼", "Mo"), "confirmed", ""),
    "cumdvalue": ("钢样铜Cu", ("铜", "Cu"), "confirmed", ""),
    "almdvalue": ("钢样总铝Al", ("总铝", "铝", "Al"), "structural", "正式名称待化验室确认"),
    "alsmdvalue": ("钢样酸溶铝Als", ("酸溶铝", "Als"), "uncertain", "口径待化验室确认"),
    "timdvalue": ("钢样钛Ti", ("钛", "Ti"), "confirmed", ""),
    "vmdvalue": ("钢样钒V", ("钒", "V"), "confirmed", ""),
    "nbmdvalue": ("钢样铌Nb", ("铌", "Nb"), "confirmed", ""),
    "wmdvalue": ("钢样钨W", ("钨", "W"), "confirmed", ""),
    "comdvalue": ("钢样钴Co", ("钴", "Co"), "confirmed", ""),
    "bmdvalue": ("钢样硼B", ("硼", "B"), "confirmed", ""),
    "camdvalue": ("钢样钙Ca", ("钙", "Ca"), "confirmed", ""),
    "sbmdvalue": ("钢样锑Sb", ("锑", "Sb"), "confirmed", ""),
    "asmdvalue": ("钢样砷As", ("砷", "As"), "confirmed", ""),
    "snmdvalue": ("钢样锡Sn", ("锡", "Sn"), "confirmed", ""),
    "pbmdvalue": ("钢样铅Pb", ("铅", "Pb"), "confirmed", ""),
    "bimdvalue": ("钢样铋Bi", ("铋", "Bi"), "confirmed", ""),
    "znmdvalue": ("钢样锌Zn", ("锌", "Zn"), "confirmed", ""),
    "insptime": ("钢样检验完成时间", ("检验时间", "化验完成时间"), "confirmed", ""),
    "smdvalue": ("钢样硫S", ("硫", "S"), "confirmed", ""),
    "crmdvalue": ("钢样铬Cr", ("铬", "Cr"), "confirmed", ""),
    "alismdvalue": ("钢样不溶铝结果", ("不溶铝",), "uncertain", "由字段与样本关系推断"),
    "alisinvalue": ("钢样不溶铝高精度结果", ("不溶铝原始值", "不溶铝高精度值"), "uncertain", "仪器/计算口径待确认"),
    "nmdvalue": ("钢样氮N", ("氮", "N"), "confirmed", ""),
    "ceq": ("钢样碳当量CEQ", ("碳当量", "CEQ"), "structural", "公式可能随钢种标准变化"),
    "businessdate": ("炼钢生产业务日期", ("生产日期", "业务日"), "confirmed", ""),
    "steelgrade": ("计划/申报钢种", ("钢种", "牌号"), "structural", ""),
    "judgingsteelgrade": ("化验判定钢种", ("判定钢种", "最终钢种"), "structural", ""),
    "heatno": ("炼钢炉位/工序代码字段", ("炉位代码", "工序代码"), "uncertain", "不是唯一炉号"),
    "prodcentercode": ("炼钢工序/加工中心编码", ("工序编码", "加工中心"), "structural", "精确中文映射待字典确认"),
    "publishtime": ("炼钢结果发布时间", ("发布时间", "结果时间"), "confirmed", ""),
    "receivesampleclass": ("炼钢接样班组", ("接样班组", "甲乙丙班"), "confirmed", ""),
    "furnacenumber": ("炼钢实际炉号/生产炉次号", ("实际炉号", "炼钢炉次"), "structural", "需与生产系统主键对账"),
    "receivesampletime": ("炼钢接样时间", ("接样时间", "样品到达时间"), "confirmed", ""),
    "prodname": ("产品/产线名称代码", ("产品代码", "产线代码"), "uncertain", "确切中文含义待字典确认"),
}


def describe_field(object_name: str, field: str) -> VariableSpec | None:
    if object_name in LAB_VIEW_FIELDS and field in LAB_VIEW_FIELDS[object_name]:
        return LAB_VIEW_FIELDS[object_name][field]
    if object_name in {
        "public.v_qpes_inner_batch_insp_final_sample",
        "public.v_qpes_mat_final",
    } and field in LAB_IRON_ELEMENTS:
        meaning, aliases = LAB_IRON_ELEMENTS[field]
        note = "asvalue历史覆盖较低，空值不是0" if field == "asvalue" else ""
        return VariableSpec(meaning, aliases, "confirmed", note)
    if object_name == "public.v_qpes_steel_final" and field in STEEL_FIELDS:
        meaning, aliases, confidence, note = STEEL_FIELDS[field]
        return VariableSpec(meaning, aliases, confidence, note)
    if object_name in OBJECT_FIELDS and field in OBJECT_FIELDS[object_name]:
        return OBJECT_FIELDS[object_name][field]
    if object_name == "public.batch_input":
        match = re.fullmatch(r"value_(\d{2})", field)
        if match:
            channel = int(match.group(1))
            return VariableSpec(
                f"第{channel}号料仓/称量通道投料值",
                (
                    f"{channel}号仓",
                    f"{channel}号料仓",
                    f"第{channel}号料仓",
                    f"通道{channel}",
                    f"第{channel}仓投料",
                    f"{channel}号仓投料",
                ),
                "structural",
                "是投料量，不是化学元素；物料需关联料仓历史",
            )
    if object_name == "public.inner_batch_insp_bb":
        match = re.fullmatch(r"value_(\d{2})", field)
        if match:
            element = IRON_ELEMENTS.get(int(match.group(1)))
            if element:
                return VariableSpec(element[0], element[1], "confirmed", "通常按质量百分含量")
    if object_name == "public.slag_inspection":
        match = re.fullmatch(r"value_(\d{2})", field)
        if match:
            number = int(match.group(1))
            return VariableSpec(
                f"旧炉渣检验编号指标{number}",
                (f"炉渣指标{number}", field),
                "unknown",
                "缺少旧表编号到化学成分映射，禁止猜测；优先使用命名炉渣视图",
            )
    return COMMON_FIELDS.get(field)


def escape_cell(value: Any) -> str:
    return (
        str(value)
        .replace("|", "\\|")
        .replace("\r", " ")
        .replace("\n", " ")
    )


def speech_example(object_spec: ObjectSpec, field: str, variable: VariableSpec) -> str:
    identifiers = "、".join(object_spec.identity_fields[:2])
    return (
        f"查一下{object_spec.speech_scope}的{variable.meaning}，"
        f"返回实际字段{field}，并带上{identifiers}。"
    )


def query_example(object_name: str, spec: ObjectSpec, first_field: str) -> str:
    variables = list(dict.fromkeys([*spec.identity_fields, first_field]))
    payload = {
        "tool": "query_imes_variables",
        "arguments": {
            "account_profile": spec.profile,
            "object_name": object_name,
            "variables": variables,
            "time_column": spec.time_field,
            "start_time": "2026-07-01 00:00:00",
            "end_time": "2026-07-28 00:00:00",
            "exact_filters": spec.exact_filter,
            "order_by": spec.time_field,
            "descending": True,
            "row_limit": 100,
        },
    }
    return json.dumps(payload, ensure_ascii=False, indent=2)


def build_appendix(
    source: dict[str, Any],
) -> tuple[str, dict[str, Any], dict[str, Any]]:
    sections = [
        START_MARKER,
        "",
        "## 6. 11个真实可读对象、315个实际变量逐项口语调用全集",
        "",
        "本节由真实只读目录自动生成。覆盖单位是“对象×字段”：同名字段在不同",
        "对象中分别登记，避免把铁水、炉渣、烧结矿与炼钢变量混用。",
        "",
        "固定调用规则：",
        "",
        "- 先用 `list_imes_business_objects(account_profile)` 复核实时可读目录；",
        "- 用 `query_imes_variables` 传入下表的实际字段名；",
        "- 时间范围固定为 `[start_time, end_time)`，即左闭右开；",
        "- `operations` 查炉次/投料/实绩/旧化验，`laboratory` 查最终化验视图；",
        "- 表中“待确认/unknown”只表示字段可读，不允许根据名称猜单位、枚举或成分；",
        "- 空值表示未检、未发布、不适用或历史缺失，不能自动当作0。",
        "",
    ]
    source_objects: list[dict[str, Any]] = []
    for account in source["accounts"]:
        for relation in account["relations"]:
            source_objects.append(
                {
                    "profile": account["account_key"],
                    "object": f"{relation['table_schema']}.{relation['table_name']}",
                    "columns": [
                        column["column_name"] for column in relation["columns"]
                    ],
                }
            )
    actual_objects = {item["object"] for item in source_objects}
    missing_specs = sorted(actual_objects - set(OBJECT_SPECS))
    extra_specs = sorted(set(OBJECT_SPECS) - actual_objects)
    undocumented: list[str] = []
    documented_keys: list[str] = []
    catalog_entries: list[dict[str, Any]] = []
    per_object: list[dict[str, Any]] = []
    for object_index, item in enumerate(source_objects, start=1):
        object_name = item["object"]
        spec = OBJECT_SPECS.get(object_name)
        if spec is None:
            continue
        sections.extend(
            [
                f"### 6.{object_index} `{object_name}`：{spec.label}",
                "",
                f"- 账号：`{spec.profile}`",
                f"- 用途：{spec.purpose}",
                f"- 推荐时间字段：`{spec.time_field}`",
                f"- 推荐主标识：`{' / '.join(spec.identity_fields)}`",
                f"- 典型精确条件：`{json.dumps(spec.exact_filter, ensure_ascii=False)}`",
                "",
                "单变量程序调用：把下面示例 `variables` 中最后一个字段替换为本节任意实际字段。",
                "",
                "```json",
                query_example(object_name, spec, item["columns"][0]),
                "```",
                "",
                "| 序号 | 实际变量 | 业务解释 | 口语别名 | 可直接对模型说 | MCP变量参数 | 可信度/边界 |",
                "|---:|---|---|---|---|---|---|",
            ]
        )
        object_documented = 0
        for field_index, field in enumerate(item["columns"], start=1):
            variable = describe_field(object_name, field)
            key = f"{object_name}.{field}"
            if variable is None:
                undocumented.append(key)
                variable = VariableSpec(
                    f"源字段{field}",
                    (field,),
                    "undocumented",
                    "未登记语义",
                )
            else:
                object_documented += 1
                documented_keys.append(key)
            catalog_entries.append(
                {
                    "account_profile": spec.profile,
                    "object": object_name,
                    "object_label": spec.label,
                    "field": field,
                    "meaning": variable.meaning,
                    "aliases": list(dict.fromkeys([*variable.aliases, field])),
                    "confidence": variable.confidence,
                    "note": variable.note or None,
                    "time_field": spec.time_field,
                    "identity_fields": list(spec.identity_fields),
                    "speech_example": speech_example(spec, field, variable),
                    "recommended_tool": "query_imes_variables",
                }
            )
            aliases = "、".join(dict.fromkeys([*variable.aliases, field]))
            boundary = variable.confidence
            if variable.note:
                boundary += f"；{variable.note}"
            sections.append(
                "| "
                + " | ".join(
                    [
                        str(field_index),
                        f"`{escape_cell(field)}`",
                        escape_cell(variable.meaning),
                        escape_cell(aliases),
                        escape_cell(speech_example(spec, field, variable)),
                        f'`variables=["{escape_cell(field)}"]`',
                        escape_cell(boundary),
                    ]
                )
                + " |"
            )
        sections.append("")
        per_object.append(
            {
                "profile": spec.profile,
                "object": object_name,
                "actual_fields": len(item["columns"]),
                "documented_fields": object_documented,
                "time_field": spec.time_field,
            }
        )
    sections.extend(
        [
            "## 7. 完整覆盖验收",
            "",
            f"- 实际可读对象：`{len(source_objects)}`",
            f"- 实际“对象×字段”：`{sum(len(item['columns']) for item in source_objects)}`",
            f"- 已登记业务解释与口语模板：`{len(documented_keys)}`",
            f"- 未登记项：`{len(undocumented)}`",
            "- 机器可读覆盖证据：`logs/imes_mcp_full_variable_coverage_20260727.json`。",
            "",
            END_MARKER,
        ]
    )
    manifest = {
        "requirement": "REQ-IMES-MCP-FULL-VARIABLE-TEMPLATES-20260727",
        "source": str(DEFAULT_SOURCE),
        "target": str(DEFAULT_TARGET),
        "actual_objects": len(source_objects),
        "actual_object_fields": sum(len(item["columns"]) for item in source_objects),
        "documented_object_fields": len(documented_keys),
        "missing_object_specs": missing_specs,
        "extra_object_specs": extra_specs,
        "undocumented_fields": undocumented,
        "per_object": per_object,
        "complete": (
            not missing_specs
            and not extra_specs
            and not undocumented
            and len(documented_keys)
            == sum(len(item["columns"]) for item in source_objects)
        ),
    }
    catalog = {
        "version": "2026-07-27",
        "requirement": "REQ-IMES-MCP-FULL-VARIABLE-TEMPLATES-20260727",
        "source": str(DEFAULT_SOURCE),
        "object_count": len(source_objects),
        "entry_count": len(catalog_entries),
        "entries": catalog_entries,
    }
    return "\n".join(sections) + "\n", manifest, catalog


def replace_generated_section(current: str, generated: str) -> str:
    if START_MARKER in current and END_MARKER in current:
        pattern = re.compile(
            re.escape(START_MARKER) + r".*?" + re.escape(END_MARKER),
            re.DOTALL,
        )
        return pattern.sub(generated.strip(), current).rstrip() + "\n"
    return current.rstrip() + "\n\n" + generated


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="生成IMES 11对象315变量逐项MCP口语调用模板。"
    )
    parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE)
    parser.add_argument("--target", type=Path, default=DEFAULT_TARGET)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--catalog", type=Path, default=DEFAULT_CATALOG)
    parser.add_argument(
        "--check",
        action="store_true",
        help="仅验证当前文档与生成内容一致，不写文件。",
    )
    return parser


def main() -> int:
    args = build_parser().parse_args()
    source = json.loads(args.source.read_text(encoding="utf-8"))
    generated, manifest, catalog = build_appendix(source)
    current = args.target.read_text(encoding="utf-8")
    updated = replace_generated_section(current, generated)
    manifest["target_up_to_date"] = current == updated
    args.manifest.parent.mkdir(parents=True, exist_ok=True)
    args.manifest.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    catalog_text = json.dumps(catalog, ensure_ascii=False, indent=2) + "\n"
    if args.check:
        catalog_up_to_date = (
            args.catalog.exists()
            and args.catalog.read_text(encoding="utf-8") == catalog_text
        )
        manifest["catalog_up_to_date"] = catalog_up_to_date
        print(json.dumps(manifest, ensure_ascii=False))
        return (
            0
            if manifest["complete"]
            and manifest["target_up_to_date"]
            and catalog_up_to_date
            else 1
        )
    args.target.write_text(updated, encoding="utf-8")
    args.catalog.parent.mkdir(parents=True, exist_ok=True)
    args.catalog.write_text(catalog_text, encoding="utf-8")
    manifest["target_up_to_date"] = True
    manifest["catalog_up_to_date"] = True
    args.manifest.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(json.dumps(manifest, ensure_ascii=False))
    return 0 if manifest["complete"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
