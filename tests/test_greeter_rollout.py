"""Greeter rollout runs once (patch_greeter_rollout_once.py): the first start begins a rollout, an expired rollout is
closed without starting a new one, and a rollout that ended long ago does not come back."""
import configparser
import contextlib
import logging
import os
import sqlite3
import sys
import tempfile
from unittest.mock import MagicMock

TREE = sys.argv[1]
os.chdir(TREE)
sys.path.insert(0, TREE)
logging.basicConfig(level=logging.ERROR)

fails = []


def check(cond, msg):
    print(("OK   " if cond else "FAIL ") + msg)
    if not cond:
        fails.append(msg)


from modules.commands.greeter_command import GreeterCommand  # noqa: E402


class DBM:
    def __init__(self, path):
        self.db_path = path

    @contextlib.contextmanager
    def connection(self):
        c = sqlite3.connect(self.db_path)
        try:
            yield c
        finally:
            c.close()

    def get_metadata(self, k):
        return None

    def set_metadata(self, k, v):
        pass


def greeter(db, days="7"):
    cfg = configparser.ConfigParser()
    cfg["Bot"] = {"bot_name": "Mesh|HA|🤖"}
    cfg["Channels"] = {"monitor_channels": "#test"}
    cfg["Greeter_Command"] = {"enabled": "true", "rollout_days": days, "channels": "Publiek"}
    bot = MagicMock()
    bot.config, bot.logger, bot.db_manager = cfg, logging.getLogger("greeter"), db
    return GreeterCommand(bot)


def rows(db):
    with db.connection() as c:
        return c.execute("SELECT id, rollout_completed FROM greeter_rollout ORDER BY id").fetchall()


def age(db, rid, days):
    with db.connection() as c:
        c.execute(f"UPDATE greeter_rollout SET rollout_started_at = datetime('now', '-{days} days') WHERE id = ?", (rid,))
        c.commit()


db = DBM(tempfile.mktemp())
g = greeter(db)
check(rows(db) == [(1, 0)] and g._is_rollout_active(), "eerste start: inloopperiode begint (bekende mensen alleen onthouden)")
greeter(db)
check(rows(db) == [(1, 0)], "herstart tijdens de inloopperiode: dezelfde, geen nieuwe")
age(db, 1, 8)
g = greeter(db)
check(rows(db) == [(1, 1)] and not g._is_rollout_active(), "verlopen: afgesloten, GEEN nieuwe inloopperiode (upstream begon opnieuw)")
age(db, 1, 30)
greeter(db)
check(rows(db) == [(1, 1)], "lang na het einde: geen nieuwe inloopperiode (upstream: elke week opnieuw)")
with db.connection() as c:
    c.execute("UPDATE greeter_rollout SET rollout_completed = 1")
    c.commit()
greeter(db)
check(rows(db) == [(1, 1)], "met de hand beëindigd: komt niet terug")
fresh = DBM(tempfile.mktemp())
greeter(fresh, days="0")
check(rows(fresh) == [], "rollout_days 0: nooit een inloopperiode")
g = greeter(db)
check(g.start_rollout(days=3, backfill_first=False) and rows(db) == [(1, 1), (2, 0)], "met de hand starten (dashboard) werkt nog")

print(f"\n{len(fails)} fouten")
sys.exit(1 if fails else 0)
