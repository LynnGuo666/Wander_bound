"""The sticker crop keeps the central object and excludes distant generation debris."""
from PIL import Image, ImageDraw
import pytest

from pyserver.media.stickers import isolate_sticker


def test_remote_artifact_is_not_cropped_into_the_sticker():
    image = Image.new("RGBA", (512, 512), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    draw.ellipse((170, 150, 350, 340), fill=(180, 110, 64, 255))
    draw.rectangle((3, 3, 48, 48), fill=(70, 90, 120, 255))
    cropped = isolate_sticker(image)
    assert cropped.width < 220 and cropped.height < 230
    assert cropped.getpixel((cropped.width // 2, cropped.height // 2))[3] == 255
    assert not any(pixel[:3] == (70, 90, 120) and pixel[3] for pixel in cropped.getdata())


def test_opaque_background_is_rejected():
    image = Image.new("RGBA", (512, 512), (200, 180, 140, 255))
    image.putpixel((0, 0), (0, 0, 0, 0))
    with pytest.raises(RuntimeError, match="不透明背景"):
        isolate_sticker(image)
