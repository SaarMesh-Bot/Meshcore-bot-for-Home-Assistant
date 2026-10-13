#!/usr/bin/env python3
"""AnalyzerFeed: the observers of the regions you choose, from the public EU Meshcore Analyzer (card: Plugins ->
AnalyzerFeed, off by default).

The analyzer (meshcore-analyzer.eu and its community sites such as cornmeister.nl) collects what thousands of MeshCore
observers hear from all the big brokers and offers it without an account. This service reads, for every region code
on the card (the IATA codes observers use, e.g. MST for South Limburg, AMS, CGN, LGG): the observers every few minutes
(status, model, packets per hour) and the packets they heard every minute (only the new ones). They land in the same
tables as the MQTT observers (modules/observers.py): Radar -> Observers shows them, and their group messages count on the
Channel radar (once per packet, also when the bot heard it itself). Only reads: nothing is published, nothing goes over
the radio, nothing is decrypted. Be kind to a free community service: the defaults are deliberately slow.
"""
import asyncio
import time
from datetime import datetime, timezone
from typing import Any, Optional

from .base_service import BaseServicePlugin

USER_AGENT = "meshcore-bot-ha AnalyzerFeed (github.com/vipje/Meshcore-bot-for-Home-Assistant)"
FIRST_WINDOW_S = 600        # at the start: only the last 10 minutes of packets
SEEN_MAX = 20000


