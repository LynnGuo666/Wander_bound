"""Spark 上那台多模态服务的公共配置：端口、模型名、鉴权。

选优打标（`vlm`）和精修建议（`develop`）打的是同一台 vLLM，配置只该有一份。
此前两边各自硬编码默认值，结果漂了两次：选优分支还指着旧端口和旧模型名，精修分支
的模型名和服务端实际 serve 的名字对不上，请求直接 400。默认值集中在这里，改一处
两边同时跟上；env 仍可覆盖，调用时读而不是 import 时读，方便测试注入。
"""
from __future__ import annotations

import os

# 团队约定 18192 作为对外唯一入口；Spark 上 vLLM 听 8192，由 spark-tunnel.sh 转发。
DEFAULT_VISION_BASE_URL = "http://127.0.0.1:18192/v1"
# vLLM 的 --served-model-name。对不上就是 400，所以这个名字以服务端实际 serve 的为准。
DEFAULT_VISION_MODEL = "qwen38-27b"


def vision_base_url() -> str:
    return os.getenv("DGX_VISION_BASE_URL", DEFAULT_VISION_BASE_URL).rstrip("/")


def vision_model() -> str:
    return os.getenv("DGX_VISION_MODEL", DEFAULT_VISION_MODEL)


def vision_token() -> str:
    return os.getenv("DGX_VISION_TOKEN", "")
