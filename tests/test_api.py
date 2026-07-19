import io
import json
import zipfile
from PIL import Image
from fastapi.testclient import TestClient
from heic_convert.app import app
from tests.conftest import make_heic_fixture, make_jpg_fixture, make_png_fixture

client = TestClient(app)


def test_preview_returns_data_url():
    data = make_heic_fixture()
    r = client.post("/preview", files={"files": ("a.heic", data, "image/heic")})
    assert r.status_code == 200
    body = r.json()
    assert body["previews"][0]["ok"] is True
    assert body["previews"][0]["preview"].startswith("data:image/jpeg;base64,")


def test_preview_rejects_non_heic():
    r = client.post("/preview", files={"files": ("a.txt", b"hello", "text/plain")})
    body = r.json()
    assert body["previews"][0]["ok"] is False
    assert body["previews"][0]["error"]


def test_convert_single_returns_image():
    data = make_heic_fixture()
    r = client.post(
        "/convert",
        files={"files": ("a.heic", data, "image/heic")},
        data={"format": "png", "quality": "95", "edits": "{}"},
    )
    assert r.status_code == 200
    assert r.headers["content-type"] == "image/png"
    assert Image.open(io.BytesIO(r.content)).format == "PNG"


def test_convert_multiple_returns_zip_with_errors_txt():
    good = make_heic_fixture()
    r = client.post(
        "/convert",
        files=[
            ("files", ("a.heic", good, "image/heic")),
            ("files", ("b.heic", good, "image/heic")),
            ("files", ("bad.heic", b"not-an-image", "image/heic")),
        ],
        data={"format": "png", "quality": "95", "edits": "{}"},
    )
    assert r.status_code == 200
    assert r.headers["content-type"] == "application/zip"
    zf = zipfile.ZipFile(io.BytesIO(r.content))
    names = zf.namelist()
    assert "a.png" in names and "b.png" in names
    assert "errors.txt" in names
    assert "bad.heic" in zf.read("errors.txt").decode()


def test_convert_applies_edit_crop():
    data = make_heic_fixture(size=(64, 48))
    edits = json.dumps({"a.heic": {"crop": [0.5, 0.5, 0.5, 0.5]}})
    r = client.post(
        "/convert",
        files={"files": ("a.heic", data, "image/heic")},
        data={"format": "png", "quality": "95", "edits": edits},
    )
    assert Image.open(io.BytesIO(r.content)).size == (32, 24)


def test_convert_applies_edit_rotate():
    data = make_heic_fixture(size=(64, 48))
    edits = json.dumps({"a.heic": {"rotate": 90}})
    r = client.post(
        "/convert",
        files={"files": ("a.heic", data, "image/heic")},
        data={"format": "png", "quality": "95", "edits": edits},
    )
    assert Image.open(io.BytesIO(r.content)).size == (48, 64)


def test_static_assets_are_served():
    r = client.get("/static/index.html")
    assert r.status_code == 200


def test_convert_malformed_edits_returns_400():
    r = client.post(
        "/convert",
        files={"files": ("a.heic", make_heic_fixture(), "image/heic")},
        data={"format": "png", "quality": "95", "edits": "{not valid json"},
    )
    assert r.status_code == 400


def test_convert_reports_files_over_batch_limit():
    data = make_heic_fixture()
    files = [("files", (f"f{i}.heic", data, "image/heic")) for i in range(51)]
    r = client.post(
        "/convert",
        files=files,
        data={"format": "png", "quality": "95", "edits": "{}"},
    )
    assert r.status_code == 200
    assert r.headers["content-type"] == "application/zip"
    zf = zipfile.ZipFile(io.BytesIO(r.content))
    assert "errors.txt" in zf.namelist()
    errors_text = zf.read("errors.txt").decode()
    assert "batch limit" in errors_text
    assert "f50.heic" in errors_text


def test_convert_accepts_jpg():
    r = client.post(
        "/convert",
        files={"files": ("a.jpg", make_jpg_fixture(), "image/jpeg")},
        data={"format": "png", "quality": "95", "edits": "{}"},
    )
    assert r.status_code == 200
    assert r.headers["content-type"] == "image/png"
    assert Image.open(io.BytesIO(r.content)).format == "PNG"


