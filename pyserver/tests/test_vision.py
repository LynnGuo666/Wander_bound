"""视觉模型端点的唯一来源：选优与精修必须拿到同一份默认值。"""
from __future__ import annotations

import os

from pyserver.media import develop, vision


def test_defaults_point_at_the_deployed_tunnel_and_model():
    """默认值就是部署事实：18192 是团队约定入口，qwen38-27b 是服务端 serve 的名字。

    这两个数写错过两次——一边还指着旧端口和旧模型名，另一边的模型名和服务端对不上，
    请求直接 400。默认值收在 vision 一处，这里把它钉住。
    """
    assert vision.DEFAULT_VISION_BASE_URL == "http://127.0.0.1:18192/v1"
    assert vision.DEFAULT_VISION_MODEL == "qwen38-27b"
    for name in ("DGX_VISION_BASE_URL", "DGX_VISION_MODEL"):
        os.environ.pop(name, None)
    assert vision.vision_base_url() == "http://127.0.0.1:18192/v1"
    assert vision.vision_model() == "qwen38-27b"


def test_both_features_resolve_the_same_endpoint(monkeypatch):
    """选优（vlm）和精修（develop）打的是同一台 vLLM，解析结果必须一致。"""
    monkeypatch.setenv("DGX_VISION_BASE_URL", "http://127.0.0.1:18192/v1")
    monkeypatch.setenv("DGX_VISION_MODEL", "qwen38-27b")
    monkeypatch.delenv("PYSERVER_VLM_BASE_URL", raising=False)
    monkeypatch.delenv("PYSERVER_VLM_MODEL", raising=False)

    from pyserver.media import vlm

    develop_url, develop_model = vision.vision_base_url(), vision.vision_model()
    vlm_url = vlm._first_env("PYSERVER_VLM_BASE_URL") or vision.vision_base_url()
    vlm_model = vlm._first_env("PYSERVER_VLM_MODEL") or vision.vision_model()
    assert (vlm_url, vlm_model) == (develop_url, develop_model)


def test_curation_side_can_override_without_touching_refinement(monkeypatch):
    """选优侧有独立的 PYSERVER_VLM_* 覆盖，且不影响精修读到的值。"""
    monkeypatch.setenv("DGX_VISION_MODEL", "qwen38-27b")
    monkeypatch.setenv("PYSERVER_VLM_MODEL", "some-other-vl-model")

    from pyserver.media import vlm

    assert vlm._first_env("PYSERVER_VLM_MODEL") == "some-other-vl-model"
    assert vision.vision_model() == "qwen38-27b"   # 精修侧不受影响


def test_env_is_read_at_call_time(monkeypatch):
    """调用时读而不是 import 时读，否则测试注入的 env 不会生效。"""
    monkeypatch.setenv("DGX_VISION_MODEL", "injected-model")
    assert vision.vision_model() == "injected-model"


def test_develop_reports_the_model_it_actually_called(monkeypatch):
    """health 上报的模型名要和真正发出去的 payload 一致，否则排查看不到真实后端。"""
    monkeypatch.setenv("DGX_VISION_MODEL", "qwen38-27b")
    assert develop.vision_model() == "qwen38-27b"
    assert vision.vision_model() == develop.vision_model()
