"""Spark 上那台多模态服务的公共配置：端口、模型名、鉴权。

选优打标和精修建议打的是同一台 vLLM。两边曾各自硬编码默认值，模型名和服务端实际
serve 的名字对不上，请求直接 400。默认值只在这里写一份；调用时读 env，方便测试注入。
"""
from __future__ import annotations

import os

# Spark 上 vLLM 听 8192，spark-tunnel.sh 把它转到本机 18192。
DEFAULT_VISION_BASE_URL = "http://127.0.0.1:18192/v1"
# 对应 vLLM 的 --served-model-name，对不上就是 400。
DEFAULT_VISION_MODEL = "qwen38-27b"


def vision_base_url() -> str:
    return os.getenv("DGX_VISION_BASE_URL", DEFAULT_VISION_BASE_URL).rstrip("/")


def vision_model() -> str:
    return os.getenv("DGX_VISION_MODEL", DEFAULT_VISION_MODEL)


def vision_token() -> str:
    return os.getenv("DGX_VISION_TOKEN", "")
