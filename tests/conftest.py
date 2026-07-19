import io
import pytest
from PIL import Image
import pillow_heif

pillow_heif.register_heif_opener()


def make_heic_fixture(size=(64, 48), color=(200, 30, 30), orientation=None, icc=None):
    """Build a HEIC image in memory. Returns bytes."""
    img = Image.new("RGB", size, color)
    exif = None
    if orientation is not None:
        exif = img.getexif()
        exif[0x0112] = orientation  # 0x0112 == Orientation tag
        exif = exif.tobytes()
    params = {}
    if exif is not None:
        params["exif"] = exif
    if icc is not None:
        params["icc_profile"] = icc
    buf = io.BytesIO()
    img.save(buf, format="HEIF", **params)
    return buf.getvalue()


def make_jpg_fixture(size=(64, 48), color=(120, 160, 80)):
    img = Image.new("RGB", size, color)
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=90)
    return buf.getvalue()


def make_png_fixture(size=(64, 48), color=(80, 120, 160)):
    img = Image.new("RGB", size, color)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


@pytest.fixture
def heic_bytes():
    return make_heic_fixture()
