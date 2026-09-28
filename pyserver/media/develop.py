"""Local DGX vision suggestions for non-generative photo development."""
from __future__ import annotations

import base64
import json
import os
import re
import time

import httpx

from .images import DEFAULT_DEVELOP, normalize_develop
from .vision import vision_base_url, vision_model, vision_token

CATEGORY_GUIDANCE = {
    "landscape": "Landscape: use a vivid, anime-inspired travel illustration style while preserving the original scene and all subjects. Push ocean blue and sky cyan toward a clear, high-saturation look, add lively separation between water, foam, vegetation, and warm sand, and use a confident but smooth curve. Keep highlight detail in clouds and waves, retain shadow texture, and avoid muddy blacks, clipped skies, neon colors, or content changes.",
    "portrait": "Portrait: prioritize the subject, natural skin tones, and clear separation from the background. Control orange and red HSL channels carefully, reduce distracting background saturation when useful, and use a gentle curve for dimensionality. Do not alter facial details, bodies, clothing, or objects.",
    "mood": "Mood: prioritize atmosphere and visual storytelling through a gentle curve, controlled highlights and shadows, and low-amplitude color separation. Keep the scene believable and avoid applying a heavy preset or theatrical filter.",
}
SYSTEM_PROMPT = """You are a travel photography editor. First classify the supplied photo as exactly one of landscape, portrait, or mood, then apply the matching guidance below. Use landscape when scenery occupies most of the frame, even if a small person is present; use portrait when a person is the clear visual subject; use mood when atmosphere and light matter more than a specific subject. Never invent, remove, replace, or redraw image content. Return only JSON with keys: category, params, rationale, cropReason. category must be one of landscape, portrait, mood. params must contain exposure (-2..2), contrast (0.5..1.5), saturation (0..2), sharpness (0..2), highlights (-1..1), shadows (-1..1), gamma (0.5..1.5), normalized crop {left,top,width,height} with all bounds inside 0..1, hsl with red/orange/yellow/green/cyan/blue/purple/magenta each containing hue/saturation/luminance (-1..1), and curve.master with exactly 5 points, each either a number y value or an object {x,y}, ordered from 0 to 1. Use HSL and curve adjustments where they improve a specific color or tonal range. Preserve the full frame unless a clear crop improves composition. Keep edits photographic and reversible.""" + "\n\n" + "\n".join(f"{key}: {value}" for key, value in CATEGORY_GUIDANCE.items())

def _content_json(content: str) -> dict:
    text = content.strip()
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text, flags=re.I)
    return json.loads(text)

async def suggest(image_bytes: bytes, mime_type: str = "image/jpeg") -> dict:
    started = time.monotonic()
    base_url = vision_base_url()
    model = vision_model()
    token = vision_token()
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    encoded = base64.b64encode(image_bytes).decode("ascii")
    payload = {"model": model, "temperature": 0.1, "max_tokens": 6000,
        "response_format": {"type": "json_object"},
        "messages": [{"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": [
                {"type": "text", "text": "Analyze this travel photograph and propose restrained development settings."},
                {"type": "image_url", "image_url": {"url": f"data:{mime_type};base64,{encoded}"}},
            ]}]}
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(90, connect=8)) as client:
            response = await client.post(f"{base_url}/chat/completions", headers=headers, json=payload)
            response.raise_for_status()
            content = response.json()["choices"][0]["message"]["content"]
        result = _content_json(content)
        params = normalize_develop({**DEFAULT_DEVELOP, **(result.get("params") or {})})
        rationale = str(result.get("rationale") or "")[:600]
        crop_reason = str(result.get("cropReason") or "")[:300]
        if not rationale:
            raise ValueError("模型没有返回调整理由")
        category = str(result.get("category") or "mood")
        if category not in CATEGORY_GUIDANCE:
            category = "mood"
        return {"category": category, "params": params, "rationale": rationale, "cropReason": crop_reason,
                "model": model, "provider": base_url, "elapsedMs": round((time.monotonic() - started) * 1000)}
    except (httpx.HTTPError, KeyError, IndexError, TypeError, ValueError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"DGX 照片分析失败：{exc}") from exc


async def review(original: bytes, edited: bytes, settings: dict) -> dict:
    started = time.monotonic()
    base_url = vision_base_url()
    model = vision_model()
    token = vision_token()
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    def image_part(data: bytes):
        return {"type": "image_url", "image_url": {"url": "data:image/jpeg;base64," + base64.b64encode(data).decode("ascii")}}
    payload = {"model": model, "temperature": 0.1, "max_tokens": 300,
        "response_format": {"type": "json_object"},
        "messages": [{"role": "system", "content": "Compare the original and edited travel photo. Return only JSON with keys approved (boolean), note (short text). Reject blown highlights, blocked shadows, unnatural skin/color, excessive sharpening, or a crop that removes important content. Do not suggest content generation."},
            {"role": "user", "content": [{"type": "text", "text": f"Original then edited. Settings: {json.dumps(settings)}"}, image_part(original), image_part(edited)]}]}
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(90, connect=8)) as client:
            response = await client.post(f"{base_url}/chat/completions", headers=headers, json=payload)
            response.raise_for_status()
            result = _content_json(response.json()["choices"][0]["message"]["content"])
        if not isinstance(result.get("approved"), bool) or not result.get("note"):
            raise ValueError("模型没有返回有效复核结论")
        return {"approved": result["approved"], "note": str(result["note"])[:400], "model": model,
                "elapsedMs": round((time.monotonic() - started) * 1000)}
    except (httpx.HTTPError, KeyError, IndexError, TypeError, ValueError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"DGX 预览复核失败：{exc}") from exc
