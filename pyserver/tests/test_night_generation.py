"""Night work waits for both the local window and a quiet Spark host."""
import asyncio
from datetime import datetime
from zoneinfo import ZoneInfo

from pyserver.inference.night_window import NightLoadGate, NightWindow
from test_local_runtime import make_jobs


def test_window_crosses_midnight_and_calculates_next_open():
    window = NightWindow(True, timezone="Asia/Shanghai", start="23:00", end="07:00")
    zone = ZoneInfo("Asia/Shanghai")
    assert window.seconds_until_open(datetime(2026, 9, 30, 23, 30, tzinfo=zone)) == 0
    assert window.seconds_until_open(datetime(2026, 10, 1, 6, 30, tzinfo=zone)) == 0
    assert window.seconds_until_open(datetime(2026, 10, 1, 7, 0, tzinfo=zone)) == 16 * 3600
    assert window.next_open_iso(datetime(2026, 10, 1, 14, 0, tzinfo=zone)) == "2026-10-01T23:00:00+08:00"


def test_load_gate_requires_sustained_low_pressure(monkeypatch):
    class Controller:
        enabled = True
        active = None
        loading_model = None
        reserve_gib = 16
        lock = asyncio.Lock()
        memory = {"availableGiB": 70, "pressureFull10": 0, "pressureSome10": 0}
        utilization = 3

        def _memory(self):
            return self.memory

        async def _gpu(self):
            return {"utilizationPercent": self.utilization}

    controller = Controller()
    gate = NightLoadGate(controller)
    clock = [100.0]
    monkeypatch.setattr("pyserver.inference.night_window.monotonic_time.monotonic", lambda: clock[0])
    monkeypatch.setattr("pyserver.inference.night_window.os.getloadavg", lambda: (0, 0, 0))

    async def scenario():
        assert await gate.seconds_until_idle() == 30
        clock[0] += 31
        assert await gate.seconds_until_idle() == 0
        controller.utilization = 80
        assert await gate.seconds_until_idle() == 30
        controller.utilization = 1
        assert await gate.seconds_until_idle() == 30
        controller.memory = {"availableGiB": 70, "pressureFull10": 2, "pressureSome10": 0}
        assert await gate.seconds_until_idle() == 30

    asyncio.run(scenario())


def test_daytime_media_waits_without_blocking_interactive_edit(tmp_path, monkeypatch):
    jobs, _, _, _, trip, chosen, _ = make_jobs(tmp_path, monkeypatch)

    class Window:
        closed = True

        def seconds_until_open(self):
            return 3600 if self.closed else 0

        def next_open_iso(self):
            return "2026-10-01T23:00:00+08:00"

    class Gate:
        quiet_since = None

        async def seconds_until_idle(self):
            return 0

    jobs.night = Window()
    jobs.night_load = Gate()
    jobs._schedule = jobs.wake.set
    memory = jobs.submit("memory", {"tripId": trip["id"], "photoIds": [chosen["id"]], "title": "旅行"})
    assert memory["status"] == "queued"
    assert memory["scheduledAt"] == "2026-10-01T23:00:00+08:00"

    async def scenario():
        completed = asyncio.Event()
        order = []

        async def run(job_id):
            job = jobs.get(job_id)
            order.append(job["kind"])
            job["status"] = "succeeded"
            jobs.save(job)
            completed.set()

        jobs._run = run
        worker = asyncio.create_task(jobs._drain())
        edit = jobs.submit("edit", {"photoId": chosen["id"], "prompt": "travel"})
        await asyncio.wait_for(completed.wait(), 1)
        assert order == ["edit"]
        assert jobs.get(memory["id"])["status"] == "queued"
        assert jobs.get(edit["id"])["status"] == "succeeded"
        jobs.night.closed = False
        jobs.wake.set()
        await asyncio.wait_for(worker, 1)
        assert order == ["edit", "memory"]

    asyncio.run(scenario())
