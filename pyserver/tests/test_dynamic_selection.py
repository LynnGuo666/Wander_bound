"""Dynamic-photo AI selection contract tests; model responses here are injected."""
import asyncio
import hashlib
import json
from concurrent.futures import ThreadPoolExecutor

import httpx
import pytest

from pyserver.media.dynamic_sources import DynamicPhotoSources
from pyserver.media.dynamic_selection import (
    DynamicPhotoSelector, SelectionError, analyze_image, validate_assessment,
)
from pyserver.tests.test_dynamic_sources import fixture, jpeg


def ready(tmp_path):
    _, media, trip, _, first, second, _, payload = fixture(tmp_path)
    edited = jpeg("purple", (48, 64))
    developed = media.save_develop(first["id"], edited, {})
    edited = media.bytes(first["id"], developed["variant"])
    sources = DynamicPhotoSources(media)
    job = sources.settle(trip["id"], payload)
    return media, sources, job, first, second, edited


def verdict(pid, *, suitable, score, reason="画面可判断", motion=None):
    return {"photoId": pid, "suitable": suitable, "score": score, "reason": reason,
            "motionPrompt": motion}


def test_selector_uses_frozen_edited_pixels_ranks_once_and_reuses_result(tmp_path):
    media, sources, job, first, second, edited = ready(tmp_path)
    seen = []
    def analyze(content, pid):
        seen.append((pid, hashlib.sha256(content).hexdigest()))
        if pid == first["id"]:
            assert content == edited
            return verdict(pid, suitable=True, score=89, reason="水面纹理可轻微流动",
                           motion="Subtle ripples on the water; steady framing and subjects.")
        return verdict(pid, suitable=True, score=51, reason="树叶可微动",
                       motion="Leaves sway gently; fixed camera and unchanged composition.")
    selector = DynamicPhotoSelector(sources)
    result = selector.run(job["id"], analyze)
    assert result["status"] == "selected"
    assert result["selection"]["selectedPhotoId"] == first["id"]
    assert [item["photoId"] for item in result["selection"]["ranking"]] == [first["id"], second["id"]]
    assert result["selection"]["promptVersion"] and result["selection"]["configuredModel"]
    assert result["selection"]["observedModels"] == []  # injected model has no provider receipt
    assert result["selection"]["ranking"][0]["requestReceipt"]["kind"] == "local_analyzer"
    assert seen[0][1] == job["sourceSnapshot"]["inputs"][0]["sha256"]
    assert selector.run(job["id"], lambda *_: pytest.fail("must reuse"))["status"] == "selected"
    assert len(seen) == 2
    assert json.loads((sources.root / f"{job['id']}.json").read_text())["selection"]["selectedPhotoId"] == first["id"]
    assert media.bytes(first["id"]) != edited


def test_all_unsuitable_is_skipped_without_motion_or_model_fallback(tmp_path):
    _, sources, job, first, second, _ = ready(tmp_path)
    def analyze(_content, pid):
        return verdict(pid, suitable=False, score=20 if pid == first["id"] else 10,
                       reason="人脸或文字为主体，动态化风险高")
    result = DynamicPhotoSelector(sources).run(job["id"], analyze)
    assert result["status"] == "skipped"
    assert result["selection"]["selectedPhotoId"] is None
    assert result["selection"]["motionPrompt"] is None
    assert [item["photoId"] for item in result["selection"]["ranking"]] == [first["id"], second["id"]]


@pytest.mark.parametrize("bad", [
    lambda pid: {"photoId": pid, "suitable": True, "score": 20, "reason": "okay", "motionPrompt": None},
    lambda pid: verdict("unknown", suitable=True, score=20, motion="tiny motion"),
    lambda pid: verdict(pid, suitable=True, score=True, motion="tiny motion"),
    lambda pid: {**verdict(pid, suitable=False, score=20), "extra": 1},
])
def test_invalid_model_output_is_failed_and_does_not_select_first(tmp_path, bad):
    _, sources, job, first, _, _ = ready(tmp_path)
    result = DynamicPhotoSelector(sources).run(job["id"], lambda _content, pid: bad(pid))
    assert result["status"] == "failed"
    assert result["selection"] is None
    assert result["error"]["code"].startswith("MODEL_")
    assert result["sourceSnapshot"]["inputs"][0]["photoId"] == first["id"]


