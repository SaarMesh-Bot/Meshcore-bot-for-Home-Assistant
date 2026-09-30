#!/usr/bin/env python3
"""RepeaterWatch: says when a repeater the bot's radio hears directly goes silent, and when it is back (card: Plugins ->
RepeaterWatch, on by default).

Watched: the direct neighbours of the last 7 days (neighbour discovery, see the BotNetwork or PacketCapture card) and
the repeaters named on the card (name or key prefix). A repeater counts as heard when the bot hears its advert or
neighbour discovery finds it. When one has not been heard for "Silent after" hours, the bot logs a warning
("RepeaterWatch: stil: ..."), which the Notifications card passes on to your room, channel or DM like the other repeater
warnings, and it can put a notification in Home Assistant. Once per silence; "weer gehoord" when it is back. Checked
every hour; nothing is sent over the radio for the check itself.
"""
import asyncio
import json
import os
import time
from typing import Any, Optional

from .base_service import BaseServicePlugin

STATE_KEY = "repeaterwatch.state"
CHECK_EVERY_S = 3600
FIRST_S = 600


def _names(raw: Any) -> list:
    return [n.strip().lower() for n in str(raw or "").strip("[]").replace("'", "").split(",") if n.strip()]


def watched(db: Any, extra: list) -> dict:
    """{key(12 hex): {name, last_heard(ts)}} of the repeaters to watch."""
    out: dict = {}
    with db.connection() as conn:
        tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        if "neighbor_links" in tables:
            for key, seen in conn.execute("SELECT neighbor_public_key, CAST(strftime('%s', MAX(last_seen)) AS INTEGER) "
                                          "FROM neighbor_links WHERE last_seen >= datetime('now', '-7 day') GROUP BY neighbor_public_key"):
                out[str(key).lower()[:12]] = {"name": "", "last_heard": seen or 0}
        if "complete_contact_tracking" in tables:
            rows = conn.execute("SELECT public_key, name, CAST(strftime('%s', last_heard) AS INTEGER) FROM complete_contact_tracking "
                                "WHERE LOWER(role) = 'repeater'").fetchall()
            for key, name, heard in rows:
                k = str(key).lower()[:12]
                wanted = k in out or any((name or "").lower() == e or k.startswith(e) for e in extra)
                if wanted:
                    item = out.setdefault(k, {"name": "", "last_heard": 0})
                    item["name"] = name or item["name"]
                    item["last_heard"] = max(item["last_heard"] or 0, heard or 0)
    return out


def check(db: Any, extra: list, silent_s: int, now: Optional[float] = None) -> list:
    """[(kind, key, name, last_heard)] with kind 'silent' (just went silent) or 'back'; remembers what it reported."""
    now = time.time() if now is None else now
    try:
        state = json.loads(db.get_metadata(STATE_KEY) or "{}")
    except ValueError:
        state = {}
    events = []
    for key, item in watched(db, extra).items():
        silent = item["last_heard"] and now - item["last_heard"] >= silent_s
        if silent and key not in state:
            state[key] = int(now)
            events.append(("silent", key, item["name"] or key[:6], item["last_heard"]))
        elif not silent and key in state:
            del state[key]
            events.append(("back", key, item["name"] or key[:6], item["last_heard"]))
    db.set_metadata(STATE_KEY, json.dumps(state))
    return events


class RepeaterWatchService(BaseServicePlugin):
    config_section = "RepeaterWatch"
    name = "repeaterwatch"
    description = "Says when a repeater your radio hears directly goes silent (and when it is back), via Notifications and Home Assistant"

    settings_schema = [
        {"key": "silent_hours", "label": "Silent after", "type": "int", "default": 24, "min": 2, "max": 168, "unit": "h",
         "help": "Hours without its advert or a neighbour-discovery reply. Many repeaters send a flood advert every 12 hours."},
        {"key": "extra", "label": "Also watch", "type": "list", "default": [],
         "help": "Repeater names or key prefixes to watch as well, also when they are not direct neighbours."},
        {"key": "ha_notification", "label": "Notification in Home Assistant", "type": "bool", "default": True,
         "help": "Also put a notification in Home Assistant (next to the Notifications card's room/channel/DM)."},
    ]

    def __init__(self, bot: Any):
        super().__init__(bot)
        cfg = bot.config
        has = cfg.has_section("RepeaterWatch")
        try:
            hours = int(cfg.get("RepeaterWatch", "silent_hours", fallback="24") or 24) if has else 24
        except ValueError:
            hours = 24
        self.silent_s = max(2, min(168, hours)) * 3600
        self.extra = _names(cfg.get("RepeaterWatch", "extra", fallback="") if has else "")
        self.ha_notification = cfg.getboolean("RepeaterWatch", "ha_notification", fallback=True) if has else True
        self._task: Optional[asyncio.Task] = None

    async def start(self) -> None:
        self._running = True
        cfg = self.bot.config
        if not (cfg.has_section("RepeaterWatch") and cfg.getboolean("RepeaterWatch", "enabled", fallback=False)):
            return
        self._task = asyncio.get_running_loop().create_task(self._loop())

    async def stop(self) -> None:
        self._running = False
        if self._task is not None:
            self._task.cancel()
            self._task = None

    async def _loop(self) -> None:
        await asyncio.sleep(FIRST_S)
        while self._running:
            try:
                await self.run_check()
            except asyncio.CancelledError:
                raise
            except Exception as e:  # noqa: BLE001
                self.logger.debug("RepeaterWatch: controle mislukt: %s", e)
            await asyncio.sleep(CHECK_EVERY_S)

    async def run_check(self, now: Optional[float] = None) -> list:
        events = await asyncio.to_thread(check, self.bot.db_manager, self.extra, self.silent_s, now)
        for kind, _key, name, last in events:
            when = time.strftime("%d-%m %H:%M", time.localtime(last)) if last else "?"
            if kind == "silent":
                text = f"stil: {name} niet meer gehoord sinds {when}"
                self.logger.warning("RepeaterWatch: %s", text)
            else:
                text = f"weer gehoord: {name}"
                self.logger.info("RepeaterWatch: %s", text)
            if self.ha_notification:
                await self._ha_notify(kind, name, text)
        return events

    async def _ha_notify(self, kind: str, name: str, text: str) -> None:
        token = os.environ.get("SUPERVISOR_TOKEN", "")
        if not token:
            return
        try:
            import aiohttp
            nid = f"meshcore_repeater_{name}".lower().replace(" ", "_")[:60]
            if kind == "silent":
                url, body = "http://supervisor/core/api/services/persistent_notification/create", {
                    "title": "MeshCore: repeater stil", "message": f"Repeater {text}.", "notification_id": nid}
            else:
                url, body = "http://supervisor/core/api/services/persistent_notification/dismiss", {"notification_id": nid}
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=15)) as s:
                async with s.post(url, json=body, headers={"Authorization": f"Bearer {token}"}) as resp:
                    if resp.status not in (200, 201):
                        self.logger.debug("RepeaterWatch: Home Assistant antwoordde HTTP %s", resp.status)
        except Exception as e:  # noqa: BLE001
            self.logger.debug("RepeaterWatch: melding in Home Assistant mislukt: %s", e)
