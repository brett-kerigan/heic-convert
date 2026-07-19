import os
import socket
import threading
import time

import uvicorn

from heic_convert.app import app

WINDOW_TITLE = "HEIC Convert"


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


class _WindowApi:
    """Controls for the frameless window, reached from JS as window.pywebview.api.* .
    The app's own green title bar drives these (there is no OS title bar)."""

    def __init__(self) -> None:
        self._window = None
        self._maximized = False

    def bind(self, window) -> None:
        self._window = window

    def minimize(self) -> None:
        if self._window is not None:
            self._window.minimize()

    def toggle_maximize(self) -> None:
        if self._window is None:
            return
        if self._maximized:
            self._window.restore()
        else:
            self._window.maximize()
        self._maximized = not self._maximized

    def close(self) -> None:
        if self._window is not None:
            self._window.destroy()


def main() -> None:
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

    # Desktop app: open a native window — no browser tab, no console. Closing it quits
    # (the daemon server thread dies with the process).
    try:
        import webview

        api = _WindowApi()
        window = webview.create_window(
            WINDOW_TITLE,
            url,
            js_api=api,
            width=1280,
            height=860,
            min_size=(960, 640),
            frameless=True,   # no OS chrome — the app's own green title bar is the window
            easy_drag=False,  # only the .pywebview-drag-region (title bar) drags the window
        )
        api.bind(window)
        webview.start()  # blocks on the main thread until the window is closed
    except Exception as exc:  # noqa: BLE001 - if the native window can't open, degrade gracefully
        try:
            import ctypes  # Windows: show a message box pointing at the URL

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
