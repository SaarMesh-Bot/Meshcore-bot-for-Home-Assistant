#!/usr/bin/env python3
"""
'feestdag' command for the MeshCore Bot.
Reports today's (or tomorrow's) official public holidays, via the free Nager.Date API (no key required).

The countries come from the card (Feestdag_Command -> countries, default NL,BE; e.g. DE,FR,LU for SaarLorLux).
Holidays that only hold in part of a country (the API lists them with their counties, e.g. DE-SL) are shown only
when one of those regions is on the card (regions, e.g. DE-SL); with no regions on the card every holiday counts,
as before.
"""

import time
from datetime import date, timedelta
from typing import Any

import aiohttp

from ..models import MeshMessage
from .base_command import BaseCommand

_API_URL = "https://date.nager.at/api/v3/PublicHolidays/{year}/{country}"
_DEFAULT_COUNTRIES = "NL,BE"
_CACHE_TTL_SECONDS = 24 * 60 * 60


class FeestdagCommand(BaseCommand):
    """Reports today's/tomorrow's official BE/NL public holidays."""

    name = "feestdag"
    keywords = ["feiertag", "feiertage", "feestdag", "vandaag"]
    description = "Public holidays of the countries on the card (usage: feestdag, feestdag morgen)"
    category = "general"
    requires_internet = True

    short_description = "Public holidays today/tomorrow"
    usage = "feestdag [morgen]"
    examples = ["feestdag", "feestdag morgen"]

    def __init__(self, bot: Any):
        super().__init__(bot)
        self.feestdag_enabled = self.get_config_value(
            "Feestdag_Command", "enabled", fallback=True, value_type="bool"
        )
        raw = self.get_config_value("Feestdag_Command", "countries", fallback=_DEFAULT_COUNTRIES) or _DEFAULT_COUNTRIES
        self.countries = [c.strip().upper() for c in raw.replace(";", ",").split(",") if c.strip()] or ["NL", "BE"]
        regions = self.get_config_value("Feestdag_Command", "regions", fallback="") or ""
        self.regions = {r.strip().upper() for r in regions.replace(";", ",").split(",") if r.strip()}
        # (year -> {country: [holiday dicts]}) cache, refreshed once a day.
        self._cache: dict[int, dict[str, list[dict]]] = {}
        self._cache_fetched_at: dict[int, float] = {}

    def can_execute(self, message: MeshMessage, skip_channel_check: bool = False) -> bool:
        if not self.feestdag_enabled:
            return False
        return super().can_execute(message, skip_channel_check=skip_channel_check)

    def get_help_text(self) -> str:
        return self.translate("commands.feestdag.help", countries="/".join(self.countries))

    async def _get_holidays_for_year(self, year: int) -> dict[str, list[dict]]:
        cached_at = self._cache_fetched_at.get(year, 0)
        if year in self._cache and (time.time() - cached_at) < _CACHE_TTL_SECONDS:
            return self._cache[year]

        result: dict[str, list[dict]] = {}
        async with aiohttp.ClientSession() as session:
            for country in self.countries:
                url = _API_URL.format(year=year, country=country)
                try:
                    async with session.get(url, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                        if resp.status == 200:
                            result[country] = await resp.json()
                        else:
                            result[country] = []
                except Exception as e:
                    self.logger.warning(f"feestdag: kon {country} {year} niet ophalen: {e}")
                    result[country] = []

        self._cache[year] = result
        self._cache_fetched_at[year] = time.time()
        return result

    @staticmethod
    def _holidays_on(holidays_by_country: dict[str, list[dict]], target: date,
                     regions: set | None = None) -> list[tuple[str, str]]:
        target_str = target.isoformat()
        found = []
        for country, holidays in holidays_by_country.items():
            for holiday in holidays:
                counties = holiday.get("counties") or []
                if regions and counties and not holiday.get("global", True) and not regions & set(counties):
                    continue
                if holiday.get("date") == target_str:
                    found.append((country, holiday.get("localName") or holiday.get("name") or "?"))
        return found

    async def execute(self, message: MeshMessage) -> bool:
        try:
            content = message.content.strip().lower()
            target = date.today()
            label = self.translate("commands.feestdag.today")
            if "morgen" in content:
                target = target + timedelta(days=1)
                label = self.translate("commands.feestdag.tomorrow")

            holidays_by_country = await self._get_holidays_for_year(target.year)
            found = self._holidays_on(holidays_by_country, target, self.regions)

            date_str = target.strftime(self.translate("commands.feestdag.date_format"))
            if not found:
                response = self.translate("commands.feestdag.none", label=label, date=date_str,
                                          countries="/".join(self.countries))
            else:
                # Dedupe identical holiday names shared by both countries.
                by_name: dict[str, list[str]] = {}
                for country, name in found:
                    by_name.setdefault(name, []).append(country)
                lines = [self.translate("commands.feestdag.header", label=label, date=date_str)]
                for name, countries in by_name.items():
                    lines.append(f"{name} ({'/'.join(countries)})")
                response = " | ".join(lines)

            return await self.send_response(message, response)
        except Exception as e:
            self.logger.error(f"Error executing feestdag command: {e}")
            return await self.send_response(message, self.translate("commands.feestdag.error", error=str(e)))
