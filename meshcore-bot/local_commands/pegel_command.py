#!/usr/bin/env python3
"""
'pegel' command: the current water level of a gauge with the 3-hour trend, from PEGELONLINE (federal waterways) or
the Saarland's HMD (smaller rivers). Stations are set on the card (Pegel_Command -> stations, see modules/de_pegel.py);
the default is the Saarland's: saar (Sankt Arnual), blies (Alsfassen), nied (Niedaltdorf).

  pegel              -> the default station
  pegel nied         -> a station by its alias
  pegel ?            -> the list of aliases
  pegel trend [nied] [7d] / pegeltrend, pegel3d, pegel7d, pegel10d
                     -> the level now and N days ago with min / max / average (default 7 days; HMD stations keep
                        one week, PEGELONLINE 30 days)
  pegel alarm / pegelalarm
                     -> the alarm station (PegelAlarm card) against its thresholds: the stage now and the next one
"""

from typing import Any

from ..models import MeshMessage
from .base_command import BaseCommand


class PegelCommand(BaseCommand):
    """Current water level of a German gauge (PEGELONLINE / Saarland HMD)."""

    name = "pegel"
    keywords = ["pegel", "pegeltrend", "pegel3d", "pegel7d", "pegel10d", "pegelalarm"]
    description = "Current water level of a gauge with 3 h trend (usage: pegel [alias|?])"
    category = "general"
    requires_internet = True

    short_description = "Current water level, German gauges"
    usage = "pegel [alias|?|trend [alias] [Nd]|alarm]"
    examples = ["pegel", "pegel nied", "pegel ?", "pegel trend 10d", "pegel alarm"]

    def __init__(self, bot: Any):
        super().__init__(bot)
        from ..de_pegel import DEFAULT_STATIONS, parse_stations, norm
        self.pegel_enabled = self.get_config_value("Pegel_Command", "enabled", fallback=True, value_type="bool")
        self.stations = parse_stations(
            self.get_config_value("Pegel_Command", "stations", fallback=DEFAULT_STATIONS) or DEFAULT_STATIONS
        ) or parse_stations(DEFAULT_STATIONS)
        default = norm(self.get_config_value("Pegel_Command", "default", fallback="") or "")
        self.default = default if default in self.stations else next(iter(self.stations))

    def can_execute(self, message: MeshMessage, skip_channel_check: bool = False) -> bool:
        if not self.pegel_enabled:
            return False
        return super().can_execute(message, skip_channel_check=skip_channel_check)

    def get_help_text(self) -> str:
        return self.translate("commands.pegel.help", stations=", ".join(self.stations))

    async def _trend_text(self, st: dict, days: int, now) -> str:
        from .. import de_fetch, de_pegel as P
        days = max(1, min(P.MAX_DAYS.get(st["source"], 7), int(days)))
        if st["source"] == "hmd":
            series = await de_fetch.hmd_series(st["id"], now.tzinfo)
        else:
            series = P.po_series(await de_fetch.pegelonline_history(st["id"], days * 24), now.tzinfo)
        sp = P.span(series, days)
        if not sp:
            return self.translate("commands.pegel.fetch_error", station=st["label"])
        text = self.translate(
            "commands.pegel.trend", station=st["label"], days=days, value=P.metres(sp["now"]),
            then=P.metres(sp["then"]), arrow=P.span_arrow(sp["diff"]), diff=f"{sp['diff']:+.0f}",
            min=P.metres(sp["min"]), max=P.metres(sp["max"]), avg=P.metres(sp["avg"]))
        if not P.fresh(sp["now_time"], now):
            text += " " + self.translate("commands.pegel.stale")
        return text

    async def _alarm_text(self) -> str:
        from .. import de_fetch, de_pegel as P
        from ..mesh_community import local_now
        cfg = self.bot.config
        sec = "PegelAlarm"

        def get(key, fallback):
            return ((cfg.get(sec, key, fallback=fallback) if cfg.has_section(sec) else fallback) or fallback).strip()

        thresholds = P.parse_thresholds(get("thresholds", P.DEFAULT_THRESHOLDS)) or P.parse_thresholds(P.DEFAULT_THRESHOLDS)
        st = self.stations.get(P.norm(get("station", "saar"))) or self.stations.get(self.default)
        now = local_now(self.bot)
        if st["source"] == "hmd":
            cur = P.hmd_current(await de_fetch.hmd_series(st["id"], now.tzinfo))
        else:
            cur = P.po_current(await de_fetch.pegelonline_station(st["id"]), now.tzinfo)
        if not cur:
            return self.translate("commands.pegel.fetch_error", station=st["label"])
        value = float(cur["value_cm"])
        n = P.stage(value, thresholds)
        nxt = P.next_threshold(value, thresholds)
        common = {"station": st["label"], "value": P.metres(value), "of": len(thresholds)}
        if n == 0:
            text = self.translate("commands.pegel.alarm_normal", **common)
        else:
            text = self.translate("commands.pegel.alarm_stage", stage=n, label=thresholds[n - 1][1], **common)
        if nxt:
            text += " " + self.translate("commands.pegel.alarm_next", cm=nxt[0], label=nxt[1])
        return text

    async def execute(self, message: MeshMessage) -> bool:
        from .. import de_fetch, de_pegel as P
        from ..mesh_community import local_now
        try:
            arg = message.content.strip()
            low = arg.lower()
            used = "pegel"
            for kw in sorted(self.keywords, key=len, reverse=True):
                if low == kw or low.startswith(kw + " "):
                    arg, used = arg[len(kw):].strip(), kw
                    break
            mode, days, rest = "now", None, []
            if used == "pegelalarm":
                mode = "alarm"
            elif used != "pegel":
                mode, days = "trend", (7 if used == "pegeltrend" else int(used[5:-1]))
            for tok in arg.split():
                t = tok.lower()
                if mode == "now" and t in ("trend", "verlauf"):
                    mode = "trend"
                elif mode == "now" and t in ("alarm", "warnstufe", "stufe"):
                    mode = "alarm"
                elif P.parse_days(t) is not None and (mode == "trend" or t[-1:] in ("d", "t")):
                    mode, days = "trend", P.parse_days(t)
                else:
                    rest.append(tok)
            arg = " ".join(rest)
            if mode == "alarm":
                return await self.send_response(message, await self._alarm_text())
            if arg in ("?", "liste", "list", "help", "hilfe"):
                return await self.send_response(
                    message, self.translate("commands.pegel.list", stations=", ".join(
                        f"{k} ({v['label']})" for k, v in self.stations.items())))
            key = P.norm(arg) if arg else self.default
            st = self.stations.get(key)
            if st is None:
                return await self.send_response(message, self.translate("commands.pegel.unknown", name=arg))

            now = local_now(self.bot)
            if mode == "trend":
                return await self.send_response(message, await self._trend_text(st, days or 7, now))
            if st["source"] == "hmd":
                cur = P.hmd_current(await de_fetch.hmd_series(st["id"], now.tzinfo))
            else:
                station = await de_fetch.pegelonline_station(st["id"])
                cur = P.po_current(station, now.tzinfo)
                if cur:
                    cur["trend_cm"] = P.po_trend(await de_fetch.pegelonline_history(st["id"], 3))
            if not cur:
                return await self.send_response(message, self.translate("commands.pegel.fetch_error", station=st["label"]))

            t = cur.get("time")
            response = self.translate(
                "commands.pegel.result", station=st["label"], value=P.metres(cur["value_cm"]),
                trend=P.trend_text(cur.get("trend_cm")), time=t.strftime("%H:%M") if t else "?")
            if not P.fresh(t, now):
                response += " " + self.translate("commands.pegel.stale")
            return await self.send_response(message, response)
        except Exception as e:  # noqa: BLE001
            self.logger.error(f"Error executing pegel command: {e}")
            return await self.send_response(message, self.translate("commands.pegel.error", error=str(e)))
