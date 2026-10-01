#!/usr/bin/env python3
"""HASensors: the bot's numbers as Home Assistant sensors (see modules/ha_sensors.py). Card: Plugins -> HASensors, on by
default; every sensor is sensor.meshcore_bot_<name>. Writes through Home Assistant's REST API like the heartbeat, never
over the radio."""
import asyncio
import os
import time
from typing import Any, Optional

try:
    import aiohttp
except ImportError:  # pragma: no cover
    aiohttp = None  # type: ignore[assignment]

from ..ha_sensors import PREFIX, collect
from ..radio_stats import radio_stats
from .base_service import BaseServicePlugin

STATES_URL = "http://supervisor/core/api/states/"
FIRST_S = 60
ERROR_LOG_INTERVAL_S = 6 * 3600


class HASensorsService(BaseServicePlugin):
    config_section = "HASensors"
    name = "hasensors"
    description = ("The bot's numbers as Home Assistant sensors (sensor.meshcore_bot_...): people, messages, commands, nodes "
                   "heard, direct neighbours, noise floor, airtime, map uploads, Farming Idle")

    settings_schema = [
        {"key": "interval_minutes", "label": "Update every", "type": "int", "default": 5, "min": 1, "max": 60, "unit": "min",
         "help": "How often the sensors are written. The radio numbers come from local commands (no airtime)."},
    ]

    def __init__(self, bot: Any):
        super().__init__(bot)
        cfg = bot.config
        try:
            minutes = int(cfg.get("HASensors", "interval_minutes", fallback="5") or 5) if cfg.has_section("HASensors") else 5
        except ValueError:
            minutes = 5
        self.interval = max(1, min(60, minutes)) * 60
        self._task: Optional[asyncio.Task] = None
        self._session = None
        self._error_logged = 0.0
        self.last_written = 0

    async def start(self) -> None:
        self._running = True
        cfg = self.bot.config
        if not (cfg.has_section("HASensors") and cfg.getboolean("HASensors", "enabled", fallback=False)):
            return
        if aiohttp is None or not os.environ.get("SUPERVISOR_TOKEN"):
            self.logger.info("HA-sensoren: niet in Home Assistant (geen token), service doet niets")
            return
        self._session = aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=15))
        self._task = asyncio.get_running_loop().create_task(self._loop())

    async def stop(self) -> None:
        self._running = False
        if self._task is not None:
            self._task.cancel()
            self._task = None
        if self._session is not None:
            await self._session.close()
            self._session = None

    async def _loop(self) -> None:
        await asyncio.sleep(FIRST_S)
        while self._running:
            try:
                await self.write()
            except asyncio.CancelledError:
                raise
            except Exception as e:  # noqa: BLE001
                self._complain(f"HA-sensoren: mislukt: {e}")
            await asyncio.sleep(self.interval)

    def _complain(self, text: str) -> None:
        if time.time() - self._error_logged >= ERROR_LOG_INTERVAL_S:
            self._error_logged = time.time()
            self.logger.warning(text)

    async def write(self) -> int:
        """Write every sensor; returns how many were accepted."""
        radio = await radio_stats(self.bot) if getattr(self.bot, "connected", False) else {}
        sensors = await asyncio.to_thread(collect, self.bot, radio)
        token = os.environ.get("SUPERVISOR_TOKEN", "")
        ok = 0
        for object_id, body in sensors.items():
            try:
                async with self._session.post(STATES_URL + PREFIX + object_id, json=body,
                                              headers={"Authorization": f"Bearer {token}"}) as resp:
                    if resp.status in (200, 201):
                        ok += 1
                    else:
                        self._complain(f"HA-sensoren: Home Assistant antwoordde HTTP {resp.status}")
            except Exception as e:  # noqa: BLE001
                self._complain(f"HA-sensoren: Home Assistant niet bereikbaar: {e}")
                break
        if ok and not self.last_written:
            self.logger.info("HA-sensoren: %d sensoren geschreven (%s...)", ok, PREFIX)
        self.last_written = ok
        return ok
