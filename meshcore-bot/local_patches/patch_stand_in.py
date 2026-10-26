#!/usr/bin/env python3
"""Source patch: stand in for an old bot that is switched off (see modules/stand_in.py, card StandIn).

Runs once during the Docker build (see patch_webviewer.py for the shared mechanics).

One hook in message_handler.process_message(), right after the hash hint's (anchors on the lines patch_hash_hint.py
added, so it runs after it) and before the bot checks and the hint channels: a channel message that mentions the old
bot gets a short note ("the old bot is on holiday, I'm standing in") and its mention is turned into one of this bot,
so the command in it is then handled normally.
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
    """                self.logger.debug("HashHint failed: %s", _e)
""",
    """                self.logger.debug("HashHint failed: %s", _e)
            # A message to the old, switched-off bot: a note that this bot stands in, then the command runs here
            try:
                from modules.stand_in import get_stand_in
                await get_stand_in(self.bot).handle(message)
            except Exception as _e:
                self.logger.debug("StandIn failed: %s", _e)
""",
)
