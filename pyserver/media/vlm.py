"""VLM 包装层：把照片发给多模态 LLM 做语义打标 + 选片打分。

按 OpenAI 兼容 ``/v1/chat/completions`` 形态调用：图片以 base64 data-URI 进 user 消息，
prompt 约束模型只返回结构化 JSON。``base_url`` / ``model`` / ``api_key`` 全走 env，默认值
见 ``vision.py``（与精修共用同一台 Spark vLLM）；本服务只读 env，不硬编码任何密钥。

识别或解析失败抛 :class:`VLMError`，不阻断上传——上层据此降级为只用 L0+EXIF。
L0（blur/exposure/dhash）先粗筛，本层在候选集上叠加"语义废片/决定性瞬间/保留价值"。
"""
from __future__ import annotations

import base64
import io
import json
import os
import re
import time

import httpx
from PIL import Image, ImageOps

from .vision import vision_base_url, vision_model

# 单次请求的读超时。实测一张图打标 53-80 秒，模型刚被调度器卸载时首张要到 180 秒；
# 60 秒是接 StepFun 时留下的值，第一张必然超时，重试三次全撞线这张就丢了。
DEFAULT_TIMEOUT = float(os.getenv("PYSERVER_VLM_TIMEOUT", "180"))


def _first_env(*names: str) -> str | None:
    """返回第一个已设置的变量，没有则 None。选优侧可用 PYSERVER_VLM_* 覆盖共享默认值。"""
    for name in names:
        value = os.getenv(name)
        if value:
            return value
    return None


class VLMError(RuntimeError):
    pass


class _Retry(VLMError):
    """可重试的失败（网络抖动 / 429 / 5xx / 输出解析失败）。"""


