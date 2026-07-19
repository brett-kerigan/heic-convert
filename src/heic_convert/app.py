import base64
import io
import json
import mimetypes
import os
import re
import sys
import zipfile

from fastapi import FastAPI, HTTPException, UploadFile, File, Form
from fastapi.responses import Response, FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from heic_convert.core import convert_image, make_preview, is_heic, is_supported_image, source_format_ext

MAX_FILE_BYTES = 100 * 1024 * 1024
MAX_FILES = 50

mimetypes.add_type("font/ttf", ".ttf")

if getattr(sys, "frozen", False):
    _BASE = getattr(sys, "_MEIPASS", os.path.dirname(sys.executable))
else:
    _BASE = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
STATIC_DIR = os.path.join(_BASE, "static")

app = FastAPI(title="heic-convert")
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

from urllib.parse import urlparse
from fastapi import Request
from starlette.responses import PlainTextResponse


@app.middleware("http")
async def _refuse_cross_origin(request: Request, call_next):
    origin = request.headers.get("origin")
    if request.method == "POST" and origin:
        # allow only same-origin POSTs: the Origin's host:port must match the Host
        # we were reached at (works for 127.0.0.1, localhost, or a LAN IP alike).
        if urlparse(origin).netloc != request.headers.get("host", ""):
            return PlainTextResponse("cross-origin request refused", status_code=403)
    return await call_next(request)


def _ext(fmt: str) -> str:
    f = fmt.lower()
    if f in ("jpg", "jpeg"):
        return "jpg"
    if f == "webp":
        return "webp"
    return "png"


def _safe_base(name: str) -> str:
    """Last path component (either separator), stem only, no traversal/control chars."""
    stem = re.split(r"[\\/]", name)[-1]
    stem = os.path.splitext(stem)[0]
    stem = re.sub(r"[\x00-\x1f]", "", stem).strip().strip(".")
    return stem or "image"


def _out_name(name: str, fmt: str) -> str:
    return f"{_safe_base(name)}.{_ext(fmt)}"


def _unique(name: str, used: set) -> str:
    if name not in used:
        used.add(name)
        return name
    stem, dot, ext = name.rpartition(".")
    n = 1
    while True:
        cand = f"{stem}_{n}.{ext}" if dot else f"{name}_{n}"
        if cand not in used:
            used.add(cand)
            return cand
        n += 1


@app.get("/")
def index():
    return FileResponse(os.path.join(STATIC_DIR, "index.html"))


@app.post("/preview")
async def preview(files: list[UploadFile] = File(...)):
    out = []
    for i, f in enumerate(files):
        item = {"name": f.filename, "ok": False, "preview": None, "error": None}
        if i >= MAX_FILES:
            item["error"] = f"batch limit ({MAX_FILES} files) exceeded"
            out.append(item)
            continue
        data = await f.read()
        if len(data) > MAX_FILE_BYTES:
            item["error"] = "file exceeds 100 MB"
        elif not is_supported_image(data):
            item["error"] = "unsupported file (not a HEIC/HEIF/JPG/PNG/WEBP image)"
        else:
            try:
                b64 = base64.b64encode(make_preview(data)).decode()
                item["preview"] = f"data:image/jpeg;base64,{b64}"
                item["ok"] = True
            except Exception as e:  # noqa: BLE001 - report per-file, don't crash batch
                item["error"] = f"preview failed: {e}"
        out.append(item)
    return JSONResponse({"previews": out})


@app.post("/convert")
async def convert(
    files: list[UploadFile] = File(...),
    format: str = Form("png"),
    quality: int = Form(95),
    edits: str = Form("{}"),
    resize: int = Form(0),
):
    try:
        edit_map = json.loads(edits or "{}")
        if not isinstance(edit_map, dict):
            raise ValueError("edits must be a JSON object")
    except (ValueError, TypeError):
        raise HTTPException(status_code=400, detail="malformed 'edits' parameter")
    results = []   # (out_name, bytes)
    errors = []    # "name: reason"
    for i, f in enumerate(files):
        if i >= MAX_FILES:
            errors.append(f"{f.filename}: batch limit ({MAX_FILES} files) exceeded")
            continue
        data = await f.read()
        if len(data) > MAX_FILE_BYTES:
            errors.append(f"{f.filename}: exceeds 100 MB")
            continue
        if not is_supported_image(data):
            errors.append(f"{f.filename}: unsupported file (not a HEIC/HEIF/JPG/PNG/WEBP image)")
            continue
        try:
            ed = edit_map.get(f.filename) or {}
            crop = ed.get("crop")
            crop_tuple = tuple(crop) if crop else None
            per_fmt = source_format_ext(data) if format.lower() == "scrub" else format
            out_bytes = convert_image(
                data, fmt=per_fmt, quality=quality, crop=crop_tuple,
                resize=resize, rotate=int(ed.get("rotate", 0) or 0),
                flip_h=bool(ed.get("flipH", False)),
            )
            results.append((_out_name(f.filename, per_fmt), out_bytes))
        except Exception as exc:  # noqa: BLE001
            errors.append(f"{f.filename}: {exc}")

    # Single successful file and no errors -> return the image directly
    if len(results) == 1 and not errors:
        name, body = results[0]
        ext = name.rsplit(".", 1)[-1].lower()
        media = {"jpg": "image/jpeg", "webp": "image/webp"}.get(ext, "image/png")
        return Response(
            content=body,
            media_type=media,
            headers={"Content-Disposition": f'attachment; filename="{name}"'},
        )

    # Otherwise -> zip (dedupe duplicate output names)
    buf = io.BytesIO()
    used = set()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for name, body in results:
            zf.writestr(_unique(name, used), body)
        if errors:
            zf.writestr("errors.txt", "\n".join(errors) + "\n")
    return Response(
        content=buf.getvalue(),
        media_type="application/zip",
        headers={"Content-Disposition": 'attachment; filename="converted.zip"'},
    )
