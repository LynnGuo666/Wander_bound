"""Convert mainland Amap GCJ-02 points for WGS-84 map renderers."""
from __future__ import annotations

import math


def gcj_to_wgs(lat: float, lng: float) -> dict:
    if not (0.8293 <= lat <= 55.8271 and 72.004 <= lng <= 137.8347):
        return {"lat": lat, "lng": lng}
    x, y = lng - 105, lat - 35
    dlat = (-100 + 2*x + 3*y + .2*y*y + .1*x*y + .2*math.sqrt(abs(x))
            + (20*math.sin(6*x*math.pi) + 20*math.sin(2*x*math.pi))*2/3
            + (20*math.sin(y*math.pi) + 40*math.sin(y/3*math.pi))*2/3
            + (160*math.sin(y/12*math.pi) + 320*math.sin(y*math.pi/30))*2/3)
    dlng = (300 + x + 2*y + .1*x*x + .1*x*y + .1*math.sqrt(abs(x))
            + (20*math.sin(6*x*math.pi) + 20*math.sin(2*x*math.pi))*2/3
            + (20*math.sin(x*math.pi) + 40*math.sin(x/3*math.pi))*2/3
            + (150*math.sin(x/12*math.pi) + 300*math.sin(x/30*math.pi))*2/3)
    rad = lat / 180 * math.pi
    magic = 1 - 0.006693421622965943 * math.sin(rad)**2
    dlat = dlat * 180 / ((6335552.717000426 / (magic * math.sqrt(magic))) * math.pi)
    dlng = dlng * 180 / ((6378245 / math.sqrt(magic) * math.cos(rad)) * math.pi)
    return {"lat": lat - dlat, "lng": lng - dlng}


def wgs_to_gcj(lat: float, lng: float) -> dict:
    guess_lat, guess_lng = lat, lng
    for _ in range(4):
        converted = gcj_to_wgs(guess_lat, guess_lng)
        guess_lat += lat - converted["lat"]
        guess_lng += lng - converted["lng"]
    return {"lat": guess_lat, "lng": guess_lng}


def add_map_coordinates(plan: dict) -> dict:
    for day in plan.get("itinerary") or []:
        for stop in day.get("stops") or []:
            if isinstance(stop.get("lat"), (float, int)) and isinstance(stop.get("lng"), (float, int)):
                stop["mapCoordinate"] = gcj_to_wgs(stop["lat"], stop["lng"]) if stop.get("source") == "高德" else {"lat": stop["lat"], "lng": stop["lng"]}
                stop["coordinateSystem"] = "GCJ-02" if stop.get("source") == "高德" else "WGS-84"
    stay = plan.get("stayArea") or {}
    if isinstance(stay.get("lat"), (float, int)) and isinstance(stay.get("lng"), (float, int)):
        stay["mapCoordinate"] = gcj_to_wgs(stay["lat"], stay["lng"])
        stay["coordinateSystem"] = "GCJ-02"
    for terminal in (plan.get("terminals") or {}).values():
        if terminal:
            terminal["mapCoordinate"] = gcj_to_wgs(terminal["lat"], terminal["lng"])
    for route in plan.get("groundJourneys") or []:
        for field in ("fromCoordinate", "toCoordinate"):
            point = route.get(field)
            if point:
                route["map" + field[0].upper() + field[1:]] = gcj_to_wgs(point["lat"], point["lng"])
        route["mapGeometry"] = [gcj_to_wgs(point["lat"], point["lng"]) for point in route.get("geometry") or []]
    return plan
