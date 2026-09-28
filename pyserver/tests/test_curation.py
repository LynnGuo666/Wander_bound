"""选优对外契约的自测：commit_selection、build_reel_assets 与 set_tags。

commit_selection 只测"选优产出 → 下游契约"的翻译，用 FakeMedia 隔离掉 store 的真实
落库；set_tags 是本分支自己的方法，用真实 MediaStore 落在 pytest 临时目录验证。
"""
import io

from pyserver.media.curate import build_reel_assets, commit_selection
from pyserver.media.store import MediaStore


class FakeMedia:
    """只实现选优编排用到的方法；set_selected/selected 模拟共享 store 的契约。"""

    def __init__(self, photos):
        self._photos = {photo["id"]: photo for photo in photos}
        self._selection = {}
        self.set_selected_calls = []

    def get(self, photo_id):
        return self._photos.get(photo_id)

    def list(self, trip_id):
        return [p for p in self._photos.values() if p.get("tripId") == trip_id]

    def set_selected(self, trip_id, payload):
        self.set_selected_calls.append((trip_id, payload))
        self._selection = {"tripId": trip_id, **payload}
        return {"tripId": trip_id, **payload, "photoIds": payload["photoIds"], "updatedAt": "now"}

    def selected(self, trip_id):
        return self._selection or {"tripId": trip_id, "batchId": None, "source": None,
                                   "photoIds": [], "updatedAt": None}


def _photo(pid, day="2026-09-01", trip="t1", tags=None, quality=None):
    return {"id": pid, "tripId": trip, "capturedDay": day,
            "exif": {"cameraMake": "Apple"}, "quality": quality or {"keep": 3},
            "tags": tags or {}}


def test_commit_selection_translates_to_contract():
    media = FakeMedia([_photo("a"), _photo("b")])
    out = commit_selection(media, "t1", ["a", "b"], batch_id="sel-1", source="photo-selection")
    trip, payload = media.set_selected_calls[0]
    assert trip == "t1"
    assert payload == {"batchId": "sel-1", "source": "photo-selection", "photoIds": ["a", "b"]}
    assert out["photoIds"] == ["a", "b"]


def test_commit_selection_default_source():
    media = FakeMedia([_photo("a")])
    commit_selection(media, "t1", ["a"], batch_id="sel-1")
    _, payload = media.set_selected_calls[0]
    assert payload["source"] == "photo-selection"


def test_build_reel_assets_aggregates_and_sorts_by_day():
    media = FakeMedia([
        _photo("late", day="2026-09-02", tags={"scene": "山顶", "quality": {"highlight": True}}),
        _photo("early", day="2026-09-01", tags={"mood": "宁静"}),
        _photo("mid", day="2026-09-01", quality={"keep": 2}),
    ])
    media.set_selected("t1", {"batchId": "sel-1", "source": "photo-selection",
                              "photoIds": ["late", "early", "mid"]})
    out = build_reel_assets(media, "t1")
    assert out["batchId"] == "sel-1"
    assert [card["photoId"] for card in out["assets"]] == ["early", "mid", "late"]  # 按拍摄日
    assert out["assets"][0]["exif"] == {"cameraMake": "Apple"}
    assert out["assets"][0]["tags"] == {"mood": "宁静"}
    assert out["highlights"] == ["late"]  # 从 VLM tags 挑高光镜头


def test_build_reel_assets_only_selected_and_tolerates_no_tags():
    media = FakeMedia([_photo("kept", day="2026-09-01"), _photo("skipped", day="2026-09-03")])
    media.set_selected("t1", {"batchId": "s", "source": "photo-selection", "photoIds": ["kept"]})
    out = build_reel_assets(media, "t1")
    assert [card["photoId"] for card in out["assets"]] == ["kept"]
    assert out["assets"][0]["tags"] == {}  # 没打过标留空，不报错
    assert out["highlights"] == []


def test_set_tags_writes_back(tmp_path):
    from PIL import Image
    buf = io.BytesIO(); Image.new("RGB", (8, 8), (1, 2, 3)).save(buf, format="JPEG")
    store = MediaStore(tmp_path)
    photo = store.add(buf.getvalue(), "t1", "2026-09-01")
    updated = store.set_tags(photo["id"], {"scene": "机场", "quality": {"highlight": True}})
    assert updated["tags"]["scene"] == "机场"
    assert store.get(photo["id"])["tags"]["quality"]["highlight"] is True


def test_set_tags_unknown_photo(tmp_path):
    store = MediaStore(tmp_path)
    assert store.set_tags("00000000-0000-0000-0000-000000000000", {"scene": "x"}) is None
