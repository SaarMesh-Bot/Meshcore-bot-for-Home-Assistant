#!/usr/bin/env python3
"""Source patch: tip for people who send with a 1-byte path hash (see modules/hash_hint.py, card HashHint).

Runs once during the Docker build (see patch_webviewer.py for the shared mechanics).

One hook in message_handler.process_message(), next to the channel hint's (anchors on the lines
patch_channel_hint.py added, so it runs after it): every channel message is shown to the hash hint, which only
schedules a tip in the background (never blocks, never stops the message from being processed further).
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
    """            _hint.note_message(message)   # remember that another bot spoke here
""",
    """            _hint.note_message(message)   # remember that another bot spoke here
            # 1-byte path hash in a watched channel: a tip that 2 bytes is better (modules/hash_hint.py)
            try:
                from modules.hash_hint import get_hash_hint
                get_hash_hint(self.bot).observe(message)
            except Exception as _e:
                self.logger.debug("HashHint failed: %s", _e)
""",
)
