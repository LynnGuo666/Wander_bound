"""Durable trip, conversation, and plan revision records."""
from __future__ import annotations

import json
import os
import re
import tempfile
import uuid
from datetime import datetime
from pathlib import Path
from threading import RLock
from zoneinfo import ZoneInfo

ID = re.compile(r"^[a-f0-9-]{36}$")


def now() -> str:
    return datetime.now(ZoneInfo("Asia/Shanghai")).isoformat()


def public_trip(trip: dict, detail: bool = False) -> dict:
    result = {key: value for key, value in trip.items() if key not in {"continuation", "request"} and (detail or key not in {"events", "revisions"})}
    plan = trip.get("plan") or {}
    today = datetime.now(ZoneInfo("Asia/Shanghai")).date().isoformat()
    result["status"] = "ended" if plan.get("endDate") and today > plan["endDate"] else "in_progress" if plan.get("startDate") and today >= plan["startDate"] else "not_started"
    return result


class TripStore:
    def __init__(self, root: str | Path | None = None):
        self.root = Path(root or os.getenv("TRIP_STORAGE_DIR", "data/trips"))
        self.lock = RLock()

    def get(self, trip_id: str) -> dict | None:
        if not ID.fullmatch(trip_id or ""):
            return None
        try:
            return json.loads((self.root / f"{trip_id}.json").read_text())
        except (FileNotFoundError, json.JSONDecodeError):
            return None

    def save(self, trip: dict) -> dict:
        with self.lock:
            self.root.mkdir(parents=True, exist_ok=True, mode=0o700)
            trip["updatedAt"] = now()
            with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=self.root, delete=False) as temporary:
                os.chmod(temporary.name, 0o600)
                json.dump(trip, temporary, ensure_ascii=False)
            os.replace(temporary.name, self.root / f"{trip['id']}.json")
            return trip

    def create(self, request: dict) -> dict:
        trip = {"id": str(uuid.uuid4()), "title": str(request.get("query") or "新行程")[:80],
                "createdAt": now(), "phase": "planning", "plan": None, "events": [], "revisions": [],
                "request": request, "continuation": None}
        return self.save(trip)

    def list(self) -> list[dict]:
        self.root.mkdir(parents=True, exist_ok=True, mode=0o700)
        records = [self.get(file.stem) for file in self.root.glob("*.json")]
        return sorted((public_trip(item) for item in records if item), key=lambda item: item["updatedAt"], reverse=True)
