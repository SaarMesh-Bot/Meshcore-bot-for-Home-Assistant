#!/usr/bin/env python3
"""
'echo' command: sends back what follows the keyword (ported from the SaarMesh bot's /echo). Useful to see how a text
arrives, e.g. umlauts or emoji through a repeater chain. Capped at the channel's message length by send_response.
"""

from typing import Any

from ..models import MeshMessage
from .base_command import BaseCommand


class EchoCommand(BaseCommand):
    """Repeats the text after the keyword."""

    name = "echo"
    keywords = ["echo"]
    description = "Repeats your text (usage: echo <text>)"
    category = "general"

    short_description = "Repeats your text"
    usage = "echo <text>"
    examples = ["echo hallo mesh"]

    def __init__(self, bot: Any):
        super().__init__(bot)
        self.echo_enabled = self.get_config_value("Echo_Command", "enabled", fallback=True, value_type="bool")

    def can_execute(self, message: MeshMessage, skip_channel_check: bool = False) -> bool:
        if not self.echo_enabled:
            return False
        return super().can_execute(message, skip_channel_check=skip_channel_check)

    def get_help_text(self) -> str:
        return self.translate("commands.echo.help")

    async def execute(self, message: MeshMessage) -> bool:
        text = message.content.strip()
        rest = text[4:].strip() if text.lower().startswith("echo") else text
        return await self.send_response(message, self.translate("commands.echo.result", text=rest or self.translate("commands.echo.empty")))
