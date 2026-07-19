"""Tests for the native-save bridge's file-writing logic (`_SaveApi`).

The dialog methods (`save_file`, `choose_folder`) need a live pywebview window and are
verified manually. `save_into` / `_dedupe` are pure disk logic and are covered here.
"""

import base64
import os

from heic_convert.launcher import _SaveApi


def test_save_into_writes_exact_bytes(tmp_path):
    api = _SaveApi()
    data = b"\x89PNG\r\n\x1a\n-hello-bytes"
    path = api.save_into(str(tmp_path), "out.png", base64.b64encode(data).decode())
    assert os.path.basename(path) == "out.png"
    with open(path, "rb") as fh:
        assert fh.read() == data


def test_save_into_dedupes_collisions(tmp_path):
    api = _SaveApi()
    b64 = base64.b64encode(b"x").decode()
    p1 = api.save_into(str(tmp_path), "a.png", b64)
    p2 = api.save_into(str(tmp_path), "a.png", b64)
    p3 = api.save_into(str(tmp_path), "a.png", b64)
    assert os.path.basename(p1) == "a.png"
    assert os.path.basename(p2) == "a_1.png"
    assert os.path.basename(p3) == "a_2.png"
    # all three exist independently — nothing overwritten
    assert len({p1, p2, p3}) == 3
    for p in (p1, p2, p3):
        assert os.path.exists(p)


def test_dedupe_returns_plain_name_when_free(tmp_path):
    api = _SaveApi()
    path = api._dedupe(str(tmp_path), "fresh.jpg")
    assert path == os.path.join(str(tmp_path), "fresh.jpg")


def test_dedupe_preserves_multi_dot_extension(tmp_path):
    api = _SaveApi()
    (tmp_path / "photo.final.jpg").write_bytes(b"1")
    path = api._dedupe(str(tmp_path), "photo.final.jpg")
    assert os.path.basename(path) == "photo.final_1.jpg"
