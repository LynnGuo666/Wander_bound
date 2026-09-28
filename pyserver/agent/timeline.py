"""Calculate a visible plan timeline without inventing supplier travel times."""
from __future__ import annotations

from datetime import datetime, time, timedelta


def _at(value):
    try:
        return datetime.fromisoformat(value) if value else None
    except ValueError:
        return None


def _offer(plan, returning=False):
    fields = ("returnFlights", "returnTrains") if returning else ("flights", "trains")
    ids = ("recommendedReturnFlightId", "recommendedReturnTrainId") if returning else ("recommendedOutboundFlightId", "recommendedOutboundTrainId")
    offers = [item for field in fields for item in plan.get(field) or []]
    return next((item for item in offers if item.get("id") in {plan.get(field) for field in ids}), None)


def build_timeline(plan: dict) -> dict:
    outbound, returning = _offer(plan), _offer(plan, returning=True)
    journeys = plan.get("groundJourneys") or []
    buffers = {"flight": {"departure": 120, "arrival": 45}, "train": {"departure": 45, "arrival": 20},
               "hotel": 25, "meal": 45}
    buffers.update({key: value for key, value in (plan.get("timeBuffers") or {}).items()
                    if key in ("hotel", "meal") and type(value) is int and 0 <= value <= 180})
    plan["timeBuffers"] = buffers
    for day in plan.get("itinerary") or []:
        number = day["day"]
        date = datetime.fromisoformat(day["date"])
        start = date.replace(hour=9)
        end = date.replace(hour=21)
        events, issues = [], []
        def event(kind, label, begin=None, finish=None, **other):
            item = {"kind": kind, "label": label, "startAt": begin.isoformat() if begin else None,
                    "endAt": finish.isoformat() if finish else None, **other}
            events.append(item)
            return item
        def journey(purpose, ordinal=0):
            matches = [item for item in journeys if item.get("day") == number and item.get("purpose") == purpose]
            return matches[ordinal] if ordinal < len(matches) else None
        def move(route, current):
            if not route:
                issues.append("缺少高德路线时间")
                event("transport", "路线待查询", None, None, routeStatus="unknown")
                return None
            minutes = route.get("minutes")
            if type(minutes) is not int or minutes < 0:
                issues.append(f"{route.get('from') or '出发地'}至{route.get('to') or '目的地'}缺少高德路线时间")
                event("transport", f"{route.get('from') or '出发地'} → {route.get('to') or '目的地'}", None, None,
                      routeStatus="unknown", routePurpose=route.get("purpose"))
                return None
            arrival = current + timedelta(minutes=minutes) if current else None
            event("transport", f"{route['from']} → {route['to']}", current, arrival,
                  routeStatus="estimated", routePurpose=route.get("purpose"), minutes=minutes, source=route.get("source"))
            return arrival
        if outbound and _at(outbound.get("departureAt")) and date.date() == _at(outbound["departureAt"]).date():
            mode = "flight" if outbound in (plan.get("flights") or []) else "train"
            departure, arrival = _at(outbound["departureAt"]), _at(outbound.get("arrivalAt"))
            before = departure - timedelta(minutes=buffers[mode]["departure"])
            access = journey("to-terminal")
            if access:
                minutes = access.get("minutes")
                access_start = before - timedelta(minutes=minutes) if type(minutes) is int else None
                move(access, access_start)
            event("preparation", "机场准备" if mode == "flight" else "车站准备", before, departure,
                  minutes=buffers[mode]["departure"], source="计划预留")
            event(mode, outbound.get("flightNumber") or outbound.get("trainNumber") or "去程", departure, arrival,
                  source=outbound.get("provider"))
            if arrival:
                exit_end = arrival + timedelta(minutes=buffers[mode]["arrival"])
                event("preparation", "落地与取行李" if mode == "flight" else "出站", arrival, exit_end,
                      minutes=buffers[mode]["arrival"], source="计划预留")
                if arrival.date() == date.date():
                    start = move(journey("arrival-to-stay"), exit_end)
                    if start:
                        checkin_end = start + timedelta(minutes=buffers["hotel"])
                        event("stay", "酒店入住或行李寄存", start, checkin_end,
                              minutes=buffers["hotel"], source="计划预留")
                        start = checkin_end
                else:
                    start = None
        elif outbound and _at(outbound.get("arrivalAt")) and date.date() == _at(outbound["arrivalAt"]).date():
            mode = "flight" if outbound in (plan.get("flights") or []) else "train"
            arrival = _at(outbound["arrivalAt"])
            exit_end = arrival + timedelta(minutes=buffers[mode]["arrival"])
            event("preparation", "落地与取行李" if mode == "flight" else "出站", arrival, exit_end,
                  minutes=buffers[mode]["arrival"], source="计划预留")
            start = move(journey("arrival-to-stay"), exit_end)
            if start:
                checkin_end = start + timedelta(minutes=buffers["hotel"])
                event("stay", "酒店入住或行李寄存", start, checkin_end,
                      minutes=buffers["hotel"], source="计划预留")
                start = checkin_end
        elif number == 1 and journey("arrival-to-stay"):
            start = move(journey("arrival-to-stay"), start)
        return_cutoff = None
        if returning and _at(returning.get("departureAt")) and date.date() == _at(returning["departureAt"]).date():
            mode = "flight" if returning in (plan.get("returnFlights") or []) else "train"
            departure = _at(returning["departureAt"])
            before = departure - timedelta(minutes=buffers[mode]["departure"])
            route = journey("to-return-terminal")
            if route and type(route.get("minutes")) is int:
                return_cutoff = before - timedelta(minutes=route["minutes"])
                end = min(end, return_cutoff)
            else:
                issues.append("返程至机场或车站的高德路线时间未知")
                end = min(end, before)
        meals = set()
        for index, stop in enumerate(day.get("stops") or []):
            start = move(journey("to-place", index), start)
            confirmed = stop.get("duration")
            recommended = stop.get("recommendedDurationMinutes")
            duration = confirmed if type(confirmed) is int and confirmed > 0 else recommended if type(recommended) is int and recommended > 0 else 90
            source = "confirmed" if type(confirmed) is int and confirmed > 0 else "ai_recommended" if type(recommended) is int and recommended > 0 else "planning_default"
            stop["durationSource"] = source
            stop["recommendedDurationMinutes"] = duration if source == "ai_recommended" else recommended
            stop["start"] = start.strftime("%H:%M") if start else None
            finish = start + timedelta(minutes=duration) if start else None
            event("place", stop["name"], start, finish, minutes=duration, durationSource=source, placeId=stop["id"],
                  coordinate={"lat": stop.get("lat"), "lng": stop.get("lng")},
                  openingHoursStatus="known" if stop.get("openingHours") else "unknown")
            if finish and finish > end:
                issues.append(f"{stop['name']}超出当日可用时间")
            start = finish
            if start:
                meal = "午餐" if 11 <= start.hour < 14 else "晚餐" if 17 <= start.hour < 20 else None
                if meal and meal not in meals:
                    after = start + timedelta(minutes=buffers["meal"])
                    event("meal", f"{meal}待定", start, after, minutes=buffers["meal"], source="计划预留")
                    start = after
                    meals.add(meal)
        if day.get("stops"):
            start = move(journey("return-to-stay"), start)
            event("stay", "返回酒店", start, start)
            if start and start > end and not returning:
                issues.append("返回酒店超过当日游玩窗口")
        elif number > 1 and not returning:
            event("stay", "酒店休息", start, start)
        if returning and _at(returning.get("departureAt")) and date.date() == _at(returning["departureAt"]).date():
            route = journey("to-return-terminal")
            if return_cutoff and start and start < return_cutoff:
                event("stay", "酒店休息与整理行李", start, return_cutoff)
                start = return_cutoff
            terminal_time = move(route, start)
            mode = "flight" if returning in (plan.get("returnFlights") or []) else "train"
            departure = _at(returning["departureAt"])
            before = departure - timedelta(minutes=buffers[mode]["departure"])
            if terminal_time and terminal_time > before:
                issues.append("无法在返程准备时间前到达机场或车站")
            event("preparation", "返程准备", before, departure, minutes=buffers[mode]["departure"], source="计划预留")
            event(mode, returning.get("flightNumber") or returning.get("trainNumber") or "返程", departure,
                  _at(returning.get("arrivalAt")), source=returning.get("provider"))
        day["timeline"] = events
        day["timeCost"] = {"travelMinutes": sum(item.get("minutes") or 0 for item in events if item["kind"] == "transport"),
                           "visitMinutes": sum(item.get("minutes") or 0 for item in events if item["kind"] == "place"),
                           "bufferMinutes": sum(item.get("minutes") or 0 for item in events if item["kind"] in {"preparation", "meal", "stay"}),
                           "unknownLegs": sum(item.get("routeStatus") == "unknown" for item in events if item["kind"] == "transport")}
        day["feasibility"] = {"status": "unknown" if any("未知" in issue or "缺少" in issue for issue in issues) else "conflict" if issues else "estimated",
                              "issues": issues}
    return plan
