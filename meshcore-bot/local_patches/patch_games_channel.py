#!/usr/bin/env python3
"""Source patch: the games channel (see modules/games_channel.py; card Plugins -> GamesChannel).

Runs once during the Docker build (see patch_webviewer.py for the shared mechanics). Runs after patch_channel_hint.py:
it anchors on the lines that patch added to command_manager.

1. BaseCommand.is_channel_allowed(): a command on the games list runs only in the games channel (direct messages
   always work); games_verdict() returns None when the games channel does not apply, and then nothing changes.
2. CommandManager.execute_commands(): a game command held back outside the games channel answers with a pointer to it
   when that is switched on (instead of the general channel hint).
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
    "modules/commands/base_command.py",
    """        # DMs are always allowed (unless requires_dm is False, but that's checked separately)
        if message.is_dm:
            return True
""",
    """        # DMs are always allowed (unless requires_dm is False, but that's checked separately)
        if message.is_dm:
            return True

        # Games channel (card GamesChannel): a game command runs only there.
        try:
            from modules.games_channel import games_verdict
            _games = games_verdict(self, message)
            if _games is not None:
                return _games
        except Exception:  # never block a command because of the games channel
            pass
""",
)

patch(
    "modules/command_manager.py",
    """            if not command.is_channel_allowed(message):
                if not message.is_dm:
                    try:
                        from modules.channel_hint import get_channel_hint""",
    """            if not command.is_channel_allowed(message):
                if not message.is_dm:
                    try:
                        from modules.games_channel import held_back, send_pointer
                        if held_back(command, message):
                            if command.matches_keyword(message):
                                await send_pointer(self.bot, message)
                            continue
                    except Exception as _e:
                        self.logger.debug("Games channel pointer failed: %s", _e)
                    try:
                        from modules.channel_hint import get_channel_hint""",
)
