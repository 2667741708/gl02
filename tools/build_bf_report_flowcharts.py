"""Generate Visio-style flowcharts for the blast-furnace decision report."""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


ROOT = Path(__file__).resolve().parents[1]
ASSET_DIR = ROOT / "docs" / "assets" / "bf_decision_report_v2_4"
FONT_BOLD = Path("C:/Windows/Fonts/simhei.ttf")
FONT_BODY = Path("C:/Windows/Fonts/simsun.ttc")

BG = "#F4F7FA"
NAVY = "#17324D"
BLUE = "#2F75B5"
TEAL = "#2F756E"
GREEN = "#4D8B61"
AMBER = "#C58A2B"
PURPLE = "#685A9D"
RED = "#A84C47"
LINE = "#A8B5C2"
WHITE = "#FFFFFF"
PALE_BLUE = "#E9F2FA"
PALE_GREEN = "#EAF4EE"
PALE_AMBER = "#FAF1DF"
PALE_PURPLE = "#F0EDF7"


def font(size: int, bold: bool = False):
    path = FONT_BOLD if bold else FONT_BODY
    return ImageFont.truetype(str(path), size=size)


def wrap_cn(text: str, max_chars: int) -> list[str]:
    lines: list[str] = []
    for paragraph in text.split("\n"):
        while len(paragraph) > max_chars:
            split = max_chars
            for mark in "，、；： ":
                pos = paragraph.rfind(mark, 0, max_chars + 1)
                if pos >= max_chars // 2:
                    split = pos + 1
                    break
            lines.append(paragraph[:split])
            paragraph = paragraph[split:]
        lines.append(paragraph)
    return [line for line in lines if line]


def center_text(draw, box, text, size=34, bold=False, color=NAVY, max_chars=11):
    lines = wrap_cn(text, max_chars)
    f = font(size, bold)
    spacing = 10
    metrics = [draw.textbbox((0, 0), line, font=f) for line in lines]
    heights = [b[3] - b[1] for b in metrics]
    total = sum(heights) + spacing * (len(lines) - 1)
    y = box[1] + (box[3] - box[1] - total) / 2
    for line, bounds, h in zip(lines, metrics, heights):
        w = bounds[2] - bounds[0]
        x = box[0] + (box[2] - box[0] - w) / 2
        draw.text((x, y), line, font=f, fill=color)
        y += h + spacing


def node(draw, box, title, subtitle="", fill=WHITE, outline=BLUE, title_color=NAVY):
    x1, y1, x2, y2 = box
    draw.rounded_rectangle((x1 + 9, y1 + 11, x2 + 9, y2 + 11), radius=26, fill="#D7E0E8")
    draw.rounded_rectangle(box, radius=26, fill=fill, outline=outline, width=5)
    title_box = (x1 + 16, y1 + 16, x2 - 16, y1 + 78)
    center_text(draw, title_box, title, 34, True, title_color, 14)
    if subtitle:
        body_box = (x1 + 24, y1 + 82, x2 - 24, y2 - 18)
        center_text(draw, body_box, subtitle, 27, False, NAVY, 18)


def arrow(draw, start, end, color=BLUE, width=8):
    draw.line((start, end), fill=color, width=width)
    x1, y1 = start
    x2, y2 = end
    if abs(x2 - x1) >= abs(y2 - y1):
        sign = 1 if x2 > x1 else -1
        pts = [(x2, y2), (x2 - sign * 28, y2 - 18), (x2 - sign * 28, y2 + 18)]
    else:
        sign = 1 if y2 > y1 else -1
        pts = [(x2, y2), (x2 - 18, y2 - sign * 28), (x2 + 18, y2 - sign * 28)]
    draw.polygon(pts, fill=color)


def title(draw, text, subtitle):
    draw.text((90, 55), text, font=font(55, True), fill=NAVY)
    draw.text((92, 128), subtitle, font=font(27), fill="#4D6275")
    draw.line((90, 180, 2310, 180), fill=BLUE, width=5)


