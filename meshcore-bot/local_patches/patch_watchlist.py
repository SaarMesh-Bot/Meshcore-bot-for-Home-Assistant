#!/usr/bin/env python3
"""Source patch: react when a watched sender writes in a channel (see modules/watchlist.py, card Watchlist).

Runs once during the Docker build (see patch_webviewer.py for the shared mechanics).

One hook in message_handler.process_message(), right after the stand-in's (anchors on the lines patch_stand_in.py
added, so it runs after it): every channel message is shown to the watchlist, which works in the background (never
blocks). Only when the sender is watched with a template that ignores commands does processing stop here, after the
statistics and the greeter, before any command runs - as the handler already does for other bots.
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
    "modules/message_handler.py",
    """                self.logger.debug("StandIn failed: %s", _e)
""",
    """                self.logger.debug("StandIn failed: %s", _e)
            # A watched sender (card Watchlist): DM once per cooldown and a note to Home Assistant (modules/watchlist.py);
            # with a template that says so, the bot does not answer this sender's commands
            _wl_mute = False
            try:
                from modules.watchlist import get_watchlist
                _wl = get_watchlist(self.bot)
                _wl_mute = _wl.ignores_commands(_wl.observe(message))
            except Exception as _e:
                self.logger.debug("Watchlist failed: %s", _e)
            if _wl_mute:
                self.logger.info("Watchlist: not answering %s (template: ignore commands)", message.sender_id)
                return
""",
)
