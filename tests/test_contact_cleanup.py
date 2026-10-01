"""ContactCleanup: when the radio's list is full of repeaters that are all still heard, far repeaters make room
(trim_active_repeaters), never people, direct neighbours, repeaters meshcore-ha follows, RepeaterWatch's list,
starred or favourites. Runs in the simulated build tree: test_contact_cleanup.py <tree>."""
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


C = imp("modules.service_plugins.contact_cleanup_service")
now = time.time()


def contact(key, typ, hours_ago, hops, flags=0):
    return {"public_key": key, "type": typ, "last_advert": int(now - hours_ago * 3600), "out_path_len": hops, "flags": flags}


contacts = {}
for i in range(6):                                  # six active repeaters, 1..6 hops
    k = f"a{i}" + "0" * 62
    contacts[k] = contact(k, 2, 1, i + 1)
contacts["b0" + "0" * 62] = contact("b0" + "0" * 62, 2, 1, -1)          # active, path unknown = far
contacts["c0" + "0" * 62] = contact("c0" + "0" * 62, 1, 2, 3)           # a person, active
contacts["d0" + "0" * 62] = contact("d0" + "0" * 62, 3, 2, 5)           # room server, active
contacts["e0" + "0" * 62] = contact("e0" + "0" * 62, 2, 1, 9, flags=1)  # favourite repeater
contacts["f0" + "0" * 62] = contact("f0" + "0" * 62, 2, 24 * 20, 2)     # quiet repeater (20 days)
contacts["a5aa" + "0" * 60] = contact("a5aa" + "0" * 60, 2, 1, 8)        # followed by meshcore-ha (prefix)
rep = lambda c: c["type"] == 2

old = C.plan_cleanup(contacts, set(), target=len(contacts) - 4, keep_days=7, now=now, is_repeater=rep)
check([c["public_key"][:2] for c in old] == ["f0"], f"zonder de nieuwe keuze: alleen de stille repeater kan weg ({[c['public_key'][:2] for c in old]})")

new = C.plan_cleanup(contacts, set(), target=len(contacts) - 4, keep_days=7, now=now, is_repeater=rep,
                     trim_active_repeaters=True, protected_prefixes=("a5aa",))
got = [c["public_key"][:4] for c in new]
check(got == ["f000", "b000", "a500", "a400"], f"stille eerst, dan de verste actieve (onbekend pad = ver) ({got})")
all_keys = [c["public_key"][:2] for c in C.plan_cleanup(contacts, set(), target=0, keep_days=7, now=now, is_repeater=rep,
                                                        trim_active_repeaters=True, protected_prefixes=("a5aa",))]
check("c0" not in all_keys and "d0" not in all_keys, "personen en room servers die actief zijn blijven altijd")
check("e0" not in all_keys, "favoriet blijft")
check(not any(c["public_key"].startswith("a5aa") for c in C.plan_cleanup(contacts, set(), target=0, keep_days=7, now=now,
      is_repeater=rep, trim_active_repeaters=True, protected_prefixes=("a5aa",))), "repeater die meshcore-ha volgt blijft")


# ---------------------------------------------------------------- the service: what it protects
class DB:
    def __init__(self):
        self.path = tempfile.mktemp()

    @contextlib.contextmanager
    def connection(self):
        c = sqlite3.connect(self.path)
        try:
            yield c
        finally:
            c.close()


db = DB()
with db.connection() as c:
    c.execute("CREATE TABLE repeater_telemetry (repeater_key TEXT, recorded_at INTEGER)")
    c.execute("INSERT INTO repeater_telemetry VALUES ('a1b2c3d4e5', ?)", (int(now),))
    c.execute("INSERT INTO repeater_telemetry VALUES ('0ld0ld0ld0', ?)", (int(now) - 90 * 86400,))
    c.execute("CREATE TABLE neighbor_links (neighbor_public_key TEXT, last_seen TIMESTAMP)")
    c.execute("INSERT INTO neighbor_links VALUES (?, datetime('now'))", ("d1e2f3" + "1" * 58,))
    c.commit()
cfg = configparser.ConfigParser()
cfg["RepeaterWatch"] = {"extra": "984d, Naam-Repeater"}
cfg["ContactCleanup"] = {"enabled": "true"}
svc = C.ContactCleanupService.__new__(C.ContactCleanupService)
svc.bot = types.SimpleNamespace(config=cfg, db_manager=db)
svc.logger = logging.getLogger("cc")
pre = svc._protected_prefixes()
check("a1b2c3d4e5" in pre and "0ld0ld0ld0" not in pre, f"meshcore-ha-repeaters van de laatste 30 dagen ({pre})")
check("d1e2f3111111" in pre and "984d" in pre, "directe buren en RepeaterWatch-voorvoegsels")
check(C.ContactCleanupService.__init__ and any(f["key"] == "trim_active_repeaters" and f["default"] is True
      for f in C.ContactCleanupService.settings_schema), "kaartveld, standaard aan")

print(f"\n{len(fails)} fouten")
sys.exit(1 if fails else 0)
