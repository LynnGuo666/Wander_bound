"""MockTransport checks of frozen ComfyUI requests; no model is started."""
import asyncio
import copy
import io
import json
from pathlib import Path

import httpx
import pytest
from PIL import Image

from pyserver.media.comfy import ComfyClient
from pyserver.media import workflow_versions

WORKFLOWS = Path(__file__).resolve().parents[2] / "workflows"


def jpeg(size=(900, 1200)):
    output = io.BytesIO()
    Image.new("RGB", size, "navy").save(output, "JPEG")
    return output.getvalue()


def mock_client(monkeypatch):
    seen = {"uploads": [], "graphs": [], "submissions": []}

    def handler(request):
        if request.url.path == "/upload/image":
            # Multipart body need not be decoded to verify the uploaded canvas.
            seen["uploads"].append(request.content)
            return httpx.Response(200, json={"name": "uploaded.jpg"})
        if request.url.path == "/prompt":
            body = json.loads(request.content)
            seen["graphs"].append(body["prompt"])
            seen["submissions"].append(body)
            return httpx.Response(200, json={"prompt_id": body.get("prompt_id", "prompt-1")})
        raise AssertionError(request.url)

    original = httpx.AsyncClient
    monkeypatch.setattr(httpx, "AsyncClient", lambda **kwargs: original(transport=httpx.MockTransport(handler), **kwargs))
    return seen


def uploaded_size(body):
    start = body.index(b"\xff\xd8")
    with Image.open(io.BytesIO(body[start:])) as image:
        return image.size


def test_persisted_prompt_identity_is_sent_and_validated_before_upload(monkeypatch):
    async def run():
        seen = mock_client(monkeypatch)
        client = ComfyClient("http://127.0.0.1:8191", WORKFLOWS / "qwen-image-2.1-edit-api.json", "image")
        identity = "4d78ae36-6c44-4d57-8bcf-a42f85b65cb4"
        assert await client.queue(jpeg(), "scene", 42, prompt_id=identity) == identity
        assert seen["submissions"][0]["prompt_id"] == identity
        for invalid in ("bad-id", identity.upper(), 42):
            with pytest.raises(ValueError, match="UUID"):
                await client.queue(jpeg(), "scene", 42, prompt_id=invalid)
        assert len(seen["uploads"]) == 1
    asyncio.run(run())


def test_mismatched_engine_identity_is_not_accepted(monkeypatch):
    async def run():
        def handler(request):
            if request.url.path == "/upload/image":
                return httpx.Response(200, json={"name": "uploaded.jpg"})
            return httpx.Response(200, json={"prompt_id": "unexpected"})
        original = httpx.AsyncClient
        monkeypatch.setattr(httpx, "AsyncClient", lambda **kwargs: original(transport=httpx.MockTransport(handler), **kwargs))
        client = ComfyClient("http://127.0.0.1:8191", WORKFLOWS / "qwen-image-2.1-edit-api.json", "image")
        with pytest.raises(RuntimeError, match="编号不匹配"):
            await client.queue(jpeg(), "scene", 42, prompt_id="4d78ae36-6c44-4d57-8bcf-a42f85b65cb4")
    asyncio.run(run())


def test_video_seed_canvas_frames_and_legacy_signature(monkeypatch):
    asyncio.run(_video_seed_canvas_frames_and_legacy_signature(monkeypatch))


async def _video_seed_canvas_frames_and_legacy_signature(monkeypatch):
    seen = mock_client(monkeypatch)
    client = ComfyClient("http://127.0.0.1:8188", WORKFLOWS / "minimax-h3-i2v-api.json", "video")
    assert await client.queue(jpeg(), "scene", 1234) == "prompt-1"
    graph = seen["graphs"][0]
    assert graph["6"]["inputs"]["width"] == 1024
    assert graph["6"]["inputs"]["height"] == 576
    assert graph["6"]["inputs"]["length"] == 124
    assert graph["7"]["inputs"]["noise_seed"] == 1234
    assert graph["14"]["inputs"]["fps"] == 24
    assert uploaded_size(seen["uploads"][0]) == (1024, 576)
    assert await client.queue(jpeg(), "scene", 9, parameters={"frames": 141}) == "prompt-1"
    assert seen["graphs"][1]["6"]["inputs"]["length"] == 141


def test_frozen_graph_stays_stable_after_file_change(tmp_path, monkeypatch):
    asyncio.run(_frozen_graph_stays_stable_after_file_change(tmp_path, monkeypatch))


