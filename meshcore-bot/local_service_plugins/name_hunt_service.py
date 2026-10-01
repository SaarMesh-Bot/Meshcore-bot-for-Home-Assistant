#!/usr/bin/env python3
"""NameHunt: at quiet hours the bot looks for the names of the unknown hashtag channels on the Channel radar (card:
Plugins -> NameHunt, on by default). See modules/name_hunt.py.

Quiet hours are learned from the stats: the hours of the day in which people send the fewest messages and commands
(about 7 days; radio packets are not used, they are mostly repeater adverts, also at night). Default 02:00-06:00
while there is too little to go on. In every quiet hour the bot works at most "Minutes per quiet hour" (30) on its
millions of candidate names, in small portions with pauses (it keeps answering), and continues the next quiet hour
where it stopped. When every name has been tried it waits until there is something new to try (new words heard, or a
new unknown channel). A name it finds goes onto the radar at once (as if added with 'Name it') and is logged. Nothing
is sent over the radio.
"""
import asyncio
import itertools
import time
from typing import Any, Optional

from .base_service import BaseServicePlugin

CHECK_EVERY_S = 300
PORTION = 100_000          # names per portion (a fraction of a second)
PAUSE_S = 0.3              # pause between portions


class NameHuntService(BaseServicePlugin):
    config_section = "NameHunt"
    name = "namehunt"
    description = "At quiet hours, tries millions of names against the unknown channels of the Channel radar (no airtime)"

    settings_schema = [
        {"key": "hours", "label": "Quiet hours to use", "type": "int", "default": 4, "min": 1, "max": 12, "unit": "h",
         "help": "How many of the day's quietest hours (fewest messages and commands of people, learned from the last week) the hunt may use."},
        {"key": "minutes", "label": "Minutes per quiet hour", "type": "int", "default": 30, "min": 1, "max": 60, "unit": "min",
         "help": "At most this long in every quiet hour, in small portions with pauses, so the bot keeps answering."},
    ]

    def __init__(self, bot: Any):
        super().__init__(bot)
        cfg = bot.config
        has = cfg.has_section("NameHunt")
        self.hours = cfg.getint("NameHunt", "hours", fallback=4) if has else 4
        self.minutes = cfg.getint("NameHunt", "minutes", fallback=30) if has else 30
        self._task: Optional[asyncio.Task] = None

    async def start(self) -> None:
        self._running = True
        cfg = self.bot.config
        if not (cfg.has_section("NameHunt") and cfg.getboolean("NameHunt", "enabled", fallback=False)):
            return
        self._task = asyncio.get_running_loop().create_task(self._loop())

    async def stop(self) -> None:
        self._running = False
        if self._task is not None:
            self._task.cancel()
            self._task = None

    async def _loop(self) -> None:
        await asyncio.sleep(CHECK_EVERY_S)
        while self._running:
            try:
                await self.maybe_run()
            except asyncio.CancelledError:
                raise
            except Exception as e:  # noqa: BLE001
                self.logger.warning("Naamzoektocht: fout: %s", e)
            await asyncio.sleep(CHECK_EVERY_S)

    def _local(self, ts: float):
        from ..mesh_community import local_now
        return local_now(self.bot, ts)

    def _unknown_bytes(self, now: float) -> list:
        from types import SimpleNamespace
        from ..channel_radar import summary
        bot = SimpleNamespace(config=self.bot.config, db_manager=self.bot.db_manager, logger=self.logger)
        return [u["hash"] for u in summary(bot, now)["unknown"] if u.get("month")]

    async def maybe_run(self, now: Optional[float] = None) -> Optional[dict]:
        """Work in a quiet hour (at most `minutes` per hour); returns what this run did, else None."""
        from .. import name_hunt as NH
        now = time.time() if now is None else now
        db = self.bot.db_manager
        state = NH.load_state(db)
        profile = await asyncio.to_thread(NH.hour_profile, db, lambda ts: self._local(ts).hour, now)
        quiet = NH.quiet_hours(db, self.hours, profile=profile)
        state["quiet_hours"], state["profile"] = sorted(quiet), profile
        local = self._local(now)
        hour_key = local.strftime("%Y-%m-%d %H")
        used = state.get("used_s", 0) if state.get("hour_key") == hour_key else 0
        if local.hour not in quiet or used >= self.minutes * 60:
            NH.save_state(db, state)
            return None
        unknown = self._unknown_bytes(now)
        samples = await asyncio.to_thread(NH.collect_samples, db, unknown, now)
        if not samples:
            state.update({"hour_key": hour_key, "used_s": used, "last_check": int(now), "bytes": 0})
            NH.save_state(db, state)
            return None
        toks = await asyncio.to_thread(NH.tokens, db)
        sig = NH.signature(toks, samples)
        if state.get("done_sig") == sig:       # every name tried already: wait for something new
            state.update({"hour_key": hour_key, "used_s": used, "last_check": int(now)})
            NH.save_state(db, state)
            return None
        if state.get("sig") != sig:
            state.update({"sig": sig, "position": 0, "total": NH.count_candidates(toks)})
        position = int(state.get("position", 0))
        started = time.monotonic()
        budget = self.minutes * 60 - used
        tried_now, found_now = 0, []
        names = itertools.islice(NH.candidates(toks), position, None)
        while True:
            if self._task is not None and not self._running:   # the service is stopping
                break
            portion = list(itertools.islice(names, PORTION))
            if not portion:
                break
            tried, found = await asyncio.to_thread(NH.hunt, samples, iter(portion), len(portion))
            tried_now += tried
            position += tried
            for name, ch, hits in found:
                self._accept(name, ch, hits, now)
                found_now.append(name)
                samples.pop(int(ch, 16), None)
            if not samples or time.monotonic() - started >= budget:
                break
            await asyncio.sleep(PAUSE_S)
        done = position >= state.get("total", 0) or not samples
        state.update({"hour_key": hour_key, "used_s": used + int(time.monotonic() - started), "last_run": int(now),
                      "position": 0 if done else position, "bytes": len(unknown),
                      "rounds": state.get("rounds", 0) + (1 if done else 0),
                      "tried_total": state.get("tried_total", 0) + tried_now})
        if done:
            state["done_sig"] = sig
        NH.save_state(db, state)
        self.logger.info("Naamzoektocht: %d namen geprobeerd tegen %d onbekende kanalen%s", tried_now, len(unknown),
                         (", gevonden: " + ", ".join("#" + n for n in found_now)) if found_now else "")
        return {"tried": tried_now, "found": found_now}

    def _accept(self, name: str, ch: str, hits: int, now: float) -> None:
        from .. import name_hunt as NH
        from ..channel_radar import add_dashboard_name
        add_dashboard_name(self.bot.db_manager, name)
        NH.add_found(self.bot.db_manager, name, ch, hits, now)
        self.logger.info("Naamzoektocht: kanaal #%s gevonden (byte %s, %d berichten kloppen)", name, ch, hits)
