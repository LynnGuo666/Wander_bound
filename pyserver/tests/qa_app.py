"""Manual browser QA fixture: real providers with scripted model tool choices."""
import json
import uuid

from pyserver import agent
from pyserver.app import create_app


async def scripted_model(messages, tools, api_key, **_kwargs):
    names = [item["function"]["name"] for item in tools]
    if "draft_plan" in names:
        places = []
        for item in messages:
            if item["role"] == "tool":
                try:
                    result = json.loads(item["content"])
                    if result.get("places"):
                        places = [place["id"] for place in result["places"]]
                except (ValueError, KeyError):
                    pass
        requested = [("draft_plan", {"placeIds": places[:10]})]
    elif "search_transport" in names:
        requested = [("search_transport", {}), ("search_stays", {})]
    elif "discover_places" in names and any(item["role"] == "tool" for item in messages):
        requested = [("resolve_origin", {}), ("discover_places", {})] if "resolve_origin" in names else [("discover_places", {})]
    else:
        requested = [("set_trip_spec", {"originCity": "长春", "destination": "柳州", "days": 13,
                                        "startDate": "2026-09-30", "totalBudgetCny": 4000,
                                        "requiredStays": [{"city": "柳州", "from": "2026-10-02", "to": "2026-10-05"}]})]
    calls = [{"id": str(uuid.uuid4()), "type": "function", "function": {"name": name,
              "arguments": json.dumps(args, ensure_ascii=False)}} for name, args in requested if name in names]
    yield {"type": "completion", "message": {"role": "assistant", "content": None, "tool_calls": calls},
           "finishReason": "tool_calls", "usage": {"prompt_tokens": 100, "completion_tokens": 30}, "publicNote": "正在核对行程数据。"}


agent.step.complete = scripted_model
app = create_app()
