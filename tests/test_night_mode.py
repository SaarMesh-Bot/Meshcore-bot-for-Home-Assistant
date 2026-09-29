"""Night mode (modules/night_mode.py + patch_night_mode.py): scheduled messages, feeds and the webhook quiet at night.

Runs in the simulated build tree (patched upstream + our modules), like the other tests: usage test_night_mode.py <tree>.
"""
import asyncio
import configparser
import contextlib
import json
import logging
import os
import sqlite3
import sys
import tempfile
import time
import types
from datetime import timedelta

TREE = sys.argv[1] if len(sys.argv) > 1 else os.getcwd()
sys.path.insert(0, TREE)
os.chdir(TREE)

from modules import night_mode as N  # noqa: E402
from modules.mesh_community import day_start_ts, local_day, local_now  # noqa: E402

fails = []


def check(cond, msg):
    print(("OK   " if cond else "FAIL ") + msg)
    if not cond:
        fails.append(msg)


class DB:
    def __init__(self, path):
        self.db_path = path

    @contextlib.contextmanager
    def connection(self):
        c = sqlite3.connect(self.db_path)
        try:
            yield c
        finally:
            c.close()


def make_bot(night=None, db=None):
    cfg = configparser.ConfigParser()
    cfg["Bot"] = {"bot_name": "X", "timezone": "Europe/Amsterdam"}
    if night is not None:
        cfg["NightMode"] = night
    return types.SimpleNamespace(config=cfg, logger=logging.getLogger("night"), db_manager=db, connected=True)


def hm(minutes):
    minutes %= 24 * 60
    return f"{minutes // 60:02d}:{minutes % 60:02d}"


# ---------------------------------------------------------------- the rule
b = make_bot({"enabled": "true", "start": "23:00", "end": "07:00"})
day = local_day(b) + timedelta(days=1)
at = lambda h, m=0: day_start_ts(b, day) + h * 3600 + m * 60
check(N.is_night(b, at(23, 30)) and N.is_night(b, at(3)) and N.is_night(b, at(6, 59)), "23:00-07:00: 23:30, 03:00 en 06:59 zijn nacht (over middernacht)")
check(not N.is_night(b, at(7)) and not N.is_night(b, at(12)) and not N.is_night(b, at(22, 59)), "07:00, 12:00 en 22:59 zijn dag")
b2 = make_bot({"enabled": "true", "start": "01:00", "end": "05:30"})
check(N.is_night(b2, at(1)) and N.is_night(b2, at(5, 29)) and not N.is_night(b2, at(5, 30)) and not N.is_night(b2, at(0, 30)), "01:00-05:30 binnen één dag")
check(not N.is_night(make_bot({"enabled": "false"}), at(3)) and not N.is_night(make_bot(None), at(3)), "uit of geen kaart: nooit nacht")
check(N.window(make_bot({"enabled": "true", "start": "25:99", "end": "x"})) == (23 * 60, 7 * 60), "onzin-tijden: terug naar 23:00-07:00")
check(N.window(make_bot({"enabled": "true", "start": "22.30", "end": "6:15"})) == (22 * 60 + 30, 6 * 60 + 15), "22.30 en 6:15 worden begrepen")
check(N.window(make_bot({"enabled": "true", "start": "07:00", "end": "07:00"})) is None, "begin = eind: geen nacht")
check(N.quiet(b, "scheduled", at(3)) and N.quiet(b, "feeds", at(3)) and not N.quiet(b, "webhook", at(3)),
      "standaard 's nachts stil: geplande berichten en feeds, de webhook niet")
b3 = make_bot({"enabled": "true", "start": "23:00", "end": "07:00", "scheduled": "false", "webhook": "true"})
check(not N.quiet(b3, "scheduled", at(3)) and N.quiet(b3, "webhook", at(3)) and not N.quiet(b3, "webhook", at(12)), "per soort aan en uit te zetten")
check(not N.quiet(b, "commands", at(3)), "onbekende soort (antwoorden aan mensen) wordt nooit stilgehouden")

# a window around "now", for the patched code (it asks without a time)
minute = local_now(b).hour * 60 + local_now(b).minute
NIGHT = {"enabled": "true", "start": hm(minute - 60), "end": hm(minute + 60), "webhook": "true"}
DAY = {"enabled": "true", "start": hm(minute + 120), "end": hm(minute + 180), "webhook": "true"}
check(N.is_night(make_bot(NIGHT)) and not N.is_night(make_bot(DAY)), "testvensters rond nu kloppen")


# ---------------------------------------------------------------- scheduled messages
async def scheduled(night):
    from modules.scheduler import MessageScheduler as Scheduler
    s = Scheduler.__new__(Scheduler)
    sent = []

    async def send(channel, message, **kw):
        sent.append((channel, message))
        return True
    s.bot = make_bot(night)
    s.bot.command_manager = types.SimpleNamespace(send_channel_message=send)
    s.logger = logging.getLogger("sched")
    s._scheduled_message_stagger_seconds = lambda key: 0
    s._has_command_placeholders = lambda m: False
    s._has_mesh_info_placeholders = lambda m: False
    s._effective_send_scope = lambda c, sc: None
    s._channel_body_budget = lambda sc: 130
    s._split_to_budget = lambda m, n: [m]
    await s._send_scheduled_message_async("#test", "Goedemorgen")
    return sent

