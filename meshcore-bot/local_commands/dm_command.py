#!/usr/bin/env python3
"""
'dm' command for the MeshCore Bot: typed in a channel, the bot sends the asker a direct message, so they can use the
bot privately from then on (all commands work in a DM).

  dm      in a channel: the bot sends you a DM ("Hi {name}, send your commands here; help gives the list")

MeshCore limits: a channel message carries only the sender's name, no key. The bot looks that name up in the radio's
contacts; when the person is not (or no longer) there, the DM cannot be sent and the bot says so in the channel, with
the tip to send an advert. The person also needs the bot as a contact, or their app cannot read the DM: the DM itself
says so. At most one DM per person per "Wait per person" minutes (card), so the command cannot be used to flood.
"""

import time
from typing import Any

from ..mesh_community import fit_bytes, own_name
from ..models import MeshMessage
from .base_command import BaseCommand


class DmCommand(BaseCommand):
    """Starts a private conversation: the bot sends a DM to whoever typed 'dm' in a channel."""

    name = "dm"
    keywords = ["dm"]
    description = "Typed in a channel: the bot sends you a direct message, so you can use it privately from then on"
    category = "basic"

    short_description = "Get a DM from the bot, to use it privately"
    usage = "dm"
    examples = ["dm"]

    settings_schema = [
        {"key": "text", "label": "Text of the DM", "type": "str", "default": "",
         "help": ("Empty = a standard text in the bot's language. {name} becomes the person's name, {bot} the bot's name. "
                  "Keep it short: one mesh message.")},
        {"key": "cooldown_minutes", "label": "Wait per person", "type": "int", "default": 10,
         "help": "Minutes before the same person gets another DM from this command (1-1440)."},
    ]

    def __init__(self, bot: Any):
        super().__init__(bot)
        self.dm_enabled = self.get_config_value("Dm_Command", "enabled", fallback=True, value_type="bool")
        self.text = (self.get_config_value("Dm_Command", "text", fallback="") or "").strip()
        try:
            minutes = int(self.get_config_value("Dm_Command", "cooldown_minutes", fallback=10) or 10)
        except (TypeError, ValueError):
            minutes = 10
        self.cooldown_s = max(1, min(1440, minutes)) * 60
        self._last: dict = {}   # name -> when the last DM went out

    def can_execute(self, message: MeshMessage, skip_channel_check: bool = False) -> bool:
        if not self.dm_enabled:
            return False
        return super().can_execute(message, skip_channel_check=skip_channel_check)

    def get_help_text(self) -> str:
        return self.translate("commands.dm.help")

    def dm_text(self, name: str, max_bytes: int) -> str:
        bot = own_name(self.bot)
        if self.text:
            return fit_bytes(self.text.replace("{name}", name).replace("{bot}", bot), max_bytes)
        return fit_bytes(self.translate("commands.dm.hello", name=name, bot=bot), max_bytes)

    async def execute(self, message: MeshMessage, now: float = None) -> bool:
        try:
            if message.is_dm:
                return await self.send_response(message, self.translate("commands.dm.already"))
            name = (message.sender_id or "").strip()
            if not name:
                return False
            now = time.time() if now is None else now
            key = name.lower()
            last = self._last.get(key)
            if last is not None and now - last < self.cooldown_s:
                self.logger.info(f"dm: {name} kreeg kortgeleden al een DM, niets gestuurd")
                return True
            recipient = getattr(message, "sender_pubkey", None) or name
            ok = False
            try:
                ok = await self.bot.command_manager.send_dm(recipient, self.dm_text(name, self.get_max_message_length(message)))
            except Exception as e:  # noqa: BLE001
                self.logger.debug(f"dm: DM to {name} failed: {e}")
            if ok:
                self._last[key] = now
                return True
            self.logger.info(f"dm: {name} staat niet in de contacten van de radio, uitleg in het kanaal")
            return await self.send_response(message, self.translate("commands.dm.unknown", name=name))
        except Exception as e:  # noqa: BLE001
            self.logger.error(f"Error executing dm command: {e}")
            return await self.send_response(message, self.translate("commands.dm.error", error=str(e)))
