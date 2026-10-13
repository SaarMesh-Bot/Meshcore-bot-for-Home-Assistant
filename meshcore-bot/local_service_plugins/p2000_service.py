#!/usr/bin/env python3
"""P2000: emergency service call-outs, with as little airtime as possible (card: Plugins -> P2000, off by default).

Reads the public AlarmeringDroid API (the same source as Home Assistant's p2000_nl integration) for the regions on the
card, keeps the messages of the last days (modules/p2000.py), and:
- posts only priority-1 messages (P1, A1, "met spoed") in the card's channel, at most a few an hour, never one that is
  older than half an hour (after a restart or a gap);
- once a day (default 12:00) posts how often the fire brigade, ambulance and police were called out in the last 24 h;
- gives the `p2000` command its data (latest message, a place, only urgent ones, today's numbers), in that channel and
  by DM only.

The first round after a start only stores what is there and posts nothing.
"""
import asyncio
import json
import time
from typing import Any, Optional

from .base_service import BaseServicePlugin

SUMMARY_KEY = "p2000.summary_day"
USER_AGENT = "meshcore-bot-ha P2000 (github.com/vipje/Meshcore-bot-for-Home-Assistant)"


def _bool(value: str, default: bool) -> bool:
    v = str(value or "").strip().lower()
    return default if not v else v in ("1", "true", "yes", "on")


