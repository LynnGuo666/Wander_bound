"""Original, versioned local scrapbook art directions.

Written from the product requirements and user visual references. No external
skill prompts or preset code are used. Titles are drawn by the application.
"""
from __future__ import annotations

import copy
import hashlib
import json
import io
import os
import unicodedata
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from .contracts import ContractError


LAYOUT_VERSION = "1.0.0"
LAYOUT = (
    "将输入照片重新创作成一张精致完整的旅行手帐图片，横向3:2。"
    "俯视平面的单张米白纸，不要桌面、书本、相框或透视。"
    "纸面左侧约三分之二是一幅完整的大场景插画，保持原照片的地形、主体、季节和空间关系，"
    "但所有景物都要按指定风格重新绘制，不要保留摄影质感。"
    "右侧留白处排布几枚独立小贴纸：只从这张照片确实可见的关键元素中提取，"
    "例如照片中的树、山体或云；不要添加照片没有的人物、动物、建筑或地标。"
    "贴纸与左侧主画使用完全一致的画风，带窄米白轮廓和轻微落影，互不遮挡。"
    "主画与贴纸之间留呼吸空间，整体丰富但整洁。保留底部一条空白纸边。"
    "不要生成任何标题、标签、字母、数字、水印或装饰性文字。"
)

_STYLES = {
    "watercolor": ("水彩", "柔和渗色与细腻纸纹", 2026092901,
                   "全场景与贴纸用透明水彩绘制：湿画法的柔和渗色、叠色、自然留白、"
                   "淡淡铅笔结构与冷压纸颗粒。树叶用流动的色块，山峦有透明色层，避免厚重塑料和硬切纸边。"),
    "papercut": ("层叠剪纸", "纸层、切边与浅浮雕投影", 2026092902,
                 "全场景与贴纸都由多层彩色卡纸剪切叠成：清晰切边、可辨纸张厚度、"
                 "不同高度的层叠纸片和柔和投影。山体是分层轮廓，树冠由成簇剪纸组成。"
                 "颜色平整，纸纤维细腻，不要水彩笔触、毛线或塑料。"),
    "clay": ("黏土", "圆润塑形与细小手工压痕", 2026092903,
             "全场景与贴纸都用手工彩色聚合物黏土塑成微缩浅浮雕：圆润饱满的山丘、"
             "揉捏成形的树冠与叶片，细微指压痕、平滑致密表面、柔和侧光和体积阴影。"
             "这是不带绒毛的实心黏土，绝对不要毛毡、羊毛、针织、织物纤维、纸层或水彩。"
             "保留原图场景，而不是把主画变成散放的玩具。"),
    "halftone": ("网点漫画", "墨线、套色与印刷网点", 2026092904,
                 "全场景与贴纸采用复古彩色网点漫画：明确的粗细墨线、平涂套色、"
                 "能看清的圆形印刷网点与少量排线，阴影由网点密度表现。"
                 "使用有活力但协调的有限配色，不要对话框、拟声词、文字、照片或水彩晕染。"),
    "pixel": ("像素", "方形网格与有限调色板", 2026092905,
              "全场景与贴纸使用精细像素画：统一可见的方形像素网格、阶梯状轮廓、"
              "有限调色板、像素簇明暗与少量有序抖动。山、树与云保持可辨细节。"
              "像素边缘锐利，不做平滑抗锯齿，不使用水彩、模糊渐变或摄影纹理。"),
}


def style_snapshot(style_id: str) -> dict:
    if not isinstance(style_id, str) or style_id not in _STYLES:
        raise ContractError("STYLE_INVALID", "请选择水彩、层叠剪纸、黏土、网点漫画或像素")
    name, description, seed, direction = _STYLES[style_id]
    prompt = LAYOUT + direction
    version = "1.0.0"
    if style_id in {"watercolor", "papercut"}:
        version = "1.1.0"
        prompt = (
            direction + "\n把整张照片彻底重新设计成简化的手作插画，远山、草坡、树林全部重新塑造，"
            "只保留场景布局、秋日颜色和可辨主体，不保留原照片像素或摄影纹理。"
            "减少细碎草叶与树枝，用大块清晰形状概括；画面每一处都必须是这个画风。"
            "成品是一张平面的米白纸旅行手帐，横向3:2，主画占左侧约三分之二，"
            "右侧放几枚同画风的山、树、云小贴纸，这些元素必须来自原场景。"
            "四边与底部留白，贴纸有窄白边。整页无任何文字。"
        )
    result = {"id": style_id, "version": version, "layoutVersion": LAYOUT_VERSION,
              "name": name, "description": description, "recommendedSeed": seed,
              "prompt": prompt}
    result["sha256"] = hashlib.sha256(json.dumps(result, ensure_ascii=False, sort_keys=True,
                                                separators=(",", ":")).encode()).hexdigest()
    return copy.deepcopy(result)


