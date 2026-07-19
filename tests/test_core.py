import io
import os
from PIL import Image
from heic_convert.core import convert_image, is_heic, is_supported_image, make_preview
from tests.conftest import make_heic_fixture, make_jpg_fixture, make_png_fixture

P3_ICC = os.path.join(os.path.dirname(__file__), "fixtures", "DisplayP3.icc")


def test_convert_to_png_returns_valid_png(heic_bytes):
    out = convert_image(heic_bytes, fmt="png")
    img = Image.open(io.BytesIO(out))
    assert img.format == "PNG"
    assert img.mode == "RGB"
    assert img.size == (64, 48)


def test_output_has_no_metadata(heic_bytes):
    out = convert_image(heic_bytes, fmt="png")
    img = Image.open(io.BytesIO(out))
    assert not dict(img.getexif())
    assert "icc_profile" not in img.info


def test_orientation_is_baked_into_pixels():
    # orientation 6 = rotate 90 CW on display; baking swaps W/H of a non-square image
    data = make_heic_fixture(size=(64, 48), orientation=6)
    out = convert_image(data, fmt="png")
    img = Image.open(io.BytesIO(out))
    assert img.size == (48, 64)
    assert not dict(img.getexif())  # orientation tag consumed, not carried over


def test_wide_gamut_is_color_managed_to_srgb():
    # (80,255,80) embedded as Display-P3 maps to a much LESS red sRGB value.
    # A color-managed decode collapses the red channel toward 0; a naive
    # (profile-ignoring) decode leaves it near 80. Margin >> codec noise (±2).
    icc = open(P3_ICC, "rb").read()
    data = make_heic_fixture(size=(16, 16), color=(80, 255, 80), icc=icc)
    out = convert_image(data, fmt="png")
    img = Image.open(io.BytesIO(out))
    r, g, b = img.getpixel((8, 8))
    assert r < 40, f"expected color-managed red near 0, got {r}"
    assert "icc_profile" not in img.info  # profile applied, then dropped


def test_jpg_output_is_valid(heic_bytes):
    out = convert_image(heic_bytes, fmt="jpg", quality=90)
    img = Image.open(io.BytesIO(out))
    assert img.format == "JPEG"
    assert img.mode == "RGB"


def test_png_is_deterministic(heic_bytes):
    a = convert_image(heic_bytes, fmt="png")
    b = convert_image(heic_bytes, fmt="png")
    assert a == b


def test_jpg_is_deterministic(heic_bytes):
    a = convert_image(heic_bytes, fmt="jpg", quality=95)
    b = convert_image(heic_bytes, fmt="jpg", quality=95)
    assert a == b


def test_crop_maps_normalized_rect_to_pixels(heic_bytes):
    # full image is 64x48; crop the right half, bottom half
    out = convert_image(heic_bytes, fmt="png", crop=(0.5, 0.5, 0.5, 0.5))
    img = Image.open(io.BytesIO(out))
    assert img.size == (32, 24)


def test_crop_after_orientation():
    data = make_heic_fixture(size=(64, 48), orientation=6)  # becomes 48x64 oriented
    out = convert_image(data, fmt="png", crop=(0.0, 0.0, 0.5, 0.5))
    img = Image.open(io.BytesIO(out))
    assert img.size == (24, 32)


def test_no_crop_when_none(heic_bytes):
    out = convert_image(heic_bytes, fmt="png", crop=None)
    assert Image.open(io.BytesIO(out)).size == (64, 48)


def test_is_heic_true_for_heic(heic_bytes):
    assert is_heic(heic_bytes) is True


def test_is_heic_false_for_png(heic_bytes):
    png = convert_image(heic_bytes, fmt="png")
    assert is_heic(png) is False


def test_make_preview_downscales_and_is_jpeg():
    data = make_heic_fixture(size=(4000, 3000))
    out = make_preview(data, max_dim=2048)
    img = Image.open(io.BytesIO(out))
    assert img.format == "JPEG"
    assert max(img.size) <= 2048
    assert "icc_profile" not in img.info


def test_is_supported_image_accepts_heic(heic_bytes):
    assert is_supported_image(heic_bytes) is True


def test_is_supported_image_accepts_jpg():
    assert is_supported_image(make_jpg_fixture()) is True


def test_is_supported_image_accepts_png():
    assert is_supported_image(make_png_fixture()) is True


def test_is_supported_image_accepts_webp():
    webp = convert_image(make_png_fixture(), fmt="webp")
    assert is_supported_image(webp) is True


def test_is_supported_image_rejects_non_image():
    assert is_supported_image(b"this is not an image") is False


def test_webp_output_is_valid(heic_bytes):
    out = convert_image(heic_bytes, fmt="webp", quality=90)
    img = Image.open(io.BytesIO(out))
    assert img.format == "WEBP"
    assert img.mode == "RGB"
    assert img.size == (64, 48)


