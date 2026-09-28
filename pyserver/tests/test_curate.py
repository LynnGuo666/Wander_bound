import io
import uuid
from PIL import Image, ImageDraw
from pyserver.media import curate
from pyserver.media.store import MediaStore


def _jpeg(gray: Image.Image) -> bytes:
    buf = io.BytesIO()
    gray.convert("RGB").save(buf, format="JPEG", quality=92)
    return buf.getvalue()


def _checker(block: int = 32, box: int = 256) -> Image.Image:
    img = Image.new("L", (box, box), 0)
    d = ImageDraw.Draw(img)
    for y in range(0, box, block):
        for x in range(0, box, block):
            if (x // block + y // block) % 2 == 0:
                d.rectangle([x, y, x + block - 1, y + block - 1], fill=255)
    return img


def test_curate_keeps_drops_and_dedups(tmp_path):
    store = MediaStore(root=tmp_path)
    trip = str(uuid.uuid4())
    sharp = _jpeg(_checker())
    flat = _jpeg(Image.new("L", (256, 256), 128))
    a = store.add(sharp, trip, None)["id"]
    b = store.add(sharp, trip, None)["id"]
    store.add(flat, trip, None)

    result = curate.curate_trip(store, trip)
    assert result["counts"]["total"] == 3
    assert result["counts"]["keep"] == 1
    assert result["counts"]["dup"] == 1
    assert result["counts"]["drop"] == 1
    assert result["keep"][0] in (a, b)

    stored = store.get(result["keep"][0])["quality"]
    assert stored["sharpness"] > 0.25 and not stored["reject"]


def test_curate_target_trims_overflow(tmp_path):
    store = MediaStore(root=tmp_path)
    trip = str(uuid.uuid4())
    for _ in range(4):
        store.add(_jpeg(_checker(block=16)), trip, None)
    result = curate.curate_trip(store, trip, target=2)
    assert len(result["keep"]) == 2
    assert result["counts"]["overflow"] == 2
