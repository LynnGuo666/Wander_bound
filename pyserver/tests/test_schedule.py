import asyncio

from pyserver.agent.planning import draft_plan
from pyserver.agent.schedule import day_windows, select_outbound
from pyserver.agent.spec import set_trip_spec
from pyserver.agent.fallback import complete_with_tools


def _state(days):
    end_day = "2026-10-04" if days == 3 else "2026-10-14"
    return {"originCity": "长春", "destination": "柳州", "startDate": "2026-10-02", "days": days,
            "requiredStays": [], "totalBudgetCny": None, "hotels": [], "flights": [], "returnFlights": [],
            "trains": [{"id": "train-out", "departureAt": "2026-10-02T10:00:00", "arrivalAt": "2026-10-03T20:46:00", "totalPrice": 341}],
            "returnTrains": [{"id": "train-back", "departureAt": f"{end_day}T10:00:00", "arrivalAt": f"{end_day}T22:00:00", "totalPrice": 341}],
            "places": [{"id": "real-place", "name": "柳州博物馆", "city": "柳州", "lat": 24.3, "lng": 109.4}],
            "providerStatus": {}}


def test_three_day_train_trip_cannot_schedule_before_arrival_or_return():
    state = _state(3)
    assert not day_windows(state)
    result = asyncio.run(draft_plan({"placeIds": ["real-place"]}, state))
    assert result["code"] == "infeasible_trip"
    assert state.get("plan") is None


def test_longer_trip_keeps_middle_days_for_verified_places():
    state = _state(13)
    windows = day_windows(state)
    assert "2026-10-02" not in windows
    assert "2026-10-03" not in windows
    assert "2026-10-04" in windows
    result = asyncio.run(draft_plan({"placeIds": ["real-place"]}, state))
    assert result["ok"] is True
    assert not state["plan"]["itinerary"][0]["stops"]
    assert not state["plan"]["itinerary"][1]["stops"]
    assert state["plan"]["itinerary"][2]["stops"][0]["start"] is None


def test_daylight_high_speed_train_is_selected_over_midnight_or_slow_train():
    state = _state(3)
    state["preferences"] = {"transportPreference": "train"}
    state["trains"] = [
        {"id": "midnight", "trainNumber": "G100", "departureAt": "2026-10-02T00:04:00",
         "arrivalAt": "2026-10-02T00:33:00", "totalPrice": 75},
        {"id": "slow", "trainNumber": "K200", "departureAt": "2026-10-02T08:00:00",
         "arrivalAt": "2026-10-02T10:00:00", "totalPrice": 24},
        {"id": "daylight", "trainNumber": "G300", "departureAt": "2026-10-02T06:20:00",
         "arrivalAt": "2026-10-02T07:00:00", "totalPrice": 75},
    ]
    assert select_outbound(state)["id"] == "daylight"


def test_answer_can_change_explicit_days_and_infeasible_plan_asks_user(monkeypatch):
    state = _state(3)
    state.update({"originDone": True, "placesDone": True, "transportDone": True, "staysDone": True,
                  "pendingQuestion": None, "answerNeedsCommit": False})

    async def scenario():
        events = [item async for item in complete_with_tools(state, {}, {"days": 3}, {})]
        assert any(phase == "end" and name == "draft_plan" and result["code"] == "infeasible_trip"
                   for phase, name, _, result in events)
        assert state["pendingQuestion"]["question"].startswith("按真实去返程时刻")
        state["pendingQuestion"] = None
        state["answerNeedsCommit"] = True
        changed = await set_trip_spec({"days": 13}, state, {"days": 3})
        assert changed["ok"] is True
        assert state["days"] == 13

    asyncio.run(scenario())
