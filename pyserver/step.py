"""Step Plan streaming client with distinct public and raw reasoning channels."""
from __future__ import annotations

import json
import os
from collections.abc import AsyncIterator

import httpx

MODEL = "step-5-preview"
BASE = "https://api.stepfun.com/step_plan/v1"


async def complete(messages: list[dict], tools: list[dict], api_key: str, *, tool_choice: str = "required") -> AsyncIterator[dict]:
    base = os.getenv("STEPFUN_BASE_URL", BASE).rstrip("/")
    if not base.startswith("https://") and not base.startswith("http://127.0.0.1:"):
        raise ValueError("StepFun 地址必须使用 HTTPS 或本机回环地址")
    async with httpx.AsyncClient(timeout=httpx.Timeout(125, connect=12)) as client:
        async with client.stream("POST", f"{base}/chat/completions", headers={"Authorization": f"Bearer {api_key}"},
                                 json={"model": MODEL, "messages": messages, "tools": tools, "tool_choice": tool_choice,
                                       "temperature": 0.2, "max_tokens": 4096, "stream": True}) as response:
            if response.status_code != 200:
                raise RuntimeError(f"StepFun HTTP {response.status_code}")
            calls: dict[int, dict] = {}
            public = ""
            reasoning = ""
            finish = None
            usage = {}
            async for line in response.aiter_lines():
                if not line.startswith("data:"):
                    continue
                raw = line[5:].strip()
                if not raw or raw == "[DONE]":
                    continue
                frame = json.loads(raw)
                if frame.get("error"):
                    raise RuntimeError("StepFun 流返回错误")
                usage = frame.get("usage") or usage
                for choice in frame.get("choices") or []:
                    delta = choice.get("delta") or {}
                    thought = delta.get("reasoning_content") or delta.get("reasoning") or ""
                    if isinstance(thought, list):
                        thought = "".join(item if isinstance(item, str) else item.get("text", "") for item in thought)
                    if thought:
                        reasoning += thought
                        yield {"type": "model_reasoning_delta", "text": thought}
                    content = delta.get("content") or ""
                    if isinstance(content, list):
                        content = "".join(item.get("text", "") for item in content)
                    if content:
                        public += content
                        # Some Step Plan responses place analysis in content. Keep it in the raw debug lane.
                        if public.lstrip().startswith(("Let me", "Let's think", "I need", "We need", "让我分析", "我需要先")) or len(public) > 240:
                            yield {"type": "model_reasoning_delta", "text": content}
                        else:
                            yield {"type": "model_text_delta", "text": content}
                    for item in delta.get("tool_calls") or []:
                        index = item.get("index", len(calls))
                        call = calls.setdefault(index, {"id": "", "type": "function", "function": {"name": "", "arguments": ""}})
                        call["id"] += item.get("id") or ""
                        call["function"]["name"] += (item.get("function") or {}).get("name") or ""
                        call["function"]["arguments"] += (item.get("function") or {}).get("arguments") or ""
                    finish = choice.get("finish_reason") or finish
            if finish not in {"stop", "tool_calls"}:
                error = RuntimeError("StepFun 本轮输出达到上限" if finish == "length" else "StepFun 响应不完整")
                error.code = "output_limit" if finish == "length" else "invalid_completion"
                error.usage = usage
                raise error
            yield {"type": "completion", "message": {"role": "assistant", "content": public or None,
                  **({"tool_calls": [calls[key] for key in sorted(calls)]} if calls else {})},
                  "finishReason": finish, "usage": usage, "publicNote": "" if public.lstrip().startswith(("Let me", "Let's think", "I need", "We need")) or len(public) > 240 else public[:240]}
