#!/usr/bin/env python3
"""
'f1' command for the MeshCore Bot: Formula 1 questions and the prediction game, in the #f1 channel and by DM.

  f1                  the next race and, in a race week, all session times
  f1 stand            championship top 10 (drivers)        f1 team      constructors
  f1 uitslag          the last race                         f1 nu        the live session, if there is one
  f1 voorspel <code>  pick the winner, by direct message only (your key proves it is you)
  f1 spel             standings of the prediction game

Everything comes from the F1 service (Plugins -> F1), which reads Home Assistant's `f1_sensor`. Nothing here
touches the radio except the reply itself.
"""

import time
from typing import Any

from ..f1_data import (calendar_text, driver_text, find_driver, fit, gp_name, gp_name_of, grid_text, live_active,
                       live_only_text, next_race_text, now_text, pack, pit_text, results_text, weather_text, weekend_text,
                       winner_text)
from ..mesh_community import is_bot_name, without_bots
from ..models import MeshMessage
from .base_command import BaseCommand

STAND = {"wm", "stand", "wk", "rijders", "standings", "klassement"}
TEAM = {"team", "teams", "constructeurs", "constructors"}
RESULT = {"ergebnis", "uitslag", "result", "resultaat", "race"}
LIVE = {"jetzt", "nu", "live", "now"}
PREDICT = {"tipp", "voorspel", "voorspelling", "predict", "gok"}
GAME = {"spiel", "spel", "game", "punten"}
CALENDAR = {"kalender", "calendar", "agenda", "races", "kalendar"}
WEEKEND = {"weekend", "schema", "schedule", "sessies", "sessions", "tijden", "times"}
SPRINT = {"sprint"}
DRIVER = {"coureur", "rijder", "driver", "fahrer", "pilote", "pilot"}
GRID = {"grid", "startgrid", "opstelling", "start", "startopstelling"}
ME = {"ik", "me", "mij", "mijn", "mine", "moi", "ich"}
WEATHER = {"weer", "weather", "wetter", "meteo", "météo"}
PIT = {"pit", "pits", "pitstop", "pitstops", "boxenstopp"}
MAX_BYTES = 130


