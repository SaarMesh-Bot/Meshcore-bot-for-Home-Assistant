#!/usr/bin/env python3
"""Install count: tells the add-on's maintainer, anonymously, that this installation runs (card: Plugins -> InstallCount,
on by default, one switch to turn it off; said in README, INSTALL and DOCS).

Once a day the bot sends one small retained MQTT message to the network's server (the same server as the bot network,
fixed in bot_network_service.py) under meshcore-bot-ha/count/v1/<install id>: {"v": <add-on version>, "d": <date>, "l": <bot language>,
"a": <processor type>, "c": <serial/ble/tcp>, "p": [<cards/commands switched on>], "o": [<switched off>],
"i": <days since installation>, "e": <errors yesterday>, "w": <warnings yesterday>} (l..o since 2.52.1, i/e/w 2.52.2).
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
import platform
import random
import re
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
SINCE_KEY = "count.since"      # the day this installation started (for "days since installation")
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


# Section names that are not cards (or say nothing useful): never sent as "on".
NOT_CARDS = {"Bot", "Connection", "Channels", "Localization", "Keywords", "Admin_ACL", "Logging", "Web_Viewer", "Channels_List"}
_NAME = re.compile(r"^[A-Za-z][A-Za-z0-9_]{0,39}$")


def known_sections(bot: Any) -> set:
    """The config sections of the commands and services the bot has loaded (names from the code, never typed by a user)."""
    out = set()
    cm = getattr(bot, "command_manager", None)
    for command in (getattr(cm, "commands", None) or {}).values():
        try:
            out.add(command._derive_config_section_name())
        except Exception:  # noqa: BLE001
            pass
    services = getattr(bot, "services", None) or {}
    for service in (services.values() if isinstance(services, dict) else services):
        section = getattr(service, "config_section", None)
        if isinstance(section, str):
            out.add(section)
    return out


def details(bot: Any) -> dict:
    """What else the daily message says, all fixed technical values (since 2.52.1, wish of the maintainer):
    l = the bot's language, a = processor type, c = how the bot reaches the radio (serial/ble/tcp), p = the cards and
    commands switched on, o = the ones switched off (their section names as written in the add-on's code, e.g. P2000,
    NLAlert, F1_Command; commands that are simply on by default have no switch and are in neither list).
    Never a name, key, channel, place or anything a user typed."""
    cfg = bot.config
    lang = (cfg.get("Localization", "language", fallback="") if cfg.has_section("Localization") else "") or ""
    lang = lang.strip().lower()[:5]
    conn = (cfg.get("Connection", "connection_type", fallback="") if cfg.has_section("Connection") else "").strip().lower()
    on, off = [], []
    known = known_sections(bot)
    for section in cfg.sections():
        if section not in known or section in NOT_CARDS or not _NAME.match(section) or not cfg.has_option(section, "enabled"):
            continue
        try:
            (on if cfg.getboolean(section, "enabled") else off).append(section)
        except ValueError:
            continue
    return {"l": lang if re.fullmatch(r"[a-z]{2}(-[a-z]{2})?", lang or "") else "?",
            "a": (platform.machine() or "?")[:16],
            "c": conn if conn in ("serial", "ble", "tcp") else "?",
            "p": sorted(on)[:120], "o": sorted(off)[:120]}


def install_day(bot: Any, today: str) -> str:
    """The day this installation started: kept once; for an installation from before 2.52.2 the first day the bot heard
    anyone (its contact list), else today."""
    raw = bot.db_manager.get_metadata(SINCE_KEY)
    if raw and re.fullmatch(r"\d{4}-\d{2}-\d{2}", str(raw)):
        return str(raw)
    day = today
    try:
        with bot.db_manager.connection() as conn:
            row = conn.execute("SELECT MIN(date(first_heard)) FROM complete_contact_tracking").fetchone()
        if row and row[0] and re.fullmatch(r"\d{4}-\d{2}-\d{2}", str(row[0])) and str(row[0]) < today:
            day = str(row[0])
    except Exception:  # noqa: BLE001 - no such table yet
        pass
    bot.db_manager.set_metadata(SINCE_KEY, day)
    return day


def health(bot: Any, today: str) -> dict:
    """i = days since installation, e / w = errors and warnings of yesterday (a whole day; only numbers, from the
    Problems page's table)."""
    out = {}
    try:
        since = datetime.date.fromisoformat(install_day(bot, today))
        out["i"] = max(0, (datetime.date.fromisoformat(today) - since).days)
    except Exception:  # noqa: BLE001
        pass
    yesterday = (datetime.date.fromisoformat(today) - datetime.timedelta(days=1)).isoformat()
    try:
        with bot.db_manager.connection() as conn:
            rows = dict(conn.execute("SELECT level, SUM(count) FROM bot_problems WHERE day = ? GROUP BY level",
                                     (yesterday,)).fetchall())
        out["e"] = int((rows.get("ERROR") or 0) + (rows.get("CRITICAL") or 0))
        out["w"] = int(rows.get("WARNING") or 0)
    except Exception:  # noqa: BLE001 - no Problems table (card off): leave it out
        pass
    return out


def count_message(bot: Any, version: str, today: str) -> tuple:
    """(topic, payload) of the daily message: the random id, the version, the date and details() - nothing else."""
    body = {"v": str(version)[:20], "d": today}
    try:
        body.update(details(bot))
    except Exception:  # noqa: BLE001 - the count itself still goes
        pass
    try:
        body.update(health(bot, today))
    except Exception:  # noqa: BLE001
        pass
    return f"{TOPIC}/{install_id(bot)}", json.dumps(body, separators=(",", ":"))


class InstallCountService(BaseServicePlugin):
    config_section = SECTION
    name = "installcount"
    description = ("Counts this installation anonymously: once a day a random number, the add-on version, the bot's language, "
                   "the processor type, the connection type, which cards are on, the days since installation and yesterday's "
                   "number of errors go to the maintainer's server, so the maintainer knows how many installations run, what is "
                   "used and whether a version misbehaves. No names, keys, channels, places or anything from the mesh")

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
