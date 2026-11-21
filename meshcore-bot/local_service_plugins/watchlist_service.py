#!/usr/bin/env python3
"""Settings card for the watchlist ([Watchlist]), on the dashboard's Plugins page.

The watchlist itself is one shared object hooked into the message handler (modules/watchlist.py,
patch_watchlist.py): when a watched sender writes in a channel, it gets one DM per cooldown and Home Assistant
(e.g. Telegram) is told. This service only gives it a card with typed fields; it does nothing at run time.
Changes apply within about 30 seconds without a restart.
"""

from typing import Any

from .base_service import BaseServicePlugin


class WatchlistService(BaseServicePlugin):
    """Card only; the work is done by modules/watchlist.py."""

    config_section = "Watchlist"
    name = "watchlist"
    description = "Watched senders: a DM once per cooldown and a note to Home Assistant when they write in a channel"

    settings_schema = [
        {"key": "targets", "label": "Watched senders", "type": "list", "default": [],
         "help": ("Comma-separated. 'Name' or 'Name=public key' (64 hex characters). The name matches "
                  "case-insensitively as part of the sender name. A channel message carries no public key: give it "
                  "here so the DM can be sent (the bot adds the key as a contact when needed).")},
        {"key": "channels", "label": "Channels to listen to", "type": "list", "default": [],
         "help": "Empty = every channel. Comma-separated, name exactly as on your radio."},
        {"key": "message_dm", "label": "Text of the DM", "type": "str", "default": "",
         "help": "Empty = a standard text. {sender} becomes the name. At most 158 bytes. Nothing goes in the channel."},
        {"key": "dm_cooldown_hours", "label": "At most one DM per sender every", "type": "int", "default": 24,
         "min": 0, "max": 8760, "unit": "h",
         "help": "Kept in the bot's database, so a restart does not start over. 0 = a DM on every message."},
        {"key": "delay_seconds", "label": "Wait before the DM", "type": "int", "default": 15,
         "min": 0, "max": 600, "unit": "s",
         "help": "Plus a random extra of up to 5 seconds, so the DM does not collide with the repeats of their message."},
        {"key": "notify", "label": "Tell Home Assistant", "type": "bool", "default": True,
         "help": "On every message of a watched sender: sender, channel, text, hops and what happened with the DM."},
        {"key": "ha_notify_service", "label": "Home Assistant service", "type": "str",
         "default": "telegram_bot.send_message",
         "help": "e.g. telegram_bot.send_message or notify.mobile_app_myphone. Called with title and message."},
    ]

    def __init__(self, bot: Any):
        super().__init__(bot)

    async def start(self) -> None:
        self._running = True

    async def stop(self) -> None:
        self._running = False
