#!/usr/bin/env python3
"""AutoChannels: hashtag channels the bot is set to use but that are missing on the radio are made there (see
modules/channel_autocreate.py). Card: Plugins -> AutoChannels, on by default.

Also stores the position the radio advertises (bot_metadata "radio.position") for the Repeater radar's distances.
Checks 2 minutes after the start (after the channel scan and the first channel checks) and then every hour; a check
costs no radio traffic when nothing is missing.
"""
import asyncio
from typing import Any, Optional

from ..channel_autocreate import ensure_channels, wanted_channels
from .base_service import BaseServicePlugin

FIRST_S = 120
EVERY_S = 3600


class AutoChannelsService(BaseServicePlugin):
    config_section = "AutoChannels"
    name = "autochannels"
    description = ("Makes missing hashtag channels on the radio (#test, #games, #f1, ...) that the bot is set to use; "
                   "private channels and removals never")

    settings_schema: list = []

    def __init__(self, bot: Any):
        super().__init__(bot)
        self._task: Optional[asyncio.Task] = None

    async def start(self) -> None:
        self._running = True
        self._remember_position()
        cfg = self.bot.config
        if not (cfg.has_section("AutoChannels") and cfg.getboolean("AutoChannels", "enabled", fallback=False)):
            return
        self._task = asyncio.get_running_loop().create_task(self._loop())
        self.logger.info("Kanalen: controle op ontbrekende hashtag-kanalen aan (%s)", ", ".join(wanted_channels(self.bot)) or "geen")

    def _remember_position(self) -> None:
        """The position the radio advertises, for the dashboard (Repeater radar distances); kept in bot_metadata."""
        try:
            import json
            info = getattr(getattr(self.bot, "meshcore", None), "self_info", None) or {}
            lat, lon = info.get("adv_lat"), info.get("adv_lon")
            if lat and lon:
                self.bot.db_manager.set_metadata("radio.position", json.dumps({"lat": lat, "lon": lon}))
        except Exception as e:  # noqa: BLE001
            self.logger.debug("Kanalen: positie van de radio niet bewaard: %s", e)

    async def stop(self) -> None:
        self._running = False
        if self._task is not None:
            self._task.cancel()
            self._task = None

    async def _loop(self) -> None:
        await asyncio.sleep(FIRST_S)
        while self._running:
            try:
                if getattr(self.bot, "connected", False):
                    await ensure_channels(self.bot, self.logger)
            except asyncio.CancelledError:
                raise
            except Exception as e:  # noqa: BLE001
                self.logger.warning("Kanalen: controle mislukt: %s", e)
            await asyncio.sleep(EVERY_S)