def test_convert_accepts_png():
    r = client.post(
        "/convert",
        files={"files": ("a.png", make_png_fixture(), "image/png")},
        data={"format": "jpg", "quality": "90", "edits": "{}"},
    )
    assert r.status_code == 200
    assert r.headers["content-type"] == "image/jpeg"


def test_preview_accepts_jpg():
    r = client.post("/preview", files={"files": ("a.jpg", make_jpg_fixture(), "image/jpeg")})
    body = r.json()
    assert body["previews"][0]["ok"] is True


def test_convert_accepts_webp_input():
    from heic_convert.core import convert_image
    webp = convert_image(make_png_fixture(), fmt="webp")
    r = client.post("/convert", files={"files": ("a.webp", webp, "image/webp")},
                    data={"format": "png", "quality": "95", "edits": "{}"})
    assert r.status_code == 200
    assert r.headers["content-type"] == "image/png"


def test_convert_webp_single():
    r = client.post(
        "/convert",
        files={"files": ("a.heic", make_heic_fixture(), "image/heic")},
        data={"format": "webp", "quality": "90", "edits": "{}"},
    )
    assert r.status_code == 200
    assert r.headers["content-type"] == "image/webp"
    assert Image.open(io.BytesIO(r.content)).format == "WEBP"


def test_convert_resize_field():
    data = make_heic_fixture(size=(4000, 3000))
    r = client.post(
        "/convert",
        files={"files": ("a.heic", data, "image/heic")},
        data={"format": "png", "quality": "95", "edits": "{}", "resize": "1024"},
    )
    assert max(Image.open(io.BytesIO(r.content)).size) == 1024


def test_scrub_keeps_jpg_format_strips_metadata():
    r = client.post(
        "/convert",
        files={"files": ("a.jpg", make_jpg_fixture(), "image/jpeg")},
        data={"format": "scrub", "quality": "95", "edits": "{}"},
    )
    assert r.headers["content-type"] == "image/jpeg"
    img = Image.open(io.BytesIO(r.content))
    assert img.format == "JPEG"
    assert not dict(img.getexif())


def test_scrub_heic_becomes_jpg():
    r = client.post(
        "/convert",
        files={"files": ("a.heic", make_heic_fixture(), "image/heic")},
        data={"format": "scrub", "quality": "95", "edits": "{}"},
    )
    assert r.headers["content-type"] == "image/jpeg"


def test_ttf_served_as_font_mime():
    r = client.get("/static/vendor/VT323-Regular.ttf")
    assert r.status_code == 200
    assert r.headers["content-type"] in ("font/ttf", "font/sfnt")


def test_output_filename_sanitized():
    data = make_heic_fixture()
    r = client.post("/convert",
        files={"files": ("../../evil.heic", data, "image/heic")},
        data={"format": "png", "quality": "95", "edits": "{}"})
    assert r.status_code == 200
    cd = r.headers["content-disposition"]
    assert "/" not in cd.split("filename=")[1] and "\\" not in cd
    assert ".." not in cd


def test_cross_origin_post_refused():
    data = make_heic_fixture()
    r = client.post("/convert",
        files={"files": ("a.heic", data, "image/heic")},
        data={"format": "png", "quality": "95", "edits": "{}"},
        headers={"origin": "http://evil.example"})
    assert r.status_code == 403


def test_same_origin_post_allowed():
    data = make_heic_fixture()
    r = client.post("/convert",
        files={"files": ("a.heic", data, "image/heic")},
        data={"format": "png", "quality": "95", "edits": "{}"},
        headers={"origin": "http://testserver"})
    assert r.status_code == 200


def test_zip_dedupes_colliding_output_names():
    data = make_heic_fixture()
    files = [("files", ("a.heic", data, "image/heic")) for _ in range(3)]
    r = client.post("/convert", files=files,
        data={"format": "png", "quality": "95", "edits": "{}"})
    assert r.status_code == 200
    zf = zipfile.ZipFile(io.BytesIO(r.content))
    names = [n for n in zf.namelist() if n != "errors.txt"]
    assert sorted(names) == ["a.png", "a_1.png", "a_2.png"]
