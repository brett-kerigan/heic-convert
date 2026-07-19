import base64
import os
import socket
import sys
import threading
import time

import uvicorn

from heic_convert.app import app

WINDOW_TITLE = "HEIC Convert"


def _ensure_std_streams() -> None:
    """Give sys.stdout/stderr a real stream when they're missing.

    PyInstaller's windowed (console=False) build sets both to None. uvicorn's log
    formatter calls ``sys.stdout.isatty()`` while configuring, which raises
    ``AttributeError: 'NoneType' object has no attribute 'isatty'`` and crashes the app
    on launch. Pointing them at os.devnull makes such calls harmless (isatty() -> False).
    """
    for name in ("stdout", "stderr"):
        if getattr(sys, name, None) is None:
            setattr(sys, name, open(os.devnull, "w", encoding="utf-8"))


def _free_port(preferred: int = 8092) -> int:
    """Return `preferred` if it can be bound on loopback, else an OS-assigned free port."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        try:
            s.bind(("127.0.0.1", preferred))
            return preferred
        except OSError:
            pass
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _serve_forever(thread: threading.Thread, url: str) -> None:
    """Block until the server thread ends — headless/self-host/fallback mode (no window)."""
    print(f"heic-convert is running at {url} — open it in your browser. Ctrl-C to quit.")
    try:
        while thread.is_alive():
            thread.join(0.5)
    except KeyboardInterrupt:
        pass


def _use_dark_titlebar(window) -> None:
    """Force a dark title bar so the OS window frame matches the black CRT content."""
    try:
        import ctypes

        hwnd = window.native.Handle.ToInt32()
        # DWMWA_USE_IMMERSIVE_DARK_MODE = 20, value 1 = dark
        ctypes.windll.dwmapi.DwmSetWindowAttribute(
            hwnd, 20, ctypes.byref(ctypes.c_int(1)), ctypes.sizeof(ctypes.c_int)
        )
    except Exception:  # noqa: BLE001 - cosmetic, best-effort
        pass


class _SaveApi:
    """JS-callable bridge for native save dialogs. Only present in the desktop app —
    the browser/self-host build has no ``window.pywebview``, so the frontend falls back
    to ordinary browser downloads. The HTTP server still writes nothing; files are only
    written here, and only to the location the user picks in a dialog."""

    def __init__(self) -> None:
        self._window = None  # set to the pywebview window after creation

    @staticmethod
    def _dedupe(folder: str, name: str) -> str:
        """A path inside `folder` that doesn't collide, appending _1, _2, … if needed."""
        path = os.path.join(folder, name)
        if not os.path.exists(path):
            return path
        stem, ext = os.path.splitext(name)
        i = 1
        while True:
            candidate = os.path.join(folder, f"{stem}_{i}{ext}")
            if not os.path.exists(candidate):
                return candidate
            i += 1

    def save_file(self, suggested_name: str, b64: str) -> dict:
        """Save one file via a native Save-As dialog. Returns {ok, path} / {cancelled} / {error}."""
        import webview

        try:
            result = self._window.create_file_dialog(
                webview.FileDialog.SAVE, save_filename=suggested_name
            )
        except Exception as exc:  # noqa: BLE001
            return {"ok": False, "error": str(exc)}
        if not result:
            return {"ok": False, "cancelled": True}
        path = result[0] if isinstance(result, (list, tuple)) else result
        try:
            with open(path, "wb") as fh:
                fh.write(base64.b64decode(b64))
        except Exception as exc:  # noqa: BLE001
            return {"ok": False, "error": str(exc)}
        return {"ok": True, "path": path}

    def choose_folder(self) -> "str | None":
        """Ask for a destination folder (batch save). Returns the path, or None if cancelled."""
        import webview

        result = self._window.create_file_dialog(webview.FileDialog.FOLDER)
        if not result:
            return None
        return result[0] if isinstance(result, (list, tuple)) else result

    def save_into(self, folder: str, name: str, b64: str) -> str:
        """Write one file into an already-chosen folder (deduping the name). Returns the path."""
        path = self._dedupe(folder, name)
        with open(path, "wb") as fh:
            fh.write(base64.b64decode(b64))
        return path

    def open_path(self, path: str) -> None:
        """Reveal a saved file/folder in the OS file manager (best-effort, Windows)."""
        try:
            target = path if os.path.isdir(path) else os.path.dirname(path)
            os.startfile(target)  # noqa: S606 - Windows-only desktop app
        except Exception:  # noqa: BLE001
            pass


def main() -> None:
    _ensure_std_streams()  # windowed exe has no console → sys.stdout is None; fix before uvicorn
    port = _free_port()
    url = f"http://127.0.0.1:{port}"
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning"))
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    for _ in range(100):  # wait up to ~10s for the server to come up
        if server.started or not thread.is_alive():
            break
        time.sleep(0.1)

    # Headless serve mode (CI smoke test, or a self-host fallback): no window, just serve.
    if os.environ.get("HEIC_CONVERT_NO_WINDOW"):
        _serve_forever(thread, url)
        return

    # Desktop app: a normal resizable OS window (dark title bar), no browser tab. Closing it quits.
    try:
        import webview

        api = _SaveApi()
        window = webview.create_window(
            WINDOW_TITLE, url, width=1280, height=860, min_size=(900, 620), js_api=api
        )
        api._window = window
        webview.start(lambda: _use_dark_titlebar(window))  # dark title bar once the window is shown
    except Exception as exc:  # noqa: BLE001 - if the window can't open, degrade gracefully
        try:
            import ctypes

            ctypes.windll.user32.MessageBoxW(
                0,
                f"Couldn't open the app window ({exc}).\n\nOpen this in your browser:\n{url}",
                WINDOW_TITLE,
                0x40,
            )
        except Exception:  # noqa: BLE001
            pass
        _serve_forever(thread, url)


if __name__ == "__main__":
    main()
