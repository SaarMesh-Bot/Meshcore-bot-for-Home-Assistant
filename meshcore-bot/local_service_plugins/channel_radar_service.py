#!/usr/bin/env python3
"""Kanaalradar service: counts which hashtag channels are in use around the bot (card: Plugins -> ChannelRadar,
page: Channel radar on the dashboard). See modules/channel_radar.py for how a channel is recognised.

Every minute it reads the packets the bot has logged since last time (table packet_stream, which the dashboard also
uses; the first run takes the last days that are still there), checks every group message against the channel names
(and the channels on the radio, with their own keys, private ones included) and adds it to that channel's count for the day. When the list of names changes (a new version, names added on the
card), the days that are still in the packet log are counted again with the new list, so a new name counts from the
start of that log, not only from now (whole days only: the first, partial day of the log keeps its counts). The same message heard via several repeaters counts once. It only
reads the bot's own database: nothing is sent and no message is decrypted.
"""
import asyncio
import json
import time
from datetime import timedelta
from typing import Any, Optional

from ..channel_radar import (DEFAULT_NAMES, build_table, ensure_tables, generated_names, identify, names_signature, radio_channels,
                             radio_signature, record)
from ..mesh_community import day_start_ts, local_day, table_exists
from .base_service import BaseServicePlugin

CHECK_EVERY_S = 60
LAST_ID_KEY = "radar.last_id"
NAMES_KEY = "radar.names"
DEDUP_WINDOW_S = 3600
MAX_ROWS_PER_RUN = 20000


class ChannelRadarService(BaseServicePlugin):
    config_section = "ChannelRadar"
    name = "channelradar"
    description = "Counts which hashtag channels are in use around the bot (group messages, never decrypted); see the Channel radar page"

    settings_schema = [
        {"key": "extra_names", "label": "Extra channel names to look for", "type": "list", "default": [],
         "help": ("Comma-separated, without or with #, for example: mijnstad, nl-zuid. They are added to the built-in list of "
                  "about 200 common names. The channels on your radio (private ones too) are recognised by themselves; other private "
                  "channels show up as unknown.")},
    ]

    def __init__(self, bot: Any):
        super().__init__(bot)
        cfg = bot.config
        raw = cfg.get(self.config_section, "extra_names", fallback="") if cfg.has_section(self.config_section) else ""
        self.extra = [n.strip() for n in str(raw).split(",") if n.strip()]
        self._main = list(DEFAULT_NAMES) + self.extra
        self._gen = generated_names()
        self._names_sig = names_signature(self._main + self._gen)
        self._radio_sig = None
        self.table, self.signature = build_table(self._main, self._gen), self._names_sig
        self._seen: dict = {}
        self._ready = False
        self._task: Optional[asyncio.Task] = None

    async def start(self) -> None:
        ensure_tables(self.bot.db_manager)
        self._running = True
        self._task = asyncio.get_running_loop().create_task(self._loop())
        self.logger.info("Kanaalradar: gestart (%d kanaalnamen, waarvan %d vaste)", sum(len(v) for v in self.table.values()),
                         len(set(DEFAULT_NAMES + self.extra)) + 1)

    async def stop(self) -> None:
        self._running = False
        if self._task is not None:
            self._task.cancel()
            self._task = None

    async def _loop(self) -> None:
        while self._running:
            try:
                await asyncio.to_thread(self.scan)
            except asyncio.CancelledError:
                raise
            except Exception as e:  # noqa: BLE001
                self.logger.warning(f"Kanaalradar: fout bij tellen: {e}")
            await asyncio.sleep(CHECK_EVERY_S)

    def scan(self, now_ts: Optional[float] = None) -> int:
        """Count the group messages logged since last time. Returns how many new messages were counted."""
        now_ts = time.time() if now_ts is None else now_ts
        db = self.bot.db_manager
        if not self._ready:
            ensure_tables(db)
            self._ready = True
        # Channels on the radio are recognised with their own keys; a channel added on the radio is picked up here
        # (within a minute) and the days still in the packet log are counted again with it.
        radio = radio_channels(db)
        try:
            from ..bot_network import network_channels
            shared = network_channels(self.bot)   # names other bots found (trusted, or from at least two bots)
        except Exception:  # noqa: BLE001
            shared = []
        rsig = radio_signature(radio) + ("." + names_signature(shared) if shared else "")
        if rsig != self._radio_sig:
            self._radio_sig = rsig
            self.table = build_table(self._main + shared, self._gen, radio)
            self.signature = f"{self._names_sig}.{rsig}"
        if db.get_metadata(NAMES_KEY) != self.signature:
            self._recount_from_log(db)
        last_id = int(db.get_metadata(LAST_ID_KEY) or 0)
        counted = 0
        with db.connection() as conn:
            if not table_exists(conn, "packet_stream"):
                return 0
            rows = conn.execute("SELECT id, timestamp, data FROM packet_stream WHERE id > ? AND type IN ('packet', 'routing') ORDER BY id LIMIT ?",
                                (last_id, MAX_ROWS_PER_RUN)).fetchall()
            for rid, ts, data in rows:
                last_id = rid
                if '"GRP_TXT"' not in data:
                    continue
                try:
                    packet = json.loads(data)
                except ValueError:
                    continue
                if packet.get("payload_type_name") != "GRP_TXT" or not packet.get("payload_hex"):
                    continue
                key = packet.get("packet_hash") or packet["payload_hex"][:40]
                if key in self._seen:
                    continue
                self._seen[key] = ts
                label, ch = identify(packet["payload_hex"], self.table)
                if ch is None:
                    continue
                record(conn, local_day(self.bot, ts).isoformat(), label, ch, int(ts))
                counted += 1
            conn.commit()
        if rows:
            db.set_metadata(LAST_ID_KEY, str(last_id))
        cutoff = now_ts - DEDUP_WINDOW_S
        self._seen = {k: t for k, t in self._seen.items() if t >= cutoff}
        return counted

    def _recount_from_log(self, db: Any) -> None:
        """New list of names: forget the counts of the whole days still in the packet log and count those days again.

        The log starts somewhere in a day; that first day keeps its counts (recounting it would lose what happened before
        the log starts), unless it has no counts yet (a new installation, or a log that starts just before midnight)."""
        last_id = 0
        with db.connection() as conn:
            first = conn.execute("SELECT MIN(timestamp) FROM packet_stream").fetchone() if table_exists(conn, "packet_stream") else None
            if first and first[0]:
                day0 = local_day(self.bot, first[0])
                counted = conn.execute("SELECT 1 FROM channel_radar WHERE day = ? UNION SELECT 1 FROM channel_radar_other WHERE day = ? LIMIT 1",
                                       (day0.isoformat(), day0.isoformat())).fetchone()
                start = day0 if (day0 >= local_day(self.bot) or not counted) else day0 + timedelta(days=1)
                start_ts = day_start_ts(self.bot, start) if start > day0 else 0
                conn.execute("DELETE FROM channel_radar WHERE day >= ?", (start.isoformat(),))
                conn.execute("DELETE FROM channel_radar_other WHERE day >= ?", (start.isoformat(),))
                row = conn.execute("SELECT MAX(id) FROM packet_stream WHERE timestamp < ?", (start_ts,)).fetchone()
                last_id = int(row[0] or 0) if start_ts else 0
                conn.commit()
        db.set_metadata(LAST_ID_KEY, str(last_id))
        db.set_metadata(NAMES_KEY, self.signature)
        self._seen = {}
        self.logger.info("Kanaalradar: namenlijst veranderd, de dagen in het pakketlogboek worden opnieuw geteld")

