"""Local-time admission window for background media generation."""
from __future__ import annotations

import os
import time as monotonic_time
from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo


class NightWindow:
    def __init__(self, enabled: bool, *, timezone: str | None = None,
                 start: str | None = None, end: str | None = None):
        self.enabled = enabled
        self.zone = ZoneInfo(timezone or os.getenv("SPARK_NIGHT_TIMEZONE", "Asia/Shanghai"))
        self.start = self._parse(start or os.getenv("SPARK_NIGHT_START", "23:00"))
        self.end = self._parse(end or os.getenv("SPARK_NIGHT_END", "07:00"))
        if self.start == self.end:
            raise ValueError("夜间窗口的开始和结束时间不能相同")

    @staticmethod
    def _parse(value: str) -> time:
        try:
            parsed = time.fromisoformat(value)
        except ValueError as exc:
            raise ValueError("夜间窗口时间应为 HH:MM") from exc
        if parsed.tzinfo or parsed.second or parsed.microsecond:
            raise ValueError("夜间窗口时间应为 HH:MM")
        return parsed

    def seconds_until_open(self, instant: datetime | None = None) -> float:
        if not self.enabled:
            return 0
        local = (instant or datetime.now(self.zone)).astimezone(self.zone)
        clock = local.timetz().replace(tzinfo=None)
        if self.start < self.end:
            open_now = self.start <= clock < self.end
        else:
            open_now = clock >= self.start or clock < self.end
        if open_now:
            return 0
        opening = datetime.combine(local.date(), self.start, self.zone)
        if opening <= local:
            opening += timedelta(days=1)
        return max(0, (opening - local).total_seconds())

    def next_open_iso(self, instant: datetime | None = None) -> str:
        local = (instant or datetime.now(self.zone)).astimezone(self.zone)
        return (local + timedelta(seconds=self.seconds_until_open(local))).isoformat(timespec="seconds")


class NightLoadGate:
    """Require a sustained quiet host before taking a background GPU job."""

    POLL_SECONDS = 30
    QUIET_SECONDS = 30

    def __init__(self, controller):
        self.controller = controller
        self.quiet_since: float | None = None

    async def seconds_until_idle(self) -> float:
        if not getattr(self.controller, "enabled", False):
            return 0
        busy = (self.controller.active is not None or self.controller.loading_model is not None
                or self.controller.lock.locked())
        memory = self.controller._memory()
        available = memory.get("availableGiB")
        full = memory.get("pressureFull10")
        some = memory.get("pressureSome10")
        busy |= (available is None or available < self.controller.reserve_gib
                 or full is None or full > 1 or some is None or some > 5)
        try:
            load = os.getloadavg()[0] / max(1, os.cpu_count() or 1)
            busy |= load > 0.75
        except OSError:
            busy = True
        gpu = await self.controller._gpu()
        utilization = gpu.get("utilizationPercent")
        # GB10 may not expose utilization; memory PSI and CPU remain usable.
        if utilization is not None:
            busy |= utilization > 20
        if busy:
            self.quiet_since = None
            return self.POLL_SECONDS
        current = monotonic_time.monotonic()
        if self.quiet_since is None:
            self.quiet_since = current
        remaining = self.QUIET_SECONDS - (current - self.quiet_since)
        return max(0, remaining)
