#!/usr/bin/env python3
"""DEWarn: new DWD weather warnings and NINA civil-protection warnings in a channel (card: Plugins -> DEWarn, off by
default). Ported from the SaarMesh bot, where this runs in #warnings.

Every few minutes: DWD warnings for the federal states on the card (default SL) and NINA warnings for the districts on
the card (default the six of the Saarland), merged (NINA's copies of DWD weather warnings dropped) and compared with
what was posted before. New ones go out as one compact block ("🚨 Warnung" + one line each, packed into as few
messages as fit). A NINA all-clear for something that was posted before goes out as "✅ Entwarnung: ...". Nothing old
is posted after a start: the first round only remembers. A warning that is still active is never posted twice; it is
forgotten a day after it left the feeds. The mesh is an extra way to hear about a warning, never the official one.
"""
import asyncio
import json
import time
from typing import Any, Optional

from .base_service import BaseServicePlugin

SEEN_KEY = "dewarn.seen"          # {key: last time it was in a feed}
CLEARED_KEY = "dewarn.cleared"    # {cancel prefix: when the all-clear went out}
FORGET_S = 24 * 3600
GAP_S = 3
POINTER_EVERY_S = 3600    # pointer channels hear about new warnings at most once an hour


class DEWarnService(BaseServicePlugin):
    config_section = "DEWarn"
    name = "dewarn"
    description = "New DWD weather warnings and NINA warnings (Germany) in a channel, with all-clears"

    settings_schema = [
        {"key": "channel", "label": "Channels", "type": "str", "default": "#warnings",
         "help": "Where the warnings go; several comma-separated, e.g. #warnings, #saarland."},
        {"key": "states", "label": "Federal states (DWD)", "type": "str", "default": "SL",
         "help": "Two-letter codes, comma-separated, e.g. SL or SL, RP. Empty = all of Germany (a lot)."},
        {"key": "districts", "label": "Districts (NINA)", "type": "str", "default": "10041,10042,10043,10044,10045,10046",
         "help": "The first 5 digits of the Amtlicher Regionalschlüssel (ARS) per district, optionally with a name: "
                 "10044=Saarlouis. Default: the six districts of the Saarland."},
        {"key": "min_level", "label": "Minimum DWD level", "type": "int", "default": 2, "min": 1, "max": 4,
         "help": "1 = also minor warnings, 2 = from 'markant' (default), 3 = severe weather only, 4 = extreme only."},
        {"key": "max_dwd", "label": "At most DWD lines per post", "type": "int", "default": 6, "min": 1, "max": 20},
        {"key": "all_clear", "label": "Post all-clears", "type": "bool", "default": True,
         "help": "A NINA all-clear for a warning that was posted before goes out as 'Entwarnung'."},
        {"key": "poll_seconds", "label": "Check every (s)", "type": "int", "default": 300, "min": 120, "max": 1800},
        {"key": "pointer_channels", "label": "Pointer channels", "type": "str", "default": "",
         "help": "Channels that get a one-line pointer ('Warnings active ... see #warnings') when new warnings were "
                 "posted, at most once an hour; comma-separated, e.g. Public, #saarland. Empty = no pointer."},
    ]

    def __init__(self, bot: Any):
        super().__init__(bot)
        from ..de_warn import settings
        self.s = settings(bot.config, self.config_section)
        self.channels = self.s["channels"]
        self.channel = ", ".join(self.channels)
        cfg = bot.config
        language = cfg.get("Localization", "language", fallback="en") if cfg.has_section("Localization") else "en"
        get_translator = getattr(bot, "get_translator", None)
        try:
            self.translate = get_translator(language).translate if get_translator else bot.translator.translate
        except Exception:  # noqa: BLE001
            self.translate = bot.translator.translate
        raw = (cfg.get(self.config_section, "pointer_channels", fallback="")
               if cfg.has_section(self.config_section) else "") or ""
        self.pointer_channels = []
        for n in raw.replace(";", ",").split(","):
            n = n.strip()
            n = n.lower() if n.startswith("#") else n
            if n and n not in self.pointer_channels and n not in self.channels:
                self.pointer_channels.append(n)
        self._last_pointer = 0.0
        self._task: Optional[asyncio.Task] = None
        self._first_run = True
        self.last_error = ""

    # ------------------------------------------------------------------ lifecycle
    async def start(self) -> None:
        self._running = True
        self._task = asyncio.create_task(self._loop())
        self.logger.info("DEWarn: gestartet (Kanal %s, Länder %s, Kreise %s)", self.channel,
                         ", ".join(self.s["states"]) or "alle", ", ".join(self.s["districts"]))

    async def stop(self) -> None:
        self._running = False
        if self._task:
            self._task.cancel()

    async def _loop(self) -> None:
        await asyncio.sleep(30)
        while self._running:
            try:
                await self.tick()
            except asyncio.CancelledError:
                raise
            except Exception as e:  # noqa: BLE001
                self.logger.warning("DEWarn: %s", e)
            await asyncio.sleep(self.s["poll_seconds"])

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
            self.logger.debug("DEWarn: speichern fehlgeschlagen: %s", e)

    # ------------------------------------------------------------------ work
    async def fetch(self, now_dt) -> tuple:
        """(dwd_items or None, nina_items, cancels, nina_ok)."""
        from .. import de_fetch, de_warn as W
        dwd_data = await de_fetch.dwd(now_dt)
        nina, cancels, reached = await de_fetch.nina(self.s["districts"], now_dt, self.s["tokens"])
        dwd = W.dwd_items(dwd_data, self.s["states"], now_dt, self.s["min_level"]) if dwd_data is not None else None
        return dwd, nina, cancels, reached == len(self.s["districts"])

    async def tick(self, now: Optional[float] = None, fetched: Optional[tuple] = None) -> int:
        """One round. Returns the number of messages sent."""
        from .. import de_warn as W
        from ..mesh_community import local_now
        now = time.time() if now is None else now
        now_dt = local_now(self.bot, now)
        dwd, nina, cancels, nina_ok = fetched if fetched is not None else await self.fetch(now_dt)
        if dwd is None and not nina and not nina_ok:
            if self.last_error != "unreachable":
                self.logger.info("DEWarn: DWD und NINA nicht erreichbar")
            self.last_error = "unreachable"
            return 0
        self.last_error = ""

        seen = {k: float(v) for k, v in self._meta(SEEN_KEY, {}).items()}
        cleared = {k: float(v) for k, v in self._meta(CLEARED_KEY, {}).items() if now - float(v) < FORGET_S}
        first = self._first_run and not seen
        self._first_run = False

        if dwd is None:
            # without DWD its copies in NINA cannot be matched; they would come out twice once DWD is back
            nina = [n for n in nina if not n.get("is_dwd")]
        items = W.merge(dwd or [], nina, self.s["max_dwd"])
        new = [i for i in items if i["key"] not in seen]
        for i in items:
            seen[i["key"]] = now
        # A source that could not be read keeps its keys alive, so they are not posted again when it comes back.
        alive = {i["key"] for i in items}
        for k in list(seen):
            if k in alive:
                continue
            src_down = (k.startswith("dwd::") and dwd is None) or (k.startswith("nina::") and not nina_ok)
            if src_down:
                seen[k] = now
            elif now - seen[k] > FORGET_S:
                del seen[k]

        sent = 0
        if not first and new:
            header = self.translate("services.dewarn.header", count=len(new))
            for i, part in enumerate(W.split_lines(header, [n["text"] for n in new])[:4]):
                if i:
                    await asyncio.sleep(GAP_S)
                if await self._send(part):
                    sent += 1
            self.logger.info("DEWarn: %d neue Warnung(en) gepostet in %s", len(new), self.channel)
            if sent and self.pointer_channels and now - self._last_pointer >= POINTER_EVERY_S:
                self._last_pointer = now
                text = self.translate("services.dewarn.pointer", channel=self.channels[0])
                for ch in self.pointer_channels:
                    await asyncio.sleep(GAP_S)
                    try:
                        await self.bot.command_manager.send_channel_message(ch, text, skip_user_rate_limit=True)
                    except Exception as e:  # noqa: BLE001
                        self.logger.info("DEWarn: Hinweis an %s fehlgeschlagen: %s", ch, e)

        if self.s["all_clear"] and not first:
            for prefix, label in cancels:
                if prefix in cleared:
                    continue
                cleared[prefix] = now
                # only an all-clear for something we posted (and that is no longer active)
                if any(k.startswith(prefix) for k in seen) and not any(k.startswith(prefix) for k in alive):
                    if await self._send(self.translate("services.dewarn.all_clear", what=label)):
                        sent += 1
                    for k in [k for k in seen if k.startswith(prefix)]:
                        del seen[k]
        elif first:
            for prefix, _label in cancels:
                cleared[prefix] = now

        self._set_meta(SEEN_KEY, seen)
        self._set_meta(CLEARED_KEY, cleared)
        return sent

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
                    self.logger.info("DEWarn: senden an %s fehlgeschlagen", channel)
            except Exception as e:  # noqa: BLE001
                self.logger.info("DEWarn: senden an %s fehlgeschlagen: %s", channel, e)
        return ok
