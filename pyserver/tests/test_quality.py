import io
from PIL import Image, ImageDraw, ImageEnhance
from pyserver.media import quality


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


def test_blur_sharp_vs_flat():
    assert quality.blur(quality.load_gray(_jpeg(_checker()))) > 200
    assert quality.blur(quality.load_gray(_jpeg(Image.new("L", (256, 256), 128)))) < 20


def test_exposure_verdicts():
    assert quality.exposure(quality.load_gray(_jpeg(Image.new("L", (256, 256), 255))))["verdict"] == "over"
    assert quality.exposure(quality.load_gray(_jpeg(Image.new("L", (256, 256), 0))))["verdict"] == "under"
    assert quality.exposure(quality.load_gray(_jpeg(Image.new("L", (256, 256), 128))))["verdict"] == "ok"


def test_dhash_identity_and_brightness_invariance():
    assert quality.hamming(quality.dhash(quality.load_gray(_jpeg(_checker()))), quality.dhash(quality.load_gray(_jpeg(_checker())))) == 0
    bright = ImageEnhance.Brightness(quality.load_gray(_jpeg(_checker()))).enhance(1.3)
    assert quality.hamming(quality.dhash(quality.load_gray(_jpeg(_checker()))), quality.dhash(bright)) <= 4


def test_quality_flags():
    q = quality.quality(_jpeg(Image.new("L", (256, 256), 128)))
    assert q["reject"] and "blurry" in q["flags"]
    q2 = quality.quality(_jpeg(_checker()))
    assert not q2["reject"] and q2["sharpness"] > 0.25
    q3 = quality.quality(_jpeg(_checker()), iso=3200)
    assert "noisy" in q3["flags"]
