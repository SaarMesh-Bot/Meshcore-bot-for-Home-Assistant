"""Counters for upstream's MapUploader (see local_patches/patch_map_uploader_counts.py): per day how many nodes were
sent to map.meshcore.dev, how many were new there, how many the map already had, and how many failed. Replaces two
log lines per upload with one summary line an hour; the Repeater radar shows today's numbers in a tile.
"""
from __future__ import annotations

import time
from typing import Any, Optional

KINDS = ("sent", "new", "duplicate", "failed")
SCHEMA = """CREATE TABLE IF NOT EXISTS map_uploads (
    day TEXT PRIMARY KEY, sent INTEGER NOT NULL DEFAULT 0, new INTEGER NOT NULL DEFAULT 0,
    duplicate INTEGER NOT NULL DEFAULT 0, failed INTEGER NOT NULL DEFAULT 0)"""


def _day(now: float) -> str:
    return time.strftime("%Y-%m-%d", time.localtime(now))


def record(db: Any, kind: str, now: Optional[float] = None) -> None:
    if kind not in KINDS:
        return
    now = time.time() if now is None else now
    with db.connection() as conn:
        conn.execute(SCHEMA)
        conn.execute(f"INSERT INTO map_uploads (day, {kind}) VALUES (?, 1) ON CONFLICT(day) DO UPDATE SET {kind} = {kind} + 1",
                     (_day(now),))
        conn.commit()


def totals(db: Any, days: int = 1, now: Optional[float] = None) -> Optional[dict]:
    """{sent, new, duplicate, failed} over the last `days` days (today = 1), or None when MapUploader never ran."""
    now = time.time() if now is None else now
    with db.connection() as conn:
        if not conn.execute("SELECT 1 FROM sqlite_master WHERE name = 'map_uploads'").fetchone():
            return None
        since = _day(now - (days - 1) * 86400)
        row = conn.execute("SELECT COALESCE(SUM(sent),0), COALESCE(SUM(new),0), COALESCE(SUM(duplicate),0), COALESCE(SUM(failed),0), "
                           "COUNT(*) FROM map_uploads WHERE day >= ?", (since,)).fetchone()
    return dict(zip(KINDS, row[:4]))


class HourlySummary:
    """Counts in memory and says once an hour in the log what happened in the previous hour."""

    def __init__(self):
        self.hour: Optional[int] = None
        self.counts = dict.fromkeys(KINDS, 0)

    def add(self, kind: str, logger: Any, now: Optional[float] = None) -> None:
        now = time.time() if now is None else now
        hour = int(now // 3600)
        if self.hour is not None and hour != self.hour and self.counts["sent"]:
            c = self.counts
            logger.info("Kaart: afgelopen uur %d knopen naar map.meshcore.dev gestuurd, %d nieuw, %d had de kaart al, %d mislukt",
                        c["sent"], c["new"], c["duplicate"], c["failed"])
            self.counts = dict.fromkeys(KINDS, 0)
        elif self.hour is not None and hour != self.hour:
            self.counts = dict.fromkeys(KINDS, 0)
        self.hour = hour
        self.counts[kind] = self.counts.get(kind, 0) + 1
