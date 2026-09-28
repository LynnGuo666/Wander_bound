from pyserver.agent.timeline import build_timeline
from pyserver.agent.planning import draft_plan
from pyserver.trips.history import reconstruct
from pyserver.providers.coordinates import gcj_to_wgs, wgs_to_gcj
import asyncio


def test_day_routes_include_hotel_departure_and_return():
    plan = {"itinerary": [{"day": 1, "date": "2026-10-01", "stops": [
        {"id": "a", "name": "A", "duration": 60},
        {"id": "b", "name": "B", "recommendedDurationMinutes": 80}]}],
        "groundJourneys": [
            {"day": 1, "purpose": "to-place", "from": "酒店", "to": "A", "minutes": 20, "source": "高德"},
            {"day": 1, "purpose": "to-place", "from": "A", "to": "B", "minutes": 15, "source": "高德"},
            {"day": 1, "purpose": "return-to-stay", "from": "B", "to": "酒店", "minutes": 25, "source": "高德"}]}
    day = build_timeline(plan)["itinerary"][0]
    assert [item["label"] for item in day["timeline"] if item["kind"] == "transport"] == [
        "酒店 → A", "A → B", "B → 酒店"]
    assert day["stops"][0]["durationSource"] == "confirmed"
    assert day["stops"][1]["durationSource"] == "ai_recommended"
    assert day["feasibility"]["status"] == "estimated"


def test_unknown_ground_leg_does_not_invent_following_times():
    plan = {"itinerary": [{"day": 1, "date": "2026-10-01", "stops": [{"id": "a", "name": "A"}]}],
            "groundJourneys": [{"day": 1, "purpose": "to-place", "from": "酒店", "to": "A", "minutes": None},
                               {"day": 1, "purpose": "return-to-stay", "from": "A", "to": "酒店", "minutes": 20}]}
    day = build_timeline(plan)["itinerary"][0]
    assert day["stops"][0]["start"] is None
    assert day["feasibility"]["status"] == "unknown"
    assert next(item for item in day["timeline"] if item["kind"] == "place")["startAt"] is None


def test_late_arrival_keeps_airport_to_hotel_and_no_activity():
    flight = {"id": "f1", "flightNumber": "CZ123", "departureAt": "2026-10-01T18:00:00",
              "arrivalAt": "2026-10-01T21:00:00", "provider": "supplier"}
    plan = {"flights": [flight], "recommendedOutboundFlightId": "f1",
            "itinerary": [{"day": 1, "date": "2026-10-01", "stops": []}],
            "groundJourneys": [{"day": 1, "purpose": "to-terminal", "from": "出发地", "to": "机场", "minutes": 40},
                               {"day": 1, "purpose": "arrival-to-stay", "from": "机场", "to": "酒店", "minutes": 35}]}
    events = build_timeline(plan)["itinerary"][0]["timeline"]
    assert any(item["kind"] == "flight" for item in events)
    assert any(item["label"] == "机场 → 酒店" and item["startAt"] == "2026-10-01T21:45:00" for item in events)
    assert any(item["label"] == "酒店入住或行李寄存" for item in events)


def test_overnight_arrival_starts_hotel_transfer_on_next_day():
    flight = {"id": "f1", "flightNumber": "CZ123", "departureAt": "2026-10-01T23:00:00",
              "arrivalAt": "2026-10-02T01:00:00"}
    plan = {"flights": [flight], "recommendedOutboundFlightId": "f1",
            "itinerary": [{"day": 1, "date": "2026-10-01", "stops": []},
                          {"day": 2, "date": "2026-10-02", "stops": []}],
            "groundJourneys": [{"day": 1, "purpose": "to-terminal", "from": "出发地", "to": "机场", "minutes": 40},
                               {"day": 2, "purpose": "arrival-to-stay", "from": "机场", "to": "酒店", "minutes": 35}]}
    days = build_timeline(plan)["itinerary"]
    assert any(item["kind"] == "flight" for item in days[0]["timeline"])
    assert any(item["label"] == "机场 → 酒店" and item["startAt"] == "2026-10-02T01:45:00"
               for item in days[1]["timeline"])


def test_reconstruction_preserves_user_confirmed_date_and_unknown_gaps():
    photos = [{"id": "p1", "capturedDay": "2026-09-01", "capturedAt": "2026-09-01T14:00",
               "gps": None, "tags": {"scene": "西湖", "location_clue": "杭州西湖", "ocr": []}}]
    previous = {"days": [{"date": "2026-09-02", "events": [{"id": "photo-p1", "date": "2026-09-02",
        "label": "西湖游船", "source": "user_confirmed", "confidence": "confirmed", "photoIds": ["p1"]}]}]}
    result = reconstruct(photos, previous)
    assert result["days"][-1]["events"][0]["label"] == "西湖游船"
    assert result["days"][-1]["date"] == "2026-09-02"
    assert "未知" in result["notice"]


def test_amap_and_device_coordinates_round_trip_without_double_shift():
    device = {"lat": 30.25, "lng": 120.15}
    amap_point = wgs_to_gcj(**device)
    rendered = gcj_to_wgs(**amap_point)
    assert abs(rendered["lat"] - device["lat"]) < 0.00001
    assert abs(rendered["lng"] - device["lng"]) < 0.00001


def test_early_arrival_can_use_the_first_afternoon():
    state = {"destination": "杭州", "originCity": "北京", "startDate": "2026-10-01", "days": 3,
             "requiredStays": [], "totalBudgetCny": None, "providerStatus": {}, "hotels": [], "trains": [],
             "returnTrains": [], "returnFlights": [], "flights": [{"id": "f1", "departureAt": "2026-10-01T07:00:00",
             "arrivalAt": "2026-10-01T09:00:00", "totalPrice": 800}],
             "places": [{"id": "west-lake", "name": "西湖", "city": "杭州", "lat": 30.25, "lng": 120.15}]}
    result = asyncio.run(draft_plan({"placeIds": ["west-lake"]}, state))
    assert result["ok"]
    assert state["plan"]["itinerary"][0]["stops"][0]["id"] == "west-lake"
