#!/usr/bin/env python3
"""
'warnung' command: the current DWD weather warnings and NINA civil-protection warnings for the area on the DEWarn card
(federal states for DWD, districts for NINA; default the Saarland), one compact line per warning.

The same data and filters as the DEWarn service, which posts new warnings by itself; this command shows what is active
right now. See modules/de_warn.py for the sources and the wording.
"""

from typing import Any

from ..models import MeshMessage
from .base_command import BaseCommand


class WarnungCommand(BaseCommand):
    """Current DWD and NINA warnings for the configured German area."""

    name = "warnung"
    keywords = ["warnung", "warnungen", "warnlage", "dwdwarnings", "ninawarnings"]
    description = "Current DWD weather and NINA warnings for the area on the DEWarn card (usage: warnung)"
    category = "general"
    requires_internet = True

    short_description = "Current DWD/NINA warnings"
    usage = "warnung"
    examples = ["warnung"]

    def __init__(self, bot: Any):
        super().__init__(bot)
        self.warnung_enabled = self.get_config_value("Warnung_Command", "enabled", fallback=True, value_type="bool")

    def can_execute(self, message: MeshMessage, skip_channel_check: bool = False) -> bool:
        if not self.warnung_enabled:
            return False
        return super().can_execute(message, skip_channel_check=skip_channel_check)

    def get_help_text(self) -> str:
        return self.translate("commands.warnung.help")

    async def execute(self, message: MeshMessage) -> bool:
        from .. import de_fetch, de_warn as W
        from ..mesh_community import local_now
        try:
            s = W.settings(self.bot.config)
            now = local_now(self.bot)
            dwd_data = await de_fetch.dwd(now)
            nina, _cancels, reached = await de_fetch.nina(s["districts"], now, s["tokens"])
            if dwd_data is None and not reached:
                return await self.send_response(message, self.translate("commands.warnung.fetch_error"))
            dwd = W.dwd_items(dwd_data, s["states"], now, s["min_level"]) if dwd_data else []
            items = W.merge(dwd, nina, s["max_dwd"])
            area = ", ".join(s["states"]) or "?"
            if not items:
                text = self.translate("commands.warnung.none", area=area)
                missing = []
                if dwd_data is None:
                    missing.append("DWD")
                if reached < len(s["districts"]):
                    missing.append(f"NINA {len(s['districts']) - reached}/{len(s['districts'])}")
                if missing:
                    text += " " + self.translate("commands.warnung.partial", sources=", ".join(missing))
                return await self.send_response(message, text)
            header = self.translate("commands.warnung.header", count=len(items))
            max_len = min(self.get_max_message_length(message), 150)
            chunks = W.split_lines(header, [i["text"] for i in items], max_len)
            return await self.send_response_chunked(message, chunks[:4])
        except Exception as e:  # noqa: BLE001
            self.logger.error(f"Error executing warnung command: {e}")
            return await self.send_response(message, self.translate("commands.warnung.error", error=str(e)))
