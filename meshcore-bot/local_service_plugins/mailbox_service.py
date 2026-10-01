#!/usr/bin/env python3
"""Mailbox: delivers the messages left with 'post' by DM as soon as the bot hears the recipient again (card:
Plugins -> Mailbox, on by default). Checked every 2 minutes; a DM goes out only when the recipient has written
something or sent an advert after the message was left, and is on the radio's contact list (found by name, exactly
one match). Not while night mode is on. See modules/mailbox.py.
"""
import asyncio
import time
from typing import Any, Optional

from .base_service import BaseServicePlugin

CHECK_EVERY_S = 120
MAX_PER_ROUND = 3


class MailboxService(BaseServicePlugin):
    config_section = "Mailbox"
    name = "mailbox"
    description = "Delivers messages left with 'post' by DM as soon as the bot hears the recipient again"
    settings_schema: list = []

    def __init__(self, bot: Any):
        super().__init__(bot)
        self._task: Optional[asyncio.Task] = None
        cfg = bot.config
        get_translator = getattr(bot, "get_translator", None)
        language = cfg.get("Localization", "language", fallback="en") if cfg.has_section("Localization") else "en"
        try:
            self.translate = get_translator(language).translate if get_translator else bot.translator.translate
        except Exception:  # noqa: BLE001
            self.translate = bot.translator.translate

    async def start(self) -> None:
        self._running = True
        cfg = self.bot.config
        if not (cfg.has_section("Mailbox") and cfg.getboolean("Mailbox", "enabled", fallback=False)):
            return
        self._task = asyncio.get_running_loop().create_task(self._loop())

    async def stop(self) -> None:
        self._running = False
        if self._task is not None:
            self._task.cancel()
            self._task = None

    async def _loop(self) -> None:
        await asyncio.sleep(60)
        while self._running:
            try:
                await self.deliver()
            except asyncio.CancelledError:
                raise
            except Exception as e:  # noqa: BLE001
                self.logger.debug("Mailbox: %s", e)
            await asyncio.sleep(CHECK_EVERY_S)

    def _contact_key(self, name: str) -> str:
        contacts = getattr(getattr(self.bot, "meshcore", None), "contacts", None) or {}
        keys = [str(c.get("public_key") or k).lower() for k, c in contacts.items()
                if isinstance(c, dict) and (c.get("adv_name") or c.get("name") or "").strip().lower() == name.strip().lower()]
        return keys[0] if len(keys) == 1 else ""

    async def deliver(self, now: Optional[float] = None) -> int:
        now = time.time() if now is None else now
        try:
            from ..night_mode import is_night
            if is_night(self.bot, now):
                return 0
        except Exception:  # noqa: BLE001
            pass
        cm = getattr(self.bot, "command_manager", None)
        if cm is None or not getattr(self.bot, "connected", False):
            return 0
        from .. import mailbox
        sent = 0
        for m in (await asyncio.to_thread(mailbox.due, self.bot.db_manager, now))[:MAX_PER_ROUND]:
            key = self._contact_key(m["to_name"])
            if not key:
                continue
            text = self.translate("commands.post.delivery", name=m["from_name"], ago=mailbox.ago(m["created"], self.translate, now),
                                  text=m["text"])
            if await cm.send_dm(key, text, skip_user_rate_limit=True):
                mailbox.delivered(self.bot.db_manager, m["id"], now)
                sent += 1
                self.logger.info(f"Mailbox: bericht van {m['from_name']} bezorgd bij {m['to_name']}")
        return sent
