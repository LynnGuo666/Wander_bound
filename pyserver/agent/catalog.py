"""Lazy tool declarations exposed to Step Plan."""
from __future__ import annotations

MAX_TURNS = 200
MAX_CALLS = 200
SYSTEM = ("你是旅行规划 Agent。直接理解用户原话，不能编造日期、地点、路线和价格。"
          "每次用户回答 ask_question 后必须先调用 set_trip_spec 增量保存答案，再问下一题。"
          "按需调用地点、交通、住宿工具。工具调用失败可根据错误重试。"
          "仅在缺少会改变路线的关键信息时提问；已有足够信息就立即继续查询并编排行程。"
          "只使用工具返回的地点 ID 制作行程。最终用简短中文总结。")


def definition(name: str, description: str, properties: dict, required: list[str] | None = None) -> dict:
    return {"type": "function", "function": {"name": name, "description": description,
            "parameters": {"type": "object", "properties": properties, **({"required": required} if required else {})}}}


TOOLS = {
    "set_trip_spec": definition("set_trip_spec", "增量保存已确认的行程字段，每次回答后先调用。只提交新增字段。", {
        "destination": {"type": "string"}, "originCity": {"type": "string"}, "days": {"type": "integer"},
        "startDate": {"type": "string"}, "totalBudgetCny": {"type": "number"},
        "requiredStays": {"type": "array", "items": {"type": "object", "properties": {"city": {"type": "string"},
                          "from": {"type": "string"}, "to": {"type": "string"}}}},
        "interests": {"type": "array", "items": {"type": "string"}},
        "preferences": {"type": "object", "description": "把用户刚回答的交通、住宿、玩法等偏好按字段增量保存"}}),
    "ask_question": definition("ask_question", "向用户提出一个会改变行程决定的问题，提供 2–5 个选项，界面会补充其他。", {
        "question": {"type": "string"}, "options": {"type": "array", "items": {"type": "object", "properties": {
            "id": {"type": "string"}, "label": {"type": "string"}, "description": {"type": "string"}}}}}, ["question", "options"]),
    "resolve_origin": definition("resolve_origin", "读取已确认的出发城市。", {}),
    "discover_places": definition("discover_places", "按指定城市查询真实地点，未指定则查主要目的地。可多次查询沿途城市，返回可用于排程的 ID。", {"city": {"type": "string"}}),
    "search_transport": definition("search_transport", "按起点、目的地和日期懒加载 12306 MCP 火车票数据。", {}),
    "search_stays": definition("search_stays", "取得住宿数据；无已认证供应商时返回空数组，不能编造酒店。", {}),
    "draft_plan": definition("draft_plan", "使用已发现的真实地点 ID 提交最终行程；可为每一天指定城市及地点 ID。不得编造价格或地点。", {
        "placeIds": {"type": "array", "items": {"type": "string"}},
        "dayAssignments": {"type": "array", "items": {"type": "object", "properties": {
            "date": {"type": "string"}, "city": {"type": "string"}, "placeIds": {"type": "array", "items": {"type": "string"}}}}}}, ["placeIds"]),
}


def available(state: dict) -> list[dict]:
    if state.get("answerNeedsCommit"):
        return [TOOLS["set_trip_spec"]]
    if state.get("plan"):
        return []
    names = ["ask_question", "set_trip_spec"]
    if not state.get("originDone"):
        names.append("resolve_origin")
    if not state.get("placesDone"):
        names.append("discover_places")
    if state.get("placesDone") and state.get("originDone"):
        names += ["search_transport", "search_stays"]
    if state.get("placesDone") and state.get("transportDone") and state.get("staysDone"):
        names.append("draft_plan")
    return [TOOLS[name] for name in names]
