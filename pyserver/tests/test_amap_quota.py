"""高德月配额保护的行为约束。"""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone

import httpx
import pytest

from pyserver.providers import amap, amap_quota, places


def test_consume_accumulates_and_persists_across_calls(tmp_path):
    path = tmp_path / "amap-quota.json"
    first = asyncio.run(amap_quota.consume("poi", path=path))
    second = asyncio.run(amap_quota.consume("poi", path=path))
    assert first["used"] == 1 and second["used"] == 2
    assert second["limit"] == 1500
    assert amap_quota._month() in path.read_text(encoding="utf-8")


def test_month_rollover_resets_usage(tmp_path):
    path = tmp_path / "amap-quota.json"
    asyncio.run(amap_quota.consume("lbs", cost=45000, path=path))
    result = asyncio.run(amap_quota.consume("lbs", path=path,
                                            now=datetime(2026, 10, 1, tzinfo=timezone.utc)))
    assert result["used"] == 1 and result["month"] == "2026-10"


def test_over_limit_fails_with_explicit_message(tmp_path):
    path = tmp_path / "amap-quota.json"
    asyncio.run(amap_quota.consume("poi", cost=1500, path=path))
    with pytest.raises(RuntimeError, match="配额保护已触发.*1500/1500.*30%"):
        asyncio.run(amap_quota.consume("poi", path=path))
    snapshot = asyncio.run(amap_quota.snapshot(path=path))
    assert snapshot["poi"] == {"used": 1500, "limit": 1500, "freeMonthly": 5000}
    assert snapshot["lbs"] == {"used": 0, "limit": 45000, "freeMonthly": 150000}


def test_unknown_bucket_is_rejected(tmp_path):
    with pytest.raises(ValueError):
        asyncio.run(amap_quota.consume("sms", path=tmp_path / "q.json"))


def test_concurrent_consumes_are_serialized(tmp_path):
    path = tmp_path / "amap-quota.json"

    async def burst():
        await asyncio.gather(*(amap_quota.consume("poi", path=path) for _ in range(25)))

    asyncio.run(burst())
    snapshot = asyncio.run(amap_quota.snapshot(path=path))
    assert snapshot["poi"]["used"] == 25


def test_dining_search_consumes_poi_quota(monkeypatch, tmp_path):
    monkeypatch.setenv("TRAVEL_AMAP_QUOTA_FILE", str(tmp_path / "quota.json"))

    async def fake_get(path, params, timeout=8):
        return {"status": "1", "pois": []}

    monkeypatch.setattr(amap, "_get", fake_get)
    asyncio.run(amap.search_dining("柳州", [{"day": 1, "lat": 24.3, "lng": 109.4}], "test-key"))
    snapshot = asyncio.run(amap_quota.snapshot())
    assert snapshot["poi"]["used"] == 1 and snapshot["lbs"]["used"] == 0


def test_ground_routes_consume_lbs_quota(monkeypatch, tmp_path):
    monkeypatch.setenv("TRAVEL_AMAP_QUOTA_FILE", str(tmp_path / "quota.json"))

    async def fake_get(path, params, timeout=8):
        return {"status": "1", "route": {"paths": [{"duration": "601", "distance": "780", "steps": []}]}}

    monkeypatch.setattr(amap, "_get", fake_get)
    plan = {"destination": "柳州", "stayArea": None, "itinerary": [{"day": 1, "city": "柳州", "stops": [
        {"name": "甲", "lat": 24.3, "lng": 109.4}, {"name": "乙", "lat": 24.301, "lng": 109.401}]}]}
    asyncio.run(amap.enrich_routes(plan, "test-key"))
    snapshot = asyncio.run(amap_quota.snapshot())
    assert snapshot["lbs"]["used"] == 1 and snapshot["poi"]["used"] == 0


def test_place_search_consumes_poi_quota(monkeypatch, tmp_path):
    monkeypatch.setenv("TRAVEL_AMAP_QUOTA_FILE", str(tmp_path / "quota.json"))

    async def fake_get(self, url, params=None):
        class Response:
            def raise_for_status(self):
                pass

            def json(self):
                return {"status": "1", "pois": [{"id": "a", "name": "西湖", "location": "120.1,30.2",
                        "adname": "西湖区", "type": "风景区;名胜", "address": "龙井路"}]}

        return Response()

    monkeypatch.setattr(httpx.AsyncClient, "get", fake_get)
    found = asyncio.run(places.search_places("杭州", "test-key"))
    assert found[0]["id"] == "a" and found[0]["duration"] is None
    snapshot = asyncio.run(amap_quota.snapshot())
    assert snapshot["poi"]["used"] == 1
