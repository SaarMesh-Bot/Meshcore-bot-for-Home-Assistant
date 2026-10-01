"""Games page speed: Mesh RPG and DX Jacht for many names in a few queries (the page took 9 s with one query set per
person). The numbers must be exactly the same as the per-person calculation. Runs in the simulated build tree."""
import configparser
import contextlib
import importlib
import logging
import os
import random
import sqlite3
import sys
import tempfile
import time
import types
from unittest.mock import MagicMock

TREE = sys.argv[1] if len(sys.argv) > 1 else os.environ["SIM_TREE"]
os.chdir(TREE)
sys.path.insert(0, TREE)
logging.basicConfig(level=logging.CRITICAL)
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


MA = imp("modules.mesh_archive")
GA = imp("modules.games_admin")


class DB:
    def __init__(self):
        self.path = tempfile.mktemp()
        self.db_path = self.path
        with self.connection() as c:
            c.execute("CREATE TABLE bot_metadata (key TEXT PRIMARY KEY, value TEXT)")
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
cfg = configparser.ConfigParser()
cfg["Bot"] = {"bot_name": "Test|🤖", "timezone": "Europe/Amsterdam"}
bot = types.SimpleNamespace(config=cfg, db_manager=db, logger=logging.getLogger("g"))
MA.ensure_archive(db)
rng = random.Random(7)
names = [f"User{i}" for i in range(1500)] + ["user5", "Echo|🤖"]          # a second spelling, and a bot
days = [f"2026-09-{d:02d}" for d in range(1, 31)]
with db.connection() as c:
    for n in names:
        for d in rng.sample(days, rng.randint(1, 12)):
            c.execute("INSERT OR IGNORE INTO community_activity (name, day, messages, commands) VALUES (?,?,?,?)",
                      (n, d, rng.randint(0, 80), rng.randint(0, 9)))
            if rng.random() < 0.3:
                c.execute("INSERT OR IGNORE INTO community_dx (name, day, hops, ts, path) VALUES (?,?,?,?,?)",
                          (n, d, rng.randint(1, 12), rng.randint(1, 10**9), "x"))
        if rng.random() < 0.2:
            c.execute("INSERT OR IGNORE INTO community_checkin (name, day, ts) VALUES (?, ?, 1)", (n, rng.choice(days)))
        if rng.random() < 0.1:
            c.execute("INSERT INTO community_karma (giver, receiver, day, ts) VALUES ('x', ?, ?, 1)", (n, rng.choice(days)))
    c.commit()

for since in (None, "2026-09-20"):
    bulk = {n.lower(): info for n, info in MA.xp_all(bot, since)}
    sample = rng.sample(sorted(bulk), 60) + ["user5"]
    same = all(MA.xp_of(bot, k, since) == bulk[k] for k in sample)
    check(same, f"xp_all geeft precies hetzelfde als xp_of per persoon (since={since})")
    check(len(bulk) == len({n.lower() for n in MA.known_names(bot, since)}), "zelfde namen als known_names")


def dx_old(since_day):
    where, params = ["1=1"], []
    if since_day:
        where.append("day >= ?"); params.append(since_day)
    with db.connection() as conn:
        rows = conn.execute(
            f"""SELECT name, hops, ts FROM community_dx d WHERE {' AND '.join(where)}
                AND hops = (SELECT MAX(hops) FROM community_dx e WHERE LOWER(e.name) = LOWER(d.name) {'AND e.day >= ?' if since_day else ''})
                ORDER BY hops DESC, ts ASC LIMIT 400""", params + ([since_day] if since_day else [])).fetchall()
    seen, out = set(), []
    for n, h, t in rows:
        if n.lower() in seen:
            continue
        seen.add(n.lower()); out.append((n, h, t))
        if len(out) >= 60:
            break
    return out


for since in (None, "2026-09-25"):
    check(MA.dx_best(bot, since) == dx_old(since), f"dx_best gelijk aan de oude vraag (since={since})")
one = MA.dx_best(bot, None, name="USER7")
with db.connection() as c:
    top7 = c.execute("SELECT MAX(hops) FROM community_dx WHERE LOWER(name) = 'user7'").fetchone()[0]
check((not one and top7 is None) or (one[0][0] == "User7" and one[0][1] == top7), f"dx_best voor één naam ({one}, {top7})")

t0 = time.time()
st = GA.standings(db, cfg)
took = time.time() - t0
check(took < 3.0, f"Games-overzicht snel genoeg met 1500 namen ({took:.2f}s)")
check(all(not r["name"].endswith("🤖") for r in st["xp"]["ever"]) and len(st["xp"]["ever"]) == GA.TOP, "top 15 zonder bots")

print(f"\n{len(fails)} fouten")
sys.exit(1 if fails else 0)
