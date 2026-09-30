"""RepeaterWatch: a directly heard repeater that goes silent is reported once, and 'back' when heard again; the
Notifications service passes it on as a repeater warning. Runs in the simulated build tree: test_repeater_watch.py <tree>.
"""
import asyncio
import configparser
import contextlib
import importlib
import logging
import os
import sqlite3
import sys
import tempfile
import time
import types
from unittest.mock import MagicMock

TREE = sys.argv[1] if len(sys.argv) > 1 else os.environ["SIM_TREE"]
os.chdir(TREE)
sys.path.insert(0, TREE)
logging.basicConfig(level=logging.ERROR)
fails = []


def check(cond, msg):
    print(("OK   " if cond else "FAIL ") + msg)
    if not cond:
        fails.append(msg)


def imp(name):
    for _ in range(40):
        try:
            return importlib.import_module(name)
        except ModuleNotFoundError as e:
            if e.name.split(".")[0] == "modules":
                raise
            sys.modules[e.name] = MagicMock()
            sys.modules.setdefault(e.name.split(".")[0], MagicMock())
    raise SystemExit("te veel ontbrekende modules")


W = imp("modules.service_plugins.repeater_watch_service")
N = imp("modules.service_plugins.notify_service")


class DB:
    def __init__(self):
        self.path = tempfile.mktemp()
        with self.connection() as c:
            c.execute("CREATE TABLE bot_metadata (key TEXT PRIMARY KEY, value TEXT)")
            c.execute("CREATE TABLE neighbor_links (neighbor_public_key TEXT, last_seen TIMESTAMP)")
            c.execute("CREATE TABLE complete_contact_tracking (public_key TEXT, name TEXT, role TEXT, last_heard TIMESTAMP)")
            c.commit()

    @contextlib.contextmanager
    def connection(self):
        c = sqlite3.connect(self.path)
        try:
            yield c
        finally:
            c.close()

    def get_metadata(self, k):
        with self.connection() as c:
            r = c.execute("SELECT value FROM bot_metadata WHERE key=?", (k,)).fetchone()
            return r[0] if r else None

    def set_metadata(self, k, v):
        with self.connection() as c:
            c.execute("INSERT OR REPLACE INTO bot_metadata VALUES (?,?)", (k, v)); c.commit()


db = DB()
A, B, C = "aa11" + "0" * 60, "bb22" + "0" * 60, "cc33" + "0" * 60
with db.connection() as c:
    c.execute("INSERT INTO neighbor_links VALUES (?, datetime('now','-30 hour'))", (A,))   # direct neighbour, silent 30 h
    c.execute("INSERT INTO neighbor_links VALUES (?, datetime('now','-2 hour'))", (B,))    # direct neighbour, fine
    c.executemany("INSERT INTO complete_contact_tracking VALUES (?,?,?,?)", [
        (A, "Heuvel RPT", "repeater", time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime(time.time() - 30 * 3600))),
        (B, "Dal RPT", "repeater", time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime(time.time() - 3600))),
        (C, "Ver RPT", "repeater", time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime(time.time() - 50 * 3600)))])
    c.commit()
ev = W.check(db, [], 24 * 3600)
check([(k, n) for k, _key, n, _t in ev] == [("silent", "Heuvel RPT")], f"directe buur 30 uur stil: gemeld, niet-buur niet ({ev})")
check(W.check(db, [], 24 * 3600) == [], "één keer per stilte: tweede controle meldt niets")
ev = W.check(db, ["ver rpt"], 24 * 3600)
check([(k, n) for k, _key, n, _t in ev] == [("silent", "Ver RPT")], "extra op de kaart (naam): ook bewaakt")
with db.connection() as c:
    c.execute("UPDATE complete_contact_tracking SET last_heard = datetime('now') WHERE public_key = ?", (A,)); c.commit()
ev = W.check(db, ["ver rpt"], 24 * 3600)
check([(k, n) for k, _key, n, _t in ev] == [("back", "Heuvel RPT")], f"advert weer gehoord: 'weer gehoord' ({ev})")

# the service logs the warning the Notifications service picks up
cfg = configparser.ConfigParser(); cfg["RepeaterWatch"] = {"enabled": "true", "silent_hours": "24", "ha_notification": "false"}
logs = []


class L:
    def warning(self, m, *a): logs.append(("W", m % a))
    def info(self, m, *a): logs.append(("I", m % a))
    def debug(self, *a): pass


svc = W.RepeaterWatchService.__new__(W.RepeaterWatchService)
svc.bot, svc.logger, svc.extra, svc.silent_s, svc.ha_notification = types.SimpleNamespace(config=cfg, db_manager=db), L(), ["ver rpt"], 24 * 3600, False
with db.connection() as c:
    c.execute("UPDATE complete_contact_tracking SET last_heard = datetime('now','-40 hour') WHERE public_key = ?", (B,))
    c.execute("UPDATE neighbor_links SET last_seen = datetime('now','-40 hour') WHERE neighbor_public_key = ?", (B,)); c.commit()
asyncio.run(svc.run_check())
check(any(k == "W" and m.startswith("RepeaterWatch: stil: Dal RPT niet meer gehoord sinds ") for k, m in logs), f"waarschuwing in het logboek ({logs})")
line = [m for k, m in logs if k == "W"][0]
ns = N.NotifyService.__new__(N.NotifyService)
ns._radio_problem, ns.min_level, ns._last_origin, ns._last_admin = False, logging.ERROR, (0, "", ""), (0.0, "")
cat = ns._classify(logging.WARNING, line, time.time())
check(cat and cat[0] == "repeater" and cat[1].startswith("Repeater stil: Dal RPT"), f"Notifications herkent hem als repeatermelding ({cat})")

print(f"\n{len(fails)} fouten")
sys.exit(1 if fails else 0)