# 打标 + 选片打分的输出契约。一次调用同时拿"内容标签"和"选优分"，避免大量照片跑两遍。
# 字段覆盖三类用途：
#  - 打标/动线：scene/activity/people/objects/setting/time/weather/location_clue/ocr/mood
#  - 选优：quality.{composition,aesthetic,highlight,trash,keep}
#  - 补 GPS 缺失：location_clue + ocr（无 EXIF 位置时从画面推断）
# scene 枚举对齐动线节点：出发→机场→飞机→交通→吃喝→见朋友→景点。
TAG_INSTRUCTION = """你是旅行相册的选片与打标助手。这张照片来自一场旅行，请同时做两件事：打标（描述内容，让我事后能重建“何时在哪发生了什么"）和打分（判断保留价值，我要据此在几千张里横向比较、排序筛选，并挑出剪进回忆视频的亮点）。

下面每个字段都可能对某张照片不适用：不适用或看不出时，用对应的 unknown / null / 空数组，不要为了填满而编造。

只输出一个 JSON 对象，不要 markdown 代码围栏、不要前后解释：
{
  "scene": "这是什么场景，一句简短中文，要能区分同一场景里的不同机位和状态。别用同一个词概括全部：同样是街头，路过拍的和站着拍的不同；同样是展台，拍全景的和拍展品的不同。拿不准具体差别时，宁可多写两个字（「展台入口人群」「地铁口地面视角」）也不要笼统写成「街头漫步」。",
  "activity": "正在做的事，一两个词，如 用餐/候机/合影/行走/赏景/购物/休息。画面里没有人的明确动作（纯风景、空镜、静物）时填 unknown，不要用「漫步」这类万能词凑数。",
  "people": {"present": 有无可见的人(含背影/局部), "count": 人数, "emotion": "happy/excited/calm/neutral/tired，无人则 null"},
  "objects": ["关键物体或地标，中文，最多5个；几乎没有可识别物体可留空数组"],
  "setting": {"indoor": 室内或室外, "environment": "city/nature/mixed/unknown"},
  "time": "morning/day/golden-hour/night，拿不准填 unknown",
  "weather": "clear/cloudy/rain/snow/fog，拿不准填 unknown",
  "ocr": ["能读出的画面文字(路牌/招牌/菜单/门牌)——常是定位和还原事件的关键，读不出留空数组"],
  "location_clue": "从画面推断的地点(海边/雪山/古镇/商业街/机场)，没有 GPS 时靠它补地点，看不出填 null",
  "mood": "画面传达的情绪氛围一词，用中文，如 宁静/震撼/温馨/欢乐/孤独/疲惫/热闹；画面没有明显情绪（普通风景/静物/空镜）时填 unknown，不要硬编一个，也不要填 calm 这类英文词",
  "quality": {
    "composition": "构图 0-5：5=主体突出、平衡有设计感；3=中规中矩；1=杂乱或主体不清晰",
    "aesthetic": "美观 0-5：5=光影色彩出众、想当壁纸；3=普通日常；1=明显难看",
    "highlight": "true/false，满足任一条即 true：罕见的情感/事件高潮（欢呼、拥抱、烟花、日出、惊喜）、或时机与构图俱佳的决定性瞬间。这类会剪进回忆视频当亮点。一批普通照片里，通常只有少数几张够得上，不可能张张都是。",
    "trash": "true/false，满足任一条即 true，这类最终删掉：①拍糊无法挽救、主体闭眼或严重模糊 ②误拍（口袋/地面/手指/黑屏/镜头被挡）③完全空镜无主体 ④被严重遮挡，主体只剩一小块 ⑤**方向错了**：画面转了 90°或 180°、地平线明显歪、主体横躺竖倒——竖拍横放、横拍竖放之类 ⑥**拖影/手抖连拍糊**：人或物边缘拖出重影、多条运动轨迹 ⑦**构图失衡**：主体被切掉一半、贴边、画面明显倾斜、前景大片遮挡 ⑧画质崩坏（严重噪点、大面积过曝或死黑）。注意：不是所有「不好看」都算 trash，普通的随手拍、有点普通但不残缺的， trash 填 false，靠 keep 给低分表达。",
    "keep": "综合保留价值 0-5，用同一把尺子衡量每张、保证可横向排序。**这批里各档都要真实出现，不要全往 3 靠**——张张都填 3 就等于没排。锚点：5=极罕见、丢了会后悔的决定性瞬间；4=很喜欢、想保留并可能剪视频；3=合格的日常记录，留着不亏但也没惊喜；2=较平淡或有明显瑕疵，可留可删；1=内容残缺或几乎没有意义；0=明确该删（trash 的通常在这里）。内容意义优先，画质作修正；同一场景连拍里，明显更好的那张才配 4，其余按差距给 2-3。"
  }
}
保持分数自洽：trash=true 时 keep<=1；highlight=true 时 keep>=4。

示例（机场候机、两个孩子、白天室内）：
{"scene":"机场候机","activity":"候机","people":{"present":true,"count":2,"emotion":"calm"},"objects":["行李箱","咖啡","登机牌"],"setting":{"indoor":true,"environment":"city"},"time":"day","weather":"unknown","ocr":["登机口 B12"],"location_clue":"机场候机厅","mood":"平静","quality":{"composition":3,"aesthetic":3,"highlight":false,"trash":false,"keep":3}}"""

_SYSTEM = "你是旅行相册的选片与打标助手，只输出一个 JSON 对象，不要额外解释或 markdown 代码围栏。"


def _data_uri(image_bytes: bytes, mime: str = "image/jpeg") -> str:
    return f"data:{mime};base64,{base64.b64encode(image_bytes).decode('ascii')}"


def compress_for_vlm(image_bytes: bytes, max_side: int = 768, quality: int = 80) -> bytes:
    """识图前把图缩到长边 max_side 并压质后返回 JPEG bytes，降低多模态 token 与上传体积。

    降采样到 ~768 不损场景/物体/情绪级识别，却能显著减少视觉 token 消耗与模型压力。
    OCR（小字）可能受损，故 max_side 可通过 PYSERVER_VLM_MAX_SIDE 调高。
    """
    image = ImageOps.exif_transpose(Image.open(io.BytesIO(image_bytes))).convert("RGB")
    image.thumbnail((max_side, max_side))
    output = io.BytesIO()
    image.save(output, format="JPEG", quality=quality, optimize=True)
    return output.getvalue()


