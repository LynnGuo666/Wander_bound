"""vlm.py 的 mock 自测：不发真实请求，用 httpx.MockTransport 注入假响应。

覆盖：请求消息构造 + base64 回环、成功解析、```json 围栏/前后废话容错、
429/5xx 重试、持续坏输出放弃、4xx 不重试、Authorization 头。
"""
import base64
import io
import json

import httpx
import pytest
from PIL import Image

from pyserver.media import vlm

_NOOP = lambda *_: None  # noqa: E731


def _jpeg_bytes(color=(120, 130, 140), size=(160, 160)) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", size, color).save(buf, format="JPEG", quality=90)
    return buf.getvalue()


def _completion(content: str) -> dict:
    return {"choices": [{"message": {"role": "assistant", "content": content}}]}


def test_build_messages_structure_and_base64_roundtrip():
    raw = b"\xff\xd8\xff\xe0somebytes"
    msgs = vlm.build_messages(raw)
    assert msgs[0]["role"] == "system"
    user = msgs[1]
    assert user["role"] == "user"
    text, image = user["content"]
    assert text["type"] == "text" and vlm.TAG_INSTRUCTION in text["text"]
    assert image["type"] == "image_url"
    url = image["image_url"]["url"]
    assert url.startswith("data:image/jpeg;base64,")
    assert base64.b64decode(url.split(",", 1)[1]) == raw


def test_tag_image_success():
    seen = {"n": 0}

    def handler(request):
        seen["n"] += 1
        seen["payload"] = json.loads(request.read())
        return httpx.Response(200, json=_completion(json.dumps({"scene": "机场", "quality": {"keep": 4}})))

    client = httpx.Client(transport=httpx.MockTransport(handler))
    out = vlm.tag_image(_jpeg_bytes(), client=client, sleep=_NOOP)
    assert out["scene"] == "机场" and out["quality"]["keep"] == 4
    assert seen["n"] == 1
    assert seen["payload"]["max_tokens"] == 900
    assert seen["payload"]["chat_template_kwargs"] == {"enable_thinking": False}


def test_extract_json_tolerates_fence_and_noise():
    assert vlm.extract_json("```json\n{\"a\": 1}\n```") == {"a": 1}
    assert vlm.extract_json("好的，结果如下：{\"a\": 2} 以上。") == {"a": 2}
    with pytest.raises(vlm.VLMError):
        vlm.extract_json("这句话没有 JSON")
    with pytest.raises(vlm.VLMError):
        vlm.extract_json("[1, 2, 3]")  # 不是对象
    with pytest.raises(vlm.VLMError):
        vlm.extract_json("")


@pytest.mark.parametrize("code", [429, 500, 503])
def test_retry_on_transient_then_success(code):
    seen = {"n": 0}

    def handler(request):
        seen["n"] += 1
        if seen["n"] == 1:
            return httpx.Response(code, json={"error": "transient"})
        return httpx.Response(200, json=_completion(json.dumps({"scene": "飞机"})))

    client = httpx.Client(transport=httpx.MockTransport(handler))
    out = vlm.tag_image(_jpeg_bytes(), client=client, retries=2, sleep=_NOOP)
    assert out["scene"] == "飞机" and seen["n"] == 2


def test_gives_up_after_retries_on_bad_output():
    seen = {"n": 0}

    def handler(request):
        seen["n"] += 1
        return httpx.Response(200, json=_completion("抱歉，我无法处理这张图。"))

    client = httpx.Client(transport=httpx.MockTransport(handler))
    with pytest.raises(vlm.VLMError):
        vlm.tag_image(_jpeg_bytes(), client=client, retries=2, sleep=_NOOP)
    assert seen["n"] == 3  # 1 + 2 retries


def test_4xx_not_retried():
    seen = {"n": 0}

    def handler(request):
        seen["n"] += 1
        return httpx.Response(400, json={"error": "bad request"})

    client = httpx.Client(transport=httpx.MockTransport(handler))
    with pytest.raises(vlm.VLMError):
        vlm.tag_image(_jpeg_bytes(), client=client, retries=2, sleep=_NOOP)
    assert seen["n"] == 1


def test_authorization_header_sent_when_key_present():
    seen = {}

    def handler(request):
        seen["auth"] = request.headers.get("authorization")
        return httpx.Response(200, json=_completion(json.dumps({"scene": "餐厅"})))

    client = httpx.Client(transport=httpx.MockTransport(handler))
    vlm.tag_image(_jpeg_bytes(), client=client, api_key="secret-key", sleep=_NOOP)
    assert seen["auth"] == "Bearer secret-key"


def test_prompt_declares_not_applicable_escapes():
    """反"被迫填写=幻觉标签"：prompt 必须给每个字段不适用出口，并禁止为填满而编造。"""
    t = vlm.TAG_INSTRUCTION
    assert "不要为了填满而编造" in t
    assert "不要硬编" in t  # mood：无情绪载体时不得瞎填
    for token in ("unknown", "null", "空数组"):
        assert token in t


def test_compress_for_vlm_shrinks_and_is_jpeg():
    big = io.BytesIO()
    Image.new("RGB", (2000, 1500), (30, 60, 90)).save(big, format="JPEG", quality=95)
    raw = big.getvalue()
    out = vlm.compress_for_vlm(raw, max_side=768)
    assert len(out) < len(raw)
    im = Image.open(io.BytesIO(out))
    assert im.format == "JPEG" and max(im.size) <= 768


def test_compress_low_max_side_respected():
    out = vlm.compress_for_vlm(_jpeg_bytes(size=(2000, 1000)), max_side=512)
    assert max(Image.open(io.BytesIO(out)).size) <= 512


def test_reasoning_effort_forwarded_only_when_set():
    def make_handler(box):
        def handler(request):
            box["body"] = json.loads(request.read())
            return httpx.Response(200, json=_completion(json.dumps({"scene": "x"})))
        return handler

    box = {}
    c = httpx.Client(transport=httpx.MockTransport(make_handler(box)))
    vlm.tag_image(_jpeg_bytes(), client=c, api_key="k", reasoning_effort="low", sleep=_NOOP)
    assert box["body"].get("reasoning_effort") == "low"
    assert box["body"]["max_tokens"] > 768  # 默认已抬高，容纳推理模型的思考+content

    box2 = {"body": {"reasoning_effort": "should-not-persist"}}
    c2 = httpx.Client(transport=httpx.MockTransport(make_handler(box2)))
    vlm.tag_image(_jpeg_bytes(), client=c2, api_key="k", sleep=_NOOP)
    assert "reasoning_effort" not in box2["body"]  # 未指定则不加，保持对其他端点通用
