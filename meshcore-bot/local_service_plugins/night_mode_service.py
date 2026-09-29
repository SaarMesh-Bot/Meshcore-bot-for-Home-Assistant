#!/usr/bin/env python3
"""Night mode: the card for keeping the bot's own messages quiet at night (card: Plugins -> NightMode).

The work is done where the messages leave (see modules/night_mode.py and local_patches/patch_night_mode.py); this service
only gives the settings a card and says in the log when night mode is on. The card is read on every check, so a change
applies at once; switching the whole card on or off also works without a restart.
"""
from typing import Any

from ..night_mode import window
from .base_service import BaseServicePlugin


class NightModeService(BaseServicePlugin):
    config_section = "NightMode"
    name = "nightmode"
    description = "Keeps scheduled messages, feeds and (optionally) the webhook quiet at night; answers to people always go out"

    settings_schema = [
        {"key": "start", "label": "Night starts at", "type": "str", "default": "23:00",
         "help": "Local time, HH:MM (Bot -> Time zone). The night may run past midnight."},
        {"key": "end", "label": "Night ends at", "type": "str", "default": "07:00", "help": "Local time, HH:MM."},
        {"key": "scheduled", "label": "Quiet: scheduled messages", "type": "bool", "default": True,
         "help": "Messages from the Schedule page that are due at night are skipped."},
        {"key": "feeds", "label": "Quiet: feeds", "type": "bool", "default": True,
         "help": "Feed items that come in at night are skipped, so they do not all go out in the morning."},
        {"key": "webhook", "label": "Quiet: webhook (Home Assistant -> mesh)", "type": "bool", "default": False,
         "help": "Off by default: what Home Assistant posts (alarms, P2000, ...) often matters at night too. When on, the "
                 "webhook answers 200 with {\"skipped\": \"night mode\"}."},
    ]

    def __init__(self, bot: Any):
        super().__init__(bot)

    async def start(self) -> None:
        self._running = True
        span = window(self.bot)
        if span:
            self.logger.info("Nachtstand: aan, %02d:%02d-%02d:%02d", span[0] // 60, span[0] % 60, span[1] // 60, span[1] % 60)

    async def stop(self) -> None:
        self._running = False
