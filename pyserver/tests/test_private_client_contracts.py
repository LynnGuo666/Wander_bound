import asyncio
import io

import httpx
from PIL import Image

from pyserver.accounts import AccountStore
from pyserver.app import create_app
from pyserver.media import MediaStore
from pyserver.settings import ConfigStore
from pyserver.trips import TripStore


def test_invite_accounts_isolate_trips_media_notes_and_admin(tmp_path, monkeypatch):
    monkeypatch.setenv("BOOTSTRAP_INVITE_CODE", "bootstrap-secret")
    auth = AccountStore(tmp_path / "accounts.sqlite3")
    trips = TripStore(tmp_path / "trips")
    media = MediaStore(tmp_path / "media")
    app = create_app(config=ConfigStore(tmp_path / "config.yml"), trips=trips, media=media, auth=auth)
    jpeg = io.BytesIO()
    Image.new("RGB", (60, 50), "green").save(jpeg, format="JPEG")

    async def scenario():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
            admin = (await client.post("/api/auth/register", json={"username": "admin", "password": "very-long-password", "invite": "bootstrap-secret"})).json()
            ah = {"Authorization": f"Bearer {admin['token']}"}
            assert admin["user"]["role"] == "admin"
            assert (await client.get("/api/settings", headers=ah)).status_code == 200
            invite = (await client.post("/api/auth/invites", headers=ah)).json()["invite"]
            member_response = await client.post("/api/auth/register", json={"username": "member", "password": "another-long-password", "invite": invite})
            assert member_response.status_code == 200
            member = member_response.json()
            mh = {"Authorization": f"Bearer {member['token']}"}
            assert (await client.post("/api/auth/register", json={"username": "third", "password": "third-long-password", "invite": invite})).status_code == 400
            assert (await client.get("/api/settings", headers=mh)).status_code == 403
            assert (await client.get("/api/trips")).status_code == 401
            trip = (await client.post("/api/plan", headers=ah, json={"query": "杭州两日游"})).json()["tripId"]
            assert (await client.get(f"/api/trips/{trip}", headers=mh)).status_code == 404
            assert (await client.get("/api/trips", headers=mh)).json()["trips"] == []
            path = f"/api/trips/{trip}/note"
            assert (await client.get(path, headers=mh)).status_code == 404
            assert (await client.get(path, headers=ah)).json()["version"] == 0
            saved = (await client.put(path, headers=ah, json={"text": "旅途日记", "version": 0})).json()
            assert saved["version"] == 1
            assert (await client.put(path, headers=ah, json={"text": "旧稿", "version": 0})).status_code == 409
            upload_headers = {**ah, "Content-Type": "image/jpeg", "X-Trip-Id": trip, "X-Client-Asset-Key": "asset-1"}
            first = await client.post("/api/media/photos", content=jpeg.getvalue(), headers=upload_headers)
            assert first.status_code == 201, first.text
            second = await client.post("/api/media/photos", content=jpeg.getvalue(), headers=upload_headers)
            assert first.json()["id"] == second.json()["id"]
            pid = first.json()["id"]
            assert "exif" not in first.json() and "gps" not in first.json()
            assert (await client.get(f"/api/media/photos/{pid}", headers=mh)).status_code == 404
            response = await client.post("/api/media/analysis-jobs", headers=ah, json={"tripId": trip, "photoIds": [pid], "batchId": "batch-1"})
            assert response.status_code == 202, response.text
            assert response.json()["total"] == 1
            assert (await client.get(f"/api/media/analysis-jobs/{response.json()['id']}", headers=mh)).status_code == 404
            assert (await client.get(f"/api/media/analysis-jobs/{response.json()['id']}")).status_code == 401
            await client.post("/api/auth/logout", headers=mh)
            assert (await client.get("/api/auth/me", headers=mh)).status_code == 401

    asyncio.run(scenario())
