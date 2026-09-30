#!/usr/bin/env python3
"""Source patch: ping answers without a ping keyword.

Upstream's ping only answers with the text of [Keywords] ping; without that keyword it sends nothing (the dashboard
shows "Command executed / Failed"). Since 1.1.0 new installations have no ping keyword (the reply was meant to be the
translated "Pong! More info: type test", commands.ping.response), but nothing used that text: ping stayed silent
(found 2026-09-30, BE-CTW-MOB in #test). Now a ping keyword still wins, and without one the translated text is used, in
the sender's language when AutoLanguage is on.
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
    """        if self.bot.config.has_section('Keywords'):
            format_str = self.bot.config.get('Keywords', 'ping', fallback=None)
            return self._strip_quotes_from_config(format_str) if format_str else None
        return None""",
    """        if self.bot.config.has_section('Keywords'):
            format_str = self.bot.config.get('Keywords', 'ping', fallback=None)
            if format_str:
                return self._strip_quotes_from_config(format_str)
        # (add-on) no ping keyword: the translated standard reply ("Pong! More info: type test")
        return self.translate('commands.ping.response')""",
)
