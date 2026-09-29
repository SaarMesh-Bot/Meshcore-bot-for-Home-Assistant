#!/usr/bin/env python3
"""Games channel: the card for keeping the game commands in one channel (card: Plugins -> GamesChannel).

The work is done where commands are allowed or held back (see modules/games_channel.py and
local_patches/patch_games_channel.py); this service only gives the settings a card. The card is read on every
message, so a change applies at once.
"""
from typing import Any

from ..games_channel import DEFAULT_COMMANDS, settings
from .base_service import BaseServicePlugin


class GamesChannelService(BaseServicePlugin):
    config_section = "GamesChannel"
    name = "gameschannel"
    description = "Keeps the game commands (quiz, hangman, stem, ...) in one channel; XP keeps counting everywhere"

    settings_schema = [
        {"key": "channel", "label": "Games channel", "type": "str", "default": "",
         "help": ("For example #games, exactly as on your radio, and also under Bot > Channels to listen on. Empty = no "
                  "restriction: games work in every channel, as before.")},
        {"key": "commands", "label": "Game commands", "type": "list", "default": DEFAULT_COMMANDS,
         "help": ("Command names that only run in the games channel (comma-separated). Lookups such as xp, dx, badge and "
                  "topu are not on it by default, so they work everywhere. Direct messages always work.")},
        {"key": "pointer", "label": "Point to the games channel", "type": "bool", "default": False,
         "help": ("When a game command is typed in another channel, answer 'Games are played in #games' (at most once per "
                  "30 minutes per channel). Off = stay silent.")},
    ]

    def __init__(self, bot: Any):
        super().__init__(bot)

    async def start(self) -> None:
        self._running = True
        s = settings(self.bot)
        if s:
            self.logger.info("Spellenkanaal: %s voor %s", s["channel"], ", ".join(sorted(s["commands"])))

    async def stop(self) -> None:
        self._running = False
