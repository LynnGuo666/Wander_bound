import asyncio

from pyserver.providers import amap


def test_dining_records_keep_source_and_known_prices(monkeypatch):
    async def fake_get(path, params, timeout=8):
        assert path == "place/around"
        return {"status": "1", "pois": [{"id": "p1", "name": "柳州螺蛳粉", "location": "109.4,24.3",
                "biz_ext": {"rating": "4.6", "cost": "28"}, "photos": [{"url": "https://example.test/photo.jpg", "title": "店面"}]}]}

    monkeypatch.setattr(amap, "_get", fake_get)
    result = asyncio.run(amap.search_dining("柳州", [{"day": 2, "lat": 24.3, "lng": 109.4}], "test-key"))
    assert result[0]["day"] == 2
    assert result[0]["averageCost"] == 28
    assert result[0]["sourceRecords"][0]["kind"] == "place-data"
    assert result[0]["photos"][0]["kind"] == "poi-photo"


def test_ground_route_uses_verified_amap_duration(monkeypatch):
    async def fake_get(path, params, timeout=8):
        assert path == "direction/walking"
        return {"status": "1", "route": {"paths": [{"duration": "601", "distance": "780", "steps": []}]}}

    monkeypatch.setattr(amap, "_get", fake_get)
    plan = {"destination": "柳州", "stayArea": None, "itinerary": [{"day": 1, "city": "柳州", "stops": [
        {"name": "甲", "lat": 24.3, "lng": 109.4}, {"name": "乙", "lat": 24.301, "lng": 109.401}]}]}
    result = asyncio.run(amap.enrich_routes(plan, "test-key"))
    assert result["itinerary"][0]["stops"][1]["travelMinutes"] == 11
    walking = next(item for item in result["groundJourneys"] if item.get("to") == "乙")
    assert walking["source"] == "高德步行路线"
