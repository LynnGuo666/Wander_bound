"""User-owned pages survive repeated Agent compositions and process restarts."""
import pytest

from pyserver.media.journal_routes import catalog
from pyserver.media.journal_store import JournalConflict, JournalStore


def test_user_pages_are_immutable_to_ai_and_survive_restart(tmp_path):
    trip = {"id": "01e53666-0558-46fb-b931-e2b628bec20a", "title": "上海重游",
            "plan": {"destination": "上海"}}
    root = tmp_path / "journals"
    store = JournalStore(root, catalog())
    initial = store.get(trip)
    assert initial["version"] == 0 and len(initial["pages"]) == 2
    edited = {**initial["pages"][0], "items": [
        {**item, "text": "我自己写的日记"} if item["kind"] == "text" else item
        for item in initial["pages"][0]["items"]]}
    saved = store.edit_page(trip, 0, edited, 0)
    assert saved["pages"][0]["protected"] and saved["pages"][0]["source"] == "user"
    with pytest.raises(JournalConflict):
        store.edit_page(trip, 1, initial["pages"][1], 0)

    ai_pages = [store._seed_page("photo-wall", trip, 0), store._seed_page("postcard-collage", trip, 1)]
    composed = store.apply_ai(trip, ai_pages)
    assert composed["updatedPageIndices"] == [1]
    assert composed["preservedPageIndices"] == [0]
    assert composed["pages"][0] == saved["pages"][0]
    assert composed["pages"][1]["source"] == "ai"

    appended = store.append_spread(trip, composed["version"])
    assert all(page["protected"] for page in appended["pages"][2:])
    protected_first = store.edit_page(trip, 1, appended["pages"][1], appended["version"])
    again = store.apply_ai(trip, ai_pages)
    assert again["updatedPageIndices"] == [4, 5]
    assert again["pages"][0] == protected_first["pages"][0]
    assert again["pages"][1] == protected_first["pages"][1]
    assert again["pages"][2:4] == protected_first["pages"][2:4]
    assert JournalStore(root, catalog()).get(trip) == {key: again[key] for key in
        ("tripId", "version", "pages", "updatedAt")}


def test_invalid_page_payload_is_rejected(tmp_path):
    trip = {"id": "50ca131f-af67-4b36-a349-9401b9576a35", "title": "广州"}
    store = JournalStore(tmp_path, catalog())
    page = store.get(trip)["pages"][0]
    with pytest.raises(ValueError, match="素材类型"):
        store.edit_page(trip, 0, {**page, "items": [{**page["items"][0], "kind": "html"}]}, 0)
    assert store.get(trip)["version"] == 0
