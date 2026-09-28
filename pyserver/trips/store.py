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
from .presentation import now, public_trip
from ..accounts import current_user

ID = re.compile(r"^[a-f0-9-]{36}$")


class TripStore:
    def __init__(self, root: str | Path | None = None):
        self.root = Path(root or os.getenv("TRIP_STORAGE_DIR") or "data/trips")
        self.lock = RLock()

    def get(self, trip_id: str) -> dict | None:
        if not ID.fullmatch(trip_id or ""):
            return None
        try:
            trip = json.loads((self.root / f"{trip_id}.json").read_text())
            user = current_user.get()
            return trip if user is None or trip.get("ownerId") == user["id"] else None
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
                "ownerId": (current_user.get() or {}).get("id"),
                "createdAt": now(), "phase": "planning", "plan": None, "events": [], "revisions": [],
                "request": request, "continuation": None}
        return self.save(trip)

    def list(self) -> list[dict]:
        self.root.mkdir(parents=True, exist_ok=True, mode=0o700)
        records = [self.get(file.stem) for file in self.root.glob("*.json")]
        return sorted((public_trip(item) for item in records if item), key=lambda item: item["updatedAt"], reverse=True)
