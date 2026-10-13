#!/usr/bin/env python3
"""
'p2000' command for the MeshCore Bot: P2000 messages on request, in the P2000 card's channel and by DM only.

  p2000            the latest message
  p2000 3          the latest 3 (at most 3, one message each)
  p2000 spoed      the latest priority-1 message (P1, A1, "met spoed")
  p2000 <place>    the latest message for a place (or a word in the text), e.g. p2000 heerlen
  p2000 vandaag    how often fire brigade, ambulance and police were called out in the last 24 hours

The data comes from the P2000 service (Plugins -> P2000, modules/p2000.py); the messages themselves are Dutch.
"""

import time
from typing import Any

from ..models import MeshMessage
from .base_command import BaseCommand

URGENT = {"spoed", "prio", "prio1", "p1", "a1", "urgent", "priority"}
TODAY = {"vandaag", "today", "heute", "telling", "count", "stats", "dag"}


class P2000Command(BaseCommand):
    """P2000 messages on request."""

    name = "p2000"
    keywords = ["p2000"]
    description = "P2000 messages on request: the latest, a place, only urgent ones, or today's count"
    category = "general"

    short_description = "P2000 messages on request"
    usage = "p2000 [3|spoed|<plaats>|vandaag]"
    examples = ["p2000", "p2000 3", "p2000 spoed", "p2000 heerlen", "p2000 vandaag"]

    def __init__(self, bot: Any):
        super().__init__(bot)
        # Only with the P2000 card on; it also decides the one channel where the command works (and DMs).
        self.p2000_enabled = (self.get_config_value("P2000_Command", "enabled", fallback=True, value_type="bool")
                              and self.get_config_value("P2000", "enabled", fallback=False, value_type="bool"))
        if self.allowed_channels is None:
            channel = (self.get_config_value("P2000", "channel", fallback="#p2000") or "#p2000").strip()
            self.allowed_channels = [channel.lower() if channel.startswith("#") else channel]

    def can_execute(self, message: MeshMessage, skip_channel_check: bool = False) -> bool:
        if not self.p2000_enabled:
            return False
        return super().can_execute(message, skip_channel_check=skip_channel_check)

    def get_help_text(self) -> str:
        return self.translate("commands.p2000.help")

    def _arguments(self, message: MeshMessage) -> list:
        tokens = (message.content or "").split()
        for i, token in enumerate(tokens):
            if token.lstrip("!/").lower() in self.keywords:
                return tokens[i + 1:]
        return []

    def answer(self, message: MeshMessage, now: float = None) -> list:
        from .. import p2000 as P
        now = time.time() if now is None else now
        args = self._arguments(message)
        word = " ".join(args).strip().lower()
        with self.bot.db_manager.connection() as conn:
            if word in TODAY:
                return [P.summary_text(P.counts(conn, now - 86400, now), self.translate)]
            if word.isdigit():
                rows = P.latest(conn, int(word))
            elif word in URGENT:
                rows = P.latest(conn, 1, prio1=True)
            elif word:
                rows = P.latest(conn, 1, place=word)
            else:
                rows = P.latest(conn, 1)
        if not rows:
            return [self.translate("commands.p2000.none_place", place=" ".join(args)) if word and not word.isdigit()
                    and word not in URGENT else self.translate("commands.p2000.none")]
        return [P.line(m, with_date=(now - m["ts"] > 20 * 3600)) for m in rows]

    async def execute(self, message: MeshMessage) -> bool:
        try:
            texts = self.answer(message)
        except Exception as e:  # noqa: BLE001
            self.logger.error(f"Error executing p2000 command: {e}")
            return await self.send_response(message, self.translate("commands.p2000.none"))
        if len(texts) == 1:
            return await self.send_response(message, texts[0])
        return await self.send_response_chunked(message, texts)
