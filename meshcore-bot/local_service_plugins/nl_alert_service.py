#!/usr/bin/env python3
"""NLAlert: NL-Alert warnings and the monthly siren test in a channel (card: Plugins -> NLAlert, off by default).

Polls the public NL-Alert feed (see modules/nl_alert.py) and posts new alerts for the chosen provinces and/or within a
radius of the bot in the channel on the card (default #nlalert; AutoChannels makes it on the radio). Every first Monday
of the month at 12:00 (local time) a short note that the sirens are being tested, with the official exceptions; in
June and December it also mentions NL-Alert's own test message. Warnings are posted at night too (night mode does not
hold them back). The mesh is an extra way to hear about a warning, never the official one: the post says "NL-Alert"
and keeps the official text.
"""
import asyncio
import json
import time
from typing import Any, Optional

from .base_service import BaseServicePlugin

SEEN_KEY = "nlalert.seen"
SENT_KEY = "nlalert.sent"
SIREN_KEY = "nlalert.siren_month"
GAP_S = 3


class NLAlertService(BaseServicePlugin):
    config_section = "NLAlert"
    name = "nlalert"
    description = "NL-Alert warnings for your province(s) and the monthly siren test (first Monday 12:00) in a channel"

    settings_schema = [
        {"key": "channel", "label": "Channels", "type": "str", "default": "#nlalert",
         "help": "Where the warnings go; several comma-separated, e.g. #nlalert, #limburg. Hashtag channels are made on the "
                 "radio by AutoChannels."},
        {"key": "provinces", "label": "Provinces", "type": "str", "default": "",
         "help": "Comma-separated, e.g. Limburg or Limburg, Noord-Brabant. The province of an alert is looked up once from the "
                 "middle of its area (OpenStreetMap). Empty, with radius 0, = the whole country."},
        {"key": "radius_km", "label": "Also within (km) of the bot", "type": "int", "default": 0, "min": 0, "max": 400,
         "help": "Also post alerts whose area comes this close to the bot (handy near a border). 0 = off."},
        {"key": "siren_test", "label": "Siren test notice", "type": "bool", "default": True,
         "help": "Every first Monday of the month at 12:00: the sirens are tested, nothing is wrong. Not on public holidays; "
                 "the sirens stop on 1 January 2028."},
        {"key": "poll_seconds", "label": "Check every (s)", "type": "int", "default": 120, "min": 60, "max": 900},
    ]

    def __init__(self, bot: Any):
        super().__init__(bot)
        cfg = bot.config
        s = self.config_section
        has = cfg.has_section(s)

        def get(key, fallback=""):
            return (cfg.get(s, key, fallback=fallback) if has else fallback) or fallback

        # one or more channels, comma-separated; a hashtag channel's key comes from its lowercase name
        self.channels = []
        for n in (get("channel", "#nlalert") or "#nlalert").replace(";", ",").split(","):
            n = n.strip()
            n = n.lower() if n.startswith("#") else n
            if n and n not in self.channels:
                self.channels.append(n)
        self.channels = self.channels or ["#nlalert"]
        self.channel = ", ".join(self.channels)
        self.provinces = [p.strip() for p in get("provinces", "").split(",") if p.strip()]
        try:
            self.radius_km = max(0, int(get("radius_km", "0") or 0))
        except ValueError:
            self.radius_km = 0
        self.siren_test = (get("siren_test", "true").strip().lower() in ("1", "true", "yes", "on"))
        try:
            self.poll_s = min(900, max(60, int(get("poll_seconds", "120") or 120)))
        except ValueError:
            self.poll_s = 120
        language = cfg.get("Localization", "language", fallback="en") if cfg.has_section("Localization") else "en"
        get_translator = getattr(bot, "get_translator", None)
        try:
            self.translate = get_translator(language).translate if get_translator else bot.translator.translate
        except Exception:  # noqa: BLE001
            self.translate = bot.translator.translate
        self._task: Optional[asyncio.Task] = None
        self._province_cache: dict = {}
        self._first_run = True
        self.last_error = ""

    # ------------------------------------------------------------------ lifecycle
    async def start(self) -> None:
        self._running = True
        self._task = asyncio.create_task(self._loop())
        self.logger.info("NL-Alert: gestart (kanaal %s, provincies %s, straal %s km, sirenetest %s)", self.channel,
                         ", ".join(self.provinces) or "alle", self.radius_km, "aan" if self.siren_test else "uit")

    async def stop(self) -> None:
        self._running = False
        if self._task:
            self._task.cancel()

    async def _loop(self) -> None:
        await asyncio.sleep(20)
        while self._running:
            try:
                await self.tick()
            except asyncio.CancelledError:
                raise
            except Exception as e:  # noqa: BLE001
                self.logger.warning("NL-Alert: %s", e)
            await asyncio.sleep(self.poll_s if not self._siren_soon() else 30)

    # ------------------------------------------------------------------ state
    def _meta(self, key: str, default):
        try:
            raw = self.bot.db_manager.get_metadata(key)
            return json.loads(raw) if raw else default
        except Exception:  # noqa: BLE001
            return default

    def _set_meta(self, key: str, value) -> None:
        try:
            self.bot.db_manager.set_metadata(key, json.dumps(value))
        except Exception as e:  # noqa: BLE001
            self.logger.debug("NL-Alert: opslaan mislukt: %s", e)

    def _here(self) -> Optional[tuple]:
        cfg = self.bot.config
        try:
            return (cfg.getfloat("Bot", "bot_latitude"), cfg.getfloat("Bot", "bot_longitude"))
        except Exception:  # noqa: BLE001
            return None

    def _siren_soon(self) -> bool:
        from ..mesh_community import local_now
        from ..nl_alert import siren_test_day
        local = local_now(self.bot)
        return self.siren_test and siren_test_day(local.date()) and 11 * 60 + 55 <= local.hour * 60 + local.minute < 12 * 60 + 15

    # ------------------------------------------------------------------ work
    async def fetch(self) -> Any:
        import aiohttp
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=20)) as session:
            from ..nl_alert import FEED_URL
            async with session.get(FEED_URL, headers={"User-Agent": "meshcore-bot-ha (NL-Alert on the mesh)"}) as r:
                r.raise_for_status()
                return await r.json(content_type=None)

    async def province_of(self, point: tuple) -> Optional[str]:
        key = (round(point[0], 3), round(point[1], 3))
        if key in self._province_cache:
            return self._province_cache[key]
        name = None
        try:
            from ..utils import rate_limited_nominatim_reverse
            res = await rate_limited_nominatim_reverse(self.bot, f"{point[0]}, {point[1]}")
            addr = (getattr(res, "raw", None) or {}).get("address", {}) if res else {}
            name = addr.get("state") or addr.get("province")
        except Exception as e:  # noqa: BLE001
            self.logger.info("NL-Alert: provincie opzoeken mislukt: %s", e)
        self._province_cache[key] = name
        return name

    async def tick(self, now: Optional[float] = None, data: Any = None) -> int:
        """One round: siren test if due, then new alerts. Returns the number of messages sent."""
        from .. import nl_alert as N
        from ..mesh_community import local_now
        now = time.time() if now is None else now
        sent_msgs = 0
        if self.siren_test:
            kind = N.siren_due(local_now(self.bot, now), self._meta(SIREN_KEY, ""))
            if kind:
                key = "services.nlalert.siren_with_test" if kind == "with_test" else "services.nlalert.siren"
                if await self._send(self.translate(key)):
                    self._set_meta(SIREN_KEY, local_now(self.bot, now).strftime("%Y-%m"))
                    sent_msgs += 1
        if data is None:
            try:
                data = await self.fetch()
                self.last_error = ""
            except Exception as e:  # noqa: BLE001
                if str(e) != self.last_error:
                    self.logger.info("NL-Alert: feed niet bereikbaar: %s", e)
                self.last_error = str(e)
                return sent_msgs
        alerts = N.parse_feed(data)
        seen_list = list(self._meta(SEEN_KEY, []))
        seen = set(seen_list)
        sent = {k: float(v) for k, v in self._meta(SENT_KEY, {}).items() if now - float(v) < N.REPEAT_WINDOW_S}
        first = self._first_run and not seen
        self._first_run = False
        here = self._here()
        for a in N.new_alerts(alerts, seen, sent, now, first):
            names = {}
            for poly in a["areas"]:
                c = N.centre(poly)
                names[c] = await self.province_of(c) if self.provinces else None
            if not N.wanted(a, self.provinces, self.radius_km, here, lambda p: names.get(p)):
                self.logger.info("NL-Alert: buiten het gebied, niet gepost: %s (%s)", a["text"][:60],
                                 ", ".join(n for n in names.values() if n) or "?")
                continue
            parts = N.split(a["text"], self.translate("services.nlalert.prefix"))
            ok = True
            for i, p in enumerate(parts):
                if i:
                    await asyncio.sleep(GAP_S)
                ok = await self._send(p) and ok
            if ok:
                sent[N.text_key(a["text"])] = now
                sent_msgs += len(parts)
                self.logger.info("NL-Alert gepost in %s: %s", self.channel, a["text"][:80])
        seen_list += [a["id"] for a in reversed(alerts) if a["id"] not in seen]
        self._set_meta(SEEN_KEY, seen_list[-500:])
        self._set_meta(SENT_KEY, sent)
        return sent_msgs

    async def _send(self, text: str) -> bool:
        """To every channel on the card; True when at least one got it."""
        cm = getattr(self.bot, "command_manager", None)
        if cm is None or not getattr(self.bot, "connected", False):
            return False
        ok = False
        for i, channel in enumerate(self.channels):
            if i:
                await asyncio.sleep(GAP_S)
            try:
                if await cm.send_channel_message(channel, text, skip_user_rate_limit=True):
                    ok = True
                else:
                    self.logger.info("NL-Alert: verzenden naar %s mislukt", channel)
            except Exception as e:  # noqa: BLE001
                self.logger.info("NL-Alert: verzenden naar %s mislukt: %s", channel, e)
        return ok
