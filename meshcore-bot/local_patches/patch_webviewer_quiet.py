#!/usr/bin/env python3
"""Source patch: two web viewer annoyances.

1. Every update or restart logged "Web viewer process exited unexpectedly (code -15) — attempting restart" (found
   2026-10-01 on the Problems page): the dashboard process gets the stop signal (SIGTERM, -15) a moment before the bot
   marks its own shutdown. A stop signal now waits two seconds for the bot's shutdown and is then logged as info
   (when the bot itself keeps running, the dashboard is started again, also logged as info); other exit codes are still
   warned about and restarted.
2. Live events (packets, commands, messages, mesh changes, log lines) were broadcast to every open dashboard page as
   soon as one page (for example Realtime) subscribed; pages like Radar and Games got every radio packet for nothing,
   which made them sluggish over remote desktop. Now they go only to the pages that subscribed.
"""
import pathlib
import sys

ROOT = pathlib.Path.cwd()


def patch(path: str, old: str, new: str, count_expected: int = 1) -> None:
    p = ROOT / path
    text = p.read_text()
    count = text.count(old)
    if count != count_expected:
        sys.exit(
            f"PATCH FAILED - anchor text found {count} time(s) in {path} "
            f"(expected {count_expected}; upstream code likely changed):\n{old!r}"
        )
    p.write_text(text.replace(old, new))
    print(f"Patched {path}")


patch(
    "modules/web_viewer/integration.py",
    """            if self.running and self.viewer_process and self.viewer_process.poll() is not None:
                if (""",
    """            if self.running and self.viewer_process and self.viewer_process.poll() is not None:
                # (add-on) a stop signal (SIGTERM/SIGINT): the add-on is stopping; give the bot a moment to say so
                if self.viewer_process.returncode in (-15, -2, 143, 130):
                    for _ in range(20):
                        if self.shutting_down or self.bot._shutdown_event.is_set():
                            break
                        time.sleep(0.1)
                    if self.shutting_down or self.bot._shutdown_event.is_set():
                        self.logger.info("Web viewer stopped (stop signal, code %s)", self.viewer_process.returncode)
                        return
                    self.logger.info("Web viewer stopped by a signal (code %s), starting it again", self.viewer_process.returncode)
                    self.restart_viewer()
                    return
                if (""",
)

for event, flag in (("'command_data', command_data", "subscribed_commands"), ("'packet_data', packet_data", "subscribed_packets"),
                    ("'mesh_node_added', node_data", "subscribed_mesh"), ("'message_data', msg_data", "subscribed_messages")):
    patch(
        "modules/web_viewer/app.py",
        f"""                self.socketio.emit({event}, room=None)""",
        f"""                for _sid in subscribed_clients:   # (add-on) only the pages that subscribed, not every open page
                    self.socketio.emit({event}, to=_sid)""",
    )

patch(
    "modules/web_viewer/app.py",
    """                self.socketio.emit(event_type, edge_data, room=None)""",
    """                for _sid in subscribed_clients:   # (add-on) only the pages that subscribed
                    self.socketio.emit(event_type, edge_data, to=_sid)""",
)

patch(
    "modules/web_viewer/app.py",
    """                self.socketio.emit(
                    'log_line', {'line': _strip_ansi_codes(line.rstrip())}, room=None
                )""",
    """                for _sid in subscribed:   # (add-on) only the pages that subscribed
                    self.socketio.emit('log_line', {'line': _strip_ansi_codes(line.rstrip())}, to=_sid)""",
)
