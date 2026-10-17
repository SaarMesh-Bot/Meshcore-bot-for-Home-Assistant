#!/usr/bin/env python3
"""
'odl' command: the gamma dose rate from the German federal radiation network (BfS ODL-Messnetz), the latest 1-hour
values in the area on the card (default the Saarland and its border area).

  odl              -> number of stations, median and the highest value
  odl saarburg     -> the stations whose name contains 'saarburg' (or whose postcode starts with the digits)

See modules/de_odl.py for the source. Only the data; the alarm stays with whoever runs one.
"""

from typing import Any

from ..models import MeshMessage
from .base_command import BaseCommand


class OdlCommand(BaseCommand):
    """Gamma dose rate (µSv/h) from the BfS ODL network in the configured area."""

    name = "odl"
    keywords = ["odl", "strahlung"]
    description = "Gamma dose rate from the German BfS network in the area on the card (usage: odl [place|postcode])"
    category = "general"
    requires_internet = True

    short_description = "Gamma dose rate, German BfS network"
    usage = "odl [place|postcode]"
    examples = ["odl", "odl saarburg"]

    def __init__(self, bot: Any):
        super().__init__(bot)
        from ..de_odl import DEFAULT_BBOX, parse_bbox
        self.odl_enabled = self.get_config_value("Odl_Command", "enabled", fallback=True, value_type="bool")
        self.bbox = parse_bbox(self.get_config_value("Odl_Command", "bbox", fallback=DEFAULT_BBOX) or DEFAULT_BBOX)
        self.area = (self.get_config_value("Odl_Command", "area", fallback="") or "").strip()

    def can_execute(self, message: MeshMessage, skip_channel_check: bool = False) -> bool:
        if not self.odl_enabled:
            return False
        return super().can_execute(message, skip_channel_check=skip_channel_check)

    def get_help_text(self) -> str:
        return self.translate("commands.odl.help")

    async def execute(self, message: MeshMessage) -> bool:
        from .. import de_fetch, de_odl as O
        from ..mesh_community import local_now
        try:
            arg = message.content.strip()
            low = arg.lower()
            for kw in self.keywords:
                if low.startswith(kw):
                    arg = arg[len(kw):].strip()
                    break
            now = local_now(self.bot)
            data = await de_fetch.get_json(O.WFS.format(bbox=self.bbox), timeout=20)
            sts = O.stations(data, now) if data is not None else []
            if data is None:
                return await self.send_response(message, self.translate("commands.odl.fetch_error"))
            if not sts:
                return await self.send_response(message, self.translate("commands.odl.none"))
            if arg:
                hits = O.find(sts, arg)
                if not hits:
                    return await self.send_response(message, self.translate("commands.odl.unknown", name=arg))
                parts = [f"{s['name']} {O.usv(s['value'])}" for s in hits[:4]]
                return await self.send_response(message, self.translate(
                    "commands.odl.stations", stations=" · ".join(parts), time=hits[0]["time"].strftime("%H:%M")))
            s = O.summary(sts)
            return await self.send_response(message, self.translate(
                "commands.odl.summary", area=self.area or self.translate("commands.odl.area_default"), count=s["count"],
                median=O.usv(s["median"]), max=O.usv(s["max"]), max_name=s["max_name"], time=s["time"].strftime("%H:%M")))
        except Exception as e:  # noqa: BLE001
            self.logger.error(f"Error executing odl command: {e}")
            return await self.send_response(message, self.translate("commands.odl.error", error=str(e)))
