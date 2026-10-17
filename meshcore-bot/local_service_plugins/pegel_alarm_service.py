#!/usr/bin/env python3
"""PegelAlarm: flood stages of one gauge in a channel (card: Plugins -> PegelAlarm, off by default). Ported from the
SaarMesh bot, where it watches the Saar at Sankt Arnual (Saarbrücken).

Every few minutes the station on the card (an alias from the Pegel card, default saar) is compared with the thresholds
(cm:label, default the official Hochwassermeldehöhen of Sankt Arnual plus the A620 mark at 380 cm). Only a rise to a
higher stage is posted (one message: stage, label, level and 3-hour trend); falling back a stage is not, so a level
that hovers around a threshold does not flood the channel. Once the level is 10 cm under the lowest threshold an
all-clear goes out. The stage survives a restart; a stale reading (older than 6 hours) is never acted on.
"""
import asyncio
import time
from typing import Any, Optional

from .base_service import BaseServicePlugin

STAGE_KEY = "pegelalarm.stage"
GAP_S = 3


class PegelAlarmService(BaseServicePlugin):
    config_section = "PegelAlarm"
    name = "pegelalarm"
    description = "Flood stages of a gauge (PEGELONLINE / Saarland HMD) in a channel, with all-clear"

    settings_schema = [
        {"key": "channel", "label": "Channels", "type": "str", "default": "#warnings",
         "help": "Where the alarms go; several comma-separated."},
        {"key": "station", "label": "Station", "type": "str", "default": "saar",
         "help": "An alias from the stations on the Pegel command card (default: saar = Sankt Arnual)."},
        {"key": "thresholds", "label": "Thresholds", "type": "str",
         "default": "280:Meldehöhe 1, 320:Warnstufe 1, 350:Meldehöhe 2, 380:A620-Sperrung wahrscheinlich, "
                    "400:Meldehöhe 3, 750:Meldehöhe 4",
         "help": "cm:label, comma-separated, e.g. 280:Meldehöhe 1, 350:Meldehöhe 2."},
        {"key": "poll_seconds", "label": "Check every (s)", "type": "int", "default": 600, "min": 300, "max": 3600},
    ]

    def __init__(self, bot: Any):
        super().__init__(bot)
        from ..de_pegel import DEFAULT_STATIONS, DEFAULT_THRESHOLDS, norm, parse_stations, parse_thresholds
        cfg = bot.config
        s = self.config_section
        has = cfg.has_section(s)

        def get(key, fallback=""):
            return ((cfg.get(s, key, fallback=fallback) if has else fallback) or fallback).strip()

        self.channels = []
        for n in get("channel", "#warnings").replace(";", ",").split(","):
            n = n.strip()
            n = n.lower() if n.startswith("#") else n
            if n and n not in self.channels:
                self.channels.append(n)
        self.channels = self.channels or ["#warnings"]
        self.channel = ", ".join(self.channels)
        stations_txt = (cfg.get("Pegel_Command", "stations", fallback="") if cfg.has_section("Pegel_Command") else "")
        stations = parse_stations(stations_txt or DEFAULT_STATIONS) or parse_stations(DEFAULT_STATIONS)
        self.station = stations.get(norm(get("station", "saar"))) or next(iter(stations.values()))
        self.thresholds = parse_thresholds(get("thresholds", DEFAULT_THRESHOLDS)) or parse_thresholds(DEFAULT_THRESHOLDS)
        try:
            self.poll_s = min(3600, max(300, int(get("poll_seconds", "600"))))
        except ValueError:
            self.poll_s = 600
        language = cfg.get("Localization", "language", fallback="en") if cfg.has_section("Localization") else "en"
        get_translator = getattr(bot, "get_translator", None)
        try:
            self.translate = get_translator(language).translate if get_translator else bot.translator.translate
        except Exception:  # noqa: BLE001
            self.translate = bot.translator.translate
        self._task: Optional[asyncio.Task] = None

    async def start(self) -> None:
        self._running = True
        self._task = asyncio.create_task(self._loop())
        self.logger.info("PegelAlarm: gestartet (%s, Kanal %s, Schwellen %s)", self.station["label"], self.channel,
                         ", ".join(str(c) for c, _ in self.thresholds))

    async def stop(self) -> None:
        self._running = False
        if self._task:
            self._task.cancel()

    async def _loop(self) -> None:
        await asyncio.sleep(45)
        while self._running:
            try:
                await self.tick()
            except asyncio.CancelledError:
                raise
            except Exception as e:  # noqa: BLE001
                self.logger.warning("PegelAlarm: %s", e)
            await asyncio.sleep(self.poll_s)

    def _stage(self) -> int:
        try:
            return int(self.bot.db_manager.get_metadata(STAGE_KEY) or 0)
        except Exception:  # noqa: BLE001
            return 0

    def _set_stage(self, n: int) -> None:
        try:
            self.bot.db_manager.set_metadata(STAGE_KEY, str(int(n)))
        except Exception as e:  # noqa: BLE001
            self.logger.debug("PegelAlarm: speichern fehlgeschlagen: %s", e)

    async def read(self, now_dt) -> Optional[dict]:
        from .. import de_fetch, de_pegel as P
        st = self.station
        if st["source"] == "hmd":
            return P.hmd_current(await de_fetch.hmd_series(st["id"], now_dt.tzinfo))
        cur = P.po_current(await de_fetch.pegelonline_station(st["id"]), now_dt.tzinfo)
        if cur:
            cur["trend_cm"] = P.po_trend(await de_fetch.pegelonline_history(st["id"], 3))
        return cur

    async def tick(self, now: Optional[float] = None, reading: Optional[dict] = None) -> int:
        from .. import de_pegel as P
        from ..mesh_community import local_now
        now_dt = local_now(self.bot, time.time() if now is None else now)
        cur = reading if reading is not None else await self.read(now_dt)
        if not cur or not P.fresh(cur.get("time"), now_dt):
            return 0
        value = float(cur["value_cm"])
        last = self._stage()
        stage = P.stage(value, self.thresholds)
        common = {"station": self.station["label"], "value": P.metres(value), "trend": P.trend_text(cur.get("trend_cm"))}
        if stage > last:
            label = self.thresholds[stage - 1][1]
            icon = "🆘" if stage >= len(self.thresholds) - 1 else ("🚨" if stage >= 4 else "⚠️")
            text = self.translate("services.pegelalarm.alarm", icon=icon, stage=stage, of=len(self.thresholds),
                                  label=label, **common)
            if await self._send(text):
                self._set_stage(stage)
                self.logger.warning("PegelAlarm: Stufe %d (%s) bei %.0f cm gepostet", stage, label, value)
                return 1
            return 0
        if last > 0 and stage == 0 and value <= self.thresholds[0][0] - P.HYSTERESIS_CM:
            if await self._send(self.translate("services.pegelalarm.all_clear", **common)):
                self._set_stage(0)
                return 1
        return 0

    async def _send(self, text: str) -> bool:
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
            except Exception as e:  # noqa: BLE001
                self.logger.info("PegelAlarm: senden an %s fehlgeschlagen: %s", channel, e)
        return ok
