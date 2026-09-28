"""L0 选优编排：打分 → 拒糊 → 连拍去重 → 排序 → 可选截断。

样本同 test_quality 的 _photo：1024px、64px 灰块，别用小图或纯色。
"""
import io
import random
import uuid
from PIL import Image, ImageFilter
from pyserver.media import curate
from pyserver.media.store import MediaStore


def _jpeg(gray: Image.Image) -> bytes:
    buf = io.BytesIO()
    gray.convert("RGB").save(buf, format="JPEG", quality=92)
    return buf.getvalue()


def _photo(seed: int, cell: int = 64, box: int = 1024) -> Image.Image:
    """确定性"照片"样本：64px 随机灰块拼成的 1024px 图，灰度 96..200。

    块比 dhash 的下采样格子粗，hash 才稳；灰度避开纯黑白，曝光才判 ok；
    边长用生产尺度，避开 1px 边框垫高 Laplacian 方差（详见 test_quality）。
    """
    rnd = random.Random(seed)
    lattice = Image.new("L", (box // cell, box // cell))
    lattice.putdata([rnd.randint(96, 200) for _ in range((box // cell) ** 2)])
    return lattice.resize((box, box), Image.NEAREST)


def test_curate_keeps_drops_and_dedups(tmp_path):
    store = MediaStore(root=tmp_path)
    trip = str(uuid.uuid4())
    sharp = _jpeg(_photo(1))
    blurred = _jpeg(_photo(1).filter(ImageFilter.GaussianBlur(8)))
    a = store.add(sharp, trip, None)["id"]
    b = store.add(sharp, trip, None)["id"]
    store.add(blurred, trip, None)

    result = curate.curate_trip(store, trip)
    assert result["counts"]["total"] == 3
    assert result["counts"]["keep"] == 1
    assert result["counts"]["dup"] == 1     # 两张一样的清晰图，只留一张
    assert result["counts"]["drop"] == 1    # 失焦那张拒掉
    assert result["keep"][0] in (a, b)

    stored = store.get(result["keep"][0])["quality"]
    assert stored["sharpness"] > 0.25 and not stored["reject"]


def test_curate_target_trims_overflow(tmp_path):
    store = MediaStore(root=tmp_path)
    trip = str(uuid.uuid4())
    for seed in range(1, 5):  # 4 张内容各异的清晰照片，互不判重
        store.add(_jpeg(_photo(seed)), trip, None)
    result = curate.curate_trip(store, trip, target=2)
    assert result["counts"]["dup"] == 0
    assert len(result["keep"]) == 2
    assert result["counts"]["overflow"] == 2
