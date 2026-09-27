import asyncio
import json

import httpx

from pyserver.agent import step


def test_step_preview_request_matches_documented_chat_contract(monkeypatch):
    seen = {}

    def respond(request):
        seen["url"] = str(request.url)
        seen["body"] = json.loads(request.content)
        chunks = [
            {"choices": [{"delta": {"reasoning": "检查地点"}, "finish_reason": None}], "usage": {"prompt_tokens": 12, "completion_tokens": 2}},
            {"choices": [{"delta": {"tool_calls": [{"index": 0, "id": "call_1", "function": {"name": "discover_places", "arguments": "{}"}}]}, "finish_reason": "tool_calls"}], "usage": {"prompt_tokens": 12, "completion_tokens": 8}},
        ]
        content = "".join(f"data: {json.dumps(chunk, ensure_ascii=False)}\n\n" for chunk in chunks) + "data: [DONE]\n\n"
        return httpx.Response(200, text=content)

    client_class = httpx.AsyncClient
    monkeypatch.setattr(step.httpx, "AsyncClient", lambda **kwargs: client_class(transport=httpx.MockTransport(respond), **kwargs))
    monkeypatch.delenv("STEPFUN_BASE_URL", raising=False)

    async def scenario():
        return [item async for item in step.complete([{"role": "user", "content": "规划旅行"}],
                                                     [{"type": "function", "function": {"name": "discover_places", "parameters": {"type": "object", "properties": {}}}}],
                                                     "test-key")]

    events = asyncio.run(scenario())
    assert seen["url"] == "https://api.stepfun.com/step_plan/v1/chat/completions"
    assert seen["body"]["model"] == "step-5-preview"
    assert seen["body"]["stream"] is True
    assert seen["body"]["tools"][0]["type"] == "function"
    assert "max_tokens" not in seen["body"]
    assert "tool_choice" not in seen["body"]
    assert events[0] == {"type": "model_reasoning_delta", "text": "检查地点"}
    assert events[-1]["message"]["tool_calls"][0]["function"]["name"] == "discover_places"
    assert events[-1]["usage"] == {"prompt_tokens": 12, "completion_tokens": 8}
