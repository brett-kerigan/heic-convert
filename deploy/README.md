# Self-hosting heic-convert on Linux

This guide walks through running heic-convert on your own Linux box: a quick
manual run, and a proper systemd service for something more permanent.

## 1. Clone and install

```bash
git clone <repo> /opt/heic-convert
cd /opt/heic-convert
python3.12 -m venv .venv
.venv/bin/pip install -e .
```

This installs the package along with its runtime dependencies and provides a
`heic-convert` command inside the virtualenv (`python -m heic_convert` also
works).

## 2. Run it

```bash
.venv/bin/heic-convert
```

By default the app listens on `http://127.0.0.1:8092` — loopback only, so
it's reachable from the machine it runs on but not from anywhere else on the
network.

If you want other devices on your **trusted LAN** to reach it, bind to all
interfaces instead:

```bash
.venv/bin/python -m uvicorn heic_convert.app:app --host 0.0.0.0 --port 8092
```

...and open port 8092 in your firewall. Before you do this, note that
**heic-convert has no authentication** — anyone who can reach the port can
use it. Only do this on a trusted home/LAN network or behind a VPN, and never
expose it directly to the open internet.

## 3. Run as a service (systemd)

To keep heic-convert running in the background and restart it automatically
on failure or reboot, install it as a systemd service:

```bash
sudo cp deploy/heic-convert.service /etc/systemd/system/
```

(or symlink it, if you'd rather keep the file tracked in the repo). Edit the
copied unit file to match your setup — set `User=` to the account that should
run the service, and update `WorkingDirectory=`/`ExecStart=` if you installed
somewhere other than `/opt/heic-convert`.

Then enable and start it:

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now heic-convert
```

Check that it's running with:

```bash
systemctl status heic-convert
```

## 4. Expose beyond your LAN (optional, advanced)

If you want to reach heic-convert from outside your LAN, don't port-forward
it directly to the internet — put something in front of it that handles
authentication and/or TLS. A reverse proxy such as nginx or Caddy (with a
TLS certificate) is a common option, as is a mesh VPN like Tailscale, which
lets your own devices reach the service securely without exposing it
publicly. Either approach works well; pick whichever fits the tools you
already use.

Whichever you choose, make sure the reverse proxy forwards the original
`Host` header it received (e.g. nginx `proxy_set_header Host $host;`) — the
app checks that header against each request's Origin to accept same-origin
POSTs, so a rewritten Host will cause it to refuse them.
