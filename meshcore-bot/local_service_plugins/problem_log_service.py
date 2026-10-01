#!/usr/bin/env python3
"""ProblemLog: keeps the bot's warnings and errors in its database, per day and per kind, for the dashboard page
Settings -> Problems (card: Plugins -> ProblemLog, on by default). See modules/problem_log.py. Nothing is sent over
the radio; the log itself stays as it is.
"""
from typing import Any

from .base_service import BaseServicePlugin


class ProblemLogService(BaseServicePlugin):
    config_section = "ProblemLog"
    name = "problemlog"
    description = "Keeps the bot's warnings and errors (14 days) for the dashboard page Settings -> Problems"
    settings_schema: list = []

    def __init__(self, bot: Any):
        super().__init__(bot)
        self._handler = None

    async def start(self) -> None:
        self._running = True
        cfg = self.bot.config
        if not (cfg.has_section("ProblemLog") and cfg.getboolean("ProblemLog", "enabled", fallback=False)):
            return
        from ..problem_log import install
        db_path = str(getattr(self.bot.db_manager, "db_path", "") or "")
        if db_path:
            self._handler = install(self.bot.logger, db_path)

    async def stop(self) -> None:
        self._running = False
        if self._handler is not None:
            try:
                self.bot.logger.removeHandler(self._handler)
            except Exception:  # noqa: BLE001
                pass
            self._handler = None