def test_timeout_and_changed_selection_fail_instead_of_skip(tmp_path):
    media, sources, job, first, second, _ = ready(tmp_path)
    result = DynamicPhotoSelector(sources).run(job["id"], lambda *_: (_ for _ in ()).throw(
        SelectionError("VISION_TIMEOUT", "视觉模型分析超时")))
    assert result["status"] == "failed" and result["error"]["code"] == "VISION_TIMEOUT"

    media.set_selected(job["tripId"], {"batchId": "batch-2", "source": "test", "photoIds": [second["id"]]})
    # A separately prepared job cannot analyze a changed selection.
    job["status"] = "prepared"
    DynamicPhotoSelector(sources)._save(job)
    changed = DynamicPhotoSelector(sources).run(job["id"], lambda *_: pytest.fail("must not reach model"))
    assert changed["status"] == "failed" and changed["error"]["code"] == "SELECTION_CHANGED"


def test_partial_restart_reuses_checked_assessment_and_parallel_callers_share_one_inference(tmp_path):
    _, sources, job, first, second, _ = ready(tmp_path)
    calls = []
    def analyze(_content, pid):
        calls.append(pid)
        return verdict(pid, suitable=True, score=50, motion="Subtle natural motion, steady camera.")
    selector = DynamicPhotoSelector(sources)
    first_assessment = {**analyze(sources.read_input(job, first["id"]), first["id"]),
                        "inputSha256": job["sourceSnapshot"]["inputs"][0]["sha256"]}
    job["status"] = "analyzing"
    job["visionModel"] = __import__("pyserver.media.vision", fromlist=["vision_model"]).vision_model()
    job["selectionPromptVersion"] = "dynamic-photo-selection@1"
    job["selectionAssessments"] = {first["id"]: first_assessment}
    selector._save(job)
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: selector.run(job["id"], analyze), range(2)))
    assert all(result["status"] == "selected" for result in results)
    assert calls == [first["id"], second["id"]]
    assert results[0]["selection"]["selectedPhotoId"] == first["id"]  # stable input-order tie break


def test_real_transport_shape_and_timeout_are_strict_without_raw_response_persistence():
    pid = "photo-1"
    seen = []
    def respond(request):
        payload = json.loads(request.content)
        seen.append(payload)
        return httpx.Response(200, headers={"x-request-id": "remote-request-1"}, json={
            "id": "chat-completion-1", "model": "qwen38-27b",
            "choices": [{"message": {"content": json.dumps(
            verdict(pid, suitable=True, score=80, reason="水波适合微动",
                    motion="Small water ripples; steady camera."))}}]})
    with httpx.Client(transport=httpx.MockTransport(respond)) as client:
        result = analyze_image(jpeg("blue"), pid, client=client)
    assert result["photoId"] == pid and result["suitable"] is True
    assert result["_providerReceipt"] == {"modelObserved": "qwen38-27b",
                                          "responseId": "chat-completion-1",
                                          "requestId": "remote-request-1"}
    assert seen[0]["messages"][1]["content"][1]["image_url"]["url"].startswith("data:image/jpeg;base64,")
    with httpx.Client(transport=httpx.MockTransport(lambda request: httpx.Response(
            200, json={"choices": [{"message": {"content": "not json"}}]}))) as client:
        with pytest.raises(SelectionError) as invalid:
            analyze_image(jpeg("blue"), pid, client=client)
    assert invalid.value.code == "MODEL_SCHEMA_INVALID"
    with pytest.raises(SelectionError):
        validate_assessment([verdict(pid, suitable=False, score=0)] * 2, pid)


def test_provider_receipt_is_separate_from_local_receipt_and_configured_model(tmp_path):
    _, sources, job, first, second, _ = ready(tmp_path)
    def analyze(_content, pid):
        return {**verdict(pid, suitable=pid == first["id"], score=80,
                          motion="Small ripples, steady frame." if pid == first["id"] else None),
                "_providerReceipt": {"modelObserved": "actual-model", "responseId": "remote-1",
                                     "requestId": "request-1"}}
    result = DynamicPhotoSelector(sources).run(job["id"], analyze)
    assert result["status"] == "selected"
    assert result["selection"]["observedModels"] == ["actual-model"]
    assert result["selection"]["configuredModel"] != "actual-model"
    receipt = result["selection"]["ranking"][0]["requestReceipt"]
    assert receipt["kind"] == "provider_response" and receipt["provider"]["requestId"] == "request-1"
    assert receipt["id"] != receipt["provider"]["responseId"]


def test_controller_unavailable_is_diagnostic_failed(tmp_path):
    _, sources, job, _, _, _ = ready(tmp_path)
    class Down:
        def use(self, name):
            assert name == "chat"
            raise RuntimeError("offline")
    result = asyncio.run(DynamicPhotoSelector(sources, Down()).run_managed(job["id"]))
    assert result["status"] == "failed" and result["error"]["code"] == "VISION_UNAVAILABLE"