def test_webp_has_no_metadata():
    icc = open(P3_ICC, "rb").read()
    data = make_heic_fixture(size=(16, 16), color=(80, 255, 80), icc=icc)
    out = convert_image(data, fmt="webp")
    img = Image.open(io.BytesIO(out))
    assert "icc_profile" not in img.info
    assert not dict(img.getexif())


def test_strips_real_exif_and_gps():
    from PIL.TiffImagePlugin import IFDRational
    img = Image.new("RGB", (32, 24), (90, 90, 90))
    exif = img.getexif()
    exif[0x0110] = "TestCam"                       # Model
    exif[0x0132] = "2021:07:04 10:00:00"           # DateTime
    gps = exif.get_ifd(0x8825)
    gps[1] = "N"
    # Each GPSLatitude component must be a rational number object (IFDRational),
    # not a raw (num, denom) tuple -- PIL's TIFF rational writer calls abs() on
    # each component, which raises TypeError on a plain tuple.
    gps[2] = (IFDRational(40, 1), IFDRational(26, 1), IFDRational(0, 1))  # GPSLatitude
    buf = io.BytesIO(); img.save(buf, format="JPEG", exif=exif)
    src = buf.getvalue()
    si = Image.open(io.BytesIO(src)).getexif()
    assert si.get(0x0110) == "TestCam"
    assert dict(si.get_ifd(0x8825)), "fixture must carry GPS or the test is vacuous"
    for fmt in ("png", "jpg", "webp"):
        out = convert_image(src, fmt=fmt)
        oi = Image.open(io.BytesIO(out)).getexif()
        assert not dict(oi), f"{fmt}: exif leaked"
        assert not dict(oi.get_ifd(0x8825)), f"{fmt}: GPS leaked"


def test_resize_caps_longest_side():
    data = make_heic_fixture(size=(4000, 3000))
    out = convert_image(data, fmt="png", resize=2048)
    assert max(Image.open(io.BytesIO(out)).size) == 2048


def test_resize_preserves_aspect():
    data = make_heic_fixture(size=(4000, 2000))
    out = convert_image(data, fmt="png", resize=1000)
    assert Image.open(io.BytesIO(out)).size == (1000, 500)


def test_resize_never_upscales():
    data = make_heic_fixture(size=(64, 48))
    out = convert_image(data, fmt="png", resize=2048)
    assert Image.open(io.BytesIO(out)).size == (64, 48)


def test_resize_zero_is_noop():
    data = make_heic_fixture(size=(64, 48))
    out = convert_image(data, fmt="png", resize=0)
    assert Image.open(io.BytesIO(out)).size == (64, 48)


def test_rotate_90_swaps_dimensions(heic_bytes):
    out = convert_image(heic_bytes, fmt="png", rotate=90)   # 64x48 -> 48x64
    assert Image.open(io.BytesIO(out)).size == (48, 64)


def test_rotate_180_keeps_dimensions(heic_bytes):
    out = convert_image(heic_bytes, fmt="png", rotate=180)
    assert Image.open(io.BytesIO(out)).size == (64, 48)


def test_rotate_is_clockwise():
    # top-left red on a black field; after 90 CW it lands top-right.
    img = Image.new("RGB", (10, 10), (0, 0, 0))
    img.putpixel((0, 0), (255, 0, 0))
    buf = io.BytesIO(); img.save(buf, format="PNG")
    out = convert_image(buf.getvalue(), fmt="png", rotate=90)
    res = Image.open(io.BytesIO(out))
    assert res.getpixel((9, 0)) == (255, 0, 0)


def test_flip_h_mirrors():
    img = Image.new("RGB", (10, 10), (0, 0, 0))
    img.putpixel((0, 0), (255, 0, 0))   # top-left
    buf = io.BytesIO(); img.save(buf, format="PNG")
    out = convert_image(buf.getvalue(), fmt="png", flip_h=True)
    res = Image.open(io.BytesIO(out))
    assert res.getpixel((9, 0)) == (255, 0, 0)   # now top-right


def test_rotate_then_crop_order():
    # Asymmetric crop so the two orderings yield DIFFERENT sizes (a symmetric
    # half-crop would commute with the 90° swap and prove nothing).
    # rotate-then-crop (correct): 64x48 -> rotate90 -> 48x64 -> crop(0,0,0.25,0.5) -> 12x32
    # crop-then-rotate (wrong):   64x48 -> crop(0,0,0.25,0.5) -> 16x24 -> rotate90 -> 24x16
    data = make_heic_fixture(size=(64, 48))
    out = convert_image(data, fmt="png", rotate=90, crop=(0.0, 0.0, 0.25, 0.5))
    assert Image.open(io.BytesIO(out)).size == (12, 32)


def test_source_format_ext():
    from heic_convert.core import source_format_ext
    assert source_format_ext(make_jpg_fixture()) == "jpg"
    assert source_format_ext(make_png_fixture()) == "png"
    assert source_format_ext(make_heic_fixture()) == "jpg"  # HEIC -> jpg for sharing
    webp = convert_image(make_png_fixture(), fmt="webp")
    assert source_format_ext(webp) == "webp"
