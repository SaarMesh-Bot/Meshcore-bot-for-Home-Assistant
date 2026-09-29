#!/usr/bin/env python3
"""Install count: tells the add-on's maintainer, anonymously, that this installation runs (card: Plugins -> InstallCount,
on by default, one switch to turn it off; said in README, INSTALL and DOCS).

Once a day the bot sends one small retained MQTT message to the network's server (the same server as the bot network,
fixed in bot_network_service.py) under meshcore-bot-ha/count/v1/<install id>: {"v": <add-on version>, "d": <date>}.
The install id is a random number made once and kept in the bot's database (bot_metadata "count.install_id"): it is
not derived from the radio, the bot's name or any key, so it says nothing about who or where. Nothing from the mesh is
sent, and no airtime is used. The connection itself shows the server an IP address, as any internet request does.
Switched off, nothing is sent at all.

The maintainer counts the ids whose date is recent (MQTT Explorer, or the SQL archive) to know how many installations
run and which versions.
"""
import asyncio
import datetime
import json
import os
import random
import ssl
import time
import uuid
from typing import Any, Optional

from .base_service import BaseServicePlugin
from .bot_network_service import BROKER

SECTION = "InstallCount"
TOPIC = "meshcore-bot-ha/count/v1"
ID_KEY = "count.install_id"
LAST_KEY = "count.last_day"
FIRST_S = 600           # the first message 10 minutes after the start (plus a random wait)
JITTER_S = 3600
CHECK_EVERY_S = 3600


def install_id(bot: Any) -> str:
    """The random, anonymous id of this installation (made once)."""
    raw = bot.db_manager.get_metadata(ID_KEY)
    if raw and len(str(raw)) == 16:
        return str(raw)
    new = uuid.uuid4().hex[:16]
    bot.db_manager.set_metadata(ID_KEY, new)
    return new


def count_message(bot: Any, version: str, today: str) -> tuple:
    """(topic, payload) of the daily message: nothing but the random id, the version and the date."""
    return f"{TOPIC}/{install_id(bot)}", json.dumps({"v": str(version)[:20], "d": today}, separators=(",", ":"))


class InstallCountService(BaseServicePlugin):
    config_section = SECTION
    name = "installcount"
    description = ("Counts this installation anonymously: once a day a random number and the add-on version go to the "
                   "maintainer's server, so the maintainer knows how many installations run. Nothing about you, your radio or the mesh")

    settings_schema: list = []

    def __init__(self, bot: Any):
        super().__init__(bot)
        self.version = os.environ.get("ADDON_VERSION", "") or "?"
        self._task: Optional[asyncio.Task] = None
        self._due = 0.0

    def is_enabled(self) -> bool:
        cfg = self.bot.config
        return cfg.has_section(SECTION) and cfg.getboolean(SECTION, "enabled", fallback=False)

    async def start(self) -> None:
        self._running = True
        if not self.is_enabled():
            return
        self._due = time.time() + FIRST_S + random.uniform(0, JITTER_S)
        self._task = asyncio.get_running_loop().create_task(self._loop())

    async def stop(self) -> None:
        self._running = False
        if self._task is not None:
            self._task.cancel()
            self._task = None

    async def _loop(self) -> None:
        while self._running:
            await asyncio.sleep(max(1.0, min(CHECK_EVERY_S, self._due - time.time())))
            try:
                await self.tick()
            except asyncio.CancelledError:
                raise
            except Exception as e:  # noqa: BLE001 - a count is never worth a crash
                self.logger.debug("Install count: %s", e)

    def _today(self) -> str:
        return datetime.date.today().isoformat()

    async def tick(self, now: Optional[float] = None) -> bool:
        """Send today's message when it is due and not sent yet today. True = sent."""
        now = time.time() if now is None else now
        if not self.is_enabled() or now < self._due:
            return False
        today = self._today()
        if self.bot.db_manager.get_metadata(LAST_KEY) == today:
            self._due = now + CHECK_EVERY_S
            return False
        topic, payload = count_message(self.bot, self.version, today)
        ok = await asyncio.get_running_loop().run_in_executor(None, self._send, topic, payload)
        if ok:
            self.bot.db_manager.set_metadata(LAST_KEY, today)
            self.logger.info("Install count: sent (anonymous id and version %s)", self.version)
        self._due = now + (CHECK_EVERY_S if ok else 3 * CHECK_EVERY_S)
        return ok

    def _send(self, topic: str, payload: str) -> bool:
        """One short connection: connect, publish (retained), disconnect."""
        try:
            import paho.mqtt.publish as publish
        except ImportError:
            return False
        try:
            publish.single(topic, payload, qos=1, retain=True, hostname=BROKER["host"], port=BROKER["port"],
                           client_id=f"mcbot-count-{topic.rsplit('/', 1)[-1][:8]}",
                           auth={"username": BROKER["username"], "password": BROKER["password"]},
                           tls={"cert_reqs": ssl.CERT_REQUIRED} if BROKER["tls"] else None, keepalive=30)
            return True
        except Exception as e:  # noqa: BLE001
            self.logger.debug("Install count not sent: %s", e)
            return False
