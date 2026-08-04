"""Generate the deterministic Chinese multi-task thermal-state flowchart."""

from __future__ import annotations

import math
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "reports" / "assets" / "铁水Si联合热状态算法流程图_20260727.png"
FONT_DIR = Path("C:/Windows/Fonts")
HEITI_PATH = FONT_DIR / "simhei.ttf"
SONGTI_PATH = FONT_DIR / "simsun.ttc"

WIDTH = 2400
HEIGHT = 1350


def font(path: Path, size: int):
    return ImageFont.truetype(str(path), size=size)


def centered_text(
    draw: ImageDraw.ImageDraw,
    box: tuple[int, int, int, int],
    text: str,
    *,
    text_font,
    fill: str,
    y_ratio: float,
) -> None:
    left, top, right, bottom = box
    target_y = top + int((bottom - top) * y_ratio)
    text_box = draw.multiline_textbbox(
        (0, 0),
        text,
        font=text_font,
        spacing=8,
        align="center",
    )
    text_width = text_box[2] - text_box[0]
    text_height = text_box[3] - text_box[1]
    draw.multiline_text(
        ((left + right - text_width) / 2, target_y - text_height / 2),
        text,
        font=text_font,
        fill=fill,
        spacing=8,
        align="center",
    )


def add_box(
    draw: ImageDraw.ImageDraw,
    box: tuple[int, int, int, int],
    *,
    title: str,
    detail: str,
    face: str,
    edge: str,
    dashed: bool = False,
) -> None:
    if dashed:
        draw.rounded_rectangle(
            box,
            radius=30,
            fill=face,
            outline=edge,
            width=5,
        )
        left, top, right, bottom = box
        dash = 22
        gap = 14
        for x in range(left + 26, right - 26, dash + gap):
            draw.line((x, top, min(x + dash, right - 26), top), fill="white", width=6)
            draw.line((x, bottom, min(x + dash, right - 26), bottom), fill="white", width=6)
        for y in range(top + 26, bottom - 26, dash + gap):
            draw.line((left, y, left, min(y + dash, bottom - 26)), fill="white", width=6)
            draw.line((right, y, right, min(y + dash, bottom - 26)), fill="white", width=6)
    else:
        draw.rounded_rectangle(
            box,
            radius=30,
            fill=face,
            outline=edge,
            width=5,
        )
    centered_text(
        draw,
        box,
        title,
        text_font=font(HEITI_PATH, 52),
        fill="#17212B",
        y_ratio=0.36,
    )
    centered_text(
        draw,
        box,
        detail,
        text_font=font(SONGTI_PATH, 34),
        fill="#34495E",
        y_ratio=0.72,
    )


def add_arrow(
    draw: ImageDraw.ImageDraw,
    start: tuple[int, int],
    end: tuple[int, int],
) -> None:
    color = "#52616B"
    width = 7
    draw.line((*start, *end), fill=color, width=width)
    angle = math.atan2(end[1] - start[1], end[0] - start[0])
    arrow_length = 34
    half_width = 18
    base_x = end[0] - arrow_length * math.cos(angle)
    base_y = end[1] - arrow_length * math.sin(angle)
    perp_x = half_width * math.sin(angle)
    perp_y = -half_width * math.cos(angle)
    points = [
        end,
        (int(base_x + perp_x), int(base_y + perp_y)),
        (int(base_x - perp_x), int(base_y - perp_y)),
    ]
    draw.polygon(points, fill=color)


def build_flowchart(output: Path = OUTPUT) -> Path:
    output.parent.mkdir(parents=True, exist_ok=True)
    image = Image.new("RGB", (WIDTH, HEIGHT), "white")
    draw = ImageDraw.Draw(image)

    title = "基于可解释热状态神经元的多任务预测流程"
    title_font = font(HEITI_PATH, 66)
    title_box = draw.textbbox((0, 0), title, font=title_font)
    draw.text(
        ((WIDTH - (title_box[2] - title_box[0])) / 2, 35),
        title,
        font=title_font,
        fill="#102A43",
    )

    input_box = (330, 185, 2070, 365)
    neuron_box = (520, 475, 1880, 655)
    latent_box = (750, 755, 1650, 910)
    temperature_box = (70, 1060, 720, 1280)
    silicon_box = (875, 1060, 1525, 1280)
    state_box = (1680, 1060, 2330, 1280)

    add_box(
        draw,
        input_box,
        title="传感器趋势 ＋ 炉料/炉渣 ＋ 前序炉次结果",
        detail="多时间窗趋势 · 已发布化验 · 严格历史可见性",
        face="#EAF2F8",
        edge="#2874A6",
    )
    add_box(
        draw,
        neuron_box,
        title="可解释热状态神经元",
        detail="热量输入｜煤气利用｜透气性｜空间场｜波动冲击｜料柱运动",
        face="#E8F6F3",
        edge="#148F77",
    )
    add_box(
        draw,
        latent_box,
        title="炉内潜在热状态",
        detail="共享概念层 / 隐状态表示",
        face="#FCF3CF",
        edge="#B7950B",
    )
    add_box(
        draw,
        temperature_box,
        title="铁水温度分布",
        detail="P10 / P50 / P90\n待真实温度标签",
        face="#FDEDEC",
        edge="#CB4335",
        dashed=True,
    )
    add_box(
        draw,
        silicon_box,
        title="Si含量分布",
        detail="P10 / P50 / P90\nV13已训练",
        face="#E9F7EF",
        edge="#239B56",
    )
    add_box(
        draw,
        state_box,
        title="热状态概率",
        detail="下行 / 正常 / 上行\n待联合标签",
        face="#FDEDEC",
        edge="#CB4335",
        dashed=True,
    )

    add_arrow(draw, (1200, 365), (1200, 470))
    add_arrow(draw, (1200, 655), (1200, 750))
    add_arrow(draw, (1030, 910), (395, 1055))
    add_arrow(draw, (1200, 910), (1200, 1055))
    add_arrow(draw, (1370, 910), (2005, 1055))

    note = "实线：当前已实现分支　　虚线：取得可信标签后训练的联合任务分支"
    note_font = font(SONGTI_PATH, 30)
    note_box = draw.textbbox((0, 0), note, font=note_font)
    draw.text(
        ((WIDTH - (note_box[2] - note_box[0])) / 2, 1300),
        note,
        font=note_font,
        fill="#5D6D7E",
    )

    image.save(output, format="PNG", optimize=True)
    return output


if __name__ == "__main__":
    print(build_flowchart())
