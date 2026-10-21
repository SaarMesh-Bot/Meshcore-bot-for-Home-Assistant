#!/usr/bin/env python3
"""
'vorhersage' command: a short hourly forecast (Open-Meteo, no key), ported from the SaarMesh bot's /vorhersage.

  vorhersage               next 6 h where you are (your advert position), else at the bot's location
  vorhersage 12            next 12 h (1..48)
  vorhersage 66117         a postcode
  vorhersage Trier 12      a place and the hours, in any order

See modules/de_forecast.py for the format. 'wx'/'wetter' stays the command for the current weather and day forecasts.
"""

import asyncio
from typing import Any, Optional

from ..models import MeshMessage
from .base_command import BaseCommand


class VorhersageCommand(BaseCommand):
    """Short hourly forecast for a place, a postcode or the sender's position."""

    name = "vorhersage"
    keywords = ["vorhersage", "forecast", "prognose"]
    description = "Hourly forecast (usage: vorhersage [place|postcode] [hours])"
    category = "general"
    requires_internet = True

    short_description = "Hourly forecast, place or postcode"
    usage = "vorhersage [place|postcode] [hours]"
    examples = ["vorhersage", "vorhersage 12", "vorhersage 66117", "vorhersage Trier 24"]

    def __init__(self, bot: Any):
        super().__init__(bot)
        self.vorhersage_enabled = self.get_config_value("Vorhersage_Command", "enabled", fallback=True, value_type="bool")

    def can_execute(self, message: MeshMessage, skip_channel_check: bool = False) -> bool:
        if not self.vorhersage_enabled:
            return False
        return super().can_execute(message, skip_channel_check=skip_channel_check)

    def get_help_text(self) -> str:
        return self.translate("commands.vorhersage.help")

    # ------------------------------------------------------------ locations
    def _sender_location(self, message: MeshMessage) -> Optional[tuple]:
        key = getattr(message, "sender_pubkey", None)
        if not key:
            return None
        try:
            rows = self.bot.db_manager.execute_query(
                """SELECT latitude, longitude FROM complete_contact_tracking
                   WHERE public_key = ? AND latitude IS NOT NULL AND longitude IS NOT NULL
                   AND latitude != 0 AND longitude != 0
                   ORDER BY COALESCE(last_advert_timestamp, last_heard) DESC LIMIT 1""", (key,))
        except Exception as e:  # noqa: BLE001
            self.logger.debug(f"vorhersage: no sender location ({e})")
            return None
        if rows:
            return float(rows[0]["latitude"]), float(rows[0]["longitude"])
        return None

    def _bot_location(self) -> Optional[tuple]:
        try:
            lat = self.bot.config.getfloat("Bot", "bot_latitude", fallback=None)
            lon = self.bot.config.getfloat("Bot", "bot_longitude", fallback=None)
        except ValueError:
            return None
        if lat is None or lon is None or not (-90 <= lat <= 90 and -180 <= lon <= 180):
            return None
        return lat, lon

    async def _geocode(self, place: str) -> Optional[tuple]:
        from .. import de_forecast as F
        from ..utils import geocode_city_sync, geocode_zipcode_sync
        country = self.bot.config.get("Weather", "default_country", fallback="DE")
        try:
            if F.is_plz(place):
                lat, lon = await asyncio.to_thread(geocode_zipcode_sync, self.bot, place.strip(), country, 10)
            else:
                lat, lon, _ = await asyncio.to_thread(geocode_city_sync, self.bot, place, None, country, False, 10)
        except Exception as e:  # noqa: BLE001
            self.logger.warning(f"vorhersage: geocoding '{place}' failed: {e}")
            return None
        if lat is None or lon is None:
            return None
        return float(lat), float(lon)

    # ------------------------------------------------------------ run
    async def execute(self, message: MeshMessage) -> bool:
        from .. import de_fetch, de_forecast as F
        from ..mesh_community import local_now
        try:
            arg = message.content.strip()
            low = arg.lower()
            for kw in sorted(self.keywords, key=len, reverse=True):
                if low == kw or low.startswith(kw + " "):
                    arg = arg[len(kw):].strip()
                    break
            if arg in ("?", "hilfe", "help"):
                return await self.send_response(message, self.get_help_text())
            hours, place = F.parse_args(arg)

            if place:
                loc = await self._geocode(place)
                if loc is None:
                    return await self.send_response(message, self.translate("commands.vorhersage.not_found", place=place))
                name = (F.plz_name(place) or place) if F.is_plz(place) else place
            else:
                loc, name = self._sender_location(message), self.translate("commands.vorhersage.here")
                if loc is None:
                    loc, name = self._bot_location(), self.translate("commands.vorhersage.bot_location")
                if loc is None:
                    return await self.send_response(message, self.get_help_text())

            now = local_now(self.bot)
            tz = getattr(now.tzinfo, "key", None) or self.bot.config.get("Bot", "timezone", fallback="") or "Europe/Berlin"
            data = await de_fetch.open_meteo_hourly(loc[0], loc[1], hours, tz)
            rows = F.rows(data, hours, now) if data else []
            if not rows:
                return await self.send_response(message, self.translate("commands.vorhersage.fetch_error"))
            head = self.translate("commands.vorhersage.head", place=name, hours=hours)
            return await self.send_response(message, "\n".join([head] + [F.line(*r) for r in rows]))
        except Exception as e:  # noqa: BLE001
            self.logger.error(f"Error executing vorhersage command: {e}")
            return await self.send_response(message, self.translate("commands.vorhersage.error", error=str(e)))