class AnalyzerFeedService(BaseServicePlugin):
    config_section = "AnalyzerFeed"
    name = "analyzerfeed"
    description = "Observers of the regions you choose (e.g. MST) from the public EU Meshcore Analyzer, for Radar -> Observers and the Channel radar"

    settings_schema = [
        {"key": "regions", "label": "Regions", "type": "str", "default": "",
         "help": "Region codes (IATA) of the observers you want, comma-separated, e.g. MST (South Limburg) or MST, LGG, EIN. "
                 "The codes in use are on the analyzer's website (observers list)."},
        {"key": "url", "label": "Analyzer", "type": "str", "default": "https://meshcore-analyzer.eu",
         "help": "The analyzer's web address (https). cornmeister.nl and analyzer.meshcorenetz.de show the same data."},
        {"key": "packets", "label": "Read packets", "type": "bool", "default": True,
         "help": "Also the packets the observers heard: nodes heard in the region and group messages for the Channel radar. "
                 "Off = only the observers and their numbers."},
        {"key": "lookup_names", "label": "Look up unknown names", "type": "bool", "default": True,
         "help": "Neighbours in your repeaters' neighbour lists that have no name (only a key prefix such as a1b2c3) are looked "
                 "up at the analyzer, at most 20 an hour and each once a week. Shown on the Repeater page with the label analyzer. "
                 "Works without regions too."},
        {"key": "observers_minutes", "label": "Observers every (min)", "type": "int", "default": 5, "min": 2, "max": 60},
        {"key": "packets_seconds", "label": "Packets every (s)", "type": "int", "default": 60, "min": 30, "max": 600},
    ]

    def __init__(self, bot: Any):
        super().__init__(bot)
        from ..observers import regions_from
        cfg = bot.config
        has = cfg.has_section("AnalyzerFeed")

        def get(key, fallback=""):
            return (cfg.get("AnalyzerFeed", key, fallback=fallback) if has else fallback) or fallback

        def getint(key, fallback, lo, hi):
            try:
                return min(hi, max(lo, int(get(key, str(fallback)) or fallback)))
            except ValueError:
                return fallback

        self.regions = regions_from(get("regions", ""))
        url = get("url", "https://meshcore-analyzer.eu").strip().rstrip("/")
        self.url = url if url.startswith("https://") else "https://meshcore-analyzer.eu"
        self.read_packets = get("packets", "true").strip().lower() in ("1", "true", "yes", "on")
        self.lookup_names = get("lookup_names", "true").strip().lower() in ("1", "true", "yes", "on")
        self.obs_every = getint("observers_minutes", 5, 2, 60) * 60
        self.pkt_every = getint("packets_seconds", 60, 30, 600)
        self._since: dict = {}
        self._seen: dict = {}
        self._task: Optional[asyncio.Task] = None
        self.last_error = ""
        self.stats = {"observers": 0, "packets": 0}

    # ------------------------------------------------------------------ lifecycle
    async def start(self) -> None:
        self._running = True
        if not self.regions and not self.lookup_names:
            self.logger.info("AnalyzerFeed: geen regio's en geen namen opzoeken op de kaart, niets te doen")
            return
        self._task = asyncio.create_task(self._loop())
        self.logger.info("AnalyzerFeed: gestart (%s, regio's %s, namen opzoeken %s)", self.url, ", ".join(self.regions) or "geen",
                         "aan" if self.lookup_names else "uit")

    async def stop(self) -> None:
        self._running = False
        if self._task:
            self._task.cancel()

    async def _loop(self) -> None:
        import aiohttp
        await asyncio.sleep(15)
        next_obs, next_clean, next_names = 0.0, 0.0, 0.0
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=30), headers={"User-Agent": USER_AGENT}) as session:
            while self._running:
                now = time.time()
                try:
                    if self.regions and now >= next_obs:
                        await self.read_observers(session)
                        next_obs = now + self.obs_every
                    if self.regions and self.read_packets:
                        await self.read_new_packets(session)
                    if self.lookup_names and now >= next_names:
                        await self.look_up_names(session)
                        next_names = now + 600
                    if now >= next_clean:
                        from ..observers import cleanup
                        await asyncio.to_thread(cleanup, self.bot.db_manager)
                        next_clean = now + 3600
                    if self.last_error:
                        self.logger.info("AnalyzerFeed: weer bereikbaar")
                        self.last_error = ""
                except asyncio.CancelledError:
                    raise
                except Exception as e:  # noqa: BLE001
                    if str(e) != self.last_error:
                        self.logger.warning("AnalyzerFeed: %s", e)
                    self.last_error = str(e)
                await asyncio.sleep(self.pkt_every if (self.regions and self.read_packets) else
                                    (self.obs_every if self.regions else 600))

    # ------------------------------------------------------------------ work
    async def _get(self, session, path: str, params: dict) -> Any:
        async with session.get(self.url + path, params=params) as r:
            r.raise_for_status()
            return await r.json(content_type=None)

    async def look_up_names(self, session, now: Optional[float] = None) -> int:
        """Names for unnamed neighbour prefixes (modules/analyzer_names.py), within the hourly budget."""
        from .. import analyzer_names as AN
        now = time.time() if now is None else now
        with self.bot.db_manager.connection() as conn:
            budget = AN.MAX_PER_HOUR - AN.asked_this_hour(conn, now)
            todo = AN.wanted(conn, now, max(0, budget))
        found = 0
        for prefix in todo:
            answer = await self._get(session, "/api/nodes/resolve", {"prefix": prefix})
            with self.bot.db_manager.connection() as conn:
                name = AN.store(conn, prefix, answer, now)
            if name:
                found += 1
                self.logger.info("AnalyzerFeed: %s = %s (EU Meshcore Analyzer)", prefix, name)
        return found

    async def read_observers(self, session) -> int:
        from ..observers import store_analyzer_observers
        total = 0
        for region in self.regions:
            data = await self._get(session, "/api/observers", {"region": region})
            items = data if isinstance(data, list) else (data.get("observers") or [])
            items = [o for o in items if str(o.get("iata") or "").upper() == region]
            total += await asyncio.to_thread(store_analyzer_observers, self.bot.db_manager, items)
        self.stats["observers"] = total
        return total

    async def read_new_packets(self, session, now: Optional[float] = None) -> int:
        from ..observers import store_analyzer_packet
        now = time.time() if now is None else now
        stored = 0
        for region in self.regions:
            since = self._since.get(region) or datetime.fromtimestamp(now - FIRST_WINDOW_S, timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
            data = await self._get(session, "/api/packets", {"region": region, "limit": 500, "since": since})
            packets = (data or {}).get("packets") or []
            seen = self._seen.setdefault(region, {})
            for p in reversed(packets):                       # oldest first
                h = p.get("hash")
                if not h or h in seen:
                    continue
                seen[h] = True
                if await asyncio.to_thread(store_analyzer_packet, self.bot.db_manager, region, p):
                    stored += 1
            if packets:
                self._since[region] = max(str(p.get("timestamp") or "") for p in packets) or since
            if len(seen) > SEEN_MAX:
                for k in list(seen)[: len(seen) - SEEN_MAX // 2]:
                    seen.pop(k, None)
        self.stats["packets"] += stored
        return stored
