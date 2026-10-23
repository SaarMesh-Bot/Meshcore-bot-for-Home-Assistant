#!/usr/bin/env python3
"""Settings card for the path hash hint ([HashHint]), on the dashboard's Plugins page.

The hint itself is one shared object hooked into the message handler (modules/hash_hint.py, patch_hash_hint.py):
someone who sends with a 1-byte path hash in a watched channel (e.g. Public) gets a short tip that 2 bytes is better.
This service only gives it a card with typed fields; it does nothing at run time. Changes apply within about
30 seconds without a restart.
"""

from typing import Any

from .base_service import BaseServicePlugin


class HashHintService(BaseServicePlugin):
    """Card only; the work is done by modules/hash_hint.py."""

    config_section = "HashHint"
    name = "hashhint"
    description = "Tip for people who send with a 1-byte path hash: 2 bytes per hop is better (once per person)"

    settings_schema = [
        {"key": "channels", "label": "Channels to listen to", "type": "list", "default": ["Public"],
         "help": "Messages in these channels are checked. Comma-separated, name exactly as on your radio."},
        {"key": "via", "label": "Send the tip as", "type": "enum", "default": "dm",
         "options": [{"value": "dm", "label": "A direct message to the sender"},
                     {"value": "channel", "label": "A message in the channel"}],
         "help": ("A DM reaches only that person and keeps the channel quiet. It needs the person among the radio's "
                  "contacts (and the bot in theirs to read it).")},
        {"key": "dm_fallback", "label": "When the DM cannot be sent", "type": "enum", "default": "channel",
         "options": [{"value": "channel", "label": "Send the tip in the channel after all"},
                     {"value": "none", "label": "Send nothing"}],
         "help": "Only with 'Send the tip as' = DM. The person counts as having had the tip either way."},
        {"key": "message_dm", "label": "Text of the DM", "type": "str", "default": "",
         "help": "Empty = a standard text in the bot's language. {sender} becomes the name. At most 158 bytes."},
        {"key": "message_channel", "label": "Text in the channel", "type": "str", "default": "",
         "help": "Empty = a standard text in the bot's language. {sender} becomes the name. Keep it short (about 120 bytes)."},
        {"key": "repeat_days", "label": "Tip the same person again after", "type": "int", "default": 30,
         "min": 1, "max": 3650, "unit": "days",
         "help": "Who got a tip is kept in the bot's database, so a restart does not start over."},
        {"key": "channel_cooldown_minutes", "label": "At most one tip in the channel every", "type": "int",
         "default": 10, "min": 0, "max": 1440, "unit": "min",
         "help": "Only for tips sent in the channel. Someone skipped because of this gets the tip another time."},
        {"key": "delay_seconds", "label": "Wait before sending", "type": "int", "default": 20,
         "min": 0, "max": 600, "unit": "s",
         "help": "Plus a random extra of up to 10 seconds, so the tip does not collide with the repeats of their message."},
        {"key": "max_hops", "label": "Only senders within this many hops", "type": "int", "default": 0,
         "min": 0, "max": 63,
         "help": "0 = any distance. A small number keeps the tips to people near the bot."},
        {"key": "skip_bots", "label": "No tips for other bots", "type": "bool", "default": True,
         "help": "Bots are recognised as for the channel hint (robot emoji, the word bot, the dashboard's Bots page)."},
    ]

    def __init__(self, bot: Any):
        super().__init__(bot)

    async def start(self) -> None:
        self._running = True

    async def stop(self) -> None:
        self._running = False