def build_system_flow():
    image = Image.new("RGB", (2400, 1400), BG)
    draw = ImageDraw.Draw(image)
    title(
        draw,
        "高炉工艺大模型智能决策系统总体流程",
        "真实运行数据、MCP工具、专家知识、27B领域大模型与多智能体协同形成可解释辅助决策",
    )

    nodes = {
        "sources": (90, 260, 430, 570),
        "mcp": (520, 260, 860, 570),
        "context": (950, 260, 1290, 570),
        "model": (1380, 260, 1720, 570),
        "answer": (1810, 260, 2310, 570),
        "knowledge": (950, 750, 1290, 1060),
        "agents": (1380, 750, 1720, 1060),
        "decision": (1810, 750, 2310, 1060),
    }
    node(draw, nodes["sources"], "真实高炉数据", "过程数据\n设备状态\n质量信息\n操作与班次记录", PALE_BLUE, BLUE)
    node(draw, nodes["mcp"], "MCP工具服务", "按权限查询\n趋势与质量分析\n资料与报表检索", PALE_BLUE, BLUE)
    node(draw, nodes["context"], "炉况上下文", "当前事实\n近期变化\n已有炉况判断\n任务与权限", PALE_GREEN, TEAL)
    node(draw, nodes["model"], "27B领域大模型", "理解任务\n融合事实与知识\n生成解释与候选方向", PALE_PURPLE, PURPLE)
    node(draw, nodes["answer"], "现场智能交互", "总览与研判\n参数优化\n趋势分析\n知识问答", PALE_GREEN, GREEN)
    node(draw, nodes["knowledge"], "高炉专家知识库", "工艺知识\n专家经验\n企业制度\n历史复盘", PALE_AMBER, AMBER)
    node(draw, nodes["agents"], "多智能体编排", "任务分解\n角色协作\n冲突协调\n班次承接", PALE_PURPLE, PURPLE)
    node(draw, nodes["decision"], "决策与安全闭环", "多目标权衡\n帕累托候选\n人工确认\n审计与反馈", "#F8EAEA", RED)

    arrow(draw, (430, 415), (520, 415))
    arrow(draw, (860, 415), (950, 415))
    arrow(draw, (1290, 415), (1380, 415))
    arrow(draw, (1720, 415), (1810, 415))
    arrow(draw, (1120, 750), (1120, 570), AMBER)
    arrow(draw, (1550, 570), (1550, 750), PURPLE)
    arrow(draw, (1720, 905), (1810, 905), RED)
    arrow(draw, (2060, 750), (2060, 570), GREEN)
    arrow(draw, (1810, 1010), (1720, 1010), "#667788", 6)

    draw.rounded_rectangle((90, 1170, 2310, 1315), radius=24, fill=WHITE, outline=LINE, width=3)
    center_text(
        draw,
        (115, 1190, 2285, 1295),
        "全过程保留数据时间、来源、工具状态、知识证据、人工确认和任务记录；系统提供辅助决策，不直接控制生产设备。",
        29,
        False,
        NAVY,
        52,
    )
    path = ASSET_DIR / "06_system_decision_flow.png"
    image.save(path, quality=95)
    return path


def build_finetune_flow():
    image = Image.new("RGB", (2400, 1400), BG)
    draw = ImageDraw.Draw(image)
    title(
        draw,
        "1.5TB高炉领域数据参数高效微调流程",
        "冻结27B基础模型主体参数，以LoRA/QLoRA适配器学习领域能力，并通过通用能力回归门控制发布质量",
    )

    top = [
        ((80, 260, 400, 560), "1.5TB领域数据", "运行数据\n工艺文档\n专家问答\n复盘材料", PALE_BLUE, BLUE),
        ((480, 260, 800, 560), "数据治理", "清洗去重\n脱敏与质量检查\n时间与来源标记", PALE_BLUE, BLUE),
        ((880, 260, 1200, 560), "训练数据组织", "领域语料\n指令样本\n工具调用样本\n通用能力样本", PALE_GREEN, TEAL),
        ((1280, 260, 1600, 560), "参数高效微调", "冻结主体参数\nLoRA/QLoRA适配\n分阶段训练", PALE_PURPLE, PURPLE),
        ((1680, 260, 2000, 560), "双轨能力评测", "高炉专业能力\n通用理解与推理\n安全与工具使用", PALE_AMBER, AMBER),
        ((2080, 260, 2320, 560), "受控发布", "适配器版本\n灰度验证\n可回退部署", "#F8EAEA", RED),
    ]
    for box, t, s, fill, outline in top:
        node(draw, box, t, s, fill, outline)
    for left, right in zip(top, top[1:]):
        arrow(draw, (left[0][2], 410), (right[0][0], 410))

    node(
        draw,
        (250, 760, 770, 1090),
        "27B基础模型保持",
        "主体参数冻结\n原有通用知识与推理能力保留在基础模型中\n领域能力由适配参数承载",
        PALE_GREEN,
        GREEN,
    )
    node(
        draw,
        (940, 760, 1460, 1090),
        "能力保持策略",
        "混入通用任务样本\n控制训练强度\n领域与通用任务联合回归\n未达门槛不发布",
        PALE_AMBER,
        AMBER,
    )
    node(
        draw,
        (1630, 760, 2150, 1090),
        "上线后持续验证",
        "真实业务影子评测\n专家复核\n漂移与失败样本回收\n版本回退",
        PALE_PURPLE,
        PURPLE,
    )
    arrow(draw, (1440, 560), (510, 760), GREEN, 7)
    arrow(draw, (1680, 560), (1200, 760), AMBER, 7)
    arrow(draw, (2200, 560), (1890, 760), PURPLE, 7)
    arrow(draw, (770, 925), (940, 925), GREEN)
    arrow(draw, (1460, 925), (1630, 925), PURPLE)

    draw.rounded_rectangle((170, 1190, 2230, 1320), radius=24, fill=WHITE, outline=LINE, width=3)
    center_text(
        draw,
        (200, 1205, 2200, 1305),
        "“不损失原有智力水平”通过冻结主体参数、通用任务混合和发布前回归评测来保障；只有专业能力提升且通用能力不退化的版本才进入受控发布。",
        29,
        False,
        NAVY,
        50,
    )
    path = ASSET_DIR / "07_efficient_finetune_flow.png"
    image.save(path, quality=95)
    return path


if __name__ == "__main__":
    ASSET_DIR.mkdir(parents=True, exist_ok=True)
    print(build_system_flow())
    print(build_finetune_flow())
