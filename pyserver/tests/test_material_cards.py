import pytest

from pyserver.media.material_cards import MaterialCards
from pyserver.media.contracts import ContractError, selected_original_snapshot
from test_generation_contract import fixture, jpeg


def test_card_qualification_provenance_version_and_frozen_original(tmp_path, monkeypatch):
    _, media, _, _, trip, photo, other, foreign = fixture(tmp_path, monkeypatch)
    media.set_selected(trip["id"], {"batchId": "card-test", "source": "test", "photoIds": [photo["id"]]})
    cards = MaterialCards(media)
    selection = selected_original_snapshot(media, trip["id"], [photo["id"]])
    initial = cards.snapshot(selection)[0]
    assert initial["fields"]["sceneDescription"]["value"] is None
    payload = {"expectedVersion": 0, "fields": {"sceneDescription": {
        "value": "秋日山坡与金色树木", "source": {"kind": "user", "reference": "用户核对原图"}}}}
    saved = cards.put(trip["id"], photo["id"], payload)
    assert saved["version"] == 1 and saved["fields"]["place"]["value"] is None
    frozen = cards.snapshot(selection)
    with pytest.raises(ContractError, match="已变化"):
        cards.put(trip["id"], photo["id"], payload)
    for invalid in (other, foreign):
        with pytest.raises(ContractError):
            cards.put(trip["id"], invalid["id"], payload)
    payload["expectedVersion"] = 1
    payload["fields"]["sceneDescription"]["value"] = "修改后的文字"
    cards.put(trip["id"], photo["id"], payload)
    assert frozen[0]["fields"]["sceneDescription"]["value"] == "秋日山坡与金色树木"
    media.photos_dir.joinpath(photo["id"] + ".jpg").write_bytes(jpeg("purple"))
    new_selection = selected_original_snapshot(media, trip["id"], [photo["id"]])
    with pytest.raises(ContractError, match="原图已变化"):
        cards.snapshot(new_selection)


def test_card_rejects_unsourced_text_and_image_fields(tmp_path, monkeypatch):
    _, media, _, _, trip, photo, _, _ = fixture(tmp_path, monkeypatch)
    media.set_selected(trip["id"], {"batchId": "cards", "source": "test", "photoIds": [photo["id"]]})
    cards = MaterialCards(media)
    for fields in ({"image_url": "https://example.com/a.jpg"},
                   {"sceneDescription": "plain unsourced text"},
                   {"sceneDescription": {"value": "scene", "source": {"kind": "user", "reference": ""}}}):
        with pytest.raises(ContractError):
            cards.put(trip["id"], photo["id"], {"expectedVersion": 0, "fields": fields})