async def _frozen_graph_stays_stable_after_file_change(tmp_path, monkeypatch):
    seen = mock_client(monkeypatch)
    path = tmp_path / "image.json"
    path.write_bytes((WORKFLOWS / "qwen-image-2.1-edit-api.json").read_bytes())
    client = ComfyClient("http://127.0.0.1:8191", path, "image")
    frozen = client.freeze_workflow()
    frozen_copy = copy.deepcopy(frozen)
    path.unlink()
    await client.queue(jpeg(), "postcard", 42, workflow_snapshot=frozen, parameters={"aspect_ratio": "3:2"})
    graph = seen["graphs"][0]
    assert graph["6"]["inputs"]["seed"] == 42
    assert graph["5"]["inputs"]["prompt"] == "<image1> postcard"
    assert frozen == frozen_copy
    assert frozen["workflow_id"] == "travel.qwen-image-2.1.edit"
    assert frozen["schema_version"] == 1
    assert graph["2"]["inputs"]["unet_name"] == frozen["api_graph"]["2"]["inputs"]["unet_name"]
    assert uploaded_size(seen["uploads"][0]) == (1536, 1024)


def test_legacy_image_keeps_source_canvas_and_ui_links(monkeypatch):
    asyncio.run(_legacy_image_keeps_source_canvas(monkeypatch))
    for stem in ("qwen-image-2.1-edit", "minimax-h3-i2v"):
        ui = json.loads((WORKFLOWS / f"{stem}-ui.json").read_text())
        nodes = {node["id"]: node for node in ui["nodes"]}
        assert len(nodes) == ui["last_node_id"]
        assert len(ui["links"]) == ui["last_link_id"]
        for link_id, origin, origin_slot, target, target_slot, kind in ui["links"]:
            assert link_id in nodes[origin]["outputs"][origin_slot]["links"]
            assert nodes[target]["inputs"][target_slot]["link"] == link_id
            assert nodes[target]["inputs"][target_slot]["type"] == kind


async def _legacy_image_keeps_source_canvas(monkeypatch):
    seen = mock_client(monkeypatch)
    client = ComfyClient("http://127.0.0.1:8191", WORKFLOWS / "qwen-image-2.1-edit-api.json", "image")
    await client.queue(jpeg(), "legacy", 1)
    assert uploaded_size(seen["uploads"][0]) == (900, 1200)


def test_invalid_parameters_and_snapshot_rejected_before_upload(monkeypatch):
    asyncio.run(_invalid_parameters_and_snapshot_rejected_before_upload(monkeypatch))


async def _invalid_parameters_and_snapshot_rejected_before_upload(monkeypatch):
    seen = mock_client(monkeypatch)
    client = ComfyClient("http://127.0.0.1:8188", WORKFLOWS / "minimax-h3-i2v-api.json", "video")
    snapshot = client.freeze_workflow()
    for settings in ({"width": 864}, {"frames": 125}, {"fps": 30}, {"aspect_ratio": "3:2"}, {"aspect_ratio": []}):
        with pytest.raises(ValueError):
            await client.queue(jpeg(), "scene", 1, workflow_snapshot=snapshot, parameters=settings)
    with pytest.raises(ValueError):
        await client.queue(jpeg(), "scene", True, workflow_snapshot=snapshot)
    altered = copy.deepcopy(snapshot)
    altered["api_graph"]["7"]["inputs"]["noise_seed"] = 0
    with pytest.raises(ValueError, match="哈希"):
        await client.queue(jpeg(), "scene", 1, workflow_snapshot=altered)
    assert not seen["uploads"]


def test_old_snapshot_keeps_its_parameter_defaults_after_manifest_change(tmp_path, monkeypatch):
    asyncio.run(_old_snapshot_keeps_defaults(tmp_path, monkeypatch))


async def _old_snapshot_keeps_defaults(tmp_path, monkeypatch):
    seen = mock_client(monkeypatch)
    client = ComfyClient("http://127.0.0.1:8188", WORKFLOWS / "minimax-h3-i2v-api.json", "video")
    old = client.freeze_workflow()
    manifest = json.loads((WORKFLOWS / "model-manifest.json").read_text())
    manifest["video"]["parameter_schema"]["frames"].update(default=141, minimum=141, maximum=141)
    new_manifest = tmp_path / "manifest.json"
    new_manifest.write_text(json.dumps(manifest))
    monkeypatch.setattr(workflow_versions, "MANIFEST", new_manifest)
    await client.queue(jpeg(), "old", 7, workflow_snapshot=old)
    assert seen["graphs"][-1]["6"]["inputs"]["length"] == 124
    with pytest.raises(ValueError):
        await client.queue(jpeg(), "new", 7, workflow_snapshot=client.freeze_workflow(), parameters={"frames": 124})
    await client.queue(jpeg(), "new", 7, workflow_snapshot=client.freeze_workflow())
    assert seen["graphs"][-1]["6"]["inputs"]["length"] == 141
