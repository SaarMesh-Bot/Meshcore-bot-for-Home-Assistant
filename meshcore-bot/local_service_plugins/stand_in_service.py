#!/usr/bin/env python3
"""Settings card for the stand-in ([StandIn]), on the dashboard's Plugins page.

The work is done by one shared object hooked into the message handler (modules/stand_in.py, patch_stand_in.py):
someone who writes "@[OldBot] ..." in a channel gets a note that this bot stands in for it, and the command runs here.
This service only gives it a card with typed fields; it does nothing at run time. Changes apply within about
30 seconds without a restart.
"""

from typing import Any

from .base_service import BaseServicePlugin


class StandInService(BaseServicePlugin):
    """Card only; the work is done by modules/stand_in.py."""

    config_section = "StandIn"
    name = "standin"
    description = "Stand in for an old bot that is switched off: a note to people who still write to it, then the answer"

    settings_schema = [
        {"key": "names", "label": "Names of the old bot", "type": "list", "default": ["SaarMesh-Bot"],
         "help": "As in @[...] in a message. Comma-separated, case does not matter."},
        {"key": "message", "label": "Text of the note", "type": "str", "default": "",
         "help": "Empty = a standard text in the bot's language. {sender} = the name, {old} = the old bot's name."},
        {"key": "answer", "label": "Then answer the command myself", "type": "bool", "default": True,
         "help": "\"@[OldBot] /path\" is handled as if it was sent to this bot."},
        {"key": "repeat_hours", "label": "The same person gets the note again after", "type": "int", "default": 12,
         "min": 0, "max": 8760, "unit": "h", "help": "0 = every time. Kept in the bot's database."},
        {"key": "channel_cooldown_minutes", "label": "At most one note per channel every", "type": "int",
         "default": 2, "min": 0, "max": 1440, "unit": "min"},
        {"key": "skip_bots", "label": "Ignore other bots", "type": "bool", "default": True},
    ]

    def __init__(self, bot: Any):
        super().__init__(bot)

    async def start(self) -> None:
        self._running = True

    async def stop(self) -> None:
        self._running = False
