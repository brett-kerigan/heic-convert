import io
import socket
import sys

from heic_convert import launcher


def test_free_port_returns_preferred_when_open():
    # find a definitely-free port, then ask launcher to prefer it
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0)); free = s.getsockname()[1]
    assert launcher._free_port(free) == free


def test_free_port_falls_back_when_busy():
    with socket.socket() as busy:
        busy.bind(("127.0.0.1", 0)); taken = busy.getsockname()[1]
        got = launcher._free_port(taken)
        assert got != taken
        # and the returned port is actually bindable
        with socket.socket() as s2:
            s2.bind(("127.0.0.1", got))


def test_ensure_std_streams_replaces_none(monkeypatch):
    # PyInstaller's windowed (console=False) build sets these to None, which crashes
    # uvicorn's log formatter (sys.stdout.isatty()) on launch. The helper must repair them.
    monkeypatch.setattr(sys, "stdout", None)
    monkeypatch.setattr(sys, "stderr", None)
    launcher._ensure_std_streams()
    assert sys.stdout is not None and sys.stderr is not None
    # the call that used to raise AttributeError on None now returns a bool instead
    assert isinstance(sys.stdout.isatty(), bool)
    assert isinstance(sys.stderr.isatty(), bool)


def test_ensure_std_streams_leaves_real_streams_untouched(monkeypatch):
    real = io.StringIO()
    monkeypatch.setattr(sys, "stdout", real)
    launcher._ensure_std_streams()
    assert sys.stdout is real
