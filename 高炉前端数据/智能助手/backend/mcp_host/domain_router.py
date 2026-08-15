"""Deterministic, low-latency routing from business language to MCP services."""

from __future__ import annotations

from dataclasses import dataclass
import re

from .server_registry import McpServerRegistry


@dataclass(frozen=True)
class DomainSelection:
    server_ids: tuple[str, ...]
    matched_domains: tuple[str, ...]
    reasons: tuple[str, ...]


IMES_TERMS = (
    "炉次", "鸬鹚", "炉号", "铁次", "铁水", "硅含量", "铁水硅", "炉渣", "渣样", "化验",
    "取样", "试样", "进料", "烧结矿", "原料成分", "上一炉", "前一炉",
    "这炉", "这一炉", "那炉", "硅", "锰", "磷", "硫", "成分", "含量",
    "meltno", "imes", "mes",
)
GL02_TERMS = (
    "顶压", "炉顶压力", "风量", "风温", "风压", "压差", "透气", "料线", "探尺",
    "炉温", "炉体温度", "静压力", "喷煤", "富氧", "传感器",
    "趋势", "走势", "曲线", "矩阵", "热力矩阵", "温度矩阵", "矩阵图",
    # Canonical point identifiers are valid user language too.  Keep the
    # explicit P_top trigger here so a mixed IMES + GL02 request cannot attach
    # only IMES merely because the user omitted the Chinese word “顶压”.
    "p_top", "pspace", "gl02",
)
DIAGNOSIS_TERMS = (
    "管道分数", "炉况分数", "诊断分数", "炉况评分", "前几次炉况", "历史炉况分数",
)
BODY_TEMPERATURE_TERMS = (
    "炉身温度", "炉身", "炉腹温度", "炉缸温度", "T_body",
    "C点温度", "C点的温度", "C点炉温", "点温度", "层温度", "层C点",
)
IMES_WEB_TERMS = (
    "imes web", "mes web", "web端", "web查询", "web数据", "web状态", "网页", "网页端", "网页查询", "网页数据库", "页面数据",
)


def _contains_any(text: str, terms: tuple[str, ...]) -> bool:
    lowered = text.lower()
    return any(term.lower() in lowered for term in terms)


def select_mcp_servers(question: str, registry: McpServerRegistry) -> DomainSelection:
    """Select one or more configured services without asking the LLM to discover them."""

    text = str(question or "")
    # A spoken heat suffix such as “072这炉” is MES intent even when the
    # question omits the words 炉次/铁水.
    spoken_heat = bool(re.search(r"(?<!\d)\d{2,4}\s*(?:这炉|那炉|炉|炉次|号炉)", text))
    imes = _contains_any(text, IMES_TERMS) or spoken_heat
    gl02 = _contains_any(text, GL02_TERMS)
    diagnosis = _contains_any(text, DIAGNOSIS_TERMS)
    spoken_body_layer = bool(
        "温度" in text
        and re.search(
            r"第?\s*(?:[7-9]|1[0-6])\s*层(?:\s*(?:到|至|-|—|－)\s*第?\s*(?:[7-9]|1[0-6])\s*层)?",
            text,
        )
    )
    body_temperature = _contains_any(text, BODY_TEMPERATURE_TERMS) or spoken_body_layer
    imes_web = _contains_any(text, IMES_WEB_TERMS)
    selected_domains: list[str] = []
    reasons: list[str] = []
    if imes:
        selected_domains.extend(("heat", "hot_metal", "slag", "feed", "imes"))
        reasons.append("命中炉次/化验/MES业务语义")
    if gl02:
        selected_domains.extend(("sensor", "chart", "report", "catalog"))
        reasons.append("命中GL02传感器/趋势业务语义")
    if diagnosis:
        selected_domains.append("diagnosis")
        reasons.append("命中历史炉况分数语义")
    if body_temperature:
        selected_domains.append("body_temperature")
        reasons.append("命中炉身/炉体温度语义")
    if imes_web:
        selected_domains.append("imes_web")
        reasons.append("明确要求通过IMES Web只读接口")

    enabled = registry.enabled_servers()
    if not selected_domains:
        defaults = tuple(server.server_id for server in enabled if server.default)
        return DomainSelection(defaults, ("default",), ("未命中专用领域，使用默认数据服务",))

    domain_set = set(selected_domains)
    server_ids = tuple(
        server.server_id for server in enabled if domain_set.intersection(server.domains)
    )
    if not server_ids:
        defaults = tuple(server.server_id for server in enabled if server.default)
        return DomainSelection(defaults, tuple(dict.fromkeys(selected_domains)), ("目标领域未配置，回退默认服务",))
    return DomainSelection(server_ids, tuple(dict.fromkeys(selected_domains)), tuple(reasons))
