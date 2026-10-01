#!/usr/bin/env python3
"""FarmDaily: once a day the Farming Idle's task of the day in the games channel (card: Plugins -> FarmDaily, on by default).

The task is the same for everyone (harvest, process or sell; see modules/farm_game.py) and each player's amount grows
with their level, so the post says what the task is and points to `farm opdracht` (by DM) for your own goal. Posted
at "Time" (default 06:00, local time) in the channel on the card, or else the channel of the GamesChannel card; not
at all when neither is set. While nobody plays yet, the post is an invitation to start ("DM me farm start"). At
"Invitation at" (default 14:00) an invitation to join goes out every day, to get more players (not when the morning post
was one already). At "Market buys at" (default 12:00) a separate post lists what the market buys (the buy orders set
on the dashboard, Games -> Farming Idle), only on days with an open order. With night mode on, a post waits until the night
is over.
"""
import asyncio
import time
from typing import Any, Optional

from .base_service import BaseServicePlugin

POSTED_KEY = "farm.daily_posted"
INVITED_KEY = "farm.invite_posted"
ORDERS_KEY = "farm.orders_posted"
SEASON_KEY = "farm.season_announced"
MAX_BYTES = 130
CHECK_EVERY_S = 60


class FarmDailyService(BaseServicePlugin):
    config_section = "FarmDaily"
    name = "farmdaily"
    description = "Posts the Farming Idle's task of the day (06:00), an invitation (14:00) and what the market buys (12:00) in the games channel"

    settings_schema = [
        {"key": "time", "label": "Time", "type": "str", "default": "06:00", "pattern": "[0-2][0-9]:[0-5][0-9]",
         "help": "Local time (Bot > Time zone), HH:MM. With night mode on, the post waits until the night is over."},
        {"key": "invite_time", "label": "Invitation at", "type": "str", "default": "14:00",
         "help": "Local time, HH:MM: an invitation to start playing, every day (also when people play, to get more players). "
                 "Empty = no invitation. Skipped on a day whose morning post was already an invitation."},
        {"key": "orders_time", "label": "Market buys at", "type": "str", "default": "12:00",
         "help": "Local time, HH:MM: what the market buys (the buy orders on the dashboard, Games -> Farming Idle). Only on days "
                 "with an open order. Empty = never."},
        {"key": "channel", "label": "Channel", "type": "str", "default": "",
         "help": "Empty = the channel of the GamesChannel card. The post goes nowhere when neither is set."},
    ]

    def __init__(self, bot: Any):
        super().__init__(bot)
        cfg = bot.config
        has = cfg.has_section("FarmDaily")
        raw = (cfg.get("FarmDaily", "time", fallback="06:00") if has else "06:00") or "06:00"
        self.minute_of_day = self._minutes(raw, 6 * 60)
        invite = (cfg.get("FarmDaily", "invite_time", fallback="14:00") if has else "14:00")
        self.invite_minute = self._minutes(invite, None) if str(invite or "").strip() else None
        orders = (cfg.get("FarmDaily", "orders_time", fallback="12:00") if has else "12:00")
        self.orders_minute = self._minutes(orders, None) if str(orders or "").strip() else None
        self.channel_setting = ((cfg.get("FarmDaily", "channel", fallback="") if has else "") or "").strip()
        self._task: Optional[asyncio.Task] = None
        get_translator = getattr(bot, "get_translator", None)
        language = cfg.get("Localization", "language", fallback="en") if cfg.has_section("Localization") else "en"
        try:
            self.translate = get_translator(language).translate if get_translator else bot.translator.translate
        except Exception:  # noqa: BLE001
            self.translate = bot.translator.translate

    @staticmethod
    def _minutes(raw: str, fallback):
        try:
            h, m = (int(x) for x in str(raw).strip().split(":"))
            return max(0, min(23, h)) * 60 + max(0, min(59, m))
        except ValueError:
            return fallback

    def channel(self) -> str:
        if self.channel_setting:
            return self.channel_setting
        cfg = self.bot.config
        if cfg.has_section("GamesChannel") and cfg.getboolean("GamesChannel", "enabled", fallback=False):
            return (cfg.get("GamesChannel", "channel", fallback="") or "").strip()
        return ""

    async def start(self) -> None:
        self._running = True
        cfg = self.bot.config
        if not (cfg.has_section("FarmDaily") and cfg.getboolean("FarmDaily", "enabled", fallback=False)):
            return
        self._task = asyncio.get_running_loop().create_task(self._loop())

    async def stop(self) -> None:
        self._running = False
        if self._task is not None:
            self._task.cancel()
            self._task = None

    async def _loop(self) -> None:
        while self._running:
            try:
                await self.tick()
            except asyncio.CancelledError:
                raise
            except Exception as e:  # noqa: BLE001
                self.logger.debug("FarmDaily: %s", e)
            await asyncio.sleep(CHECK_EVERY_S)

    def _players(self) -> int:
        try:
            with self.bot.db_manager.connection() as conn:
                if not conn.execute("SELECT 1 FROM sqlite_master WHERE name='farm_players'").fetchone():
                    return 0
                return conn.execute("SELECT COUNT(*) FROM farm_players").fetchone()[0]
        except Exception:  # noqa: BLE001
            return 0

    def orders_text(self, now: float) -> Optional[str]:
        """'Market buys: ...' with the open buy orders (best price first), as many as fit in one message; None without."""
        try:
            with self.bot.db_manager.connection() as conn:
                if not conn.execute("SELECT 1 FROM sqlite_master WHERE name='farm_orders'").fetchone():
                    return None
            from ..farm_game import FarmGame
            game = FarmGame(self.bot.db_manager)
            with self.bot.db_manager.connection() as conn:
                orders = game._open_orders(conn, now)
        except Exception:  # noqa: BLE001
            return None
        if not orders:
            return None
        t = self.translate
        parts = [t("commands.farm.order_item", qty=o["qty"] - o["filled"], item=game._goods_name(o["item"], t), price=o["price"])
                 for o in orders]
        text = t("commands.farm.daily_orders", items=parts[0])
        for n in range(len(parts), 0, -1):
            candidate = t("commands.farm.daily_orders", items=", ".join(parts[:n]))
            if len(candidate.encode()) <= MAX_BYTES:
                return candidate
        return text

    def _invite(self) -> str:
        name = (self.bot.config.get("Bot", "bot_name", fallback="") or "").strip() or "de bot"
        return self.translate("commands.farm.daily_invite", bot=name)

    def due(self, now: Optional[float] = None) -> Optional[tuple]:
        """(metadata key, text) to post now, or None (not time yet, already posted today, no channel, night).
        Morning: the task of the day (an invitation while nobody plays). Afternoon: an invitation to join, unless the
        morning post was one already."""
        now = time.time() if now is None else now
        from ..mesh_community import local_now
        local = local_now(self.bot, now)
        day, minute = local.date().isoformat(), local.hour * 60 + local.minute
        if not self.channel():
            return None
        try:
            from ..night_mode import is_night
            if is_night(self.bot, now):
                return None
        except Exception:  # noqa: BLE001
            pass
        db = self.bot.db_manager
        if minute >= self.minute_of_day and self._players():
            # a season (calendar month) that just ended: the winners, once, before the morning task
            from ..farm_game import FarmGame
            game = FarmGame(db)
            game.season_roll(now)
            prev = game.last_closed_season()
            if prev and db.get_metadata(SEASON_KEY) != prev:
                text = game.season_announcement(prev, self.translate)
                if text:
                    return SEASON_KEY + ":" + prev, text
                db.set_metadata(SEASON_KEY, prev)
        if minute >= self.minute_of_day and db.get_metadata(POSTED_KEY) != day:
            if not self._players():
                return POSTED_KEY, self._invite()   # nobody plays yet: an invitation instead
            from ..farm_game import FarmGame
            return POSTED_KEY, self.translate(f"commands.farm.daily_post.{FarmGame.task_of_day(now)}")
        if (self.invite_minute is not None and minute >= self.invite_minute and db.get_metadata(INVITED_KEY) != day
                and db.get_metadata(POSTED_KEY) == day and db.get_metadata(POSTED_KEY + ".kind") != "invite"):
            return INVITED_KEY, self._invite()
        if self.orders_minute is not None and minute >= self.orders_minute and db.get_metadata(ORDERS_KEY) != day:
            text = self.orders_text(now)
            if text:
                return ORDERS_KEY, text
        return None

    async def tick(self, now: Optional[float] = None) -> bool:
        todo = self.due(now)
        if not todo:
            return False
        key, text = todo
        cm = getattr(self.bot, "command_manager", None)
        if cm is None or not getattr(self.bot, "connected", False):
            return False
        ok = bool(await cm.send_channel_message(self.channel(), text, skip_user_rate_limit=True))
        if ok and key.startswith(SEASON_KEY + ":"):
            self.bot.db_manager.set_metadata(SEASON_KEY, key.split(":", 1)[1])
            self.logger.info("FarmDaily: seizoensuitslag gepost in %s", self.channel())
            return ok
        if ok:
            from ..mesh_community import local_now
            db = self.bot.db_manager
            db.set_metadata(key, local_now(self.bot, now).date().isoformat())
            if key == POSTED_KEY:
                db.set_metadata(POSTED_KEY + ".kind", "invite" if text == self._invite() else "task")
            self.logger.info("FarmDaily: %s gepost in %s", {INVITED_KEY: "uitnodiging", ORDERS_KEY: "inkooporders"}.get(key, "ochtendbericht"), self.channel())
        return ok