def style_catalog() -> list[dict]:
    return [{key: value for key, value in style_snapshot(style_id).items() if key != "prompt"}
            for style_id in _STYLES]


def title_contract(title: object) -> tuple[str, dict | None]:
    if not isinstance(title, str) or len(title) > 32 or any(
            unicodedata.category(ch).startswith("C") for ch in title):
        raise ContractError("TITLE_INVALID", "标题最多32字符，不能包含换行或控制字符")
    title = title.strip()
    if not title:
        return "", None
    candidates = [os.getenv("SCRAPBOOK_FONT_PATH", ""),
                  "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
                  "/System/Library/Fonts/PingFang.ttc",
                  "/System/Library/Fonts/Supplemental/Arial Unicode.ttf"]
    for path in candidates:
        if not path or not Path(path).is_file():
            continue
        try:
            font = ImageFont.truetype(path, 36)
            missing = font.getmask("\U0010ffff")
            signature = (missing.size, bytes(missing))
            if any((mask.size, bytes(mask)) == signature
                   for char in title if not char.isspace() for mask in [font.getmask(char)]):
                continue
            return title, {"path": path, "sha256": hashlib.sha256(Path(path).read_bytes()).hexdigest(),
                           "index": 0, "layoutVersion": "caption-1.0.0"}
        except OSError:
            continue
    raise ContractError("TITLE_FONT_UNAVAILABLE", "本机字体不能完整显示此标题，请修改标题或配置中文字体", 503)


def render_page(raw: bytes, title: str, font_snapshot: dict | None) -> tuple[bytes, bytes, dict]:
    with Image.open(io.BytesIO(raw)) as source:
        source.load()
        image = source.convert("RGB")
    width, height = image.size
    if width * 2 != height * 3 or width < 300:
        raise ContractError("OUTPUT_ASPECT_INVALID", "模型输出不是有效3:2横版图片", 502)
    if title:
        if not font_snapshot or font_snapshot.get("layoutVersion") != "caption-1.0.0":
            raise ContractError("TITLE_FONT_CHANGED", "任务标题排版快照无效", 409)
        path = Path(font_snapshot["path"])
        if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != font_snapshot["sha256"]:
            raise ContractError("TITLE_FONT_CHANGED", "排队后的字体已变化，请恢复任务字体", 409)
        page = Image.new("RGB", image.size, "#f7f3e9")
        footer = max(52, height // 10)
        art_height = height - footer
        art_width = round(width * art_height / height)
        page.paste(image.resize((art_width, art_height), Image.Resampling.LANCZOS), ((width - art_width) // 2, 0))
        draw = ImageDraw.Draw(page)
        size = max(18, round(height * .037))
        while True:
            font = ImageFont.truetype(str(path), size, index=font_snapshot.get("index", 0))
            box = draw.textbbox((0, 0), title, font=font)
            if box[2] - box[0] <= width * .90 and box[3] - box[1] <= footer * .7:
                break
            size -= 1
            if size < 12:
                raise ContractError("TITLE_TOO_WIDE", "标题无法清晰排入图片，请缩短标题")
        draw.text(((width - (box[2] - box[0])) / 2 - box[0],
                   art_height + (footer - (box[3] - box[1])) / 2 - box[1]),
                  title, font=font, fill="#504b42")
        image = page
    full = io.BytesIO(); image.save(full, "JPEG", quality=95, optimize=True)
    image.thumbnail((480, 320))
    thumb = io.BytesIO(); image.save(thumb, "JPEG", quality=88, optimize=True)
    return full.getvalue(), thumb.getvalue(), {"width": width, "height": height, "mimeType": "image/jpeg"}
