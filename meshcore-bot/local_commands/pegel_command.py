#!/usr/bin/env python3
"""
'pegel' command: the current water level of a gauge with the 3-hour trend, from PEGELONLINE (federal waterways) or
the Saarland's HMD (smaller rivers). Stations are set on the card (Pegel_Command -> stations, see modules/de_pegel.py);
the default is the Saarland's: saar (Sankt Arnual), blies (Alsfassen), nied (Niedaltdorf).

  pegel          -> the default station
  pegel nied     -> a station by its alias
  pegel ?        -> the list of aliases
"""

from typing import Any

from ..models import MeshMessage
from .base_command import BaseCommand


class PegelCommand(BaseCommand):
    """Current water level of a German gauge (PEGELONLINE / Saarland HMD)."""

    name = "pegel"
    keywords = ["pegel"]
    description = "Current water level of a gauge with 3 h trend (usage: pegel [alias|?])"
    category = "general"
    requires_internet = True

    short_description = "Current water level, German gauges"
    usage = "pegel [alias|?]"
    examples = ["pegel", "pegel nied", "pegel ?"]

    def __init__(self, bot: Any):
        super().__init__(bot)
        from ..de_pegel import DEFAULT_STATIONS, parse_stations, norm
        self.pegel_enabled = self.get_config_value("Pegel_Command", "enabled", fallback=True, value_type="bool")
        self.stations = parse_stations(
            self.get_config_value("Pegel_Command", "stations", fallback=DEFAULT_STATIONS) or DEFAULT_STATIONS
        ) or parse_stations(DEFAULT_STATIONS)
        default = norm(self.get_config_value("Pegel_Command", "default", fallback="") or "")
        self.default = default if default in self.stations else next(iter(self.stations))

    def can_execute(self, message: MeshMessage, skip_channel_check: bool = False) -> bool:
        if not self.pegel_enabled:
            return False
        return super().can_execute(message, skip_channel_check=skip_channel_check)

    def get_help_text(self) -> str:
        return self.translate("commands.pegel.help", stations=", ".join(self.stations))

    async def execute(self, message: MeshMessage) -> bool:
        from .. import de_fetch, de_pegel as P
        from ..mesh_community import local_now
        try:
            arg = message.content.strip()
            low = arg.lower()
            for kw in self.keywords:
                if low.startswith(kw):
                    arg = arg[len(kw):].strip()
                    break
            if arg in ("?", "liste", "list", "help", "hilfe"):
                return await self.send_response(
                    message, self.translate("commands.pegel.list", stations=", ".join(
                        f"{k} ({v['label']})" for k, v in self.stations.items())))
            key = P.norm(arg) if arg else self.default
            st = self.stations.get(key)
            if st is None:
                return await self.send_response(message, self.translate("commands.pegel.unknown", name=arg))

            now = local_now(self.bot)
            if st["source"] == "hmd":
                cur = P.hmd_current(await de_fetch.hmd_series(st["id"], now.tzinfo))
            else:
                station = await de_fetch.pegelonline_station(st["id"])
                cur = P.po_current(station, now.tzinfo)
                if cur:
                    cur["trend_cm"] = P.po_trend(await de_fetch.pegelonline_history(st["id"], 3))
            if not cur:
                return await self.send_response(message, self.translate("commands.pegel.fetch_error", station=st["label"]))

            t = cur.get("time")
            response = self.translate(
                "commands.pegel.result", station=st["label"], value=P.metres(cur["value_cm"]),
                trend=P.trend_text(cur.get("trend_cm")), time=t.strftime("%H:%M") if t else "?")
            if not P.fresh(t, now):
                response += " " + self.translate("commands.pegel.stale")
            return await self.send_response(message, response)
        except Exception as e:  # noqa: BLE001
            self.logger.error(f"Error executing pegel command: {e}")
            return await self.send_response(message, self.translate("commands.pegel.error", error=str(e)))
