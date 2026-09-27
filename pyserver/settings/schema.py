"""Supported credentials and provider priorities."""
KEY_ENV = {"stepfun": "STEPFUN_API_KEY", "amap": "AMAP_WEB_KEY", "dida": "DIDA_API_KEY",
           "duffel": "DUFFEL_API_KEY", "tuniu": "TUNIU_API_KEY", "flyai": "FLYAI_API_KEY"}
PRIORITY_OPTIONS = {"flights": ["duffel", "flyai", "tuniu"],
                    "trains": ["rail12306", "flyai", "tuniu"],
                    "attractions": ["flyai", "tuniu"]}
