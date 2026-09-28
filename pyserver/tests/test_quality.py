"""L0 质量信号：锐度、曝光、dHash、分块清晰度、运动方向性。样本构造见 _photo。"""
import io
import random
import numpy as np
from PIL import Image, ImageEnhance, ImageFilter
from pyserver.media import quality


def _jpeg(gray: Image.Image) -> bytes:
    buf = io.BytesIO()
    gray.convert("RGB").save(buf, format="JPEG", quality=92)
    return buf.getvalue()


def _noise(seed: int, box: int = 1024) -> Image.Image:
    """连续噪声图。测模糊必须用它：台阶式放大图（_photo）无论怎么模糊都保留块内硬边，
    Laplacian 不会下降，测不出糊。"""
    rnd = random.Random(seed)
    img = Image.new("L", (box, box))
    img.putdata([rnd.randint(96, 200) for _ in range(box * box)])
    return img


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


def test_spatial_separates_flat_blur_from_partial_blur():
    """分块锐度存在的理由：整幅糊该拒，只有局部糊（浅景深/主体失焦）不该一律拒。

    用强噪声样本：Laplacian 走的是 uint8 卷积（见 _laplacian_clamps_on_uint8 的说明），
    方差很小时 clamp 噪声会主导，只有高方差区才测得准。
    """
    noisy = _noise(1)
    blurred = noisy.filter(ImageFilter.GaussianBlur(3))                  # 整幅糊
    partial = noisy.copy()                                               # 只糊右半 = 局部失焦
    partial.paste(noisy.crop((512, 0, 1024, 1024)).filter(ImageFilter.GaussianBlur(3)), (512, 0))

    flat_map = quality.sharpness_map(quality.load_gray(_jpeg(blurred)))
    partial_map = quality.sharpness_map(quality.load_gray(_jpeg(partial)))
    # contrast（清晰块/糊块的比值）才是区分"整体糊"与"局部糊"的量：
    # 整幅糊块间一致，局部糊则一边高一边低。sharpFraction 在这里分不开，
    # 因为两块都在清晰侧或都在糊侧时它是平的——阈值要靠真样本标定。
    assert flat_map["contrast"] < 2.0                             # 整幅糊：块间一致
    assert partial_map["contrast"] > flat_map["contrast"] * 3     # 局部糊：块间差异被拉开

    # 关键：全局 blur 分不开这两者——这正是老判据误杀浅景深照片的原因
    assert quality.blur(quality.load_gray(_jpeg(partial))) < quality.blur(quality.load_gray(_jpeg(noisy)))


def test_laplacian_clamps_on_uint8():
    """记录 blur() 的一个真实局限：PIL Kernel 在 uint8 上卷积会把负值 clamp 成 0。

    Laplacian 本应有正有负，clamp 后只剩非负一半，动态范围损失大半；方差越小，
    被 clamp 噪声主导得越厉害。所以 blur 只在方差较大的区间可信——这就是
    sharpness_map 要用高噪声样本测、且阈值要拿真样本标定的原因。
    """
    gray = Image.new("L", (256, 256), 100)
    clamped = np.asarray(gray.filter(quality._LAPLACIAN))          # 无内核冲突时应全 0
    assert clamped.min() >= 0
    checker = Image.new("L", (64, 64), 0)
    for y in range(0, 64, 16):
        for x in range(0, 64, 16):
            if (x // 16 + y // 16) % 2 == 0:
                checker.paste(Image.new("L", (16, 16), 200), (x, y))
    values = np.asarray(checker.filter(quality._LAPLACIAN), dtype=float)
    assert values.min() >= 0        # 负响应被 clamp，不会出现负值
    assert values.max() > 0         # 边缘仍有正响应


def test_spatial_handles_small_image():
    """小到切不出有意义的块时要 graceful，不能崩、不能返半截数据。"""
    tiny = quality.sharpness_map(quality.load_gray(_jpeg(Image.new("L", (32, 32), 128))))
    assert tiny["grid"] == 0 and tiny["verdict"] == "unknown"
    assert tiny["blocks"] == []


def test_sharpness_map_blocks_cover_the_frame():
    """块要覆盖整幅（不留边角盲区），且数量与 grid 一致。"""
    info = quality.sharpness_map(quality.load_gray(_jpeg(_noise(2))), grid=4)
    assert len(info["blocks"]) == 16
    assert all(value > 0 for value in info["blocks"])   # 噪声图每块都该有响应


def test_motion_anisotropy_reports_both_axes():
    """只输出数值，不给布尔结论；两个轴都要量到。"""
    info = quality.motion_anisotropy(quality.load_gray(_jpeg(_photo(1))))
    assert info["dominant"] in {"vertical", "horizontal"}
    assert 0.0 <= info["anisotropy"] <= 1.0
    assert 0.0 <= info["weakAxisEnergy"] <= 1.0


def test_motion_anisotropy_responds_to_directional_texture():
    """方向直方图要能反映方向性纹理：竖条的梯度集中在 0°（竖直边缘），横条集中在 90°。"""
    vertical_bars = Image.new("L", (512, 512), 60)
    for x in range(0, 512, 64):
        vertical_bars.paste(Image.new("L", (32, 512), 190), (x, 0))
    assert len(set(vertical_bars.getdata())) == 2      # 确认不是无缝铺满的纯色
    info = quality.motion_anisotropy(quality.load_gray(_jpeg(vertical_bars)))
    assert info["dominant"] == "vertical"      # 竖条 → 梯度沿 x → 竖直边缘
    assert info["weakAxisEnergy"] < 0.2       # 水平边缘那侧被压制

