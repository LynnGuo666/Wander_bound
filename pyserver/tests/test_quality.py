"""L0 质量信号：锐度、曝光、dHash。样本构造见 _photo。"""
import io
import random
from PIL import Image, ImageEnhance, ImageFilter
from pyserver.media import quality


def _jpeg(gray: Image.Image) -> bytes:
    buf = io.BytesIO()
    gray.convert("RGB").save(buf, format="JPEG", quality=92)
    return buf.getvalue()


def _photo(seed: int, cell: int = 64, box: int = 1024) -> Image.Image:
    """确定性"照片"样本：64px 随机灰块拼成的 1024px 图，灰度 96..200。

    三处讲究，都是踩过的坑：
    - 块要比 dhash 的下采样格子粗。dhash 先把图缩到 17×16，一格约 60px；块太小
      会被平均掉，哈希位改由数值噪声决定，亮度一动结果就跳。
    - 灰度避开纯黑纯白，否则整片像素顶到 255，曝光判 over、缩放还截断比较关系。
    - 边长用生产尺度（load_gray 长边就是 1024）。小图上 1 像素边框占比大，
      全局 Laplacian 方差会被边框垫高到和画面内容无关——256px 纯色能到 251，
      比拒糊线还高，"越平坦越糊"的前提在小图上不成立。
    """
    rnd = random.Random(seed)
    lattice = Image.new("L", (box // cell, box // cell))
    lattice.putdata([rnd.randint(96, 200) for _ in range((box // cell) ** 2)])
    return lattice.resize((box, box), Image.NEAREST)


def _blurred(seed: int = 1) -> Image.Image:
    return _photo(seed).filter(ImageFilter.GaussianBlur(8))


def test_blur_sharp_vs_blurred():
    sharp = quality.blur(quality.load_gray(_jpeg(_photo(1))))
    blurred = quality.blur(quality.load_gray(_jpeg(_blurred(1))))
    assert sharp > 150            # 清晰：拒糊线以上
    assert blurred < 150          # 失焦：线以下
    assert sharp > blurred * 3    # 区分明显，不是擦线过关


def test_exposure_verdicts():
    assert quality.exposure(quality.load_gray(_jpeg(Image.new("L", (256, 256), 255))))["verdict"] == "over"
    assert quality.exposure(quality.load_gray(_jpeg(Image.new("L", (256, 256), 0))))["verdict"] == "under"
    assert quality.exposure(quality.load_gray(_jpeg(_photo(2))))["verdict"] == "ok"


def test_dhash_identity_and_brightness_invariance():
    h = lambda img: quality.dhash(quality.load_gray(_jpeg(img)))  # noqa: E731
    assert quality.hamming(h(_photo(3)), h(_photo(3))) == 0  # 同一张图，hash 一致
    bright = ImageEnhance.Brightness(quality.load_gray(_jpeg(_photo(3)))).enhance(1.3)
    assert quality.hamming(h(_photo(3)), quality.dhash(bright)) <= 4  # 亮度变了，hash 基本不动


def test_quality_flags():
    q = quality.quality(_jpeg(_blurred(1)))
    assert q["reject"] and "blurry" in q["flags"]
    q2 = quality.quality(_jpeg(_photo(1)))
    assert not q2["reject"] and q2["sharpness"] > 0.25
    q3 = quality.quality(_jpeg(_photo(1)), iso=3200)
    assert "noisy" in q3["flags"]
