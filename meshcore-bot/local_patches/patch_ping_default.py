#!/usr/bin/env python3
"""Source patch: ping answers without a ping keyword.

Upstream's ping only answers with the text of [Keywords] ping; without that keyword it sends nothing (the dashboard
shows "Command executed / Failed"). Since 1.1.0 new installations have no ping keyword (the reply was meant to be the
translated "Pong! More info: type test", commands.ping.response), but nothing used that text: ping stayed silent
(found 2026-09-30 in #test). Now a ping keyword still wins, and without one the translated text is used, in
the sender's language when AutoLanguage is on.

Since 2.51.2 the reply without a keyword tells more: "Pong @[Jan]! 3 hops via <repeater> · SNR 6.5 dB · RSSI -92 dBm ·
1.2s onderweg · 07:01" (modules/ping_info.py; unknown parts are left out).
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
    "modules/commands/ping_command.py",
    """        return await self.handle_keyword_match(message)""",
    """        if self.get_response_format():
            return await self.handle_keyword_match(message)
        # (add-on) no ping keyword: Pong with hops, the repeater it came via, SNR, RSSI, travel time (modules/ping_info.py)
        from ..ping_info import reply
        return await self.send_response(message, reply(self, message))""",
)
