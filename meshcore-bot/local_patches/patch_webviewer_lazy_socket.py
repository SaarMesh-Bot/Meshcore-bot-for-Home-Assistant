#!/usr/bin/env python3
"""Source patch: the dashboard's live connection (socket.io) only starts on a page that uses it.

Every dashboard page opened a live connection in base.html, also pages that never use it (Games, Radar, Plugins,
Problems, Mailbox, ...). In the Home Assistant sidebar every request goes through Home Assistant (ingress) on the same
address as Home Assistant itself, and a browser talks to one address over about six connections at a time: Home
Assistant's own connections plus a live connection per dashboard page filled that up, and the next request had to wait
(the page seemed to hang; found 2026-10-01). Now `connectionManager.socket` starts the connection the first time a page
asks for it (Realtime, Logs and Mesh do so at once, so they work as before); other pages never open it, and the navbar
shows "Live: off" there. The banner check (radio offline, ...) runs every 30 s instead of 10 s, and only while the
page is visible.
"""
import pathlib
import sys

ROOT = pathlib.Path.cwd()


def patch(path: str, old: str, new: str) -> None:
    p = ROOT / path
    text = p.read_text()
    count = text.count(old)
    if count != 1:
        sys.exit(
            f"PATCH FAILED - anchor text found {count} time(s) in {path} "
            f"(expected 1; upstream code likely changed):\n{old!r}"
        )
    p.write_text(text.replace(old, new))
    print(f"Patched {path}")


patch(
    "modules/web_viewer/templates/base.html",
    """            constructor() {
                this.socket = null;
                this.connected = false;
                this.lastActivity = null;
                this.pingInterval = null;

                this.initializeSocket();
                this.startPingInterval();
            }
""",
    """            constructor() {
                this._socket = null;
                this._starting = false;
                this.connected = false;
                this.lastActivity = null;
                this.pingInterval = null;
                // (add-on) no connection yet: it starts when a page asks for connectionManager.socket
            }

            get socket() {
                if (!this._socket && !this._starting) {
                    this._starting = true;
                    this.initializeSocket();
                    this.startPingInterval();
                }
                return this._socket;
            }

            set socket(value) {
                this._socket = value;
            }
""",
)

patch(
    "modules/web_viewer/templates/base.html",
    """            // Update timestamp immediately and every second
            updateTimestamp();""",
    """            // (add-on) a page that never asked for the live connection: say so instead of "Disconnected"
            if (!window.connectionManager._socket) {
                const t = document.getElementById('connection-text');
                if (t) t.textContent = 'Live: off';
            }

            // Update timestamp immediately and every second
            updateTimestamp();""",
)

patch(
    "modules/web_viewer/templates/base.html",
    """            setInterval(pollBanners, 10000);""",
    """            // (add-on) every 30 s and only while the page is visible (was every 10 s, also in a background tab); at once
            // when the page becomes visible again
            setInterval(function () { if (!document.hidden) pollBanners(); }, 30000);
            document.addEventListener('visibilitychange', function () { if (!document.hidden) pollBanners(); });""",
)