try:
    check(asyncio.run(scheduled(NIGHT)) == [], "gepland bericht 's nachts: niet verstuurd")
    check(asyncio.run(scheduled(DAY)) == [("#test", "Goedemorgen")], "gepland bericht overdag: verstuurd")
except ImportError as e:
    check(False, f"scheduler niet te laden: {e}")


# ---------------------------------------------------------------- feeds
async def feeds(night):
    from modules.feed_manager import FeedManager
    tmp = tempfile.mkdtemp()
    db = DB(f"{tmp}/f.db")
    with db.connection() as c:
        c.execute("CREATE TABLE feed_subscriptions (id INTEGER PRIMARY KEY, message_send_interval_seconds REAL)")
        c.execute("""CREATE TABLE feed_message_queue (id INTEGER PRIMARY KEY, feed_id INTEGER, channel_name TEXT, message TEXT,
                     item_id TEXT, item_title TEXT, priority INTEGER DEFAULT 0, queued_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                     sent_at TIMESTAMP)""")
        c.execute("INSERT INTO feed_subscriptions VALUES (1, 0)")
        c.executemany("INSERT INTO feed_message_queue (feed_id, channel_name, message, item_id, item_title) VALUES (1, '#test', ?, ?, ?)",
                      [("nieuws 1", "a", "A"), ("nieuws 2", "b", "B")])
        c.commit()
    f = FeedManager.__new__(FeedManager)
    sent = []

    async def send(channel, message, **kw):
        sent.append(message)
        return True
    f.bot = make_bot(night, db)
    f.bot.command_manager = types.SimpleNamespace(send_channel_message=send)
    f.logger = logging.getLogger("feed")
    f.db_path = db.db_path
    f._feed_last_send = {}
    f.default_send_interval = 0
    await f._process_message_queue_inner()
    with db.connection() as c:
        left = c.execute("SELECT COUNT(*) FROM feed_message_queue WHERE sent_at IS NULL").fetchone()[0]
    return sent, left

sent, left = asyncio.run(feeds(NIGHT))
check(sent == [] and left == 0, f"feeds 's nachts: niets verstuurd en afgehandeld, dus 's ochtends geen stapel ({sent}, {left} over)")
sent, left = asyncio.run(feeds(DAY))
check(sent[:1] == ["nieuws 1"], f"feeds overdag: gewoon verstuurd ({sent})")


# ---------------------------------------------------------------- webhook
async def webhook(night, enabled_for_webhook=True):
    from modules.service_plugins.webhook_service import WebhookService
    w = WebhookService.__new__(WebhookService)
    sent = []

    async def send(channel, message, **kw):
        sent.append(message)
        return True
    cfg = dict(night)
    cfg["webhook"] = "true" if enabled_for_webhook else "false"
    w.bot = make_bot(cfg)
    w.logger = logging.getLogger("webhook")
    w._is_rate_limited = lambda ip: False
    w.secret_token = ""
    w.max_message_length = 130
    w.allowed_channels = set()
    w.get_mesh_flood_scope = lambda: None
    w._send_channel_message = lambda channel, text, scope=None: send(channel, text)

    class Req:
        remote = "127.0.0.1"
        headers = {}

        async def json(self):
            return {"channel": "test", "message": "P2000 melding"}
    resp = await w._handle_webhook(Req())
    return resp.status, resp.text, sent

status, text, sent = asyncio.run(webhook(NIGHT))
check(status == 200 and json.loads(text) == {"skipped": "night mode"} and sent == [], f"webhook 's nachts (aangezet): 200, niets verstuurd ({status} {text})")
status, text, sent = asyncio.run(webhook(NIGHT, enabled_for_webhook=False))
check(sent == ["P2000 melding"], f"webhook 's nachts maar niet aangezet voor de webhook: gewoon verstuurd ({status}, {sent})")
status, text, sent = asyncio.run(webhook(DAY))
check(sent == ["P2000 melding"], f"webhook overdag: verstuurd ({status}, {sent})")

# ---------------------------------------------------------------- card
from modules.service_plugins.night_mode_service import NightModeService  # noqa: E402
keys = [f["key"] for f in NightModeService.settings_schema]
check(keys == ["start", "end", "scheduled", "feeds", "webhook"] and NightModeService.config_section == "NightMode", f"kaart NightMode met de juiste velden ({keys})")
defaults = {f["key"]: f["default"] for f in NightModeService.settings_schema}
check(defaults == {"start": "23:00", "end": "07:00", "scheduled": True, "feeds": True, "webhook": False}, "standaardwaarden van de kaart")

print(f"\n{len(fails)} fouten")
sys.exit(1 if fails else 0)