class P2000Service(BaseServicePlugin):
    config_section = "P2000"
    name = "p2000"
    description = "P2000: only priority-1 call-outs in a channel, a daily count at noon, and the p2000 command for the rest"

    settings_schema = [
        {"key": "regions", "label": "Regions (P2000 region numbers)", "type": "str", "default": "",
         "help": "Comma-separated region numbers as used by P2000 / AlarmeringDroid, e.g. 21 for Zuid-Limburg, 22 for "
                 "Limburg-Noord. Empty = nothing is read."},
        {"key": "channel", "label": "Channel", "type": "str", "default": "#p2000",
         "help": "Where priority-1 messages and the daily count go. The p2000 command works only here and by DM."},
        {"key": "post_priority1", "label": "Post priority-1 messages", "type": "bool", "default": True,
         "help": "P1 (police), A1 (ambulance) and 'met spoed' (fire brigade) as they come in. Everything else only on request "
                 "with the p2000 command."},
        {"key": "max_per_hour", "label": "At most per hour", "type": "int", "default": 4, "min": 1, "max": 30,
         "help": "Priority-1 messages above this number in one hour are not posted (they are still in p2000)."},
        {"key": "daily_summary", "label": "Daily count", "type": "bool", "default": True,
         "help": "Once a day: how often the fire brigade, ambulance and police were called out in the last 24 hours."},
        {"key": "summary_time", "label": "Daily count at", "type": "str", "default": "12:00",
         "help": "Local time, HH:MM."},
        {"key": "poll_seconds", "label": "Check every (s)", "type": "int", "default": 60, "min": 30, "max": 600},
    ]

    def __init__(self, bot: Any):
        super().__init__(bot)
        cfg = bot.config
        s = self.config_section
        has = cfg.has_section(s)

        def get(key, fallback=""):
            return (cfg.get(s, key, fallback=fallback) if has else fallback) or fallback

        def getint(key, fallback, lo, hi):
            try:
                return min(hi, max(lo, int(get(key, str(fallback)) or fallback)))
            except ValueError:
                return fallback

        self.regions = [r.strip() for r in get("regions", "").replace(";", ",").split(",") if r.strip().isdigit()]
        channel = get("channel", "#p2000").strip() or "#p2000"
        self.channel = channel.lower() if channel.startswith("#") else channel
        self.post_priority1 = _bool(get("post_priority1", "true"), True)
        self.max_per_hour = getint("max_per_hour", 4, 1, 30)
        self.daily_summary = _bool(get("daily_summary", "true"), True)
        self.summary_time = get("summary_time", "12:00").strip() or "12:00"
        self.poll_s = getint("poll_seconds", 60, 30, 600)
        language = cfg.get("Localization", "language", fallback="en") if cfg.has_section("Localization") else "en"
        get_translator = getattr(bot, "get_translator", None)
        try:
            self.translate = get_translator(language).translate if get_translator else bot.translator.translate
        except Exception:  # noqa: BLE001
            self.translate = bot.translator.translate
        self._task: Optional[asyncio.Task] = None
        self._first_run = True
        self.last_error = ""

    # ------------------------------------------------------------------ lifecycle
    async def start(self) -> None:
        self._running = True
        if not self.regions:
            self.logger.info("P2000: geen regio's op de kaart, niets te doen")
            return
        self._task = asyncio.create_task(self._loop())
        self.logger.info("P2000: gestart (regio's %s, kanaal %s, prio 1 %s, max %s/u, dagtelling %s)",
                         ", ".join(self.regions), self.channel, "aan" if self.post_priority1 else "uit",
                         self.max_per_hour, self.summary_time if self.daily_summary else "uit")

    async def stop(self) -> None:
        self._running = False
        if self._task:
            self._task.cancel()

    async def _loop(self) -> None:
        await asyncio.sleep(15)
        while self._running:
            try:
                await self.tick()
            except asyncio.CancelledError:
                raise
            except Exception as e:  # noqa: BLE001
                self.logger.warning("P2000: %s", e)
            await asyncio.sleep(self.poll_s)

    # ------------------------------------------------------------------ work
    async def fetch(self) -> Any:
        import aiohttp
        from ..p2000 import API_URL
        url = API_URL + json.dumps({"regios": self.regions}, separators=(",", ":"))
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=20), headers={"User-Agent": USER_AGENT}) as session:
            async with session.get(url) as r:
                r.raise_for_status()
                return await r.json(content_type=None)

    async def tick(self, now: Optional[float] = None, data: Any = None) -> int:
        """One round: read, store, post new priority-1 messages, the daily count when due. Returns messages sent."""
        from .. import p2000 as P
        from ..mesh_community import local_now
        now = time.time() if now is None else now
        local = local_now(self.bot, now)
        if data is None:
            try:
                data = await self.fetch()
                if self.last_error:
                    self.logger.info("P2000: bron weer bereikbaar")
                self.last_error = ""
            except Exception as e:  # noqa: BLE001
                if str(e) != self.last_error:
                    self.logger.info("P2000: bron niet bereikbaar: %s", e)
                self.last_error = str(e)
                data = None
        sent = 0
        with self.bot.db_manager.connection() as conn:
            new = P.store(conn, P.parse(data, local), now) if data is not None else []
            first, self._first_run = self._first_run, False
            if self.post_priority1 and not first:
                for m in new:
                    if not m["prio1"] or now - m["ts"] > P.FRESH_S:
                        continue
                    if P.posted_since(conn, now - 3600) >= self.max_per_hour:
                        self.logger.info("P2000: maximum per uur bereikt, niet gepost: %s", m["tekst"][:60])
                        continue
                    if await self._send(P.line(m)):
                        P.mark_posted(conn, m["id"])
                        sent += 1
            if self.daily_summary and P.summary_due(local, self.summary_time, self._summary_done()):
                text = P.summary_text(P.counts(conn, now - 86400, now), self.translate)
                if await self._send(text):
                    self._set_summary_done(local.strftime("%Y-%m-%d"))
                    sent += 1
        return sent

    def _summary_done(self) -> str:
        try:
            return self.bot.db_manager.get_metadata(SUMMARY_KEY) or ""
        except Exception:  # noqa: BLE001
            return ""

    def _set_summary_done(self, day: str) -> None:
        try:
            self.bot.db_manager.set_metadata(SUMMARY_KEY, day)
        except Exception as e:  # noqa: BLE001
            self.logger.debug("P2000: opslaan mislukt: %s", e)

    async def _send(self, text: str) -> bool:
        cm = getattr(self.bot, "command_manager", None)
        if cm is None or not getattr(self.bot, "connected", False):
            return False
        try:
            ok = await cm.send_channel_message(self.channel, text, skip_user_rate_limit=True)
        except Exception as e:  # noqa: BLE001
            self.logger.info("P2000: verzenden naar %s mislukt: %s", self.channel, e)
            return False
        if ok:
            self.logger.info("P2000 gepost in %s: %s", self.channel, text[:80])
        return bool(ok)