class F1Command(BaseCommand):
    """Formula 1: next race, standings, results, live, and the prediction game."""

    name = "f1"
    keywords = ["f1"]
    description = "Formula 1: next race, standings, result, live, calendar and the prediction game"
    category = "general"

    short_description = "Formula 1 info and prediction game"
    usage = "f1 [stand|team|uitslag|sprint|weekend|grid|coureur <code>|nu|weer|pit|kalender|voorspel <code>|spel|ik]"
    examples = ["f1", "f1 stand", "f1 uitslag", "f1 weekend", "f1 grid", "f1 coureur VER", "f1 voorspel VER", "f1 ik"]

    def __init__(self, bot: Any):
        super().__init__(bot)
        # Only on when the F1 service is on too (it needs Home Assistant's f1_sensor); otherwise left out of 'help'.
        self.f1_enabled = (self.get_config_value("F1_Command", "enabled", fallback=True, value_type="bool")
                           and self.get_config_value("F1", "enabled", fallback=False, value_type="bool"))

    def can_execute(self, message: MeshMessage, skip_channel_check: bool = False) -> bool:
        if not self.f1_enabled:
            return False
        return super().can_execute(message, skip_channel_check=skip_channel_check)

    def get_help_text(self) -> str:
        return self.translate("commands.f1.help")

    def _arguments(self, message: MeshMessage) -> list:
        tokens = (message.content or "").split()
        for i, token in enumerate(tokens):
            if token.lstrip("!/").lower() in self.keywords:
                return tokens[i + 1:]
        return []

    async def _reply(self, message: MeshMessage, texts: list) -> bool:
        texts = [t for t in texts if t]
        if not texts:
            return False
        if len(texts) == 1:
            return await self.send_response(message, texts[0])
        return await self.send_response_chunked(message, texts[:3])

    async def execute(self, message: MeshMessage) -> bool:
        service = getattr(self.bot, "services", {}).get("f1")
        if service is None:
            return await self.send_response(message, self.translate("commands.f1.service_off"))
        try:
            args = [a.lower() for a in self._arguments(message)]
            sub = args[0] if args else ""
            snap, now = service.snapshot, time.time()
            if not service.last_read:
                why = f" ({service.last_error})" if service.last_error else ""
                return await self.send_response(
                    message, fit(self.translate("commands.f1.no_ha_data", why=why), MAX_BYTES)
                )

            if sub in PREDICT:
                return await self._predict(message, service, snap, args[1:], now)
            if sub in GAME:
                return await self._game(message, service, snap)
            if sub in STAND:
                if not snap["drivers"]:
                    return await self.send_response(message, self.translate("commands.f1.no_standings"))
                head = (
                    self.translate("commands.f1.standings_round_header", round=snap["standings_round"])
                    if snap.get("standings_round") else self.translate("commands.f1.standings_header_bare")
                )
                return await self._reply(message, pack(head, [f"{d['pos']} {d['code']} {d['points']}" for d in snap["drivers"][:10]]))
            if sub in TEAM:
                if not snap["teams"]:
                    return await self.send_response(message, self.translate("commands.f1.no_team_standings"))
                return await self._reply(
                    message,
                    pack(self.translate("commands.f1.constructors_header"), [f"{t['pos']} {t['name']} {t['points']}" for t in snap["teams"][:10]]),
                )
            if sub in ME:
                return await self._me(message, service, snap)
            if sub in WEEKEND:
                return await self._reply(message, weekend_text(snap.get("next"), service.tz, self.translate))
            if sub in SPRINT:
                last = snap.get("sprint")
                if not last:
                    return await self.send_response(message, self.translate("commands.f1.no_sprint"))
                return await self._reply(message, results_text(
                    f"{self.translate('commands.f1.sprint_label')} {gp_name_of(last, self.translate)}", last["results"]))
            if sub in DRIVER:
                if len(args) < 2:
                    return await self.send_response(message, self.translate("commands.f1.driver_usage"))
                d = find_driver(snap, " ".join(args[1:]))
                if not d:
                    return await self.send_response(message, fit(self.translate("commands.f1.driver_unknown", q=" ".join(args[1:])[:20]), MAX_BYTES))
                return await self.send_response(message, driver_text(d, snap, self.translate))
            if sub in GRID:
                return await self._reply(message, grid_text(snap, snap.get("next"), now, service.tz, self.translate))
            if sub in WEATHER or sub in PIT:
                if not live_active(snap):
                    return await self.send_response(message, live_only_text(snap, now, service.tz, self.translate))
                if sub in WEATHER:
                    if not snap.get("weather"):
                        return await self.send_response(message, self.translate("commands.f1.no_weather"))
                    return await self.send_response(message, weather_text(snap, self.translate))
                return await self.send_response(message, pit_text(snap, self.translate))
            if sub in RESULT:
                last = snap.get("last_race")
                if not last:
                    return await self.send_response(message, self.translate("commands.f1.no_result"))
                return await self._reply(
                    message,
                    results_text(f"{self.translate('commands.f1.result_label')} {gp_name_of(last, self.translate)}", last["results"])
                    + [winner_text(last, self.translate)],
                )
            if sub in CALENDAR:
                return await self._reply(message, calendar_text(snap.get("calendar") or [], now, service.tz, self.translate))
            if sub in LIVE:
                lines = now_text(snap, self.translate)
                if lines:
                    return await self._reply(message, lines)
                return await self.send_response(message, live_only_text(snap, now, service.tz, self.translate))
            if sub in ("", "volgende", "next", "race"):
                return await self._reply(message, next_race_text(snap.get("next"), now, service.tz, self.translate))
            return await self.send_response(message, self.translate("commands.f1.usage"))
        except Exception as e:
            self.logger.error(f"Error executing f1 command: {e}")
            return await self.send_response(message, self.translate("commands.f1.error", error=str(e)))

    # ------------------------------------------------------------------ the game
    async def _me(self, message: MeshMessage, service: Any, snap: dict) -> bool:
        """Your own place in the prediction game (by DM: the key says who you are)."""
        if not service.game_enabled or service.game is None:
            return await self.send_response(message, self.translate("commands.f1.game_off"))
        if not message.is_dm:
            return await self.send_response(message, self.translate("commands.f1.me_dm_only"))
        nxt = snap.get("next")
        season = (nxt or {}).get("season") or snap.get("standings_season") or ""
        key = message.sender_pubkey or ""
        pts, races = service.game.points_of(season, key)
        pick = service.game.pick_of(nxt["season"], nxt["round"], key) if nxt else None
        if not races and not pick:
            return await self.send_response(message, self.translate("commands.f1.me_none"))
        table = without_bots(self.bot, service.game.standings(season, 999), 999)
        place = 1 + sum(1 for _n, p, _r in table if p > pts)
        text = self.translate("commands.f1.me", season=season, points=pts, races=races, place=place, players=max(len(table), place))
        text += self.translate("commands.f1.your_pick", pick=pick) if pick else self.translate("commands.f1.no_pick_yet")
        return await self.send_response(message, fit(text, MAX_BYTES))

    async def _predict(self, message: MeshMessage, service: Any, snap: dict, args: list, now: float) -> bool:
        if not service.game_enabled or service.game is None:
            return await self.send_response(message, self.translate("commands.f1.game_off"))
        if not message.is_dm:
            return await self.send_response(message, self.translate("commands.f1.predict_dm_only"))
        nxt = snap.get("next")
        if not nxt:
            return await self.send_response(message, self.translate("commands.f1.no_next_to_predict"))
        if is_bot_name(self.bot, message.sender_id or ""):
            return await self.send_response(message, fit(self.translate("commands.games.no_bots", name=message.sender_id), MAX_BYTES))
        code = " ".join(args[:4])   # one code (the winner) or three (your top 3)
        if not code:
            codes = sorted(service.valid_codes())
            return await self.send_response(
                message,
                fit(
                    self.translate(
                        "commands.f1.predict_prompt", gp=gp_name(nxt, self.translate), example=", ".join(codes[:4]) or "VER"
                    ),
                    MAX_BYTES,
                ),
            )
        ok, text = service.game.predict(
            nxt["season"], nxt["round"], message.sender_pubkey or "", message.sender_id or "", code, now,
            service.lock_ts(), service.valid_codes(), self.translate,
        )
        return await self.send_response(message, fit(text, MAX_BYTES))

    async def _game(self, message: MeshMessage, service: Any, snap: dict) -> bool:
        if not service.game_enabled or service.game is None:
            return await self.send_response(message, self.translate("commands.f1.game_off"))
        nxt = snap.get("next")
        season = (nxt or {}).get("season") or snap.get("standings_season") or ""
        table = without_bots(self.bot, service.game.standings(season, 15), 5)
        parts = []
        if table:
            parts.append(
                self.translate("commands.f1.game_standing")
                + " | ".join(f"{i} {n} {p}" for i, (n, p, _r) in enumerate(table, 1))
            )
        else:
            parts.append(self.translate("commands.f1.no_points_yet"))
        if message.is_dm and nxt:
            pick = service.game.pick_of(nxt["season"], nxt["round"], message.sender_pubkey or "")
            pts, races = service.game.points_of(season, message.sender_pubkey or "")
            parts.append(
                self.translate("commands.f1.your_points", points=pts, races=races)
                + (self.translate("commands.f1.your_pick", pick=pick) if pick else self.translate("commands.f1.no_pick_yet"))
            )
        elif nxt:
            parts.append(self.translate("commands.f1.join_game", gp=gp_name(nxt, self.translate)))
        return await self._reply(message, pack(self.translate("commands.f1.game_header", season=season), parts))
