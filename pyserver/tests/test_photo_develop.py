import asyncio
import io
import json
import sys

import httpx
import pytest
from PIL import Image

from pyserver.app import create_app
from pyserver.media import MediaStore
from pyserver.media import images
from pyserver.media.mcp_images import MCPImagesClient
from pyserver.media import photo_routes
from pyserver.media import develop as develop_provider
from pyserver.settings import ConfigStore
from pyserver.trips import TripStore


def jpeg(color="red"):
    output = io.BytesIO()
    Image.new("RGB", (64, 48), color).save(output, format="JPEG")
    return output.getvalue()


def test_selection_handoff_and_develop_gate(tmp_path, monkeypatch):
    monkeypatch.setenv("MEDIA_API_TOKEN", "develop-token")
    trips = TripStore(tmp_path / "trips")
    first = trips.create({"query": "深圳旅行"})
    second = trips.create({"query": "上海旅行"})
    media = MediaStore(tmp_path / "media")
    selected = media.add(jpeg(), first["id"], None)
    other = media.add(jpeg("blue"), first["id"], None)
    foreign = media.add(jpeg("green"), second["id"], None)
    app = create_app(config=ConfigStore(tmp_path / "config.yml"), trips=trips, media=media)

    async def scenario():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
            path = f"/api/media/trips/{first['id']}/selected-photos"
            develop = f"/api/media/photos/{selected['id']}/develop"
            headers = {"Authorization": "Bearer develop-token"}
            assert (await client.get(path)).status_code == 401
            empty = (await client.get(path, headers=headers)).json()
            assert empty["photos"] == [] and empty["batchId"] is None
            for endpoint in ("suggest", "preview", "review", "save"):
                response = await client.post(f"{develop}/{endpoint}", headers=headers, json={"params": {}})
                assert response.status_code == 409
            payload = {"batchId": "batch-1", "source": "selection-agent", "photoIds": [selected["id"]]}
            assert (await client.put(path, json=payload)).status_code == 401
            for invalid in ([selected["id"], selected["id"]], [foreign["id"]], ["missing"]):
                response = await client.put(path, headers=headers, json={**payload, "photoIds": invalid})
                assert response.status_code == 400
                assert (await client.get(path, headers=headers)).json()["photoIds"] == []
            created = (await client.put(path, headers=headers, json=payload)).json()
            assert created["photoIds"] == [selected["id"]]
            assert created["photos"][0]["id"] == selected["id"]
            repeated = (await client.put(path, headers=headers, json=payload)).json()
            assert repeated["updatedAt"] == created["updatedAt"]
            assert (await client.post(f"/api/media/photos/{other['id']}/develop/save",
                                      headers=headers, json={"params": {}})).status_code == 409
            cleared = (await client.put(path, headers=headers, json={**payload, "batchId": "batch-2", "photoIds": []})).json()
            assert cleared["photos"] == []
            assert (await client.post(f"{develop}/preview", headers=headers, json={"params": {}})).status_code == 409

    asyncio.run(scenario())


def test_develop_validates_bounds_and_renders_without_mutating_source():
    original = jpeg()
    rendered = images.develop(original, {"exposure": 0.4, "crop": {"left": 0.1, "top": 0, "width": 0.8, "height": 1}})
    with Image.open(io.BytesIO(rendered)) as result:
        assert result.size == (52, 48)
    with pytest.raises(ValueError, match="exposure"):
        images.develop(original, {"exposure": 4})
    with pytest.raises(ValueError, match="裁切"):
        images.develop(original, {"crop": {"left": 0.8, "top": 0, "width": 0.5, "height": 1}})


def test_develop_api_auth_preview_and_saved_version(tmp_path, monkeypatch):
    monkeypatch.setenv("MEDIA_API_TOKEN", "develop-token")
    trips = TripStore(tmp_path / "trips")
    trip = trips.create({"query": "深圳旅行"})
    media = MediaStore(tmp_path / "media")
    photo = media.add(jpeg(), trip["id"], None)
    media.set_selected(trip["id"], {"batchId": "test-batch", "source": "test", "photoIds": [photo["id"]]})
    original = media.bytes(photo["id"], "original")
    async def fake_mcp(self, source, destination, settings, size):
        rendered = images.develop(source.read_bytes(), settings)
        destination.write_bytes(rendered)
        return rendered
    monkeypatch.setattr(MCPImagesClient, "develop", fake_mcp)
    app = create_app(config=ConfigStore(tmp_path / "config.yml"), trips=trips, media=media)

    async def scenario():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
            path = f"/api/media/photos/{photo['id']}/develop/preview"
            assert (await client.post(path, json={"params": {}})).status_code == 401
            headers = {"Authorization": "Bearer develop-token"}
            preview = await client.post(path, headers=headers, json={"params": {"exposure": 0.3}})
            assert preview.status_code == 200
            assert preview.headers["content-type"] == "image/jpeg"
            invalid = await client.post(path, headers=headers, json={"params": {"gamma": 9}})
            assert invalid.status_code == 400
            saved = await client.post(f"/api/media/photos/{photo['id']}/develop/save", headers=headers,
                                      json={"params": {"contrast": 1.1}, "note": "natural light"})
            assert saved.status_code == 200
            body = saved.json()
            assert body["variant"].startswith("develop-")
            assert body["photo"]["variants"] == [body["variant"]]
            assert media.bytes(photo["id"], "original") == original
            assert media.bytes(photo["id"], body["variant"])

    asyncio.run(scenario())


