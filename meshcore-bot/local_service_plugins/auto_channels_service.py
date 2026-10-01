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
REQUEST_CHECK_S = 60   # requests from the radar page ('Add to radio') are handled within a minute
RETRY_S = 900


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

    def _requests_done(self) -> None:
        """Requests from the radar page that are on the radio now are taken off the list."""
        from ..channel_radar import ADD_META, _save_list, add_to_radio_requests
        cm = getattr(self.bot, "channel_manager", None)
        asked = add_to_radio_requests(self.bot.db_manager)
        if cm is None or not asked:
            return
        left = [n for n in asked if cm.get_channel_number(n) is None]
        if left != asked:
            _save_list(self.bot.db_manager, ADD_META, left)

    async def _loop(self) -> None:
        await asyncio.sleep(FIRST_S)
        last_full = 0.0
        tried: list = []
        while self._running:
            try:
                from ..channel_radar import add_to_radio_requests
                now = asyncio.get_running_loop().time()
                asked = add_to_radio_requests(self.bot.db_manager)
                # every hour, and within a minute when the radar page asked for a channel
                new_request = bool(asked) and asked != tried
                retry = bool(asked) and now - last_full >= RETRY_S   # a request that could not be done (radio full): every 15 min
                if getattr(self.bot, "connected", False) and (new_request or retry or now - last_full >= EVERY_S):
                    last_full, tried = now, asked
                    made = await ensure_channels(self.bot, self.logger)
                    if made:
                        self.logger.info("Kanalen: op de radio gezet: %s", ", ".join(made))
                    self._requests_done()
            except asyncio.CancelledError:
                raise
            except Exception as e:  # noqa: BLE001
                self.logger.warning("Kanalen: controle mislukt: %s", e)
            await asyncio.sleep(REQUEST_CHECK_S)