def build_messages(image_bytes: bytes) -> list[dict]:
    """构造 OpenAI 多模态消息：system 约束纯 JSON，user 携带指令 + 图片。"""
    return [
        {"role": "system", "content": _SYSTEM},
        {"role": "user", "content": [
            {"type": "text", "text": TAG_INSTRUCTION},
            {"type": "image_url", "image_url": {"url": _data_uri(image_bytes)}},
        ]},
    ]


def extract_json(text: str) -> dict:
    """从模型输出抠出 JSON 对象；容忍 ```json 围栏和前后废话。失败抛 VLMError。"""
    if not text:
        raise VLMError("empty completion")
    fenced = re.search(r"```(?:json)?\s*(\{.*\})\s*```", text, re.S)
    candidate = fenced.group(1) if fenced else None
    if candidate is None:
        start, end = text.find("{"), text.rfind("}")
        if start == -1 or end <= start:
            raise VLMError("no JSON object in completion")
        candidate = text[start:end + 1]
    try:
        data = json.loads(candidate)
    except json.JSONDecodeError as exc:
        raise VLMError(f"bad JSON: {exc}") from exc
    if not isinstance(data, dict):
        raise VLMError("JSON is not an object")
    return data


def tag_image(
    image_bytes: bytes,
    *,
    model: str | None = None,
    max_side: int | None = None,
    max_tokens: int | None = None,
    reasoning_effort: str | None = None,
    base_url: str | None = None,
    api_key: str | None = None,
    timeout: float | None = None,
    retries: int = 2,
    client: httpx.Client | None = None,
    sleep=time.sleep,
) -> dict:
    """对单张照片打标+打分，返回解析后的 dict。

    4xx（除 429）立即抛 VLMError（不重试，客户端错误重试无益）；
    网络抖动 / 429 / 5xx / 输出解析失败按 retries 指数退避后仍失败则抛 VLMError。
    注入 client 便于用 MockTransport 测试，不发真实请求。
    """
    model = model or _first_env("PYSERVER_VLM_MODEL") or vision_model()
    image_bytes = compress_for_vlm(image_bytes, max_side or int(os.getenv("PYSERVER_VLM_MAX_SIDE", "768")))
    base_url = (base_url or _first_env("PYSERVER_VLM_BASE_URL") or vision_base_url()).rstrip("/")
    if api_key is None:
        api_key = os.getenv("PYSERVER_VLM_API_KEY")
    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    max_tokens = max_tokens or int(os.getenv("PYSERVER_VLM_MAX_TOKENS", "900" if model == "qwen38-27b" else "4096"))
    reasoning_effort = reasoning_effort or os.getenv("PYSERVER_VLM_REASONING_EFFORT")
    payload = {"model": model, "messages": build_messages(image_bytes),
               "temperature": 0, "max_tokens": max_tokens}
    if model == "qwen38-27b":
        payload["chat_template_kwargs"] = {"enable_thinking": False}
    if reasoning_effort:  # 推理强度（如 stepfun step-5 的 "low"）：推理模型先思考后出 content，max_tokens 需容纳二者
        payload["reasoning_effort"] = reasoning_effort

    owns = client is None
    if owns:
        client = httpx.Client(timeout=timeout or DEFAULT_TIMEOUT)
    url = f"{base_url}/chat/completions"
    last: Exception | None = None
    try:
        for attempt in range(retries + 1):
            try:
                resp = client.post(url, headers=headers, json=payload)
                if resp.status_code == 429 or resp.status_code >= 500:
                    raise _Retry(f"upstream {resp.status_code}")
                if resp.status_code >= 400:
                    raise VLMError(f"http {resp.status_code}: {resp.text[:200]}")
                try:
                    content = resp.json()["choices"][0]["message"]["content"]
                except (ValueError, KeyError, IndexError) as exc:
                    raise _Retry(f"bad completion shape: {exc}") from exc
                try:
                    return extract_json(content)
                except VLMError as exc:
                    raise _Retry(str(exc)) from exc
            except (_Retry, httpx.RequestError) as exc:
                last = exc
                if attempt >= retries:
                    raise VLMError(f"tag_image failed after {retries + 1} tries: {last}") from last
                sleep(0.5 * (attempt + 1))
        raise VLMError("unreachable")
    finally:
        if owns:
            client.close()
