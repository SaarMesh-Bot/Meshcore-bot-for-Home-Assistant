#!/usr/bin/env python3
"""Source patch: `help` in a channel with its own commands (such as #f1) lists only those commands.

Runs once during the Docker build (see patch_webviewer.py for the shared mechanics).

Upstream's help keyword path gives up when the help command is not allowed in the channel. In #f1 (only `f1` works
there) `help` then got the channel hint "that command does not work here". Now it answers with the help of the
commands that have that channel on their own card; see local_shared/channel_help.py. The help response also stops the
command loop, so no hint follows.
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
    "modules/command_manager.py",
    """                            if not help_command.is_channel_allowed(message):
                                break  # Not allowed in this channel, skip help keyword""",
    """                            if not help_command.is_channel_allowed(message):
                                # A channel with its own commands (such as #f1): help lists only those
                                try:
                                    from modules.channel_help import channel_help_text
                                    _channel_help = channel_help_text(self, message)
                                except Exception as _e:
                                    self.logger.debug("Channel help failed: %s", _e)
                                    _channel_help = ""
                                if _channel_help:
                                    matches.append(('help', _channel_help))
                                    return matches
                                break  # Not allowed in this channel, skip help keyword""",
)
