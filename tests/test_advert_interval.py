"""Interval advert (patch_advert_interval.py): the time of the last interval advert is kept in the database, so a
restart does not start the count again. Runs in the simulated build tree: test_advert_interval.py <tree>."""
import configparser
import importlib
import logging
import os
import sys
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


S = imp("modules.scheduler")
meta = {}
db = types.SimpleNamespace(get_metadata=lambda k: meta.get(k), set_metadata=lambda k, v: meta.__setitem__(k, v))


def bot(hours=12):
    cfg = configparser.ConfigParser()
    cfg["Bot"] = {"advert_interval_hours": str(hours)}
    return types.SimpleNamespace(config=cfg, db_manager=db, logger=logging.getLogger("s"))


def scheduler(b):
    sc = S.MessageScheduler.__new__(S.MessageScheduler) if hasattr(S, "MessageScheduler") else None
    if sc is None:
        cls = next(v for v in vars(S).values() if isinstance(v, type) and hasattr(v, "check_interval_advertising"))
        sc = cls.__new__(cls)
    sc.bot, sc.logger = b, logging.getLogger("s")
    sc.sent = []
    sc.send_interval_advert = lambda: sc.sent.append(1)
    return sc


real_time = S.time.time
now = [1_790_000_000.0]
S.time.time = lambda: now[0]

b = bot(); sc = scheduler(b)
sc.check_interval_advertising()
check(not sc.sent and b.last_advert_time == now[0], "eerste start zonder geschiedenis: timer begint, nog geen advert")
now[0] += 12 * 3600
sc.check_interval_advertising()
check(sc.sent == [1] and meta.get("advert.last_interval") == str(int(now[0])), "na 12 uur: advert, tijdstip in de database")

# restart 11 hours later: the count goes on, the next advert 1 hour after the restart (not 12)
now[0] += 11 * 3600
b2 = bot(); sc2 = scheduler(b2)
sc2.check_interval_advertising()
check(not sc2.sent, "herstart na 11 uur: nog geen advert")
now[0] += 3600 + 1
sc2.check_interval_advertising()
check(sc2.sent == [1], "een uur later: advert (de telling liep door)")

# restart long after the last advert: the advert comes 5 minutes after the start, not at once
now[0] += 48 * 3600
b3 = bot(); sc3 = scheduler(b3)
sc3.check_interval_advertising()
now[0] += 60
sc3.check_interval_advertising()
check(not sc3.sent, "lang na de vorige advert: niet meteen bij de start")
now[0] += 300
sc3.check_interval_advertising()
check(sc3.sent == [1], "maar wel 5 minuten na de start")

b4 = bot(0); sc4 = scheduler(b4); now[0] += 99 * 3600
sc4.check_interval_advertising()
check(not sc4.sent, "0 = uit")
S.time.time = real_time

print(f"\n{len(fails)} fouten")
sys.exit(1 if fails else 0)