def test_dgx_suggestion_reports_unavailable_without_fallback(tmp_path, monkeypatch):
    monkeypatch.setenv("MEDIA_API_TOKEN", "develop-token")
    monkeypatch.setenv("DGX_VISION_BASE_URL", "http://127.0.0.1:1/v1")
    trips = TripStore(tmp_path / "trips")
    trip = trips.create({"query": "深圳旅行"})
    media = MediaStore(tmp_path / "media")
    photo = media.add(jpeg(), trip["id"], None)
    media.set_selected(trip["id"], {"batchId": "test-batch", "source": "test", "photoIds": [photo["id"]]})
    app = create_app(config=ConfigStore(tmp_path / "config.yml"), trips=trips, media=media)

    async def scenario():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post(f"/api/media/photos/{photo['id']}/develop/suggest",
                                         headers={"Authorization": "Bearer develop-token"})
            assert response.status_code == 503
            assert "DGX 照片分析失败" in response.json()["detail"]

    asyncio.run(scenario())


def test_preview_reports_missing_mcp_server_instead_of_substituting_a_filter(tmp_path, monkeypatch):
    monkeypatch.setenv("MEDIA_API_TOKEN", "develop-token")
    monkeypatch.delenv("MCP_IMAGES_COMMAND", raising=False)
    trips = TripStore(tmp_path / "trips")
    trip = trips.create({"query": "深圳旅行"})
    media = MediaStore(tmp_path / "media")
    photo = media.add(jpeg(), trip["id"], None)
    media.set_selected(trip["id"], {"batchId": "test-batch", "source": "test", "photoIds": [photo["id"]]})
    app = create_app(config=ConfigStore(tmp_path / "config.yml"), trips=trips, media=media)

    async def scenario():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post(f"/api/media/photos/{photo['id']}/develop/preview",
                headers={"Authorization": "Bearer develop-token"}, json={"params": {}})
            assert response.status_code == 503
            assert "mcp_images 尚未配置" in response.json()["detail"]

    asyncio.run(scenario())


def test_mcp_tool_paths_are_bound_to_server_owned_files(tmp_path):
    client = MCPImagesClient("unused")
    source = tmp_path / "controlled-source.jpg"
    destination = tmp_path / "controlled-output.jpg"
    tool = {"name": "raster_adjust", "inputSchema": {"required": ["path", "output", "contrast"],
             "properties": {"path": {}, "output": {}, "contrast": {}}}}
    args = client._args_for_tool(tool, source=source, destination=destination, operation="adjust",
        settings={**images.DEFAULT_DEVELOP, "_size": (64, 48), "contrast": 1.2})
    assert args == {"path": str(source), "output": str(destination), "contrast": 1.2}


def test_mcp_stdio_executes_only_crop_and_adjust_with_private_copies(tmp_path):
    source = tmp_path / "source.jpg"
    output = tmp_path / "output.jpg"
    source.write_bytes(jpeg())
    original = source.read_bytes()
    server = tmp_path / "fake_mcp.py"
    server.write_text('''import json, shutil, sys\nfrom PIL import Image\nfor line in sys.stdin:\n m=json.loads(line); method=m["method"]; result={}\n if method == "initialize": result={"protocolVersion":"2024-11-05","capabilities":{},"serverInfo":{"name":"fake","version":"1"}}\n elif method == "tools/list": result={"tools":[{"name":"raster_crop","inputSchema":{"required":["path","left","top","right","bottom"],"properties":{k:{} for k in ["path","output","left","top","right","bottom"]}}},{"name":"raster_adjust","inputSchema":{"required":["path"],"properties":{k:{} for k in ["path","output","contrast"]}}}]}\n elif method == "tools/call":\n  a=m["params"]["arguments"]\n  if m["params"]["name"] == "raster_crop":\n   im=Image.open(a["path"]); box=tuple(a[k] for k in ["left","top","right","bottom"]); im.crop(box).save(a["output"])\n  else: shutil.copyfile(a["path"],a["output"])\n  result={"content":[{"type":"text","text":json.dumps({"success":True})}]}\n if "id" in m: print(json.dumps({"jsonrpc":"2.0","id":m["id"],"result":result}),flush=True)\n''', encoding="utf-8")
    client = MCPImagesClient(f"{sys.executable} {server}", timeout=4)
    settings = images.normalize_develop({"crop": {"left": 0.1, "top": 0, "width": 0.8, "height": 1}, "contrast": 1.2})
    rendered = asyncio.run(client.develop(source, output, settings, (64, 48)))
    with Image.open(io.BytesIO(rendered)) as result:
        assert result.size == (52, 48)
    assert source.read_bytes() == original


