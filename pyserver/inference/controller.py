"""Serialize heavy inference and manage a fixed set of private model services."""
from __future__ import annotations

import asyncio
import fcntl
import os
import time
from contextlib import asynccontextmanager
from dataclasses import dataclass

import httpx


@dataclass(frozen=True)
class ModelSpec:
    name: str
    label: str
    service: str
    url: str
    health_path: str
    minimum_gib: int


class ModelController:
    def __init__(self, *, enabled: bool | None = None, idle_seconds: int | None = None,
                 specs: tuple[ModelSpec, ...] | None = None):
        self.enabled = (os.getenv("SPARK_MODEL_CONTROL") == "1") if enabled is None else enabled
        self.idle_seconds = idle_seconds if idle_seconds is not None else int(os.getenv("SPARK_MODEL_IDLE_SECONDS", "600"))
        self.chat_idle_seconds = int(os.getenv("SPARK_QWEN38_IDLE_SECONDS", "1800"))
        self.primary_chat = self.enabled and os.getenv("SPARK_QWEN38_STICKY") == "1"
        self.primary_paused = False
        self.reserve_gib = 16
        self.peak_gib = {"image": 26, "video": 50, "chat": 60}
        self.specs = {item.name: item for item in (specs or (
            ModelSpec("image", "Qwen-Image-2.1", "qwen21-comfy.service", os.getenv("SPARK_QWEN_COMFY_URL", "http://127.0.0.1:18191"), "/system_stats", 24),
            ModelSpec("video", "MiniMax H3", "minimax-h3-comfy.service", os.getenv("SPARK_COMFY_URL", "http://127.0.0.1:18188"), "/system_stats", 48),
            ModelSpec("chat", "Qwen3.8-27B", "qwen38.service", os.getenv("SPARK_QWEN38_URL", "http://127.0.0.1:8192"), "/v1/models", 32),
        ))}
        self.lock = asyncio.Lock()
        self.active: str | None = None
        self.last_used: dict[str, float] = {}
        self.phase = "idle"
        self.error: str | None = None
        self.sweeper: asyncio.Task | None = None
        self.warm_task: asyncio.Task | None = None
        self.loading_model: str | None = None
        self.owner_file = None

    async def _command(self, *args: str, timeout: int = 30) -> str:
        try:
            proc = await asyncio.create_subprocess_exec(*args, stdout=asyncio.subprocess.PIPE,
                                                        stderr=asyncio.subprocess.PIPE)
        except FileNotFoundError:
            raise RuntimeError(f"未安装命令：{args[0]}") from None
        try:
            output, error = await asyncio.wait_for(proc.communicate(), timeout)
        except asyncio.TimeoutError:
            proc.kill()
            await proc.communicate()
            raise RuntimeError(f"服务操作超时：{args[-1]}") from None
        if proc.returncode:
            raise RuntimeError(f"服务操作失败：{args[-1]} ({error.decode(errors='replace')[:160].strip()})")
        return output.decode(errors="replace").strip()

    async def _service_state(self, spec: ModelSpec) -> str:
        if not self.enabled:
            return "external"
        try:
            loaded = await self._command("systemctl", "--user", "show", "--property=LoadState", "--value", spec.service, timeout=8)
            if loaded != "loaded":
                return "not_installed"
            return (await self._command("systemctl", "--user", "is-active", spec.service, timeout=8)) or "inactive"
        except RuntimeError:
            return "stopped"

    async def _ready(self, spec: ModelSpec) -> bool:
        try:
            async with httpx.AsyncClient(timeout=3) as client:
                response = await client.get(spec.url.rstrip("/") + spec.health_path)
            return response.status_code == 200
        except httpx.HTTPError:
            return False

    async def _comfy_busy(self, spec: ModelSpec) -> bool:
        if spec.name not in {"image", "video"}:
            return False
        try:
            async with httpx.AsyncClient(timeout=3) as client:
                response = await client.get(spec.url.rstrip("/") + "/queue")
            response.raise_for_status()
            queue = response.json()
            return bool(queue.get("queue_running") or queue.get("queue_pending"))
        except (httpx.HTTPError, ValueError):
            return True  # Unknown state must never be treated as idle.

    async def _chat_busy(self, spec: ModelSpec) -> bool:
        try:
            async with httpx.AsyncClient(timeout=3) as client:
                response = await client.get(spec.url.rstrip("/") + "/metrics")
            response.raise_for_status()
            seen = set()
            for line in response.text.splitlines():
                name = line.split("{", 1)[0].split(" ", 1)[0]
                if name in {"vllm:num_requests_running", "vllm:num_requests_waiting"}:
                    seen.add(name)
                    if float(line.rsplit(" ", 1)[-1]) > 0:
                        return True
            return len(seen) != 2
        except (httpx.HTTPError, ValueError):
            return True

    @staticmethod
    def _memory() -> dict:
        values = {}
        try:
            for line in open("/proc/meminfo"):
                if line.startswith(("MemTotal:", "MemAvailable:", "MemFree:", "SwapFree:")):
                    key, value = line.split(":", 1)
                    values[key] = round(int(value.strip().split()[0]) / 1024 / 1024, 1)
        except OSError:
            pass
        try:
            lines = open("/proc/pressure/memory").read().splitlines()
            values["pressureSome10"] = float(lines[0].split("avg10=")[1].split()[0])
            values["pressureFull10"] = float(lines[1].split("avg10=")[1].split()[0])
        except (OSError, IndexError, ValueError):
            pass
        return {"totalGiB": values.get("MemTotal"), "availableGiB": values.get("MemAvailable"),
                "freeGiB": values.get("MemFree"), "swapFreeGiB": values.get("SwapFree"),
                "pressureSome10": values.get("pressureSome10"), "pressureFull10": values.get("pressureFull10")}

    async def _stop(self, spec: ModelSpec):
        if await self._service_state(spec) != "active":
            return
        if await (self._chat_busy(spec) if spec.name == "chat" else self._comfy_busy(spec)):
            raise RuntimeError(f"{spec.label} 仍有任务，不能卸载")
        await asyncio.sleep(1)
        if await (self._chat_busy(spec) if spec.name == "chat" else self._comfy_busy(spec)):
            raise RuntimeError(f"{spec.label} 仍有任务，不能卸载")
        self.phase = "releasing"
        await self._command("systemctl", "--user", "stop", spec.service, timeout=45)
        self.last_used.pop(spec.name, None)

    async def _start(self, spec: ModelSpec):
        self.phase = "loading_model"
        memory = self._memory()
        available = memory.get("availableGiB")
        required = max(spec.minimum_gib, self.peak_gib[spec.name] + self.reserve_gib)
        if available is None or available < required:
            raise RuntimeError(f"可用内存 {available} GiB，启动 {spec.label} 至少需要 {required} GiB")
        if (memory.get("pressureFull10") or 0) > 1:
            raise RuntimeError("系统内存压力过高，暂缓加载模型")
        await self._command("systemctl", "--user", "start", spec.service, timeout=45)
        for _ in range(450 if spec.name == "chat" else 60):
            if await self._ready(spec):
                self.phase = "ready"
                return
            await asyncio.sleep(2)
        raise RuntimeError(f"{spec.label} 启动后未通过健康检查")

    async def _ensure(self, name: str):
        spec = self.specs[name]
        if not self.enabled:
            if not await self._ready(spec):
                raise RuntimeError(f"{spec.label} 未运行")
            return
        state = await self._service_state(spec)
        load_needed = state != "active" or not await self._ready(spec)
        if name == "video":
            await self._stop(self.specs["image"])
            await self._stop(self.specs["chat"])
        elif name == "image":
            await self._stop(self.specs["video"])
            if await self._service_state(self.specs["chat"]) == "active":
                available = self._memory().get("availableGiB")
                required = self.peak_gib["image"] + self.reserve_gib if load_needed else self.reserve_gib
                if available is None or available < required:
                    await self._stop(self.specs["chat"])
        elif name == "chat":
            await self._stop(self.specs["video"])
            if await self._service_state(self.specs["image"]) == "active":
                available = self._memory().get("availableGiB")
                required = self.peak_gib["chat"] + self.reserve_gib if load_needed else self.reserve_gib
                if available is None or available < required:
                    await self._stop(self.specs["image"])
        if load_needed:
            await self._start(spec)
        self.last_used[name] = time.monotonic()
        self.error = None

    @asynccontextmanager
    async def use(self, name: str):
        if name not in self.specs:
            raise ValueError("未知模型")
        async with self.lock:
            try:
                await self._ensure(name)
                self.active = name
                self.phase = "running"
                yield self.specs[name]
            except Exception as exc:
                self.error = str(exc)[:200]
                self.phase = "degraded"
                raise
            finally:
                self.active = None
                self.last_used[name] = time.monotonic()
                if self.phase == "running":
                    self.phase = "cooling"

    async def warm(self, name: str):
        if name not in self.specs:
            raise ValueError("未知模型")
        if not self.enabled:
            raise RuntimeError("此环境未启用模型服务控制")
        async with self.lock:
            try:
                await self._ensure(name)
                self.phase = "cooling"
            except RuntimeError as exc:
                self.phase = "degraded"
                self.error = str(exc)[:200]
                raise

    def begin_warm(self, name: str):
        if name not in self.specs:
            raise ValueError("未知模型")
        if not self.enabled:
            raise RuntimeError("此环境未启用模型服务控制")
        if name == "chat":
            self.primary_paused = False
        if self.warm_task and not self.warm_task.done():
            if self.loading_model != name:
                raise RuntimeError("另一个模型正在加载")
            return
        self.loading_model = name
        self.phase = "loading_model"

        async def run():
            try:
                await self.warm(name)
            except RuntimeError:
                pass  # warm() records the error for the status endpoint.
            finally:
                self.loading_model = None

        self.warm_task = asyncio.create_task(run())

    async def release(self, name: str):
        if name not in self.specs:
            raise ValueError("未知模型")
        if not self.enabled:
            raise RuntimeError("此环境未启用模型服务控制")
        async with self.lock:
            try:
                await self._stop(self.specs[name])
                if name == "chat":
                    self.primary_paused = True
                self.phase = "idle"
            except RuntimeError as exc:
                self.error = str(exc)[:200]
                raise

    async def _gpu(self) -> dict:
        try:
            data = await self._command("nvidia-smi", "--query-gpu=utilization.gpu,power.draw", "--format=csv,noheader,nounits", timeout=5)
            utilization, power = [part.strip() for part in data.splitlines()[0].split(",")]
            return {"utilizationPercent": float(utilization), "powerWatts": float(power)}
        except (RuntimeError, ValueError, IndexError):
            return {"utilizationPercent": None, "powerWatts": None}

    async def status(self) -> dict:
        async def describe(spec: ModelSpec) -> dict:
            state = await self._service_state(spec)
            ready = await self._ready(spec) if state in {"active", "external"} else False
            return {"id": spec.name, "label": spec.label, "service": spec.service,
                    "state": "ready" if ready else "stopped_on_demand" if state == "stopped" and self.enabled else state,
                    "active": self.active == spec.name,
                    "idleTimeoutSeconds": self.chat_idle_seconds if spec.name == "chat" else self.idle_seconds,
                    "idleSeconds": round(time.monotonic() - self.last_used[spec.name]) if spec.name in self.last_used else None}
        models = await asyncio.gather(*(describe(spec) for spec in self.specs.values()))
        return {"enabled": self.enabled, "phase": self.phase, "activeModel": self.active,
                "loadingModel": self.loading_model,
                "primaryChat": self.primary_chat and not self.primary_paused,
                "idleTimeoutSeconds": self.idle_seconds, "error": self.error, "memory": self._memory(), "gpu": await self._gpu(),
                "models": models}

    async def _sweep(self):
        while True:
            await asyncio.sleep(15)
            if not self.enabled or self.lock.locked():
                continue
            async with self.lock:
                for spec in self.specs.values():
                    last = self.last_used.get(spec.name)
                    if last is None:
                        self.last_used[spec.name] = time.monotonic()
                    elif spec.name == "chat" and self.primary_chat and not self.primary_paused:
                        if (self._memory().get("availableGiB") or 0) < self.reserve_gib:
                            try:
                                await self._stop(spec)
                                self.error = "可用内存低于安全余量，已释放常驻 Qwen"
                            except RuntimeError as exc:
                                self.error = str(exc)[:200]
                    elif time.monotonic() - last >= (self.chat_idle_seconds if spec.name == "chat" else self.idle_seconds):
                        try:
                            await self._stop(spec)
                            if self.phase == "cooling":
                                self.phase = "idle"
                        except RuntimeError as exc:
                            self.error = str(exc)[:200]

    def start(self):
        if self.enabled and self.sweeper is None:
            path = os.getenv("SPARK_MODEL_LOCK_FILE", "data/model-controller.lock")
            os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
            self.owner_file = open(path, "a+")
            try:
                fcntl.flock(self.owner_file, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                self.owner_file.close()
                self.owner_file = None
                raise RuntimeError("已有模型控制器在运行") from None
            self.sweeper = asyncio.create_task(self._sweep())

    async def close(self):
        if self.warm_task and not self.warm_task.done():
            self.warm_task.cancel()
            try:
                await self.warm_task
            except asyncio.CancelledError:
                pass
        self.warm_task = None
        if self.sweeper:
            self.sweeper.cancel()
            try:
                await self.sweeper
            except asyncio.CancelledError:
                pass
            self.sweeper = None
        if self.owner_file:
            fcntl.flock(self.owner_file, fcntl.LOCK_UN)
            self.owner_file.close()
            self.owner_file = None
