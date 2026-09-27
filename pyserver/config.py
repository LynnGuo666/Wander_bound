"""Private YAML settings and provider priority."""
from __future__ import annotations

import os
import tempfile
from pathlib import Path
from threading import RLock

import yaml

KEY_ENV = {"stepfun": "STEPFUN_API_KEY", "amap": "AMAP_WEB_KEY", "dida": "DIDA_API_KEY",
           "duffel": "DUFFEL_API_KEY", "tuniu": "TUNIU_API_KEY", "flyai": "FLYAI_API_KEY"}
PRIORITY_OPTIONS = {"flights": ["duffel", "flyai", "tuniu"],
                    "trains": ["rail12306", "flyai", "tuniu"],
                    "attractions": ["flyai", "tuniu"]}


class ConfigStore:
    def __init__(self, path: str | Path | None = None):
        self.path = Path(path or os.getenv("TRAVEL_CONFIG_PATH", "config.yml"))
        self.lock = RLock()

    def read(self) -> dict:
        with self.lock:
            raw = yaml.safe_load(self.path.read_text()) if self.path.exists() else {}
            if not isinstance(raw, dict):
                raise ValueError("config.yml 格式无效")
            credentials = raw.get("credentials") or {}
            if not isinstance(credentials, dict):
                raise ValueError("config.yml 密钥格式无效")
            priorities = {key: list(values) for key, values in PRIORITY_OPTIONS.items()}
            for key, values in (raw.get("priorities") or {}).items():
                if key not in priorities or not isinstance(values, list) or set(values) != set(priorities[key]) or len(values) != len(priorities[key]):
                    raise ValueError(f"{key} 优先级无效")
                priorities[key] = values
            return {"credentials": {key: value for key, value in credentials.items() if key in KEY_ENV and isinstance(value, str) and value},
                    "priorities": priorities}

    def update(self, patch: dict) -> dict:
        with self.lock:
            current = self.read()
            for key, value in (patch.get("credentials") or {}).items():
                if key not in KEY_ENV or (value is not None and (not isinstance(value, str) or len(value) > 512 or any(ord(c) < 32 for c in value))):
                    raise ValueError("密钥格式无效")
                if value is None:
                    current["credentials"].pop(key, None)
                elif value:
                    current["credentials"][key] = value.strip()
            for key, values in (patch.get("priorities") or {}).items():
                if key not in PRIORITY_OPTIONS or not isinstance(values, list) or set(values) != set(PRIORITY_OPTIONS[key]) or len(values) != len(PRIORITY_OPTIONS[key]):
                    raise ValueError("来源优先级无效")
                current["priorities"][key] = values
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=self.path.parent, delete=False) as temporary:
                os.chmod(temporary.name, 0o600)
                yaml.safe_dump(current, temporary, allow_unicode=True, sort_keys=False)
            os.replace(temporary.name, self.path)
            return self.public()

    def credentials(self, supplied: dict | None = None) -> dict:
        stored = self.read()["credentials"]
        return {key: (supplied or {}).get(key) or stored.get(key) or os.getenv(env) or (os.getenv("STEP_API_KEY") if key == "stepfun" else None)
                for key, env in KEY_ENV.items()}

    def public(self) -> dict:
        current = self.read()
        return {"file": "config.yml", "credentials": {key: {"stored": bool(current["credentials"].get(key)),
                  "environment": bool(os.getenv(env)), "configured": bool(current["credentials"].get(key) or os.getenv(env))}
                  for key, env in KEY_ENV.items()}, "priorities": current["priorities"], "priorityOptions": PRIORITY_OPTIONS}