def test_dgx_suggest_and_review_are_injectable_without_spark(tmp_path, monkeypatch):
    monkeypatch.setenv("MEDIA_API_TOKEN", "develop-token")
    trips = TripStore(tmp_path / "trips")
    trip = trips.create({"query": "深圳旅行"})
    media = MediaStore(tmp_path / "media")
    photo = media.add(jpeg(), trip["id"], None)
    media.set_selected(trip["id"], {"batchId": "test-batch", "source": "test", "photoIds": [photo["id"]]})
    async def fake_suggest(source):
        assert source == media.bytes(photo["id"])
        return {"params": images.normalize_develop({"exposure": 0.2}), "rationale": "保留天空层次", "cropReason": "", "model": "test-vl"}
    async def fake_render(store, photo_id, settings):
        return images.develop(store.bytes(photo_id), settings)
    async def fake_review(original, edited, settings):
        assert original != edited and settings["exposure"] == 0.2
        return {"approved": True, "note": "高光与肤色自然", "model": "test-vl"}
    monkeypatch.setattr(photo_routes, "suggest_development", fake_suggest)
    monkeypatch.setattr(photo_routes, "_render_development", fake_render)
    monkeypatch.setattr(photo_routes, "review_development", fake_review)
    app = create_app(config=ConfigStore(tmp_path / "config.yml"), trips=trips, media=media)

    async def scenario():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
            headers = {"Authorization": "Bearer develop-token"}
            path = f"/api/media/photos/{photo['id']}/develop"
            suggested = (await client.post(f"{path}/suggest", headers=headers)).json()
            assert suggested["params"]["exposure"] == 0.2
            response = await client.post(f"{path}/review", headers=headers, json={"params": suggested["params"]})
            assert response.status_code == 200
            assert response.json()["approved"] is True

    asyncio.run(scenario())


def test_dgx_provider_contract_sends_only_private_jpeg_data_and_parses_responses(monkeypatch):
    monkeypatch.setenv("DGX_VISION_BASE_URL", "http://127.0.0.1:18192/v1")
    monkeypatch.setenv("DGX_VISION_MODEL", "qwen38-27b")
    requests = []
    def respond(request):
        assert str(request.url) == "http://127.0.0.1:18192/v1/chat/completions"
        payload = json.loads(request.content)
        requests.append(payload)
        content = payload["messages"][1]["content"]
        assert all(part["image_url"]["url"].startswith("data:image/jpeg;base64,")
                   for part in content if part["type"] == "image_url")
        answer = ({"params": {"exposure": 0.2}, "rationale": "保留高光", "cropReason": "保留原构图"}
                  if len(requests) == 1 else {"approved": True, "note": "颜色自然"})
        return httpx.Response(200, json={"choices": [{"message": {"content": json.dumps(answer)}}]})
    real_client = httpx.AsyncClient
    monkeypatch.setattr(develop_provider.httpx, "AsyncClient",
                        lambda **kwargs: real_client(transport=httpx.MockTransport(respond), **kwargs))

    async def scenario():
        suggested = await develop_provider.suggest(jpeg())
        assert suggested["params"]["exposure"] == 0.2
        assert suggested["model"] == "qwen38-27b"
        assert isinstance(suggested["elapsedMs"], int)
        reviewed = await develop_provider.review(jpeg(), images.develop(jpeg(), suggested["params"]), suggested["params"])
        assert reviewed["approved"] is True
        assert reviewed["note"] == "颜色自然"
        assert isinstance(reviewed["elapsedMs"], int)
        assert len([part for part in requests[0]["messages"][1]["content"] if part["type"] == "image_url"]) == 1
        assert len([part for part in requests[1]["messages"][1]["content"] if part["type"] == "image_url"]) == 2

    asyncio.run(scenario())
