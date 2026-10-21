#!/usr/bin/env python3
"""
'zeit' command: the bot's local date and time (the bot's time zone, see [Bot] timezone). Ported from the SaarMesh
bot's /zeit - handy to check a node's clock against.
"""

from typing import Any

from ..models import MeshMessage
from .base_command import BaseCommand


class ZeitCommand(BaseCommand):
    """The bot's local date and time."""

    name = "zeit"
    keywords = ["zeit", "uhrzeit", "time"]
    description = "The bot's local date and time"
    category = "general"

    short_description = "Date and time"
    usage = "zeit"
    examples = ["zeit"]

    def __init__(self, bot: Any):
        super().__init__(bot)
        self.zeit_enabled = self.get_config_value("Zeit_Command", "enabled", fallback=True, value_type="bool")

    def can_execute(self, message: MeshMessage, skip_channel_check: bool = False) -> bool:
        if not self.zeit_enabled:
            return False
        return super().can_execute(message, skip_channel_check=skip_channel_check)

    def get_help_text(self) -> str:
        return self.translate("commands.zeit.help")

    async def execute(self, message: MeshMessage) -> bool:
        from ..mesh_community import local_now
        now = local_now(self.bot)
        return await self.send_response(message, self.translate(
            "commands.zeit.result", date=now.strftime("%d.%m.%Y"), time=now.strftime("%H:%M:%S"),
            tz=now.tzname() or ""))
