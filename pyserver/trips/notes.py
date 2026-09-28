"""Private, versioned journal text shared by Web and iOS."""
from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from threading import RLock

from .presentation import now


class NoteStore:
    def __init__(self, root: str | Path):
        self.root = Path(root)
        self.lock = RLock()

    def get(self, trip_id: str) -> dict:
        try:
            value = json.loads((self.root / f"{trip_id}.json").read_text())
            if isinstance(value, dict):
                return value
        except (FileNotFoundError, json.JSONDecodeError):
            pass
        return {"tripId": trip_id, "text": "", "version": 0, "updatedAt": None}

    def put(self, trip_id: str, text: str, version: int) -> dict | None:
        with self.lock:
            previous = self.get(trip_id)
            if previous["version"] != version:
                return None
            value = {"tripId": trip_id, "text": text, "version": version + 1, "updatedAt": now()}
            self.root.mkdir(parents=True, exist_ok=True, mode=0o700)
            with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=self.root, delete=False) as temporary:
                os.chmod(temporary.name, 0o600)
                json.dump(value, temporary, ensure_ascii=False)
            os.replace(temporary.name, self.root / f"{trip_id}.json")
            return value
