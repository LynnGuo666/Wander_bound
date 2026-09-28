"""Restricted stdio client for the configured mcp_images server."""
from __future__ import annotations

import asyncio
import json
import os
import shlex
import shutil
import uuid
from pathlib import Path


class MCPImagesClient:
    def __init__(self, command: str | None = None, timeout: float = 45):
        self.command = command if command is not None else os.getenv("MCP_IMAGES_COMMAND", "")
        self.timeout = timeout

    @property
    def configured(self) -> bool:
        return bool(self.command.strip())

    async def _exchange(self, process, message: dict, expected_id: int | None):
        process.stdin.write((json.dumps(message) + "\n").encode())
        await process.stdin.drain()
        if expected_id is None:
            return None
        while True:
            line = await asyncio.wait_for(process.stdout.readline(), timeout=self.timeout)
            if not line:
                raise RuntimeError("mcp_images 子进程已退出")
            response = json.loads(line)
            if response.get("id") == expected_id:
                if response.get("error"):
                    raise RuntimeError(response["error"].get("message", "MCP 调用失败"))
                return response.get("result") or {}

    def _args_for_tool(self, tool: dict, *, source: Path, destination: Path, operation: str, settings: dict):
        schema = tool.get("inputSchema") or {}
        properties = schema.get("properties") or {}
        required = set(schema.get("required") or [])
        crop = settings["crop"]
        width, height = settings["_size"]
        x, y = round(crop["left"] * width), round(crop["top"] * height)
        right = max(x + 1, round((crop["left"] + crop["width"]) * width))
        bottom = max(y + 1, round((crop["top"] + crop["height"]) * height))
        pixel_crop = {"x": x, "y": y, "left": x, "top": y, "right": right, "bottom": bottom,
                      "width": max(1, right - x), "height": max(1, bottom - y)}
        values = {}
        path_names = {"path", "file_path", "image_path", "input_path", "source_path", "output", "output_path", "save_path", "destination_path"}
        has_output = any(name.lower() in {"output", "output_path", "save_path", "destination_path"} for name in properties)
        numeric = {"exposure": settings["exposure"], "brightness": 2 ** settings["exposure"],
                   "contrast": settings["contrast"], "saturation": settings["saturation"],
                   "sharpness": settings["sharpness"], "gamma": settings["gamma"], **pixel_crop}
        for name in properties:
            key = name.lower()
            if key in path_names:
                values[name] = str(destination if key in {"output", "output_path", "save_path", "destination_path"} or not has_output else source)
            elif operation == "crop" and key in pixel_crop:
                values[name] = pixel_crop[key]
            elif operation == "adjust" and key in numeric:
                values[name] = numeric[key]
            elif key in {"x", "left"} and operation == "crop":
                values[name] = pixel_crop["x"]
            elif key in {"y", "top"} and operation == "crop":
                values[name] = pixel_crop["y"]
        missing = required - values.keys()
        if missing:
            raise RuntimeError(f"mcp_images {tool.get('name')} 有未映射参数：{', '.join(sorted(missing))}")
        return values

    @staticmethod
    def _tool_failed(result: dict) -> bool:
        if result.get("isError"):
            return True
        structured = result.get("structuredContent")
        if isinstance(structured, dict) and structured.get("success") is False:
            return True
        for item in result.get("content") or []:
            if item.get("type") == "text":
                try:
                    if json.loads(item["text"]).get("success") is False:
                        return True
                except (ValueError, AttributeError):
                    pass
        return False

    async def develop(self, source: Path, destination: Path, settings: dict, size: tuple[int, int]) -> bytes:
        if not self.configured:
            raise RuntimeError("mcp_images 尚未配置。设置 MCP_IMAGES_COMMAND 后才能生成照片预览。")
        command = shlex.split(self.command)
        if not command:
            raise RuntimeError("MCP_IMAGES_COMMAND 为空")
        process = await asyncio.create_subprocess_exec(*command, stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL)
        try:
            await self._exchange(process, {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {
                "protocolVersion": "2024-11-05", "capabilities": {},
                "clientInfo": {"name": "travel-photo-develop", "version": "1.0.0"}}}, 1)
            await self._exchange(process, {"jsonrpc": "2.0", "method": "notifications/initialized"}, None)
            result = await self._exchange(process, {"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}}, 2)
            tools = {tool.get("name"): tool for tool in result.get("tools", [])}
            working_source = destination.with_name(f"{uuid.uuid4().hex}-source.jpg")
            shutil.copyfile(source, working_source)
            current_source = working_source
            crop = settings["crop"]
            if crop != {"left": 0.0, "top": 0.0, "width": 1.0, "height": 1.0}:
                tool = tools.get("raster_crop")
                if not tool:
                    raise RuntimeError("mcp_images 未提供 raster_crop 工具")
                cropped = destination.with_name(f"{uuid.uuid4().hex}-crop.jpg")
                args = self._args_for_tool(tool, source=current_source, destination=cropped,
                                           operation="crop", settings={**settings, "_size": size})
                result = await self._exchange(process, {"jsonrpc": "2.0", "id": 3, "method": "tools/call",
                    "params": {"name": "raster_crop", "arguments": args}}, 3)
                crop_has_output = any(name.lower() in {"output", "output_path", "save_path", "destination_path"}
                                      for name in (tool.get("inputSchema", {}).get("properties") or {}))
                if self._tool_failed(result) or crop_has_output and not cropped.is_file():
                    raise RuntimeError("mcp_images 裁切失败")
                current_source = cropped if cropped.is_file() else current_source
            tool = tools.get("raster_adjust")
            if not tool:
                raise RuntimeError("mcp_images 未提供 raster_adjust 工具")
            args = self._args_for_tool(tool, source=current_source, destination=destination,
                                       operation="adjust", settings={**settings, "_size": size})
            result = await self._exchange(process, {"jsonrpc": "2.0", "id": 4, "method": "tools/call",
                "params": {"name": "raster_adjust", "arguments": args}}, 4)
            adjust_has_output = any(name.lower() in {"output", "output_path", "save_path", "destination_path"}
                                    for name in (tool.get("inputSchema", {}).get("properties") or {}))
            if self._tool_failed(result) or adjust_has_output and not destination.is_file():
                raise RuntimeError("mcp_images 参数调整失败")
            final_path = destination if destination.is_file() else current_source
            if not final_path.is_file():
                raise RuntimeError("mcp_images 没有生成照片文件")
            return final_path.read_bytes()
        except (OSError, asyncio.TimeoutError, json.JSONDecodeError) as exc:
            raise RuntimeError(f"mcp_images 调用失败：{exc}") from exc
        finally:
            if process.returncode is None:
                try:
                    process.kill()
                except ProcessLookupError:
                    pass
                await process.wait()
