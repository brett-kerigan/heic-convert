import socket
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
