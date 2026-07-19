import io
from PIL import Image, ImageOps, ImageCms
import pillow_heif

_registered = False


def register_heif() -> None:
    global _registered
    if not _registered:
        pillow_heif.register_heif_opener()
        _registered = True


def convert_image(data: bytes, fmt: str = "png", quality: int = 95, crop=None,
                  resize: int = 0, rotate: int = 0, flip_h: bool = False) -> bytes:
    register_heif()
    fmt = fmt.lower()
    if fmt not in ("png", "jpg", "jpeg", "webp"):
        raise ValueError(f"unsupported format: {fmt}")

    img = Image.open(io.BytesIO(data))
    img = ImageOps.exif_transpose(img)  # bake EXIF orientation into pixels

    icc = img.info.get("icc_profile")
    if icc:
        try:
            src_profile = ImageCms.ImageCmsProfile(io.BytesIO(icc))
            srgb = ImageCms.createProfile("sRGB")
            img = ImageCms.profileToProfile(
                img, src_profile, srgb, outputMode="RGB"
            )
            img.info.pop("icc_profile", None)  # profile applied; drop it
        except (ImageCms.PyCMSError, OSError):
            img = img.convert("RGB")
    else:
        img = img.convert("RGB")

    rotate = int(rotate) % 360
    if rotate in (90, 180, 270):
        # PIL rotate is counter-clockwise; negate for clockwise intent.
        img = img.rotate(-rotate, expand=True)
    if flip_h:
        img = img.transpose(Image.FLIP_LEFT_RIGHT)

    if crop is not None:
        x, y, w, h = crop
        W, H = img.size
        left = max(0, round(x * W))
        top = max(0, round(y * H))
        right = min(W, round((x + w) * W))
        bottom = min(H, round((y + h) * H))
        if right > left and bottom > top:
            img = img.crop((left, top, right, bottom))

    if resize and resize > 0:
        W, H = img.size
        longest = max(W, H)
        if longest > resize:
            scale = resize / longest
            img = img.resize((max(1, round(W * scale)), max(1, round(H * scale))),
                             Image.LANCZOS)

    out = io.BytesIO()
    if fmt == "png":
        # No exif, no icc, fixed compress level -> deterministic, metadata-free
        img.save(out, format="PNG", compress_level=6)
    elif fmt == "webp":
        img.save(out, format="WEBP", quality=quality, method=6)
    else:
        img.save(out, format="JPEG", quality=quality, subsampling="4:2:0",
                 optimize=False)
    return out.getvalue()


def is_heic(data: bytes) -> bool:
    return bool(pillow_heif.is_supported(io.BytesIO(data)))


SUPPORTED_FORMATS = {"HEIF", "HEIC", "JPEG", "MPO", "PNG", "WEBP"}


def is_supported_image(data: bytes) -> bool:
    """True if data is a supported still image (HEIC/HEIF/JPG/PNG/WebP), by content."""
    register_heif()
    try:
        with Image.open(io.BytesIO(data)) as im:
            return im.format in SUPPORTED_FORMATS
    except Exception:
        return False


def source_format_ext(data: bytes) -> str:
    """Output extension for scrub mode: keep source format, but HEIC/HEIF -> jpg."""
    register_heif()
    try:
        with Image.open(io.BytesIO(data)) as im:
            fmt = im.format
    except Exception:
        return "jpg"
    if fmt == "PNG":
        return "png"
    if fmt == "WEBP":
        return "webp"
    return "jpg"  # JPEG, MPO, HEIF, HEIC -> jpg


def make_preview(data: bytes, max_dim: int = 2048) -> bytes:
    register_heif()
    img = Image.open(io.BytesIO(data))
    img = ImageOps.exif_transpose(img)
    icc = img.info.get("icc_profile")
    if icc:
        try:
            src = ImageCms.ImageCmsProfile(io.BytesIO(icc))
            img = ImageCms.profileToProfile(
                img, src, ImageCms.createProfile("sRGB"), outputMode="RGB"
            )
        except (ImageCms.PyCMSError, OSError):
            img = img.convert("RGB")
    else:
        img = img.convert("RGB")
    img.thumbnail((max_dim, max_dim))
    out = io.BytesIO()
    img.save(out, format="JPEG", quality=85)
    return out.getvalue()
